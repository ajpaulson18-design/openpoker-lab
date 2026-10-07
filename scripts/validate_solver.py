"""Compare convergence and tree growth across configured river abstractions.

Usage: python -m scripts.validate_solver [iterations ...]
"""
import sys
import time

from pokerlab.river_config import RiverConfig
from pokerlab.solver import solve

BOARD = "Js8d4c2h2s"
OOP = "AsAh,KsKh,QsQh,AsKs"
IP = "AcAd,KcKd,QcQd,AcKc"
SCENARIOS = (
    ("A: one bet, no raises", RiverConfig(100, 500, (.5,), (), 0, False)),
    ("B: several bets, no raises", RiverConfig(100, 500, (.33, .75, 1.0), (), 0, False)),
    ("C: several bets, one raise level",
     RiverConfig(100, 500, (.33, .75, 1.0), (.75,), 1, False)),
)


def main(argv):
    counts = [int(value) for value in argv] or [100, 1000, 3000]
    print(f"Game: board {BOARD}; OOP range {OOP}; IP range {IP}")
    previous = None
    for name, config in SCENARIOS:
        print(f"\n{name}")
        print(f"  pot={config.pot:g}; effective_stack={config.effective_stack:g}; "
              f"bet_sizes={list(config.bet_sizes)}; raise_sizes={list(config.raise_sizes)}; "
              f"max_raises={config.max_raises}; include_all_in={config.include_all_in}")
        print(f"  {'iters':>6} {'secs':>7} {'infosets':>8} {'nodes':>6} {'actions':>7} "
              f"{'NashConv':>10} {'exploit.':>10} {'BR OOP':>10} {'BR IP':>10}")
        last = None
        for iterations in counts:
            start = time.perf_counter()
            result = solve(BOARD, OOP, IP, iterations=iterations, config=config)
            elapsed = time.perf_counter() - start
            print(f"  {iterations:>6} {elapsed:>7.3f} {result['info_sets']:>8} "
                  f"{result['public_nodes']:>6} {result['tree_actions']:>7} "
                  f"{result['nash_conv']:>10.4f} {result['exploitability']:>10.4f} "
                  f"{result['oop_best_response_value']:>10.4f} "
                  f"{result['ip_best_response_value']:>10.4f}")
            last = result
        if previous is not None:
            print(f"  Growth vs previous tree: {last['public_nodes'] / previous['public_nodes']:.2f}x "
                  f"public nodes, {last['info_sets'] / previous['info_sets']:.2f}x "
                  f"information sets, {last['tree_actions'] / previous['tree_actions']:.2f}x actions")
        previous = last
    print("\nCFR: vanilla full-traversal CFR with simultaneous regret-matching and "
          "reach-weighted uniform averaging.")
    print("NashConv is the sum of the two players' best-response values; "
          "exploitability is NashConv / 2.")
    print("Results describe approximate equilibria of these configured abstractions only.")


if __name__ == "__main__":
    main(sys.argv[1:])
