"""Independent full-future-deck and numeric-rule replay for direct flop games.

Only card/range input grammar and the existing independent best-five ranker
are shared. No production tree, utility, trainer or best-response helper is
used as an oracle.
"""
from fractions import Fraction
from itertools import permutations
from math import fsum, isfinite
from pokerlab.cards import cards, expand_range
from scripts.preflop_validation import independent_rank


def _money(x):
    return round(float(x), 9)


def _token(name, target):
    if name not in ("bet", "raise", "all_in"):
        return name
    return name + "@" + format(target, ".9f").rstrip("0").rstrip(".")


def _validated_count_rows(count_rows, pairs):
    """Validate trusted ordered physical W/T/L rows against the requested support."""
    if type(count_rows) not in (list, tuple) or len(count_rows) != len(pairs):
        raise ValueError("Trusted oracle counts must cover every compatible pair in order")
    validated = []
    for row, (oop_hand, ip_hand, _) in zip(count_rows, pairs):
        if type(row) is not dict:
            raise ValueError("Trusted oracle count rows must be mappings")
        if (type(row.get("oop_hand")) is not str or type(row.get("ip_hand")) is not str
                or row["oop_hand"] != "".join(oop_hand)
                or row["ip_hand"] != "".join(ip_hand)):
            raise ValueError("Trusted oracle counts have wrong pair identity or order")
        values = tuple(row.get(key) for key in ("wins", "ties", "losses"))
        if (any(type(value) is not int or value < 0 for value in values)
                or type(row.get("ordered_outcomes")) is not int
                or row["ordered_outcomes"] != 1980
                or sum(values) != 1980):
            raise ValueError("Trusted ordered W/T/L counts must be nonnegative integers totaling 1,980")
        validated.append(values)
    return tuple(validated)


def prepare_oracle_from_counts(board, oop_range, ip_range, config, counts):
    """Build independent configured replay state from caller-trusted W/T/L rows.

    Counts must be independently sourced and in compatible-pair expansion
    order. This helper performs no physical ranking; joint priors are recomputed
    exactly from the requested represented input weights.
    """
    if type(counts) not in (list, tuple):
        raise ValueError("Trusted oracle counts must be an ordered list or tuple")
    return prepare_oracle(board, oop_range, ip_range, config,
                          _trusted_counts=counts)


def prepare_oracle(board, oop_range, ip_range, config, *, _trusted_counts=None):
    board = tuple(sorted(cards(board, 3), key=lambda c: ("23456789TJQKA".index(c[0]), "cdhs".index(c[1]))))
    ranges = [expand_range(r, board) for r in (oop_range, ip_range)]
    pairs = [(a, b, Fraction.from_float(x) * Fraction.from_float(y))
             for a, x in ranges[0].items() for b, y in ranges[1].items()
             if set(a).isdisjoint(b)]
    if not pairs:
        raise ValueError("No compatible oracle pairs")
    total = sum((w for _, _, w in pairs), Fraction())
    deals, reports = [], []
    if _trusted_counts is None:
        # Deliberately enumerate ordered future deals from an independently spelled
        # deck; cache only best-five ranks within the current pair, not its counts.
        for a, b, weight in pairs:
            dead = set(board + a + b)
            deck = [r+s for r in "23456789TJQKA" for s in "cdhs" if r+s not in dead]
            counts = {-1: 0, 0: 0, 1: 0}
            cache = {}
            for turn, river in permutations(deck, 2):
                final = tuple(sorted(board + (turn, river)))
                ranked = []
                for player, hand in enumerate((a, b)):
                    key = player, final
                    if key not in cache:
                        cache[key] = independent_rank(hand + final)
                    ranked.append(cache[key])
                counts[(ranked[0] > ranked[1]) - (ranked[0] < ranked[1])] += 1
            assert sum(counts.values()) == 1980
            prior = weight / total
            name_a, name_b = "".join(a), "".join(b)
            deals.append((name_a, name_b, float(prior), (counts[1] - counts[-1]) / 1980))
            reports.append({"oop_hand": name_a, "ip_hand": name_b, "wins": counts[1],
                            "ties": counts[0], "losses": counts[-1], "ordered_outcomes": 1980,
                            "pair_probability": float(prior)})
    else:
        validated = _validated_count_rows(_trusted_counts, pairs)
        for (a, b, weight), (wins, ties, losses) in zip(pairs, validated):
            prior = weight / total
            name_a, name_b = "".join(a), "".join(b)
            deals.append((name_a, name_b, float(prior), (wins - losses) / 1980))
            reports.append({"oop_hand": name_a, "ip_hand": name_b, "wins": wins,
                            "ties": ties, "losses": losses, "ordered_outcomes": 1980,
                            "pair_probability": float(prior)})
    pot = float(config["pot"])
    raw_stacks = config["effective_stack"]
    stacks = tuple(map(float, raw_stacks)) if isinstance(raw_stacks, (tuple, list)) else (float(raw_stacks),)*2
    nodes, states = {}, [0]

    def build(player=0, committed=(0.0, 0.0), history=(), checks=0,
              previous_raise=0.0, raises=0, reopened=True):
        states[0] += 1
        if committed[player] >= stacks[player] - 1e-9:
            return ("terminal", "showdown", committed, None)
        other = 1-player
        own, theirs = committed[player], committed[other]
        if abs(own-theirs) <= 1e-9:
            options = [("check", 0.0, 0.0, False)]
            requests = [("bet", own + float(f) * (pot+sum(committed))) for f in config["bet_sizes"]]
            if config["include_all_in"]:
                requests.append(("all_in", stacks[player]))
        else:
            call = _money(min(theirs-own, stacks[player]-own))
            options = [("fold", 0.0, 0.0, False), ("call", call, _money(own+call), False)]
            requests = []
            if reopened and raises < config["max_raises"] and theirs < stacks[other]-1e-9:
                for f in config["raise_sizes"]:
                    target = theirs + float(f) * (pot+sum(committed)+theirs-own)
                    if target < theirs+previous_raise:
                        target = theirs+previous_raise
                    requests.append(("raise", target))
                if config["include_all_in"]:
                    requests.append(("all_in", stacks[player]))
        sized = []
        for name, requested in requests:
            target = _money(min(stacks[player], max(own, requested)))
            if target <= own+1e-9 or (abs(own-theirs)>1e-9 and target <= theirs+1e-9):
                continue
            full = target-theirs+1e-9 >= previous_raise
            if abs(own-theirs)>1e-9 and target < theirs+previous_raise-1e-9 and target < stacks[player]-1e-9:
                continue
            if target >= stacks[player]-1e-9:
                name = "all_in"
            if any(abs(a[2]-target)<=1e-9 for a in sized):
                continue
            sized.append((name, _money(target-own), target, full))
        options += sorted(sized, key=lambda x:x[2])
        children = []
        for name, amount, target, full in options:
            h = history + (_token(name,target),)
            c = list(committed)
            if name == "fold":
                states[0] += 1
                child = ("terminal", "fold", committed, other)
            elif name == "check" and checks == 1:
                states[0] += 1
                child = ("terminal", "showdown", committed, None)
            elif name == "call":
                c[player] = target
                states[0] += 1
                child = ("terminal", "showdown", tuple(c), None)
            elif name == "check":
                child = build(other, committed, h, checks+1, previous_raise, raises, reopened)
            else:
                c[player] = target
                opening = abs(own-theirs)<=1e-9
                increment = amount if opening else target-theirs
                child = build(other, tuple(c), h, 0,
                              increment if opening or full else previous_raise,
                              0 if opening else raises+int(full), True if opening else full)
            children.append(child)
        node = ("decision", player, history, options, children)
        nodes[(player,history)] = node
        return node
    root = build()
    return {"board": tuple(board), "deals": deals, "counts": reports, "root": root,
            "nodes": nodes, "public_states": states[0], "pot": pot}


