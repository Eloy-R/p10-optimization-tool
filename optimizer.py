import itertools
import pandas as pd

from simulation import PRMSimulationConfig, compute_prm_kpis, simulate_prm


def generate_orders(arms_config):
    """
    Génère uniquement les permutations du mix actuel choisi sur les 4 bras.
    Exemple : si le mix actuel est Cuve / Cuve / Cloison / Cloison,
    on teste uniquement les permutations uniques de ce mix.
    """
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


def _compute_multi_criteria_score(row, mode_optim: str):
    production = float(row["Production"])
    lat_moy = float(row["Latence moy"])
    lat_max_obs = float(row["Latence max observée"])
    taux_four = float(row["Taux four (%)"])
    pause = float(row["Pause (min)"])
    latence_consigne = float(row["Latence consigne (min)"])

    if mode_optim == "Production max":
        # priorité absolue au volume ; départage par latence moyenne puis taux four
        score = (
            production * 1000
            - lat_moy * 10
            - lat_max_obs * 2
            + taux_four * 0.5
            - pause * 0.1
            - latence_consigne * 0.1
        )
    elif mode_optim == "Latence faible":
        # priorité à la qualité process, puis volume
        score = (
            production * 300
            - lat_moy * 60
            - lat_max_obs * 25
            + taux_four * 0.3
            - pause * 0.1
            - latence_consigne * 0.5
        )
    else:
        # Équilibre : compromis industriel production / qualité / taux four
        score = (
            production * 700
            - lat_moy * 25
            - lat_max_obs * 8
            + taux_four * 0.8
            - pause * 0.1
            - latence_consigne * 0.3
        )

    return round(score, 3)


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
    mode_optim="Équilibre",
    latence_limite_process=20,
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
                        "Bras 1": order[0],
                        "Bras 2": order[1],
                        "Bras 3": order[2],
                        "Bras 4": order[3],
                        "Latence consigne (min)": lat,
                        "Production": int(kpis["production"]),
                        "Latence moy": round(float(kpis["latence_moy"]), 3),
                        "Latence max observée": round(float(kpis["latence_max_obs"]), 3),
                        "Taux four (%)": round(float(kpis["taux_four"]), 3),
                        "Mode optimisation": mode_optim,
                    }
                )

    df_scenarios = pd.DataFrame(records)
    if df_scenarios.empty:
        return df_scenarios, None

    # Contrainte dure : seuls les scénarios respectant la limite process sont gardés.
    df_scenarios = df_scenarios[df_scenarios["Latence max observée"] <= latence_limite_process].copy()

    if df_scenarios.empty:
        return df_scenarios, None

    df_scenarios["Score multicritère"] = df_scenarios.apply(
        lambda row: _compute_multi_criteria_score(row, mode_optim),
        axis=1,
    )

    # Classement global selon le mode choisi
    df_scenarios = df_scenarios.sort_values(
        by=["Score multicritère", "Production", "Latence moy", "Taux four (%)"],
        ascending=[False, False, True, False],
    ).reset_index(drop=True)

    # Rang global
    df_scenarios["Rang global"] = range(1, len(df_scenarios) + 1)

    # Rang par pause (utile pour sortir le meilleur 0 / 30 / 60)
    df_scenarios["Rang pause"] = (
        df_scenarios.groupby("Pause (min)")["Score multicritère"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    best = df_scenarios.iloc[0].to_dict()
    return df_scenarios, best


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

    pause = int(best_scenario["Pause (min)"])
    if pause > 0:
        pause_windows = [
            (pause_start_matin, pause_start_matin + pause),
            (pause_start_aprem, pause_start_aprem + pause),
        ]
    else:
        pause_windows = []

    latence = int(best_scenario["Latence consigne (min)"])
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
