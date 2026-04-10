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

st.title("🔥 Simulateur P10 - Régulation intelligente")

jour = st.selectbox("Jour", list(HORAIRES.keys()))

pause_enabled = st.checkbox("Pause midi", True)
pause_duration = st.selectbox("Durée pause (min)", [30, 60])
pause_mode = st.selectbox("Mode pause", ["deco_only", "full_stop"])

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
        end_four = start_four + four_time

        end_refroid = end_four + data["refroid"]

        # =====================
        # REGULATION LATENCE
        # =====================
        start_deco_estime = max(end_refroid, last_deco_end)
        latence_estimee = start_deco_estime - end_refroid

        # 🔴 CONTRAINTE MAX
        if latence_estimee > LATENCE_MAX:
            decalage = latence_estimee - LATENCE_MAX

        # 🟢 OBJECTIF CIBLE
        elif latence_estimee > LATENCE_CIBLE:
            decalage = (latence_estimee - LATENCE_CIBLE) * 0.7

        # 🔵 TROP FAIBLE → accélérer légèrement
        elif latence_estimee < 0.5:
            decalage = -(min(0.5 - latence_estimee, 2))

        else:
            decalage = 0

        start_four += decalage
        end_four += decalage
        end_refroid += decalage

        # =====================
        # PAUSE FOUR
        # =====================
        if pause_enabled and pause_mode == "full_stop":
            start_four = apply_pause(start_four, pause_start)
            end_four = start_four + four_time
            end_refroid = end_four + data["refroid"]

        # STOP FOUR
        if end_four > END_TIME:
            break

        # =====================
        # DECO
        # =====================
        start_deco = max(end_refroid, last_deco_end)
        start_deco = apply_pause(start_deco, pause_start)

        end_deco = start_deco + data["deco"]

        latence = start_deco - end_refroid

        # STOP JOURNEE
        if end_deco > END_TIME:
            break

        # =====================
        # SAVE
        # =====================
        results.append({
            "Bras": bras,
            "Produit": produit,
            "Début Four": format_time(start_four),
            "Fin Four": format_time(end_four),
            "Début Refroid": format_time(end_four),
            "Fin Refroid": format_time(end_refroid),
            "Début Déco": format_time(start_deco),
            "Fin Déco": format_time(end_deco),
            "Latence (min)": round(latence, 2)
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

    # KPI
    nb_cuves = len(df[df["Produit"] == "cuve"])
    nb_cloisons = len(df[df["Produit"] == "cloison"])

    total_four_time = sum(
        to_minutes(r["Fin Four"]) - to_minutes(r["Début Four"])
        for _, r in df.iterrows()
    )

    total_available_time = END_TIME - START_TIME
    taux_four = (total_four_time / total_available_time) * 100

    latence_moy = df["Latence (min)"].mean()
    latence_max = df["Latence (min)"].max()

    # =========================
    # AFFICHAGE
    # =========================

    st.subheader("📊 Performance")

    col1, col2, col3 = st.columns(3)
    col1.metric("Cuves", nb_cuves)
    col2.metric("Cloisons", nb_cloisons)
    col3.metric("Utilisation four (%)", round(taux_four, 1))

    st.subheader("📈 Qualité flux")

    col4, col5 = st.columns(2)
    col4.metric("Latence moyenne", round(latence_moy, 2))
    col5.metric("Latence max", round(latence_max, 2))

    st.subheader("📋 Détail complet")

    st.dataframe(df)
