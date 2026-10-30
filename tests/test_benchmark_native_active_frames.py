"""Protocol and evidence-preservation controls; never run the fixed study here."""
import base64
from copy import deepcopy
import itertools
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import benchmark_native_active_frames as study


def _tiny_native_request():
    z = "0000000000000000"
    return ("\n".join((
        "OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4",
        "10 64 1 1 1 3 2 0 0",
        "65536 500000000 2000000 1073741824 500000000 2000000 16000000 500000000 2000000 1000000 2000000",
        "49 51 3fe0000000000000",
        "44 46 3fe0000000000000",
        "0 4 10 15 18",
        "D 0 1",
        f"fold {z} {z} 0 fold 1",
        "C 1 4 1",
        "2c3c4h 2",
        f"F 0 {z} {z}",
    )) + "\n").encode("ascii")


def _frame_fixture(group=2, iterations=10, visits=7, depth=2, hands=3, decisions=6, prefixes=80):
    roots = 3 * iterations
    edges = roots * (visits - 1)
    activations = roots + edges
    frames = depth + 1
    slots = frames * group
    workspace = 64 + 3 * frames + 8 * slots
    borrowed = 4 * (depth + 4) * 6
    per_visit = 64 + 4 * 6 + 8 * group
    flow = workspace + activations * per_visit
    decision_calls = 3 * iterations * decisions
    validation = decision_calls * 32 * (1 + group + hands * (1 + group)) + prefixes * 64
    setup_plan, setup_index, setup_router, index_upper = 100, 200, 300, 400
    caller_work, router_upper = flow + 5, validation + 7
    total_work, total_entries = setup_plan + setup_index + setup_router + index_upper + caller_work + router_upper, 456789
    forecast = study._indexed_admission_amounts(group=group, iterations=iterations,
        history_tokens=12, decision_hands=5, action_count=7, history_entries=17,
        row_bytes=280, depth=depth, visits=visits)
    route = {"roots": roots, "roots_upper": roots, "edges": edges, "edges_upper": edges,
        "decisions": decision_calls, "decisions_upper": decision_calls,
        "prefixes": prefixes, "prefixes_upper": prefixes,
        "q_rows": 4, "map_entries": 4, "map_upper": 4, "r_lookup_entries": 0,
        "old_q_histories_retained": 1, "q_routes": 4, "q_routes_upper": 4,
        "q_tokens": 24, "q_tokens_upper": 24,
        "cursor_fields": 3, "cursor_frames_upper": workspace + borrowed,
        "caller_work": caller_work, "router_work": 2, "router_work_upper": router_upper,
        "index_work": 3, "index_work_upper": index_upper, "index_entries": 2,
        "index_entries_upper": 5, "router_retained": 1, "router_retained_upper": 10,
        "final_router_entries": 0, "decision_comparisons": 0, "prefix_comparisons": 0,
        "legacy_extensions": 0, "legacy_rows": 0, "legacy_prefixes": 0,
        "caller_entries": workspace + borrowed + 9,
        "old_history_forecast": forecast["trainer_history_retained"],
        "combined_work": total_work, "combined_entries": total_entries}
    done = {"group_size": group, "modeled_work_upper": total_work,
        "retained_entries_upper": total_entries}
    admission = {"mode": "indexed-v1", **forecast,
        "plan_setup_work": setup_plan, "index_setup_work": setup_index,
        "router_setup_work": setup_router,
        "marginal_calls_upper": 3, "marginal_calls_actual": 2, "marginal_reuse": 1,
        "combined_work": total_work, "combined_entries": total_entries}
    frame = {"group_size": group, "frames": frames, "image_slots": slots,
        "header_entries": 3 * frames, "workspace_entries": workspace,
        "workspace_setup_work": workspace, "view_fields": 3, "lease_fields": 3,
        "borrowed_entries_upper": borrowed, "flow_per_visit": per_visit,
        "flow_work_upper": flow, "validation_work_upper": validation,
        "activations": activations, "activations_upper": activations,
        "released_frames": activations, "release_calls": activations,
        "final_active_frames": 0, "final_workspace_entries": 0,
        "value_cursor_learning_calls": 0, "router_owned_workspace": 1,
        "combined_work": total_work, "combined_entries": total_entries}
    direct = {"maximum_depth": depth, "expanded_logical_visits": visits,
        "decision_occurrences": decisions, "terminal_occurrences": 1}
    return frame, direct, route, admission, done, (iterations, hands)


