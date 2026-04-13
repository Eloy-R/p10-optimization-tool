import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# =========================
# PARAMETRES
# =========================

PRODUITS = {
    "cloison": {"four": 35, "refroid": 45, "deco": 40},
    "cuve": {"four": 45, "refroid": 46, "deco": 60},
}

BRAS_SEQUENCE = [4, 1, 2, 3]

END_TIME = 21 * 60 + 45
GAP_FOUR = 1

PAUSE_START = 12 * 60
PAUSE_END = 13 * 60

# =========================
# TABS
# =========================

tab1, tab2 = st.tabs(["Simulation P10", "Optimisation"])

# =========================
# OUTILS
# =========================

def format_time(m):
    return f"{int(m//60):02d}:{int(m%60):02d}"

def to_minutes(t):
    return int(t[:2]) * 60 + int(t[3:])

def to_datetime(t):
    return datetime(2024, 1, 1, int(t[:2]), int(t[3:]))

# =========================
# SIMULATION
# =========================

with tab1:

    st.title("Simulateur P10 - Production")

    jour = st.selectbox("Type de journée", ["Lundi", "Autres jours"])
    latence_max = st.slider("Latence max (min)", 0, 10, 10)
    pause_active = st.checkbox("Activer pause midi (12h-13h)", True)

    if jour == "Lundi":
        START_TIME = 6 * 60 + 25
    else:
        START_TIME = 4 * 60 + 52

    def simulate():

        results = []

        last_four_end = START_TIME
        last_deco_end = START_TIME

        i = 0

        while True:

            produit = "cloison" if i % 2 == 0 else "cuve"
            bras = BRAS_SEQUENCE[i % 4]
            data = PRODUITS[produit]

            base_four = data["four"]
            refroid = data["refroid"]
            deco = data["deco"]

            if i < 4:
                four_time = base_four + 2
            else:
                four_time = base_four

            if i == 0:
                start_four = START_TIME
            else:
                start_four = last_four_end + GAP_FOUR

            end_four = start_four + four_time
            start_refroid = end_four
            end_refroid = start_refroid + refroid

            start_deco = max(end_refroid, last_deco_end)

            # =========================
            # ✅ PAUSE MIDI (CORRIGÉE)
            # =========================
            if pause_active:

                end_deco_temp = start_deco + deco

                if PAUSE_START <= start_deco < PAUSE_END:
                    start_deco = PAUSE_END

                elif start_deco < PAUSE_START and end_deco_temp > PAUSE_START:
                    start_deco = PAUSE_END

            latence = start_deco - end_refroid

            # =========================
            # CONTRAINTE LATENCE
            # =========================
            if latence > latence_max:

                retard = latence - latence_max

                start_four += retard
                end_four += retard
                start_refroid += retard
                end_refroid += retard

                start_deco = max(end_refroid, last_deco_end)

                # =========================
                # ✅ PAUSE MIDI APRES LATENCE (CORRIGÉE)
                # =========================
                if pause_active:

                    end_deco_temp = start_deco + deco

                    if PAUSE_START <= start_deco < PAUSE_END:
                        start_deco = PAUSE_END

                    elif start_deco < PAUSE_START and end_deco_temp > PAUSE_START:
                        start_deco = PAUSE_END

                latence = start_deco - end_refroid

            end_deco = start_deco + deco

            if end_deco > END_TIME:
                break

            results.append({
                "Bras": bras,
                "Produit": produit,
                "Début Four": format_time(start_four),
                "Fin Four": format_time(end_four),
                "Début Refroid": format_time(start_refroid),
                "Fin Refroid": format_time(end_refroid),
                "Début Déco": format_time(start_deco),
                "Fin Déco": format_time(end_deco),
                "Latence (min)": round(latence, 2)
            })

            last_four_end = end_four
            last_deco_end = end_deco

            i += 1

        return pd.DataFrame(results)
