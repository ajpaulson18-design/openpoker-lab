"""Bounded exact sequence-form LP feasibility for two fixed river games."""
from __future__ import annotations

import hashlib
import json
import sys
import subprocess
import platform
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from pokerlab.cards import expand_range  # noqa: E402
from scripts import audit_river_rational_certificate as audit  # noqa: E402
from scripts import turn_rational_certificate as exact_helper  # noqa: E402
from scripts import turn_river_validation as validator  # noqa: E402

OUTPUT = REPO / "benchmarks/results/river-sequence-equilibrium-v1.json"
PRIOR_CERTIFICATE_SHA256 = '5acb6b4a0f1fa9a05af36feb2c010ac0b005be0bf29629571d99738b7ba34a34'
CAPS = {"rows": 96, "columns": 256, "cells": 25_000, "pivots": 512,
        "updates": 10_000_000, "bits": 4096, "exact_work": 100_000,
        "exact_depth": 64, "exact_bits": 65_536}


class _Limit(Exception):
    pass


def _bits(value):
    if not isinstance(value, Fraction):
        raise TypeError("simplex scalar must be Fraction")
    return max(abs(value.numerator).bit_length(), value.denominator.bit_length(), 1)


class _Simplex:
    """Exact primal-feasible two-phase simplex, Bland ordering, checked caps."""

    def __init__(self, matrix, rhs, names, objective, artificial, name):
        self.name, self.n, self.m = name, len(names), len(matrix)
        self.names, self.artificial = list(names), frozenset(artificial)
        self.cells = (self.m + 1) * (self.n + 1)  # include RHS and objective row
        if self.m > CAPS["rows"] or self.n > CAPS["columns"] or self.cells > CAPS["cells"]:
            raise _Limit("row/column/tableau-cell cap")
        self.pivots = self.updates = 0
        self.max_bits = 1
        self.tableau, self.basis = [], []
        if not (len(matrix) == len(rhs) == len(artificial) and
                len(set(artificial)) == len(artificial) and
                all(type(j) is int and 0 <= j < self.n for j in artificial)):
            raise ValueError("Incomplete artificial basis")
        for row, bound, art in zip(matrix, rhs, artificial):
            if len(row) != self.n or bound < 0 or any(row[j] != int(j == art) for j in artificial):
                raise ValueError("initial artificial basis needs nonnegative RHS")
            extended = list(row) + [Fraction(bound)]
            extended[art] = Fraction(1)
            self._track(extended)
            self.tableau.append(extended)
            self.basis.append(art)
        self._set_objective([-1 if j in self.artificial else 0 for j in range(self.n)])

    def _track(self, values):
        for value in values:
            self.max_bits = max(self.max_bits, _bits(value))
            if self.max_bits > CAPS["bits"]:
                raise _Limit("4096-bit Fraction cap")

    def _charge(self, amount):
        if self.updates + amount > CAPS["updates"]:
            raise _Limit("10,000,000 logical tableau-cell-update cap")
        self.updates += amount

    def _set_objective(self, costs):
        self._charge(self.m * self.n + self.n + self.m)
        cb = [Fraction(costs[j]) for j in self.basis]
        self.z = sum((cb[i] * self.tableau[i][-1] for i in range(self.m)), Fraction(0))
        self.reduced = [Fraction(costs[j]) - sum(
            (cb[i] * self.tableau[i][j] for i in range(self.m)), Fraction(0))
            for j in range(self.n)]
        self._track([self.z, *self.reduced])

    def _pivot(self, i, j):
        # Charge the entire tableau scalar-update envelope before pivot work.
        if self.pivots >= CAPS["pivots"]:
            raise _Limit("512-pivot cap")
        if self.updates + self.cells > CAPS["updates"]:
            raise _Limit("10,000,000 logical cell-update cap")
        self.pivots += 1
        self.updates += self.cells
        divisor = self.tableau[i][j]
        if divisor == 0:
            raise ArithmeticError("zero simplex pivot")
        pivot_row = [v / divisor for v in self.tableau[i]]
        self._track(pivot_row)
        for r in range(self.m):
            if r == i:
                continue
            factor = self.tableau[r][j]
            if factor:
                self.tableau[r] = [self.tableau[r][k] - factor * pivot_row[k]
                                   for k in range(self.n + 1)]
                self._track(self.tableau[r])
        factor = self.reduced[j]
        if factor:
            self.z += factor * pivot_row[-1]
            self.reduced = [self.reduced[k] - factor * pivot_row[k]
                            for k in range(self.n)]
            self._track([self.z, *self.reduced])
        self.tableau[i] = pivot_row
        self.basis[i] = j

    def _iterate(self, allowed):
        allowed = set(allowed)
        while True:
            self._charge(self.n + self.m)  # reduced-cost and ratio scan envelope
            basic = set(self.basis)
            entering = next((j for j in range(self.n)
                             if j in allowed and j not in basic and self.reduced[j] > 0), None)
            if entering is None:
                return
            ratios = [(row[-1] / row[entering], self.basis[i], i)
                      for i, row in enumerate(self.tableau) if row[entering] > 0]
            self._track([item[0] for item in ratios])
            if not ratios:
                raise _Limit("unbounded LP detected")
            least = min(item[0] for item in ratios)
            leaving = min(item for item in ratios if item[0] == least)[2]
            self._pivot(leaving, entering)

    def _drop_artificial_basis(self):
        row = 0
        art = self.artificial
        while row < len(self.basis):
            if self.basis[row] not in art:
                row += 1
                continue
            if self.tableau[row][-1] != 0:
                raise _Limit("positive artificial remains after phase I")
            self._charge(self.n)
            entering = next((j for j in range(self.n) if j not in art and
                             j not in self.basis and self.tableau[row][j] != 0), None)
            if entering is not None:
                self._pivot(row, entering)  # zero-step basis exchange
                row += 1
            else:
                if any(self.tableau[row][j] for j in range(self.n) if j not in art):
                    raise _Limit("artificial row not provably redundant")
                del self.tableau[row]
                del self.basis[row]
                self.m -= 1
                self.cells = (self.m + 1) * (self.n + 1)
        if any(j in art for j in self.basis):
            raise _Limit("artificial basis survived cleanup")

    def solve(self, objective):
        self._iterate(range(self.n))
        phase_one = self.z
        if phase_one != 0:
            raise _Limit("phase-I infeasible")
        self._drop_artificial_basis()
        self._set_objective(objective)
        self._iterate(set(range(self.n)) - self.artificial)
        if any(row[-1] < 0 for row in self.tableau):
            raise ValueError("Simplex lost primal feasibility")
        values = [Fraction(0) for _ in range(self.n)]
        for row, basic in zip(self.tableau, self.basis):
            values[basic] = row[-1]
        return {"objective": self.z, "values": values, "phase_one_objective": phase_one,
                "pivots": self.pivots, "logical_cell_updates": self.updates,
                "maximum_fraction_bits": self.max_bits, "tableau_rows": self.m,
                "tableau_columns": self.n,
                "tableau_cells_including_rhs_and_objective": self.cells}


