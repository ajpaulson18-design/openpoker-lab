"""Source-frozen, rank-free storage-frontier batch for exact selected poker.

The runner records admitted preparation/census structure or the first exact
request rejection. It does not train, rank, query private pairs, serialize a
policy, or run a large-game oracle. No runtime or memory claim is made.
"""
import argparse
from contextlib import ExitStack
import hashlib
import itertools
import json
import platform
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch

from pokerlab.cards import DECK, expand_range
from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.exact_storage_census import census_exact_selected_storage
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.preflop_solver import _requested_runouts
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from scripts.benchmark_selected_operator import ROOT, _identity, _write

ITERATIONS = 10
RANK_CACHE_BOARDS = 1
ARITHMETIC = "fraction"
SUIT_ORBITS = True
RANGE_SIZES = (1, 2, 4, 8, 16)
BOARD_SIZES = (1, 6, 12, 24, 48)
POSTFLOP_RAISES = (0, 1, 2)
FULL_RANGE = "full-range-not-used"
FORBIDDEN_WORLD_PATHS = (
    "pokerlab.preflop_solver._enumerate_physical_worlds",
    "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds",
)
FORBIDDEN_NATIVE_PATHS = (
    "pokerlab.native_selected_operator.train_native_selected",
    "pokerlab.native_selected_dag.train_native_selected_dag",
    "pokerlab.native_public_cfr.train_native_public",
    "subprocess.Popen",
)


def _runtime_identity():
    return {"implementation": platform.python_implementation(), "version": platform.python_version(),
        "sys_version": sys.version, "system": platform.system(), "platform": sys.platform,
        "machine": platform.machine()}


def _board_fixture():
    pool0, pool1 = tuple(DECK[:12]), tuple(DECK[12:24])
    remaining = tuple(DECK[24:])
    flop, later = remaining[:3], remaining[3:]
    boards = tuple(tuple(flop) + tuple(pair) for pair in itertools.islice(itertools.permutations(later, 2), 48))
    return pool0, pool1, boards


def _range_text(pool, count):
    return ",".join("".join(hand) for hand in itertools.islice(itertools.combinations(pool, 2), count))


def _actions(raises):
    return PostflopActions(bet_sizes=(0.5,), raise_sizes=((0.5,) if raises else ()),
        max_raises=raises, include_all_in=False)


def _request(sb_range, bb_range, runouts, *, config=None, raises=0, preflop_raises=1, sizes=(0.5,)):
    acts = PostflopActions(bet_sizes=tuple(sizes), raise_sizes=(tuple(sizes) if raises else ()),
        max_raises=raises, include_all_in=False)
    preflop = PreflopConfig(small_blind=0.5, big_blind=1,
        starting_stack=(8, 8) if config is None else tuple(config),
        raise_sizes=(0.5,), max_raises=preflop_raises, include_all_in=False)
    return FourStreetSolveRequest(sb_range, bb_range, tuple("".join(board) for board in runouts),
        preflop_config=preflop, flop_actions=acts, turn_actions=acts, river_actions=acts,
        iterations=ITERATIONS, algorithm="cfrplus", traversal="public-batched",
        diagnostics="public-batched", resource_model="public-vector")


def _symmetry_boards():
    first = tuple("2c3c4h5s6h"[i:i+2] for i in range(0, 10, 2))
    second = tuple("2d3d4h5s6h"[i:i+2] for i in range(0, 10, 2))
    return first, second


