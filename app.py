import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.set_page_config(layout="wide")

st.title("🏭 P10 - Simulation + Gantt")

# =============================
# PARAMÈTRES
# =============================

st.sidebar.header("Paramètres")

jour = st.sidebar.selectbox("Jour", ["Lundi"])

MAX_BUFFER = st.sidebar.slider(
    "Temps max avant décoffrage (min)",
    0, 60, 20
)

pause = st.sidebar.selectbox(
    "Pause de midi",
    ["Aucune", "30 min", "1 heure"]
)

# =============================
# TEMPS PROCESS
# =============================

TIMES = {
    "cuve": {"four": 45, "cool": 46, "deco": 60},
    "cloison": {"four": 35, "cool": 45, "deco": 40}
}

BRAS_ORDER = [
    ("Bras 4", "cloison"),
    ("Bras 1", "cuve"),
    ("Bras 2", "cloison"),
    ("Bras 3", "cuve"),
]

# =============================
# HORAIRES
# =============================

start_time = datetime(2024, 1, 1, 6, 25)
end_time = datetime(2024, 1, 1, 21, 45)

# pause midi (12:00)
pause_start = datetime(2024, 1, 1, 12, 0)

if pause == "30 min":
    pause_duration = timedelta(minutes=30)
elif pause == "1 heure":
    pause_duration = timedelta(hours=1)
else:
    pause_duration = timedelta(minutes=0)

pause_end = pause_start + pause_duration

MOVE = timedelta(minutes=1)

# =============================
# SIMULATION
# =============================

def simulate():

    rows = []

    current_time = start_time
    deco_available = start_time

    index = 0

    first_cycle_done = {b: False for b, _ in BRAS_ORDER}

    while current_time < end_time:

        bras, prod = BRAS_ORDER[index % len(BRAS_ORDER)]
        t = TIMES[prod]

        # pause midi (bloque décoffrage)
        if pause_duration > timedelta(0):
            if deco_available >= pause_start and deco_available < pause_end:
                deco_available = pause_end

        # premier cycle
        if not first_cycle_done[bras]:
            four_time = t["four"] + 2
            first_cycle_done[bras] = True
        else:
            four_time = t["four"]

        # FOUR
        start_four = current_time
        end_four = start_four + timedelta(minutes=four_time)

        # REFROID
        end_cool = end_four + timedelta(minutes=t["cool"])

        # latence intelligente
        projected_start_deco = max(end_cool, deco_available)
        wait_time = (projected_start_deco - end_cool).total_seconds() / 60

        if wait_time > MAX_BUFFER:
            delay = wait_time - MAX_BUFFER
            current_time += timedelta(minutes=delay)

            start_four = current_time
            end_four = start_four + timedelta(minutes=four_time)
            end_cool = end_four + timedelta(minutes=t["cool"])

        # DECOFFRAGE
        start_deco = max(end_cool, deco_available)
        end_deco = start_deco + timedelta(minutes=t["deco"])

        if end_deco > end_time:
            break

        rows.append({
            "Bras": bras,
            "Produit": prod.capitalize(),
            "Start": start_four,
            "End": end_deco,
            "Type": prod
        })

        current_time = end_four + MOVE
        deco_available = end_deco
        index += 1

    return pd.DataFrame(rows)

# =============================
# RUN
# =============================

df = simulate()

# =============================
# KPI
# =============================

st.subheader("📊 KPI")

col1, col2 = st.columns(2)

col1.metric("Production", len(df))

# =============================
# GANTT VISUEL
# =============================

st.subheader("📊 Gantt de production")

if not df.empty:

    gantt_df = df.copy()
    gantt_df["Start_num"] = gantt_df["Start"].astype("int64") / 1e9
    gantt_df["Duration"] = (gantt_df["End"] - gantt_df["Start"]).dt.total_seconds() / 60

    chart = st.bar_chart(
        data=gantt_df,
        x="Start_num",
        y="Duration",
        horizontal=True
    )

# =============================
# TABLE
# =============================

st.subheader("📋 Détail")

df_display = df.copy()
df_display["Start"] = df_display["Start"].dt.strftime("%H:%M")
df_display["End"] = df_display["End"].dt.strftime("%H:%M")

st.dataframe(df_display)
