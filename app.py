import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.title("🏭 P10 - Simulation basée sur Excel")

# =============================
# PARAMÈTRES
# =============================

st.sidebar.header("Paramètres")

jour = st.sidebar.selectbox("Jour", ["Lundi"])

# =============================
# TEMPS PROCESS
# =============================

TIMES = {
    "cuve": {"four": 45, "cool": 46, "deco": 60},
    "cloison": {"four": 35, "cool": 45, "deco": 40}
}

# =============================
# CONFIG RÉELLE (Excel)
# =============================

STARTS = {
    4: datetime(2024, 1, 1, 6, 25),
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
# SIMULATION
# =============================

def simulate():

    rows = []

    for bras in BRAS_TYPE:

        current = STARTS[bras]
        prod = BRAS_TYPE[bras]
        t = TIMES[prod]

        first = True
        cycle = 0

        while current < END_TIME:

            cycle += 1

            # =============================
            # BYPASS (comme Excel)
            # =============================
            if cycle % 3 == 0:

                bypass_start = current
                bypass_end = current + timedelta(minutes=3)

                rows.append({
                    "Bras": bras,
                    "Type": "BYPASS",
                    "Four début": f(bypass_start),
                    "Four fin": f(bypass_end),
                    "Refroid fin": f(bypass_end),
                    "Décoffrage fin": f(bypass_end),
                    "Note": "By-pass (tampon)"
                })

                current = bypass_end
                continue

            # =============================
            # FOUR
            # =============================
            four_time = t["four"] + (2 if first else 0)
            four_start = current
            four_end = four_start + timedelta(minutes=four_time)

            # =============================
            # REFROIDISSEMENT
            # =============================
            cool_end = four_end + timedelta(minutes=t["cool"])

            # =============================
            # DECOFFRAGE
            # =============================
            deco_end = cool_end + timedelta(minutes=t["deco"])

            if deco_end > END_TIME:
                break

            rows.append({
                "Bras": bras,
                "Type": prod.capitalize(),
                "Four début": f(four_start),
                "Four fin": f(four_end),
                "Refroid fin": f(cool_end),
                "Décoffrage fin": f(deco_end),
                "Note": ""
            })

            current = four_end
            first = False

    return pd.DataFrame(rows)

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

col1, col2 = st.columns(2)

col1.metric("Production", f"{nb_pieces} pièces")
col2.metric("By-pass", f"{nb_bypass}")

# =============================
# AFFICHAGE PAR BRAS
# =============================

st.subheader("📋 Flux détaillé")

for bras in sorted(df["Bras"].unique()):
    st.markdown(f"### Bras {bras}")
    st.dataframe(df[df["Bras"] == bras].drop(columns=["Bras"]))