def fixtures():
    """Build fixed, named cases from the retained held-out census dimensions."""
    pool0, pool1, boards = _board_fixture()
    rows = []
    for count in RANGE_SIZES:
        rows.append({"id": f"range-scale-{count}", "axis": "private_range_scale",
            "parameters": {"hands_per_seat": count, "boards": 6, "postflop_max_raises": 0},
            "request": _request(_range_text(pool0, count), _range_text(pool1, count), boards[:6])})
    for count in BOARD_SIZES:
        rows.append({"id": f"board-scale-{count}", "axis": "selected_board_scale",
            "parameters": {"hands_per_seat": 4, "boards": count, "postflop_max_raises": 0},
            "request": _request(_range_text(pool0, 4), _range_text(pool1, 4), boards[:count])})
    for raises in POSTFLOP_RAISES:
        rows.append({"id": f"menu-scale-{raises}", "axis": "betting_history_scale",
            "parameters": {"hands_per_seat": 4, "boards": 6, "postflop_max_raises": raises},
            "request": _request(_range_text(pool0, 4), _range_text(pool1, 4), boards[:6], raises=raises)})

    held_case = json.loads((ROOT / "benchmarks/results/native-selected-heldout-v1/study-receipt.json").read_text(encoding="utf-8"))["case"]
    rows.append({"id": "heldout-96-worlds", "axis": "heldout_reference",
        "parameters": {"hands_per_seat": 4, "boards": 6, "flops": 2, "represented_worlds_expected": 96},
        "request": _request(held_case["sb_range"], held_case["bb_range"], held_case["runouts"],
            raises=0, preflop_raises=held_case["config"]["max_raises"],
            config=held_case["config"]["starting_stack"])})

    original = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text(encoding="utf-8"))["case"]
    rows.append({"id": "original-22-world-anchor", "axis": "original_anchor",
        "parameters": {"hands_per_seat": 2, "boards": len(original["runouts"]), "worlds_expected": 22},
        "request": _request(original["sb_range"], original["bb_range"], original["runouts"],
            config=original["config"]["starting_stack"], raises=original["flop_config"]["max_raises"],
            preflop_raises=original["config"]["max_raises"])})

    symmetric_boards = _symmetry_boards()
    common = dict(config=(2, 2), raises=0, preflop_raises=1)
    rows.append({"id": "club-diamond-symmetric", "axis": "suit_symmetry_control",
        "parameters": {"selected_boards": ["".join(b) for b in symmetric_boards],
                       "ranges": ["AcAh:1,AdAh:1", "KcKh:1,KdKh:1"],
                       "counterpart": "range-weights-broken"},
        "request": _request("AcAh:1,AdAh:1", "KcKh:1,KdKh:1", symmetric_boards, **common)})
    rows.append({"id": "club-diamond-weight-broken", "axis": "suit_symmetry_control",
        "parameters": {"selected_boards": ["".join(b) for b in symmetric_boards],
                       "ranges": ["AcAh:0.7,AdAh:0.3", "KcKh:0.4,KdKh:0.6"],
                       "counterpart": "invariant-ranges-and-boards"},
        "request": _request("AcAh:0.7,AdAh:0.3", "KcKh:0.4,KdKh:0.6", symmetric_boards, **common)})
    return tuple(rows)


def _case_input(request):
    return {"sb_range": request.sb_range, "bb_range": request.bb_range,
        "runouts": list(request.runouts), "preflop_config": request.preflop_config.to_dict(),
        "flop_actions": request.flop_actions.to_dict(),
        "turn_actions": None if request.turn_actions is None else request.turn_actions.to_dict(),
        "river_actions": None if request.river_actions is None else request.river_actions.to_dict(),
        "iterations": request.iterations, "algorithm": request.algorithm,
        "traversal": request.traversal, "diagnostics": request.diagnostics,
        "resource_model": request.resource_model}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _phase(message):
    value = message.lower()
    if "postflop solver public tree" in value or "preflop" in value or "topology" in value:
        return "direct-topology-construction"
    if "storage census" in value or "census history-byte" in value:
        return "additional-census-admission"
    if "whole-request" in value or "output" in value or "fraction forecast" in value or "integer-bit" in value:
        return "exact-selected-request-admission"
    if "range" in value or "runout" in value or "supports" in value:
        return "request-or-kernel-input-validation"
    return "census-preparation"


def _expected_resource_rejection(exc):
    if not isinstance(exc, ValueError):
        return False
    text = str(exc).lower()
    return re.search(r"\b(?:admission|limit|exceeds?|exceeded|supports at most|too many|capacity|forecast|cap)\b", text) is not None