def _build_model(fixture):
    board = validator.cards(fixture["board"])
    config = validator._config(fixture["config"], "config")
    ranges = tuple(expand_range(value, board) for value in (fixture["oop"], fixture["ip"]))
    ranges = tuple({h: w for h, w in side.items() if w > 0} for side in ranges)
    worlds, selected = validator._worlds(board, ranges, None)
    if selected:
        raise ValueError("fixed river unexpectedly has future runouts")
    root = validator._public_tree(board, config, config, selected, worlds)
    pending = [(root, 1)]
    seen = set()
    while pending:
        node, depth = pending.pop()
        if id(node) in seen:
            raise ValueError("fixed model must be a tree")
        seen.add(id(node))
        if len(seen) > 51 or depth > 6:
            raise _Limit("fixed-model public-node/depth cap")
        if isinstance(node, validator._Decision):
            if len(node.actions) != len(node.children) or not node.children:
                raise ValueError("incomplete public decision")
            pending.extend((child, depth + 1) for child in node.children)
        elif not isinstance(node, validator._Terminal):
            raise ValueError("chance or unknown node in fixed river model")
    nodes = validator._collect_nodes(root)
    empty = ("oop:empty", "ip:empty")
    sequences = [{empty[p]: {"id": empty[p], "player": p, "hand": None,
                            "history": [], "action_token": None, "parent": None}}
                 for p in (0, 1)]
    infos, parents, children_by_info = [{}, {}], [{}, {}], [{}, {}]

    def seq_id(player, hand, history, token):
        return f"{('oop','ip')[player]}|{hand}|{'/'.join(history) or 'root'}|{token}"

    def collect(node, current, world):
        if isinstance(node, validator._Terminal):
            return
        if isinstance(node, validator._Chance):
            raise ValueError("chance node in sequence construction")
        p = node.player
        hand = "".join(world["hands"][p])
        info = (p, hand, tuple(node.history))
        if info in parents[p] and parents[p][info] != current[p]:
            raise ValueError(f"perfect-recall violation at {info}")
        parents[p][info] = current[p]
        tokens = tuple(action.token for action in node.actions)
        if len(set(tokens)) != len(tokens):
            raise ValueError(f"duplicate legal action token at {info}")
        record = infos[p].get(info)
        if record and record["tokens"] != tokens:
            raise ValueError(f"inconsistent repeated information set {info}")
        infos[p][info] = {"tokens": tokens, "actions": tuple(node.actions)}
        seq_children = []
        for token, child in zip(tokens, node.children):
            sid = seq_id(p, hand, tuple(node.history), token)
            sequence = {"id": sid, "player": p, "hand": hand,
                        "history": list(node.history), "action_token": token,
                        "parent": current[p]}
            if sid in sequences[p] and sequences[p][sid] != sequence:
                raise ValueError("own sequence token identity collision")
            sequences[p][sid] = sequence
            seq_children.append(sid)
            nxt = list(current); nxt[p] = sid
            collect(child, tuple(nxt), world)
        if info in children_by_info[p] and children_by_info[p][info] != tuple(seq_children):
            raise ValueError("inconsistent repeated information-set children")
        children_by_info[p][info] = tuple(seq_children)

    for world in worlds:
        collect(root, empty, world)

    ordered, index = [], []
    for p in (0, 1):
        names = [empty[p]] + sorted(k for k in sequences[p] if k != empty[p])
        ordered.append([sequences[p][k] for k in names])
        index.append({k: i for i, k in enumerate(names)})

    flows, flow_labels = [], []
    for p in (0, 1):
        row = [Fraction(0)] * len(ordered[p]); row[0] = Fraction(1)
        flows.append(row)
        flow_labels.append({"id": f"{('oop','ip')[p]}:empty=1", "player": p,
                            "kind": "root", "parent_sequence": empty[p],
                            "child_sequences": [], "rhs": "1"})
        for info in sorted(infos[p], key=lambda k: (k[1], k[2])):
            row = [Fraction(0)] * len(ordered[p])
            for child in children_by_info[p][info]:
                row[index[p][child]] += 1
            parent = parents[p][info]
            row[index[p][parent]] -= 1
            flows.append(row)
            flow_labels.append({"id": f"{('oop','ip')[p]}:flow:{info[1]}:{'/'.join(info[2]) or 'root'}",
                                "player": p, "kind": "information_set",
                                "parent_sequence": parent,
                                "child_sequences": list(children_by_info[p][info]),
                                "rhs": "0"})

    expected = {
        "river-polarised-bluffcatcher": (2, 4, (4, 2), (9, 5), 5, 3, 4),
        "river-weighted-raises": (4, 18, (16, 20), (49, 53), 17, 21, 6),
    }[fixture["id"]]
    def tree_depth(node):
        if isinstance(node, validator._Terminal):
            return 1
        if isinstance(node, validator._Chance):
            return 1 + max(map(tree_depth, node.branches.values()))
        return 1 + max(map(tree_depth, node.children))
    observed = (len(worlds), len(nodes), (len(infos[0]), len(infos[1])),
                (len(ordered[0]), len(ordered[1])), len(infos[0]) + 1,
                len(infos[1]) + 1, tree_depth(root))
    if observed != expected:
        raise ValueError(f"fixed-fixture sequence census changed: {observed}")

    # Only after the fixed shape census passes do we allocate dense A.
    payoff = [[Fraction(0) for _ in ordered[1]] for _ in ordered[0]]

    def utility(node, world):
        matched = min(node.contributions)
        sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world["sign"]
        return Fraction.from_float(float(sign * (config.pot / 2 + matched)))

    def payoffs(node, current, world):
        if isinstance(node, validator._Terminal):
            i, j = index[0][current[0]], index[1][current[1]]
            payoff[i][j] += world["weight"] * utility(node, world)
            return
        if isinstance(node, validator._Chance):
            raise ValueError("chance node in payoff construction")
        p = node.player; hand = "".join(world["hands"][p])
        info = (p, hand, tuple(node.history))
        for token, child in zip(infos[p][info]["tokens"], node.children):
            sid = seq_id(p, hand, tuple(node.history), token)
            nxt = list(current); nxt[p] = sid
            payoffs(child, tuple(nxt), world)

    for world in worlds:
        payoffs(root, empty, world)
    info_labels = [{"player": p, "hand": info[1], "history": list(info[2]),
                    "action_tokens": list(infos[p][info]["tokens"]),
                    "parent_sequence": parents[p][info],
                    "child_sequences": list(children_by_info[p][info])}
                   for p in (0, 1)
                   for info in sorted(infos[p], key=lambda k: (k[1], k[2]))]
    return {"fixture": fixture, "board": board, "config": config, "worlds": worlds,
            "root": root, "nodes": nodes, "empty": empty,
            "sequences": ordered, "index": index, "infos": infos,
            "parents": parents, "children_by_info": children_by_info,
            "flows": flows, "flow_labels": flow_labels,
            "information_sets": info_labels, "A": payoff,
            "seq_id": seq_id}


