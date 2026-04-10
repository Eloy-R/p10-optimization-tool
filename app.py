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
        st.session_state["df"] = df

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

    st.markdown("### 🎯 Maximiser production + utilisation four")

    if st.button("Lancer optimisation avancée"):

        results = []
        best_score = -999
        best_config = None

        # 🔥 pauses dynamiques
        pauses = [
            ("Pas de pause", False, None),
            ("11:30-12:00", True, (11*60+30, 12*60)),
            ("12:00-12:30", True, (12*60, 12*60+30)),
            ("12:30-13:00", True, (12*60+30, 13*60)),
            ("12:00-13:00", True, (12*60, 13*60)),
        ]

        latences = range(0, 11)

        for pause_name, pause_active_val, pause_window in pauses:

            for lat in latences:

                pause_start_orig = PAUSE_START
                pause_end_orig = PAUSE_END
                latence_orig = latence_max

                if pause_active_val:
                    globals()["PAUSE_START"] = pause_window[0]
                    globals()["PAUSE_END"] = pause_window[1]
                else:
                    globals()["PAUSE_START"] = 0
                    globals()["PAUSE_END"] = 0

                globals()["latence_max"] = lat

                df = simulate()

                globals()["PAUSE_START"] = pause_start_orig
                globals()["PAUSE_END"] = pause_end_orig
                globals()["latence_max"] = latence_orig

                if df.empty:
                    continue

                nb_cuves = len(df[df["Produit"] == "cuve"])
                nb_cloisons = len(df[df["Produit"] == "cloison"])
                total_prod = nb_cuves + nb_cloisons

                total_four_time = sum(
                    to_minutes(r["Fin Four"]) - to_minutes(r["Début Four"])
                    for _, r in df.iterrows()
                )

                total_available_time = END_TIME - START_TIME
                taux_four = (total_four_time / total_available_time) * 100

                lat_moy = df["Latence (min)"].mean()

                score = total_prod * 100 + taux_four - lat_moy * 2

                results.append({
                    "Pause": pause_name,
                    "Latence max": lat,
                    "Production": total_prod,
                    "Taux four (%)": round(taux_four, 1),
                    "Latence moy": round(lat_moy, 2),
                    "Score": round(score, 1)
                })

                if score > best_score:
                    best_score = score
                    best_config = results[-1]

        df_results = pd.DataFrame(results).sort_values(by="Score", ascending=False)

        st.subheader("📊 Scénarios")
        st.dataframe(df_results)

        st.subheader(" Meilleur scénario")

        st.success(
            f"""
             {best_config['Pause']}
            - Latence : {best_config['Latence max']} min
            - Production : {best_config['Production']}
            - Taux four : {best_config['Taux four (%)']}%
            """
        )

        # =========================
        # 📊 PARETO
        # =========================

        st.subheader("📈 Pareto Production vs Four")

        fig = px.scatter(
            df_results,
            x="Taux four (%)",
            y="Production",
            color="Pause",
            hover_data=["Latence max"]
        )

        st.plotly_chart(fig, use_container_width=True)

        # =========================
        # ⏱️ OVERTIME
        # =========================

        st.subheader("⏱️ Overtime intelligent")

        overtime_results = []

        for extra in [0, 15, 30, 45, 60]:

            original_end = END_TIME
            globals()["END_TIME"] = original_end + extra

            df = simulate()

            globals()["END_TIME"] = original_end

            if df.empty:
                continue

            overtime_results.append({
                "Overtime (min)": extra,
                "Production": len(df)
            })

        df_ot = pd.DataFrame(overtime_results)

        st.dataframe(df_ot)

        for i in range(1, len(df_ot)):
            if df_ot.iloc[i]["Production"] > df_ot.iloc[i-1]["Production"]:
                gain = df_ot.iloc[i]["Production"] - df_ot.iloc[i-1]["Production"]
                extra = df_ot.iloc[i]["Overtime (min)"]

                st.info(f"👉 +{extra} min permet +{gain} pièce(s)")

        # =========================
        # 🎯 SEUIL CRITIQUE PRODUCTION
        # =========================

        st.subheader("🎯 Seuil pour produire une pièce en plus")

        base_df = simulate()
        base_prod = len(base_df)

        seuil = None

        for extra in range(1, 121):  # test jusqu'à +2h

            original_end = END_TIME
            globals()["END_TIME"] = original_end + extra

            df_test = simulate()

            globals()["END_TIME"] = original_end

            if len(df_test) > base_prod:
                seuil = extra
                break

        if seuil:
            st.success(f"👉 +{seuil} min permet de produire +1 pièce")
        else:
            st.warning("👉 Même avec +2h, pas de pièce supplémentaire")

        # =========================
        # ⏱️ DERNIÈRE PIÈCE POSSIBLE
        # =========================

        st.subheader("⏱️ Dernière pièce possible")

        if seuil:

            original_end = END_TIME
            globals()["END_TIME"] = original_end + seuil

            df_final = simulate()

            globals()["END_TIME"] = original_end

            last_piece = df_final.iloc[-1]

            st.write("👉 Dernière pièce ajoutée :")

            st.dataframe(pd.DataFrame([last_piece]))

            fin_deco = last_piece["Fin Déco"]

            st.info(f"👉 Cette pièce se termine à {fin_deco}")

        # =========================
        # MIX ANNUEL OPTIMAL
        # =========================

        st.subheader(" Mix annuel optimal (C: Cloison ; V: Cuve)")

        configs = {
            "CCVV": ["cloison", "cloison", "cuve", "cuve"],
            "CVVC": ["cuve", "cloison", "cloison", "cuve"],
            "CVCV": ["cuve", "cloison", "cuve", "cloison"],
            "VVCC": ["cuve", "cuve", "cloison", "cloison"],
            "Actu": ["cloison", "cuve", "cloison", "cuve"],
        }

        mix_results = []

        for name, pattern in configs.items():

            performances = []

            for lat in range(0, 11):

                lat_orig = latence_max
                globals()["latence_max"] = lat

                results_alt = []
                last_four_end = START_TIME
                last_deco_end = START_TIME
                i = 0

                while True:

                    produit = pattern[i % 4]
                    data = PRODUITS[produit]

                    four_time = data["four"] + 2 if i < 4 else data["four"]

                    start_four = START_TIME if i == 0 else last_four_end + GAP_FOUR

                    end_four = start_four + four_time
                    start_refroid = end_four
                    end_refroid = start_refroid + data["refroid"]

                    start_deco = max(end_refroid, last_deco_end)

                    if PAUSE_START <= start_deco < PAUSE_END:
                        start_deco = PAUSE_END

                    latence = start_deco - end_refroid

                    if latence > lat:
                        shift = latence - lat

                        start_four += shift
                        end_four += shift
                        start_refroid += shift
                        end_refroid += shift

                        start_deco = max(end_refroid, last_deco_end)

                    end_deco = start_deco + data["deco"]

                    if end_deco > END_TIME:
                        break

                    results_alt.append(1)

                    last_four_end = end_four
                    last_deco_end = end_deco
                    i += 1

                globals()["latence_max"] = lat_orig

                performances.append(len(results_alt))

            mix_results.append({
                "Configuration": name,
                "Production moyenne": round(sum(performances)/len(performances), 1),
                "Production min": min(performances),
                "Production max": max(performances),
                "Variabilité": max(performances) - min(performances)
            })

        df_mix = pd.DataFrame(mix_results).sort_values(
            by=["Production moyenne", "Production min"],
            ascending=False
        )

        st.dataframe(df_mix)

        best = df_mix.iloc[0]

        st.success(
            f"""
            Mix recommandé annuel : {best['Configuration']}
            ✔ Moyenne : {best['Production moyenne']}
            ✔ Pire cas : {best['Production min']}
            ✔ Variabilité : {best['Variabilité']}
            """
        )
