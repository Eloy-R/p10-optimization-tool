from ortools.sat.python import cp_model

def optimize(nb_cycles=40):

    model = cp_model.CpModel()
    horizon = 24 * 60

    starts = []
    ends = []
    intervals = []

    for i in range(nb_cycles):

        is_cuve = model.NewBoolVar(f"is_cuve_{i}")

        # Durées
        four = model.NewIntVar(35, 45, f"four_{i}")
        cool = model.NewIntVar(45, 46, f"cool_{i}")
        deco = model.NewIntVar(40, 60, f"deco_{i}")

        model.Add(four == 45).OnlyEnforceIf(is_cuve)
        model.Add(four == 35).OnlyEnforceIf(is_cuve.Not())

        model.Add(cool == 46).OnlyEnforceIf(is_cuve)
        model.Add(cool == 45).OnlyEnforceIf(is_cuve.Not())

        model.Add(deco == 60).OnlyEnforceIf(is_cuve)
        model.Add(deco == 40).OnlyEnforceIf(is_cuve.Not())

        start = model.NewIntVar(0, horizon, f"start_{i}")
        mid1 = model.NewIntVar(0, horizon, f"mid1_{i}")
        mid2 = model.NewIntVar(0, horizon, f"mid2_{i}")
        end = model.NewIntVar(0, horizon, f"end_{i}")

        model.Add(mid1 == start + four)
        model.Add(mid2 == mid1 + cool)
        model.Add(end == mid2 + deco)

        interval = model.NewIntervalVar(start, deco, end, f"interval_{i}")

        starts.append(start)
        ends.append(end)
        intervals.append(interval)

    # Goulot décoffrage
    model.AddNoOverlap(intervals)

    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, ends)

    model.Minimize(makespan)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    result = []

    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        for i in range(nb_cycles):
            result.append({
                "cycle": i,
                "start": solver.Value(starts[i]),
                "end": solver.Value(ends[i])
            })

    return result
