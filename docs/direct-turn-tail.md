# Direct original-weight turn tail solver

pokerlab.turn_tail_adapter.solve_turn_tail is a separate opt-in research API for
configured heads-up turn/river games. It materializes the same joint private-hand
and river worlds as the existing public-batched solver and trains alternating
CFR+. Existing solver entry points, defaults, preflop/flop code and frontend
remain unchanged.

The adapter directly accumulates only completed sweeps t > discard, with their
original weight t. It avoids subtraction of two normalized average policies and
does not use module-global patches. This differs from delayed weights t-discard.
It does not apply probability cleanup or infer exact equilibrium from numeric zero.

## Use

    from pokerlab.turn_tail_adapter import solve_turn_tail

    result = solve_turn_tail(
        "Js8d4c2h", "AsAh:0.5,KsKh:1", "AcAd:1,KcKd:0.75",
        config={"pot": 100, "effective_stack": 220,
                "bet_sizes": [0.5], "raise_sizes": [0.5],
                "max_raises": 1, "include_all_in": False},
        iterations=20, discard=10,
    )

The board must contain exactly four cards. Iterations must be an exact integer
from 10 through 10,000 and discard an exact integer in [0, iterations).
River sizing may be configured separately while preserving the original pot
and stack caps. Omitted runouts use the full remaining deck; selected rivers
condition the entire joint game, including private-pair masses.

The output retains postflop-strategy-v1 rows and legal action amounts, with a
new research solver version and fresh direct-tail provenance. It reports the full
requested iteration count, averaged window, triangular weight sum, scheduled
regret/average passes, physical counts, and recomputed value and legal responses.
The materialized public-vector backend is the only supported backend here.

## Admission and arithmetic

All original candidate/world, public-tree and prefix-edge caps remain enforced.
World enumeration and the old world-node training charge use the full requested
iteration count. The adapter additionally admits at most one million information
action slots before allocating policy tables, and checks a separate dense
hand-state envelope:

    max(original hand counts) * public states * (3*T + 3) <= 30,000,000

Both this and the original 30-million world-node charge apply separately, even
when only the last sweep is averaged. For the fixed raised-turn game, T=1500
charges 25,344,000 original world-node units and 27,369,234 dense units. The first
dense-envelope miss is T=1645 at 30,013,164 units; discarding 1644 sweeps does not
admit that request. These are modeled passes, not instruction, elapsed-time or
RSS guarantees. Ranking and preparation retain their existing separate bounds.

At every acting-player row, the average includes that player's own sequence
reach and the original joint marginal for the public prefix. Opponent action
reach is excluded from averaging. Regret updates retain opponent reach and
the established alternating schedule. Every invocation keeps its own tables
and traversal closures. Diagnostics reject nonfinite values, gains or NashConv
and violations of legal response lower bounds.

## Validation scope

Zero-discard policies match the unchanged public-batched CFR+ solver exactly
on the tested small weighted and full-deck cases. Positive windows, including
the final sweep alone, match independently reconstructed own-realization flows
within 1e-11. Independent numeric rules agree on all eight metrics within 1e-9.
A conditioned 14-world case includes an incompatible original hand and unequal
three/four-river private-pair supports.

The local trainer also passes the predeclared Kuhn quality gates at T=1000,
discard=500: independently measured NashConv about 8.02235e-5 and value error
about 4.46108e-9. Exact normalized-policy enumeration of all 64 own-hand
responses verifies containment of -1/18 and the predeclared 1/100 gap gate.
That known-game check does not certify a larger Hold'em abstraction.

Run python -m unittest tests.test_turn_tail_adapter -v and repeat with python -O.
Tests cover finite diagnostic overflow, one training call, full-request
admission, dead-hand indices, concurrent local state, and empty information
tables. A full fixed-game 1500-sweep quality experiment remains separate from
these focused tests; no general tail-window improvement is assumed.

The eleven integrated tests passed normal Python (3.431 seconds) and optimized
Python (3.178 seconds). Four older saved-proof regressions also passed with
the new module present (56.579 seconds), reconstructing the original numeric
tails, exact tails, clean witnesses and full-physical report without training.
