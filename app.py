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
# UI TABS
# =========================

tab1, tab2 = st.tabs(["Simulation", "Optimisation avancée"])

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
# SIMULATION (EXISTANT)
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

        base_four = data["four"]
        refroid = data["refroid"]
        deco = data["deco"]

        four_time = base_four + 2 if i < 4 else base_four

        start_four = start_time if i == 0 else last_four_end + GAP_FOUR

        end_four = start_four + four_time
        start_refroid = end_four
        end_refroid = start_refroid + refroid

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

            if pause_active and PAUSE_START <= start_deco < PAUSE_END:
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
            "Latence (min)": latence
        })

        last_four_end = end_four
        last_deco_end = end_deco
        i += 1

    return pd.DataFrame(results)

# =========================
# ONGLET 1 : SIMULATION
# =========================

with tab1:

    st.title("🔥 Simulation P10")

    jour = st.selectbox("Jour", ["Lundi", "Autres jours"])
    latence_max = st.slider("Latence max", 0, 10, 10)
    pause_active = st.checkbox("Pause midi", True)

    START_TIME = 6*60+25 if jour == "Lundi" else 4*60+52

    if st.button("Lancer simulation"):

        df = simulate(START_TIME, latence_max, pause_active)

        st.dataframe(df)

# =========================
# ONGLET 2 : OR-TOOLS
# =========================

with tab2:

    st.title("🧠 Optimisation OR-Tools PRO")

    if st.button("Optimiser"):

        model = cp_model.CpModel()

        max_cycles = 25
        horizon = 1000

        starts = []
        ends = []

        for i in range(max_cycles):
            s = model.NewIntVar(0, horizon, f"s_{i}")
            d = 40  # approx
            e = model.NewIntVar(0, horizon, f"e_{i}")

            model.Add(e == s + d)

            starts.append(s)
            ends.append(e)

        # ordre
        for i in range(1, max_cycles):
            model.Add(starts[i] >= ends[i-1] + 1)

        # pause midi
        for i in range(max_cycles):
            before = model.NewBoolVar(f"before_{i}")
            after = model.NewBoolVar(f"after_{i}")

            model.Add(starts[i] <= PAUSE_START).OnlyEnforceIf(before)
            model.Add(starts[i] >= PAUSE_END).OnlyEnforceIf(after)

            model.AddBoolOr([before, after])

        # objectif
        model.Maximize(max_cycles)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5

        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:

            rows = []
            for i in range(max_cycles):
                rows.append({
                    "Cycle": i,
                    "Start": solver.Value(starts[i]),
                    "End": solver.Value(ends[i])
                })

            df_opt = pd.DataFrame(rows)

            st.subheader("📊 Résultat optimisation")
            st.dataframe(df_opt)

        else:
            st.error("Pas de solution")
