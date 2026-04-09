import pandas as pd

TIMES = {
    "cuve": {"four": 45, "cool": 46, "deco": 60},
    "cloison": {"four": 35, "cool": 45, "deco": 40}
}

MAX_WAIT = 20
NB_BRAS = 4

def simulate(sequence):

    bras_time = [0] * NB_BRAS
    deco_available = 0

    records = []

    for i, prod in enumerate(sequence):

        bras = i % NB_BRAS
        t = TIMES[prod]

        start_four = bras_time[bras]
        end_four = start_four + t["four"]

        end_cool = end_four + t["cool"]

        start_deco = max(end_cool, deco_available)
        wait = start_deco - end_cool

        end_deco = start_deco + t["deco"]

        deco_available = end_deco
        bras_time[bras] += t["four"]

        records.append({
            "bras": bras,
            "produit": prod,
            "start": start_four,
            "end": end_deco,
            "wait": wait
        })

    return pd.DataFrame(records)
