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

tab1, tab2, tab3 = st.tabs(["Simulation P10", "Optimisation", "Analyse"])

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

                # 🔥 backup
                pause_start_orig = PAUSE_START
                pause_end_orig = PAUSE_END
                latence_orig = latence_max

                # 🔥 inject pause dynamique
                if pause_active_val:
                    globals()["PAUSE_START"] = pause_window[0]
                    globals()["PAUSE_END"] = pause_window[1]
                else:
                    globals()["PAUSE_START"] = 0
                    globals()["PAUSE_END"] = 0

                globals()["latence_max"] = lat

                df = simulate()

                # 🔥 restore
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

        # =========================
        # TABLEAU
        # =========================

        st.subheader("📊 Scénarios")
        st.dataframe(df_results)

        # =========================
        # MEILLEUR
        # =========================

        st.subheader("🏆 Meilleur scénario")

        st.success(
            f"""
            🔥 {best_config['Pause']}
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
            hover_data=["Latence max"],
            title="Optimisation production"
        )

        st.plotly_chart(fig, use_container_width=True)

        # =========================
        # ⏱️ OVERTIME INTELLIGENT
        # =========================

        st.subheader("⏱️ Overtime intelligent")

        overtime_results = []

        for extra in [0, 15, 30, 45, 60]:

            # hack simple : prolonger END_TIME temporairement
            original_end = END_TIME
            globals()["END_TIME"] = original_end + extra

            df = simulate()

            globals()["END_TIME"] = original_end

            if df.empty:
                continue

            total = len(df)

            overtime_results.append({
                "Overtime (min)": extra,
                "Production": total
            })

        df_ot = pd.DataFrame(overtime_results)

        st.dataframe(df_ot)

        # 💡 insight overtime
        for i in range(1, len(df_ot)):
            if df_ot.iloc[i]["Production"] > df_ot.iloc[i-1]["Production"]:
                gain = df_ot.iloc[i]["Production"] - df_ot.iloc[i-1]["Production"]
                extra = df_ot.iloc[i]["Overtime (min)"]

                st.info(f"👉 +{extra} min permet +{gain} pièce(s)")

with tab3:

    st.title("🧠 Analyse & Aide à la décision P10")

    try:
        df
    except:
        st.warning("👉 Lance une simulation d'abord")
        st.stop()

    # =========================
    # 📊 1. VUE GLOBALE
    # =========================

    st.subheader("📊 Vue globale")

    lat_moy = df["Latence (min)"].mean()
    lat_max = df["Latence (min)"].max()

    total_prod = len(df)

    total_four_time = sum(
        to_minutes(r["Fin Four"]) - to_minutes(r["Début Four"])
        for _, r in df.iterrows()
    )

    taux_four = (total_four_time / (END_TIME - START_TIME)) * 100

    col1, col2, col3 = st.columns(3)
    col1.metric("Production", total_prod)
    col2.metric("Latence moy", round(lat_moy, 2))
    col3.metric("Utilisation four (%)", round(taux_four, 1))

    # =========================
    # 🔍 2. DIAGNOSTIC
    # =========================

    st.subheader("🔍 Diagnostic")

    problems = []
    reco = []

    if lat_moy > 5:
        problems.append("Latence élevée → déco saturé")
        reco.append("Réduire latence ou décaler entrée four")

    if taux_four < 65:
        problems.append("Four sous-utilisé")
        reco.append("Augmenter cadence four")

    if taux_four > 80:
        problems.append("Four surchargé")
        reco.append("Risque saturation déco")

    impacted = df[
        df["Début Déco"].apply(lambda t: 12 <= int(t[:2]) < 13)
    ]

    if len(impacted) > 0:
        problems.append("Pause midi mal positionnée")
        reco.append("Tester pause à 11h30 ou 12h30")

    st.write("### 🚨 Problèmes")
    for p in problems:
        st.error(p)

    st.write("### 🚀 Recommandations")
    for r in reco:
        st.info(r)

    # =========================
    # 🔄 3. AVANT / APRES
    # =========================

    st.subheader("🔄 Simulation avant / après")

    if st.button("Tester amélioration automatique"):

        # test simple : latence 10 vs latence 5
        lat_orig = latence_max

        globals()["latence_max"] = 5
        df_new = simulate()
        globals()["latence_max"] = lat_orig

        prod_old = len(df)
        prod_new = len(df_new)

        st.write(f"Avant : {prod_old} pièces")
        st.write(f"Après : {prod_new} pièces")

        if prod_new > prod_old:
            st.success(f"👉 Gain de {prod_new - prod_old} pièces")
        else:
            st.warning("👉 Pas d'amélioration")

        st.dataframe(df_new)

    # =========================
    # 🧠 4. MIX ANNUEL EXPERT
    # =========================

    st.subheader("🧠 Mix annuel optimal")

    configs = {
        "CCVV": ["cloison", "cloison", "cuve", "cuve"],
        "CVVC": ["cuve", "cloison", "cloison", "cuve"],
        "CVCV": ["cuve", "cloison", "cuve", "cloison"],
        "VVCC": ["cuve", "cuve", "cloison", "cloison"],
        "Alt": ["cloison", "cuve", "cloison", "cuve"],
    }

    results_mix = []

    for name, pattern in configs.items():

        count = 0

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

            if latence > latence_max:
                shift = latence - latence_max

                start_four += shift
                end_four += shift
                start_refroid += shift
                end_refroid += shift

                start_deco = max(end_refroid, last_deco_end)

            end_deco = start_deco + data["deco"]

            if end_deco > END_TIME:
                break

            count += 1

            last_four_end = end_four
            last_deco_end = end_deco
            i += 1

        results_mix.append({
            "Config": name,
            "Production": count
        })

    df_mix = pd.DataFrame(results_mix).sort_values(by="Production", ascending=False)

    st.dataframe(df_mix)

    best = df_mix.iloc[0]

    st.success(f"🏆 Mix recommandé : {best['Config']} → {best['Production']} pièces")
