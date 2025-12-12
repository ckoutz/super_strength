import ast
from datetime import date
from typing import Dict, Any, List, Optional

import streamlit as st

from utils.load_json import load_workouts, load_exercises, load_phases
from utils.get_today_plan import get_today_plan
from utils.tcx_parser import load_tcx_from_upload
from utils.hypertrophy import (
    get_hypertrophy_suggestions,
    load_log as load_training_log,
    get_last_strength_entry,
)
from utils.save_log import save_log_row




# --------------------------------------------------------------------
# PATHS / LOAD DATA
# --------------------------------------------------------------------
WORKOUTS_PATH = "data/workouts.json"
EXERCISES_PATH = "data/exercises.json"
PHASES_FOLDER = "data/phases"

workouts_raw = load_workouts(WORKOUTS_PATH)
exercises = load_exercises(EXERCISES_PATH)
phases = load_phases(PHASES_FOLDER)

# Flatten workouts: {"workout_A": {...}, "Z2_run": {...}, ...}
workouts: Dict[str, Dict[str, Any]] = {}
if isinstance(workouts_raw, dict):
    for category, group in workouts_raw.items():
        if isinstance(group, dict):
            for wid, wdata in group.items():
                workouts[str(wid)] = wdata

# Full training log (used for “last time you did this”)
df_log = load_training_log()


# --------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------
def is_strength_workout(w: Dict[str, Any]) -> bool:
    return w.get("display_type") == "strength_block"


def is_cardio_workout(w: Dict[str, Any]) -> bool:
    dt = str(w.get("display_type", ""))
    if dt.startswith("cardio") or dt.startswith("swim") or dt == "brick_dual":
        return True
    if dt in ["recovery", "mobility"]:
        return True
    return False


def summarize_workout_line(w: Dict[str, Any]) -> str:
    """
    One clean line showing primary + accessory lifts:
    Bench Press · Romanian Deadlift · Incline Press · Laterals · Rear Delt Fly · Triceps · Hammer Curl
    """
    if not w:
        return "[Missing]"

    names: List[str] = []

    if is_strength_workout(w):
        for blk_key in ["primary", "accessories"]:
            for e in w.get(blk_key, []):
                ex_id = e.get("exercise_id")
                if not ex_id:
                    continue
                ex_def = exercises.get(ex_id, {})
                names.append(ex_def.get("name", ex_id))
    else:
        # For cardio / other, just use the workout name + focus
        nm = w.get("name", "")
        focus = w.get("focus", "")
        if nm:
            names.append(nm)
        if focus:
            names.append(focus)

    # De-duplicate but keep order
    seen = set()
    clean = []
    for n in names:
        if n not in seen:
            seen.add(n)
            clean.append(n)

    return " · ".join(clean) if clean else "[No exercise list]"


def default_duration_minutes(raw) -> int:
    """Turn duration_min (which might be '30–45') into an int default."""
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str):
        s = raw.replace("–", "-")
        if "-" in s:
            low, _ = s.split("-", 1)
            try:
                return int(low.strip())
            except Exception:
                return 0
        try:
            return int(s.strip())
        except Exception:
            return 0
    return 0


def get_variant_options(ex_id: str, ex_def: Dict[str, Any]) -> List[str]:
    """
    Build list of variant labels for an exercise from exercises.json.
    Uses full_gym / hotel_gym / no_equipment plus the base name.
    """
    variants: List[str] = []
    for key in ["full_gym", "hotel_gym", "no_equipment"]:
        v = ex_def.get(key)
        if v:
            variants.append(v)

    base_name = ex_def.get("name", ex_id)
    if base_name:
        variants.append(base_name)

    # De-duplicate
    seen = set()
    clean = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            clean.append(v)
    return clean if clean else [base_name]


def strength_exercise_ids() -> List[str]:
    """All strength-category exercises from exercises.json."""
    ids = []
    for ex_id, ex_def in exercises.items():
        if ex_def.get("category") == "strength":
            ids.append(ex_id)
    return ids


