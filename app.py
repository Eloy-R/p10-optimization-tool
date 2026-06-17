import time
import streamlit as st
import pandas as pd
import plotly.express as px

from config import (
    DEFAULT_CYCLE_TIMES,
    DEFAULT_END_TIME,
    DEFAULT_FIRST_ARMS,
    DEFAULT_LATENCE_MAX,
    DEFAULT_START_TIMES,
    FIXED_DECO_GAP,
    FIXED_SEND_GAP,
    PRM_LABELS,
)
from simulation import (
    PRMSimulationConfig,
    ScenarioInfeasibleError,
    build_gantt_source,
    compute_prm_kpis,
    format_simulation_df,
    get_process_state_at_time,
    simulate_prm,
)
from optimizer import (
    evaluate_optimization,
    build_pause_latency_curve,
    evaluate_overtime_summary_from_best,
)
from exports import build_excel_bytes

st.set_page_config(page_title="Simulateur P10", layout="wide")


def safe_minute_value(value, fallback: int = 0) -> int:
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return int(fallback)
        value = value[0]
    if value is None:
        return int(fallback)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def align_minute_to_step(value, start_min: int, end_min: int, step_min: int) -> int:
    v = safe_minute_value(value, fallback=start_min)
    v = max(start_min, min(end_min, v))
    if step_min > 1:
        offset = v - start_min
        v = start_min + (offset // step_min) * step_min
    return v


def minutes_to_hhmm(m) -> str:
    return f"{int(m // 60):02d}:{int(m % 60):02d}"


def get_start_time(day_type: str) -> int:
    return DEFAULT_START_TIMES["Lundi"] if day_type == "Lundi" else DEFAULT_START_TIMES["Autres jours"]


def cycle_times_from_editor(df_editor: pd.DataFrame) -> dict:
    out = {}
    for prm_name, group in df_editor.groupby("PRM"):
        out[prm_name] = {}
        for _, row in group.iterrows():
            out[prm_name][row["Produit"]] = {
                "heat": int(row["Chauffe"]),
                "cool": int(row["Refroidissement"]),
                "deco": int(row["Décoffrage"]),
            }
    return out


if "cycle_times_all" not in st.session_state:
    rows = []
    for prm_name, products in DEFAULT_CYCLE_TIMES.items():
        for product, vals in products.items():
            rows.append(
                {
                    "PRM": prm_name,
                    "Produit": product,
                    "Chauffe": vals["heat"],
                    "Refroidissement": vals["cool"],
                    "Décoffrage": vals["deco"],
                }
            )
    st.session_state["cycle_times_all"] = pd.DataFrame(rows)

DEFAULTS = {
    "df_raw": None,
    "df_view": None,
    "gantt_df": None,
    "kpis": None,
    "df_scenarios": None,
    "df_scenarios_all": None,
    "df_curve": None,
    "best_scenario": None,
    "selected_prm": None,
    "df_ot_summary": None,
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


st.title("Simulateur et optimisation de la ligne P10")

with st.sidebar:
    selected_prm = st.radio(
        "Choisir le four",
        ["PRM4500-1", "PRM4500-2"],
        format_func=lambda x: PRM_LABELS[x],
    )

    day_type = st.selectbox("Type de journée", ["Lundi", "Autres jours"])
    start_time = get_start_time(day_type)
    end_time = DEFAULT_END_TIME

    latence_max = st.slider("Latence max (min)", 0, 20, DEFAULT_LATENCE_MAX)

    pause_matin_start = st.time_input("Début pause matin", value=pd.Timestamp("12:00").time())
    pause_soir_start = st.time_input("Début pause soir", value=pd.Timestamp("15:00").time())


tab1, tab2 = st.tabs(["Simulation", "Optimisation"])
with tab2:
    st.header(f"Optimisation – {PRM_LABELS[selected_prm]}")

    cycle_times_all = cycle_times_from_editor(st.session_state["cycle_times_all"])
    available_products = list(cycle_times_all.get(selected_prm, {}).keys())

    if not available_products:
        st.info("Définissez d'abord les temps de cycle.")
    else:
        if st.button("Lancer l'optimisation"):
            base_config = {
                "arms_config": {
                    1: available_products[0],
                    2: available_products[min(1, len(available_products)-1)],
                    3: available_products[min(2, len(available_products)-1)],
                    4: available_products[min(3, len(available_products)-1)],
                },
                "cycle_times": cycle_times_all[selected_prm],
                "first_arm": 4,
            }

            pause_start_matin = pause_matin_start.hour * 60 + pause_matin_start.minute
            pause_start_soir = pause_soir_start.hour * 60 + pause_soir_start.minute

            latence_values = list(range(max(5, latence_max), 21))

            df_scenarios_all, best = evaluate_optimization(
                prm_name=selected_prm,
                start_time=start_time,
                end_time=end_time,
                base_config=base_config,
                latence_values=latence_values,
                send_gap_min=FIXED_SEND_GAP,
                deco_gap_min=FIXED_DECO_GAP,
                pause_start_matin=pause_start_matin,
                pause_start_aprem=pause_start_soir,
                pause_durations=[0, 30, 60],
            )

            df_top3 = (
                df_scenarios_all.sort_values(
                    by=["Pause (min)", "Production"],
                    ascending=[True, False],
                )
                .groupby("Pause (min)", as_index=False)
                .first()
            )

            df_curve = build_pause_latency_curve(df_scenarios_all)
            df_ot = evaluate_overtime_summary_from_best(
                best, selected_prm, start_time, end_time,
                base_config, FIXED_SEND_GAP, FIXED_DECO_GAP,
                pause_start_matin, pause_start_soir,
                [0, 15, 30, 45, 60]
            )

            st.session_state["df_scenarios"] = df_top3
            st.session_state["df_curve"] = df_curve
            st.session_state["df_ot_summary"] = df_ot

        if st.session_state["df_scenarios"] is not None:
            st.dataframe(st.session_state["df_scenarios"])

            if st.session_state["df_ot_summary"] is not None:
                st.subheader("Overtime")
                st.dataframe(st.session_state["df_ot_summary"])

            if st.session_state["df_curve"] is not None:
                fig = px.line(
                    st.session_state["df_curve"],
                    x="Latence consigne (min)",
                    y="Production",
                    color="Pause (min)",
                )
                st.plotly_chart(fig, use_container_width=True)
