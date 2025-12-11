# utils/manage_overrides.py

import json
import os
from datetime import date, timedelta

OVERRIDES_PATH = "data/schedule_overrides.json"


# ---------------------------------------------------------
# Load + Save helpers
# ---------------------------------------------------------

def load_overrides() -> dict:
    """Load override map stored as { 'YYYY-MM-DD': { override data } }."""
    if not os.path.exists(OVERRIDES_PATH):
        return {}
    try:
        with open(OVERRIDES_PATH, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_overrides(data: dict):
    """Write override dictionary back to disk."""
    with open(OVERRIDES_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------
# Reset week
# ---------------------------------------------------------

def reset_week(start_date: date, end_date: date) -> int:
    """
    Remove ALL overrides between start_date → end_date, inclusive.
    Returns count of overrides removed.
    """
    overrides = load_overrides()
    to_delete = []

    cur = start_date
    while cur <= end_date:
        d_str = str(cur)
        if d_str in overrides:
            to_delete.append(d_str)
        cur += timedelta(days=1)

    for d in to_delete:
        del overrides[d]

    save_overrides(overrides)

    return len(to_delete)
