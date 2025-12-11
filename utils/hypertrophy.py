import ast
from datetime import date
from typing import Dict, Any, List, Optional

import pandas as pd


LOG_FILE = "training_log.csv"


# -----------------------------
# Log loading + parsing
# -----------------------------

def load_log() -> pd.DataFrame:
    """Load training_log.csv if it exists, else empty DataFrame."""
    try:
        df = pd.read_csv(LOG_FILE, parse_dates=["date"])
        df["date"] = df["date"].dt.date
    except FileNotFoundError:
        df = pd.DataFrame()
    return df


def _iter_strength_entries(df: pd.DataFrame):
    """
    Yield (row_date, entry_dict) for each strength entry in the log.

    Expects a column 'strength_block' that is a stringified list of dicts:
    [
      {"exercise_id": "bench", "sets": 4, "reps": "8-10", "weight": 115, "rpe": 7},
      ...
    ]
    """
    if df.empty or "strength_block" not in df.columns:
        return

    for _, row in df.iterrows():
        block_str = row.get("strength_block", "")
        if not isinstance(block_str, str) or not block_str.strip():
            continue
        try:
            entries = ast.literal_eval(block_str)
        except Exception:
            continue
        if not isinstance(entries, list):
            continue
        for e in entries:
            if not isinstance(e, dict):
                continue
            yield row["date"], e


