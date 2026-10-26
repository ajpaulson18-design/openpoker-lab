"""Explicit source-built CFR+ trainer for a bounded public chance tree.

The caller retains physical-world construction, historical admission and exact
diagnostics. This module validates and serializes the complete visible tree;
the helper only trains its affine fold/showdown game.
"""

from collections.abc import Mapping
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

from .public_cfr import _aggregate_prefixes, _validate_inputs
from .river_tree import _Node, _Terminal

SOURCE = Path(__file__).resolve().parents[1] / "native" / "public_tree_train.cpp"
PROTOCOL = "OPENPOKER_PUBLIC_CFR_V1"
WORK_MODEL = "native-public-cfr-work-v2"
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
        raise ValueError("Native public trainer must not be a symlink")
    path = supplied.resolve(strict=True)
    if not path.is_file() or path.name not in (
            "native-public-train", "native-public-train.exe"):
        raise ValueError("Native public trainer must be a regular named executable")
    manifest_path = path.parent / "native-public-manifest.json"
    if manifest_path.stat().st_size > 32768:
        raise ValueError("Native public manifest exceeds its size limit")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"),
                          object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ValueError("Nonfinite native manifest value")))
    required = {"schema_version", "protocol", "work_model", "source_sha256",
                "source_lf_sha256", "executable", "executable_sha256",
                "compiler", "compiler_version", "flags", "platform"}
    if type(manifest) is not dict or set(manifest) != required:
        raise ValueError("Unsupported native public manifest")
    source = SOURCE.read_bytes()
    if (manifest["schema_version"] != 1 or manifest["protocol"] != PROTOCOL
            or manifest["work_model"] != WORK_MODEL
            or manifest["executable"] != path.name
            or manifest["source_sha256"] != hashlib.sha256(source).hexdigest()
            or manifest["source_lf_sha256"] != hashlib.sha256(
                source.replace(b"\r\n", b"\n")).hexdigest()
            or manifest["executable_sha256"] != _sha(path)):
        raise ValueError("Native public source or executable changed; rebuild explicitly")
    if (any(type(manifest[k]) is not str or not manifest[k] for k in
            ("compiler", "compiler_version", "platform", "executable_sha256"))
            or type(manifest["flags"]) is not list
            or any(type(flag) is not str for flag in manifest["flags"])):
        raise ValueError("Malformed native public compiler provenance")
    return manifest


def _finite(value, label, *, lower=0.0, upper=1e12):
    if type(value) not in (int, float):
        raise ValueError(label + " must be finite numeric")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(label + " must be finite numeric") from exc
    if not math.isfinite(result) or not lower <= result <= upper:
        raise ValueError(label + " exceeds native numeric envelope")
    return result