def _solve_lp(model, kind):
    """Build and solve one prescribed LP; return labeled realization/duals."""
    a = model["A"]
    me = len(model["infos"][0]) + 1
    mf = len(model["infos"][1]) + 1
    E, F = model["flows"][:me], model["flows"][me:]
    nx, ny = len(model["sequences"][0]), len(model["sequences"][1])
    if kind == "oop_guarantee":
        rows_count, columns_count = me + ny, nx + 2 * mf + ny + me + ny
    elif kind == "ip_ceiling":
        rows_count, columns_count = mf + nx, ny + 2 * me + nx + mf + nx
    else:
        raise ValueError("unknown LP model")
    cells_count = (rows_count + 1) * (columns_count + 1)
    if (rows_count > CAPS["rows"] or columns_count > CAPS["columns"] or
            cells_count > CAPS["cells"]):
        raise _Limit("LP preflight row/column/tableau-cell cap")
    labels, rows, rhs, constraint_labels = [], [], [], []

    if kind == "oop_guarantee":
        # Ex, then A^T x - F^T(q+ - q-) - surplus = 0.
        x0, qp0, qm0, s0 = 0, nx, nx + mf, nx + 2 * mf
        art0 = s0 + ny
        total = art0 + me + ny
        labels.extend(f"x:{row['id']}" for row in model["sequences"][0])
        labels.extend(f"q+:{row['id']}" for row in model["flow_labels"][me:])
        labels.extend(f"q-:{row['id']}" for row in model["flow_labels"][me:])
        labels.extend(f"surplus:{row['id']}" for row in model["sequences"][1])
        labels.extend(f"artificial:{model['flow_labels'][r]['id']}" for r in range(me))
        labels.extend(f"artificial:cover:{row['id']}" for row in model["sequences"][1])
        art = list(range(art0, total))
        for r, flow in enumerate(E):
            row = [Fraction(0)] * total
            row[x0:x0 + nx] = flow
            row[art0 + r] = Fraction(1)
            rows.append(row); rhs.append(Fraction(1 if r == 0 else 0))
            constraint_labels.append({"id": model["flow_labels"][r]["id"], "sense": "="})
        for j in range(ny):
            row = [Fraction(0)] * total
            for i in range(nx):
                row[x0 + i] = a[i][j]
            for r in range(mf):
                row[qp0 + r] = -F[r][j]
                row[qm0 + r] = F[r][j]
            row[s0 + j] = Fraction(-1)
            row[art0 + me + j] = Fraction(1)
            rows.append(row); rhs.append(Fraction(0))
            constraint_labels.append({"id": f"cover:{model['sequences'][1][j]['id']}",
                                      "sense": ">=", "slack_variable": labels[s0 + j]})
        objective = [Fraction(0)] * total
        objective[qp0] = Fraction(1)
        objective[qm0] = Fraction(-1)
        simplex = _Simplex(rows, rhs, labels, objective, art, kind)
        solved = simplex.solve(objective)
        values = solved.pop("values")
        x = values[x0:x0 + nx]
        q = [values[qp0 + r] - values[qm0 + r] for r in range(mf)]
        slacks = [sum((a[i][j] * x[i] for i in range(nx)), Fraction(0)) -
                  sum((F[r][j] * q[r] for r in range(mf)), Fraction(0))
                  for j in range(ny)]
        if any(value < 0 for value in slacks):
            raise ValueError("OOP sequence-form inequality has negative slack")
        bound = q[0]
        dual_labels = [row["id"] for row in model["flow_labels"][me:]]
        own = {"sequence_labels": [row["id"] for row in model["sequences"][0]],
               "fractions": [str(value) for value in x]}
        dual = {"flow_labels": dual_labels, "fractions": [str(value) for value in q]}
        slack_output = {"sequence_labels": [row["id"] for row in model["sequences"][1]],
                        "fractions": [str(value) for value in slacks]}
    elif kind == "ip_ceiling":
        # Fy, then E^T(p+ - p-) - A y - surplus = 0; maximize -p_root.
        y0, pp0, pm0, s0 = 0, ny, ny + me, ny + 2 * me
        art0 = s0 + nx
        total = art0 + mf + nx
        labels.extend(f"y:{row['id']}" for row in model["sequences"][1])
        labels.extend(f"p+:{row['id']}" for row in model["flow_labels"][:me])
        labels.extend(f"p-:{row['id']}" for row in model["flow_labels"][:me])
        labels.extend(f"surplus:{row['id']}" for row in model["sequences"][0])
        labels.extend(f"artificial:{model['flow_labels'][me + r]['id']}" for r in range(mf))
        labels.extend(f"artificial:cover:{row['id']}" for row in model["sequences"][0])
        art = list(range(art0, total))
        for r, flow in enumerate(F):
            row = [Fraction(0)] * total
            row[y0:y0 + ny] = flow
            row[art0 + r] = Fraction(1)
            rows.append(row); rhs.append(Fraction(1 if r == 0 else 0))
            constraint_labels.append({"id": model["flow_labels"][me + r]["id"], "sense": "="})
        for i in range(nx):
            row = [Fraction(0)] * total
            for j in range(ny):
                row[y0 + j] = -a[i][j]
            for r in range(me):
                row[pp0 + r] = E[r][i]
                row[pm0 + r] = -E[r][i]
            row[s0 + i] = Fraction(-1)
            row[art0 + mf + i] = Fraction(1)
            rows.append(row); rhs.append(Fraction(0))
            constraint_labels.append({"id": f"cover:{model['sequences'][0][i]['id']}",
                                      "sense": ">=", "slack_variable": labels[s0 + i]})
        objective = [Fraction(0)] * total
        objective[pp0] = Fraction(-1)
        objective[pm0] = Fraction(1)
        simplex = _Simplex(rows, rhs, labels, objective, art, kind)
        solved = simplex.solve(objective)
        values = solved.pop("values")
        y = values[y0:y0 + ny]
        p = [values[pp0 + r] - values[pm0 + r] for r in range(me)]
        slacks = [sum((E[r][i] * p[r] for r in range(me)), Fraction(0)) -
                  sum((a[i][j] * y[j] for j in range(ny)), Fraction(0))
                  for i in range(nx)]
        if any(value < 0 for value in slacks):
            raise ValueError("IP sequence-form inequality has negative slack")
        bound = p[0]
        if solved["objective"] != -bound:
            raise ValueError("IP maximized objective does not equal negative p_root")
        dual_labels = [row["id"] for row in model["flow_labels"][:me]]
        own = {"sequence_labels": [row["id"] for row in model["sequences"][1]],
               "fractions": [str(value) for value in y]}
        dual = {"flow_labels": dual_labels, "fractions": [str(value) for value in p]}
        slack_output = {"sequence_labels": [row["id"] for row in model["sequences"][0]],
                        "fractions": [str(value) for value in slacks]}
    else:  # pragma: no cover - kind checked before allocation
        raise ValueError("unknown LP model")

    solved.update({"lp": kind, "objective_bound_fraction": str(bound),
                   "variable_labels": labels, "constraint_labels": constraint_labels,
                   "own_realization": own, "dual_flow_values": dual,
                   "inequality_slacks": slack_output})
    return solved, (x if kind == "oop_guarantee" else y), (q if kind == "oop_guarantee" else p), slacks


