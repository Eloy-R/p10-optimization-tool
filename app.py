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
from optimizer import evaluate_mixes, evaluate_overtime, evaluate_scenarios
from exports import build_excel_bytes

st.set_page_config(page_title="Simulateur P10", layout="wide")


def minutes_to_hhmm(m: int) -> str:
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


def update_selected_cycle_times(prm_name: str, edited_selected: pd.DataFrame):
    current = st.session_state["cycle_times_all"].copy()
    current = current[current["PRM"] != prm_name]
    merged = pd.concat([current, edited_selected], ignore_index=True)
    st.session_state["cycle_times_all"] = merged


def build_prm_form(prm_name: str, available_products, default_first_arm: int):
    st.markdown(f"### Paramètres {PRM_LABELS[prm_name]}")
    first_arm = st.selectbox(
        f"Premier bras {PRM_LABELS[prm_name]}",
        [1, 2, 3, 4],
        index=[1, 2, 3, 4].index(default_first_arm),
        key=f"first_arm_{prm_name}",
    )

    st.caption("Affectation produit / bras")
    cols = st.columns(4)
    arms_config = {}
    for arm in [1, 2, 3, 4]:
        with cols[arm - 1]:
            default_index = min(arm - 1, len(available_products) - 1) if available_products else 0
            arms_config[arm] = st.selectbox(
                f"Bras {arm}",
                available_products,
                key=f"{prm_name}_arm_{arm}",
                index=default_index,
            )
    return first_arm, arms_config


# ----------------------
# Initialisation session_state
# ----------------------
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

