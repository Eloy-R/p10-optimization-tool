import itertools
from typing import Dict, List, Optional, Tuple

import pandas as pd

from simulation import PRMSimulationConfig, compute_prm_kpis, simulate_prm

FOUR_GAP_MIN = 1

WEIGHT_PROFILES = {
    "Production max": {
        "plan": {"target_penalty": 0.8, "latency": 0.15, "start_delay": 4.0, "cycle_span": 0.05},
        "scenario": {"prod": 1200.0, "lat_moy": 8.0, "lat_max": 2.0, "taux_four": 1.5, "pause": 0.1, "lat_cible": 0.05},
    },
    "Équilibre": {
        "plan": {"target_penalty": 1.5, "latency": 0.6, "start_delay": 2.0, "cycle_span": 0.15},
        "scenario": {"prod": 900.0, "lat_moy": 25.0, "lat_max": 6.0, "taux_four": 1.2, "pause": 0.1, "lat_cible": 0.12},
    },
    "Latence faible": {
        "plan": {"target_penalty": 3.5, "latency": 1.8, "start_delay": 0.8, "cycle_span": 0.25},
        "scenario": {"prod": 500.0, "lat_moy": 80.0, "lat_max": 18.0, "taux_four": 0.8, "pause": 0.1, "lat_cible": 0.25},
    },
}


def _unique_orders_from_current_mix(arms_config: dict) -> List[Tuple[str, str, str, str]]:
    base_order = [arms_config[1], arms_config[2], arms_config[3], arms_config[4]]
    return sorted(set(itertools.permutations(base_order, 4)))


def _pause_windows_from_duration(pause_start_matin: int, pause_start_aprem: int, duration_min: int):
    if duration_min <= 0:
        return []
    return [(pause_start_matin, pause_start_matin + duration_min), (pause_start_aprem, pause_start_aprem + duration_min)]


def _build_arms_config_from_order(order: Tuple[str, str, str, str]) -> Dict[int, str]:
    return {1: order[0], 2: order[1], 3: order[2], 4: order[3]}


def _compute_multi_criteria_score(row: pd.Series, mode_optim: str) -> float:
    profile = WEIGHT_PROFILES.get(mode_optim, WEIGHT_PROFILES["Équilibre"])["scenario"]
    return round(
        profile["prod"] * float(row["Production"])
        - profile["lat_moy"] * float(row["Latence moy"])
        - profile["lat_max"] * float(row["Latence max observée"])
        + profile["taux_four"] * float(row["Taux four (%)"])
        - profile["pause"] * float(row["Pause (min)"])
        - profile["lat_cible"] * float(row["Latence cible acceptée (min)"]),
        3,
    )


def evaluate_optimization(prm_name: str, start_time: int, end_time: int, base_config: dict, latence_values: List[int], send_gap_min: int, deco_gap_min: int, pause_start_matin: int, pause_start_aprem: int, pause_durations: List[int], mode_optim: str = "Équilibre", latence_limite_process: int = 20):
    profile = WEIGHT_PROFILES.get(mode_optim, WEIGHT_PROFILES["Équilibre"])
    unique_orders = _unique_orders_from_current_mix(base_config["arms_config"])
    records = []

    for pause_duration in pause_durations:
        pause_windows = _pause_windows_from_duration(pause_start_matin, pause_start_aprem, pause_duration)
        for order in unique_orders:
            arms_config = _build_arms_config_from_order(order)
            order_label = " / ".join(order)
            for latence_cible in latence_values:
                cfg = PRMSimulationConfig(
                    prm_name=prm_name,
                    start_time=start_time,
                    end_time=end_time,
                    arms_config=arms_config,
                    cycle_times=base_config["cycle_times"],
                    first_arm=base_config["first_arm"],
                    send_gap_min=send_gap_min,
                    latence_max=latence_limite_process,
                    latence_cible=latence_cible,
                    deco_gap_min=deco_gap_min,
                    four_gap_min=FOUR_GAP_MIN,
                    pause_windows=pause_windows,
                    arbitration_weights=profile["plan"],
                )
                df = simulate_prm(cfg)
                kpis = compute_prm_kpis(df, start_time, end_time)
                records.append({
                    "Pause (min)": pause_duration,
                    "Bras 1": order[0],
                    "Bras 2": order[1],
                    "Bras 3": order[2],
                    "Bras 4": order[3],
                    "Ordre bras": order_label,
                    "Latence cible acceptée (min)": latence_cible,
                    "Production": int(kpis["production"]),
                    "Latence moy": round(float(kpis["latence_moy"]), 3),
                    "Latence max observée": round(float(kpis["latence_max_obs"]), 3),
                    "Taux four (%)": round(float(kpis["taux_four"]), 3),
                    "Mode optimisation": mode_optim,
                })

    df_scenarios = pd.DataFrame(records)
    if df_scenarios.empty:
        return df_scenarios, None

    df_scenarios = df_scenarios[df_scenarios["Latence max observée"] <= latence_limite_process].copy()
    if df_scenarios.empty:
        return df_scenarios, None

    df_scenarios["Score multicritère"] = df_scenarios.apply(lambda row: _compute_multi_criteria_score(row, mode_optim), axis=1)
    df_scenarios = df_scenarios.sort_values(by=["Score multicritère", "Production", "Latence moy", "Taux four (%)"], ascending=[False, False, True, False]).reset_index(drop=True)
    df_scenarios["Rang global"] = range(1, len(df_scenarios) + 1)
    df_scenarios["Rang pause"] = df_scenarios.groupby("Pause (min)")["Score multicritère"].rank(method="first", ascending=False).astype(int)
    best = df_scenarios.iloc[0].to_dict()
    return df_scenarios, best


def evaluate_overtime_summary_from_best(best_scenario: Optional[dict], prm_name: str, start_time: int, end_time: int, base_config: dict, send_gap_min: int, deco_gap_min: int, pause_start_matin: int, pause_start_aprem: int, overtime_values: List[int]) -> pd.DataFrame:
    if best_scenario is None:
        return pd.DataFrame()
    pause_duration = int(best_scenario["Pause (min)"])
    pause_windows = _pause_windows_from_duration(pause_start_matin, pause_start_aprem, pause_duration)
    arms_config = {1: best_scenario["Bras 1"], 2: best_scenario["Bras 2"], 3: best_scenario["Bras 3"], 4: best_scenario["Bras 4"]}
    latence_cible = int(best_scenario["Latence cible acceptée (min)"])
    mode_optim = best_scenario.get("Mode optimisation", "Équilibre")
    profile = WEIGHT_PROFILES.get(mode_optim, WEIGHT_PROFILES["Équilibre"])

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
            latence_max=20,
            latence_cible=latence_cible,
            deco_gap_min=deco_gap_min,
            four_gap_min=FOUR_GAP_MIN,
            pause_windows=pause_windows,
            arbitration_weights=profile["plan"],
        )
        df = simulate_prm(cfg)
        kpis = compute_prm_kpis(df, start_time, end_time + overtime)
        rows.append({
            "Overtime (min)": overtime,
            "Production": int(kpis["production"]),
            "Latence moy": round(float(kpis["latence_moy"]), 3),
            "Latence max observée": round(float(kpis["latence_max_obs"]), 3),
            "Taux four (%)": round(float(kpis["taux_four"]), 3),
        })
    return pd.DataFrame(rows)
