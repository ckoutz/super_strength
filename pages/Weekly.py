# pages/Weekly.py

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Dict, Any, List, Tuple

import streamlit as st
from streamlit_sortables import sort_items  # pip install streamlit-sortables

from utils.load_json import load_workouts, load_phases
from utils.get_today_plan import get_today_plan

WORKOUTS_PATH = "data/workouts.json"
PHASES_FOLDER = "data/phases"
WEEK_OVERRIDES_PATH = os.path.join("data", "week_overrides.json")


# ---------------------------------------------------------
# Load data
# ---------------------------------------------------------
workouts_raw = load_workouts(WORKOUTS_PATH)
phases = load_phases(PHASES_FOLDER)

# Flatten workouts like in main app
workouts: Dict[str, Dict[str, Any]] = {}
if isinstance(workouts_raw, dict):
    for category, group in workouts_raw.items():
        if isinstance(group, dict):
            for wid, wdata in group.items():
                workouts[str(wid)] = wdata


# ---------------------------------------------------------
# Helpers for week overrides
# ---------------------------------------------------------

def load_week_overrides() -> Dict[str, Dict[str, List[str]]]:
    if not os.path.exists(WEEK_OVERRIDES_PATH):
        return {}
    try:
        with open(WEEK_OVERRIDES_PATH, "r") as f:
            data = json.load(f)
        # Normalize inner lists
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


def save_week_overrides(data: Dict[str, Dict[str, List[str]]]) -> None:
    os.makedirs(os.path.dirname(WEEK_OVERRIDES_PATH), exist_ok=True)
    with open(WEEK_OVERRIDES_PATH, "w") as f:
        json.dump(data, f, indent=2)


def week_monday(any_date: date) -> date:
    """Return Monday of the ISO week containing any_date."""
    return any_date - timedelta(days=any_date.weekday())


def build_week_rows(week_ref: date) -> List[Dict[str, Any]]:
    """
    For the Monday–Sunday of the selected week, build a list of:
    {
      "date": date_obj,
      "workout_ids": [ids...],
      "label": "Mon 12/08 — Strength Workout A, Z2 Run"
    }
    Using *current effective plan* (after overrides).
    """
    rows: List[Dict[str, Any]] = []

    mon = week_monday(week_ref)
    for i in range(7):
        d = mon + timedelta(days=i)
        phase_name, primary_id, secondary_ids = get_today_plan(d, phases)
        ids: List[str] = []
        if primary_id:
            ids.append(primary_id)
        if secondary_ids:
            ids.extend(secondary_ids)

        # Build label
        day_label = d.strftime("%a %m/%d")
        if ids:
            names = []
            for wid in ids:
                w = workouts.get(wid, {})
                names.append(w.get("name", wid))
            workouts_str = ", ".join(names)
        else:
            workouts_str = "Rest / No workout"

        label = f"{day_label} — {workouts_str}"

        rows.append(
            {
                "date": d,
                "workout_ids": ids,
                "label": label,
            }
        )
    return rows


# ---------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------

st.set_page_config(page_title="Weekly Plan", layout="centered")
st.title("Weekly Plan – Drag & Drop")

st.markdown(
    "Use this page to **reorder which workout happens on which day** for a given week.  \n"
    "Changes are stored in `week_overrides.json` and automatically reflected on the **Today** page."
)

# Choose a week (any date inside that week)
selected_date = st.date_input("Week containing:", value=date.today())
week_start = week_monday(selected_date)
st.caption(f"Week start (Monday): {week_start.isoformat()}")

week_rows = build_week_rows(week_start)

st.markdown("### Current Week Overview")
st.write("This table shows the **current effective plan** (after any existing overrides).")

for row in week_rows:
    d = row["date"]
    label = row["label"]
    st.write(f"- {label}")

st.markdown("---")
st.markdown("### Drag & Drop to Reorder Days")

items = [f"{idx}|{row['label']}" for idx, row in enumerate(week_rows)]

sorted_items = sort_items(
    items=items,
    direction="vertical",
    key=f"week_sort_{week_start.isoformat()}",
)

sorted_indices = [int(s.split("|", 1)[0]) for s in sorted_items]
reordered_rows = [week_rows[i] for i in sorted_indices]

st.markdown("**New order preview (top to bottom = Mon → Sun slot):**")
for slot, row in enumerate(reordered_rows):
    st.write(f"{slot + 1}. {row['label']}")

st.markdown("---")

# Load existing overrides (so Save & Reset operate on one shared structure)
week_overrides = load_week_overrides()

col_save, col_reset = st.columns(2)

with col_save:
    if st.button("Save this week's order"):
        # Build overrides for this week: slot 0 → Monday, 1 → Tue, ..., 6 → Sun
        mapping: Dict[str, List[str]] = {}
        for dow in range(7):
            src_row = reordered_rows[dow]
            ids = src_row["workout_ids"]
            mapping[str(dow)] = ids

        week_overrides[week_start.isoformat()] = mapping
        save_week_overrides(week_overrides)
        st.success("Week order saved. The Today page will now reflect this order.")

with col_reset:
    if st.button("Reset this week to default plan"):
        if week_start.isoformat() in week_overrides:
            del week_overrides[week_start.isoformat()]
            save_week_overrides(week_overrides)
            st.success("Overrides cleared for this week. Today page will use the base plan again.")
        else:
            st.info("There were no overrides saved for this week.")

st.markdown("---")
st.caption("Weekly Plan – drag-and-drop reordering without changing your underlying phase JSON.")
