"""Lifecycle and independent-wire controls; never launch the fixed study."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_native_fold_classes as study
from scripts import benchmark_native_active_frames as active
from scripts.benchmark_native_active_frames import _wire_census
from tests.test_benchmark_native_active_frames import _tiny_native_request


def _tiny_direct():
    return {"expanded_logical_visits": 3, "decision_occurrences": 1, "terminal_occurrences": 1,
        "maximum_depth": 2, "logical_history_token_work": 5, "logical_history_token_bytes": 34}


def _sample_payload(metrics):
    return {"strategy": [{"player": 0, "hand": "AsAd", "history": [],
        "actions": [{"action": "fold", "probability": 0.25},
                    {"action": "call", "probability": 0.75}]}],
        "info_sets": 1, "chance_input_snapshot": {"contract": "exact-product-selected-v1", "ranges": []},
        **metrics}


def _protocol_child(deps, payoff):
    """Build a bounded synthetic child using the real V4/V5 wire/receipt schemas."""
    from pokerlab.cards import DECK, expand_range

    request = _tiny_native_request()
    fold_mode = payoff == "fold-mask-classes-v1"
    request = request.replace(b"OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4",
        b"OPENPOKER_NATIVE_EXACT_FOUR_STREET_FOLD_CLASSES_V5" if fold_mode else
        b"OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4")
    direct = _tiny_direct()
    iterations, hands = 10, (1, 1)
    header = request.splitlines()[0].decode("ascii")
    wire = _wire_census(request, expected_header=header, expected_iterations=iterations,
        expected_hands=hands, direct=direct)
    group = wire["group_size"]
    depth, visits, decisions, terminals = direct["maximum_depth"], direct["expanded_logical_visits"], \
        direct["decision_occurrences"], direct["terminal_occurrences"]
    frame_count = depth + 1
    workspace = 64 + 3 * frame_count + 8 * frame_count * group
    borrowed = 4 * (depth + 4) * 6
    flow_per = 64 + 24 + 8 * group
    activations = 3 * iterations * visits
    flow = workspace + activations * flow_per
    validation = 3 * iterations * decisions * 32 * (1 + group + max(hands) * (1 + group)) + \
        wire["admission_amounts"].get("none", 0) + iterations * (2 * terminals + decisions) * 64
    setup_work = 2048 * sum(hands) + 8 * 1 * sum(hands) + 65536
    setup_entries = 10 * sum(hands) + 128
    fold_work = setup_work + 1000
    index_setup, router_setup, index_upper = 200, 300, 100
    caller_work, router_upper = flow + 100, validation + 100
    combined_work = fold_work + index_setup + router_setup + index_upper + caller_work + router_upper
    combined_entries = 2000
    route = {name: 0 for name in deps.native.ROUTE_FIELDS}
    route.update(mode="indexed", q_rows=1, map_entries=1, map_upper=1,
        r_lookup_entries=0, old_q_histories_retained=1, q_routes=1, q_routes_upper=1,
        q_tokens=0, q_tokens_upper=0, roots=3 * iterations, roots_upper=3 * iterations,
        edges=3 * iterations * (visits - 1), edges_upper=3 * iterations * (visits - 1),
        decisions=3 * iterations * decisions, decisions_upper=3 * iterations * decisions,
        prefixes=iterations * (2 * terminals + decisions),
        prefixes_upper=iterations * (2 * terminals + decisions), cursor_fields=3,
        cursor_frames_upper=workspace + borrowed, caller_work=caller_work,
        caller_entries=workspace + borrowed + 100, router_work=0, router_work_upper=router_upper,
        index_work=0, index_work_upper=index_upper, index_entries=0, index_entries_upper=10,
        router_retained=0, router_retained_upper=10, old_history_forecast=
            wire["admission_amounts"]["trainer_history_retained"], final_router_entries=0,
        combined_work=combined_work, combined_entries=combined_entries)
    admission = {name: 0 for name in deps.native.ADMISSION_FIELDS}
    admission.update(mode="indexed-v1", **wire["admission_amounts"], plan_setup_work=fold_work,
        index_setup_work=index_setup, router_setup_work=router_setup,
        marginal_calls_upper=1, marginal_calls_actual=1, marginal_reuse=1,
        combined_work=combined_work, combined_entries=combined_entries)
    frame = {"group_size": group, "frames": frame_count, "image_slots": frame_count * group,
        "header_entries": 3 * frame_count, "workspace_entries": workspace,
        "workspace_setup_work": workspace, "view_fields": 3, "lease_fields": 3,
        "borrowed_entries_upper": borrowed, "flow_per_visit": flow_per,
        "flow_work_upper": flow, "validation_work_upper": validation,
        "activations": activations, "activations_upper": activations,
        "released_frames": activations, "release_calls": activations,
        "final_active_frames": 0, "final_workspace_entries": 0,
        "value_cursor_learning_calls": 0, "router_owned_workspace": 1,
        "combined_work": combined_work, "combined_entries": combined_entries}
    fold = {**study._wire_fold_expectation(request, iterations=iterations, census=wire),
        "buckets_sb": 0, "buckets_bb": 0, "own_checks": 0,
        "retained_pair_entries": 0, "query_allowance_retained": 1,
        "combined_work": combined_work, "combined_entries": combined_entries}
    counters = dict(zip(deps.native.COUNTERS, (1, 2, group, 1, 2, 20, 20,
        combined_work, 1, combined_entries, 8, 0, 1)))
    done_line = "DONE\t" + "\t".join(str(counters[name]) for name in deps.native.COUNTERS)
    route_line = "\t".join(("ROUTE", "indexed", *(f"{name}={route[name]}" for name in deps.native.ROUTE_FIELDS)))
    admission_line = "\t".join(("ADMISSION", "indexed-v1", *(f"{name}={admission[name]}" for name in deps.native.ADMISSION_FIELDS)))
    frame_line = "\t".join(("FRAME", "active-v1", *(f"{name}={frame[name]}" for name in deps.native.FRAME_FIELDS)))
    fold_line = "\t".join(("FOLD", "mask-classes-v1", *(f"{name}={fold[name]}" for name in study.FOLD_FIELDS)))
    result_header = deps.native.FOLD_CLASSES_RESULT if fold_mode else deps.native.ACTIVE_FRAMES_RESULT
    probabilities = ("3fe0000000000000", "3fe0000000000000")
    result_lines = [result_header,
        "ROW\t0\t0\t0\t2\t" + "\t".join(probabilities),
        done_line, route_line, admission_line, frame_line]
    if fold_mode:
        result_lines.append(fold_line)
    output = ("\n".join(result_lines) + "\n").encode("ascii")
    ranges = []
    for values in wire["hands_by_seat"]:
        ranges.append([{"hand": "".join((DECK[a], DECK[b])), "weight_hex": "0x1.0000000000000p-1"}
            for (a, b) in values])
    runout = "".join(DECK[card] for card in wire["boards"][0])
    case = {"id": "tiny-active-v4-v5", "sb_range": ranges[0][0]["hand"] + ":0.5",
        "bb_range": ranges[1][0]["hand"] + ":0.5", "runouts": [runout]}
    expected_ranges = []
    for expression in (case["sb_range"], case["bb_range"]):
        expanded = expand_range(expression)
        expected_ranges.append([{"hand": "".join(hand), "weight_hex": float(weight).hex()}
            for hand, weight in expanded.items()])
    exact_payload = {**counters, "calls": 1, "rank_calls": 1,
        "indexed_routing": route, "indexed_admission": admission,
        "active_frames": {"mode": "active-v1", **frame},
        "request_bytes": len(request), "result_bytes": len(output),
        "request_sha256": hashlib.sha256(request).hexdigest(),
        "result_sha256": hashlib.sha256(output).hexdigest()}
    if fold_mode:
        exact_payload["fold_classes"] = {"mode": "mask-classes-v1",
            **{name: fold[name] for name in study.FOLD_FIELDS}}
    payload = {"training_backend": "native-exact-four-street-fold-classes-v5" if fold_mode else
        "native-exact-four-street-active-frames-v4",
        **({"native_payoffs": payoff} if fold_mode else {}),
        "native_admission": "indexed-v1", "native_routing": "indexed", "native_traversal": "active-frames",
        "chance_contract": "exact-product-selected-v1", "conversion_contract": "exact-product-vectors-binary64-v1",
        "training_reduction": "suit-equivariant-sorted-chance-binary64-v1",
        "strategy_storage": "suit-quotient-packed-v1", "quotient_lookup": "per-decision-suit-history-transform-v1",
        "pair_diagnostics": "compact-exact-product-inputs-v1", "strategy": [{"player": 0, "hand": ranges[0][0]["hand"],
            "history": [], "actions": [{"action": "fold", "probability": .5}, {"action": "call", "probability": .5}]}],
        "info_sets": 1, "chance_input_snapshot": {"contract": "exact-product-selected-v1", "ranges": expected_ranges},
        "operator_census": {"stored_complete_worlds": 0, "stored_prefix_pair_edges": 0,
            "kernel": {"hands": [1, 1]}, "direct_topology": direct,
            "native_exact": exact_payload},
        "value_sb": 0.0, "value_bb": 0.0, "sb_best_response_value": 0.0, "bb_best_response_value": 0.0,
        "sb_gain": 0.0, "bb_gain": 0.0, "nash_conv": 0.0, "exploitability": 0.0}
    raw = {"case": "tiny", "iterations": iterations, "native_traversal": "active-frames", "routing": "indexed",
        "sample": 0, "traced": False, "request_case": case, "native_admission": "indexed-v1",
        "native_payoffs": payoff, "runtime": deps.quotient._runtime(), "seconds": 1.0,
        "process_peak_bytes": 1, "python_allocation_peak_bytes": None,
        "counts": {"python_trainer": 0, "native_invoke": 1, "python_rank": 1,
            "rank_before_native": 0, "pair": 0, "world": 0, "legacy": 0},
        "failure": None, "status": "complete", "payload": payload,
        "payload_sha256": hashlib.sha256(study._canonical(payload)).hexdigest(),
        "payload_bytes": len(study._canonical(payload)), "native_observations": {"learning_completed": True, "rank_calls": 1},
        "native_streams": [{"request": base64.b64encode(request).decode(),
            "stdout": base64.b64encode(output).decode(), "stderr": "", "returncode": 0}]}
    return case, raw


class NativeFoldClassBenchmarkTests(unittest.TestCase):
    def test_fixed_34_child_schedule_and_original_pair_alternation(self):
        self.assertEqual(len(study.SCHEDULE), 34)
        self.assertEqual(len(set(study.SCHEDULE)), 34)
        self.assertEqual(study.SCHEDULE[:12], tuple((case, 10, mode, 0)
            for case in study.BASELINES for mode in study.PAYOFFS))
        self.assertEqual(study.SCHEDULE[12:16], (
            ("original-22-t10", 10, "fold-mask-classes-v1", 1),
            ("original-22-t10", 10, "board-sweep", 1),
            ("original-22-t10", 10, "board-sweep", 2),
            ("original-22-t10", 10, "fold-mask-classes-v1", 2)))
        self.assertEqual(study.SCHEDULE[16:20], tuple(("original-22-t10", t, mode, 0)
            for t in (40, 60) for mode in study.PAYOFFS))
        self.assertEqual(study.SCHEDULE[20:22], tuple(("payoff-varied-t100", 100, mode, 0)
            for mode in study.PAYOFFS))
        self.assertEqual(study.SCHEDULE[30:], tuple(("original-22-t10", t, mode, 0)
            for t in (100, 1000) for mode in study.PAYOFFS))
        self.assertEqual(study.REQUIRED_COMPLETE,
            frozenset([(case, 10) for case in study.BASELINES] + [("payoff-varied-t100", 100)]))

    def test_raw_wire_fold_census_covers_occurrences_masks_and_crossover(self):
        request = _tiny_native_request().replace(
            b"OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4",
            b"OPENPOKER_NATIVE_EXACT_FOUR_STREET_FOLD_CLASSES_V5")
        direct = _tiny_direct()
        wire = _wire_census(request, expected_header="OPENPOKER_NATIVE_EXACT_FOUR_STREET_FOLD_CLASSES_V5",
            expected_iterations=10, expected_hands=(1, 1), direct=direct)
        wire["class_counts"] = study._classes_from_census(wire)
        expected = study._wire_fold_expectation(request, iterations=10, census=wire)
        self.assertEqual(expected["fold_occurrences"], 1)
        self.assertEqual((expected["class_calls_sb"] + expected["literal_calls_sb"],
                          expected["class_calls_bb"] + expected["literal_calls_bb"]), (10, 10))
        self.assertEqual(expected["setup_work_upper"], 2048 * 2 + 8 * 1 * 2 + 65536)
        self.assertEqual(expected["setup_entries_upper"], 10 * 2 + 128)

    def test_complete_child_validator_accepts_real_v4_and_v5_record_shapes(self):
        source = {"commit": "fixture"}
        with patch.object(active, "_AUTH", source):
            deps = active._dependencies()
        for payoff in study.PAYOFFS:
            with self.subTest(payoff=payoff):
                case, raw = _protocol_child(deps, payoff)
                outcome = study._validate_child(raw, ("tiny", 10, payoff, 0), deps, {"tiny": case})
                self.assertEqual(outcome["status"], "complete")
                self.assertEqual(outcome["payload"], raw["payload"])

    def test_complete_child_rejects_boolean_rank_order_and_extra_native_observation(self):
        source = {"commit": "fixture"}
        with patch.object(active, "_AUTH", source):
            deps = active._dependencies()
        case, raw = _protocol_child(deps, "board-sweep")
        raw["counts"]["rank_before_native"] = False
        with self.assertRaisesRegex(ValueError, "call counters"):
            study._validate_child(raw, ("tiny", 10, "board-sweep", 0), deps, {"tiny": case})
        case, raw = _protocol_child(deps, "board-sweep")
        raw["native_observations"]["unexpected"] = 0
        with self.assertRaisesRegex(ValueError, "native complete call"):
            study._validate_child(raw, ("tiny", 10, "board-sweep", 0), deps, {"tiny": case})

    def test_numeric_replay_gaps_must_be_finite_nonnegative_and_within_tolerance(self):
        metrics = ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
            "sb_gain", "bb_gain", "nash_conv", "exploitability")
        deps = SimpleNamespace(equivariant=SimpleNamespace(METRICS=metrics, REPLAY_TOLERANCE=1e-9))
        good = {"numeric": {"status": "complete"}, "numeric_metric_gaps": dict.fromkeys(metrics, 0.0)}
        study._validate_numeric_replay(good, deps)
        for value in (-1e-15, 1.1e-9, float("nan"), True):
            bad = {"numeric": {"status": "complete"}, "numeric_metric_gaps": dict.fromkeys(metrics, 0.0)}
            bad["numeric_metric_gaps"]["value_sb"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "numeric replay"):
                study._validate_numeric_replay(bad, deps)

    def test_fold_line_order_version_uint64_and_payload_marker_are_strict(self):
        valid = ["FOLD", "mask-classes-v1"] + [f"{name}=0" for name in study.FOLD_FIELDS]
        parsed = study._record("\t".join(valid), "FOLD", "mask-classes-v1", study.FOLD_FIELDS, ordered=True)
        self.assertEqual(tuple(parsed), study.FOLD_FIELDS)
        for bad in (
            "\t".join(["FOLD", "mask-classes-v2"] + valid[2:]),
            "\t".join([*valid[:2], valid[3], valid[2], *valid[4:]]),
            "\t".join([*valid[:2], f"{study.FOLD_FIELDS[0]}={(1 << 64)}", *valid[3:]]),
        ):
            with self.subTest(line=bad[:70]), self.assertRaises(ValueError):
                study._record(bad, "FOLD", "mask-classes-v1", study.FOLD_FIELDS, ordered=True)
        self.assertTrue(study.fold_line_missing_marker({"training_backend": "native-exact-four-street-active-frames-v4"}))
        self.assertFalse(study.fold_line_missing_marker({"native_payoffs": "fold-mask-classes-v1"}))

    def test_resource_payload_contradiction_is_never_a_resource_rejection(self):
        raw = {"payload": {"strategy": []}, "failure": {"type": "ValueError",
            "message": "whole-request work limit exceeded"},
            "counts": {"native_invoke": 0, "python_rank": 0, "python_trainer": 0}, "native_streams": []}
        self.assertIsNone(study.active._resource_outcome(raw))
        raw["payload"] = None
        self.assertEqual(study.active._resource_outcome(raw), "host-admission-rejected")

    def test_runner_imports_no_project_modules_before_source_authentication(self):
        code = ("import sys; from scripts import benchmark_native_fold_classes; "
                "assert not any(name.startswith('pokerlab') for name in sys.modules)")
        process = subprocess.run([__import__("sys").executable, "-B", "-c", code],
            cwd=study.ROOT, capture_output=True, check=False)
        self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", "replace"))

    def test_child_injects_only_payoff_mode_and_keeps_native_routing(self):
        entry = study.SCHEDULE[1]
        source = {"commit": "fixture", "status": "", "sha256": {}}
        case = {"id": "fixture"}
        observed = {}
        solver = SimpleNamespace(solve_four_street_exact_selected=
            lambda request, **kwargs: observed.update(kwargs))
        native = SimpleNamespace(executable_identity=lambda _: {"build": "fixed"})
        deps = SimpleNamespace(solver=solver, native=native)
        raw = {"failure": None, "payload": {"operator_census": {"native_exact": {"rank_calls": 3}}},
            "status": "complete", "counts": {}, "native_streams": []}

        def active_child(name, iterations, traversal, sample, executable):
            solver.solve_four_street_exact_selected(None, native_executable=executable,
                native_routing="indexed", native_admission="indexed-v1", native_traversal=traversal)
            return dict(raw, case=name, iterations=iterations, native_traversal=traversal,
                routing="indexed", sample=sample, traced=False, request_case=case)

        with patch.object(study, "_authenticate_source", return_value=source), \
             patch.object(study, "_dependencies", return_value=deps), \
             patch.object(study, "_case", return_value=case), \
             patch.object(study.active, "child", side_effect=active_child):
            result = study.child(*entry, "native.exe")
        self.assertEqual(result["native_payoffs"], "fold-mask-classes-v1")
        self.assertEqual(observed["native_payoffs"], "fold-mask-classes-v1")
        self.assertEqual(observed["native_traversal"], "active-frames")
        self.assertEqual(observed["native_admission"], "indexed-v1")

    def test_child_uses_fixed_schedule_projection_for_original_t1000(self):
        entry = ("original-22-t10", 1000, "fold-mask-classes-v1", 0)
        self.assertNotIn(("original-22-t10", 1000, "active-frames", 0), active.SCHEDULE)
        source = {"commit": "fixture"}
        case = {"id": "fixture"}
        build = {"executable": "pinned"}
        observed = {}
        solver = SimpleNamespace(solve_four_street_exact_selected=lambda request, **kwargs:
            observed.update(kwargs))

        def indexed_child(*args):
            observed["indexed_child_args"] = args
            solver.solve_four_street_exact_selected(None)
            return {"failure": None, "payload": {"operator_census": {"native_exact": {"rank_calls": 7}}},
                "counts": {"native_invoke": 1}, "native_streams": []}

        deps = SimpleNamespace(solver=solver, native=SimpleNamespace(executable_identity=lambda _: build),
            indexed=SimpleNamespace(child=indexed_child, case_for=lambda _name: case,
                ITERATIONS={"original-22-t10": 10}))
        with patch.object(study, "_authenticate_source", return_value=source), \
             patch.object(study, "_dependencies", return_value=deps), \
             patch.object(study, "_case", return_value=case), \
             patch.object(study.active, "_authenticate_source", return_value=source), \
             patch.object(study.active, "_dependencies", return_value=deps), \
             patch.object(study.active, "_AUTH", source), \
             patch.object(study.active, "_identity", return_value=source), \
             patch.object(study.active, "SCHEDULE", tuple((name, count, "active-frames", sample)
                 for name, count, _payoff, sample in study.SCHEDULE)):
            result = study.child(*entry, "native.exe")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(observed["indexed_child_args"], ("original-22-t10", "indexed", 0, False, "native.exe"))
        self.assertEqual(observed["native_admission"], "indexed-v1")
        self.assertEqual(observed["native_traversal"], "active-frames")
        self.assertEqual(observed["native_payoffs"], "fold-mask-classes-v1")

    def test_parent_complete_pair_flow_retains_raw_and_pair_identity(self):
        entries = (("tiny", 10, "board-sweep", 0),
                   ("tiny", 10, "fold-mask-classes-v1", 0))
        source = {"commit": "a" * 40, "status": "", "sha256": {"tracked.py": "b" * 64}}
        build = {"executable_sha256": "c" * 64}
        metrics = {name: i / 8 for i, name in enumerate(("value_sb", "value_bb", "sb_best_response_value",
            "bb_best_response_value", "sb_gain", "bb_gain", "nash_conv", "exploitability"))}
        with patch.object(active, "_AUTH", source):
            deps = active._dependencies()
        raw_rows, payload = [], None
        case = None
        for entry in entries:
            case, raw = _protocol_child(deps, entry[2])
            for key, value in metrics.items():
                raw["payload"][key] = value
            encoded = study._canonical(raw["payload"])
            raw["payload_sha256"], raw["payload_bytes"] = hashlib.sha256(encoded).hexdigest(), len(encoded)
            raw_rows.append(raw)
            payload = raw["payload"]
        runtime = deps.quotient._runtime()
        verification = {"quality_gate": False, "numeric": {"status": "complete"},
            "numeric_metric_gaps": dict.fromkeys(metrics, 0.0),
            "exact": {"status": "complete", "result": {"exact_certificate": {
                "metrics": metrics, "threshold": 0.001, "threshold_met": False,
                "normalized_policy_sha256": "d" * 64,
                "normalized_policy_rows": payload["strategy"]}}}}
        process = [subprocess.CompletedProcess([], 0,
                    json.dumps(raw, sort_keys=True, separators=(",", ":")).encode(), b"")
                   for raw in raw_rows]
        with TemporaryDirectory() as directory, \
             patch.object(deps.native, "executable_identity", return_value=build), \
             patch.object(study, "_authenticate_source", return_value=source), \
             patch.object(study, "_AUTH_PROOF", {"commit": source["commit"], "tree": {}}), \
             patch.object(study, "_identity", return_value=source), \
             patch.object(study, "_dependencies", return_value=deps), \
             patch.object(study.active, "validate_cases", return_value={"tiny": case}), \
             patch.object(study, "SCHEDULE", entries), \
             patch.object(study, "REQUIRED_COMPLETE", frozenset({("tiny", 10)})), \
             patch.object(study, "_run_child", side_effect=process), \
             patch.object(study, "_verify", return_value=verification):
            output = Path(directory) / "evidence"
            result = study.run(output, Path("native.exe"))
            self.assertEqual(result["outcome"], "complete", result)
            report = json.loads((output / "report.json").read_bytes())
            self.assertEqual(report["calls_captured"], 2)
            self.assertEqual(len(report["paired_comparisons"]), 1)
            self.assertTrue((output / "tiny-t10-board-sweep-p0.raw.json").exists())
            self.assertTrue((output / "source-auth-proof.json").exists())

    def test_late_replay_mutation_fails_after_retaining_raw_child(self):
        entries = (("original-22-t10", 10, "board-sweep", 0),)
        source = {"commit": "a" * 40, "status": "", "sha256": {"tracked.py": "b" * 64}}
        build = {"executable_sha256": "c" * 64}
        metrics = {name: i / 8 for i, name in enumerate(("value_sb", "value_bb", "sb_best_response_value",
            "bb_best_response_value", "sb_gain", "bb_gain", "nash_conv", "exploitability"))}
        payload = _sample_payload(metrics)
        runtime = {"python": "fixture"}
        deps = SimpleNamespace(native=SimpleNamespace(executable_identity=lambda _: build),
            quotient=SimpleNamespace(_runtime=lambda: runtime),
            equivariant=SimpleNamespace(METRICS=tuple(metrics), REPLAY_TOLERANCE=1e-9), capacity=SimpleNamespace())
        raw = {"case": entries[0][0], "iterations": 10, "native_traversal": "active-frames",
            "routing": "indexed", "sample": 0, "traced": False, "request_case": {"case": entries[0][0]},
            "native_admission": "indexed-v1", "native_payoffs": "board-sweep", "runtime": runtime,
            "seconds": 1.0, "process_peak_bytes": 100, "python_allocation_peak_bytes": None,
            "counts": {}, "failure": None, "status": "complete", "payload": deepcopy(payload),
            "payload_sha256": hashlib.sha256(study._canonical(payload)).hexdigest(),
            "payload_bytes": len(study._canonical(payload)), "native_streams": []}
        with TemporaryDirectory() as directory, \
             patch.object(study, "_authenticate_source", return_value=source), \
             patch.object(study, "_AUTH_PROOF", {"commit": source["commit"]}), \
             patch.object(study, "_identity", return_value=source), \
             patch.object(study, "_dependencies", return_value=deps), \
             patch.object(study.active, "validate_cases", return_value={entries[0][0]: raw["request_case"]}), \
             patch.object(study, "SCHEDULE", entries), patch.object(study, "REQUIRED_COMPLETE", frozenset()), \
             patch.object(study, "_run_child", return_value=subprocess.CompletedProcess([], 0, b"raw", b"")), \
             patch.object(study, "_decode", return_value=raw), \
             patch.object(study, "_validate_child", return_value={"status": "complete", "payload": raw["payload"]}), \
             patch.object(study, "_verify", side_effect=lambda _case, saved, _deps: saved.update({"tampered": True}) or {}):
            output = Path(directory) / "evidence"
            result = study.run(output, Path("native.exe"))
            self.assertEqual(result["outcome"], "failed")
            self.assertTrue((output / "original-22-t10-t10-board-sweep-p0.raw.json").exists())
            self.assertTrue((output / "original-22-t10-t10-board-sweep-p0.stdout.bin").exists())
            self.assertEqual(result["calls_captured"], 1)


if __name__ == "__main__":
    unittest.main()
