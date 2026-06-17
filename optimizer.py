import itertools
import pandas as pd

from simulation import PRMSimulationConfig, compute_prm_kpis, simulate_prm


def generate_all_orders(products):
    """
    Génère toutes les combinaisons possibles de 4 bras
    ex: cuve, cuve, cuve, cloison
    """
    return list(itertools.product(products, repeat=4))


def build_arms_config(order):
    return {
        1: order[0],
        2: order[1],
        3: order[2],
        4: order[3],
    }


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
    products = list(base_config["cycle_times"].keys())

    all_orders = generate_all_orders(products)

    results = []

    for pause in pause_durations:
        if pause > 0:
            pause_windows = [
                (pause_start_matin, pause_start_matin + pause),
                (pause_start_aprem, pause_start_aprem + pause),
            ]
        else:
            pause_windows = []

        for order in all_orders:
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

                results.append(
                    {
                        "Pause (min)": pause,
                        "Ordre bras": order_label,
                        "Latence consigne (min)": lat,
                        "Production": int(kpis["production"]),
                        "Latence moy": round(float(kpis["latence_moy"]), 2),
                        "Latence max observée": round(float(kpis["latence_max_obs"]), 2),
                        "Taux four (%)": round(float(kpis["taux_four"]), 2),
                    }
                )

    df_results = pd.DataFrame(results)

    if df_results.empty:
        return df_results, None

    # Garder seulement les scénarios valides
    df_valid = df_results[df_results["Latence max observée"] <= 20]

    if df_valid.empty:
        best = None
    else:
        best = df_valid.sort_values(
            by=["Production", "Latence moy"],
            ascending=[False, True],
        ).iloc[0].to_dict()

    return df_results, best


def build_pause_latency_curve(df):
    return pd.DataFrame()


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

    pause = best_scenario["Pause (min)"]
    order = best_scenario["Ordre bras"].split(" / ")

    arms_config = {
        1: order[0],
        2: order[1],
        3: order[2],
        4: order[3],
    }

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
                "Latence moy": round(float(kpis["latence_moy"]), 2),
                "Latence max observée": round(float(kpis["latence_max_obs"]), 2),
                "Taux four (%)": round(float(kpis["taux_four"]), 2),
            }
        )

    return pd.DataFrame(rows)
