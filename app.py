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

HORAIRES = {
    "Lundi": 6 * 60 + 25,
    "Mardi": 4 * 60 + 52,
    "Mercredi": 4 * 60 + 52,
    "Jeudi": 4 * 60 + 52,
    "Vendredi": 4 * 60 + 52,
}

END_TIME = 21 * 60 + 45

LATENCE_CIBLE = 1
LATENCE_MAX = 10


# =========================
# UI
# =========================

st.title("🔥 Simulateur P10 - Avec équilibrage des bras")

jour = st.selectbox("Jour", list(HORAIRES.keys()))

pause_enabled = st.checkbox("Pause midi", True)
pause_duration = st.selectbox("Durée pause (min)", [30, 60])
pause_mode = st.selectbox("Mode pause", ["deco_only", "full_stop"])

# 🔥 nouveau paramètre clé
DECALAGE_BRAS = st.slider("Décalage entre bras (min)", 0, 30, 8)

START_TIME = HORAIRES[jour]


# =========================
# OUTILS
# =========================

def format_time(minutes):
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h:02d}:{m:02d}"


def to_minutes(t):
    return int(t[:2]) * 60 + int(t[3:])


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

    pause_start = 12 * 60

    last_deco_end = START_TIME

    i = 0

    while True:
        produit = "cloison" if i % 2 == 0 else "cuve"
        bras_index = i % 4
        bras = BRAS_SEQUENCE[bras_index]
        data = PRODUITS[produit]

        # 🔥 décalage initial des bras
        start_four = START_TIME + bras_index * DECALAGE_BRAS + (i // 4) * 5

        four_time = data["four"]
        if i < 4:
            four_time += 2

        end_four = start_four + four_time

        if end_four > END_TIME:
            break

        end_refroid = end_four + data["refroid"]

        # DECO
        start_deco = max(end_refroid, last_deco_end)
        start_deco = apply_pause(start_deco, pause_start)

        end_deco = start_deco + data["deco"]

        latence = start_deco - end_refroid

        if end_deco > END_TIME:
            break

        results.append({
            "Bras": bras,
            "Produit": produit,
            "Début Four": format_time(start_four),
            "Fin Four": format_time(end_four),
            "Fin Refroid": format_time(end_refroid),
            "Début Déco": format_time(start_deco),
            "Fin Déco": format_time(end_deco),
            "Latence (min)": round(latence, 2)
        })

        last_deco_end = end_deco
        i += 1

    return pd.DataFrame(results)


# =========================
# EXECUTION
# =========================

if st.button("Lancer la simulation"):

    df = simulate()

    nb_cuves = len(df[df["Produit"] == "cuve"])
    nb_cloisons = len(df[df["Produit"] == "cloison"])

    latence_moy = df["Latence (min)"].mean()
    latence_max = df["Latence (min)"].max()

    st.subheader("📊 Production")

    col1, col2 = st.columns(2)
    col1.metric("Cuves", nb_cuves)
    col2.metric("Cloisons", nb_cloisons)

    st.subheader("📈 Qualité")

    col3, col4 = st.columns(2)
    col3.metric("Latence moyenne", round(latence_moy, 2))
    col4.metric("Latence max", round(latence_max, 2))

    st.subheader("📋 Détail")

    st.dataframe(df)
