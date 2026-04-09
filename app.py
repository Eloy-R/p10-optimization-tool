import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.title("🏭 P10 - Simulation globale correcte")

# =============================
# PARAMÈTRES
# =============================

jour = st.selectbox("Jour", ["Lundi"])

# =============================
# TEMPS
# =============================

TIMES = {
    "cuve": {"four": 45, "cool": 46, "deco": 60},
    "cloison": {"four": 35, "cool": 45, "deco": 40}
}

# ordre des bras dans le carrousel
BRAS_ORDER = [
    ("bras 4", "cloison"),
    ("bras 1", "cuve"),
    ("bras 2", "cloison"),
    ("bras 3", "cuve"),
]

# heure de départ (lundi)
start_time = datetime(2024, 1, 1, 6, 25)
end_time = datetime(2024, 1, 1, 21, 45)

MOVE = timedelta(seconds=15)

# =============================
# FORMAT
# =============================

def f(t):
    return t.strftime("%H:%M")

# =============================
# SIMULATION GLOBALE
# =============================

def simulate():

    rows = []

    current_time = start_time
    deco_available = start_time

    index = 0
    first = True

    while current_time < end_time:

        bras, prod = BRAS_ORDER[index % len(BRAS_ORDER)]
        t = TIMES[prod]

        # FOUR
        four_time = t["four"] + (2 if first else 0)
        start_four = current_time
        end_four = start_four + timedelta(minutes=four_time)

        # REFROID
        end_cool = end_four + timedelta(minutes=t["cool"])

        # DECOFFRAGE
        start_deco = max(end_cool, deco_available)
        end_deco = start_deco + timedelta(minutes=t["deco"])

        if end_deco > end_time:
            break

        rows.append({
            "Bras": bras,
            "Produit": prod,
            "Four début": f(start_four),
            "Four fin": f(end_four),
            "Refroid fin": f(end_cool),
            "Décoffrage fin": f(end_deco),
        })

        # update
        current_time = end_four + MOVE
        deco_available = end_deco

        first = False
        index += 1

    return pd.DataFrame(rows)

# =============================
# RUN
# =============================

df = simulate()

# =============================
# AFFICHAGE
# =============================

st.subheader("📋 Flux global")

st.dataframe(df)

# affichage par bras
st.subheader("📊 Vue par bras")

for bras in df["Bras"].unique():
    st.markdown(f"### {bras}")
    st.dataframe(df[df["Bras"] == bras].drop(columns=["Bras"]))
