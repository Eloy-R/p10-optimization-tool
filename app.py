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
# SIMULATION (TON CODE INTACT)
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
        h = int(t[:2])
        m = int(t[3:])
        return datetime(2024, 1, 1, h, m)

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

            if pause_active:
                if PAUSE_START <= start_deco < PAUSE_END:
                    start_deco = PAUSE_END

            latence = start_deco - end_refroid

            if latence > latence_max:
                retard = latence - latence_max

                start_four += retard
                end_four += retard
                start_refroid += retard
                end_refroid += retard

                start_deco = max(end_refroid, last_deco_end)

                if pause_active:
                    if PAUSE_START <= start_deco < PAUSE_END:
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

    if st.button("Lancer la simulation"):

        df = simulate()

        nb_cuves = len(df[df["Produit"] == "cuve"])
        nb_cloisons = len(df[df["Produit"] == "cloison"])

        total_four_time = sum(
            to_minutes(r["Fin Four"]) - to_minutes(r["Début Four"])
            for _, r in df.iterrows()
        )

        total_available_time = END_TIME - START_TIME
        taux_four = (total_four_time / total_available_time) * 100

        st.subheader("📊 Production")

        col1, col2 = st.columns(2)
        col1.metric("Cuves", nb_cuves)
        col2.metric("Cloisons", nb_cloisons)

        st.subheader("🔥 Utilisation du four")
        st.metric("Taux (%)", round(taux_four, 1))

        st.subheader("📋 Détail")
        st.dataframe(df)

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

# =========================
# ONGLET OPTIMISATION ===================
# =========================

with tab2:

    st.title("🚀 Optimisation avancée production")

    st.markdown("### 🎯 Maximiser la production sous contraintes")

    if st.button("Lancer optimisation avancée"):

        results = []
        best_score = -999
        best_config = None

        # 🔁 paramètres testés
        pauses = [
            ("Pas de pause", False, None),
            ("Pause 30 min", True, 30),
            ("Pause 1h", True, 60),
        ]

        latences = range(0, 11)  # 0 → 10 min
        overtime_options = [0, 15, 30, 45, 60]  # minutes en plus

        for pause_name, pause_active_val, pause_duree in pauses:

            for lat in latences:

                for overtime in overtime_options:

                    # 🔥 adaption dynamique de fin de journée
                    global END_TIME
                    original_end = END_TIME
                    END_TIME = original_end + overtime

                    # 🔥 adaptation pause dynamique
                    global PAUSE_END
                    if pause_active_val:
                        PAUSE_END = PAUSE_START + (pause_duree or 60)
                    else:
                        PAUSE_END = PAUSE_START  # pas de pause

                    # 🔥 appel simulateur (INTACT)
                    df = simulate()

                    # reset END_TIME
                    END_TIME = original_end

                    if df.empty:
                        continue

                    # KPI
                    nb_cuves = len(df[df["Produit"] == "cuve"])
                    nb_cloisons = len(df[df["Produit"] == "cloison"])
                    total_prod = nb_cuves + nb_cloisons

                    total_four_time = sum(
                        to_minutes(r["Fin Four"]) - to_minutes(r["Début Four"])
                        for _, r in df.iterrows()
                    )

                    total_available_time = END_TIME - START_TIME + overtime
                    taux_four = (total_four_time / total_available_time) * 100

                    lat_moy = df["Latence (min)"].mean()

                    # 🎯 score multi-critères
                    score = (
                        total_prod * 100
                        + taux_four
                        - lat_moy * 2
                        - overtime * 0.5
                    )

                    results.append({
                        "Pause": pause_name,
                        "Latence max": lat,
                        "Overtime (min)": overtime,
                        "Cuves": nb_cuves,
                        "Cloisons": nb_cloisons,
                        "Total": total_prod,
                        "Taux four (%)": round(taux_four, 1),
                        "Latence moy": round(lat_moy, 2),
                        "Score": round(score, 1)
                    })

                    if score > best_score:
                        best_score = score
                        best_config = results[-1]

        df_results = pd.DataFrame(results).sort_values(by="Score", ascending=False)

        st.subheader("📊 Tous les scénarios")
        st.dataframe(df_results)

        st.subheader("🏆 Meilleur scénario")

        st.success(
            f"""
            🔥 {best_config['Pause']}
            - Latence max : {best_config['Latence max']} min
            - Overtime : {best_config['Overtime (min)']} min
            - Production : {best_config['Total']} pièces
            - Taux four : {best_config['Taux four (%)']}%
            """
        )

        # 🔥 recommandation overtime intelligente
        st.subheader("💡 Insight")

        top = df_results.head(5)

        for i in range(1, len(top)):
            prev = top.iloc[i-1]
            curr = top.iloc[i]

            if curr["Total"] > prev["Total"]:
                gain = curr["Total"] - prev["Total"]
                overtime = curr["Overtime (min)"]

                st.info(
                    f"👉 +{overtime} min permet de produire +{gain} pièce(s)"
                )
