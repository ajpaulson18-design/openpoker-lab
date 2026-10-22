"""No-training proof for positive range reweighting on one fixed flop support.

This is a distinct research model. It never treats the old-prior ClassModel or
its physical-world hash as authority for a reweighted distribution.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
import math
import struct

from scripts import flop_class_reweight_plan as planning
from scripts import flop_multistreet_validation as physical
from scripts import flop_public_classes as proof
from scripts import flop_public_classes_candidate as candidate


EXPECTED_CENSUS = {
    "compact_public_states": 1001, "compact_decisions": 316,
    "compact_chance_nodes": 58, "compact_terminals": 627,
    "physical_policy_rows": 16912, "compact_policy_rows": 466,
    "physical_action_slots": 33824, "compact_action_slots": 932,
    "compact_worlds": 126, "turn_classes": 11, "river_signatures": 19,
}
STATIC_ORACLE_FIELDS = (
    "board", "config", "street_configs", "runouts", "reachable_runouts",
    "runout_mode", "physical_worlds", "worlds_count", "compatible_pairs",
    "public_nodes", "public_states", "chance_nodes", "terminal_nodes", "pot",
    "effective_stack",
)


@dataclass(frozen=True)
class WeightedClassModel:
    plan: planning.ReweightPlan
    baseline: dict
    physical: dict
    partition: dict
    turns: dict
    rivers: dict
    worlds: tuple
    root: object
    census: dict


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _canonical_hand(hand):
    return "".join(sorted((hand[:2], hand[2:])))


def _validate_plan(plan):
    _need(type(plan) is planning.ReweightPlan, "Expected the fixed-support ReweightPlan")
    _need(type(plan.board) is tuple and type(plan.oop_weights) is tuple and
          type(plan.ip_weights) is tuple and
          all(type(value) is Fraction for value in plan.oop_weights + plan.ip_weights) and
          type(plan.global_blocker_normalizer) is Fraction and
          type(plan.compatible_pair_raw_products) is tuple and
          type(plan.exact_pair_priors) is tuple and
          type(plan.ordered_runouts_per_pair) is int and
          type(plan.physical_world_forecast) is int and type(plan.scope) is str,
          "Reweight plan fields are not in canonical immutable form")
    rebuilt = planning.plan_weights(plan.oop_weights, plan.ip_weights)
    _need(proof._typed(vars(plan)) == proof._typed(vars(rebuilt)) and
          plan.board == planning.BOARD and
          plan.ordered_runouts_per_pair == 1980 and
          plan.physical_world_forecast == 5940,
          "Reweight plan is malformed or outside the fixed support")
    return rebuilt


def _range_rows(hand_names, weights):
    return tuple((hand, f"{weight.numerator}/{weight.denominator}")
                 for hand, weight in zip(hand_names, weights))


def _pair_prior_map(plan):
    return {(_canonical_hand(oop), _canonical_hand(ip)): prior
            for oop, ip, prior in plan.exact_pair_priors}


def _validate_weighted_distribution(plan, baseline_worlds, weighted_worlds,
                                    baseline_counts, weighted_counts, normalizer,
                                    pair_probabilities, *, outcomes_per_pair=1980):
    """Check support/sign identity and globally conditioned joint masses.

    ``outcomes_per_pair`` is fixed to 1980 in production; the keyword exists
    only so focused synthetic tests can exercise the arithmetic with tiny data.
    """
    priors = _pair_prior_map(plan)
    _need(type(normalizer) is Fraction and normalizer == plan.global_blocker_normalizer,
          "Weighted oracle global blocker normalizer differs")
    _need(len(baseline_worlds) == len(weighted_worlds) ==
          len(priors) * outcomes_per_pair,
          "Weighted physical world count differs from fixed support")
    def index(worlds, *, weighted):
        result = {}
        for row in worlds:
            _need(type(row) is tuple and len(row) == 5 and type(row[2]) is Fraction and
                  type(row[3]) is int and row[3] in (-1, 0, 1) and
                  type(row[0]) is str and type(row[1]) is str and
                  type(row[4]) is tuple and len(row[4]) == 5 and
                  all(type(card) is str for card in row[4]),
                  "Malformed physical world row")
            key = (row[0], row[1], row[4])
            _need(key not in result, "Duplicate physical world row")
            if weighted:
                pair = (row[0], row[1])
                _need(pair in priors and row[2] == priors[pair] / outcomes_per_pair,
                      "Weighted world mass is not the globally conditioned pair mass")
            result[key] = (row[2], row[3])
        return result
    original, current = index(baseline_worlds, weighted=False), index(weighted_worlds, weighted=True)
    _need(original.keys() == current.keys() and all(original[key][1] == current[key][1]
          for key in original), "Reweighting changed physical support or showdown signs")
    def count_index(rows, *, weighted=False):
        _need(type(rows) in (tuple, list), "Malformed weighted pair-count metadata")
        result = {}
        for row in rows:
            _need(type(row) is dict, "Malformed weighted pair-count row")
            pair = (_canonical_hand(row.get("oop_hand", "")),
                    _canonical_hand(row.get("ip_hand", "")))
            _need(pair in priors and pair not in result and
                  type(row.get("ordered_outcomes")) is int and
                  row["ordered_outcomes"] == outcomes_per_pair,
                  "Weighted pair support or runout count differs")
            result[pair] = tuple(row.get(k) for k in ("wins", "ties", "losses"))
            _need(all(type(v) is int and v >= 0 for v in result[pair]),
                  "Malformed weighted sign census")
            _need(sum(result[pair]) == outcomes_per_pair,
                  "Weighted sign census does not cover its pair")
            if weighted:
                _need(type(row.get("pair_probability_fraction")) is str and
                      len(row["pair_probability_fraction"]) <= 2048,
                      "Malformed or oversized weighted exact pair-prior metadata")
                try:
                    exact_prior = Fraction(row["pair_probability_fraction"])
                except (ValueError, TypeError, ZeroDivisionError):
                    raise ValueError("Malformed weighted exact pair-prior metadata") from None
                _need(type(row.get("pair_probability_fraction")) is str and
                      exact_prior == priors[pair] and
                      type(row.get("pair_probability")) is float and
                      row["pair_probability"] == float(priors[pair]),
                      "Weighted pair-count prior differs from exact joint prior")
        return result
    old_counts = count_index(baseline_counts)
    new_counts = count_index(weighted_counts, weighted=True)
    _need(old_counts == new_counts and set(new_counts) == set(priors),
          "Reweighting changed pairwise showdown outcomes")
    observed = defaultdict(list)
    for (oop, ip, _), (_, sign) in current.items():
        observed[(oop, ip)].append(sign)
    for pair, signs in observed.items():
        _need((signs.count(1), signs.count(0), signs.count(-1)) == new_counts[pair],
              "Weighted pair sign metadata differs from physical worlds")
    _need(type(pair_probabilities) is dict and set(pair_probabilities) == set(priors) and
          all(type(pair_probabilities[pair]) is float and
              math.isfinite(pair_probabilities[pair]) and
              pair_probabilities[pair] == float(prior)
              for pair, prior in priors.items()),
          "Weighted pair-prior metadata differs from the exact joint prior")
    return True


def _validate_tree_compat(baseline, weighted):
    _need(baseline is not weighted, "Baseline and weighted physical oracles must be distinct")
    _need(proof._typed(proof._structure(baseline["root"])) ==
          proof._typed(proof._structure(weighted["root"])),
          "Reweighting changed the physical numeric tree")
    for field in STATIC_ORACLE_FIELDS:
        _need(proof._typed(baseline[field]) == proof._typed(weighted[field]),
              "Reweighting changed physical tree metadata: " + field)
    weighted_nodes = proof._walk(weighted["root"])
    expected_nodes = {(node.player, node.history): node for node in weighted_nodes
                      if isinstance(node, physical._Decision)}
    _need(set(baseline["nodes"]) == set(expected_nodes) == set(weighted["nodes"]) and
          all(weighted["nodes"][key] is node for key, node in expected_nodes.items()),
          "Weighted oracle decision index is not rooted in its numeric tree")
    def active(oracle):
        rows = defaultdict(set)
        for world in oracle["worlds"]:
            for length in range(3):
                for player in (0, 1):
                    rows[(player, world[4][3:3+length])].add(world[player])
        return dict(rows)
    baseline_active = active(baseline)
    _need(baseline_active, "Unreachable baseline information rows")
    _need(baseline_active == active(weighted) == weighted["active_hands_by_prefix"],
          "Reweighting changed physical own-hand visibility")


def _validate_weighted_anchor(plan, baseline, weighted):
    proof._physical_anchor(baseline)
    _validate_tree_compat(baseline, weighted)
    _need(weighted["normalizer"] == plan.global_blocker_normalizer and
          weighted["physical_worlds"] == plan.physical_world_forecast == 5940 and
          weighted["compatible_pairs"] == 3 and weighted["runout_mode"] == "full-deck",
          "Weighted physical anchor dimensions or global normalization differ")
    _validate_weighted_distribution(
        plan, baseline["worlds"], weighted["worlds"], baseline["counts"],
        weighted["counts"], weighted["normalizer"], weighted["pair_probabilities"])
    rank_keys = set()
    for oop, ip, _mass, _sign, board in baseline["worlds"]:
        rank_board = tuple(sorted(board, key=physical.DECK_INDEX.__getitem__))
        for hand in (oop, ip):
            rank_keys.add((hand[:2], hand[2:]) + rank_board)
    pair_counts = {oop + "/" + ip: 1980 for oop, ip in _pair_prior_map(plan)}
    expected_counters = {
        "rank_hand_calls": len(rank_keys), "physical_world_rows": 5940,
        "pair_runout_rows_checked": 5940, "world_count_by_pair": pair_counts}
    _need(proof._typed(weighted["deals"]) == proof._typed(weighted["worlds"]) and
          proof._typed(weighted["pair_counts"]) == proof._typed(weighted["counts"]) and
          proof._typed(weighted["worlds_count"]) == proof._typed(5940) and
          proof._typed(baseline["worlds_count"]) == proof._typed(5940) and
          proof._typed(weighted["world_count_per_pair"]) == proof._typed(pair_counts) and
          proof._typed(baseline["world_count_per_pair"]) == proof._typed(pair_counts) and
          proof._typed(weighted["source_counters"]) == proof._typed(expected_counters) and
          proof._typed(baseline["source_counters"]) == proof._typed(expected_counters),
          "Oracle aliases or support-derived source counters differ")
    return True


def _world_rows(worlds):
    return [[w[0], w[1], str(w[2]), w[3], list(w[4])] for w in worlds]


def _make_model(plan, baseline, weighted, partition):
    _validate_weighted_anchor(plan, baseline, weighted)
    turns, rivers, worlds = proof._verify_partition(partition, weighted["worlds"])
    root, collapse_census = proof._collapse(weighted["root"], turns, rivers)
    physical_rows = proof._expected_rows(weighted)
    keys = {(p, hand, proof._mapped_history(h, turns, rivers))
            for p, hand, h in physical_rows}
    nodes = proof._walk(root)
    census = dict(collapse_census)
    census.update(compact_public_states=len(nodes),
                   compact_decisions=sum(isinstance(n, physical._Decision) for n in nodes),
                   compact_chance_nodes=sum(isinstance(n, physical._Chance) for n in nodes),
                   compact_terminals=sum(isinstance(n, physical._Terminal) for n in nodes),
                   physical_policy_rows=len(physical_rows), compact_policy_rows=len(keys),
                   physical_action_slots=2*len(physical_rows), compact_action_slots=2*len(keys),
                   compact_worlds=len(worlds), turn_classes=len(partition["turn_classes"]),
                   river_signatures=len(partition["river_classes"]))
    _need(all(census.get(key) == value for key, value in EXPECTED_CENSUS.items()),
          "Reweighted compact tree census differs from fixed support")
    return WeightedClassModel(plan, baseline, weighted, partition, turns, rivers,
                              tuple(worlds), root, census)


def build_model(plan, baseline=None):
    """Validate weights, authenticate baseline, then freshly prepare both games."""
    plan = _validate_plan(plan)
    if baseline is None:
        baseline = physical.prepare_oracle(proof.BOARD, proof.OOP, proof.IP, proof.CONFIG)
    proof._physical_anchor(baseline)
    oop_rows = _range_rows(planning.OOP_HANDS, plan.oop_weights)
    ip_rows = _range_rows(planning.IP_HANDS, plan.ip_weights)
    weighted = physical.prepare_oracle(proof.BOARD, oop_rows, ip_rows, proof.CONFIG)
    partition = candidate.build_candidate(_world_rows(weighted["worlds"]), board=proof.BOARD)
    return _make_model(plan, baseline, weighted, partition)


def validate_model(model):
    """Reauthenticate both physical games and rebuild every compact component."""
    _need(type(model) is WeightedClassModel and model.baseline is not model.physical,
          "Expected a distinct weighted physical class model")
    plan = _validate_plan(model.plan)
    # The anchor authenticates every supplied world against the genuine
    # baseline support/signs and the requested exact pair priors. Rebuild the
    # quotient from those authenticated rows; do not enumerate/rank again.
    rebuilt = _make_model(plan, model.baseline, model.physical, model.partition)
    _need(proof._typed(model.partition) == proof._typed(rebuilt.partition) and
          proof._typed(model.turns) == proof._typed(rebuilt.turns) and
          proof._typed(model.rivers) == proof._typed(rebuilt.rivers) and
          proof._typed(model.worlds) == proof._typed(rebuilt.worlds) and
          proof._typed(model.census) == proof._typed(rebuilt.census) and
          proof._typed(proof._structure(model.root)) ==
          proof._typed(proof._structure(rebuilt.root)),
          "Weighted class model differs from authenticated physical reconstruction")
    return dict(rebuilt.census)


def _class_rows(model):
    return {(p, hand, proof._mapped_history(history, model.turns, model.rivers)): node
            for (p, hand, history), node in proof._expected_rows(model.physical).items()}


def project_policy(payload, model):
    validate_model(model)
    rows = physical._validate_policy(payload, model.physical, 1e-10)
    projected, bits = {}, {}
    for (player, hand, history), values in rows.items():
        proof._probabilities(values)
        key = (player, hand, proof._mapped_history(history, model.turns, model.rivers))
        raw = tuple(struct.pack(">d", value) for value in values)
        _need(key not in bits or bits[key] == raw,
              "Physical policy is not bit-exact class-constant")
        bits[key], projected[key] = raw, values
    _need(set(projected) == set(_class_rows(model)), "Projected weighted class rows differ")
    return projected


def lift_policy(rows, model):
    validate_model(model)
    _need(type(rows) is dict and set(rows) == set(_class_rows(model)),
          "Weighted class policy omits or adds an information set")
    for values in rows.values():
        proof._probabilities(values)
    oracle = model.physical
    strategy = []
    for (player, hand, history), node in sorted(proof._expected_rows(oracle).items()):
        key = (player, hand, proof._mapped_history(history, model.turns, model.rivers))
        actions = [{k: action[k] for k in ("name", "amount", "raise_to", "history_key")}
                   for action in node.actions]
        for action, probability in zip(actions, rows[key]):
            action["probability"] = probability
        strategy.append({"player": "oop" if player == 0 else "ip", "hand": hand,
                         "history": list(history), "street": node.street,
                         "board": list(node.board), "actions": actions})
    metrics = proof._exact_metrics(model.root, model.worlds, rows)
    return {"solver_version": "configured-postflop-v1",
            "algorithm": "no-training-positive-range-reweight-control",
            "strategy_schema": "postflop-strategy-v1", "board": list(proof.BOARD),
            "config": deepcopy(oracle["config"]),
            "street_configs": deepcopy(oracle["street_configs"]), "pot": oracle["pot"],
            "effective_stack": list(oracle["effective_stack"]), "runout_mode": "full-deck",
            "runouts": [list(r) for r in oracle["runouts"]],
            "reachable_runouts": [list(r) for r in oracle["reachable_runouts"]],
            "worlds": len(oracle["worlds"]), "compatible_pairs": oracle["compatible_pairs"],
            "deals": oracle["compatible_pairs"], "info_sets": len(strategy),
            "strategy": strategy,
            **{k: oracle[k] for k in ("public_nodes", "public_states", "chance_nodes",
                                      "terminal_nodes")},
            **{k: float(v) for k, v in metrics.items()}}


def audit_policy(payload, model):
    rows = project_policy(payload, model)
    compact = proof._exact_metrics(model.root, model.worlds, rows)
    physical_rows = physical._validate_policy(payload, model.physical, 1e-10)
    full = proof._exact_metrics(model.physical["root"], model.physical["worlds"], physical_rows)
    _need(compact == full, "Weighted compact and unrestricted physical exact metrics differ")
    numeric = physical.replay(payload, model.physical)
    gaps = {key: abs(float(full[key]) - numeric[key]) for key in proof.METRICS}
    _need(max(gaps.values()) <= 1e-10, "Weighted independent numeric replay differs")
    lifted_rows = physical._validate_policy(lift_policy(rows, model), model.physical, 1e-10)
    _need(all(tuple(struct.pack(">d", v) for v in values) ==
              tuple(struct.pack(">d", v) for v in lifted_rows[key])
              for key, values in physical_rows.items()), "Weighted lift changes a physical probability")
    return {"exact_metrics": {k: str(v) for k, v in full.items()},
            "independent_numeric_metrics": {k: numeric[k] for k in proof.METRICS},
            "maximum_numeric_gap": max(gaps.values()), "exact_metric_count": len(proof.METRICS),
            "physical_rows_lifted": len(lifted_rows), "class_rows": len(rows),
            "physical_strategy_sha256": proof._digest(payload["strategy"]),
            "class_policy": [[p, hand, list(history), list(values)]
                             for (p, hand, history), values in sorted(rows.items())]}


def control_policy(model, mode):
    _need(mode in ("check-call", "bet-fold", "class-varying", "zero-reach"),
          "Unknown weighted no-training control")
    validate_model(model)
    rows = {}
    for key, source in sorted(_class_rows(model).items()):
        if mode == "check-call":
            first = 1.0 if source.actions[0]["name"] == "check" else 0.0
        elif mode == "bet-fold":
            first = 0.0 if source.actions[0]["name"] == "check" else 1.0
        elif mode == "zero-reach":
            first = 1.0
        else:
            first = (int(proof._digest([key[0], key[1], list(key[2])])[:8], 16) % 5) / 4.0
        rows[key] = (first, 1.0-first)
    return lift_policy(rows, model)
