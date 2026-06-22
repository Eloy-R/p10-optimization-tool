import time
import streamlit as st
import pandas as pd
import plotly.express as px
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

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
    evaluate_overtime_summary_from_best,
    WEIGHT_PROFILES,
)
from exports import build_excel_bytes

FOUR_GAP_MIN = 1

st.set_page_config(page_title="Simulateur P10", layout="wide")


def safe_minute_value(value, fallback: int = 0) -> int:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else fallback
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
    m = safe_minute_value(m, fallback=0)
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


def _default_arm_indices(available_products):
    if not available_products:
        return [0, 0, 0, 0]
    cuve_idx = None
    cloison_idx = None
    for i, p in enumerate(available_products):
        lower = str(p).lower()
        if cuve_idx is None and "cuve" in lower:
            cuve_idx = i
        if cloison_idx is None and ("cloison" in lower or "cloisons" in lower):
            cloison_idx = i
    if cuve_idx is None:
        cuve_idx = 0
    if cloison_idx is None:
        cloison_idx = 1 if len(available_products) > 1 else 0
    return [cuve_idx, cloison_idx, cuve_idx, cloison_idx]


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
    defaults = _default_arm_indices(available_products)
    for arm in [1, 2, 3, 4]:
        with cols[arm - 1]:
            idx = defaults[arm - 1]
            arms_config[arm] = st.selectbox(
                f"Bras {arm}",
                available_products,
                key=f"{prm_name}_arm_{arm}",
                index=min(idx, max(0, len(available_products) - 1)),
            )
    return first_arm, arms_config


if "cycle_times_all" not in st.session_state:
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
    st.session_state["cycle_times_all"] = pd.DataFrame(rows)

