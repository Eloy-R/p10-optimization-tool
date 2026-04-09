import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.title("🏭 Simulation P10 (mode réel)")

# =============================
# PARAMÈTRES
# =============================

st.sidebar.header("Paramètres")

jour = st.sidebar.selectbox(
    "Jour",
    ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
)

MAX_WAIT = 20  # minutes

# Heures
if jour == "Lundi":
    start_time = datetime(2024, 1, 1, 6, 25)
else:
    start_time = datetime(2024, 1, 1, 4, 52)

end_time = datetime(2024, 1, 1, 21, 45)

# =============================
# CONFIG BRAS (IMPORTANT)
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
# FORMAT HEURE
# =============================

def format_time(dt):
    return dt.strftime("%H:%M")

# =============================
# SIMULATION
# =============================

def simulate_day():

    bras_times = {b: start_time for b in BRAS_CONFIG}
    deco_available = start_time

    events = []
    first_cycle = True

    while True:

        for bras in BRAS_CONFIG:

            current_time = bras_times[bras]

            if current_time >= end_time:
                return pd.DataFrame(events).sort_values("Start_real")

            prod = BRAS_CONFIG[bras]
            t = TIMES[prod]

            # FOUR
            four_time = t["four"] + (2 if first_cycle else 0)
            end_four = current_time + timedelta(minutes=four_time)

            # COOL
            end_cool = end_four + timedelta(minutes=t["cool"])

            # DECO (goulot)
            start_deco = max(end_cool, deco_available)
            wait = (start_deco - end_cool).total_seconds() / 60

            # BYPASS si problème
            if wait > MAX_WAIT:
                events.append({
                    "Bras": bras,
                    "Type": "BYPASS",
                    "Start_real": current_time,
                    "Début": format_time(current_time),
                    "Fin": format_time(current_time),
                    "Attente (min)": round(wait, 1)
                })

                bras_times[bras] += timedelta(minutes=5)
                continue

            end_deco = start_deco + timedelta(minutes=t["deco"])

            if end_deco > end_time:
                return pd.DataFrame(events).sort_values("Start_real")

            events.append({
                "Bras": bras,
                "Type": prod.capitalize(),
                "Start_real": current_time,
                "Début": format_time(current_time),
                "Fin": format_time(end_deco),
                "Attente (min)": round(wait, 1)
            })

            deco_available = end_deco

            # IMPORTANT : le bras avance selon le four (car carrousel)
            bras_times[bras] = end_four

            first_cycle = False

    return pd.DataFrame(events).sort_values("Start_real")

# =============================
# RUN
# =============================

df = simulate_day()

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
# TABLE ORDONNÉE
# =============================

st.subheader("📋 Ordre de passage réel")

df_display = df.drop(columns=["Start_real"])
st.dataframe(df_display)

# =============================
# ALERTES
# =============================

st.subheader("🚨 Qualité")

risk_df = df[df["Attente (min)"] > MAX_WAIT]

if len(risk_df) > 0:
    st.error(f"{len(risk_df)} pièces à risque")
else:
    st.success("Aucun risque qualité")
