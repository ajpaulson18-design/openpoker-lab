"""One no-retry four-call study of two fixed weighted 16x16 river games."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import traceback
import uuid


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks/matrix-free-river-range-quality-v1.json"
MANIFEST_LF_SHA256 = "08ce0f8a890abc08ebec21cca8c7f6a6ecb2ad140553194dc3acb6c502945a19"
MANIFEST_CANONICAL_SHA256 = "b91cb3e7d584d5dc4e07daf417a1b7f2b54bb8ce01d8f5bbbd8200b200785b44"
CONTROL_HELPER = "benchmarks/results/native-river-controls-v1/validate_compiled_river.py"
CONTROL_HELPER_SHA256 = "a4155547d39b49c65a7fcb3b22a0ee5ce751de17a6183026ee713f62f88203b6"
BASELINE_HASHES = {
    "report.json": "e348d38048f2dc235caa7a8c1674cd92b56490cf6196152a7268b1b0badb52f5",
    "claim.json": "5244c65f875b57816b4602d850969a4c1eed921dd5a2c7849022143da8c64e00",
    "status.json": "9e4b41653b0153e2036efe716bbd72f74ce79f8f0a6d27006c325b382efb93b9",
}
OWN_FILES = (
    "scripts/benchmark_matrix_free_river_range_quality.py",
    "docs/matrix-free-river-range-quality-protocol.md",
    "benchmarks/matrix-free-river-range-quality-v1.json",
    "tests/test_benchmark_matrix_free_river_range_quality.py",
)
EXACT_LIMITS = {"work": 100000, "depth": 64, "fraction_bits": 65536}
NUMERIC_LIMITS = {"MAX_WORLD_COUNT": 200000, "MAX_ORACLE_WORK": 8000000}
MF_LIMITS = {
    "iterations": 100000, "hand_state_pass_work": 30000000,
    "info_action_slots": 1000000, "public_states": 250000,
    "fallback_pair_checks": 30000000,
}
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
    "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability",
)
IDS = (
    "river-unpaired-club-16x16-fractional-short-refund",
    "river-paired-heart-16x16-rank-extremes-short-refund",
)
BACKENDS = ("matrix-free-D0", "matrix-free-tail")
TARGET = Fraction(1, 1000)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _lf(raw):
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def _pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def _same(expected, actual, label):
    if _json_bytes(expected) != _json_bytes(actual):
        raise RuntimeError(label + " changed or differs")


def _exclusive(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _atomic(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    _exclusive(temporary, _pretty(value))
    os.replace(temporary, path)


def _validate_manifest(manifest):
    # A canonical digest binds every literal card, weight, menu, and call field.
    if _sha(_json_bytes(manifest)) != MANIFEST_CANONICAL_SHA256:
        raise ValueError("Manifest differs from the complete fixed 16x16 design")
    calls = [(case, backend, iterations, discard) for case in IDS
             for backend, iterations, discard in (
                 (BACKENDS[0], 10000, 0), (BACKENDS[1], 20000, 10000))]
    if [(c["case"], c["backend"], c["iterations"], c["discard"])
            for c in manifest["calls"]] != calls:
        raise ValueError("Manifest does not contain the exact ordered four calls")


def _retained_helper(root, name):
    path = root / CONTROL_HELPER
    if _sha(path.read_bytes()) != CONTROL_HELPER_SHA256:
        raise RuntimeError("Retained production-tripwire/source helper digest differs")
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def authenticate_baselines(baseline_root, control_root):
    """Byte-authenticate completed 8x8 and 16-policy controls; no replay/build."""
    from scripts import benchmark_native_river_range_quality as prior
    baseline_root = Path(baseline_root).resolve()
    raw = {name: (baseline_root / name).read_bytes() for name in BASELINE_HASHES}
    if any(_sha(raw[name]) != digest for name, digest in BASELINE_HASHES.items()):
        raise RuntimeError("Retained 8x8 report/claim/status digest differs")
    report, claim, status = (json.loads(raw[name].decode("utf-8"))
                             for name in ("report.json", "claim.json", "status.json"))
    if (report.get("schema") != "native-river-range-quality-report-v1" or
            report.get("status") != "completed" or status.get("status") != "completed" or
            claim.get("retry_permitted") is not False or status.get("retry_permitted") is not False or
            not claim.get("claim_id") or
            not claim["claim_id"] == report.get("claim_id") == status.get("claim_id")):
        raise RuntimeError("Retained 8x8 completed/no-retry identity is invalid")
    receipts = []
    profiles = report.get("profiles")
    if not isinstance(profiles, list) or len(profiles) != 4:
        raise RuntimeError("Retained 8x8 corpus does not contain exactly four policies")
    for row in profiles:
        relative = row.get("file")
        path = baseline_root / relative
        if not path.resolve().is_relative_to(baseline_root) or path.is_symlink():
            raise RuntimeError("Retained 8x8 policy receipt escapes its corpus")
        policy = path.read_bytes()
        if len(policy) != row.get("bytes") or _sha(policy) != row.get("sha256"):
            raise RuntimeError("Retained 8x8 raw policy receipt differs")
        if _json_bytes(json.loads(policy.decode("utf-8"))) != policy:
            raise RuntimeError("Retained 8x8 raw policy is not canonical JSON")
        receipts.append({"file": relative, "bytes": len(policy), "sha256": _sha(policy)})
    _same(claim["build"], report["build"], "Retained 8x8 static build provenance")
    controls = prior.authenticate_control_corpus(control_root)
    _same({k:v for k,v in controls.items() if k!="root"},
          {k:v for k,v in report["control_authentication"].items() if k!="root"},
          "Retained 8x8/16-control provenance")
    return {
        "baseline_root": str(baseline_root), "control_root": str(Path(control_root).resolve()),
        "claim_id": claim["claim_id"], "evidence_sha256": {n: _sha(v) for n, v in raw.items()},
        "policies": receipts, "historical_build_receipt_only": report["build"],
        "retained_controls": controls, "live_native_build_requested": False,
    }


def _physical_model(rules, ranks, case):
    """Exhaustive independent pair/mass/rank census; never passed to a trainer."""
    board = rules.cards(case["board"], 5)
    ranges = (rules.expand_range(case["oop"], board), rules.expand_range(case["ip"], board))
    if [len(side) for side in ranges] != [16, 16]:
        raise ValueError("Independent positive supports are not exactly 16x16")
    worlds, selected = rules._worlds(board, ranges, None)
    if selected or len(worlds) > rules.MAX_WORLD_COUNT:
        raise ValueError("Independent complete-board physical-world admission rejected")
    by_pair = {world["hands"]: world for world in worlds}
    if len(by_pair) != len(worlds):
        raise ValueError("Independent physical worlds duplicate a private pair")
    masses, collisions = {}, []
    hand_ranks = [{hand: ranks.independent_rank(board + hand) for hand in side} for side in ranges]
    for h0, w0 in ranges[0].items():
        for h1, w1 in ranges[1].items():
            if set(h0) & set(h1):
                if (h0, h1) in by_pair:
                    raise ValueError("Blocked private pair entered independent physical worlds")
                collisions.append(["".join(h0), "".join(h1), sorted(set(h0) & set(h1))])
            else:
                masses[(h0, h1)] = Fraction.from_float(float(w0)) * Fraction.from_float(float(w1))
    if set(masses) != set(by_pair):
        raise ValueError("Independent physical pair bijection differs from all 256 candidates")
    total = sum(masses.values(), Fraction())
    physical, marginals = [], [{}, {}]
    for pair, mass in masses.items():
        normalized = mass / total
        r0, r1 = (hand_ranks[p][pair[p]] for p in (0, 1))
        sign = (r0 > r1) - (r0 < r1)
        if by_pair[pair]["weight"] != normalized or by_pair[pair]["sign"] != sign:
            raise ValueError("Independent normalized mass or best-five rank sign differs")
        physical.append({"hands": ["".join(hand) for hand in pair],
                         "mass_fraction": str(normalized), "sign": sign})
        for player in (0, 1):
            marginals[player][pair[player]] = marginals[player].get(pair[player], Fraction()) + normalized
    if sum((world["weight"] for world in worlds), Fraction()) != 1:
        raise ValueError("Independent normalized world mass is not exactly one")
    evidence = {
        "candidate_pairs": 256, "compatible_pairs": len(worlds),
        "blocked_pairs": collisions, "physical_worlds": physical, "normalized_mass_fraction": "1",
        "hand_ranks": [{"".join(hand): list(rank) for hand, rank in side.items()} for side in hand_ranks],
        "rank_categories": sorted({rank[0] for side in hand_ranks for rank in side.values()}),
        "compatible_exact_rank_tie_pairs": [row["hands"] for row in physical if row["sign"] == 0],
    }
    return board, ranges, worlds, hand_ranks, marginals, evidence


def _legal_metric_identities(metrics, tolerance=1e-9):
    lower, upper, value = -metrics["ip_best_response_value"], metrics["oop_best_response_value"], metrics["value_oop"]
    errors = (
        metrics["value_ip"] + value,
        metrics["oop_best_response_gain"] - (upper - value),
        metrics["ip_best_response_gain"] - (value - lower),
        metrics["nash_conv"] - (upper - lower),
        metrics["nash_conv"] - metrics["oop_best_response_gain"] - metrics["ip_best_response_gain"],
        metrics["exploitability"] - metrics["nash_conv"] / 2,
    )
    if (any(abs(error) > tolerance for error in errors) or
            lower > value + tolerance or value > upper + tolerance or
            min(metrics["oop_best_response_gain"], metrics["ip_best_response_gain"], metrics["nash_conv"]) < 0):
        raise ValueError("Numeric/exact legal response interval, gain, or zero-sum identity fails")
    return {"lower": str(lower) if isinstance(lower, Fraction) else float(lower),
            "upper": str(upper) if isinstance(upper, Fraction) else float(upper)}


class ProductionRuntime:
    def __init__(self, source_root, baseline_root, control_root):
        self.root = Path(source_root).resolve()
        self.baseline_root, self.control_root = Path(baseline_root).resolve(), Path(control_root).resolve()
        if Path(__file__).resolve() != self.root / OWN_FILES[0]:
            raise RuntimeError("Production runner must resolve from its installed pinned checkout path")
        if str(self.root) not in sys.path:
            sys.path.insert(0, str(self.root))
        from pokerlab import matrix_free_river as mf
        from pokerlab import matrix_free_river_tail as tail
        from pokerlab import native_fixed_street as native
        from pokerlab import river_tail_adapter as materialized
        from pokerlab.river_config import RiverConfig
        from scripts import benchmark_river_heldout_quality as baseline
        from scripts import river_heldout_preflight as census
        from scripts import turn_rational_certificate as exact
        from scripts import turn_river_validation as rules
        from scripts import preflop_validation as ranks
        self.mf, self.tail, self.native, self.materialized = mf, tail, native, materialized
        self.config, self.baseline, self.census = RiverConfig, baseline, census
        self.exact, self.rules, self.ranks = exact, rules, ranks
        for module in (mf, tail, native, materialized, baseline, census, exact, rules, ranks,
                       sys.modules[RiverConfig.__module__]):
            if not Path(module.__file__).resolve().is_relative_to(self.root):
                raise RuntimeError("Imported study helper resolved outside the pinned checkout: " + module.__name__)
        self._cap_contract()

    def _cap_contract(self):
        observed = {
            "iterations": self.mf._MAX_ITERATIONS,
            "hand_state_pass_work": self.mf.MAX_HAND_STATE_PASS_WORK,
            "info_action_slots": self.mf.MAX_INFO_ACTION_SLOTS,
            "public_states": self.mf.MAX_PUBLIC_STATES,
            "fallback_pair_checks": self.mf.MAX_FALLBACK_PAIR_CHECKS,
        }
        _same(MF_LIMITS, observed, "Actual matrix-free caps")
        for name in ("_MAX_ITERATIONS", "MAX_HAND_STATE_PASS_WORK", "MAX_INFO_ACTION_SLOTS", "MAX_PUBLIC_STATES", "MAX_FALLBACK_PAIR_CHECKS"):
            if getattr(self.tail, name) != getattr(self.mf, name):
                raise RuntimeError("Tail changed an inherited matrix-free cap: " + name)
        _same(NUMERIC_LIMITS, {key: getattr(self.rules, key) for key in NUMERIC_LIMITS}, "Actual independent numeric caps")
        _same(EXACT_LIMITS, {"work": self.exact.MAX_EXACT_WORK, "depth": self.exact.MAX_EXACT_DEPTH,
                             "fraction_bits": self.exact.MAX_FRACTION_BITS}, "Actual exact caps")
        _same(EXACT_LIMITS, {"work": self.baseline.LIMITS["exact_work"],
                             "depth": self.baseline.LIMITS["exact_depth"],
                             "fraction_bits": self.baseline.LIMITS["exact_fraction_bits"]}, "Generic exact-summary helper caps")
        if self.baseline.TARGET_NASH_CONV != TARGET or self.baseline.FLOAT_TOLERANCE != 1e-9:
            raise RuntimeError("Generic exact-summary target or numeric tolerance differs")

    def baseline_snapshot(self):
        return authenticate_baselines(self.baseline_root, self.control_root)

    def source_snapshot(self, expected_head):
        helper = _retained_helper(self.root, "_mf16_source_helper")
        state = helper._source_snapshot(self.root, self.baseline)
        if state.get("head") != expected_head or state.get("status") != "clean":
            raise RuntimeError("Expected source HEAD/clean status differs")
        extras = OWN_FILES + (CONTROL_HELPER, "scripts/river_heldout_preflight.py",
                              "scripts/benchmark_native_river_range_quality.py")
        for relative in extras:
            path = self.root / relative
            raw = path.read_bytes()
            committed = subprocess.check_output(["git", "-C", str(self.root), "show", f"{expected_head}:{relative}"], stderr=subprocess.STDOUT)
            if _lf(raw) != _lf(committed):
                raise RuntimeError("Required helper/study bytes differ from committed Git blob: " + relative)
            blob = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", f"{expected_head}:{relative}"], text=True).strip()
            state["files"][relative] = {"bytes": len(raw), "raw_sha256": _sha(raw),
                                       "normalized_lf_sha256": _sha(_lf(raw)), "git_blob": blob}
        for relative in ("pokerlab/matrix_free_river.py", "pokerlab/matrix_free_river_tail.py"):
            if relative not in state["files"]:
                raise RuntimeError("Complete source inventory omitted a study solver")
        self._cap_contract()
        return state

    def preflight(self, case, cell):
        board, ranges, worlds, hand_ranks, expected_marginals, physical = _physical_model(self.rules, self.ranks, case)
        from pokerlab import cards as production_cards
        production_ranges = (production_cards.expand_range(case["oop"], board), production_cards.expand_range(case["ip"], board))
        _same([{str(k): v for k, v in r.items()} for r in ranges],
              [{str(k): v for k, v in r.items()} for r in production_ranges], "Production/independent ranges")
        hands = tuple(tuple(side) for side in production_ranges)
        weights = tuple(tuple(side.values()) for side in production_ranges)
        kernel = self.mf.RankedRiverPayoffs(board, hands, weights, pot=case["config"]["pot"], fallback_pair_limit=self.mf.MAX_FALLBACK_PAIR_CHECKS)
        if kernel.compatible_pair_count != len(worlds):
            raise ValueError("Ranked kernel/independent compatible pair counts differ")
        validation_worlds = []
        for world in worlds:
            pair = world["hands"]
            indexes = tuple(kernel.holding_index[p][pair[p]] for p in (0, 1))
            if any(kernel._rank_by_index[p][indexes[p]] != hand_ranks[p][pair[p]] for p in (0, 1)):
                raise ValueError("Kernel cached best-five rank differs from independent evaluator")
            validation_worlds.append((*indexes, float(world["weight"]), world["sign"]))
        kernel.validate_worlds(validation_worlds, pot=case["config"]["pot"])
        marginals = kernel.joint_marginals()
        maximum_error = 0.0
        for p in (0, 1):
            for i, hand in enumerate(kernel.hands[p]):
                error = abs(marginals[p][i] - float(expected_marginals[p].get(hand, Fraction())))
                maximum_error = max(maximum_error, error)
                if error > 1e-15:
                    raise ValueError("Kernel joint marginal differs from global blocker-conditioned physical law")
        config = self.config.from_dict(case["config"])
        counts = {"decision": 0, "terminal": 0, "total": 0}
        def reserve(kind):
            if counts["total"] >= self.mf.MAX_PUBLIC_STATES:
                raise ValueError("Fresh matrix-free public-state admission rejected")
            counts[kind] += 1
            counts["total"] += 1
        proot, _ = self.mf._build_tree(config, allocation_hook=reserve)
        icfg = self.rules._config(case["config"], "config")
        iroot = self.rules._public_tree(board, icfg, icfg, (), worlds)
        isig = self.census._tree_signature(iroot, independent=True, pot=config.pot)
        psig = self.census._tree_signature(proot, independent=False, pot=config.pot)
        _same(isig, psig, "Every public history/action/terminal/refund utility by sign")
        iw = self.census._walk(iroot, independent=True)
        pw = self.census._walk(proot, independent=False)
        if iw[:5] != pw[:5] or counts != {"decision": iw[0], "terminal": iw[1], "total": iw[0] + iw[1]}:
            raise ValueError("Fresh independent and production tree counts differ")
        slots = sum(len(node.actions) * sum(m > 0 for m in marginals[node.player]) for node in pw[5])
        infos = sum(sum(m > 0 for m in marginals[node.player]) for node in pw[5])
        admitted_passes = 3 * cell["iterations"] + 3
        vector_work = max(map(len, hands)) * counts["total"] * admitted_passes
        if slots > self.mf.MAX_INFO_ACTION_SLOTS or vector_work > self.mf.MAX_HAND_STATE_PASS_WORK:
            raise ValueError("Fresh matrix-free full-request vector/action admission rejected")
        numeric_work = len(worlds) * iw[0] * 4
        if numeric_work > self.rules.MAX_ORACLE_WORK:
            raise ValueError("Fresh independent numeric modeled-work admission rejected")
        uniform, policies, _ = self.census._uniform_production_artifact(case, board, proot, worlds, config)
        replay = self.rules.replay_policy(uniform, case["oop"], case["ip"], board=board, config=config)
        uniform.update({m: replay[m] for m in METRICS})
        self.rules.compare_result(uniform, replay, tolerance=1e-9)
        exact_summary, _ = self.baseline._exact_result(iroot, worlds, policies, config, uniform)
        refunds = []
        pending = [iroot]
        while pending:
            node = pending.pop()
            if isinstance(node, self.rules._Decision):
                pending.extend(node.children)
            elif node.kind == "showdown" and node.contributions[0] != node.contributions[1]:
                refunds.append({"contributions": list(node.contributions),
                                "unmatched_refund": abs(node.contributions[0] - node.contributions[1]),
                                "utilities_by_sign": [self.rules._terminal_payoff(node, {"sign": sign, "pot": config.pot}) for sign in (-1, 0, 1)]})
        if not refunds or any(iw[4][name] <= 0 for name in ("check", "bet", "raise", "fold", "call", "all_in")):
            raise ValueError("Frozen game lost required menu/refund coverage")
        materialized_work = len(worlds) * iw[0] * cell["iterations"] * 3
        materialized = {"world_node_work": materialized_work,
                        "world_node_cap": self.materialized.MAX_WORLD_NODE_WORK,
                        "status": "admitted" if materialized_work <= self.materialized.MAX_WORLD_NODE_WORK else "admission-rejected",
                        "solver_called": False}
        try:
            native_shape = self.native.admit_native_shape(counts["total"], len(worlds), slots, cell["iterations"], "cfrplus", reduction="public-batched", hand_counts=(16, 16))
        except ValueError as exc:
            native = {"status": "admission-rejected", "reason": str(exc), "solver_called": False}
        else:
            native = {"status": "admitted", "shape_receipt": native_shape, "solver_called": False}
        return {
            **cell, "range_hand_counts": [16, 16], "compatible_pairs": len(worlds),
            "public_nodes": iw[0], "terminal_nodes": iw[1], "public_states": counts["total"],
            "tree_actions": iw[2], "tree_depth": iw[3], "information_sets": infos,
            "information_action_slots": slots, "admitted_traversal_passes": admitted_passes,
            "hand_state_pass_work": vector_work, "limits": MF_LIMITS,
            "initial_fallback_pair_checks": kernel.fallback_pair_checks,
            "kernel_joint_marginal_max_abs_difference": maximum_error,
            "kernel_cached_ranks_and_pair_masses_validated": True,
            "independent_numeric_modeled_work": numeric_work,
            "independent_physical_model": physical, "complete_tree_signature": isig,
            "unequal_showdown_refunds": refunds, "action_names": dict(iw[4]),
            "uniform_numeric_metrics_capacity_only": {m: replay[m] for m in METRICS},
            "uniform_exact_capacity_only": exact_summary,
            "materialized_original_cap_observation": materialized,
            "native_original_shape_observation": native,
            "solver_trainer_build_backend_calls": 0,
        }

    def call(self, case, cell):
        # Only factorized holding vectors enter the solver. Independent worlds
        # constructed by preflight/audit are never supplied to either API.
        config = self.config.from_dict(case["config"])
        if cell["backend"] == BACKENDS[0]:
            return self.mf.solve_matrix_free_river(case["board"], case["oop"], case["ip"], config,
                                                  iterations=10000, algorithm="cfrplus")
        return self.tail.solve_matrix_free_river_tail(case["board"], case["oop"], case["ip"], config,
                                                      iterations=20000, discard=10000)

    def audit(self, result, case, cell):
        """Generic saved-policy audit for the cell's actual T; no T10000 wrapper."""
        helper = _retained_helper(self.root, "_mf16_audit_tripwires")
        with helper._production_helpers_forbidden() as blocked:
            board, ranges, worlds, _, _, physical = _physical_model(self.rules, self.ranks, case)
            config = self.config.from_dict(case["config"])
            icfg = self.rules._config(case["config"], "config")
            root = self.rules._public_tree(board, icfg, icfg, (), worlds)
            nodes = self.rules._collect_nodes(root)
            oracle = self.rules.replay_policy(result, case["oop"], case["ip"], board=board, config=config)
            differences = self.rules.compare_result(result, oracle, tolerance=1e-9)
            if set(differences) != set(METRICS):
                raise ValueError("Independent replay did not compare all eight metrics")
            policies = self.rules._validate_policy(result, root, nodes, worlds, board, (), runouts_were_omitted=True)
            self.rules._validate_count_metadata(result, world_count=len(worlds), pair_count=len(worlds), info_count=len(policies), board_length=5)
            if (oracle["worlds"] != len(worlds) or oracle["compatible_pair_count"] != len(worlds) or
                    oracle["checked_information_sets"] != len(policies)):
                raise ValueError("Independent physical replay counts differ")
            exact, outcomes = self.baseline._exact_result(root, worlds, policies, config, result)
            exact_numeric = exact_result = None
            if exact["status"] == "admitted":
                fractions = outcomes["scan"]["output"]["metrics"]
                _legal_metric_identities(fractions, tolerance=Fraction())
                exact_numeric = self.baseline._compare_metric_maps(fractions, oracle, "exact-vs-independent numeric")
                exact_result = self.baseline._compare_metric_maps(fractions, result, "exact-vs-serialized result")
            metrics = {m: float(oracle[m]) for m in METRICS}
            interval = _legal_metric_identities(metrics)
        if blocked:
            raise RuntimeError("Independent saved replay called production solve/tree/rank/train/diagnostics")
        return {
            "numeric_metrics": metrics, "numeric_differences": differences,
            "numeric_response_interval": interval, "world_count": len(worlds),
            "compatible_pairs": len(worlds), "information_sets": len(policies),
            "public_decision_nodes": len(nodes), "independent_physical_model": physical,
            "action_rows": result["strategy"], "exact_audit": exact,
            "exact_vs_numeric_differences": exact_numeric,
            "exact_vs_result_differences": exact_result,
            "quality_gate": exact["target_met"] if exact["status"] == "admitted" else None,
            "blocked_production_helper_calls": [],
        }


