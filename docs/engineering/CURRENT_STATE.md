# Current engineering state

The [unified four-street interface](../four-street-solver.md) adds an immutable
request and complete-result envelope around the existing single-root all-streets
preflop solver. It preserves its kernels, histories, joint chance law, numerical
rules and admission. This is the first boundary milestone under D036's autonomous
integration priority, not a new full-deck capability or exact quality certificate.
The [integration plan](../unified-solver-integration.md) defines the remaining
whole-game corpus/certificate and later expansion work.

The [second-board flop reference](../flop-second-board-reference.md) is a
separate no-training preparation for `7c8d9h`. Its planner and bounded harness
completed one frozen physical batch: 5,940 worlds, 30,812 public states and
13/17/170 candidate turn/river/world dimensions. Full saved views and fresh
hashes are retained; no new-board equivalence or training is claimed. Original
fixed-board evidence remains specific to `2c3d4h`, and fresh full equivalence
is required before new-board training.

The [separate second-board equivalence implementation](../flop-second-board-equivalence.md)
completed its frozen no-training physical/control batch: full joint-mass and
numeric subtree checks, all four exact compact/unrestricted response controls
and both intended projection rejections passed. Derived compact dimensions are
170 worlds, 1,270 states and 608 own-hand rows; all raw policies/receipts are
retained. These control results establish no trained strategy or convergence
target outcome.

