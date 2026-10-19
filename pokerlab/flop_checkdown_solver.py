"""Exact future-deck integration for a finite heads-up flop betting game.

Only flop betting is optimized. Turn and river are hidden forced checkdown;
this adapter does not change shared postflop, turn/river, or CFR kernels.
"""
from .flop_checkdown_worlds import prepare_flop_worlds
from .flop_checkdown_equity import FlopCheckdownEquities
from .preflop_vector_budget import estimate_vector_budget, MAX_TOTAL_LOOP_ENTRIES, MAX_INFO_ACTION_SLOTS
from .public_cfr import train_public_batched
from .public_diagnostics import evaluate_profile
from .river_config import RiverConfig
from .river_tree import _build_tree, _Node

MAX_PUBLIC_STATES = 25_000


class _NoPublicChance:
    """There are no visible future reveals in the checkdown model."""


def solve_flop_checkdown(board, oop_range, ip_range, *, config=None,
                         iterations=1000, algorithm="cfrplus"):
    """Solve fixed-flop betting with every legal hidden future board integrated.

    Values use the existing symmetric pot-share convention: initial pot/2 plus
    matched additional contributions, with unmatched excess refunded. Starting
    effective stacks exclude the existing pot. This is a zero-sum finite action
    abstraction, with no later-street betting, rake or multiway equilibrium.
    """
    config = _validate_options(config, iterations, algorithm)
    plan = prepare_flop_worlds(board, oop_range, ip_range)
    return _solve_plan(plan, config, iterations, algorithm)


def solve_prepared_flop_checkdown(equities, *, config=None, iterations=1000,
                                  algorithm="cfrplus", training_backend="python",
                                  build_directory=None):
    """Solve using immutable fixed-flop counts without board enumeration.

    Structural validation does not authenticate caller-supplied outcome counts.
    Admission conservatively retains the ordinary source-inclusive work bound;
    the additive preparation metadata describes the current call's avoided work.
    The default solve API and its result payload remain unchanged.
    """
    from . import native_fixed_street as native
    native.validate_backend(training_backend, build_directory)
    config = _validate_options(config, iterations, algorithm)
    if training_backend == "native" and (max(config.stacks) > 1e12
            or config.pot / 2 + min(config.stacks) > 1e12):
        raise ValueError("Native terminal utility exceeds 1e12 chips")
    if type(equities) is not FlopCheckdownEquities:
        raise TypeError("equities must be FlopCheckdownEquities")
    equities.validate()
    result = _solve_plan(equities, config, iterations, algorithm,
                         native_build_directory=build_directory if training_backend == "native" else None)
    result["equity_preparation"] = {
        "mode": "prepared-counts",
        "current_rank_calls": 0,
        "current_unordered_board_evaluations": 0,
        "source_inclusive_admission": True,
        "validation": "Structural consistency only; supplied counts require trusted provenance.",
    }
    return result


def _validate_options(config, iterations, algorithm):
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError("Iterations must be an integer from 10 to 10,000")
    if algorithm not in ("vanilla", "dcfr", "cfrplus"):
        raise ValueError("Algorithm must be vanilla, dcfr or cfrplus")
    if config is None:
        config = RiverConfig()
    elif isinstance(config, dict):
        config = RiverConfig.from_dict(config)
    elif not isinstance(config, RiverConfig):
        raise TypeError("config must be RiverConfig or its serialized mapping")
    return config


