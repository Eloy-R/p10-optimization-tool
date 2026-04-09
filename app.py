import streamlit as st
import pandas as pd
import numpy as np

from optimizer import optimize
from simulation import simulate

st.set_page_config(layout="wide")

st.title("🏭 P10 Optimization Tool")

# =============================
# SIDEBAR
# =============================

st.sidebar.header("Paramètres")

mode = st.sidebar.radio("Mode", ["Simulation", "Optimisation avancée"])
nb_cycles = st.sidebar.slider("Nombre de cycles", 10, 80, 40)

# =============================
# MODE SIMULATION
# =============================

if mode == "Simulation":

    st.subheader("🔁 Simulation")

    sequence = list(np.random.choice(["cuve", "cloison"], nb_cycles))

    df = simulate(sequence)

    col1, col2, col3 = st.columns(3)
    col1.metric("Production", len(df))
    col2.metric("Attente totale", int(df["wait"].sum()))
    col3.metric("Max attente", int(df["wait"].max()))

    st.dataframe(df)

# =============================
# MODE OPTIMISATION
# =============================

if mode == "Optimisation avancée":

    st.subheader("🧠 OR-Tools Optimisation")

    if st.button("Lancer optimisation"):

        result = optimize(nb_cycles)

        df = pd.DataFrame(result)

        if df.empty:
            st.warning("⚠️ Aucune solution trouvée")
        else:
            st.success("Optimisation terminée")

            st.dataframe(df)

            # ✅ FIX BUG
            if "end" in df.columns:
                st.line_chart(df["end"])
            else:
                st.warning("Colonne 'end' absente")

        # debug utile
        st.write("DEBUG :", df)
