import xml.etree.ElementTree as ET
from datetime import datetime


# =====================================================================
# INTERNAL TCX PROCESSOR (core logic)
# =====================================================================
def _parse_tcx_tree(root):
    """
    Process an XML tree and extract all metrics.
    Used by both file-object and text parsing paths.
    """

    ns = {"tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
    trackpoints = root.findall(".//tcx:Trackpoint", ns)

    if not trackpoints:
        return None

    times = []
    hrs = []
    cadence = []
    altitude = []
    distance = []

    # ------------------------------
    # Extract fields
    # ------------------------------
    for tp in trackpoints:

        # Time
        t = tp.find("tcx:Time", ns)
        if t is not None and t.text:
            try:
                times.append(datetime.fromisoformat(t.text.replace("Z", "+00:00")))
            except Exception:
                pass

        # Heart Rate
        hr = tp.find("tcx:HeartRateBpm/tcx:Value", ns)
        if hr is not None and hr.text:
            try:
                hrs.append(float(hr.text))
            except Exception:
                pass

        # Cadence
        cad = tp.find("tcx:Cadence", ns)
        if cad is not None and cad.text:
            try:
                cadence.append(float(cad.text))
            except Exception:
                pass

        # Altitude
        alt = tp.find("tcx:AltitudeMeters", ns)
        if alt is not None and alt.text:
            try:
                altitude.append(float(alt.text))
            except Exception:
                pass

        # Distance
        dist = tp.find("tcx:DistanceMeters", ns)
        if dist is not None and dist.text:
            try:
                distance.append(float(dist.text))
            except Exception:
                pass

    if len(times) < 2:
        return None

    # ------------------------------
    # Duration
    # ------------------------------
    duration_sec = (times[-1] - times[0]).total_seconds()

    # ------------------------------
    # Distance
    # ------------------------------
    total_distance = distance[-1] if distance else 0.0

    # ------------------------------
    # Heart Rate stats
    # ------------------------------
    avg_hr = sum(hrs) / len(hrs) if hrs else 0
    max_hr = max(hrs) if hrs else 0

    # ------------------------------
    # Cadence
    # ------------------------------
    avg_cad = sum(cadence) / len(cadence) if cadence else 0

    # ------------------------------
    # Elevation Gain
    # ------------------------------
    elev_gain = 0
    for i in range(1, len(altitude)):
        diff = altitude[i] - altitude[i - 1]
        if diff > 0:
            elev_gain += diff

    # ------------------------------
    # Pace (min per km)
    # ------------------------------
    if total_distance > 0:
        pace_min_per_km = (duration_sec / 60) / (total_distance / 1000)
    else:
        pace_min_per_km = 0

    # ------------------------------
    # HR Drift
    # ------------------------------
    if hrs:
        half = len(hrs) // 2
        if half > 0:
            first_half = sum(hrs[:half]) / half
            second_half = sum(hrs[half:]) / (len(hrs) - half)
            if first_half > 0:
                hr_drift = (second_half - first_half) / first_half
            else:
                hr_drift = 0
        else:
            hr_drift = 0
    else:
        hr_drift = 0

    # ------------------------------
    # Return structured output
    # ------------------------------
    return {
        "duration_sec": round(duration_sec, 2),
        "distance_m": round(total_distance, 2),
        "avg_hr": round(avg_hr, 2),
        "max_hr": round(max_hr, 2),
        "avg_cadence": round(avg_cad, 2),
        "elevation_gain_m": round(elev_gain, 2),
        "pace_min_per_km": round(pace_min_per_km, 3),
        "hr_drift": round(hr_drift, 4),
    }


# =====================================================================
# FILE-OBJECT PARSER (desktop browsers)
# =====================================================================
def parse_tcx(file_obj):
    """
    Parses TCX from a real file object (works on desktop browsers).
    """
    try:
        tree = ET.parse(file_obj)
        root = tree.getroot()
        return _parse_tcx_tree(root)
    except Exception:
        return None


# =====================================================================
# TEXT/XML PARSER (needed for iPhone Safari uploads)
# =====================================================================
def parse_tcx_text(text: str):
    """
    Parse TCX from raw XML text.

    iPhone Safari often sends the uploaded file as a TEXT blob,
    not a real file stream — this handles that case.
    """
    try:
        root = ET.fromstring(text)
        return _parse_tcx_tree(root)
    except Exception:
        return None


# =====================================================================
# UNIFIED FRONT-END WRAPPER (use this from app.py)
# =====================================================================
def load_tcx_from_upload(upload):
    """
    Safely parses TCX uploads from ALL devices:
        - Desktop browsers (file object → parse_tcx)
        - iPhone Safari (raw text → parse_tcx_text)

    Returns None if parsing failed.
    """

    if upload is None:
        return None

    # ---- Try normal file-object parsing first
    parsed = parse_tcx(upload)
    if parsed:
        return parsed

    # ---- If that fails, try raw text parsing (iPhone)
    try:
        upload.seek(0)
        raw = upload.read()
        text = raw.decode("utf-8", errors="ignore")
        return parse_tcx_text(text)
    except Exception:
        return None
