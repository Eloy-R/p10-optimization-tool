import streamlit as st
import pandas as pd
import plotly.express as px

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

st.title("🔥 Simulateur P10 - Version complète")

jour = st.selectbox("Type de journée", ["Lundi", "Autres jours"])
mode = st.selectbox("Mode", ["Optimisé (0 latence)", "Réel"])
latence_max = st.slider("Latence max (min)", 0, 10, 10)

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
        # MODE
        # =====================

        if mode == "Optimisé (0 latence)":

            target_start_deco = last_deco_end
            target_end_refroid = target_start_deco
            target_end_four = target_end_refroid - refroid
            target_start_four = target_end_four - four_time

            if i == 0:
                start_four = START_TIME
            else:
                start_four = max(target_start_four, last_four_end + GAP_FOUR)

        else:

            if i == 0:
                start_four = START_TIME
            else:
                start_four = last_four_end + GAP_FOUR

        # =====================
        # FLUX
        # =====================

        end_four = start_four + four_time
        start_refroid = end_four
        end_refroid = start_refroid + refroid

        start_deco = max(end_refroid, last_deco_end)
        latence = start_deco - end_refroid

        # =====================
        # CONTRAINTE LATENCE
        # =====================

        if latence > latence_max:
            retard = latence - latence_max

            start_four += retard
            end_four += retard
            start_refroid += retard
            end_refroid += retard

            start_deco = max(end_refroid, last_deco_end)
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

    def to_hour_float(t):
        h = int(t[:2])
        m = int(t[3:])
        return h + m / 60

    tasks = []

    for _, row in df.iterrows():

        label = f"B{row['Bras']} - {row['Produit']}"

        # FOUR
        tasks.append({
            "Task": label,
            "Start": to_hour_float(row["Début Four"]),
            "Finish": to_hour_float(row["Fin Four"]),
            "Type": "Four"
        })

        # REFROID
        tasks.append({
            "Task": label,
            "Start": to_hour_float(row["Début Refroid"]),
            "Finish": to_hour_float(row["Fin Refroid"]),
            "Type": "Refroid"
        })

        # DECO
        tasks.append({
            "Task": label,
            "Start": to_hour_float(row["Début Déco"]),
            "Finish": to_hour_float(row["Fin Déco"]),
            "Type": "Déco"
        })

        # LATENCE
        if row["Latence (min)"] > 0:
            tasks.append({
                "Task": label,
                "Start": to_hour_float(row["Fin Refroid"]),
                "Finish": to_hour_float(row["Début Déco"]),
                "Type": "LATENCE"
            })

    return pd.DataFrame(tasks)

# =========================
# EXECUTION
# =========================

if st.button("Lancer la simulation"):

    df = simulate()

    # KPI
    nb_cuves = len(df[df["Produit"] == "cuve"])
    nb_cloisons = len(df[df["Produit"] == "cloison"])

    total_four_time = sum(
        to_minutes(r["Fin Four"]) - to_minutes(r["Début Four"])
        for _, r in df.iterrows()
    )

    total_available_time = END_TIME - START_TIME
    taux_four = (total_four_time / total_available_time) * 100

    # AFFICHAGE KPI
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

if gantt_df.empty:
    st.warning("Aucune donnée à afficher")
else:

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

    # 🔥 Axe propre sans date
    fig.update_layout(
        xaxis=dict(
            range=[4.87, 22],  # 04:52 → 22:00
            tickvals=list(range(5, 23)),
            ticktext=[f"{h:02d}:00" for h in range(5, 23)],
            title="Heures"
        )
    )

    st.plotly_chart(fig, use_container_width=True)

    fig.update_yaxes(autorange="reversed")

    st.plotly_chart(fig, use_container_width=True)
