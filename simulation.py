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
    Version 'calcul historique' :
    - on ne rejette plus les scénarios comme infaisables,
    - on décale l'entrée au four de la pièce courante si la latence projetée dépasse la limite,
    - l'objectif est de calculer une production cohérente en fonction de la latence proposée.
    """
    pause_windows = sorted(config.pause_windows or [])
    arm_order = normalize_arm_order(config.first_arm)

    # disponibilité de chaque bras après son cycle complet
    arm_available = {arm: config.start_time for arm in config.arms_config}

    # disponibilité du poste déco/coffrage (1 ressource manuelle)
    deco_available = config.start_time

    # prochaine fenêtre d'envoi au four
    next_send_time = config.start_time

    # disponibilité de 2 zones de refroidissement simplifiées comme 2 capacités parallèles
    cool_slot_available = {
        "Z1": config.start_time,
        "Z2": config.start_time,
    }

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

        # départ four : le plus tôt possible selon cadence mini et disponibilité bras
        start_four = max(next_send_time, arm_available[arm])

        # logique historique : si la latence dépasse la limite, on décale l'amont
        while True:
            end_four = start_four + heat

            # zone de refroidissement disponible la plus tôt
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

            # on décale l'entrée au four de l'excès constaté
            start_four += (latence - config.latence_max)

        end_deco = start_deco + deco

        # borne fin de journée = fin du dernier décoffrage
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

