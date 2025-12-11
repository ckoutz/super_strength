def suggest_weight(exercise_id: str, user_history: list, default_rpe: str):
    """
    Very simple auto-suggestion:
    - If user has previous logs, return last logged working weight.
    - Otherwise pick a safe default range based on exercise.
    """

    # 1. Check user history
    for entry in reversed(user_history):
        if entry["exercise_id"] == exercise_id and entry["weight"]:
            return entry["weight"]

    # 2. No history → fallback simple logic
    defaults = {
        "bench": "95",
        "incline_press": "25s",
        "rdl": "95",
        "deadlift": "135",
        "pullup": "bodyweight",
        "row": "40s",
        "lat_pulldown": "80",
        "shoulder_press": "25s",
        "curl": "20s",
        "laterals": "10s",
        "rear_delts": "10s",
        "overhead_triceps": "20s",
        "triceps_ext": "40",
        "hammer_curl": "20s"
    }

    return defaults.get(exercise_id, "0")
