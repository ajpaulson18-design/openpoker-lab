"""Explicit native training over bounded selected probability/payoff queries."""

from collections.abc import Mapping
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

from .river_tree import _Node, _Terminal
from .postflop_solver import _Chance
from .packed_operator_cfr import layout_census
from .selected_runout_operator import SelectedRunoutOperator
from .cards import DECK, cards

SOURCE = Path(__file__).resolve().parents[1] / "native" / "selected_operator_train.cpp"
PROTOCOL = "OPENPOKER_SELECTED_OPERATOR_V1"
WORK_MODEL = "native-selected-operator-work-v1"
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_HEAP_BYTES = 256 * 1024 * 1024
MAX_WORK = 500_000_000
MAX_DEPTH = 64
MAX_HANDS = 128
MAX_NODES = 250_000
MAX_PREFIXES = 4096
MAX_SLOTS = 1_000_000
TIMEOUT = 180
MAX_BOARDS = 64
MAX_RANK_ENTRIES = 8192
_BITS = {card: 1 << i for i, card in enumerate(DECK)}


def arithmetic_identity():
    """Runtime reduction mode matching the caller's Python float sum."""
    return {"arithmetic_mode": "compensated" if sys.version_info >= (3, 12)
            else "left-to-right", "python_version": sys.version.split()[0]}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate native manifest field")
        result[key] = value
    return result


def executable_identity(executable):
    """Authenticate a separately built helper and return its recorded identity."""
    supplied = Path(executable)
    if supplied.is_symlink():
        raise ValueError("Native selected operator trainer must not be a symlink")
    path = supplied.resolve(strict=True)
    if not path.is_file() or path.name not in (
            "native-selected-train", "native-selected-train.exe"):
        raise ValueError("Native selected operator trainer must be a regular named executable")
    manifest_path = path.parent / "native-selected-manifest.json"
    if manifest_path.stat().st_size > 32768:
        raise ValueError("Native selected operator manifest exceeds its size limit")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"),
                          object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ValueError("Nonfinite native manifest value")))
    required = {"schema_version", "protocol", "work_model", "source_sha256",
                "source_lf_sha256", "executable", "executable_sha256",
                "compiler", "compiler_version", "flags", "platform"}
    if type(manifest) is not dict or set(manifest) != required:
        raise ValueError("Unsupported native selected operator manifest")
    source = SOURCE.read_bytes()
    if (manifest["schema_version"] != 1 or manifest["protocol"] != PROTOCOL
            or manifest["work_model"] != WORK_MODEL
            or manifest["executable"] != path.name
            or manifest["source_sha256"] != hashlib.sha256(source).hexdigest()
            or manifest["source_lf_sha256"] != hashlib.sha256(
                source.replace(b"\r\n", b"\n")).hexdigest()
            or manifest["executable_sha256"] != _sha(path)):
        raise ValueError("Native selected operator source or executable changed; rebuild explicitly")
    if (any(type(manifest[k]) is not str or not manifest[k] for k in
            ("compiler", "compiler_version", "platform", "executable_sha256"))
            or type(manifest["flags"]) is not list
            or any(type(flag) is not str for flag in manifest["flags"])):
        raise ValueError("Malformed native selected operator compiler provenance")
    return manifest


def _mask(cards_):
    return sum(_BITS[card] for card in cards_)


def _prefix_tokens(prefix):
    return (() if not prefix else
            (_mask(cards(prefix[0], 3)),) + tuple(_BITS[c] for c in prefix[1:]))


def _rank_code(rank):
    """Order-preserving fixed-width encoding of valid category/tiebreak tuples."""
    lengths = (6, 5, 4, 4, 2, 6, 3, 3, 2)
    if (not isinstance(rank, tuple) or not rank or type(rank[0]) is not int or
            not 0 <= rank[0] <= 8 or len(rank) != lengths[rank[0]] or
            any(type(x) is not int or not 2 <= x <= 14 for x in rank[1:])):
        raise ValueError("Malformed selected native rank tuple")
    code = 0
    for value in tuple(rank) + (0,) * (6 - len(rank)):
        code = 16 * code + value
    return code


