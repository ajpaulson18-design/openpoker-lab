"""Independent two-board immutable-policy session resource equation.

The owner graph and its full policy import are common; board-specific values,
staging and raw output are retained for both selectors until atomic completion.
This is a forecast only and never calls a native producer or forecast helper.
"""
from __future__ import annotations

from functools import lru_cache
from tests.virtual_frozen_grid_preflight_reference import boards, census, dense_public_census, geometry
from tests.virtual_frozen_update_reference import scaled_proof9_ranges

WORK_CAP = 500_000_000
HISTORY_CAP = 42_000_000
STATE_CAP = 75_000_000
CHANCE_CAP = 110_000_000
PARENT_CAP = 115_000_000
ENTRIES_CAP = 2_000_000
PAYLOAD_CAP = 1 << 30
OUTPUT_CAP = 2_100_000
INPUT_CAP = 8 << 20
ROWS = 24_420
SLOTS = 58_164
HISTORY_TOKENS = 249_662
LAWS = ("uniform", "river_weighted")
CAPS = {"work": WORK_CAP, "history": HISTORY_CAP, "state": STATE_CAP,
        "chance": CHANCE_CAP, "parent": PARENT_CAP, "entries": ENTRIES_CAP,
        "payload": PAYLOAD_CAP, "output": OUTPUT_CAP}


