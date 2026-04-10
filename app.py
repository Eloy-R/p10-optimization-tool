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

    def format_time(m):
        return f"{int(m//60):02d}:{int(m%60):02d}"

    def to_minutes(t):
        return int(t[:2]) * 60 + int(t[3:])

    def to_datetime(t):
        return datetime(2024, 1, 1, int(t[:2]), int(t[3:]))

    def simulate():

        results = []
        last_four_end = START_TIME
        last_deco_end = START_TIME

        i = 0

        while True:

            produit = "cloison" if i % 2 == 0 else "cuve"
            bras = BRAS_SEQUENCE[i % 4]
            data = PRODUITS[produit]

            four_time = data["four"] + 2 if i < 4 else data["four"]

            start_four = START_TIME if i == 0 else last_four_end + GAP_FOUR

            end_four = start_four + four_time
            start_refroid = end_four
            end_refroid = start_refroid + data["refroid"]

            start_deco = max(end_refroid, last_deco_end)

            if pause_active and PAUSE_START <= start_deco < PAUSE_END:
                start_deco = PAUSE_END

            latence = start_deco - end_refroid

            if latence > latence_max:
                retard = latence - latence_max
                start_four += retard
                end_four += retard
                start_refroid += retard
                end_refroid += retard
                start_deco = max(end_refroid, last_deco_end)

                if pause_active and PAUSE_START <= start_deco < PAUSE_END:
                    start_deco = PAUSE_END

                latence = start_deco - end_refroid

            end_deco = start_deco + data["deco"]

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

    def build_gantt(df):

        tasks = []

        for _, row in df.iterrows():

            label = f"B{row['Bras']} - {row['Produit']}"

            for phase in [
                ("Four", "Début Four", "Fin Four"),
                ("Refroid", "Début Refroid", "Fin Refroid"),
                ("Déco", "Début Déco", "Fin Déco")
            ]:
                tasks.append({
                    "Task": label,
                    "Start": to_datetime(row[phase[1]]),
                    "Finish": to_datetime(row[phase[2]]),
                    "Type": phase[0]
                })

            if row["Latence (min)"] > 0:
                tasks.append({
                    "Task": label,
                    "Start": to_datetime(row["Fin Refroid"]),
                    "Finish": to_datetime(row["Début Déco"]),
                    "Type": "LATENCE"
                })

        return pd.DataFrame(tasks)

    if st.button("Lancer la simulation"):

        df = simulate()
        st.session_state["df"] = df

        nb_cuves = len(df[df["Produit"] == "cuve"])
        nb_cloisons = len(df[df["Produit"] == "cloison"])

        total_four_time = sum(
            to_minutes(r["Fin Four"]) - to_minutes(r["Début Four"])
            for _, r in df.iterrows()
        )

        taux_four = (total_four_time / (END_TIME - START_TIME)) * 100

        col1, col2 = st.columns(2)
        col1.metric("Cuves", nb_cuves)
        col2.metric("Cloisons", nb_cloisons)

        st.metric("Taux four (%)", round(taux_four, 1))

        st.dataframe(df)

        fig = px.timeline(
            build_gantt(df),
            x_start="Start",
            x_end="Finish",
            y="Task",
            color="Type"
        )

        fig.update_yaxes(autorange="reversed")
        fig.update_layout(xaxis=dict(tickformat="%H:%M"))

        st.plotly_chart(fig, use_container_width=True)

# =========================
# OPTIMISATION
# =========================

with tab2:

    st.title("Optimisation avancée production")

    # 🔥 AFFICHAGE SIMULATION EN HAUT
    if "df" in st.session_state:

        st.subheader("Simulation actuelle")
        df_sim = st.session_state["df"]
        st.dataframe(df_sim)

    else:
        st.warning("Lancer une simulation d'abord")

    st.divider()

    def simulate_with_overtime(extra):
        original_end = END_TIME
        globals()["END_TIME"] = original_end + extra
        df = simulate()
        globals()["END_TIME"] = original_end
        return df

    if st.button("Lancer optimisation avancée"):

        overtime_range = [0, 15, 30, 45, 60]

        df_ot = pd.DataFrame([
            {"Overtime (min)": e, "Production": len(simulate_with_overtime(e))}
            for e in overtime_range
        ])

        st.dataframe(df_ot)

        for i in range(1, len(df_ot)):
            if df_ot.iloc[i]["Production"] > df_ot.iloc[i-1]["Production"]:
                st.info(f"+{df_ot.iloc[i]['Overtime (min)']} min → +1 pièce")
                break
