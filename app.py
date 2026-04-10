# =========================
# SIMULATEUR LIGNE P10
# =========================

# Temps en minutes
PRODUITS = {
    "cloison": {"four": 35, "refroid": 45, "deco": 40},
    "cuve": {"four": 45, "refroid": 46, "deco": 60},
}

BRAS_SEQUENCE = [4, 1, 2, 3]

# Heure de départ (ex : mardi 04:52)
START_TIME = 4 * 60 + 52


# =========================
# PARAMETRES PAUSE MIDI
# =========================

PAUSE_ENABLED = True
PAUSE_START = 12 * 60  # 12:00
PAUSE_DURATION = 60    # 30 ou 60
PAUSE_MODE = "deco_only"  # "full_stop" ou "deco_only"


# =========================
# OUTILS
# =========================

def format_time(minutes):
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h:02d}:{m:02d}"


def generate_sequence(n_cycles):
    sequence = []
    for i in range(n_cycles):
        sequence.append("cloison" if i % 2 == 0 else "cuve")
    return sequence


def is_in_pause(time):
    if not PAUSE_ENABLED:
        return False
    return PAUSE_START <= time < PAUSE_START + PAUSE_DURATION


def apply_pause(time):
    if not PAUSE_ENABLED:
        return time

    pause_end = PAUSE_START + PAUSE_DURATION

    if is_in_pause(time):
        return pause_end

    return time


# =========================
# MOTEUR DE SIMULATION
# =========================

def simulate(sequence):
    results = []

    last_four_end = START_TIME
    last_deco_end = START_TIME

    for i, produit in enumerate(sequence):
        bras = BRAS_SEQUENCE[i % 4]
        data = PRODUITS[produit]

        # Temps four (avec +2 min au démarrage)
        four_time = data["four"]
        if i < 4:
            four_time += 2

        # =====================
        # FOUR
        # =====================
        start_four = last_four_end

        if PAUSE_ENABLED and PAUSE_MODE == "full_stop":
            start_four = apply_pause(start_four)

        end_four = start_four + four_time

        # =====================
        # REFROIDISSEMENT
        # =====================
        end_refroid = end_four + data["refroid"]

        # =====================
        # DECOFFRAGE
        # =====================
        start_deco = max(end_refroid, last_deco_end)

        # Gestion pause (interdiction de décoffrer)
        start_deco = apply_pause(start_deco)

        end_deco = start_deco + data["deco"]

        # =====================
        # LATENCE
        # =====================
        latence = start_deco - end_refroid

        # =====================
        # STOCKAGE
        # =====================
        results.append({
            "cycle": i + 1,
            "bras": bras,
            "produit": produit,
            "start_four": start_four,
            "end_four": end_four,
            "end_refroid": end_refroid,
            "start_deco": start_deco,
            "end_deco": end_deco,
            "latence": latence
        })

        # =====================
        # UPDATE
        # =====================
        last_four_end = end_four
        last_deco_end = end_deco

    return results


# =========================
# AFFICHAGE
# =========================

def print_results(results):
    print("\n=== RESULTATS SIMULATION P10 ===\n")

    print(
        f"{'Cycle':<6} {'Bras':<5} {'Produit':<10} "
        f"{'Début Four':<10} {'Fin Four':<10} "
        f"{'Fin Refroid':<12} {'Début Déco':<12} "
        f"{'Fin Déco':<10} {'Latence':<8}"
    )

    print("-" * 95)

    for r in results:
        print(
            f"{r['cycle']:<6} {r['bras']:<5} {r['produit']:<10} "
            f"{format_time(r['start_four']):<10} {format_time(r['end_four']):<10} "
            f"{format_time(r['end_refroid']):<12} {format_time(r['start_deco']):<12} "
            f"{format_time(r['end_deco']):<10} {r['latence']:<8}"
        )


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    sequence = generate_sequence(20)
    results = simulate(sequence)
    print_results(results)