def _words(bits):
    return max(1, (bits + 63) // 64)


def _copy(bits):
    return 1 + 2 * _words(bits)


def _add(bits):
    return 2 + 3 * _words(bits)


def _multiply(a, b):
    return 2 + 2 * (_words(a) + _words(b)) + _words(a) * _words(b)


def _prepared_query(showdown, own, opponent):
    input_work = 12 + 11 + 2 * (4 + 2 * _words(365)) + 4
    dynamic = 12
    if own and opponent:
        bucket = 4 + 365 + (opponent - 1).bit_length() + 4
        output = 4 + bucket
        dynamic += opponent * _multiply(4, 365)
        dynamic += 53 * (2 + own if showdown else 1)
        dynamic += opponent * (9 if showdown else 3) * _add(bucket)
        dynamic += own * ((12 if showdown else 3) * _add(bucket) +
                          _multiply(4, bucket) + _copy(output) + 2 * _words(bucket))
        dynamic += 128
    return input_work + dynamic + (384 if showdown else 0)


@lru_cache(maxsize=1)
def _fixed():
    g = geometry()
    dense = dense_public_census()["shape"]
    phases = tuple(g["by_street"].values())
    edges = sum(x["decision_action_slots"] for x in phases)
    reveals = sum(x["reveals"] for x in phases)
    folds = sum(x["folds"] for x in phases)
    showdowns = sum(x["showdowns"] for x in phases)
    decisions = sum(sum(x["decision_occurrences"]) for x in phases)
    catalog = 3_000_000 + 8 * dense["visits"] + 64 * dense["candidates"] + 16 * ROWS + 4 * SLOTS
    read_cost = 208 + 16 * (ROWS + 1).bit_length()
    state_entries = 1024 + 16 * ROWS + 10 * SLOTS
    state_payload = ((5 * SLOTS + 256) * (648 + 58) + 128 * SLOTS +
                     512 * SLOTS + 16 * ROWS)
    entries_base = (state_entries + 131_072 + 32 * 1105 + 1 + 12_000 +
                    16_384)
    payload_base = (state_payload + (1 << 20) + 8 * (1 << 20) + (1 << 22) +
                    32 * 181 + 8 * 16_384)
    history_base = (4096 * 1105 + 1280 + 40 * dense["actions"] +
                    72 * dense["reveals"] + 48 * dense["visits"] + 40 * ROWS +
                    8 * ROWS + 72 * HISTORY_TOKENS + 56 * ROWS + 16 * SLOTS +
                    288 * ROWS)
    state_base = (1024 + 8 * ROWS + 16 * SLOTS + 4 * 11 +
                  ROWS * (128 + 16 * (ROWS + 1).bit_length()) + 256 * SLOTS +
                  1088 + 130 * ROWS + 258 * SLOTS + read_cost * ROWS)
    raw_history_per_board = 2 * (48 * edges + 80 * reveals + 8)
    return (g, dense, phases, edges, reveals, folds, showdowns, decisions, catalog,
            read_cost, entries_base, payload_base, history_base, state_base,
            raw_history_per_board)


def _board_terms(board):
    (g, dense, phases, edges, reveals, folds, showdowns, decisions, catalog,
     _read_cost, _entries_base, _payload_base, _history_base, _state_base,
     raw_history_per_board) = _fixed()
    shape = census(board)
    r, s = shape["supported_rows"], shape["supported_action_slots"]
    hands = scaled_proof9_ranges()
    blocked = set(board)
    live = [sum(not blocked.intersection(hand) for hand, _ in side) for side in hands]

    chance = sum(folds * _prepared_query(False, live[p], live[1-p]) +
                 showdowns * _prepared_query(True, live[p], live[1-p]) for p in (0, 1))
    chance += 4 * 4096 + 512 + 64 + 4 * 64
    chance += 8 * _prepared_query(False, 2, 2)
    reach = 2 * edges * (24 + 2 * (_multiply(365, 53) + _copy(365)))
    scale = 4 * (folds + showdowns) * (32 + _multiply(378, 4) +
        _multiply(382, 14) + _copy(647) + 2 * _words(699))
    mix = (4 * edges * (8 + _multiply(647, 53) + _add(699) + _copy(699)) +
           s * (8 + _add(648) + _copy(648)) +
           4 * decisions * (_copy(699) + _copy(648)))
    average = (r * (64 + _multiply(5, 14) + _multiply(313, 19) +
                    _copy(381) + _copy(383)) +
               s * (16 + _multiply(332, 53) + _copy(383)))
    stage = 1024 + 64 * r + 16 * s
    walk = 512 + 256 * g["literal_occurrences"]
    parent_raw = reach + scale + mix + average + stage + walk
    staged_payload = (r * (2 * (383 + 58) + 512) +
                      s * ((648 + 58) + (383 + 58)) +
                      64 * 19 * (704 + 58) + 16 * (5 + 58) + 4096)
    return {"rows": r, "slots": s, "chance_raw": chance,
            "state_reads": 2 * r, "history_reads": 80 * r,
            "history_walk": raw_history_per_board,
            "parent_raw": parent_raw, "entries_raw": 8 * r + 2 * s + 64 * 19 + 64,
            "payload_raw": staged_payload,
            "output_raw": 728 + 136 * (r + s)}


def session_forecast(first_board, first_law, second_board, second_law):
    """Forecast two selectors; repeated selectors are legal (sampling is with replacement)."""
    if first_law not in LAWS or second_law not in LAWS:
        raise ValueError("unsupported session proposal law")
    terms = [_board_terms(first_board), _board_terms(second_board)]
    (g, dense, _phases, _edges, _reveals, _folds, _showdowns, _decisions,
     catalog, read_cost, entries_base, payload_base, history_base, state_base,
     _raw_history_per_board) = _fixed()
    reads = ROWS + sum(x["state_reads"] for x in terms)
    state = state_base - read_cost * ROWS + read_cost * reads
    history = history_base + 40 * reads + sum(x["history_walk"] for x in terms)
    chance = 65_536 + sum(x["chance_raw"] for x in terms)
    parent = catalog + 1_024 + sum(x["parent_raw"] for x in terms)
    entries = entries_base + 512 + sum(x["entries_raw"] for x in terms)
    payload = payload_base + 4_096 + sum(x["payload_raw"] for x in terms)
    output = 136 + 1_442_112 + 208 + sum(x["output_raw"] for x in terms)
    # The 1.04M geometry reservation is inside the unchanged 3M catalog family.
    geometry_family = 1_040_000 + 149_420
    if geometry_family > 3_000_000:
        raise ArithmeticError("shared template/catalog geometry family exceeded")
    work = (43_000_000 + chance + history + state + 1 + parent +
            16 * INPUT_CAP + 16 * OUTPUT_CAP)
    return {"reads": reads, "state": state, "history": history,
            "chance": chance, "parent": parent, "work": work,
            "entries": entries, "payload": payload, "output": output,
            "boards": terms,
            "feasible": fits_caps({"work":work,"history":history,"state":state+1,
                "chance":chance,"parent":parent,"entries":entries,
                "payload":payload,"output":output})}


def fits_caps(metrics, caps=None):
    """Apply the fixed session ceilings, or stricter test-only ceilings."""
    limits = dict(CAPS)
    if caps is not None:
        if type(caps) is not dict or set(caps) - set(limits):
            raise ValueError("unknown session resource cap")
        for name, value in caps.items():
            if type(value) is not int or value <= 0 or value > limits[name]:
                raise ValueError("session caps are positive and reduce-only")
            limits[name] = value
    return all(type(metrics.get(name)) is int and metrics[name] <= limit
               for name, limit in limits.items())


def pairwise_maxima():
    """Exact axis maxima over ordered selector pairs, including replacement.

    Every axis is C + V(B1) + V(B2), so with replacement its exact maximum is
    C + 2*max(V). This proves the full ordered Cartesian product without
    materializing its roughly 25 million pairs.
    """
    candidates = [_board_terms(board) for board in boards()]
    (_g, dense, _phases, _edges, _reveals, _folds, _showdowns, _decisions,
     catalog, read_cost, entries_base, payload_base, history_base, state_base,
     raw_history) = _fixed()
    common = {
        "state": state_base - read_cost * ROWS + read_cost * ROWS,
        "history": history_base + 40 * ROWS,
        "chance": 65_536,
        "parent": catalog + 1_024,
        "entries": entries_base + 512,
        "payload": payload_base + 4_096,
        "output": 136 + 1_442_112 + 208,
        "work": 43_000_000 + (state_base) + (history_base + 40 * ROWS) +
            65_536 + 1 + catalog + 1_024 + 16 * INPUT_CAP + 16 * OUTPUT_CAP,
    }
    variables = {
        "state": lambda x: read_cost * x["state_reads"],
        "history": lambda x: 40 * x["state_reads"] + x["history_walk"],
        "chance": lambda x: x["chance_raw"],
        "parent": lambda x: x["parent_raw"],
        "entries": lambda x: x["entries_raw"],
        "payload": lambda x: x["payload_raw"],
        "output": lambda x: x["output_raw"],
        "stage_payload": lambda x: x["payload_raw"],
        "work": lambda x: (x["chance_raw"] + 40 * x["state_reads"] +
            x["history_walk"] + read_cost * x["state_reads"] + x["parent_raw"]),
    }
    maxima = {name: base + 2 * max(fn(x) for x in candidates)
              for name, (base, fn) in ((name, (common[name], variables[name])) for name in common)}
    maxima["stage_payload"] = 2 * max(x["payload_raw"] for x in candidates)
    maximizers = {name: candidates[max(range(len(candidates)), key=lambda i: fn(candidates[i]))]
                  for name, fn in variables.items()}
    # Session-level history's 40*R and State's common readback are already in C.
    return {"maximum": maxima, "maximizer_terms": maximizers,
            "boards_examined": len(candidates),
            "proposal_laws_per_board": len(LAWS), "ordered_pairs_proven":
                (len(candidates) * len(LAWS)) ** 2,
            "replacement_allowed": True,
            "scope": "rank-free two-board immutable-policy session forecast only"}
