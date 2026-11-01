"""Independent parity checks for the card-free native betting template."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest
import zipfile

from tests.test_four_street_validation import CASE
from tests.virtual_betting_template_reference import (
    DEFAULT_NATIVE_TEST_LIMITS, _double_bits, _initial_state, _source_parts, _state_parts,
    build_reference_template, literal_reference_census, native_config_tokens, native_state_tokens,
    project_unfiltered_selected_prefix_counts,
    override_native_config_bits,
)
from scripts.matrix_free_certificate_budget import Budget
from scripts.matrix_free_four_street_rules import _actions_for, _next_decision, _snapshot_inputs
from scripts.preflop_validation import _State


ROOT = Path(__file__).resolve().parents[1]
EXE_ENV = "OPENPOKER_NATIVE_VIRTUAL_BETTING_TEMPLATE_EXE"


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def authenticate_native_executable(executable):
    """Authenticate the optional native test executable and complete build closure."""
    from scripts import build_native_exact_four_street as builder

    supplied_exe = Path(executable)
    if supplied_exe.is_symlink():
        raise AssertionError("native template executable path cannot be a symbolic link")
    exe = supplied_exe.resolve(strict=True)
    if not exe.is_file() or exe.is_symlink():
        raise AssertionError("native template executable must be a regular file")
    manifest_path = exe.parent / "native-exact-build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract") != "native-exact-build-v1":
        raise AssertionError("native template build manifest contract mismatch")
    if manifest.get("target") != "virtual-betting-template":
        raise AssertionError("native template build target mismatch")
    expected_sources = set(builder.TARGETS["virtual-betting-template"][1])
    expected_sources.update((
        "scripts/build_native_exact_four_street.py",
        "third_party/boost-multiprecision-1.92.0/manifest.json",
        "third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt",
        "third_party/boost-multiprecision-1.92.0/headers.zip",
    ))
    source_hashes = manifest.get("source_sha256")
    if type(source_hashes) is not dict or set(source_hashes) != expected_sources:
        raise AssertionError("native template source closure is incomplete or unexpected")
    for name, expected_hash in source_hashes.items():
        source = ROOT / Path(*name.split("/"))
        if source.is_symlink() or not source.is_file() or _hash(source) != expected_hash:
            raise AssertionError(f"native template source changed: {name}")
    lf_hashes = manifest.get("source_lf_sha256")
    expected_lf_names = {name for name in expected_sources if not name.endswith(".zip")}
    if type(lf_hashes) is not dict or set(lf_hashes) != expected_lf_names:
        raise AssertionError("native template normalized source closure is incomplete")
    for name, expected_hash in lf_hashes.items():
        source = ROOT / Path(*name.split("/"))
        if hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != expected_hash:
            raise AssertionError(f"native template normalized source changed: {name}")
    if manifest.get("executable_sha256") != _hash(exe):
        raise AssertionError("native template executable hash mismatch")
    if Path(manifest.get("executable", "")).resolve() != exe:
        raise AssertionError("native template executable path mismatch")
    if manifest.get("dependency_headers") != 198 or manifest.get("license") != "BSL-1.0":
        raise AssertionError("native template dependency pin mismatch")
    dependency_root = ROOT / "third_party/boost-multiprecision-1.92.0"
    dependency = json.loads((dependency_root / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("dependency_commit") != dependency.get("commit") or
            manifest.get("dependency_archive_sha256") != dependency.get("archive_sha256") or
            manifest.get("dependency_manifest_sha256") != _hash(dependency_root / "manifest.json")):
        raise AssertionError("native template dependency provenance mismatch")
    if (dependency.get("commit") != "1f7acd34fe929573c131e869867dc1d12b8080b6" or
            dependency.get("archive_sha256") != builder.HEADER_ARCHIVE_SHA256 or
            _hash(dependency_root / "manifest.json") != builder.DEPENDENCY_MANIFEST_SHA256 or
            _hash(dependency_root / "LICENSE_1_0.txt") != builder.LICENSE_SHA256):
        raise AssertionError("native template dependency pin differs from the builder")
    expected_headers = dependency.get("headers_sha256")
    if type(expected_headers) is not dict or len(expected_headers) != 198:
        raise AssertionError("pinned native header inventory is malformed")
    include = exe.parent / "boost-include"
    actual_names = set()
    for path in include.rglob("*"):
        if path.is_symlink():
            raise AssertionError("native template extracted header closure contains a link")
        if path.is_file():
            actual_names.add(path.relative_to(include).as_posix())
            if _hash(path) != expected_headers.get(path.relative_to(include).as_posix()):
                raise AssertionError(f"extracted native header changed: {path.name}")
    if actual_names != set(expected_headers):
        raise AssertionError("extracted native header closure is incomplete or unexpected")
    return {"manifest": manifest, "manifest_path": manifest_path,
            "executable": exe, "source_hashes": source_hashes}


def parse_native_export(text):
    lines = text.splitlines()
    if not lines or lines[0] != "VIRTUAL_BETTING_RESULT_V1":
        raise AssertionError(f"native template returned an error or invalid header: {text[:240]!r}")
    cursor = 1

    def take(label):
        nonlocal cursor
        if cursor >= len(lines):
            raise AssertionError(f"missing {label} record")
        fields = lines[cursor].split()
        cursor += 1
        if not fields or fields[0] != label:
            raise AssertionError(f"expected {label} record, got {fields[:2]!r}")
        return fields

    root = int(take("root")[1])
    receipt_fields = take("receipt")
    if len(receipt_fields) != 8:
        raise AssertionError("receipt field count mismatch")
    receipt = tuple(map(int, receipt_fields[1:]))
    transport_fields = take("transport")
    if len(transport_fields) != 5:
        raise AssertionError("transport field count mismatch")
    transport = tuple(map(int, transport_fields[1:]))
    history_scope_fields = take("history_scope")
    if len(history_scope_fields) != 2:
        raise AssertionError("history scope field count mismatch")
    history_scope = history_scope_fields[1]

    streets = []
    for street in (0, 3, 4, 5):
        fields = take("street")
        if len(fields) != 8 or int(fields[1]) != street:
            raise AssertionError("street record shape/order mismatch")
        streets.append(tuple(map(int, fields[1:])))

    nodes = []
    edges = []
    while cursor < len(lines):
        fields = take("node")
        if len(fields) != 27:
            raise AssertionError(f"node record field count mismatch: {len(fields)}")
        node_id = int(fields[1])
        node = {
            "id": node_id, "phase": int(fields[2]), "street": int(fields[3]),
            "actor": int(fields[4]), "next_street": int(fields[5]),
            "winner": int(fields[6]), "committed": (int(fields[7], 16), int(fields[8], 16)),
            "increment": int(fields[9], 16), "raises": int(fields[10]),
            "reopened": bool(int(fields[11])), "checks": int(fields[12]),
            "origin_present": bool(int(fields[13])), "origin": int(fields[14], 16),
            "boundary_pot": int(fields[15], 16), "local_present": bool(int(fields[16])),
            "local": (int(fields[17], 16), int(fields[18], 16)),
            "history_empty": bool(int(fields[19])), "matched": int(fields[20], 16),
            "edge_count": int(fields[21]), "history": tuple(map(int, fields[22:27])),
        }
        if node_id != len(nodes):
            raise AssertionError("node IDs are not contiguous in export order")
        nodes.append(node)
        for expected_index in range(node["edge_count"]):
            edge_fields = take("edge")
            if len(edge_fields) != 11:
                raise AssertionError("edge record field count mismatch")
            edge = {
                "parent": int(edge_fields[1]), "index": int(edge_fields[2]),
                "kind": edge_fields[3], "amount": int(edge_fields[4], 16),
                "target": int(edge_fields[5], 16), "local_target": int(edge_fields[6], 16),
                "has_local_target": bool(int(edge_fields[7])),
                "full_raise": bool(int(edge_fields[8])),
                "token": None if edge_fields[9] == "-" else edge_fields[9],
                "child": int(edge_fields[10]),
            }
            if edge["parent"] != node_id or edge["index"] != expected_index:
                raise AssertionError("edge parent/index mismatch")
            edges.append(edge)
    if len(nodes) != receipt[0] or len(edges) != receipt[1]:
        raise AssertionError("receipt totals do not match the exported graph")
    if not 0 <= root < len(nodes):
        raise AssertionError("root ID is outside exported graph")
    return {"root": root, "receipt": receipt, "transport": transport,
            "history_scope": history_scope, "streets": tuple(streets),
            "nodes": tuple(nodes), "edges": tuple(edges)}


def compare_export_to_reference(actual, expected, *, initial_history_empty=True):
    if actual["root"] != expected.root:
        raise AssertionError("root ID differs from reference")
    if actual["history_scope"] != ("empty-root" if initial_history_empty else "suffix-only"):
        raise AssertionError("initial-history scope marker mismatch")
    receipt = actual["receipt"]
    for actual_value, expected_value, name in (
        (receipt[0], expected.receipt["nodes"], "nodes"),
        (receipt[1], expected.receipt["edges"], "edges"),
        (receipt[5], expected.receipt["logical_occurrences"], "logical occurrences"),
        (receipt[6], expected.receipt["max_depth"], "depth"),
    ):
        if actual_value != expected_value:
            raise AssertionError(f"{name} differs: native={actual_value}, reference={expected_value}")
    expected_streets = []
    counts = expected.receipt
    for i, street in enumerate((0, 3, 4, 5)):
        expected_streets.append((street, *counts["decisions"][i], counts["reveals"][i],
                                 counts["folds"][i], counts["showdowns"][i],
                                 counts["action_slots"][i]))
    if actual["streets"] != tuple(expected_streets):
        raise AssertionError("per-street occurrence totals differ")
    if len(actual["nodes"]) != len(expected.nodes):
        raise AssertionError("node count differs")
    expected_edges = []
    for i, node in enumerate(expected.nodes):
        raw = node.state
        state = raw.state if hasattr(raw, "state") else raw
        next_street = raw.board_length if hasattr(raw, "board_length") else 0
        winner = raw.winner if hasattr(raw, "winner") and raw.winner is not None else 2
        origin_present = state.origin is not None
        local_present = state.local_committed is not None
        histories = expected.histories[i]
        values = (
            node.phase == {0: "decision", 1: "reveal", 2: "fold", 3: "showdown"}[
                actual["nodes"][i]["phase"]],
            actual["nodes"][i]["street"] == state.street,
            actual["nodes"][i]["actor"] == state.player,
            actual["nodes"][i]["next_street"] == next_street,
            actual["nodes"][i]["winner"] == winner,
            actual["nodes"][i]["committed"] == tuple(_double_bits(v) for v in state.committed),
            actual["nodes"][i]["increment"] == _double_bits(state.increment),
            actual["nodes"][i]["raises"] == state.raises,
            actual["nodes"][i]["reopened"] == bool(state.reopened),
            actual["nodes"][i]["checks"] == state.checks,
            actual["nodes"][i]["origin_present"] == origin_present,
            actual["nodes"][i]["origin"] == _double_bits(0.0 if state.origin is None else state.origin),
            actual["nodes"][i]["boundary_pot"] == _double_bits(state.boundary_pot),
            actual["nodes"][i]["local_present"] == local_present,
            actual["nodes"][i]["local"] == tuple(_double_bits(x) for x in
                ((0.0, 0.0) if state.local_committed is None else state.local_committed)),
            actual["nodes"][i]["history_empty"] == node.history_empty,
            actual["nodes"][i]["matched"] == _double_bits(min(state.committed)),
            actual["nodes"][i]["edge_count"] == len(node.edges),
            actual["nodes"][i]["history"] == histories,
        )
        if not all(values):
            raise AssertionError(f"native node {i} differs from independent state or census")
        for edge_index, edge in enumerate(node.edges):
            expected_edges.append({
                "parent": i, "index": edge_index,
                "kind": edge.kind, "amount": _double_bits(edge.amount),
                "target": _double_bits(edge.target), "local_target": _double_bits(edge.local_target),
                "has_local_target": edge.has_local_target, "full_raise": edge.full_raise,
                "token": edge.token, "child": edge.child,
            })
    if tuple(expected_edges) != actual["edges"]:
        for exp, got in zip(expected_edges, actual["edges"]):
            if exp != got:
                raise AssertionError(f"native edge differs: expected={exp}, actual={got}")
        raise AssertionError("edge count differs")


def compare_state_menu_and_successors(actual, case, supplied):
    budget = Budget()
    _case, _ranges, _boards, stacks, _sb, _bb, stages = _snapshot_inputs(
        case, budget, {"hands_per_seat": 16, "selected_outcomes": 64,
                       "public_nodes": 250_000, "public_depth": 64})
    state = _State(supplied["street"], supplied["actor"], supplied["committed"],
                   history=("__synthetic_suffix__",) if not supplied["history_empty"] else (),
                   increment=supplied["increment"], raises=supplied["raises"],
                   reopened=supplied["reopened"], checks=supplied["checks"],
                   origin=supplied["origin"] if supplied["origin_present"] else None,
                   boundary_pot=supplied["boundary_pot"],
                   local_committed=supplied["local"] if supplied["local_present"] else None)
    actions, details = _actions_for(state, stacks, stages, budget)
    root_edges = [edge for edge in actual["edges"] if edge["parent"] == actual["root"]]
    if len(root_edges) != len(actions):
        raise AssertionError("STATE root action width differs from independent numeric rules")
    for edge, action, detail in zip(root_edges, actions, details):
        local = detail[4] if len(detail) > 4 else None
        if (edge["kind"], edge["amount"], edge["target"], edge["local_target"],
                edge["has_local_target"], edge["full_raise"], edge["token"]) != (
                action.name, _double_bits(action.amount), _double_bits(action.raise_to),
                _double_bits(0.0 if local is None else local), local is not None,
                bool(detail[3]), action.token):
            raise AssertionError("STATE legal menu differs from independent numeric rules")
        child, _winner = _next_decision(state, detail, stacks, budget)
        child_flag = supplied["history_empty"] if detail[0] == "fold" else False
        expected_key = _state_parts(child, child_flag)[4]
        node = actual["nodes"][edge["child"]]
        actual_key = (node["phase"], node["street"], node["actor"], node["next_street"],
                      node["winner"], *node["committed"], node["increment"], node["raises"],
                      node["reopened"], node["checks"], node["origin_present"], node["origin"],
                      node["boundary_pot"], node["local_present"], *node["local"],
                      node["history_empty"])
        if expected_key != actual_key:
            raise AssertionError("STATE successor differs from independent money/state transition")


def run_probe(executable, request):
    completed = subprocess.run([str(executable)], input=request, text=True,
                               capture_output=True, timeout=30, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"native probe exited {completed.returncode}: {completed.stderr}")
    return completed.stdout


class PythonReferenceTests(unittest.TestCase):
    def test_accepted_case_has_bounded_full_history_template(self):
        model = build_reference_template(CASE)
        self.assertEqual((len(model.nodes), model.receipt["edges"],
                          model.receipt["logical_occurrences"]), (109, 116, 289))
        self.assertEqual(model.receipt["decisions"], [[2, 2], [6, 6], [18, 18], [38, 38]])
        self.assertGreater(max(path[0] for path in model.histories), 1)

    def test_fold_token_has_separate_semantic_and_legacy_history_counters(self):
        model = build_reference_template(CASE)
        fold_nodes = [i for i, node in enumerate(model.nodes) if node.phase == "fold"]
        self.assertTrue(fold_nodes)
        for node_id in fold_nodes:
            paths, semantic_tokens, semantic_bytes, legacy_tokens, legacy_bytes = model.histories[node_id]
            self.assertEqual(semantic_tokens - legacy_tokens, paths)
            self.assertEqual(semantic_bytes - legacy_bytes, 4 * paths)
        for node_id, node in enumerate(model.nodes):
            if node.phase != "fold":
                paths, semantic_tokens, semantic_bytes, legacy_tokens, legacy_bytes = model.histories[node_id]
                self.assertEqual((semantic_tokens, semantic_bytes), (legacy_tokens, legacy_bytes))

    def test_literal_tree_walk_independently_recovers_dag_path_census(self):
        model = build_reference_template(CASE)
        literal = literal_reference_census(CASE)
        self.assertEqual(literal["nodes"], model.receipt["logical_occurrences"])
        self.assertEqual(literal["edges"], literal["nodes"] - 1)
        self.assertEqual(set(literal["by_key"]), {node.key for node in model.nodes})
        for node_id, node in enumerate(model.nodes):
            self.assertEqual(literal["by_key"][node.key], model.histories[node_id])
        for field in ("decisions", "reveals", "folds", "showdowns", "action_slots"):
            self.assertEqual(literal["streets"][field], model.receipt[field])

    def test_saved_v1_betting_configuration_has_independent_card_free_census(self):
        case = copy.deepcopy(CASE)
        case["config"].update({"starting_stack": 8.0, "small_blind": 0.5,
                               "big_blind": 1.0, "raise_sizes": [1.0],
                               "max_raises": 1, "include_all_in": True})
        for street in ("flop_config", "turn_config", "river_config"):
            case[street] = {"bet_sizes": [0.5, 1.0], "raise_sizes": [0.25],
                            "max_raises": 1, "include_all_in": True}
        model = build_reference_template(case)
        literal = literal_reference_census(case)
        self.assertEqual((model.receipt["nodes"], model.receipt["edges"],
                          model.receipt["logical_occurrences"]), (388, 410, 1105))
        self.assertEqual(literal["nodes"], 1105)
        self.assertEqual(set(literal["by_key"]), {node.key for node in model.nodes})
        for node_id, node in enumerate(model.nodes):
            self.assertEqual(literal["by_key"][node.key], model.histories[node_id])

    def test_selected_prefix_projection_matches_saved_six_runout_public_census(self):
        template = build_reference_template(CASE)
        projected = project_unfiltered_selected_prefix_counts(CASE, template)
        self.assertEqual(projected["prefix_counts"], {0: 1, 3: 2, 4: 4, 5: 6})
        self.assertEqual(projected["counts"], {
            "decisions": 628, "action_slots": 1257, "reveals": 97,
            "reveal_edges": 156, "folds": 315, "showdowns": 374,
            "history_tokens": 14582, "history_characters": 86877,
            "semantic_history_tokens": 14897, "semantic_history_characters": 88137,
            "action_token_characters": 6187, "public_nodes": 1414, "depth": 14,
        })
        self.assertTrue(projected["unfiltered_prefix_geometry"])

    def test_initial_history_flag_controls_only_bb_option_and_suffix_scope(self):
        empty = build_reference_template(CASE, initial_history_empty=True)
        suffix = build_reference_template(CASE, initial_history_empty=False)
        self.assertFalse(empty.nodes[empty.root].history_empty is False)
        self.assertFalse(suffix.nodes[suffix.root].history_empty)
        call_empty = next(edge for edge in empty.nodes[empty.root].edges if edge.kind == "call")
        call_suffix = next(edge for edge in suffix.nodes[suffix.root].edges if edge.kind == "call")
        self.assertEqual(empty.nodes[call_empty.child].phase, "decision")
        self.assertEqual(suffix.nodes[call_suffix.child].phase, "reveal")
        # Supplied initial tokens are intentionally not part of path counters.
        self.assertEqual(suffix.histories[suffix.root], (1, 0, 0, 0, 0))

    def test_future_runout_cards_do_not_change_template_identity_or_wire(self):
        alternate = copy.deepcopy(CASE)
        alternate["runouts"] = ["2d3d4c7s8s", "2d3d4c7sKh", "2d3d4cKh8s",
                                "2d3d4cQh8s", "5d6c7h8d9s", "5d6c7h8dJs"]
        self.assertEqual(native_config_tokens(CASE), native_config_tokens(alternate))
        left = build_reference_template(CASE)
        right = build_reference_template(alternate)
        self.assertEqual(left.receipt, right.receipt)
        self.assertEqual([node.key for node in left.nodes], [node.key for node in right.nodes])

    def test_money_and_history_fields_are_part_of_reference_state_key(self):
        _, stacks, sb, bb, _ = _source_parts(CASE, Budget())
        state = _initial_state(stacks, sb, bb, Budget())
        _, _, _, _, key = _state_parts(state, True)
        from dataclasses import replace
        self.assertNotEqual(key, _state_parts(replace(state, player=1), True)[4])
        self.assertNotEqual(key, _state_parts(replace(state, committed=(0.75, 1.0)), True)[4])
        self.assertNotEqual(key, _state_parts(state, False)[4])


class NativeTemplateParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = os.environ.get(EXE_ENV)
        if not executable:
            raise unittest.SkipTest(f"{EXE_ENV} is not set; native checks run in the compiled CI job")
        cls.auth = authenticate_native_executable(executable)
        cls.executable = cls.auth["executable"]

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "auth"):
            after = authenticate_native_executable(cls.executable)
            if after["source_hashes"] != cls.auth["source_hashes"] or \
                    after["manifest"]["executable_sha256"] != cls.auth["manifest"]["executable_sha256"]:
                raise AssertionError("native source or executable changed during parity tests")

    def assert_case_parity(self, case, *, initial_history_empty=True, wire=None):
        expected = build_reference_template(case, initial_history_empty=initial_history_empty)
        request = wire or native_config_tokens(case, initial_history_empty=initial_history_empty,
                                               limits=DEFAULT_NATIVE_TEST_LIMITS)
        actual = parse_native_export(run_probe(self.executable, request))
        compare_export_to_reference(actual, expected,
                                    initial_history_empty=initial_history_empty)
        fields = request.split()
        node_limit, edge_limit, work_limit, entry_limit = map(int, fields[3:7])
        output_upper = 4096 + 768 * node_limit + 192 * edge_limit
        expected_transport = 8 * len(request.rstrip("\n")) + 32 * len(fields) + 8 * output_upper
        self.assertEqual(actual["transport"],
                         (len(request.rstrip("\n")), output_upper, expected_transport, 256))
        self.assertLessEqual(actual["receipt"][2] + expected_transport, work_limit)
        self.assertLessEqual(actual["receipt"][3] + actual["transport"][3], entry_limit)
        return actual, expected

    def test_accepted_complete_template_matches_independent_reference(self):
        actual, expected = self.assert_case_parity(CASE)
        self.assertEqual((actual["receipt"][0], actual["receipt"][1], actual["receipt"][5]),
                         (109, 116, 289))
        self.assertEqual(len(actual["nodes"]), len(expected.nodes))

    def test_saved_v1_betting_config_matches_independent_card_free_reference(self):
        case = copy.deepcopy(CASE)
        case["config"].update({"starting_stack": 8.0, "small_blind": 0.5,
                               "big_blind": 1.0, "raise_sizes": [1.0],
                               "max_raises": 1, "include_all_in": True})
        for street in ("flop_config", "turn_config", "river_config"):
            case[street] = {"bet_sizes": [0.5, 1.0], "raise_sizes": [0.25],
                            "max_raises": 1, "include_all_in": True}
        actual, expected = self.assert_case_parity(case)
        self.assertEqual((len(actual["nodes"]), actual["receipt"][1],
                          actual["receipt"][5]), (388, 410, 1105))
        self.assertEqual(expected.receipt["nodes"], 388)

    def test_initial_history_false_suppresses_preflop_bb_option(self):
        self.assert_case_parity(CASE, initial_history_empty=False)

    def test_binary64_money_inputs_are_cleaned_before_state_construction(self):
        case = copy.deepcopy(CASE)
        case["config"]["starting_stack"] = [8.0000000004, 8.0000000004]
        case["config"]["small_blind"] = 0.5000000004
        case["config"]["big_blind"] = 1.0000000004
        base_wire = native_config_tokens(case)
        raw_wire = override_native_config_bits(base_wire, stack0=8.0000000004,
                                               stack1=8.0000000004,
                                               small_blind=0.5000000004,
                                               big_blind=1.0000000004)
        self.assert_case_parity(case, wire=raw_wire)

    def test_post_rounding_blind_gap_must_stay_strictly_positive(self):
        invalid = copy.deepcopy(CASE)
        invalid["config"]["small_blind"] = 0.5000000002
        invalid["config"]["big_blind"] = 0.5000000013
        with self.assertRaisesRegex(ValueError, "blinds"):
            build_reference_template(invalid)
        base_wire = native_config_tokens(CASE)
        wire = override_native_config_bits(base_wire, small_blind=0.5000000002,
                                           big_blind=0.5000000013)
        response = run_probe(self.executable, wire)
        self.assertTrue(response.startswith("ERR invalid rounded stack or blinds\n"), response)

    def test_blind_all_in_exports_posted_commitments_and_matched_amount(self):
        case = copy.deepcopy(CASE)
        case["config"]["starting_stack"] = [0.5, 1.0]
        actual, expected = self.assert_case_parity(case)
        root = actual["nodes"][actual["root"]]
        self.assertEqual(root["phase"], 3)
        self.assertEqual(root["committed"], (_double_bits(0.5), _double_bits(1.0)))
        self.assertEqual(root["matched"], _double_bits(0.5))
        self.assertEqual(expected.nodes[expected.root].phase, "showdown")

    def test_short_all_in_reopen_and_local_refund_states_match(self):
        case = copy.deepcopy(CASE)
        case["config"].update({"starting_stack": [3.25, 4.0], "raise_sizes": [0.5, 1.0],
                               "max_raises": 2, "include_all_in": True})
        for field in ("flop_config", "turn_config", "river_config"):
            case[field] = {"bet_sizes": [0.5, 1.0], "raise_sizes": [0.5, 1.0],
                           "max_raises": 2, "include_all_in": True}
        actual, _ = self.assert_case_parity(case)
        self.assertTrue(any(edge["kind"] == "all_in" for edge in actual["edges"]))
        self.assertTrue(any(node["local_present"] for node in actual["nodes"]))
        self.assertTrue(any(not node["reopened"] for node in actual["nodes"]))

    def test_state_mode_accepts_decision_and_rejects_invalid_state_fields(self):
        valid = {"phase": 0, "street": 3, "actor": 1, "committed": (1.5, 1.5),
                 "increment": 0.0, "raises": 0, "reopened": True, "checks": 0,
                 "origin_present": True, "origin": 1.5, "boundary_pot": 3.0,
                 "local_present": True, "local": (0.0, 0.0), "history_empty": False}
        request = native_state_tokens(CASE, valid)
        actual = parse_native_export(run_probe(self.executable, request))
        self.assertEqual(actual["nodes"][actual["root"]]["street"], 3)
        compare_state_menu_and_successors(actual, CASE, valid)
        for changed, expected_error in (
            ({**valid, "phase": 1}, "state must be decision"),
            ({**valid, "street": 2}, "invalid street"),
            ({**valid, "origin_present": False}, "invalid origin state"),
            ({**valid, "local_present": False, "local": (0.5, 0.0)}, "invalid local state"),
            ({**valid, "boundary_pot": 2.5}, "boundary pot does not match origin"),
            ({**valid, "committed": (1.25, 1.5)}, "local/global commitment mismatch"),
            ({**valid, "history_empty": True}, "empty history after preflop"),
            ({**valid, "actor": 2}, "integer cap"),
        ):
            with self.subTest(state=changed):
                response = run_probe(self.executable, native_state_tokens(CASE, changed))
                self.assertTrue(response.startswith("ERR " + expected_error), response)


if __name__ == "__main__":
    unittest.main()
