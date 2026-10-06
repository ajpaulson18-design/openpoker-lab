"""Batch Monte Carlo hand simulation: many independent hands, aggregated.

Each simulated hand is a fresh, independent no-limit Hold'em hand played to
completion by ``pokerlab.game.Game`` with every seat driven by a parameterized
``pokerlab.archetypes.ArchetypePolicy``. This models a cash-game style
scenario: stacks reset to the configured starting amounts every hand, so
results are an estimate of per-hand expected value for the supplied archetype
mix, not a bankroll or tournament survival simulation. That assumption is
reported alongside the results rather than hidden.

Aggregation follows the same sampling-uncertainty conventions as
``pokerlab.equity``: a normal approximation standard error and 95% interval
around each seat's mean net result.
"""
from __future__ import annotations

import math
import random

from .archetypes import ArchetypePolicy
from .game import Game

MIN_TRIALS, MAX_TRIALS = 50, 20_000
MAX_SEAT_HANDS = 40_000  # trials * seats cap, scaling the cost bound with table size


def _interval(mean, se):
    return [mean - 1.96 * se, mean + 1.96 * se]


def _new_seat_stats():
    return {
        "hands_won": 0, "hands_tied": 0, "hands_lost": 0,
        "showdowns_reached": 0, "voluntarily_played": 0,
        "preflop_raised": 0, "folded_to_a_bet": 0, "faced_a_bet": 0,
        "postflop_bets_or_raises": 0, "postflop_decisions": 0,
        "total_net": 0.0, "total_net_sq": 0.0,
        "street_actions": {street: {"fold": 0, "check": 0, "call": 0, "raise": 0}
                           for street in ("preflop", "flop", "turn", "river")},
    }


def simulate_hands(stacks, archetypes, names=None, small_blind=1, big_blind=2,
                   button=0, trials=2000, seed=42, rotate_button=True):
    """Run many independent hands and return aggregated per-seat statistics."""
    if not isinstance(stacks, list) or not 2 <= len(stacks) <= 6:
        raise ValueError("Provide 2-6 starting stacks.")
    if not isinstance(archetypes, list) or len(archetypes) != len(stacks):
        raise ValueError("Provide one archetype per seat.")
    if isinstance(trials, bool) or not isinstance(trials, int) or not MIN_TRIALS <= trials <= MAX_TRIALS:
        raise ValueError(f"Trials must be an integer between {MIN_TRIALS} and {MAX_TRIALS}.")
    seats = len(stacks)
    if trials * seats > MAX_SEAT_HANDS:
        raise ValueError(
            f"Trials times seats is capped at {MAX_SEAT_HANDS:,} for responsiveness. "
            "Reduce trials or the number of seats.")
    names = names if names is not None else [f"Player {i+1}" for i in range(seats)]
    normalized = [ArchetypePolicy(a, random.Random(0)).archetype for a in archetypes]
    seat_stats = [_new_seat_stats() for _ in range(seats)]
    position_net = [0.0] * seats  # pooled by (seat - button) % n, index 0 = button
    position_net_sq = [0.0] * seats
    position_hands = [0] * seats
    master = random.Random(seed)

    for hand_index in range(trials):
        hand_button = (button + hand_index) % seats if rotate_button else button
        hand_seed = master.randrange(2**32)
        game = Game(list(stacks), names=list(names), button=hand_button,
                   small_blind=small_blind, big_blind=big_blind, seed=hand_seed)
        policies = {i: ArchetypePolicy(archetypes[i], random.Random(hand_seed * 1000 + i))
                   for i in range(seats)}
        preflop_contributed = [False] * seats
        while not game.done:
            seat = game.actor
            legal = game.legal()
            owe = legal["call"]
            street = game.street
            action, amount = policies[seat].decide(game, seat)
            if street == "preflop" and action in ("call", "raise"):
                preflop_contributed[seat] = True
            if street == "preflop" and action == "raise":
                seat_stats[seat]["preflop_raised"] += 1
            if owe:
                seat_stats[seat]["faced_a_bet"] += 1
                if action == "fold":
                    seat_stats[seat]["folded_to_a_bet"] += 1
            if street != "preflop" and not owe:
                seat_stats[seat]["postflop_decisions"] += 1
                if action == "raise":
                    seat_stats[seat]["postflop_bets_or_raises"] += 1
            seat_stats[seat]["street_actions"][street][action] += 1
            game.act(action, amount)
        net = game.state()["net"]
        showdown = sum(1 for folded in game.folded if not folded) > 1
        for seat in range(seats):
            stats = seat_stats[seat]
            stats["total_net"] += net[seat]
            stats["total_net_sq"] += net[seat] * net[seat]
            if net[seat] > 0:
                stats["hands_won"] += 1
            elif net[seat] < 0:
                stats["hands_lost"] += 1
            else:
                stats["hands_tied"] += 1
            if showdown and not game.folded[seat]:
                stats["showdowns_reached"] += 1
            if preflop_contributed[seat]:
                stats["voluntarily_played"] += 1
            relative = (seat - hand_button) % seats
            position_net[relative] += net[seat]
            position_net_sq[relative] += net[seat] * net[seat]
            position_hands[relative] += 1

    def _rate(successes, opportunities):
        return successes / opportunities if opportunities else None

    seats_report = []
    for seat in range(seats):
        stats = seat_stats[seat]
        mean = stats["total_net"] / trials
        variance = max(0.0, (stats["total_net_sq"] - trials * mean * mean) / max(1, trials - 1))
        se = math.sqrt(variance / trials)
        seats_report.append({
            "seat": seat, "name": names[seat], "archetype": normalized[seat],
            "hands": trials,
            "win_rate": stats["hands_won"] / trials,
            "tie_rate": stats["hands_tied"] / trials,
            "loss_rate": stats["hands_lost"] / trials,
            "showdown_rate": stats["showdowns_reached"] / trials,
            "mean_net_per_hand": mean,
            "standard_error": se,
            "interval95": _interval(mean, se),
            "total_net": stats["total_net"],
            "observed_vpip": _rate(stats["voluntarily_played"], trials),
            "observed_pfr": _rate(stats["preflop_raised"], trials),
            "observed_fold_to_bet": _rate(stats["folded_to_a_bet"], stats["faced_a_bet"]),
            "observed_postflop_aggression": _rate(
                stats["postflop_bets_or_raises"], stats["postflop_decisions"]),
            "action_frequencies": {
                street: {action: count / trials for action, count in counts.items()}
                for street, counts in stats["street_actions"].items()
            },
        })

    positional_report = []
    for relative in range(seats):
        n = position_hands[relative]
        mean = position_net[relative] / n if n else 0.0
        variance = max(0.0, (position_net_sq[relative] - n * mean * mean) / max(1, n - 1))
        se = math.sqrt(variance / n) if n else 0.0
        positional_report.append({
            "seats_from_button": relative, "hands": n,
            "mean_net_per_hand": mean, "standard_error": se,
            "interval95": _interval(mean, se),
        })

    return {
        "trials": trials, "seed": seed, "button": button, "rotate_button": rotate_button,
        "small_blind": small_blind, "big_blind": big_blind, "starting_stacks": list(stacks),
        "seats": seats_report,
        "positional_effects": positional_report,
        "assumption": ("Each hand is an independent cash-game-style deal: stacks reset to the "
                      "configured starting amounts every hand. This estimates per-hand EV for "
                      "the supplied archetype mix; it is not a bankroll or tournament survival "
                      "simulation, and archetype behavior is a declared heuristic policy, not a "
                      "claim about real human play or a solved equilibrium."),
    }
