import streamlit as st
import pandas as pd
import plotly.express as px

from config import (
    DEFAULT_CYCLE_TIMES,
    DEFAULT_END_TIME,
    DEFAULT_START_TIMES,
    DEFAULT_DECO_GAP,
    DEFAULT_LATENCE_MAX,
    DEFAULT_SEND_GAP,
    DEFAULT_FIRST_ARMS,
)
from simulation import (
    PRMSimulationConfig,
    simulate_all,
    format_simulation_df,
    build_gantt_source,
    compute_global_kpis,
)
from optimizer import evaluate_scenarios, evaluate_overtime, evaluate_mixes
from exports import build_excel_bytes

st.set_page_config(page_title="Simulateur P10", layout="wide")


def minutes_to_hhmm(m: int) -> str:
    return f"{int(m//60):02d}:{int(m%60):02d}"


def get_start_time(jour: str) -> int:
    return DEFAULT_START_TIMES["Lundi"] if jour == "Lundi" else DEFAULT_START_TIMES["Autres jours"]


if "cycle_times" not in st.session_state:
    rows = []
    for prm_name, products in DEFAULT_CYCLE_TIMES.items():
        for product, vals in products.items():
            rows.append({
                "PRM": prm_name,
                "Produit": product,
                "Chauffe": vals["heat"],
                "Refroidissement": vals["cool"],
                "Décoffrage": vals["deco"],
            })
    st.session_state["cycle_times"] = pd.DataFrame(rows)

for key in ["df_raw", "df_view", "gantt_df", "kpis", "df_scenarios", "best_scenario", "df_ot", "df_mix", "last_piece"]:
    st.session_state.setdefault(key, None)

st.title("Simulateur et optimisation de la ligne P10")

with st.sidebar:
    st.header("Paramètres journée")
    jour = st.selectbox("Type de journée", ["Lundi", "Autres jours"])
    start_time = get_start_time(jour)
    end_time = DEFAULT_END_TIME

    st.caption(f"Début : {minutes_to_hhmm(start_time)} | Fin max : {minutes_to_hhmm(end_time)}")

    latence_max = st.slider("Latence max (min)", 0, 30, DEFAULT_LATENCE_MAX)
    send_gap_min = st.slider("Temps entre envois au four (min)", 1, 60, DEFAULT_SEND_GAP)
    deco_gap_min = st.slider("Marge mini entre deux décoffrages (min)", 0, 15, DEFAULT_DECO_GAP)

    st.subheader("Pauses")
    pause_midi_active = st.checkbox("Pause midi", True)
    pause_pm_active = st.checkbox("Pause après-midi", True)

    col1, col2 = st.columns(2)
    with col1:
        pause_midi_start = st.time_input("Début pause midi", value=pd.Timestamp("12:00").to_pydatetime().time())
        pause_pm_start = st.time_input("Début pause PM", value=pd.Timestamp("15:00").to_pydatetime().time())
    with col2:
        pause_midi_end = st.time_input("Fin pause midi", value=pd.Timestamp("13:00").to_pydatetime().time())
        pause_pm_end = st.time_input("Fin pause PM", value=pd.Timestamp("15:15").to_pydatetime().time())

    pause_windows = []
    if pause_midi_active:
        pause_windows.append((pause_midi_start.hour * 60 + pause_midi_start.minute,
                              pause_midi_end.hour * 60 + pause_midi_end.minute))
    if pause_pm_active:
        pause_windows.append((pause_pm_start.hour * 60 + pause_pm_start.minute,
                              pause_pm_end.hour * 60 + pause_pm_end.minute))

tab1, tab2, tab3 = st.tabs(["Simulation", "Optimisation", "Table des temps"])

with tab3:
    st.subheader("Temps de cycle modifiables")
    edited = st.data_editor(
        st.session_state["cycle_times"],
        num_rows="dynamic",
        use_container_width=True,
        key="cycle_times_editor",
        column_config={
            "Chauffe": st.column_config.NumberColumn(min_value=1, step=1),
            "Refroidissement": st.column_config.NumberColumn(min_value=1, step=1),
            "Décoffrage": st.column_config.NumberColumn(min_value=1, step=1),
        },
    )
    st.session_state["cycle_times"] = edited.copy()


def cycle_times_from_editor(df_editor: pd.DataFrame):
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


