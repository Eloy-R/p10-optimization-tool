import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from ortools.sat.python import cp_model

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

tab1, tab2 = st.tabs(["Simulation", "Optimisation"])

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

def simulate(start_time, latence_max, pause_active):

    results = []
    last_four_end = start_time
    last_deco_end = start_time
    i = 0

    while True:

        produit = "cloison" if i % 2 == 0 else "cuve"
        bras = BRAS_SEQUENCE[i % 4]
        data = PRODUITS[produit]

        four_time = data["four"] + 2 if i < 4 else data["four"]

        start_four = start_time if i == 0 else last_four_end + GAP_FOUR
        end_four = start_four + four_time

        start_refroid = end_four
        end_refroid = start_refroid + data["refroid"]

        start_deco = max(end_refroid, last_deco_end)

        if pause_active and PAUSE_START <= start_deco < PAUSE_END:
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

        results.append({
            "Bras": bras,
            "Produit": produit,
            "Début Four": format_time(start_four),
            "Fin Four": format_time(end_four),
            "Début Refroid": format_time(start_refroid),
            "Fin Refroid": format_time(end_refroid),
            "Début Déco": format_time(start_deco),
            "Fin Déco": format_time(end_deco),
            "Latence (min)": latence
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

        for phase, start, end in [
            ("Four", "Début Four", "Fin Four"),
            ("Refroid", "Début Refroid", "Fin Refroid"),
            ("Déco", "Début Déco", "Fin Déco")
        ]:
            tasks.append({
                "Task": label,
                "Start": to_datetime(row[start]),
                "Finish": to_datetime(row[end]),
                "Type": phase
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
# TAB 1 : SIMULATION
# =========================

with tab1:

    st.title("🔥 Simulation P10")

    jour = st.selectbox("Jour", ["Lundi", "Autres jours"])
    latence_max = st.slider("Latence max", 0, 10, 10)
    pause_active = st.checkbox("Pause midi", True)

    START_TIME = 6*60+25 if jour == "Lundi" else 4*60+52

    if st.button("Lancer simulation"):

        df = simulate(START_TIME, latence_max, pause_active)

        # KPI
        nb_cuves = len(df[df["Produit"] == "cuve"])
        nb_cloisons = len(df[df["Produit"] == "cloison"])

        total_four_time = sum(
            to_minutes(r["Fin Four"]) - to_minutes(r["Début Four"])
            for _, r in df.iterrows()
        )

        taux_four = (total_four_time / (END_TIME - START_TIME)) * 100

        st.metric("Cuves", nb_cuves)
        st.metric("Cloisons", nb_cloisons)
        st.metric("Utilisation four (%)", round(taux_four, 1))

        st.dataframe(df)

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
# TAB 2 : OPTIMISATION SIMPLE (FIABLE)
# =========================

with tab2:

    st.title("🚀 Optimisation automatique fiable")

    if st.button("Optimiser"):

        best_df = None
        best_score = -999

        results = []

        for offset in range(0, 30):

            df = simulate(START_TIME + offset, 10, True)

            if df.empty:
                continue

            nb = len(df)

            total_four_time = sum(
                to_minutes(r["Fin Four"]) - to_minutes(r["Début Four"])
                for _, r in df.iterrows()
            )

            taux = (total_four_time / (END_TIME - START_TIME)) * 100
            lat = df["Latence (min)"].mean()

            score = nb * 100 + taux - lat

            results.append({
                "Offset": offset,
                "Production": nb,
                "Taux four": round(taux, 1),
                "Latence moy": round(lat, 2),
                "Score": round(score, 2)
            })

            if score > best_score:
                best_score = score
                best_df = df

        st.subheader("Comparaison")
        st.dataframe(pd.DataFrame(results))

        st.subheader("Meilleur scénario")
        st.dataframe(best_df)