def cardio_workout_ids() -> List[str]:
    """All cardio-type workouts from workouts.json."""
    ids = []
    for wid, w in workouts.items():
        if is_cardio_workout(w):
            ids.append(wid)
    return ids


def parse_strength_block_from_log(str_block_str: str) -> List[Dict[str, Any]]:
    if not isinstance(str_block_str, str) or not str_block_str.strip():
        return []
    try:
        data = ast.literal_eval(str_block_str)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def parse_cardio_sessions_from_log(cardio_str: str) -> List[Dict[str, Any]]:
    if not isinstance(cardio_str, str) or not cardio_str.strip():
        return []
    try:
        data = ast.literal_eval(cardio_str)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def load_existing_day(selected_date: date) -> Optional[Dict[str, Any]]:
    """Return last saved row for this date, or None."""
    if df_log.empty or "date" not in df_log.columns:
        return None
    df_day = df_log[df_log["date"] == selected_date]
    if df_day.empty:
        return None
    row = df_day.sort_values("date").iloc[-1].to_dict()
    # Normalize nested fields
    row["strength_block"] = parse_strength_block_from_log(row.get("strength_block", ""))
    row["cardio_sessions"] = parse_cardio_sessions_from_log(row.get("cardio_sessions", ""))
    return row


def find_saved_strength_for_ex(saved_strength: List[Dict[str, Any]], ex_id: str, origin: str) -> Optional[Dict[str, Any]]:
    """
    Try to find a previous log entry for this exercise_id and origin ('primary','secondary','manual','extra').
    Falls back to any matching exercise_id if origin not found.
    """
    if not saved_strength:
        return None
    # Try strict match on origin
    for e in saved_strength:
        if e.get("exercise_id") == ex_id and e.get("origin") == origin:
            return e
    # Fallback: any match
    for e in saved_strength:
        if e.get("exercise_id") == ex_id:
            return e
    return None


def find_saved_cardio_for_wid(saved_cardio: List[Dict[str, Any]], workout_id: str, origin: str) -> Optional[Dict[str, Any]]:
    if not saved_cardio:
        return None
    for c in saved_cardio:
        if c.get("workout_id") == workout_id and c.get("origin") == origin:
            return c
    for c in saved_cardio:
        if c.get("workout_id") == workout_id:
            return c
    return None


# --------------------------------------------------------------------
# STREAMLIT CONFIG
# --------------------------------------------------------------------
st.set_page_config(page_title="Training App", layout="centered")
st.title("Daily Training")


# --------------------------------------------------------------------
# DATE / PLAN / MODE
# --------------------------------------------------------------------
selected_date = st.date_input("Select date", value=date.today())
phase_name, primary_id, secondary_ids = get_today_plan(selected_date, phases)

saved_day = load_existing_day(selected_date)
saved_strength = saved_day.get("strength_block", []) if saved_day else []
saved_cardio = saved_day.get("cardio_sessions", []) if saved_day else []

scheduled_ids: List[str] = []
if primary_id:
    scheduled_ids.append(primary_id)
if secondary_ids:
    scheduled_ids.extend(secondary_ids)

existing_ids = [wid for wid in scheduled_ids if wid in workouts]
missing_ids = [wid for wid in scheduled_ids if wid not in workouts]

st.header(f"Phase: {phase_name}")

if missing_ids:
    st.warning(f"These workout IDs are referenced in the phase plan but missing in workouts.json: {missing_ids}")

primary_workout = workouts.get(primary_id) if primary_id in workouts else None
secondary_workouts = [workouts[w_id] for w_id in existing_ids[1:] if w_id in workouts]

# Mode selection
mode_options: List[str] = []
mode_map: Dict[str, str] = {}

if primary_workout:
    planned_label = f"Planned – {primary_workout.get('name', primary_id)}"
    mode_options.append(planned_label)
    mode_map[planned_label] = "planned"

manual_label = "Manual Day"
rest_label = "Rest Day"

mode_options.append(manual_label)
mode_map[manual_label] = "manual"
mode_options.append(rest_label)
mode_map[rest_label] = "rest"

default_mode_index = 0
if saved_day:
    # If there was no strength/cardio logged and maybe notes only, we could infer rest/manual, but keep it simple.
    pass

