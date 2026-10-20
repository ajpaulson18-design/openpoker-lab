# Repository agent instructions

## Required onboarding

Read [docs/START_HERE.md](docs/START_HERE.md) and the relevant canonical specifications before changes. Preserve owner intent in [the decision register](docs/decisions/DECISION_LOG.md); keep plans, implementation evidence and unknowns distinct. Follow [the contribution and handoff protocol](docs/agents/TASK_PROTOCOL.md). Run `python -m scripts.validate_docs` for documentation changes.

## Project

For matrix-free turn `terminal_cache="ranked-lru"`, preserve the literal default
path and all legacy payload fields. Keep caches private to a solve through
branch composition, restore original references on every exit, validate before
every lookup, and cache only successful zero-fallback vectors. Retain original
root-fold arithmetic and full requested-work guards plus separate cache
admission. No global patch, cross-river reuse, exceptional-conditioning support
or RSS/general-speed claim follows. See [cache scope and evidence](docs/turn-terminal-cache.md).

OpenPoker Lab is a standard-library Python research application with a plain JavaScript browser UI. It combines poker simulation, persistent opponent observations, transparent EV analysis, deterministic explanations, practice/review flows, and bounded heads-up preflop and postflop CFR solvers. It does not solve unrestricted no-limit Hold'em and makes no profitability claims.

## Setup and validation

Use Python 3.11 or newer. There are no runtime dependencies.

- Run the application with `python -m pokerlab.server`.
- Run the full unit suite with `python -m unittest discover -s tests -v`.
- Run the exhaustive evaluator validation with `python -m scripts.validate_evaluator` when card-evaluation logic changes; it is intentionally slower.
- CI runs the unit suite on Python 3.11, 3.12, and 3.13.

## Architecture and constraints

