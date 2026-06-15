import itertools
import pandas as pd
from simulation import (
    PRMSimulationConfig,
    ScenarioInfeasibleError,
    compute_prm_kpis,
    format_simulation_df,
    simulate_prm,
)


def _score(kpis: dict) -> float:
    return (
        kpis["production"] * 100
        + kpis["taux_four"]
        - kpis["latence_moy"] * 10
        - kpis["latence_max_obs"] * 2
    )


def _build_config(
    prm_name,
    start_time,
    end_time,
    base_config,
    send_gap_min,
    latence_max,
    deco_gap_min,
    pause_windows,
):
    return PRMSimulationConfig(
        prm_name=prm_name,
        start_time=start_time,
        end_time=end_time,
        arms_config=base_config["arms_config"],
        cycle_times=base_config["cycle_times"],
        first_arm=base_config["first_arm"],
        send_gap_min=send_gap_min,
        latence_max=latence_max,
        deco_gap_min=deco_gap_min,
        pause_windows=pause_windows,
    )


def evaluate_scenarios(
    prm_name,
    start_time,
    end_time,
    base_config,
    send_gap_values,
    latence_values,
    deco_gap_values,
    pause_sets,
):
    records = []
    best = None
    best_score = float("-inf")

    for (pause_name, pause_windows), send_gap, lat, deco_gap in itertools.product(
        pause_sets,
        send_gap_values,
        latence_values,
        deco_gap_values,
    ):
        cfg = _build_config(
            prm_name,
            start_time,
            end_time,
            base_config,
            send_gap,
            lat,
            deco_gap,
            pause_windows,
        )

        try:
            df = simulate_prm(cfg)
        except ScenarioInfeasibleError:
            continue

        if df.empty:
            continue

        kpis = compute_prm_kpis(df, start_time, end_time)
        score = round(_score(kpis), 2)

        record = {
            "Scenario": f"{pause_name} | send {send_gap} | lat {lat} | deco {deco_gap}",
            "Pause": pause_name,
            "Send gap": send_gap,
            "Latence max": lat,
            "Déco gap": deco_gap,
            "Production": kpis["production"],
            "Taux four (%)": kpis["taux_four"],
            "Latence moy": kpis["latence_moy"],
            "Latence max observée": kpis["latence_max_obs"],
            "Score": score,
        }
        records.append(record)

        if score > best_score:
            best_score = score
            best = record

    df_records = pd.DataFrame(records)
    if not df_records.empty:
        df_records = df_records.sort_values("Score", ascending=False).reset_index(drop=True)

    return df_records, best


def evaluate_overtime(
    prm_name,
    start_time,
    end_time,
    base_config,
    send_gap_min,
    latence_max,
    deco_gap_min,
    pause_windows,
    overtime_values,
):
    rows = []
    best_extra = None
    last_piece = None
    prev_prod = None

    for extra in overtime_values:
        cfg = _build_config(
            prm_name,
            start_time,
            end_time + extra,
            base_config,
            send_gap_min,
            latence_max,
            deco_gap_min,
            pause_windows,
        )

        try:
            df = simulate_prm(cfg)
        except ScenarioInfeasibleError:
            df = pd.DataFrame()

        prod = 0 if df.empty else len(df)
        rows.append({"Overtime (min)": extra, "Production": prod})

        if prev_prod is not None and best_extra is None and prod > prev_prod:
            best_extra = extra
            if not df.empty:
                last_piece = format_simulation_df(df.tail(1))

        prev_prod = prod

    return pd.DataFrame(rows), best_extra, last_piece


def evaluate_mixes(
    prm_name,
    start_time,
    end_time,
    base_config,
    product_options,
    send_gap_min,
    latence_max,
    deco_gap_min,
    pause_windows,
):
    motifs = {
        "Actuel": None,
        "Alterné": [0, 1, 0, 1],
        "Blocs": [0, 0, 1, 1],
    }

    rows = []

    for motif_name, motif in motifs.items():
        arms = base_config["arms_config"].copy()

        if motif is not None and len(product_options) >= 2:
            for i, arm in enumerate([1, 2, 3, 4]):
                arms[arm] = product_options[motif[i] % len(product_options)]

        cfg = PRMSimulationConfig(
            prm_name=prm_name,
            start_time=start_time,
            end_time=end_time,
            arms_config=arms,
            cycle_times=base_config["cycle_times"],
            first_arm=base_config["first_arm"],
            send_gap_min=send_gap_min,
            latence_max=latence_max,
            deco_gap_min=deco_gap_min,
            pause_windows=pause_windows,
        )

        try:
            df = simulate_prm(cfg)
        except ScenarioInfeasibleError:
            continue

        if df.empty:
            continue

        kpis = compute_prm_kpis(df, start_time, end_time)
        rows.append(
            {
                "Configuration": motif_name,
                "Production": kpis["production"],
                "Taux four (%)": kpis["taux_four"],
                "Latence moy": kpis["latence_moy"],
            }
        )

    df_rows = pd.DataFrame(rows)
    if not df_rows.empty:
        df_rows = df_rows.sort_values(
            ["Production", "Taux four (%)"],
            ascending=False,
        ).reset_index(drop=True)

    return df_rows
