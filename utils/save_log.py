import os
import pandas as pd
import json

LOG_PATH = "training_log.csv"


def json_safe(obj):
    """Ensure all objects are JSON-serializable."""
    try:
        return obj if isinstance(obj, (dict, list, str, int, float, bool)) else str(obj)
    except Exception:
        return str(obj)


def save_log_row(log_data: dict):
    """
    Writes a single day's training log to CSV.
    All nested objects are stored as valid JSON strings, not Python repr().
    """
    log_data_clean = {}

    for key, val in log_data.items():
        # Convert nested python objects to clean JSON
        if isinstance(val, (list, dict)):
            log_data_clean[key] = json.dumps(val, default=json_safe)
        else:
            log_data_clean[key] = val

    # Load existing log
    if os.path.exists(LOG_PATH):
        df = pd.read_csv(LOG_PATH)
    else:
        df = pd.DataFrame()

    # Remove previous entry for this same date (overwrite logic)
    if "date" in df.columns:
        df = df[df["date"] != str(log_data_clean["date"])]

    # Append
    df = pd.concat([df, pd.DataFrame([log_data_clean])], ignore_index=True)

    # Save
    df.to_csv(LOG_PATH, index=False)
    print("Saved log row for:", log_data_clean["date"])
