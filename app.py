import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.title("🏭 Simulation P10 avec contraintes")

# =============================
# PARAMÈTRES
# =============================

st.sidebar.header("Paramètres")

jour = st.sidebar.selectbox(
    "Jour",
    ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
)

NB_BRAS = 4
MAX_WAIT = 20  # minutes

# Heures de départ selon jour
if jour == "Lundi":
    start_time = datetime(2024, 1, 1, 6, 25)
else:
    start_time = datetime(2024, 1, 1, 4, 52)

end_time = datetime(2024, 1, 1, 21, 45)

CLOISON = {"four": 35, "cool": 45, "deco": 40}
CUVE = {"four": 45, "cool": 46, "deco": 60}

# =============================
# FORMAT HEURE
# =============================

def format_time(dt):
    return dt.strftime("%H:%M")

# =============================
# SIMULATION
# =============================

def simulate_day():

    bras_times = [start_time] * NB_BRAS
    deco_available = start_time

    results = []
    first_cycle = True

    while True:

        for bras in range(NB_BRAS):

            current_time = bras_times[bras]

            if current_time >= end_time:
                return pd.DataFrame(results)

            for prod in ["cloison", "cuve"]:

                t = CLOISON if prod == "cloison" else CUVE

                # FOUR
                four_time = t["four"] + (2 if first_cycle else 0)
                end_four = current_time + timedelta(minutes=four_time)

                # REFROIDISSEMENT
                end_cool = end_four + timedelta(minutes=t["cool"])

                # DÉCOFFRAGE
                start_deco = max(end_cool, deco_available)
                wait = (start_deco - end_cool).total_seconds() / 60

                # BY-PASS si attente trop grande
                if wait > MAX_WAIT:
                    results.append({
                        "Bras": bras + 1,
                        "Type": "BYPASS",
                        "Début": format_time(current_time),
                        "Fin": format_time(current_time),
                        "Attente (min)": round(wait, 1)
                    })

                    bras_times[bras] = current_time + timedelta(minutes=5)
                    break

                end_deco = start_deco + timedelta(minutes=t["deco"])

                if end_deco > end_time:
                    return pd.DataFrame(results)

                results.append({
                    "Bras": bras + 1,
                    "Type": prod.capitalize(),
                    "Début": format_time(current_time),
                    "Fin": format_time(end_deco),
                    "Attente (min)": round(wait, 1)
                })

                deco_available = end_deco
                current_time = end_four
                bras_times[bras] = current_time

                first_cycle = False

    return pd.DataFrame(results)

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

col1.metric("Production totale", f"{nb_pieces} pièces")
col2.metric("By-pass", f"{nb_bypass} cycles")
col3.metric("Attente max", f"{int(max_wait)} min")

# =============================
# TABLE
# =============================

st.subheader("📋 Planning")

st.dataframe(df)

# =============================
# ALERTES
# =============================

st.subheader("🚨 Qualité")

risk_df = df[df["Attente (min)"] > MAX_WAIT]

if len(risk_df) > 0:
    st.error(f"{len(risk_df)} pièces à risque (> {MAX_WAIT} min)")
else:
    st.success("Aucun risque qualité")