def _certificate_shape_screen(census):
    """Compare admitted counts with unchanged validator caps; never run it."""
    from scripts import four_street_validation as validator
    observed = {
        "hands_per_player": list(census["rank_free_kernel_receipt"]["hands"]),
        "selected_boards": census["selected_boards"],
        "physical_worlds": census["support_pair_board_occurrences"],
        # Expanded logical visits conservatively screen the validator's graph cap.
        "states": census["logical_visits"],
        "policy_rows": census["information_rows"],
        "action_slots": max(census["action_slots"],
            census["complete_solve_admission"]["packed_layout"]["upper_action_slots"]),
    }
    limits = {
        "hands_per_player": validator.MAX_HANDS_PER_PLAYER,
        "selected_boards": validator.MAX_SELECTED,
        "physical_worlds": validator.MAX_WORLDS,
        "states": validator.MAX_STATES,
        "policy_rows": validator.MAX_ROWS,
        "action_slots": validator.MAX_ACTIONS,
    }
    gates = {}
    for name, ceiling in limits.items():
        actual = observed[name]
        passes = all(value <= ceiling for value in actual) if name == "hands_per_player" else actual <= ceiling
        gates[name] = {"observed": actual, "limit": ceiling, "passes_shape_screen": passes}
    return {"version": "exact-selected-certificate-shape-screen-v1", "status": "screen-only",
        "gates": gates, "all_shape_gates_pass": all(row["passes_shape_screen"] for row in gates.values()),
        "validator_caps_source": "scripts/four_street_validation.py",
        "scope": "Shape comparison only. Passing does not establish full proof-input validity, verifier work/bit admission, independent replay, or quality; no certificate oracle was run."}


def _forbidden_child(request, case_id):
    counters = {key: 0 for key in ("training_calls", "rank_calls", "pair_query_calls",
        "terminal_query_calls", "marginal_query_calls", "native_calls", "world_producer_calls", "popen_calls")}
    def forbidden(key, label):
        def call(*args, **kwargs):
            counters[key] += 1
            raise AssertionError(f"forbidden {label} call")
        return call
    from pokerlab import exact_selected_solver as solver
    from pokerlab import exact_selected_kernel as kernel_module
    stack = ExitStack()
    for target in FORBIDDEN_WORLD_PATHS:
        stack.enter_context(patch(target, side_effect=forbidden("world_producer_calls", target)))
    stack.enter_context(patch.object(solver, "train_packed", new=forbidden("training_calls", "train_packed")))
    stack.enter_context(patch.object(kernel_module, "rank_hand", new=forbidden("rank_calls", "rank_hand")))
    stack.enter_context(patch.object(ExactSelectedRunoutKernel, "pair_probability_exact",
        new=forbidden("pair_query_calls", "pair_probability_exact")))
    stack.enter_context(patch.object(ExactSelectedRunoutKernel, "terminal_values_exact",
        new=forbidden("terminal_query_calls", "terminal_values_exact")))
    stack.enter_context(patch.object(ExactSelectedRunoutKernel, "joint_marginals_exact",
        new=forbidden("marginal_query_calls", "joint_marginals_exact")))
    for target in FORBIDDEN_NATIVE_PATHS[:-1]:
        stack.enter_context(patch(target, side_effect=forbidden("native_calls", target)))
    stack.enter_context(patch("subprocess.Popen", new=forbidden("popen_calls", "subprocess.Popen")))
    try:
        result = census_exact_selected_storage(request, rank_cache_boards=RANK_CACHE_BOARDS,
            exact_arithmetic=ARITHMETIC, suit_orbits=SUIT_ORBITS, include_witness=True)
    except Exception as exc:
        expected = _expected_resource_rejection(exc)
        if any(counters.values()):
            return {"case_id": case_id, "status": "forbidden-call-detected", "phase": _phase(str(exc)),
                "error_type": type(exc).__name__, "error": str(exc), "resource_rejection": False,
                "actual_calls": counters, "census": None}
        return {"case_id": case_id,
            "status": "resource-rejected" if expected else "failed",
            "phase": _phase(str(exc)), "error_type": type(exc).__name__, "error": str(exc),
            "resource_rejection": expected, "actual_calls": counters, "census": None}
    else:
        return {"case_id": case_id, "status": "accepted", "phase": "rank-free-census-complete",
            "error_type": None, "error": None, "resource_rejection": False,
            "actual_calls": counters, "census": result}
    finally:
        stack.close()


def child(case_id):
    selected = {item["id"]: item for item in fixtures()}
    if case_id not in selected:
        raise ValueError("Unknown fixed storage-frontier case")
    spec = selected[case_id]
    request = spec["request"]
    output = _forbidden_child(request, case_id)
    return {**output, "case": {"id": case_id, "axis": spec["axis"],
        "parameters": spec["parameters"], "request": _case_input(request)},
        "runtime": _runtime_identity(), "exact_arithmetic": ARITHMETIC,
        "rank_cache_boards": RANK_CACHE_BOARDS, "suit_orbits": SUIT_ORBITS,
        "include_witness": True,
        "independent_certificate_shape_screen": (None if output["status"] != "accepted" else
            _certificate_shape_screen(output["census"])),
        "training_requested": False, "rank_requested": False, "pair_queries_requested": False,
        "scope": "One fixed rank-free admitted setup/census. Structural counters are not timing, measured bytes, a production storage format, or a solver quality result."}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result, "duplicate child JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite child JSON")))


