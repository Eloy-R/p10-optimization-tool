from dataclasses import dataclassfrom dataclasses import dat
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
    Hypothèses de capacité (1 bras max par secteur) :
    - Four : 1 capacité
    - Refroid. Z1 : 1 capacité
    - Refroid. Z2 : 1 capacité
    - Avant déco : 1 capacité
    - Déco : 1 capacité

    La latence reste pilotée comme avant : si la latence projetée dépasse la consigne,
    on retarde l'entrée au four de la pièce courante.
    """
    pause_windows = sorted(config.pause_windows or [])
    arm_order = normalize_arm_order(config.first_arm)

    # disponibilités des ressources / secteurs
    arm_available = {arm: config.start_time for arm in config.arms_config}
    furnace_available = config.start_time               # 1 pièce max au four
    next_send_time = config.start_time                 # cadence minimale entre envois

    cooling_zone_available = {
        "Z1": config.start_time,
        "Z2": config.start_time,
    }                                                  # zones physiquement libres
    predeco_available = config.start_time              # 1 pièce max en avant déco
    deco_available = config.start_time                 # 1 pièce max au déco

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

        start_four = max(next_send_time, arm_available[arm], furnace_available)

        # On décale l'amont tant que la latence dépasse la limite.
        # Pour un start_four donné, on choisit le secteur qui minimise le démarrage déco.
        while True:
            end_four = start_four + heat

            best_plan = None
            for zone_name in ["Z1", "Z2"]:
                # La pièce ne peut entrer dans la zone que lorsqu'elle est libre.
                start_zone = max(end_four, cooling_zone_available[zone_name])
                cool_finish = start_zone + cool

                # La pièce reste physiquement en zone de refroidissement jusqu'à ce que
                # l'emplacement Avant déco soit libre.
                enter_predeco = max(cool_finish, predeco_available)

                # Le début de déco dépend ensuite du poste manuel et des pauses.
                raw_start_deco = max(enter_predeco, deco_available)
                start_deco, pause_reason = apply_pause_windows(raw_start_deco, deco, pause_windows)
                end_deco = start_deco + deco
                latence = start_deco - cool_finish

                plan = {
                    "zone": zone_name,
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
                    # priorité au départ déco le plus tôt, puis latence la plus faible
                    if (plan["start_deco"], plan["latence"], plan["end_deco"]) < (
                        best_plan["start_deco"],
                        best_plan["latence"],
                        best_plan["end_deco"],
                    ):
                        best_plan = plan

            if best_plan["latence"] <= config.latence_max:
                break

            # même logique métier que précédemment : on décale l'entrée au four
            start_four += (best_plan["latence"] - config.latence_max)

        end_four = start_four + heat
        chosen_zone = best_plan["zone"]
        start_zone = best_plan["start_zone"]
        cool_finish = best_plan["cool_finish"]
        enter_predeco = best_plan["enter_predeco"]
        start_deco = best_plan["start_deco"]
        end_deco = best_plan["end_deco"]
        latence = best_plan["latence"]
        pause_reason = best_plan["pause_reason"]

        # borne fin de journée : on retient uniquement les pièces finies au déco
        if end_deco > config.end_time:
            break

        # temps physique dans les secteurs
        zone_occupation = enter_predeco - start_zone           # inclut éventuel blocage après fin de refroidissement
        predeco_occupation = start_deco - enter_predeco         # attente en avant déco

        results.append(
            {
                "PRM": config.prm_name,
                "Bras": arm,
                "Produit": product,
                "Début Four (min)": start_four,
                "Fin Four (min)": end_four,
                "Début Refroidissement (min)": start_zone,
                "Fin Refroidissement (min)": cool_finish,              # fin réelle du refroidissement
                "Fin Occupation Refroidissement (min)": enter_predeco, # sortie physique de la zone
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

        # mise à jour des disponibilités physiques
        furnace_available = end_four                   # four occupé jusqu'à la fin de chauffe
        cooling_zone_available[chosen_zone] = enter_predeco  # zone libérée seulement quand la pièce en sort
        predeco_available = start_deco                 # l'emplacement avant déco se libère au démarrage déco
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
    """
    Vue instantanée du process en respectant bien la capacité 1 par secteur.
    On utilise :
    - Four : [Début Four, Fin Four)
    - Refroid. : [Début Refroidissement, Fin Occupation Refroidissement)
    - Avant déco : [Début Avant Déco, Fin Avant Déco)
    - Déco : [Début Déco, Fin Déco)
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
    """
    Vérifie qu'il n'y a jamais > 1 pièce simultanément dans un secteur listé.
    Utile pour contrôle qualité visuel.
    """
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
    # les fins avant les débuts si même minute
    for _, sector, delta in sorted(events, key=lambda x: (x[0], x[2])):
        counts[sector] += delta
        if counts[sector] > 1:
            return False
    return True
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd


class ScenarioInfeasibleError(Exception):
    """Conservée pour compatibilité avec app.py / optimizer.py."""
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
    Si l'opération démarre pendant une pause ou la chevauche,
    le démarrage est décalé à la fin de la pause.
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

