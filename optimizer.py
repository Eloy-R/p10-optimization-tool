import itertools
import pandas as pd

from simulation import PRMSimulationConfig, compute_prm_kpis, simulate_prm


# =========================================================
# Génère uniquement les permutations du mix actuel (4 bras)
# =========================================================
def generate_orders(arms_config):
    base_order = [
        arms_config[1],
        arms_config[2],
        arms_config[3],
        arms_config[4],
    ]
    return list(set(itertools.permutations(base_order, 4)))


def build_arms_config(order):
    return {
        1: order[0],
        2: order[1],
        3: order[2],
        4: order[3],
    }


# =========================================================
# OPTIMISATION PRINCIPALE
# =========================================================
def evaluate_optimization(
    prm_name,
    start_time,
    end_time,
    base_config,
    latence_values,
    send_gap_min,
    deco_gap_min,
    pause_start_matin,
    pause_start_aprem,
    pause_durations,
):

    orders = generate_orders(base_config["arms_config"])

    records = []

    for pause in pause_durations:

        if pause > 0:
            pause_windows = [
                (pause_start_matin, pause_start_matin + pause),
                (pause_start_aprem, pause_start_aprem + pause),
            ]
        else:
            pause_windows = []

        for order in orders:

            arms_config = build_arms_config(order)
            order_label = " / ".join(order)

            for lat in latence_values:

                cfg = PRMSimulationConfig(
                    prm_name=prm_name,
                    start_time=start_time,
                    end_time=end_time,
                    arms_config=arms_config,
                    cycle_times=base_config["cycle_times"],
                    first_arm=base_config["first_arm"],
                    send_gap_min=send_gap_min,
                    latence_max=lat,
                    deco_gap_min=deco_gap_min,
                    pause_windows=pause_windows,
                )

                df = simulate_prm(cfg)
                kpis = compute_prm_kpis(df, start_time, end_time)

                records.append(
                    {
                        "Pause (min)": pause,
                        "Ordre bras": order_label,
                        "Latence consigne (min)": lat,
                        "Production": int(kpis["production"]),
                        "Latence moy": float(kpis["latence_moy"]),
                        "Latence max observée": float(kpis["latence_max_obs"]),
                        "Taux four (%)": float(kpis["taux_four"]),
                    }
                )

    df_scenarios = pd.DataFrame(records)

    if df_scenarios.empty:
        return df_scenarios, None

    # =========================================================
    # ✅ FILTRE MÉTIER : seulement latence <= 20
    # =========================================================
    df_scenarios = df_scenarios[df_scenarios["Latence max observée"] <= 20]

    if df_scenarios.empty:
        return df_scenarios, None

    # =========================================================
    # ✅ TRI LOGIQUE :
    # 1. Production max
    # 2. Latence moyenne min
    # =========================================================
    df_scenarios = df_scenarios.sort_values(
        by=["Production", "Latence moy"],
        ascending=[False, True],
    ).reset_index(drop=True)

    best = df_scenarios.iloc[0].to_dict()

    return df_scenarios, best


# =========================================================
# (inutile maintenant mais gardé pour compatibilité app.py)
# =========================================================
def build_pause_latency_curve(df):
    return pd.DataFrame()


# =========================================================
# OVERTIME
# =========================================================
def evaluate_overtime_summary_from_best(
    best_scenario,
    prm_name,
    start_time,
    end_time,
    base_config,
    send_gap_min,
    deco_gap_min,
    pause_start_matin,
    pause_start_aprem,
    overtime_values,
):

    if best_scenario is None:
        return pd.DataFrame()

    order = best_scenario["Ordre bras"].split(" / ")

    arms_config = {
        1: order[0],
        2: order[1],
        3: order[2],
        4: order[3],
    }

    pause = best_scenario["Pause (min)"]

    if pause > 0:
        pause_windows = [
            (pause_start_matin, pause_start_matin + pause),
            (pause_start_aprem, pause_start_aprem + pause),
        ]
    else:
        pause_windows = []

    latence = best_scenario["Latence consigne (min)"]

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
            latence_max=latence,
            deco_gap_min=deco_gap_min,
            pause_windows=pause_windows,
        )

        df = simulate_prm(cfg)
        kpis = compute_prm_kpis(df, start_time, end_time + overtime)

        rows.append(
            {
                "Overtime (min)": overtime,
                "Production": int(kpis["production"]),
                "Latence moy": float(kpis["latence_moy"]),
                "Latence max observée": float(kpis["latence_max_obs"]),
                "Taux four (%)": float(kpis["taux_four"]),
            }
        )

    return pd.DataFrame(rows)