def _validate_child(raw, spec):
    _need(type(raw) is dict, "child record is not an object")
    _need(raw.get("case_id") == spec["id"] and raw.get("case", {}).get("axis") == spec["axis"],
          "child case identity mismatch")
    _need(raw.get("case", {}).get("parameters") == spec["parameters"] and
          raw["case"].get("request") == _case_input(spec["request"]), "child request differs from frozen fixture")
    _need(raw.get("runtime") == _runtime_identity(), "child runtime differs from batch parent")
    _need(raw.get("exact_arithmetic") == ARITHMETIC and raw.get("rank_cache_boards") == RANK_CACHE_BOARDS and
          raw.get("include_witness") is True and
          raw.get("suit_orbits") is True and raw.get("training_requested") is False and
          raw.get("rank_requested") is False and raw.get("pair_queries_requested") is False,
          "child arithmetic/admission protocol mismatch")
    calls = raw.get("actual_calls")
    _need(type(calls) is dict and set(calls) == {"training_calls", "rank_calls", "pair_query_calls",
          "terminal_query_calls", "marginal_query_calls", "native_calls", "world_producer_calls", "popen_calls"} and
          all(type(value) is int and value == 0 for value in calls.values()), "a forbidden production path was entered")
    _need(raw.get("status") in ("accepted", "resource-rejected"),
          "child reported unexpected failure: " + str(raw.get("error")))
    if raw["status"] == "resource-rejected":
        _need(raw.get("resource_rejection") is True and type(raw.get("error_type")) is str and
              type(raw.get("error")) is str and bool(raw["error"]) and type(raw.get("phase")) is str,
              "rejection lost its first type/message/phase")
        _need(_expected_resource_rejection(ValueError(raw["error"])) and raw["error_type"] == "ValueError",
              "child rejection is not an unchanged resource/admission boundary")
        _need(raw.get("phase") == _phase(raw["error"]),
              "rejection phase does not match its first error message")
        _need(raw.get("census") is None, "rejected request supplied fabricated census counts")
        _need(raw.get("independent_certificate_shape_screen") is None,
              "rejected request reported certificate shape counts without a census")
        return
    _need(raw.get("phase") == "rank-free-census-complete" and raw.get("error_type") is None and
          raw.get("error") is None and raw.get("resource_rejection") is False,
          "accepted child carries an error or rejection marker")
    census = raw.get("census")
    _need(type(census) is dict and census.get("contract") == "exact-selected-storage-census-v1" and
          census.get("chance_contract") == "exact-product-selected-v1" and census.get("training_calls") == 0 and
          census.get("pair_query_calls") == 0 and census.get("native_calls") == 0 and
          census.get("quality_gate") is None, "accepted child is not a rank-free census")
    receipt = census["rank_free_kernel_receipt"]
    _need(receipt["rank_calls"] == 0 and type(receipt.get("queries")) is int,
          "rank-free preparation executed ranking or lost its prefix-query counter")
    _need(census["complete_solve_admission"]["kernel"]["configured_limit"] == 500_000_000 and
          census["complete_solve_admission"]["retained_storage"]["entry_limit"] == 25_000_000,
          "existing exact-solver caps changed")
    screen = raw.get("independent_certificate_shape_screen")
    _need(type(screen) is dict and screen.get("version") == "exact-selected-certificate-shape-screen-v1" and
          screen.get("status") == "screen-only" and type(screen.get("gates")) is dict and
          set(screen["gates"]) == {"hands_per_player", "selected_boards", "physical_worlds", "states", "policy_rows", "action_slots"} and
          type(screen.get("all_shape_gates_pass")) is bool,
          "independent validator shape screen missing or malformed")
    _need(all(type(row) is dict and type(row.get("passes_shape_screen")) is bool
              for row in screen["gates"].values()), "shape screen gates lack individual results")
    _need(screen == _certificate_shape_screen(census),
          "independent validator shape screen differs from pinned caps/counts")
    witness = census.get("structural_witness")
    _need(type(witness) is dict and set(witness) == {"contract", "root_id", "initial_history", "vertices",
          "ranges", "selected_runouts", "scope"} and
          witness.get("contract") == "exact-selected-structural-witness-v1" and
          type(witness.get("root_id")) is int and type(witness.get("initial_history")) is list and
          type(witness.get("vertices")) is list and len(witness["vertices"]) == census["unique_vertices"] and
          type(witness.get("ranges")) is list and len(witness["ranges"]) == 2 and
          type(witness.get("selected_runouts")) is list and
          len(witness["selected_runouts"]) == census["selected_boards"],
          "compact structural witness contract/dimensions mismatch")
    _need(0 <= witness["root_id"] < len(witness["vertices"]) and
          [len(side) for side in witness["ranges"]] == census["rank_free_kernel_receipt"]["hands"] and
          all(type(row) is dict and set(row) == {"hand", "weight_hex"} and
              type(row["hand"]) is str and len(row["hand"]) == 4 and
              type(row["weight_hex"]) is str and len(row["weight_hex"]) <= 64
              for side in witness["ranges"] for row in side) and
          all(type(board) is list and len(board) == 5 and all(type(card) is str and len(card) == 2 for card in board)
              for board in witness["selected_runouts"]), "compact witness input dimensions malformed")
    expected_ranges = []
    for expression in (spec["request"].sb_range, spec["request"].bb_range):
        expanded = expand_range(expression)
        expected_ranges.append([{"hand": "".join(hand), "weight_hex": float(weight).hex()}
            for hand, weight in expanded.items()])
    expected_boards = [[*board[0], board[1], board[2]]
        for board in _requested_runouts(spec["request"].runouts)]
    _need(witness["ranges"] == expected_ranges and witness["selected_runouts"] == expected_boards,
          "compact witness inputs differ from the frozen parsed request")
    witness_admission = census["additional_census_admission"]
    _need(type(witness_admission.get("witness_entries_upper")) is int and
          witness_admission["witness_entries_upper"] <= witness_admission["limits"]["max_additional_entries"] and
          not any(key in witness for key in ("worlds", "histories", "information_rows", "policy_rows", "pair_edges")),
          "compact witness exceeded its admitted slot bound or leaked expanded rows")
    for vertex in witness["vertices"]:
        _need(type(vertex) is dict and vertex.get("kind") in ("decision", "chance", "terminal"),
              "compact witness has unsupported vertex")
        if vertex["kind"] == "decision":
            _need(type(vertex.get("player")) is int and vertex["player"] in (0, 1) and
                  type(vertex.get("actions")) is list and type(vertex.get("children")) is list and
                  len(vertex["actions"]) == len(vertex["children"]) and
                  all(type(action) is dict and set(action) == {"name", "amount_hex", "raise_to_hex", "full_raise", "token"}
                      for action in vertex["actions"]) and
                  all(type(child) is int and 0 <= child < len(witness["vertices"]) for child in vertex["children"]),
                  "compact decision witness shape malformed")
        elif vertex["kind"] == "chance":
            _need(type(vertex.get("branches")) is list and
                  all(type(branch) is list and len(branch) == 2 and type(branch[0]) is str and
                      type(branch[1]) is int and 0 <= branch[1] < len(witness["vertices"])
                      for branch in vertex["branches"]), "compact chance witness shape malformed")
        else:
            _need(type(vertex.get("contributions_hex")) is list and len(vertex["contributions_hex"]) == 2,
                  "compact terminal witness shape malformed")
    if spec["axis"] == "suit_symmetry_control":
        perms = census["suit_symmetry"]["permutations"]
        if spec["id"] == "club-diamond-symmetric":
            _need("dchs" in perms and census["suit_symmetry"]["potential_row_reduction"] > 0,
                  "invariant two-board club/diamond control lost its expected opportunity")
        else:
            _need("dchs" not in perms, "weight-broken control retained the club/diamond stabilizer")


