"""Finite heads-up preflop betting trees with explicit continuation leaves.

This module models blind posting and preflop actions only. A live flop or an
all-in runout is represented by :class:`PreflopContinuation`; neither is
silently converted into a showdown terminal.
"""
from dataclasses import asdict, dataclass
import math

from .analysis import number
from .river_tree import _Action, _Node, _Terminal, _raise_actions


_EPSILON = 1e-9


def _clean(value):
    value = round(float(value), 9)
    return 0.0 if value == 0 else value


def _sizes(values):
    if isinstance(values, (str, bytes)):
        raise ValueError("Raise sizes must be a sequence of positive pot fractions.")
    try:
        result = tuple(number(value, "Raise sizes", .000000001) for value in values)
    except TypeError as exc:
        raise ValueError("Raise sizes must be a sequence of positive pot fractions.") from exc
    if not all(math.isfinite(value) for value in result):
        raise ValueError("Raise sizes must contain finite positive fractions.")
    if len(result) > 8:
        raise ValueError("At most eight raise sizes are supported.")
    return tuple(sorted(set(result)))


@dataclass(frozen=True)
class PreflopConfig:
    """Serializable heads-up blind and raise-size configuration.

    Player 0 is the small blind/button and acts first preflop. Starting stacks
    are total chips before blinds and may be a shared scalar or a player pair.
    Raise fractions follow ``river_tree._raise_actions``: they size the raise
    increment from the call amount against the pot after calling.
    """

    small_blind: float = 0.5
    big_blind: float = 1.0
    starting_stack: float | tuple = 100.0
    raise_sizes: tuple = (1.0,)
    max_raises: int = 3
    include_all_in: bool = True

    def __post_init__(self):
        small_blind = _clean(number(self.small_blind, "Small blind", .000000001))
        big_blind = _clean(number(self.big_blind, "Big blind", .000000001))
        if small_blind >= big_blind:
            raise ValueError("Small blind must be less than big blind.")
        if small_blind <= _EPSILON or big_blind - small_blind <= _EPSILON:
            raise ValueError("Blinds and their difference must exceed the 1e-9-chip comparison tolerance.")
        if isinstance(self.starting_stack, (tuple, list)):
            if len(self.starting_stack) != 2:
                raise ValueError("Starting stack must be one amount or a player pair.")
            stacks = tuple(_clean(number(value, "Starting stack", .000000001))
                           for value in self.starting_stack)
        else:
            stacks = _clean(number(self.starting_stack, "Starting stack", .000000001))
        sizes = _sizes(self.raise_sizes)
        if type(self.max_raises) is not int or not 0 <= self.max_raises <= 8:
            raise ValueError("Maximum raises must be an integer from 0 to 8.")
        if type(self.include_all_in) is not bool:
            raise ValueError("include_all_in must be a boolean.")
        object.__setattr__(self, "small_blind", small_blind)
        object.__setattr__(self, "big_blind", big_blind)
        object.__setattr__(self, "starting_stack", stacks)
        object.__setattr__(self, "raise_sizes", sizes)

    @property
    def stacks(self):
        """Player stack caps in (small blind/button, big blind) order."""
        if isinstance(self.starting_stack, tuple):
            return self.starting_stack
        return self.starting_stack, self.starting_stack

    @property
    def pot(self):
        """Pot before this street's blinds, for the shared raise helper."""
        return 0.0

    def to_dict(self):
        result = asdict(self)
        if isinstance(self.starting_stack, tuple):
            result["starting_stack"] = list(self.starting_stack)
        result["raise_sizes"] = list(self.raise_sizes)
        return result

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict):
            raise ValueError("Preflop configuration must be an object.")
        allowed = {"small_blind", "big_blind", "starting_stack", "raise_sizes",
                   "max_raises", "include_all_in"}
        extra = set(values) - allowed
        if extra:
            raise ValueError(f"Unknown preflop configuration fields: {sorted(extra)}")
        return cls(**values)


@dataclass(frozen=True)
class PreflopContinuation:
    """Unsolved boundary passed to a future flop or all-in runout builder."""

    history: tuple
    matched_contributions: tuple
    refunds: tuple
    pot: float
    remaining_stacks: tuple
    all_in: tuple
    next_player: int | None
    street: str


@dataclass(frozen=True)
class PreflopTree:
    """A built preflop tree and counts for its owned public state boundary."""

    root: object
    nodes: dict
    config: PreflopConfig
    decision_node_count: int
    fold_terminal_count: int
    continuation_count: int
    public_state_count: int

    @property
    def counts(self):
        return {
            "decision_nodes": self.decision_node_count,
            "fold_terminals": self.fold_terminal_count,
            "continuations": self.continuation_count,
            "public_states": self.public_state_count,
        }


def _continuation(config, history, contributions):
    matched = min(contributions)
    matched_contributions = (_clean(matched), _clean(matched))
    refunds = tuple(_clean(value - matched) for value in contributions)
    remaining = tuple(_clean(stack - matched)
                      for stack in config.stacks)
    all_in = tuple(value <= _EPSILON for value in remaining)
    has_all_in = any(all_in)
    return PreflopContinuation(
        history=tuple(history),
        matched_contributions=matched_contributions,
        refunds=refunds,
        pot=_clean(sum(matched_contributions)),
        remaining_stacks=remaining,
        all_in=all_in,
        next_player=None if has_all_in else 1,
        street="showdown" if has_all_in else "flop",
    )