mode_label = st.selectbox("Today's structure", mode_options, index=default_mode_index)
mode = mode_map[mode_label]


# --------------------------------------------------------------------
# HYPERTROPHY SUGGESTIONS FOR SCHEDULED STRENGTH (BACKGROUND ONLY)
# --------------------------------------------------------------------
strength_sched_ids = [
    wid for wid in existing_ids
    if wid in workouts and is_strength_workout(workouts[wid])
]
hypertrophy_suggestions: Dict[str, Dict[str, Any]] = {}
if strength_sched_ids:
    # We ignore fatigue here so daily log can live at bottom
    hypertrophy_suggestions = get_hypertrophy_suggestions(
        selected_date,
        strength_sched_ids,
        workouts,
        fatigue_score=None,
    )


# --------------------------------------------------------------------
# OVERVIEW
# --------------------------------------------------------------------
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Primary / Manual Plan")
    if mode == "planned" and primary_workout:
        st.markdown(f"**{primary_workout.get('name', '[Unnamed]')}**")
        st.caption(summarize_workout_line(primary_workout))
    elif mode == "manual":
        st.markdown("**Manual Day**")
        st.caption("Build your own strength and cardio sessions below.")
    else:
        st.markdown("**Rest Day**")
        st.caption("No structured training. Recovery, walking, and life things.")

with col_right:
    st.subheader("Additional Scheduled Sessions")
    if mode == "planned" and secondary_workouts:
        for w in secondary_workouts:
            st.markdown(f"- **{w.get('name', '[Unnamed]')}**")
            st.caption(summarize_workout_line(w))
    else:
        st.caption("None." if mode != "planned" else "No additional sessions today.")

st.markdown("---")


# --------------------------------------------------------------------
# LOGGING BUCKETS
# --------------------------------------------------------------------
strength_entries: List[Dict[str, Any]] = []
cardio_entries: List[Dict[str, Any]] = []


