"""Independent Kuhn-poker quality checks for the three CFR trainers.

The oracle below evaluates the six ordered J/Q/K private-card deals directly
from Kuhn's betting rules. It does not use the production evaluator or
best-response implementation. Those functions are called only as candidates
in :func:`training_report`, where their results are checked against this
independent oracle.

The game and equilibrium value are described in pages 1-2 of:
https://webdocs.cs.ualberta.ca/~holte/Publications/aaai2005poker.pdf
"""

from fractions import Fraction
from itertools import product
import time

from pokerlab import cfr, planned_cfr, public_cfr
from pokerlab.postflop_solver import (
    _Chance, _chance_child, _chance_partitions, _node_key,
)
from pokerlab.river_config import RiverConfig
from pokerlab.river_tree import _Node, _Terminal, _build_tree, _terminal_value


RANKS = ("J", "Q", "K")
KNOWN_P1_VALUE = Fraction(-1, 18)


class KuhnAdapterError(AssertionError):
    """The production action builder no longer represents the Kuhn fixture."""


class _KuhnLayout:
    """Immutable public-history tokens used only for infoset-key translation."""

    __slots__ = ("p1_root", "p2_after_check", "p1_after_check_bet",
                 "p2_after_bet", "check_token", "bet_token", "_frozen")

    def __init__(self, check_token, bet_token):
        object.__setattr__(self, "p1_root", ())
        object.__setattr__(self, "p2_after_check", (check_token,))
        object.__setattr__(self, "p1_after_check_bet", (check_token, bet_token))
        object.__setattr__(self, "p2_after_bet", (bet_token,))
        object.__setattr__(self, "check_token", check_token)
        object.__setattr__(self, "bet_token", bet_token)
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise AttributeError("Kuhn layout is immutable.")
        object.__setattr__(self, name, value)


def _collect_decisions(root):
    nodes = {}

    def collect(node):
        if isinstance(node, _Node):
            nodes[(node.player, node.history)] = node
            for child in node.children:
                collect(child)

    try:
        collect(root)
    finally:
        # Break the local recursive closure's self-reference promptly.
        collect = None
    return nodes


def _layout_from_nodes(nodes):
    root = nodes.get((0, ()))
    if root is None or len(root.actions) != 2:
        raise KuhnAdapterError("Kuhn root must have exactly check and bet actions.")
    check, bet = root.actions
    if check.name != "check" or bet.name not in ("bet", "all_in"):
        raise KuhnAdapterError("Kuhn root actions must be ordered check then bet/all-in.")
    if abs(bet.raise_to - 1.0) > 1e-9:
        raise KuhnAdapterError("The Kuhn bet must be exactly one chip.")
    layout = _KuhnLayout(check.token, bet.token)

    expected = {
        (1, layout.p2_after_check): ("check", bet.name),
        (0, layout.p1_after_check_bet): ("fold", "call"),
        (1, layout.p2_after_bet): ("fold", "call"),
    }
    for key, action_names in expected.items():
        node = nodes.get(key)
        if node is None or tuple(action.name for action in node.actions) != action_names:
            raise KuhnAdapterError(
                f"Kuhn response node {key!r} must have actions {action_names!r}."
            )
    return layout


def _independent_terminal_payoff(kind, contributions, winner, sign):
    """Kuhn net payoff from antes and one-chip bets, independent of solver code."""
    if kind == "fold":
        # The folder loses their ante; the winner's additional bet is returned.
        return 1.0 if winner == 0 else -1.0
    if kind == "showdown":
        # Check/check pays one ante unit; a called bet pays two units.
        if contributions == (0.0, 0.0):
            return float(sign)
        if contributions == (1.0, 1.0):
            return 2.0 * float(sign)
    raise KuhnAdapterError(
        f"Unexpected Kuhn terminal {kind!r} with contributions {contributions!r}."
    )


