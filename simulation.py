from dataclasses import dataclass
from datetime import datetime
import pandas as pd


class ScenarioInfeasibleError(Exception):
    """
    Conservée pour compatibilité avec app.py / optimizer.py.
    La simulation courante ne lève plus cette erreur métier.
    """
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


def format_time(minutes):
    return f"{int(minutes // 60):02d}:{int(minutes % 60):02d}"


def to_datetime(minutes):
    return datetime(2024, 1, 1, int(minutes // 60), int(minutes % 60))


def normalize_arm_order(first_arm):
    arms = [1, 2, 3, 4]
    idx = arms.index(first_arm)
    return arms[idx:] + arms[:idx]


def apply_pause_windows(start_op, duration, pause_windows):
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
            # démarre pendant la pause
            if p_start <= start_op < p_end:
                start_op = p_end
                reason = "Pause"
                changed = True
                break

            # chevauche la pause
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
    arms_config: dict
    cycle_times: dict
    first_arm: int = 4
    send_gap_min: int = 1
    latence_max: int = 20
    deco_gap_min: int = 5
    pause_windows: list = None
    extra_first_cycles: int = 2
    extra_first_cycles_count: int = 4


def simulate_prm(config):
    """
    Version 'calcul historique' :

    - on ne rejette plus les scénarios comme infaisables
    - on décale l'entrée au four de la pièce courante si la latence projetée dépasse la limite
    - l'objectif est de calculer une production cohérente en fonction de la latence proposée
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

        # +2 min sur les premiers cycles
        if cycle_idx < config.extra_first_cycles_count:
            heat += config.extra_first_cycles

        # départ four : le plus tôt possible selon cadence mini et disponibilité bras
        start_four = max(next_send_time, arm_available[arm])

        # logique historique : si la latence dépasse la limite, on décale l'amont
        while True:
            end_four = start_four + heat

            # refroidissement sur la première zone disponible la plus tôt
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

        reason = pause_reason if pause_reason else ""
        attente_avant_four = max(0, start_four - arm_available[arm])
        attente_avant_deco = latence

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
                "Attente avant four (min)": attente_avant_four,
                "Attente avant déco (min)": attente_avant_deco,
                "Temps zone 1 (min)": cool if chosen_zone == "Z1" else 0,
                "Temps zone 2 (min)": cool if chosen_zone == "Z2" else 0,
                "Chemin refroidissement": "Z1" if chosen_zone == "Z1" else "Z2 seul",
                "Motif décalage": reason,
                "Cycle": cycle_idx + 1,
            }
        )

        # mise à jour des disponibilités
        cool_slot_available[chosen_zone] = cool_finish
        deco_available = end_deco + config.deco_gap_min
        arm_available[arm] = end_deco
        next_send_time = start_four + config.send_gap_min
        cycle_idx += 1

    return pd.DataFrame(results)


def format_simulation_df(df):
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


def build_gantt_source(df):
    if df.empty:
        return pd.DataFrame()

    tasks = []
    for _, row in df.iterrows():
        label = f"{row['PRM']} - B{row['Bras']} - {row['Produit']}"

        tasks.extend(
            [
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
            ]
        )

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


def compute_prm_kpis(df, start_time, end_time):
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
