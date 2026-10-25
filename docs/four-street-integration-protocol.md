# Four-street integration v1: staged acceptance protocol

Status: the [literal fixture](../benchmarks/four-street-integration-v1.json) has
passed bounded independent numeric controls under D038 and exact prescribed-policy
controls under D040. The frozen production quality run remains unexecuted.
The Sol-reviewed architecture fixes one coupled game, one complete policy and
one whole-game legal-response gap. Interface or backend agreement alone cannot
satisfy this gate.

## Fixed game and controls

The fixture has two weighted physical hands per player, two flops and shared
hidden turn/river prefixes, blind-aware preflop betting and live action menus
through river. Selected outcomes condition one joint physical law. The exact
support/ledger and coupling fractions in the fixture are analytic predictions
to establish independently, not results fitted from a production solve.

The new numeric adapter independently rebuilds all betting, reveal and terminal
states, preserving global SB/BB identity, fixed preflop origin, local monetary
quantization, refunds and perfect-recall history. It reuses existing independent
numeric-state/ranking utilities read-only; old fingerprinted oracles remain fixed.
Its bounded scope is stricter than the production solver: at most four hands per
player, eight selected outcomes, 32 worlds, 2,048 public states/own-hand rows,
4,096 action slots and depth 32. Admit shape/support before independent ranking.
Case IDs, range expressions, runout strings and history tokens have explicit
length bounds before parsing or indexing. Inputs are snapshotted so later caller
mutation cannot change the numeric case. Live flop template bounds use the same
local monetary quantization as the declared configured game.

The adapter exposes `build_model(case)`, `validate_policy(model, payload)` and
`replay_policy(payload, case)`. Replay validates every independent information row
before calling the unchanged configured floating oracle. Its receipt includes
separate `numeric_counts`; collapsed all-in chance nodes need not match the
production public-state total. The literal independent model has 22 worlds,
1,414 states, 628 decisions, 1,200 information rows, 2,402 action slots and depth 14.

U3 acceptance ran all 15 numeric-control tests normally and with optimized Python.
The combined numeric/interface/legacy suite passed 44 tests in 14.799 seconds.
A separate development T10 vanilla recursive result validated all 1,200 rows;
the largest production-versus-independent scalar gap was
`2.498001805406602e-16`. This control is not the frozen accuracy run. The exact
generic rational evaluator and its known zero/nonzero-gap controls were pending
at that numeric-only milestone.

