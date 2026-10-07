"""Report diagnostics for a representative restricted-river CFR solve.

Usage: python -m scripts.validate_solver [iterations ...]
"""
import sys
import time

from pokerlab.solver import solve

BOARD, OOP, IP, POT, BET = "Js8d4c2h2s", "AsAh,KsKh,QsQh,AsKs", "AcAd,KcKd,QcQd,AcKc", 100, 50


def main(argv):
    counts = [int(a) for a in argv] or [10, 100, 1000, 5000]
    print(f"Game: heads-up river, board {BOARD}, pot {POT}, one bet size {BET}, "
          "check/bet/fold/call, no raises")
    print(f"OOP range: {OOP}\nIP range:  {IP}")
    print(f"{'iters':>6} {'secs':>7} {'infosets':>8} {'deals':>5} {'OOP EV':>9} "
          f"{'NashConv':>9} {'exploit.':>9} {'OOP BR gain':>11}")
    for n in counts:
        start = time.perf_counter()
        r = solve(BOARD, OOP, IP, POT, BET, n)
        secs = time.perf_counter() - start
        print(f"{n:>6} {secs:>7.2f} {r['info_sets']:>8} {r['deals']:>5} {r['value_oop']:>9.3f} "
              f"{r['nash_conv']:>9.4f} {r['exploitability']:>9.4f} {r['oop_best_response_gain']:>11.4f}")
    print(f"CFR variant: {r['cfr_variant']}")
    print("NashConv = (BR_OOP value - OOP EV) + (BR_IP value - IP EV); exploitability = NashConv / 2.")
    print("Values are chips relative to half the pot. Applies to this restricted game only.")


if __name__ == "__main__":
    main(sys.argv[1:])
