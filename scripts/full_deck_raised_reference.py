"""Independent pretraining physical/tree reference for one full-deck raised game.

No production tree, solver, trainer, or candidate census is imported. The numeric
rules and exhaustive best-five reference are existing development oracles.
"""
from collections import defaultdict
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import subprocess

from scripts.historical_foundation_sources import compatible_historical_reference_sources, operation_fingerprints
from scripts import turn_river_validation as rules
from scripts.verify_turn_blocker_sequence import rank as best_five_rank

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "benchmarks/results/full-deck-raised-turn-reference-v1.json"
MAX_REPORT_BYTES = 200_000
FIXTURE = {
    "id": "full-deck-raised-turn-v1", "board": "Js8d4c2h",
    "oop": "AsAh:0.5,KsKh:1", "ip": "AcAd:1,KcKd:0.75",
    "config": {"pot": 100.0, "effective_stack": 220.0, "bet_sizes": [0.5],
               "raise_sizes": [0.5], "max_raises": 1, "include_all_in": False},
}
EXPECTED_PAIRS = {
    ("AhAs", "AcAd"): (F(4, 21), (0, 44, 0)),
    ("AhAs", "KcKd"): (F(1, 7), (42, 0, 2)),
    ("KhKs", "AcAd"): (F(8, 21), (2, 0, 42)),
    ("KhKs", "KcKd"): (F(2, 7), (0, 44, 0)),
}
METRICS = ("value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
           "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability")
