import streamlit as st
import json
from pathlib import Path
from datetime import date

# ---------- Helper Functions ----------
def load_json_file(path: Path):
    with open(path, "r") as f:
        return json.load(f)

def load_workouts():
    return load_json_file(Path("workouts_full.txt"))

def load_all_phases():
    """Load all Phase_XXX files and merge into one dictionary by date."""
    phases = {}
    for pf in sorted(Path(".").glob("Phase_*.txt")):
        try:
            data = load_json_file(pf)
            for entry in data:
                phases[entry["date"]] = entry
        except Exception as e:
            st.warning(f"Could not load {pf.name}: {e}")
    return phases

# ---------- Load Data ----------
workouts = load_workouts()
phases = load_all_phases()

# ---------- App UI ----------
today = date.today().isoformat()
st.title("Today's Workout")

if today not in phases:
    st.error(f"No workout found for {today}.")
    st.write("Check your Phase files or date format.")
    st.stop()

day_entry = phases[today]

st.subheader(f"{today} — {day_entry['day_of_week']}")
st.caption(f"Phase: {day_entry['phase']} | Week: {day_entry['week']}")

# ---------- Display each workout ----------
for wid in day_entry["workouts"]:
    # find workout definition
    found = False
    for category in workouts.values():
        if isinstance(category, dict) and wid in category:
            workout = category[wid]
            found = True
            break

    if not found:
        st.error(f"Workout '{wid}' not found in workouts_full.txt")
        continue

    st.markdown("---")
    st.markdown(f"## {workout['name']}")

    if "focus" in workout:
        st.write(f"**Focus:** {workout['focus']}")

    if "purpose" in workout:
        st.write(f"**Purpose:** {workout['purpose']}")

    # Strength workouts
    if "primary" in workout:
        st.write("### Primary Lifts")
        for ex in workout["primary"]:
            st.write(f"- **{ex['exercise_id']}**: {ex['sets']} x {ex['reps']} @ RPE {ex['rpe']}")

    if "accessories" in workout:
        st.write("### Accessories")
        for ex in workout["accessories"]:
            st.write(f"- **{ex['exercise_id']}**: {ex['sets']} x {ex['reps']} @ RPE {ex['rpe']}")

    # Cardio workouts
    if "cardio" in workout and workout["cardio"] is not None:
        st.write("### Cardio")
        st.write(f"- **Duration:** {workout['cardio']['duration_min']} minutes")
        st.write(f"- **Intensity:** {workout['cardio']['intensity']}")
        st.write(f"- **Instructions:** {workout['cardio']['instructions']}")

    # Coaching notes
    if "coaching_notes" in workout:
        with st.expander("Coaching Notes"):
            for note in workout["coaching_notes"]:
                st.write(f"- {note}")