def _solve_plan(plan, config, iterations, algorithm, *, native_build_directory=None):
    counts = {"decision": 0, "terminal": 0}

    def reserve(kind):
        if sum(counts.values()) >= MAX_PUBLIC_STATES:
            raise ValueError("Direct flop tree exceeds the 25,000-state cap")
        counts[kind] += 1

    root, decisions = _build_tree(config, allocation_hook=reserve)
    active = ({i for i, _, _ in plan.pairs}, {j for _, j, _ in plan.pairs})
    infos, metadata = {}, {}
    pending = [root]
    slots = 0
    while pending:
        node = pending.pop()
        if not isinstance(node, _Node):
            continue
        for hand in sorted(active[node.player]):
            key = node.player, hand, node.history
            slots += len(node.actions)
            if slots > MAX_INFO_ACTION_SLOTS:
                raise ValueError("Direct flop information-action cap exceeded")
            infos[key], metadata[key] = len(node.actions), node
        pending.extend(reversed(node.children))
    # Three categorical signs per compatible pair upper-bound the actual rows.
    # These uniform placeholder masses serve structural admission exclusively.
    shape = [(i, j, 1.0 / (3 * len(plan.pairs)), sign)
             for i, j, _ in plan.pairs for sign in (-1, 0, 1)]
    vector = estimate_vector_budget(root, shape, infos, iterations, algorithm,
                                    chance_type=_NoPublicChance)
    source_loops = (128 + 4 * plan.budget["candidate_pairs"] +
                    128 * len(plan.pairs) + 64 * plan.budget["unordered_boards"])
    total = vector["total_loop_entries_upper_bound"] + source_loops
    if total > MAX_TOTAL_LOOP_ENTRIES:
        raise ValueError("Direct flop combined modeled work exceeds 500,000,000")
    budget = {"budget_version": "direct-flop-checkdown-budget-v1",
              "vector_upper_bound": vector, "source_admission": plan.budget,
              "source_bookkeeping_loop_entries_upper_bound": source_loops,
              "total_loop_entries_upper_bound": total,
              "total_loop_entry_limit": MAX_TOTAL_LOOP_ENTRIES,
              "scope": "Full requested training and exact diagnostics, with at most three categorical rows per pair. Source bookkeeping excludes internal hand-ranking instructions; rank calls are independently bounded before ranking. Logical counts are not bytecode, elapsed time, allocation bytes or RSS bounds."}
    native_admission = None
    if native_build_directory is not None:
        from . import native_fixed_street as native
        shape = native.admit_native_shape(sum(counts.values()), len(plan.pairs),
                                          slots, iterations, algorithm, reduction='public-batched',
                                          hand_counts=tuple(map(len, active)))
        native_admission = native.complete_solve_admission(
            shape, total, vector["training_loop_entries_upper_bound"])
    worlds, equity = plan.build()
    native_metadata = None
    if native_build_directory is not None:
        # The Python public trainer already sums category mass and signed mass
        # per hidden pair. Preserve that signed mass directly for the compiled
        # public traversal; retain zero means and distinct opponent hands.
        pairs = {}
        for i, j, mass, sign in worlds:
            row = pairs.setdefault((i, j), [0.0, 0.0])
            row[0] += mass
            row[1] += mass * sign
        native_worlds = tuple((i, j, mass, signed)
                              for (i, j), (mass, signed) in pairs.items())
        averages, native_metadata = native.train_native_fixed_street(
            root, native_worlds, infos, iterations, algorithm,
            pot=config.pot, build_directory=native_build_directory, reduction='public-batched')
        native_metadata["complete_solve_admission"] = native_admission
        native_metadata["world_indexing"] = "hidden-category-mass-and-signed-mass"
    else:
        averages = train_public_batched(root, worlds, infos, iterations, algorithm,
                                        pot=config.pot, chance_type=_NoPublicChance)
    value, br0, br1 = evaluate_profile(root, worlds, averages, pot=config.pot,
                                      chance_type=_NoPublicChance)
    gap = max(0.0, br0 + br1)
    rows = []
    for key in sorted(infos):
        player, hand, history = key
        node = metadata[key]
        rows.append({"player": "oop" if player == 0 else "ip",
                     "hand": "".join(plan.hands[player][hand]), "street": "flop",
                     "board": list(plan.board), "history": list(history),
                     "actions": [{"name": a.name, "amount": a.amount,
                                  "raise_to": a.raise_to, "history_key": a.token,
                                  "probability": probability}
                                 for a, probability in zip(node.actions, averages[key])]})
    result = {"solver_version": "direct-flop-checkdown-v1",
            "strategy_schema": "postflop-strategy-v1", "algorithm": algorithm,
            "execution_backend": "public-batched-python",
            "board": list(plan.board), "config": config.to_dict(),
            "iterations": iterations, "runout_mode": "full-future-deck",
            "postflop_scope": "flop-checkdown", "compatible_pairs": len(plan.pairs),
            "physical_worlds": 1980 * len(plan.pairs), "training_world_rows": len(worlds),
            "info_sets": len(infos), "public_nodes": decisions,
            "public_states": sum(counts.values()), "terminal_nodes": counts["terminal"],
            "work_budget": budget, "pair_equities": equity,
            "value_oop": value, "value_ip": -value,
            "oop_best_response_value": br0, "ip_best_response_value": br1,
            "oop_best_response_gain": max(0.0, br0 - value),
            "ip_best_response_gain": max(0.0, br1 + value),
            "nash_conv": gap, "exploitability": gap / 2,
            "strategy": rows,
            "update_schedule": ("alternating-oop-then-ip; linear completed-sweep own-reach average"
                                if algorithm == "cfrplus" else
                                "simultaneous; quadratic own-reach average" if algorithm == "dcfr" else
                                "simultaneous; uniform own-reach average"),
            "scope": "Finite heads-up fixed-flop betting abstraction with every legal turn/river integrated under forced checkdown. No later-street betting, full-deck preflop, rake or multiway equilibrium. Pot-share values split the existing pot symmetrically and include matched additional wagers."}

    if native_metadata is not None:
        result["execution_backend"] = "native-fixed-street-v1"
        result["native_training"] = native_metadata
    return result
