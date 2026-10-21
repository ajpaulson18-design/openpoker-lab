"""Contract and corruption controls for the frozen alternating protocol.

These tests exercise admission, numeric replay and evidence bookkeeping. They never run a
solver, rank cards, or prepare the independent physical oracle.
"""
import copy
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from fractions import Fraction


REPO = Path(__file__).resolve().parents[1]
STAGING = REPO.parent
from scripts import benchmark_flop_alternating as runner


def frozen_spec():
    raw = (REPO / "benchmarks/weighted-full-deck-flop-alternating-v1.json").read_bytes()
    return json.loads(raw)


def candidate(method_id, probability=0.5):
    spec = frozen_spec()
    method = runner._method_spec(spec, method_id)
    payload = {
        "algorithm": method["solver_algorithm"],
        "iterations": 140,
        "strategy_schema": "postflop-strategy-v1",
        "execution_backend": "public-batched-python",
        "plan_operation_limit": None,
        "public_batch_edge_limit": 250_000,
        "update_schedule": "alternating-oop-then-ip",
        "training_passes_per_iteration": 3,
        "board": ["2c", "3d", "4h"],
        "runout_mode": "full-deck",
        "worlds": 5940,
        "config": copy.deepcopy(spec["config"]),
        "value_oop": 0.0,
        "value_ip": 0.0,
        "oop_best_response_value": 0.0,
        "ip_best_response_value": 0.0,
        "oop_best_response_gain": 0.0,
        "ip_best_response_gain": 0.0,
        "nash_conv": 0.0,
        "exploitability": 0.0,
        "strategy": [{
            "player": "oop", "hand": "AdAs", "street": "flop",
            "board": ["2c", "3d", "4h"], "history": [],
            "actions": [{"name": "check", "history_key": "check",
                         "amount": 0.0, "raise_to": 0.0,
                         "probability": probability},
                        {"name": "bet", "amount": 5.0, "raise_to": 5.0,
                         "history_key": "bet@5",
                         "probability": 1.0 - probability}],
        }],
    }
    if method_id == "cfrplus-control":
        payload.update({"solver_version": "configured-postflop-v1",
                        "average_schedule": "linear-post-sweep-own-reach"})
    else:
        payload.update({
            "solver_version": "configured-postflop-alternating-v1",
            "average_schedule": method["average_schedule"],
            "regret_schedule": method["regret_schedule"],
            "regret_floor": method["regret_floor"],
            "training_kernel": method["training_kernel"],
        })
    return payload


