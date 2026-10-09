"""Independent physical-world and numeric-state replay of serialized policies.

No production tree, hand ranker, utility, CFR, evaluation or best-response helper
is an oracle here. Only the established card/range input grammar is shared.
The replay supports the bounded action abstraction, not unrestricted NLHE.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import combinations
from math import comb, fsum, isfinite

from pokerlab.cards import cards, expand_range


def _q(value):
    return Fraction(str(round(float(value), 9)))


def _five_rank(hand):
    ranks = sorted(("23456789TJQKA".index(card[0]) + 2 for card in hand), reverse=True)
    counts = Counter(ranks)
    groups = sorted(((count, rank) for rank, count in counts.items()), reverse=True)
    flush = len({card[1] for card in hand}) == 1
    unique = sorted(counts)
    straight = (5 if unique == [2, 3, 4, 5, 14] else
                unique[-1] if len(unique) == 5 and unique[-1] - unique[0] == 4 else 0)
    if flush and straight:
        return 8, straight
    if groups[0][0] == 4:
        return 7, groups[0][1], groups[1][1]
    if [count for count, _ in groups] == [3, 2]:
        return 6, groups[0][1], groups[1][1]
    if flush:
        return (5, *ranks)
    if straight:
        return 4, straight
    if groups[0][0] == 3:
        return (3, groups[0][1], *sorted((rank for count, rank in groups if count == 1), reverse=True))
    pairs = sorted((rank for count, rank in groups if count == 2), reverse=True)
    singles = sorted((rank for count, rank in groups if count == 1), reverse=True)
    if len(pairs) == 2:
        return (2, *pairs, *singles)
    if pairs:
        return (1, *pairs, *singles)
    return (0, *ranks)


def independent_rank(hand):
    """Enumerate all best-five candidates instead of the production rank path."""
    return max(_five_rank(five) for five in combinations(hand, 5))


def physical_worlds(sb_range, bb_range, runouts):
    """Construct one jointly conditioned distribution, including blocker shifts."""
    ranges = [expand_range(expression) for expression in (sb_range, bb_range)]
    outcomes = []
    for raw in runouts:
        board = cards(raw, 5)
        outcome = tuple(sorted(board[:3], key=lambda card: ("23456789TJQKA".index(card[0]), "cdhs".index(card[1])))) + board[3:]
        if outcome in outcomes:
            raise ValueError("Duplicate physical outcome")
        outcomes.append(outcome)
    denominator = comb(48, 3) * 45 * 44
    pending = []
    rank_cache = {}
    for sb, sb_weight in sorted(ranges[0].items()):
        for bb, bb_weight in sorted(ranges[1].items()):
            if set(sb) & set(bb) or not sb_weight or not bb_weight:
                continue
            for board in outcomes:
                if (set(sb) | set(bb)) & set(board):
                    continue
                ranks = []
                for hand in (sb, bb):
                    key = tuple(sorted(hand + board))
                    if key not in rank_cache:
                        rank_cache[key] = independent_rank(key)
                    ranks.append(rank_cache[key])
                sign = (ranks[0] > ranks[1]) - (ranks[0] < ranks[1])
                pending.append(("".join(sb), "".join(bb),
                                sb_weight * bb_weight / denominator, sign, board))
    normalizer = fsum(world[2] for world in pending)
    if normalizer <= 0:
        raise ValueError("No compatible worlds")
    return [(sb, bb, mass / normalizer, sign, board)
            for sb, bb, mass, sign, board in pending]


@dataclass(frozen=True)
class _State:
    street: int
    player: int
    committed: tuple
    history: tuple = ()
    board: tuple = ()
    increment: Fraction = Fraction(0)
    raises: int = 0
    reopened: bool = True
    checks: int = 0


def _token(name, target):
    if name not in ("bet", "raise", "all_in"):
        return name
    return name + "@" + format(float(target), ".9f").rstrip("0").rstrip(".")


def replay_policy(result, sb_range, bb_range, *, config, runouts,
                  flop_config=None, turn_config=None, river_config=None):
    """Rebuild states from rules and integrate a policy and both legal exact BRs.

    A responder maximizes only after its own hand and revealed public history
    are known. Opponent hands and unrevealed cards remain grouped. Every
    reachable serialized row is checked against independently derived actions.
    """
    config = config.to_dict() if hasattr(config, "to_dict") else dict(config)
    raw_stacks = config.get("starting_stack", 100)
    stacks = tuple(map(_q, raw_stacks)) if isinstance(raw_stacks, (list, tuple)) else (_q(raw_stacks),) * 2
    sb_blind, bb_blind = _q(config.get("small_blind", .5)), _q(config.get("big_blind", 1))
    defaults = {"bet_sizes": [.5], "raise_sizes": [], "max_raises": 0, "include_all_in": True}
    flop = defaults | (flop_config or {})
    stages = {0: config, 3: flop, 4: flop | (turn_config or {}), 5: flop | (river_config or {})}
    worlds = physical_worlds(sb_range, bb_range, runouts)
    rows = {}
    for row in result["strategy"]:
        key = (row["player"], row["hand"], tuple(row["history"]))
        assert key not in rows, "Duplicate serialized information set"
        rows[key] = row
    checked = set()

    def actions(state):
        player, other = state.player, 1 - state.player
        own, theirs = state.committed[player], state.committed[other]
        owed = max(Fraction(0), theirs - own)
        candidates = [("fold", Fraction(0), Fraction(0), False),
                      ("call", min(owed, stacks[player] - own), min(theirs, stacks[player]), False)] if owed else [
                      ("check", Fraction(0), Fraction(0), False)]
        options = stages[state.street]
        targets = {}
        if state.street and not owed:
            for fraction in options["bet_sizes"]:
                target = _q(min(stacks[player], own + _q(fraction) * sum(state.committed)))
                if target > own:
                    targets[target] = ("bet", False)
            if options["include_all_in"] and stacks[player] > own:
                targets.setdefault(stacks[player], ("all_in", False))
        elif (state.reopened and state.raises < options.get("max_raises", 3)
              and theirs < stacks[other]):
            for fraction in options.get("raise_sizes", [1]):
                target = _q(min(stacks[player], max(theirs + state.increment,
                             theirs + _q(fraction) * 2 * theirs)))
                if target > theirs:
                    targets.setdefault(target, ("raise", target - theirs >= state.increment))
            if options.get("include_all_in", True) and stacks[player] > theirs:
                targets.setdefault(stacks[player], ("all_in", stacks[player] - theirs >= state.increment))
        for target, (name, full) in sorted(targets.items()):
            if target == stacks[player]:
                name = "all_in"
            candidates.append((name, target - own, target, full))
        return candidates

    def policy(state, hand, expected):
        key = (("sb", "bb")[state.player], hand, state.history)
        assert key in rows, f"Missing information set: {key}"
        row = rows[key]
        actual = row["actions"]
        if key not in checked:
            assert row["street"] == {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[state.street]
            assert tuple(row["revealed_board"]) == state.board, "Future/private-card leak"
            assert len(actual) == len(expected), (key, actual, expected)
            for item, (name, amount, target, _) in zip(actual, expected):
                assert item["name"] == name, (key, item, name)
                assert abs(item["amount"] - float(amount)) < 1e-8, (key, item, amount)
                assert abs(item["raise_to"] - float(target)) < 1e-8, (key, item, target)
                assert item["history_key"] == _token(name, target)
            probs = [item["probability"] for item in actual]
            assert all(isfinite(value) and value >= 0 for value in probs)
            assert abs(fsum(probs) - 1) < 1e-10
            checked.add(key)
        return [item["probability"] for item in actual]

    def terminal(group, state, winner=None):
        matched = float(min(state.committed))
        return fsum(world[2] * matched * (world[3] if winner is None else (1 if winner == 0 else -1))
                    for world in group)

    def settled(group, state, responder):
        matched = min(state.committed)
        state = replace(state, committed=(matched, matched))
        if state.street == 5 or any(matched >= stack for stack in stacks):
            return terminal(group, state)
        next_street = {0: 3, 3: 4, 4: 5}[state.street]
        partitions = defaultdict(list)
        for world in group:
            partitions[world[4][:next_street]].append(world)
        values = []
        for board, subset in sorted(partitions.items()):
            reveal = ("flop@" + "".join(board) if next_street == 3 else
                      ("turn@" if next_street == 4 else "river@") + board[-1])
            fresh = _State(next_street, 1, state.committed, state.history + (reveal,), board)
            values.append(visit(subset, fresh, responder))
        return fsum(values)

    def child(group, state, action, responder):
        name, amount, target, full = action
        player, other = state.player, 1 - state.player
        next_state = replace(state, history=state.history + (_token(name, target),))
        if name == "fold":
            return terminal(group, state, other)
        if name == "call":
            committed = list(state.committed)
            committed[player] += amount
            next_state = replace(next_state, committed=tuple(committed))
            if (state.street == 0 and not state.history and
                    committed[0] == committed[1] and
                    all(value < stack for value, stack in zip(committed, stacks))):
                return visit(group, replace(next_state, player=1), responder)
            return settled(group, next_state, responder)
        if name == "check":
            if state.street == 0 or state.checks == 1:
                return settled(group, next_state, responder)
            return visit(group, replace(next_state, player=other, checks=1), responder)
        committed = list(state.committed)
        committed[player] = target
        opening = bool(state.street and state.committed[0] == state.committed[1])
        increment = amount if opening else (target - state.committed[other] if full else state.increment)
        return visit(group, replace(next_state, player=other, committed=tuple(committed),
                                   increment=increment, raises=0 if opening else state.raises + 1,
                                   reopened=True if opening else full, checks=0), responder)

    def visit(group, state, responder):
        expected = actions(state)
        probabilities = {hand: policy(state, hand, expected) for hand in {world[state.player] for world in group}}
        if responder == state.player:
            # The root call has already separated the responder's own hand.
            assert len({world[responder] for world in group}) == 1
            values = [child(group, state, action, responder) for action in expected]
            return (max if responder == 0 else min)(values)
        values = []
        for index, action in enumerate(expected):
            weighted = [(sb, bb, mass * probabilities[(sb, bb)[state.player]][index], sign, board)
                        for sb, bb, mass, sign, board in group]
            # Keep zero-mass worlds to audit structurally legal off-policy rows.
            values.append(child(weighted, state, action, responder))
        return fsum(values)

    posted = tuple(min(blind, stack) for blind, stack in zip((sb_blind, bb_blind), stacks))
    initial = _State(0, 0, posted, increment=bb_blind)
    forced = any(posted[player] == stacks[player] and posted[1 - player] >= posted[player] for player in range(2))
    if forced:
        value = terminal(worlds, initial)
        br_sb, br_bb = value, -value
    else:
        value = visit(worlds, initial, None)
        br = []
        for player in (0, 1):
            groups = defaultdict(list)
            for world in worlds:
                groups[world[player]].append(world)
            best = fsum(visit(group, initial, player) for group in groups.values())
            br.append(best if player == 0 else -best)
        br_sb, br_bb = br
    assert checked == set(rows), f"Unreachable information sets: {set(rows) - checked}"
    pair_probabilities = defaultdict(float)
    for sb, bb, mass, _, _ in worlds:
        pair_probabilities[(sb, bb)] += mass
    return {"value_sb": value, "value_bb": -value,
            "sb_best_response_value": br_sb, "bb_best_response_value": br_bb,
            "nash_conv": max(0.0, br_sb + br_bb), "worlds": len(worlds),
            "checked_information_sets": len(checked),
            "private_pair_probabilities": [{"sb": sb, "bb": bb, "probability": mass}
                                            for (sb, bb), mass in sorted(pair_probabilities.items())]}


def compare_result(result, oracle, tolerance=1e-10):
    """Reject candidate metrics that disagree with independent legal replay."""
    fields = ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value", "nash_conv")
    gaps = {field: abs(result[field] - oracle[field]) for field in fields}
    assert max(gaps.values()) <= tolerance, gaps
    assert result["worlds"] == oracle["worlds"]
    return gaps
