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