def _summary(raw):
    if raw["status"] == "resource-rejected":
        return {"case_id": raw["case_id"], "axis": raw["case"]["axis"], "parameters": raw["case"]["parameters"],
            "status": raw["status"], "phase": raw["phase"], "error_type": raw["error_type"], "error": raw["error"],
            "actual_calls": raw["actual_calls"], **{k: None for k in (
                "information_rows", "action_slots", "dense_slots", "dense_holes", "history_token_entries",
                "history_token_bytes", "unique_vertices", "unique_edges", "vertex_prefix_contexts",
                "context_edges", "logical_visits", "maximum_depth", "numeric_payload_bytes",
                "phase_upper_bounds", "solver_retained_peak_upper", "additional_entries_upper", "additional_work_upper",
                "stabilizer_size", "supported_row_orbits", "potential_row_reduction",
                "independent_certificate_shape_screen")}}
    census = raw["census"]
    admission = census["complete_solve_admission"]
    storage = admission["retained_storage"]
    symmetry = census["suit_symmetry"]
    additional = census["additional_census_admission"]
    return {"case_id": raw["case_id"], "axis": raw["case"]["axis"], "parameters": raw["case"]["parameters"],
        "status": raw["status"], "information_rows": census["information_rows"],
        "action_slots": census["action_slots"], "dense_slots": census["dense_slots"],
        "dense_holes": census["dense_holes"], "history_token_entries": census["history_token_entries"],
        "history_token_bytes": census["history_token_bytes"], "unique_vertices": census["unique_vertices"],
        "unique_edges": census["unique_edges"], "vertex_prefix_contexts": census["vertex_prefix_contexts"],
        "context_edges": census["context_edges"], "logical_visits": census["logical_visits"],
        "maximum_depth": census["maximum_depth"],
        "numeric_payload_bytes": census["four_packed_numeric_buffers_payload_bytes"],
        "phase_upper_bounds": storage["phase_upper_bounds"],
        "solver_retained_peak_upper": storage["whole_request_peak_upper"],
        "additional_entries_upper": additional["retained_entries_upper"],
        "additional_work_upper": additional["modeled_work_upper"],
        "stabilizer_size": symmetry["conservative_stabilizer_size"],
        "suit_permutations": symmetry["permutations"],
        "supported_row_orbits": symmetry["supported_row_orbits"],
        "potential_row_reduction": symmetry["potential_row_reduction"],
        "independent_certificate_shape_screen": raw["independent_certificate_shape_screen"],
        "structural_witness": {"contract": census["structural_witness"]["contract"],
            "vertex_count": len(census["structural_witness"]["vertices"]),
            "input_range_counts": [len(side) for side in census["structural_witness"]["ranges"]],
            "selected_board_count": len(census["structural_witness"]["selected_runouts"]),
            "scope": census["structural_witness"]["scope"]},
        "actual_calls": raw["actual_calls"]}