- Keep calculation, immutable contracts, opponent-model snapshots, explanations, and presentation voices separate.
- `pokerlab/contracts.py` defines shared structured boundaries. Preserve deterministic serialization and provenance.
- `pokerlab/solver.py` dispatches the fixed-board river solver: the optimized fixed-bet compatibility kernel in `restricted_solver.py`, or the finite configured bet/raise/stack tree. Both expose `river-strategy-v1` and vanilla CFR or optional DCFR. Never present either as unrestricted Hold'em GTO or earlier-street solving.
- `pokerlab/postflop_solver.py` handles finite heads-up flop, turn and river starts through shared `cfr.py`/`planned_cfr.py` kernels and the `river_tree.py` betting builder. `turn_solver.py` preserves its established API as a thin facade. Preserve physical joint hand/runout weights, ordered future reveals, perfect recall, hidden future cards, cumulative stack accounting and `postflop-strategy-v1`. Selected runouts condition the entire joint game; they are not an unconditional full-deck approximation. Full-deck flop coverage is limited by strict resource guards; full-deck preflop with later-street betting, multiway equilibrium and unrestricted NLHE remain future work.
- `planned_cfr.py` is an optional static-world Python traversal backend; recursive remains the default/reference. Preserve callback/lock semantics, deterministic constant terminal utilities, local plan lifetime and the 250,000-operation guard. Measure full-call runtime and memory independently; do not describe this as native compilation or chance sampling.
- `public_cfr.py` is an optional exact public-tree/private-hand-vector trainer selected by postflop `traversal="public-batched"`. It specializes fold/showdown payoffs and has no lock or arbitrary-utility callback API. Preserve joint physical edge weights, opponent reach in regrets, own reach in averaging, simultaneous CFR/DCFR updates, hidden-card histories, the 250,000 prefix-edge cap, and prompt recursive-closure release. Keep recursive as the reference and measure complete calls including exact best responses.
- `scripts/cfr_quality.py` validates the three production training kernels on a known Kuhn game using independent terminal-history payoffs and exhaustive pure-policy best responses. Production evaluation/BR are candidates, never the oracle. Preserve rational anchors, visible-information policies and quantitative finite-iteration gates; a Kuhn result does not certify Hold'em equilibrium accuracy.
- `pokerlab/preflop_tree.py` constructs heads-up SB/button and BB betting states with explicit unsolved flop/all-in continuations. Preserve the BB option after a limp, total-stack blind accounting, refunds, position change and callback-owned subtree budgets. Reuse shared CFR/action types, and do not describe tree coverage or synthetic utility tests as a preflop equilibrium solution.
- `pokerlab/preflop_solver.py` connects that boundary to physical flop chance and existing postflop templates without changing shared kernels. Preserve global SB/BB identity, cumulative whole-hand sized action tokens, joint selected-outcome conditioning, ordered turn/river reveals, action-only stage configs and aggregate/transient resource limits. The existing selected-outcome preflop API rejects full-deck chance. Recursive/planned training and optional public-batched training are supported; CFR+ supports recursive/public-batched only. The vector training view uses a binary positive-pot anchor and shifted terminal contributions; preserve its utility identity, original tree for evaluation/BR, separate copy-state bound and prefix-edge cap. Optional diagnostics="public-batched" reuses the unchanged vector evaluator on that shifted view, before release; other training backends require a separate bounded view. Keep recursive diagnostics as default/reference, exact visible-information BR semantics, prompt view cleanup, and separate training/diagnostic metadata. `scripts/preflop_validation.py` independently replays serialized policies from numeric rules and exact visible-information best responses; never replace its oracle with production tree, utility, rank or evaluation helpers. Default configured replay tracks binary64 local postflop quantization before whole-hand translation and checks serialized amounts/targets exactly. Preserve the explicit historical global-rational diagnostic and distinguish its rounding-boundary rejection from configured-model verification; neither proves exact-decimal equivalence.
- `pokerlab/models.py` persists local observations. Preserve explicit opportunity denominators, idempotent observation IDs, street/context filtering, transactions, and legacy-data error handling.
- `preflop_delayed_cfrplus.py` isolates optional preflop CFR+ averaging delay from shared training kernels. Preserve zero-delay solver paths/payload and early exact-integer `0 <= delay < iterations` validation. Apply `max(t-delay,0)` to completed-sweep own-reach averaging, retaining joint physical marginal weights and hidden-information keys. Positive-delay vector orchestration caches the current profile, rematches only updated player rows and skips zero-weight averages. Preserve exact policy values and original row order; record two regret passes per sweep and iterations-minus-delay average passes. The zero-delay solver still uses the unchanged shared trainer. Use independent configured replay and known-game legal BR quality; delay improvement is measured, never assumed.
- `preflop_vector_budget.py` is an independent structural admission census for opt-in preflop `resource_model="public-vector"`, requiring public-batched training and diagnostics. Default world admission/output remain unchanged. Explicit tree_admission="vector" may replace the aggregate 10,000-decision ceiling only in public-vector mode; retain the 250,000 aggregate public-state ceiling, per-flop template caps, copy-state ceiling and action-slot/work admission. Positive-delay optimized work uses a distinct versioned envelope. Preserve all other world/candidate/tree/view guards, reserve prefix/dense/info-action capacity before insertion, and check the modeled loop envelope before vector view/training allocation. Account for dense index holes, asymmetric ranges, repeated terminal-prefix edges, CFR+ passes/rematches, row setup and missing diagnostic policy fallbacks. Shared backend changes require reviewing the versioned envelope. Counters are modeled loops/allocation slots, not runtime or RSS guarantees. Keep configured replay and legal BR accuracy independent; report unmet targets.
- `pokerlab/practice.py` must store every live opponent range and enough decision-time state to replay a decision exactly.
- Explanation and personality layers may change prose, never recommendations, EVs, frequencies, confidence, analysis IDs, or protected facts.
- The server remains loopback-only with Host/Origin validation, JSON mutation boundaries, concurrency limits, and a restrictive CSP unless a deliberate architecture change is approved.
- Never commit `data/`, SQLite databases, credentials, personal opponent records, proprietary solver output, or copied commercial interfaces.
- Prefer synthetic examples. Avoid silently changing poker rules, probability meanings, model assumptions, or public API shapes.

## Completion standard

`preflop_checkdown_solver.py` is a separate prepared-counts preflop betting
adapter. Reuse the existing preflop builder and shared CFR/CFR+ kernels; every
nonfolded closed betting line settles at matched contributions using hidden
full-board categories. Preserve limps and the BB option, finite raise rules,
short all-ins, refunds, private-own-hand/public-history keys and zero-decision
blind-all-in handling. Admit the complete requested solve with independent
configuration-derived tree and modeled-loop forecasts before building a tree.
Source-inclusive bookkeeping remains default; prepared-counts is explicit.
Do not change old APIs, expose future cards, or imply later-street decisions.
Validate serialized policies with independent numeric rules and exact rational
own-hand best responses. See [scope and evidence](docs/preflop-full-checkdown.md).