def prepare(root, infos, iterations, *, operator):
    """Admit the complete native request before ranking or wire construction."""
    if type(operator) is not SelectedRunoutOperator:
        raise TypeError("Native selected training requires its fixed probability operator")
    if (not 1 <= len(operator.selected) <= MAX_BOARDS or
            any(not 1 <= h <= MAX_HANDS for h in operator.hand_counts) or
            len(operator.selected) * sum(operator.hand_counts) > MAX_RANK_ENTRIES):
        raise ValueError("Native selected board/hand/rank-vector capacity exceeded")
    layout = layout_census(root, infos, operator.hand_counts, iterations)
    nodes, prefixes, prefix_ids = [], [()], {(): 0}
    pending = [(root, (), 0)]
    counters = [0] * 6
    selected = [("".join(f), t, r) for f, t, r in operator.selected]
    supported = [("".join(f), t, r) for f, t, r in operator.reachable_selected()]
    pairs = operator.hand_counts[0] * operator.hand_counts[1]
    while pending:
        node, prefix, depth = pending.pop()
        if depth > MAX_DEPTH:
            raise ValueError("Native selected public depth exceeds 64")
        if isinstance(node, _Terminal):
            children, player, history = (), -1, ()
            kind, terminal = 0, 0 if node.kind == "fold" else 1
            if node.kind not in ("fold", "showdown"):
                raise ValueError("Unsupported native selected terminal")
            payoff = (0.0 if operator.pot is None else operator.pot / 2) + min(node.contributions)
            if node.kind == "fold":
                if type(node.winner) is not int or node.winner not in (0, 1):
                    raise ValueError("Invalid native selected fold winner")
                payoff *= 1 if node.winner == 0 else -1
            elif node.winner is not None:
                raise ValueError("Invalid native selected showdown winner")
            if not math.isfinite(payoff) or abs(payoff) > 1e12:
                raise ValueError("Native selected terminal numeric envelope exceeded")
        elif isinstance(node, _Chance):
            children = tuple(node.branches.items())
            if not 1 <= len(children) <= 64:
                raise ValueError("Native selected chance fanout exceeds 64")
            if len(prefix) >= 3:
                raise ValueError("Native selected chance cannot follow a complete board")
            expected = {board[len(prefix)] for board in supported if board[:len(prefix)] == prefix}
            if set(node.branches) != expected:
                raise ValueError("Native selected chance branches must partition all supported outcomes")
            kind, player, history, payoff, terminal = 2, -1, (), 0.0, -1
        else:
            kind, player, history, payoff, terminal = 1, node.player, node.history, 0.0, -1
            children = tuple(enumerate(node.children))
            if not 1 <= len(children) <= 12:
                raise ValueError("Native selected action fanout exceeds 12")
        matches = sum(board[:len(prefix)] == prefix for board in selected)
        if not matches:
            raise ValueError("Native selected tree prefix has no selected board")
        if kind == 0:
            counters[0] += matches * pairs
        elif kind == 1:
            counters[1] += matches * pairs
            counters[2] += len(children) * operator.hand_counts[player]
            counters[3] += len(children) * operator.hand_counts[1-player]
            counters[5] += len(children)
        else:
            counters[4] += len(children)
        nodes.append((node, kind, prefix, player, history, payoff, terminal, children))
        for token, child in reversed(children):
            child_prefix = prefix + (token,) if kind == 2 else prefix
            if child_prefix not in prefix_ids:
                prefix_ids[child_prefix] = len(prefixes)
                prefixes.append(child_prefix)
            pending.append((child, child_prefix, depth + 1))
    if len(prefixes) > 193:
        raise ValueError("Native selected prefix capacity exceeded")
    n, m = len(nodes), sum(len(x[7]) for x in nodes)
    r, s = len(infos), layout["action_slots"]
    q, hand_sum = layout["dense_decision_hand_slots"], sum(operator.hand_counts)
    b, p, width = len(operator.selected), len(prefixes), max(operator.hand_counts)
    terminal, marginal, actions, opponents, chances, decisions = counters
    setup = 128 * (n + q + s) + 10 * marginal + 32 * n * b + 128 * b * pairs + 64 * p
    sweep = (20 * terminal + 10 * marginal + 10 * n * hand_sum + 12 * s +
             6 * b * n + 8 * actions + opponents + chances * hand_sum + 4 * decisions)
    work = setup + iterations * sweep + r + 2 * s
    heap = (128 * 1024 * 1024 + 1 + 96 * n + 8 * m + 8 * q + 24 * r +
            40 * s + 48 * p + b * (32 + 8 * hand_sum) + 32 * hand_sum +
            (MAX_DEPTH + 1) * (64 + 2) * width * 16)
    if work > MAX_WORK or heap > MAX_HEAP_BYTES:
        raise ValueError("Native selected work/heap admission rejected")
    receipt = {"version": WORK_MODEL, "nodes": n, "children": m, "prefixes": p,
               "rows": r, "dense_map_slots": q, "action_slots": s,
               "hands": list(operator.hand_counts), "selected_boards": b,
               "retained_rank_entries": b * hand_sum, "stored_worlds": 0,
               "stored_prefix_pair_edges": 0, "prefix_marginal_cache_entries": hand_sum,
               "structural_counters": counters, "modeled_work_entries": work,
               "work_limit": MAX_WORK, "modeled_heap_bytes": heap, "heap_limit": MAX_HEAP_BYTES,
               "scope": "Whole-request logical loops and conservative storage model, not CPU/RSS guarantees."}
    receipt["normalizer_verification"] = "exact-positive-binary64-superaccumulator-v1"
    return nodes, prefixes, prefix_ids, receipt


