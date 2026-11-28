"""Rank-free work delta for preparing opponent reach across hidden runouts."""

from itertools import combinations, permutations
from math import comb
import json

from scripts.project_virtual_dyadic_eleven import ranges, template, uniform_exp, words
from tests.full_deck_public_chance_reference import PROOF9


def forecast_reuse(deck_size, minimum_completions):
    if deck_size not in (10, 11) or minimum_completions not in (1, 4):
        raise ValueError("use a pinned ten- or eleven-card, two-sweep comparison")
    deck = set((*PROOF9, *range(deck_size-9)))
    holdouts = [set(a) | set(b) for a, _ in ranges[0] for b, _ in ranges[1]
                if set(a).isdisjoint(b)]
    prefixes = {0: {()}, 3: set(), 4: set(), 5: set()}
    for private in holdouts:
        available = deck - private
        for flop in combinations(sorted(available), 3):
            prefixes[3].add(flop)
            for turn, river in permutations(available - set(flop), 2):
                prefixes[4].add((*flop, turn))
                prefixes[5].add((*flop, turn, river))
    full_boards = prefixes[5]
    physical_opponents = [
        sum(set(holding).isdisjoint(board) for board in full_boards for holding, _ in side)
        for side in ranges
    ]
    flop_divisor = comb(deck_size-4, 3)
    divisors = {0: 1, 3: flop_divisor, 4: flop_divisor*(deck_size-7),
                5: flop_divisor*(deck_size-7)*(deck_size-8)}
    totals = {street: {"groups_per_seat_pass": 0, "board_calls_per_seat_pass": 0,
                       "preparation_work": 0, "removed_per_board_work": 0}
              for street in (0, 3, 4)}

    def visit(node_id, first, full):
        node = template.nodes[node_id]
        if node.phase == "decision":
            actor = node.state.player
            first = tuple(bits + (uniform_exp(len(node.edges)) if p == actor else 0)
                          for p, bits in enumerate(first))
            full = tuple(bits + (52 if p == actor else 0) for p, bits in enumerate(full))
        if (node.phase == "showdown" and node.street < 5 and
                divisors[5] // divisors[node.street] >= minimum_completions):
            groups = len(prefixes[node.street])
            row = totals[node.street]
            row["groups_per_seat_pass"] += groups
            row["board_calls_per_seat_pass"] += len(full_boards)
            for side in (0, 1):
                for exponent in (first[side], full[side]):
                    width = words(exponent+1)
                    # One four-bit prior operand, one possibly wide reach.
                    multiply = 2+2*(1+width)+width
                    input_per_row = 4+2*width
                    row["preparation_work"] += groups*(12+2*(8+input_per_row+multiply))
                    row["removed_per_board_work"] += (
                        len(full_boards)*2*(input_per_row-2)+physical_opponents[side]*multiply
                    )
        for edge in node.edges:
            visit(edge.child, first, full)

    visit(template.root, (0, 0), (0, 0))
    saved = sum(row["removed_per_board_work"]-row["preparation_work"] for row in totals.values())
    return {"deck": deck_size, "minimum_completions": minimum_completions,
            "by_street": totals, "chance_forecast_work_saved": saved}


if __name__ == "__main__":
    print(json.dumps([forecast_reuse(n, minimum) for n in (10, 11) for minimum in (1, 4)],
                     indent=2, sort_keys=True))
