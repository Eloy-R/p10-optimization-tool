from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd


class ScenarioInfeasibleError(Exception):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.details = details or {}


def format_time(minutes: int) -> str:
    return f"{int(minutes // 60):02d}:{int(minutes % 60):02d}"


def to_datetime(minutes: int) -> datetime:
    return datetime(2024, 1, 1, int(minutes // 60), int(minutes % 60))


def normalize_arm_order(first_arm: int) -> List[int]:
    arms = [1, 2, 3, 4]
    idx = arms.index(first_arm)
    return arms[idx:] + arms[:idx]


def apply_pause_windows(start_op: int, duration: int, pause_windows: List[Tuple[int, int]]) -> Tuple[int, str]:
    reason = ""
    changed = True
    while changed:
        changed = False
        end_temp = start_op + duration
        for p_start, p_end in sorted(pause_windows):
            if p_start <= start_op < p_end:
                start_op = p_end
                reason = "Pause"
                changed = True
                break
            if start_op < p_start and end_temp > p_start:
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
    send_gap_min: int = 1
    latence_max: int = 20
    latence_cible: int = 0
    deco_gap_min: int = 5
    four_gap_min: int = 1
    pause_windows: Optional[List[Tuple[int, int]]] = None
    extra_first_cycles: int = 2
    extra_first_cycles_count: int = 4
    arbitration_weights: Optional[Dict[str, float]] = None


def _build_plan_for_start(start_four: int, heat: int, cool: int, deco: int, cooling_zone_available: Dict[str, int], predeco_available: int, deco_available: int, pause_windows: List[Tuple[int, int]]) -> Optional[dict]:
    end_four = start_four + heat
    best_plan = None
    for zone_name in ["Z1", "Z2"]:
        start_zone = max(end_four, cooling_zone_available[zone_name])
        cool_finish = start_zone + cool
        enter_predeco = max(cool_finish, predeco_available)
        raw_start_deco = max(enter_predeco, deco_available)
        start_deco, pause_reason = apply_pause_windows(raw_start_deco, deco, pause_windows)
        end_deco = start_deco + deco
        latence = start_deco - cool_finish
        candidate = {"zone": zone_name, "start_four": start_four, "end_four": end_four, "start_zone": start_zone, "cool_finish": cool_finish, "enter_predeco": enter_predeco, "start_deco": start_deco, "end_deco": end_deco, "latence": latence, "pause_reason": pause_reason}
        if best_plan is None or (candidate["latence"], candidate["end_deco"], candidate["start_four"]) < (best_plan["latence"], best_plan["end_deco"], best_plan["start_four"]):
            best_plan = candidate
    return best_plan


def _plan_objective(plan: dict, earliest_start_four: int, latence_cible: int, weights: Dict[str, float]) -> float:
    target_over = max(0, plan["latence"] - latence_cible)
    lead_delay = max(0, plan["start_four"] - earliest_start_four)
    cycle_span = max(0, plan["end_deco"] - earliest_start_four)
    return weights.get("target_penalty", 2.0) * target_over + weights.get("latency", 1.0) * plan["latence"] + weights.get("start_delay", 1.0) * lead_delay + weights.get("cycle_span", 0.2) * cycle_span


def _find_best_feasible_plan(earliest_start_four: int, latest_end_time: int, heat: int, cool: int, deco: int, cooling_zone_available: Dict[str, int], predeco_available: int, deco_available: int, pause_windows: List[Tuple[int, int]], latence_max: int, latence_cible: int, arbitration_weights: Optional[Dict[str, float]]) -> Optional[dict]:
    latest_start_four = latest_end_time - heat
    if earliest_start_four > latest_start_four:
        return None
    weights = arbitration_weights or {"target_penalty": 2.0, "latency": 1.0, "start_delay": 1.0, "cycle_span": 0.2}
    best_plan = None
    best_score = None
    for start_four in range(earliest_start_four, latest_start_four + 1):
        plan = _build_plan_for_start(start_four, heat, cool, deco, cooling_zone_available, predeco_available, deco_available, pause_windows)
        if plan is None or plan["end_deco"] > latest_end_time or plan["latence"] > latence_max:
            continue
        score = _plan_objective(plan, earliest_start_four, latence_cible, weights)
        tie_break = (plan["start_four"], plan["latence"], plan["end_deco"])
        candidate = (score, tie_break)
        if best_score is None or candidate < best_score:
            best_score = candidate
            best_plan = plan
    return best_plan


def simulate_prm(config: PRMSimulationConfig) -> pd.DataFrame:
    pause_windows = sorted(config.pause_windows or [])
    arm_order = normalize_arm_order(config.first_arm)
    arm_available = {arm: config.start_time for arm in config.arms_config}
    furnace_available = config.start_time
    next_send_time = config.start_time
    cooling_zone_available = {"Z1": config.start_time, "Z2": config.start_time}
    predeco_available = config.start_time
    deco_available = config.start_time
    results = []
    cycle_idx = 0
    while True:
        arm = arm_order[cycle_idx % len(arm_order)]
        product = config.arms_config[arm]
        if product not in config.cycle_times:
            raise ValueError(f"Produit '{product}' introuvable pour {config.prm_name}")
        times = config.cycle_times[product]
        heat = int(times["heat"])
        cool = int(times["cool"])
        deco = int(times["deco"])
        if cycle_idx < config.extra_first_cycles_count:
            heat += config.extra_first_cycles
        earliest_start_four = max(next_send_time, arm_available[arm], furnace_available)
        plan = _find_best_feasible_plan(earliest_start_four, config.end_time, heat, cool, deco, cooling_zone_available, predeco_available, deco_available, pause_windows, config.latence_max, config.latence_cible, config.arbitration_weights)
        if plan is None:
            break
        start_four = plan["start_four"]
        end_four = plan["end_four"]
        chosen_zone = plan["zone"]
        start_zone = plan["start_zone"]
        cool_finish = plan["cool_finish"]
        enter_predeco = plan["enter_predeco"]
        start_deco = plan["start_deco"]
        end_deco = plan["end_deco"]
        latence = plan["latence"]
        pause_reason = plan["pause_reason"]
        if latence > config.latence_max:
            raise ScenarioInfeasibleError(f"Latence observée {latence} > latence max autorisée {config.latence_max}")
        if end_deco > config.end_time:
            break
        zone_occupation = enter_predeco - start_zone
        predeco_occupation = start_deco - enter_predeco
        results.append({"PRM": config.prm_name, "Bras": arm, "Produit": product, "Début Four (min)": start_four, "Fin Four (min)": end_four, "Début Refroidissement (min)": start_zone, "Fin Refroidissement (min)": cool_finish, "Fin Occupation Refroidissement (min)": enter_predeco, "Début Avant Déco (min)": enter_predeco, "Fin Avant Déco (min)": start_deco, "Début Déco (min)": start_deco, "Fin Déco (min)": end_deco, "Latence (min)": latence, "Attente avant four (min)": max(0, start_four - arm_available[arm]), "Attente avant déco (min)": latence, "Temps zone 1 (min)": zone_occupation if chosen_zone == "Z1" else 0, "Temps zone 2 (min)": zone_occupation if chosen_zone == "Z2" else 0, "Temps avant déco (min)": predeco_occupation, "Chemin refroidissement": chosen_zone, "Motif décalage": pause_reason, "Cycle": cycle_idx + 1})
        furnace_available = end_four + config.four_gap_min
        cooling_zone_available[chosen_zone] = enter_predeco
        predeco_available = start_deco
        deco_available = end_deco + config.deco_gap_min
        arm_available[arm] = end_deco
        next_send_time = start_four + config.send_gap_min
        cycle_idx += 1
    return pd.DataFrame(results)


def format_simulation_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    mapping = [("Début Four (min)", "Début Four"), ("Fin Four (min)", "Fin Four"), ("Début Refroidissement (min)", "Début Refroidissement"), ("Fin Refroidissement (min)", "Fin Refroidissement"), ("Début Avant Déco (min)", "Début Avant Déco"), ("Fin Avant Déco (min)", "Fin Avant Déco"), ("Début Déco (min)", "Début Déco"), ("Fin Déco (min)", "Fin Déco")]
    for c_in, c_out in mapping:
        if c_in in out.columns:
            out[c_out] = out[c_in].apply(format_time)
    ordered = ["PRM", "Bras", "Produit", "Début Four", "Fin Four", "Début Refroidissement", "Fin Refroidissement", "Début Avant Déco", "Fin Avant Déco", "Début Déco", "Fin Déco", "Latence (min)", "Attente avant four (min)", "Attente avant déco (min)", "Temps zone 1 (min)", "Temps zone 2 (min)", "Temps avant déco (min)", "Chemin refroidissement", "Motif décalage", "Cycle"]
    return out[[c for c in ordered if c in out.columns]]


def build_gantt_source(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    tasks = []
    for _, row in df.iterrows():
        label = f"{row['PRM']} - B{row['Bras']} - {row['Produit']}"
        tasks.extend([
            {"Task": label, "Start": to_datetime(row["Début Four (min)"]), "Finish": to_datetime(row["Fin Four (min)"]), "Type": "Four"},
            {"Task": label, "Start": to_datetime(row["Début Refroidissement (min)"]), "Finish": to_datetime(row["Fin Occupation Refroidissement (min)"]), "Type": "Refroidissement"},
            {"Task": label, "Start": to_datetime(row["Début Avant Déco (min)"]), "Finish": to_datetime(row["Fin Avant Déco (min)"]), "Type": "Avant déco"},
            {"Task": label, "Start": to_datetime(row["Début Déco (min)"]), "Finish": to_datetime(row["Fin Déco (min)"]), "Type": "Déco"},
        ])
        if row["Latence (min)"] > 0:
            tasks.append({"Task": label, "Start": to_datetime(row["Fin Refroidissement (min)"]), "Finish": to_datetime(row["Début Déco (min)"]), "Type": "LATENCE"})
    return pd.DataFrame(tasks)


def compute_prm_kpis(df: pd.DataFrame, start_time: int, end_time: int) -> dict:
    if df.empty:
        return {"production": 0, "taux_four": 0.0, "latence_moy": 0.0, "latence_max_obs": 0.0, "par_produit": {}}
    total_available = max(1, end_time - start_time)
    total_four = (df["Fin Four (min)"] - df["Début Four (min)"]).sum()
    taux_four = (total_four / total_available) * 100
    return {"production": int(len(df)), "taux_four": round(taux_four, 1), "latence_moy": round(df["Latence (min)"].mean(), 2), "latence_max_obs": round(df["Latence (min)"].max(), 2), "par_produit": df["Produit"].value_counts().to_dict()}


def get_process_state_at_time(df: pd.DataFrame, current_minute: int) -> dict:
    state = {"Four": [], "Refroid. Z1": [], "Refroid. Z2": [], "Avant déco": [], "Déco": []}
    if df.empty:
        return state
    for _, row in df.iterrows():
        label = f"B{int(row['Bras'])} - {row['Produit']}"
        start_four = row["Début Four (min)"]
        end_four = row["Fin Four (min)"]
        start_ref = row["Début Refroidissement (min)"]
        end_ref_phys = row.get("Fin Occupation Refroidissement (min)", row["Fin Refroidissement (min)"])
        start_pre = row.get("Début Avant Déco (min)", row["Fin Refroidissement (min)"])
        end_pre = row.get("Fin Avant Déco (min)", row["Début Déco (min)"])
        start_deco = row["Début Déco (min)"]
        end_deco = row["Fin Déco (min)"]
        path = row.get("Chemin refroidissement", "Z1")
        if start_four <= current_minute < end_four:
            state["Four"].append(label)
        elif start_ref <= current_minute < end_ref_phys:
            state["Refroid. Z2" if path == "Z2" else "Refroid. Z1"].append(label)
        elif start_pre <= current_minute < end_pre:
            state["Avant déco"].append(label)
        elif start_deco <= current_minute < end_deco:
            state["Déco"].append(label)
    return state