Opt-in preflop `world_indexing="pair-mean"` integrates hidden W/T/L categories
within each ordered private pair. Retain separate hidden opponent hands and
zero-mean pair mass, exact conditional Fraction means before binary64 conversion,
unchanged default categorical payloads, full table/category validation and source
charges, and all tree/action/rank caps. Admit P-world training/diagnostics with
retained 3P setup plus separately disclosed included collapse work before building.
Use independent physical-count policy/own-hand BR replay, declared cross-mode
tolerances and paired complete calls/traces; changing summation order does not
promise bitwise policies or a universal 3x speedup. See [pair means](docs/preflop-pair-mean.md).

Full-board preflop equity tables support `reweight_preflop_equities` for new
weights and covered private-pair subsets. Preserve global collision conditioning,
unchanged source counts and table immutability, and reject any uncovered compatible
pair without board enumeration. Validation establishes structure, not physical
provenance of caller-supplied counts. See [reweighting evidence](docs/preflop-equity-reweight.md).

Opt-in `remap_preflop_equities_by_suit` reuses counts through one joint global
suit permutation of an ordered SB/BB pair. Preserve relative suits, role order,
source-orbit consistency, current admission caps and literal reweight behavior.
Record source/target endpoints and the full suit bijection; structural validation
does not authenticate counts. See [suit transfer](docs/preflop-suit-remap.md).

Prepared shove/fold solves may explicitly select `resource_model="prepared-counts"`
to charge a separate compact-table setup envelope instead of historical board
preparation. Preserve the source-inclusive default and full-solve pre-build
guard, unchanged training/diagnostic bounds, full requested iterations and
500-million ceiling. Validate tables and reject before tree/training allocation;
logical entries are not CPU, allocation or RSS bounds. See [prepared admission](docs/preflop-prepared-budget.md).

The [weighted eight-hand flop matrix](docs/flop-weighted-eight-hand.md) uses
the direct fixed-flop API with forced future checkdown. Keep all six no-ranking
preflights ahead of oracle/training work, exact blocker-conditioned pair support,
the unchanged admission limits, independent policy replay and explicit flop
re-raise histories. Preserve every rejection/target miss and publish generated
policy artifacts only after the clean-source verification.

`flop_checkdown_equity.py` provides immutable fixed-flop ordered W/T/L tables
for `solve_prepared_flop_checkdown`. Reweight only physically covered compatible
pairs and preserve the fixed board, exact global collision conditioning, original
counts and all caps. Validate immutable structure and positive representable
category support before tree allocation. Structural validation does not prove
physical provenance. Keep the ordinary solver payload unchanged and retain
source-inclusive admission for prepared solves; report zero current ranking
separately. See [API and measured scope](docs/flop-equity-reuse.md).

`flop_suit_equity.py` explicitly transfers fixed-flop counts to covered joint
suit orbits. Canonicalize the board and ordered OOP/IP hands under one global
four-suit bijection per target pair; retain ranks, relative suits and player
roles. Resolve all pairs and reject inconsistent source-orbit counts before
output construction. Keep target priors/caps from the existing plan, unchanged
literal reweighting, rank-free transfers and full endpoint/permutation provenance.
See [mathematical scope and validation](docs/flop-suit-equity.md).

`native_preflop_equity.py` is a separate explicit source-built count adapter.
Preserve ordinary Python preparation/callbacks/default payloads and all existing
pre-enumeration caps. The project-owned C helper returns integer counts; Python
retains exact priors and category-mass construction. Fail explicitly, with no
silent fallback. Keep source/compiler/binary identities, independent best-five
and full-board conformance, and complete-call measurements. Python allocation
traces exclude native-process allocations and RSS. Source-only distribution does
not establish compiled-binary packaging clearance. See [native preparation](docs/native-preflop-equity.md).

Keep changes narrow and reviewable. For defects and model changes, add a reproducible case and externally meaningful regression test or measurable benchmark. Run the smallest relevant tests while working and the full applicable suite before completion. Record commands actually run and limitations. Surface ambiguous poker rules, statistical assumptions, security decisions, and architecture changes instead of guessing.

The lead agent owns architecture, product judgment, difficult debugging and integration review. Delegate bounded implementation, research, documentation and validation to workers when authorized, following the owner's Sol/Luna preference in the task protocol. Copilot specialists provide support when a working account route is available; workflow configuration alone does not prove they run. Preserve the same model-neutral knowledge and calculation boundaries across agents.

