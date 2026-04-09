import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.title("🏭 Simulation P10 avec contraintes")

# =============================
# PARAMÈTRES
# =============================

start_time = datetime(2024, 1, 1, 4, 52)
end_time = datetime(2024, 1, 1, 21, 45)

NB_BRAS = 4
MAX_WAIT = 20  # minutes

CLOISON = {"four": 35, "cool": 45, "deco": 40}
CUVE = {"four": 45, "cool": 46, "deco": 60}

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

            # alternance cloison / cuve
            for prod in ["cloison", "cuve"]:

                if prod == "cloison":
                    t = CLOISON
                else:
                    t = CUVE

                # FOUR
                four_time = t["four"] + (2 if first_cycle else 0)
                end_four = current_time + timedelta(minutes=four_time)

                # REFROIDISSEMENT
                end_cool = end_four + timedelta(minutes=t["cool"])

                # DÉCOFFRAGE (goulot)
                start_deco = max(end_cool, deco_available)
                wait = (start_deco - end_cool).total_seconds() / 60

                # 👉 BY-PASS si attente trop grande
                if wait > MAX_WAIT:
                    results.append({
                        "bras": bras,
                        "type": "BYPASS",
                        "start": current_time,
                        "end": current_time,
                        "wait": wait
                    })

                    # on avance juste le bras (simulation passage vide)
                    bras_times[bras] = current_time + timedelta(minutes=5)
                    break

                end_deco = start_deco + timedelta(minutes=t["deco"])

                if end_deco > end_time:
                    return pd.DataFrame(results)

                results.append({
                    "bras": bras,
                    "type": prod,
                    "start": current_time,
                    "end": end_deco,
                    "wait": wait
                })

                # update ressources
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

col1, col2, col3 = st.columns(3)

col1.metric("Total pièces", len(df[df["type"] != "BYPASS"]))
col2.metric("By-pass", len(df[df["type"] == "BYPASS"]))
col3.metric("Attente max", int(df["wait"].max()))

# =============================
# TABLE
# =============================

st.dataframe(df)

# =============================
# ALERTES
# =============================

st.subheader("🚨 Risques")

risk_df = df[df["wait"] > MAX_WAIT]

if len(risk_df) > 0:
    st.error(f"{len(risk_df)} pièces en risque")
else:
    st.success("Aucun risque qualité")
