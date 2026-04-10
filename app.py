import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")

st.title("🏭 P10 - Simulation Production")

# =============================
# PARAMÈTRES
# =============================

MAX_LATENCE = st.sidebar.slider("Latence max (min)", 0, 60, 20)

pause_duration = st.sidebar.selectbox(
    "Durée pause midi",
    [0, 30, 60]
)

pause_type = st.sidebar.selectbox(
    "Type de pause",
    ["Aucune", "Tout à l'arrêt", "Décoffrage uniquement"]
)

# =============================
# OUTILS TEMPS
# =============================

def to_minutes(h, m):
    return h * 60 + m

def to_hhmm(minutes):
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h:02d}:{m:02d}"

# =============================
# CONFIG PROCESS
# =============================

TIMES = {
    "cuve": {"four": 45, "cool": 46, "deco": 60},
    "cloison": {"four": 35, "cool": 45, "deco": 40}
}

# ⚠️ ordre réel carrousel
BRAS_ORDER = [
    ("Bras 4", "cloison"),
    ("Bras 1", "cuve"),
    ("Bras 2", "cloison"),
    ("Bras 3", "cuve"),
]

start_time = to_minutes(6, 25)
end_time = to_minutes(21, 45)

pause_start = to_minutes(12, 0)
pause_end = pause_start + pause_duration

MOVE = 1  # minute entre bras

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
        # TEMPS FOUR (+2 min premier cycle)
        # =============================
        if not first_cycle_done[bras]:
            four_time = t["four"] + 2
            first_cycle_done[bras] = True
        else:
            four_time = t["four"]

        start_four = current_time
        end_four = start_four + four_time

        # =============================
        # PAUSE (cas tout à l’arrêt)
        # =============================
        if pause_type == "Tout à l'arrêt":
            if start_four < pause_end and end_four > pause_start:
                start_four = max(start_four, pause_end)
                end_four = start_four + four_time

        # =============================
        # REFROID
        # =============================
        end_cool = end_four + t["cool"]

        # =============================
        # GESTION PAUSE DÉCO
        # =============================
        if pause_type == "Décoffrage uniquement":
            if deco_available >= pause_start and deco_available < pause_end:
                deco_available = pause_end

        # =============================
        # LATENCE
        # =============================
        start_deco = max(end_cool, deco_available)
        latence = start_deco - end_cool

        # =============================
        # AJUSTEMENT LATENCE
        # =============================
        if latence > MAX_LATENCE:
            delay = latence - MAX_LATENCE
            current_time += delay

            start_four = current_time
            end_four = start_four + four_time
            end_cool = end_four + t["cool"]
            start_deco = max(end_cool, deco_available)

        # =============================
        # DECOFFRAGE
        # =============================
        end_deco = start_deco + t["deco"]

        # sécurité pause déco
        if pause_type != "Aucune":
            if start_deco < pause_end and start_deco >= pause_start:
                start_deco = pause_end
                end_deco = start_deco + t["deco"]

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
            "Latence": latence
        })

        # =============================
        # AVANCEMENT CARROUSEL
        # =============================
        current_time = current_time + MOVE
        deco_available = end_deco
        index += 1

    return pd.DataFrame(rows)

# =============================
# RUN
# =============================

df = simulate()

# =============================
# FORMAT TABLE
# =============================

st.subheader("📋 Flux global")

df_display = df.copy()

for col in ["Four début","Four fin","Refroid fin","Déco début","Déco fin"]:
    df_display[col] = df_display[col].apply(to_hhmm)

# 🔥 ordre flux réel (PAS groupé)
df_display = df_display.reset_index(drop=True)

st.dataframe(df_display, use_container_width=True)

# =============================
# KPI
# =============================

st.subheader("📊 KPI")

col1, col2, col3 = st.columns(3)

col1.metric("Production totale", len(df))
col2.metric("Latence max", int(df["Latence"].max()))
col3.metric("Latence moyenne", int(df["Latence"].mean()))