- `preflop_runout_index.py` indexes canonical selected outcomes by card under the unchanged 300,000-outcome bound. Preserve exact valid counts, ascending selected index/world order, original per-pair admission charges and guard order before ranking/world allocation. Do not retain per-pair masks or normalized outcome copies after posting construction. Packed payload/conversion estimates exclude Python object overhead and are not allocation/RSS bounds; distinguish index-only traces from whole-solve memory.

- `preflop_sampled_cfr.py` is opt-in preflop chance-block vanilla CFR, requiring chance-sampled resource admission and full public-batched exact diagnostics. Preserve frozen simultaneous batch profiles, total joint-mass importance scaling, opponent-reach regrets, own-reach averages, own-hand/public-history keys, exact-integer CDF support for tiny positive weights and uniform unvisited rows. Reserve sampler entry count before ranking and logical CDF bits before sampler allocation; distinguish bit payload from allocated memory. The independent sampled census uses max chance branch and sum all betting actions; retain tree/construction caps and conservative exact-diagnostic vector admission. Report every seed and unmet accuracy target; no CFR+, unrestricted/full-deck or whole-solver speed claim follows from cheaper sampled updates.

- Preflop exact convergence stopping is opt-in positive-delay CFR+ with public-vector training/diagnostics. Admit the full requested iteration ceiling plus every snapshot and possible positive-average exact check before training; early stopping must never bypass any resource cap. Keep delay fixed, check completed sweeps only after averaging has positive weight, retain fresh nonalias callback snapshots, release them promptly, reuse matching final diagnostics, and report actual completed/pass counts separately from the requested ceiling. A target miss at the ceiling remains a miss. The 1e-10 target guard is conservative padding, not a formal floating-point error bound. Shared kernels and default fixed-iteration output stay unchanged.

- Preflop `private_indexing="compact"` is opt-in positive-delay CFR+ with public-vector training/diagnostics only. Preserve ascending active-hand bijection, physical row/mass/history order, exact policy arithmetic and restoration of original policy identities/order. Admit v4 actual compact dimensions plus copy/reference/work overhead before copying or training-view allocation; retain all original caps and full requested convergence admission. Use compact ids for all checkpoints/diagnostics and release copies on success/error before serialization. Logical reference bounds exclude Python headers/RSS; measure complete calls and separate allocation traces, and keep shape-specific limits explicit. Shared postflop kernels and default payloads remain unchanged.

- Preflop `postflop_scope="flop-checkdown"` is an explicit positive-delay CFR+ public-vector/public-batched game model: preflop/flop betting, then forced checkdown with all selected future world ranks/masses hidden and integrated at terminals. Reject turn/river configs early; keep only active flop config metadata and preflop/flop strategy rows, distinct solver version and existing row schema. Preserve unchanged default all-streets payload, all admission guards, original global utility/identity translation and independent numeric scoped replay/visible-information BR. Do not describe this as solving or speeding up the rejected all-streets raised game. Shared postflop kernels and Coach remain separate.

- Preflop legal-hand setup may restrict prefixes to root/flop only in explicit flop-checkdown mode and cache canonical flop decoding. Preserve literal all-streets behavior, identical active legal hand sets, sorted info identities and exact full solver payloads against the frozen old-loop test reference. Retain every physical-world/resource guard; do not infer memory or runtime gains without paired complete calls and separate traces.

- Preflop `future_indexing="flop-sign"` is opt-in flop-checkdown only. Group original normalized physical worlds by private pair/public flop/discrete final sign in deterministic first-seen order with bounded compensated mass sums; never reveal futures, renormalize, average signs or change original output counts/priors. Retain the complete original-world vector envelope and every old cap, then pre-admit separate grouping references/work before grouping or compact copies. Compact original seven-field rows remain charged; grouped rows serve training, all exact checkpoints and final diagnostics and are released before serialization on success/error. Changed summation order requires independent full-world policy/visible-information BR replay with predeclared tolerances and measured complete-call gains; no bitwise, full-deck, shared-kernel or RSS claim.

- Preflop `world_admission="grouped-vector"` is explicitly opt-in grouped flop-checkdown only. Replace only the legacy physical-worlds times requested-iterations proxy with the minimum-legal-iteration construction bound (10 per world, at most 300,000 physical worlds at the current constant), enforced in compatible-count preflight before ranking/raw-world allocation. Candidate-pair admission and the original-world vector/checkpoint envelope still use full requested iterations, with grouping/copy/work caps before allocation; retain all other guards. Report the old world-iteration cap as reference, its enforced slot as null and the actual construction-row limit separately. Preserve default path/payload, physical outcomes/priors, compact restoration, independent full-world replay and all target misses. This is admission-only, not a storage-byte/RSS bound or permission to change shared postflop/turn/river kernels.

