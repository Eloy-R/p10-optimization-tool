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

END_TIME = 21 * 60 + 45
GAP_FOUR = 1

# =========================
# UI
# =========================

st.title("🔥 Simulateur P10 - Version optimisée")

jour = st.selectbox("Type de journée", ["Lundi", "Autres jours"])

latence_max = st.slider("Latence max (min)", 0, 10, 10)

if jour == "Lundi":
    START_TIME = 6 * 60 + 25
else:
    START_TIME = 4 * 60 + 52


def format_time(m):
    return f"{int(m//60):02d}:{int(m%60):02d}"


# =========================
# SIMULATION
# =========================

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

        # +2 min sur 4 premiers cycles
        if i < 4:
            four_time = base_four + 2
        else:
            four_time = base_four

        # =====================
        # CALCUL CIBLE
        # =====================

        target_start_deco = last_deco_end
        target_end_refroid = target_start_deco
        target_end_four = target_end_refroid - refroid
        target_start_four = target_end_four - four_time

        # =====================
        # CONTRAINTE FOUR
        # =====================

        if i == 0:
            start_four = START_TIME
        else:
            min_start = last_four_end + GAP_FOUR
            start_four = max(target_start_four, min_start)

        # =====================
        # CALCUL NORMAL
        # =====================

        end_four = start_four + four_time
        start_refroid = end_four
        end_refroid = start_refroid + refroid
        start_deco = max(end_refroid, last_deco_end)

        # =====================
        # 🔥 CONTRAINTE LATENCE MAX
        # =====================

        latence = start_deco - end_refroid

        if latence > latence_max:
            # on retarde le four
            retard = latence - latence_max

            start_four += retard
            end_four += retard
            start_refroid += retard
            end_refroid += retard

            # recalcul déco
            start_deco = max(end_refroid, last_deco_end)
            latence = start_deco - end_refroid

        end_deco = start_deco + deco

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


# =========================
# EXECUTION
# =========================

if st.button("Lancer la simulation"):

    df = simulate()

    st.subheader("📋 Résultat")
    st.dataframe(df)