def _validate_admission(admission, cell):
    for name, expected in cell.items():
        if admission.get(name) != expected or type(admission.get(name)) is not type(expected):
            raise ValueError("Fresh preflight identity differs: " + name)
    for name in ("compatible_pairs", "public_nodes", "terminal_nodes", "public_states", "tree_actions",
                 "tree_depth", "information_sets", "information_action_slots", "admitted_traversal_passes",
                 "hand_state_pass_work", "initial_fallback_pair_checks", "independent_numeric_modeled_work",
                 "solver_trainer_build_backend_calls"):
        if type(admission.get(name)) is not int or admission[name] < 0:
            raise ValueError("Fresh preflight count must be an exact nonnegative integer: " + name)
    if (admission["admitted_traversal_passes"] != 3 * cell["iterations"] + 3 or
            admission["hand_state_pass_work"] != 16 * admission["public_states"] * (3 * cell["iterations"] + 3)):
        raise ValueError("Fresh vector admission did not reserve the full 3T+3 envelope")
    for name, limit in (("hand_state_pass_work", 30000000), ("information_action_slots", 1000000),
                        ("public_states", 250000), ("initial_fallback_pair_checks", 30000000),
                        ("compatible_pairs", 200000), ("independent_numeric_modeled_work", 8000000)):
        if admission[name] > limit:
            raise ValueError("Fresh preflight exceeds unchanged cap: " + name)
    _same(admission.get("limits"), MF_LIMITS, "Fresh matrix-free limits")
    if (admission.get("range_hand_counts") != [16, 16] or
            admission["public_states"] != admission["public_nodes"] + admission["terminal_nodes"] or
            admission["solver_trainer_build_backend_calls"] != 0 or
            admission.get("kernel_cached_ranks_and_pair_masses_validated") is not True):
        raise ValueError("Fresh preflight shape/physical validation metadata differs")
    return admission