The equivalence publication is now merged through
[PR #213](https://github.com/ajpaulson18-design/openpoker-lab/pull/213): all 49
focused tests, clean saved-data authentication and all six Python CI jobs passed.
The separate [second-board CFR+ pilot](../flop-second-board-cfrplus.md) stopped
after T140 because its result-schema check incorrectly excluded numeric replay
audit metadata. The failed attempt retains raw/normalized/full policies,
identical compact/physical exact metrics, zero authority counters and clean
sources. T560 never ran; the quality-gate field stays null. This is not a
validated training interface or completed verified policy. The frozen v1 source
and failure remain preserved for a separate reviewed correction.

The [replay boundary v2](../flop-second-board-cfrplus-replay-v2.md) stages that
correction as separate files/protocol. It validates and retains all thirteen
replay fields before exposing the eight metrics expected by v1, restoring the
callable and preserving exact-once instrumentation on every exit. Its one frozen
batch completed both exact/numeric/model audits without errors: T140 retained
NashConv 0.014166984012911272 (miss), and T560 reached 0.0016464625267553663
(pass against 0.005). Full policies, all replay metadata, source/guard receipts
and the earlier failure are retained. Saved-data publication authentication and
final-head CI remain separate; no unrestricted NLHE or general convergence claim
follows from these two finite-game observations.

Current source snapshot: merged main [`46e142be8e9585005e5de70bb32bf4a76f731a1c`](https://github.com/ajpaulson18-design/openpoker-lab/commit/46e142be8e9585005e5de70bb32bf4a76f731a1c) (Oct. 13, 2026). This is a source/documentation update only; it does not report a test run performed for this snapshot. The original Oct. 8–9 knowledge audit at `65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce` is retained as historical evidence in [the transfer validation record](KNOWLEDGE_TRANSFER_VALIDATION.md).

OpenPoker Lab is a standard-library Python 3.11+ research app with a plain JavaScript client. Its implemented surface includes weighted Hold'em range parsing and hand evaluation, sampled multiway equity and exact heads-up river equity, one-decision EV estimates, a locally persisted opponent tendency model, finite heads-up river/postflop solvers, bounded heads-up preflop models, a separate fixed-flop checkdown game, hand practice, deterministic explanations, optional coaching and a loopback HTTP server. README.md, AGENTS.md and the detailed solver references define the limits: no unrestricted no-limit equilibrium, no multiway equilibrium, and no full-deck preflop solution with later-street betting.

## Implemented surface and boundaries

| Area | Implemented at baseline | Key constraints |
| --- | --- | --- |
| Cards and ranges | `pokerlab/cards.py`: card parsing, weighted range expansion, blocker removal and best-five hand ranking | Range tokens and override behavior are described in README.md. |
| Equity | `pokerlab/equity.py`: seeded Monte Carlo for one to five opponents; exact weighted enumeration for a heads-up five-card board | Monte Carlo interval is a normal-approximation sampling interval, not range uncertainty. Multiway draws use independent weighted draws with joint rejection on collisions. |
| Decision analysis | `pokerlab/analysis.py`: fold/call or check/bet one-decision EV using supplied ranges and fold rate | No rake, raises, stack caps, or subsequent betting. Pre-river results are checkdown estimates. The default comparison's 45% fold rate is illustrative, not equilibrium. |
| Opponent observations | `pokerlab/models.py`: independent Beta-prior tendencies, explicit opportunity counts, street/context filtering, SQLite persistence, immutable snapshots and legacy reads | Aggregate tendencies do not identify hidden-card ranges or hand-specific action frequencies. Showdown bluff evidence is selected and biased. |
| River solving | `pokerlab/solver.py`, `restricted_solver.py`, `river_tree.py`, `cfr.py`, and `equilibrium.py`: exact compatible private-hand traversal over a configured finite action tree; vanilla CFR default and optional DCFR | Fixed-board, heads-up, supplied ranges and bounded sizes/stack/depth. Legacy fixed-bet entry remains a compatibility path. No future street or unrestricted NLHE. Node locks make the unrestricted best-response gap a profile exploitability diagnostic, not a locked-game convergence certificate. |
| Postflop solving | `pokerlab/postflop_solver.py`, `turn_solver.py`, `planned_cfr.py`, `public_cfr.py`, `matrix_free_turn.py`: finite flop/turn/river starts with exact configured chance and optional Python traversal paths | Resource caps constrain ranges and trees. Selected runouts condition and renormalize the whole joint game. Matrix-free turn solving is a separate optional API. No unrestricted sizing or multiway equilibrium. |
| Preflop and fixed-flop | `preflop_tree.py`, `preflop_solver.py`, `flop_checkdown_solver.py`, `flop_checkdown_worlds.py`: bounded blind-aware heads-up trees, selected-outcome preflop solving and isolated fixed-flop forced-checkdown integration | The existing selected-outcome preflop API rejects full-deck chance. Direct fixed-flop solving integrates all legal future cards only under forced checkdown, not later-street decisions. No multiway equilibrium. See [preflop solver](../preflop-solver.md) and [direct fixed-flop solver](../direct-flop-checkdown.md). |
| Specialized river paths | `matrix_free_river.py`, `ranked_river.py`, `cfr_plus.py` | Optional library paths have distinct action, utility and admission constraints; see [matrix-free river](../matrix-free-river.md), [ranked river](../ranked-river.md) and [CFR+ validation](../turn-river-quality.md). |
| Hand practice | `pokerlab/game.py`, `practice.py`, `decision_study.py`, and `server.py`: 2–6 seat hand mechanics, side pots, review and decision capture | Sandbox state is in memory; local observations and reports are persisted. Capture and persistence adapters are implemented in `practice.py` and `server.py`; there is no `decision_capture.py` module. Opponent cards are kept out of the human-facing decision serialization. |
| Explanations/coaching | `contracts.py`, `explanations.py`, `personalities.py`, `coach_*`, `situation_teaching.py`: structured facts, deterministic prose and local voices; optional external plan selector and bounded multi-turn coach | The external provider selects a validated reply plan; deterministic local rendering supplies the response. External AI is explicitly opt-in and allowlisted. See canonical coaching docs below. |
| HTTP/browser | `server.py` and `pokerlab/web/`: JSON endpoints, static interface and local session state | Server is loopback-only with Host/Origin checks, JSON mutation boundaries, concurrency controls and restrictive CSP. It is not an authenticated public service. |

## Validation evidence and its status

Validation statements have different evidentiary status and should not be conflated:

* **Implemented checks** are executable tests/scripts present in the repository. Their existence does not establish that they passed at this baseline or in a particular environment.
* **Historical documented runs** are claims recorded in docs or benchmark artifacts for their stated source revision, Python version, fixtures and machine. They are not a fresh run of the current source snapshot unless the record says so.
* **Audit activity** here was source and documentation inspection only. No test command was run for this audit; no pass claim is made.

The source tree includes unit tests under `tests/` and validation/benchmark scripts under `scripts/`. Relevant map:

| Concern | Executable evidence in repository | Canonical detailed reference |
| --- | --- | --- |
| Evaluator, range parsing, equity, EV, game settlement | `tests/test_core.py`; `scripts/validate_evaluator.py` | README.md, “Tests” and “Range notation” |
| River CFR formulas, exact best responses, strategy interface | `tests/test_solver_validation.py`, `tests/test_solver_variants.py`, `tests/test_configurable_solver.py`; `scripts/validate_solver.py` | `docs/solver-validation.md`, `docs/configured-river-validation.md` |
| Turn/flop physical worlds, serialized policy replay, stack/chance semantics | `tests/test_turn_solver.py`, `tests/test_postflop_solver.py`, `tests/test_public_postflop.py`, `tests/test_postflop_budget.py` | `docs/turn-river-validation.md`, `docs/postflop-validation.md`, `docs/public-batched-cfr.md` |
| Bounded preflop and fixed-flop games | `tests/test_preflop_solver.py`, `tests/test_preflop_validation.py`, `tests/test_preflop_public_batched.py`, `tests/test_preflop_vector_budget.py`, `tests/test_flop_checkdown_solver.py`, `tests/test_flop_checkdown_worlds.py` | `docs/preflop-betting.md`, `docs/preflop-solver.md`, `docs/preflop-public-batched.md`, `docs/preflop-vector-resources.md`, `docs/preflop-flop-checkdown.md`, `docs/direct-flop-checkdown.md` |
| Optional matrix-free and ranked river paths | `tests/test_matrix_free_river.py`, `tests/test_matrix_free_turn.py`, `tests/test_ranked_river.py` | `docs/matrix-free-river.md`, `docs/matrix-free-turn.md`, `docs/ranked-river.md` |
| Planned/public traversal lifecycle and agreement | `tests/test_planned_cfr.py`, `tests/test_cfr_lifetime.py`, `tests/test_public_cfr.py` | `docs/planned-traversal.md`, `docs/public-batched-cfr.md` |
| Opponent estimates, persistence, deduplication, filtering, malformed legacy data | `tests/test_opponent_model.py`, `tests/test_core.py` | `docs/architecture.md`, `docs/human-aware-strategy.md` |
| Practice replay, decision capture, hidden-information constraints | `tests/test_practice.py`, `tests/test_decision_capture.py`, `tests/test_decision_study.py` | `docs/decision-capture-v1.md`, `docs/decision-study-v1.md` |
| Explanation facts, coach grounding/visibility, voices and bounded conversation | `tests/test_explanations.py`, `tests/test_coach_grounding.py`, `tests/test_coach_analysis.py`, `tests/test_coach_teaching.py`, `tests/test_personalities.py`, `tests/test_coach_provider.py`, `tests/test_coach_conversation.py`, `tests/test_current_coach.py`, `tests/test_current_coach_conversation.py`, `tests/test_coach_request.py` | `docs/ai-coach-architecture.md`, `docs/current-coach-conversation-v1.md`, `docs/coach-analysis-v1.md` |
| HTTP/security and front-end contract | `tests/test_core.py`, `tests/test_practice.py`, `scripts/test_frontend.cjs` | README.md, “Data and local access”; `docs/architecture.md` |

Detailed docs and `benchmarks/results/` contain source-specific suite counts, parity, accuracy, runtime and allocation records. Read each with its recorded commit, interpreter, harness and fixture; a benchmark is not CI. The 331-test count in the Oct. 8–9 transfer audit applies to `65c9ba7`, not this later main snapshot. The current README, [solver progress](../solver-progress.md), and linked versioned solver reports describe capabilities merged after that historical baseline. No unfinished or unpublished worktree experiment is counted as shipped here.

## Documentation map and maintenance gaps

Use existing detailed docs as canonical, rather than copying their derivations into overview pages:

* Overall product assumptions and user-facing feature inventory: [README](../../README.md).
* Layers, contracts, EV and posterior conventions: [architecture](../architecture.md) and [human-aware strategy](../human-aware-strategy.md).
* River solver scope and independent mathematical validation: [solver validation](../solver-validation.md); configurable betting semantics: [configured river validation](../configured-river-validation.md).
* Turn and shared postflop contracts: [turn/rivers](../turn-river-validation.md), [postflop](../postflop-validation.md), [planned traversal](../planned-traversal.md), [public-batched CFR](../public-batched-cfr.md).
* External and deterministic coaching boundaries: [AI coach architecture](../ai-coach-architecture.md), [coach setup](../ai-coach-setup.md), [current conversation](../current-coach-conversation-v1.md).
* Hand capture and review: [decision capture](../decision-capture-v1.md), [decision study](../decision-study-v1.md).

The pre-existing `docs/architecture.md` remains valuable for mathematical and API detail; use [system overview](../architecture/SYSTEM_OVERVIEW.md), [solver progress](../solver-progress.md) and the preflop specifications for the current source map. Historical October 8 knowledge files remain pinned snapshots and do not supersede these current records. Validation results must retain full source SHA, Python version, command, outcome and scope; do not convert tests present or passes on another snapshot into a fresh current-baseline result.

## Full-board restricted preflop addition

The separate [preflop shove/fold API](../preflop-push-fold.md) adds full-deck final-board
chance to a bounded heads-up SB fold/shove and BB fold/call game, with at most
four compatible private pairs. Its prepared equity tables can be reused. This
does not expand the existing selected-outcome preflop API to a full-deck game,
or add limps, non-all-in raises, later-street betting or multiway equilibrium.
Read the dedicated specification for work admission and independent evidence.

A separate source-built [native preparation adapter](../native-preflop-equity.md)
retains that exact table and scope, with explicit compiler/binary provenance.
Python remains the reference/default. Read its current validation and benchmark
status before asserting performance; native-process memory is outside Python
allocation tracing.

The separate [prepared full-board preflop betting API](../preflop-full-checkdown.md)
adds finite limps, checks, configured raises and reraises using those same
immutable W/T/L tables. Future boards remain hidden and all postflop action is
forced checkdown. Its own configuration-derived tree/work admission precedes
building/training, and its independent replay rebuilds numeric rules and exact
own-hand best responses. See the dedicated record for measured status; this
does not enable full-deck later-street betting in the selected-outcome API.

## Optional turn terminal cache addition

The separate matrix-free turn API accepts explicit `terminal_cache="ranked-lru"`
for admitted fixed CFR+ calls with at most two original hands per player and
48 reachable branches. Its default remains `"none"`. Per-solve branch proxies
preserve the original outer kernel, exact root-fold paths, fallback limits and
all legacy result fields, with separate full-request cache admission and
cleanup accounting. Target mode and exceptional conditioning reject before
training. See [the cache specification and measured evidence](../turn-terminal-cache.md)
for exact parity, independent replay, concurrency/failure checks and the
fixture-specific timing/resource limits. This adds no earlier-street, UI,
general speed or RSS claim.

## Exact normalized archived river certificates

The development [river certificate audit](../river-rational-certificate.md)
reconstructs all fifteen saved extension/long-budget river policies, including
weighted raises. It records exact normalized EV/legal-response intervals,
all five target meets and ten misses, normalization ledgers and pinned inputs.
Saved-file verification freshly recomputes the mathematical rows. Its scope
is the configured numeric model and separately normalized policies; it adds
no production API, unrestricted equilibrium or raw-binary64 interval claim.

## Exact fixed-river equilibrium reference

The research [sequence-form witness](../river-sequence-equilibrium.md)
establishes exact configured-game values 25 for the polarised fixture and
-43339/2163 for weighted raises, with complete rational policies and zero
legal-response gap. Independent saved-file verification rebuilds the physical
numeric model, flow/payoff matrices and both responses. This supplies a
stronger small-game validation anchor; it changes no production solver,
earlier-street API or archived trained profile.

## Blocker-correlated river witness

A separate development fixture has independently proved exact value
-43339/1751 and zero exact NashConv with blocker-correlated private hands.
Six fixed-budget CFR+ policies retain full independent float/exact replay
and all target misses. Production and earlier-street paths are unchanged.
See [model, proof and executed evidence](../river-blocker-equilibrium.md).

## Exact selected-river turn witness

A separate development-only two-street witness proves value 50 and zero exact
NashConv in a four-world conditioned game, with independent payoff/flow and
legal-response reconstruction. Literal negative controls detect future-card
peeking and cumulative-wager mistakes. The equilibrium folds on the turn;
river policies remain fully certified off-path. See [scope and evidence](../turn-sequence-equilibrium.md).

## Weighted turn witness with on-path river play

A separate four-world conditioned game has two independently validated exact
policies at value 30 and zero NashConv, with river decisions reached with
probability 1. A hand-written policy was certified before the LP candidate;
the separate verifier checks all payoff/flow data and both legal responses.
See [fixed game, proof, reach and limits](../turn-weighted-sequence-equilibrium.md).

## Production turn CFR+ against the value-30 anchor

Six complete production policies now have independent numeric and exact
normalized own-hand response checks against the proved weighted turn value.
Both backends miss 0.001-chip NashConv at 1,000/3,000 iterations and meet it
at 10,000 (about 0.000681). Every miss and full policy remains saved.
See [experiment, independent reconstruction and scope](../turn-weighted-cfrplus.md).

## Compact blocker-conditioned turn witness

A separate six-world turn game with private blockers has exact value 115/7
and zero NashConv, certified through original full primal/dual equations and
independent legal responses. Fixing empty realization coordinates removes two
LP columns while preserving all existing resource caps; the rejected legacy
258-column admission and hidden-information controls remain recorded.
See [model, affine reduction, proof and limits](../turn-blocker-sequence-equilibrium.md).

## Production turn CFR+ with private blockers

Six complete policies for the six-world blocker-conditioned turn game have
independent numeric and exact normalized own-hand response checks against
the proved 115/7 value. Both backends miss 0.001-chip NashConv at 1,000/3,000
iterations and meet it at 10,000 (about 0.000414). All four misses and full
policies remain saved. See [experiment, proof and limits](../turn-blocker-cfrplus.md).

## Global suit symmetry of blocker-conditioned turn policies

Independent reconstruction preserves the exact 115/7 equilibrium through all
24 global suit bijections and replays 144 archived policy transports. Eight
fresh 1,000-iteration production calls pass the fixed 1e-9-chip symmetry gate;
all eight still miss the unchanged 0.001-chip NashConv target. Full policies
and misses remain saved. See [experiment and scope](../turn-suit-equivariance.md).

## Full-deck raised turn reference and fixed-budget accuracy

Independent numeric rules and exhaustive best-five signs now establish a fixed
176-world game with finite turn/river raises. A complete hand-written check/call
policy has independently derived exact value -2500/231 and legal-response
NashConv 75. Production structure matches the complete independent tree hash;
all production defaults and guards stay unchanged. Six actual full-deck CFR+
calls at 100/1000/1500 iterations independently replay all 2,404 policy rows.
Both backends reach NashConv 0.001658745330324507 at 1,500; all six profiles
still miss 0.001 chips. Complete policies and misses are retained. Numeric
trained-policy replay is separate from the hand-written exact anchors.
See [reference, completed experiment and limits](../full-deck-raised-turn.md).
A separate [checked chance-quotient audit](../full-deck-raised-exact.md) certifies
all six explicitly normalized policies without changing the generic exact cap.
All six exact gaps still miss 1/1000 chips; this is fixed-policy evidence for
that full-deck game, not an equilibrium or arbitrary-policy certificate.

## Explicit compiled training for prepared preflop and fixed flop

The prepared full-board preflop betting and forced-checkdown flop APIs accept an
explicit source-built native trainer. Python defaults, poker rules, physical
counts, strategy formats and exact diagnostics remain unchanged. Preflop uses
scalar traversal; flop uses public-hand-vector reduction with direct signed
joint masses. The initial scalar flop DCFR parity miss is retained alongside
the passing revised six-profile report. All 38 revised saved policies pass
independent physical-count replay. Measured complete-call median ratios are
40.13–103.06 on two finite prepared games; no general speedup or RSS saving
follows. Native conformance passes on Windows/Linux. See
[build, resource guards, quality misses and evidence](../native-fixed-street.md).

## Exact weighted preflop/checkdown anchor

A three-compatible-pair finite preflop betting game with all final boards hidden
has exact value `100107990869/130471452826` in SB net-transfer chips. Original
sequence-form primal/dual certificates, independently reconstructed exact legal
responses and exhaustive own-hand pure responses agree at NashConv zero. The
19-state game retains limps, BB's option, configured raises, all-ins and refunds.
This research adds a model-specific validation target while production defaults
and broader full-deck future betting remain unchanged. See
[frozen scope and reproducible proof](../preflop-weighted-sequence.md).

## Covered prepared preflop count pool

An explicit covered-table path can reuse ordinary source counts across joint
suit-equivalent private pairs while retaining the original four-pair enumeration
limits. The separate table is bounded to 128 compatible pairs and 32 source
tables; all ordinary solver work/state/action/native caps still apply. The
physical six-pair weighted benchmark independently replays full-board hidden
checkdown with limps and actual reraises. Wider synthetic tests establish
routing/guard behavior only. See [API, provenance and measured scope](../preflop-covered-counts.md).

## Full-physical raised-turn exact verification

A separate [independent physical oracle](../full-physical-audit-wrapper.md) verifies
both saved equilibrium witnesses at exact NashConv zero and OOP value -400/21.
All 48 river cards remain separate; the original numeric tails keep their positive
exact gaps. This fixed-game research leaves production defaults and earlier
streets unchanged. See the linked immutable report, controls and scope.

## Optional direct turn tail averaging

The separate [turn tail research API](../direct-turn-tail.md) directly averages
an explicit completed-sweep CFR+ window with original iteration weights. Old
solver APIs and earlier streets are unchanged. Full-request admission, additional
dense/slot guards, exact zero-discard parity and independent small-game quality
tests bound this addition; broader quality depends on recorded experiments.

The separate [fixed direct-tail experiment](../direct-turn-tail-experiment.md)
defines a frozen full-deck call and complete independent saved-policy audits.
The raw T=1500,D=1000 profile now has exact normalized-policy NashConv zero and
OOP value -400/21, with all eight metrics matched by both exact auditors. This
is fixed 176-world game evidence; the saved result receives no cleanup and
does not establish a general direct-tail convergence guarantee.

## Optional direct river tail averaging

A separate [five-card river research API](../direct-river-tail.md) reuses the
local original-weight accumulator with full requested admission, independent
flow/response checks and fresh diagnostics. Its known one-bet test retains a
quality miss, and zero-reach conditional fallbacks are compared by realization
flow. Existing solver defaults, shared kernels and earlier streets are unchanged.

The [fixed river experiment](../direct-river-tail-experiment.md) defines separate
T=10000,D=3000 calls for the historical polarized and weighted raised fixtures,
with raw-policy exact audits and prior-tail realization comparison. Both actual
calls are saved: polarized NashConv 0.0068727141 misses 0.001; weighted raised
NashConv 0.0002232345 meets it. Both are positive exact gaps and reproduce prior
tail flows within 1e-11. This is correctness evidence, with no general quality
or speed improvement claim.

The [longer direct river budget](../direct-river-long-tail.md) admits explicit
requests up to 100,000 with a distinct result version above 10,000. Existing
v1 payloads and the turn ceiling remain unchanged; the weighted 100k fixture
still rejects under the original dense-work cap. This API extension supplies
no actual 100k direct-tail quality result.

The [fixed longer river experiment](../direct-river-long-tail-experiment.md)
defines one polarized T=100000,D=3000 call, exact old/new response-gain
comparison and immutable raw output. The actual raw policy meets exact 0.001
at NashConv about 0.0008944742, with both response gains reduced from the
preserved 10k miss. Its gap remains positive; independent exact audits and
known-value containment apply to this fixed game only.

## Three-hand TURN audit preparation

A separate [fixed three-hand physical audit](../turn-three-hand-physical-audit.md)
rebuilds nine weighted private pairs and all 396 legal pair/river worlds with
independent exact visible-information responses. Its own fixed work envelope
and control-policy anchors extend validation breadth while preserving the old
176-world proof and generic exact limits. This validation slice records no
trained policy or equilibrium-quality result for the larger game.

The [three-hand direct-tail experiment](../turn-three-hand-direct-tail-experiment.md)
defines one T=750, discard=250 call with unchanged full-request admission,
independent numeric/exact replay, complete source guards and immutable raw output.
The source-frozen protocol records quality separately from replay validity.
The actual raw policy passes independent replay but misses the unchanged
0.001-chip target at exact NashConv about 0.01069549. Its positive gap and both
response gains remain saved without cleanup or a general convergence claim.

The [exact seven-class river audit](../turn-three-hand-classes.md) checks an
equivalent 45-world representation for class-constant policies in this same
fixed game. It preserves original joint masses, every physical policy row and
both unrestricted physical best responses, comparing all eight exact metrics
under the existing generic and physical audit limits. This adds a no-training
mathematical foundation; the accepted T750 policy's positive target miss remains
unchanged. A compact trainer and its full resource admission are separate work.


## Full-future flop delayed-averaging evidence

The [corrected delayed-averaging study](../flop-delayed-study.md#completed-corrected-study)
finished all 20 candidate policies with independent replay and exact repeat
controls. All six final 0.005-chip decisions miss; delays 70 and 100 yield larger
NashConv than delay zero on this fixed weighted 5,940-world game. The complete
raw corpus, two earlier baseline receipts and source identities are preserved.
This is measured finite-game evidence, with no new convergence or general speed
claim. Flop APIs, resource caps and coaching defaults are unchanged.

## Optional alternating flop trainers

The opt-in public-batched flop algorithms `lcfr` and `dcfr-alternating` add
unfloored alternating updates with pre-sweep own-reach averaging. The shared
legacy algorithms and defaults remain covered by exact archived-adapter controls.
All requested sweeps reserve three passes under the existing resource caps.
Mathematical controls and independent physical/legal-response replay pass.
The [completed frozen comparison](../flop-alternating-study.md#completed-frozen-measurement)
retains all three original 0.005-chip misses: CFR+ about 0.012538 NashConv, LCFR
0.090593 and alternating DCFR 0.011509. All 12 policies and both historical
baselines reconstruct; the 15-file corpus, 626-file source identity and transient
non-input scratch incident are authenticated. This is finite-game evidence,
with no successful convergence or controlled speed claim. See
[equations, scope and validation](../flop-alternating-cfr.md).

## Fixed flop chance equivalence foundation

The [no-training fixed-game audit](../flop-public-classes.md) checks an exact
126-world representation of the weighted 5,940-world flop fixture: 11 turn
classes and 19 global river signatures. It checks every original mass and
private-hand boundary, all 30,812 public nodes and 11,787 chance-branch subtrees,
then lifts 466 class rows to all 16,912 physical rows. Four synthetic controls
match all eight exact metrics under unrestricted physical responses; independent
numeric replay agrees within 8.89e-16. The saved proof authenticates all compact
probabilities, physical policy digests, six source files and the separate first
execution interruption. This adds a mathematical foundation; the completed
alternating-study quality misses remain unchanged, and no compact trainer or
solver/API/default/resource-cap change is included.


### Fixed-game turn class-tail research API

The explicit fixed three-hand turn class-tail adapter restores all physical
policy identities before diagnostics and retains separate full-request/logical
storage admission. Ordinary solver defaults and earlier streets are unchanged.
See [scope, controls and model](../turn-class-tail.md); a longer-budget quality
experiment remains separate.

The opt-in [fixed-game flop class CFR+ research adapter](../flop-class-cfrplus.md)
uses the proved quotient with its own retained physical request caps, raw output
normalization record and exact physical response audit. Production defaults and
the historical no-training proof remain unchanged; see that page for pilot status.

A separate explicit [compact-work fixed-flop entry](../flop-class-compact-cfrplus.md)
uses versioned named-loop admission and passed the preregistered 560-sweep
finite-game quality gate with exact physical responses. It preserves all
published lower-budget executable sources and old defaults; see the linked
page for evidence and publication status.

The fixed-game class quality pass is published in
[merged PR #202](https://github.com/ajpaulson18-design/openpoker-lab/pull/202),
with both full Python matrices passing. The completed eight-call
[call-cost experiment](../flop-class-call-cost.md) records whole-call median
148.360679 s / 175.079169 s at 140 / 560 sweeps, with separate Python traced
peaks 96,955,723 / 96,959,799 bytes and preserved miss/pass outcomes. Both
entries use the same representation; these are different work/quality budgets,
not a same-work speedup or RSS measurement. See the retained
[Windows validation qualification](../flop-class-windows-validation.md).

## Fixed-flop phase profiling

The opt-in [phase-profile harness](../flop-class-phase-profile.md) is a separate
diagnostic entry for one fully admitted 560-sweep compact solve. It wraps only
existing module boundaries, records nested inclusive wall/CPU intervals, and
retains the full raw report. Synthetic validation is distinct from execution;
the single profile completed with 21 events, stable source and a byte-identical
passing policy. Its 172.881961 s whole call includes 89.552585 s publication
verification, 46.553740 s training and 20.418856 s policy auditing as root
intervals. This diagnostic does not change the solver,
proof, recurrence, defaults, Coach, or turn/river paths, and its overlapping phase
times are not primary timing evidence.


The cost and phase evidence are published in merged
[PR #204](https://github.com/ajpaulson18-design/openpoker-lab/pull/204) and
[PR #205](https://github.com/ajpaulson18-design/openpoker-lab/pull/205), with both
full Python matrices passing and GitHub-main ancestry/tree checks completed.
The [fixed-support range-prior proof](../flop-class-reweight.md) completed
baseline, uniform and skewed positive-weight games with all twelve no-training
controls passing exact unrestricted physical response checks. Its 15 immutable
artifacts preserve full policies, priors, source identities and numeric gaps.
The saved verifier authenticates those bytes and receipts without fresh replay.
New-prior CFR+ training and convergence remain a later milestone.


The separate [positive-prior CFR+ adapter](../flop-class-reweight-cfrplus.md)
is implemented with synthetic admission/lifecycle tests, an explicit weighted
setup charge, fresh weighted model checks and a three-case pilot protocol.
Its completed three-case 560-sweep pilot passed the 0.005 exact NashConv gate
for baseline, uniform and skew, and all three retained policies passed fresh
no-training physical replay. These are finite fixed-support results.


The no-training range-prior evidence is published in merged
[PR #206](https://github.com/ajpaulson18-design/openpoker-lab/pull/206), merge
`53bb4a1266e2450dc8a0b7e0c20a82b2728b5c63`. Both complete Python matrices
passed its final head; GitHub-main ancestry and exact merged-tree equality were
verified, including the original solver handoff commit. The new training entry
has 49 passing combined focused regressions (20 new adapter/harness/replay tests
plus 29 prior-proof regressions) before freezing e1. The actual pilot and three
fresh saved-policy replays completed with stable sources and no errors; full
artifacts, receipt authentication and final publication are tracked in
[PR #207](https://github.com/ajpaulson18-design/openpoker-lab/pull/207).


The [baseline call diagnostic](../flop-class-reweight-baseline-diagnostic.md)
completed its single frozen two-call batch at source
`602a37eac96dfd146069e361f2501efff15b3576`. Both reports match the independently
replayed pilot byte for byte; trainer count is exactly one per sample/two total,
all 35 sources remained clean/stable, and no error or retry occurred. The phase
sample has 13 complete events (242.0216675 wall / 191.09375 CPU seconds); four
nested model validations total 79.6207668 wall seconds, included within their
parents. The separate allocation sample peaks at 401,901,644 new Python traced
bytes and retains a large wall/CPU gap (9873.9262813 / 711.265625 seconds).
These single observations imply no speed, RSS, stable memory or general
bottleneck claim. Full policies, index and no-solve saved-evidence verifier are
tracked in [PR #209](https://github.com/ajpaulson18-design/openpoker-lab/pull/209).

PR #207 merged as `08e3a339eadfcff706fa75f0851e8f9978361ce2` after both final
Python 3.11/3.12/3.13 matrices passed. Fetched main matched the reviewed tree
and retained the original advance-solver commit before this diagnostic.

PR #209 merged as `2b0867acf65ff3eaeff8e52bac1b2f2acf9b896c` after both final
Python 3.11/3.12/3.13 matrices and all other checks passed. Fetched main had the
exact reviewed tree and both the diagnostic head and original advance-solver
commit as ancestors; all three evidence blobs match local Git hashes/sizes.

The next [owned-model integrity experiment](../flop-owned-fingerprint.md) is a
separate no-training precursor to considering validation reuse. It retains
full independent model validation and uses six bounded graph fingerprints and
two restored mutations. The single actual model census now passed: six fingerprints, two full
validations, 41 zero authority counters and stable clean 39-source identities.
Stable/repeated/restored graphs have 318,280 tracked objects and 1,608,777 edges;
both value and rooted-index alias mutations change the digest and restore exactly.
The saved report is tracked in PR #211. It implements no solver shortcut/cache
and establishes no comparative performance or memory result.

## Fixed three-hand TURN accuracy result

The [T6000/D2000 experiment](../turn-class-tail-T6000-experiment.md) met its
unchanged exact normalized-policy NashConv target of 0.001 chip at approximately
0.00003025771156. One fixed 396-world game was trained through seven proved
river classes, then lifted to all 3,606 physical policy rows and 8,046 actions.
Independent full-physical and both class exact audits agree on all eight metrics;
the previous T750 miss remains immutable. The complete policy, source identities
and numeric/exact checks are retained. This is fixed-game accuracy evidence;
the broader range of supported games and the separately exact game value remain
unfinished work.

## Three-class JJ/KK physical source counts

The separate [JJ/KK observation](../preflop-jj-kk-basis-results.md) completed
one full-board source-count batch. The independent best-five reference and
native seven-card counter agree exactly on all three relative-suit classes,
after exhaustive five-card conformance and the published AA calibration.
Complete raw JSON/text receipts and strict saved-data authentication are
retained. This adds no strategy or equilibrium certificate; the subsequent
[108-pair transport observation](../preflop-three-rank-transport-results.md)
separately verifies every physical joint-suit map and exact global prior.
Publication checks and merge status are tracked in
[PR #216](https://github.com/ajpaulson18-design/openpoker-lab/pull/216).

## Configurable matrix-free TURN tail

The separate [original-weight tail API](../matrix-free-turn-tail.md) adds configurable four-card boards, weighted ranges, physical selected/full-deck rivers and compatible street sizing to matrix-free CFR+. It averages completed sweeps t>discard with original weight t and preserves full-request admission. D=0 matches the existing matrix-free policy exactly in the control; positive tails match materialized training and independent physical rules at the declared tolerances. This is new research API coverage, with bounded correctness controls; broader convergence and commercial solver parity remain unproved.

## Three-rank preflop count transport

One frozen [no-enumeration transport observation](../preflop-three-rank-transport-results.md)
passed for SB AA:1, QQ:0.5, JJ:0.25 versus BB KK. All 108 physical pair rows
authenticate from nine saved source classes; exact priors sum to one and all
six/24/six relative-suit censuses pass. One candidate and both independent
memory/saved checks agree, all eleven forbidden-calculation counters are zero,
and the clean measured source snapshot is stable. This establishes prepared
count provenance, with no strategy, later-street betting or equilibrium claim.

The subsequent [exact physical witness](../preflop-three-rank-exact-witness-results.md)
certifies one mutual-response profile for the 108-pair finite three-chip
preflop/checkdown game. Exact SB value is 1464215/2330174 chips; both unilateral
gains and NashConv are zero. Independent replay checks all 96 own-hand rows,
258 probabilities and 1,080 complete legal responses, preserving hidden
opponents and permitting suit-dependent deviations. This supplies a fixed-game
accuracy anchor; unrestricted ranges, later-street betting and production
trainer convergence remain separate work.


## Held-out RIVER accuracy evidence

The separate [four-profile river corpus](../river-heldout-quality-results.md) adds two weighted 4x4 games with blocker/tie and short-stack/rank-extreme coverage. All CFR+10000 profiles pass independent physical and exact normalized-policy replay, but all four miss the fixed 0.001-chip NashConv target (about 0.00174251 and 0.00232499). Complete policies, source/claim receipts and unchanged misses are retained. This is an observed accuracy limitation, not commercial solver parity.


## Fixed river original-weight tail accuracy

The separate [four-profile follow-up](../river-heldout-tail-results.md) reaches exact normalized-policy NashConv<=0.001 chip for both original weighted 4x4 river games at T50000/D25000. Both T10000/D5000 tails remain misses; the unpaired one worsens at equal T. Complete policies, immutable baseline misses, all source/admission receipts and independent physical numeric/exact saved replays are retained. This finite-game milestone does not establish wider game accuracy, equal-cost benefits, performance or GTO Wizard quality.


## Explicit native river research API

The separate [compiled river adapter](../native-river-solver.md) supports existing admitted fixed-board games at CFR+10..10000 with explicit local build identity, full historical/native guards and original completed-sweep D=0 averaging. Independent physical numeric/exact controls cover weighted blockers, ties, short refunds, 8x8 supports and a known-zero game. Production defaults, shared native C and earlier-street paths are unchanged; broader accuracy, admission and measured performance remain pending.


## Matrix-free river original-weight tail integration

The opt-in [ranked river tail](../matrix-free-river-tail.md) keeps later completed CFR+ sweep averages under unchanged full-request admission and dynamic cancellation fallback limits. Independent bounded controls cover original-policy parity, physical numeric/exact replay, blockers, ties, refunds and dead hands; broader accuracy remains a separate study.

## Broader native river quality study

The [fixed two-game 8x8 protocol](../native-river-range-quality-protocol.md) expands the paired Python/native accuracy study at T10000/D0. Source/build/control authentication and full physical preflight are required before its exclusive four-call claim. No trained outcome is established by this source freeze.


The [completed 8x8 accuracy record](../native-river-range-quality-results.md) preserves four fixed-budget policies with exact NashConv below 0.001 chip and zero observed native/Python policy differences on the recorded build. All independent physical/exact checks passed; original 4x4 misses remain unchanged and broader game accuracy remains unproven.

## Blocker-sensitive AK/KK source counts

One [complete seven-stage physical observation](../preflop-ak-kk-basis-results.md) passed exact native/best-five agreement for three new AK/KK suit classes after current-build all-five conformance and published AA calibration. The original reports and thirteen small raw streams retain all 783 stable source identities and both build identities. These are source counts only; 84-pair joint-suit transport and strategy accuracy remain separate prerequisites. No shared solver or Coach behavior changes.

## Physical AA/AK preflop count transport

One [independent blocker-sensitive transport observation](../preflop-aa-ak-transport-results.md) passed for 84 compatible AA/AK-versus-KK pairs after removing 48 physical collisions. Six authenticated source orbits, every integer count/map/source identity and exact global 1/84 prior passed both memory and fresh saved-file verification. All sixteen forbidden-call counters are zero and ten clean source identities are stable. This is count provenance only; real-source policy accuracy and convergence remain separate work.
