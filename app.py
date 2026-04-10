import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# =========================
# PARAMETRES
# =========================

PRODUITS = {
    "cloison": {"four": 35, "refroid": 45, "deco": 40},
    "cuve": {"four": 45, "refroid": 46, "deco": 60},
}

BRAS_SEQUENCE = [4, 1, 2, 3]

END_TIME = 21 * 60 + 45
GAP_FOUR = 1

PAUSE_START = 12 * 60
PAUSE_END = 13 * 60

# =========================
# TABS
# =========================

tab1, tab2 = st.tabs(["Simulation P10", "Optimisation"])

# =========================
# SIMULATION (INCHANGÉE)
# =========================

with tab1:

    st.title("Simulateur P10 - Production")

    jour = st.selectbox("Type de journée", ["Lundi", "Autres jours"])
    latence_max = st.slider("Latence max (min)", 0, 10, 10)
    pause_active = st.checkbox("Activer pause midi (12h-13h)", True)

    if jour == "Lundi":
        START_TIME = 6 * 60 + 25
    else:
        START_TIME = 4 * 60 + 52

    def format_time(m):
        return f"{int(m//60):02d}:{int(m%60):02d}"

    def to_minutes(t):
        return int(t[:2]) * 60 + int(t[3:])

    def to_datetime(t):
        return datetime(2024, 1, 1, int(t[:2]), int(t[3:]))

    def simulate():

        results = []
        last_four_end = START_TIME
        last_deco_end = START_TIME
        i = 0

        while True:

            produit = "cloison" if i % 2 == 0 else "cuve"
            bras = BRAS_SEQUENCE[i % 4]
            data = PRODUITS[produit]

            base_four = data["four"]
            refroid = data["refroid"]
            deco = data["deco"]

            if i < 4:
                four_time = base_four + 2
            else:
                four_time = base_four

            if i == 0:
                start_four = START_TIME
            else:
                start_four = last_four_end + GAP_FOUR

            end_four = start_four + four_time
            start_refroid = end_four
            end_refroid = start_refroid + refroid

            start_deco = max(end_refroid, last_deco_end)

            if pause_active:
                if PAUSE_START <= start_deco < PAUSE_END:
                    start_deco = PAUSE_END

            latence = start_deco - end_refroid

            if latence > latence_max:
                retard = latence - latence_max

                start_four += retard
                end_four += retard
                start_refroid += retard
                end_refroid += retard

                start_deco = max(end_refroid, last_deco_end)

                if pause_active:
                    if PAUSE_START <= start_deco < PAUSE_END:
                        start_deco = PAUSE_END

                latence = start_deco - end_refroid

            end_deco = start_deco + deco

            if end_deco > END_TIME:
                break

            results.append({
                "Bras": bras,
                "Produit": produit,
                "Début Four": format_time(start_four),
                "Fin Four": format_time(end_four),
                "Début Refroid": format_time(start_refroid),
                "Fin Refroid": format_time(end_refroid),
                "Début Déco": format_time(start_deco),
                "Fin Déco": format_time(end_deco),
                "Latence (min)": round(latence, 2)
            })

            last_four_end = end_four
            last_deco_end = end_deco
            i += 1

        return pd.DataFrame(results)

    def build_gantt(df):

        tasks = []

        for _, row in df.iterrows():

            label = f"B{row['Bras']} - {row['Produit']}"

            for phase in [
                ("Four", "Début Four", "Fin Four"),
                ("Refroid", "Début Refroid", "Fin Refroid"),
                ("Déco", "Début Déco", "Fin Déco")
            ]:
                tasks.append({
                    "Task": label,
                    "Start": to_datetime(row[phase[1]]),
                    "Finish": to_datetime(row[phase[2]]),
                    "Type": phase[0]
                })

            if row["Latence (min)"] > 0:
                tasks.append({
                    "Task": label,
                    "Start": to_datetime(row["Fin Refroid"]),
                    "Finish": to_datetime(row["Début Déco"]),
                    "Type": "LATENCE"
                })

        return pd.DataFrame(tasks)

    if st.button("Lancer la simulation"):

        df = simulate()
        st.session_state["df"] = df

        st.dataframe(df)

        # 🔥 EXPORT EXCEL (AJOUT UNIQUEMENT)
        def df_to_excel_xml(df):
            xml = '<?xml version="1.0"?>\n'
            xml += '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet">'
            xml += '<Worksheet ss:Name="Simulation"><Table>'

            xml += '<Row>'
            for col in df.columns:
                xml += f'<Cell><Data ss:Type="String">{col}</Data></Cell>'
            xml += '</Row>'

            for _, row in df.iterrows():
                xml += '<Row>'
                for val in row:
                    xml += f'<Cell><Data ss:Type="String">{val}</Data></Cell>'
                xml += '</Row>'

            xml += '</Table></Worksheet></Workbook>'
            return xml

        st.download_button(
            "📥 Télécharger Excel",
            df_to_excel_xml(df),
            file_name="simulation.xml",
            mime="application/xml"
        )

# =========================
# ONGLET OPTIMISATION
# =========================

with tab2:

    st.title("Optimisation avancée production")
    st.markdown("### Maximiser production + utilisation four")

    # 🔥 AJOUT : AFFICHER LA SIMULATION
    if "df" in st.session_state:
        st.subheader("📋 Simulation actuelle")
        st.dataframe(st.session_state["df"])
        st.divider()

    # 🔧 fonction centrale
    def simulate_with_overtime(extra):
        original_end = END_TIME
        globals()["END_TIME"] = original_end + extra
        df = simulate()
        globals()["END_TIME"] = original_end
        return df

    if st.button("Lancer optimisation avancée"):

        results = []
        best_score = -999
        best_config = None

        pauses = [
            ("Pas de pause", False, None),
            ("11:30-12:00", True, (11*60+30, 12*60)),
            ("12:00-12:30", True, (12*60, 12*60+30)),
            ("12:30-13:00", True, (12*60+30, 13*60)),
            ("12:00-13:00", True, (12*60, 13*60)),
        ]

        for pause_name, pause_active_val, pause_window in pauses:
            for lat in range(0, 11):

                pause_start_orig = PAUSE_START
                pause_end_orig = PAUSE_END
                latence_orig = latence_max

                if pause_active_val:
                    globals()["PAUSE_START"] = pause_window[0]
                    globals()["PAUSE_END"] = pause_window[1]
                else:
                    globals()["PAUSE_START"] = 0
                    globals()["PAUSE_END"] = 0

                globals()["latence_max"] = lat

                df = simulate()

                globals()["PAUSE_START"] = pause_start_orig
                globals()["PAUSE_END"] = pause_end_orig
                globals()["latence_max"] = latence_orig

                if df.empty:
                    continue

                total_prod = len(df)

                total_four_time = sum(
                    to_minutes(r["Fin Four"]) - to_minutes(r["Début Four"])
                    for _, r in df.iterrows()
                )

                taux_four = (total_four_time / (END_TIME - START_TIME)) * 100
                lat_moy = df["Latence (min)"].mean()

                score = total_prod * 100 + taux_four - lat_moy * 2

                results.append({
                    "Pause": pause_name,
                    "Latence max": lat,
                    "Production": total_prod,
                    "Taux four (%)": round(taux_four, 1),
                    "Latence moy": round(lat_moy, 2),
                    "Score": round(score, 1)
                })

                if score > best_score:
                    best_score = score
                    best_config = results[-1]

        df_results = pd.DataFrame(results).sort_values(by="Score", ascending=False)

        st.dataframe(df_results)
