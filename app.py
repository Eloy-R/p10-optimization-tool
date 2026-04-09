import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.set_page_config(layout="wide")

st.title("🏭 P10 - Simulation globale (fidèle Excel + latence)")

# =============================
# PARAMÈTRES
# =============================

st.sidebar.header("Paramètres")

jour = st.sidebar.selectbox("Jour", ["Lundi"])

MAX_BUFFER = st.sidebar.slider(
    "Temps max avant décoffrage (min)",
    0, 60, 20
)

# =============================
# TEMPS PROCESS
# =============================

TIMES = {
    "cuve": {"four": 45, "cool": 46, "deco": 60},
    "cloison": {"four": 35, "cool": 45, "deco": 40}
}

# Ordre réel carrousel
BRAS_ORDER = [
    ("Bras 4", "cloison"),
    ("Bras 1", "cuve"),
    ("Bras 2", "cloison"),
    ("Bras 3", "cuve"),
]

# =============================
# HORAIRES
# =============================

if jour == "Lundi":
    start_time = datetime(2024, 1, 1, 6, 25)
else:
    start_time = datetime(2024, 1, 1, 4, 52)

end_time = datetime(2024, 1, 1, 21, 45)

MOVE = timedelta(minutes=1)

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

    current_time = start_time
    deco_available = start_time

    index = 0

    # suivi premier cycle par bras
    first_cycle_done = {
        "Bras 1": False,
        "Bras 2": False,
        "Bras 3": False,
        "Bras 4": False
    }

    while current_time < end_time:

        bras, prod = BRAS_ORDER[index % len(BRAS_ORDER)]
        t = TIMES[prod]

        # =============================
        # PREMIER CYCLE (+2 min)
        # =============================
        if not first_cycle_done[bras]:
            four_time = t["four"] + 2
            first_cycle_done[bras] = True
        else:
            four_time = t["four"]

        # =============================
        # FOUR
        # =============================
        start_four = current_time
        end_four = start_four + timedelta(minutes=four_time)

        # =============================
        # REFROID
        # =============================
        end_cool = end_four + timedelta(minutes=t["cool"])

        # =============================
        # TEST LATENCE (clé)
        # =============================
        projected_start_deco = max(end_cool, deco_available)
        wait_time = (projected_start_deco - end_cool).total_seconds() / 60

        # 👉 correction intelligente (comme opérateur)
        if wait_time > MAX_BUFFER:

            delay = wait_time - MAX_BUFFER
            current_time += timedelta(minutes=delay)

            # recalcul
            start_four = current_time
            end_four = start_four + timedelta(minutes=four_time)
            end_cool = end_four + timedelta(minutes=t["cool"])

        # =============================
        # DECOFFRAGE
        # =============================
        start_deco = max(end_cool, deco_available)
        end_deco = start_deco + timedelta(minutes=t["deco"])

        if end_deco > end_time:
            break

        rows.append({
            "Bras": bras,
            "Produit": prod.capitalize(),
            "Four début": f(start_four),
            "Four fin": f(end_four),
            "Refroid fin": f(end_cool),
            "Décoffrage début": f(start_deco),
            "Décoffrage fin": f(end_deco),
            "Attente (min)": round((start_deco - end_cool).total_seconds() / 60, 1)
        })

        # =============================
        # UPDATE GLOBAL
        # =============================
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

col1.metric("Production totale", len(df))
col2.metric("Attente max", int(df["Attente (min)"].max()))
col3.metric("Attente moyenne", int(df["Attente (min)"].mean()))

# =============================
# TABLE GLOBALE
# =============================

st.subheader("📋 Flux global")

st.dataframe(df)

# =============================
# VUE PAR BRAS
# =============================

st.subheader("📊 Vue par bras")

for bras in df["Bras"].unique():
    st.markdown(f"### {bras}")
    st.dataframe(df[df["Bras"] == bras].drop(columns=["Bras"]))