def _uniform_realizations(model):
    realizations = []
    policies = {}
    for player in (0, 1):
        index = model["index"][player]
        masses = [Fraction(0)] * len(model["sequences"][player])
        masses[0] = Fraction(1)
        infos = sorted(model["infos"][player], key=lambda key: (len(key[2]), key[1], key[2]))
        for info in infos:
            parent = model["parents"][player][info]
            children = model["children_by_info"][player][info]
            row = tuple(Fraction(1, len(children)) for _ in children)
            policies[(player, info[1], info[2])] = row
            parent_mass = masses[index[parent]]
            for child in children:
                mass = parent_mass / len(children)
                prior = masses[index[child]]
                if prior and prior != mass:
                    raise ValueError("uniform realization has conflicting sequence mass")
                masses[index[child]] = mass
        realizations.append(masses)
    return realizations, policies


def _realization_policies(model, realization):
    policies = {}
    for player in (0, 1):
        index = model["index"][player]
        for info in sorted(model["infos"][player], key=lambda key: (key[1], key[2])):
            parent = model["parents"][player][info]
            parent_mass = realization[player][index[parent]]
            children = model["children_by_info"][player][info]
            masses = [realization[player][index[child]] for child in children]
            if parent_mass:
                row = tuple(value / parent_mass for value in masses)
            else:
                row = tuple(Fraction(1, len(children)) for _ in children)
            if any(value < 0 for value in row) or sum(row, Fraction(0)) != 1:
                raise ValueError(f"invalid behavioral row at {(player, info)}")
            policies[(player, info[1], info[2])] = row
    return policies