def _validate_return(result, case, cell, admission):
    if not isinstance(result, dict):
        raise ValueError("Solver return is not an object")
    if (result.get("algorithm") != "cfrplus" or type(result.get("iterations")) is not int or
            result["iterations"] != cell["iterations"] or "convergence" in result or
            result.get("strategy_schema") != "postflop-strategy-v1" or
            result.get("board") != [case["board"][i:i+2] for i in range(0, 10, 2)]):
        raise ValueError("Solver returned another case/schedule/schema or target-stopping metadata")
    for name, expected in (("config", case["config"]), ("river_config", case["config"]),
                           ("street_configs", {"river": case["config"]}), ("turn_config", None),
                           ("runouts", []), ("reachable_runouts", []), ("runout_mode", "none")):
        if name not in result:
            raise ValueError("Solver omitted configuration/chance metadata: " + name)
        _same(result[name], expected, "Returned configuration/chance field " + name)
    expected_counts = {
        "deals": admission["compatible_pairs"], "compatible_pairs": admission["compatible_pairs"],
        "worlds_materialized": 0, "info_sets": admission["information_sets"],
        "public_nodes": admission["public_nodes"], "public_states": admission["public_states"],
        "terminal_nodes": admission["terminal_nodes"], "public_state_limit": 250000,
        "chance_nodes": 0, "world_traversal_nodes": admission["public_nodes"],
        "tree_actions": admission["tree_actions"],
    }
    for name, expected in expected_counts.items():
        if type(result.get(name)) is not int or result[name] != expected:
            raise ValueError("Solver count differs from fresh independent admission: " + name)
    for name in ("worlds", "compatible_world_count"):
        if name in result:
            if type(result[name]) is not int or result[name] != admission["compatible_pairs"]:
                raise ValueError("Optional physical count alias is invalid: " + name)
    for metric in METRICS:
        value = result.get(metric)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("Solver metric is missing/nonfinite: " + metric)
    if result.get("update_schedule") != "alternating-oop-then-ip":
        raise ValueError("Solver update schedule differs")
    for name, expected in (("backend", "exact-public-chance-tree"),
                           ("terminal_backend", "ranked-river-python"),
                           ("resource_model", "river-hand-vectors-v1")):
        if result.get(name) != expected:
            raise ValueError("Solver backend/resource metadata differs: " + name)
    if not isinstance(result.get("strategy"), list) or not result["strategy"]:
        raise ValueError("Complete saved strategy rows are absent")
    resource = result.get("resource_usage")
    if not isinstance(resource, dict):
        raise ValueError("Solver omitted matrix-free resource provenance")
    expected_resource = {"hand_state_pass_work": admission["hand_state_pass_work"],
                         "info_action_slots": admission["information_action_slots"]}
    for name, expected in expected_resource.items():
        if type(resource.get(name)) is not int or resource[name] != expected:
            raise ValueError("Matrix-free full-request resource count differs: " + name)
    if (type(resource.get("fallback_pair_checks")) is not int or
            not 0 <= resource["fallback_pair_checks"] <= 30000000 or
            type(resource.get("hand_counts")) is not list or
            any(type(v) is not int for v in resource["hand_counts"]) or resource["hand_counts"] != [16, 16]):
        raise ValueError("Matrix-free fallback counter/holding counts are invalid")
    _same(resource.get("limits"), {key: MF_LIMITS[key] for key in
                                  ("hand_state_pass_work", "info_action_slots", "fallback_pair_checks", "public_states")},
          "Returned unchanged matrix-free limits")
    if cell["backend"] == BACKENDS[0]:
        if (result.get("solver_version") != "matrix-free-river-v1" or
                result.get("execution_backend") != "matrix-free-ranked-python" or
                result.get("average_schedule") != "linear-post-sweep-own-reach" or
                type(result.get("training_passes_per_iteration")) is not int or
                result["training_passes_per_iteration"] != 3):
            raise ValueError("Existing matrix-free API metadata differs")
        # The existing API has no T-window/discard/requested-pass/training-call
        # fields. Their absence is preserved; this producer never invents them.
        omitted = ("requested_iterations", "discard", "source_iteration_window", "averaged_sweeps",
                   "average_weight_sum", "requested_regret_passes", "requested_average_passes",
                   "requested_total_traversal_passes", "training_calls")
        if any(name in result for name in omitted):
            raise ValueError("Existing matrix-free API unexpectedly added tail/request metadata")
    else:
        t, d = cell["iterations"], cell["discard"]
        expected = {"requested_iterations": t, "discard": d, "averaged_sweeps": t-d,
                    "average_weight_sum": (t*(t+1)-d*(d+1))//2, "requested_regret_passes": 2*t,
                    "requested_average_passes": t-d, "requested_total_traversal_passes": 3*t-d,
                    "admitted_training_passes_per_iteration": 3, "training_calls": 1}
        for name, value in expected.items():
            if type(result.get(name)) is not int or result[name] != value:
                raise ValueError("Tail original-weight window/pass metadata differs: " + name)
        window = result.get("source_iteration_window")
        if type(window) is not list or any(type(v) is not int for v in window) or window != [d+1, t]:
            raise ValueError("Tail source iteration window differs")
        if (result.get("solver_version") != "research-matrix-free-river-tail-v1" or
                result.get("execution_backend") != "matrix-free-original-weight-river-tail-python" or
                result.get("average_schedule") != "direct-original-linear-sweep-weight-own-reach-tail" or
                type(resource.get("admitted_traversal_passes")) is not int or
                resource["admitted_traversal_passes"] != 3*t+3):
            raise ValueError("Tail backend/admission schedule differs")
    return result


