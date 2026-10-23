# Second-board flop equivalence audit

The [fresh reference](flop-second-board-reference.md) independently prepared
the fixed `7c8d9h` weighted game and measured 13 turn classes, 17 river
signatures and 170 candidate aggregate worlds. This separate no-training audit
must establish joint-mass, complete numeric tree and own-hand response
equivalence before class training on that board. First-board proof and solver
sources remain unchanged.

## Fixed scope and full admission

The [protocol](../benchmarks/flop-second-board-equivalence-v1.json) fixes one
fresh physical model, the same literal ranges/global blocker-conditioned
priors, pot 10, stacks 5 each, half-pot bets, no raises and no explicit all-in
sizing. It authenticates the saved reference only after full batch admission.
Fresh preparation counts and bounds rank calls at 11,880, and the complete
new physical world/tree hashes must match that reference. The original
`2c3d4h` anchors are not authorities for this proof.

The requested batch includes ten complete model-proof passes: initial model
construction, entry/exit validation for four controls and final validation
after two negative projections. Each pass reserves 250,000 physical tree
input nodes, 250,000 compact tree output nodes, 100,000 partition items,
5,940 physical worlds, 170 aggregate worlds and at most 33 all-action path
states per world. Compact tree and policy dimensions are measured, rather
than inherited from the first board. Physical or compact row tables may have
at most 20,000 own-hand information sets.

Eight exact metric calls and four separate numeric replays reserve 4,771,800
world-node terms for profile and both responses. At most 100 expected-row
tables reserve 4,000,000 row/action slots. Combined with the ten proof-pass
reservations, the named total is 16,849,200 under a 20-million cap. Reversible
wrappers count these call families and reject excess before dispatch.
These are named families and conservative reservations, not a count or bound
of every internal loop, arithmetic operation, allocation, runtime or RSS.

The complete request also reserves 49 named dependency files at 2 MiB each,
an index at 2 MiB and six lossless policy files, each at most 64 MiB raw and
16 MiB compressed (384/96 MiB aggregate). The existing streaming output
helpers enforce those byte bounds. Output must be a new directory outside
the measured checkout. No retry, replacement or discarded observation is
allowed; original errors, partial counters, policies and metrics are retained.
If gzip serialization fails, one additional raw-JSON fallback of at most 64 MiB
may retain the available policy without rerunning an audit. The batch still
fails and stops. If both output paths fail, their errors/partial paths are
recorded and the available full policy is retained in the returned Python API
report, in memory. The bounded index explicitly marks it as not durably saved
and omits that large in-memory value. No successful persistence claim is made
for an unavailable output device; the CLI reports the failed batch.

## Independent mass and full-tree checks

The pure-data auditor validates every legal ordered future deck, canonical
private pair, exact positive mass, sign type, duplicate/blocker condition and
global/pair marginal. Both numerator and denominator are bounded before
arithmetic. It checks complete unique class membership, explicit absent-pair
signatures, exact turn posterior vectors, river-signature multiplicities and
complete per-turn bijective transports. Every aggregate class world must
retain original joint support, exact mass/sign and physical multiplicity.
A separate candidate rebuild authenticates descriptive fields after these
independent checks; its candidate-only/provenance flags stay unchanged.

The tree auditor compares every mapped physical descendant subtree across
both reveal layers, including public histories, boards, players, all numeric
action fields, terminal contributions and fold winners. It derives each
information key from the acting player's own hand and visible public history.
No opponent private hand or hidden future card enters that key. Full model
reconstruction detects changes before and after each positive control.

## Policies and unrestricted responses

The four positive controls are check-call, bet-fold, across-class-varying and
zero-reach. They retain every physical row and both action probabilities,
including zero-reach rows. Lift/project must preserve every binary64 value
bitwise; no averaging of physical probabilities is permitted. Across-class
variation is valid; variation between physical card members of one class is
invalid.

The unchanged generic exact metric routine is reused with this fixed pot-10
game: terminal payoffs use its 5-chip half-pot constant. It computes a rational
profile and each unrestricted response separately by the responder's own
private hand. Hidden opponent hands and future cards sum before maximization.
All eight compact and full physical metrics must agree exactly. The separate
independent physical numeric replay must agree within `1e-10` chips.

Two intentionally invalid policy copies must reject projection: one changes
a single physical card member to `(0.75, 0.25)` within a shared compact row;
the other uses `(1.0, 2**-54)`, which fails exact rational normalization even
when a floating sum rounds to one. Complete invalid policies and rejection
errors are saved. Their metric headers deliberately remain from the original
zero-reach policy; they are negative projection controls, not solver outputs.

## Provenance and current status

The complete 41-entry production-authority guard stays zero. Source recording
requires identical clean committed HEAD/status and all 49 named LF hashes
before and after. All additions are project-owned standard-library research
code. No published executable, shared turn/river kernel, production/default,
Coach workstream or third-party source/dependency is changed.

The current implementation has synthetic tests for mass/transport tampering,
both reveal layers, public/private information, exact response ordering,
bitwise policy constancy and error restoration. No real second-board
equivalence batch has run yet. No new-board class policy has been trained.
The final source and complete protocol must be reviewed and frozen first.