- `flop_checkdown_solver.py` is a separate direct fixed-flop betting adapter with full hidden future-deck integration and forced turn/river checkdown. It does not change shared postflop or preflop APIs. Preserve exact binary64-input rational pair normalization after board/private blockers, 990 unordered boards/1,980 ordered outcomes per pair, categorical sign rows (at most three per pair), matched-wager refunds and symmetric existing-pot share values. Never reveal future cards in information sets or describe this as later-street/full-deck preflop solving. `flop_checkdown_worlds.py` admits candidate/pair/rank-call caps before ranking; the solver reserves tree/action and full requested vector/diagnostic work using a three-row-per-pair structural upper bound before calling build. Ranking instructions are outside bookkeeping-loop counts and have their own bounded call count. Positive probability underflow must reject rather than discard support. Keep independent ordered-deck, best-five numeric-rule/visible-information BR replay and constructive known-value coverage. Complete-call timings and separate allocation traces establish only recorded model-specific evidence, not RSS or general speed gains.

- `preflop_full_board_equity.py` prepares bounded exact full-board showdown categories for the separate `preflop_push_fold.py` API. Preserve exact binary64-input rational private-pair conditioning, all 1,712,304 unordered boards per compatible pair, hidden-board own-hand policies, nonzero category support and pre-enumeration pair/rank caps. The restricted SB fold/shove, BB fold/call game uses total stacks/blinds, refund-aware net transfers and full requested work admission. Structural table validation is not proof that caller-supplied counts came from real boards. Independent best-five full enumeration and numeric-rule own-hand best responses in `scripts/preflop_push_fold_validation.py` remain the oracle. No limps, non-all-in raises, later-street betting, full-range or multiway claim follows.

Optional prepared fixed-street `training_backend="native"` requires an explicit
source build and retains Python rules, defaults and exact diagnostics. Preserve
actor/own-hand/public-node policy indexing, affine matched-wager utilities,
simultaneous CFR/DCFR versus alternating CFR+ schedules, zero-mean pair mass,
strict complete-input protocol checks, source/compiler/executable provenance,
and independent full-request native work/storage admission. Historical admission
also remains mandatory; complete-solve bookkeeping replaces only the reference
trainer charge. Do not equate modeled native storage or Python tracemalloc with
RSS. See [native training scope and evidence](docs/native-fixed-street.md).

The [weighted preflop exact witness](docs/preflop-weighted-sequence.md) is a
separate fixed research game with forced full-board checkdown. Preserve its
predeclared physical-count/spec hashes, independent legal-history/payoff/flow
reconstruction, own-hand responses and unchanged rational LP limits. Keep the
candidate separate from independent verification, retain failed feasibility
observations and require clean-source saved-file verification before publishing
formal proof. No production defaults, earlier/later-street model, range caps or
frontend behavior are expanded by this certificate.

The [exact-anchor trainer comparison](docs/preflop-exact-anchor-comparison.md)
keeps the saved rational proof separate from finite-iteration production
strategies. Preserve strict rational `-BR_BB <= V_exact <= BR_SB`, BB own-utility
signs, pinned physical counts and full-request admission before build/training.
Keep early target misses, final quality gates, backend agreement and timings
separate; do not require policy equality to one chosen equilibrium or infer
RSS/native memory from Python allocation traces.

The [covered preflop count pool](docs/preflop-covered-counts.md) is a separate
explicit prepared-data path. Keep ordinary four-pair enumeration/solver admission
literal. Admit covered target candidates/pairs before orbit work, reject every
missing or conflicting joint suit orbit, and keep full requested solve budgets
before tree/native invocation. Preserve exact global blocker conditioning and
separate private identities. Source fingerprints and structural validation do
not authenticate counts. Never describe synthetic range tests as physical
accuracy evidence or infer permission for more enumeration from represented
board coverage. Shared kernels/defaults and later-street work remain unchanged.

The [best-five physical reference](docs/preflop-five-card-reference.md) is an
isolated fixed research executable. Require exhaustive five-card tuple parity
before its full-board census, exact actual call counts, the old full-board
anchor, independent production seven-card count agreement, clean frozen source
and unchanged build identities. Compilation or consistent category totals alone
do not certify new counts. Keep binary data/builds outside Git and preserve
all failure observations. No production rank/board limit or backend changes
follow from this reference.