def _payload(strategy=None, metrics=None):
    strategy = strategy if strategy is not None else [{"player": 0, "hand": "AsAd", "history": [],
        "actions": [{"action": "fold", "probability": 0.25}, {"action": "call", "probability": 0.75}]}]
    metrics = metrics if metrics is not None else {name: i / 8 for i, name in enumerate((
        "value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
        "sb_gain", "bb_gain", "nash_conv", "exploitability"))}
    return {"strategy": strategy, "info_sets": len(strategy),
        "chance_input_snapshot": {"selected": ["2c3c4h5s6h"]}, **metrics}


class ActiveFrameBenchmarkControls(unittest.TestCase):
    def test_fixed_schedule_has_37_calls_aliases_and_requested_alternation(self):
        self.assertEqual(len(study.SCHEDULE), 37)
        self.assertEqual(len(set(study.SCHEDULE)), 37)
        self.assertEqual(study.SCHEDULE[:12], tuple((case, 10, mode, 0)
            for case in study.BASELINES for mode in study.TRAVERSALS))
        self.assertEqual(study.SCHEDULE[12:16], (
            ("original-22-t10", 10, "active-frames", 1),
            ("original-22-t10", 10, "value-cursor", 1),
            ("original-22-t10", 10, "value-cursor", 2),
            ("original-22-t10", 10, "active-frames", 2)))
        self.assertEqual(study.SCHEDULE[16:22], tuple(("original-22-t10", t, mode, 0)
            for t in (40, 60, 100) for mode in study.TRAVERSALS))
        self.assertEqual(study.SCHEDULE[22:24], tuple(("payoff-varied-t100", 100, mode, 0)
            for mode in study.TRAVERSALS))
        matrix = [row for row in study.SCHEDULE if row[0] in study.MATRIX]
        self.assertEqual(len(matrix), 13)
        self.assertTrue(all(row[2] == "active-frames" for row in matrix))
        self.assertEqual(sum(row[0] == "original-weighted-2x2" and row[1] == 1000 for row in matrix), 1)
        self.assertNotIn(("original-weighted-2x2", 10, "active-frames", 0), study.SCHEDULE)
        self.assertNotIn(("original-weighted-2x2", 100, "active-frames", 0), study.SCHEDULE)

    def test_physical_g6_range_has_nine_worlds_and_full_suit_stabilizer(self):
        base = {"sb_range": "old", "bb_range": "old", "runouts": [],
            "config": {"starting_stack": [2, 2]}, "flop_config": {}, "turn_config": {}, "river_config": {}}
        deps = SimpleNamespace(quotient=SimpleNamespace(case_for=lambda _name: dict(base)))
        case = study.case_for("physical-g6", deps)
        board = tuple(case["runouts"][0][i:i + 2] for i in range(0, 10, 2))
        sb = [frozenset((token[:2], token[2:])) for token in case["sb_range"].split(",")]
        bb = [frozenset((token[:2], token[2:])) for token in case["bb_range"].split(",")]
        self.assertEqual(sum(not (left & right or left & set(board) or right & set(board))
            for left in sb for right in bb), 9)
        for permutation in itertools.permutations("dhs"):
            mapping = dict(zip("dhs", permutation))
            transform_card = lambda card: card[0] + mapping.get(card[1], card[1])
            transform = lambda hand: frozenset(transform_card(card) for card in hand)
            self.assertEqual({transform(hand) for hand in sb}, set(sb))
            self.assertEqual({transform(hand) for hand in bb}, set(bb))
            self.assertEqual(tuple(transform_card(card) for card in board), board)
        self.assertEqual(case["runouts"], ["2c3c4c7c8c"])
        with patch.object(study, "_AUTH", {"source": "authenticated-for-fixture-test"}):
            deps = study._dependencies()
            cases = study.validate_cases(deps)
        self.assertEqual(cases["physical-g6"]["sb_range"], case["sb_range"])
        self.assertEqual(len(deps.expand_range(cases["balanced-16x16-unit"]["sb_range"])), 16)
        self.assertEqual(len(deps.expand_range(cases["asymmetric-2x16-unit"]["bb_range"])), 16)

    def test_frame_math_uses_caller_flow_and_router_query_validation_separately(self):
        frame, direct, route, admission, done, (iterations, hands) = _frame_fixture(group=6)
        study._validate_frame(frame, iterations=iterations, direct=direct,
            kernel_hands=hands, route=route, admission=admission, done=done)
        exact = {**done, "modeled_work_upper": done["modeled_work_upper"],
            "retained_entries_upper": done["retained_entries_upper"]}
        forecast = {key: admission[key] for key in ("plan_legacy_lookup_removed",
            "plan_legacy_action_removed", "trainer_legacy_history_removed", "trainer_history_retained")}
        study._validate_indexed_ledger(exact=exact,
            route={**route, "mode": "indexed"}, admission=admission,
            direct=direct, iterations=iterations, traversal="active-frames", forecast=forecast)
        wrong = dict(frame)
        wrong["release_calls"] += 1
        with self.assertRaisesRegex(ValueError, "FRAME"):
            study._validate_frame(wrong, iterations=iterations, direct=direct,
                kernel_hands=hands, route=route, admission=admission, done=done)
        with self.assertRaisesRegex(ValueError, "admission"):
            study._validate_frame(frame, iterations=iterations, direct=direct,
                kernel_hands=hands, route={**route, "router_work_upper": 0}, admission=admission, done=done)

    def test_pair_identity_requires_complete_policy_and_all_eight_metric_bits(self):
        metrics = {name: i / 8 for i, name in enumerate(("value_sb", "value_bb", "sb_best_response_value",
            "bb_best_response_value", "sb_gain", "bb_gain", "nash_conv", "exploitability"))}
        left_payload, right_payload = _payload(metrics=metrics), _payload(metrics=metrics)
        cert = {"metrics": metrics, "threshold": 0.001, "threshold_met": False}
        verification = {"quality_gate": False, "numeric": {"status": "complete"},
            "exact": {"status": "complete", "result": {"exact_certificate": cert}}}
        deps = SimpleNamespace(equivariant=SimpleNamespace(METRICS=tuple(metrics)))
        result = study._pair_identity({"payload": left_payload, "seconds": 1.0},
            {"payload": right_payload, "seconds": 0.9}, verification, verification, deps)
        self.assertTrue(result["policy_and_action_rows_bitwise_identical"])
        self.assertTrue(result["all_eight_metric_binary64_identical"])
        self.assertFalse(result["threshold_met"])
        changed_metric = deepcopy(right_payload)
        changed_metric["value_sb"] = 0.12500000000000003
        with self.assertRaisesRegex(ValueError, "metric"):
            study._pair_identity({"payload": left_payload, "seconds": 1.0},
                {"payload": changed_metric, "seconds": 0.9}, verification, verification, deps)
        changed_policy = deepcopy(right_payload)
        changed_policy["strategy"][0]["actions"][0]["probability"] = 0.5
        with self.assertRaisesRegex(ValueError, "policy"):
            study._pair_identity({"payload": left_payload, "seconds": 1.0},
                {"payload": changed_policy, "seconds": 0.9}, verification, verification, deps)

    def test_resource_classifier_does_not_hide_unrelated_failures(self):
        self.assertTrue(study._resource_message("native admission work limit exceeded"))
        for message in ("escape failed", "capricious parser error", "FRAME proof mismatch",
                        "unsupported active traversal requires another backend"):
            self.assertFalse(study._resource_message(message))
        raw = {"failure": {"type": "ValueError", "message": "whole-request work limit exceeded"},
            "counts": {"native_invoke": 0, "python_rank": 0, "python_trainer": 0}, "native_streams": []}
        self.assertEqual(study._resource_outcome(raw), "host-admission-rejected")
        raw["payload"] = {"strategy": []}
        self.assertIsNone(study._resource_outcome(raw))
        raw.pop("payload")
        raw["failure"]["message"] = "FRAME proof mismatch: work limit exceeded"
        self.assertIsNone(study._resource_outcome(raw))
        rejected = {"failure": {"type": "NativeFailure", "message": "native work limit exceeded"},
            "payload": None, "counts": {"native_invoke": 1, "rank_before_native": 0,
                "python_rank": 0, "python_trainer": 0}, "native_streams": [{"stdout": "",
                "stderr": base64.b64encode(b"native exact four-street rejected: work limit exceeded").decode(),
                "returncode": 2}]}
        self.assertEqual(study._resource_outcome(rejected), "native-resource-rejected")
        rejected["counts"]["python_rank"] = 1
        self.assertIsNone(study._resource_outcome(rejected))

    def test_indexed_admission_fields_are_recomputed_quantities(self):
        amounts = study._indexed_admission_amounts(group=2, iterations=10,
            history_tokens=12, decision_hands=5, action_count=7,
            history_entries=17, row_bytes=280, depth=2, visits=7)
        self.assertEqual(amounts, {"plan_legacy_lookup_removed": 168960,
            "plan_legacy_action_removed": 13440, "trainer_legacy_history_removed": 110880,
            "trainer_history_retained": 14784})
        frame, direct, route, admission, done, (iterations, _) = _frame_fixture()
        exact = {**done, "modeled_work_upper": done["modeled_work_upper"],
            "retained_entries_upper": done["retained_entries_upper"]}
        forecast = {key: admission[key] for key in amounts}
        study._validate_indexed_ledger(exact=exact, route={**route, "mode": "indexed"},
            admission=admission, direct=direct, iterations=iterations,
            traversal="active-frames", forecast=forecast)
        bad = dict(admission); bad["plan_legacy_action_removed"] = 1
        with self.assertRaisesRegex(ValueError, "indexed"):
            study._validate_indexed_ledger(exact=exact, route={**route, "mode": "indexed"},
                admission=bad, direct=direct, iterations=iterations,
                traversal="active-frames", forecast=forecast)

    def test_saved_wire_census_derives_occurrences_group_and_admission(self):
        direct = {"expanded_logical_visits": 3, "decision_occurrences": 1,
            "terminal_occurrences": 1, "maximum_depth": 2,
            "logical_history_token_work": 5, "logical_history_token_bytes": 34}
        result = study._wire_census(_tiny_native_request(),
            expected_header="OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4",
            expected_iterations=10, expected_hands=(1, 1), direct=direct)
        self.assertEqual((result["visits"], result["decisions"], result["terminals"], result["depth"]),
            (3, 1, 1, 2))
        self.assertGreaterEqual(result["group_size"], 1)
        self.assertEqual(result["history_tokens"], 3)
        self.assertEqual(result["admission_amounts"], study._indexed_admission_amounts(
            group=result["group_size"], iterations=10, history_tokens=3, decision_hands=1,
            action_count=1, history_entries=1, row_bytes=64, depth=2, visits=3))
        reversed_hand = _tiny_native_request().replace(b"49 51 3fe0000000000000", b"51 49 3fe0000000000000")
        self.assertEqual(study._wire_census(reversed_hand,
            expected_header="OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4",
            expected_iterations=10, expected_hands=(1, 1), direct=direct), result)
        malformed = _tiny_native_request().replace(b"C 1 4 1\n", b"C 1 9 1\n")
        with self.assertRaisesRegex(ValueError, "chance street"):
            study._wire_census(malformed,
                expected_header="OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4",
                expected_iterations=10, expected_hands=(1, 1), direct=direct)

    def test_child_guard_failure_rejects_before_mathematical_validation(self):
        with self.assertRaisesRegex(ValueError, "source/build guard"):
            study.validate({"source_build_guard_failure": ["drift"]}, study.SCHEDULE[0], None, {})

    def test_shared_child_and_initial_history_census_preserve_edge_multiplicity(self):
        wire = _tiny_native_request().decode("ascii").splitlines()
        wire[1] = "10 64 1 1 1 2 2 0 1"
        wire = wire[:6] + ["flop@2c3c4h", "D 0 2",
            "check 0000000000000000 0000000000000000 0 check 1",
            "fold 0000000000000000 0000000000000000 0 fold 1",
            "F 0 0000000000000000 0000000000000000"]
        direct = {"expanded_logical_visits": 3, "decision_occurrences": 1,
            "terminal_occurrences": 2, "maximum_depth": 1,
            "logical_history_token_work": 7, "logical_history_token_bytes": 51}
        census = study._wire_census(("\n".join(wire) + "\n").encode(),
            expected_header="OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4",
            expected_iterations=10, expected_hands=(1, 1), direct=direct)
        self.assertEqual((census["visits"], census["history_tokens"], census["action_count"],
                          census["history_entries"], census["row_bytes"]), (3, 6, 2, 3, 139))

    def test_source_authentication_precedes_project_imports(self):
        process = subprocess.run([sys.executable, "-B", "-c",
            "import sys; from scripts import benchmark_native_active_frames; "
            "assert not any(name.startswith('pokerlab') for name in sys.modules)"],
            cwd=study.ROOT, capture_output=True, check=False)
        self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", "replace"))
        with patch.object(study, "_AUTH", None), self.assertRaisesRegex(ValueError, "authenticate source"):
            study._dependencies()

    def test_child_injects_both_explicit_native_selectors_without_fallback(self):
        entry = study.SCHEDULE[1]
        source = {"commit": "fixture", "status": "", "sha256": {}}
        observed = {}
        case = {"fixture": "fixed"}
        solver_module = SimpleNamespace(solve_four_street_exact_selected=
            lambda request, **kwargs: observed.update(kwargs))
        indexed_module = SimpleNamespace(case_for=lambda _: case, ITERATIONS={}, child=None)
        def captured_child(name, routing, sample, traced, executable):
            observed["iterations"] = indexed_module.ITERATIONS[name]
            solver_module.solve_four_street_exact_selected(None, native_executable=executable,
                native_routing=routing)
            return {"case": name, "routing": routing, "sample": sample, "traced": traced,
                "failure": {"type": "RuntimeError", "message": "sentinel"}, "payload": None,
                "counts": {"native_invoke": 0, "python_rank": 0, "python_trainer": 0}, "native_streams": []}
        indexed_module.child = captured_child
        deps = SimpleNamespace(solver=solver_module, indexed=indexed_module,
            native=SimpleNamespace(executable_identity=lambda _: {"build": "fixed"}))
        with patch.object(study, "_AUTH", source), patch.object(study, "_authenticate_source", return_value=source), \
             patch.object(study, "_identity", return_value=source), patch.object(study, "_dependencies", return_value=deps), \
             patch.object(study, "case_for", return_value=case):
            raw = study.child(*entry, "native.exe")
        self.assertEqual(raw["status"], "failed")
        self.assertEqual(observed["native_admission"], "indexed-v1")
        self.assertEqual(observed["native_traversal"], entry[2])
        self.assertEqual(observed["iterations"], entry[1])

    def test_child_preserves_payload_and_native_streams_when_source_drifts_after_solve(self):
        entry = study.SCHEDULE[0]
        source = {"commit": "fixture", "status": "", "sha256": {}}
        drift = {"commit": "changed", "status": "dirty", "sha256": {}}
        native_stream = {"request": "cmVxdWVzdA==", "stdout": "b3V0", "stderr": "",
            "returncode": 0}
        payload = {"operator_census": {"native_exact": {"rank_calls": 7}}}
        case = {"fixture": "fixed"}
        indexed_module = SimpleNamespace(case_for=lambda _: case, ITERATIONS={}, child=lambda *args: {
            "case": entry[0], "routing": "indexed", "sample": entry[3], "traced": False,
            "failure": None, "payload": payload, "native_streams": [native_stream],
            "counts": {"native_invoke": 1, "python_rank": 1, "python_trainer": 0}})
        deps = SimpleNamespace(indexed=indexed_module,
            solver=SimpleNamespace(solve_four_street_exact_selected=lambda *_a, **_k: None),
            native=SimpleNamespace(executable_identity=lambda _: {"build": "fixed"}))
        with patch.object(study, "_AUTH", source), patch.object(study, "_authenticate_source", return_value=source), \
             patch.object(study, "_identity", return_value=drift), patch.object(study, "_dependencies", return_value=deps), \
             patch.object(study, "case_for", return_value=case):
            raw = study.child(*entry, "native.exe")
        self.assertEqual(raw["status"], "failed")
        self.assertIs(raw["payload"], payload)
        self.assertEqual(raw["native_streams"], [native_stream])
        self.assertTrue(raw["source_build_guard_failure"])

    def test_source_proof_is_written_before_project_dependency_import(self):
        source = {"commit": "fixture", "status": "", "sha256": {"tracked.py": "a" * 64}}
        proof = {"commit": "fixture", "committed_tree_blob_oid": {"tracked.py": "blob"},
            "git_normalized_blob_oid": {"tracked.py": "blob"}, "closure_count": 1}
        with TemporaryDirectory() as directory, patch.object(study, "_AUTH_PROOF", proof), \
             patch.object(study, "_authenticate_source", return_value=source), \
             patch.object(study, "_dependencies", side_effect=RuntimeError("math imports unavailable")), \
             patch.object(study, "_identity", return_value=source):
            output = Path(directory) / "study"
            result = study.run(output, Path("native.exe"))
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(json.loads((output / "source-before.json").read_bytes()), source)
            self.assertEqual(json.loads((output / "source-auth-proof.json").read_bytes()), proof)
            report = json.loads((output / "report.json").read_bytes())
            self.assertEqual(report["calls_attempted"], 0)

    def test_first_child_failure_retains_raw_streams_and_never_retries(self):
        source = {"commit": "fixture", "status": "", "sha256": {}}
        deps = SimpleNamespace(quotient=SimpleNamespace(_runtime=lambda: {"runtime": "fixture"}),
            native=SimpleNamespace(executable_identity=lambda _: {"build": "fixed"}))
        process = subprocess.CompletedProcess([], 17, b"first stdout raw", b"first stderr raw")
        with TemporaryDirectory() as directory, patch.object(study, "_authenticate_source", return_value=source), \
             patch.object(study, "_identity", return_value=source), patch.object(study, "_dependencies", return_value=deps), \
             patch.object(study, "validate_cases", return_value={}), patch.object(study, "_run_child", return_value=process) as calls:
            output = Path(directory) / "study"
            result = study.run(output, Path("native.exe"))
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(calls.call_count, 1)
            self.assertEqual((output / (study.label(study.SCHEDULE[0]) + ".stdout.bin")).read_bytes(), process.stdout)
            self.assertEqual((output / (study.label(study.SCHEDULE[0]) + ".stderr.bin")).read_bytes(), process.stderr)
            self.assertTrue((output / "source-after.json").exists())
            report = json.loads((output / "report.json").read_bytes())
            self.assertEqual(report["calls_attempted"], 1)
            self.assertEqual(report["calls_captured"], 0)

    def test_post_math_source_drift_keeps_verified_and_raw_artifacts(self):
        entry = study.SCHEDULE[0]
        source = {"commit": "fixture", "status": "", "sha256": {}}
        drift = {"commit": "changed", "status": "dirty", "sha256": {}}
        build = {"build": "fixed"}
        deps = SimpleNamespace(quotient=SimpleNamespace(_runtime=lambda: {"runtime": "fixture"}),
            native=SimpleNamespace(executable_identity=lambda _: build), equivariant=SimpleNamespace(METRICS=()))
        payload = {"strategy": [], "value_sb": 0.0}
        raw = {"case": entry[0], "iterations": entry[1], "native_traversal": entry[2],
            "routing": "indexed", "sample": entry[3], "traced": False, "runtime": {"runtime": "fixture"},
            "request_case": {"fixture": entry[0]}, "seconds": 1.0, "process_peak_bytes": 1,
            "python_allocation_peak_bytes": None, "counts": {}, "native_streams": [],
            "failure": None, "payload": payload, "payload_sha256": "unused", "payload_bytes": 1}
        process = subprocess.CompletedProcess([], 0, b"child json bytes", b"")
        schedule_patch = patch.object(study, "SCHEDULE", (entry,))
        required_patch = patch.object(study, "REQUIRED_COMPLETE", frozenset())
        with TemporaryDirectory() as directory, patch.object(study, "_authenticate_source", return_value=source), \
             patch.object(study, "_identity", side_effect=(source, source, source, drift)), patch.object(study, "_dependencies", return_value=deps), \
             patch.object(study, "validate_cases", return_value={entry[0]: raw["request_case"]}), \
             patch.object(study, "_decode", return_value=raw), patch.object(study, "validate", return_value={"status": "complete", "payload": payload}), \
             patch.object(study, "_verify", return_value={"quality_gate": None,
                "numeric": {"status": "complete"}, "numeric_metric_gaps": {},
                "exact": {"status": "resource-unverified"}}), \
             patch.object(study, "_run_child", return_value=process), schedule_patch, required_patch:
            output = Path(directory) / "study"
            result = study.run(output, Path("native.exe"))
            self.assertEqual(result["outcome"], "failed")
            self.assertTrue((output / (study.label(entry) + ".stdout.bin")).exists())
            self.assertTrue((output / (study.label(entry) + ".raw.json")).exists())
            self.assertTrue((output / (study.label(entry) + "-verification.json")).exists())
            self.assertTrue((output / "source-drift.json").exists())
            self.assertEqual(json.loads((output / "report.json").read_bytes())["calls_captured"], 1)

    def test_complete_parent_pair_reads_actual_top_level_numeric_gap_schema(self):
        entries = study.SCHEDULE[:2]
        source = {"commit": "fixture", "status": "", "sha256": {}}
        build = {"build": "fixed"}
        payload = _payload()
        metrics = tuple(key for key in payload if key not in ("strategy", "info_sets", "chance_input_snapshot"))
        deps = SimpleNamespace(quotient=SimpleNamespace(_runtime=lambda: {}),
            native=SimpleNamespace(executable_identity=lambda _: build),
            equivariant=SimpleNamespace(METRICS=metrics, REPLAY_TOLERANCE=1e-9))
        observations = [{"case": row[0], "iterations": row[1], "native_traversal": row[2],
            "sample": row[3], "seconds": 1.0, "status": "complete", "native_streams": [], "payload": payload}
            for row in entries]
        verification = {"quality_gate": None, "numeric": {"status": "complete"},
            "numeric_metric_gaps": dict.fromkeys(metrics, 0.0), "exact": {"status": "resource-unverified"}}
        with TemporaryDirectory() as directory, patch.object(study, "_authenticate_source", return_value=source), \
             patch.object(study, "_identity", return_value=source), patch.object(study, "_dependencies", return_value=deps), \
             patch.object(study, "validate_cases", return_value={entries[0][0]: {}}), \
             patch.object(study, "_run_child", return_value=subprocess.CompletedProcess([], 0, b"raw", b"")), \
             patch.object(study, "_decode", side_effect=observations), \
             patch.object(study, "validate", return_value={"status": "complete", "payload": payload}), \
             patch.object(study, "_verify", return_value=verification) as verifier, \
             patch.object(study, "SCHEDULE", entries), \
             patch.object(study, "REQUIRED_COMPLETE", frozenset(((entries[0][0], entries[0][1]),))):
            result = study.run(Path(directory) / "study", Path("native.exe"))
            self.assertEqual(result["outcome"], "complete")
            report = json.loads((Path(directory) / "study/report.json").read_bytes())
            self.assertEqual(report["calls_attempted"], 2)
            self.assertEqual(len(report["paired_comparisons"]), 1)
            self.assertEqual(len(report["quality_misses_or_unverified_retained"]), 2)
            for tamper in ("payload", "captured-file"):
                output = Path(directory) / tamper
                def mutate(_case, returned, _deps):
                    if tamper == "payload":
                        returned["strategy"] = []
                    else:
                        (output / (study.label(entries[0]) + ".stdout.bin")).write_bytes(b"tampered")
                    return verification
                verifier.side_effect = mutate
                with patch.object(study, "_decode", side_effect=deepcopy(observations)):
                    failed = study.run(output, Path("native.exe"))
                self.assertEqual(failed["outcome"], "failed")
                self.assertEqual(failed["calls_captured"], 1)
                self.assertTrue((output / (study.label(entries[0]) + ".raw.json")).exists())
                self.assertIn("changed", failed["failure"]["message"])


if __name__ == "__main__":
    unittest.main()
