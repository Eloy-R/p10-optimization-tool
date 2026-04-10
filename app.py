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


# =========================
# UI
# =========================

st.title("Simulateur Ligne P10 🔥")

nb_cycles = st.slider("Nombre de cycles", 5, 50, 20)

pause_enabled = st.checkbox("Activer pause midi", True)

pause_duration = st.selectbox("Durée pause", [30, 60])

pause_mode = st.selectbox("Mode pause", ["deco_only", "full_stop"])


# =========================
# OUTILS
# =========================

def format_time(minutes):
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h:02d}:{m:02d}"


def generate_sequence(n):
    return ["cloison" if i % 2 == 0 else "cuve" for i in range(n)]


def apply_pause(time, pause_start, pause_duration):
    if not pause_enabled:
        return time

    pause_end = pause_start + pause_duration

    if pause_start <= time < pause_end:
        return pause_end

    return time


# =========================
# SIMULATION
# =========================

def simulate(sequence):
    results = []

    last_four_end = START_TIME
    last_deco_end = START_TIME

    pause_start = 12 * 60

    for i, produit in enumerate(sequence):
        bras = BRAS_SEQUENCE[i % 4]
        data = PRODUITS[produit]

        # FOUR
        four_time = data["four"]
        if i < 4:
            four_time += 2

        start_four = last_four_end

        if pause_enabled and pause_mode == "full_stop":
            start_four = apply_pause(start_four, pause_start, pause_duration)

        end_four = start_four + four_time

        # REFROID
        end_refroid = end_four + data["refroid"]

        # DECO
        start_deco = max(end_refroid, last_deco_end)
        start_deco = apply_pause(start_deco, pause_start, pause_duration)

        end_deco = start_deco + data["deco"]

        latence = start_deco - end_refroid

        results.append({
            "Cycle": i + 1,
            "Bras": bras,
            "Produit": produit,
            "Début Four": format_time(start_four),
            "Fin Four": format_time(end_four),
            "Fin Refroid": format_time(end_refroid),
            "Début Déco": format_time(start_deco),
            "Fin Déco": format_time(end_deco),
            "Latence (min)": latence
        })

        last_four_end = end_four
        last_deco_end = end_deco

    return pd.DataFrame(results)


# =========================
# EXECUTION
# =========================

if st.button("Lancer la simulation"):
    seq = generate_sequence(nb_cycles)
    df = simulate(seq)

    st.subheader("Résultats")
    st.dataframe(df)

    st.subheader("KPI")

    st.write("Latence moyenne :", round(df["Latence (min)"].mean(), 2))
    st.write("Latence max :", df["Latence (min)"].max())