def build_preflop_tree(config=None, *, continuation_factory=None,
                       max_public_states=250_000, max_decision_nodes=10_000):
    """Build a fresh heads-up preflop tree.

    The optional callback receives a frozen settlement object and may return a
    compatible future subtree. Counts and limits stop at that boundary; a
    callback owns any states it creates.
    """
    config = PreflopConfig() if config is None else config
    if not isinstance(config, PreflopConfig):
        raise TypeError("config must be a PreflopConfig.")
    if type(max_public_states) is not int or max_public_states < 1:
        raise ValueError("max_public_states must be a positive integer.")
    if type(max_decision_nodes) is not int or max_decision_nodes < 0:
        raise ValueError("max_decision_nodes must be a nonnegative integer.")

    nodes = {}
    public_states = decision_nodes = fold_terminals = continuations = 0

    def reserve(kind):
        nonlocal public_states, decision_nodes, fold_terminals, continuations
        if public_states >= max_public_states:
            raise ValueError("Preflop tree exceeds the public-state limit.")
        if kind == "decision" and decision_nodes >= max_decision_nodes:
            raise ValueError("Preflop tree exceeds the decision-node limit.")
        public_states += 1
        if kind == "decision":
            decision_nodes += 1
        elif kind == "fold":
            fold_terminals += 1
        else:
            continuations += 1

    def settled(history, contributions):
        reserve("continuation")
        boundary = _continuation(config, history, contributions)
        return continuation_factory(boundary) if continuation_factory else boundary

    def fold(history, contributions, winner):
        reserve("fold")
        return _Terminal("fold", tuple(_clean(value) for value in contributions), winner)

    def build(history, player, contributions, previous_full_raise,
              raises_made, raise_reopened):
        reserve("decision")
        opponent = 1 - player
        committed, other = contributions[player], contributions[opponent]
        actions, children = [], []

        if abs(committed - other) <= _EPSILON:
            check = _Action("check")
            actions.append(check)
            checked_history = history + (check.token,)
            children.append(settled(checked_history, contributions))
            opponent_all_in = (contributions[opponent] >=
                               config.stacks[opponent] - _EPSILON)
            if raises_made < config.max_raises and not opponent_all_in:
                for action in _raise_actions(config, contributions, player,
                                             previous_full_raise, raises_made):
                    updated = list(contributions)
                    updated[player] = action.raise_to
                    increment = action.raise_to - other
                    full_raise = increment + _EPSILON >= previous_full_raise
                    next_full_raise = increment if full_raise else previous_full_raise
                    actions.append(action)
                    children.append(build(history + (action.token,), opponent,
                                          tuple(updated), next_full_raise,
                                          raises_made + 1, full_raise))
        else:
            call_target = min(other, config.stacks[player])
            call_amount = _clean(call_target - committed)
            call_contributions = list(contributions)
            call_contributions[player] = _clean(call_target)
            actions.extend((_Action("fold"),
                            _Action("call", call_amount, _clean(call_target))))
            call_history = history + ("call",)
            if (player == 0 and not history and
                    abs(call_contributions[0] - call_contributions[1]) <= _EPSILON and
                    all(call_contributions[index] < config.stacks[index] - _EPSILON
                        for index in range(2))):
                # The small blind's call is a limp; the big blind retains its
                # check/raise option before a live flop is dealt.
                call_child = build(call_history, 1, tuple(call_contributions),
                                   config.big_blind, raises_made, True)
            else:
                call_child = settled(call_history, tuple(call_contributions))
            children.extend((fold(history + ("fold",), contributions, opponent),
                             call_child))
            opponent_all_in = (contributions[opponent] >=
                               config.stacks[opponent] - _EPSILON)
            if (raises_made < config.max_raises and raise_reopened and
                    not opponent_all_in):
                for action in _raise_actions(config, contributions, player,
                                             previous_full_raise, raises_made):
                    updated = list(contributions)
                    updated[player] = action.raise_to
                    increment = action.raise_to - other
                    full_raise = increment + _EPSILON >= previous_full_raise
                    next_full_raise = increment if full_raise else previous_full_raise
                    actions.append(action)
                    children.append(build(history + (action.token,), opponent,
                                          tuple(updated), next_full_raise,
                                          raises_made + 1, full_raise))

        node = _Node(tuple(history), player, tuple(actions), tuple(children))
        nodes[(player, tuple(history))] = node
        return node

    raw = (_clean(min(config.small_blind, config.stacks[0])),
           _clean(min(config.big_blind, config.stacks[1])))
    all_in = tuple(config.stacks[index] <= raw[index] + _EPSILON
                    for index in range(2))
    try:
        if any(all_in) and any(raw[1 - player] >= raw[player] - _EPSILON
                               for player in range(2) if all_in[player]):
            root = settled((), raw)
        else:
            # The initial full raise increment is the posted big blind.
            root = build((), 0, raw, config.big_blind, 0, True)
        return PreflopTree(root, nodes, config, decision_nodes, fold_terminals,
                           continuations, public_states)
    finally:
        # Recursive closure captures the mutable tree state. Break its cycle on
        # successful construction and on budget/callback exceptions.
        build = None
        settled = None
        fold = None
        reserve = None
