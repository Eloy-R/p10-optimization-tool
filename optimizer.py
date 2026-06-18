import itertools
from typing import Dict, List, Optional, Tuple

import pandas as pd

from simulation import PRMSimulationConfig, compute_prm_kpis, simulate_prm


def _unique_orders_from_current_mix(arms_config: dict) -> List[Tuple[str, str, str, str]]:
    base_order = [
        arms_config[1],
        arms_config[2],
        arms_config[3],
        arms_config[4],
    ]
    return sorted(set(itertools.permutations(base_order, 4)))


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


def _build_arms_config_from_order(order: Tuple[str, str, str, str]) -> Dict[int, str]:
    return {
        1: order[0],
        2: order[1],
        3: order[2],
        4: order[3],
    }


def _compute_multi_criteria_score(row: pd.Series, mode_optim: str) -> float:
    production = float(row["Production"])
    lat_moy = float(row["Latence moy"])
    lat_max_obs = float(row["Latence max observée"])
    taux_four = float(row["Taux four (%)"])
    pause = float(row["Pause (min)"])
    latence_consigne = float(row["Latence consigne (min)"])

    if mode_optim == "Production max":
        score = (
            production * 1000
            - lat_moy * 15
            - lat_max_obs * 4
            + taux_four * 0.5
            - pause * 0.1
            - latence_consigne * 0.1
        )
    elif mode_optim == "Latence faible":
        score = (
            production * 350
            - lat_moy * 80
            - lat_max_obs * 25
            + taux_four * 0.6
            - pause * 0.1
            - latence_consigne * 0.5
        )
    else:
        score = (
            production * 700
            - lat_moy * 40
            - lat_max_obs * 12
            + taux_four * 1.0
            - pause * 0.1
            - latence_consigne * 0.2
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
    mode_optim: str = "Équilibre",
    latence_limite_process: int = 20,
):
    """
    Optimisation logique :
    - on garde exactement le mix choisi dans l'UI ;
    - on teste les permutations uniques de ce mix ;
    - on teste les pauses 0 / 30 / 60 ;
    - on teste toutes les latences autorisées demandées ;
    - on filtre strictement les scénarios où la latence max observée dépasse la limite process ;
    - on classe selon un score multi-critères.
    """
    unique_orders = _unique_orders_from_current_mix(base_config["arms_config"])
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

                row = {
                    "Pause (min)": pause_duration,
                    "Bras 1": order[0],
                    "Bras 2": order[1],
                    "Bras 3": order[2],
                    "Bras 4": order[3],
                    "Ordre bras": order_label,
                    "Latence consigne (min)": latence_consigne,
                    "Production": int(kpis["production"]),
                    "Latence moy": round(float(kpis["latence_moy"]), 3),
                    "Latence max observée": round(float(kpis["latence_max_obs"]), 3),
                    "Taux four (%)": round(float(kpis["taux_four"]), 3),
                    "Mode optimisation": mode_optim,
                }
                records.append(row)

    df_scenarios = pd.DataFrame(records)
    if df_scenarios.empty:
        return df_scenarios, None

    # Contrainte dure process
    df_scenarios = df_scenarios[
        df_scenarios["Latence max observée"] <= latence_limite_process
    ].copy()

    if df_scenarios.empty:
        return df_scenarios, None

    df_scenarios["Score multicritère"] = df_scenarios.apply(
        lambda row: _compute_multi_criteria_score(row, mode_optim),
        axis=1,
    )

    df_scenarios = df_scenarios.sort_values(
        by=["Score multicritère", "Production", "Latence moy", "Taux four (%)"],
        ascending=[False, False, True, False],
    ).reset_index(drop=True)

    df_scenarios["Rang global"] = range(1, len(df_scenarios) + 1)
    df_scenarios["Rang pause"] = (
        df_scenarios.groupby("Pause (min)")["Score multicritère"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    best = df_scenarios.iloc[0].to_dict()
    return df_scenarios, best


def build_pause_latency_curve(df_scenarios: pd.DataFrame) -> pd.DataFrame:
    """
    Conservée pour compatibilité si vous réactivez un jour un graphe.
    Non utilisée dans la version actuelle de l'app.
    """
    if df_scenarios is None or df_scenarios.empty:
        return pd.DataFrame()

    work = df_scenarios.copy()
    work = work.sort_values(
        by=["Pause (min)", "Latence consigne (min)", "Score multicritère"],
        ascending=[True, True, False],
    )
    return work.groupby(["Pause (min)", "Latence consigne (min)"], as_index=False).first()


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