def _validate_terminal_mapping(root, nodes, config):
    if config.stacks != (1.0, 1.0) or config.pot != 2.0:
        raise KuhnAdapterError("Kuhn adapter requires pot two and one-chip stacks.")
    layout = _layout_from_nodes(nodes)
    check_node = nodes[(1, layout.p2_after_check)]
    after_check_bet = nodes[(0, layout.p1_after_check_bet)]
    after_root_bet = nodes[(1, layout.p2_after_bet)]
    terminals = (
        (check_node.children[0], "showdown", (0.0, 0.0), None),
        (after_check_bet.children[0], "fold", (0.0, 1.0), 1),
        (after_check_bet.children[1], "showdown", (1.0, 1.0), None),
        (after_root_bet.children[0], "fold", (1.0, 0.0), 0),
        (after_root_bet.children[1], "showdown", (1.0, 1.0), None),
    )
    for terminal, kind, contributions, winner in terminals:
        if not isinstance(terminal, _Terminal):
            raise KuhnAdapterError("Kuhn action branches must end at the expected terminal.")
        if (terminal.kind != kind or terminal.contributions != contributions or
                terminal.winner != winner):
            raise KuhnAdapterError("Kuhn production terminal shape or stack accounting changed.")
        for sign in (-1, 1):
            direct = _independent_terminal_payoff(kind, contributions, winner, sign)
            production = _terminal_value(terminal, sign, config.pot)
            if abs(float(production) - direct) > 1e-12:
                raise KuhnAdapterError("Kuhn production utility disagrees with ante/bet rules.")
    return layout


def build_kuhn_adapter():
    """Build and validate a fresh 4-node, 12-infoset production Kuhn tree.

    Returns a dictionary containing config, root, nodes, infos, worlds, and the
    immutable history-token layout. A fresh mutable tree is built per call.
    """
    config = RiverConfig(
        pot=2, effective_stack=1, bet_sizes=(0.5,), max_raises=0,
        include_all_in=False,
    )
    root, public_node_count = _build_tree(config)
    nodes = _collect_decisions(root)
    if public_node_count != 4 or len(nodes) != 4:
        raise KuhnAdapterError("Kuhn tree must contain exactly four public decisions.")
    layout = _validate_terminal_mapping(root, nodes, config)
    infos = {
        (player, hand, history): len(node.actions)
        for (player, history), node in nodes.items()
        for hand in range(3)
    }
    if len(infos) != 12:
        raise KuhnAdapterError("Kuhn tree must expose exactly twelve private-hand infosets.")
    return {
        "config": config,
        "root": root,
        "nodes": nodes,
        "infos": infos,
        "worlds": _ordered_worlds(exact=False),
        "layout": layout,
    }


def _ordered_worlds(*, exact):
    weight = Fraction(1, 6) if exact else 1.0 / 6.0
    return [
        (first, second, weight, (first > second) - (first < second))
        for first in range(3)
        for second in range(3)
        if first != second
    ]


def _choose(profile, player, hand, history, action):
    return profile[(player, hand, history)][action]


def _direct_profile_value(profile0, profile1, worlds, layout):
    """Compute first-player value directly from Kuhn's terminal histories."""
    value = Fraction(0) if all(isinstance(world[2], Fraction) for world in worlds) else 0.0
    for world in worlds:
        p1_hand, p2_hand, mass, sign = world
        # P1 checks, then P2 checks to a one-unit showdown or bets. A P1 call
        # puts one unit in each player's stack, so the called showdown is ±2.
        checked = _choose(profile0, 0, p1_hand, layout.p1_root, 0) * (
            _choose(profile1, 1, p2_hand, layout.p2_after_check, 0) * sign +
            _choose(profile1, 1, p2_hand, layout.p2_after_check, 1) * (
                _choose(profile0, 0, p1_hand, layout.p1_after_check_bet, 0) * -1 +
                _choose(profile0, 0, p1_hand, layout.p1_after_check_bet, 1) *
                (2 * sign)
            )
        )
        # If P1 bets, P2 folds for a one-unit P1 win or calls to a two-unit
        # showdown. No generic solver terminal-payoff callback is used here.
        bet = _choose(profile0, 0, p1_hand, layout.p1_root, 1) * (
            _choose(profile1, 1, p2_hand, layout.p2_after_bet, 0) * 1 +
            _choose(profile1, 1, p2_hand, layout.p2_after_bet, 1) *
            (2 * sign)
        )
        value += mass * (checked + bet)
    return value


