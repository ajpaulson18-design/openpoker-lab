"""Public betting-tree construction for configured river abstractions."""
from dataclasses import dataclass


OOP, IP = 0, 1
_EPSILON = 1e-9


def _clean(value):
    value = round(float(value), 9)
    return 0.0 if value == 0 else value


def _amount_label(value):
    return format(_clean(value), ".9f").rstrip("0").rstrip(".")


@dataclass(frozen=True)
class _Action:
    name: str
    amount: float = 0.0
    raise_to: float = 0.0
    full_raise: bool = False

    @property
    def token(self):
        if self.name in {"bet", "raise", "all_in"}:
            return f"{self.name}@{_amount_label(self.raise_to)}"
        return self.name


@dataclass
class _Node:
    history: tuple
    player: int
    actions: tuple
    children: tuple


@dataclass(frozen=True)
class _Terminal:
    kind: str
    contributions: tuple
    winner: int | None = None


def _add_action(actions, name, target, committed, stack, full_raise=False):
    target = _clean(min(stack, max(committed, target)))
    if target <= committed + _EPSILON:
        return
    if target >= stack - _EPSILON:
        name = "all_in"
    if any(abs(existing.raise_to - target) <= _EPSILON for existing in actions):
        return
    actions.append(_Action(name, _clean(target - committed), target, full_raise))


def _opening_actions(config, committed, total_pot, player):
    stack = config.stacks[player]
    actions = []
    for fraction in config.bet_sizes:
        target = committed + fraction * total_pot
        _add_action(actions, "bet", target, committed, stack)
    if config.include_all_in:
        _add_action(actions, "all_in", stack, committed, stack)
    return tuple(sorted(actions, key=lambda action: action.raise_to))


def _raise_actions(config, contributions, player, previous_full_raise, raises_made):
    committed = contributions[player]
    opponent = contributions[1 - player]
    call_amount = opponent - committed
    call_target = opponent
    max_target = config.stacks[player]
    minimum_target = opponent + previous_full_raise
    pot_after_call = config.pot + sum(contributions) + call_amount
    actions = []
    if max_target <= call_target + _EPSILON:
        return ()
    for fraction in config.raise_sizes:
        requested_target = call_target + fraction * pot_after_call
        target = requested_target
        if target < minimum_target:
            target = minimum_target
        if target > max_target:
            target = max_target
        increment = target - call_target
        is_full = increment + _EPSILON >= previous_full_raise
        if is_full:
            _add_action(actions, "raise", target, committed, max_target, True)
        elif requested_target + _EPSILON >= max_target or minimum_target > max_target:
            _add_action(actions, "all_in", max_target, committed, max_target, False)
    if config.include_all_in and max_target > call_target + _EPSILON:
        all_in_increment = max_target - call_target
        _add_action(actions, "all_in", max_target, committed, max_target,
                    all_in_increment + _EPSILON >= previous_full_raise)
    return tuple(sorted(actions, key=lambda action: action.raise_to))


def _terminal_value(terminal, sign, pot):
    """Return OOP's zero-sum payoff after returning any unmatched excess."""
    matched = min(terminal.contributions)
    if terminal.kind == "fold":
        winner_sign = 1 if terminal.winner == OOP else -1
        return winner_sign * (pot / 2 + matched)
    return sign * (pot / 2 + matched)


def _build_tree(config, *, starting_history=(), starting_contributions=(0.0, 0.0),
                showdown_factory=None):
    """Build one fresh-street tree; optional factory handles settled showdowns.

    The callback receives the settled public history and contribution tuple.
    It may return any terminal/chance subtree understood by a solver kernel.
    ``starting_history`` is a prior-street public-history prefix. Betting state
    starts fresh: OOP acts first and no checks or raises have occurred yet.
    """
    node_count = 0
    starting_history = tuple(starting_history)
    starting_contributions = tuple(_clean(value) for value in starting_contributions)
    if len(starting_contributions) != 2:
        raise ValueError("Starting contributions must contain OOP and IP amounts.")

    def settled(history, contributions):
        contributions = tuple(contributions)
        if showdown_factory is not None:
            return showdown_factory(tuple(history), contributions)
        return _Terminal("showdown", contributions)

    def build(history, player, contributions, previous_full_raise, raises_made,
              raise_reopened, checks):
        nonlocal node_count
        if contributions[player] >= config.stacks[player] - _EPSILON:
            return settled(history, contributions)
        node_count += 1
        if node_count > 10_000:
            raise ValueError("Configured action tree exceeds 10,000 public nodes.")
        opponent = 1 - player
        committed, other = contributions[player], contributions[opponent]
        if abs(committed - other) <= _EPSILON:
            check = _Action("check")
            checked_history = history + (check.token,)
            if checks == 1:
                check_child = settled(checked_history, contributions)
            else:
                check_child = build(checked_history, opponent, contributions,
                                    previous_full_raise, raises_made, raise_reopened, checks + 1)
            actions = [check]
            children = [check_child]
            for action in _opening_actions(config, committed,
                                           config.pot + sum(contributions), player):
                next_contributions = list(contributions)
                next_contributions[player] = action.raise_to
                actions.append(action)
                children.append(build(history + (action.token,), opponent,
                                      tuple(next_contributions), action.amount, 0, True, 0))
        else:
            call_amount = other - committed
            actual_call = min(call_amount, config.stacks[player] - committed)
            call_contributions = list(contributions)
            call_contributions[player] = committed + actual_call
            actions = [_Action("fold"), _Action("call", _clean(actual_call),
                                               call_contributions[player])]
            children = [_Terminal("fold", contributions, opponent),
                        settled(history + ("call",), call_contributions)]
            if raise_reopened and raises_made < config.max_raises and \
                    other < config.stacks[opponent] - _EPSILON:
                for action in _raise_actions(config, contributions, player,
                                             previous_full_raise, raises_made):
                    next_contributions = list(contributions)
                    next_contributions[player] = action.raise_to
                    actions.append(action)
                    increment = action.raise_to - other
                    full_raise = increment + _EPSILON >= previous_full_raise
                    next_full_raise = increment if full_raise else previous_full_raise
                    children.append(build(history + (action.token,), opponent,
                                          tuple(next_contributions), next_full_raise,
                                          raises_made + 1, full_raise, 0))
        return _Node(history, player, tuple(actions), tuple(children))

    return build(starting_history, OOP, starting_contributions, 0.0, 0, True, 0), node_count
