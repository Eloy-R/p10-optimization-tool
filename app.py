import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.title("🏭 P10 - Flux par bras (lecture claire)")

# =============================
# PARAMÈTRES
# =============================

st.sidebar.header("Paramètres")

jour = st.sidebar.selectbox(
    "Jour",
    ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
)

# Départ
if jour == "Lundi":
    start_time = datetime(2024, 1, 1, 6, 25)
else:
    start_time = datetime(2024, 1, 1, 4, 52)

end_time = datetime(2024, 1, 1, 21, 45)

# =============================
# CONFIG
# =============================

BRAS_CONFIG = {
    1: "cuve",
    2: "cloison",
    3: "cuve",
    4: "cloison"
}

TIMES = {
    "cuve": {"four": 45, "cool1": 20, "cool2": 26, "deco": 60},
    "cloison": {"four": 35, "cool1": 20, "cool2": 25, "deco": 40}
}

MOVE_TIME = 15  # secondes

# =============================
# FORMAT
# =============================

def f(t):
    return t.strftime("%H:%M:%S")

# =============================
# SIMULATION SIMPLE
# =============================

def simulate():

    current_time = start_time
    rows = []
    first_cycle = True

    while current_time < end_time:

        for bras in BRAS_CONFIG:

            prod = BRAS_CONFIG[bras]
            t = TIMES[prod]

            # FOUR
            four_time = t["four"] + (2 if first_cycle else 0)
            four_start = current_time
            four_end = four_start + timedelta(minutes=four_time)

            # REFROID 1
            cool1_end = four_end + timedelta(minutes=t["cool1"])

            # REFROID 2
            cool2_end = cool1_end + timedelta(minutes=t["cool2"])

            # ZONE TAMPON (fixe simple)
            buffer_end = cool2_end + timedelta(minutes=5)

            # DECOFFRAGE
            deco_end = buffer_end + timedelta(minutes=t["deco"])

            if deco_end > end_time:
                return pd.DataFrame(rows)

            rows.append({
                "Bras": bras,
                "Produit": prod.capitalize(),
                "Four début": f(four_start),
                "Sortie four": f(four_end),
                "Refroid 1": f(cool1_end),
                "Refroid 2": f(cool2_end),
                "Zone tampon": f(buffer_end),
                "Décoffrage fin": f(deco_end)
            })

        # mouvement carrousel
        current_time += timedelta(seconds=MOVE_TIME)
        first_cycle = False

    return pd.DataFrame(rows)

# =============================
# RUN
# =============================

df = simulate()

# =============================
# AFFICHAGE
# =============================

st.subheader("📋 Flux détaillé par bras")

for bras in sorted(df["Bras"].unique()):
    st.markdown(f"### Bras {bras}")
    st.dataframe(df[df["Bras"] == bras].drop(columns=["Bras"]))
