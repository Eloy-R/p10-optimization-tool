import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.title("🏭 P10 - Reproduction Excel")

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

# =============================
# DÉCALAGE RÉEL (TRÈS IMPORTANT)
# =============================

STARTS = {
    4: datetime(2024, 1, 1, 6, 25),  # bras 4 commence
    1: datetime(2024, 1, 1, 7, 3),
    2: datetime(2024, 1, 1, 7, 51),
    3: datetime(2024, 1, 1, 8, 12),
}

BRAS_TYPE = {
    1: "cuve",
    2: "cloison",
    3: "cuve",
    4: "cloison"
}

END_TIME = datetime(2024, 1, 1, 21, 45)

# =============================
# FORMAT
# =============================

def f(t):
    return t.strftime("%H:%M")

# =============================
# SIMULATION (FIDÈLE)
# =============================

def simulate():

    rows = []

    for bras in BRAS_TYPE:

        current = STARTS[bras]
        prod = BRAS_TYPE[bras]
        t = TIMES[prod]

        first = True

        while current < END_TIME:

            # FOUR
            four_time = t["four"] + (2 if first else 0)
            four_start = current
            four_end = four_start + timedelta(minutes=four_time)

            # REFROID
            cool_end = four_end + timedelta(minutes=t["cool"])

            # DECO
            deco_end = cool_end + timedelta(minutes=t["deco"])

            if deco_end > END_TIME:
                break

            rows.append({
                "Bras": bras,
                "Produit": prod,
                "Four début": f(four_start),
                "Four fin": f(four_end),
                "Refroid fin": f(cool_end),
                "Décoffrage fin": f(deco_end)
            })

            current = four_end
            first = False

    return pd.DataFrame(rows)

# =============================
# RUN
# =============================

df = simulate()

# =============================
# AFFICHAGE
# =============================

for bras in sorted(df["Bras"].unique()):
    st.subheader(f"Bras {bras}")
    st.dataframe(df[df["Bras"] == bras].drop(columns=["Bras"]))
