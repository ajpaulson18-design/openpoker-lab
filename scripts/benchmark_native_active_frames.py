"""Fixed 37-child indexed value-cursor versus active-frame study.

This module imports only the standard library until it authenticates a clean,
committed source closure. It is a bounded finite-game study, not a general
performance claim. Every child and native stream is retained before checking;
there are no retries or replacement fixtures.
"""
from argparse import ArgumentParser
from contextlib import ExitStack
import base64
import hashlib
from itertools import permutations
import json
import math
from pathlib import Path
import platform
import re
import statistics
import struct
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASELINES = ("original-22-t10", "payoff-varied-t10", "blocker-18",
             "asymmetric-weighted", "mixed-stabilizer", "physical-g6")
MATRIX = ("original-weighted-2x2", "balanced-4x4-unit", "balanced-8x8-unit",
          "balanced-16x16-unit", "asymmetric-2x16-unit")
TRAVERSALS = ("value-cursor", "active-frames")
FRAME_FIELDS = ("group_size", "frames", "image_slots", "header_entries", "workspace_entries",
    "workspace_setup_work", "view_fields", "lease_fields", "borrowed_entries_upper", "flow_per_visit",
    "flow_work_upper", "validation_work_upper", "activations", "activations_upper", "released_frames",
    "release_calls", "final_active_frames", "final_workspace_entries", "value_cursor_learning_calls",
    "router_owned_workspace", "combined_work", "combined_entries")
OPTIONS = {"rank_cache_boards": 64, "pair_diagnostics": "compact",
    "exact_arithmetic": "dyadic", "training_reduction": "suit-equivariant",
    "strategy_storage": "suit-quotient", "quotient_lookup": "per-decision",
    "native_routing": "indexed", "native_admission": "indexed-v1"}

_schedule = []
for _case in BASELINES:
    _schedule.extend((_case, 10, mode, 0) for mode in TRAVERSALS)
_schedule.extend((("original-22-t10", 10, "active-frames", 1),
                 ("original-22-t10", 10, "value-cursor", 1),
                 ("original-22-t10", 10, "value-cursor", 2),
                 ("original-22-t10", 10, "active-frames", 2)))
for _iterations in (40, 60, 100):
    _schedule.extend(("original-22-t10", _iterations, mode, 0) for mode in TRAVERSALS)
_schedule.extend(("payoff-varied-t100", 100, mode, 0) for mode in TRAVERSALS)
for _case in MATRIX:
    for _iterations in (10, 100, 1000):
        if (_case, _iterations) in ((MATRIX[0], 10), (MATRIX[0], 100)):
            continue
        _schedule.append((_case, _iterations, "active-frames", 0))
SCHEDULE = tuple(_schedule)
del _schedule, _case, _iterations
if len(SCHEDULE) != 37 or len(set(SCHEDULE)) != 37:
    raise RuntimeError("The fixed active-frame schedule must contain exactly 37 unique calls")

REQUIRED_COMPLETE = frozenset(
    [(case, 10) for case in BASELINES] + [("original-22-t10", 10), ("payoff-varied-t100", 100)])
RESOURCE = re.compile(
    r"\b(?:admission|capacity|limit|cap|forecast|budget|ceiling|preflight|envelope)\b[^\n]*\bexceeded\b"
    r"|\bexceeds?\b[^\n]*\b(?:envelope|ceiling|limit|cap|capped|slots|states|depth|decisions|rows|work)\b"
    r"|\b(?:is |are )?capped at\b|\bno retained-entry allowance remains\b"
    r"|\bindexed router whole-work limit is below its bounded schedule scan floor\b"
    r"|\bhistory-index bounded input scan exceeds remaining combined work before token scan\b", re.I)
_AUTH = None
_AUTH_PROOF = None


