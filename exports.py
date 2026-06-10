from io import BytesIO
import pandas as pd


def build_excel_bytes(simulation_df=None, scenarios_df=None, overtime_df=None, mix_df=None, cycle_times_df=None):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if simulation_df is not None and not simulation_df.empty:
            simulation_df.to_excel(writer, sheet_name="Simulation", index=False)
        if scenarios_df is not None and not scenarios_df.empty:
            scenarios_df.to_excel(writer, sheet_name="Optimisation", index=False)
        if overtime_df is not None and not overtime_df.empty:
            overtime_df.to_excel(writer, sheet_name="Overtime", index=False)
        if mix_df is not None and not mix_df.empty:
            mix_df.to_excel(writer, sheet_name="Mix_Annuel", index=False)
        if cycle_times_df is not None and not cycle_times_df.empty:
            cycle_times_df.to_excel(writer, sheet_name="Temps_Cycle", index=False)
    output.seek(0)
    return output.getvalue()
