import streamlit as st
import pandas as pd

# =========================
# PARAMETRES
# =========================

PRODUITS = {
    "cloison": {"four": 35, "refroid": 45, "deco": 40},
    "cuve": {"four": 45, "refroid": 46, "deco": 60},
}

BRAS_SEQUENCE = [4, 1, 2, 3]

START_TIME = 4 * 60 + 52
END_TIME = 21 * 60 + 45


# =========================
# UI
# =========================

st.title("Simulateur P10 - Performance Ligne 🔥")

pause_enabled = st.checkbox("Activer pause midi", True)
pause_duration = st.selectbox("Durée pause (min)", [30, 60])
pause_mode = st.selectbox("Mode pause", ["deco_only", "full_stop"])


# =========================
# OUTILS
# =========================

def format_time(minutes):
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h:02d}:{m:02d}"


def apply_pause(time, pause_start):
    if not pause_enabled:
        return time

    pause_end = pause_start + pause_duration

    if pause_start <= time < pause_end:
        return pause_end

    return time


# =========================
# SIMULATION
# =========================

def simulate():
    results = []

    last_four_end = START_TIME
    last_deco_end = START_TIME

    pause_start = 12 * 60

    i = 0

    while True:
        produit = "cloison" if i % 2 == 0 else "cuve"
        bras = BRAS_SEQUENCE[i % 4]
        data = PRODUITS[produit]

        # FOUR
        four_time = data["four"]
        if i < 4:
            four_time += 2

        start_four = last_four_end

        if pause_enabled and pause_mode == "full_stop":
            start_four = apply_pause(start_four, pause_start)

        end_four = start_four + four_time

        # STOP si dépasse la journée
        if end_four > END_TIME:
            break

        # REFROID
        end_refroid = end_four + data["refroid"]

        # DECO
        start_deco = max(end_refroid, last_deco_end)
        start_deco = apply_pause(start_deco, pause_start)

        end_deco = start_deco + data["deco"]

        latence = start_deco - end_refroid

        results.append({
            "Produit": produit,
            "start_four": start_four,
            "end_four": end_four,
            "latence": latence,
            "end_deco": end_deco
        })

        last_four_end = end_four
        last_deco_end = end_deco

        i += 1

    return pd.DataFrame(results)


# =========================
# EXECUTION
# =========================

if st.button("Lancer la simulation"):

    df = simulate()

    # =========================
    # KPI
    # =========================

    nb_cuves = len(df[df["Produit"] == "cuve"])
    nb_cloisons = len(df[df["Produit"] == "cloison"])

    total_four_time = df["end_four"] - df["start_four"]
    total_four_time = total_four_time.sum()

    total_available_time = END_TIME - START_TIME

    taux_four = (total_four_time / total_available_time) * 100

    latence_moy = df["latence"].mean()
    latence_max = df["latence"].max()

    # =========================
    # AFFICHAGE
    # =========================

    st.subheader("📊 Résultats")

    col1, col2, col3 = st.columns(3)

    col1.metric("Cuves produites", nb_cuves)
    col2.metric("Cloisons produites", nb_cloisons)
    col3.metric("Utilisation four (%)", round(taux_four, 1))

    st.subheader("📈 Qualité flux")

    col4, col5 = st.columns(2)

    col4.metric("Latence moyenne (min)", round(latence_moy, 1))
    col5.metric("Latence max (min)", latence_max)

    st.subheader("📋 Détail (debug)")

    df_display = df.copy()
    df_display["Début Four"] = df_display["start_four"].apply(format_time)
    df_display["Fin Four"] = df_display["end_four"].apply(format_time)

    st.dataframe(df_display[[
        "Produit", "Début Four", "Fin Four", "latence"
    ]])
