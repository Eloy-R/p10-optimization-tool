import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

st.title("🏭 P10 - Simulation proche Excel réel")

# =============================
# PARAMÈTRES
# =============================

STARTS = {
    1: datetime(2024, 1, 1, 7, 3),
}

END_TIME = datetime(2024, 1, 1, 21, 45)

TIMES = {
    "cuve": {"four": 45, "cool": 46, "deco": 60},
}

# 👉 seuil pour déclencher by-pass
MIN_GAP = 120  # minutes entre deux cycles (à ajuster)

# =============================
# FORMAT
# =============================

def f(t):
    return t.strftime("%H:%M")

# =============================
# SIMULATION
# =============================

def simulate():

    current = STARTS[1]
    t = TIMES["cuve"]

    rows = []
    first = True

    last_deco = None

    while current < END_TIME:

        # FOUR
        four_time = t["four"] + (2 if first else 0)
        four_start = current
        four_end = four_start + timedelta(minutes=four_time)

        cool_end = four_end + timedelta(minutes=t["cool"])
        deco_end = cool_end + timedelta(minutes=t["deco"])

        # =============================
        # LOGIQUE BYPASS
        # =============================

        if last_deco is not None:
            gap = (four_start - last_deco).total_seconds() / 60

            if gap < MIN_GAP:
                # 👉 insertion BYPASS
                bypass_start = current
                bypass_end = current + timedelta(minutes=3)

                rows.append({
                    "Type": "BYPASS",
                    "Début": f(bypass_start),
                    "Fin": f(bypass_end)
                })

                current = bypass_end
                continue

        # =============================
        # NORMAL
        # =============================

        rows.append({
            "Type": "CUVE",
            "Four début": f(four_start),
            "Four fin": f(four_end),
            "Refroid fin": f(cool_end),
            "Décoffrage fin": f(deco_end)
        })

        last_deco = deco_end
        current = four_end
        first = False

    return pd.DataFrame(rows)

# =============================
# RUN
# =============================

df = simulate()

st.dataframe(df)
