# utils/get_today_plan.py

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional, Any

# Where we store weekly overrides written by the Weekly page
WEEK_OVERRIDES_PATH = os.path.join("data", "week_overrides.json")


# ---------------------------------------------------------
# Helpers for phase-based scheduling
# ---------------------------------------------------------

def find_active_phase(selected_date: date, phases: Dict[str, Dict[str, Any]]
                      ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Find which phase contains selected_date.
    phases = { "2A": { "start": "...", "end": "...", ... }, ... }
    """
    for phase_name, phase_data in phases.items():
        start = date.fromisoformat(phase_data["start"])
        end = date.fromisoformat(phase_data["end"])
        if start <= selected_date <= end:
            return phase_name, phase_data
    return None, None


def get_week_number(selected_date: date, phase_data: Dict[str, Any]) -> int:
    """Return week number in phase (1-indexed)."""
    start_date = date.fromisoformat(phase_data["start"])
    delta_days = (selected_date - start_date).days
    return (delta_days // 7) + 1


def get_base_workouts_for_day(selected_date: date, phase_data: Dict[str, Any]) -> List[str]:
    """
    Return the default (un-overridden) workouts list for this weekday
    from the phase 'days' mapping.
    """
    dow = str(selected_date.weekday())  # 0=Mon, 6=Sun
    days = phase_data.get("days", {})

    if dow not in days:
        return []

    w = days[dow]
    # Always return list form
    return w if isinstance(w, list) else [w]


def apply_week_overrides_static(
    selected_date: date,
    phase_data: Dict[str, Any],
    base_workouts: List[str],
) -> List[str]:
    """
    Apply week-specific overrides defined *inside the phase JSON*
    (phase_data["weeks"]).

    This is your original static 'weeks' logic.
    """
    weeks_cfg = phase_data.get("weeks")
    if not weeks_cfg:
        return base_workouts

    week_num = str(get_week_number(selected_date, phase_data))
    if week_num not in weeks_cfg:
        return base_workouts

    week_overrides = weeks_cfg[week_num]
    dow = str(selected_date.weekday())

    if dow not in week_overrides:
        return base_workouts

    override_list = week_overrides[dow]
    return override_list if isinstance(override_list, list) else [override_list]


def resolve_alt_saturday(
    selected_date: date,
    workouts: List[str],
    phase_data: Dict[str, Any],
) -> List[str]:
    """
    Replace 'ALT_SATURDAY' with alternating A/B schedule based on week number.
    Odd weeks → workout_A, even weeks → workout_B.
    """
    if "ALT_SATURDAY" not in workouts:
        return workouts

    if selected_date.weekday() != 5:  # Saturday = 5
        return workouts  # Safety: ALT_SATURDAY should only appear on Saturdays

    week_num = get_week_number(selected_date, phase_data)
    is_even = (week_num % 2 == 0)
    alt_id = "workout_B" if is_even else "workout_A"

    out: List[str] = []
    for w in workouts:
        if w == "ALT_SATURDAY":
            out.append(alt_id)
        else:
            out.append(w)
    return out


# ---------------------------------------------------------
# Dynamic weekly overrides (from Weekly page)
# ---------------------------------------------------------

def _load_week_overrides() -> Dict[str, Dict[str, List[str]]]:
    """
    Load dynamic weekly overrides from data/week_overrides.json.

    Structure:
    {
      "2025-12-08": {        # week_start (Monday)
        "0": ["workout_A"],
        "1": ["Z2_run"],
        "2": ["workout_B"],
        ...
      },
      ...
    }
    """
    if not os.path.exists(WEEK_OVERRIDES_PATH):
        return {}
    try:
        with open(WEEK_OVERRIDES_PATH, "r") as f:
            data = json.load(f)
        # Ensure inner mappings are lists
        for week_start, mapping in data.items():
            if not isinstance(mapping, dict):
                continue
            for dow, v in mapping.items():
                if isinstance(v, list):
                    continue
                data[week_start][dow] = [v]
        return data
    except Exception:
        return {}


def apply_dynamic_week_overrides(
    selected_date: date,
    current_workouts: List[str],
) -> List[str]:
    """
    If there is a dynamic override for this calendar week & weekday,
    replace the workouts list with that override.
    """
    week_overrides = _load_week_overrides()
    if not week_overrides:
        return current_workouts

    # Week is identified by Monday's date
    monday = selected_date - timedelta(days=selected_date.weekday())
    week_key = monday.isoformat()
    if week_key not in week_overrides:
        return current_workouts

    dow = str(selected_date.weekday())
    mapping = week_overrides.get(week_key, {})
    if dow not in mapping:
        return current_workouts

    override_list = mapping[dow]
    return override_list if isinstance(override_list, list) else [override_list]


# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def get_today_plan(
    selected_date: date,
    phases: Dict[str, Dict[str, Any]],
) -> Tuple[str, Optional[str], List[str]]:
    """
    Main entrypoint used by app.py.

    Returns:
      phase_name, primary_workout_id, secondary_workout_ids
    """
    phase_name, phase_data = find_active_phase(selected_date, phases)
    if not phase_name or not phase_data:
        # Off-plan date or no phase found
        return "Off-plan", None, []

    # 1) Base workouts from phase["days"]
    base = get_base_workouts_for_day(selected_date, phase_data)

    # 2) Apply static week overrides from phase JSON (phase["weeks"])
    week_applied = apply_week_overrides_static(selected_date, phase_data, base)

    # 3) Resolve ALT_SATURDAY (alternating workout_A / workout_B on Saturdays)
    alt_applied = resolve_alt_saturday(selected_date, week_applied, phase_data)

    # 4) Apply dynamic week overrides from data/week_overrides.json (Weekly page)
    final_workouts = apply_dynamic_week_overrides(selected_date, alt_applied)

    if not final_workouts:
        return phase_name, None, []

    primary_id = final_workouts[0]
    secondary_ids = final_workouts[1:] if len(final_workouts) > 1 else []

    return phase_name, primary_id, secondary_ids