def build_prm_form(prm_name: str, available_products, default_first_arm: int):
    st.markdown(f"### {prm_name}")
    c1, c2 = st.columns([1, 2])

    with c1:
        first_arm = st.selectbox(
            f"Premier bras {prm_name}",
            [1, 2, 3, 4],
            index=[1, 2, 3, 4].index(default_first_arm),
            key=f"first_arm_{prm_name}"
        )

    with c2:
        st.caption("Affectation produit / bras")

    cols = st.columns(4)
    arms_config = {}
    for arm in [1, 2, 3, 4]:
        with cols[arm - 1]:
            arms_config[arm] = st.selectbox(
                f"Bras {arm}",
                available_products,
                key=f"{prm_name}_arm_{arm}",
                index=min(arm - 1, len(available_products) - 1)
            )

    return first_arm, arms_config


with tab1:
    st.header("Simulation")
    ct = cycle_times_from_editor(st.session_state["cycle_times"])

    xperco_products = list(ct.get("PRM4500-1", {}).keys())
    oxy_products = list(ct.get("PRM4500-2", {}).keys())

    col_a, col_b = st.columns(2)
    with col_a:
        first_arm_xperco, xperco_arms = build_prm_form("PRM4500-1", xperco_products, DEFAULT_FIRST_ARMS["PRM4500-1"])
    with col_b:
        first_arm_oxy, oxy_arms = build_prm_form("PRM4500-2", oxy_products, DEFAULT_FIRST_ARMS["PRM4500-2"])

    if st.button("Lancer la simulation", type="primary"):
        cfgs = [
            PRMSimulationConfig(
                prm_name="PRM4500-1",
                start_time=start_time,
                end_time=end_time,
                arms_config=xperco_arms,
                cycle_times=ct["PRM4500-1"],
                first_arm=first_arm_xperco,
                send_gap_min=send_gap_min,
                latence_max=latence_max,
                deco_gap_min=deco_gap_min,
                pause_windows=pause_windows,
            ),
            PRMSimulationConfig(
                prm_name="PRM4500-2",
                start_time=start_time,
                end_time=end_time,
                arms_config=oxy_arms,
                cycle_times=ct["PRM4500-2"],
                first_arm=first_arm_oxy,
                send_gap_min=send_gap_min,
                latence_max=latence_max,
                deco_gap_min=deco_gap_min,
                pause_windows=pause_windows,
            ),
        ]

        df_raw = simulate_all(cfgs)
        df_view = format_simulation_df(df_raw)
        gantt_df = build_gantt_source(df_raw)
        kpis = compute_global_kpis(df_raw, start_time, end_time)

        st.session_state["df_raw"] = df_raw
        st.session_state["df_view"] = df_view
        st.session_state["gantt_df"] = gantt_df
        st.session_state["kpis"] = kpis

    if st.session_state["df_view"] is not None:
        kpis = st.session_state["kpis"]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Production totale", kpis["production"])
        col2.metric("Taux four global (%)", kpis["taux_four_global"])
        col3.metric("Latence moyenne (min)", kpis["latence_moy"])
        col4.metric("Latence max observée (min)", kpis["latence_max_obs"])

        st.subheader("Production par PRM")
        st.write(kpis["par_prm"])

        st.subheader("Production par produit")
        st.write(kpis["par_produit"])

        st.subheader("Détail simulation")
        st.dataframe(st.session_state["df_view"], use_container_width=True)

        st.subheader("Diagramme de Gantt")
        fig = px.timeline(
            st.session_state["gantt_df"],
            x_start="Start",
            x_end="Finish",
            y="Task",
            color="Type",
            color_discrete_map={
                "Four": "green",
                "Refroidissement": "blue",
                "Déco": "purple",
                "LATENCE": "red",
            },
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(xaxis=dict(tickformat="%H:%M"))
        st.plotly_chart(fig, use_container_width=True)

        excel_bytes = build_excel_bytes(
            simulation_df=st.session_state["df_view"],
            scenarios_df=st.session_state["df_scenarios"],
            overtime_df=st.session_state["df_ot"],
            mix_df=st.session_state["df_mix"],
            cycle_times_df=st.session_state["cycle_times"],
        )
        st.download_button(
            "Télécharger Excel",
            data=excel_bytes,
            file_name="simulation_p10.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with tab2:
    st.header("Optimisation")

    if st.session_state["df_view"] is None:
        st.info("Lancez d'abord une simulation pour figer les paramètres de base.")
    else:
        if st.button("Lancer l'optimisation"):
            ct = cycle_times_from_editor(st.session_state["cycle_times"])

            base_configs = {
                "PRM4500-1": {
                    "arms_config": {
                        1: st.session_state.get("PRM4500-1_arm_1", xperco_products[0]),
                        2: st.session_state.get("PRM4500-1_arm_2", xperco_products[min(1, len(xperco_products)-1)]),
                        3: st.session_state.get("PRM4500-1_arm_3", xperco_products[min(2, len(xperco_products)-1)]),
                        4: st.session_state.get("PRM4500-1_arm_4", xperco_products[min(0, len(xperco_products)-1)]),
                    },
                    "cycle_times": ct["PRM4500-1"],
                    "first_arm": st.session_state.get("first_arm_PRM4500-1", DEFAULT_FIRST_ARMS["PRM4500-1"]),
                },
                "PRM4500-2": {
                    "arms_config": {
                        1: st.session_state.get("PRM4500-2_arm_1", oxy_products[0]),
                        2: st.session_state.get("PRM4500-2_arm_2", oxy_products[min(1, len(oxy_products)-1)]),
                        3: st.session_state.get("PRM4500-2_arm_3", oxy_products[min(0, len(oxy_products)-1)]),
                        4: st.session_state.get("PRM4500-2_arm_4", oxy_products[min(1, len(oxy_products)-1)]),
                    },
                    "cycle_times": ct["PRM4500-2"],
                    "first_arm": st.session_state.get("first_arm_PRM4500-2", DEFAULT_FIRST_ARMS["PRM4500-2"]),
                },
            }

            df_scenarios, best = evaluate_scenarios(
                start_time=start_time,
                end_time=end_time,
                base_configs=base_configs,
                send_gap_values=[max(1, send_gap_min - 5), send_gap_min, send_gap_min + 5],
                latence_values=list(range(max(0, latence_max - 3), latence_max + 4)),
                deco_gap_values=[max(0, deco_gap_min - 2), deco_gap_min, deco_gap_min + 2],
                pause_sets=[
                    ("Sans pause", []),
                    ("Midi", [(12*60, 13*60)]),
                    ("Midi+PM", [(12*60, 13*60), (15*60, 15*60+15)]),
                ],
            )
            st.session_state["df_scenarios"] = df_scenarios
            st.session_state["best_scenario"] = best

            df_ot, best_extra, last_piece = evaluate_overtime(
                start_time=start_time,
                end_time=end_time,
                base_configs=base_configs,
                send_gap_min=send_gap_min,
                latence_max=latence_max,
                deco_gap_min=deco_gap_min,
                pause_windows=pause_windows,
                overtime_values=[0, 15, 30, 45, 60],
            )
            st.session_state["df_ot"] = df_ot
            st.session_state["last_piece"] = last_piece

            product_options = {
                "PRM4500-1": list(ct["PRM4500-1"].keys()),
                "PRM4500-2": list(ct["PRM4500-2"].keys()),
            }

            df_mix = evaluate_mixes(
                start_time=start_time,
                end_time=end_time,
                base_configs=base_configs,
                product_options=product_options,
                send_gap_min=send_gap_min,
                latence_max=latence_max,
                deco_gap_min=deco_gap_min,
                pause_windows=pause_windows,
            )
            st.session_state["df_mix"] = df_mix

        if st.session_state["df_scenarios"] is not None:
            st.subheader("Scénarios")
            st.dataframe(st.session_state["df_scenarios"], use_container_width=True)

            best = st.session_state["best_scenario"]
            if best:
                st.success(
                    f"Meilleur scénario : {best['Scenario']} | "
                    f"Production {best['Production']} | "
                    f"Latence moy {best['Latence moy']} | "
                    f"Taux four {best['Taux four global (%)']}%"
                )

                fig = px.scatter(
                    st.session_state["df_scenarios"],
                    x="Taux four global (%)",
                    y="Production",
                    color="Pause",
                    hover_data=["Latence max", "Send gap", "Déco gap"],
                )
                st.plotly_chart(fig, use_container_width=True)

        if st.session_state["df_ot"] is not None:
            st.subheader("Overtime intelligent")
            st.dataframe(st.session_state["df_ot"], use_container_width=True)

            if st.session_state["last_piece"] is not None:
                st.subheader("Dernière pièce ajoutée")
                st.dataframe(st.session_state["last_piece"], use_container_width=True)

        if st.session_state["df_mix"] is not None:
            st.subheader("Mix annuel")
            st.dataframe(st.session_state["df_mix"], use_container_width=True)
