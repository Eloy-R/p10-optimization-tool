import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.title("🏭 P10 - Flux par bras (version claire)")

# =============================
# PARAMÈTRES
# =============================

st.sidebar.header("Paramètres")

jour = st.sidebar.selectbox(
    "Jour",
    ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
)

# Heure de départ
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
    "cuve": {"four": 45, "cool1": 20, "cool2": 26, "buffer": 5, "deco": 60},
    "cloison": {"four": 35, "cool1": 20, "cool2": 25, "buffer": 5, "deco": 40}
}

# =============================
# FORMAT
# =============================

def f(t):
    return t.strftime("%H:%M")

# =============================
# SIMULATION SIMPLE PAR BRAS
# =============================

def simulate():

    rows = []

    for bras in BRAS_CONFIG:

        current_time = start_time
        prod = BRAS_CONFIG[bras]
        t = TIMES[prod]

        first_cycle = True

        while current_time < end_time:

            # FOUR
            four_time = t["four"] + (2 if first_cycle else 0)
            four_start = current_time
            four_end = four_start + timedelta(minutes=four_time)

            # REFROID 1
            cool1_end = four_end + timedelta(minutes=t["cool1"])

            # REFROID 2
            cool2_end = cool1_end + timedelta(minutes=t["cool2"])

            # TAMPON
            buffer_end = cool2_end + timedelta(minutes=t["buffer"])

            # DECOFFRAGE
            deco_end = buffer_end + timedelta(minutes=t["deco"])

            if deco_end > end_time:
                break

            rows.append({
                "Bras": bras,
                "Produit": prod.capitalize(),
                "Four début": f(four_start),
                "Sortie four": f(four_end),
                "Refroid 1": f(cool1_end),
                "Refroid 2": f(cool2_end),
                "Tampon": f(buffer_end),
                "Fin décoffrage": f(deco_end)
            })

            # prochain cycle = après four
            current_time = four_end
            first_cycle = False

    return pd.DataFrame(rows)

# =============================
# RUN
# =============================

df = simulate()

# =============================
# AFFICHAGE
# =============================

st.subheader("📋 Flux clair par bras")

for bras in sorted(df["Bras"].unique()):
    st.markdown(f"### Bras {bras}")
    st.dataframe(df[df["Bras"] == bras].drop(columns=["Bras"]))
