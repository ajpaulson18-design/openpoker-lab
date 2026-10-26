# Selected-runout operator four-street foundation

Owner direction, October 26, 2026: Sol leads architecture, Terra challenges
mathematics and resource claims, and Luna implements. This follows the
[foundation audit](foundation-first-audit.md) and
[execution record](foundation-first-execution.md). The overall goal remains open.

## Implemented boundary

`pokerlab.selected_operator_solver.solve_four_street_operator(request)` takes
the existing immutable `FourStreetSolveRequest` with public-batched training and
diagnostics and public-vector resources. It returns the complete replay-compatible
`preflop-strategy-v1` payload. It shares the original betting builders,
positive-pot translation, CFR/CFR+/DCFR kernels, averaging schedule and
visible-information best-response diagnostics. Original defaults and historical
benchmark source files are unchanged.

The provider retains hands, weights and masks plus selected board tokens/masks:
O(H0 + H1 + R) input storage, with one board's per-hand rank vectors cached.
It stores no complete private-pair/board worlds or prefix/private-pair edges.
Queries reduce one pair's compatible board masses at a time. The O(R) public
topology projection has dummy hand/mass fields used only by the shared tree
builder for board tokens. Actual support and work are established separately.

The public tree, information-set rows, regret/average arrays and serialized
policy remain explicit. The compatible output also emits O(P) private-pair
probabilities, counted separately. The **whole solver does not have linear total
memory**. There is no full-deck, sampled, delayed-average or native operator mode.

## Mathematical and game contracts

Each compatible private pair and selected board has the reference binary64
raw range product divided by the constant physical runout count. A global
`fsum` normalizer integrates every compatible pair/board occurrence. Each
normalized occurrence passes the original positive-normal mass guard. Absolute
prefix mass sums occurrences extending that prefix; there is no local
renormalization. Unequal blockers change preflop pair probabilities. The
full-deck prefix research operator cannot substitute for this selected law.

Pair order and within-pair binary64 `+=` reductions precede payoff/reach
multiplication, matching the reference. Equivalent real-arithmetic reductions
can differ at near-zero regret branches; no general bitwise equivalence is
claimed. Exact conditioning of finite support is distinct from binary64 training
and exact rational saved-policy certification.

Terminal vectors contain joint chance mass once and opponent sequence reach
once. Own reach enters averaging with the own-hand prefix marginal. SB/button
is player zero; BB is player one. Public chance children sum without a second
chance multiplier. Early all-in terminals integrate still-hidden boards.
Information-set keys contain only own hand and visible public history.

The existing finite betting menus, local nine-decimal monetary quantization,
stack/refund and short-all-in semantics remain. No omitted action, rake or
real-world rules expansion is implied. See [model boundary](preflop-solver.md)
and [independent numerical rules](four-street-integration-protocol.md).

## Admission and next bottlenecks

`census_four_street_operator(request)` performs bounded rank-free preparation.
It reports worlds represented, zero stored complete worlds/edges, public states,
decisions, terminals, information sets, action slots, regret/average scalar
slots and pair-output capacity. Existing candidate/world/iteration and public
tree/template limits remain. Support scans receive incremental preparation
admission. A separate conservative 500-million requested scan envelope is
checked before training/ranking. It includes prefix filtering, candidate pairs,
board checks, support/output queries and public-topology filtering. Counts are
logical entries, not instructions, allocation bytes or RSS guarantees.

Next limiting structures are explicit public histories and per-hand action
storage, plus repeated mass/rank queries. The measurement runner varies selected
support and stack depth. Exact compression and native operator integration each
need a measured independent acceptance; prior isolated native speedups do not
activate them automatically.

## Validation and evidence protocol

Tests compare complete policies and metrics with the original 22-world game and
weighted/shared-prefix, tie, raised, short-stack and blind-all-in controls across
vanilla CFR, DCFR and CFR+. Tripwires forbid complete-world enumeration and
prefix-edge materialization on the new production path. Independent tests use
physical cards, exact fractions, a separate best-five ranker and asymmetric
reaches. Complete serialized policies are replayed under independent numeric
rules and legal own-hand best responses.

Run `python -B -m scripts.benchmark_selected_operator --output <fresh-external-dir>`
from clean committed source. It retains three complete untraced calls and one
allocation-traced call per backend in fresh processes. Complete-call timing
includes preparation, training, diagnostics and serialization-ready payloads.
Traced timing includes instrumentation. Process lifetime peak working set
includes interpreter/imports; Python traced allocation is measured separately.

A manifest pins raw measurements before replay. Saved-only verification requires
its externally supplied SHA-256, checks bytes before parsing and after mathematics,
and checks clean source/HEAD throughout. Existing audits are compared, never
overwritten. Numeric and v3 rational certificates cover sample zero of each
backend; all sample bytes are authenticated. Low-iteration quality misses remain
in evidence. This is a representation milestone, not commercial accuracy proof.

From the original clean measurement revision:

```text
python -B -m scripts.benchmark_selected_operator --verify-saved <directory> --expected-manifest-sha256 <published-digest>
```

Results, commands and publication status are recorded after execution.
