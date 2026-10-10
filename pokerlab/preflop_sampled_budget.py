"""Independent admission census for preflop chance-block training.

Chance follows one branch per draw; every betting action is traversed. The
separate exact-vector admission reference includes an unused one-iteration
trainer allowance, so it conservatively bounds final full-game diagnostics.
Counters are structural visits and action cells, not bytes or elapsed time.
"""
from .river_tree import _Node, _Terminal

MAX_SAMPLED_NODE_VISITS = 30_000_000
MAX_SAMPLED_ACTION_CELLS = 30_000_000


def estimate_sampled_budget(root, infos, iterations, batch_size, *, chance_type):
    if type(iterations) is not int or iterations < 1:
        raise ValueError("Sampled iterations must be positive integers.")
    if type(batch_size) is not int or not 1 <= batch_size <= 256:
        raise ValueError("Samples per iteration must be integers from 1 to 256.")
    active = set()

    def walk(node):
        ident = id(node)
        if ident in active:
            raise ValueError("Sampled public tree contains a cycle.")
        active.add(ident)
        try:
            if isinstance(node, chance_type):
                if not node.branches:
                    raise ValueError("Sampled chance nodes need a branch.")
                bounds = [walk(child) for child in node.branches.values()]
                return (1 + max(row[0] for row in bounds),
                        max(row[1] for row in bounds))
            if isinstance(node, _Terminal):
                return (1, 0)
            if not isinstance(node, _Node):
                raise TypeError("Unsupported sampled public node.")
            if not node.children or len(node.children) != len(node.actions):
                raise ValueError("Sampled decision action/child counts must match.")
            bounds = [walk(child) for child in node.children]
            return (1 + sum(row[0] for row in bounds),
                    len(node.actions) + sum(row[1] for row in bounds))
        finally:
            active.remove(ident)

    try:
        per_draw_nodes, per_draw_actions = walk(root)
    finally:
        walk = None
    draws = iterations * batch_size if infos else 0
    nodes, actions = draws * per_draw_nodes, draws * per_draw_actions
    if nodes > MAX_SAMPLED_NODE_VISITS:
        raise ValueError("Sampled training exceeds 30 million node visits.")
    if actions > MAX_SAMPLED_ACTION_CELLS:
        raise ValueError("Sampled training exceeds 30 million action cells.")
    return {
        "budget_version": "preflop-chance-sampled-budget-v1",
        "world_draws": draws,
        "node_visits_per_draw_upper_bound": per_draw_nodes,
        "action_cells_per_draw_upper_bound": per_draw_actions,
        "total_node_visits_upper_bound": nodes,
        "total_action_cells_upper_bound": actions,
        "node_visit_limit": MAX_SAMPLED_NODE_VISITS,
        "action_cell_limit": MAX_SAMPLED_ACTION_CELLS,
        "scope": "All-action sampled-world traversal visits; exact full-world diagnostics have separate conservative vector admission. Not runtime or RSS bounds.",
    }