def _prepare(root, worlds, infos, iterations, pot, chance_type):
    pot, hands = _validate_inputs(worlds, infos, iterations, "cfrplus", pot,
                                  chance_type)
    if not all(1 <= count <= MAX_HANDS for count in hands):
        raise ValueError("Native public active hand envelope is 1..128 per player")
    if iterations > 100_000:
        raise ValueError("Native public iteration envelope exceeded")
    if pot > 1e12:
        raise ValueError("Native public pot exceeds numeric envelope")

    # A bounded preflight precedes sparse aggregation and wire construction.
    if len(worlds) > 250_000:
        raise ValueError("Native public world count exceeds 250,000")
    nodes, prefixes, prefix_ids = [], [()], {(): 0}
    seen, encountered = set(), set()
    stack = [(root, (), 0)]
    while stack:
        node, prefix, depth = stack.pop()
        if depth > MAX_DEPTH or len(nodes) >= MAX_NODES or id(node) in seen:
            raise ValueError("Native public tree exceeds depth/node limit or is not an arborescence")
        seen.add(id(node))
        kind = 0 if type(node) is _Terminal else 2 if isinstance(node, chance_type) else 1
        if kind == 0:
            if (node.kind not in ("fold", "showdown") or
                    type(node.contributions) not in (tuple, list) or
                    len(node.contributions) != 2):
                raise ValueError("Native public terminal must be fold or showdown")
            c0, c1 = (_finite(x, "Contribution") for x in node.contributions)
            unit = pot / 2.0 + min(c0, c1)
            if not math.isfinite(unit) or unit > 1e12:
                raise ValueError("Native public terminal payoff exceeds envelope")
            if node.kind == "fold":
                if type(node.winner) is not int or node.winner not in (0, 1):
                    raise ValueError("Native fold terminal needs a winner")
                payoff = unit if node.winner == 0 else -unit
                terminal_kind = 0
            else:
                if node.winner is not None:
                    raise ValueError("Native showdown cannot have a fixed winner")
                payoff, terminal_kind = unit, 1
            children = ()
            player, history = -1, ()
        elif kind == 2:
            if type(node.branches) is not dict or not node.branches:
                raise ValueError("Native chance node needs nonempty branches")
            children = tuple(node.branches.items())
            if len(children) > 52:
                raise ValueError("Native chance fanout exceeds 52")
            player, history, payoff, terminal_kind = -1, (), 0.0, -1
        else:
            if (type(node) is not _Node or type(node.player) is not int or
                    node.player not in (0, 1) or type(node.history) is not tuple or
                    type(node.actions) is not tuple or
                    type(node.children) is not tuple or
                    not 1 <= len(node.children) <= 12 or
                    len(node.actions) != len(node.children)):
                raise ValueError("Native public decision shape is invalid")
            children = tuple(enumerate(node.children))
            player, history, payoff, terminal_kind = node.player, node.history, 0.0, -1
            encountered.add((player, history, len(children)))
        node_id = len(nodes)
        nodes.append((node, kind, prefix, depth, player, history, payoff,
                      terminal_kind, children))
        for token, child in reversed(children):
            next_prefix = prefix
            if kind == 2:
                try:
                    next_prefix = prefix + (token,)
                    hash(next_prefix)
                except TypeError as exc:
                    raise ValueError("Unhashable public chance branch") from exc
                if next_prefix not in prefix_ids:
                    prefix_ids[next_prefix] = len(prefixes)
                    prefixes.append(next_prefix)
            stack.append((child, next_prefix, depth + 1))
    if len(prefixes) > MAX_PREFIXES:
        raise ValueError("Native public prefix count exceeds limit")
    # The flattened tree is preorder, so descendants may be found by identity.
    ids = {id(row[0]): index for index, row in enumerate(nodes)}
    for row in nodes:
        if row[1] == 1 and len(row[5]) > MAX_DEPTH:
            raise ValueError("Native public history length exceeds limit")
    edges, marginals = _aggregate_prefixes(worlds, hands)
    # Early all-in terminals legitimately settle at the current public prefix;
    # their worlds still carry later hidden runout fields. Only revealed tree
    # prefixes are serialized. The root aggregate retains every world.
    if any(row[1] in (0, 1) and row[2] not in edges for row in nodes):
        raise ValueError("A terminal or decision prefix has no weighted worlds")
    for prefix, pairs in edges.items():
        if not pairs or any(not all(math.isfinite(x) for x in pair[2:]) for pair in pairs):
            raise ValueError("Nonfinite or empty native prefix edge row")
    shapes = {(player, history): count for player, history, count in encountered}
    if len(shapes) != len(encountered):
        raise ValueError("Repeated information history has inconsistent action counts")
    for key, count in infos.items():
        expected = shapes.get((key[0], key[2]))
        if expected is not None and count != expected:
            raise ValueError("Information-set action count disagrees with tree")
    return pot, hands, nodes, ids, prefixes, prefix_ids, edges, marginals


