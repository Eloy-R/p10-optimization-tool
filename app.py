import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.set_page_config(layout="wide")

st.title("🏭 P10 - Simulation (logique terrain correcte)")

# =============================
# PARAMÈTRES
# =============================

MAX_LATENCE = st.sidebar.slider(
    "Latence max avant déco (min)",
    0, 60, 20
)

pause_active = st.sidebar.checkbox("Pause midi (12h-13h)", True)

# =============================
# CONFIG
# =============================

TIMES = {
    "cuve": {"four": 45, "cool": 46, "deco": 60},
    "cloison": {"four": 35, "cool": 45, "deco": 40}
}

BRAS_ORDER = [
    ("Bras 4", "cloison"),
    ("Bras 1", "cuve"),
    ("Bras 2", "cloison"),
    ("Bras 3", "cuve"),
]

start_time = datetime(2024, 1, 1, 6, 25)
end_time = datetime(2024, 1, 1, 21, 45)

pause_start = datetime(2024, 1, 1, 12, 0)
pause_end = datetime(2024, 1, 1, 13, 0)

MOVE = timedelta(minutes=1)

# =============================
# SIMULATION
# =============================

def simulate():

    rows = []

    current_time = start_time
    deco_available = start_time

    index = 0

    first_cycle_done = {b: False for b, _ in BRAS_ORDER}

    while current_time < end_time:

        bras, prod = BRAS_ORDER[index % len(BRAS_ORDER)]
        t = TIMES[prod]

        # =============================
        # PREMIER CYCLE
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
        # PAUSE MIDI (corrigée)
        # =============================
        if pause_active:
            # si le déco commence pendant la pause → on décale
            if deco_available < pause_end and deco_available >= pause_start:
                deco_available = pause_end

        # =============================
        # CALCUL LATENCE
        # =============================
        start_deco = max(end_cool, deco_available)
        latence = (start_deco - end_cool).total_seconds() / 60

        # =============================
        # AJUSTEMENT INTELLIGENT
        # =============================
        if latence > MAX_LATENCE:

            # on retarde l'entrée four
            delay = latence - MAX_LATENCE
            current_time += timedelta(minutes=delay)

            # recalcul complet
            start_four = current_time
            end_four = start_four + timedelta(minutes=four_time)
            end_cool = end_four + timedelta(minutes=t["cool"])

            start_deco = max(end_cool, deco_available)

        # =============================
        # DECOFFRAGE
        # =============================
        end_deco = start_deco + timedelta(minutes=t["deco"])

        if end_deco > end_time:
            break

        rows.append({
            "Bras": bras,
            "Produit": prod.capitalize(),
            "Four début": start_four,
            "Four fin": end_four,
            "Refroid fin": end_cool,
            "Déco début": start_deco,
            "Déco fin": end_deco,
            "Latence (min)": round((start_deco - end_cool).total_seconds()/60,1)
        })

        # =============================
        # UPDATE
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
# TABLE (COMME TON EXCEL)
# =============================

st.subheader("📋 Flux production")

df_display = df.copy()

for col in ["Four début","Four fin","Refroid fin","Déco début","Déco fin"]:
    df_display[col] = df_display[col].dt.strftime("%H:%M")

# tri bras 1 → 4
df_display["Bras_num"] = df_display["Bras"].str.extract(r'(\d+)').astype(int)
df_display = df_display.sort_values(["Bras_num","Four début"])

st.dataframe(df_display.drop(columns="Bras_num"))

# =============================
# KPI
# =============================

st.subheader("📊 KPI")

col1, col2 = st.columns(2)

col1.metric("Production", len(df))
col2.metric("Latence max", int(df["Latence (min)"].max()))