DEFAULTS = {
    "df_raw": None,
    "df_view": None,
    "gantt_df": None,
    "kpis": None,
    "df_scenarios": None,
    "df_scenarios_all": None,
    "best_scenario": None,
    "df_ot_summary": None,
    "process_time_slider": None,
    "process_step_widget": 10,
    "process_autoplay_widget": False,
    "_next_process_time": None,
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

st.title("Simulateur et optimisation de la ligne P10")

with st.sidebar:
    st.header("Périmètre")
    selected_prm = st.radio("Choisir le four / la PRM", ["PRM4500-1", "PRM4500-2"], format_func=lambda x: PRM_LABELS[x])
    st.header("Paramètres journée")
    day_type = st.selectbox("Type de journée", ["Lundi", "Autres jours"])
    start_time = get_start_time(day_type)
    end_time = DEFAULT_END_TIME
    st.caption(f"Début : {minutes_to_hhmm(start_time)} | Fin max : {minutes_to_hhmm(end_time)}")
    latence_limite_optim = st.slider("Latence max process pour optimisation (min)", 0, 20, DEFAULT_LATENCE_MAX)
    st.caption("Ce curseur ne sert qu'à l'optimisation : aucune proposition ne dépassera cette latence maximale observée.")
    send_gap_min = FIXED_SEND_GAP
    deco_gap_min = FIXED_DECO_GAP
    st.caption(f"Marge mini entre deux décoffrages fixée à {FIXED_DECO_GAP} min.")
    st.caption(f"Marge mini entre deux passages au four fixée à {FOUR_GAP_MIN} min.")
    st.subheader("Pauses")
    pause_matin_active = st.checkbox("Pause matin", True)
    pause_soir_active = st.checkbox("Pause soir", True)
    c1, c2 = st.columns(2)
    with c1:
        pause_matin_start = st.time_input("Début pause matin", value=pd.Timestamp("12:00").to_pydatetime().time())
        pause_soir_start = st.time_input("Début pause soir", value=pd.Timestamp("15:00").to_pydatetime().time())
    with c2:
        pause_matin_end = st.time_input("Fin pause matin", value=pd.Timestamp("13:00").to_pydatetime().time())
        pause_soir_end = st.time_input("Fin pause soir", value=pd.Timestamp("16:00").to_pydatetime().time())
    pause_windows = []
    if pause_matin_active:
        pause_windows.append((pause_matin_start.hour * 60 + pause_matin_start.minute, pause_matin_end.hour * 60 + pause_matin_end.minute))
    if pause_soir_active:
        pause_windows.append((pause_soir_start.hour * 60 + pause_soir_start.minute, pause_soir_end.hour * 60 + pause_soir_end.minute))


tab1, tab2, tab3 = st.tabs(["Simulation", "Optimisation", "Table des temps"])

with tab3:
    st.subheader(f"Temps de cycle – {PRM_LABELS[selected_prm]}")
    full_df = st.session_state["cycle_times_all"].copy()
    selected_df = full_df[full_df["PRM"] == selected_prm].reset_index(drop=True)
    edited = st.data_editor(selected_df, num_rows="dynamic", use_container_width=True, key=f"cycle_times_editor_{selected_prm}", column_config={
        "Chauffe": st.column_config.NumberColumn(min_value=1, step=1),
        "Refroidissement": st.column_config.NumberColumn(min_value=1, step=1),
        "Décoffrage": st.column_config.NumberColumn(min_value=1, step=1),
    })
    update_selected_cycle_times(selected_prm, edited.copy())

with tab1:
    st.header(f"Simulation – {PRM_LABELS[selected_prm]}")
    cycle_times_all = cycle_times_from_editor(st.session_state["cycle_times_all"])
    available_products = list(cycle_times_all.get(selected_prm, {}).keys())
    if not available_products:
        st.warning("Aucun produit défini pour cette PRM dans la table des temps.")
    else:
        first_arm, arms_config = build_prm_form(selected_prm, available_products, DEFAULT_FIRST_ARMS[selected_prm])
        if st.button("Lancer la simulation", type="primary"):
            cfg = PRMSimulationConfig(prm_name=selected_prm, start_time=start_time, end_time=end_time, arms_config=arms_config, cycle_times=cycle_times_all[selected_prm], first_arm=first_arm, send_gap_min=send_gap_min, latence_max=20, latence_cible=0, deco_gap_min=deco_gap_min, four_gap_min=FOUR_GAP_MIN, pause_windows=pause_windows)
            try:
                df_raw = simulate_prm(cfg)
                st.session_state["df_raw"] = df_raw
                st.session_state["df_view"] = format_simulation_df(df_raw)
                st.session_state["gantt_df"] = build_gantt_source(df_raw)
                st.session_state["kpis"] = compute_prm_kpis(df_raw, start_time, end_time)
                st.session_state["process_time_slider"] = start_time
                st.session_state["process_step_widget"] = 10
                st.session_state["process_autoplay_widget"] = False
                st.session_state["_next_process_time"] = None
            except Exception:
                import traceback
                st.error("Erreur détaillée dans simulate_prm")
                st.code(traceback.format_exc(), language="python")
                st.stop()

    if st.session_state["df_view"] is not None:
        kpis = st.session_state["kpis"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Production totale", kpis["production"])
        c2.metric("Taux four (%)", kpis["taux_four"])
        c3.metric("Latence moyenne (min)", kpis["latence_moy"])
        c4.metric("Latence max observée (min)", kpis["latence_max_obs"])
        st.subheader("Production par produit")
        st.write(kpis["par_produit"])
        st.subheader("Détail simulation")
        st.dataframe(st.session_state["df_view"], use_container_width=True)
        st.subheader("Diagramme de Gantt")
        fig = px.timeline(st.session_state["gantt_df"], x_start="Start", x_end="Finish", y="Task", color="Type", color_discrete_map={"Four":"green","Refroidissement":"blue","Avant déco":"orange","Déco":"purple","LATENCE":"red"})
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(xaxis=dict(tickformat="%H:%M"))
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("Vue process dans la journée")
        if st.session_state["_next_process_time"] is not None:
            st.session_state["process_time_slider"] = st.session_state["_next_process_time"]
            st.session_state["_next_process_time"] = None
        if st.session_state["process_time_slider"] is None:
            st.session_state["process_time_slider"] = start_time
        c1, c2, c3 = st.columns([1,1,1])
        with c1:
            if st.button("Réinitialiser la lecture"):
                st.session_state["process_time_slider"] = start_time
                st.session_state["process_autoplay_widget"] = False
                st.session_state["_next_process_time"] = None
                st.rerun()
        with c2:
            step_min = st.selectbox("Lapse de temps", [1, 5, 10, 15, 20, 30], key="process_step_widget")
        with c3:
            autoplay = st.toggle("Lecture automatique", key="process_autoplay_widget")
        current_value_aligned = align_minute_to_step(st.session_state["process_time_slider"], start_min=start_time, end_min=end_time, step_min=step_min)
        st.session_state["process_time_slider"] = current_value_aligned
        current_minute = st.slider("Choisir un instant dans la journée", min_value=start_time, max_value=end_time, value=current_value_aligned, step=step_min, key="process_time_slider")
        current_minute = align_minute_to_step(current_minute, start_min=start_time, end_min=end_time, step_min=step_min)
        st.markdown(f"""<div style='display:inline-block;width:260px;font-size:26px;font-weight:bold;background-color:#f0f4ff;color:#003366;border-left:6px solid #FF4B4B;padding:10px;border-radius:6px;margin-top:10px;'>⏱ {minutes_to_hhmm(current_minute)}</div>""", unsafe_allow_html=True)
        process_state = get_process_state_at_time(st.session_state["df_raw"], current_minute)
        zone_cols = st.columns(5)
        for zone_name, col in [("Four", zone_cols[0]), ("Refroid. Z1", zone_cols[1]), ("Refroid. Z2", zone_cols[2]), ("Avant déco", zone_cols[3]), ("Déco", zone_cols[4])]:
            with col:
                st.markdown(f"### {zone_name}")
                zone_items = process_state.get(zone_name, [])
                if zone_items:
                    for item in zone_items:
                        st.markdown(f"- {item}")
                else:
                    st.caption("—")
        if autoplay:
            next_value = current_minute + step_min
            if next_value > end_time:
                next_value = start_time
            st.session_state["_next_process_time"] = align_minute_to_step(next_value, start_min=start_time, end_min=end_time, step_min=step_min)
            time.sleep(0.6)
            st.rerun()
        excel_bytes = build_excel_bytes(simulation_df=st.session_state["df_view"], scenarios_df=st.session_state.get("df_scenarios"), overtime_df=st.session_state.get("df_ot_summary"), mix_df=st.session_state.get("df_mix"), cycle_times_df=st.session_state["cycle_times_all"])
        st.download_button("Télécharger Excel", data=excel_bytes, file_name=f"simulation_{selected_prm}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab2:
    st.header(f"Optimisation – {PRM_LABELS[selected_prm]}")
    cycle_times_all = cycle_times_from_editor(st.session_state["cycle_times_all"])
    available_products = list(cycle_times_all.get(selected_prm, {}).keys())
    if not available_products:
        st.info("Définissez d'abord les temps de cycle pour cette PRM.")
    else:
        mode_optim = st.selectbox("Mode d'optimisation", ["Production max", "Équilibre", "Latence faible"], index=1)
        st.write("L'optimisation compare : les pauses (0 / 30 / 60 min matin + soir), les permutations du mix actuellement choisi sur les 4 bras, et plusieurs latences cibles acceptées.")
        st.write(f"La limite dure process reste fixée à {latence_limite_optim} min : aucune proposition ne dépassera cette valeur.")
        if st.button("Lancer l'optimisation"):
            base_config = {
                "arms_config": {1: st.session_state.get(f"{selected_prm}_arm_1", available_products[0]), 2: st.session_state.get(f"{selected_prm}_arm_2", available_products[min(1,len(available_products)-1)]), 3: st.session_state.get(f"{selected_prm}_arm_3", available_products[min(2,len(available_products)-1)]), 4: st.session_state.get(f"{selected_prm}_arm_4", available_products[min(3,len(available_products)-1)])},
                "cycle_times": cycle_times_all[selected_prm],
                "first_arm": st.session_state.get(f"first_arm_{selected_prm}", DEFAULT_FIRST_ARMS[selected_prm]),
            }
            pause_start_matin_min = pause_matin_start.hour * 60 + pause_matin_start.minute
            pause_start_soir_min = pause_soir_start.hour * 60 + pause_soir_start.minute
            latence_values = [v for v in [0,2,4,6,8,10,15,20] if v <= latence_limite_optim]
            if latence_limite_optim not in latence_values:
                latence_values.append(latence_limite_optim)
            latence_values = sorted(set(latence_values))
            df_scenarios_all, best = evaluate_optimization(prm_name=selected_prm, start_time=start_time, end_time=end_time, base_config=base_config, latence_values=latence_values, send_gap_min=send_gap_min, deco_gap_min=deco_gap_min, pause_start_matin=pause_start_matin_min, pause_start_aprem=pause_start_soir_min, pause_durations=[0,30,60], mode_optim=mode_optim, latence_limite_process=latence_limite_optim)
            df_top3 = pd.DataFrame()
            if df_scenarios_all is not None and not df_scenarios_all.empty:
                df_top3 = (df_scenarios_all.sort_values(by=["Rang pause","Pause (min)"], ascending=[True,True]).groupby("Pause (min)", as_index=False).first().sort_values("Pause (min)").reset_index(drop=True))
            df_ot_summary = evaluate_overtime_summary_from_best(best_scenario=best, prm_name=selected_prm, start_time=start_time, end_time=end_time, base_config=base_config, send_gap_min=send_gap_min, deco_gap_min=deco_gap_min, pause_start_matin=pause_start_matin_min, pause_start_aprem=pause_start_soir_min, overtime_values=[0,15,30,45,60])
            st.session_state["df_scenarios_all"] = df_scenarios_all
            st.session_state["df_scenarios"] = df_top3
            st.session_state["best_scenario"] = best
            st.session_state["df_ot_summary"] = df_ot_summary

        if st.session_state["df_scenarios"] is not None and not st.session_state["df_scenarios"].empty:
            best = st.session_state["best_scenario"]
            df_top3 = st.session_state["df_scenarios"]
            df_ot_summary = st.session_state.get("df_ot_summary")
            c1, c2, c3, c4 = st.columns(4)
            if best is not None:
                c1.metric("Meilleur scénario – Production", int(best["Production"]))
                c2.metric("Meilleur scénario – Latence cible", int(best["Latence cible acceptée (min)"]))
                c3.metric("Meilleur scénario – Latence moy", round(best["Latence moy"], 2))
                c4.metric("Meilleur scénario – Taux four (%)", round(best["Taux four (%)"], 1))
                st.success(f"Meilleur scénario : pause {best['Pause (min)']} min matin + soir | ordre {best['Ordre bras']} | latence cible acceptée {best['Latence cible acceptée (min)']} min | production {best['Production']} | latence moy {best['Latence moy']:.2f} | latence max obs {best['Latence max observée']:.2f} | taux four {best['Taux four (%)']:.1f}%")
            st.subheader("Cliquez directement sur un scénario")
            columns_to_show = ["Pause (min)", "Ordre bras", "Latence cible acceptée (min)", "Production", "Latence moy", "Latence max observée", "Taux four (%)", "Mode optimisation"]
            df_grid = df_top3[[c for c in columns_to_show if c in df_top3.columns]].copy()
            gb = GridOptionsBuilder.from_dataframe(df_grid)
            gb.configure_selection(selection_mode="single", use_checkbox=False)
            gb.configure_grid_options(domLayout="normal")
            grid_response = AgGrid(df_grid, gridOptions=gb.build(), update_mode=GridUpdateMode.SELECTION_CHANGED, theme="streamlit", fit_columns_on_grid_load=True, height=240, reload_data=True)
            selected_rows = grid_response.get("selected_rows", [])
            if isinstance(selected_rows, pd.DataFrame):
                selected_rows = selected_rows.to_dict("records")
            if selected_rows:
                selected = selected_rows[0]
                match = df_top3[(df_top3["Pause (min)"] == selected["Pause (min)"]) & (df_top3["Ordre bras"] == selected["Ordre bras"]) & (df_top3["Latence cible acceptée (min)"] == selected["Latence cible acceptée (min)"])]
                if not match.empty:
                    scenario_row = match.iloc[0]
                    pause_duration = int(scenario_row["Pause (min)"])
                    latence_cible_selected = int(scenario_row["Latence cible acceptée (min)"])
                    mode_selected = scenario_row.get("Mode optimisation", mode_optim)
                    arms_config_selected = {1: scenario_row["Bras 1"], 2: scenario_row["Bras 2"], 3: scenario_row["Bras 3"], 4: scenario_row["Bras 4"]}
                    pause_start_matin_min = pause_matin_start.hour * 60 + pause_matin_start.minute
                    pause_start_soir_min = pause_soir_start.hour * 60 + pause_soir_start.minute
                    pause_windows_selected = []
                    if pause_duration > 0:
                        pause_windows_selected = [(pause_start_matin_min, pause_start_matin_min + pause_duration), (pause_start_soir_min, pause_start_soir_min + pause_duration)]
                    arbitration_weights = WEIGHT_PROFILES.get(mode_selected, WEIGHT_PROFILES["Équilibre"])["plan"]
                    cfg_selected = PRMSimulationConfig(prm_name=selected_prm, start_time=start_time, end_time=end_time, arms_config=arms_config_selected, cycle_times=cycle_times_all[selected_prm], first_arm=st.session_state.get(f"first_arm_{selected_prm}", DEFAULT_FIRST_ARMS[selected_prm]), send_gap_min=send_gap_min, latence_max=latence_limite_optim, latence_cible=latence_cible_selected, deco_gap_min=deco_gap_min, four_gap_min=FOUR_GAP_MIN, pause_windows=pause_windows_selected, arbitration_weights=arbitration_weights)
                    try:
                        df_detail = simulate_prm(cfg_selected)
                        kpis_detail = compute_prm_kpis(df_detail, start_time, end_time)
                        st.subheader("Détail du scénario sélectionné")
                        d1, d2, d3, d4 = st.columns(4)
                        d1.metric("Production", kpis_detail["production"])
                        d2.metric("Taux four (%)", kpis_detail["taux_four"])
                        d3.metric("Latence moy", kpis_detail["latence_moy"])
                        d4.metric("Latence max", kpis_detail["latence_max_obs"])
                        st.dataframe(format_simulation_df(df_detail), use_container_width=True)
                        st.subheader("Gantt du scénario sélectionné")
                        gantt_detail = build_gantt_source(df_detail)
                        fig_detail = px.timeline(gantt_detail, x_start="Start", x_end="Finish", y="Task", color="Type", color_discrete_map={"Four":"green","Refroidissement":"blue","Avant déco":"orange","Déco":"purple","LATENCE":"red"})
                        fig_detail.update_yaxes(autorange="reversed")
                        fig_detail.update_layout(xaxis=dict(tickformat="%H:%M"))
                        st.plotly_chart(fig_detail, use_container_width=True)
                    except Exception:
                        import traceback
                        st.error("Erreur lors de la reconstruction du scénario cliqué")
                        st.code(traceback.format_exc(), language="python")
            if df_ot_summary is not None and not df_ot_summary.empty:
                st.subheader("Synthèse overtime du meilleur scénario")
                st.dataframe(df_ot_summary, use_container_width=True)
        elif st.session_state["df_scenarios"] is not None:
            st.warning("Aucun scénario n'a pu être évalué.")
