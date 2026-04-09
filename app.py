import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")

st.title("🏭 P10 - Simulation (logique heures uniquement)")

# =============================
# PARAMÈTRES
# =============================

MAX_LATENCE = st.sidebar.slider("Latence max (min)", 0, 60, 20)
pause_active = st.sidebar.checkbox("Pause midi 12h-13h", True)

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

BRAS_ORDER = [
    ("Bras 4", "cloison"),
    ("Bras 1", "cuve"),
    ("Bras 2", "cloison"),
    ("Bras 3", "cuve"),
]

# temps en minutes
start_time = to_minutes(6, 25)
end_time = to_minutes(21, 45)

pause_start = to_minutes(12, 0)
pause_end = to_minutes(13, 0)

MOVE = 1  # 1 minute

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

        # premier cycle
        if not first_cycle_done[bras]:
            four_time = t["four"] + 2
            first_cycle_done[bras] = True
        else:
            four_time = t["four"]

        # FOUR
        start_four = current_time
        end_four = start_four + four_time

        # REFROID
        end_cool = end_four + t["cool"]

        # pause midi
        if pause_active:
            if deco_available >= pause_start and deco_available < pause_end:
                deco_available = pause_end

        # LATENCE
        start_deco = max(end_cool, deco_available)
        latence = start_deco - end_cool

        # AJUSTEMENT LATENCE
        if latence > MAX_LATENCE:
            delay = latence - MAX_LATENCE
            current_time += delay

            start_four = current_time
            end_four = start_four + four_time
            end_cool = end_four + t["cool"]
            start_deco = max(end_cool, deco_available)

        # DECO
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

        current_time = end_four + MOVE
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

# tri propre
df_display["Bras"] = pd.Categorical(
    df_display["Bras"],
    categories=["Bras 1", "Bras 2", "Bras 3", "Bras 4"],
    ordered=True
)

df_display = df_display.sort_values(["Bras","Four début"]).reset_index(drop=True)

st.dataframe(df_display, use_container_width=True)

# =============================
# KPI
# =============================

st.subheader("📊 KPI")

col1, col2 = st.columns(2)

col1.metric("Production", len(df))
col2.metric("Latence max", int(df["Latence"].max()))
