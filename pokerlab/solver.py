"""Full-traversal CFR for a precisely defined heads-up river game.

Both players have weighted private ranges. OOP checks or bets one fixed size;
after a check IP checks or bets that size. Responses are fold/call. No raises.
All compatible hole-card pairs are enumerated; utilities are zero sum,
measured relative to half of the existing pot. The strategy gap is evaluated
by exact information-set best responses, not by looking at hidden cards.
"""
from .cards import cards, expand_range, rank_hand
from .analysis import number


def strategy(regret):
    positive = [max(0, r) for r in regret]
    mass = sum(positive)
    return [r/mass for r in positive] if mass else [.5, .5]


def terminal_utilities(pot, bet, sign):
    """OOP utility at every terminal line; IP receives the exact negative.

    ``sign`` is +1 when OOP wins at showdown, -1 when IP wins and 0 on a tie.
    Utilities are chips relative to half of the existing pot, so a fold or
    showdown that nets nothing from a side bet is worth +/- pot/2.
    """
    half = pot/2
    return {"check_check": sign*half, "bet_fold": half, "bet_call": sign*(half+bet),
            "check_bet_fold": -half, "check_bet_call": sign*(half+bet)}


def _node_locks(lock, h1):
    """Validate public lock input and map hand names to IP information sets.

    A scalar retains the legacy uniform lock.  A mapping locks only the named
    private hands, which lets an upstream model adjust a behavioral segment
    without pretending that an aggregate statistic reveals every hidden hand.
    """
    lock = lock or {}
    if set(lock) - {"ip_bet", "ip_call"}:
        raise ValueError("Available node locks are ip_bet and ip_call.")
    hand_indexes = {"".join(hand): index for index, hand in enumerate(h1)}
    nodes, report = {}, {}
    for public_name, value in lock.items():
        node = "b" if public_name == "ip_bet" else "c"
        if isinstance(value, dict):
            unknown = set(value) - set(hand_indexes)
            if unknown:
                raise ValueError(f"Node lock contains hands outside the IP range: {sorted(unknown)}")
            nodes[node] = {hand_indexes[hand]: number(frequency, public_name, 0, 1)
                           for hand, frequency in value.items()}
            report[public_name] = {hand: nodes[node][hand_indexes[hand]]
                                   for hand in sorted(value)}
        else:
            frequency = number(value, public_name, 0, 1)
            nodes[node] = {index: frequency for index in range(len(h1))}
            report[public_name] = frequency
    return nodes, report