def _equilibrium_family(alpha, layout):
    """Create Kuhn's exact equilibrium family for 0 <= alpha <= 1/3."""
    alpha = Fraction(alpha)
    if not 0 <= alpha <= Fraction(1, 3):
        raise ValueError("Kuhn equilibrium alpha must lie in [0, 1/3].")
    profile = {}

    def bet(player, hand, history, probability):
        profile[(player, hand, history)] = [1 - probability, probability]

    def call(player, hand, history, probability):
        profile[(player, hand, history)] = [1 - probability, probability]

    # Kuhn's parameter alpha is gamma/3: P1 bluffs with J at alpha and bets K
    # at 3 alpha; P1 calls with Q at alpha + 1/3 after checking.
    bet(0, 0, layout.p1_root, alpha)
    bet(0, 1, layout.p1_root, Fraction(0))
    bet(0, 2, layout.p1_root, 3 * alpha)
    call(0, 0, layout.p1_after_check_bet, Fraction(0))
    call(0, 1, layout.p1_after_check_bet, alpha + Fraction(1, 3))
    call(0, 2, layout.p1_after_check_bet, Fraction(1))
    bet(1, 0, layout.p2_after_check, Fraction(1, 3))
    bet(1, 1, layout.p2_after_check, Fraction(0))
    bet(1, 2, layout.p2_after_check, Fraction(1))
    call(1, 0, layout.p2_after_bet, Fraction(0))
    call(1, 1, layout.p2_after_bet, Fraction(1, 3))
    call(1, 2, layout.p2_after_bet, Fraction(1))
    return profile


def _pure_policy(player, choices, layout):
    if player not in (0, 1) or len(choices) != 6 or any(
            choice not in (0, 1) for choice in choices):
        raise ValueError("A pure Kuhn policy requires six binary choices for one player.")
    first = layout.p1_root if player == 0 else layout.p2_after_check
    second = layout.p1_after_check_bet if player == 0 else layout.p2_after_bet
    policy = {}
    cursor = 0
    for hand in range(3):
        for history in (first, second):
            selected = choices[cursor]
            policy[(player, hand, history)] = [
                Fraction(int(selected == 0)), Fraction(int(selected == 1)),
            ]
            cursor += 1
    return policy


def _independent_best_response(player, opponent_profile, worlds, layout):
    """Exhaustively score all 64 private-hand policies using direct rules."""
    if player not in (0, 1):
        raise ValueError("Player must be 0 (first) or 1 (second).")
    best = None
    for choices in product((0, 1), repeat=6):
        own = _pure_policy(player, choices, layout)
        if player == 0:
            value = _direct_profile_value(own, opponent_profile, worlds, layout)
        else:
            value = -_direct_profile_value(opponent_profile, own, worlds, layout)
        if best is None or value > best:
            best = value
    return best


def verify_known_equilibrium_family():
    """Prove the three documented equilibrium points with exact Fractions."""
    adapter = build_kuhn_adapter()
    layout = adapter["layout"]
    worlds = _ordered_worlds(exact=True)
    proof = []
    for alpha in (Fraction(0), Fraction(1, 6), Fraction(1, 3)):
        profile = _equilibrium_family(alpha, layout)
        value = _direct_profile_value(profile, profile, worlds, layout)
        br0 = _independent_best_response(0, profile, worlds, layout)
        br1 = _independent_best_response(1, profile, worlds, layout)
        if value != KNOWN_P1_VALUE or br0 != value or br1 != -value:
            raise AssertionError(
                f"Kuhn analytic equilibrium failed at alpha={alpha}: "
                f"value={value}, BRs=({br0}, {br1})."
            )
        proof.append({
            "alpha": str(alpha), "value_p1": str(value),
            "p1_best_response": str(br0), "p2_best_response": str(br1),
            "p1_gain": str(br0 - value), "p2_gain": str(br1 + value),
        })
    return proof


def _rationalize_profile(profile):
    """Convert represented float rows to exact, exactly normalized ratios."""
    rational = {}
    for key, probabilities in profile.items():
        values = [value if isinstance(value, Fraction) else
                  Fraction.from_float(float(value)) for value in probabilities]
        total = sum(values, Fraction(0))
        if total <= 0:
            raise ValueError(f"Cannot rationalize empty strategy at {key!r}.")
        rational[key] = [value / total for value in values]
    return rational