def _flow_residuals(model, realization, player):
    residuals = []
    for label, row in zip(model["flow_labels"], model["flows"]):
        if label["player"] != player:
            continue
        lhs = sum((coefficient * value for coefficient, value in zip(row, realization[player])),
                  Fraction(0))
        rhs = Fraction(1) if label["kind"] == "root" else Fraction(0)
        residuals.append({"constraint": label["id"], "lhs": str(lhs),
                          "rhs": str(rhs), "residual": str(lhs - rhs)})
        if lhs != rhs:
            raise ValueError(f"flow equation failed at {label['id']}")
    if any(value < 0 for value in realization[player]):
        raise ValueError("negative sequence realization")
    return residuals


def _matrix_profile(model, x, y):
    return sum((x[i] * model["A"][i][j] * y[j]
                for i in range(len(x)) for j in range(len(y))), Fraction(0))


def _profile_recursion(model, policies):
    """Exact public-tree recursion, separate from the sequence matrix walk."""
    def terminal(node, world):
        matched = min(node.contributions)
        sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world["sign"]
        return Fraction.from_float(float(sign * (model["config"].pot / 2 + matched)))

    def visit(node, world):
        if isinstance(node, validator._Terminal):
            return terminal(node, world)
        if isinstance(node, validator._Chance):
            raise ValueError("chance node in exact river recursion")
        key = (node.player, "".join(world["hands"][node.player]), tuple(node.history))
        return sum((prob * visit(child, world)
                    for prob, child in zip(policies[key], node.children)), Fraction(0))

    return sum((world["weight"] * visit(model["root"], world)
                for world in model["worlds"]), Fraction(0))


