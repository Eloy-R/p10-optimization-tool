from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd


def format_time(minutes: int) -> str:
    return f"{int(minutes//60):02d}:{int(minutes%60):02d}"


def to_datetime(minutes: int) -> datetime:
    return datetime(2024, 1, 1, int(minutes//60), int(minutes%60))


def normalize_arm_order(first_arm: int) -> List[int]:
    arms = [1, 2, 3, 4]
    idx = arms.index(first_arm)
    return arms[idx:] + arms[:idx]


def apply_pause_windows(start_op: int, duration: int, pause_windows: List[Tuple[int, int]]) -> Tuple[int, Optional[str]]:
    reason = None
    changed = True
    while changed:
        changed = False
        end_temp = start_op + duration
        for p_start, p_end in sorted(pause_windows):
            if p_start <= start_op < p_end or (start_op < p_start < end_temp):
                start_op = p_end
                reason = "Pause"
                changed = True
                break
    return start_op, reason


@dataclass
class PRMSimulationConfig:
    prm_name: str
    start_time: int
    end_time: int
    arms_config: Dict[int, str]
    cycle_times: Dict[str, Dict[str, int]]
    first_arm: int = 4
    send_gap_min: int = 20
    latence_max: int = 10
    deco_gap_min: int = 5
    pause_windows: Optional[List[Tuple[int, int]]] = None
    extra_first_cycles: int = 2
    extra_first_cycles_count: int = 4


def simulate_prm(config: PRMSimulationConfig) -> pd.DataFrame:
    """
    Simulation évènementielle pragmatique par PRM.

    Hypothèses de cette version :
    - 2 zones de refroidissement dynamiques (Z1, Z2)
    - priorité à Z2 si libre à la sortie four
    - si Z2 occupée : insertion en Z1 puis bascule vers Z2 quand possible
    - décoffrage/coffrage manuel, une seule ressource par PRM
    - la latence max est appliquée par décalage préventif de l'entrée four
      sur une estimation prudente basée sur la disponibilité déco et le refroidissement requis
    """
    pause_windows = sorted(config.pause_windows or [])
    arm_order = normalize_arm_order(config.first_arm)

    deco_available = config.start_time
    next_send_time = config.start_time
    arm_available = {arm: config.start_time for arm in config.arms_config}

    zones = {"Z1": None, "Z2": None}
    zone_last_update = {"Z1": config.start_time, "Z2": config.start_time}
    ready_for_deco: List[dict] = []
    results = []

    def update_zone_cooling(zone_name: str, now: int):
        occ = zones[zone_name]
        if occ is None:
            zone_last_update[zone_name] = now
            return

        elapsed = max(0, now - zone_last_update[zone_name])
        if elapsed <= 0:
            return

        occ["cool_done"] += elapsed
        if zone_name == "Z1":
            occ["time_z1"] += elapsed
        else:
            occ["time_z2"] += elapsed

        zone_last_update[zone_name] = now

        if occ["cool_done"] >= occ["cool_required"] and occ["cool_finish"] is None:
            over = occ["cool_done"] - occ["cool_required"]
            occ["cool_finish"] = now - over

    def update_all_cooling(now: int):
        update_zone_cooling("Z1", now)
        update_zone_cooling("Z2", now)

    def move_finished_to_ready(now: int):
        moved = True
        while moved:
            moved = False
            for zone_name in ["Z2", "Z1"]:
                occ = zones[zone_name]
                if occ is not None and occ["cool_finish"] is not None:
                    ready_for_deco.append(occ)
                    zones[zone_name] = None
                    zone_last_update[zone_name] = now
                    moved = True
                    break

    def rebalance_zones(now: int):
        update_all_cooling(now)
        move_finished_to_ready(now)

        # Si Z2 est libre et Z1 occupée, on pousse de Z1 vers Z2
        if zones["Z2"] is None and zones["Z1"] is not None:
            occ = zones["Z1"]
            zones["Z1"] = None
            zone_last_update["Z1"] = now
            if occ["path"] == "":
                occ["path"] = "Z1→Z2"
            zones["Z2"] = occ
            zone_last_update["Z2"] = now

    def predicted_deco_start(cool_finish: int, deco_duration: int, manual_available: int) -> Tuple[int, str]:
        start_deco = max(cool_finish, manual_available)
        start_deco, pause_reason = apply_pause_windows(start_deco, deco_duration, pause_windows)
        return start_deco, pause_reason or ""

    def try_process_ready(until_time: int):
        nonlocal deco_available

        update_all_cooling(until_time)
        rebalance_zones(until_time)

        while ready_for_deco:
            # priorité à la pièce refroidie le plus tôt
            ready_for_deco.sort(key=lambda x: (x["cool_finish"], x["arm"]))
            piece = ready_for_deco[0]

            start_deco, pause_reason = predicted_deco_start(piece["cool_finish"], piece["deco"], deco_available)
            if start_deco > until_time:
                break

            end_deco = start_deco + piece["deco"]
            latence = start_deco - piece["cool_finish"]

            reason = piece.get("reason", "")
            if pause_reason:
                reason = pause_reason if not reason else f"{reason}; Pause"
            if latence > config.latence_max and "Latence" not in reason:
                reason = "Latence" if not reason else f"{reason}; Latence"

            results.append({
                "PRM": config.prm_name,
                "Bras": piece["arm"],
                "Produit": piece["product"],
                "Début Four (min)": piece["start_four"],
                "Fin Four (min)": piece["end_four"],
                "Début Refroidissement (min)": piece["start_cool"],
                "Fin Refroidissement (min)": piece["cool_finish"],
                "Début Déco (min)": start_deco,
                "Fin Déco (min)": end_deco,
                "Latence (min)": latence,
                "Attente avant four (min)": piece["attente_avant_four"],
                "Attente avant déco (min)": start_deco - piece["cool_finish"],
                "Temps zone 1 (min)": piece["time_z1"],
                "Temps zone 2 (min)": piece["time_z2"],
                "Chemin refroidissement": piece["path"] or ("Z2 seul" if piece["time_z1"] == 0 else "Z1→Z2"),
                "Motif décalage": reason,
                "Cycle": piece["cycle"],
            })

            deco_available = end_deco + config.deco_gap_min
            arm_available[piece["arm"]] = end_deco
            ready_for_deco.pop(0)

    def insert_into_cooling(piece: dict, now: int) -> int:
        rebalance_zones(now)

        if zones["Z2"] is None:
            piece["path"] = "Z2 seul"
            zones["Z2"] = piece
            zone_last_update["Z2"] = now
            return now

        if zones["Z1"] is None:
            piece["path"] = "Z1→Z2"
            zones["Z1"] = piece
            zone_last_update["Z1"] = now
            return now

        # si les deux zones sont occupées, on attend la première libération réelle
        future_times = []
        for zn in ["Z1", "Z2"]:
            occ = zones[zn]
            remaining = max(0, occ["cool_required"] - occ["cool_done"])
            future_times.append(now + remaining)

        future = min(future_times)
        rebalance_zones(future)

        if zones["Z2"] is None:
            piece["path"] = "Z2 seul"
            zones["Z2"] = piece
            zone_last_update["Z2"] = future
            return future

        if zones["Z1"] is None:
            piece["path"] = "Z1→Z2"
            zones["Z1"] = piece
            zone_last_update["Z1"] = future
            return future

        raise RuntimeError(f"Insertion impossible dans les zones de refroidissement pour {config.prm_name}")

    cycle = 0

    while True:
        arm = arm_order[cycle % len(arm_order)]
        product = config.arms_config[arm]
        t = config.cycle_times[product]

        heat = t["heat"] + (config.extra_first_cycles if cycle < config.extra_first_cycles_count else 0)
        cool_required = t["cool"]
        deco = t["deco"]

        try_process_ready(next_send_time)

        raw_start_four = max(next_send_time, arm_available[arm])

        # estimation prudente pour limiter la latence en amont
        est_end_four = raw_start_four + heat
        est_cool_finish = est_end_four + cool_required
        est_start_deco, pause_reason = predicted_deco_start(est_cool_finish, deco, deco_available)
        est_latence = est_start_deco - est_cool_finish
        shift = max(0, est_latence - config.latence_max)

        start_four = raw_start_four + shift
        end_four = start_four + heat

        if end_four > config.end_time:
            break

        try_process_ready(end_four)

        piece = {
            "arm": arm,
            "product": product,
            "cycle": cycle + 1,
            "start_four": start_four,
            "end_four": end_four,
            "start_cool": end_four,
            "cool_required": cool_required,
            "cool_done": 0,
            "cool_finish": None,
            "deco": deco,
            "time_z1": 0,
            "time_z2": 0,
            "path": "",
            "attente_avant_four": max(0, start_four - arm_available[arm]),
            "reason": "Latence" if shift > 0 else ("Pause" if pause_reason else ""),
        }

        insert_time = insert_into_cooling(piece, end_four)

        if insert_time > end_four:
            if piece["reason"]:
                piece["reason"] += "; Tampon"
            else:
                piece["reason"] = "Tampon"

        next_send_time = start_four + config.send_gap_min
        cycle += 1

        if start_four >= config.end_time:
            break

    try_process_ready(config.end_time)
    return pd.DataFrame(results)


def simulate_all(configs: List[PRMSimulationConfig]) -> pd.DataFrame:
    frames = [simulate_prm(cfg) for cfg in configs]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def format_simulation_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    out = df.copy()
    pairs = [
        ("Début Four (min)", "Début Four"),
        ("Fin Four (min)", "Fin Four"),
        ("Début Refroidissement (min)", "Début Refroidissement"),
        ("Fin Refroidissement (min)", "Fin Refroidissement"),
        ("Début Déco (min)", "Début Déco"),
        ("Fin Déco (min)", "Fin Déco"),
    ]

    for c_in, c_out in pairs:
        out[c_out] = out[c_in].apply(format_time)

    ordered = [
        "PRM", "Bras", "Produit",
        "Début Four", "Fin Four",
        "Début Refroidissement", "Fin Refroidissement",
        "Début Déco", "Fin Déco",
        "Latence (min)",
        "Attente avant four (min)",
        "Attente avant déco (min)",
        "Temps zone 1 (min)",
        "Temps zone 2 (min)",
        "Chemin refroidissement",
        "Motif décalage",
        "Cycle",
    ]
    return out[ordered]


def build_gantt_source(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    tasks = []
    for _, row in df.iterrows():
        label = f"{row['PRM']} - B{row['Bras']} - {row['Produit']}"

        tasks.extend([
            {
                "Task": label,
                "Start": to_datetime(row["Début Four (min)"]),
                "Finish": to_datetime(row["Fin Four (min)"]),
                "Type": "Four",
            },
            {
                "Task": label,
                "Start": to_datetime(row["Début Refroidissement (min)"]),
                "Finish": to_datetime(row["Fin Refroidissement (min)"]),
                "Type": "Refroidissement",
            },
            {
                "Task": label,
                "Start": to_datetime(row["Début Déco (min)"]),
                "Finish": to_datetime(row["Fin Déco (min)"]),
                "Type": "Déco",
            },
        ])

        if row["Latence (min)"] > 0:
            tasks.append({
                "Task": label,
                "Start": to_datetime(row["Fin Refroidissement (min)"]),
                "Finish": to_datetime(row["Début Déco (min)"]),
                "Type": "LATENCE",
            })

    return pd.DataFrame(tasks)


def compute_global_kpis(df: pd.DataFrame, start_time: int, end_time: int) -> dict:
    if df.empty:
        return {
            "production": 0,
            "taux_four_global": 0.0,
            "latence_moy": 0.0,
            "latence_max_obs": 0.0,
            "par_produit": {},
            "par_prm": {},
        }

    total_available = max(1, end_time - start_time)
    total_four = (df["Fin Four (min)"] - df["Début Four (min)"]).sum()
    taux_four_global = (total_four / (2 * total_available)) * 100  # 2 fours

    return {
        "production": int(len(df)),
        "taux_four_global": round(taux_four_global, 1),
        "latence_moy": round(df["Latence (min)"].mean(), 2),
        "latence_max_obs": round(df["Latence (min)"].max(), 2),
        "par_produit": df["Produit"].value_counts().to_dict(),
        "par_prm": df["PRM"].value_counts().to_dict(),
    }
