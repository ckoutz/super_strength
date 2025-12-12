import xml.etree.ElementTree as ET
from datetime import datetime


def parse_tcx(file_obj):
    """
    Robust TCX parser that extracts:
    - duration (sec)
    - distance (meters)
    - avg HR
    - max HR
    - avg cadence
    - elevation gain (meters)
    - pace (min/km)
    - HR drift
    """

    try:
        tree = ET.parse(file_obj)
        root = tree.getroot()
    except Exception:
        return None

    ns = {"tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}

    trackpoints = root.findall(".//tcx:Trackpoint", ns)
    if not trackpoints:
        return None

    times = []
    hrs = []
    cadence = []
    altitude = []
    distance = []

    for tp in trackpoints:
        # Time
        t = tp.find("tcx:Time", ns)
        if t is not None and t.text:
            try:
                times.append(datetime.fromisoformat(t.text.replace("Z", "+00:00")))
            except:
                pass

        # HR
        hr = tp.find("tcx:HeartRateBpm/tcx:Value", ns)
        if hr is not None and hr.text:
            try:
                hrs.append(float(hr.text))
            except:
                pass

        # Cadence
        cad = tp.find("tcx:Cadence", ns)
        if cad is not None and cad.text:
            try:
                cadence.append(float(cad.text))
            except:
                pass

        # Altitude
        alt = tp.find("tcx:AltitudeMeters", ns)
        if alt is not None and alt.text:
            try:
                altitude.append(float(alt.text))
            except:
                pass

        # Distance
        dist = tp.find("tcx:DistanceMeters", ns)
        if dist is not None and dist.text:
            try:
                distance.append(float(dist.text))
            except:
                pass

    if len(times) < 2:
        return None

    # Duration
    duration_sec = (times[-1] - times[0]).total_seconds()

    # Distance
    total_distance = distance[-1] if distance else 0.0

    # HR
    avg_hr = sum(hrs) / len(hrs) if hrs else 0
    max_hr = max(hrs) if hrs else 0

    # Cadence
    avg_cad = sum(cadence) / len(cadence) if cadence else 0

    # Elevation gain
    elev_gain = 0
    for i in range(1, len(altitude)):
        diff = altitude[i] - altitude[i - 1]
        if diff > 0:
            elev_gain += diff

    # Pace (min/km)
    if total_distance > 0:
        pace_min_per_km = (duration_sec / 60) / (total_distance / 1000)
    else:
        pace_min_per_km = 0

    # HR drift
    if hrs:
        half = len(hrs) // 2
        if half > 0:
            first = sum(hrs[:half]) / half
            second = sum(hrs[half:]) / (len(hrs) - half)
            hr_drift = (second - first) / first if first > 0 else 0
        else:
            hr_drift = 0
    else:
        hr_drift = 0

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


# ---------------------------------------------------------
# The missing wrapper your app expects
# ---------------------------------------------------------

def load_tcx_from_upload(uploaded_file):
    """
    Wrapper so the Streamlit app can call parse_tcx(uploaded_file)
    even when uploaded_file is an UploadedFile object.
    """
    try:
        return parse_tcx(uploaded_file)
    except Exception:
        return None