def _result_object(model, policies, *, include_fraction):
    rows, seen = [], set()
    for node in model["nodes"]:
        p = node.player
        for world in model["worlds"]:
            if world["board"][:len(node.board)] != node.board:
                continue
            hand = "".join(world["hands"][p])
            key = (p, hand, tuple(node.history))
            if key in seen:
                continue
            seen.add(key)
            actions = validator._row_actions(node)
            for action, probability in zip(actions, policies[key]):
                action["probability"] = float(probability)
                if include_fraction:
                    action["probability_fraction"] = str(probability)
            rows.append({"player": "oop" if p == 0 else "ip", "hand": hand,
                         "street": "river", "board": list(node.board),
                         "history": list(node.history), "actions": actions})
    pair_count = len({(world["hands"][0], world["hands"][1]) for world in model["worlds"]})
    return {"board": list(model["board"]), "runouts": [], "runout_mode": "none",
            "reachable_runouts": [], "config": model["config"].to_dict(),
            "strategy": rows, "info_sets": len(rows),
            "compatible_pairs": pair_count, "deals": pair_count}


def _validate_uniform(model):
    realization, policies = _uniform_realizations(model)
    _flow_residuals(model, realization, 0)
    _flow_residuals(model, realization, 1)
    matrix_value = _matrix_profile(model, realization[0], realization[1])
    tree_value = _profile_recursion(model, policies)
    if matrix_value != tree_value:
        raise ValueError("uniform sequence payoff fails independent recursive cross-check")
    expected = {"river-polarised-bluffcatcher": Fraction(25, 4),
                "river-weighted-raises": Fraction(-38029, 3360)}[model["fixture"]["id"]]
    if matrix_value != expected:
        raise ValueError(f"uniform matrix EV differs from frozen independent reference: {matrix_value}")
    residuals = (_flow_residuals(model, realization, 0) +
                 _flow_residuals(model, realization, 1))
    return {"value_fraction": str(matrix_value), "matrix_equals_independent_tree": True,
            "flow_residuals": residuals}


