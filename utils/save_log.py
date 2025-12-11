import os
import json
from typing import Dict, Any

import pandas as pd

# -------------------------------------------------------------------
# FILE PATHS
# -------------------------------------------------------------------
LOG_FILE = "training_log.csv"
WEEK_OVERRIDE_FILE = "week_overrides.json"


# -------------------------------------------------------------------
# DAILY LOGGING (USED BY app.py / Today page)
# -------------------------------------------------------------------
def save_log_row(row: Dict[str, Any]) -> None:
    """
    Save or update a single day's training log.

    - If an entry for the same date already exists, it is replaced.
    - Otherwise, the row is appended.
    """
    # Make a one-row DataFrame
    df_new = pd.DataFrame([row])

    # Normalize date to ISO string for stable comparisons
    if "date" in df_new.columns:
        df_new["date"] = pd.to_datetime(df_new["date"]).dt.date.astype(str)

    # Load existing log if it exists
    if os.path.exists(LOG_FILE):
        try:
            df_old = pd.read_csv(LOG_FILE)
        except Exception:
            df_old = pd.DataFrame()
    else:
        df_old = pd.DataFrame()

    if not df_old.empty:
        # Normalize existing date column
        if "date" in df_old.columns:
            df_old["date"] = pd.to_datetime(df_old["date"]).dt.date.astype(str)

        # Remove any row with the same date as the new row
        new_date = df_new["date"].iloc[0]
        df_old = df_old[df_old["date"] != new_date]

        # Combine
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new

    # Save back to CSV
    df_all.to_csv(LOG_FILE, index=False)


# -------------------------------------------------------------------
# WEEKLY OVERRIDES (USED BY Weekly.py)
# -------------------------------------------------------------------
def _load_all_week_overrides() -> Dict[str, Dict[str, Any]]:
    """
    Internal helper: load the full JSON of all week overrides.
    Structure:
    {
      "2025-W03": {
        "2025-01-13": "REST",
        "2025-01-14": "MANUAL:workout_A",
        "2025-01-15": "SWAP:2025-01-17",
        ...
      },
      "2025-W04": { ... }
    }
    """
    if not os.path.exists(WEEK_OVERRIDE_FILE):
        return {}

    try:
        with open(WEEK_OVERRIDE_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def _save_all_week_overrides(all_data: Dict[str, Dict[str, Any]]) -> None:
    """Internal helper: write the full overrides structure back to disk."""
    with open(WEEK_OVERRIDE_FILE, "w") as f:
        json.dump(all_data, f, indent=2)


def load_week_overrides(week_key: str) -> Dict[str, Any]:
    """
    Load overrides for a specific ISO week key (e.g., '2025-W03').

    Returns a dict mapping date strings -> override directive, e.g.:
      {
        "2025-01-13": "REST",
        "2025-01-14": "MANUAL:workout_A",
        "2025-01-15": "SWAP:2025-01-17"
      }
    """
    all_data = _load_all_week_overrides()
    wk = all_data.get(week_key, {})
    return wk if isinstance(wk, dict) else {}


def save_week_overrides(week_key: str, overrides: Dict[str, Any]) -> None:
    """
    Save overrides for a given week key (e.g., '2025-W03').

    `overrides` should be a dict mapping date strings to override directives, e.g.:
      {
        "2025-01-13": "REST",
        "2025-01-14": "MANUAL:workout_A",
        "2025-01-15": "SWAP:2025-01-17"
      }
    """
    all_data = _load_all_week_overrides()
    all_data[week_key] = overrides
    _save_all_week_overrides(all_data)
