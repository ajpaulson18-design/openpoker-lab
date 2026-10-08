"""CFR-agnostic strategy interface for configured restricted river games."""
from dataclasses import dataclass, field

from .cards import cards
from .river_config import RiverConfig
from .solver import solve

OOP, IP = "oop", "ip"


@dataclass(frozen=True)
class Action:
    """A public action; amount is added now and raise_to is total commitment."""

    name: str
    amount: float = 0.0
    raise_to: float = field(default=0.0, compare=False)
    history_key: str = field(default="", compare=False)


@dataclass(frozen=True)
class InfoSet:
    """Private hand and public history; use Action.history_key for sized actions."""

    player: str
    hand: str
    history: tuple = ()


class EquilibriumStrategy:
    """Immutable view of one solved configured river action abstraction."""

    def __init__(self, result):
        self._result = result
        self._rows = {}
        self._nodes = {}
        for row in result["strategy"]:
            player = row["player"]
            history = tuple(row["history"])
            hand = "".join(cards(row["hand"], 2))
            key = (player, hand, history)
            self._rows[key] = tuple(row["actions"])
            self._nodes.setdefault((player, history), tuple(row["actions"]))

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

    @property
    def config(self):
        if self._result["config"] is None:
            return None
        return RiverConfig.from_dict(self._result["config"]).to_dict()

    def _resolve_history(self, history):
        history = tuple(history)
        resolved = ()
        for token in history:
            if not isinstance(token, str):
                raise ValueError(f"Invalid public action history: {history}.")
            actions = self._nodes.get((OOP, resolved)) or self._nodes.get((IP, resolved))
            if actions is None:
                raise ValueError(f"No public decision exists after history {resolved}.")
            exact = [action for action in actions if action["history_key"] == token]
            if exact:
                selected = exact[0]
            else:
                # Retain the old unsized names only when they identify one action.
                named = [action for action in actions if action["name"] == token]
                if len(named) != 1:
                    raise ValueError(f"Action {token!r} is ambiguous or illegal after {resolved}.")
                selected = named[0]
            resolved += (selected["history_key"],)
        return resolved

    def _node(self, infoset):
        if infoset.player not in (OOP, IP):
            raise ValueError(f"Unknown player {infoset.player!r}.")
        history = self._resolve_history(infoset.history)
        actions = self._nodes.get((infoset.player, history))
        if actions is None:
            raise ValueError(f"No {infoset.player} decision exists after history {history}.")
        return history, actions

    @staticmethod
    def _public_action(action):
        return Action(action["name"], action["amount"], action["raise_to"],
                      action["history_key"])

    def legal_actions(self, infoset):
        _, actions = self._node(infoset)
        return tuple(self._public_action(action) for action in actions)

    def strategy_at(self, infoset):
        """Return a normalized distribution over legal explicit actions."""
        history, actions = self._node(infoset)
        hand = "".join(sorted(cards(infoset.hand, 2)))
        row = self._rows.get((infoset.player, hand, history))
        if row is None:
            raise ValueError(f"Hand {infoset.hand} is not in the {infoset.player.upper()} range.")
        return tuple((self._public_action(action), action["probability"]) for action in row)


def solve_equilibrium(board, oop_range, ip_range, pot=100, bet=50, iterations=1000,
                      config=None, effective_stack=None, bet_sizes=None,
                      raise_sizes=None, max_raises=0, include_all_in=True,
                      *, algorithm="vanilla"):
    """Solve and wrap the exact configured river action abstraction."""
    result = solve(board, oop_range, ip_range, pot, bet, iterations,
                   config=config, effective_stack=effective_stack,
                   bet_sizes=bet_sizes, raise_sizes=raise_sizes,
                   max_raises=max_raises, include_all_in=include_all_in,
                   algorithm=algorithm)
    return EquilibriumStrategy(result)
