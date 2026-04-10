import streamlit as st
import pandas as pd

PRODUITS = {
    "cloison": {"four": 35, "refroid": 45, "deco": 40},
    "cuve": {"four": 45, "refroid": 46, "deco": 60},
}

BRAS_SEQUENCE = [4, 1, 2, 3]

END_TIME = 21 * 60 + 45
GAP_FOUR = 1

st.title("🔥 Simulateur P10 - Version terrain validée")

jour = st.selectbox("Type de journée", ["Lundi", "Autres jours"])

if jour == "Lundi":
    START_TIME = 6 * 60 + 25
else:
    START_TIME = 4 * 60 + 52


def format_time(m):
    return f"{int(m//60):02d}:{int(m%60):02d}"


def simulate():
    results = []

    last_deco_end = None
    last_four_end = None

    i = 0

    while True:

        produit = "cloison" if i % 2 == 0 else "cuve"
        bras = BRAS_SEQUENCE[i % 4]
        data = PRODUITS[produit]

        base_four = data["four"]
        refroid = data["refroid"]
        deco = data["deco"]

        # =====================
        # PREMIERE LIGNE
        # =====================

        if i == 0:
            start_four = START_TIME
            four_time = base_four + 2
            end_four = start_four + four_time

            start_refroid = end_four
            end_refroid = start_refroid + refroid

            start_deco = end_refroid
            end_deco = start_deco + deco

        else:

            # =====================
            # DECO pilote
            # =====================

            start_deco = last_deco_end
            end_deco = start_deco + deco

            if end_deco > END_TIME:
                break

            # =====================
            # Remontée
            # =====================

            end_refroid = start_deco
            start_refroid = end_refroid - refroid

            end_four = start_refroid

            # =====================
            # règle +2 min
            # =====================

            ecart = end_four - last_four_end

            if ecart > 2:
                four_time = base_four + 2
            else:
                four_time = base_four

            start_four = end_four - four_time

            # =====================
            # CONTRAINTE FOUR (clé corrigée)
            # =====================

            min_start = last_four_end + GAP_FOUR

            if start_four < min_start:
                start_four = min_start
                end_four = start_four + four_time

                # ⚠️ on ajuste UNIQUEMENT le refroid
                start_refroid = end_four
                end_refroid = start_refroid + refroid

                # ⚠️ mais on NE TOUCHE PAS AU DECO
                latence = start_deco - end_refroid

            else:
                latence = start_deco - end_refroid

        results.append({
            "Bras": bras,
            "Produit": produit,
            "Début Four": format_time(start_four),
            "Fin Four": format_time(end_four),
            "Début Refroid": format_time(start_refroid),
            "Fin Refroid": format_time(end_refroid),
            "Début Déco": format_time(start_deco),
            "Fin Déco": format_time(end_deco),
            "Latence": round(latence, 2)
        })

        last_deco_end = end_deco
        last_four_end = end_four

        i += 1

    return pd.DataFrame(results)


if st.button("Lancer la simulation"):

    df = simulate()

    st.dataframe(df)
