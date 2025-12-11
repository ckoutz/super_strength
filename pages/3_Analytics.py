import streamlit as st
import pandas as pd
import ast
import json


# -------------------------------------------------------------
# SAFE PARSER FOR LIST COLUMNS
# -------------------------------------------------------------
def safe_parse_list(val):
    """
    Safely parse list-like fields in the CSV.
    
    Supports:
        - Valid JSON lists
        - Python literal lists/dicts
        - Empty strings
        - NaN
    Always returns a list.
    """
    if not isinstance(val, str):
        return []

    s = val.strip()
    if s == "":
        return []

    # Try JSON first
    if s.startswith("[") and "{" in s:
        try:
            return json.loads(s)
        except Exception:
            pass

    # Try Python literal
    try:
        parsed = ast.literal_eval(s)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


# -------------------------------------------------------------
# LOAD LOGS
# -------------------------------------------------------------
@st.cache_data
def load_logs():
    try:
        df = pd.read_csv("training_log.csv")
    except FileNotFoundError:
        return pd.DataFrame()

    # Fix date parsing
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    # Columns that contain stored lists
    list_cols = ["strength_block", "cardio_sessions"]

    for col in list_cols:
        if col in df.columns:
            df[col] = df[col].apply(safe_parse_list)

    return df


# -------------------------------------------------------------
# PAGE LAYOUT
# -------------------------------------------------------------
st.title("📊 Training Analytics")

df = load_logs()

if df.empty:
    st.warning("No training data found yet. Complete a workout day to generate logs.")
    st.stop()


# -------------------------------------------------------------
# DATE FILTERING
# -------------------------------------------------------------
st.subheader("Filter Date Range")

col1, col2 = st.columns(2)
default_start = df["date"].min()
default_end = df["date"].max()

start_date = col1.date_input("Start", default_start)
end_date = col2.date_input("End", default_end)

# Convert to comparable format
mask = (df["date"] >= start_date) & (df["date"] <= end_date)
filtered = df.loc[mask]

st.write(f"Showing **{len(filtered)} entries** from **{start_date} → {end_date}**")

if filtered.empty:
    st.info("No logs in this date range.")
    st.stop()


# -------------------------------------------------------------
# RAW TABLE VIEW
# -------------------------------------------------------------
st.subheader("Raw Log Data")
st.dataframe(filtered, use_container_width=True)


# -------------------------------------------------------------
# BASIC SUMMARY STATS
# -------------------------------------------------------------
st.subheader("Summary Metrics")

total_strength_sessions = filtered["strength_block"].apply(lambda x: len(x) > 0).sum()
total_cardio_sessions = filtered["cardio_sessions"].apply(lambda x: len(x) > 0).sum()

colA, colB = st.columns(2)
colA.metric("Strength Days Logged", total_strength_sessions)
colB.metric("Cardio Sessions Logged", total_cardio_sessions)


# -------------------------------------------------------------
# VOLUME ANALYSIS (SETS × REPS × WEIGHT)
# -------------------------------------------------------------
st.subheader("Strength Volume Analysis")

def calc_volume(str_block):
    """
    Computes volume = sum(weight * reps) for last set of each exercise.
    """
    vol = 0
    for ex in str_block:
        try:
            reps = float(ex.get("reps", 0))
            wt = float(ex.get("weight", 0))
            vol += reps * wt
        except:
            pass
    return vol

filtered["volume"] = filtered["strength_block"].apply(calc_volume)
st.line_chart(filtered.set_index("date")["volume"])


# -------------------------------------------------------------
# EXPORT OPTIONS
# -------------------------------------------------------------
st.subheader("Export Data")

csv = filtered.to_csv(index=False).encode("utf-8")

st.download_button(
    "Download Filtered CSV",
    csv,
    "training_logs_filtered.csv",
    "text/csv",
)

st.success("Analytics page is fully operational.")