# --------------------------------------------------------------------
# HELPERS TO RENDER LOGS
# --------------------------------------------------------------------
def render_strength_exercise_block(
    origin: str,
    w_id: str,
    ex_id: str,
    block_index: int,
    base_sets: int,
    base_reps,
    base_rpe,
    ex_name: str,
    ex_def: Dict[str, Any],
    suggestion: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Render one exercise (with variant, sets, per-set reps/weight/RPE).
    Returns an entry dict suitable to append to strength_entries.
    """
    # Saved entry from previous log, if any
    saved_entry = find_saved_strength_for_ex(saved_strength, ex_id, origin)

    last_entry = get_last_strength_entry(df_log, selected_date, ex_id)

    # Variant options and default
    variants = get_variant_options(ex_id, ex_def)
    default_variant = variants[0]
    if saved_entry and saved_entry.get("variant") in variants:
        default_variant = saved_entry["variant"]
    elif last_entry and last_entry.get("variant") in variants:
        default_variant = last_entry["variant"]

    st.markdown(f"**{ex_name}**")
    if last_entry:
        st.caption(
            f"Last logged: {last_entry.get('sets')} × {last_entry.get('reps')} "
            f"@ {last_entry.get('weight')} (RPE {last_entry.get('rpe')}) on {last_entry.get('date')}"
        )

    c_var, c_sets = st.columns(2)
    variant = c_var.selectbox(
        "Variant",
        variants,
        index=variants.index(default_variant),
        key=f"{origin}_{w_id}_{ex_id}_variant_{block_index}",
    )

    # Sets default
    sug_sets = suggestion.get("sets") if suggestion else None
    default_sets = base_sets
    if saved_entry and isinstance(saved_entry.get("sets"), int):
        default_sets = saved_entry["sets"]
    elif isinstance(sug_sets, int):
        default_sets = sug_sets

    num_sets = c_sets.number_input(
        "Sets",
        min_value=1,
        max_value=10,
        value=int(default_sets),
        key=f"{origin}_{w_id}_{ex_id}_sets_{block_index}",
    )
   
    def safe_int(value, default=3):
        """
        Convert a value to int safely.
        Handles '', None, 'nan', float('nan'), etc.
        """
        try:
            if value is None:
                return default
            if isinstance(value, float) and (value != value):  # NaN check
                return default
            value_str = str(value).strip().lower()
            if value_str in ["", "nan", "none"]:
                return default
            return int(float(value))
        except Exception:
            return default


    sets_detail: List[Dict[str, Any]] = []

    # Per-set defaults
    def _get_default_for_set(field: str, s_idx: int, fallback):
        # Saved per-set first
        if saved_entry and isinstance(saved_entry.get("sets_detail"), list):
            s_list = saved_entry["sets_detail"]
            if 0 <= s_idx < len(s_list):
                val = s_list[s_idx].get(field)
                if val not in [None, ""]:
                    return str(val)
        # Otherwise suggestion or base
        if suggestion and field == "reps" and suggestion.get("reps") is not None:
            return str(suggestion["reps"])
        if suggestion and field == "rpe" and suggestion.get("target_rpe") is not None:
            return str(suggestion["target_rpe"])
        if field == "reps":
            return str(base_reps)
        if field == "rpe":
            return str(base_rpe)
        return "" if fallback is None else str(fallback)

    for s_idx in range(int(num_sets)):
        c_r, c_w, c_rpe = st.columns(3)
        reps_val = c_r.text_input(
            f"Reps (set {s_idx+1})",
            value=_get_default_for_set("reps", s_idx, base_reps),
            key=f"{origin}_{w_id}_{ex_id}_reps_{block_index}_{s_idx}",
        )
        weight_val = c_w.text_input(
            f"Weight (set {s_idx+1})",
            value=_get_default_for_set("weight", s_idx, None),
            key=f"{origin}_{w_id}_{ex_id}_wt_{block_index}_{s_idx}",
        )
        rpe_val = c_rpe.text_input(
            f"RPE (set {s_idx+1})",
            value=_get_default_for_set("rpe", s_idx, base_rpe),
            key=f"{origin}_{w_id}_{ex_id}_rpe_{block_index}_{s_idx}",
        )

        sets_detail.append(
            {
                "set_number": s_idx + 1,
                "reps": reps_val,
                "weight": weight_val,
                "rpe": rpe_val,
            }
        )

    last_set = sets_detail[-1] if sets_detail else {"reps": "", "weight": "", "rpe": ""}

    return {
        "origin": origin,
        "workout_id": w_id,
        "exercise_id": ex_id,
        "exercise_name": ex_name,
        "variant": variant,
        "sets": int(num_sets),
        "reps": last_set["reps"],
        "weight": last_set["weight"],
        "rpe": last_set["rpe"],
        "sets_detail": sets_detail,
    }


def render_cardio_block(origin: str, w_id: str, w: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Full cardio log + TCX upload + auto-fill.

    Behavior:
      - Shows workout name + description + suggested duration
      - TCX uploader appears directly under the session header
      - TCX parse can auto-populate:
          * duration
          * distance
          * avg HR
          * max HR
          * elevation gain
          * pace
          * time in zones
      - We ONLY write to st.session_state for these keys BEFORE
        their widgets are instantiated (to avoid StreamlitAPIException).
    """
    name = w.get("name", w_id)
    st.markdown(f"**{name}**")

    # Description + suggested duration
    desc = w.get("instructions", "")
    if desc:
        st.markdown(f"*{desc}*")

    dur_raw = w.get("duration_min", "")
    if dur_raw:
        st.caption(f"Suggested duration: **{dur_raw} min**")

    # Load any previously saved session for this workout/origin
    saved = find_saved_cardio_for_wid(saved_cardio, w_id, origin)

    # Base defaults (before TCX)
    default_min = default_duration_minutes(dur_raw)

    # Keys for this block
    base_key = f"{origin}_{w_id}"
    done_key = f"{base_key}_done"
    duration_key = f"{base_key}_dur"
    distance_key = f"{base_key}_dist"
    rpe_key = f"{base_key}_rpe"
    avg_key = f"{base_key}_hr"
    max_key = f"{base_key}_maxhr"
    elev_key = f"{base_key}_elev"
    notes_key = f"{base_key}_notes"

    # --------------------------
    # 1) BASELINE DEFAULT VALUES
    # --------------------------
    done_default = True if not saved else bool(saved.get("done", True))

    if saved and isinstance(saved.get("duration_min"), (int, float)):
        dur_default = int(saved["duration_min"])
    else:
        dur_default = default_min

    dist_default = str(saved.get("distance", "")) if saved else ""
    rpe_default = int(saved.get("rpe", 6)) if saved and saved.get("rpe") else 6
    avg_default = str(saved.get("avg_hr", "")) if saved else ""
    max_default = str(saved.get("max_hr", "")) if saved else ""
    elev_default = str(saved.get("elev", "")) if saved else ""
    notes_default = saved.get("notes", "") if saved else ""

    # --------------------------
    # 2) TCX UPLOAD (BEFORE WIDGETS)
    # --------------------------
    st.caption("TCX upload (optional — autofills this session)")
    tcx_file = st.file_uploader(
        "Upload TCX (.tcx)",
        type=["tcx"],
        key=f"{origin}_{w_id}_tcx",
    )

    tcx_info = None
    if tcx_file:
        parsed = load_tcx_from_upload(tcx_file)
        if parsed:
            tcx_info = parsed
            st.success("TCX parsed")

            # Auto-fill duration
            if parsed.get("duration_sec"):
                auto_dur = int(parsed["duration_sec"] / 60)
                dur_key = f"{origin}_{w_id}_dur"
                if st.session_state.get(dur_key) in [None, 0, ""]:
                    st.session_state[dur_key] = auto_dur

            # Auto-fill distance
            if parsed.get("distance_m", 0) > 0:
                miles = round(parsed["distance_m"] / 1609.34, 2)
                dist_key = f"{origin}_{w_id}_dist"
                if st.session_state.get(dist_key) in [None, "", "0"]:
                    st.session_state[dist_key] = str(miles)

            # Auto-fill HR
            if parsed.get("avg_hr"):
                st.session_state[f"{origin}_{w_id}_hr"] = str(int(parsed["avg_hr"]))
            if parsed.get("max_hr"):
                st.session_state[f"{origin}_{w_id}_maxhr"] = str(int(parsed["max_hr"]))

            # Auto-fill elevation
            if parsed.get("elevation_gain_m"):
                st.session_state[f"{origin}_{w_id}_elev"] = str(int(parsed["elevation_gain_m"]))

            # Pace display
            if parsed.get("pace_min_per_km"):
                pace = parsed["pace_min_per_km"]
                st.caption(f"Pace: **{pace:.2f} min/km**")

            # HR drift
            if parsed.get("hr_drift") is not None:
                st.caption(f"HR Drift: **{parsed['hr_drift']:.3f}**")

        else:
            st.error("Could not parse TCX (try again or upload a different file).")

        if parsed:
            tcx_info = parsed
            st.success("TCX parsed")

            # -----------------------------
            # SAFE AUTOFILL DEFAULT VALUES
            # -----------------------------
            # Duration (sec -> min)
            dur_default = duration  # existing values remain unless blank
            if parsed.get("duration_sec"):
                dur_default = int(parsed["duration_sec"] / 60)

            # Distance (m -> mi)
            dist_default = distance
            if parsed.get("distance_m", 0) > 0:
                miles = round(parsed["distance_m"] / 1609.34, 2)
                dist_default = str(miles)

            # Average HR
            avg_default = avg_hr
            if parsed.get("avg_hr"):
                avg_default = str(int(parsed["avg_hr"]))

            # Max HR
            max_default = max_hr
            if parsed.get("max_hr"):
                max_default = str(int(parsed["max_hr"]))

            # Elevation gain
            elev_default = elevation
            if parsed.get("elevation_gain_m"):
                elev_default = str(int(parsed["elevation_gain_m"]))

            # -----------------------------
            # DISPLAY PACE + HR ZONES
            # -----------------------------
            pace = None
            if parsed.get("duration_sec") and parsed.get("distance_m"):
                miles_for_pace = parsed["distance_m"] / 1609.34
                if miles_for_pace > 0:
                    pace = (parsed["duration_sec"] / 60) / miles_for_pace

            if pace:
                st.caption(f"Pace: **{pace:.2f} min/mi**")

            zones = parsed.get("time_in_zones", {})
            if zones:
                st.markdown("**HR Time in Zones:**")
                for z, sec in zones.items():
                    st.write(f"- {z}: {sec / 60:.1f} min")

            # -----------------------------
            # UPDATE WIDGET VALUES SAFELY
            # (avoid Streamlit locked-state errors)
            # -----------------------------
            st.session_state.setdefault(f"{origin}_{w_id}_dur", dur_default)
            st.session_state.setdefault(f"{origin}_{w_id}_dist", dist_default)
            st.session_state.setdefault(f"{origin}_{w_id}_hr", avg_default)
            st.session_state.setdefault(f"{origin}_{w_id}_maxhr", max_default)
            st.session_state.setdefault(f"{origin}_{w_id}_elev", elev_default)

        else:
            st.error("Could not parse TCX.")


    # --------------------------
    # 3) SET SESSION STATE BEFORE WIDGETS
    # --------------------------
    # These writes happen BEFORE any widget is created for these keys, so
    # Streamlit is fine with us setting st.session_state here.
    st.session_state[done_key] = done_default
    st.session_state[duration_key] = dur_default
    st.session_state[distance_key] = dist_default
    st.session_state[rpe_key] = rpe_default
    st.session_state[avg_key] = avg_default
    st.session_state[max_key] = max_default
    st.session_state[elev_key] = elev_default
    st.session_state[notes_key] = notes_default

    # --------------------------
    # 4) CARDIO INPUT WIDGETS
    # --------------------------
    c1, c2, c3, c4 = st.columns(4)
    done = c1.checkbox(
        "Done?",
        key=done_key,
    )
    duration = c2.number_input(
        "Minutes",
        min_value=0,
        max_value=400,
        key=duration_key,
    )
    distance = c3.text_input(
        "Distance (mi/km)",
        key=distance_key,
    )
    rpe_cardio = c4.slider(
        "RPE",
        min_value=1,
        max_value=10,
        key=rpe_key,
    )

    hr_col, maxhr_col, elev_col = st.columns(3)
    avg_hr = hr_col.text_input(
        "Average HR",
        key=avg_key,
    )
    max_hr = maxhr_col.text_input(
        "Max HR",
        key=max_key,
    )
    elevation = elev_col.text_input(
        "Elevation Gain (ft/m)",
        key=elev_key,
    )

    cardio_notes = st.text_area(
        "Session notes",
        key=notes_key,
        height=60,
    )

    st.markdown("---")

    if not done:
        return None

    # Build and return the log entry
    return {
        "origin": origin,
        "workout_id": w_id,
        "name": name,
        "duration_min": duration,
        "distance": distance,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "elev": elevation,
        "rpe": rpe_cardio,
        "notes": cardio_notes,
        "tcx": tcx_info,
    }


def safe_int(value, default=3):
    """
    Convert a value to int safely.
    Handles '', None, 'nan', float('nan'), and invalid strings.
    """
    try:
        if value is None:
            return default
        if isinstance(value, float) and (value != value):  # float NaN
            return default

        s = str(value).strip().lower()
        if s in ["", "nan", "none"]:
            return default

        return int(float(value))
    except Exception:
        return default


# --------------------------------------------------------------------
# MAIN LOGGING – PLANNED MODE
# --------------------------------------------------------------------
if mode == "planned":
    # 1) Scheduled strength workouts
    scheduled_strength_ids = [wid for wid in existing_ids if wid in workouts and is_strength_workout(workouts[wid])]

    if scheduled_strength_ids:
        st.markdown("### Strength Session Log (Scheduled)")
        for w_idx, w_id in enumerate(scheduled_strength_ids):
            w = workouts[w_id]
            st.markdown(f"#### {w.get('name', 'Strength Workout')}")

            # Primary + accessories
            for block_name, block_key in [("Primary Lifts", "primary"), ("Accessories", "accessories")]:
                block = w.get(block_key, [])
                if not block:
                    continue
                st.caption(block_name)

                for ex_idx, lift in enumerate(block):
                    ex_id = lift["exercise_id"]
                    ex_def = exercises.get(ex_id, {})
                    ex_name = ex_def.get("name", ex_id)

                    base_sets = int(lift.get("sets", 3))
                    base_reps = lift.get("reps", "8-12")
                    base_rpe = lift.get("rpe", "7")

                    sug = hypertrophy_suggestions.get(ex_id, {})

                    entry = render_strength_exercise_block(
                        origin="primary" if block_key == "primary" else "secondary",
                        w_id=w_id,
                        ex_id=ex_id,
                        block_index=w_idx * 10 + ex_idx,
                        base_sets=base_sets,
                        base_reps=base_reps,
                        base_rpe=base_rpe,
                        ex_name=ex_name,
                        ex_def=ex_def,
                        suggestion=sug,
                    )
                    strength_entries.append(entry)

            st.markdown("---")

    # 2) Scheduled cardio workouts
    scheduled_cardio_ids = [wid for wid in existing_ids if wid in workouts and is_cardio_workout(workouts[wid])]

    if scheduled_cardio_ids:
        st.markdown("### Cardio / Conditioning Log (Scheduled)")
        for w_id in scheduled_cardio_ids:
            w = workouts[w_id]
            entry = render_cardio_block(origin="scheduled", w_id=w_id, w=w)
            if entry:
                cardio_entries.append(entry)

    # 3) Extra sessions (strength/cardio) – FULL LOGS
    st.markdown("### Optional Extra Session")
    extra_type_options = ["None", "Extra Strength", "Extra Cardio"]
    extra_type_default = saved_day.get("extra_session_type", "None") if saved_day else "None"
    if extra_type_default not in extra_type_options:
        extra_type_default = "None"

    extra_type = st.selectbox(
        "Extra Session?",
        extra_type_options,
        index=extra_type_options.index(extra_type_default),
    )

    extra_notes = st.text_area(
        "Extra session details (optional)",
        value=saved_day.get("extra_session_notes", "") if saved_day else "",
        height=60,
    )

    # Extra Strength = manual exercises with full log
    if extra_type == "Extra Strength":
        st.markdown("#### Extra Strength – Manual Exercises")
        num_ex = st.number_input(
            "Number of extra strength exercises",
            min_value=1,
            max_value=12,
            value=3,
        )
        str_ids = strength_exercise_ids()
        for i in range(int(num_ex)):
            ex_id = st.selectbox(
                f"Exercise #{i+1}",
                str_ids,
                key=f"extra_strength_ex_{i}",
            )
            ex_def = exercises.get(ex_id, {})
            ex_name = ex_def.get("name", ex_id)

            # Defaults for manual extra: 3 sets 8-12 @ RPE 8
            entry = render_strength_exercise_block(
                origin="extra",
                w_id=f"extra_strength_{i}",
                ex_id=ex_id,
                block_index=100 + i,
                base_sets=3,
                base_reps="8-12",
                base_rpe="8",
                ex_name=ex_name,
                ex_def=ex_def,
                suggestion=None,
            )
            strength_entries.append(entry)

    # Extra Cardio = one full cardio block + TCX
    if extra_type == "Extra Cardio":
        st.markdown("#### Extra Cardio Session")
        card_ids = cardio_workout_ids()
        if card_ids:
            extra_wid = st.selectbox(
                "Choose a cardio template",
                card_ids,
                format_func=lambda wid: workouts[wid].get("name", wid),
                key="extra_cardio_template",
            )
            w_extra = workouts[extra_wid]
            entry = render_cardio_block(origin="extra", w_id=extra_wid, w=w_extra)
            if entry:
                cardio_entries.append(entry)


# --------------------------------------------------------------------
# MAIN LOGGING – MANUAL MODE (FULL LOGS)
# --------------------------------------------------------------------
elif mode == "manual":
    st.markdown("### Manual Strength Session (Full Log)")
    num_ex = st.number_input(
        "How many strength exercises today?",
        min_value=0,
        max_value=20,
        value=3,
    )
    str_ids = strength_exercise_ids()

    for i in range(int(num_ex)):
        if not str_ids:
            break
        ex_id = st.selectbox(
            f"Exercise #{i+1}",
            str_ids,
            key=f"manual_strength_ex_{i}",
        )
        ex_def = exercises.get(ex_id, {})
        ex_name = ex_def.get("name", ex_id)

        entry = render_strength_exercise_block(
            origin="manual",
            w_id=f"manual_strength_{i}",
            ex_id=ex_id,
            block_index=200 + i,
            base_sets=3,
            base_reps="8-12",
            base_rpe="8",
            ex_name=ex_name,
            ex_def=ex_def,
            suggestion=None,
        )
        strength_entries.append(entry)

    st.markdown("---")
    st.markdown("### Manual Cardio Sessions (Full Log + TCX)")
    num_card = st.number_input(
        "How many cardio sessions today?",
        min_value=0,
        max_value=6,
        value=1,
    )

    card_ids = cardio_workout_ids()
    for i in range(int(num_card)):
        if not card_ids:
            break
        wid = st.selectbox(
            f"Cardio session #{i+1}",
            card_ids,
            format_func=lambda x: workouts[x].get("name", x),
            key=f"manual_cardio_wid_{i}",
        )
        w = workouts[wid]
        entry = render_cardio_block(origin="manual", w_id=f"manual_{wid}_{i}", w=w)
        if entry:
            cardio_entries.append(entry)


# --------------------------------------------------------------------
# REST MODE – NO WORKOUT LOGS
# --------------------------------------------------------------------
else:  # mode == "rest"
    st.info("Rest day selected – no strength or cardio logging required today.")
    extra_type = "None"
    extra_notes = ""


# --------------------------------------------------------------------
# DAILY READINESS / LIFE LOG  (BOTTOM)
# --------------------------------------------------------------------
st.markdown("---")
st.markdown("### Daily Readiness / Life Log")

c1, c2 = st.columns(2)
hrv = c1.text_input(
    "HRV (optional)",
    value=str(saved_day.get("hrv", "")) if saved_day else "",
)
sleep_hours = c2.text_input(
    "Sleep hours",
    value=str(saved_day.get("sleep_hours", "")) if saved_day else "",
)

c3, c4, c5 = st.columns(3)
fatigue = c3.slider(
    "Fatigue (1 = wrecked, 5 = great)",
    1,
    5,
    safe_int(saved_day.get("fatigue_1_5"), 3) if saved_day else 3,
)

soreness = c4.slider(
    "Soreness (1–5)",
    1,
    5,
    safe_int(saved_day.get("soreness_1_5"), 3) if saved_day else 3,
)

mood = c5.slider(
    "Mood (1–5)",
    1,
    5,
    safe_int(saved_day.get("mood_1_5"), 3) if saved_day else 3,
)


notes = st.text_area(
    "Notes",
    value=saved_day.get("notes", "") if saved_day else "",
    height=100,
)


# --------------------------------------------------------------------
# SAVE
# --------------------------------------------------------------------
scheduled_str = ",".join(existing_ids) if mode == "planned" else ""
secondary_str = ",".join(secondary_ids) if secondary_ids else ""

log_data: Dict[str, Any] = {
    "date": selected_date,
    "phase": phase_name,
    "primary_id": primary_id if mode == "planned" else "",
    "secondary_ids": secondary_str if mode == "planned" else "",
    "scheduled_workouts": scheduled_str,
    "strength_block": str(strength_entries),
    "cardio_sessions": str(cardio_entries),
    "hrv": hrv,
    "sleep_hours": sleep_hours,
    "fatigue_1_5": fatigue,
    "soreness_1_5": soreness,
    "mood_1_5": mood,
    "notes": notes,
    "extra_session_type": extra_type if mode == "planned" else "None",
    "extra_session_notes": extra_notes if mode == "planned" else "",
}

if st.button("Save today’s log"):
    save_log_row(log_data)
    st.success("Logged ✅")
