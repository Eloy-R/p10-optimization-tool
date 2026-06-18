from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd


class ScenarioInfeasibleError(Exception):
    """Levée lorsqu'un scénario ne peut pas respecter les contraintes process."""

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


def apply_pause_windows(
    start_op: int,
    duration: int,
    pause_windows: List[Tuple[int, int]],
) -> Tuple[int, str]:
    """
    Si l'opération démarre pendant une pause ou la chevauche,
    le démarrage est décalé à la fin de la pause.
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


def _build_plan_for_start(
    start_four: int,
    heat: int,
    cool: int,
    deco: int,
    cooling_zone_available: Dict[str, int],
    predeco_available: int,
    deco_available: int,
    pause_windows: List[Tuple[int, int]],
) -> Optional[dict]:
    """
    Construit le meilleur plan possible pour un départ four donné.
    On compare Z1 et Z2 et on garde le plan de latence minimale.
    """
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

        plan = {
            "zone": zone_name,
            "start_four": start_four,
            "end_four": end_four,
            "start_zone": start_zone,
            "cool_finish": cool_finish,
            "enter_predeco": enter_predeco,
            "start_deco": start_deco,
            "end_deco": end_deco,
            "latence": latence,
            "pause_reason": pause_reason,
        }

        if best_plan is None:
            best_plan = plan
        else:
            # Logique préventive / qualité :
            # 1) latence minimale possible
            # 2) fin de déco la plus tôt possible
            # 3) départ four le plus tôt possible
            if (plan["latence"], plan["end_deco"], plan["start_four"]) < (
                best_plan["latence"],
                best_plan["end_deco"],
                best_plan["start_four"],
            ):
                best_plan = plan

    return best_plan


def _find_best_feasible_plan(
    earliest_start_four: int,
    latest_end_time: int,
    heat: int,
    cool: int,
    deco: int,
    cooling_zone_available: Dict[str, int],
    predeco_available: int,
    deco_available: int,
    pause_windows: List[Tuple[int, int]],
    latence_max: int,
) -> Optional[dict]:
    """
    Recherche préventivement le meilleur départ four :
    - latence la plus basse possible
    - sous la contrainte latence <= latence_max
    - sans dépasser la fin de journée

    On scanne les départs minute par minute depuis le plus tôt possible.
    C'est plus robuste et plus fidèle métier qu'un simple 'premier scénario acceptable'.
    """
    latest_start_four = latest_end_time - heat
    if earliest_start_four > latest_start_four:
        return None

    best_feasible = None

    for start_four in range(earliest_start_four, latest_start_four + 1):
        plan = _build_plan_for_start(
            start_four=start_four,
            heat=heat,
            cool=cool,
            deco=deco,
            cooling_zone_available=cooling_zone_available,
            predeco_available=predeco_available,
            deco_available=deco_available,
            pause_windows=pause_windows,
        )

        if plan is None:
            continue

        if plan["end_deco"] > latest_end_time:
            continue

        if plan["latence"] > latence_max:
            continue

        if best_feasible is None:
            best_feasible = plan
        else:
            if (plan["latence"], plan["end_deco"], plan["start_four"]) < (
                best_feasible["latence"],
                best_feasible["end_deco"],
                best_feasible["start_four"],
            ):
                best_feasible = plan

        # optimisation légère : si on a trouvé une latence nulle, on ne fera pas mieux
        if best_feasible is not None and best_feasible["latence"] == 0:
            break

    return best_feasible


def simulate_prm(config: PRMSimulationConfig) -> pd.DataFrame:
    """
    Hypothèses de capacité :
    - Four : capacité 1
    - Refroid. Z1 : capacité 1
    - Refroid. Z2 : capacité 1
    - Avant déco : capacité 1
    - Déco : capacité 1

    Logique préventive sur la latence :
    - la latence maximale est une CONTRAINTE DURE ;
    - avant d'envoyer une pièce au four, on cherche le meilleur départ possible ;
    - la simulation choisit la latence la plus basse possible sous la limite ;
    - si aucune solution ne respecte la contrainte dans la journée, on arrête la production ;
    - aucune pièce hors limite n'est jamais acceptée.
    """
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

        plan = _find_best_feasible_plan(
            earliest_start_four=earliest_start_four,
            latest_end_time=config.end_time,
            heat=heat,
            cool=cool,
            deco=deco,
            cooling_zone_available=cooling_zone_available,
            predeco_available=predeco_available,
            deco_available=deco_available,
            pause_windows=pause_windows,
            latence_max=config.latence_max,
        )

        # Si aucune solution n'existe sous la limite de latence, on s'arrête.
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

        # Double sécurité : on n'enregistre jamais une pièce invalide.
        if latence > config.latence_max:
            raise ScenarioInfeasibleError(
                f"Latence observée {latence} > latence max autorisée {config.latence_max}",
                details={
                    "produit": product,
                    "bras": arm,
                    "cycle": cycle_idx + 1,
                    "latence_obs": latence,
                    "latence_max": config.latence_max,
                },
            )

        if end_deco > config.end_time:
            break

        zone_occupation = enter_predeco - start_zone
        predeco_occupation = start_deco - enter_predeco

        results.append(
            {
                "PRM": config.prm_name,
                "Bras": arm,
                "Produit": product,
                "Début Four (min)": start_four,
                "Fin Four (min)": end_four,
                "Début Refroidissement (min)": start_zone,
                "Fin Refroidissement (min)": cool_finish,
                "Fin Occupation Refroidissement (min)": enter_predeco,
                "Début Avant Déco (min)": enter_predeco,
                "Fin Avant Déco (min)": start_deco,
                "Début Déco (min)": start_deco,
                "Fin Déco (min)": end_deco,
                "Latence (min)": latence,
                "Attente avant four (min)": max(0, start_four - arm_available[arm]),
                "Attente avant déco (min)": latence,
                "Temps zone 1 (min)": zone_occupation if chosen_zone == "Z1" else 0,
                "Temps zone 2 (min)": zone_occupation if chosen_zone == "Z2" else 0,
                "Temps avant déco (min)": predeco_occupation,
                "Chemin refroidissement": chosen_zone,
                "Motif décalage": pause_reason,
                "Cycle": cycle_idx + 1,
            }
        )

        furnace_available = end_four
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
    mapping = [
        ("Début Four (min)", "Début Four"),
        ("Fin Four (min)", "Fin Four"),
        ("Début Refroidissement (min)", "Début Refroidissement"),
        ("Fin Refroidissement (min)", "Fin Refroidissement"),
        ("Début Avant Déco (min)", "Début Avant Déco"),
        ("Fin Avant Déco (min)", "Fin Avant Déco"),
        ("Début Déco (min)", "Début Déco"),
        ("Fin Déco (min)", "Fin Déco"),
    ]
    for c_in, c_out in mapping:
        if c_in in out.columns:
            out[c_out] = out[c_in].apply(format_time)

    ordered = [
        "PRM", "Bras", "Produit", "Début Four", "Fin Four",
        "Début Refroidissement", "Fin Refroidissement",
        "Début Avant Déco", "Fin Avant Déco",
        "Début Déco", "Fin Déco",
        "Latence (min)", "Attente avant four (min)", "Attente avant déco (min)",
        "Temps zone 1 (min)", "Temps zone 2 (min)", "Temps avant déco (min)",
        "Chemin refroidissement", "Motif décalage", "Cycle",
    ]
    ordered_existing = [c for c in ordered if c in out.columns]
    return out[ordered_existing]


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
                "Finish": to_datetime(row["Fin Occupation Refroidissement (min)"]),
                "Type": "Refroidissement",
            },
            {
                "Task": label,
                "Start": to_datetime(row["Début Avant Déco (min)"]),
                "Finish": to_datetime(row["Fin Avant Déco (min)"]),
                "Type": "Avant déco",
            },
            {
                "Task": label,
                "Start": to_datetime(row["Début Déco (min)"]),
                "Finish": to_datetime(row["Fin Déco (min)"]),
                "Type": "Déco",
            },
        ])
        if row["Latence (min)"] > 0:
            tasks.append(
                {
                    "Task": label,
                    "Start": to_datetime(row["Fin Refroidissement (min)"]),
                    "Finish": to_datetime(row["Début Déco (min)"]),
                    "Type": "LATENCE",
                }
            )
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
        end_ref_phys = row.get("Fin Occupation Refroidissement (min)", row["Fin Refroidissement (min)"])
        start_pre = row.get("Début Avant Déco (min)", row["Fin Refroidissement (min)"])
        end_pre = row.get("Fin Avant Déco (min)", row["Début Déco (min)"])
        start_deco = row["Début Déco (min)"]
        end_deco = row["Fin Déco (min)"]
        path = row.get("Chemin refroidissement", "Z1")

        if start_four <= current_minute < end_four:
            state["Four"].append(label)
        elif start_ref <= current_minute < end_ref_phys:
            if path == "Z2":
                state["Refroid. Z2"].append(label)
            else:
                state["Refroid. Z1"].append(label)
        elif start_pre <= current_minute < end_pre:
            state["Avant déco"].append(label)
        elif start_deco <= current_minute < end_deco:
            state["Déco"].append(label)

    return state


def validate_single_capacity_per_sector(df: pd.DataFrame) -> bool:
    if df.empty:
        return True

    events = []
    for _, row in df.iterrows():
        events.extend([
            (row["Début Four (min)"], "four", +1),
            (row["Fin Four (min)"], "four", -1),
            (row["Début Refroidissement (min)"], f"ref_{row['Chemin refroidissement']}", +1),
            (row["Fin Occupation Refroidissement (min)"], f"ref_{row['Chemin refroidissement']}", -1),
            (row["Début Avant Déco (min)"], "pre", +1),
            (row["Fin Avant Déco (min)"], "pre", -1),
            (row["Début Déco (min)"], "deco", +1),
            (row["Fin Déco (min)"], "deco", -1),
        ])

    counts = {"four": 0, "ref_Z1": 0, "ref_Z2": 0, "pre": 0, "deco": 0}
    for _, sector, delta in sorted(events, key=lambda x: (x[0], x[2])):
        counts[sector] += delta
        if counts[sector] > 1:
            return False
    return True