def replay(result, oracle, tolerance=1e-10):
    rows = {}
    active = [{w[p] for w in oracle["deals"]} for p in (0,1)]
    for row in result["strategy"]:
        player = {"oop":0,"ip":1}[row["player"]]
        key = player, row["hand"], tuple(row["history"])
        assert key not in rows, "Duplicate policy row"
        assert row["street"] == "flop" and tuple(row["board"]) == oracle["board"]
        assert row["hand"] in active[player], "Inactive hand policy"
        node = oracle["nodes"][(player,key[2])]
        assert len(row["actions"]) == len(node[3])
        probabilities = []
        for a, expected in zip(row["actions"],node[3]):
            name, amount, target, _ = expected
            assert (a["name"],a["amount"],a["raise_to"],a["history_key"]) == (name,amount,target,_token(name,target)), "Action differs from numeric rules"
            p=float(a["probability"])
            assert isfinite(p) and 0 <= p <= 1
            probabilities.append(p)
        assert abs(fsum(probabilities)-1) <= 1e-9
        rows[key] = probabilities
    expected = {(p,h,history) for p,history in oracle["nodes"] for h in active[p]}
    assert set(rows)==expected, "Missing or unexpected information sets"
    assert result["info_sets"]==len(expected)
    assert result["public_nodes"]==len(oracle["nodes"])
    assert result["public_states"]==oracle["public_states"]
    assert result["physical_worlds"]==1980*len(oracle["deals"])
    assert len(result["pair_equities"])==len(oracle["counts"])
    for actual, wanted in zip(result["pair_equities"],oracle["counts"]):
        for k in ("oop_hand","ip_hand","wins","ties","losses","ordered_outcomes"):
            assert actual[k]==wanted[k], "Chance count mismatch"
        assert abs(actual["pair_probability"]-wanted["pair_probability"])<=1e-12
    def payoff(node, deal):
        unit = oracle["pot"]/2 + min(node[2])
        return unit*((1 if node[3]==0 else -1) if node[1]=="fold" else deal[3])
    def profile(node, deal):
        if node[0]=="terminal":
            return payoff(node,deal)
        player,history,_,children=node[1:]
        return fsum(p*profile(c,deal) for p,c in zip(rows[(player,deal[player],history)],children))
    value=fsum(w[2]*profile(oracle["root"],w) for w in oracle["deals"])
    def best(player):
        def visit(node, deals):
            if node[0]=="terminal":
                return fsum(w[2]*(1 if player==0 else -1)*payoff(node,w) for w in deals)
            owner,history,options,children=node[1:]
            if owner==player:
                return max(visit(c,deals) for c in children)
            return fsum(visit(c,[(w[0],w[1],w[2]*rows[(owner,w[owner],history)][a],w[3]) for w in deals]) for a,c in enumerate(children))
        return fsum(visit(oracle["root"],[w for w in oracle["deals"] if w[player]==h]) for h in sorted(active[player]))
    br0,br1=best(0),best(1)
    gap=max(0.0,br0+br1)
    metrics={"value_oop":value,"value_ip":-value,"oop_best_response_value":br0,
             "ip_best_response_value":br1,"nash_conv":gap,"exploitability":gap/2}
    deltas={k:abs(result[k]-v) for k,v in metrics.items()}
    assert all(isfinite(v) and v<=tolerance for v in deltas.values()), deltas
    return {**metrics,"scalar_absolute_gaps":deltas,"checked_information_sets":len(rows),
            "checked_physical_worlds":result["physical_worlds"]}
