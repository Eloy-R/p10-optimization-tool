import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🏭 P10 - Simulation industrielle")

# =============================
# PARAMÈTRES
# =============================

st.sidebar.header("Paramètres")

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

start_time = datetime(2024, 1, 1, 6, 25)
end_time = datetime(2024, 1, 1, 21, 45)

# pause midi fixe 12h-13h
pause_start = datetime(2024, 1, 1, 12, 0)
pause_end = datetime(2024, 1, 1, 13, 0)

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

        # pause midi bloque décoffrage
        if pause != "Aucune":
            if deco_available >= pause_start and deco_available < pause_end:
                deco_available = pause_end

        # ATTENTE
        start_deco = max(end_cool, deco_available)
        wait = (start_deco - end_cool).total_seconds() / 60

        # 🔥 BYPASS SI ATTENTE TROP GRANDE
        if wait > MAX_BUFFER:

            bypass_start = current_time
            bypass_end = current_time + timedelta(minutes=3)

            rows.append({
                "Bras": bras,
                "Zone": "Bypass",
                "Start": bypass_start,
                "End": bypass_end
            })

            current_time = bypass_end
            continue

        # DECO
        end_deco = start_deco + timedelta(minutes=t["deco"])

        if end_deco > end_time:
            break

        # FOUR
        rows.append({
            "Bras": bras,
            "Zone": "Four",
            "Start": start_four,
            "End": end_four
        })

        # REFROID
        rows.append({
            "Bras": bras,
            "Zone": "Refroidissement",
            "Start": end_four,
            "End": end_cool
        })

        # ATTENTE VISUELLE
        if start_deco > end_cool:
            rows.append({
                "Bras": bras,
                "Zone": "Attente",
                "Start": end_cool,
                "End": start_deco
            })

        # DECO
        rows.append({
            "Bras": bras,
            "Zone": "Décoffrage",
            "Start": start_deco,
            "End": end_deco
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

col1.metric("Segments", len(df))
col2.metric("Bypass", len(df[df["Zone"] == "Bypass"]))

# =============================
# GANTT PRO
# =============================

st.subheader("📊 Gantt industriel")

fig = px.timeline(
    df,
    x_start="Start",
    x_end="End",
    y="Bras",
    color="Zone",
    color_discrete_map={
        "Four": "red",
        "Refroidissement": "blue",
        "Décoffrage": "green",
        "Attente": "orange",
        "Bypass": "yellow"
    }
)

fig.update_yaxes(autorange="reversed")

st.plotly_chart(fig, use_container_width=True)

# =============================
# TABLE
# =============================

st.subheader("📋 Détail")

df_display = df.copy()
df_display["Start"] = df_display["Start"].dt.strftime("%H:%M")
df_display["End"] = df_display["End"].dt.strftime("%H:%M")

st.dataframe(df_display)