def _need(value, message):
    if not value:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _write(path, value):
    Path(path).write_bytes(json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n")


def _decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON value")))


def _git(*args, data=None):
    return subprocess.check_output(["git", *args], cwd=ROOT, input=data)


def _identity():
    names = _git("ls-files", "-z").decode("utf-8").split("\0")[:-1]
    return {"commit": _git("rev-parse", "HEAD").decode().strip(),
        "status": _git("status", "--porcelain", "--untracked-files=all").decode().strip(),
        "sha256": {name: _sha((ROOT / name).read_bytes()) for name in names}}


def _authenticate_source():
    """Authenticate raw and Git-normalized tracked blobs before project imports."""
    global _AUTH, _AUTH_PROOF
    source = _identity()
    _need(not source["status"], "Commit and clean the full source closure before this fixed study")
    tree = {}
    for item in _git("ls-tree", "-rz", "--full-tree", source["commit"]).split(b"\0")[:-1]:
        metadata, name = item.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        _need(kind == b"blob" and mode in (b"100644", b"100755"), "nonordinary source-tree entry")
        tree[name.decode("utf-8")] = oid.decode("ascii")
    names = list(source["sha256"])
    _need(set(names) == set(tree), "tracked source keyset differs from committed tree")
    normalized = _git("hash-object", "--stdin-paths", data=("\n".join(names) + "\n").encode()).decode().splitlines()
    _need(len(normalized) == len(names), "incomplete Git normalization closure")
    for name, oid in zip(names, normalized):
        raw = (ROOT / name).read_bytes()
        raw_oid = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        _need(raw_oid == tree[name] or oid == tree[name], "raw/normalized committed blob mismatch: " + name)
    _need(_identity() == source, "source changed during authentication")
    _AUTH_PROOF = {"commit": source["commit"], "tracked_raw_sha256": dict(source["sha256"]),
        "committed_tree_blob_oid": tree, "git_normalized_blob_oid": dict(zip(names, normalized)),
        "closure_count": len(names), "raw_or_normalized_blob_match": True}
    _AUTH = source
    return source


def _dependencies():
    _need(_AUTH is not None, "authenticate source before importing project code")
    from scripts import benchmark_native_indexed_admission as capacity
    from scripts import benchmark_native_indexed_routing as indexed
    from scripts import benchmark_suit_quotient_solver as quotient
    from scripts import benchmark_equivariant_selected_solver as equivariant
    from pokerlab import exact_selected_solver as solver, native_exact_four_street as native
    from pokerlab import suit_quotient_cfr as qtrainer, exact_selected_kernel as kernel
    from pokerlab.cards import expand_range
    return SimpleNamespace(capacity=capacity, indexed=indexed, quotient=quotient,
        equivariant=equivariant, solver=solver, native=native,
        qtrainer=qtrainer, kernel=kernel, expand_range=expand_range)


def case_for(name, deps):
    if name == "physical-g6":
        case = dict(deps.quotient.case_for("original-22-t10"))
        case.update(id="active-frame-physical-s3-v1", sb_range="AdAh,AdAs,AhAs",
            bb_range="KdKh,KdKs,KhKs", runouts=["2c3c4c7c8c"])
        return case
    if name == "payoff-varied-t100":
        name = "payoff-varied-t10"
    return deps.capacity.case_for(name, deps)


def validate_cases(deps):
    cases = {name: case_for(name, deps) for name in (*BASELINES, *MATRIX, "payoff-varied-t100")}
    g6 = cases["physical-g6"]
    _need(g6["sb_range"] == "AdAh,AdAs,AhAs" and g6["bb_range"] == "KdKh,KdKs,KhKs" and
          g6["runouts"] == ["2c3c4c7c8c"], "physical G6 fixture changed")
    for matrix in MATRIX[1:]:
        h0, h1 = (2, 16) if matrix == MATRIX[-1] else (int(matrix.split("-")[1].split("x")[0]),) * 2
        for field, count in (("sb_range", h0), ("bb_range", h1)):
            expanded = deps.expand_range(cases[matrix][field])
            _need(len(expanded) == count and all(float(weight).hex() == (1.0).hex()
                for weight in expanded.values()), "unit range fixture changed after parsing")
    return cases


def label(entry):
    case, iterations, traversal, sample = entry
    return f"{case}-t{iterations}-{traversal}-p{sample}"


def _resource_message(message):
    if type(message) is not str or re.search(
            r"\b(?:stale|unsupported|missing|mismatch|invalid|requires|wrong|unknown)\b|already reserved|cannot exceed",
            message, re.I):
        return False
    return RESOURCE.search(message) is not None


def _resource_outcome(raw):
    # A resource-rejection record must not discard a contradictory result.
    if raw.get("payload") is not None:
        return None
    failure = raw.get("failure")
    counts = raw.get("counts", {})
    streams = raw.get("native_streams")
    if type(failure) is not dict or not _resource_message(failure.get("message")):
        return None
    if (failure.get("type") == "ValueError" and counts.get("native_invoke") == 0 and
            counts.get("python_rank") == 0 and counts.get("python_trainer") == 0 and streams == []):
        return "host-admission-rejected"
    if (failure.get("type") == "NativeFailure" and counts.get("native_invoke") == 1 and
            counts.get("rank_before_native") == 0 and counts.get("python_rank") == 0 and counts.get("python_trainer") == 0 and
            type(streams) is list and len(streams) == 1):
        stream = streams[0]
        try:
            output = base64.b64decode(stream["stdout"], validate=True)
            error = base64.b64decode(stream["stderr"], validate=True).decode("utf-8", "replace")
        except (KeyError, ValueError, TypeError):
            return None
        if stream.get("returncode") == 2 and not output and error.startswith("native exact four-street rejected:") and _resource_message(error):
            return "native-resource-rejected"
    return None


def _forbidden(counter, label, counts):
    def reject(*_args, **_kwargs):
        counts[counter] += 1
        raise AssertionError("forbidden path entered: " + label)
    return reject


def child(case_name, iterations, traversal, sample, executable):
    """One isolated solve using the established native stream/timer instrumentation."""
    _authenticate_source()
    deps = _dependencies()
    _need((case_name, iterations, traversal, sample) in SCHEDULE, "child is not a fixed scheduled request")
    case = case_for(case_name, deps)
    build = deps.native.executable_identity(executable)
    original = deps.solver.solve_four_street_exact_selected

    def select_traversal(request, **kwargs):
        return original(request, native_admission="indexed-v1", native_traversal=traversal, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch.object(deps.indexed, "case_for", new=lambda _name: case))
        stack.enter_context(patch.object(deps.indexed, "ITERATIONS", new={case_name: iterations}))
        stack.enter_context(patch.object(deps.solver, "solve_four_street_exact_selected", new=select_traversal))
        raw = deps.indexed.child(case_name, "indexed", sample, False, executable)
    raw.update(native_admission="indexed-v1", native_traversal=traversal, request_case=case)
    raw["status"] = "complete" if raw.get("failure") is None else (_resource_outcome(raw) or "failed")
    if raw["status"] == "complete":
        exact = raw["payload"]["operator_census"]["native_exact"]
        raw["native_observations"] = {"learning_completed": True, "rank_calls": exact["rank_calls"]}
    elif raw["status"] == "host-admission-rejected":
        raw["native_observations"] = {"learning_completed": False, "rank_calls": 0}
    elif raw["status"] == "native-resource-rejected":
        raw["native_observations"] = {"learning_completed": None, "rank_calls": None}
    guard_failures = []
    try:
        if _identity() != _AUTH:
            guard_failures.append({"source": "source identity changed during complete API call"})
    except Exception as exc:
        guard_failures.append({"source": type(exc).__name__ + ": " + str(exc)})
    try:
        if deps.native.executable_identity(executable) != build:
            guard_failures.append({"build": "native executable/build identity changed during complete API call"})
    except Exception as exc:
        guard_failures.append({"build": type(exc).__name__ + ": " + str(exc)})
    if guard_failures:
        raw["source_build_guard_failure"] = guard_failures
        if raw.get("failure") is None:
            raw["failure"] = {"type": "ValueError", "message": "source/build changed during complete API call"}
        raw["status"] = "failed"
    return raw


def _parse_record(line, tag, mode, fields):
    cells = line.split("\t")
    expected_fields = set(fields)
    _need(len(cells) == len(expected_fields) + 2 and cells[:2] == [tag, mode], "native record tag/mode/width mismatch")
    parsed = {}
    for cell in cells[2:]:
        key, separator, value = cell.partition("=")
        _need(separator and key in expected_fields and key not in parsed and value.isascii() and
              value.isdecimal() and len(value) <= 20, "native record key/value/duplicate mismatch")
        parsed[key] = int(value)
    _need(set(parsed) == expected_fields, "native record is incomplete or unknown")
    return parsed


def _parse_frame_line(line):
    cells = line.split("\t")
    _need(len(cells) == len(FRAME_FIELDS) + 2 and cells[:2] == ["FRAME", "active-v1"],
          "FRAME record missing/wrong mode/width")
    frame = {}
    for expected, cell in zip(FRAME_FIELDS, cells[2:]):
        key, separator, value = cell.partition("=")
        _need(separator and key == expected and value.isascii() and value.isdecimal() and len(value) <= 20,
              "FRAME record key/order/value mismatch")
        frame[key] = int(value)
    _need(tuple(frame) == FRAME_FIELDS, "FRAME record incomplete")
    return frame


def _validate_frame(frame, *, iterations, direct, kernel_hands, route, admission, done):
    _need(tuple(frame) == FRAME_FIELDS, "FRAME fields are not the exact ordered schema")
    _need(all(type(v) is int and v >= 0 for v in frame.values()), "FRAME fields must be nonnegative integers")
    group = done["group_size"]
    depth = direct["maximum_depth"]
    visits = direct["expanded_logical_visits"]
    frames = depth + 1
    image_slots = frames * group
    workspace = 64 + 3 * frames + 8 * image_slots
    borrowed = 4 * (depth + 4) * 6
    flow_per_visit = 64 + 4 * 6 + 8 * group
    activations = 3 * iterations * visits
    flow = workspace + activations * flow_per_visit
    validation = route["decisions"] * 32 * (1 + group + kernel_hands * (1 + group)) + route["prefixes"] * 64
    expected = {"group_size": group, "frames": frames, "image_slots": image_slots,
        "header_entries": 3 * frames, "workspace_entries": workspace, "workspace_setup_work": workspace,
        "view_fields": 3, "lease_fields": 3, "borrowed_entries_upper": borrowed,
        "flow_per_visit": flow_per_visit, "flow_work_upper": flow, "validation_work_upper": validation,
        "activations": activations, "activations_upper": activations, "released_frames": activations,
        "release_calls": activations, "final_active_frames": 0, "final_workspace_entries": 0,
        "value_cursor_learning_calls": 0, "router_owned_workspace": 1,
        "combined_work": route["combined_work"], "combined_entries": route["combined_entries"]}
    _need(frame == expected, "FRAME fields differ from independently recomputed route/occurrence bounds")
    _need(route["roots"] == 3 * iterations and route["edges"] == 3 * iterations * (visits - 1) and
        activations == route["roots"] + route["edges"], "FRAME activation coverage differs from full-call occurrence census")
    _need(route["cursor_fields"] == 3 and route["cursor_frames_upper"] == workspace + borrowed and
        route["caller_work"] >= flow and route["router_work_upper"] >= validation and
        route["caller_entries"] >= workspace + borrowed,
        "active route cursor/caller-flow/router-query-validation admission mismatch")
    _need(route["combined_work"] == admission["combined_work"] == done["modeled_work_upper"] and
        route["combined_entries"] == admission["combined_entries"] == done["retained_entries_upper"],
        "FRAME whole-owner combined budget mismatch")


def _indexed_admission_amounts(*, group, iterations, history_tokens, decision_hands,
                               action_count, history_entries, row_bytes, depth, visits):
    lookup = group * (128 * history_tokens + 256 * decision_hands)
    one_history_pass = group * (16 * history_entries + 4 * row_bytes +
        8 * (depth + 1) * decision_hands + 16 * (depth + 1) * visits)
    return {
        "plan_legacy_lookup_removed": 3 * iterations * lookup,
        "plan_legacy_action_removed": 6 * iterations * 32 * action_count,
        "trainer_legacy_history_removed": 3 * iterations * one_history_pass,
        "trainer_history_retained": 4 * one_history_pass,
    }


def _wire_census(request, *, expected_header, expected_iterations, expected_hands, direct):
    """Independently derive bounded history and admission counts from the saved wire."""
    _need(type(request) is bytes and len(request) <= 16_000_000,
          "independent request wire exceeds the existing byte ceiling")
    try:
        lines = request.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("native request wire is not ASCII") from exc
    _need(len(lines) >= 4 and lines[0] == expected_header, "independent request header mismatch")

    def ints(line, width, label):
        cells = line.split()
        _need(len(cells) == width and all(cell.isascii() and cell.isdecimal() and len(cell) <= 20
              for cell in cells), "malformed bounded " + label)
        return tuple(map(int, cells))

    t, rank_cache, h0, h1, board_count, vertex_count, edge_count, root_id, initial_count = ints(
        lines[1], 9, "request census header")
    _need(t == expected_iterations and rank_cache == 64 and 1 <= h0 <= 1326 and 1 <= h1 <= 1326 and
          1 <= board_count <= 64 and 1 <= vertex_count <= 250_000 and 0 <= edge_count <= 250_000 and
          root_id < vertex_count and initial_count <= 64 and (h0, h1) == tuple(expected_hands),
          "request census exceeds existing bounded shape or differs from original input")
    limits = ints(lines[2], 11, "request admission limits")
    max_bits, kernel_work, kernel_entries, integer_payload, native_work, native_entries = limits[:6]
    _need(max_bits == 65_536 and 0 < kernel_work <= 500_000_000 and
          0 < kernel_entries <= 2_000_000 and integer_payload == 1 << 30 and
          0 < native_work <= 500_000_000 and 0 < native_entries <= 2_000_000 and
          limits[6] == 16_000_000 and limits[7] == native_work and limits[8] == native_entries and
          limits[9:] == (1_000_000, 2_000_000),
          "request wire widened or changed an existing native/kernel cap")

    pos = 3
    hands_by_seat = []
    for count in (h0, h1):
        seat = {}
        for _ in range(count):
            cells = lines[pos].split(); pos += 1
            _need(len(cells) == 3 and all(c.isascii() for c in cells), "malformed weighted hand row")
            a, b = int(cells[0]), int(cells[1])
            _need(0 <= a < 52 and 0 <= b < 52 and a != b and
                  len(cells[2]) == 16 and all(ch in "0123456789abcdefABCDEF" for ch in cells[2]),
                  "invalid canonical wire holding/weight")
            try:
                weight_value = struct.unpack(">d", bytes.fromhex(cells[2]))[0]
                weight = weight_value.hex()
            except (ValueError, OverflowError) as exc:
                raise ValueError("invalid finite binary64 hand weight") from exc
            holding = tuple(sorted((a, b)))
            _need(math.isfinite(weight_value) and weight_value > 0 and holding not in seat,
                  "duplicate or nonpositive wire holding weight")
            seat[holding] = weight
        hands_by_seat.append(seat)

    boards = []
    for _ in range(board_count):
        row = ints(lines[pos], 5, "selected-board row"); pos += 1
        _need(all(0 <= card < 52 for card in row) and len(set(row)) == 5 and
              row[:3] == tuple(sorted(row[:3])) and row not in boards,
              "invalid or duplicate selected board")
        boards.append(row)
    initial = []
    for _ in range(initial_count):
        token = lines[pos]; pos += 1
        _need(0 < len(token.encode("ascii")) <= 64, "initial history token exceeds existing cap")
        initial.append(token)
    _need(sum(len(token.encode("ascii")) for token in initial) <= 16_000_000,
          "initial public-history byte cap exceeded")

    vertices = []
    observed_edges = 0
    for _ in range(vertex_count):
        cells = lines[pos].split(); pos += 1
        _need(cells, "empty vertex row")
        if cells[0] == "D":
            _need(len(cells) == 3 and cells[1] in ("0", "1"), "malformed decision vertex")
            actor, count = int(cells[1]), int(cells[2])
            _need(1 <= count <= 64, "invalid decision width")
            action_tokens = []; children = []; seen = set()
            for _ in range(count):
                action = lines[pos].split(); pos += 1
                _need(len(action) == 6 and action[3] in ("0", "1") and
                      len(action[1]) == len(action[2]) == 16 and
                      all(ch in "0123456789abcdefABCDEF" for ch in action[1] + action[2]),
                      "malformed decision action")
                token, child = action[4], int(action[5])
                _need(0 < len(token.encode("ascii")) <= 64 and token not in seen and
                      0 <= child < vertex_count, "invalid/duplicate decision token or child")
                seen.add(token); action_tokens.append(token); children.append(child)
            vertices.append(("D", actor, tuple(action_tokens), tuple(children)))
            observed_edges += count
        elif cells[0] == "C":
            _need(len(cells) == 4, "malformed chance vertex")
            street, card_index, count = map(int, cells[1:])
            _need(street in (1, 2, 3) and card_index == (4, 5, 6)[street - 1] and
                  1 <= count <= 64, "invalid chance street/card index/branch count")
            branch_tokens = []; children = []; seen = set()
            for _ in range(count):
                branch = lines[pos].split(); pos += 1
                _need(len(branch) == 2, "malformed chance branch")
                label, child = branch[0], int(branch[1])
                prefix = {1: "flop", 2: "turn", 3: "river"}[street]
                token = prefix + "@" + label
                ranks, suits = "23456789TJQKA", "cdhs"
                deck = tuple(rank + suit for rank in ranks for suit in suits)
                if street == 1:
                    cards = tuple(label[index:index + 2] for index in (0, 2, 4)) if len(label) == 6 else ()
                    _need(len(cards) == 3 and all(card in deck for card in cards) and
                          tuple(sorted(cards, key=deck.index)) == cards and len(set(cards)) == 3,
                          "malformed/noncanonical flop branch")
                else:
                    _need(len(label) == 2 and label in deck, "malformed turn/river branch")
                _need(0 < len(token.encode("ascii")) <= 64 and token not in seen and
                      0 <= child < vertex_count, "invalid/duplicate chance token or child")
                seen.add(token); branch_tokens.append(token); children.append(child)
            vertices.append(("C", street, card_index, tuple(branch_tokens), tuple(children)))
            observed_edges += count
        elif cells[0] == "F":
            _need(len(cells) == 4 and cells[1] in ("0", "1") and
                  all(len(value) == 16 and all(ch in "0123456789abcdefABCDEF" for ch in value)
                      for value in cells[2:]), "malformed fold terminal")
            vertices.append(("F",))
        elif cells[0] == "S":
            _need(len(cells) == 3 and
                  all(len(value) == 16 and all(ch in "0123456789abcdefABCDEF" for ch in value)
                      for value in cells[1:]), "malformed showdown terminal")
            vertices.append(("S",))
        else:
            raise ValueError("unknown request vertex kind")
    _need(pos == len(lines) and observed_edges == edge_count, "request vertex/edge count mismatch")

    indegree = [0] * vertex_count
    adjacency = []
    for vertex in vertices:
        children = vertex[-1] if vertex[0] in ("D", "C") else ()
        adjacency.append(children)
        for child in children:
            indegree[child] += 1
    _need([i for i, value in enumerate(indegree) if value == 0] == [root_id],
          "request graph has a foreign root or disconnected component")
    # Kahn traversal verifies every vertex is reachable/acyclic and preserves
    # repeated edges in the route census.
    remaining = indegree[:]; ready = [root_id]; topo = []
    while ready:
        node = ready.pop(); topo.append(node)
        for child in adjacency[node]:
            remaining[child] -= 1
            if remaining[child] == 0:
                ready.append(child)
    _need(len(topo) == vertex_count, "request graph contains a cycle or unreachable vertex")

    # DECK is rank-major with four suits (c,d,h,s). Compute the weighted-role
    # and selected-board stabilizer directly from the authenticated wire.
    def mapped_card(card, image):
        return (card // 4) * 4 + image[card % 4]
    group = []
    for image in permutations(range(4)):
        preserved = True
        for seat in hands_by_seat:
            mapped = {(tuple(sorted((mapped_card(a, image), mapped_card(b, image)))), weight)
                      for (a, b), weight in seat.items()}
            if mapped != set(seat.items()):
                preserved = False; break
        if preserved:
            mapped_boards = set()
            for board in boards:
                mapped = tuple(mapped_card(card, image) for card in board)
                mapped_boards.add(tuple(sorted(mapped[:3])) + mapped[3:])
            if mapped_boards == set(boards):
                group.append(image)
    _need((0, 1, 2, 3) in group, "wire ranges/boards lack the identity suit map")

    # Saturate path multiplicities at the first value beyond the existing work
    # ceiling; never build an exponential-size Python integer.
    cap = 500_000_001
    def add(a, b): return min(cap, a + b)
    def mul(a, b): return 0 if not a or not b else min(cap, a * b)
    occ = [0] * vertex_count; tokens = [0] * vertex_count
    byte_counts = [0] * vertex_count; depths = [-1] * vertex_count
    occ[root_id] = 1; tokens[root_id] = len(initial)
    initial_bytes = sum(len(token.encode("ascii")) for token in initial)
    byte_counts[root_id] = initial_bytes; depths[root_id] = 0
    history_tokens = len(initial)
    history_bytes = initial_bytes
    transition_tokens = transition_bytes = 0
    visits = decisions = terminals = decision_hands = action_count = history_entries = row_bytes = 0
    for node in topo:
        count = occ[node]
        _need(count > 0, "reachable DAG vertex has zero occurrence count")
        vertex = vertices[node]
        visits = add(visits, count)
        history_tokens = add(history_tokens, tokens[node])
        history_bytes = add(history_bytes, byte_counts[node])
        if vertex[0] == "D":
            decisions = add(decisions, count)
            actions = len(vertex[2]); hand_count = h0 if vertex[1] == 0 else h1
            decision_hands = add(decision_hands, mul(count, hand_count))
            action_count = add(action_count, mul(count, actions))
            history_entries = add(history_entries, add(tokens[node], mul(count, actions)))
            row_bytes = add(row_bytes, add(byte_counts[node], mul(64 * actions, count)))
            edges = zip(vertex[2], vertex[3])
        elif vertex[0] == "C":
            edges = zip(vertex[3], vertex[4])
        else:
            terminals = add(terminals, count); edges = ()
        for token, child in edges:
            occ[child] = add(occ[child], count)
            tokens[child] = add(tokens[child], add(tokens[node], count))
            token_size = len(token.encode("ascii"))
            transition_tokens = add(transition_tokens, count)
            transition_bytes = add(transition_bytes, mul(count, token_size))
            byte_counts[child] = add(byte_counts[child], add(byte_counts[node], mul(count, token_size)))
            depths[child] = max(depths[child], depths[node] + 1)
            _need(occ[child] <= 250_000 and tokens[child] <= 16_000_000 and
                  byte_counts[child] <= 16_000_000 and depths[child] <= 64,
                  "independent occurrence route exceeds existing visit/depth/history caps")
        _need(visits <= 250_000 and history_tokens <= 16_000_000 and
              history_bytes <= 16_000_000 and decisions <= 250_000 and terminals <= 250_000,
              "independent aggregate census exceeds existing visit/history caps")
    depth = max(depths)
    _need(visits <= 250_000 and depth <= 64 and history_tokens <= 16_000_000 and
          row_bytes <= 16_000_000 and max(occ, default=0) <= cap,
          "independent occurrence/history census exceeds existing graph caps")
    _need(visits == direct.get("expanded_logical_visits") and
          decisions == direct.get("decision_occurrences") and
          terminals == direct.get("terminal_occurrences") and depth == direct.get("maximum_depth"),
          "raw-wire occurrence census differs from direct topology receipt")
    _need(history_tokens - len(initial) + transition_tokens == direct.get("logical_history_token_work") and
          history_bytes - initial_bytes + transition_bytes == direct.get("logical_history_token_bytes"),
          "raw-wire history-token census differs from direct topology receipt")
    amounts = _indexed_admission_amounts(group=len(group), iterations=expected_iterations,
        history_tokens=history_tokens, decision_hands=decision_hands,
        action_count=action_count, history_entries=history_entries, row_bytes=row_bytes,
        depth=depth, visits=visits)
    return {"group_size": len(group), "hands_by_seat": hands_by_seat, "boards": boards,
        "visits": visits, "decisions": decisions,
        "terminals": terminals, "depth": depth, "history_tokens": history_tokens,
        "decision_hands": decision_hands, "action_count": action_count,
        "history_entries": history_entries, "row_bytes": row_bytes,
        "admission_amounts": amounts, "native_work_limit": native_work,
        "native_entries_limit": native_entries, "kernel_work_limit": kernel_work,
        "kernel_entries_limit": kernel_entries, "integer_payload_bits_limit": integer_payload}


def _validate_indexed_ledger(*, exact, route, admission, direct, iterations, traversal, forecast):
    visits = direct["expanded_logical_visits"]
    decisions = direct["decision_occurrences"]
    terminals = direct["terminal_occurrences"]
    _need(type(decisions) is int and decisions > 0 and type(terminals) is int and terminals > 0,
          "direct decision/terminal occurrence census malformed")
    _need(route.get("mode") == "indexed" and route["roots"] == route["roots_upper"] == 3 * iterations and
        route["edges"] == route["edges_upper"] == 3 * iterations * (visits - 1) and
        route["decisions"] == route["decisions_upper"] == 3 * iterations * decisions and
        route["prefixes"] == route["prefixes_upper"] == iterations * (2 * terminals + decisions),
        "indexed route calls differ from direct topology census")
    _need(route["q_rows"] == route["map_entries"] == route["map_upper"] and
        route["q_routes"] == route["q_routes_upper"] == route["q_rows"] and
        route["q_tokens"] == route["q_tokens_upper"] and route["r_lookup_entries"] == 0 and
        route["old_q_histories_retained"] == 1 and route["final_router_entries"] == 0 and
        route["combined_work"] == exact["modeled_work_upper"] and
        route["combined_entries"] == exact["retained_entries_upper"] and
        all(type(route[name]) is int and 0 <= route[name] <= route[name + "_upper"]
            for name in ("router_work", "index_work", "index_entries", "router_retained")),
        "indexed route map/work/owner receipt mismatch")
    _need(route["decision_comparisons"] == route["prefix_comparisons"] ==
        route["legacy_extensions"] == route["legacy_rows"] == route["legacy_prefixes"] == 0,
        "indexed learning reported a legacy traversal operation")
    expected_cursor_fields = 3 if traversal == "active-frames" else 4 + 24 * 8
    _need(route["cursor_fields"] == expected_cursor_fields,
        "active or V3 indexed cursor schema differs")
    _need(admission["mode"] == "indexed-v1" and
        all(admission.get(name) == value for name, value in forecast.items()) and
        admission["marginal_reuse"] == 1 and 0 < admission["marginal_calls_actual"] <= admission["marginal_calls_upper"] and
        admission["combined_work"] == route["combined_work"] ==
            admission["plan_setup_work"] + admission["index_setup_work"] + admission["router_setup_work"] +
            route["router_work_upper"] + route["index_work_upper"] + route["caller_work"] and
        admission["combined_entries"] == route["combined_entries"] == exact["retained_entries_upper"] and
        route["combined_work"] <= 500_000_000 and route["combined_entries"] <= 2_000_000,
        "whole-request indexed work/storage ledger mismatch")


def validate(raw, entry, deps, cases):
    case_name, iterations, traversal, sample = entry
    _need(type(raw) is dict and not raw.get("source_build_guard_failure"),
          "child source/build guard failed after preserving its raw observation")
    _need(type(raw) is dict and (raw.get("case"), raw.get("iterations"), raw.get("native_traversal"),
        raw.get("routing"), raw.get("sample"), raw.get("traced"), raw.get("request_case")) ==
        (case_name, iterations, traversal, "indexed", sample, False, cases[case_name]) and
        raw.get("native_admission") == "indexed-v1" and
        raw.get("runtime") == deps.quotient._runtime(), "child identity/runtime/fixture mismatch")
    _need(type(raw.get("seconds")) in (int, float) and math.isfinite(raw["seconds"]) and raw["seconds"] > 0 and
        type(raw.get("process_peak_bytes")) is int and raw["process_peak_bytes"] > 0 and
        raw.get("python_allocation_peak_bytes") is None, "invalid complete-call timing/RSS scope")
    calls = raw.get("counts")
    keys = {"python_trainer", "native_invoke", "python_rank", "rank_before_native", "pair", "world", "legacy"}
    _need(type(calls) is dict and set(calls) == keys and
        all(type(calls[k]) is int and calls[k] >= 0 for k in keys - {"rank_before_native"}) and
        (calls["rank_before_native"] is None or type(calls["rank_before_native"]) is int and calls["rank_before_native"] == 0) and
        not any(calls[k] for k in ("python_trainer", "pair", "world", "legacy")),
        "forbidden or malformed call counters")
    streams = raw.get("native_streams")
    _need(type(streams) is list and len(streams) == calls["native_invoke"] <= 1, "native stream/call count mismatch")
    outcome = _resource_outcome(raw)
    must_complete = (case_name, iterations) in REQUIRED_COMPLETE
    if outcome is not None:
        _need(raw.get("status") == outcome and not must_complete, "required complete fixture rejected or resource status forged")
        expected_observations = ({"learning_completed": False, "rank_calls": 0} if outcome == "host-admission-rejected"
            else {"learning_completed": None, "rank_calls": None})
        _need(raw.get("native_observations") == expected_observations, "resource-rejection process scope overstated")
        return {"status": outcome, "payload": None}
    _need(raw.get("status") == "complete" and raw.get("failure") is None and type(raw.get("payload")) is dict and
        calls["native_invoke"] == 1 and calls["rank_before_native"] == 0 and calls["python_rank"] > 0 and
        raw.get("native_observations", {}).get("learning_completed") is True,
        "required native call did not complete in order")
    payload = raw["payload"]
    encoded = _canonical(payload)
    _need(_sha(encoded) == raw.get("payload_sha256") and len(encoded) == raw.get("payload_bytes"),
        "canonical complete payload digest/length mismatch")
    expected_backend = ("native-exact-four-street-active-frames-v4" if traversal == "active-frames"
                        else "native-exact-four-street-indexed-admission-v3")
    _need(payload.get("training_backend") == expected_backend and
        payload.get("native_admission") == "indexed-v1" and payload.get("native_routing") == "indexed" and
        (payload.get("native_traversal") == "active-frames" if traversal == "active-frames"
         else "native_traversal" not in payload), "backend/traversal/admission marker mismatch")
    _need(payload.get("chance_contract") == "exact-product-selected-v1" and
        payload.get("conversion_contract") == "exact-product-vectors-binary64-v1" and
        payload.get("training_reduction") == "suit-equivariant-sorted-chance-binary64-v1" and
        payload.get("pair_diagnostics") == "compact-exact-product-inputs-v1" and
        "private_pair_probabilities" not in payload, "chance/conversion/reduction/diagnostic scope mismatch")
    metrics = deps.equivariant.METRICS
    _need(all(type(payload.get(key)) in (int, float) and type(payload[key]) is not bool and
        math.isfinite(payload[key]) for key in metrics), "one or more of the eight metrics is missing/nonfinite")
    census = payload.get("operator_census")
    _need(type(census) is dict and census.get("stored_complete_worlds") == 0 and
        census.get("stored_prefix_pair_edges") == 0 and type(census.get("native_exact")) is dict and
        type(census.get("direct_topology")) is dict, "native/topology census missing or world/pair state stored")
    exact = census["native_exact"]
    _need(raw.get("native_observations", {}).get("rank_calls") == exact.get("rank_calls"),
          "native rank observation differs from completed receipt")
    _need(exact.get("calls") == 1 and exact.get("member_checks") == exact.get("expected_member_checks") ==
        2 * iterations * payload.get("info_sets", -1) and exact.get("rank_calls", 0) > 0 and
        exact.get("maximum_numeric_workspace_slots") == 4 * exact.get("quotient_action_slots", -1) and
        exact.get("final_numeric_workspace_slots") == 0 and 0 < exact.get("modeled_work_upper", 500_000_001) <= 500_000_000 and
        0 < exact.get("retained_entries_upper", 2_000_001) <= 2_000_000,
        "native training counts or bounded workspace/budget receipt mismatch")
    direct = census["direct_topology"]
    visits, depth = direct.get("expanded_logical_visits"), direct.get("maximum_depth")
    _need(type(visits) is int and visits > 0 and type(depth) is int and depth >= 0,
        "direct topology visit/depth census malformed")
    hands = census["kernel"].get("hands")
    _need(type(hands) in (tuple, list) and len(hands) == 2 and
        all(type(v) is int and v > 0 for v in hands), "kernel hand-count census missing")
    route = exact.get("indexed_routing")
    admission = exact.get("indexed_admission")
    _need(type(route) is dict and type(admission) is dict,
          "complete indexed route/admission receipts missing")
    native_stream = streams[0]
    _need(type(native_stream) is dict and set(native_stream) == {"request", "stdout", "stderr", "returncode"} and
        native_stream.get("returncode") == 0, "malformed raw native stream record")
    request, output, error = (base64.b64decode(native_stream[key], validate=True)
                              for key in ("request", "stdout", "stderr"))
    request_header = (deps.native.ACTIVE_FRAMES_PROTOCOL if traversal == "active-frames"
                      else deps.native.INDEXED_PROTOCOL).encode("ascii")
    result_header = (deps.native.ACTIVE_FRAMES_RESULT if traversal == "active-frames"
                     else deps.native.INDEXED_RESULT).encode("ascii")
    _need(request.splitlines()[0] == request_header and output.splitlines()[0] == result_header and not error and
        len(request) == exact["request_bytes"] and len(output) == exact["result_bytes"] and
        _sha(request) == exact["request_sha256"] and _sha(output) == exact["result_sha256"],
        "raw V3/V4 protocol header or stream receipt mismatch")
    census = _wire_census(request, expected_header=request_header.decode("ascii"),
        expected_iterations=iterations, expected_hands=hands, direct=direct)
    _need(census["group_size"] == exact.get("group_size") and
          census["admission_amounts"]["trainer_history_retained"] == route.get("old_history_forecast") and
          exact["modeled_work_upper"] <= census["native_work_limit"] and
          exact["retained_entries_upper"] <= census["native_entries_limit"],
          "raw-wire symmetry/admission census differs from native receipt")
    from pokerlab.cards import DECK, expand_range
    expected_ranges = []
    expected_maps = []
    for expression in (cases[case_name]["sb_range"], cases[case_name]["bb_range"]):
        expanded = expand_range(expression)
        rows = [{"hand": "".join(hand), "weight_hex": float(weight).hex()}
                for hand, weight in expanded.items()]
        expected_ranges.append(rows)
        expected_maps.append({(a, b): float(weight).hex()
            for hand, weight in expanded.items()
            for a, b in [tuple(sorted((DECK.index(hand[0]), DECK.index(hand[1]))))]})
    _need(payload.get("chance_input_snapshot") == {"contract": "exact-product-selected-v1",
          "ranges": expected_ranges} and census["hands_by_seat"] == expected_maps,
          "raw wire weighted ranges differ from the original fixed fixture")
    expected_boards = set()
    for token in cases[case_name]["runouts"]:
        cards = tuple(token[index:index + 2] for index in range(0, 10, 2))
        expected_boards.add(tuple(sorted((DECK.index(card) for card in cards[:3]))) +
                             tuple(DECK.index(card) for card in cards[3:]))
    _need(set(census["boards"]) == expected_boards,
          "raw wire ordered selected boards differ from the original fixed fixture")
    forecast = census["admission_amounts"]
    _validate_indexed_ledger(exact=exact, route=route, admission=admission, direct=direct,
        iterations=iterations, traversal=traversal, forecast=forecast)
    lines = output.decode("ascii").splitlines()
    done_positions = [i for i, line in enumerate(lines) if line.startswith("DONE\t")]
    route_positions = [i for i, line in enumerate(lines) if line.startswith("ROUTE\t")]
    admission_positions = [i for i, line in enumerate(lines) if line.startswith("ADMISSION\t")]
    frame_positions = [i for i, line in enumerate(lines) if line.startswith("FRAME\t")]
    _need((len(done_positions), len(route_positions), len(admission_positions), len(frame_positions)) ==
        (1, 1, 1, 1 if traversal == "active-frames" else 0), "native proof record multiplicity mismatch")
    done_i, route_i, admission_i = done_positions[0], route_positions[0], admission_positions[0]
    _need(done_i < route_i < admission_i and
        (traversal != "active-frames" or admission_i < frame_positions[0]), "native proof records are out of order")
    # DONE has no mode token; keep its versioned width/order check explicit.
    done_cells = lines[done_i].split("\t")
    _need(len(done_cells) == 1 + len(deps.native.COUNTERS) and done_cells[0] == "DONE" and
        all(value.isascii() and value.isdecimal() and len(value) <= 20 for value in done_cells[1:]),
        "DONE record schema mismatch")
    done = dict(zip(deps.native.COUNTERS, map(int, done_cells[1:])))
    _need(all(exact.get(k) == value for k, value in done.items()), "raw DONE counters differ from payload")
    route_fields = deps.native.ROUTE_FIELDS
    route = _parse_record(lines[route_i], "ROUTE", "indexed", route_fields)
    route_payload = exact.get("indexed_routing")
    _need(type(route_payload) is dict and route_payload.get("mode") == "indexed" and
        {k: v for k, v in route_payload.items() if k != "mode"} == route,
        "raw ROUTE fields differ from payload")
    admission_fields = deps.native.ADMISSION_FIELDS
    admission = _parse_record(lines[admission_i], "ADMISSION", "indexed-v1", admission_fields)
    admission_payload = exact.get("indexed_admission")
    _need(type(admission_payload) is dict and admission_payload.get("mode") == "indexed-v1" and
        {k: v for k, v in admission_payload.items() if k != "mode"} == admission,
        "raw ADMISSION fields differ from payload")
    if traversal == "active-frames":
        _need(tuple(deps.native.FRAME_FIELDS) == FRAME_FIELDS, "Python/native FRAME schema pin differs")
        frame = _parse_frame_line(lines[frame_positions[0]])
        frame_payload = exact.get("active_frames")
        _need(type(frame_payload) is dict and frame_payload.get("mode") == "active-v1" and
            {k: v for k, v in frame_payload.items() if k != "mode"} == frame,
            "raw FRAME proof differs from payload")
        _validate_frame(frame, iterations=iterations, direct=direct, kernel_hands=max(hands),
            route=route, admission=admission, done=done)
    else:
        _need("active_frames" not in exact, "V3 result unexpectedly contains active-frame proof")
    if case_name == "physical-g6":
        _need(done["group_size"] == 6 and exact["quotient_rows"] < exact["expanded_rows"],
              "physical G6 fixture did not exercise Q member deduplication")
    return {"status": "complete", "payload": payload}


def _verify(case, payload, deps):
    return deps.capacity._verify(case, payload, deps)


def _pair_identity(left, right, left_verification, right_verification, deps):
    a, b = left["payload"], right["payload"]
    _need(a.get("chance_input_snapshot") == b.get("chance_input_snapshot"),
          "paired chance input snapshots differ")
    _need(_canonical(a.get("strategy")) == _canonical(b.get("strategy")),
          "paired complete policy rows/action menus/probabilities differ")
    metrics = deps.equivariant.METRICS
    _need(all(float(a[key]).hex() == float(b[key]).hex() for key in metrics),
          "paired binary64 metric values differ")
    result = {"complete_rows": len(a["strategy"]), "policy_and_action_rows_bitwise_identical": True,
        "all_eight_metric_binary64_identical": True,
        "value_cursor_seconds": left["seconds"], "active_frames_seconds": right["seconds"],
        "scope": "One fixed fixture/pair only; complete API call plus serialization/hash, no universal speed claim."}
    exact_a, exact_b = left_verification.get("exact", {}), right_verification.get("exact", {})
    cert_a = exact_a.get("result", {}).get("exact_certificate") if exact_a.get("status") == "complete" else None
    cert_b = exact_b.get("result", {}).get("exact_certificate") if exact_b.get("status") == "complete" else None
    if type(cert_a) is dict and type(cert_b) is dict:
        _need(cert_a.get("metrics") == cert_b.get("metrics") and cert_a.get("threshold") == cert_b.get("threshold") and
              cert_a.get("threshold_met") == cert_b.get("threshold_met"),
              "paired exact certificate metrics/threshold flags differ")
        result["exact_certificate_metrics_and_flags_identical"] = True
        result["threshold_met"] = cert_a.get("threshold_met")
    else:
        result["exact_certificate_metrics_and_flags_identical"] = None
        result["exact_certificate_statuses"] = (exact_a.get("status"), exact_b.get("status"))
    return result


def _pair_key(entry):
    case, iterations, traversal, sample = entry
    return case, iterations, sample


def _run_child(command):
    return subprocess.run(command, cwd=ROOT, capture_output=True, check=False)


def _check_captured(output, captured):
    _need(all((output / name).is_file() and _sha((output / name).read_bytes()) == digest
              for name, digest in captured.items()), "captured raw evidence changed")


def run(output, executable):
    output = Path(output).resolve()
    _need(output != ROOT and ROOT not in output.parents and not output.exists(),
          "Use a new external active-frame study directory")
    source = build = cases = deps = None
    samples, payloads, verifications = [], {}, {}
    first_failure = None
    attempts = 0
    output.mkdir(parents=True)
    pair_results = {}
    captured = {}
    def capture(name, raw):
        _need(name not in captured and not (output / name).exists(), "duplicate captured artifact")
        (output / name).write_bytes(raw)
        captured[name] = _sha(raw)
    def capture_json(name, value):
        capture(name, json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n")
    try:
        source = _authenticate_source()
        _write(output / "source-before.json", source)
        auth_proof = (_AUTH_PROOF if type(_AUTH_PROOF) is dict and _AUTH_PROOF.get("commit") == source["commit"]
                      else {"commit": source["commit"], "capture_status": "not-captured-by-mocked-authenticator"})
        _write(output / "source-auth-proof.json", auth_proof)
        deps = _dependencies()
        cases = validate_cases(deps)
        build = deps.native.executable_identity(executable)
        _write(output / "build-before.json", build)
        _write(output / "protocol.json", {"version": "native-active-frames-fixed-study-v1",
            "source_commit": source["commit"], "source_sha256": source["sha256"], "build": build,
            "runtime": deps.quotient._runtime(), "schedule": SCHEDULE,
            "cases": cases, "options": OPTIONS,
            "aliases": ((MATRIX[0], 10, "original-22-t10", 10, 0),
                        (MATRIX[0], 100, "original-22-t10", 100, 0)),
            "retry_policy": "none; preserve first child stdout/stderr and native streams",
            "scope": "Fixed finite selected-runout games; native V3 indexed value-cursor versus V4 active-frames. Complete-call timer includes API serialization/hash; process peak is process-wide. No Python tracing and no universal speed or native-memory claim."})
        for entry in SCHEDULE:
            identifier = label(entry)
            case_name, iterations, traversal, sample = entry
            try:
                _need(_identity() == source and deps.native.executable_identity(executable) == build,
                      "source/build changed before scheduled child")
                _check_captured(output, captured)
                attempts += 1
                command = [sys.executable, "-B", "-m", "scripts.benchmark_native_active_frames",
                    "--child", case_name, "--iterations", str(iterations), "--traversal", traversal,
                    "--sample", str(sample), "--native-executable", str(executable)]
                process = _run_child(command)
                capture(identifier + ".stdout.bin", process.stdout)
                capture(identifier + ".stderr.bin", process.stderr)
                capture_json(identifier + "-process-status.json", {"returncode": process.returncode,
                    "stdout_sha256": _sha(process.stdout), "stderr_sha256": _sha(process.stderr)})
                _need(process.returncode == 0, "active-frame child process failed: " + str(process.returncode))
                raw = _decode(process.stdout)
                # Save complete child JSON and every decoded native stream before validation.
                capture(identifier + ".raw.json", process.stdout)
                for index, stream in enumerate(raw.get("native_streams", ())):
                    for key in ("request", "stdout", "stderr"):
                        value = base64.b64decode(stream[key], validate=True)
                        capture(f"{identifier}-native-{index}-{key}.bin", value)
                    capture_json(f"{identifier}-native-{index}-status.json",
                        {"returncode": stream.get("returncode"), "request_sha256": _sha(base64.b64decode(stream["request"], validate=True)),
                         "stdout_sha256": _sha(base64.b64decode(stream["stdout"], validate=True)),
                         "stderr_sha256": _sha(base64.b64decode(stream["stderr"], validate=True))})
                outcome = validate(raw, entry, deps, cases)
                summary = {key: value for key, value in raw.items() if key not in ("payload", "native_streams")}
                summary["artifact"] = identifier + ".raw.json"
                samples.append(summary)
                if outcome["payload"] is not None:
                    payloads[identifier] = raw
                    _need(_identity() == source and deps.native.executable_identity(executable) == build,
                          "source/build changed before saved-only independent replay")
                    payload_before = _sha(_canonical(raw["payload"]))
                    _check_captured(output, captured)
                    try:
                        verification = _verify(cases[case_name], raw["payload"], deps)
                    finally:
                        _need(_sha(_canonical(raw["payload"])) == payload_before,
                              "saved policy payload changed during independent replay")
                        _check_captured(output, captured)
                        _need(_identity() == source and deps.native.executable_identity(executable) == build,
                              "source/build changed during independent replay")
                    verifications[identifier] = verification
                    _write(output / (identifier + "-verification.json"), verification)
                    numeric = verification.get("numeric")
                    _need(type(numeric) is dict and numeric.get("status") in ("complete", "resource-unverified"),
                          "independent numeric replay has an invalid status")
                    if numeric["status"] == "complete":
                        gaps = verification.get("numeric_metric_gaps")
                        _need(type(gaps) is dict and set(gaps) == set(deps.equivariant.METRICS) and
                            all(type(value) in (int, float) and math.isfinite(value) and
                                value <= deps.equivariant.REPLAY_TOLERANCE for value in gaps.values()),
                            "independent numeric replay did not pass its recorded tolerance")
                    else:
                        _need(verification.get("quality_gate") is None,
                              "unverified numeric replay must not carry a quality pass")
                print(identifier, outcome["status"], flush=True)
            except Exception as exc:
                first_failure = {"stage": "child", "sample": identifier,
                    "type": type(exc).__name__, "message": str(exc)}
                _write(output / (identifier + "-first-failure.json"), first_failure)
                break
        # Every T10 pair and the private-flush T100 pair is a required complete control.
        if first_failure is None:
            for case_name, iterations in REQUIRED_COMPLETE:
                matches = [row for row in SCHEDULE if row[0] == case_name and row[1] == iterations]
                _need(len(matches) >= 2 and all(label(row) in payloads for row in matches),
                      "required paired baseline/payload is missing: " + case_name)
            grouped = {}
            for row in SCHEDULE:
                key = _pair_key(row)
                if row[2] in TRAVERSALS:
                    grouped.setdefault(key, {})[row[2]] = row
            for key, modes in grouped.items():
                if set(modes) != set(TRAVERSALS):
                    continue
                left_id, right_id = label(modes["value-cursor"]), label(modes["active-frames"])
                if left_id not in payloads or right_id not in payloads:
                    continue
                comparison = _pair_identity(payloads[left_id], payloads[right_id],
                    verifications[left_id], verifications[right_id], deps)
                pair_results[left_id + "__vs__" + right_id] = comparison
                _write(output / (left_id + "__vs__" + right_id + "-comparison.json"), comparison)
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
                drift = {"stage": "source-after", "type": "ValueError", "message": "source drift after active-frame study"}
                if first_failure is None:
                    first_failure = drift
                _write(output / "source-drift.json", drift)
        except Exception as exc:
            _write(output / "source-after-error.json", {"type": type(exc).__name__, "message": str(exc)})
            if first_failure is None:
                first_failure = {"stage": "source-after", "type": type(exc).__name__, "message": str(exc)}
        if deps is not None and build is not None:
            try:
                build_after = deps.native.executable_identity(executable)
                _write(output / "build-after.json", build_after)
                if build_after != build:
                    drift = {"stage": "build-after", "type": "ValueError", "message": "native build drift after active-frame study"}
                    if first_failure is None:
                        first_failure = drift
                    _write(output / "build-drift.json", drift)
            except Exception as exc:
                _write(output / "build-after-error.json", {"type": type(exc).__name__, "message": str(exc)})
                if first_failure is None:
                    first_failure = {"stage": "build-after", "type": type(exc).__name__, "message": str(exc)}
    quality_misses = []
    for key, verification in verifications.items():
        exact = verification.get("exact", {})
        cert = exact.get("result", {}).get("exact_certificate") if exact.get("status") == "complete" else None
        if verification.get("quality_gate") is None or type(cert) is not dict or cert.get("threshold_met") is not True:
            quality_misses.append(key)
    original_t10_medians = {}
    for traversal in TRAVERSALS:
        rows = [row for row in samples if row.get("case") == "original-22-t10" and
            row.get("iterations") == 10 and row.get("native_traversal") == traversal and
            row.get("sample") in (0, 1, 2) and row.get("status") == "complete"]
        if {row["sample"] for row in rows} == {0, 1, 2}:
            original_t10_medians[traversal] = statistics.median(row["seconds"] for row in rows)
    if set(original_t10_medians) == set(TRAVERSALS):
        original_t10_medians["scope"] = "Three paired original-22 T10 replicates only; descriptive timing, not a universal performance claim."
    report = {"source_commit": source.get("commit") if source else None,
        "calls_planned": len(SCHEDULE), "calls_attempted": attempts,
        "calls_captured": len(samples), "samples": samples,
        "paired_comparisons": pair_results, "original_t10_three_pair_medians_seconds": original_t10_medians,
        "quality_misses_or_unverified_retained": quality_misses,
        "failure": first_failure,
        "scope": "Fixed native V3/V4 finite-game comparison. Every outcome, resource miss, and verifier-limited result is retained; this does not establish unrestricted speed, memory, or convergence claims."}
    _write(output / "report.json", report)
    _write(output / "manifest.json", {"version": "native-active-frames-evidence-manifest-v1",
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
    parser.add_argument("--traversal", choices=TRAVERSALS)
    parser.add_argument("--sample", type=int, default=0)
    args = parser.parse_args()
    if args.child:
        _need(args.iterations is not None and args.traversal is not None,
              "child requires explicit fixed iterations/traversal")
        result = child(args.child, args.iterations, args.traversal, args.sample, args.native_executable)
    else:
        if args.output is None:
            parser.error("--output is required")
        result = run(args.output, args.native_executable)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if args.child or result["outcome"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