The [exact evaluator v2](four-street-certificate.md) now passes thirteen focused tests
normally and under optimized Python. The combined certificate/numeric/interface/
legacy suite passes 57 tests (23.329 seconds in the lead's latest control run).
Its all-positive literal forecast is 98,298 under the unchanged 100,000 cap;
the prescribed check/call policy uses 48,577 named entries. Full normalized rows
and per-family runtime/forecast dominance are checked. The exact whole-game
value moves `1/34 -> 5/34` after the one prescribed river-row change, with legal
response values unchanged. Known zero/nonzero gaps, hidden-future cheating,
mixed/zero/subnormal probabilities, fractional money and an independent slow
exact profile replay pass. This accepts control evidence for runner development;
Sol's final mathematical review accepts this scope with separate bounded
structural-preparation receipts. The guarded output formatter also retains exact
large-fraction text without changing global settings. Frozen runner/authenticator
review, clean source authentication and both admissions still precede the
production quality call.

The first U4 development census rejected the unchanged fixture: 118,261 modeled
work exceeds the fixed 100,000 cap. No literal exact policy evaluation or quality
training followed. D039 requires a separately reviewed fused profile/SB-response
traversal, complete familywise accounting and fresh exact controls. Small-game
control success cannot replace the named fixture's pending certificate.

Required pre-training controls include the 22-world exact prior, cumulative
matched ledger `1 -> 2 -> 4 -> 8`, all check/call profile, a single legal river
policy change with a nonzero upstream-value difference, a sure-winner exact-zero
equilibrium control, a nonzero-gap control, hidden-future cheating, short-blind
refunds, fractional monetary boundaries and complete malformed/off-path rejection.
Production rank/tree/utility/evaluation/response authorities must be disabled
during the independent model/replay controls. Normal and optimized Python must
preserve certificate-critical rejection behavior.

## Frozen quality call

After independent controls and the complete exact-audit work forecast pass,
freeze the committed executable, fixture, protocol and full source identities.
The run uses exactly one fixed 1,000-sweep, zero-delay CFR+ call through the new
four-street interface, with public-batched training/diagnostics, public-vector
admission and legacy decision-count tree admission. No early stopping, grouping,
private compaction, sampling, alternative backend or retry is allowed.

The existing engine must admit the entire requested solve before training. The
independent certificate must separately admit its full requested shape, rows,
arithmetic schedule, output and bit envelope before the quality call. A preparation
or capacity failure is retained, with quality unknown. Admission is not a strategy
quality result. The earlier planning-only trainer interception executed zero
training passes and cannot serve as the frozen source/quality receipt.

Save the complete raw returned envelope and its bytes/hash before independent
replay. Keep the original underlying payload unchanged. Reconstruct exact world
mass from the declared input weights/support, convert configured terminal
binary64 constants explicitly to fractions, and normalize each serialized policy
row in exact arithmetic with a complete raw-to-normalized ledger. Audit all four
streets together, summing hidden opponent hands/future reveals before maximization.

Report the exact profile value, both legal best responses, nonnegative gains,
`L=-BR_BB <= V <= U=BR_SB`, NashConv `U-L` and exploitability `(U-L)/2`.
The quality gate is exact-normalized NashConv **<= 1/1000 big blind** (BB is one
chip here). This is the normalized policy's finite-game certificate, not a formal
raw-floating-point interval or proof of unrestricted Hold'em equilibrium.

## Evidence lifecycle

The [single-attempt runner](../scripts/benchmark_four_street_integration.py)
accepts `--expected-source-commit` and an absolute external
`--attempt-directory`. Its source closure includes every committed Python file
under `pokerlab/` and `scripts/`, this protocol, the literal benchmark and the
reused river protocol. It checks the committed and working inventories, clean
status and source hashes around both preparations, claim creation, the sole
solve call and both audits. A fresh directory is exclusive; interrupted attempts
cannot resume. The original facade serialization is flushed and hashed before
any policy validation. The facade's inner unrecorded-source fields remain intact;
the companion claim supplies the actual frozen execution provenance.

The [saved-only verifier](../scripts/verify_four_street_integration_publication.py)
accepts `--directory` and `--expected-index-sha256`. The external index pin is the
SHA256 of the original `report.json` bytes. Before importing mathematical code,
it authenticates that pin, bounded artifact inventory and the frozen Git/current
LF source closure. It checks the full fixed request, raw bytes, admissions and
source checks, then recomputes independent physical support, the complete numeric
receipt and the entire exact certificate, including all off-path rows and the
normalization ledger. It never calls production preparation, solving or training.
Raw source size/hash remains a pinned historical receipt; Git blobs independently
authenticate normalized content and permit a different checkout line ending.

Complete outcomes are `completed-met`, `completed-missed` or
`completed-unknown`. A saved exact capacity failure must reproduce with the
authenticated source; replay cannot promote it to a passed gate. General failures
retain their first error and receipt-backed artifacts, with no quality claim.
Unreceipted partial bytes remain explicitly unauthenticated observations. Test
services are marked `injected-test-services`; publication verification requires
`frozen-production`. Synthetic lifecycle tests do not establish actual training
or a production quality result.

Artifact I/O limits are fixed before the production attempt: 16 MiB for the raw
envelope, 32 MiB for each replay/certificate/source/report JSON, 1 MiB for each
attempt/claim/failure/status JSON, at most 14 files and 256 MiB total. Strict JSON
also limits nesting to 80 and nodes to 1,000,000. These storage/parser limits do
not change the independent mathematical shape, 100,000-work, depth-32 or
65,536-bit limits, or any production admission cap.

Use a fresh external attempt directory and exclusive claim. Admit the complete
literal request before creating the claim. Retain source/fixture/protocol hashes,
clean source status before/after, raw envelope/policy, numeric replay, exact audit,
normalization ledger, requested/executed passes, work/bit receipts and first errors.
Preserve partial results before further validation; never overwrite or retry the
same attempt. Source drift rejects the claim even if numerical checks pass.

A target miss remains a miss. A resource/audit failure leaves its gate unknown.
The lead may autonomously review a separately versioned next experiment or an
integration-specific correction, preserving the original outcome and sources.
It may not silently change the fixture, threshold, iteration budget or old caps.

Publishing a complete run is distinct from passing its quality gate. Only a
verified gate pass supports calling this named four-street game solved to the
declared tolerance. Later support expansion retains this corpus and all earlier
benchmarks, including their misses.
