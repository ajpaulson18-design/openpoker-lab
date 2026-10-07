"""Serializable action abstraction for the restricted heads-up river solver."""
from dataclasses import asdict, dataclass
import math

from .analysis import number


@dataclass(frozen=True)
class RiverConfig:
    """Pot-relative river action abstraction.

    ``bet_sizes`` and ``raise_sizes`` contain positive pot fractions. A raise
    fraction is applied to the pot after calling, and describes the additional
    raise increment (not the raise-to amount).
    """

    pot: float = 100.0
    effective_stack: float | tuple = 500.0
    bet_sizes: tuple = (0.5,)
    raise_sizes: tuple = ()
    max_raises: int = 0
    include_all_in: bool = True

    def __post_init__(self):
        pot = number(self.pot, "Pot", .01)
        if isinstance(self.effective_stack, (tuple, list)):
            if len(self.effective_stack) != 2:
                raise ValueError("Effective stack must be one number or an (OOP, IP) pair.")
            stack = tuple(number(value, f"{player} effective stack", .01)
                          for value, player in zip(self.effective_stack, ("OOP", "IP")))
        else:
            stack = number(self.effective_stack, "Effective stack", .01)
        bets = _sizes(self.bet_sizes, "Bet sizes")
        raises = _sizes(self.raise_sizes, "Raise sizes")
        if not bets:
            raise ValueError("At least one first-bet size is required.")
        if type(self.max_raises) is not int or self.max_raises < 0 or self.max_raises > 8:
            raise ValueError("Maximum raises must be an integer from 0 to 8.")
        if type(self.include_all_in) is not bool:
            raise ValueError("include_all_in must be a boolean.")
        object.__setattr__(self, "pot", pot)
        object.__setattr__(self, "effective_stack", stack)
        object.__setattr__(self, "bet_sizes", bets)
        object.__setattr__(self, "raise_sizes", raises)

    @property
    def stacks(self):
        """Effective stack caps ordered as (OOP, IP)."""
        if isinstance(self.effective_stack, tuple):
            return self.effective_stack
        return self.effective_stack, self.effective_stack

    def to_dict(self):
        """Return a deterministic JSON-serializable configuration."""
        result = asdict(self)
        if isinstance(self.effective_stack, tuple):
            result["effective_stack"] = list(self.effective_stack)
        result["bet_sizes"] = list(self.bet_sizes)
        result["raise_sizes"] = list(self.raise_sizes)
        return result

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict):
            raise ValueError("River configuration must be an object.")
        allowed = {"pot", "effective_stack", "bet_sizes", "raise_sizes",
                   "max_raises", "include_all_in"}
        extra = set(values) - allowed
        if extra:
            raise ValueError(f"Unknown river configuration fields: {sorted(extra)}")
        return cls(**values)


def _sizes(values, label):
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{label} must be a sequence of positive pot fractions.")
    try:
        result = tuple(number(value, label, .000000001) for value in values)
    except TypeError as exc:
        raise ValueError(f"{label} must be a sequence of positive pot fractions.") from exc
    if not all(math.isfinite(value) for value in result):
        raise ValueError(f"{label} must contain finite positive fractions.")
    if len(result) > 8:
        raise ValueError(f"{label} supports at most eight configured sizes.")
    return tuple(sorted(set(result)))
