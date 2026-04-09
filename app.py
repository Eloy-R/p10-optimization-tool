import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

st.title("🏭 P10 - Simulation simple (base Excel)")

# =============================
# CONFIG
# =============================

TIMES = {
    "cuve": {"four": 45, "cool": 46, "deco": 60},
    "cloison": {"four": 35, "cool": 45, "deco": 40}
}

BRAS_ORDER = [
    ("Bras 4", "cloison"),
    ("Bras 1", "cuve"),
    ("Bras 2", "cloison"),
    ("Bras 3", "cuve"),
]

start_time = datetime(2024, 1, 1, 6, 25)
end_time = datetime(2024, 1, 1, 21, 45)

MOVE = timedelta(minutes=1)

# =============================
# SIMULATION SIMPLE
# =============================

def simulate():

    rows = []

    current_time = start_time
    deco_available = start_time

    index = 0

    first_cycle_done = {b: False for b, _ in BRAS_ORDER}

    while current_time < end_time:

        bras, prod = BRAS_ORDER[index % len(BRAS_ORDER)]
        t = TIMES[prod]

        # premier cycle +2 min
        if not first_cycle_done[bras]:
            four_time = t["four"] + 2
            first_cycle_done[bras] = True
        else:
            four_time = t["four"]

        # FOUR
        start_four = current_time
        end_four = start_four + timedelta(minutes=four_time)

        # REFROID
        end_cool = end_four + timedelta(minutes=t["cool"])

        # DECO
        start_deco = max(end_cool, deco_available)
        end_deco = start_deco + timedelta(minutes=t["deco"])

        if end_deco > end_time:
            break

        rows.append({
            "Bras": bras,
            "Produit": prod.capitalize(),
            "Four début": start_four,
            "Four fin": end_four,
            "Refroid fin": end_cool,
            "Déco début": start_deco,
            "Déco fin": end_deco
        })

        current_time = end_four + MOVE
        deco_available = end_deco
        index += 1

    return pd.DataFrame(rows)

# =============================
# RUN
# =============================

df = simulate()

# =============================
# TABLE (COMME EXCEL)
# =============================

st.subheader("📋 Flux production")

df_display = df.copy()

for col in ["Four début","Four fin","Refroid fin","Déco début","Déco fin"]:
    df_display[col] = df_display[col].dt.strftime("%H:%M")

# tri bras 1 → 4
df_display["Bras_num"] = df_display["Bras"].str.extract(r'(\d+)').astype(int)
df_display = df_display.sort_values(["Bras_num","Four début"])

st.dataframe(df_display.drop(columns="Bras_num"))

# =============================
# GANTT SIMPLE (OPTION)
# =============================

st.subheader("📊 Gantt simple")

gantt_rows = []

for _, row in df.iterrows():

    gantt_rows.append({
        "Bras": row["Bras"],
        "Zone": "Four",
        "Start": row["Four début"],
        "End": row["Four fin"]
    })

    gantt_rows.append({
        "Bras": row["Bras"],
        "Zone": "Refroid",
        "Start": row["Four fin"],
        "End": row["Refroid fin"]
    })

    gantt_rows.append({
        "Bras": row["Bras"],
        "Zone": "Déco",
        "Start": row["Déco début"],
        "End": row["Déco fin"]
    })

gantt_df = pd.DataFrame(gantt_rows)

fig = px.timeline(
    gantt_df,
    x_start="Start",
    x_end="End",
    y="Bras",
    color="Zone"
)

fig.update_yaxes(autorange="reversed")
fig.update_xaxes(tickformat="%H:%M")

st.plotly_chart(fig, use_container_width=True)
