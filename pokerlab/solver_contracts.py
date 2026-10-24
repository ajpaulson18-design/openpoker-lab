"""Immutable request and result contracts for bounded four-street solving."""

from dataclasses import dataclass, field
import json

from .preflop_tree import PreflopConfig
from .river_config import RiverConfig


_ALGORITHMS = frozenset(("vanilla", "dcfr", "cfrplus"))
_TRAVERSALS = frozenset(("recursive", "planned", "public-batched"))
_DIAGNOSTICS = frozenset(("recursive", "public-batched"))
_RESOURCE_MODELS = frozenset(("world", "public-vector"))
_MAX_RUNOUTS = 300_000


@dataclass(frozen=True, slots=True)
class PostflopActions:
    """Complete action abstraction for one postflop stage."""

    bet_sizes: tuple[float, ...] = (0.5,)
    raise_sizes: tuple[float, ...] = ()
    max_raises: int = 0
    include_all_in: bool = True

    def __post_init__(self):
        # RiverConfig is the existing canonical validator and normalizer for
        # action-only stage fields. Its pot/stack values are validation anchors
        # only and are deliberately not retained in this contract.
        normalized = RiverConfig(
            pot=1,
            effective_stack=(1, 1),
            bet_sizes=self.bet_sizes,
            raise_sizes=self.raise_sizes,
            max_raises=self.max_raises,
            include_all_in=self.include_all_in,
        )
        object.__setattr__(self, "bet_sizes", normalized.bet_sizes)
        object.__setattr__(self, "raise_sizes", normalized.raise_sizes)
        object.__setattr__(self, "max_raises", normalized.max_raises)
        object.__setattr__(self, "include_all_in", normalized.include_all_in)

    def to_dict(self) -> dict:
        """Return a fresh JSON-ready action specification."""
        return {
            "bet_sizes": list(self.bet_sizes),
            "raise_sizes": list(self.raise_sizes),
            "max_raises": self.max_raises,
            "include_all_in": self.include_all_in,
        }


@dataclass(frozen=True, slots=True)
class FourStreetSolveRequest:
    """Bounded immutable input for one selected-runout all-streets solve."""

    sb_range: str
    bb_range: str
    runouts: tuple[str, ...]
    preflop_config: PreflopConfig = field(default_factory=PreflopConfig)
    flop_actions: PostflopActions = field(default_factory=PostflopActions)
    turn_actions: PostflopActions | None = None
    river_actions: PostflopActions | None = None
    iterations: int = 1000
    algorithm: str = "vanilla"
    traversal: str = "recursive"
    diagnostics: str = "recursive"
    resource_model: str = "world"

    def __post_init__(self):
        for name in ("sb_range", "bb_range"):
            value = getattr(self, name)
            if type(value) is not str:
                raise TypeError(f"{name} must be a string.")
            if not value.strip():
                raise ValueError(f"{name} must not be blank.")

        if type(self.runouts) is not tuple:
            raise TypeError("runouts must be a tuple of five-card strings.")
        if not 1 <= len(self.runouts) <= _MAX_RUNOUTS:
            raise ValueError("runouts must contain between 1 and 300,000 outcomes.")
        if any(type(runout) is not str for runout in self.runouts):
            raise TypeError("Each runout must be a string.")
        if any(not runout.strip() for runout in self.runouts):
            raise ValueError("Runout strings must not be blank.")

        if not isinstance(self.preflop_config, PreflopConfig):
            raise TypeError("preflop_config must be a PreflopConfig.")
        if not isinstance(self.flop_actions, PostflopActions):
            raise TypeError("flop_actions must be PostflopActions.")
        if self.turn_actions is not None and not isinstance(self.turn_actions, PostflopActions):
            raise TypeError("turn_actions must be PostflopActions or None.")
        if self.river_actions is not None and not isinstance(self.river_actions, PostflopActions):
            raise TypeError("river_actions must be PostflopActions or None.")

        if type(self.iterations) is not int:
            raise TypeError("iterations must be an integer.")
        self._validate_selector("algorithm", self.algorithm, _ALGORITHMS)
        self._validate_selector("traversal", self.traversal, _TRAVERSALS)
        self._validate_selector("diagnostics", self.diagnostics, _DIAGNOSTICS)
        self._validate_selector("resource_model", self.resource_model, _RESOURCE_MODELS)

    @staticmethod
    def _validate_selector(name: str, value: object, allowed: frozenset[str]) -> None:
        if type(value) is not str:
            raise TypeError(f"{name} must be a string.")
        if value not in allowed:
            options = ", ".join(sorted(allowed))
            raise ValueError(f"{name} must be one of: {options}.")

    def to_dict(self) -> dict:
        """Return a fresh JSON-ready receipt without parsing source strings."""
        return {
            "schema_version": "four-street-request-v1",
            "sb_range": self.sb_range,
            "bb_range": self.bb_range,
            "runouts": list(self.runouts),
            "preflop_config": self.preflop_config.to_dict(),
            "flop_actions": self.flop_actions.to_dict(),
            "turn_actions": None if self.turn_actions is None else self.turn_actions.to_dict(),
            "river_actions": None if self.river_actions is None else self.river_actions.to_dict(),
            "iterations": self.iterations,
            "algorithm": self.algorithm,
            "traversal": self.traversal,
            "diagnostics": self.diagnostics,
            "resource_model": self.resource_model,
        }