The [physical AA/KK range experiment](docs/preflop-aa-kk-physical-range.md)
retains all 36 private pairs and uses only the independently checked three-class
count basis. Verify the constructive +1-chip lower/upper bounds from independent
numeric rules before comparing trained policies. Preserve strict rational value
containment, legal own-hand responses and full-request admission. The fixed
AA/KK result does not establish mixed-range or later-street equilibrium accuracy.

The [generic best-five reference](docs/preflop-generic-five-reference.md) accepts
only one-to-four explicitly admitted private pairs after current-build exhaustive
conformance. Validate the whole argv before output/work; preserve ordered roles,
full board/call censuses and complete failed stdout/stderr. No source-count
query may bypass original production preparation caps. Keep raw independent and
native values, old physical anchors and source/both-build identity checks.
This research extension adds no production backend/default or equilibrium claim.

The [mixed physical preflop benchmark](docs/preflop-mixed-physical-range.md)
retains all 72 AA/QQ-versus-KK pairs and independently authenticates both
three-class physical bases. Preserve exact global priors, own-hand legal BRs,
constructive [1/2,1] value bounds and interval-intersection semantics. There is
no exact mixed-game value anchor. Keep final quality gates, complete-call
admission and all raw policies/failures; no solver default or work-cap change.

The [mixed physical exact witness](docs/preflop-mixed-exact-witness.md) keeps
rank-type sequence-form search solely in the candidate lane. The certificate
must authenticate physical counts independently, rebuild all 72 private pairs,
retain own-hand information boundaries, enumerate all 792 legal pure responses
and require exact value agreement and zero NashConv. Disable candidate/tree/LP
calls during independent replay; never promote reduced-LP output alone to a
physical-game certificate. Preserve unchanged LP caps and every failed artifact.

The [native fixed-flop preparer](docs/native-flop-preparation.md) is explicit:
normal range/blocker/preparation admission precedes executable lookup, and
only a source-built FLOP count mode feeds the existing immutable table. Keep
COUNT/RANK semantics and original preparation/solve caps, raw board/ordered
pair echoes, even 1,980-outcome counts and separate actual 990-board/1,980-rank
censuses. Defaults remain Python. Require independent physical counts, complete
policy replay and measured cold/full-call evidence before performance claims.


For `solve_native_flop_checkdown`, preserve the single no-ranking plan and run
all historical source/tree/slot plus native trainer/combined-work admissions
before count or training executable lookup. The cold count branch belongs after
these guards in `_solve_plan`; keep Python/default and prepared-count outputs
unchanged. Report current cold preparation work separately from immutable-table
reuse and native training provenance. See [API contract](docs/native-flop-preparation.md).


Native public CFR+ targeted rematch must initialize every policy row on sweep1,
refresh every row of the updated player after each alternating update, and
retain the completed-sweep averaging order. Keep scalar/vanilla/DCFR arithmetic
and old conservative work charges intact. Require exact old/new wire evidence
and independent legal-response replay; see [experiment](docs/native-cfrplus-rematch.md).


The [weighted full-deck flop validator](docs/weighted-full-deck-flop.md) must own
literal parsing, deck/chance normalization and numeric betting/action coverage.
Disable production grammar/rank/tree/train/value/BR helpers during independent
replay. Preserve ordered future cards, globally conditioned exact priors and
own-hand/visible-history response grouping, including zero-reach rows. Keep all
raw lossless policies and quality misses; validated replay is separate from the
unchanged final 0.005-chip gate. No later-street kernel or resource cap changes.


For full-future flop CFR+, retain all old caps and charge three full training
passes before dispatch. Keep recursive/vanilla defaults and later-street payloads
unchanged. Planned CFR+, flop public diagnostics and target stopping remain
unsupported. Require the independent weighted physical/action/own-hand response
validator and a frozen quality experiment; adapter support alone is not a
convergence claim. See [flop CFR+ scope](docs/flop-cfrplus.md).


Historical turn-proof compatibility for flop CFR+ uses only the seven exact
old/current source pairs in `scripts/historical_turn_sources.py`. Preserve old
reports/policies and generation fingerprints. Unknown, reversed or omitted
source identities must reject; new measurements and source guards use actual
current hashes. Keep complete independent no-training replay and witness
reconstruction. The CFR+ comparison must first authenticate and reconstruct the
completed 3963e3c baseline, pin all misses, and preserve its 0.005-chip gate.
