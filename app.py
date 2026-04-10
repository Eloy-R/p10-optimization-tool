import plotly.express as px

# =========================
# GANTT
# =========================

def build_gantt(df):

    tasks = []

    for _, row in df.iterrows():

        def to_min(t):
            return int(t[:2]) * 60 + int(t[3:])

        bras = f"Bras {row['Bras']} - {row['Produit']}"

        # FOUR
        tasks.append({
            "Task": bras,
            "Start": to_min(row["Début Four"]),
            "Finish": to_min(row["Fin Four"]),
            "Type": "Four"
        })

        # REFROID
        tasks.append({
            "Task": bras,
            "Start": to_min(row["Début Refroid"]),
            "Finish": to_min(row["Fin Refroid"]),
            "Type": "Refroidissement"
        })

        # DECO
        tasks.append({
            "Task": bras,
            "Start": to_min(row["Début Déco"]),
            "Finish": to_min(row["Fin Déco"]),
            "Type": "Décoffrage"
        })

        # LATENCE
        latence = row["Latence (min)"]
        if latence > 0:
            tasks.append({
                "Task": bras,
                "Start": to_min(row["Fin Refroid"]),
                "Finish": to_min(row["Début Déco"]),
                "Type": "LATENCE"
            })

    return pd.DataFrame(tasks)


# =========================
# AFFICHAGE GANTT
# =========================

st.subheader("📊 Diagramme de Gantt")

gantt_df = build_gantt(df)

fig = px.timeline(
    gantt_df,
    x_start="Start",
    x_end="Finish",
    y="Task",
    color="Type",
    color_discrete_map={
        "Four": "green",
        "Refroidissement": "blue",
        "Décoffrage": "purple",
        "LATENCE": "red"  # 🔥 bien visible
    }
)

fig.update_yaxes(autorange="reversed")

st.plotly_chart(fig, use_container_width=True)
