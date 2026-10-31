"""Fixed source-frozen V4 board-sweep versus V5 fold-mask-class study.

This compares two native payoff operators under the same active-frame indexed
trainer. Every outcome is captured before validation; no retries or fixture
replacement are allowed. Timings are scoped to these finite selected games.
"""
from argparse import ArgumentParser
import base64
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from scripts import benchmark_native_active_frames as active

ROOT = Path(__file__).resolve().parents[1]
PAYOFFS = ("board-sweep", "fold-mask-classes-v1")
BASELINES = ("original-22-t10", "payoff-varied-t10", "blocker-18",
             "asymmetric-weighted", "mixed-stabilizer", "physical-g6")
MATRIX = ("balanced-4x4-unit", "balanced-8x8-unit", "balanced-16x16-unit", "asymmetric-2x16-unit")
OPTIONS = {**active.OPTIONS, "native_traversal": "active-frames"}
FOLD_FIELDS = ("setup_work_upper", "setup_entries_upper", "mask_entries", "membership_entries",
    "classes_sb", "classes_bb", "class_calls_sb", "class_calls_bb", "literal_calls_sb",
    "literal_calls_bb", "buckets_sb", "buckets_bb", "own_checks", "retained_pair_entries",
    "query_allowance_retained", "combined_work", "combined_entries")

_schedule = []
for _case in BASELINES:
    _schedule.extend((_case, 10, mode, 0) for mode in PAYOFFS)
_schedule.extend(("original-22-t10", 10, mode, sample) for sample, pair in (
    (1, ("fold-mask-classes-v1", "board-sweep")),
    (2, ("board-sweep", "fold-mask-classes-v1"))) for mode in pair)
for _iterations in (40, 60):
    _schedule.extend(("original-22-t10", _iterations, mode, 0) for mode in PAYOFFS)
_schedule.extend(("payoff-varied-t100", 100, mode, 0) for mode in PAYOFFS)
for _case in MATRIX:
    _schedule.extend((_case, 10, mode, 0) for mode in PAYOFFS)
for _iterations in (100, 1000):
    _schedule.extend(("original-22-t10", _iterations, mode, 0) for mode in PAYOFFS)
SCHEDULE = tuple(_schedule)
del _schedule, _case, _iterations
if len(SCHEDULE) != 34 or len(set(SCHEDULE)) != 34:
    raise RuntimeError("The fixed fold-class schedule must contain exactly 34 unique children")

REQUIRED_COMPLETE = frozenset([(case, 10) for case in BASELINES] + [("payoff-varied-t100", 100)])
_AUTH = None
_AUTH_PROOF = None


def _need(value, message):
    if not value:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _decode(raw):
    return active._decode(raw)


