"""CFR-agnostic equilibrium-strategy interface for the restricted river game.

Callers ask for the strategy at an information set and receive an explicit,
normalised distribution over *legal* actions.  Nothing here exposes regrets,
reach probabilities or the solver's internal node letters, so a future
deviation layer can wrap ``EquilibriumStrategy`` without knowing about CFR.

The strategy is an equilibrium approximation only for the exact restricted
game that produced it (see docs/solver-validation.md).
"""
from dataclasses import dataclass
from .cards import cards
from .solver import solve

OOP, IP = "oop", "ip"
# public histories -> (acting player, legal action names)
_NODES = {
    (): (OOP, ("check", "bet")),
    ("check",): (IP, ("check", "bet")),
    ("bet",): (IP, ("fold", "call")),
    ("check", "bet"): (OOP, ("fold", "call")),
}
# (player, history) -> keys of the solver's per-hand rows; second key is the
# probability of the aggressive/continuing action (bet or call).
_ROW_KEYS = {(OOP, ()): "bet", (IP, ("check",)): "bet_after_check",
             (IP, ("bet",)): "call", (OOP, ("check", "bet")): "call_after_check"}


@dataclass(frozen=True)
class Action:
    """An explicit action; ``amount`` is the chips added (0 for check/fold)."""
    name: str
    amount: float = 0.0


@dataclass(frozen=True)
class InfoSet:
    """A player's private hand (e.g. 'AsAh') plus the public action history."""
    player: str
    hand: str
    history: tuple = ()


class EquilibriumStrategy:
    """Immutable view of a solved restricted river game."""

    def __init__(self, result):
        self._result = result
        self._bet = float(result["bet"])
        self._rows = {OOP: {r["hand"]: r for r in result["oop"]},
                      IP: {r["hand"]: r for r in result["ip"]}}

    @property
    def exploitability(self):
        return self._result["exploitability"]

    @property
    def nash_conv(self):
        return self._result["nash_conv"]

    @property
    def iterations(self):
        return self._result["iterations"]

    @property
    def scope(self):
        return self._result["scope"]

    def legal_actions(self, infoset):
        _, names = self._node(infoset)
        return tuple(Action(n, self._bet if n in ("bet", "call") else 0.0) for n in names)

    def strategy_at(self, infoset):
        """Return ``((Action, probability), ...)`` over legal actions only."""
        player, names = self._node(infoset)
        hand = "".join(sorted(cards(infoset.hand, 2)))
        row = self._rows[player].get(hand)
        if row is None:
            raise ValueError(f"Hand {infoset.hand} is not in the {player.upper()} range.")
        aggressive = min(1.0, max(0.0, row[_ROW_KEYS[(player, tuple(infoset.history))]]))
        probabilities = (1 - aggressive, aggressive)
        return tuple((Action(n, self._bet if n in ("bet", "call") else 0.0), p)
                     for n, p in zip(names, probabilities))

    def _node(self, infoset):
        key = tuple(infoset.history)
        node = _NODES.get(key)
        if node is None or node[0] != infoset.player:
            raise ValueError(f"No {infoset.player} decision exists after history {key}.")
        return node


def solve_equilibrium(board, oop_range, ip_range, pot=100, bet=50, iterations=1000):
    """Solve the restricted river game (no node locks) and wrap the result."""
    return EquilibriumStrategy(solve(board, oop_range, ip_range, pot, bet, iterations))
