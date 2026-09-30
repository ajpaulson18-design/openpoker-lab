"""Seeded Monte Carlo and exact river equity, including split pots."""
import math
import random
from .cards import cards, DECK, expand_range, rank_hand, NAMES


def simulate(hero, board="", ranges=None, trials=5000, seed=42):
    hero, board = cards(hero, 2), cards(board)
    cards(hero + board)
    if len(board) not in (0, 3, 4, 5):
        raise ValueError("The board must contain 0, 3, 4, or 5 cards.")
    ranges = ["random"] if ranges is None else ranges
    if not isinstance(ranges, list) or not 1 <= len(ranges) <= 5:
        raise ValueError("Provide 1–5 opponent ranges.")
    if isinstance(trials, bool) or not isinstance(trials, int) or not 100 <= trials <= 50000:
        raise ValueError("Trials must be an integer between 100 and 50,000.")
    pools = [expand_range(r, hero + board) for r in ranges]
    rng = random.Random(seed)
    total = total_sq = wins = ties = mass = 0.0
    categories = [0.0] * 9
    exact = len(board) == 5 and len(pools) == 1
    choices = [(list(p), list(p.values())) for p in pools]
    iterations = len(pools[0]) if exact else trials
    for i in range(iterations):
        if exact:
            villains = [choices[0][0][i]]
            weight = choices[0][1][i]
        else:
            # Independent draws then joint rejection preserve product range weights.
            # Sequential renormalization would bias earlier players' ranges.
            for attempt in range(10000):
                villains = [rng.choices(h, w)[0] for h, w in choices]
                flat = [c for h in villains for c in h]
                if len(flat) == len(set(flat)):
                    break
            else:
                raise ValueError("Opponent ranges overlap too much to sample a legal deal.")
            weight = 1.0
        used = set(hero + board + tuple(c for h in villains for c in h))
        runout = board + tuple(rng.sample([c for c in DECK if c not in used], 5-len(board)))
        ranks = [rank_hand(h + runout) for h in [hero] + villains]
        best = max(ranks)
        tied = sum(r == best for r in ranks)
        share = 1/tied if ranks[0] == best else 0.0
        wins += weight * (share == 1)
        ties += weight * (0 < share < 1)
        total += weight * share
        total_sq += weight * share * share
        mass += weight
        categories[ranks[0][0]] += weight
    eq = total/mass
    se = 0 if exact else math.sqrt(max(0, (total_sq-mass*eq*eq)/(mass-1))/mass)
    return {"equity": eq, "win": wins/mass, "tie": ties/mass,
            "interval95": [max(0, eq-1.96*se), min(1, eq+1.96*se)],
            "standard_error": se, "trials": iterations, "exact": exact, "seed": seed,
            "range_combos": [len(p) for p in pools],
            "categories": dict(zip(NAMES, [v/mass for v in categories])),
            "assumption": "Showdown equity against the supplied ranges; future betting and rake are excluded."}
