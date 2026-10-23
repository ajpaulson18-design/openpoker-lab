"""Independent T6000 verifier regressions. These tests never train."""
from __future__ import annotations
import copy
import json
import math
import shutil
import unittest
import uuid
from fractions import Fraction
from pathlib import Path
from contextlib import contextmanager
from unittest import mock

from pokerlab import turn_class_vector_budget as budget
from scripts import verify_turn_class_tail_experiment as verifier
from scripts import turn_river_validation as rules
from scripts import turn_three_hand_classes as classes
from scripts import turn_three_hand_reference as reference

REPO = Path(reference.__file__).resolve().parents[1]

@contextmanager
def _scratch(label):
    base = REPO / "work"
    base.mkdir(parents=True, exist_ok=True)
    root = base / ("turn-class-verifier-" + label + "-" + uuid.uuid4().hex)
    root.mkdir(parents=False, exist_ok=False)
    try:
        yield root
    finally:
        resolved = root.resolve()
        if resolved.parent != base.resolve() or not resolved.name.startswith("turn-class-verifier-"):
            raise ValueError("Unsafe scratch cleanup target")
        shutil.rmtree(resolved)

def _rows(game):
    worlds, root = game[3], game[5]
    rows = []
    for node in rules._collect_nodes(root):
        player = node.player
        hands = sorted({w["hands"][player] for w in worlds
                        if w["board"][:len(node.board)] == node.board
                        and not (set(w["hands"][player]) & set(node.board))})
        for hand in hands:
            legal = rules._row_actions(node)
            rows.append({"player": "oop" if player == 0 else "ip", "hand": "".join(hand),
                         "street": "turn" if len(node.board) == 4 else "river",
                         "board": list(node.board), "history": list(node.history),
                         "actions": [dict(a, probability=1.0 if i == 0 else 0.0)
                                     for i, a in enumerate(legal)]})
    return rows

def _usage(plan):
    components, caps = dict(plan["components"]), dict(plan["storage_caps"])
    return {
        "ordinary_physical_reference": {
            "world_node_work": 396 * 32 * 18_000, "world_node_work_limit": 30_000_000,
            "world_node_work_would_admit": False,
            "dense_hand_state_pass_work": 3 * 3039 * 18_003,
            "dense_hand_state_pass_work_limit": 30_000_000,
            "dense_hand_state_pass_work_would_admit": False, "enforced": False},
        "info_action_slots": 8046, "info_action_slots_limit": 1_000_000,
        "prefix_hand_edges": 405, "prefix_hand_edge_limit": 250_000,
        **{k: plan[k] for k in ("physical_world_iterations", "candidate_pair_iterations",
          "compact_world_proxy", "compact_dense_proxy", "legacy_physical_world_proxy",
          "legacy_proxy_enforced", "trainer_vector_work", "complete_vector_work",
          "one_time_work_reserve", "explicit_list_writes")},
        "component_charge_note": ("Component allowances are source-derived modeled work reservations; observed counts "
          "contain adapter-owned logical traversal counts only. Neither is measured runtime, bytes, or RSS."),
        "resource_accounting": {"planned": components, "reserved": dict(components),
          "observed": {k: 0 for k in components}, "storage_caps": caps,
          "storage_reserved": dict(caps), "storage_observed": {k: 0 for k in caps}},
    }