def solve(board, oop_range, ip_range, pot=100, bet=50, iterations=1000, lock=None,
          *, algorithm="vanilla"):
    """Solve the restricted river game; DCFR is an opt-in algorithm variant.

    DCFR uses Brown-Sandholm (2019) parameters (1.5, 0, 2): add the
    iteration's regret delta, then discount the resulting sign-split total.
    Direct t**2 average weights are equivalent to discounting the average
    accumulator by (t/(t+1))**2 after adding each iteration's contribution.
    """
    if algorithm not in ("vanilla", "dcfr"):
        raise ValueError("Solver algorithm must be vanilla or dcfr.")
    board = cards(board, 5)
    pot, bet = number(pot, "Pot", .01), number(bet, "Bet", .01)
    if type(iterations) is not int or not 10 <= iterations <= 10000:
        raise ValueError("Use 10–10,000 solver iterations.")
    r0, r1 = expand_range(oop_range, board), expand_range(ip_range, board)
    if len(r0)*len(r1)*iterations > 3_000_000:
        raise ValueError("This exact solver allows 3 million hand-pair iterations. Narrow ranges or reduce iterations.")
    h0, h1 = list(r0), list(r1)
    ranks0 = [rank_hand(h+board) for h in h0]
    ranks1 = [rank_hand(h+board) for h in h1]
    deals = [(i, j, r0[a]*r1[b], (ranks0[i] > ranks1[j])-(ranks0[i] < ranks1[j]))
             for i, a in enumerate(h0) for j, b in enumerate(h1) if not set(a).intersection(b)]
    mass = sum(d[2] for d in deals)
    if not mass:
        raise ValueError("Ranges contain no compatible pair of hands.")
    deals = [(i, j, w/mass, sign) for i, j, w, sign in deals]
    # a: OOP opening, d: OOP responding; b: IP after check, c: IP responding.
    sizes = {"a": len(h0), "d": len(h0), "b": len(h1), "c": len(h1)}
    regrets = {k: [[0., 0.] for _ in range(n)] for k, n in sizes.items()}
    sums = {k: [[0., 0.] for _ in range(n)] for k, n in sizes.items()}
    locks, lock_report = _node_locks(lock, h1)
    utilities = {sign: terminal_utilities(pot, bet, sign) for sign in (-1, 0, 1)}
    # Chance marginals are constant per private hand. Hoist strategy averaging
    # out of the deal loop; only OOP's response includes a prior own action.
    marginal0, marginal1 = [0.] * len(h0), [0.] * len(h1)
    for i, j, w, _ in deals:
        marginal0[i] += w
        marginal1[j] += w
    for iteration in range(1, iterations + 1):
        s = {k: [[1-locks[k][i], locks[k][i]] if k in locks and i in locks[k]
                 else strategy(r) for i, r in enumerate(rows)]
             for k, rows in regrets.items()}
        delta = {k: [[0., 0.] for _ in range(n)] for k, n in sizes.items()}
        average_weight = iteration**2 if algorithm == "dcfr" else 1.
        for k, rows in s.items():
            marginals = marginal0 if k in ("a", "d") else marginal1
            for idx, probabilities in enumerate(rows):
                own = 1-s["a"][idx][1] if k == "d" else 1.
                weight = average_weight * marginals[idx] * own
                sums[k][idx][0] += weight * probabilities[0]
                sums[k][idx][1] += weight * probabilities[1]
        da, dd, db, dc = (delta[k] for k in ("a", "d", "b", "c"))
        for i, j, w, sign in deals:
            x, d, y, c = s["a"][i][1], s["d"][i][1], s["b"][j][1], s["c"][j][1]
            t = utilities[sign]
            showdown, called = t["check_check"], t["bet_call"]
            response = (1-d)*t["check_bet_fold"]+d*t["check_bet_call"]
            vb = (1-c)*t["bet_fold"]+c*t["bet_call"]
            vc = (1-y)*showdown+y*response
            # Binary-action regret increments from the action-value difference.
            # Opponent reach belongs in regrets; own reach belongs in averages.
            root_diff = vb-vc
            response_diff = t["check_bet_call"]-t["check_bet_fold"]
            ip_bet_diff = showdown-response
            ip_call_diff = t["bet_fold"]-called
            da[i][0] -= w*x*root_diff
            da[i][1] += w*(1-x)*root_diff
            dd[i][0] -= w*y*d*response_diff
            dd[i][1] += w*y*(1-d)*response_diff
            db[j][0] -= w*(1-x)*y*ip_bet_diff
            db[j][1] += w*(1-x)*(1-y)*ip_bet_diff
            dc[j][0] -= w*x*c*ip_call_diff
            dc[j][1] += w*x*(1-c)*ip_call_diff
        positive_discount = iteration**1.5 / (iteration**1.5 + 1)
        for k in regrets:
            for i in range(sizes[k]):
                for a in (0, 1):
                    regrets[k][i][a] += delta[k][i][a]
                    if algorithm == "dcfr":
                        regrets[k][i][a] *= positive_discount if regrets[k][i][a] > 0 else .5
    avg = {k: [[v/sum(row) for v in row] if sum(row) else [.5, .5] for row in rows]
           for k, rows in sums.items()}
    # Best responses aggregate over indistinguishable opponent hands BEFORE max.
    d_values = [[0., 0.] for _ in h0]
    c_values = [[0., 0.] for _ in h1]
    b_values = [[0., 0.] for _ in h1]
    value = 0.
    for i, j, w, sign in deals:
        x, d, y, c = avg["a"][i][1], avg["d"][i][1], avg["b"][j][1], avg["c"][j][1]
        t = utilities[sign]
        show, called = t["check_check"], t["bet_call"]
        response = (1-d)*t["check_bet_fold"]+d*t["check_bet_call"]
        value += w*((1-x)*((1-y)*show+y*response)+x*((1-c)*t["bet_fold"]+c*called))
        for a, u in enumerate((t["check_bet_fold"], t["check_bet_call"])):
            d_values[i][a] += w*y*u
        for a, u in enumerate((-t["bet_fold"], -called)):
            c_values[j][a] += w*x*u
        for a, u in enumerate((-show, -response)):
            b_values[j][a] += w*(1-x)*u
    root_values = [[max(row), 0.] for row in d_values]
    for i, j, w, sign in deals:
        y, c = avg["b"][j][1], avg["c"][j][1]
        t = utilities[sign]
        root_values[i][0] += w*(1-y)*t["check_check"]
        root_values[i][1] += w*((1-c)*t["bet_fold"]+c*t["bet_call"])
    br0 = sum(max(row) for row in root_values)
    br1 = sum(max(row) for row in c_values)+sum(max(row) for row in b_values)
    gap = max(0, br0+br1)
    variant = ("DCFR(1.5,0,2), simultaneous regret-matching updates, reach-weighted quadratic strategy averaging"
               if algorithm == "dcfr" else
               "vanilla CFR, simultaneous regret-matching updates, reach-weighted uniform strategy averaging")
    return {"method": "full-traversal CFR", "cfr_variant": variant,
            "algorithm": algorithm, "solver_version": "restricted-river-v2",
            "info_sets": 2*(len(h0)+len(h1)), "iterations": iterations, "deals": len(deals),
            "pot": pot, "bet": bet, "value_oop": value, "value_ip": -value,
            "nash_conv": gap, "exploitability": gap/2,
            "oop_best_response_gain": max(0, br0-value),
            "gap_note": "Unrestricted best-response gap; with node locks, this is not a convergence certificate for the locked game.",
            "lock": lock_report, "scope": "River only; one fixed bet size; check/bet/fold/call; no raises or rake.",
            "oop": [{"hand": "".join(h), "bet": avg["a"][i][1], "call_after_check": avg["d"][i][1]} for i, h in enumerate(h0)],
            "ip": [{"hand": "".join(h), "bet_after_check": avg["b"][i][1], "call": avg["c"][i][1]} for i, h in enumerate(h1)]}
