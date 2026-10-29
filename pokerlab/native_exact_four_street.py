"""Explicit one-process exact-product native training transport.

Python prepares legal public structure and independently evaluates the expanded
returned policy. Native owns exact normalization/ranking/vectors and Q learning.
No Python ranks, normalizer, strategy, private pairs or worlds enter this wire.
"""
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
from threading import Thread

from .cards import DECK
from .shared_public_topology import ChanceVertex, DecisionVertex, TerminalVertex

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "OPENPOKER_NATIVE_EXACT_FOUR_STREET_V1"
RESULT = "OPENPOKER_NATIVE_EXACT_FOUR_STREET_RESULT_V1"
ROUTED_PROTOCOL = "OPENPOKER_NATIVE_EXACT_FOUR_STREET_ROUTED_V2"
ROUTED_RESULT = "OPENPOKER_NATIVE_EXACT_FOUR_STREET_ROUTED_RESULT_V2"
ROUTES = ("full-history", "shadow", "indexed")
ROUTE_FIELDS = frozenset("q_rows map_entries map_upper r_lookup_entries old_q_histories_retained "
    "q_routes q_routes_upper q_tokens q_tokens_upper roots roots_upper edges edges_upper "
    "decisions decisions_upper prefixes prefixes_upper decision_comparisons prefix_comparisons "
    "legacy_extensions legacy_rows legacy_prefixes router_work router_work_upper index_work index_work_upper "
    "index_entries index_entries_upper router_retained router_retained_upper setup_scratch_upper query_scratch_upper "
    "cursor_fields cursor_frames_upper combined_work combined_entries caller_work caller_entries "
    "old_kernel_overlap old_history_forecast final_router_entries".split())
MAX_INPUT = 64 * 1024 * 1024
MAX_OUTPUT = 32 * 1024 * 1024
MAX_STDERR = 8192
TIMEOUT = 180
COUNTERS = ("expanded_rows", "expanded_action_slots", "group_size", "quotient_rows",
    "quotient_action_slots", "member_checks", "expected_member_checks", "modeled_work_upper",
    "kernel_work_upper", "retained_entries_upper", "maximum_numeric_workspace_slots",
    "final_numeric_workspace_slots", "rank_calls")

class NativeFailure(ValueError):
    """Retain bounded first process streams for caller-owned evidence capture."""
    def __init__(self, message, returncode, stdout, stderr):
        super().__init__(message)
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

def _need(value, message):
    if not value:
        raise ValueError(message)

def _hash(raw):
    return hashlib.sha256(raw).hexdigest()

def _object(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "Duplicate exact native build manifest key")
        result[key] = value
    return result

