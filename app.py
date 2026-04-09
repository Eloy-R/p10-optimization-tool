import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🏭 P10 - Simulation + Gantt visuel")

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

pause_start = datetime(2024, 1, 1, 12, 0)

if pause == "30 min":
    pause_duration = timedelta(minutes=30)
elif pause == "1 heure":
    pause_duration = timedelta(hours=1)
else:
    pause_duration = timedelta(0)

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
            "Produit": prod,
            "Four_start": start_four,
            "Four_end": end_four,
            "Cool_start": end_four,
            "Cool_end": end_cool,
            "Deco_start": start_deco,
            "Deco_end": end_deco,
            "Wait": round((start_deco - end_cool).total_seconds()/60, 1)
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

col1, col2, col3 = st.columns(3)

col1.metric("Production", len(df))
col2.metric("Attente max", int(df["Wait"].max()))
col3.metric("Attente moyenne", int(df["Wait"].mean()))

# =============================
# TABLE GLOBALE
# =============================

st.subheader("📋 Flux global")

df_display = df.copy()

for col in ["Four_start","Four_end","Cool_start","Cool_end","Deco_start","Deco_end"]:
    df_display[col] = df_display[col].dt.strftime("%H:%M")

st.dataframe(df_display)

# =============================
# GANTT VISUEL PROPRE
# =============================

st.subheader("📊 Gantt par bras (zones visibles)")

gantt_rows = []

for _, row in df.iterrows():

    gantt_rows.append({
        "Bras": row["Bras"],
        "Zone": "Four",
        "Start": row["Four_start"],
        "End": row["Four_end"]
    })

    gantt_rows.append({
        "Bras": row["Bras"],
        "Zone": "Refroidissement",
        "Start": row["Cool_start"],
        "End": row["Cool_end"]
    })

    gantt_rows.append({
        "Bras": row["Bras"],
        "Zone": "Décoffrage",
        "Start": row["Deco_start"],
        "End": row["Deco_end"]
    })

gantt_df = pd.DataFrame(gantt_rows)

fig = px.timeline(
    gantt_df,
    x_start="Start",
    x_end="End",
    y="Bras",
    color="Zone",
    color_discrete_map={
        "Four": "red",
        "Refroidissement": "blue",
        "Décoffrage": "green"
    }
)

fig.update_yaxes(autorange="reversed")

st.plotly_chart(fig, use_container_width=True)