for key, default_value in {
    "df_raw": None,
    "df_view": None,
    "gantt_df": None,
    "kpis": None,
    "df_scenarios": None,
    "best_scenario": None,
    "df_ot": None,
    "df_mix": None,
    "last_piece": None,
    "selected_prm": None,
    "process_time": None,
    "process_step": 10,
    "process_autoplay": False,
    "_next_process_time": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


st.title("Simulateur et optimisation de la ligne P10")

with st.sidebar:
    st.header("Périmètre")
    selected_prm = st.radio(
        "Choisir le four / la PRM",
        ["PRM4500-1", "PRM4500-2"],
        format_func=lambda x: PRM_LABELS[x],
    )
    st.session_state["selected_prm"] = selected_prm

    st.header("Paramètres journée")
    day_type = st.selectbox("Type de journée", ["Lundi", "Autres jours"])
    start_time = get_start_time(day_type)
    end_time = DEFAULT_END_TIME
    st.caption(f"Début : {minutes_to_hhmm(start_time)} | Fin max : {minutes_to_hhmm(end_time)}")

    latence_max = st.slider("Latence max (min)", 0, 20, DEFAULT_LATENCE_MAX)

    send_gap_min = FIXED_SEND_GAP
    deco_gap_min = FIXED_DECO_GAP
    st.caption("Le rythme d’envoi au four est calculé automatiquement pour respecter la latence.")
    st.caption(f"Marge mini entre deux décoffrages fixée à {FIXED_DECO_GAP} min.")

    st.subheader("Pauses")
    pause_midi_active = st.checkbox("Pause midi", True)
    pause_pm_active = st.checkbox("Pause après-midi", True)

    col1, col2 = st.columns(2)
    with col1:
        pause_midi_start = st.time_input(
            "Début pause midi",
            value=pd.Timestamp("12:00").to_pydatetime().time(),
        )
        pause_pm_start = st.time_input(
            "Début pause PM",
            value=pd.Timestamp("15:00").to_pydatetime().time(),
        )
    with col2:
        pause_midi_end = st.time_input(
            "Fin pause midi",
            value=pd.Timestamp("13:00").to_pydatetime().time(),
        )
        pause_pm_end = st.time_input(
            "Fin pause PM",
            value=pd.Timestamp("16:00").to_pydatetime().time(),
        )

    pause_windows = []
    if pause_midi_active:
        pause_windows.append(
            (
                pause_midi_start.hour * 60 + pause_midi_start.minute,
                pause_midi_end.hour * 60 + pause_midi_end.minute,
            )
        )
    if pause_pm_active:
        pause_windows.append(
            (
                pause_pm_start.hour * 60 + pause_pm_start.minute,
                pause_pm_end.hour * 60 + pause_pm_end.minute,
            )
        )


tab1, tab2, tab3 = st.tabs(["Simulation", "Optimisation", "Table des temps"])


with tab3:
    st.subheader(f"Temps de cycle – {PRM_LABELS[selected_prm]}")
    full_df = st.session_state["cycle_times_all"].copy()
    selected_df = full_df[full_df["PRM"] == selected_prm].reset_index(drop=True)

    edited = st.data_editor(
        selected_df,
        num_rows="dynamic",
        use_container_width=True,
        key=f"cycle_times_editor_{selected_prm}",
        column_config={
            "Chauffe": st.column_config.NumberColumn(min_value=1, step=1),
            "Refroidissement": st.column_config.NumberColumn(min_value=1, step=1),
            "Décoffrage": st.column_config.NumberColumn(min_value=1, step=1),
        },
    )
    update_selected_cycle_times(selected_prm, edited.copy())


with tab1:
    st.header(f"Simulation – {PRM_LABELS[selected_prm]}")
    cycle_times_all = cycle_times_from_editor(st.session_state["cycle_times_all"])
    available_products = list(cycle_times_all.get(selected_prm, {}).keys())

    if not available_products:
        st.warning("Aucun produit défini pour cette PRM dans la table des temps.")
    else:
        first_arm, arms_config = build_prm_form(
            selected_prm,
            available_products,
            DEFAULT_FIRST_ARMS[selected_prm],
        )

        if st.button("Lancer la simulation", type="primary"):
            cfg = PRMSimulationConfig(
                prm_name=selected_prm,
                start_time=start_time,
                end_time=end_time,
                arms_config=arms_config,
                cycle_times=cycle_times_all[selected_prm],
                first_arm=first_arm,
                send_gap_min=send_gap_min,
                latence_max=latence_max,
                deco_gap_min=deco_gap_min,
                pause_windows=pause_windows,
            )

            try:
                df_raw = simulate_prm(cfg)
                df_view = format_simulation_df(df_raw)
                gantt_df = build_gantt_source(df_raw)
                kpis = compute_prm_kpis(df_raw, start_time, end_time)

                st.session_state["df_raw"] = df_raw
                st.session_state["df_view"] = df_view
                st.session_state["gantt_df"] = gantt_df
                st.session_state["kpis"] = kpis
                st.session_state["selected_prm"] = selected_prm

                # réinitialisation lecture après nouvelle simulation
                st.session_state["process_time"] = start_time
                st.session_state["process_step"] = 10
                st.session_state["process_autoplay"] = False
                st.session_state["_next_process_time"] = None

            except ScenarioInfeasibleError as e:
                st.session_state["df_raw"] = None
                st.session_state["df_view"] = None
                st.session_state["gantt_df"] = None
                st.session_state["kpis"] = None

                st.error(
                    "Scénario infaisable : la latence maximale ne peut pas être respectée "
                    "avec les paramètres actuels."
                )
                st.code(str(e), language="text")

            except Exception as e:
                st.session_state["df_raw"] = None
                st.session_state["df_view"] = None
                st.session_state["gantt_df"] = None
                st.session_state["kpis"] = None

                st.error("Une erreur technique inattendue est survenue pendant la simulation.")
                st.code(str(e), language="text")

    if (
        st.session_state["df_view"] is not None
        and st.session_state["selected_prm"] == selected_prm
    ):
        kpis = st.session_state["kpis"]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Production totale", kpis["production"])
        col2.metric("Taux four (%)", kpis["taux_four"])
        col3.metric("Latence moyenne (min)", kpis["latence_moy"])
        col4.metric("Latence max observée (min)", kpis["latence_max_obs"])

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

        # ----------------------
        # Vue process + lecture automatique corrigée
        # ----------------------
        st.subheader("Vue process dans la journée")

        # appliquer la prochaine valeur AVANT les widgets
        if st.session_state["_next_process_time"] is not None:
            st.session_state["process_time"] = st.session_state["_next_process_time"]
            st.session_state["_next_process_time"] = None

        if st.session_state["process_time"] is None:
            st.session_state["process_time"] = start_time

        c1, c2, c3 = st.columns([1, 1, 1])

        with c1:
            step_min = st.selectbox(
                "Pas de temps (min)",
                [1, 5, 10, 15, 30],
                index=2,
                key="process_step_widget",
            )
            st.session_state["process_step"] = step_min

        with c2:
            autoplay = st.toggle(
                "Lecture automatique",
                value=st.session_state["process_autoplay"],
                key="process_autoplay_widget",
            )
            st.session_state["process_autoplay"] = autoplay

        with c3:
            if st.button("Réinitialiser la lecture"):
                st.session_state["_next_process_time"] = start_time
                st.session_state["process_autoplay"] = False
                st.rerun()

        current_minute = st.slider(
            "Choisir un instant dans la journée",
            min_value=start_time,
            max_value=end_time,
            value=int(st.session_state["process_time"]),
            step=step_min,
            key="process_time_widget",
        )

        st.session_state["process_time"] = current_minute

        st.caption(f"Heure sélectionnée : {minutes_to_hhmm(current_minute)}")

        process_state = get_process_state_at_time(
            st.session_state["df_raw"],
            current_minute
        )

        zone_cols = st.columns(5)
        zones = [
            ("Four", zone_cols[0]),
            ("Refroid. Z1", zone_cols[1]),
            ("Refroid. Z2", zone_cols[2]),
            ("Avant déco", zone_cols[3]),
            ("Déco", zone_cols[4]),
        ]

        for zone_name, col in zones:
            with col:
                st.markdown(f"### {zone_name}")
                zone_items = process_state.get(zone_name, [])
                if zone_items:
                    for item in zone_items:
                        st.markdown(f"- {item}")
                else:
                    st.caption("—")

        # auto-play corrigé
        if st.session_state["process_autoplay"]:
            next_value = current_minute + step_min
            if next_value > end_time:
                next_value = start_time

            st.session_state["_next_process_time"] = next_value
            time.sleep(0.6)
            st.rerun()

        excel_bytes = build_excel_bytes(
            simulation_df=st.session_state["df_view"],
            scenarios_df=st.session_state["df_scenarios"],
            overtime_df=st.session_state["df_ot"],
            mix_df=st.session_state["df_mix"],
            cycle_times_df=st.session_state["cycle_times_all"],
        )
        st.download_button(
            "Télécharger Excel",
            data=excel_bytes,
            file_name=f"simulation_{selected_prm}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


with tab2:
    st.header(f"Optimisation – {PRM_LABELS[selected_prm]}")

    if (
        st.session_state["df_view"] is None
        or st.session_state["selected_prm"] != selected_prm
    ):
        st.info("Lancez d'abord une simulation faisable pour cette PRM.")
    else:
        if st.button("Lancer l'optimisation"):
            cycle_times_all = cycle_times_from_editor(st.session_state["cycle_times_all"])
            available_products = list(cycle_times_all.get(selected_prm, {}).keys())

            base_config = {
                "arms_config": {
                    1: st.session_state.get(f"{selected_prm}_arm_1", available_products[0]),
                    2: st.session_state.get(f"{selected_prm}_arm_2", available_products[min(1, len(available_products) - 1)]),
                    3: st.session_state.get(f"{selected_prm}_arm_3", available_products[min(2, len(available_products) - 1)]),
                    4: st.session_state.get(f"{selected_prm}_arm_4", available_products[min(3, len(available_products) - 1)]),
                },
                "cycle_times": cycle_times_all[selected_prm],
                "first_arm": st.session_state.get(
                    f"first_arm_{selected_prm}",
                    DEFAULT_FIRST_ARMS[selected_prm],
                ),
            }

            df_scenarios, best = evaluate_scenarios(
                prm_name=selected_prm,
                start_time=start_time,
                end_time=end_time,
                base_config=base_config,
                send_gap_values=[send_gap_min],
                latence_values=[latence_max],
                deco_gap_values=[deco_gap_min],
                pause_sets=[
                    ("Sans pause", []),
                    ("Midi", [(12 * 60, 13 * 60)]),
                    ("Midi+PM", [(12 * 60, 13 * 60), (15 * 60, 16 * 60)]),
                ],
            )
            st.session_state["df_scenarios"] = df_scenarios
            st.session_state["best_scenario"] = best

            df_ot, best_extra, last_piece = evaluate_overtime(
                prm_name=selected_prm,
                start_time=start_time,
                end_time=end_time,
                base_config=base_config,
                send_gap_min=send_gap_min,
                latence_max=latence_max,
                deco_gap_min=deco_gap_min,
                pause_windows=pause_windows,
                overtime_values=[0, 15, 30, 45, 60],
            )
            st.session_state["df_ot"] = df_ot
            st.session_state["last_piece"] = last_piece

            df_mix = evaluate_mixes(
                prm_name=selected_prm,
                start_time=start_time,
                end_time=end_time,
                base_config=base_config,
                product_options=available_products,
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
                    f"Taux four {best['Taux four (%)']}%"
                )

                fig = px.scatter(
                    st.session_state["df_scenarios"],
                    x="Taux four (%)",
                    y="Production",
                    color="Pause",
                    hover_data=["Statut", "Raison"],
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
