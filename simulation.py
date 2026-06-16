from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd


class ScenarioInfeasibleError(Exception):
    """
    Présente uniquement pour compatibilité avec app.py / optimizer.py.
    La simulation actuelle ne lève pas cette erreur métier.
    """
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
    """
    Reporte le démarrage d'une opération manuelle si elle démarre pendant une pause
    ou si elle chevauche une pause.
    """
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
    deco_gap_min: int = 5
    pause_windows: Optional[List[Tuple[int, int]]] = None
    extra_first_cycles: int = 2
    extra_first_cycles_count: int = 4


def simulate_prm(config: PRMSimulationConfig) -> pd.DataFrame:
    """
    Logique de calcul :
    - on ne rejette plus les scénarios comme infaisables
    - on décale l'entrée au four de la pièce courante si la latence projetée dépasse la limite
    - l'objectif est de calculer une production cohérente en fonction de la latence proposée
    """
    pause_windows = sorted(config.pause_windows or [])
    arm_order = normalize_arm_order(config.first_arm)

    arm_available = {arm: config.start_time for arm in config.arms_config}
    deco_available = config.start_time
    next_send_time = config.start_time
    cool_slot_available = {"Z1": config.start_time, "Z2": config.start_time}

    results = []
    cycle_idx = 0

    while True:
        arm = arm_order[cycle_idx % len(arm_order)]
        product = config.arms_config[arm]

        if product not in config.cycle_times:
            raise ValueError(f"Produit '{product}' introuvable pour {config.prm_name}")

        times = config.cycle_times[product]
        heat = times["heat"]
        cool = times["cool"]
        deco = times["deco"]

        if cycle_idx < config.extra_first_cycles_count:
            heat += config.extra_first_cycles

        start_four = max(next_send_time, arm_available[arm])

        while True:
            end_four = start_four + heat

            chosen_zone = min(
                cool_slot_available,
                key=lambda z: max(cool_slot_available[z], end_four)
            )
            start_cool = max(end_four, cool_slot_available[chosen_zone])
            cool_finish = start_cool + cool

            start_deco = max(cool_finish, deco_available)
            start_deco, pause_reason = apply_pause_windows(start_deco, deco, pause_windows)

            latence = start_deco - cool_finish

            if latence <= config.latence_max:
                break

            # logique historique : on décale l'entrée au four de l'excès constaté
            start_four += (latence - config.latence_max)

        end_deco = start_deco + deco

        if end_deco > config.end_time:
            break

        results.append(
            {
                "PRM": config.prm_name,
                "Bras": arm,
                "Produit": product,
                "Début Four (min)": start_four,
                "Fin Four (min)": end_four,
                "Début Refroidissement (min)": start_cool,
                "Fin Refroidissement (min)": cool_finish,
                "Début Déco (min)": start_deco,
                "Fin Déco (min)": end_deco,
                "Latence (min)": latence,
                "Attente avant four (min)": max(0, start_four - arm_available[arm]),
                "Attente avant déco (min)": latence,
                "Temps zone 1 (min)": cool if chosen_zone == "Z1" else 0,
                "Temps zone 2 (min)": cool if chosen_zone == "Z2" else 0,
                "Chemin refroidissement": "Z1" if chosen_zone == "Z1" else "Z2 seul",
                "Motif décalage": pause_reason,
                "Cycle": cycle_idx + 1,
            }
        )

        cool_slot_available[chosen_zone] = cool_finish
        deco_available = end_deco + config.deco_gap_min
        arm_available[arm] = end_deco
        next_send_time = start_four + config.send_gap_min
        cycle_idx += 1

    return pd.DataFrame(results)


def format_simulation_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    out = df.copy()
    mapping = [
        ("Début Four (min)", "Début Four"),
        ("Fin Four (min)", "Fin Four"),
        ("Début Refroidissement (min)", "Début Refroidissement"),
        ("Fin Refroidissement (min)", "Fin Refroidissement"),
        ("Début Déco (min)", "Début Déco"),
        ("Fin Déco (min)", "Fin Déco"),
    ]
    for c_in, c_out in mapping:
        out[c_out] = out[c_in].apply(format_time)

    ordered = [
        "PRM", "Bras", "Produit", "Début Four", "Fin Four",
        "Début Refroidissement", "Fin Refroidissement", "Début Déco", "Fin Déco",
        "Latence (min)", "Attente avant four (min)", "Attente avant déco (min)",
        "Temps zone 1 (min)", "Temps zone 2 (min)", "Chemin refroidissement",
        "Motif décalage", "Cycle",
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


def compute_prm_kpis(df: pd.DataFrame, start_time: int, end_time: int) -> dict:
    if df.empty:
        return {
            "production": 0,
            "taux_four": 0.0,
            "latence_moy": 0.0,
            "latence_max_obs": 0.0,
            "par_produit": {},
        }

    total_available = max(1, end_time - start_time)
    total_four = (df["Fin Four (min)"] - df["Début Four (min)"]).sum()
    taux_four = (total_four / total_available) * 100

    return {
        "production": int(len(df)),
        "taux_four": round(taux_four, 1),
        "latence_moy": round(df["Latence (min)"].mean(), 2),
        "latence_max_obs": round(df["Latence (min)"].max(), 2),
        "par_produit": df["Produit"].value_counts().to_dict(),
    }


def get_process_state_at_time(df: pd.DataFrame, current_minute: int) -> dict:
    """
    Retourne l'état du process à un instant donné.
    """
    state = {
        "Four": [],
        "Refroid. Z1": [],
        "Refroid. Z2": [],
        "Avant déco": [],
        "Déco": [],
    }

    if df.empty:
        return state

    for _, row in df.iterrows():
        label = f"B{int(row['Bras'])} - {row['Produit']}"

        start_four = row["Début Four (min)"]
        end_four = row["Fin Four (min)"]
        start_ref = row["Début Refroidissement (min)"]
        end_ref = row["Fin Refroidissement (min)"]
        start_deco = row["Début Déco (min)"]
        end_deco = row["Fin Déco (min)"]

        if start_four <= current_minute < end_four:
            state["Four"].append(label)

        elif start_ref <= current_minute < end_ref:
            tz1 = row.get("Temps zone 1 (min)", 0)
            tz2 = row.get("Temps zone 2 (min)", 0)

            if tz1 > 0 and tz2 == 0:
                state["Refroid. Z1"].append(label)
            elif tz2 > 0 and tz1 == 0:
                state["Refroid. Z2"].append(label)
            elif tz1 > 0 and tz2 > 0:
                total = tz1 + tz2
                elapsed = current_minute - start_ref
                threshold = tz1 / total if total > 0 else 1
                progression = elapsed / max(1, (end_ref - start_ref))
                if progression <= threshold:
                    state["Refroid. Z1"].append(label)
                else:
                    state["Refroid. Z2"].append(label)
            else:
                state["Refroid. Z1"].append(label)

        elif end_ref <= current_minute < start_deco:
            state["Avant déco"].append(label)

        elif start_deco <= current_minute < end_deco:
            state["Déco"].append(label)

    return state