class AlternatingBenchmarkTests(unittest.TestCase):
    def test_spec_protocol_is_exact_and_tampering_is_rejected(self):
        spec = frozen_spec()
        digest = runner._checksum(spec)
        self.assertEqual(runner.validate_spec(spec, expected_digest=digest), spec)
        altered = copy.deepcopy(spec)
        altered["iterations"] = 280
        with self.assertRaisesRegex(ValueError, "hash changed"):
            runner.validate_spec(altered, expected_digest=digest)
        self.assertEqual(spec["expected"]["worlds"], 5940)
        self.assertEqual(spec["expected"]["max_world_node_iterations"], 29_937_600)
        self.assertEqual(spec["training_passes_per_iteration"], 3)
        self.assertEqual(len(spec["method_orders"]), 3)
        self.assertNotIn("source_freeze", spec)
        self.assertNotIn("SOURCE_REVISION", vars(runner))
        self.assertNotIn("SOURCE_MANIFEST_SHA256", vars(runner))
        self.assertNotIn("PUBLISHED_INDEX_SHA256", vars(runner))

    def test_recorded_measurement_identity_is_not_a_future_checkout_pin(self):
        historical = {"revision": "a" * 40, "status": [],
                      "source_hashes": {"scripts/runner.py": {
                          "raw_sha256": "a" * 64, "lf_sha256": "b" * 64}}}
        runner._validate_recorded_source(historical, copy.deepcopy(historical))
        current = {"revision": "c" * 40, "status": [],
                   "source_hashes": {"scripts/runner.py": {
                       "raw_sha256": "d" * 64, "lf_sha256": "e" * 64}}}
        with patch.object(runner, "_source_snapshot", return_value=current):
            runner._require_source_unchanged(current)
        with patch.object(runner, "_source_snapshot", return_value={**current,
                                                                       "revision": "changed-during-check"}):
            with self.assertRaisesRegex(ValueError, "changed during benchmark"):
                runner._require_source_unchanged(current)
        dirty = {**historical, "status": [" M scripts/runner.py"]}
        with self.assertRaisesRegex(ValueError, "dirty or changed"):
            runner._validate_recorded_source(dirty, dirty)
        # A captured manifest may grow in a later checkout; record validity is
        # typed and bounded without requiring today's inventory to match it.
        large = {"revision": "f" * 40, "status": [], "source_hashes": {
            f"src/module_{index}.py": {"raw_sha256": "1" * 64,
                                       "lf_sha256": "2" * 64}
            for index in range(602)}}
        runner._validate_recorded_source(large, copy.deepcopy(large))
        for bad in (
            {**historical, "revision": "old-commit"},
            {**historical, "status": False},
            {"revision": "a" * 40, "status": [], "source_hashes": {"../escape.py": historical["source_hashes"]["scripts/runner.py"]}},
            {"revision": "a" * 40, "status": [], "source_hashes": {"x.py": {"raw_sha256": "short", "lf_sha256": "b" * 64}}},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                runner._validate_recorded_source(bad, bad)

    def test_saved_verification_refuses_live_source_drift(self):
        expected = {"revision": "frozen", "source_hashes": {"x": "a"}}
        with patch.object(runner, "_source_snapshot",
                          return_value={"revision": "changed", "source_hashes": {"x": "b"}}):
            with self.assertRaisesRegex(ValueError, "Source changed"):
                runner._require_source_unchanged(expected)

    def test_saved_header_requires_terminal_complete_phase(self):
        spec = frozen_spec()
        report = {
            "schema_version": 1, "benchmark_id": spec["benchmark_id"],
            "specification": spec, "spec_sha256": "a" * 64,
            "source_before": {}, "created_at_utc": "2026-10-21T12:00:00+00:00",
            "runtime": {"python": "3.12", "executable": "python", "platform": "test"},
            "execution_state": {"mode": "direct-call", "system_required": False},
            "samples": [], "separate_allocation_calls": [], "validation_errors": [],
            "phase": "complete", "baseline": {}, "preflight": {},
            "oracle_forbidden_production_calls": {}, "oracle_physical_evidence": {},
            "production_physical_evidence": {}, "summary": [], "final_quality": [],
            "cross_method_diagnostics": {}, "quality_gate_met": False,
            "status": "quality-miss", "source_after": {},
            "finished_at_utc": "2026-10-21T12:01:00+00:00", "artifact_sha256": "b" * 64,
        }
        with patch.object(runner, "SPEC_SHA256", "a" * 64):
            runner._validate_saved_header(report, spec)
            for key, value in (("phase", "saved-policy-reconstruction"),
                               ("status", True), ("quality_gate_met", 0),
                               ("execution_state", {"mode": "direct-call", "system_required": 0})):
                bad = copy.deepcopy(report)
                bad[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    runner._validate_saved_header(bad, spec)
            active = copy.deepcopy(report)
            active["active_request"] = {"method": "lcfr", "iterations": 10}
            with self.assertRaisesRegex(ValueError, "report fields changed"):
                runner._validate_saved_header(active, spec)

    def test_real_fixed_game_preflight_never_ranks_or_trains(self):
        from contextlib import ExitStack
        from pokerlab import cards, postflop_solver, alternating_public_cfr
        targets = [(cards, name) for name in ("expand_range", "rank_hand")]
        targets += [(postflop_solver, name) for name in (
            "expand_range", "rank_hand", "_enumerate_worlds", "solve_postflop")]
        targets += [(alternating_public_cfr, name) for name in (
            "train_public_lcfr", "train_public_alternating_dcfr")]
        with ExitStack() as stack:
            for module, name in targets:
                stack.enter_context(patch.object(module, name, side_effect=AssertionError(
                    "Rank-free admission called " + name)))
            admission = runner.preflight(runner.load_spec())
        self.assertEqual(admission["requested_calls"], 12)
        self.assertEqual(admission["census"]["worlds"], 5940)
        self.assertEqual(admission["census"]["max_world_node_iterations"], 29_937_600)
        self.assertEqual(admission["census"]["public_prefix_hand_edges"], 6078)
        self.assertEqual({row["training_passes_per_iteration"]
                          for row in admission["requests"]}, {3})

    def test_all_nine_timed_and_three_trace_requests_preflight_before_oracle(self):
        spec = frozen_spec()
        census = copy.deepcopy(spec["expected"])
        census["max_world_iterations"] = 831_600
        production = type("Production", (), {"_MAX_WORLD_NODE_WORK": 30_000_000})
        validate_spec = runner.validate_spec
        digest = runner._checksum(spec)
        with patch.object(runner, "SPEC_SHA256", digest), \
                patch.object(runner, "_rank_free_census", return_value=census) as rank_free, \
                patch.object(runner, "_source_modules",
                             return_value=(None, production, None, None, None)):
            result = runner.preflight(spec)
        self.assertEqual(rank_free.call_args_list[0].args, (140,))
        self.assertEqual([c.args[0] for c in rank_free.call_args_list],
                         [140, 10, 10, 10])
        self.assertEqual(result["requested_calls"], 12)
        self.assertEqual(len(result["requests"]), 12)
        self.assertEqual(sum(r["kind"] == "timed" for r in result["requests"]), 9)
        self.assertEqual(sum(r["kind"] == "allocation" for r in result["requests"]), 3)
        self.assertTrue(all(r["training_passes_per_iteration"] == 3
                            for r in result["requests"]))
        self.assertTrue(all(r["world_node_iterations"] <= 30_000_000
                            for r in result["requests"]))

    def test_candidate_metadata_and_invalid_probabilities_are_checked(self):
        spec = frozen_spec()
        for method_id in runner.METHOD_IDS:
            payload = candidate(method_id)
            runner._check_candidate(payload, spec, method_id, 140)
            bad = copy.deepcopy(payload)
            bad["training_passes_per_iteration"] = 1
            with self.assertRaisesRegex(ValueError, "training_passes"):
                runner._check_candidate(bad, spec, method_id, 140)
            bad = copy.deepcopy(payload)
            bad["training_passes_per_iteration"] = 3.0
            with self.assertRaisesRegex(ValueError, "training_passes"):
                runner._check_candidate(bad, spec, method_id, 140)
            bad = copy.deepcopy(payload)
            bad["iterations"] = 140.0
            with self.assertRaisesRegex(ValueError, "iterations"):
                runner._check_candidate(bad, spec, method_id, 140)
            bad = copy.deepcopy(payload)
            bad["strategy"][0]["actions"][0]["probability"] = float("nan")
            with self.assertRaisesRegex(ValueError, "probability"):
                runner._check_candidate(bad, spec, method_id, 140)
            bad = copy.deepcopy(payload)
            del bad["strategy"][0]["actions"][0]["raise_to"]
            with self.assertRaisesRegex(ValueError, "numeric fields"):
                runner._check_candidate(bad, spec, method_id, 140)
            bad = copy.deepcopy(payload)
            bad["strategy"][0]["actions"][0]["amount"] = True
            with self.assertRaisesRegex(ValueError, "numeric fields"):
                runner._check_candidate(bad, spec, method_id, 140)
            bad = copy.deepcopy(payload)
            bad["strategy"][0]["extra"] = "private-card-leak"
            with self.assertRaisesRegex(ValueError, "strategy row"):
                runner._check_candidate(bad, spec, method_id, 140)
        delayed = candidate("lcfr")
        delayed["averaging_delay"] = 10
        with self.assertRaisesRegex(ValueError, "No averaging delay"):
            runner._check_candidate(delayed, spec, "lcfr", 140)

    def test_saved_run_census_is_complete_and_rejects_boolean_counters(self):
        spec = frozen_spec()
        methods = {row["id"]: row["solver_algorithm"] for row in spec["algorithms"]}
        stamp = "2026-10-21T12:00:00+00:00"

        def sample(method, repeat):
            iterations = spec["iterations"]
            payload_sha = (spec["baseline"]["zero_cfrplus_140_public_batched_payload_sha256"]
                           if method == "cfrplus-control" else "a" * 64)
            return {
                "kind": "timed", "method": method, "algorithm": methods[method],
                "iterations": iterations, "repeat": repeat,
                "started_at_utc": stamp, "elapsed_seconds": 1.25,
                "finished_at_utc": stamp, "file": f"{runner._method_file_slug(method)}-{iterations}-{repeat}.json.gz",
                "raw_bytes": 100, "gzip_bytes": 50, "payload_sha256": payload_sha,
                "gzip_sha256": "b" * 64, "independent_replay": {},
                "forbidden_production_calls": {},
            }

        timed = [sample(method, repeat) for method, repeat in runner._expected_timed_order(spec)]
        allocations = []
        for method in spec["separate_allocation_calls"]["methods"]:
            iterations = spec["separate_allocation_calls"]["iterations"]
            allocations.append({
                "kind": "allocation", "method": method, "algorithm": methods[method],
                "iterations": iterations, "started_at_utc": stamp,
                "finished_at_utc": stamp, "python_traced_peak_bytes": 1234,
                "file": f"allocation-{runner._method_file_slug(method)}.json.gz",
                "raw_bytes": 100, "gzip_bytes": 50, "payload_sha256": "c" * 64,
                "gzip_sha256": "d" * 64, "independent_replay": {},
                "forbidden_production_calls": {},
            })

        runner._validate_run_census(timed, allocations, spec)
        variants = []
        bad = copy.deepcopy(timed); bad[0]["iterations"] = True; variants.append((bad, allocations))
        bad = copy.deepcopy(timed); bad[0]["repeat"] = True; variants.append((bad, allocations))
        bad = copy.deepcopy(timed); bad[0]["kind"] = True; variants.append((bad, allocations))
        bad = copy.deepcopy(timed); bad[0]["algorithm"] = "vanilla"; variants.append((bad, allocations))
        bad = copy.deepcopy(timed); bad.pop(); variants.append((bad, allocations))
        bad_alloc = copy.deepcopy(allocations); bad_alloc[0]["iterations"] = True
        variants.append((timed, bad_alloc))
        bad_alloc = copy.deepcopy(allocations); bad_alloc[0]["kind"] = "timed"
        variants.append((timed, bad_alloc))
        bad_alloc = copy.deepcopy(allocations); bad_alloc[0]["python_traced_peak_bytes"] = True
        variants.append((timed, bad_alloc))
        for index, (bad_timed, bad_allocations) in enumerate(variants):
            with self.subTest(index=index), \
                    self.assertRaises(ValueError):
                runner._validate_run_census(bad_timed, bad_allocations, spec)

    def test_control_payload_pin_is_rechecked_during_saved_summary(self):
        spec = frozen_spec()
        payload = candidate("cfrplus-control")
        digest = runner._canonical(payload)
        import hashlib
        expected = hashlib.sha256(digest).hexdigest()
        spec["baseline"]["zero_cfrplus_140_public_batched_payload_sha256"] = expected
        runner._check_control_payload_hash(payload, spec, "cfrplus-control", 140)
        runner._check_control_payload_hash(payload, spec, "cfrplus-control", 10)
        payload["value_oop"] = 0.25
        with self.assertRaisesRegex(ValueError, "CFR\\+ control"):
            runner._check_control_payload_hash(payload, spec, "cfrplus-control", 140)

    def test_actual_immutable_cfrplus_payload_matches_exact_config_and_pin(self):
        spec = frozen_spec()
        payload_path = (runner.ROOT / "benchmarks" / "results" /
                        "weighted-full-deck-flop-delayed-cfrplus-v1" /
                        "cfrplus-140-delay-0-public-batched-1.json.gz")
        raw = gzip.decompress(payload_path.read_bytes())
        payload = json.loads(raw)
        self.assertEqual(payload["config"], spec["config"])
        self.assertIs(type(payload["config"]["pot"]), float)
        self.assertIs(type(payload["config"]["effective_stack"]), float)
        runner._check_candidate(payload, spec, "cfrplus-control", 140)
        runner._check_control_payload_hash(payload, spec, "cfrplus-control", 140)

    def test_producer_physical_comparison_adapts_scalar_iterations_without_ranking(self):
        from fractions import Fraction
        from scripts import benchmark_weighted_full_deck_flop as base
        spec = {
            "iterations": 140, "board": "2c3d4h", "oop_range": "AsAd:1",
            "ip_range": "KdKs:1",
            "expected": {"worlds": 1, "compatible_pairs": 1},
        }
        oracle = {"worlds": [("AdAs", "KdKs", Fraction(1), 0,
                              ("2c", "3d", "4h", "5c", "6c"))]}
        hands = (["AdAs"], ["KdKs"])
        worlds = [(0, 0, 1.0, 0, "5c", "6c")]
        with patch.object(base.production, "_enumerate_worlds",
                          return_value=(hands, worlds, (), 1)) as enumeration:
            result = runner._compare_production_physical(spec, oracle)
        enumeration.assert_called_once_with("2c3d4h", "AsAd:1", "KdKs:1", iterations=140)
        self.assertEqual(result["worlds"], 1)
        self.assertEqual(result["pairs"], 1)

    def test_storage_method_slugs_are_safe_and_bounded(self):
        from scripts import benchmark_weighted_full_deck_flop as base
        with patch.object(base, "store_payload", side_effect=lambda directory, filename, payload: {
                "file": filename, "raw_bytes": 1, "gzip_bytes": 1,
                "payload_sha256": "a" * 64, "gzip_sha256": "b" * 64}) as store:
            for method in runner.METHOD_IDS:
                filename = f"{runner._method_file_slug(method)}-140-1.json.gz"
                self.assertNotIn("/", filename)
                self.assertNotIn("\\", filename)
                receipt = runner._store(STAGING, filename, {"method": method})
                self.assertEqual(receipt["file"], filename)
                runner._validate_payload_receipt(receipt, expected_file=filename)
            self.assertEqual(store.call_count, len(runner.METHOD_IDS))
        self.assertEqual(runner._method_file_slug("alternating-dcfr-3/2-0-2"),
                         "alternating-dcfr-3_2-0-2")

    def test_independent_guard_covers_directly_imported_training_aliases(self):
        from contextlib import ExitStack
        from pokerlab import alternating_public_cfr
        calls = {}
        with ExitStack() as stack:
            runner._forbid_new_trainers(stack, alternating_public_cfr, calls)
            for name in ("_aggregate_prefixes", "_cfrplus_target_deltas"):
                with self.subTest(name=name), self.assertRaises(AssertionError):
                    getattr(alternating_public_cfr, name)([], (1, 1))
        self.assertTrue(any(calls.values()))

    def test_independent_replay_rejects_wrong_physical_action_fields_without_ranking(self):
        from scripts import flop_multistreet_validation as independent
        board = ("2c", "3d", "4h", "5s", "6c")
        config = {"pot": 2, "effective_stack": [2, 2], "bet_sizes": [0.5],
                  "raise_sizes": [], "max_raises": 0, "include_all_in": False}
        public_config = independent._public_config(independent._configuration(config))
        hand0, hand1 = "AdAs", "KdKs"
        actions = (independent._action("check"),
                   independent._action("bet", 1.0, 1.0))
        terminals = (
            independent._Terminal((), "showdown", (0.0, 0.0)),
            independent._Terminal(("bet@1",), "fold", (1.0, 0.0), winner=0),
        )
        node = independent._Decision((), 0, "river", board, actions, terminals)
        oracle = {
            "board": board, "config": public_config,
            "street_configs": {"river": public_config}, "runouts": (),
            "reachable_runouts": (), "runout_mode": "none",
            "worlds": ((hand0, hand1, Fraction(1), 0, board),),
            "nodes": {(0, ()): node},
            "active_hands_by_prefix": {(0, ()): {hand0}, (1, ()): {hand1}},
            "root": node, "public_nodes": 1, "public_states": 3,
            "chance_nodes": 0, "terminal_nodes": 2, "compatible_pairs": 1,
            "pot": 2.0,
        }
        result = {
            "solver_version": "configured-postflop-v1", "algorithm": "vanilla",
            "strategy_schema": "postflop-strategy-v1", "board": list(board),
            "config": public_config, "street_configs": {"river": public_config},
            "runout_mode": "none", "runouts": [], "reachable_runouts": [],
            "pot": 2.0, "effective_stack": [2.0, 2.0], "worlds": 1,
            "compatible_pairs": 1, "deals": 1, "info_sets": 1,
            "public_nodes": 1, "public_states": 3, "chance_nodes": 0,
            "terminal_nodes": 2,
            "strategy": [{
                "player": "oop", "hand": hand0, "street": "river",
                "board": list(board), "history": [],
                "actions": [
                    {"name": "check", "amount": 0.0, "raise_to": 0.0,
                     "history_key": "check", "probability": 0.5},
                    {"name": "bet", "amount": 1.0, "raise_to": 1.0,
                     "history_key": "bet@1", "probability": 0.5},
                ],
            }],
            "value_oop": 0.5, "value_ip": -0.5,
            "oop_best_response_value": 1.0, "ip_best_response_value": -0.5,
            "oop_best_response_gain": 0.5, "ip_best_response_gain": 0.0,
            "nash_conv": 0.5, "exploitability": 0.25,
        }
        independent.replay(result, oracle, tolerance=1e-12)
        wrong_amount = copy.deepcopy(result)
        wrong_amount["strategy"][0]["actions"][1]["raise_to"] = 1.5
        with self.assertRaisesRegex(ValueError, "differs from independent numeric rules"):
            independent.replay(wrong_amount, oracle, tolerance=1e-12)
        extra_key = copy.deepcopy(result)
        extra_key["strategy"][0]["actions"][0]["debug"] = "hidden-info"
        with self.assertRaisesRegex(ValueError, "exactly the serialized action fields"):
            independent.replay(extra_key, oracle, tolerance=1e-12)

    def test_cli_exit_codes_distinguish_verification_quality_and_errors(self):
        import contextlib
        import io
        with patch.object(runner, "run", return_value={
                "status": "quality-miss", "quality_gate_met": False,
                "validation_errors": []}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(["--output", "out", "--baseline", "base"]), 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "quality-miss")
        with patch.object(runner, "verify_saved", return_value={
                "quality_gate_met": False, "raw_index_sha256": "a" * 64,
                "timed_and_allocation_policies_replayed": 12,
                "worlds_reenumerated": 5940, "file_count": 15}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(["--output", "out", "--baseline", "base", "--verify"]), 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "verified")
        with patch.object(runner, "verify_saved", return_value={
                "quality_gate_met": False, "raw_index_sha256": "a" * 64,
                "timed_and_allocation_policies_replayed": 12,
                "worlds_reenumerated": 5940, "file_count": 15}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(["--output", "out", "--baseline", "base",
                                          "--verify", "--require-quality"]), 1)
        with patch.object(runner, "run", return_value={
                "status": "error", "quality_gate_met": False,
                "validation_errors": ["failed allocation"]}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(["--output", "out", "--baseline", "base"]), 2)

    def test_allocation_failure_is_retained_and_never_becomes_quality_miss(self):
        spec = frozen_spec()
        source = {"revision": "a" * 40, "status": [],
                  "source_hashes": {"scripts/a.py": {
                      "raw_sha256": "a" * 64, "lf_sha256": "b" * 64}}}
        class Delayed:
            def load_spec(self):
                return {}
            def verify_baseline(self, *_args):
                return {"publication_index_sha256":
                        spec["baseline"]["publication_index_sha256"],
                        "quality_gate_met": False}
        class Base:
            @staticmethod
            def _world_projection(worlds):
                return list(worlds)
        base = Base()
        delayed = Delayed()
        staged_writes = []
        directory = STAGING / "simulated-run-output-no-files-created"
        with (
            patch.object(runner, "ROOT", REPO),
            patch.object(runner, "SPEC_SHA256", runner._checksum(spec)),
            patch.object(runner, "load_spec", return_value=spec),
            patch.object(runner, "_source_snapshot", return_value=source),
            patch.object(runner.platform, "platform", return_value="test-platform"),
            patch.object(runner.subprocess, "run"),
            patch.object(runner, "preflight", return_value={"requests": [None] * 12}),
            patch.object(runner, "_source_modules", return_value=(None, None, None, delayed, base)),
            patch.object(runner, "_guarded_reference", return_value=({"worlds": []}, {})),
            patch.object(runner, "_store", side_effect=lambda _d, filename, _p: {
                "file": filename, "raw_bytes": 1, "gzip_bytes": 1,
                "payload_sha256": "a" * 64, "gzip_sha256": "b" * 64}),
            patch.object(runner, "_compare_production_physical", return_value={}),
            patch.object(runner, "_timed_call", return_value={"kind": "timed", "error": "timed fail"}),
            patch.object(runner, "_allocation_call", return_value={"kind": "allocation",
                                                                      "error": "trace fail"}),
            patch.object(runner, "_write_index", side_effect=lambda _d, report:
                         staged_writes.append(copy.deepcopy(report))),
            patch.object(Path, "mkdir"),
        ):
            report = runner.run(directory, STAGING.parent / "baseline")
        self.assertEqual(report["status"], "error")
        self.assertTrue(report["validation_errors"])
        self.assertEqual(len(report["samples"]), 9)
        self.assertEqual(len(report["separate_allocation_calls"]), 3)
        self.assertTrue(all("error" in row for row in report["separate_allocation_calls"]))
        self.assertTrue(staged_writes)
        self.assertEqual(staged_writes[-1]["status"], "error")
        self.assertEqual(staged_writes[-1]["validation_errors"], report["validation_errors"])

    def test_complete_artifact_pipeline_with_stubbed_training_and_archived_policy(self):
        # This is a bookkeeping rehearsal, not a solver benchmark. The archived
        # policy supplies real serialization shapes; training, ranking, oracle
        # preparation and baseline reconstruction are explicitly replaced.
        import gzip
        import tempfile
        from scripts import benchmark_weighted_full_deck_flop as base
        from scripts import benchmark_flop_delayed_cfrplus as delayed
        from pokerlab import postflop_solver as production
        spec = frozen_spec()
        folder = REPO / "benchmarks/results/weighted-full-deck-flop-cfrplus-v1"
        index = json.loads((folder / "index.json").read_bytes())
        saved = next(row for row in index["samples"]
                     if row["iterations"] == 140 and row["traversal"] == "public-batched")
        original = json.loads(gzip.decompress((folder / saved["file"]).read_bytes()))
        baseline = {"publication_index_sha256": spec["baseline"]["publication_index_sha256"],
                    "quality_gate_met": False}
        source = {"revision": "a" * 40, "status": [], "source_hashes": {
            "scripts/runner.py": {"raw_sha256": "b" * 64, "lf_sha256": "c" * 64}}}
        current = [source]

        def supplied_policy(*_args, algorithm, iterations, **_kwargs):
            # Nested policy/config data are read-only throughout this rehearsal.
            payload = dict(original)
            payload["iterations"] = iterations
            if algorithm != "cfrplus":
                method = next(item for item in spec["algorithms"]
                              if item["solver_algorithm"] == algorithm)
                payload.update(algorithm=algorithm,
                               solver_version="configured-postflop-alternating-v1")
                for key in ("average_schedule", "regret_schedule", "regret_floor", "training_kernel"):
                    payload[key] = method[key]
            return payload

        def own_reaches(payload, *_args):
            return {(0 if row["player"] == "oop" else 1, row["hand"], tuple(row["history"])): 1.0
                    for row in payload["strategy"]}

        with (
            tempfile.TemporaryDirectory(dir=REPO.parent) as temporary,
            patch.object(runner, "_source_snapshot", side_effect=lambda: copy.deepcopy(current[0])),
            patch.object(runner.subprocess, "run"),
            patch.object(runner, "preflight", return_value={"requests": [None] * 12}),
            patch.object(delayed, "verify_baseline", return_value=baseline),
            patch.object(runner, "_guarded_reference", return_value=({"worlds": []}, {})),
            patch.object(runner, "_compare_production_physical", return_value={"stub": True}),
            patch.object(base, "_check_physical_record"),
            patch.object(production, "solve_postflop", side_effect=supplied_policy) as solve,
            patch.object(runner, "_assess", side_effect=lambda payload, *_args:
                         ({"nash_conv": payload["nash_conv"]}, {})),
            patch.object(delayed, "_decision_paths", return_value=None),
            patch.object(delayed, "_own_reach_masses", side_effect=own_reaches),
        ):
            output = Path(temporary) / "evidence"
            report = runner.run(output, folder)
            self.assertEqual(report["status"], "quality-miss", report.get("validation_errors"))
            self.assertEqual(solve.call_count, 12)
            self.assertEqual(len(list(output.iterdir())), 15)
            self.assertNotIn("active_request", report)
            self.assertEqual(report["phase"], "complete")
            # Replaying historical evidence in a newer stable checkout is valid.
            current[0] = {**source, "revision": "d" * 40, "source_hashes": {
                **source["source_hashes"], "scripts/new.py": {
                    "raw_sha256": "e" * 64, "lf_sha256": "f" * 64}}}
            checked = runner.verify_saved(output, folder)
            self.assertEqual(checked["timed_and_allocation_policies_replayed"], 12)
            self.assertEqual(checked["measurement_source_revision"], "a" * 40)
            self.assertIs(checked["quality_gate_met"], False)
            self.assertEqual(solve.call_count, 12, "Saved verification must not retrain")
            # A recomputed checksum cannot turn a boolean counter into an integer.
            report["samples"][0]["repeat"] = True
            runner._write_index(output, report)
            with self.assertRaisesRegex(ValueError, "exact integers"):
                runner.verify_saved(output, folder)

    def test_cross_method_probability_differences_are_diagnostics_only(self):
        spec = frozen_spec()
        left = candidate("cfrplus-control", 0.25)
        right = candidate("lcfr", 0.75)
        oracle = object()
        delayed = type("Delayed", (), {
            "_decision_paths": staticmethod(lambda _oracle: object()),
            "_own_reach_masses": staticmethod(
                lambda payload, _oracle, _paths: {(0, "AdAs", ()): 0.0 if
                                                   payload["algorithm"] == "cfrplus" else 0.5}),
        })
        base = type("Base", (), {})
        with patch.object(runner, "_source_modules",
                          return_value=(None, None, None, delayed, base)):
            result = runner._cross_method(left, right, spec, oracle, "cfrplus-control", "lcfr")
        self.assertTrue(result["policy_probability_and_cross_method_metric_gaps_are_diagnostic_only"])
        self.assertEqual(result["maximum_raw_conditional_probability_gap"], 0.5)
        self.assertEqual(result["maximum_own_reach_action_realization_gap"], 0.375)
        self.assertEqual(result["aligned_information_sets"], 1)
        self.assertEqual(result["scalar_absolute_gaps"]["nash_conv"], 0.0)


if __name__ == "__main__":
    unittest.main()
