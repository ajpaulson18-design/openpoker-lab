# Independent whole-game four-street certificate

The development certificate in `scripts/four_street_certificate.py` evaluates
one complete serialized policy for the bounded game defined by the
[integration protocol](four-street-integration-protocol.md). It does not train a
policy. The [unified solver interface](four-street-solver.md) still delegates to
the existing single-root engine; this certificate independently checks the
resulting physical game and legal responses across all four streets.

`forecast_exact(case)` builds a fresh independent numeric model and reports its
complete probability-independent work forecast. `evaluate_exact(case, payload)`
builds its own fresh model, admits the forecast, validates every policy row and
returns exact rational metrics, the complete normalization ledger and policy,
and resource receipts. Neither function accepts a caller-built graph or a cache.

The numeric model reuses existing independent monetary/state and best-five
ranking utilities read-only. Production tree, payoff, ranking, evaluation and
best-response functions do not determine the certificate. Shared range/card
grammar is explicit; the independently constructed joint physical masses retain
blockers and globally conditioned selected outcomes. Future cards and opposing
private hands remain hidden when choosing a response.

## Rational policy and response semantics

Each serialized binary64 action probability is converted to its exact rational
image and divided by that row's exact sum. Every raw fraction, row sum,
normalized fraction and adjustment is retained. All physically valid information
rows are checked, including rows unreachable under the current policy. The
certificate applies to this explicitly normalized policy. The mapping hash is
named `input_policy_canonical_sha256`; a frozen runner must separately hash the
original returned file bytes.

An SB response group contains one SB own hand and one complete visible history.
World masses include the joint prior and BB sequence reach. A fused traversal
returns both SB's legal best response and the supplied profile's value. Terminals
share one exact weighted utility sum; public reveals and BB actions sum their
continuations. At SB nodes, the response maximizes across every legal action,
while the profile mixes those children using the fixed own-hand policy row.
Those mixtures introduce SB reach exactly once. Zero-probability SB actions
remain available to the response. A separate own-hand grouped traversal computes
BB's best response; neither traversal may maximize separately by hidden world.

Terminal chip constants use the independent configured binary64 monetary model
before rational conversion. They are not exact-decimal replacements. The report
requires `L = -BR_BB <= V_SB <= U = BR_SB`, nonnegative unilateral gains,
`NashConv = U-L` and exploitability `(U-L)/2`. The literal fixture's quality target
is NashConv at most `1/1000` big blind. A finite-game certificate does not imply
unrestricted Hold'em equilibrium or a general convergence guarantee.

## Resource and evidence boundaries

The exact arithmetic schedule retains the fixed 100,000-work and 65,536-bit
Fraction limits, plus depth 32. Its all-positive structural forecast covers
normalization, full ledger/output, both legal responses and the fused profile
channel. Runtime counters must fit the forecast separately for every named
family; unknown families are rejected. Independent model construction, input
parsing/hashing and floating replay have separate bounded preparation receipts.
Named work is a model of specified entries and arithmetic, not elapsed time or
RSS. Unknown trained denominators can still exhaust the Fraction-width guard.

D039 preserves the first evaluator's rejected 118,261-work census. The v2
algorithm shares profile and SB response arithmetic; it does not raise the cap,
change the fixture or omit ledger rows. Current exact-control acceptance and the
frozen production-run status are recorded in the integration protocol and
[decision register](decisions/DECISION_LOG.md). A capacity failure leaves the
quality gate unknown; a valid certificate above target remains a miss.
