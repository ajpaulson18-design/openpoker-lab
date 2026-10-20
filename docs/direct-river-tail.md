# Direct original-weight river tail API

`pokerlab.river_tail_adapter.solve_river_tail` is a separate opt-in research API
for a configured heads-up game on a complete five-card board. It prepares the
existing compatible private-hand worlds and legal river tree, then reuses the
local direct original-weight accumulator from the turn tail adapter. All
regrets and average tables belong to that invocation. Existing solver APIs,
shared kernels, defaults and earlier streets remain unchanged.

The average uses completed alternating CFR+ sweeps `t > discard`, weighted by
the original `t`. The acting player's own reach and the fixed private-hand
marginal weight its action flow. Opponent action reach is excluded from
averaging. This differs from the delayed weight `t-discard` and requires no
prefix/full-policy subtraction. Rows with zero own averaged reach may use a
different legal conditional fallback without changing that player's realization
plan. Probability equality at such rows is not a correctness requirement.

## Calling and output

```python
from pokerlab.river_tail_adapter import solve_river_tail

result = solve_river_tail(
    "2c7d9hJsKd", "AsAh:1,3c4c:1", "QsQh:1",
    {"pot": 100, "effective_stack": 300,
     "bet_sizes": [1], "raise_sizes": [],
     "max_raises": 0, "include_all_in": False},
    iterations=1000, discard=500,
)
```

The board must contain exactly five unique cards. `iterations` must be an exact
integer from 10 through 100,000 and `discard` an exact integer in
`[0, iterations)`. Only materialized public-vector CFR+ is supported. A complete
board has no future-card/runout configuration.

Output uses `postflop-strategy-v1` legal row/action metadata with a fresh research
solver version and direct-tail provenance. It reports full requested iterations,
discard, averaged window/count, original triangular weight sum, scheduled regret
and average passes, physical counts and separate resource charges. All eight
profile/response metrics are recomputed for the returned policy. Nonfinite
values, response-bound violations and derived diagnostic overflow reject.

## Admission

Candidate/world enumeration, tree and prefix guards retain full requested `T`.
The original world-node charge `3*T*worlds*visited_decisions` must remain at most
30 million. Before policy-table allocation, information-action slots must be at
most one million and the additional dense hand-state envelope must satisfy:

```text
max(original hand counts) * public_states * (3*T + 3) <= 30,000,000
```

Both charges use full `T` even when only the final sweep is averaged. Original
hand indices are retained after joint private-card blockers; dead original
hands are not renumbered into another holding. Public state/decision and prefix
edge limits remain 250,000 / 10,000 / 250,000. These are modeled admission
charges, not guarantees about every operation, elapsed time or RSS.

An independently counted boundary case uses the example board/ranges, stack
10,000, bet/raise fractions `[0.25,0.5,1]`, and three raises. Its 723 public
states and 242 decisions imply dense work 30,001,608 at `T=6915`, while the old
world charge is only 10,040,580. `discard=6914` must still reject before training.

## Evidence and limits

The scratch feasibility probe used the example one-bet game at `T=1000,D=500`.
Its exact normalized-policy response interval contains the known value 25,
but the tail gap is about 0.105816876 versus the ordinary full average's
0.070565704. Both miss 0.001. Direct accumulation therefore carries no promise
of a convergence improvement for a chosen game or window.

The independent one-bet calculation enumerates literal terminal histories and
all 16 OOP / four IP pure visible-information responses. Each binary64 row is
converted to exact Fractions and normalized by its exact sum before evaluation.
That certificate applies only to this one-bet hand-labeled game. Broader weighted
raised games require separate independent numeric legality and response replay.
No arbitrary-game exact-equilibrium, full-range, performance or RSS claim follows.

Nine integrated tests passed in normal Python (1.189 seconds) and optimized
Python (1.130 seconds). Zero-discard complete row lists match the unchanged
solver exactly in the one-bet and weighted unequal-stack raised games. Positive
windows and the final sweep alone match independent same-trajectory reference
realization flows within an exact Fraction gate of 1e-11; all eight metrics
match independent numeric-rule replay within 1e-9. The explicit zero-own-reach
case permits changed conditional fallbacks while checking zero action flow.

Tests also cover the real 6,915-sweep admission boundary before training,
full original hand counts after blockers, a genuine single-trainer-call spy,
malformed requests, nonfinite diagnostics, illegal response bounds, overflow
in derived gains, and concurrent local-state calls. The independent one-bet
pure-response calculation contains value 25 and explicitly retains the target
miss at T=1000,D=500.

The preceding saved turn direct-tail bundle also reconstructed completely with
seven training entry points disabled after the river module was added (17.524
seconds). Historical policy/report bytes and mathematical verification sources
remain unchanged.

Run `python -m unittest tests.test_river_tail_adapter -v` and repeat with
`python -O`. This source/API slice adds no frozen larger river quality
experiment; such an experiment must separately pin and save the raw policy,
independent audit, complete-call observations and every target outcome.

The subsequent [fixed river experiment](direct-river-tail-experiment.md) defines
that separate evidence bundle for the two historical configured river games.

The [river-only longer-budget extension](direct-river-long-tail.md) preserves
the v1 payload through 10,000 iterations and uses a distinct long-request
version above that threshold. All original work limits remain in force; the
longer admission does not guarantee an accuracy target.