@dataclass(frozen=True, slots=True, init=False)
class FourStreetSolveResult:
    """Detached complete engine result with semantic and source identities.

    Instances are created only by :meth:`_from_payload`; the public constructor
    is intentionally closed so public construction cannot bypass the envelope's
    serialization and schema checks.
    """

    request: FourStreetSolveRequest
    _payload_json: str

    def __init__(self, *args, **kwargs):
        raise TypeError("FourStreetSolveResult instances are created by solve_four_street().")

    @classmethod
    def _from_payload(cls, request: FourStreetSolveRequest, payload: dict):
        if not isinstance(request, FourStreetSolveRequest):
            raise TypeError("request must be a FourStreetSolveRequest.")
        if not isinstance(payload, dict):
            raise TypeError("The solver payload must be a dictionary.")
        if payload.get("solver_version") != "preflop-strategy-v1":
            raise ValueError("The solver payload has an unsupported solver_version.")
        if payload.get("strategy_schema") != "preflop-strategy-v1":
            raise ValueError("The solver payload has an unsupported strategy_schema.")
        if payload.get("runout_mode") != "conditioned-ordered-selected-runouts":
            raise ValueError("The solver payload has an unsupported runout_mode.")
        try:
            snapshot = json.dumps(payload, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("The solver payload must be finite JSON-serializable data.") from exc

        result = object.__new__(cls)
        object.__setattr__(result, "request", request)
        object.__setattr__(result, "_payload_json", snapshot)
        return result

    def to_dict(self) -> dict:
        """Return a fresh envelope, including a detached complete payload."""
        payload = json.loads(self._payload_json)
        return {
            "schema_version": "four-street-solve-v1",
            "request": self.request.to_dict(),
            "identities": {
                "seats": "sb-button-0-bb-1",
                "scope": "all-streets",
                "numerical_model": "binary64-local-nine-decimal-whole-hand-v1",
                "chance_model": "conditioned-ordered-selected-runouts",
                "range_model": "physical-combo-product-blocker-conditioned-v1",
                "reach_model": "global-joint-law-separated-sequence-reach-v1",
            },
            "source_identity": {
                "entry_point": "pokerlab.preflop_solver.solve_preflop",
                "solver_version": payload["solver_version"],
                "source_revision": None,
                "source_verification": "not-recorded",
            },
            "payload": payload,
        }

    def to_json(self) -> str:
        """Return deterministic finite JSON for the complete result envelope."""
        return json.dumps(self.to_dict(), allow_nan=False, sort_keys=True, separators=(",", ":"))