def check_metrics(profile, *, layout=None):
    """Score a profile using only the direct payoff and exhaustive BR oracle."""
    if layout is None:
        layout = build_kuhn_adapter()["layout"]
    worlds = _ordered_worlds(exact=False)
    exact_worlds = _ordered_worlds(exact=True)
    value = float(_direct_profile_value(profile, profile, worlds, layout))
    br0 = float(_independent_best_response(0, profile, worlds, layout))
    br1 = float(_independent_best_response(1, profile, worlds, layout))
    gain0 = max(0.0, br0 - value)
    gain1 = max(0.0, br1 + value)
    rational_profile = _rationalize_profile(profile)
    rational_value = _direct_profile_value(
        rational_profile, rational_profile, exact_worlds, layout,
    )
    return {
        "value_p1": value,
        "known_p1_value": float(KNOWN_P1_VALUE),
        "value_error": abs(value - float(KNOWN_P1_VALUE)),
        "p1_best_response": br0,
        "p2_best_response": br1,
        "p1_gain": gain0,
        "p2_gain": gain1,
        "nash_conv": gain0 + gain1,
        "exploitability": (gain0 + gain1) / 2.0,
        "rational_replay_value_p1": str(rational_value),
        "rational_replay_float_delta": float(rational_value) - value,
    }


def _train_on_adapter(adapter, iterations, algorithm, backend):
    root = adapter["root"]
    worlds = adapter["worlds"]
    infos = adapter["infos"]
    config = adapter["config"]
    payoff = lambda node, world: _terminal_value(node, world[3], config.pot)
    if backend == "recursive":
        return cfr.train(root, worlds, infos, iterations, algorithm, payoff,
                         _node_key, _chance_child)
    if backend == "planned":
        return planned_cfr.train(root, worlds, infos, iterations, algorithm, payoff,
                                 _node_key, _chance_child)
    if backend == "public-batched":
        return public_cfr.train_public_batched(
            root, worlds, infos, iterations, algorithm,
            pot=config.pot, chance_type=_Chance,
        )
    raise ValueError("Backend must be recursive, planned, or public-batched.")


def train_profile(iterations, algorithm, backend):
    """Train and return one profile with a fresh validated Kuhn adapter tree."""
    if type(iterations) is not int or iterations < 1:
        raise ValueError("Iterations must be a positive integer.")
    if algorithm not in ("vanilla", "dcfr"):
        raise ValueError("Algorithm must be vanilla or dcfr.")
    if backend not in ("recursive", "planned", "public-batched"):
        raise ValueError("Backend must be recursive, planned, or public-batched.")
    adapter = build_kuhn_adapter()
    return _train_on_adapter(adapter, iterations, algorithm, backend)


def training_report(iterations, algorithm, backend):
    """Train one configuration and compare independent and production metrics.

    ``trainer_seconds`` times only the selected training function. Tree setup,
    independent best responses, and production candidate metric calculations
    are excluded from the trainer duration.
    """
    if type(iterations) is not int or iterations < 1:
        raise ValueError("Iterations must be a positive integer.")
    if algorithm not in ("vanilla", "dcfr"):
        raise ValueError("Algorithm must be vanilla or dcfr.")
    if backend not in ("recursive", "planned", "public-batched"):
        raise ValueError("Backend must be recursive, planned, or public-batched.")

    adapter = build_kuhn_adapter()
    started = time.perf_counter()
    profile = _train_on_adapter(adapter, iterations, algorithm, backend)
    trainer_seconds = time.perf_counter() - started
    oracle = check_metrics(profile, layout=adapter["layout"])

    # Production evaluator and BR routines are comparison candidates only.
    config = adapter["config"]
    payoff = lambda node, world: _terminal_value(node, world[3], config.pot)
    candidate_value = cfr.evaluate(
        adapter["root"], adapter["worlds"], profile, payoff,
        _node_key, _chance_child,
    )
    candidate_br0 = cfr.best_response(
        0, adapter["root"], adapter["worlds"], profile, payoff,
        _node_key, _chance_partitions,
    )
    candidate_br1 = cfr.best_response(
        1, adapter["root"], adapter["worlds"], profile, payoff,
        _node_key, _chance_partitions,
    )
    candidate = {
        "value_p1": float(candidate_value),
        "p1_best_response": float(candidate_br0),
        "p2_best_response": float(candidate_br1),
    }
    shared_differences = {
        "value_p1": abs(candidate["value_p1"] - oracle["value_p1"]),
        "p1_best_response": abs(candidate["p1_best_response"] -
                                 oracle["p1_best_response"]),
        "p2_best_response": abs(candidate["p2_best_response"] -
                                 oracle["p2_best_response"]),
    }
    return {
        "iterations": iterations,
        "algorithm": algorithm,
        "backend": backend,
        "trainer_seconds": trainer_seconds,
        **oracle,
        "production_candidate_metrics": candidate,
        "shared_metric_differences": shared_differences,
        "shared_metric_max_abs_difference": max(shared_differences.values()),
    }