def _metric_profile(model, realization, lower, upper):
    policies = _realization_policies(model, realization)
    value = _matrix_profile(model, realization[0], realization[1])
    recursive = _profile_recursion(model, policies)
    if value != recursive:
        raise ValueError("candidate x^T A y differs from independent profile recursion")
    float_policies = {key: tuple(float(v) for v in row) for key, row in policies.items()}
    result = _result_object(model, float_policies, include_fraction=False)
    result.update({"value_oop": float(value), "value_ip": -float(value),
                   "oop_best_response_value": float(upper),
                   "ip_best_response_value": -float(lower),
                   "oop_best_response_gain": float(upper - value),
                   "ip_best_response_gain": float(value - lower),
                   "nash_conv": float(upper - lower),
                   "exploitability": float((upper - lower) / 2)})
    oracle = validator.replay_policy(
        result, model["fixture"]["oop"], model["fixture"]["ip"],
        board=model["fixture"]["board"], config=model["fixture"]["config"])
    float_differences = validator.compare_result(result, oracle, tolerance=1e-9)
    exact_result = _result_object(model, policies, include_fraction=True)
    exact_result.update(result)
    exact_result["strategy"] = _result_object(
        model, policies, include_fraction=True)["strategy"]
    exact = exact_helper.evaluate_exact(
        model["root"], model["worlds"], policies, model["config"].pot,
        max_work=CAPS["exact_work"], max_depth=CAPS["exact_depth"],
        max_bits=CAPS["exact_bits"], result=exact_result)
    return {"policies": policies, "value": value, "recursive_value": recursive,
            "float_projection_oracle": oracle,
            "float_projection_compare_differences": float_differences,
            "rational_strategy": exact_result["strategy"], "exact": exact}


