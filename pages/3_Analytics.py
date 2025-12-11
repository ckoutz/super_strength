import streamlit as st
import pandas as pd
import json
from datetime import date, timedelta

st.set_page_config(page_title="Training Analytics", layout="wide")
st.title("Training Analytics Dashboard")

LOG_PATH = "training_log.csv"


# -----------------------------------------------------------------------
# Load + Normalize
# -----------------------------------------------------------------------
@st.cache_data
def load_logs():
    try:
        df = pd.read_csv(LOG_PATH)
    except FileNotFoundError:
        return pd.DataFrame()

    # Convert date field
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date

    # Parse JSON columns
    for col in ["strength_block", "cardio_sessions"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: json.loads(x) if isinstance(x, str) and x.startswith("[") else [])

    return df


df = load_logs()

if df.empty:
    st.warning("No training logs found.")
    st.stop()


# -----------------------------------------------------------------------
# Sidebar Filters
# -----------------------------------------------------------------------
st.sidebar.header("Filters")

end_date = st.sidebar.date_input("End Date", value=date.today())
start_date = st.sidebar.date_input("Start Date", value=end_date - timedelta(days=30))

mask = (df["date"] >= start_date) & (df["date"] <= end_date)
df_f = df[mask].sort_values("date")

st.sidebar.write(f"Loaded **{len(df_f)} days** of logs.")


# -----------------------------------------------------------------------
# TRAINING VOLUME SUMMARY
# -----------------------------------------------------------------------
st.subheader("Strength Volume Summary")

volume_rows = []

for _, row in df_f.iterrows():
    for ex in row["strength_block"]:
        sets = ex.get("sets", 0)
        reps = ex.get("reps", 0)
        weight = ex.get("weight", 0)

        try:
            volume = int(sets) * int(reps) * float(weight)
        except:
            volume = None

        volume_rows.append({
            "date": row["date"],
            "exercise": ex.get("exercise_name", ""),
            "sets": sets,
            "reps": reps,
            "weight": weight,
            "volume": volume
        })

vol_df = pd.DataFrame(volume_rows)

if not vol_df.empty:
    # Weekly volume
    vol_df["week"] = vol_df["date"].apply(lambda d: d.isocalendar()[1])
    weekly_volume = vol_df.groupby("week")["volume"].sum()

    st.line_chart(weekly_volume, height=250)

    # Per-exercise breakdown
    ex_vol = vol_df.groupby("exercise")["volume"].sum().sort_values(ascending=False)
    st.bar_chart(ex_vol, height=300)
else:
    st.info("No strength volume data.")


# -----------------------------------------------------------------------
# CARDIO ANALYTICS
# -----------------------------------------------------------------------
st.subheader("Cardio Analytics")

cardio_rows = []

for _, row in df_f.iterrows():
    for c in row["cardio_sessions"]:
        cardio_rows.append({
            "date": row["date"],
            "name": c.get("name", ""),
            "duration": float(c.get("duration_min", 0)),
            "distance": float(c.get("distance", 0) or 0),
            "avg_hr": float(c.get("avg_hr", 0) or 0),
            "max_hr": float(c.get("max_hr", 0) or 0),
        })

cardio_df = pd.DataFrame(cardio_rows)

if not cardio_df.empty:
    st.write("### Cardio Duration (Minutes per Day)")
    dur = cardio_df.groupby("date")["duration"].sum()
    st.area_chart(dur, height=250)

    st.write("### Average Heart Rate Over Time")
    hr = cardio_df.groupby("date")["avg_hr"].mean()
    st.line_chart(hr, height=250)

    st.write("### Distance Over Time")
    dist = cardio_df.groupby("date")["distance"].sum()
    st.line_chart(dist, height=250)

else:
    st.info("No cardio data logged.")


# -----------------------------------------------------------------------
# READINESS METRICS
# -----------------------------------------------------------------------
st.subheader("Readiness: HRV / Fatigue / Soreness / Mood")

readiness_cols = ["hrv", "fatigue_1_5", "soreness_1_5", "mood_1_5"]
ready_df = df_f[["date"] + readiness_cols].set_index("date")

st.line_chart(ready_df, height=300)

st.success("Analytics loaded successfully.")
