import pandas as pd
import streamlit as st
from datetime import date, timedelta

from utils.hypertrophy import load_log as load_training_log


# -----------------------------------------------------
# PAGE CONFIG
# -----------------------------------------------------
st.set_page_config(page_title="Export Training Logs", layout="centered")
st.title("Export Training Logs")


# -----------------------------------------------------
# LOAD CSV LOG
# -----------------------------------------------------
df = load_training_log()

if df.empty:
    st.warning("No training logs found yet.")
    st.stop()

# Ensure date column is normalized to Python date
if "date" in df.columns:
    df["date"] = pd.to_datetime(df["date"]).dt.date


# -----------------------------------------------------
# HELPER TO FILTER DATE RANGE
# -----------------------------------------------------
def filter_range(start: date, end: date) -> pd.DataFrame:
    """Return rows where date is within the inclusive range."""
    mask = (df["date"] >= start) & (df["date"] <= end)
    return df.loc[mask].sort_values("date")


# -----------------------------------------------------
# PRESET RANGES
# -----------------------------------------------------
today = date.today()
one_week_ago = today - timedelta(days=7)
one_month_ago = today - timedelta(days=30)
three_months_ago = today - timedelta(days=90)

preset_options = {
    "Last 7 Days": (one_week_ago, today),
    "Last 30 Days": (one_month_ago, today),
    "Last 90 Days": (three_months_ago, today),
    "Custom Range": None,
}

st.header("1. Select Log Range")

choice = st.selectbox("Range:", list(preset_options.keys()))

if choice == "Custom Range":
    col1, col2 = st.columns(2)
    start = col1.date_input("Start date", one_month_ago)
    end = col2.date_input("End date", today)
else:
    start, end = preset_options[choice]

# Ensure start <= end
if start > end:
    st.error("Start date must be before end date.")
    st.stop()

# -----------------------------------------------------
# APPLY FILTER
# -----------------------------------------------------
filtered = filter_range(start, end)

st.subheader(f"Showing logs from {start} → {end} ({len(filtered)} entries)")
st.dataframe(filtered, use_container_width=True)


# -----------------------------------------------------
# EXPORT OPTIONS
# -----------------------------------------------------
st.header("2. Export")

# Export as CSV
csv_data = filtered.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download CSV",
    data=csv_data,
    file_name=f"training_logs_{start}_to_{end}.csv",
    mime="text/csv",
)

# Export as JSON
json_data = filtered.to_json(orient="records", indent=2).encode("utf-8")
st.download_button(
    label="Download JSON",
    data=json_data,
    file_name=f"training_logs_{start}_to_{end}.json",
    mime="application/json",
)

# -----------------------------------------------------
# SUMMARY METRICS BLOCK
# -----------------------------------------------------
st.header("3. Quick Summary (beta)")

# Basic metrics (can expand later)
total_cardio = filtered["cardio_sessions"].apply(lambda x: len(eval(x)) if isinstance(x, str) and x.strip() else 0).sum()
total_strength = filtered["strength_block"].apply(lambda x: len(eval(x)) if isinstance(x, str) and x.strip() else 0).sum()

colA, colB = st.columns(2)
colA.metric("Strength Exercises Logged", total_strength)
colB.metric("Cardio Sessions Logged", total_cardio)

st.caption("Future version will add volume calculations, HR summaries, RPE tracking, weekly load charts, etc.")