def executable_identity(executable):
    from scripts import build_native_exact_four_street as builder
    supplied = Path(executable)
    _need(not supplied.is_symlink(), "Exact native executable cannot be linked")
    path = supplied.resolve(strict=True)
    _need(path.name in ("native-exact-four-street-train", "native-exact-four-street-train.exe") and
          path.is_file() and path.stat().st_size <= 64 * 1024 * 1024, "Invalid exact native executable")
    manifest_path = path.parent / "native-exact-build-manifest.json"
    raw = builder._bounded_read(manifest_path, 128 * 1024)
    manifest = json.loads(raw, object_pairs_hook=_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite native manifest")))
    sources = (*builder.TARGETS["engine"][1], "scripts/build_native_exact_four_street.py",
        "third_party/boost-multiprecision-1.92.0/manifest.json",
        "third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt",
        "third_party/boost-multiprecision-1.92.0/headers.zip")
    expected = {name: _hash(builder._bounded_read(ROOT / name, 2 * 1024 * 1024)) for name in sources}
    dependency, headers = builder._dependency()
    _need(manifest.get("contract") == "native-exact-build-v1" and manifest.get("target") == "engine" and
          manifest.get("source_sha256") == expected and manifest.get("executable_sha256") == _hash(path.read_bytes()) and
          Path(manifest.get("executable", "")).resolve() == path and
          manifest.get("dependency_commit") == dependency["commit"] and
          manifest.get("dependency_archive_sha256") == builder.HEADER_ARCHIVE_SHA256 and
          manifest.get("dependency_manifest_sha256") == builder.DEPENDENCY_MANIFEST_SHA256 and
          manifest.get("dependency_headers") == len(headers) and manifest.get("license") == "BSL-1.0",
          "Exact native source/build changed; rebuild explicitly")
    flags = manifest.get("flags")
    _need(type(flags) is list and all(type(value) is str for value in flags) and
          any("BOOST_MP_STANDALONE" in value for value in flags) and
          (("/fp:strict" in flags and "/std:c++20" in flags) or
           ("-fno-fast-math" in flags and "-ffp-contract=off" in flags and "-std=c++20" in flags)) and
          all(type(manifest.get(key)) is str and manifest[key] for key in ("compiler", "compiler_version", "platform")),
          "Missing strict exact-native compiler identity")
    return {"executable": str(path), "executable_sha256": manifest["executable_sha256"],
        "manifest_sha256": _hash(raw), "source_sha256": expected, "compiler": manifest["compiler"],
        "compiler_version": manifest["compiler_version"], "flags": flags, "platform": manifest["platform"]}

def _bits(value):
    value = float(value)
    _need(math.isfinite(value), "Nonfinite exact native wire value")
    return format(struct.unpack(">Q", struct.pack(">d", value))[0], "016x")

def _text(value):
    _need(type(value) is str and 0 < len(value) <= 64 and value.isascii() and
          all(32 < ord(char) < 127 for char in value), "Invalid exact native text token")
    return value

def admit(prepared):
    """Retain every old R/Q guard and reserve new native work additionally."""
    from .suit_quotient_plan import _group, plan_admission
    from .suit_public_automorphism import verify_public_suit_automorphisms
    old = prepared.admission
    group_work = 24 * (16 * sum(prepared.kernel.hand_counts) + 32 * len(prepared.kernel.selected))
    group_entries = 32 * sum(prepared.kernel.hand_counts) + 16 * len(prepared.kernel.selected) + 2048
    retained = old["retained_storage"]
    _need(old["combined_modeled_work_upper"] + group_work < old["whole_request_limit"] and
          retained["whole_request_peak_upper"] + group_entries < retained["entry_limit"],
          "Native old quotient group-search admission exceeded")
    group = _group(prepared.kernel)
    quotient = plan_admission(prepared, prepared.iterations, len(group))
    work_left = old["whole_request_limit"] - old["combined_modeled_work_upper"] - quotient["modeled_work_upper"]
    entries_left = retained["entry_limit"] - retained["whole_request_peak_upper"] - quotient["additional_retained_entries_upper"]
    _need(work_left > 0 and entries_left > 0, "Native old quotient whole-request admission exceeded")
    graph = verify_public_suit_automorphisms(prepared.topology, group,
        max_additional_work=min(work_left, 500_000_000), max_additional_entries=min(entries_left, 2_000_000))
    old_work = quotient["modeled_work_upper"] + graph["modeled_work_upper"]
    old_entries = quotient["additional_retained_entries_upper"] + graph["additional_retained_entries_upper"]
    vertices = prepared.topology.vertices
    edges = sum(len(value.child_ids) if isinstance(value, DecisionVertex) else
        len(value.branches) if isinstance(value, ChanceVertex) else 0 for value in vertices)
    input_upper = (4096 + 128 * sum(prepared.kernel.hand_counts) + 128 * len(prepared.kernel.selected) +
        512 * len(vertices) + 512 * edges + 65 * len(prepared.topology.initial_history))
    output_upper = (8192 + prepared.layout_upper["upper_history_token_bytes"] +
        64 * prepared.layout_upper["upper_dense_decision_hand_slots"] + 32 * prepared.action_slots_upper)
    _need(input_upper <= MAX_INPUT and output_upper <= MAX_OUTPUT, "Native exact complete I/O admission exceeded")
    # Counts character/byte buffers conservatively as logical entries, including
    # wire fragments, encoded request, captured bytes and parsed token lists.
    io_entries = 4 * input_upper + 8 * output_upper
    io_work = 8 * (input_upper + output_upper)
    work_left = old["whole_request_limit"] - old["combined_modeled_work_upper"] - old_work - io_work
    entries_left = retained["entry_limit"] - retained["whole_request_peak_upper"] - old_entries - io_entries
    _need(work_left > 0 and entries_left > 0, "Native exact additional process/I/O admission exceeded")
    old["combined_modeled_work_upper"] += old_work + io_work
    retained["phase_upper_bounds"] = {name: value + old_entries + io_entries
        for name, value in retained["phase_upper_bounds"].items()}
    retained["whole_request_peak_upper"] += old_entries + io_entries
    reservation = {"version": "native-exact-additional-whole-request-v1", "old_quotient": quotient,
        "old_graph": graph, "group": ["".join(image) for image in group], "group_size": len(group),
        "input_bytes_upper": input_upper, "output_bytes_upper": output_upper,
        "io_entries_upper": io_entries, "io_work_upper": io_work,
        "native_work_limit": min(work_left, 500_000_000), "native_entries_limit": min(entries_left, 2_000_000),
        "scope": "Additional native process, wire and computation admission; every old expanded and Q guard remains charged, with no savings credit. Logical units, not CPU/RSS."}
    old["native_additional_admission"] = reservation
    return reservation

def wire(prepared, iterations, *, rank_cache_boards=1, native_work=500_000_000, native_entries=2_000_000,
         routing="full-history"):
    _need(type(routing) is str and routing in ROUTES, "Unsupported exact native routing mode")
    _need(type(iterations) is int and iterations == prepared.iterations, "Native iterations differ from admission")
    _need(type(rank_cache_boards) is int and 1 <= rank_cache_boards <= 64, "Invalid native rank-cache ceiling")
    _need(type(native_work) is int and 0 < native_work <= 500_000_000 and
          type(native_entries) is int and 0 < native_entries <= 2_000_000, "Invalid native remaining budget")
    kernel, topology = prepared.kernel, prepared.topology
    vertices = topology.vertices
    edge_count = sum(len(v.child_ids) if isinstance(v, DecisionVertex) else
        len(v.branches) if isinstance(v, ChanceVertex) else 0 for v in vertices)
    # Reserve a conservative complete input estimate before growing wire pieces.
    maximum_bytes = (4096 + 128 * sum(kernel.hand_counts) + 128 * len(kernel.selected) +
        512 * len(vertices) + 512 * edge_count + 65 * len(topology.initial_history))
    _need(maximum_bytes <= MAX_INPUT, "Exact native request byte admission exceeded")
    rows = [PROTOCOL if routing == "full-history" else ROUTED_PROTOCOL + "\n" + routing,
        " ".join(map(str, (iterations, rank_cache_boards, *kernel.hand_counts,
        len(kernel.selected), len(vertices), edge_count, topology.root_id, len(topology.initial_history)))),
        " ".join(map(str, (kernel.limits.max_integer_bits, min(kernel.limits.max_modeled_work, native_work),
            min(kernel.limits.max_storage_entries, native_entries), 1 << 30,
            native_work, native_entries, 16_000_000, native_work, native_entries, 1_000_000, 2_000_000)))]
    for hands, weights in zip(kernel.hands, kernel.weights):
        for hand, weight in zip(hands, weights):
            rows.append(f"{DECK.index(hand[0])} {DECK.index(hand[1])} {_bits(weight)}")
    for flop, turn, river in kernel.selected:
        rows.append(" ".join(str(DECK.index(card)) for card in (*flop, turn, river)))
    rows.extend(_text(token) for token in topology.initial_history)
    for vertex in vertices:
        if isinstance(vertex, DecisionVertex):
            rows.append(f"D {vertex.player} {len(vertex.actions)}")
            for action, child in zip(vertex.actions, vertex.child_ids):
                rows.append(f"{_text(action.name)} {_bits(action.amount)} {_bits(action.raise_to)} "
                    f"{int(action.full_raise)} {_text(action.token)} {child}")
        elif isinstance(vertex, ChanceVertex):
            rows.append(f"C {('flop', 'turn', 'river').index(vertex.street) + 1} {vertex.card_index} {len(vertex.branches)}")
            rows.extend(f"{_text(label)} {child}" for label, child in vertex.branches)
        else:
            _need(isinstance(vertex, TerminalVertex), "Unsupported native exact vertex")
            rows.append((f"F {vertex.winner} " if vertex.kind == "fold" else "S ") +
                f"{_bits(vertex.contributions[0])} {_bits(vertex.contributions[1])}")
    encoded = ("\n".join(rows) + "\n").encode("ascii")
    _need(len(encoded) <= maximum_bytes <= MAX_INPUT, "Native wire exceeded input forecast")
    return encoded

def _start_process(executable):
    return subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def _invoke(executable, raw):
    """Bound both pipes while the one-shot native process is running."""
    process = _start_process(executable)
    outputs, errors = {}, []
    def read(name, stream, limit):
        chunks, used = [], 0
        try:
            while True:
                value = stream.read(min(65536, limit + 1 - used))
                if not value:
                    break
                used += len(value)
                if used > limit:
                    allowed = limit - (used - len(value))
                    if allowed:
                        chunks.append(value[:allowed])
                    errors.append(ValueError("Native " + name + " byte ceiling exceeded")); process.kill(); break
                chunks.append(value)
            outputs[name] = b"".join(chunks)
        except BaseException as exc:
            errors.append(exc); process.kill()
        finally:
            stream.close()
    def write():
        try:
            process.stdin.write(raw); process.stdin.flush()
        except BrokenPipeError:
            pass
        except BaseException as exc:
            errors.append(exc); process.kill()
        finally:
            process.stdin.close()
    threads = [Thread(target=read, args=("stdout", process.stdout, MAX_OUTPUT)),
        Thread(target=read, args=("stderr", process.stderr, MAX_STDERR)), Thread(target=write)]
    for thread in threads:
        thread.start()
    try:
        status = process.wait(timeout=TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        process.kill(); status = process.wait(); errors.append(exc)
    except BaseException:
        process.kill(); process.wait(); raise
    finally:
        for thread in threads:
            thread.join(timeout=10)
    _need(not any(thread.is_alive() for thread in threads), "Native process pipe did not terminate")
    if errors:
        raise NativeFailure("Native process transport failed: " + str(errors[0]), status,
            outputs.get("stdout", b""), outputs.get("stderr", b"")) from errors[0]
    if status != 0 or outputs["stderr"]:
        raise NativeFailure("Native exact computation rejected: " + outputs["stderr"].decode("ascii", "replace"),
            status, outputs["stdout"], outputs["stderr"])
    return outputs["stdout"]

def parse_policy(raw, prepared, *, routing="full-history"):
    _need(type(raw) is bytes and len(raw) <= MAX_OUTPUT, "Native exact output byte ceiling exceeded")
    _need(type(routing) is str and routing in ROUTES, "Unsupported exact native routing mode")
    lines = raw.decode("ascii").splitlines()
    expected_result = RESULT if routing == "full-history" else ROUTED_RESULT
    _need(lines and lines[0] == expected_result and len(lines) >= 2, "Wrong native exact result protocol")
    route_receipt = None
    if routing != "full-history":
        fields = lines.pop().split("\t")
        _need(len(fields) == len(ROUTE_FIELDS) + 2 and fields[:2] == ["ROUTE", routing],
              "Missing or wrong indexed routing proof")
        route_receipt = {}
        for field in fields[2:]:
            key, separator, value = field.partition("=")
            _need(separator and key in ROUTE_FIELDS and key not in route_receipt and
                  value.isascii() and value.isdecimal() and len(value) <= 20,
                  "Malformed or duplicate indexed routing proof field")
            route_receipt[key] = int(value)
        _need(set(route_receipt) == ROUTE_FIELDS, "Incomplete indexed routing proof")
    averages, action_slots = {}, 0
    for line in lines[1:-1]:
        fields = line.split("\t")
        _need(fields and fields[0] == "ROW" and len(fields) >= 6, "Malformed native policy row")
        player, hand, length = map(int, fields[1:4])
        _need(player in (0, 1) and 0 <= hand < prepared.kernel.hand_counts[player] and 0 <= length <= 64,
              "Invalid native policy identity")
        history = tuple(_text(value) for value in fields[4:4 + length])
        _need(len(fields) > 4 + length, "Truncated native history/action count")
        count = int(fields[4 + length])
        _need(0 < count <= 64 and len(fields) == 5 + length + count, "Invalid native action count")
        key = (player, hand, history)
        _need(key not in averages and len(averages) < prepared.layout_upper["upper_dense_decision_hand_slots"],
              "Duplicate or oversized native policy row")
        values = []
        for token in fields[5 + length:]:
            _need(len(token) == 16 and all(char in "0123456789abcdef" for char in token), "Invalid native probability bits")
            value = struct.unpack(">d", bytes.fromhex(token))[0]
            _need(math.isfinite(value) and 0 <= value <= 1 and not (value == 0 and token != "0" * 16),
                  "Invalid native probability")
            values.append(value)
        _need(abs(math.fsum(values) - 1.0) <= 1e-12, "Native policy row is not normalized")
        action_slots += count
        _need(action_slots <= prepared.action_slots_upper, "Native expanded action capacity exceeded")
        averages[key] = values
    tail = lines[-1].split("\t")
    _need(tail[0] == "DONE" and len(tail) == len(COUNTERS) + 1, "Incomplete native exact result")
    _need(all(value.isdecimal() for value in tail[1:]), "Malformed native counters")
    receipt = dict(zip(COUNTERS, map(int, tail[1:])))
    _need(receipt["expanded_rows"] == len(averages) and receipt["expanded_action_slots"] == action_slots and
        1 <= receipt["group_size"] <= 24 and receipt["member_checks"] == receipt["expected_member_checks"] and
        receipt["expected_member_checks"] == 2 * prepared.iterations * len(averages) and
        receipt["quotient_rows"] <= len(averages) and receipt["quotient_action_slots"] <= action_slots and
        receipt["modeled_work_upper"] <= 500_000_000 and receipt["kernel_work_upper"] <= receipt["modeled_work_upper"] and
        receipt["retained_entries_upper"] <= 25_000_000 and
        receipt["maximum_numeric_workspace_slots"] == 4 * receipt["quotient_action_slots"] and
        receipt["final_numeric_workspace_slots"] == 0, "Native exact result/counter contract mismatch")
    # Authenticate complete physical visible-information support against the
    # admitted Python rules, after native numeric buffers have been released.
    support = {prefix: prepared.kernel.legal_hands(prefix) for prefix in prepared.unique_prefixes}
    from .preflop_solver import _revealed_board
    seen = 0
    for occurrence in prepared.topology.iter_occurrences():
        vertex = prepared.topology.vertices[occurrence.vertex_id]
        if not isinstance(vertex, DecisionVertex):
            continue
        board = _revealed_board(occurrence.history)
        prefix = () if not board else ("".join(board[:3]),) + tuple(board[3:])
        for hand in support[prefix][vertex.player]:
            key = (vertex.player, hand, occurrence.history)
            _need(key in averages and len(averages[key]) == len(vertex.actions), "Native lost or changed a physical policy row")
            seen += 1
    _need(seen == len(averages), "Native returned an extra physical row")
    if route_receipt is not None:
        r = route_receipt
        decisions = terminals = visits = 0
        for occurrence in prepared.topology.iter_occurrences():
            visits += 1
            vertex = prepared.topology.vertices[occurrence.vertex_id]
            decisions += isinstance(vertex, DecisionVertex)
            terminals += isinstance(vertex, TerminalVertex)
        iterations = prepared.iterations
        expected = {"roots": 3 * iterations, "edges": 3 * iterations * (visits - 1),
            "decisions": 3 * iterations * decisions,
            "prefixes": iterations * (2 * terminals + decisions), "q_routes": receipt["quotient_rows"]}
        for name, count in expected.items():
            _need(r[name] == r[name + "_upper"] == count, "Indexed complete-call schedule mismatch: " + name)
        _need(r["q_rows"] == receipt["quotient_rows"] and r["map_entries"] == r["map_upper"] == r["q_rows"] and
              r["q_tokens"] == r["q_tokens_upper"] and r["r_lookup_entries"] == 0 and
              r["old_q_histories_retained"] == 1 and r["final_router_entries"] == 0 and
              r["combined_work"] == receipt["modeled_work_upper"] and
              r["combined_entries"] == receipt["retained_entries_upper"] and
              r["cursor_fields"] == 4 + 24 * 8,
              "Indexed layout or whole-owner proof mismatch")
        for name in ("router_work", "index_work", "index_entries", "router_retained"):
            _need(r[name] <= r[name + "_upper"], "Indexed reservation exceeded: " + name)
        shadow = routing == "shadow"
        _need(r["decision_comparisons"] == (r["decisions"] if shadow else 0) and
              r["prefix_comparisons"] == (r["prefixes"] if shadow else 0) and
              r["legacy_extensions"] == (r["edges"] if shadow else 0) and
              r["legacy_rows"] == (r["decisions"] if shadow else 0) and
              r["legacy_prefixes"] == (r["prefixes"] if shadow else 0),
              "Indexed mode executed legacy hot-path operations or lost shadow comparisons")
        receipt["indexed_routing"] = {"mode": routing, **r}
    return averages, receipt

def train(prepared, *, executable, rank_cache_boards=1, native_work=500_000_000, native_entries=2_000_000,
          reservation=None, routing="full-history"):
    identity = executable_identity(executable)
    request = wire(prepared, prepared.iterations, rank_cache_boards=rank_cache_boards,
        native_work=native_work, native_entries=native_entries, routing=routing)
    output = _invoke(identity["executable"], request)
    _need(executable_identity(executable) == identity, "Native exact executable/source changed during solve")
    averages, receipt = parse_policy(output, prepared, routing=routing)
    _need(receipt["modeled_work_upper"] <= native_work and receipt["retained_entries_upper"] <= native_entries,
          "Native exceeded caller's reserved remaining work/storage")
    if reservation is not None:
        _need(receipt["group_size"] == reservation["group_size"] and len(request) <= reservation["input_bytes_upper"] and
              len(output) <= reservation["output_bytes_upper"], "Native proof differs from Python game/I/O admission")
    return averages, {**receipt, "protocol": PROTOCOL if routing == "full-history" else ROUTED_PROTOCOL, "request_sha256": _hash(request),
        "result_sha256": _hash(output), "request_bytes": len(request), "result_bytes": len(output),
        "build": identity, "calls": 1}
