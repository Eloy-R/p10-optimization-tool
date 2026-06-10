from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import copy
import pandas as pd


def format_time(minutes: int) -> str:
    return f"{int(minutes // 60):02d}:{int(minutes % 60):02d}"


def to_datetime(minutes: int) -> datetime:
    return datetime(2024, 1, 1, int(minutes // 60), int(minutes % 60))


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
    latence_max: int = 20
    deco_gap_min: int = 5
    pause_windows: Optional[List[Tuple[int, int]]] = None
    extra_first_cycles: int = 2
    extra_first_cycles_count: int = 4


def _schedule_pending(
    pending: List[dict],
    deco_available: int,
    deco_gap_min: int,
    pause_windows: List[Tuple[int, int]],
):
    ordered = sorted(pending, key=lambda x: (x["cool_finish"], x["arm"], x["cycle"]))
    current = deco_available
    scheduled = []

    for p in ordered:
        start_deco = max(current, p["cool_finish"])
        start_deco, pause_reason = apply_pause_windows(start_deco, p["deco"], pause_windows)
        end_deco = start_deco + p["deco"]
        latence = start_deco - p["cool_finish"]

        s = copy.deepcopy(p)
        s["start_deco"] = start_deco
        s["end_deco"] = end_deco
        s["latence"] = latence
        s["pause_reason"] = pause_reason or ""
        scheduled.append(s)

        current = end_deco + deco_gap_min

    return scheduled


def simulate_prm(config: PRMSimulationConfig) -> pd.DataFrame:
    """
    Version corrigée orientée métier :
    - la latence max devient une CONTRAINTE DURE
    - si une pièce projetée dépasse la latence max, l'entrée au four est retardée jusqu'à respecter la limite
    - 2 zones de refroidissement modélisées comme 2 capacités de refroidissement parallèles (tampons)

    Remarque importante :
    le détail spatial Z1 -> Z2 reste simplifié pour cette version.
    L'objectif prioritaire ici est de faire respecter la règle métier de latence.
    """
    pause_windows = sorted(config.pause_windows or [])
    arm_order = normalize_arm_order(config.first_arm)

    # disponibilité des bras après décoffrage
    arm_available = {arm: config.start_time for arm in config.arms_config}

    # disponibilité des 2 zones de refroidissement (capacités parallèles)
    cool_slots = {
        "Z1": config.start_time,
        "Z2": config.start_time,
    }

    # poste déco/coffrage unique
    deco_available = config.start_time

    # envoi vers le four
    next_send_time = config.start_time

    pending = []   # pièces en attente de déco (cool fini ou pas encore fini)
    results = []

    def project_piece(start_four: int, arm: int, product: str, cycle: int):
        data = config.cycle_times[product]
        heat = data["heat"] + (config.extra_first_cycles if cycle < config.extra_first_cycles_count else 0)
        cool = data["cool"]
        deco = data["deco"]

        end_four = start_four + heat

        # Choix du slot de refroidissement le plus tôt disponible
        # priorité à Z2 si libre à la minute de sortie four, sinon Z1, sinon le premier slot qui se libère
        if cool_slots["Z2"] <= end_four:
            chosen_zone = "Z2"
            cool_start = end_four
        elif cool_slots["Z1"] <= end_four:
            chosen_zone = "Z1"
            cool_start = end_four
        else:
            chosen_zone = min(cool_slots, key=lambda z: cool_slots[z])
            cool_start = cool_slots[chosen_zone]

        cool_finish = cool_start + cool

        projected = {
            "PRM": config.prm_name,
            "arm": arm,
            "product": product,
            "cycle": cycle + 1,
            "start_four": start_four,
            "end_four": end_four,
            "start_cool": cool_start,
            "cool_finish": cool_finish,
            "deco": deco,
            "attente_avant_four": max(0, start_four - arm_available[arm]),
            "time_z1": cool if chosen_zone == "Z1" else 0,
            "time_z2": cool if chosen_zone == "Z2" else 0,
            "path": "Z1" if chosen_zone == "Z1" else "Z2 seul",
            "reason": "",
            "chosen_zone": chosen_zone,
        }
        return projected

    cycle = 0
    while True:
        arm = arm_order[cycle % len(arm_order)]
        product = config.arms_config[arm]

        # Planifier tout ce qui est déjà en attente avec l'état actuel
        pending_schedule = _schedule_pending(
            pending, deco_available, config.deco_gap_min, pause_windows
        )

        # Sécuriser l'invariant : aucune pièce déjà pendante ne doit déjà violer la contrainte
        if pending_schedule and max(x["latence"] for x in pending_schedule) > config.latence_max:
            raise RuntimeError(
                f"La file d'attente existante dépasse déjà la latence max ({config.latence_max} min). "
                f"Réduisez le temps entre envois, augmentez la latence max ou la marge opératoire."
            )

        raw_start_four = max(next_send_time, arm_available[arm])

        # Recherche du premier démarrage four qui respecte la latence max en projection
        start_four = raw_start_four
        found = False
        guard = 0

        while guard < 2000:
            candidate = project_piece(start_four, arm, product, cycle)
            trial_pending = pending + [candidate]
            trial_schedule = _schedule_pending(
                trial_pending, deco_available, config.deco_gap_min, pause_windows
            )

            candidate_scheduled = next(
                x for x in trial_schedule
                if x["cycle"] == candidate["cycle"] and x["arm"] == arm
            )

            if (
                candidate_scheduled["latence"] <= config.latence_max
                and candidate_scheduled["end_deco"] <= config.end_time
            ):
                found = True
                break

            # on décale au moins du dépassement observé, sinon de 1 minute
            delay = max(1, candidate_scheduled["latence"] - config.latence_max)
            start_four += delay
            guard += 1

        if not found:
            break

        # Si le four finit après la fin de journée, on stoppe
        if candidate["end_four"] > config.end_time:
            break

        # On engage réellement la pièce
        pending.append(candidate)
        cool_slots[candidate["chosen_zone"]] = candidate["cool_finish"]
        next_send_time = start_four + config.send_gap_min

        # Replanifier et sortir toutes les pièces devenues fermes avant le prochain envoi
        scheduled_all = _schedule_pending(
            pending, deco_available, config.deco_gap_min, pause_windows
        )

        # On fige les pièces qui commencent leur déco avant ou à next_send_time
        still_pending = []
        for s in scheduled_all:
            if s["start_deco"] <= next_send_time and s["end_deco"] <= config.end_time:
                reason = s["pause_reason"] or s["reason"]
                if s["latence"] > config.latence_max:
                    reason = "Latence" if not reason else f"{reason}; Latence"

                results.append({
                    "PRM": config.prm_name,
                    "Bras": s["arm"],
                    "Produit": s["product"],
                    "Début Four (min)": s["start_four"],
                    "Fin Four (min)": s["end_four"],
                    "Début Refroidissement (min)": s["start_cool"],
                    "Fin Refroidissement (min)": s["cool_finish"],
                    "Début Déco (min)": s["start_deco"],
                    "Fin Déco (min)": s["end_deco"],
                    "Latence (min)": s["latence"],
                    "Attente avant four (min)": s["attente_avant_four"],
                    "Attente avant déco (min)": s["latence"],
                    "Temps zone 1 (min)": s["time_z1"],
                    "Temps zone 2 (min)": s["time_z2"],
                    "Chemin refroidissement": s["path"],
                    "Motif décalage": reason,
                    "Cycle": s["cycle"],
                })

                deco_available = s["end_deco"] + config.deco_gap_min
                arm_available[s["arm"]] = s["end_deco"]
            else:
                still_pending.append({
                    k: v for k, v in s.items()
                    if k in [
                        "PRM",
                        "arm",
                        "product",
                        "cycle",
                        "start_four",
                        "end_four",
                        "start_cool",
                        "cool_finish",
                        "deco",
                        "attente_avant_four",
                        "time_z1",
                        "time_z2",
                        "path",
                        "reason",
                        "chosen_zone",
                    ]
                })

        pending = still_pending
        cycle += 1

        if start_four >= config.end_time:
            break

    # flush final
    final_schedule = _schedule_pending(
        pending, deco_available, config.deco_gap_min, pause_windows
    )

    for s in final_schedule:
        if s["end_deco"] <= config.end_time:
            reason = s["pause_reason"] or s["reason"]
            if s["latence"] > config.latence_max:
                reason = "Latence" if not reason else f"{reason}; Latence"

            results.append({
                "PRM": config.prm_name,
                "Bras": s["arm"],
                "Produit": s["product"],
                "Début Four (min)": s["start_four"],
                "Fin Four (min)": s["end_four"],
                "Début Refroidissement (min)": s["start_cool"],
                "Fin Refroidissement (min)": s["cool_finish"],
                "Début Déco (min)": s["start_deco"],
                "Fin Déco (min)": s["end_deco"],
                "Latence (min)": s["latence"],
                "Attente avant four (min)": s["attente_avant_four"],
                "Attente avant déco (min)": s["latence"],
                "Temps zone 1 (min)": s["time_z1"],
                "Temps zone 2 (min)": s["time_z2"],
                "Chemin refroidissement": s["path"],
                "Motif décalage": reason,
                "Cycle": s["cycle"],
            })

    return pd.DataFrame(results)


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
        "PRM",
        "Bras",
        "Produit",
        "Début Four",
        "Fin Four",
        "Début Refroidissement",
        "Fin Refroidissement",
        "Début Déco",
        "Fin Déco",
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
