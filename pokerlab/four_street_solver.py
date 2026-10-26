"""Thin immutable-contract facade for the existing all-streets solver."""

from . import preflop_solver
from .solver_contracts import FourStreetSolveRequest, FourStreetSolveResult


def solve_four_street(request: FourStreetSolveRequest, *,
                      native_executable=None) -> FourStreetSolveResult:
    """Delegate one bounded request to the existing selected-runout solver.

    The complete engine payload is snapshotted as finite JSON in the returned
    envelope. That adds serialization and allocation work beyond the legacy
    trainer's modeled loop bounds; this facade makes no performance claim.
    """
    if not isinstance(request, FourStreetSolveRequest):
        raise TypeError("request must be a FourStreetSolveRequest.")

    native_options = ({} if native_executable is None else
                      {"native_executable": native_executable})
    payload = preflop_solver.solve_preflop(
        request.sb_range,
        request.bb_range,
        request.preflop_config,
        runouts=request.runouts,
        flop_config=request.flop_actions.to_dict(),
        turn_config=(None if request.turn_actions is None
                     else request.turn_actions.to_dict()),
        river_config=(None if request.river_actions is None
                      else request.river_actions.to_dict()),
        postflop_scope="all-streets",
        iterations=request.iterations,
        algorithm=request.algorithm,
        traversal=request.traversal,
        diagnostics=request.diagnostics,
        resource_model=request.resource_model,
        **native_options,
    )
    return FourStreetSolveResult._from_payload(request, payload)