def _write(path, value):
    Path(path).write_bytes(json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n")


def _identity():
    return active._identity()


def _authenticate_source():
    global _AUTH, _AUTH_PROOF
    source = active._authenticate_source()
    _AUTH, _AUTH_PROOF = source, active._AUTH_PROOF
    return source


def _dependencies():
    _need(_AUTH is not None, "authenticate committed source before importing project code")
    return active._dependencies()


def _label(entry):
    case, iterations, mode, sample = entry
    return f"{case}-t{iterations}-{mode}-p{sample}"


def _case(name, deps):
    return active.case_for(name, deps)


def child(case_name, iterations, native_payoffs, sample, executable):
    """One isolated solve; source/build admission precedes project imports."""
    _authenticate_source()
    deps = _dependencies()
    _need((case_name, iterations, native_payoffs, sample) in SCHEDULE,
          "child is not an entry in the fixed payoff schedule")
    case = _case(case_name, deps)
    build = deps.native.executable_identity(executable)
    original = deps.solver.solve_four_street_exact_selected

    def inject(request, **kwargs):
        kwargs["native_admission"] = "indexed-v1"
        kwargs["native_traversal"] = "active-frames"
        kwargs["native_payoffs"] = native_payoffs
        return original(request, **kwargs)

    projected_schedule = tuple((name, count, "active-frames", index)
        for name, count, _mode, index in SCHEDULE)
    with patch.object(deps.solver, "solve_four_street_exact_selected", new=inject), \
         patch.object(active, "SCHEDULE", projected_schedule), \
         patch.object(active, "case_for", new=lambda _name, _deps: case):
        raw = active.child(case_name, iterations, "active-frames", sample, executable)
    raw["native_payoffs"] = native_payoffs
    outcome = active._resource_outcome(raw)
    raw["status"] = "complete" if raw.get("failure") is None else (outcome or "failed")
    # active.child already checks source/build after the complete call. Repeat
    # the executable pin here so this new selector is part of the receipt.
    try:
        _need(deps.native.executable_identity(executable) == build,
              "native build changed during fold-class child")
    except Exception as exc:
        raw["source_build_guard_failure"] = [{"build": type(exc).__name__ + ": " + str(exc)}]
        raw["status"] = "failed"
        if raw.get("failure") is None:
            raw["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    return raw


def _record(line, tag, mode, fields, *, ordered=False):
    cells = line.split("\t")
    _need(len(cells) == len(fields) + 2 and cells[:2] == [tag, mode],
          tag + " record tag/mode/width mismatch")
    result = {}
    for expected, cell in zip(fields, cells[2:]):
        key, sep, value = cell.partition("=")
        _need(sep and key == expected and key not in result and value.isascii() and value.isdecimal() and
              len(value) <= 20, tag + " record key/order/value mismatch")
        number = int(value)
        _need(number <= (1 << 64) - 1, tag + " integer exceeds uint64")
        result[key] = number
    _need(tuple(result) == tuple(fields) if ordered else set(result) == set(fields), tag + " record incomplete")
    return result


def _wire_fold_expectation(request, *, iterations, census):
    """Independent bounded fold-prefix/mask census from captured protocol bytes."""
    lines = request.decode("ascii").splitlines()
    _need(len(lines) >= 4 and lines[0] in ("OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4",
        "OPENPOKER_NATIVE_EXACT_FOUR_STREET_FOLD_CLASSES_V5"), "fold census request protocol mismatch")
    head = tuple(map(int, lines[1].split()))
    _, _, h0, h1, board_count, vertex_count, edge_count, root_id, initial_count = head
    _need(1 <= h0 <= 1326 and 1 <= h1 <= 1326 and 1 <= board_count <= 64 and
          1 <= vertex_count <= 250_000 and edge_count <= 250_000 and initial_count <= 64,
          "fold census exceeds existing bounded request shape")
    pos = 3 + h0 + h1
    boards = census["boards"]
    classes = _classes_from_census(census)
    _need(len(boards) == board_count, "fold census board count differs from saved request census")
    pos += board_count
    initial = tuple(lines[pos:pos + initial_count]); pos += initial_count
    vertices = []
    observed_edges = 0
    for _ in range(vertex_count):
        cells = lines[pos].split(); pos += 1
        if cells[0] == "D":
            width = int(cells[2]); edges = []
            for _ in range(width):
                row = lines[pos].split(); pos += 1
                _need(len(row) == 6, "fold census malformed action wire")
                edges.append((row[4], int(row[5])))
            vertices.append(("D", tuple(edges))); observed_edges += width
        elif cells[0] == "C":
            street, _, width = map(int, cells[1:])
            prefix = {1: "flop", 2: "turn", 3: "river"}[street]
            edges = []
            for _ in range(width):
                row = lines[pos].split(); pos += 1
                _need(len(row) == 2, "fold census malformed chance wire")
                edges.append((prefix + "@" + row[0], int(row[1])))
            vertices.append(("C", tuple(edges))); observed_edges += width
        elif cells[0] == "F":
            vertices.append(("F", ()))
        elif cells[0] == "S":
            vertices.append(("S", ()))
        else:
            raise ValueError("fold census unknown native vertex kind")
    _need(pos == len(lines) and observed_edges == edge_count,
          "fold census request graph width mismatch")
    visits = folds = terminals = 0
    maximum_depth = 0
    fold_counts = [0, 0]
    stack = [(root_id, initial, 0)]
    while stack:
        vertex_id, history, depth = stack.pop()
        visits += 1
        maximum_depth = max(maximum_depth, depth)
        _need(visits <= 250_000 and depth <= 64, "fold census logical route exceeds existing graph caps")
        kind, edges = vertices[vertex_id]
        if kind == "F":
            folds += 1; terminals += 1
            visible = []
            for token in history:
                if token.startswith("flop@"):
                    label = token[5:]
                    visible.extend(tuple(label[i:i + 2] for i in (0, 2, 4)))
                elif token.startswith("turn@"):
                    visible.append(token[5:])
                elif token.startswith("river@"):
                    visible.append(token[6:])
            def card_index(card):
                ranks, suits = "23456789TJQKA", "cdhs"
                _need(len(card) == 2 and card[0] in ranks and card[1] in suits,
                      "fold census malformed reveal token")
                return ranks.index(card[0]) * 4 + suits.index(card[1])
            prefix = tuple(card_index(card) for card in visible)
            board_matches = sum(board[:len(prefix)] == prefix for board in boards)
            h = h0 + h1
            for player in (0, 1):
                own, opp = (h0, h1) if player == 0 else (h1, h0)
                class_work = classes[1 - player] * (64 * own + 256) + 64 * opp + 8 * board_matches + 128
                literal_work = board_matches * (48 * h + 512)
                fold_counts[player] += int(class_work <= literal_work)
        elif kind == "S":
            terminals += 1
        for token, child_id in reversed(edges):
            stack.append((child_id, history + (token,), depth + 1))
    _need(pos == len(lines) and visits == census.get("visits") and
          terminals == census.get("terminals") and maximum_depth == census.get("depth"),
          "fold census occurrence/depth count differs from bounded wire census")
    h = h0 + h1
    return {
        "setup_work_upper": 2048 * h + 8 * board_count * h + 65536,
        "setup_entries_upper": 10 * h + 128,
        "mask_entries": h,
        "membership_entries": h,
        "classes_sb": classes[0], "classes_bb": classes[1],
        "class_calls_sb": iterations * fold_counts[0],
        "class_calls_bb": iterations * fold_counts[1],
        "literal_calls_sb": iterations * (folds - fold_counts[0]),
        "literal_calls_bb": iterations * (folds - fold_counts[1]),
        "fold_occurrences": folds,
    }


def _classes_from_census(census):
    hands_by_seat, boards = census["hands_by_seat"], census["boards"]
    result = []
    for hands in hands_by_seat:
        masks = set()
        for holding in hands:
            blocked = set(holding)
            mask = 0
            for index, board in enumerate(boards):
                if not blocked.intersection(board):
                    mask |= 1 << index
            masks.add(mask)
        result.append(len(masks))
    return tuple(result)


def _validate_child(raw, entry, deps, cases):
    case_name, iterations, payoff, sample = entry
    _need(type(raw) is dict and not raw.get("source_build_guard_failure"),
          "child source/build guard failed after raw capture")
    _need((raw.get("case"), raw.get("iterations"), raw.get("native_traversal"), raw.get("routing"),
        raw.get("sample"), raw.get("traced"), raw.get("request_case"), raw.get("native_admission"),
        raw.get("native_payoffs")) ==
        (case_name, iterations, "active-frames", "indexed", sample, False, cases[case_name],
         "indexed-v1", payoff) and raw.get("runtime") == deps.quotient._runtime(),
        "child selector/runtime/fixture identity mismatch")
    _need(type(raw.get("seconds")) in (int, float) and math.isfinite(raw["seconds"]) and raw["seconds"] > 0 and
          type(raw.get("process_peak_bytes")) is int and raw["process_peak_bytes"] > 0 and
          raw.get("python_allocation_peak_bytes") is None,
          "invalid complete-call time/process memory scope")
    calls = raw.get("counts")
    keys = {"python_trainer", "native_invoke", "python_rank", "rank_before_native", "pair", "world", "legacy"}
    _need(type(calls) is dict and set(calls) == keys and
        all(type(calls[key]) is int and calls[key] >= 0 for key in keys - {"rank_before_native"}) and
        (calls["rank_before_native"] is None or
         type(calls["rank_before_native"]) is int and calls["rank_before_native"] == 0) and
        not any(calls[key] for key in ("python_trainer", "pair", "world", "legacy")),
        "forbidden training path or malformed call counters")
    outcome = active._resource_outcome(raw)
    if outcome is not None:
        _need(raw.get("status") == outcome and (case_name, iterations) not in REQUIRED_COMPLETE and
              raw.get("payload") is None, "resource rejection has contradictory payload/status or is required complete")
        expected = ({"learning_completed": False, "rank_calls": 0} if outcome == "host-admission-rejected"
                    else {"learning_completed": None, "rank_calls": None})
        _need(raw.get("native_observations") == expected and calls["native_invoke"] in (0, 1) and
              calls["python_rank"] == 0, "resource rejection overstated execution")
        return {"status": outcome, "payload": None}
    _need(raw.get("status") == "complete" and raw.get("failure") is None and
          type(raw.get("payload")) is dict and calls["native_invoke"] == 1 and
          type(calls["rank_before_native"]) is int and calls["rank_before_native"] == 0 and
          calls["python_rank"] > 0 and
          type(raw.get("native_observations")) is dict and
          set(raw["native_observations"]) == {"learning_completed", "rank_calls"} and
          raw["native_observations"].get("learning_completed") is True,
          "native complete call or rank ordering mismatch")

    payload = raw["payload"]
    encoded = _canonical(payload)
    _need(_sha(encoded) == raw.get("payload_sha256") and len(encoded) == raw.get("payload_bytes"),
          "canonical full payload hash/length mismatch")
    expected_backend = ("native-exact-four-street-fold-classes-v5" if payoff == PAYOFFS[1]
                        else "native-exact-four-street-active-frames-v4")
    _need(payload.get("training_backend") == expected_backend and
          payload.get("native_admission") == "indexed-v1" and payload.get("native_routing") == "indexed" and
          payload.get("native_traversal") == "active-frames" and
          (payload.get("native_payoffs") == payoff if payoff == PAYOFFS[1]
           else "native_payoffs" not in payload), "native backend/payoff marker mismatch")
    _need(payload.get("chance_contract") == "exact-product-selected-v1" and
          payload.get("conversion_contract") == "exact-product-vectors-binary64-v1" and
          payload.get("training_reduction") == "suit-equivariant-sorted-chance-binary64-v1" and
          payload.get("strategy_storage") == "suit-quotient-packed-v1" and
          payload.get("quotient_lookup") == "per-decision-suit-history-transform-v1" and
          payload.get("pair_diagnostics") == "compact-exact-product-inputs-v1" and
          "private_pair_probabilities" not in payload,
          "native chance/reduction/storage/diagnostic contract mismatch")
    metrics = deps.equivariant.METRICS
    _need(len(metrics) == 8 and all(type(payload.get(key)) in (int, float) and type(payload[key]) is not bool and
          math.isfinite(payload[key]) for key in metrics), "one or more of the eight metrics is missing/nonfinite")
    census = payload.get("operator_census")
    _need(type(census) is dict and census.get("stored_complete_worlds") == 0 and
          census.get("stored_prefix_pair_edges") == 0 and type(census.get("native_exact")) is dict and
          type(census.get("direct_topology")) is dict and type(census.get("kernel")) is dict,
          "native/direct topology receipt missing or forbidden world/pair table retained")
    exact, direct = census["native_exact"], census["direct_topology"]
    _need(raw.get("native_observations", {}).get("rank_calls") == exact.get("rank_calls") and
          exact.get("calls") == 1 and exact.get("rank_calls", 0) > 0 and
          exact.get("member_checks") == exact.get("expected_member_checks") ==
              2 * iterations * payload.get("info_sets", -1) and
          exact.get("maximum_numeric_workspace_slots") == 4 * exact.get("quotient_action_slots", -1) and
          exact.get("final_numeric_workspace_slots") == 0 and
          0 < exact.get("modeled_work_upper", 500_000_001) <= 500_000_000 and
          0 < exact.get("retained_entries_upper", 2_000_001) <= 2_000_000,
          "native counters or old work/storage ceilings mismatch")
    hands = census["kernel"].get("hands")
    _need(type(hands) in (tuple, list) and len(hands) == 2 and
          all(type(value) is int and 1 <= value <= 1326 for value in hands),
          "kernel seat hand counts malformed")
    route, admission, frame = (exact.get("indexed_routing"), exact.get("indexed_admission"), exact.get("active_frames"))
    _need(type(route) is dict and type(admission) is dict and type(frame) is dict,
          "active indexed route/admission/frame receipts absent")
    streams = raw.get("native_streams")
    _need(type(streams) is list and len(streams) == 1 and calls["native_invoke"] == 1 and
          set(streams[0]) == {"request", "stdout", "stderr", "returncode"} and streams[0]["returncode"] == 0,
          "native raw stream count/status mismatch")
    stream = streams[0]
    request, output, error = (base64.b64decode(stream[key], validate=True)
                              for key in ("request", "stdout", "stderr"))
    fold_mode = payoff == PAYOFFS[1]
    request_header = ("OPENPOKER_NATIVE_EXACT_FOUR_STREET_FOLD_CLASSES_V5" if fold_mode
                      else "OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4")
    result_header = ("OPENPOKER_NATIVE_EXACT_FOUR_STREET_FOLD_CLASSES_RESULT_V5" if fold_mode
                     else "OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_RESULT_V4")
    _need(not error and request.splitlines()[0] == request_header.encode() and
          output.splitlines()[0] == result_header.encode() and
          len(request) == exact["request_bytes"] and len(output) == exact["result_bytes"] and
          _sha(request) == exact["request_sha256"] and _sha(output) == exact["result_sha256"],
          "captured V4/V5 native protocol bytes differ from payload receipt")

    wire = active._wire_census(request, expected_header=request_header,
        expected_iterations=iterations, expected_hands=tuple(hands), direct=direct)
    _need(wire["group_size"] == exact.get("group_size") and
          wire["admission_amounts"]["trainer_history_retained"] == route.get("old_history_forecast") and
          exact["modeled_work_upper"] <= wire["native_work_limit"] and
          exact["retained_entries_upper"] <= wire["native_entries_limit"],
          "independent raw-wire group/admission mismatch")
    expected_ranges, expected_maps = [], []
    from pokerlab.cards import DECK
    for expression in (cases[case_name]["sb_range"], cases[case_name]["bb_range"]):
        expanded = deps.expand_range(expression)
        expected_ranges.append([{"hand": "".join(hand), "weight_hex": float(weight).hex()}
            for hand, weight in expanded.items()])
        expected_maps.append({tuple(sorted((DECK.index(hand[0]), DECK.index(hand[1])))): float(weight).hex()
            for hand, weight in expanded.items()})
    _need(payload.get("chance_input_snapshot") == {"contract": "exact-product-selected-v1", "ranges": expected_ranges} and
          wire["hands_by_seat"] == expected_maps,
          "weighted range snapshot/raw wire differs from fixed request")
    expected_boards = set()
    for runout in cases[case_name]["runouts"]:
        cards = tuple(runout[i:i+2] for i in range(0, 10, 2))
        expected_boards.add(tuple(sorted(DECK.index(card) for card in cards[:3])) +
                             tuple(DECK.index(card) for card in cards[3:]))
    _need(set(wire["boards"]) == expected_boards, "raw selected board order differs from fixed fixture")
    active._validate_indexed_ledger(exact=exact, route=route, admission=admission,
        direct=direct, iterations=iterations, traversal="active-frames", forecast=wire["admission_amounts"])

    lines = output.decode("ascii").splitlines()
    done_positions = [i for i, line in enumerate(lines) if line.startswith("DONE\t")]
    route_positions = [i for i, line in enumerate(lines) if line.startswith("ROUTE\t")]
    admission_positions = [i for i, line in enumerate(lines) if line.startswith("ADMISSION\t")]
    frame_positions = [i for i, line in enumerate(lines) if line.startswith("FRAME\t")]
    fold_positions = [i for i, line in enumerate(lines) if line.startswith("FOLD\t")]
    _need((len(done_positions), len(route_positions), len(admission_positions), len(frame_positions),
           len(fold_positions)) == (1, 1, 1, 1, int(fold_mode)),
          "V4/V5 proof record multiplicity mismatch")
    di, ri, ai, fi = done_positions[0], route_positions[0], admission_positions[0], frame_positions[0]
    _need(di < ri < ai < fi and (not fold_mode or fi < fold_positions[0]),
          "V4/V5 proof records are out of order")
    done_cells = lines[di].split("\t")
    _need(len(done_cells) == len(deps.native.COUNTERS) + 1 and done_cells[0] == "DONE" and
          all(cell.isascii() and cell.isdecimal() and len(cell) <= 20 for cell in done_cells[1:]),
          "DONE record schema mismatch")
    done = dict(zip(deps.native.COUNTERS, map(int, done_cells[1:])))
    _need(all(exact.get(key) == value for key, value in done.items()), "raw DONE counters differ from payload")
    route_line = active._parse_record(lines[ri], "ROUTE", "indexed", deps.native.ROUTE_FIELDS)
    admission_line = active._parse_record(lines[ai], "ADMISSION", "indexed-v1", deps.native.ADMISSION_FIELDS)
    _need({key: value for key, value in route.items() if key != "mode"} == route_line and
          {key: value for key, value in admission.items() if key != "mode"} == admission_line,
          "raw ROUTE/ADMISSION differs from payload")
    frame_line = active._parse_frame_line(lines[fi])
    _need({key: value for key, value in frame.items() if key != "mode"} == frame_line,
          "raw FRAME differs from payload")
    active._validate_frame(frame_line, iterations=iterations, direct=direct,
        kernel_hands=max(hands), route=route_line, admission=admission_line, done=done)

    if fold_mode:
        fold_line = _record(lines[fold_positions[0]], "FOLD", "mask-classes-v1", FOLD_FIELDS, ordered=True)
        mask_census = {**wire, "class_counts": _classes_from_census(wire)}
        expected_fold = _wire_fold_expectation(request, iterations=iterations, census=mask_census)
        for name, value in expected_fold.items():
            if name == "fold_occurrences":
                continue
            _need(fold_line[name] == value, "FOLD field differs from independent raw-wire census: " + name)
        _need(fold_line["class_calls_sb"] + fold_line["literal_calls_sb"] == iterations * expected_fold["fold_occurrences"] and
              fold_line["class_calls_bb"] + fold_line["literal_calls_bb"] == iterations * expected_fold["fold_occurrences"],
              "FOLD terminal call totals differ from independent occurrence census")
        _need(fold_line["buckets_sb"] <= fold_line["class_calls_sb"] * fold_line["classes_bb"] and
              fold_line["buckets_bb"] <= fold_line["class_calls_bb"] * fold_line["classes_sb"] and
              fold_line["own_checks"] == fold_line["buckets_sb"] * hands[0] +
                  fold_line["buckets_bb"] * hands[1] and fold_line["retained_pair_entries"] == 0 and
              fold_line["query_allowance_retained"] == 1 and
              fold_line["combined_work"] == done["modeled_work_upper"] == route_line["combined_work"] == admission_line["combined_work"] and
              fold_line["combined_entries"] == done["retained_entries_upper"] ==
                  route_line["combined_entries"] == admission_line["combined_entries"] <= 2_000_000 and
              admission_line["plan_setup_work"] >= fold_line["setup_work_upper"] and
              admission_line["combined_entries"] >= fold_line["setup_entries_upper"],
              "FOLD bucket/constructor/whole-request proof mismatch")
        _need(exact.get("fold_classes") == {"mode": "mask-classes-v1", **fold_line},
              "raw FOLD record differs from normalized payload proof")
    else:
        _need("fold_classes" not in exact and fold_line_missing_marker(payload),
              "V4 board-sweep result carries fold-class proof/selector markers")
    return {"status": "complete", "payload": payload, "wire_census": wire}


def fold_line_missing_marker(payload):
    return "native_payoffs" not in payload


def _verify(case, payload, deps):
    return deps.capacity._verify(case, payload, deps)


def _validate_numeric_replay(verification, deps):
    numeric = verification.get("numeric")
    _need(type(numeric) is dict and numeric.get("status") in ("complete", "resource-unverified"),
          "independent numeric replay status malformed")
    if numeric["status"] == "complete":
        gaps = verification.get("numeric_metric_gaps")
        _need(type(gaps) is dict and set(gaps) == set(deps.equivariant.METRICS) and
              all(type(value) in (int, float) and not isinstance(value, bool) and
                  math.isfinite(value) and 0 <= value <= deps.equivariant.REPLAY_TOLERANCE
                  for value in gaps.values()),
              "independent physical numeric replay exceeded its recorded tolerance")
    else:
        _need(verification.get("quality_gate") is None,
              "unverified numeric replay cannot report a quality pass")


def _pair_identity(left, right, left_verification, right_verification, deps):
    a, b = left["payload"], right["payload"]
    _need(a.get("chance_input_snapshot") == b.get("chance_input_snapshot"),
          "paired chance-input snapshots differ")
    _need(_canonical(a.get("strategy")) == _canonical(b.get("strategy")),
          "paired complete policy/action/history/probability rows differ")
    metrics = deps.equivariant.METRICS
    _need(all(float(a[key]).hex() == float(b[key]).hex() for key in metrics),
          "paired binary64 metric values differ")
    result = {"complete_policy_rows": len(a["strategy"]),
        "complete_policy_and_action_rows_bitwise_identical": True,
        "all_eight_metric_binary64_identical": True,
        "board_sweep_seconds": left["seconds"], "fold_mask_classes_seconds": right["seconds"],
        "scope": "One paired fixture and iteration count; full native API call plus serialization/hash."}
    exact_a, exact_b = left_verification.get("exact", {}), right_verification.get("exact", {})
    numeric_a, numeric_b = left_verification.get("numeric", {}), right_verification.get("numeric", {})
    _need(numeric_a.get("status") == numeric_b.get("status") and
          exact_a.get("status") == exact_b.get("status") and
          left_verification.get("quality_gate") == right_verification.get("quality_gate"),
          "paired independent numeric/exact verification statuses differ")
    gaps_a, gaps_b = left_verification.get("numeric_metric_gaps"), right_verification.get("numeric_metric_gaps")
    if numeric_a.get("status") == "complete":
        _need(type(gaps_a) is dict and type(gaps_b) is dict and gaps_a == gaps_b,
              "paired independent numeric replay gaps differ")
        result["independent_numeric_replay_gaps_identical"] = True
    else:
        result["independent_numeric_replay_gaps_identical"] = None
    cert_a = exact_a.get("result", {}).get("exact_certificate") if exact_a.get("status") == "complete" else None
    cert_b = exact_b.get("result", {}).get("exact_certificate") if exact_b.get("status") == "complete" else None
    if type(cert_a) is dict and type(cert_b) is dict:
        _need(cert_a.get("metrics") == cert_b.get("metrics") and
              cert_a.get("threshold") == cert_b.get("threshold") and
              cert_a.get("threshold_met") == cert_b.get("threshold_met") and
              cert_a.get("normalized_policy_sha256") == cert_b.get("normalized_policy_sha256") and
              _canonical(cert_a.get("normalized_policy_rows")) == _canonical(cert_b.get("normalized_policy_rows")),
              "paired normalized-policy certificate/metrics/threshold identity differs")
        result["exact_certificate_metrics_and_flags_identical"] = True
        result["threshold_met"] = cert_a.get("threshold_met")
    else:
        result["exact_certificate_metrics_and_flags_identical"] = None
        result["exact_certificate_statuses"] = (exact_a.get("status"), exact_b.get("status"))
    return result


def _pair_key(entry):
    return entry[0], entry[1], entry[3]


def _run_child(command):
    return subprocess.run(command, cwd=ROOT, capture_output=True, check=False)


def _check_captured(output, captured):
    _need(all((output / name).is_file() and _sha((output / name).read_bytes()) == digest
              for name, digest in captured.items()), "captured raw evidence changed")


def run(output, executable):
    output = Path(output).resolve()
    _need(output != ROOT and ROOT not in output.parents and not output.exists(),
          "use a new external fold-class study directory")
    output.mkdir(parents=True)
    source = build = deps = cases = None
    captured, samples, payloads, verifications, pairs = {}, [], {}, {}, {}
    first_failure = None
    attempts = 0

    def capture(name, raw):
        _need(name not in captured and not (output / name).exists(), "duplicate captured artifact")
        (output / name).write_bytes(raw)
        captured[name] = _sha(raw)

    def capture_json(name, value):
        capture(name, json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n")

    try:
        source = _authenticate_source()
        _write(output / "source-before.json", source)
        proof = (_AUTH_PROOF if type(_AUTH_PROOF) is dict and _AUTH_PROOF.get("commit") == source["commit"]
                 else {"commit": source["commit"], "capture_status": "auth-proof-unavailable"})
        _write(output / "source-auth-proof.json", proof)
        deps = _dependencies()
        cases = active.validate_cases(deps)
        build = deps.native.executable_identity(executable)
        _write(output / "build-before.json", build)
        _write(output / "protocol.json", {"version": "native-fold-mask-classes-fixed-study-v1",
            "source_commit": source["commit"], "source_sha256": source["sha256"],
            "source_auth_proof_sha256": _sha(_canonical(proof)), "build": build,
            "runtime": deps.quotient._runtime(), "schedule": SCHEDULE,
            "required_complete": sorted([list(x) for x in REQUIRED_COMPLETE]),
            "payoff_modes": PAYOFFS, "selectors": OPTIONS,
            "scope": "V4 board-sweep versus V5 fold-mask classes under the same native active-frame indexed trainer. No native heap measurement or general speed/memory/convergence claim."})

        for entry in SCHEDULE:
            case_name, iterations, payoff, sample = entry
            identifier = _label(entry)
            try:
                _need(_identity() == source and deps.native.executable_identity(executable) == build,
                      "source/build changed before scheduled child")
                _check_captured(output, captured)
                attempts += 1
                command = [sys.executable, "-B", "-m", "scripts.benchmark_native_fold_classes",
                    "--child", case_name, "--iterations", str(iterations), "--native-payoffs", payoff,
                    "--sample", str(sample), "--native-executable", str(executable)]
                process = _run_child(command)
                capture(identifier + ".stdout.bin", process.stdout)
                capture(identifier + ".stderr.bin", process.stderr)
                capture_json(identifier + "-process-status.json", {"returncode": process.returncode,
                    "stdout_sha256": _sha(process.stdout), "stderr_sha256": _sha(process.stderr)})
                _need(process.returncode == 0, "fold-class child process failed: " + str(process.returncode))
                raw = _decode(process.stdout)
                capture(identifier + ".raw.json", process.stdout)
                for index, stream in enumerate(raw.get("native_streams", ())):
                    for key in ("request", "stdout", "stderr"):
                        capture(f"{identifier}-native-{index}-{key}.bin", base64.b64decode(stream[key], validate=True))
                    capture_json(f"{identifier}-native-{index}-status.json", {
                        "returncode": stream.get("returncode"),
                        "request_sha256": _sha(base64.b64decode(stream["request"], validate=True)),
                        "stdout_sha256": _sha(base64.b64decode(stream["stdout"], validate=True)),
                        "stderr_sha256": _sha(base64.b64decode(stream["stderr"], validate=True))})
                outcome = _validate_child(raw, entry, deps, cases)
                sample_summary = {key: value for key, value in raw.items() if key not in ("payload", "native_streams")}
                sample_summary["artifact"] = identifier + ".raw.json"
                samples.append(sample_summary)
                if outcome["payload"] is not None:
                    payloads[identifier] = raw
                    _need(_identity() == source and deps.native.executable_identity(executable) == build,
                          "source/build changed before independent policy replay")
                    payload_before = _sha(_canonical(raw["payload"]))
                    _check_captured(output, captured)
                    try:
                        verification = _verify(cases[case_name], raw["payload"], deps)
                    finally:
                        _need(_sha(_canonical(raw["payload"])) == payload_before,
                              "saved policy changed during independent replay")
                        _check_captured(output, captured)
                        _need(_identity() == source and deps.native.executable_identity(executable) == build,
                              "source/build changed during independent replay")
                    verifications[identifier] = verification
                    capture_json(identifier + "-verification.json", verification)
                    _validate_numeric_replay(verification, deps)
                print(identifier, outcome["status"], flush=True)
            except Exception as exc:
                first_failure = {"stage": "child", "sample": identifier,
                    "type": type(exc).__name__, "message": str(exc)}
                _write(output / (identifier + "-first-failure.json"), first_failure)
                break

        if first_failure is None:
            for case_name, iterations in REQUIRED_COMPLETE:
                rows = [row for row in SCHEDULE if row[0] == case_name and row[1] == iterations]
                _need(len(rows) >= 2 and all(_label(row) in payloads for row in rows),
                      "required complete payoff pair is missing: " + case_name)
            grouped = {}
            for row in SCHEDULE:
                grouped.setdefault(_pair_key(row), {})[row[2]] = row
            for key, modes in grouped.items():
                if set(modes) != set(PAYOFFS):
                    continue
                left_id, right_id = _label(modes["board-sweep"]), _label(modes["fold-mask-classes-v1"])
                if left_id not in payloads or right_id not in payloads:
                    continue
                result = _pair_identity(payloads[left_id], payloads[right_id],
                    verifications[left_id], verifications[right_id], deps)
                pairs[left_id + "__vs__" + right_id] = result
                capture_json(left_id + "__vs__" + right_id + "-comparison.json", result)
    except Exception as exc:
        if first_failure is None:
            first_failure = {"stage": "study", "type": type(exc).__name__, "message": str(exc)}
            _write(output / "first-failure.json", first_failure)
    finally:
        try:
            _check_captured(output, captured)
        except Exception as exc:
            drift = {"stage": "capture-after", "type": type(exc).__name__, "message": str(exc)}
            _write(output / "capture-drift.json", drift)
            if first_failure is None:
                first_failure = drift
        _write(output / "capture-time-sha256.json", captured)
        try:
            after = _identity()
            _write(output / "source-after.json", after)
            if source is not None and after != source:
                drift = {"stage": "source-after", "type": "ValueError", "message": "source drift after fold-class study"}
                _write(output / "source-drift.json", drift)
                if first_failure is None:
                    first_failure = drift
        except Exception as exc:
            _write(output / "source-after-error.json", {"type": type(exc).__name__, "message": str(exc)})
            if first_failure is None:
                first_failure = {"stage": "source-after", "type": type(exc).__name__, "message": str(exc)}
        if deps is not None and build is not None:
            try:
                after_build = deps.native.executable_identity(executable)
                _write(output / "build-after.json", after_build)
                if after_build != build:
                    drift = {"stage": "build-after", "type": "ValueError", "message": "native build drift after fold-class study"}
                    _write(output / "build-drift.json", drift)
                    if first_failure is None:
                        first_failure = drift
            except Exception as exc:
                _write(output / "build-after-error.json", {"type": type(exc).__name__, "message": str(exc)})
                if first_failure is None:
                    first_failure = {"stage": "build-after", "type": type(exc).__name__, "message": str(exc)}
    quality_misses = []
    for identifier, verification in verifications.items():
        exact = verification.get("exact", {})
        cert = exact.get("result", {}).get("exact_certificate") if exact.get("status") == "complete" else None
        if verification.get("quality_gate") is None or type(cert) is not dict or cert.get("threshold_met") is not True:
            quality_misses.append(identifier)
    medians = {}
    for payoff in PAYOFFS:
        rows = [row for row in samples if row.get("case") == "original-22-t10" and
            row.get("iterations") == 10 and row.get("native_payoffs") == payoff and
            row.get("sample") in (0, 1, 2) and row.get("status") == "complete"]
        if {row["sample"] for row in rows} == {0, 1, 2}:
            medians[payoff] = statistics.median(row["seconds"] for row in rows)
    if set(medians) == set(PAYOFFS):
        medians["scope"] = "Three original-22 T10 pairs only; descriptive timing for this fixed fixture."
    report = {"source_commit": source.get("commit") if source else None,
        "calls_planned": len(SCHEDULE), "calls_attempted": attempts, "calls_captured": len(samples),
        "samples": samples, "paired_comparisons": pairs,
        "original_t10_three_pair_medians_seconds": medians,
        "quality_misses_or_unverified_retained": quality_misses, "failure": first_failure,
        "scope": "Fixed native V4/V5 finite selected-runout comparison. All errors, resource rejections and quality misses are retained. No general speed, native-memory, unrestricted-convergence or full-deck claim."}
    _write(output / "report.json", report)
    _write(output / "manifest.json", {"version": "native-fold-mask-classes-evidence-manifest-v1",
        "files": {str(path.relative_to(output)): _sha(path.read_bytes())
            for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"}})
    return {"outcome": "complete" if first_failure is None and len(samples) == len(SCHEDULE) else "failed",
        "calls_captured": len(samples), "failure": first_failure}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--native-executable", type=Path, required=True)
    parser.add_argument("--child", choices=sorted({row[0] for row in SCHEDULE}))
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--native-payoffs", choices=PAYOFFS)
    parser.add_argument("--sample", type=int, default=0)
    args = parser.parse_args()
    if args.child:
        _need(args.iterations is not None and args.native_payoffs is not None,
              "child requires fixed iterations and payoff mode")
        result = child(args.child, args.iterations, args.native_payoffs, args.sample, args.native_executable)
    else:
        if args.output is None:
            parser.error("--output is required")
        result = run(args.output, args.native_executable)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if args.child or result["outcome"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())

