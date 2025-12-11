import json
import os

# -----------------------------
# Load workouts.json
# -----------------------------
def load_workouts(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


# -----------------------------
# Load exercises.json
# -----------------------------
def load_exercises(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


# -----------------------------
# Load all phase JSON files
# -----------------------------
def load_phases(folder: str) -> dict:
    phases = {}
    for file in os.listdir(folder):
        if file.lower().endswith(".json"):
            phase_name = file.replace(".json", "")
            with open(os.path.join(folder, file), "r") as f:
                phases[phase_name] = json.load(f)
    return phases