SOURCE_PATHS = (
    "pokerlab/cards.py", "scripts/turn_river_validation.py",
    "scripts/preflop_validation.py", "scripts/verify_turn_blocker_sequence.py",
    "scripts/turn_blocker_sequence_fixture.py", "scripts/full_deck_raised_reference.py",
    "tests/test_full_deck_raised_reference.py",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def structure(node):
    if isinstance(node, rules._Terminal):
        return ["terminal", node.kind, node.winner, list(node.contributions)]
    if isinstance(node, rules._Chance):
        return ["chance", list(node.history), [[r, structure(c)] for r, c in sorted(node.branches.items())]]
    require(isinstance(node, rules._Decision), "Unknown independent node")
    return ["decision", node.player, list(node.history), list(node.board),
            [[a.name, a.token, a.amount, a.raise_to, structure(c)]
             for a, c in zip(node.actions, node.children)]]


def model():
    f = deepcopy(FIXTURE)
    board = rules.cards(f["board"])
    config = rules._config(f["config"], "config")
    worlds, selected = rules._worlds(board, tuple(rules.expand_range(f[p], board)
                                                for p in ("oop", "ip")), None)
    require(len(worlds) == 176 and len(selected) == 48, "Full physical support differs")
    require(sum((w["weight"] for w in worlds), F(0)) == 1, "Global physical mass differs")
    pairs = defaultdict(list)
    for world in worlds:
        pair = tuple("".join(h) for h in world["hands"])
        pairs[pair].append(world)
    require(set(pairs) == set(EXPECTED_PAIRS), "Ordered private pair support differs")
    pair_rows = []
    for pair in sorted(pairs):
        group = pairs[pair]
        mass, counts = EXPECTED_PAIRS[pair]
        dead = set(board) | set(group[0]["hands"][0]) | set(group[0]["hands"][1])
        expected_rivers = set(rules.DECK) - dead
        require(len(expected_rivers) == 44 and len(group) == 44
                and {w["river"] for w in group} == expected_rivers, "Per-pair full deck differs")
        require(all(w["weight"] == mass / 44 for w in group), "Exact physical world weights differ")
        for world in group:
            a, b = (best_five_rank(world["board"] + hand) for hand in world["hands"])
            require((a > b) - (a < b) == world["sign"], "Independent best-five sign mismatch")
        actual = tuple(sum(w["sign"] == sign for w in group) for sign in (1, 0, -1))
        require(actual == counts, "Literal physical showdown law differs")
        pair_rows.append(dict(oop=pair[0], ip=pair[1], mass_fraction=str(mass),
                              world_mass_fraction=str(mass / 44), rivers=44,
                              wins=actual[0], ties=actual[1], losses=actual[2]))
    root = rules._public_tree(board, config, config, selected, worlds)
    return f, board, config, worlds, selected, root, pair_rows


def _walk(root):
    pending = [(root, 1)]
    total = deepest = 0
    decisions = []
    while pending:
        node, depth = pending.pop()
        total += 1
        deepest = max(deepest, depth)
        require(total <= 3039 and depth <= 9, "Fixed public tree exceeded census")
        if isinstance(node, rules._Decision):
            decisions.append(node)
            pending.extend((c, depth + 1) for c in node.children)
        elif isinstance(node, rules._Chance):
            pending.extend((c, depth + 1) for c in node.branches.values())
        else:
            require(isinstance(node, rules._Terminal), "Unknown independent terminal")
    require((total, len(decisions), deepest) == (3039, 1254, 9), "Independent public census differs")
    return decisions


def _policy_rows(decisions, worlds):
    rows = {}
    for node in decisions:
        choices = {a.name: i for i, a in enumerate(node.actions)}
        chosen = choices["check"] if "check" in choices else choices["call"]
        for world in worlds:
            if world["board"][:len(node.board)] != node.board:
                continue
            hand = "".join(world["hands"][node.player])
            rows[node.player, hand, node.history] = {
                "player": ("oop", "ip")[node.player], "hand": hand,
                "street": "turn" if len(node.board) == 4 else "river",
                "board": list(node.board), "history": list(node.history),
                "actions": [dict(name=a.name, history_key=a.token, amount=a.amount,
                                 raise_to=a.raise_to, probability=float(i == chosen))
                            for i, a in enumerate(node.actions)],
            }
    require(len(rows) == 2404, "Independent information-set census differs")
    return [rows[k] for k in sorted(rows)]


def check_call_response_bounds(worlds):
    """Closed-form legal responses to the particular always-check/call policy.

    The fixed opponent never bets or raises. A response can invest t=0 or50 on
    the turn, then b=0 or(50+t) on the river, after seeing that river. Stakes
    remain below220. For each own hand and visible river, aggregate the signed
    physical mass BEFORE choosing b; integrate every river BEFORE choosing t.
    This specialized identity is not an auditor for arbitrary trained policies.
    """
    require(len(worlds) == 176, "Fixed response formula requires176 worlds")
    bounds = []
    for player in (0, 1):
        signed = defaultdict(lambda: defaultdict(F))
        for world in worlds:
            signed[world["hands"][player]][world["river"]] += world["weight"] * world["sign"]
        require(len(signed) == 2, "Fixed response formula requires two own hands")
        choose = max if player == 0 else min
        response = F(0)
        for by_river in signed.values():
            # River wager is0 or50+t; terminal payoff is sign*(50+t+b).
            coefficient = sum((s + choose(F(0), s) for s in by_river.values()), F(0))
            response += choose(50 * coefficient, 100 * coefficient)
        bounds.append(response)
    return bounds[0], -bounds[1]


def reconstruct():
    f, board, config, worlds, selected, root, pair_rows = model()
    decisions = _walk(root)
    rows = _policy_rows(decisions, worlds)
    checkdown = sum((w["weight"] * w["sign"] * F(50) for w in worlds), F(0))
    require(checkdown == F(-2500, 231), "Literal all-check policy value differs")
    result = dict(board=list(board), runouts=list(selected), runout_mode="full-deck",
                  reachable_runouts=sorted({w["river"] for w in worlds}), strategy=rows,
                  info_sets=len(rows), compatible_world_count=len(worlds), compatible_pairs=4,
                  config=config.to_dict(), river_config=config.to_dict())
    oracle = rules.replay_policy(result, f["oop"], f["ip"], board=f["board"], config=f["config"])
    require(abs(oracle["value_oop"] - float(checkdown)) < 1e-12, "All-check numeric replay differs")
    br_oop, br_ip = check_call_response_bounds(worlds)
    require(br_oop == F(2350, 231) and br_ip == F(14975, 231), "Closed-form own-hand response anchor differs")
    exact = dict(value_oop=checkdown, value_ip=-checkdown,
                 oop_best_response_value=br_oop, ip_best_response_value=br_ip,
                 oop_best_response_gain=br_oop-checkdown, ip_best_response_gain=br_ip+checkdown,
                 nash_conv=br_oop+br_ip, exploitability=(br_oop+br_ip)/2)
    require(all(abs(float(v)-oracle[k]) < 1e-12 for k, v in exact.items()),
            "Closed-form responses disagree with independent numeric tree")
    tokens = sorted({a.token for n in decisions for a in n.actions})
    require("raise@150" in tokens and "all_in@220" in tokens, "Required raise/capped action missing")
    # Cumulative turn investment must be carried into the river call and payout.
    history = ("bet@50", "raise@150", "call", "river@2c")
    node = next(n for n in decisions if n.history == history)
    action = next(a for a in node.actions if a.token == "all_in@220")
    require(action.amount == 70 and action.raise_to == 220, "Turn contribution was lost on river")
    call_node = node.children[node.actions.index(action)]
    call_index = next(i for i, a in enumerate(call_node.actions) if a.name == "call")
    terminal = call_node.children[call_index]
    require(isinstance(terminal, rules._Terminal) and terminal.kind == "showdown"
            and terminal.contributions == (220.0, 220.0), "Cumulative showdown contributions differ")
    shape = json.dumps(structure(root), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return dict(kind="PRETRAINING_FULL_DECK_RAISED_TURN_REFERENCE", training_calls=0,
                fixture=f, worlds=176, compatible_pairs=4, rivers_per_pair=44,
                public_candidates=48, reachable_rivers=48, public_nodes=3039,
                public_decisions=1254, information_rows=2404, depth=9,
                physical_pairs=pair_rows, global_mass_fraction="1",
                best_five_checked_worlds=176, all_check_policy_value_fraction=str(checkdown),
                all_check_call_exact_metrics={k: str(v) for k, v in exact.items()},
                all_check_float_replay={k: oracle[k] for k in METRICS},
                action_tokens=tokens, public_tree_sha256=sha256(shape).hexdigest(),
                carried_raise_witness=dict(history=list(history), river_wager=70,
                    cumulative_target=220, matched_showdown_contributions=[220, 220],
                    winning_oop_terminal_value_fraction="270"),
                scope="One fixed full-deck configured turn/river game; no equilibrium value or trained-policy certificate.")


def fingerprints():
    return {p: sha256((ROOT / p).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for p in SOURCE_PATHS}


def head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def verify_saved_artifact(path=REPORT):
    path = Path(path)
    require(path.stat().st_size <= MAX_REPORT_BYTES, "Reference report exceeds byte cap")
    raw = path.read_bytes()
    require(len(raw) <= MAX_REPORT_BYTES, "Reference report grew beyond byte cap")
    before, before_head = fingerprints(), head()
    operation_before = operation_fingerprints(SOURCE_PATHS)
    report = json.loads(raw)
    require(set(report) == {"schema_version", "baseline_git_commit", "source_sha256", "reference"}
            and type(report["schema_version"]) is int and report["schema_version"] == 1,
            "Unsupported reference envelope")
    baseline = report["baseline_git_commit"]
    require(type(baseline) is str and len(baseline) == 40
            and all(c in "0123456789abcdef" for c in baseline), "Invalid historical generation commit")
    require(compatible_historical_reference_sources(report["source_sha256"], before, SOURCE_PATHS),
            "Current reference sources differ")
    expected = reconstruct()
    saved = deepcopy(report["reference"])
    require(type(saved) is dict and set(saved) == set(expected), "Reference field set differs")
    observed = saved.pop("all_check_float_replay")
    projected = expected.pop("all_check_float_replay")
    require(type(observed) is dict and set(observed) == set(METRICS)
            and all(type(observed[k]) is float and isfinite(observed[k])
                    and abs(observed[k] - projected[k]) <= 1e-12 for k in METRICS),
            "All-check float reference differs beyond1e-12")
    require(canonical(saved) == canonical(expected), "Independent full-deck reference differs")
    require(fingerprints() == before and operation_fingerprints(SOURCE_PATHS) == operation_before
            and head() == before_head and path.read_bytes() == raw,
            "Source, HEAD or accepted reference changed during replay")
    return report


def generate():
    before, before_head = fingerprints(), head()
    report = dict(schema_version=1, baseline_git_commit=before_head,
                  source_sha256=before, reference=reconstruct())
    raw = canonical(report)
    require(len(raw) <= MAX_REPORT_BYTES and fingerprints() == before and head() == before_head,
            "Generation source/HEAD/size guard failed")
    created = False
    if REPORT.exists():
        require(REPORT.read_bytes() == raw, "Refusing to replace differing frozen reference")
    else:
        # Exclusive creation cannot overwrite a previously accepted reference.
        stream = REPORT.open("xb")
        created = True
        try:
            with stream:
                stream.write(raw)
        except BaseException:
            REPORT.unlink(missing_ok=True)
            raise
    try:
        verify_saved_artifact()
    except BaseException:
        if created:
            REPORT.unlink(missing_ok=True)
        raise
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    report = verify_saved_artifact() if args.verify else generate()
    print(json.dumps(dict(status="FULL_DECK_RAISED_PRETRAINING_REFERENCE_VERIFIED",
                          training_calls=0, worlds=report["reference"]["worlds"])))
