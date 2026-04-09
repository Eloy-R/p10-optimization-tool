import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.title("🏭 Simulation P10 - Carrousel réel (événementiel)")

# =============================
# PARAMÈTRES
# =============================

st.sidebar.header("Paramètres")

jour = st.sidebar.selectbox(
    "Jour",
    ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
)

MAX_WAIT = 20  # minutes
MOVE_TIME = 15  # secondes carrousel

# Heures
if jour == "Lundi":
    start_time = datetime(2024, 1, 1, 6, 25)
else:
    start_time = datetime(2024, 1, 1, 4, 52)

end_time = datetime(2024, 1, 1, 21, 45)

# =============================
# CONFIG BRAS
# =============================

BRAS_CONFIG = {
    1: "cuve",
    2: "cloison",
    3: "cuve",
    4: "cloison"
}

TIMES = {
    "cuve": {"four": 45, "cool": 46, "deco": 60},
    "cloison": {"four": 35, "cool": 45, "deco": 40}
}

# =============================
# FORMAT
# =============================

def format_time(dt):
    return dt.strftime("%H:%M:%S")

# =============================
# SIMULATION
# =============================

def simulate():

    current_time = start_time

    bras_next_event = {
        b: start_time for b in BRAS_CONFIG
    }

    deco_available = start_time
    events = []

    first_cycle = True

    while current_time < end_time:

        # 🔥 trouver le prochain événement (sortie four)
        next_bras = min(bras_next_event, key=bras_next_event.get)
        current_time = bras_next_event[next_bras]

        if current_time >= end_time:
            break

        prod = BRAS_CONFIG[next_bras]
        t = TIMES[prod]

        # FOUR
        four_time = t["four"] + (2 if first_cycle else 0)
        end_four = current_time + timedelta(minutes=four_time)

        # COOL
        end_cool = end_four + timedelta(minutes=t["cool"])

        # DECO
        start_deco = max(end_cool, deco_available)
        wait = (start_deco - end_cool).total_seconds() / 60

        # BYPASS
        if wait > MAX_WAIT:
            events.append({
                "Bras": next_bras,
                "Type": "BYPASS",
                "Début": format_time(current_time),
                "Fin": format_time(current_time),
                "Attente (min)": round(wait, 1)
            })

            # on retente au prochain cycle
            bras_next_event[next_bras] += timedelta(seconds=MOVE_TIME)
            continue

        end_deco = start_deco + timedelta(minutes=t["deco"])

        if end_deco > end_time:
            break

        events.append({
            "Bras": next_bras,
            "Type": prod.capitalize(),
            "Début": format_time(current_time),
            "Fin": format_time(end_deco),
            "Attente (min)": round(wait, 1)
        })

        deco_available = end_deco

        # 🔁 mouvement carrousel (TOUS les bras)
        for b in bras_next_event:
            bras_next_event[b] += timedelta(seconds=MOVE_TIME)

        first_cycle = False

    return pd.DataFrame(events)

# =============================
# RUN
# =============================

df = simulate()

# =============================
# KPI
# =============================

st.subheader("📊 KPI")

nb_pieces = len(df[df["Type"] != "BYPASS"])
nb_bypass = len(df[df["Type"] == "BYPASS"])
max_wait = df["Attente (min)"].max() if not df.empty else 0

col1, col2, col3 = st.columns(3)

col1.metric("Production", f"{nb_pieces} pièces")
col2.metric("By-pass", f"{nb_bypass}")
col3.metric("Attente max", f"{int(max_wait)} min")

# =============================
# TABLE
# =============================

st.subheader("📋 Flux réel")

st.dataframe(df)
