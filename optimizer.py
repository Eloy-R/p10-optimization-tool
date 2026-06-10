import itertools
import pandas as pd
from simulation import PRMSimulationConfig, simulate_all, compute_global_kpis, format_simulation_df


def _score(kpis: dict) -> float:
    return (
        kpis["production"] * 100
        + kpis["taux_four_global"]
        - kpis["latence_moy"] * 10
        - kpis["latence_max_obs"] * 2
    )


def _build_configs(start_time, end_time, base_configs, send_gap_min, latence_max, deco_gap_min, pause_windows):
    cfgs = []
    for prm_name, vals in base_configs.items():
        cfgs.append(
            PRMSimulationConfig(
                prm_name=prm_name,
                start_time=start_time,
                end_time=end_time,
                arms_config=vals["arms_config"],
                cycle_times=vals["cycle_times"],
                first_arm=vals["first_arm"],
                send_gap_min=send_gap_min,
                latence_max=latence_max,
                deco_gap_min=deco_gap_min,
                pause_windows=pause_windows,
            )
        )
    return cfgs


def evaluate_scenarios(start_time, end_time, base_configs, send_gap_values, latence_values, deco_gap_values, pause_sets):
    records = []
    best = None
    best_score = float("-inf")

    for (pause_name, pause_windows), send_gap, lat, deco_gap in itertools.product(
        pause_sets, send_gap_values, latence_values, deco_gap_values
    ):
        cfgs = _build_configs(start_time, end_time, base_configs, send_gap, lat, deco_gap, pause_windows)
        df = simulate_all(cfgs)
        if df.empty:
            continue

        kpis = compute_global_kpis(df, start_time, end_time)
        score = round(_score(kpis), 2)

        record = {
            "Scenario": f"{pause_name} | send {send_gap} | lat {lat} | deco {deco_gap}",
            "Pause": pause_name,
            "Send gap": send_gap,
            "Latence max": lat,
            "Déco gap": deco_gap,
            "Production": kpis["production"],
            "Taux four global (%)": kpis["taux_four_global"],
            "Latence moy": kpis["latence_moy"],
            "Latence max observée": kpis["latence_max_obs"],
            "Score": score,
        }
        records.append(record)

        if score > best_score:
            best_score = score
            best = record

    df_records = (
        pd.DataFrame(records).sort_values("Score", ascending=False).reset_index(drop=True)
        if records else pd.DataFrame()
    )
    return df_records, best


def evaluate_overtime(start_time, end_time, base_configs, send_gap_min, latence_max, deco_gap_min, pause_windows, overtime_values):
    rows = []
    best_extra = None
    last_piece = None
    prev_prod = None

    for extra in overtime_values:
        cfgs = _build_configs(start_time, end_time + extra, base_configs, send_gap_min, latence_max, deco_gap_min, pause_windows)
        df = simulate_all(cfgs)
        prod = 0 if df.empty else len(df)

        rows.append({
            "Overtime (min)": extra,
            "Production": prod,
        })

        if prev_prod is not None and best_extra is None and prod > prev_prod:
            best_extra = extra
            if not df.empty:
                last_piece = format_simulation_df(df.tail(1))

        prev_prod = prod

    return pd.DataFrame(rows), best_extra, last_piece


def evaluate_mixes(start_time, end_time, base_configs, product_options, send_gap_min, latence_max, deco_gap_min, pause_windows):
    motifs = {
        "Actuel": None,
        "Alterné": [0, 1, 0, 1],
        "Blocs": [0, 0, 1, 1],
    }

    rows = []
    for motif_name, motif in motifs.items():
        cfgs_dict = {}

        for prm_name, base in base_configs.items():
            arms = base["arms_config"].copy()
            opts = product_options[prm_name]

            if motif is not None and len(opts) >= 2:
                for i, arm in enumerate([1, 2, 3, 4]):
                    arms[arm] = opts[motif[i] % len(opts)]

            cfgs_dict[prm_name] = {
                **base,
                "arms_config": arms,
            }

        cfgs = _build_configs(start_time, end_time, cfgs_dict, send_gap_min, latence_max, deco_gap_min, pause_windows)
        df = simulate_all(cfgs)
        if df.empty:
            continue

        kpis = compute_global_kpis(df, start_time, end_time)
        rows.append({
            "Configuration": motif_name,
            "Production": kpis["production"],
            "Taux four global (%)": kpis["taux_four_global"],
            "Latence moy": kpis["latence_moy"],
        })

    return (
        pd.DataFrame(rows).sort_values(["Production", "Taux four global (%)"], ascending=False).reset_index(drop=True)
        if rows else pd.DataFrame()
    )