def wire(root, infos, iterations, *, operator):
    nodes, prefixes, prefix_ids, receipt = prepare(root, infos, iterations, operator=operator)
    keys = list(infos)
    indices = {key: i for i, key in enumerate(keys)}
    ids = {id(row[0]): i for i, row in enumerate(nodes)}
    offsets, slot = [], 0
    for key in keys:
        offsets.append(slot)
        slot += infos[key]
    mode = int(sys.version_info >= (3, 12))
    header = [receipt[k] for k in ("nodes", "children", "rows", "dense_map_slots", "action_slots")]
    header += [*operator.hand_counts, len(operator.selected), len(prefixes), iterations, mode]
    lines = [PROTOCOL, " ".join(map(str, header + receipt["structural_counters"])), operator.normalizer.hex()]
    for player in (0, 1):
        lines.extend(f"{_mask(hand)} {weight.hex()}" for hand, weight in zip(operator.hands[player], operator.weights[player]))
    # These ranks are O(B*(H0+H1)), capped at 8192, never private-pair worlds.
    for index, (flop, turn, river) in enumerate(operator.selected):
        ranks = operator._build_rank_vectors(index)
        lines.append(f"{_mask(flop)} {_BITS[turn]} {_BITS[river]}")
        lines.append(" ".join(str(0 if rank is None else _rank_code(rank)) for side in ranks for rank in side))
    for prefix in prefixes:
        tokens = _prefix_tokens(prefix)
        lines.append(" ".join(map(str, (len(tokens), *tokens, *((0,) * (3-len(tokens)))))))
    first = map_offset = 0
    children, maps = [], []
    for node, kind, prefix, player, history, payoff, terminal, branches in nodes:
        lines.append(f"{kind} {player} {prefix_ids[prefix]} {first} {len(branches)} {map_offset} {terminal} {payoff.hex()}")
        children.extend(ids[id(child)] for _, child in branches)
        first += len(branches)
        if kind == 1:
            maps.extend(indices.get((player, h, history), -1) for h in range(operator.hand_counts[player]))
            map_offset += operator.hand_counts[player]
    lines.append(" ".join(map(str, children)))
    lines.extend(f"{infos[key]} {offset}" for key, offset in zip(keys, offsets))
    lines.append(" ".join(map(str, maps)))
    payload = ("\n".join(lines) + "\n").encode("ascii")
    if len(payload) > MAX_INPUT_BYTES:
        raise ValueError("Native selected payload exceeds 64 MiB")
    receipt["input_bytes"] = len(payload)
    return payload, keys, receipt


def train_native_selected(root, infos, iterations, *, operator, executable):
    prepare(root, infos, iterations, operator=operator)
    before = executable_identity(executable)
    payload, keys, receipt = wire(root, infos, iterations, operator=operator)
    try:
        process = subprocess.run([str(Path(executable).resolve(strict=True))], input=payload,
                                 capture_output=True, timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Native selected operator timed out; no fallback") from exc
    if len(process.stdout) > MAX_OUTPUT_BYTES or len(process.stderr) > 8192:
        raise RuntimeError("Native selected output exceeds its bound")
    if process.returncode:
        raise RuntimeError("Native selected training failed: " + process.stderr.decode("utf-8", "replace")[:4096])
    if executable_identity(executable) != before:
        raise RuntimeError("Native selected binary/source identity changed during training")
    tokens = process.stdout.decode("ascii").split()
    if (len(tokens) != receipt["action_slots"] + 7 or tokens[0] != PROTOCOL or
            int(tokens[1]) != receipt["action_slots"] or tokens[-2] != "RSS"):
        raise ValueError("Malformed native selected result")
    counters = [int(x) for x in tokens[2:5]]
    expected = receipt["structural_counters"]
    if (any(x < 0 for x in counters) or counters[0] > 2 * iterations * expected[0] or
            counters[1] > iterations * expected[1] or
            counters[2] > len(operator.selected) * operator.hand_counts[0] * operator.hand_counts[1]):
        raise ValueError("Native selected exceeded its admitted pair/board loops")
    native_peak = int(tokens[-1])
    if not 0 < native_peak < 1 << 64:
        raise ValueError("Invalid native process memory measurement")
    values = [float.fromhex(x) for x in tokens[5:-2]]
    if any(not math.isfinite(x) or x < 0 or x > 1 for x in values):
        raise ValueError("Native selected returned invalid probabilities")
    result, offset = {}, 0
    for key in keys:
        row = values[offset:offset + infos[key]]
        offset += infos[key]
        if abs(math.fsum(row) - 1.0) > 1e-9:
            raise ValueError("Native selected row is not normalized")
        result[key] = row
    receipt.update({"terminal_pair_board_checks": counters[0], "marginal_pair_board_checks": counters[1],
                    "normalization_pair_board_checks": counters[2], "identity": before,
                    "native_process_lifetime_peak_working_set_bytes": native_peak,
                    **arithmetic_identity()})
    return result, receipt

