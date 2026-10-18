"""Draft exact affine empty-sequence elimination for sequence-form LPs."""
from __future__ import annotations

from fractions import Fraction

from scripts import river_sequence_form as legacy

CAPS = legacy.CAPS


def _root_slices(model):
    if not {"A", "flows", "flow_labels", "infos", "sequences", "empty"} <= set(model):
        raise ValueError("incomplete sequence-form model")
    me, mf = len(model["infos"][0]) + 1, len(model["infos"][1]) + 1
    if len(model["flows"]) != me + mf or len(model["flow_labels"]) != me + mf:
        raise ValueError("flow rows do not match information-set census")
    if len(model["sequences"]) != 2 or len(model["empty"]) != 2:
        raise ValueError("expected two players and two empty sequences")
    for player, count in ((0, me), (1, mf)):
        seqs = model["sequences"][player]
        start = 0 if player == 0 else me
        labels = model["flow_labels"][start:start+count]
        own_flows = model["flows"][start:start+count]
        if not seqs or seqs[0]["id"] != model["empty"][player]:
            raise ValueError("empty sequence must be first in original sequence order")
        if seqs[0].get("parent") is not None:
            raise ValueError("empty sequence must have no parent")
        if labels[0].get("kind") != "root" or labels[0].get("parent_sequence") != seqs[0]["id"]:
            raise ValueError("root flow label does not identify the first empty sequence")
        if labels[0].get("rhs") != "1" or own_flows[0] != [Fraction(1)] + [Fraction(0)] * (len(seqs)-1):
            raise ValueError("original root equation must fix the first empty coordinate to one")
        if any(len(row) != len(seqs) for row in own_flows):
            raise ValueError("flow matrix width differs from sequence count")
        if any(label.get("player") != player for label in labels):
            raise ValueError("flow labels are not grouped by player")
    nx, ny = len(model["sequences"][0]), len(model["sequences"][1])
    if len(model["A"]) != nx or any(len(row) != ny for row in model["A"]):
        raise ValueError("payoff matrix shape differs from sequences")
    return me, mf, model["flows"][:me], model["flows"][me:], nx, ny


def _preflight(kind, me, mf, nx, ny):
    if kind == "oop_guarantee":
        rows = me - 1 + ny
        columns = nx - 1 + 2 * mf + ny + (me - 1) + ny
    elif kind == "ip_ceiling":
        rows = mf - 1 + nx
        columns = ny - 1 + 2 * me + nx + (mf - 1) + nx
    else:
        raise ValueError("unknown LP model")
    cells = (rows + 1) * (columns + 1)
    if rows > CAPS["rows"] or columns > CAPS["columns"] or cells > CAPS["cells"]:
        raise legacy._Limit("compact LP row/column/tableau-cell cap")
    return rows, columns, cells


def _append_signed_row(coefficients, rhs, artificial_index, total_columns):
    """Normalize raw RHS before introducing a +1 artificial basis column."""
    sign = -1 if rhs < 0 else 1
    row = [Fraction(0)] * total_columns
    for index, value in coefficients.items():
        row[index] = sign * value
    row[artificial_index] = Fraction(1)
    return row, sign * rhs, sign


def _check_original(model, kind, own, free, slacks):
    me, mf, E, F, nx, ny = _root_slices(model)
    if kind == "oop_guarantee":
        if len(own) != nx or len(free) != mf or len(slacks) != ny:
            raise ValueError("lower witness dimensions do not reconstruct original LP")
        flow_rhs = [Fraction(1)] + [Fraction(0)] * (me-1)
        recomputed = [sum((E[r][i] * own[i] for i in range(nx)), Fraction(0))
                      for r in range(me)]
        expected_slacks = [sum((model["A"][i][j] * own[i] for i in range(nx)), Fraction(0)) -
                           sum((F[r][j] * free[r] for r in range(mf)), Fraction(0))
                           for j in range(ny)]
        objective = free[0]
    else:
        if len(own) != ny or len(free) != me or len(slacks) != nx:
            raise ValueError("upper witness dimensions do not reconstruct original LP")
        flow_rhs = [Fraction(1)] + [Fraction(0)] * (mf-1)
        recomputed = [sum((F[r][j] * own[j] for j in range(ny)), Fraction(0))
                      for r in range(mf)]
        expected_slacks = [sum((E[r][i] * free[r] for r in range(me)), Fraction(0)) -
                           sum((model["A"][i][j] * own[j] for j in range(ny)), Fraction(0))
                           for i in range(nx)]
        objective = free[0]
    if own[0] != 1 or any(value < 0 for value in own):
        raise ValueError("reconstructed realization must have empty coordinate one and be nonnegative")
    if recomputed != flow_rhs:
        raise ValueError("reconstructed full original realization violates flow equations")
    if any(value < 0 for value in expected_slacks) or expected_slacks != slacks:
        raise ValueError("reconstructed full original payoff inequalities fail")
    return objective