def _descriptive_difference(tail_result, old_result, tail_audit, old_audit):
    def rows(result):
        indexed = {}
        for row in result["strategy"]:
            key = (row["player"], row["hand"], tuple(row["history"]))
            if key in indexed:
                raise ValueError("Descriptive comparison encountered duplicate information row")
            indexed[key] = row
        return indexed
    left, right = rows(tail_result), rows(old_result)
    if set(left) != set(right):
        raise ValueError("Validated policies disagree in own-hand/public-history coverage")
    maximum = 0.0
    for key in left:
        a, b = left[key]["actions"], right[key]["actions"]
        if len(a) != len(b):
            raise ValueError("Validated policies disagree in action count")
        for x, y in zip(a, b):
            for field in ("name", "amount", "raise_to", "history_key"):
                _same(x.get(field), y.get(field), "Descriptive comparison action metadata")
            maximum = max(maximum, abs(float(x["probability"])-float(y["probability"])))
    return {"kind": "descriptive-only-different-schedules-and-budgets",
            "max_absolute_probability_difference": maximum,
            "tail_minus_D0_numeric_metrics": {m: tail_audit["numeric_metrics"][m]-old_audit["numeric_metrics"][m] for m in METRICS}}


def run_with_runtime(runtime, manifest, output, expected_head):
    """Strict four-call lifecycle; injected runtimes permit mocked-only tests."""
    _validate_manifest(manifest)
    if (not isinstance(expected_head, str) or len(expected_head) != 40 or
            any(ch not in "0123456789abcdef" for ch in expected_head)):
        raise ValueError("Expected source HEAD must be an exact lowercase Git commit hash")
    output, root = Path(output).resolve(), Path(runtime.root).resolve()
    protected_roots = [root] + [Path(getattr(runtime, name)).resolve() for name in
                                ("baseline_root", "control_root") if hasattr(runtime, name)]
    if any(output.is_relative_to(parent) for parent in protected_roots):
        raise ValueError("Attempt directory must be outside source and retained baseline/control corpora")
    if output.exists():
        raise FileExistsError(output)
    source, baselines = runtime.source_snapshot(expected_head), runtime.baseline_snapshot()
    cases = {case["id"]: case for case in manifest["cases"]}
    admissions = [_validate_admission(runtime.preflight(cases[cell["case"]], cell), cell)
                  for cell in manifest["calls"]]
    def guards(label):
        _same(source, runtime.source_snapshot(expected_head), "Source " + label)
        _same(baselines, runtime.baseline_snapshot(), "8x8/four-policy/16-control baselines " + label)
    guards("after all four fresh preflights, before claim")
    claim_id = uuid.uuid4().hex
    claim = {"schema": "matrix-free-river-range-quality-claim-v1", "claim_id": claim_id,
             "output": str(output), "source": source, "baselines": baselines,
             "manifest": manifest, "preflight_admissions": admissions,
             "created_utc": datetime.now(timezone.utc).isoformat(), "retry_permitted": False}
    status = {"claim_id": claim_id, "status": "starting", "phase": "claim", "saved_policies": [],
              "completed_audits": [], "retry_permitted": False}
    saved, profiles, active, created = [], [], None, False
    def saved_policy(receipt):
        raw = (output / receipt["file"]).read_bytes()
        if len(raw) != receipt["bytes"] or _sha(raw) != receipt["sha256"]:
            raise RuntimeError("Saved complete raw policy receipt changed")
        result = json.loads(raw.decode("utf-8"))
        if _json_bytes(result) != raw:
            raise RuntimeError("Saved complete raw policy is not canonical UTF-8 JSON")
        return result
    try:
        output.mkdir(parents=True, exist_ok=False)
        created = True
        _exclusive(output / "claim.json", _pretty(claim))
        (output / "policies").mkdir()
        status.update(status="running", phase="training")
        _atomic(output / "status.json", status)
        # Save every complete return first; no metadata/replay/quality gate may
        # suppress another requested fixed-budget call or erase a raw return.
        for index, cell in enumerate(manifest["calls"]):
            active = {**cell, "index": index}
            guards("before call")
            result = runtime.call(cases[cell["case"]], cell)
            raw = _json_bytes(result)
            name = f"{cell['case']}-{cell['backend']}-T{cell['iterations']}-D{cell['discard']}.json"
            _exclusive(output / "policies" / name, raw)
            receipt = {**cell, "file": "policies/" + name, "bytes": len(raw), "sha256": _sha(raw)}
            saved.append(receipt)
            saved_policy(receipt)
            status.update(active_call=active, saved_policies=saved.copy())
            _atomic(output / "status.json", status)
            guards("after call")
        for receipt in saved:
            saved_policy(receipt)
        status.update(phase="independent-audits", active_call=None)
        _atomic(output / "status.json", status)
        audits = {}
        for receipt, admission in zip(saved, admissions):
            guards("before audit")
            result = saved_policy(receipt)
            case = cases[receipt["case"]]
            cell = {key: receipt[key] for key in ("case", "backend", "iterations", "discard")}
            try:
                _validate_return(result, case, cell, admission)
                audit = runtime.audit(result, case, cell)
                if audit.get("world_count") != admission["compatible_pairs"] or audit.get("information_sets") != admission["information_sets"] or audit.get("public_decision_nodes") != admission["public_nodes"]:
                    raise ValueError("Independent replay counts differ from fresh preflight")
                _same(audit.get("independent_physical_model"), admission["independent_physical_model"], "Saved replay/fresh complete independent physical model")
                exact = audit.get("exact_audit", {})
                if exact.get("status") not in ("admitted", "admission-rejected"):
                    raise ValueError("Independent exact audit returned an unknown status")
                audit.update(replay_status="valid", numeric_target_met=float(audit["numeric_metrics"]["nash_conv"]) <= float(TARGET),
                             exact_target_met=exact.get("target_met") if exact["status"] == "admitted" else None)
                if exact["status"] == "admission-rejected" and audit.get("quality_gate") is not None:
                    raise ValueError("Exact capacity rejection must preserve unknown accuracy")
            except Exception as exc:
                audit = {"replay_status": "invalid", "quality_gate": None, "numeric_target_met": None,
                         "exact_target_met": None, "failure_type": type(exc).__name__, "failure": str(exc),
                         "traceback": traceback.format_exc()}
            audits[(receipt["case"], receipt["backend"])] = audit
            profiles.append({**receipt, "independent_audit": audit,
                             "numeric_target_met": audit.get("numeric_target_met"),
                             "exact_target_met": audit.get("exact_target_met")})
            status["completed_audits"].append({"case": receipt["case"], "backend": receipt["backend"], "replay_status": audit["replay_status"]})
            _atomic(output / "status.json", status)
            guards("after audit")
        comparisons = []
        for case in manifest["cases"]:
            guards("before descriptive comparison")
            old, tail = (audits[(case["id"], backend)] for backend in BACKENDS)
            if old["replay_status"] != "valid" or tail["replay_status"] != "valid":
                comparison = {"kind": "unavailable", "reason": "one or both independent saved-policy replays invalid"}
            else:
                receipts = {row["backend"]: row for row in saved if row["case"] == case["id"]}
                try:
                    comparison = _descriptive_difference(saved_policy(receipts[BACKENDS[1]]), saved_policy(receipts[BACKENDS[0]]), tail, old)
                except Exception as exc:
                    comparison = {"kind":"invalid-comparison", "failure_type":type(exc).__name__, "failure":str(exc)}
            comparisons.append({"case": case["id"], **comparison})
        guards("after descriptive comparisons")
        for receipt in saved:
            saved_policy(receipt)
        invalid = any(profile["independent_audit"]["replay_status"] != "valid" for profile in profiles)
        report = {"schema": "matrix-free-river-range-quality-report-v1", "claim_id": claim_id,
                  "status": "completed-with-audit-errors" if invalid else "completed",
                  "source": source, "baselines": baselines, "preflight_admissions": admissions,
                  "profiles": profiles, "descriptive_comparisons": comparisons,
                  "scope": "Two fixed 16x16 river games; T10000 D0 and T20000/D10000 original-weight tails. Different schedules/budgets, descriptive comparisons only; no speed, equal-cost, guaranteed-improvement, commercial-quality or unrestricted NLHE claim.",
                  "completed_utc": datetime.now(timezone.utc).isoformat()}
        _exclusive(output / "report.json", _pretty(report))
        status.update(status=report["status"], phase="done", descriptive_comparisons=comparisons)
        _atomic(output / "status.json", status)
        return report
    except BaseException as exc:
        failure = {"schema": "matrix-free-river-range-quality-failure-v1", "claim_id": claim_id,
                   "status": "failed", "active_call": active, "saved_policies": saved,
                   "failure_type": type(exc).__name__, "failure": str(exc),
                   "traceback": traceback.format_exc(), "retry_permitted": False}
        if created:
            try:
                _exclusive(output / "failure.json", _pretty(failure))
            except BaseException:
                pass
            try:
                status.update(status="failed", phase="failed", failure_type=type(exc).__name__, failure=str(exc), saved_policies=saved)
                _atomic(output / "status.json", status)
            except BaseException:
                pass
        raise


def run(source_root, baseline_root, control_root, output, expected_head):
    runtime = ProductionRuntime(source_root, baseline_root, control_root)
    raw = MANIFEST_PATH.read_bytes()
    if _sha(_lf(raw)) != MANIFEST_LF_SHA256:
        raise RuntimeError("Installed fixed case manifest LF digest differs")
    manifest = json.loads(raw.decode("utf-8"))
    return run_with_runtime(runtime, manifest, output, expected_head)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--baseline-root", required=True, type=Path)
    parser.add_argument("--control-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-source-head", required=True)
    args = parser.parse_args(argv)
    report = run(args.source_root, args.baseline_root, args.control_root, args.output, args.expected_source_head)
    print(json.dumps({"status": report["status"], "policies": len(report["profiles"]),
                      "output": str(args.output.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