def _wire(prepared, infos, iterations, *, with_receipt=False):
    pot, hands, nodes, ids, prefixes, prefix_ids, edges, marginals = prepared
    keys = list(infos)
    rows = {key: index for index, key in enumerate(keys)}
    offsets, slots = [], 0
    for key in keys:
        offsets.append(slots)
        slots += infos[key]
    if slots > MAX_SLOTS:
        raise ValueError("Native information-action slots exceed 1,000,000")
    child_ids, maps, node_lines = [], [], []
    for node, kind, prefix, depth, player, history, payoff, terminal_kind, children in nodes:
        first_child = len(child_ids)
        child_ids.extend(ids[id(child)] for _, child in children)
        row_start = len(maps)
        if kind == 1:
            maps.extend(rows.get((player, hand, history), -1)
                        for hand in range(hands[player]))
        node_lines.append((kind, player, prefix_ids[prefix], first_child,
                           len(children), row_start, terminal_kind, payoff))
    if len(maps) > MAX_SLOTS or len(child_ids) > MAX_NODES:
        raise ValueError("Native row-map or tree-edge envelope exceeded")
    flat_pairs, prefix_lines = [], []
    for prefix in prefixes:
        start = len(flat_pairs)
        flat_pairs.extend(edges.get(prefix, ()))
        prefix_lines.append((start, len(flat_pairs) - start))
    if len(flat_pairs) > 250_000:
        raise ValueError("Native public edge envelope exceeded")
    terminal_edge_visits = sum(prefix_lines[row[2]][1]
                               for row in node_lines if row[0] == 0)
    decision_action_hands = sum(len(row[8]) * hands[row[4]]
                                for row in nodes if row[1] == 1)
    opponent_action_hands = sum(len(row[8]) * hands[1 - row[4]]
                                for row in nodes if row[1] == 1)
    chance_children = sum(len(row[8]) for row in nodes if row[1] == 2)
    decision_children = sum(len(row[8]) for row in nodes if row[1] == 1)
    hand_sum = sum(hands)
    # Reserve all modeled native state, scratch and work before serialization.
    depth_width = (MAX_DEPTH + 1) * 52 * max(hands)
    heap = (2 * MAX_INPUT_BYTES + 1 + len(nodes) * 80 + len(child_ids) * 4 +
            len(prefixes) * (16 + 8 * hand_sum) + len(flat_pairs) * 32 +
            len(keys) * 20 + len(maps) * 4 + slots * 40 +
            depth_width * 8 * 2 + 262144)
    traversal = (3 * len(nodes) + len(nodes) * hand_sum +
                 2 * terminal_edge_visits + (hand_sum + 3) * chance_children +
                 5 * decision_action_hands + opponent_action_hands +
                 2 * len(maps) + 3 * decision_children + 7 * slots +
                 4 * len(keys))
    setup = (128 * (len(nodes) + len(flat_pairs) + len(maps) + slots +
                    len(prefixes) * hand_sum) + len(keys) + 2 * slots +
             (MAX_DEPTH + 1) * 54 * max(hands) + hand_sum + max(hands))
    output_work = len(keys) + 2 * slots
    work = iterations * traversal + setup + output_work
    if heap > MAX_HEAP_BYTES or work > MAX_WORK:
        raise ValueError("Native public full-request heap/work envelope exceeded")
    sum_mode = 1 if sys.version_info >= (3, 12) else 0
    lines = [PROTOCOL, " ".join(map(str, (
        len(nodes), len(child_ids), len(prefixes), len(flat_pairs), len(keys),
        len(maps), slots, hands[0], hands[1], iterations, sum_mode,
        terminal_edge_visits, decision_action_hands,
        opponent_action_hands, chance_children, decision_children))) + " " + pot.hex()]
    lines.extend(" ".join(map(str, row[:-1])) + " " + row[-1].hex()
                 for row in node_lines)
    lines.extend(map(str, child_ids))
    lines.extend(" ".join(map(str, row)) for row in prefix_lines)
    lines.extend(f"{i} {j} {mass.hex()} {signed.hex()}"
                 for i, j, mass, signed in flat_pairs)
    lines.extend(f"{infos[key]} {offsets[index]}" for index, key in enumerate(keys))
    lines.extend(map(str, maps))
    payload = ("\n".join(lines) + "\n").encode("ascii")
    if len(payload) > MAX_INPUT_BYTES:
        raise ValueError("Native public wire exceeds 64 MiB")
    if with_receipt:
        return payload, keys, slots, {
            "budget_version": WORK_MODEL,
            "requested_iterations": iterations,
            "public_nodes": len(nodes),
            "public_prefixes": len(prefixes),
            "prefix_hand_edges": len(flat_pairs),
            "terminal_edge_visits_per_target_pass": terminal_edge_visits,
            "information_rows": len(keys),
            "information_action_slots": slots,
            "modeled_heap_bytes_upper_bound": heap,
            "modeled_heap_byte_limit": MAX_HEAP_BYTES,
            "modeled_work_entries_upper_bound": work,
            "modeled_work_entry_limit": MAX_WORK,
            "input_bytes": len(payload),
            "input_byte_limit": MAX_INPUT_BYTES,
            "scope": "Full native CFR+ request; Python adapter/preparation, "
                     "historical admission and exact diagnostics are separate. "
                     "Modeled entries and bytes are not elapsed time or "
                     "process RSS.",
        }
    return payload, keys, slots


def train_native_public(root, worlds, infos, iterations, *, pot, chance_type,
                        executable, return_receipt=False):
    """Return the same average-policy mapping as public CFR+ for a bounded tree."""
    if not isinstance(infos, Mapping):
        raise TypeError("infos must be a mapping")
    prepared = _prepare(root, worlds, infos, iterations, pot, chance_type)
    if type(return_receipt) is not bool:
        raise TypeError("return_receipt must be bool")
    if return_receipt:
        payload, keys, slots, receipt = _wire(
            prepared, infos, iterations, with_receipt=True)
    else:
        payload, keys, slots = _wire(prepared, infos, iterations)
    before = executable_identity(executable)
    try:
        result = subprocess.run([str(Path(executable).resolve(strict=True))],
                                input=payload, capture_output=True,
                                timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Native public trainer timed out") from exc
    if len(result.stdout) > MAX_OUTPUT_BYTES or len(result.stderr) > 8192:
        raise RuntimeError("Native public trainer output exceeds limit")
    if result.returncode:
        raise RuntimeError("Native public trainer failed: " +
                           result.stderr.decode("utf-8", "replace")[:4096])
    if executable_identity(executable) != before:
        raise RuntimeError("Native public binary or source changed during training")
    tokens = result.stdout.decode("ascii").split()
    if len(tokens) != slots + 2 or tokens[0] != PROTOCOL or int(tokens[1]) != slots:
        raise ValueError("Malformed native public result")
    values = [float.fromhex(token) for token in tokens[2:]]
    if any(not math.isfinite(value) or value < 0 or value > 1 for value in values):
        raise ValueError("Native public result contains invalid probability")
    output, offset = {}, 0
    for key in keys:
        count = infos[key]
        row = values[offset:offset + count]
        offset += count
        if abs(math.fsum(row) - 1) > 1e-9:
            raise ValueError("Native public policy row is not normalized")
        output[key] = row
    return (output, receipt) if return_receipt else output