def solve_lp(model, kind):
    """Return the legacy-compatible (record, own realization, free dual, slacks)."""
    me, mf, E, F, nx, ny = _root_slices(model)
    rows_count, columns_count, cells_count = _preflight(kind, me, mf, nx, ny)
    a = model["A"]
    labels, rows, rhs, constraint_labels = [], [], [], []

    if kind == "oop_guarantee":
        own_n, free_n, cover_n = nx-1, mf, ny
        qp0, qm0 = own_n, own_n + free_n
        surplus0 = own_n + 2*free_n
        art0 = surplus0 + cover_n
        total = art0 + rows_count
        labels.extend(f"x:{seq['id']}" for seq in model["sequences"][0][1:])
        labels.extend(f"q+:{row['id']}" for row in model["flow_labels"][me:])
        labels.extend(f"q-:{row['id']}" for row in model["flow_labels"][me:])
        labels.extend(f"surplus:{row['id']}" for row in model["sequences"][1])
        labels.extend(f"artificial:{label['id']}" for label in model["flow_labels"][1:me])
        labels.extend(f"artificial:cover:{row['id']}" for row in model["sequences"][1])
        artificial = list(range(art0, total))
        # Remaining own-flow rows: E[r,1:] x = e_r - E[r,0].
        for reduced_row, r in enumerate(range(1, me)):
            raw_rhs = (Fraction(1) if r == 0 else Fraction(0)) - E[r][0]
            coefficients = {i-1: E[r][i] for i in range(1, nx) if E[r][i]}
            row, bound, sign = _append_signed_row(coefficients, raw_rhs, art0+reduced_row, total)
            rows.append(row); rhs.append(bound)
            constraint_labels.append({"id": model["flow_labels"][r]["id"], "sense": "=", "raw_rhs": str(raw_rhs), "row_sign": sign})
        for j in range(ny):
            coefficients = {}
            for i in range(1, nx):
                if a[i][j]: coefficients[i-1] = a[i][j]
            for r in range(mf):
                if F[r][j]:
                    coefficients[qp0+r] = -F[r][j]
                    coefficients[qm0+r] = F[r][j]
            coefficients[surplus0+j] = Fraction(-1)
            raw_rhs = -a[0][j]
            art_index = art0 + (me-1) + j
            row, bound, sign = _append_signed_row(coefficients, raw_rhs, art_index, total)
            rows.append(row); rhs.append(bound)
            constraint_labels.append({"id": f"cover:{model['sequences'][1][j]['id']}", "sense": ">=", "slack_variable": labels[surplus0+j], "raw_rhs": str(raw_rhs), "row_sign": sign})
        objective = [Fraction(0)] * total
        objective[qp0] = Fraction(1); objective[qm0] = Fraction(-1)
        simplex = legacy._Simplex(rows, rhs, labels, objective, artificial, kind)
        solved = simplex.solve(objective)
        values = solved.pop("values")
        own = [Fraction(1), *values[:own_n]]
        free = [values[qp0+r]-values[qm0+r] for r in range(mf)]
        slacks = [sum((a[i][j]*own[i] for i in range(nx)), Fraction(0)) -
                  sum((F[r][j]*free[r] for r in range(mf)), Fraction(0)) for j in range(ny)]
        bound = _check_original(model, kind, own, free, slacks)
        expected_objective = bound
        dual_labels = [row["id"] for row in model["flow_labels"][me:]]
        own_record = {"sequence_labels": [row["id"] for row in model["sequences"][0]], "fractions": [str(v) for v in own]}
        free_record = {"flow_labels": dual_labels, "fractions": [str(v) for v in free]}
        slack_record = {"sequence_labels": [row["id"] for row in model["sequences"][1]], "fractions": [str(v) for v in slacks]}
    else:
        own_n, free_n, cover_n = ny-1, me, nx
        pp0, pm0 = own_n, own_n + free_n
        surplus0 = own_n + 2*free_n
        art0 = surplus0 + cover_n
        total = art0 + rows_count
        labels.extend(f"y:{seq['id']}" for seq in model["sequences"][1][1:])
        labels.extend(f"p+:{row['id']}" for row in model["flow_labels"][:me])
        labels.extend(f"p-:{row['id']}" for row in model["flow_labels"][:me])
        labels.extend(f"surplus:{row['id']}" for row in model["sequences"][0])
        labels.extend(f"artificial:{label['id']}" for label in model["flow_labels"][me+1:me+mf])
        labels.extend(f"artificial:cover:{row['id']}" for row in model["sequences"][0])
        artificial = list(range(art0, total))
        for reduced_row, r in enumerate(range(1, mf)):
            raw_rhs = (Fraction(1) if r == 0 else Fraction(0)) - F[r][0]
            coefficients = {j-1: F[r][j] for j in range(1, ny) if F[r][j]}
            row, bound, sign = _append_signed_row(coefficients, raw_rhs, art0+reduced_row, total)
            rows.append(row); rhs.append(bound)
            constraint_labels.append({"id": model["flow_labels"][me+r]["id"], "sense": "=", "raw_rhs": str(raw_rhs), "row_sign": sign})
        for i in range(nx):
            coefficients = {}
            for j in range(1, ny):
                if a[i][j]: coefficients[j-1] = -a[i][j]
            for r in range(me):
                if E[r][i]:
                    coefficients[pp0+r] = E[r][i]
                    coefficients[pm0+r] = -E[r][i]
            coefficients[surplus0+i] = Fraction(-1)
            raw_rhs = a[i][0]
            art_index = art0 + (mf-1) + i
            row, bound, sign = _append_signed_row(coefficients, raw_rhs, art_index, total)
            rows.append(row); rhs.append(bound)
            constraint_labels.append({"id": f"cover:{model['sequences'][0][i]['id']}", "sense": ">=", "slack_variable": labels[surplus0+i], "raw_rhs": str(raw_rhs), "row_sign": sign})
        objective = [Fraction(0)] * total
        objective[pp0] = Fraction(-1); objective[pm0] = Fraction(1)
        simplex = legacy._Simplex(rows, rhs, labels, objective, artificial, kind)
        solved = simplex.solve(objective)
        values = solved.pop("values")
        own = [Fraction(1), *values[:own_n]]
        free = [values[pp0+r]-values[pm0+r] for r in range(me)]
        slacks = [sum((E[r][i]*free[r] for r in range(me)), Fraction(0)) -
                  sum((a[i][j]*own[j] for j in range(ny)), Fraction(0)) for i in range(nx)]
        bound = _check_original(model, kind, own, free, slacks)
        expected_objective = -bound
        dual_labels = [row["id"] for row in model["flow_labels"][:me]]
        own_record = {"sequence_labels": [row["id"] for row in model["sequences"][1]], "fractions": [str(v) for v in own]}
        free_record = {"flow_labels": dual_labels, "fractions": [str(v) for v in free]}
        slack_record = {"sequence_labels": [row["id"] for row in model["sequences"][0]], "fractions": [str(v) for v in slacks]}
    if solved["objective"] != expected_objective:
        raise ValueError("simplex objective differs from reconstructed original LP objective")
    solved.update({
        "lp": kind,
        "objective_bound_fraction": str(bound),
        "variable_labels": labels,
        "constraint_labels": constraint_labels,
        "own_realization": own_record,
        "dual_flow_values": free_record,
        "inequality_slacks": slack_record,
        "empty_sequence_reduction": {
            "fixed_sequence": model["empty"][0 if kind == "oop_guarantee" else 1],
            "fixed_value": "1",
            "removed_root_constraint": model["flow_labels"][0 if kind == "oop_guarantee" else me]["id"],
            "root_free_flow_coordinate_retained": True,
        },
    })
    actual_rows = solved["tableau_rows"]
    actual_columns = solved["tableau_columns"]
    actual_cells = (actual_rows + 1) * (actual_columns + 1)
    if actual_columns != columns_count or not 0 < actual_rows <= rows_count:
        raise ValueError("legacy simplex allocated a tableau outside reduced preflight dimensions")
    if solved["tableau_cells_including_rhs_and_objective"] != actual_cells:
        raise ValueError("legacy simplex cell count does not match its cleaned tableau")
    solved["initial_tableau_forecast"] = {
        "rows": rows_count, "columns": columns_count,
        "cells_including_rhs_and_objective": cells_count,
    }
    return solved, own, free, slacks
