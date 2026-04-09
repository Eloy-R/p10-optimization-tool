import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.title("🏭 P10 - Simulation Rotomoulage")

# =============================
# PARAMÈTRES
# =============================

st.sidebar.header("Paramètres")

jour = st.sidebar.selectbox(
    "Jour",
    ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
)

sequence_type = st.sidebar.selectbox(
    "Séquence",
    ["Cloison → Cuve", "Cuve → Cloison"]
)

# Heure départ
if jour == "Lundi":
    current_time = datetime(2024, 1, 1, 6, 25)
else:
    current_time = datetime(2024, 1, 1, 4, 52)

end_time = datetime(2024, 1, 1, 21, 45)

# =============================
# TEMPS PROCESS
# =============================

TIMES = {
    "cuve": {"four": 45, "cool": 46, "deco": 60},
    "cloison": {"four": 35, "cool": 45, "deco": 40}
}

MOVE = timedelta(seconds=15)

# =============================
# FORMAT
# =============================

def f(t):
    return t.strftime("%H:%M")

# =============================
# SIMULATION
# =============================

def simulate():

    rows = []
    deco_available = current_time

    first_cycle = True

    if sequence_type == "Cloison → Cuve":
        seq = ["cloison", "cuve"]
    else:
        seq = ["cuve", "cloison"]

    i = 0

    while current_time < end_time:

        prod = seq[i % 2]
        t = TIMES[prod]

        # FOUR
        four_time = t["four"] + (2 if first_cycle else 0)
        start_four = current_time
        end_four = start_four + timedelta(minutes=four_time)

        # REFROID
        end_cool = end_four + timedelta(minutes=t["cool"])

        # ZONE LATENTE
        start_deco = max(end_cool, deco_available)
        wait = (start_deco - end_cool).total_seconds() / 60

        # DECOFFRAGE
        end_deco = start_deco + timedelta(minutes=t["deco"])

        if end_deco > end_time:
            break

        rows.append({
            "Produit": prod.capitalize(),
            "Entrée four": f(start_four),
            "Sortie four": f(end_four),
            "Fin refroid": f(end_cool),
            "Début décoffrage": f(start_deco),
            "Fin décoffrage": f(end_deco),
            "Attente (min)": round(wait, 1)
        })

        # mise à jour
        current_time = end_four + MOVE  # rotation carrousel
        deco_available = end_deco

        first_cycle = False
        i += 1

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

col1.metric("Production totale", len(df))
col2.metric("Attente max", int(df["Attente (min)"].max()))

# =============================
# TABLE
# =============================

st.subheader("📋 Flux réel (four → sortie)")

st.dataframe(df)
