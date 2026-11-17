"""Count exact early-showdown completion groups without ranking or training."""

from collections import Counter
import json
from math import comb

from scripts.project_virtual_dyadic_eleven import collect, template


def terminal_reuse_census():
    showdown_histories = Counter()

    def visit(node_id):
        node = template.nodes[node_id]
        if node.phase == "showdown":
            showdown_histories[node.street] += 1
        for edge in node.edges:
            visit(edge.child)

    visit(template.root)
    records = []
    for deck in (10, 11, 52):
        if deck == 52:
            flops = comb(deck, 3)
            prefixes = {0: 1, 3: flops, 4: flops * (deck - 3),
                        5: flops * (deck - 3) * (deck - 4)}
        else:
            shape, prefixes, _, _ = collect(deck, 644 if deck == 10 else 646, 12)
            observed = sum(showdown_histories[k] * prefixes[k] for k in showdown_histories)
            if observed != shape["showdowns"]:
                raise ValueError("showdown terminal census differs")
        total = sum(showdown_histories.values()) * prefixes[5]
        if deck != 52 and total != shape["showdown_contractions"]:
            raise ValueError("showdown completion census differs")
        hidden_groups = sum(showdown_histories[k] * prefixes[k] for k in showdown_histories if k < 5)
        hidden_boards = sum(showdown_histories[k] * prefixes[5] for k in showdown_histories if k < 5)
        records.append({
            "cards": deck,
            "prefix_counts": prefixes,
            "showdown_history_counts": dict(showdown_histories),
            "all_showdown_calls_per_pass": total,
            "early_terminal_groups": hidden_groups,
            "hidden_full_board_calls": hidden_boards,
            "repeat_groups_after_first_board": hidden_boards - hidden_groups,
            "scope": "rank-free geometry for fixed betting tree, before zero-reach effects",
        })
    return records


if __name__ == "__main__":
    print(json.dumps(terminal_reuse_census(), indent=2, sort_keys=True))