def run(output):
    output = Path(output).resolve()
    _need(output != ROOT and ROOT not in output.parents and not output.exists(), "Use a new external census directory")
    source = _identity()
    _need(not source["status"], "Commit and clean all source before the fixed census batch")
    specs = fixtures()
    output.mkdir(parents=True)
    from scripts import four_street_validation as physical
    protocol = {"version": "exact-selected-storage-frontier-v1", "source_commit": source["commit"],
        "source_sha256": source["sha256"], "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime": _runtime_identity(), "case_count": len(specs), "cases": [
            {"id": x["id"], "axis": x["axis"], "parameters": x["parameters"], "request": _case_input(x["request"])}
            for x in specs], "iterations_requested": ITERATIONS, "exact_arithmetic": ARITHMETIC,
        "rank_cache_boards": RANK_CACHE_BOARDS, "suit_orbits": SUIT_ORBITS,
        "structural_witness": {"requested": True,
            "contract": "exact-selected-structural-witness-v1",
            "include_witness": True,
            "scope": "Compact unique graph and input snapshot only; no expanded occurrences, histories, worlds or policy rows. Structural replay remains conditional on this exported graph."},
        "independent_certificate_shape_screen": {"version": "exact-selected-certificate-shape-screen-v1",
            "validator_caps_source": "scripts/four_street_validation.py",
            "caps": {"hands_per_player": physical.MAX_HANDS_PER_PLAYER,
                "selected_boards": physical.MAX_SELECTED, "physical_worlds": physical.MAX_WORLDS,
                "states": physical.MAX_STATES, "policy_rows": physical.MAX_ROWS,
                "action_slots": physical.MAX_ACTIONS},
            "scope": "Screen-only; all-shape-pass does not imply full proof/work/bit admission, independent replay, or quality."},
        "retry_policy": "none; preserve raw first output and first failure for each case",
        "scope": "Rank-free preparation and bounded support/history/suit-stabilizer census. No solve, policy, rank, pair query, or performance claim.",
        "fixture_provenance": {"range_and_board_axes": "retained native-selected-heldout-v1 rank-free census pools DECK[:12], DECK[12:24], remaining board pool; counts sampled from the archived dimensions",
            "heldout": "benchmarks/results/native-selected-heldout-v1/study-receipt.json case",
            "original_anchor": "benchmarks/four-street-integration-v1.json case",
            "symmetry": "club/diamond paired boards and invariant AcAh/AdAh, KcKh/KdKh priors; weight-broken counterpart"}}
    _write(output / "source-before.json", source)
    _write(output / "protocol.json", protocol)
    records, summaries, attempted_ids, failure = [], [], [], None
    for spec in specs:
        label = spec["id"]
        process = None
        try:
            command = [sys.executable, "-B", "-m", "scripts.benchmark_exact_storage_frontier", "--child", label]
            attempted_ids.append(label)
            process = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
            (output / (label + ".json")).write_bytes(process.stdout)
            (output / (label + ".stderr.txt")).write_bytes(process.stderr)
            _need(process.returncode == 0, "child process exited with status " + str(process.returncode))
            raw = _decode(process.stdout)
            _validate_child(raw, spec)
            digest = hashlib.sha256(process.stdout).hexdigest()
            records.append({"artifact": label + ".json", "raw_sha256": digest,
                "status": raw["status"], "phase": raw["phase"], "actual_calls": raw["actual_calls"]})
            summaries.append(_summary(raw))
            print(label, raw["status"], flush=True)
        except Exception as exc:
            failure = {"case_id": label, "artifact": label + ".json", "error_type": type(exc).__name__,
                "error": str(exc), "child_returncode": None if process is None else process.returncode}
            _write(output / (label + "-failure.json"), failure)
            break
    source_after = None
    try:
        source_after = _identity()
        if source_after != source:
            failure = {"stage": "source-changed", "prior_failure": failure}
    except Exception as exc:
        failure = {"stage": "source-identity-failed", "error_type": type(exc).__name__,
            "error": str(exc), "prior_failure": failure}
    _write(output / "source-after.json", source_after)
    axes = {}
    for axis in sorted({spec["axis"] for spec in specs}):
        selected = [row for row in summaries if row["axis"] == axis]
        axes[axis] = {"case_count_planned": sum(1 for spec in specs if spec["axis"] == axis),
            "case_count_attempted": sum(next(spec for spec in specs if spec["id"] == case_id)["axis"] == axis
                                         for case_id in attempted_ids),
            "accepted": sum(row["status"] == "accepted" for row in selected),
            "resource_rejected": sum(row["status"] == "resource-rejected" for row in selected),
            "observations": selected}
    report = {"outcome": "complete" if failure is None and len(summaries) == len(specs) else "failed",
        "source_commit": source["commit"], "protocol": protocol, "cases": summaries, "axes": axes,
        "raw_records": records, "failure": failure, "attempted_case_ids": attempted_ids,
        "attempted_cases": len(attempted_ids), "validated_records": len(records),
        "accepted_cases": sum(row["status"] == "accepted" for row in records),
        "resource_rejections": sum(row["status"] == "resource-rejected" for row in records),
        "training_calls": sum(row["actual_calls"]["training_calls"] for row in records),
        "rank_calls": sum(row["actual_calls"]["rank_calls"] for row in records),
        "pair_query_calls": sum(row["actual_calls"]["pair_query_calls"] for row in records),
        "native_calls": sum(row["actual_calls"]["native_calls"] for row in records),
        "popen_calls_inside_children": sum(row["actual_calls"]["popen_calls"] for row in records),
        "scope": protocol["scope"]}
    _write(output / "report.json", report)
    manifest = {"source_commit": source["commit"], "sha256": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.iterdir()) if path.is_file()}}
    _write(output / "manifest.json", manifest)
    return {"outcome": report["outcome"], "cases": report["attempted_cases"],
        "manifest_sha256": hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest(), "failure": failure}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", choices=tuple(spec["id"] for spec in fixtures()))
    args = parser.parse_args()
    if args.child:
        result = child(args.child)
    elif args.output is not None:
        result = run(args.output)
    else:
        parser.error("--output or --child is required")
    print(json.dumps(result, allow_nan=False))
    return 0 if args.child or result["outcome"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
