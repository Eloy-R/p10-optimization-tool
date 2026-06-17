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


# =========================================================
# OUTILS
# =========================================================
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


# =========================================================
# SESSION STATE
# =========================================================
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
    "df_scenarios": None,       # affichage = 3 meilleures lignes (1 par pause)
    "df_scenarios_all": None,   # base complète pour calcul/graph
    "df_curve": None,           # une ligne par couple pause / latence
    "best_scenario": None,
    "selected_prm": None,
    "df_mix": None,
    "df_ot_summary": None,      # synthèse overtime du meilleur scénario
    # viewer process
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
    pause_matin_active = st.checkbox("Pause matin", True)
    pause_soir_active = st.checkbox("Pause soir", True)

    col1, col2 = st.columns(2)
    with col1:
        pause_matin_start = st.time_input(
            "Début pause matin",
            value=pd.Timestamp("12:00").to_pydatetime().time(),
        )
        pause_soir_start = st.time_input(
            "Début pause soir",
            value=pd.Timestamp("15:00").to_pydatetime().time(),
        )
    with col2:
        pause_matin_end = st.time_input(
            "Fin pause matin",
            value=pd.Timestamp("13:00").to_pydatetime().time(),
        )
        pause_soir_end = st.time_input(
            "Fin pause soir",
            value=pd.Timestamp("16:00").to_pydatetime().time(),
        )

    pause_windows = []
    if pause_matin_active:
        pause_windows.append(
            (
                pause_matin_start.hour * 60 + pause_matin_start.minute,
                pause_matin_end.hour * 60 + pause_matin_end.minute,
            )
        )
    if pause_soir_active:
        pause_windows.append(
            (
                pause_soir_start.hour * 60 + pause_soir_start.minute,
                pause_soir_end.hour * 60 + pause_soir_end.minute,
            )
        )


tab1, tab2, tab3 = st.tabs(["Simulation", "Optimisation", "Table des temps"])


# =========================================================
# ONGLET TEMPS DE CYCLE
# =========================================================
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