def _payload():
    fixture = reference.FIXTURE
    game = reference.model()
    plan = budget.plan_request(6000, 2000, "turn-seven-class-vector-v1")
    board = list(rules.cards(fixture["board"]))
    runouts = [card for card in rules.DECK if card not in board]
    config = copy.deepcopy(fixture["config"])
    payload = {
      "method": "Direct original-weight CFR+ tail averaging on seven exact public-river classes",
      "algorithm": "cfrplus", "solver_version": "research-turn-seven-class-tail-adapter-v1",
      "strategy_schema": "postflop-strategy-v1", "backend": "exact-public-chance-tree",
      "execution_backend": "direct-original-weight-seven-class-tail-python",
      "diagnostics_backend": "public-batched-python", "board": board,
      "config": config, "street_configs": {"turn": config, "river": config},
      "turn_config": config, "river_config": config, "runouts": runouts,
      "reachable_runouts": runouts, "runout_mode": "full-deck",
      "chance_note": "Class masses derive from the original rational joint law; all 48 physical rivers are restored in the output policy.",
      "iterations": 6000, "requested_iterations": 6000, "discard": 2000,
      "source_iteration_window": [2001, 6000], "averaged_sweeps": 4000,
      "average_weight_sum": 16_002_000,
      "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
      "update_schedule": "alternating-oop-then-ip", "requested_regret_passes": 12_000,
      "requested_average_passes": 4000, "requested_total_traversal_passes": 16_000,
      "deals": 9, "compatible_pairs": 9, "worlds": 396, "worlds_materialized": 396,
      "info_sets": 3606, "public_nodes": 1254, "public_states": 3039,
      "terminal_nodes": 1780, "chance_nodes": 5, "world_traversal_nodes": 32,
      "tree_actions": 2798, "public_state_limit": 250_000, "public_node_limit": 10_000,
      "public_batch_edge_limit": 250_000, "resource_model": "turn-seven-class-vector-v1",
      "physical_representation": {"worlds": 396, "rivers": 48, "public_states": 3039,
                                   "policy_rows": 3606, "action_slots": 8046},
      "training_representation": {"worlds": 45, "river_classes": 7, "public_states": 456,
                                   "policy_rows": 486, "action_slots": 1086},
      "modeled_rank_inputs": 276, "modeled_rank_loop_cells": plan["modeled_rank_loop_cells"],
      "pot": 100.0, "effective_stack": 220.0,
      "scope": ("Fixed three-hand turn game using a globally lossless seven-class public-river "
        "representation; full physical policy rows are restored before diagnostics. No preflop, "
        "multiway, rake, unrestricted no-limit, or exact-equilibrium claim."),
      "diagnostic_provenance": ("Fresh full-physical public-batched profile and best-response diagnostics on "
        "the lifted policy; numeric convergence diagnostics are not an exact certificate."),
      "training_calls": 1, "strategy": _rows(game), "resource_usage": _usage(plan),
    }
    numeric = rules.replay_policy(payload, fixture["oop"], fixture["ip"],
        board=fixture["board"], config=fixture["config"])
    for key in verifier.METRICS:
        payload[key] = numeric[key]
    return payload

class TurnClassTailVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()
        with mock.patch("pokerlab.turn_tail_adapter._train_original_weight_tail",
                        side_effect=AssertionError("training called")), \
             mock.patch("pokerlab.postflop_solver._build_postflop_tree",
                        side_effect=AssertionError("production tree builder called")), \
             mock.patch("pokerlab.public_diagnostics.evaluate_profile",
                        side_effect=AssertionError("production evaluator called")):
            cls.audit = verifier.audit_payload(cls.payload, root=REPO)

    def test_metadata_and_fixed_admission(self):
        plan = verifier.validate_metadata(self.payload)
        self.assertEqual(plan["setup_component_total"], 1_970_224)
        self.assertEqual(plan["complete_vector_work"], 452_960_288)
        for field, value in (("discard", 2001), ("requested_iterations", True)):
            bad = copy.deepcopy(self.payload); bad[field] = value
            with self.assertRaises(ValueError): verifier.validate_metadata(bad)
        bad = copy.deepcopy(self.payload); bad["resource_usage"]["trainer_vector_work"] += 1
        with self.assertRaises(ValueError): verifier.validate_metadata(bad)

    def test_full_plan_reservations_are_required(self):
        bad = copy.deepcopy(self.payload)
        bad["resource_usage"]["resource_accounting"]["reserved"]["class_mapping"] = 0
        with self.assertRaises(ValueError): verifier.validate_metadata(bad)

    def test_independent_synthetic_class_constant_audit_without_production_helpers(self):
        result = self.audit
        exact = {k: Fraction(v) for k, v in result["exact_metrics_fractions"].items()}
        self.assertEqual(set(exact), set(verifier.METRICS))
        self.assertEqual(exact["value_ip"], -exact["value_oop"])
        self.assertEqual(exact["nash_conv"], exact["oop_best_response_gain"] + exact["ip_best_response_gain"])
        self.assertEqual(exact["exploitability"] * 2, exact["nash_conv"])
        self.assertEqual(result["class_audit"]["training_calls"], 0)
        self.assertEqual(result["target_met"], exact["nash_conv"] <= verifier.TARGET)

    def test_producer_bundle_matches_independent_verifier_on_cached_synthetic_audit(self):
        from scripts import benchmark_turn_class_tail as experiment
        experiment._validate_payload(self.payload)
        self.assertEqual(experiment.REQUIRED_SOURCES, verifier.REQUIRED_SOURCES)
        numeric, differences = experiment._numeric_gate(self.payload, self.audit["class_audit"])
        policy = experiment.canonical(self.payload)
        commit, pins = "a" * 40, {"source.py": "b" * 64}
        report = experiment._build_report(
            commit, pins, self.payload, self.audit["class_audit"], numeric,
            differences, self.audit["old_baseline"], policy, 1.0, 2.0)
        with _scratch("producer-contract") as root:
            with mock.patch.object(experiment, "_guard"), \
                 mock.patch.object(verifier, "_head", return_value=commit), \
                 mock.patch.object(verifier, "verify_source_map", return_value=(commit, pins)), \
                 mock.patch.object(verifier, "audit_payload", return_value=self.audit) as audit:
                experiment._publish(root, experiment.canonical(report), policy, commit, (), {})
            self.assertEqual(audit.call_count, 2)
            self.assertEqual(experiment.targets(root)["policy"].read_bytes(), policy)
            self.assertEqual(experiment.targets(root)["report"].read_bytes(), experiment.canonical(report))

    def test_exact_and_numeric_corruption_is_rejected(self):
        metrics = {k: Fraction(v) for k, v in self.audit["exact_metrics_fractions"].items()}
        numeric = self.audit["numeric_oracle_metrics"]
        verifier._compare_metrics(metrics, numeric)
        for bad in (dict(metrics, nash_conv=metrics["nash_conv"] + 1),
                    {k: v for k, v in metrics.items() if k != "value_ip"}):
            with self.assertRaises(ValueError): verifier._compare_metrics(bad, numeric)
        bad_numeric = dict(numeric); bad_numeric["value_oop"] += 1e-6
        with self.assertRaises(ValueError): verifier._compare_metrics(metrics, bad_numeric)
        bad_numeric["value_oop"] = math.nan
        with self.assertRaises(ValueError): verifier._compare_metrics(metrics, bad_numeric)

    def test_one_physical_river_class_deviation_fails_independent_class_audit(self):
        bad = copy.deepcopy(self.payload)
        row = next(r for r in bad["strategy"] if r["street"] == "river" and len(r["actions"]) > 1)
        row["actions"][0]["probability"], row["actions"][1]["probability"] = 0.0, 1.0
        with self.assertRaises(ValueError):
            classes.audit_policy(bad, classes.build_model(reference.model()), chance_grouping="both")

    def test_malformed_rows_and_noncanonical_report_json_reject(self):
        bad = copy.deepcopy(self.payload); bad["strategy"].pop()
        with self.assertRaises(ValueError): verifier.validate_metadata(bad)
        bad = copy.deepcopy(self.payload); bad["strategy"][0]["actions"][0]["probability"] = math.inf
        with self.assertRaises(ValueError):
            classes.audit_policy(bad, classes.build_model(reference.model()), chance_grouping="both")
        for raw in (b'{"x": 1}\n', b'{"x": 1.0}\r\n'):
            with self.assertRaises(ValueError): verifier._object(raw)

    def test_historical_baseline_is_recomputed_and_remains_a_miss(self):
        old = self.audit["old_baseline"]
        self.assertTrue(old["threshold_miss"])
        self.assertEqual(old["policy_sha256"], verifier.OLD_IDENTITIES[verifier.OLD_POLICY][1])

    def _fake_source_root(self, root, commit):
        modules = ["pokerlab/turn_class_tail_adapter.py", "pokerlab/turn_class_vector_budget.py"]
        names = sorted(set(modules) | set(verifier.REQUIRED_SOURCES))
        frozen = {}
        for name in names:
            raw = ("fixed " + name + "\n").encode()
            frozen[name] = raw
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        pins = {n: verifier.sha(verifier._normalized(n, raw)) for n, raw in frozen.items()}
        report = {"training_source_git_commit": commit, "generation_head": commit, "source_sha256": pins}
        def fake_git(_root, *args):
            if args[0] == "cat-file": return b"commit"
            if args[0] == "ls-tree": return ("\n".join(modules) + "\n").encode()
            if args[0] == "show": return frozen[args[1].split(":", 1)[1]]
            raise AssertionError("unexpected git command " + repr(args))
        return report, pins, frozen, mock.patch.object(verifier, "_git", side_effect=fake_git)

    def test_frozen_commit_and_current_source_bytes_are_pinned(self):
        with _scratch("source") as root:
            commit = "a" * 40
            report, pins, _, gitpatch = self._fake_source_root(root, commit)
            with gitpatch, mock.patch.object(verifier.subprocess, "run"):
                self.assertEqual(verifier.verify_source_map(root, report), (commit, pins))
                (root / "scripts/turn_three_hand_reference.py").write_bytes(b"changed\n")
                with self.assertRaises(ValueError): verifier.verify_source_map(root, report)
                with self.assertRaises(ValueError):
                    verifier.verify_source_map(root, dict(report, generation_head="bad"))

    def test_added_unpinned_pokerlab_module_is_source_inventory_drift(self):
        with _scratch("inventory") as root:
            report, _, _, gitpatch = self._fake_source_root(root, "b" * 40)
            with gitpatch, mock.patch.object(verifier.subprocess, "run"):
                verifier.verify_source_map(root, report)
                (root / "pokerlab/untracked_extra.py").write_text("# extra\n", encoding="utf-8")
                with self.assertRaises(ValueError): verifier.verify_source_map(root, report)

    def _bundle(self, root, stage_name=".turn-class.stage"):
        folder = root / "benchmarks/results"; folder.mkdir(parents=True, exist_ok=True)
        policy = verifier.canonical({"synthetic": "serialized"})
        (folder / verifier.POLICY_NAME).write_bytes(policy)
        commit, pins = "c" * 40, {"scripts/fixed.py": "d" * 64}
        observed = {"numeric_oracle_metrics": {}, "exact_numeric_differences": {},
          "class_audit": {}, "exact_metrics_fractions": {}, "exact_value_interval": {"lower": "0", "upper": "0"},
          "target_nash_conv_fraction": str(verifier.TARGET), "target_met": False,
          "threshold_miss": True, "old_baseline": {}}
        report = {"schema": verifier.SCHEMA, "schema_version": 1, "generation_head": commit,
          "training_source_git_commit": commit, "source_sha256": pins, "python": "test",
          "platform": "test", "fixture_id": verifier.FIXTURE["id"], "fixture": verifier.FIXTURE,
          "request": verifier.REQUEST, "completed_training_calls": 1, "policy_file": verifier.POLICY_NAME,
          "policy_sha256": verifier.sha(policy), "policy_bytes": len(policy), **observed,
          "complete_api_json_seconds": 0.1, "independent_math_audit_seconds": 0.2, "scope": verifier.SCOPE,
          "verification_scope": verifier.VERIFICATION_SCOPE}
        path = folder / stage_name; path.write_bytes(verifier.canonical(report))
        return path, folder / verifier.POLICY_NAME, report, observed, commit, pins

    def test_staged_report_is_accepted_without_training(self):
        with _scratch("stage") as root:
            path, _, report, observed, commit, pins = self._bundle(root)
            with mock.patch.object(verifier, "_head", return_value=commit), \
                 mock.patch.object(verifier, "verify_source_map", return_value=(commit, pins)), \
                 mock.patch.object(verifier, "audit_payload", return_value=observed) as audit:
                self.assertEqual(verifier.verify_saved_artifact(path=path, root=root), report)
            audit.assert_called_once()

    def test_unsafe_and_oversize_paths_are_rejected_before_json_parse(self):
        with _scratch("path") as root:
            outside = root / "outside.json"; outside.write_bytes(b"{}\n")
            with self.assertRaises(ValueError): verifier.verify_saved_artifact(path=outside, root=root)
            folder = root / "benchmarks/results"; folder.mkdir(parents=True)
            huge = folder / "huge.json"; huge.write_bytes(b" " * (verifier.BYTE_CAP + 1))
            with mock.patch.object(verifier, "_object", side_effect=AssertionError("oversize parsed")):
                with self.assertRaises(ValueError): verifier.verify_saved_artifact(path=huge, root=root)
            stage, policy, _, _, _, _ = self._bundle(root, stage_name=".policy-cap.stage")
            policy.write_bytes(b"x" * (verifier.BYTE_CAP + 1))
            real_object = verifier._object
            with mock.patch.object(verifier, "_object", wraps=real_object) as parse:
                with self.assertRaises(ValueError): verifier.verify_saved_artifact(path=stage, root=root)
            self.assertEqual(parse.call_count, 1)  # report parsed; oversize policy rejected before parse

    def test_head_bundle_and_source_drift_after_read_are_rejected(self):
        with _scratch("drift") as root:
            path, policy_path, _, observed, commit, pins = self._bundle(root)
            with mock.patch.object(verifier, "_head", side_effect=[commit, "e" * 40]), \
                 mock.patch.object(verifier, "verify_source_map", return_value=(commit, pins)), \
                 mock.patch.object(verifier, "audit_payload", return_value=observed):
                with self.assertRaises(ValueError): verifier.verify_saved_artifact(path=path, root=root)
            with _scratch("source-after-read") as source_root:
                source_report, source_pins, _, gitpatch = self._fake_source_root(source_root, commit)
                path, _, report, observed, _, _ = self._bundle(source_root)
                report["training_source_git_commit"] = source_report["training_source_git_commit"]
                report["generation_head"] = source_report["generation_head"]
                report["source_sha256"] = source_pins
                path.write_bytes(verifier.canonical(report))
                changed = source_root / "scripts/turn_three_hand_reference.py"
                def mutate_source(*_args, **_kwargs):
                    changed.write_bytes(b"changed after initial source snapshot\n")
                    return observed
                with gitpatch, mock.patch.object(verifier.subprocess, "run"), \
                     mock.patch.object(verifier, "_head", return_value=commit), \
                     mock.patch.object(verifier, "audit_payload", side_effect=mutate_source):
                    with self.assertRaises(ValueError): verifier.verify_saved_artifact(path=path, root=source_root)
            with mock.patch.object(verifier, "_head", return_value=commit), \
                 mock.patch.object(verifier, "verify_source_map", return_value=(commit, pins)), \
                 mock.patch.object(verifier, "audit_payload", side_effect=lambda *_a, **_k: (policy_path.write_bytes(b"changed"), observed)[1]):
                with self.assertRaises(ValueError): verifier.verify_saved_artifact(path=path, root=root)

if __name__ == "__main__":
    unittest.main()
