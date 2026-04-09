import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🏭 P10 - Simulation industrielle")

# =============================
# PARAMÈTRES
# =============================

MAX_BUFFER = st.sidebar.slider("Attente max (min)", 0, 60, 20)

pause = st.sidebar.selectbox(
    "Pause midi",
    ["Aucune", "Active (12h-13h)"]
)

# =============================
# CONFIG
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

        # =============================
        # PREMIER CYCLE
        # =============================
        if not first_cycle_done[bras]:
            four_time = t["four"] + 2
            first_cycle_done[bras] = True
        else:
            four_time = t["four"]

        start_four = current_time
        end_four = start_four + timedelta(minutes=four_time)
        end_cool = end_four + timedelta(minutes=t["cool"])

        # =============================
        # PAUSE MIDI (bloque déco)
        # =============================
        if pause == "Active (12h-13h)":
            if deco_available >= pause_start and deco_available < pause_end:
                deco_available = pause_end

        start_deco = max(end_cool, deco_available)
        wait = (start_deco - end_cool).total_seconds() / 60

        # =============================
        # BYPASS (VRAI COMPORTEMENT)
        # =============================
        if wait > MAX_BUFFER:

            rows.append({
                "Bras": bras,
                "Zone": "Bypass",
                "Start": current_time,
                "End": current_time + timedelta(minutes=3)
            })

            # 👉 on avance juste le carrousel
            current_time += timedelta(minutes=3)
            index += 1
            continue

        end_deco = start_deco + timedelta(minutes=t["deco"])

        if end_deco > end_time:
            break

        # FOUR
        rows.append({"Bras": bras, "Zone": "Four", "Start": start_four, "End": end_four})

        # REFROID
        rows.append({"Bras": bras, "Zone": "Refroidissement", "Start": end_four, "End": end_cool})

        # ATTENTE
        if start_deco > end_cool:
            rows.append({"Bras": bras, "Zone": "Attente", "Start": end_cool, "End": start_deco})

        # DECO
        rows.append({"Bras": bras, "Zone": "Décoffrage", "Start": start_deco, "End": end_deco})

        current_time = end_four + MOVE
        deco_available = end_deco
        index += 1

    return pd.DataFrame(rows)

# =============================
# RUN
# =============================

df = simulate()

# =============================
# TABLE PROPRE (ORDRE BRAS)
# =============================

st.subheader("📋 Vue globale")

df_table = df.copy()

df_table["Start"] = df_table["Start"].dt.strftime("%H:%M")
df_table["End"] = df_table["End"].dt.strftime("%H:%M")

# tri correct
df_table["Bras_num"] = df_table["Bras"].str.extract(r'(\d+)').astype(int)
df_table = df_table.sort_values(["Bras_num", "Start"])

st.dataframe(df_table.drop(columns="Bras_num"))

# =============================
# ZOOM PAR BRAS
# =============================

bras_selected = st.selectbox(
    "🔎 Zoom sur un bras",
    ["Tous"] + sorted(df["Bras"].unique())
)

if bras_selected != "Tous":
    df_plot = df[df["Bras"] == bras_selected]
else:
    df_plot = df

# =============================
# GANTT
# =============================

st.subheader("📊 Gantt industriel")

fig = px.timeline(
    df_plot,
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

fig.update_xaxes(
    tickformat="%H:%M",
    title="Heure"
)

st.plotly_chart(fig, use_container_width=True)