# =========================================================
# ONGLET SIMULATION
# =========================================================
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

                st.session_state["process_time_slider"] = start_time
                st.session_state["process_step_widget"] = 10
                st.session_state["process_autoplay_widget"] = False
                st.session_state["_next_process_time"] = None

            except ScenarioInfeasibleError as e:
                st.session_state["df_raw"] = None
                st.session_state["df_view"] = None
                st.session_state["gantt_df"] = None
                st.session_state["kpis"] = None
                st.error(
                    "Scénario infaisable : la latence maximale ne peut pas être respectée avec les paramètres actuels."
                )
                st.code(str(e), language="text")

            except Exception as e:
                st.session_state["df_raw"] = None
                st.session_state["df_view"] = None
                st.session_state["gantt_df"] = None
                st.session_state["kpis"] = None
                st.error("Une erreur technique inattendue est survenue pendant la simulation.")
                st.code(str(e), language="text")

    if st.session_state["df_view"] is not None and st.session_state["selected_prm"] == selected_prm:
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
                "Avant déco": "orange",
                "Déco": "purple",
                "LATENCE": "red",
            },
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(xaxis=dict(tickformat="%H:%M"))
        st.plotly_chart(fig, use_container_width=True)

        # ----------------------
        # Vue process + lecture automatique
        # ----------------------
        st.subheader("Vue process dans la journée")

        if st.session_state["_next_process_time"] is not None:
            st.session_state["process_time_slider"] = st.session_state["_next_process_time"]
            st.session_state["_next_process_time"] = None

        if st.session_state["process_time_slider"] is None:
            st.session_state["process_time_slider"] = start_time

        c1, c2, c3 = st.columns([1, 1, 1])

        with c1:
            if st.button("Réinitialiser la lecture"):
                st.session_state["process_time_slider"] = start_time
                st.session_state["process_autoplay_widget"] = False
                st.session_state["_next_process_time"] = None
                st.rerun()

        with c2:
            step_min = st.selectbox(
                "Lapse de temps",
                [1, 5, 10, 15, 20, 30],
                key="process_step_widget",
            )

        with c3:
            autoplay = st.toggle(
                "Lecture automatique",
                key="process_autoplay_widget",
            )

        current_value_aligned = align_minute_to_step(
            st.session_state["process_time_slider"],
            start_min=start_time,
            end_min=end_time,
            step_min=step_min,
        )
        st.session_state["process_time_slider"] = current_value_aligned

        current_minute = st.slider(
            "Choisir un instant dans la journée",
            min_value=start_time,
            max_value=end_time,
            value=current_value_aligned,
            step=step_min,
            key="process_time_slider",
        )

        current_minute = align_minute_to_step(
            current_minute,
            start_min=start_time,
            end_min=end_time,
            step_min=step_min,
        )

        st.caption(f"Heure sélectionnée : {minutes_to_hhmm(current_minute)}")

        process_state = get_process_state_at_time(
            st.session_state["df_raw"],
            current_minute,
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

        if autoplay:
            next_value = current_minute + step_min
            if next_value > end_time:
                next_value = start_time

            next_value = align_minute_to_step(
                next_value,
                start_min=start_time,
                end_min=end_time,
                step_min=step_min,
            )

            st.session_state["_next_process_time"] = next_value
            time.sleep(0.6)
            st.rerun()

        excel_bytes = build_excel_bytes(
            simulation_df=st.session_state["df_view"],
            scenarios_df=st.session_state.get("df_scenarios"),
            overtime_df=st.session_state.get("df_ot_summary"),
            mix_df=st.session_state.get("df_mix"),
            cycle_times_df=st.session_state["cycle_times_all"],
        )
        st.download_button(
            "Télécharger Excel",
            data=excel_bytes,
            file_name=f"simulation_{selected_prm}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


# =========================================================
# ONGLET OPTIMISATION
# =========================================================
with tab2:
    st.header(f"Optimisation – {PRM_LABELS[selected_prm]}")

    cycle_times_all = cycle_times_from_editor(st.session_state["cycle_times_all"])
    available_products = list(cycle_times_all.get(selected_prm, {}).keys())

    if not available_products:
        st.info("Définissez d'abord les temps de cycle pour cette PRM.")
    else:
        st.write(
            "L'optimisation compare : les **pauses** (0 / 30 / 60 min matin + soir), "
            "les **permutations des 4 bras** et les **valeurs de latence** jusqu'à 20 min."
        )
        st.write(
            "Le tableau reprend uniquement **3 scénarios** : le meilleur pour **0 min**, **30 min** et **60 min** de pause."
        )
        st.write(
            "L'**overtime** est conservé en **synthèse annexe** sur le meilleur scénario, mais n'entre pas dans le classement principal."
        )

        if st.button(\"Lancer l'optimisation\"):\n            base_config = {\n                \"arms_config\": {\n                    1: st.session_state.get(f\"{selected_prm}_arm_1\", available_products[0]),\n                    2: st.session_state.get(f\"{selected_prm}_arm_2\", available_products[min(1, len(available_products) - 1)]),\n                    3: st.session_state.get(f\"{selected_prm}_arm_3\", available_products[min(2, len(available_products) - 1)]),\n                    4: st.session_state.get(f\"{selected_prm}_arm_4\", available_products[min(3, len(available_products) - 1)]),\n                },\n                \"cycle_times\": cycle_times_all[selected_prm],\n                \"first_arm\": st.session_state.get(\n                    f\"first_arm_{selected_prm}\",\n                    DEFAULT_FIRST_ARMS[selected_prm],\n                ),\n            }\n\n            pause_start_matin = pause_matin_start.hour * 60 + pause_matin_start.minute\n            pause_start_soir = pause_soir_start.hour * 60 + pause_soir_start.minute\n\n            latence_values = list(range(max(5, latence_max), 21))\n            if latence_max <= 20 and latence_max not in latence_values:\n                latence_values = sorted(set(latence_values + [latence_max]))\n\n            df_scenarios_all, best = evaluate_optimization(\n                prm_name=selected_prm,\n                start_time=start_time,\n                end_time=end_time,\n                base_config=base_config,\n                latence_values=latence_values,\n                send_gap_min=send_gap_min,\n                deco_gap_min=deco_gap_min,\n                pause_start_matin=pause_start_matin,\n                pause_start_aprem=pause_start_soir,\n                pause_durations=[0, 30, 60],\n            )\n\n            df_top3 = pd.DataFrame()\n            if df_scenarios_all is not None and not df_scenarios_all.empty:\n                df_top3 = (\n                    df_scenarios_all.sort_values(\n                        by=[\"Pause (min)\", \"Production\", \"Latence moy\", \"Taux four (%)\", \"Latence consigne (min)\"],\n                        ascending=[True, False, True, False, True],\n                    )\n                    .groupby(\"Pause (min)\", as_index=False)\n                    .first()\n                    .sort_values(\"Pause (min)\")\n                    .reset_index(drop=True)\n                )\n\n            df_curve = build_pause_latency_curve(df_scenarios_all)\n            df_ot_summary = evaluate_overtime_summary_from_best(\n                best_scenario=best,\n                prm_name=selected_prm,\n                start_time=start_time,\n                end_time=end_time,\n                base_config=base_config,\n                send_gap_min=send_gap_min,\n                deco_gap_min=deco_gap_min,\n                pause_start_matin=pause_start_matin,\n                pause_start_aprem=pause_start_soir,\n                overtime_values=[0, 15, 30, 45, 60],\n            )\n\n            st.session_state[\"df_scenarios_all\"] = df_scenarios_all\n            st.session_state[\"df_scenarios\"] = df_top3\n            st.session_state[\"df_curve\"] = df_curve\n            st.session_state[\"best_scenario\"] = best\n            st.session_state[\"df_ot_summary\"] = df_ot_summary\n\n        if st.session_state[\"df_scenarios\"] is not None and not st.session_state[\"df_scenarios\"].empty:\n            best = st.session_state[\"best_scenario\"]\n            df_top3 = st.session_state[\"df_scenarios\"]\n            df_curve = st.session_state.get(\"df_curve\")\n            df_ot_summary = st.session_state.get(\"df_ot_summary\")\n\n            c1, c2, c3, c4 = st.columns(4)\n            if best is not None:\n                c1.metric(\"Meilleur scénario – Production\", int(best[\"Production\"]))\n                c2.metric(\"Meilleur scénario – Latence consigne\", int(best[\"Latence consigne (min)\"]))\n                c3.metric(\"Meilleur scénario – Latence moy\", round(best[\"Latence moy\"], 2))\n                c4.metric(\"Meilleur scénario – Taux four (%)\", round(best[\"Taux four (%)\"], 1))\n\n            if best is not None:\n                st.success(\n                    f\"Meilleur scénario : pause {best['Pause (min)']} min matin + soir | \"\n                    f\"ordre {best['Ordre bras']} | latence consigne {best['Latence consigne (min)']} min | \"\n                    f\"production {best['Production']} | latence moy {best['Latence moy']:.2f} | \"\n                    f\"latence max obs {best['Latence max observée']:.2f} | taux four {best['Taux four (%)']:.1f}%\"\n                )\n\n            st.subheader(\"Les 3 meilleurs scénarios (1 par niveau de pause)\")\n            st.dataframe(df_top3, use_container_width=True)\n\n            if df_ot_summary is not None and not df_ot_summary.empty:\n                st.subheader(\"Synthèse overtime du meilleur scénario\")\n                st.dataframe(df_ot_summary, use_container_width=True)\n\n            if df_curve is not None and not df_curve.empty:\n                st.subheader(\"Production en fonction de la latence et des pauses\")\n                fig_curve = px.line(\n                    df_curve,\n                    x=\"Latence consigne (min)\",\n                    y=\"Production\",\n                    color=\"Pause (min)\",\n                    markers=True,\n                    hover_data=[\"Ordre bras\", \"Latence moy\", \"Taux four (%)\", \"Latence max observée\"],\n                    title=\"Production selon la latence et les pauses\",\n                )\n                st.plotly_chart(fig_curve, use_container_width=True)\n\n        elif st.session_state[\"df_scenarios\"] is not None:\n            st.warning(\"Aucun scénario n'a pu être évalué.\")\n'''\ncompile(app_code,'app.py','exec')\nprint('app ok')","result":"","status":"Success","stdout":"app ok\n","stderr":"","outputFiles":[]}Oui, c’est beaucoup plus logique comme ça 👍

## Ce que je prends en compte dans cette nouvelle version
Vous voulez désormais :

### Dans l’onglet **Optimisation**
1. **Un tableau court**
   - seulement **3 lignes**
   - la meilleure pour :
     - **0 min de pause**
     - **30 min de pause**
     - **60 min de pause**

2. **Un seul graphe utile**
   - **production en fonction de la latence**
   - avec les **pauses** comme série / couleur

3. **L’overtime ne doit pas disparaître**
   - mais **pas dans le tableau principal**
   - et **pas avec un graphe**
   - donc je le garde en **synthèse annexe** du meilleur scénario

4. **Aucune modification de `simulation.py`**
   - on garde votre moteur tel quel

👉 C’est exactement ce que j’ai structuré ci-dessous.

---

# Fichiers à remplacer entièrement
Remplacez **entièrement** :

- `optimizer.py`
- `app.py`

⚠️ **Ne touchez pas à `simulation.py`** dans cette étape.

---

# 1) `optimizer.py`

```python
import itertools
from typing import List, Tuple, Optional

import pandas as pd

from simulation import PRMSimulationConfig, compute_prm_kpis, simulate_prm


def _unique_orders(values: List[str]) -> List[Tuple[str, str, str, str]]:
    return sorted(set(itertools.permutations(values, 4)))


def _pause_windows_from_duration(
    pause_start_matin: int,
    pause_start_aprem: int,
    duration_min: int,
):
    if duration_min <= 0:
        return []
    return [
        (pause_start_matin, pause_start_matin + duration_min),
        (pause_start_aprem, pause_start_aprem + duration_min),
    ]


def _build_arms_config_from_order(order: Tuple[str, str, str, str]) -> dict:
    return {1: order[0], 2: order[1], 3: order[2], 4: order[3]}


def _score_row(
    production: int,
    latence_moy: float,
    latence_max_obs: float,
    taux_four: float,
    pause_duration: int,
    latence_consigne: int,
) -> float:
    """
    Priorité métier :
    1) Production maximale
    2) Impact minimal sur la latence
    3) Bonus léger sur le taux four
    4) Léger malus si on augmente trop la latence consigne / longues pauses
    """
    score = (
        production * 1000
        - latence_moy * 10
        - max(0.0, latence_max_obs - 20) * 100
        + taux_four * 0.5
        - latence_consigne * 1.0
        - pause_duration * 0.1
    )
    return round(score, 3)


def evaluate_optimization(
    prm_name: str,
    start_time: int,
    end_time: int,
    base_config: dict,
    latence_values: List[int],
    send_gap_min: int,
    deco_gap_min: int,
    pause_start_matin: int,
    pause_start_aprem: int,
    pause_durations: List[int],
):
    """
    Variables du classement principal :
    - pauses : 0 / 30 / 60 min matin + soir
    - permutations des 4 bras
    - latence consigne testée

    L'overtime n'est PAS pris en compte dans le tableau principal.
    """
    base_arms_order = [
        base_config["arms_config"][1],
        base_config["arms_config"][2],
        base_config["arms_config"][3],
        base_config["arms_config"][4],
    ]
    unique_orders = _unique_orders(base_arms_order)

    records = []

    for pause_duration in pause_durations:
        pause_windows = _pause_windows_from_duration(
            pause_start_matin,
            pause_start_aprem,
            pause_duration,
        )

        for order in unique_orders:
            arms_config = _build_arms_config_from_order(order)
            order_label = " / ".join(order)

            for latence_consigne in latence_values:
                cfg = PRMSimulationConfig(
                    prm_name=prm_name,
                    start_time=start_time,
                    end_time=end_time,
                    arms_config=arms_config,
                    cycle_times=base_config["cycle_times"],
                    first_arm=base_config["first_arm"],
                    send_gap_min=send_gap_min,
                    latence_max=latence_consigne,
                    deco_gap_min=deco_gap_min,
                    pause_windows=pause_windows,
                )

                df = simulate_prm(cfg)
                kpis = compute_prm_kpis(df, start_time, end_time)

                production = int(kpis["production"])
                lat_moy = float(kpis["latence_moy"])
                lat_max_obs = float(kpis["latence_max_obs"])
                taux_four = float(kpis["taux_four"])

                score = _score_row(
                    production=production,
                    latence_moy=lat_moy,
                    latence_max_obs=lat_max_obs,
                    taux_four=taux_four,
                    pause_duration=pause_duration,
                    latence_consigne=latence_consigne,
                )

                records.append(
                    {
                        "Pause (min)": pause_duration,
                        "Bras 1": order[0],
                        "Bras 2": order[1],
                        "Bras 3": order[2],
                        "Bras 4": order[3],
                        "Ordre bras": order_label,
                        "Latence consigne (min)": latence_consigne,
                        "Production": production,
                        "Latence moy": round(lat_moy, 3),
                        "Latence max observée": round(lat_max_obs, 3),
                        "Taux four (%)": round(taux_four, 3),
                        "Score": score,
                        "Statut": "OK" if lat_max_obs <= 20 else "Latence > 20",
                    }
                )

    df_scenarios = pd.DataFrame(records)
    if df_scenarios.empty:
        return df_scenarios, None

    df_scenarios["_ok"] = (df_scenarios["Latence max observée"] <= 20).astype(int)
    df_scenarios = df_scenarios.sort_values(
        by=["_ok", "Production", "Latence moy", "Taux four (%)", "Latence consigne (min)", "Pause (min)"],
        ascending=[False, False, True, False, True, True],
    ).drop(columns=["_ok"]).reset_index(drop=True)

    best = None
    ok_df = df_scenarios[df_scenarios["Latence max observée"] <= 20]
    if not ok_df.empty:
        best = ok_df.iloc[0].to_dict()

    return df_scenarios, best


def build_pause_latency_curve(df_scenarios: pd.DataFrame) -> pd.DataFrame:
    """
    Retourne une ligne par couple (Pause, Latence consigne)
    en gardant le meilleur scénario pour ce couple.
    """
    if df_scenarios is None or df_scenarios.empty:
        return pd.DataFrame()

    work = df_scenarios.copy()
    work["_ok"] = (work["Latence max observée"] <= 20).astype(int)
    work = work.sort_values(
        by=["Pause (min)", "Latence consigne (min)", "_ok", "Production", "Latence moy", "Taux four (%)"],
        ascending=[True, True, False, False, True, False],
    )

    best_curve = work.groupby(["Pause (min)", "Latence consigne (min)"], as_index=False).first()
    return best_curve.drop(columns=["_ok"])


def evaluate_overtime_summary_from_best(
    best_scenario: Optional[dict],
    prm_name: str,
    start_time: int,
    end_time: int,
    base_config: dict,
    send_gap_min: int,
    deco_gap_min: int,
    pause_start_matin: int,
    pause_start_aprem: int,
    overtime_values: List[int],
) -> pd.DataFrame:
    """
    Calcule l'impact de l'overtime sur LE meilleur scénario de base.
    Cette synthèse est annexe : elle n'entre pas dans le classement principal.
    """
    if best_scenario is None:
        return pd.DataFrame()

    pause_duration = int(best_scenario["Pause (min)"])
    pause_windows = _pause_windows_from_duration(
        pause_start_matin,
        pause_start_aprem,
        pause_duration,
    )

    arms_config = {
        1: best_scenario["Bras 1"],
        2: best_scenario["Bras 2"],
        3: best_scenario["Bras 3"],
        4: best_scenario["Bras 4"],
    }
    latence_consigne = int(best_scenario["Latence consigne (min)"])

    rows = []
    for overtime in overtime_values:
        cfg = PRMSimulationConfig(
            prm_name=prm_name,
            start_time=start_time,
            end_time=end_time + overtime,
            arms_config=arms_config,
            cycle_times=base_config["cycle_times"],
            first_arm=base_config["first_arm"],
            send_gap_min=send_gap_min,
            latence_max=latence_consigne,
            deco_gap_min=deco_gap_min,
            pause_windows=pause_windows,
        )

        df = simulate_prm(cfg)
        kpis = compute_prm_kpis(df, start_time, end_time + overtime)

        rows.append(
            {
                "Overtime (min)": overtime,
                "Production": int(kpis["production"]),
                "Latence moy": round(float(kpis["latence_moy"]), 3),
                "Latence max observée": round(float(kpis["latence_max_obs"]), 3),
                "Taux four (%)": round(float(kpis["taux_four"]), 3),
            }
        )

    return pd.DataFrame(rows)
