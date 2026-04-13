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

    # =========================
    # UI
    # =========================

    jour = st.selectbox("Type de journée", ["Lundi", "Autres jours"])
    latence_max = st.slider("Latence max (min)", 0, 10, 10)
    pause_active = st.checkbox("Activer pause midi (12h-13h)", True)

    if jour == "Lundi":
        START_TIME = 6 * 60 + 25
    else:
        START_TIME = 4 * 60 + 52

    # =========================
    # OUTILS
    # =========================

    def format_time(m):
        return f"{int(m//60):02d}:{int(m%60):02d}"

    def to_minutes(t):
        return int(t[:2]) * 60 + int(t[3:])

    def to_datetime(t):
        h = int(t[:2])
        m = int(t[3:])
        return datetime(2024, 1, 1, h, m)

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

            # +2 min sur les 4 premiers cycles
            if i < 4:
                four_time = base_four + 2
            else:
                four_time = base_four

            # MODE REEL
            if i == 0:
                start_four = START_TIME
            else:
                start_four = last_four_end + GAP_FOUR

            # FLUX
            end_four = start_four + four_time
            start_refroid = end_four
            end_refroid = start_refroid + refroid

            start_deco = max(end_refroid, last_deco_end)

            # PAUSE MIDI
            if pause_active:

                end_deco_temp = start_deco + deco

                if PAUSE_START <= start_deco < PAUSE_END:
                    start_deco = PAUSE_END

                elif start_deco < PAUSE_START and end_deco_temp > PAUSE_START:
                    start_deco = PAUSE_END

            latence = start_deco - end_refroid

            # CONTRAINTE LATENCE
            if latence > latence_max:

                retard = latence - latence_max

                start_four += retard
                end_four += retard
                start_refroid += retard
                end_refroid += retard

                start_deco = max(end_refroid, last_deco_end)

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

    # =========================
    # GANTT
    # =========================

    def build_gantt(df):

        tasks = []

        for _, row in df.iterrows():

            label = f"B{row['Bras']} - {row['Produit']}"

            tasks.append({
                "Task": label,
                "Start": to_datetime(row["Début Four"]),
                "Finish": to_datetime(row["Fin Four"]),
                "Type": "Four"
            })

            tasks.append({
                "Task": label,
                "Start": to_datetime(row["Début Refroid"]),
                "Finish": to_datetime(row["Fin Refroid"]),
                "Type": "Refroid"
            })

            tasks.append({
                "Task": label,
                "Start": to_datetime(row["Début Déco"]),
                "Finish": to_datetime(row["Fin Déco"]),
                "Type": "Déco"
            })

            if row["Latence (min)"] > 0:
                tasks.append({
                    "Task": label,
                    "Start": to_datetime(row["Fin Refroid"]),
                    "Finish": to_datetime(row["Début Déco"]),
                    "Type": "LATENCE"
                })

        return pd.DataFrame(tasks)

    # =========================
    # EXECUTION
    # =========================

    if st.button("Lancer la simulation"):

        df = simulate()

        # 👉 IMPORTANT pour tab2
        st.session_state["df"] = df

        # KPI
        nb_cuves = len(df[df["Produit"] == "cuve"])
        nb_cloisons = len(df[df["Produit"] == "cloison"])

        total_four_time = sum(
            to_minutes(r["Fin Four"]) - to_minutes(r["Début Four"])
            for _, r in df.iterrows()
        )

        total_available_time = END_TIME - START_TIME
        taux_four = (total_four_time / total_available_time) * 100

        # KPI AFFICHAGE
        st.subheader("📊 Production")

        col1, col2 = st.columns(2)
        col1.metric("Cuves", nb_cuves)
        col2.metric("Cloisons", nb_cloisons)

        st.subheader("🔥 Utilisation du four")
        st.metric("Taux (%)", round(taux_four, 1))

        # TABLEAU
        st.subheader("📋 Détail")
        st.dataframe(df)

        # GANTT
        st.subheader("📊 Diagramme de Gantt")

        gantt_df = build_gantt(df)

        fig = px.timeline(
            gantt_df,
            x_start="Start",
            x_end="Finish",
            y="Task",
            color="Type",
            color_discrete_map={
                "Four": "green",
                "Refroid": "blue",
                "Déco": "purple",
                "LATENCE": "red"
            }
        )

        fig.update_yaxes(autorange="reversed")
        fig.update_layout(xaxis=dict(tickformat="%H:%M"))

        st.plotly_chart(fig, use_container_width=True)
