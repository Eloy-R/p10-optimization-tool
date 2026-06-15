from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import copy
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


def apply_pause_windows(
    start_op: int,
    duration: int,
    pause_windows: List[Tuple[int, int]],
) -> Tuple[int, Optional[str]]:
    reason = None
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

            if start_op < p_start < end_temp:
                start_op = p_end
                reason = "Pause"
                changed = True
                break

    return start_op, reason


def build_infeasibility_reason(
    piece: dict,
    latence_max: int,
    send_gap_min: int,
    deco_gap_min: int,
    pending_count: int,
    end_time: Optional[int] = None,
) -> str:
    lines = []

    latence = piece.get("latence")
    cool_finish = piece.get("cool_finish")
    start_deco = piece.get("start_deco")
    end_deco = piece.get("end_deco")
    product = piece.get("product", "?")
    arm = piece.get("arm", "?")
    pause_reason = piece.get("pause_reason", "")

    if latence is not None:
        lines.append(f"Latence projetée = {latence} min > limite = {latence_max} min.")

    lines.append(f"Pièce concernée : bras {arm} - {product}.")

    if cool_finish is not None:
        lines.append(f"Fin refroidissement prévue : {format_time(cool_finish)}.")
    if start_deco is not None:
        lines.append(f"Début déco projeté : {format_time(start_deco)}.")
    if end_deco is not None and end_time is not None and end_deco > end_time:
        lines.append(
            f"La pièce finirait son décoffrage à {format_time(end_deco)}, "
            f"au-delà de la fin de journée autorisée ({format_time(end_time)})."
        )

    causes = []
    if pending_count > 0:
        causes.append(f"poste déco déjà chargé avec {pending_count} pièce(s) avant celle-ci")
    if pause_reason:
        causes.append("pause active qui décale le démarrage du décoffrage")
    if deco_gap_min > 0:
        causes.append(f"marge de sécurité entre décos = {deco_gap_min} min")
    if send_gap_min <= 10:
        causes.append(f"cadence d'envoi au four très agressive ({send_gap_min} min)")
    elif send_gap_min <= 15:
        causes.append(f"cadence d'envoi au four soutenue ({send_gap_min} min)")

    if causes:
        lines.append("Cause probable : " + " + ".join(causes) + ".")

    suggestions = [
        "augmenter le temps entre envois au four",
        "réduire la marge entre deux décoffrages",
        "desserrer la contrainte de latence",
    ]
    if pause_reason:
        suggestions.append("tester un autre scénario de pauses")

    lines.append("Suggestion : " + ", ".join(suggestions) + ".")
    return "\n".join(lines)


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
    pause_windows = sorted(config.pause_windows or [])
    arm_order = normalize_arm_order(config.first_arm)

    arm_available = {arm: config.start_time for arm in config.arms_config}
    cool_slots = {"Z1": config.start_time, "Z2": config.start_time}
    deco_available = config.start_time
    next_send_time = config.start_time
    pending = []
    results = []

    def project_piece(start_four: int, arm: int, product: str, cycle: int):
        data = config.cycle_times[product]
        heat = data["heat"] + (config.extra_first_cycles if cycle < config.extra_first_cycles_count else 0)
        cool = data["cool"]
        deco = data["deco"]
        end_four = start_four + heat

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

        return {
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

    cycle = 0

    while True:
        arm = arm_order[cycle % len(arm_order)]
        product = config.arms_config[arm]

        pending_schedule = _schedule_pending(
            pending,
            deco_available,
            config.deco_gap_min,
            pause_windows,
        )

        if pending_schedule:
            worst_existing = max(pending_schedule, key=lambda x: x["latence"])
            if worst_existing["latence"] > config.latence_max:
                msg = build_infeasibility_reason(
                    piece=worst_existing,
                    latence_max=config.latence_max,
                    send_gap_min=config.send_gap_min,
                    deco_gap_min=config.deco_gap_min,
                    pending_count=max(0, len(pending_schedule) - 1),
                    end_time=config.end_time,
                )
                raise ScenarioInfeasibleError(
                    msg,
                    details={
                        "type": "latence_queue",
                        "piece": worst_existing,
                        "latence_max": config.latence_max,
                    },
                )

        raw_start_four = max(next_send_time, arm_available[arm])
        start_four = raw_start_four
        found = False
        guard = 0
        last_candidate_scheduled = None

        while guard < 2000:
            candidate = project_piece(start_four, arm, product, cycle)
            trial_pending = pending + [candidate]

            trial_schedule = _schedule_pending(
                trial_pending,
                deco_available,
                config.deco_gap_min,
                pause_windows,
            )

            last_candidate_scheduled = next(
                x for x in trial_schedule
                if x["cycle"] == candidate["cycle"] and x["arm"] == arm
            )

            if (
                last_candidate_scheduled["latence"] <= config.latence_max
                and last_candidate_scheduled["end_deco"] <= config.end_time
            ):
                found = True
                break

            delay = max(1, last_candidate_scheduled["latence"] - config.latence_max)
            start_four += delay
            guard += 1

        if not found:
            msg = build_infeasibility_reason(
                piece=last_candidate_scheduled if last_candidate_scheduled else {
                    "product": product,
                    "arm": arm,
                },
                latence_max=config.latence_max,
                send_gap_min=config.send_gap_min,
                deco_gap_min=config.deco_gap_min,
                pending_count=max(0, len(pending)),
                end_time=config.end_time,
            )
            raise ScenarioInfeasibleError(
                msg,
                details={
                    "type": "no_feasible_start",
                    "piece": last_candidate_scheduled,
                    "latence_max": config.latence_max,
                },
            )

        if candidate["end_four"] > config.end_time:
            break

        pending.append(candidate)
        cool_slots[candidate["chosen_zone"]] = candidate["cool_finish"]
        next_send_time = start_four + config.send_gap_min

        scheduled_all = _schedule_pending(
            pending,
            deco_available,
            config.deco_gap_min,
            pause_windows,
        )

        still_pending = []
        for s in scheduled_all:
            if s["start_deco"] <= next_send_time and s["end_deco"] <= config.end_time:
                reason = s["pause_reason"] or s["reason"]
                if s["latence"] > config.latence_max:
                    reason = "Latence" if not reason else f"{reason}; Latence"

                results.append(
                    {
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
                    }
                )

                deco_available = s["end_deco"] + config.deco_gap_min
                arm_available[s["arm"]] = s["end_deco"]
            else:
                still_pending.append(
                    {
                        k: v
                        for k, v in s.items()
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
                    }
                )

        pending = still_pending
        cycle += 1

        if start_four >= config.end_time:
            break

    final_schedule = _schedule_pending(
        pending,
        deco_available,
        config.deco_gap_min,
        pause_windows,
    )

    for s in final_schedule:
        if s["end_deco"] <= config.end_time:
            reason = s["pause_reason"] or s["reason"]
            if s["latence"] > config.latence_max:
                reason = "Latence" if not reason else f"{reason}; Latence"

            results.append(
                {
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
                }
            )

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