def _jsonable(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        if all(isinstance(key, str) for key in value):
            return {key: _jsonable(item) for key, item in value.items()}
        return {"key_value_entries": [{"key": _jsonable(key), "value": _jsonable(item)}
                                      for key, item in value.items()]}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _inputs():
    values = audit._source_fingerprints()
    for name in ("scripts/river_sequence_form.py", "scripts/verify_river_sequence.py",
                 "tests/test_river_sequence_form.py",
                 "benchmarks/results/river-rational-certificate-v1.json"):
        values[name] = hashlib.sha256((REPO/name).read_bytes()).hexdigest()
    return dict(sorted(values.items()))


def run_feasibility():
    baseline = subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()
    inputs = _inputs()
    digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    outputs = []
    for scenario, fixture in audit.FIXTURES.items():
        key = ("river-cfrplus-accuracy-extension-v1", scenario, "matrix-free", 10000)
        archived, _, raw_sha, _ = audit._read_policy(key[0], key)
        validator.compare_result(archived, validator.replay_policy(
            archived, fixture["oop"], fixture["ip"], board=fixture["board"],
            config=fixture["config"]), tolerance=1e-9)
        model = _build_model(fixture)
        uniform = _validate_uniform(model)
        lower_lp, x, q, lower_slacks = _solve_lp(model, "oop_guarantee")
        upper_lp, y, p, upper_slacks = _solve_lp(model, "ip_ceiling")
        realization = [x, y]
        residuals = [_flow_residuals(model, realization, player) for player in (0, 1)]
        measured = _metric_profile(model, realization, q[0], p[0])
        value = measured["value"]
        metrics = measured["exact"]["metrics"]
        if not (q[0] == value == p[0] == metrics["value_oop"] and
                metrics["oop_best_response_value"] == p[0] and
                metrics["ip_best_response_value"] == -q[0]):
            raise ValueError("LP objectives, profile and exact legal responses differ")
        if any(metrics[name] != 0 for name in (
                "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability")):
            raise ValueError("Candidate is not an exact mutual best response")
        if sum((a*b for a,b in zip(x, upper_slacks)), Fraction(0)) != 0 or sum(
                (a*b for a,b in zip(y, lower_slacks)), Fraction(0)) != 0:
            raise ValueError("Complementary slackness failed")
        if lower_lp["objective"] != q[0] or upper_lp["objective"] != -p[0]:
            raise ValueError("Reported LP objective signs differ")
        if scenario == "river-polarised-bluffcatcher" and value != 25:
            raise ValueError("Known polarised game value differs")
        prior_bytes = (REPO / "benchmarks/results/river-rational-certificate-v1.json").read_bytes()
        if hashlib.sha256(prior_bytes).hexdigest() != PRIOR_CERTIFICATE_SHA256:
            raise ValueError("Prior river certificate hash differs")
        prior = json.loads(prior_bytes)
        for row in prior["results"]:
            if row["scenario"] == scenario and not (
                    Fraction(row["lower_value_bound_fraction"]) <= value <=
                    Fraction(row["upper_value_bound_fraction"])):
                raise ValueError("Candidate value is outside a prior exact interval")
        outputs.append(dict(scenario=scenario, fixture=fixture,
            archived_template_sha256=raw_sha, uniform_crosscheck=uniform,
            sequences=model["sequences"], information_sets=model["information_sets"],
            flow_labels=model["flow_labels"], flow_matrix=model["flows"],
            payoff_matrix=model["A"], flow_residuals=residuals,
            lower_lp=lower_lp, upper_lp=upper_lp,
            rational_strategy=measured["rational_strategy"], exact=measured["exact"],
            float_projection_oracle=measured["float_projection_oracle"],
            float_projection_compare_differences=measured["float_projection_compare_differences"]))
        print(scenario, "EXACT value", value, "NashConv", metrics["nash_conv"],
            "pivots", lower_lp["pivots"], upper_lp["pivots"],
            "cell updates", lower_lp["logical_cell_updates"], upper_lp["logical_cell_updates"], flush=True)
    if _inputs() != inputs or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != digest:
        raise RuntimeError("Feasibility inputs/source changed during execution")
    if subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip() != baseline:
        raise RuntimeError("Git HEAD changed during candidate generation")
    report = dict(schema_version=1, certificate_id="river-sequence-equilibrium-v1",
        status="exact-mutual-response-witnesses", caps=CAPS,
        baseline_git_commit=baseline, python=platform.python_version(),
        generator_sha256=digest, prior_certificate_sha256=PRIOR_CERTIFICATE_SHA256, source_sha256=inputs, results=outputs,
        scope="Exact rational mutual-response witnesses for two fixed configured binary64-terminal river games; no unrestricted Hold'em claim.")
    payload = json.dumps(_jsonable(report), sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    OUTPUT.write_bytes(payload)
    if json.loads(OUTPUT.read_bytes()) != _jsonable(report):
        raise ValueError("Save/reload mismatch")
    from scripts.verify_river_sequence import verify_saved_artifact
    verify_saved_artifact(OUTPUT)
    print("SAVED AND INDEPENDENTLY VERIFIED", len(payload), hashlib.sha256(payload).hexdigest(), flush=True)


if __name__ == "__main__":
    run_feasibility()
