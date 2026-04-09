import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🏭 P10 - Simulation (base propre Excel)")

# =============================
# PARAMÈTRES
# =============================

MAX_LATENCE = st.sidebar.slider(
    "Latence max avant déco (min)",
    0, 60, 20
)

pause_active = st.sidebar.checkbox("Pause midi (12h-13h)", True)

# =============================
# CONFIG PROCESS
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

        # 🔥 premier cycle (+2 min)
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

        # 🔥 PAUSE MIDI (bloque déco uniquement)
        if pause_active:
            if deco_available >= pause_start and deco_available < pause_end:
                deco_available = pause_end

        # LATENCE
        start_deco = max(end_cool, deco_available)
        latence = (start_deco - end_cool).total_seconds() / 60

        # 🔥 AJUSTEMENT LATENCE (zone critique)
        if latence > MAX_LATENCE:
            delay = latence - MAX_LATENCE
            current_time += timedelta(minutes=delay)

            # recalcul
            start_four = current_time
            end_four = start_four + timedelta(minutes=four_time)
            end_cool = end_four + timedelta(minutes=t["cool"])
            start_deco = max(end_cool, deco_available)

        # DECO
        end_deco = start_deco + timedelta(minutes=t["deco"])

        if end_deco > end_time:
            break

        rows.append({
            "Bras": bras,
            "Produit": prod.capitalize(),
            "Four début": start_four,
            "Four fin": end_four,
            "Refroid fin": end_cool,
            "Déco début": start_deco,
            "Déco fin": end_deco,
            "Latence": round((start_deco - end_cool).total_seconds()/60,1)
        })

        # UPDATE
        current_time = end_four + MOVE
        deco_available = end_deco
        index += 1

    return pd.DataFrame(rows)

# =============================
# RUN
# =============================

df = simulate()

# =============================
# TABLE GLOBAL (CORRIGÉE)
# =============================

st.subheader("📋 Flux global")

df_display = df.copy()

# format heure
for col in ["Four début","Four fin","Refroid fin","Déco début","Déco fin"]:
    df_display[col] = df_display[col].dt.strftime("%H:%M")

# 🔥 TRI PROPRE PAR BRAS
df_display["Bras"] = pd.Categorical(
    df_display["Bras"],
    categories=["Bras 1", "Bras 2", "Bras 3", "Bras 4"],
    ordered=True
)

df_display = df_display.sort_values(["Bras","Four début"]).reset_index(drop=True)

st.dataframe(df_display, use_container_width=True)

# =============================
# GANTT SIMPLE
# =============================

st.subheader("📊 Gantt")

gantt_rows = []

for _, row in df.iterrows():

    gantt_rows.append({
        "Bras": row["Bras"],
        "Zone": "Four",
        "Start": row["Four début"],
        "End": row["Four fin"]
    })

    gantt_rows.append({
        "Bras": row["Bras"],
        "Zone": "Refroidissement",
        "Start": row["Four fin"],
        "End": row["Refroid fin"]
    })

    gantt_rows.append({
        "Bras": row["Bras"],
        "Zone": "Décoffrage",
        "Start": row["Déco début"],
        "End": row["Déco fin"]
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
fig.update_xaxes(tickformat="%H:%M", title="Heure")

st.plotly_chart(fig, use_container_width=True)

# =============================
# KPI
# =============================

st.subheader("📊 KPI")

col1, col2 = st.columns(2)

col1.metric("Production", len(df))
col2.metric("Latence max", int(df["Latence"].max()))