def get_last_strength_entry(
    df: pd.DataFrame,
    current_date: date,
    exercise_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Return the most recent logged set for this exercise_id before current_date.
    """
    if df.empty:
        return None

    df_past = df[df["date"] < current_date]
    if df_past.empty:
        return None

    # Sort descending by date
    df_past = df_past.sort_values("date", ascending=False)

    for row_date, entry in _iter_strength_entries(df_past):
        if entry.get("exercise_id") == exercise_id:
            out = entry.copy()
            out["date"] = row_date
            return out

    return None


# -----------------------------
# Hypertrophy suggestion logic
# -----------------------------

def _parse_rep_range(rep_spec) -> (int, int):
    """
    Parse reps spec from workouts.json.

    Examples:
      "8-10" -> (8, 10)
      "8–10" (en dash) -> (8, 10)
      10 -> (10, 10)
    """
    if isinstance(rep_spec, int):
        return rep_spec, rep_spec
    if not isinstance(rep_spec, str):
        return 8, 12

    s = rep_spec.replace("–", "-")
    if "-" in s:
        low, high = s.split("-", 1)
        try:
            return int(low.strip()), int(high.strip())
        except Exception:
            return 8, 12
    else:
        try:
            v = int(s.strip())
            return v, v
        except Exception:
            return 8, 12


def _parse_rpe(rpe_spec) -> (float, float):
    """
    Parse RPE spec from workouts.json.

    Examples:
      "7" -> (7, 7)
      "6–7" -> (6, 7)
    """
    if isinstance(rpe_spec, (int, float)):
        return float(rpe_spec), float(rpe_spec)
    if not isinstance(rpe_spec, str):
        return 7.0, 7.0

    s = rpe_spec.replace("–", "-")
    if "-" in s:
        low, high = s.split("-", 1)
        try:
            return float(low.strip()), float(high.strip())
        except Exception:
            return 7.0, 7.0
    else:
        try:
            v = float(s.strip())
            return v, v
        except Exception:
            return 7.0, 7.0


def _is_lower_body(exercise_id: str) -> bool:
    lower_keywords = ["deadlift", "rdl", "squat", "lunge", "split", "hip", "step"]
    return any(k in exercise_id.lower() for k in lower_keywords)


def _suggest_weight(
    exercise_id: str,
    target_rpe_low: float,
    target_rpe_high: float,
    last: Optional[Dict[str, Any]],
) -> Optional[float]:
    """
    Simple load progression logic:
      - if last RPE <= target_low - 1 → increase weight
      - if within target range → keep same
      - if last RPE > target_high → reduce weight a bit
    """
    if not last:
        # No history → let user pick; we don't guess blindly
        return None

    try:
        last_weight = float(last.get("weight", 0))
        last_rpe = float(last.get("rpe", 0))
    except Exception:
        return None

    if last_weight <= 0:
        return None

    # Choose increment size
    if _is_lower_body(exercise_id):
        small_inc = 5.0
        big_inc = 10.0
    else:
        small_inc = 2.5
        big_inc = 5.0

    # Very rough 5% unit for reductions
    red_factor = 0.95

    # Rules
    if last_rpe <= (target_rpe_low - 1):
        # Too easy → increase more aggressively for lower RPE
        if last_rpe <= (target_rpe_low - 2):
            return last_weight + big_inc
        return last_weight + small_inc

    if target_rpe_low <= last_rpe <= target_rpe_high:
        # Exactly where we want → keep weight
        return last_weight

    if last_rpe > target_rpe_high:
        # Too hard → reduce a bit
        return round(last_weight * red_factor, 1)

    # Fallback
    return last_weight


def _suggest_sets(
    base_sets: int,
    fatigue_score: Optional[float],
    last_rpe: Optional[float],
    primary: bool,
) -> int:
    """
    Adjust sets up or down based on fatigue and last RPE.

    fatigue_score: 1–5 (1 = wrecked, 5 = amazing) or None.
    primary: True for main lifts (bench, deadlift, etc.), False for accessories.
    """
    sets = base_sets

    if fatigue_score is None and last_rpe is None:
        return sets

    # If fatigue is low and last RPE was high → trim volume
    if (fatigue_score is not None and fatigue_score <= 2) or (
        last_rpe is not None and last_rpe >= 9
    ):
        return max(sets - 1, 1)

    # If fatigue is good and last RPE was easy → maybe add a set (mostly accessories)
    if (fatigue_score is not None and fatigue_score >= 4) and (
        last_rpe is not None and last_rpe <= 6
    ):
        if not primary:
            return sets + 1

    return sets


def _suggest_reps(rep_low: int, rep_high: int, last_rpe: Optional[float]) -> int:
    """
    If last session was easy → push toward upper end.
    If last session was very hard → lower end.
    Otherwise → middle.
    """
    if rep_low == rep_high:
        return rep_low

    if last_rpe is None:
        return rep_high  # default to higher reps for hypertrophy

    mid = (rep_low + rep_high) // 2

    if last_rpe <= 6:
        return rep_high
    if last_rpe >= 9:
        return rep_low
    return mid


def get_hypertrophy_suggestions(
    selected_date: date,
    workout_ids: List[str],
    workouts_flat: Dict[str, Dict[str, Any]],
    fatigue_score: Optional[float] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Main entrypoint.

    Returns:
      {
        "bench": {
           "sets": 4,
           "reps": 10,
           "weight": 120,
           "target_rpe": "7",
           "reason": "Last 115 x 10 @ RPE 6 → bump weight slightly."
        },
        ...
      }
    """
    df_log = load_log()
    suggestions: Dict[str, Dict[str, Any]] = {}

    for w_id in workout_ids:
        workout = workouts_flat.get(w_id)
        if not workout:
            continue

        # Determine if main or accessory block
        primary_block = workout.get("primary", [])
        accessory_block = workout.get("accessories", [])

        # Primary lifts
        for block in primary_block:
            ex_id = block["exercise_id"]
            base_sets = int(block.get("sets", 3))
            rep_low, rep_high = _parse_rep_range(block.get("reps", "8-12"))
            rpe_low, rpe_high = _parse_rpe(block.get("rpe", "7"))

            last = get_last_strength_entry(df_log, selected_date, ex_id)
            last_rpe = float(last.get("rpe")) if last and "rpe" in last else None

            weight_sug = _suggest_weight(ex_id, rpe_low, rpe_high, last)
            sets_sug = _suggest_sets(base_sets, fatigue_score, last_rpe, primary=True)
            reps_sug = _suggest_reps(rep_low, rep_high, last_rpe)

            if last:
                reason = (
                    f"Last {ex_id} on {last['date']}: {last.get('weight')} x {last.get('reps')} @ RPE {last.get('rpe')}."
                )
            else:
                reason = f"No prior log for {ex_id}; using base sets/reps."

            suggestions[ex_id] = {
                "sets": sets_sug,
                "reps": reps_sug,
                "weight": weight_sug,
                "target_rpe": block.get("rpe", "7"),
                "primary": True,
                "reason": reason,
            }

        # Accessories
        for block in accessory_block:
            ex_id = block["exercise_id"]
            base_sets = int(block.get("sets", 3))
            rep_low, rep_high = _parse_rep_range(block.get("reps", "10-15"))
            rpe_low, rpe_high = _parse_rpe(block.get("rpe", "8"))

            last = get_last_strength_entry(df_log, selected_date, ex_id)
            last_rpe = float(last.get("rpe")) if last and "rpe" in last else None

            weight_sug = _suggest_weight(ex_id, rpe_low, rpe_high, last)
            sets_sug = _suggest_sets(base_sets, fatigue_score, last_rpe, primary=False)
            reps_sug = _suggest_reps(rep_low, rep_high, last_rpe)

            if last:
                reason = (
                    f"Last {ex_id} on {last['date']}: {last.get('weight')} x {last.get('reps')} @ RPE {last.get('rpe')}."
                )
            else:
                reason = f"No prior log for {ex_id}; using base sets/reps."

            suggestions[ex_id] = {
                "sets": sets_sug,
                "reps": reps_sug,
                "weight": weight_sug,
                "target_rpe": block.get("rpe", "8"),
                "primary": False,
                "reason": reason,
            }

    return suggestions
