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
ROTATION = 1  # 1 min carrousel


# =========================
# UI
# =========================

st.title("🔥 Simulateur P10 - By-pass automatique (0 latence)")

jour = st.selectbox("Jour de production", list(HORAIRES.keys()))
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


# =========================
# SIMULATION
# =========================

def simulate():
    results = []

    last_four_start = START_TIME - ROTATION
    last_deco_end = START_TIME

    i = 0

    while True:

        bras = BRAS_SEQUENCE[i % 4]

        # 🔁 alternance produit
        produit = "cloison" if i % 2 == 0 else "cuve"
        data = PRODUITS[produit]

        # =====================
        # CARROUSEL
        # =====================
        start_four = last_four_start + ROTATION

        four_time = data["four"]
        if i < 4:
            four_time += 2

        end_four = start_four + four_time
        end_refroid = end_four + data["refroid"]

        # =====================
        # TEST LATENCE
        # =====================
        start_deco_test = max(end_refroid, last_deco_end)
        latence_test = start_deco_test - end_refroid

        # =====================
        # DECISION BY-PASS
        # =====================
        if latence_test > 0:
            # 🔥 BY-PASS
            results.append({
                "Bras": bras,
                "Produit": "BY-PASS",
                "Début Four": format_time(start_four),
                "Fin Four": "-",
                "Fin Refroid": "-",
                "Début Déco": "-",
                "Fin Déco": "-",
                "Latence (min)": "-"
            })

            last_four_start = start_four
            i += 1
            continue

        # =====================
        # VALIDATION PRODUIT
        # =====================
        start_refroid = end_four
        start_deco = max(end_refroid, last_deco_end)
        end_deco = start_deco + data["deco"]

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
            "Latence (min)": 0
        })

        last_four_start = start_four
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
    nb_bypass = len(df[df["Produit"] == "BY-PASS"])

    st.subheader("📊 Production")

    col1, col2, col3 = st.columns(3)
    col1.metric("Cuves", nb_cuves)
    col2.metric("Cloisons", nb_cloisons)
    col3.metric("By-pass", nb_bypass)

    st.subheader("📋 Détail complet")

    st.dataframe(df)
