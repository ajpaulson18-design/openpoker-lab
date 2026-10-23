# Solver progress record

## Second-board flop proof published; failed training pilot retained

The complete no-training `7c8d9h` quotient proof is merged in
[PR #213](https://github.com/ajpaulson18-design/openpoker-lab/pull/213).
Its four control policies have identical exact compact/unrestricted physical
responses, and both invalid projection controls reject. All seven saved files
authenticate without live poker computation; 49 focused tests and both final
Python CI matrices passed. This establishes correctness for the stated finite
game, not trained quality or general convergence.

A distinct [second-board CFR+ pilot](flop-second-board-cfrplus.md) stopped
after T140 on an adapter check that wrongly excluded numeric replay audit
metadata. Its full raw/normalized policies and identical compact/physical exact
metrics are retained with the original error and clean source/guard receipts.
T560 never ran, and the original quality gate remains null. This failed attempt
is preserved with its frozen source; a separate correction must be reviewed
before another version is measured. No completed verified policy is claimed.

The [separate replay boundary v2](flop-second-board-cfrplus-replay-v2.md)
preserves the v1 failure and validates/retains the complete replay metadata
before passing eight metrics to the unchanged adapter. Fourteen focused tests
passed before measurement. Its single frozen batch completed both fresh calls:
T140 missed 0.005 with exact physical NashConv about 0.014166984012911272; T560
passed with about 0.0016464625267553663. All eight exact compact/physical metrics
agree, both full numeric receipts pass, and all source/guard/model checks held.
The miss and original failed v1 attempt remain retained. Saved-data authentication
and final-head CI are publication gates; these are finite-game observations.

## Independent physical source rows for mixed-range work

The project-owned best-five reference now supports strictly bounded one-to-four
explicit private-pair queries after current-build exhaustive conformance. Whole
requests are admitted before binary lookup, malformed input rejects before any
output/counting, and raw failed stdout/stderr are retained. Original production
preparation caps and evaluator/solver defaults remain unchanged.

All three QQ/KK relative-suit classes now have exact full-board counts agreeing
with the separate native seven-card counter and the original independent
shared-suits anchor. The current v2 build also reproduces every five-card rank
tuple and the previous AA/KK basis. Together these source rows support later
mixed strong/weak covered ranges; wider equilibrium accuracy is still separately
measured. See [raw counts, conformance and limits](preflop-generic-five-reference.md).

## Full physical AA-versus-KK range reaches a checked exact anchor

All 36 physical AA/KK private pairs and 61,642,944 represented boards now have
an independently verified constructive +1-chip value in the finite preflop
checkdown game. Source counts come from all three exhaustively checked relative
suit classes; no new ranking occurs in the solve. The hidden own-hand model
retains six hands per player, limps and finite reraises under existing budgets.

All ten saved Python/native CFR+ profiles pass strict rational exact-value
containment and independent own-hand best-response replay. At 500 iterations
NashConv is about 0.000000608 chips and value error about 0.0000000146 chips.
This validates a full physical rank-pair range, not arbitrary starting ranges
or later-street play. See [proof, raw observations and limits](preflop-aa-kk-physical-range.md).

## Physical preflop source basis independently expanded

A separate project-owned C best-five reference agrees with the independent
Python oracle on every 2,598,960 five-card rank tuple, then checks all boards
of three AA/KK relative-suit classes using all 21 five-card subsets per hand.
All integer counts agree with the independent original anchor and separately
retained production seven-card counts. This supplies two additional physically
checked source rows for broader suit-covered ranges, without changing any
production enumeration cap or solver default. See
[raw counts, exhaustive evidence and limits](preflop-five-card-reference.md).

## Prepared full-board preflop coverage extends beyond four private pairs

A separate bounded suit-covered count pool and explicit solve entry now reuse
trusted ordinary source counts across more compatible private pairs. The
original four-pair enumeration and solver APIs retain their limits and payloads;
the new entry shares their betting/training body and full-request admission.

A frozen six-pair weighted physical fixture with five BB hands, limps and actual
reraises passes independent own-hand best-response replay in Python/native at
about 0.000000189-chip NashConv after 3,000 CFR+ iterations. Three pinned count
rows cover 10,273,824 represented boards through verified joint suit maps with
zero new ranking. The 10-iteration miss remains visible. Synthetic 36-pair tests
are separately labeled. See [limits, raw evidence and provenance](preflop-covered-counts.md).

## Python/native preflop trainers checked against the proved weighted value

The same weighted one-raise full-board checkdown game now has a frozen
finite-iteration comparison for vanilla CFR, DCFR and CFR+. All 38 retained
Python/native policies pass independent physical-count replay and strict exact
best-response containment of the separately proved value. At 8,000 iterations,
CFR+ reaches about 0.0000402-chip NashConv in each backend; earlier misses remain
visible. Complete-call timings and Python allocator traces are reported
separately, including higher native traced allocation and low-iteration process
overhead. See [protocol, raw observations and limits](preflop-exact-anchor-comparison.md).

## Weighted preflop game has an independently verified exact value

A frozen three-pair preflop/checkdown game with asymmetric stacks, limps, a BB
option, finite raises and all-ins now has an exact sequence-form equilibrium
witness at SB net-transfer value `100107990869/130471452826`. The physical count
inputs represent all 5,136,912 hidden final boards across those compatible pairs.
A separate numeric verifier reconstructs every flow/payoff and original
primal/dual inequality; a second unrolled terminal-history oracle checks all 88
own-hand pure responses. Both produce exact NashConv zero, and illegal private
information controls change the value as expected. All LP limits are unchanged.

The clean-source saved report, raw candidate and adversarial verification tests
remain distinct. This is a fixed-game accuracy anchor; production defaults,
later-street betting and private-range caps are unchanged. See
[model, proof, source identities and limits](preflop-weighted-sequence.md).

## Explicit native training passes the fixed-street comparison

Prepared preflop and forced-checkdown flop calls now have an explicit source-built
C11 training backend. Python retains table/rule validation and exact diagnostics;
default Python outputs remain unchanged. A public-hand-vector flop reduction
resolves the initial scalar experiment's DCFR probability mismatch without
loosening any frozen gate. The failed initial report remains published.

The revised six-profile experiment retains 36 timed calls and two separate
Python allocation traces. All three flop profiles exactly match Python policies
and eight diagnostics; all 38 saved policies pass independent physical-count
replay. Complete-call median ratios range from 40.13 to 103.06 on the two measured
finite games. Both mandatory CFR+ quality targets pass; vanilla flop still misses
the reported target. Native uses more traced Python allocation in the preflop
trace, and no child-memory/RSS saving is established. Strict Windows/Linux native
conformance passes. See [scope, failed evidence and followup](native-fixed-street.md).

## Exact rational equilibria establish both small river game values

A bounded development sequence-form search now supplies rational equilibrium
witnesses for the two archived river fixtures: polarised value 25 and weighted
raised value -43339/2163, both with exactly zero NashConv. The weighted game
uses 49/53 sequence coordinates instead of enumerating its millions of pure
policies. This is a fixed configured numeric-model result, not a production
solver/API change.

An independent verifier reconstructs the payoff/flow model, validates primal
and dual feasibility, checks normalization and complete own-information
responses, and reproduces all eight exact metrics. The earlier trained
policies and their target misses remain unchanged. See
[proof, limits and reproducible evidence](river-sequence-equilibrium.md).

## Prepared-call profiling identifies training as the next bottleneck

Pinned physical-count preflop and fixed-flop games now have a frozen coarse
profiling artifact. Training accounts for more than 99.8% of every complete
instrumented call in both fixtures; all eight payloads match their current
unwrapped reference and pass independent policy/own-hand response replay.
Guarded ranking calls remain zero. All raw times and source identities are
retained. This supports a separate optional native-training experiment, with
Python diagnostics preserved; no native result or broader game coverage follows.
See [scope, measurements and reproduction](fixed-street-profile.md).

## Exact normalized certificates cover both archived river games

All fifteen saved extension/long-budget river records now have exact profile
EV and legal own-information response bounds, including the weighted raised
game. Mandatory independent physical replay precedes exact arithmetic, and
the saved artifact is reloaded for complete fresh reconstruction. Every
polarised row also exactly matches the separate five-history pure-response
oracle and contains the known value 25.

Five records meet exact NashConv 1/1000 and all ten misses remain recorded.
The weighted raised 10k bounds span approximately 0.000279553443 chips;
the later witness above establishes its exact game value. Sol separately reconstructed all
270 normalization rows, all eight metrics and 83 fingerprints, comparing
with independent exact vectors computed before the final artifact. The
13 focused tests pass normally and with Python optimization; 53 broader
exact/replay tests pass. Production and earlier-street code is unchanged.
See [certificate scope, results and reproduction](river-rational-certificate.md).

## Optional per-solve turn terminal caching preserves complete policies

The matrix-free turn API now accepts explicit `terminal_cache="ranked-lru"`
for admitted fixed CFR+ calls with at most two original hands per player and
48 branches. Private branch composition preserves original outer/root-fold
arithmetic, fallback accounting and every legacy result field. Defaults remain
unchanged. A separate full-request logical cache budget and 16,384-entry LRU
apply; target mode and exceptional conditioning reject before training.

Seven complete policies pass independent all-eight-metric replay and Sol's
separate hash/counter/source/timing audit. Both 1k candidates and selected 3k
exactly match archived legacy payloads. Selected 3k also recomputes its exact
normalized rational certificate, with NashConv about 0.00047081005 below exact
1/1000; both 1k misses and all four 300-sweep misses remain recorded.

Three paired complete calls gave ratios of default median to cached median
1.245519 selected / 1.373634 full deck, passing the predeclared 1.10 gate on
both fixtures. These are shared-host observations, not a general speed or RSS
claim. All 92 broader regression tests passed; the final 32 focused tests
passed normally and with `python -O`. The 18 captured old default outputs
also remain identical. See [API scope, limits and complete evidence](turn-terminal-cache.md).

## Exact normalized response bounds cover every remaining river

All six archived full44 CFR+ policies now have exact rational EV/legal-response
bounds, preserving all 44 rivers per private pair and the original independent
physical model. Exact NashConv is approximately 0.00145336964360 /
0.000646157234394 / 0.000161593137092 at 1k/1.5k/3k on both backends.
The two 1k misses and four later meets of exact 1/1000 remain explicit.

An optional stable chance partition in the development exact helper completes
each audit at 82,950/100,000 modeled work units without raising work/depth/bit
caps. The original scan default retains all six complete selected-turn outputs.
All 47 focused tests passed. Sol separately reconstructed every normalization
row/hash and verified exact metric identities, model dimensions and 65 frozen
fingerprints. Maximum exact-versus-floating metric difference is 1.07e-14 chips.
Production and earlier-street code is unchanged. These bounds concern explicitly
normalized saved policies; see [derivation, evidence and limits](full-deck-turn-rational-certificate.md).

## Research: bounded turn terminal reuse preserves complete policies

A development-only per-solve memoizer now has exact complete-policy parity
against both archived matrix-free CFR+ 1,000-sweep turn fixtures. All six saved
profiles independently replay all eight metrics; Sol's separate artifact audit
checked hashes, physical counts, resource counters, medians and 62 frozen
source/input fingerprints. Maximum scalar difference is 1.42e-14 chips and all
84 focused tests passed. Every accuracy threshold miss is retained.

Three paired complete 300-sweep calls per fixture gave median baseline/candidate
ratios of 1.490869 for selected rivers and 1.423057 for full44, meeting the
predeclared 1.10 research gate in this environment. The wrapper retains original
solver admission, adds a separate full-request cache-slot guard and capped LRU,
validates before lookup, preserves fallback accounting, and excludes exceptional
numerical paths. Production/shared/earlier-street code is unchanged. No public
solver mode, general performance or memory gain follows; see
[scope, raw timings, evidence and reproduction](turn-terminal-memoization.md).

## Full remaining-deck turn accuracy on both existing backends

The existing full44 fixture now has complete CFR+ evidence at 1k/1.5k/3k
sweeps on both materialized/public-batched and matrix-free backends. Each
private pair retains all 44 remaining rivers: four pairs, 176 physical worlds,
48 globally reachable public rivers and 1,112 information sets. Independent
NashConv is approximately 0.00145336964 / 0.000646157234 / 0.000161593137
on each backend. Both 1k profiles miss the unchanged 0.001 reporting threshold;
all four 1.5k/3k profiles meet. No stopping target is configured.

All six complete saved policies independently replay all eight metrics before
and after saving. Sol separately checked each byte hash, physical deal law,
resource dimensions and all 53 source fingerprints. Maximum scalar difference
is 2.84e-14 chips; all 24 focused tests passed. Original modeled-work caps and
production/earlier-street sources remain unchanged. Raw uncontrolled timings,
including an extreme outlier, are retained without a performance claim. See
[full model, admission, evidence and reproduction](full-deck-turn-accuracy.md).

## Exact rational response bounds for normalized selected-turn policies

All six saved selected-turn CFR+ profiles now have exact rational EV and legal
best-response bounds for explicitly normalized complete policies. The four
3k/10k threshold meets and two 1k misses remain unchanged under exact `1/1000`
NashConv comparisons. The 10k legal-response interval is approximately
`[-19.047634645102352, -19.04759226231214]` OOP chips in the configured model.

All 32 focused tests passed. Sol independently reconstructed all row ledgers
and normalized hashes, checked eight exact metric identities and all 55 source
fingerprints. Maximum exact-versus-floating metric difference is 1.50e-14 chips;
maximum row adjustment is 1.16e-16. This audits the existing independent numeric
rules with exact arithmetic; it does not establish a raw-binary64 interval proof,
compute an exact equilibrium, or extend selected rivers to the full deck.
Production and earlier-street source are unchanged. See
[derivation, provenance, resource limits and evidence](turn-rational-certificate.md).

## Longer-budget conditional turn-to-river accuracy

Both existing backends now have saved complete CFR+ evidence at 1k/3k/10k
on the predeclared two-runout, weighted, raised, asymmetric-stack fixture.
Independent NashConv is 0.00423446838 / 0.000470810047 / 0.0000423827902
on each backend to the shown precision. Both 1k profiles miss the unchanged
0.001 reporting threshold; both 3k and 10k meet. All six policies are retained.

Every saved complete policy independently replays all eight metrics, physical
counts, both street configurations and selected-runout legality. Sol separately
checked saved bytes/hashes/replay and all 53 source fingerprints. Maximum
scalar disagreement is 1.42e-14 chips. All 21 focused tests passed; full-request
resource charges remain under the unchanged backend caps. Production and
earlier-street source are unchanged. See
[full evidence, scope and reproduction](turn-selected-accuracy.md).

## Bounded longer river solves meet the bluff-catcher threshold

The isolated matrix-free river ceiling is now 100,000 requested iterations
under its unchanged 30-million modeled hand/state/pass cap. Defaults, shared
postflop limits, training and ordinary payloads remain unchanged. Full requested
work and conservatively planned diagnostics still admit before information
rows and training, even when a target could stop early.

On the predeclared polarised fixture, independently replayed CFR+ NashConv is
0.00790056594 / 0.00265815977 / 0.000907974712 at 10k/30k/100k. Only 100k
meets the unchanged 0.001-chip reporting threshold; every miss is retained.
All saved profiles pass all eight independent metrics and normalized exact
rational known-value witnesses. The 10k complete payload exactly equals its
archived baseline. All 41 focused tests and 12 complete ordinary parity/replay
cases pass. No speed/RSS or broader equilibrium claim follows. See
[admission, full policies and reproducible evidence](river-long-budget.md).

## Stable turn root-fold products at normal branch mass

A rare exact binary-rational pair sum now preserves representable fold values
when positive weighted reach, joint mass or normalized mass becomes
zero/subnormal on the ordinary root path. The normal-mass regression loses
1.0 under a payoff-scale transformation in the old kernel; the correction
agrees exactly with the independent one-world answer. Pair reservations precede
all rare conversions/scanning under both shared and separate cumulative caps.
Integer-width bounds are explicit and make no operation-count or RSS claim.

All 55 focused tests passed. All 48 independent numerical fold-vector witnesses
equal their independently computed binary64 answers; old output differs in 32,
up to 1.0. All 12 ordinary complete solver payloads and the six previously
saved exceptional complete profiles remain exactly equal and independently
replay. Every short-budget ordinary 0.001 benchmark threshold still misses. Shared ranked
river, CFR and earlier-street code remain unchanged. See
[design, resource limits and reproducible evidence](turn-root-reach-stability.md).

## Stable conditioned turn masses and fold utilities

The isolated matrix-free turn path now preserves representable selected games
whose raw branch mass is zero/subnormal. Exceptional branches use retained
mantissa/exponent masses and conditioned fold vectors. The exact one-world
regression now returns 2.5/7.5 chips at quarter/three-quarter opponent reach,
replacing 0/10. Full requested exceptional vector work is reserved before
information-row allocation and training, including every planned target check.

All 12 frozen ordinary complete payloads remain exactly equal, across two
turn fixtures, three algorithms and fixed/zero-target modes. Every policy
passes independent replay; maximum scalar disagreement is 3.91e-14 chips and
every 0.001-chip target misses. All 13 kernel, 16 adapter and 18 oracle tests
passed; the strengthened admission assertion was additionally rerun.
Shared ranked-river and earlier-street implementations remain unchanged.
Broader extreme-range ranked-kernel admission remains unresolved. See
[numerical design, evidence and reproduction](turn-conditioned-mass.md).

## Research-only same-run river CFR+ tail realization

An exact Fraction conversion reconstructs original-weight CFR+ tails from
same-trajectory D3000/T10000 snapshots using each player's own realization
reach. All four predeclared fixture/backend cases pass complete independent
replay and correction gates. Full production payloads and prefix strategy
rows exactly match the historical baselines; observational callbacks leave
the final solver return unchanged.

The bluff-catcher gap falls from 0.00790056594 to 0.00687271407, still missing
the unchanged 0.001 target. Weighted raises falls from 0.000279553443 to
0.000223234524, meeting it on both backends. Every prefix/full/tail policy,
including all misses, is retained. Tiny corrections/fallbacks are explicit;
maximum reconstructed-flow discrepancy is 3.39e-20, under the predeclared
1e-11 gate. This is an experimental gate, not a formal trainer rounding bound.

All 40 focused tests pass, including an independent exact toy proof, all-row
callback parity, error restoration and hardened replay. Saved-policy audit
adds six separate rational one-bet witnesses; maximum diagnostic disagreement
is 1.78e-14 chips. This stays research-only, with production/shared/earlier-street
source unchanged and no speed/RSS claim. See [derivation, complete evidence and reproduction](river-tail-realization.md).

## Longer-budget independently verified river CFR+ accuracy

An evidence-guided extension preserves all 12 fixed river CFR+ profiles at
1,000/3,000/10,000 iterations with materialized and matrix-free backends.
Weighted raises meets the unchanged 0.001-chip NashConv target at 3,000 and
10,000: gaps 0.000848854325 and 0.000279553443. The polarised bluff-catcher
still misses at 10,000 with gap 0.00790056594. Four profiles meet, eight miss.

Every saved complete policy passes hardened independent replay across all
eight metrics, physical counts and metadata; maximum disagreement is 1.78e-14
chips. Six separately normalized exact rational one-bet witnesses have legal
BR intervals containing the known 25-chip game value. This certifies only
those explicitly normalized witness profiles, with probability adjustment at
most 9.34e-17. It is not a general binary64 interval proof or raised-game proof.
All policies/hashes, target misses and raw single-call timings are retained.
Production, shared trainer and earlier-street source remain unchanged; no
runtime/memory claim follows. See [evidence, scope and reproduction](river-accuracy-extension.md).

## Strict complete-result turn and river replay

The independent oracle now requires current board/runout/reachability metadata
and core physical counts, checks every world/private-pair alias with bool-safe
integer types, and compares both unilateral gains and metric identities.
Reachability is derived from physical worlds; both existing canonical serializer
orders are preserved. Independent BR sanity checks precede per-player clipping.

All 18 focused tests passed normally and with Python `-O`. All 24 complete
20-iteration profiles across four fixtures, two backends and three algorithms
pass the hardened replay; maximum scalar disagreement is `3.91e-14` chips and
every 0.001-chip target still misses. Production/earlier-street code is unchanged.
See [contract, source hashes and results](turn-river-independent-validation.md#cycle-3-complete-result-metadata-and-gain-validation).

## Matrix-free turn and river diagnostic gain consistency

The isolated adapters separately clamp accepted small negative unilateral BR
differences before summing NashConv. A positive gain can no longer be canceled
by the other player's tolerated negative roundoff and falsely satisfy a zero
target. Existing finite/material-invalid guards and training are unchanged.
The reproduction is fault-injected accepted roundoff, not a measured natural
solver failure or a formal floating-point bound.

Eight new regressions cover both players, fixed and target modes, continuation
through both checkpoints, invalid responses and ordinary profiles. The combined
42 focused tests passed. All 24 ordinary complete profiles match the frozen
baseline and pass independent replay. Shared postflop/preflop/flop diagnostics
remain outside this isolated change. See the
[cycle 2 method and results](turn-river-independent-validation.md#cycle-2-preserve-each-unilateral-gain).

## Independent complete turn and river policy replay

A development oracle rebuilds physical deals, weighted blocker conditioning,
numeric betting rules, best-five ranks and legal information-set best responses
without production tree, payoff, CFR or diagnostic helpers. It checks every
serialized policy row, including rows with zero policy reach. Production solver
and preflop/flop behavior are unchanged in this validation slice.

At frozen `431db6f`, all 216 calls across four finite fixtures, materialized and
matrix-free backends, vanilla/DCFR/CFR+, and 20/100/300 iterations passed
independent replay. Maximum scalar disagreement is `3.91e-14` chips. Every
measured profile missed the predeclared `0.001`-chip NashConv target; these
results validate diagnostics, not that convergence claim. Thirteen new tests
include known rational equilibrium, exhaustive tiny-game legal BR, no-peek,
decimal sizing, blockers, full turn chance and malformed-policy rejection.
Full CI suites passed on Python 3.11/3.12/3.13. See the
[scope, all results and reproduction](turn-river-independent-validation.md).

## 2026-10-09 matrix-free turn continuation

Branch `solver/matrix-free-turn-20261009` follows merged river PR80. New isolated
turn API preserves global pair/runout conditioning, 48 possible rivers versus
44 per private pair, original hand indices and exact visible-information BR
ordering. A direct selected-card multiplicity operator accelerates turn folds.
Nine independent kernel test methods, integration replay/guard/no-peek tests and
all **488 full-suite tests** pass. No flop/preflop/Coach modules are edited;
shared defaults retain their previous arithmetic.

Small complete calls are slower, not a claimed speedup. Full two-river random
ranges now admit 2,140,380 compatible outcomes without world lists (4.48s,
45.12 MB traced at ten iterations); the 12.158-chip gap explicitly shows this
probe is not converged. Prepared fold calls improve 17â€“22x. Investigation of
finite-iteration differences traced them to exact-tie regret roundoff; all
candidate policy metrics pass materialized replay. A bounded small-pair phase
experiment found a narrow crossover, insufficient for broad dispatch. See
[mathematics, evidence and remaining constraints](matrix-free-turn.md).

## 2026-10-09 matrix-free river storage

Branch `solver/matrix-free-river-20261009`, base `3ee96fb`: a separate fixed-board
API eliminates quadratic pair-world/prefix-edge storage without changing world
API limits or default flop/preflop/Coach behavior. Exact blocker-conditioned
marginals, ranked terminals and prepared CFR/BR traversals retain the configured
game. Full random ranges now admit all 1,081 holdings per player (1,070,190
compatible deals), without materialized worlds. Independent review caught an
extreme joint-product underflow; the backend now explicitly rejects it.

Complete-call median improvements are 1.54â€“2.43x on 128/256-hand fixtures, with
256-hand traced allocation reduced from 25.59 MB to 1.75 MB. Full-range CFR+
exploitability fell to 0.0404 chips at 100 iterations on the pot-100 fixture.
Fourteen default result dictionaries match merged base exactly; the shared
preflop resource-envelope review found no loop expansion. See
[model, validation, measurements and limits](matrix-free-river.md).

## 2026-10-09 ranked river terminal work

Branch `solver/ranked-river-20261009`, base merged `5c712f8`: added an optional
fixed-board ranked payoff backend for public-batched river training and
diagnostics. Blocker-aware rank sweeps, compensated accumulation and direct
summation on ill-conditioned cases preserve physical range products and
short-stack refunds. Rational pair-loop tests caught and prevented two
cancellation defects. No earlier-street or Coach behavior is changed.

Cached-sparse terminal phase comparisons show 1.22â€“15.19x speedups across
64â€“512 hands per player, with increased working allocation. Complete-call
results are mixed: small/preparation-heavy cases can slow down, while the
256-hand/40-iteration probe improved median time by 1.40x DCFR / 1.72x CFR+.
That CFR+ probe uses 96% of the existing world-node guard; no limits were
relaxed. Default results matched the merged baseline exactly on eight
flop/turn/river cases. Full local tests passed 453 before the final numerical
regression; all 48 focused tests passed after it. See
[mathematics, validation, exact measurements and architectural limits](ranked-river.md).

## 2026-10-09 turn/river accuracy-controlled follow-up

Branch `solver/turn-river-accuracy-20261009`, base `b7bf525`: added optional
absolute-chip exploitability targets with exact completed-iteration checkpoints
and explicit budget misses. Existing training schedules and default results
remain unchanged; target mode rejects earlier streets and unsupported backends.
All four CFR+ benchmark fixtures reached 0.1 chips in 100â€“240 iterations;
same-iteration policy comparisons were identical. DCFR missed three targets.
Six rational poker equilibria and independent pure-policy best responses extend
validation beyond Kuhn. The full suite passed **436 tests in 114.951 seconds**.

Larger synthetic ranges (up to 128 hands per player on river, 16 on full-deck
turn) expose pair-world memory growth; all twelve scaling cases were admitted.
Their single-call timings ran alongside unit tests and are descriptive, not
controlled optimization comparisons. Commercial parity remains unproven.
See [accuracy semantics, research, measurements and limits](turn-river-accuracy.md).

## 2026-10-09 isolated turn/river quality work

Branch `solver/turn-river-quality-20261009`, base `65c9ba7`: optional
alternating CFR+ with linear post-sweep own-reach averaging is enabled only
for turn/river library starts. An independently authored callback reference,
closed-form Kuhn equilibrium, exhaustive pure-policy BR checks and public
backend differential tests validate the addition. Optional exact public-vector
diagnostics retain generic best responses as the reference. Coach/UI code,
flop tree construction, evaluator, defaults and existing result shapes remain
unchanged; source-based vanilla/DCFR comparisons on six turn/river/flop cases
matched the base exactly. All **352 tests passed in 70.236 seconds**.

Target-only CFR+ regret vectors reduce measured complete-call runtime by
21â€“28% across eight synthetic fixture/checkpoint comparisons with pre-optimization
source `7553734`; maximum frequency/value differences are `5.42e-13`/`7.11e-14`.
Diagnostics-only turn evaluation is 2.17x faster on a 352-world uniform-policy
fixture with higher memory consumption. The completed 36-row algorithm report
shows lower CFR+ gaps but higher runtime than DCFR at 300 iterations, so the
default is unchanged. No external runtime dependency or third-party code is
incorporated. The user explicitly authorized public push and merge on 2026-10-09;
publishing uses the authenticated GitHub connector. See
[quality work, exact benchmarks, research decisions and remaining priorities](turn-river-quality.md).

Snapshot: 2026-10-09. Mathematical calculation only; the AI Coach workstream
and its contracts remain separate. GitHub is the delivery source of truth.

## restricted-river-v2

- Streets: river only, fixed public board; no future-card chance nodes.
- Players: two. Caller-provided weighted private ranges; exact compatible
  hole-card pairs, board removal and private-card blockers.
- Actions: check, one fixed affordable bet, fold, call. No raises, multiple
  bet sizes, stack cap, rake or range inference in this entry point.
- Tree: four public decision nodes, eight decision edges, five terminal
  lines per compatible private-hand pair. Two information sets per hand.
- Work limits: 10â€“10,000 iterations and at most three million nominal
  hand-pair iterations. Exact traversal; no sampling or card abstraction.
- Algorithms: vanilla simultaneous CFR (default); opt-in DCFR(1.5,0,2), with
  sign-split cumulative-regret discounts and quadratic own-reach averaging.
- Version: `restricted-river-v2`; algorithm reported in every result.
- Quality: exact information-set best responses against the average profile;
  NashConv in chips and exploitability = NashConv/2. Locked profiles report
  unrestricted deviation gaps, not equilibrium certificates for a locked game.

## Reproducible benchmark

`benchmarks/solver-v1.json` defines six synthetic fixtures, 50/200/500 iteration
checkpoints, three timed independent calls per checkpoint, and a separate
untimed traced-memory call. Each report records source/configuration checksums,
revision label, dirty-worktree flag, Python version, platform, ranges, pot/bet,
deal/information-set counts, timing samples, peak memory, values and exact gap.
The baseline source was extracted byte-for-byte from GitHub commit `477d073`;
the optimized solver is commit `0f10524`. No external solver output is used.

Run from the repository root:

```text
python -m scripts.benchmark_solver --algorithm vanilla --output work/vanilla.json
python -m scripts.benchmark_solver --algorithm dcfr --output work/dcfr.json
```

To reproduce the prior implementation, extract `pokerlab/solver.py` from
`477d073` to a temporary file and pass `--solver-source PATH` and
`--revision-label 477d073`. Original baseline, optimized-vanilla and DCFR
reports are in `benchmarks/results/`. Source checksums describe the exact
measured bytes; line endings may differ across platforms.

On this shared Windows machine (Python 3.12.14), median runtime across the
six fixtures was:

| Iterations | Prior vanilla (ms) | Optimized vanilla (ms) | DCFR (ms) |
| --- | ---: | ---: | ---: |
| 50 | 21.46 | 6.61 | 7.62 |
| 200 | 75.50 | 30.11 | 29.71 |
| 500 | 163.68 | 82.34 | 69.87 |

At 500 iterations, the median of scenario runtimes fell about 50% for vanilla
CFR. Its NashConv values matched the prior implementation to floating-point
rounding (under 1e-12 in these fixtures). Median traced Python peak memory was
about 12.1 KB before and 12.2 KB after: this is a runtime improvement with a
small memory increase, not a memory-reduction claim. Tracemalloc excludes
process RSS and native allocations. Wall timings are machine-dependent and
noisy; these small fixtures do not establish performance for full ranges.

Median NashConv across the six fixtures was 2.6323/1.0577 chips
(vanilla/DCFR) at 50 iterations, 0.8764/0.2411 at 200, and 0.4093/0.0415 at 500.
Per-fixture results matter: DCFR's bluff-catcher gap at 200 was 4.0344 versus
vanilla's 3.6686, and at 500 the gaps were nearly equal (2.0778/2.0826) while
DCFR took 41.92 ms versus vanilla's 23.64 ms. DCFR remains optional.

## Validation and provenance

The 34 focused tests include an independently implemented recursive CFR oracle,
exhaustive pure-policy best responses, card blockers, weighted ranges, ties,
node locks, a known bluff-catcher equilibrium, deterministic runs and legal
strategy distributions. The full local suite passed 252 tests after using a
writable Windows test directory outside the sandbox that denied temporary
SQLite files. GitHub Tests passed on Python 3.11, 3.12 and 3.13 for `0f10524`.
The evaluator was not changed; its exhaustive hand census was not rerun.

No third-party code, dependencies, trained values, licenses, ownership or
repository visibility settings changed. Research and the targeted public
patent-search limits are recorded in `docs/solver-research.md`; that research
does not establish freedom to operate.

## configured-river-v1: existing PR #23 integration

The existing stack-aware PR #23 was repaired and integrated with the optimized
kernel. This builds on its original game-tree, sizing and settlement code.
The fixed-bet compatibility entry point retains the optimized traversal;
explicit configurations use the finite public tree. Both expose
`river-strategy-v1`, sized histories, legal per-hand action distributions,
vanilla CFR and optional DCFR, and exact information-set best responses.

Supported: two players, fixed river board, weighted exact private ranges,
up to eight configured opening sizes and eight raise sizes, 0â€“8 raises per
betting sequence, positive shared or asymmetric stack caps, optional shoves,
minimum full raises, short-all-in non-reopening, capped calls and uncalled-chip
refunds. There is no blind-sized minimum opening bet, rake, multiway tree or
future-street chance node. Chip sizes use the documented fractional abstraction.
Tree limits are 10,000 public decision nodes, three million nominal deal
iterations and 30 million deal-node iterations. Larger full-range trees remain
computationally restricted.

Repairs include truthful scalar `bet` metadata: a 100%-pot wager clipped by
a 50-chip stack is reported as 50; multiple/asymmetric opening amounts yield
`None` and the per-size profile is authoritative. Complete pure-policy
enumeration independently validates multi-size/raise best responses. An
adversarial fixture demonstrates a hidden-card-dependent choice can score
better than any legal hand/history policy, and is excluded by the oracle.
Cross-backend tests verify a configured one-size tree matches the optimized
kernel for both algorithms. All 287 local tests passed, including the current
AI Coach/explanation regressions. No coach, practice, persistence, contract,
server or browser code differs from the GitHub base.

`benchmarks/river-tree-v1.json` adds five versioned fixtures, again at
50/200/500 iterations with three timed repeats and separate memory calls.
Each has four compatible weighted deals. The 500-iteration measurements were:

| Configured fixture | Public nodes/actions | Information sets | Vanilla ms | DCFR ms | Vanilla NashConv | DCFR NashConv |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Legacy optimized | 4 / 8 | 8 | 24.17 | 22.60 | 0.167167 | 0.000448 |
| 33% / 75%, no shoves | 6 / 14 | 12 | 91.65 | 131.80 | 0.197893 | 0.027571 |
| Raises and shoves, stack 220 | 12 / 32 | 24 | 211.00 | 234.31 | 0.891051 | 0.002008 |
| Unequal stacks, oversized wager refund | 8 / 20 | 16 | 136.36 | 183.33 | 0.312111 | 0.000428 |
| Stack 120, short raise branches | 8 / 20 | 16 | 134.75 | 245.18 | 0.957332 | 0.174692 |

Traced peak memory for vanilla/DCFR was approximately 5.3/5.3 KB for the
optimized fixture and 24.9â€“44.0/24.9â€“44.1 KB for the configured fixtures.
These narrow two-hand examples quantify tree growth and solution quality in
their exact abstractions; they do not establish realistic full-range speed.
DCFR improves these measured gaps while costing more time on several trees.

```text
python -m scripts.benchmark_solver --config benchmarks/river-tree-v1.json --algorithm vanilla
python -m scripts.benchmark_solver --config benchmarks/river-tree-v1.json --algorithm dcfr
```

The two configured JSON reports record actual normalized configurations, tree
sizes, backend, strategy schema, input checksum and both solver-module
checksums. Earlier v2 benchmark files remain the original measurements of that
version. The integrated default adds public strategy serialization, so its
runtime/memory is represented by the configured benchmark's legacy fixture.

## configured-turn-river-v1: exact public chance

The additive `solve_turn_river` API now solves finite two-street heads-up games.
The configured river solver and the new API share `cfr.py` and `river_tree.py`;
the optimized fixed-bet compatibility kernel remains separate. Both CFR variants
preserve the prior configured-river results: 12 weighted multi-size, raised and
asymmetric configurations at 10/100 iterations matched the old implementation
with maximum numerical difference exactly zero.

Each compatible private pair has 44 physical river cards. Selected runouts
explicitly condition the complete joint hand/card distribution, changing private
priors when blockers remove different numbers of selected cards. Turn information
sets omit the latent river; river information sets include its revealed card and
the entire preceding turn history. Best responses aggregate hidden worlds before
maximization and sum public chance branches. Settled turn commitments are matched,
refunded and carried to the river; pot fractions and stack caps remain cumulative.
Each fresh river street begins OOP. See [validation](turn-river-validation.md).

Supported streets are now river and turn-to-river. The new library supports the
same finite configured sizes, raises, stacks and all-ins, weighted private ranges,
exact cards, vanilla CFR and DCFR(1.5,0,2). It reports `postflop-strategy-v1` and
exact NashConv/exploitability. Browser/coaching APIs retain their previous shapes.
The new limits are 10,000 public decision nodes, three million candidate-pair and
chance-world iterations, and 30 million per-world decision-node iterations.

Eleven new independent tests cover physical worlds, global subset conditioning,
serialized-profile values/BRs for both algorithms, exhaustive tiny-game pure-policy
BR maxima, a future-card-peeking adversary, OOP street restart, cumulative sizing,
asymmetric settlement, invalid inputs and measured convergence. The 69 existing
mathematical tests also passed. The full local suite passed 298 tests, including
all application/AI Coach regressions, in 79.848 seconds using a writable Windows
test directory. Card evaluation code is unchanged; its exhaustive census was
not rerun. The GitHub Python 3.11/3.12/3.13 matrix passed for the implementation
and test commit; final publication checks also run on the report/docs commit.

`benchmarks/turn-river-v1.json` defines two synthetic fixtures at 20/100/300
iterations, three timed repeats and a separate untimed tracemalloc call. Reports
in `benchmarks/results/turn-river-{vanilla,dcfr}.json` identify measured source
revision `b093c99`, five exact module checksums, configuration checksum, platform,
Python and dirty-worktree state. Benchmark files were uncommitted at measurement;
the recorded implementation hashes match the committed implementation. Later
commits add tests/docs/reports, without changing the measured modules.

| Fixture at 300 iterations | Worlds / deals | Public nodes / information sets | Vanilla seconds | DCFR seconds | Vanilla NashConv | DCFR NashConv |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full physical deck, no raises | 176 / 4 | 580 / 1112 | 8.850 | 7.559 | 1.477155 | 0.021497 |
| Two selected rivers, asymmetric stacks/sizes/raises | 8 / 4 | 69 / 138 | 0.787 | 0.834 | 3.234919 | 1.811793 |

Both fixtures visit one chance branch per world: their per-world traversal
counts are 16 and 41 decision nodes. Traced peaks are about 2.41 MiB and 288 KiB
at 300 iterations. Tracing excludes process RSS/native memory. Wall times vary
on the shared Windows machine; small synthetic ranges do not establish full-range
performance. DCFR's 20-iteration gap was worse on both fixtures (16.205 vs 15.125
and 29.649 vs 27.633); better late gaps do not justify changing the default.

```text
python -m scripts.benchmark_turn_solver --algorithm vanilla
python -m scripts.benchmark_turn_solver --algorithm dcfr
```

No external implementation, dependency, trained values, licensing or repository
ownership changes were incorporated. Primary research and conceptual references
are recorded in [turn research notes](turn-research-notes.md).

## configured-turn-river-v2: optional planned traversal

`traversal="planned"` prepares per-world static Python operations and computes
iterative value/reach passes. Recursive traversal remains the default and the
independent reference. Both variants use the same exact physical world model,
public action tree, `postflop-strategy-v1`, values and information-set BRs.
The result identifies its execution backend and planned operation limit. Generic
chance/key callbacks and nonuniform locks are preserved in the reusable backend.
Plans remain local to one call and are limited to 250,000 retained operations.

Six new differential tests cover both algorithms, weighted blocker-conditioned
worlds, every average frequency, values/BRs, custom callbacks, locks, early caps
and public API parity. The 22 focused planned/turn/configured tests passed.
The full local application/AI Coach suite passed 304 tests in 81.433 seconds
using a writable Windows test directory. Evaluation code is unchanged.

Four whole-API reports compare recursive/planned traversal under vanilla/DCFR,
using both prior fixtures at 20/100/300 iterations and three repeats. They record
measured commit `f6f46a2`, six matching module hashes and the same configuration
hash. Values/BRs/NashConv/exploitability matched within 1e-12 across all 24 rows;
counts matched exactly. Prior v1 reports remain unchanged historical measurements.

At 300 iterations, full-deck vanilla runtime fell 5.921 to 4.440 seconds (1.33x),
and DCFR fell 7.332 to 4.295 seconds (1.71x). Conditioned-subset vanilla improved
0.748 to 0.517 seconds, while DCFR worsened 0.802 to 0.877 seconds. Full-deck
vanilla was also slower with planning at 20 and 100 iterations. Shared-machine
timing does not establish a universal speedup; the default is unchanged.

Whole-call traced peaks were about 2.34/2.09 MiB (recursive/planned) for the full
fixture and 296/233 KiB for the subset at 300 iterations. Training-only scratch
peak went in the opposite direction, showing a retained plan-memory cost. Memory
scope and allocation lifetime matter; neither measurement proves a universal
memory advantage. See [traversal validation and reproducible commands](planned-traversal.md).

The broader street/range objective remains active. No AI Coach/UI/contracts code,
third-party source, dependency, repository license or visibility changed.

## Traversal temporary-state lifetime

A fresh-process weak-reference diagnostic with cyclic GC disabled found both
trainers retained a terminal callback after returning. The recursive trainer's
`traverse` closure captured itself and final strategy/delta/sum state; the planned
compiler's `visit` closure captured itself, callbacks, key indexes and its final
operation array. Clearing each recursive closure binding in `finally` after its
last use breaks those cycles on success and failure. The mathematical update
order, profiles, interfaces and independent BR evaluation are unchanged.

Before the fix, both callback weak references remained live until `gc.collect()`;
after it, both were released without cyclic collection on CPython. A known tiny
policy remains exactly `[0.05, 0.95]`. Two regression tests verify successful
training under both backends and partial-plan budget failure with GC disabled;
immediate-release checks are CPython-specific. All 88 focused mathematical tests
passed, followed by all 306 repository tests (138.585 seconds). This measures
state lifetime, not a universal runtime/peak-memory gain.
Earlier benchmark reports remain measurements of their recorded source commits.

## Shared flop, turn and river engine

The shared postflop engine now includes bounded flop, turn and river starts,
reusing the betting builder and CFR backends. It enumerates physical ordered
turn/river worlds, preserves latent future information and cumulative accounting,
and indexes legal private hands by public reveal prefix. The turn API delegates
through a compatible facade. Eight added tests cover independent three-street
policy/BR replay, nested hidden-chance adversaries, full physical flop execution,
configured river agreement, dictionary configs and backend parity. Three further
tests cover the total-public-state cap, independently counted tree states and
tree release with cyclic GC disabled. All 317 repository tests passed in
259.519 seconds, including the coaching regressions. A separate
16-case before/after check against the actual prior turn source produced zero
differences in policies, values, BRs, gaps and counts. See
[postflop validation](postflop-validation.md) for scope and reproductions.

The initial recursive vanilla report records source `3a8a78a`, before the
allocation guard and tree-closure cleanup. In its full-deck single-pair fixture,
10/30 iterations took 7.367/22.095 seconds median and NashConv fell
0.441288 to 0.147096 chips; traced peaks were about 21 MiB. In the weighted
conditional 8-world fixture, gaps fell 11.632962 to 6.817565 chips, with medians
0.251/1.152 seconds and about 530 KiB traced peaks. The latter gap remains large;
these checkpoints demonstrate measured coverage and convergence, not a high
accuracy certificate. Historical timings/memory apply to their recorded source.

An independent structural audit found that decision counts alone omit all-in
runout allocations: 8,104 decisions plus 228 chance nodes and 17,912 leaves in
the short-stack full fixture. The shared engine now reserves every public state
before expansion, bounded at 250,000; the 10,000-decision cap is also charged
before continuations. Returned counters expose both bounds. Recursive tree
builders/collectors clear their closure cycles on exit. Original algorithms,
game probabilities, contracts and zero-sum accounting are unchanged.

The current planned-vanilla report records guarded source `bac5e47` with the
same four fixtures/checkpoints. Full-deck medians at 10/30 iterations are
4.115/6.444 seconds; traced peaks are about 23.9/23.5 MiB. Conditional medians
are 0.077/0.162 seconds with about 540/539 KiB peaks. All values, exact BRs,
gaps and game counts match the historical recursive report within 1e-12.
The source revisions differ, so these reports do not establish a controlled
backend speed or memory comparison. Both retain source/config/harness hashes.

## Next implementation milestone

Before merging, the branch incorporated GitHub main `f32dc71`, including the
separate coaching and interface updates. All 323 integrated repository tests
passed in 92.403 seconds, and all eight frontend contract checks passed. The
solver diff preserves those independently developed application changes.

Profile and reduce repeated per-world traversal work while preserving the exact
chance model and oracle results. Use measured gains before selecting a compiled
backend. Expand the reusable chance architecture toward flop, preflop, positions,
larger ranges and eventually multiway games, with an independent quality measure
for each supported game. The commercial full-NLHE objective remains active;
action-tree and street coverage alone do not prove equilibrium accuracy.

## Exact public-batched candidate

An optional `public-batched` backend shares each public traversal over private
hand vectors while retaining exact physical chance enumeration and the existing
game model. Eight added regressions passed, including independent flop policy
and best-response replay, both algorithms, blocker-sensitive weighted worlds,
three street starts, asymmetric stacks, sizing, raises and all-ins. A 250,000
prefix/hand-edge cap reserves sparse aggregation entries before allocation;
recursive visitor bindings clear on success and failure. Accurate global chance
normalization fixes a reproduced Python 3.11 tie-sensitivity trigger without
altering the update rule or policy tolerance. All 331 repository
tests passed in 105.342 seconds, including coaching regressions. Recursive
remains the default/reference. Controlled whole-call reports at source `b6085fc`
compare the same 864-world conditional game at 20 iterations on Python 3.14.7.
Three interleaved calls including construction, training, exact values/BRs and
JSON serialization give vanilla medians 9.225/1.580 seconds and DCFR medians
10.965/1.668 seconds (recursive/public-batched). Traced Python peaks rise slightly,
6.47/6.66 MB and 6.50/6.70 MB. All policy/value/BR differences stay below
`5.4e-15`. These are fixture-specific efficiency gains, not universal gains.
NashConv remains 6.1505 chips vanilla and 2.8662 DCFR at these short checkpoints;
neither is a high-accuracy certificate. Both reports preserve source/config/harness
hashes; the earlier v1 report remains historical. See
[public-batched validation](public-batched-cfr.md).

## Solver handoff completion and known-game quality

The takeover of the interrupted "Advance OpenPoker solver" chat verified the
complete final heads of PRs #23, #51, #52, #53, #54, #55 and #63 as ancestors
of GitHub main `65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce`. These include
configured river betting, DCFR, turn-to-river chance, planned traversal,
prompt traversal-state release, the shared postflop engine and public batching.
Their production changes and published benchmark evidence are already merged.

The remaining local work was the independent known-Kuhn quality package,
completed here with its versioned config, oracle, tests and measured report.
All 18 checkpoints passed at source `e9d9339`; the 10,000-iteration gaps are
0.00463557 chips vanilla and 0.00165554 DCFR across all three trainers.
Four focused tests passed during takeover; the prior complete log records
335 passing tests. See [quality validation](cfr-known-quality.md) and its
linked source-frozen report for exact values, provenance and reproduction.
No solver, Coach, server, browser, persistence or shared contract source changes
are required by this quality milestone; no external dependency was introduced.

The ongoing solver goal now takes a flop/preflop detour while a separate
reviewing workstream evaluates turn and river. Preserve the merged turn/river
implementation and isolate any future shared-kernel changes behind compatible
interfaces and full regression checks. Full-deck preflop and unrestricted no-limit
Hold'em equilibrium remain unsupported; Kuhn quality is evidence about these
training kernels, not a Hold'em accuracy certificate.

## Preflop betting foundation during the flop/preflop detour

The additive `preflop_tree.py` module now constructs heads-up betting from
capped small/big blind posts. It preserves the big blind's option after a
limp, minimum full raises, finite sizing/reraise abstractions, short calls,
all-ins and refunds, and passes an explicit typed boundary to future flop
play. It shares existing action/node types, sizing and generic CFR interfaces;
no turn/river or Coach production source was changed. This is preflop game
construction; live flop and all-in runout boundaries remain unsolved until
an explicit continuation is supplied.

Luna implemented the bounded tree and rule tests, followed by lead review,
independent rational edge replay and additional regression cases. Nine focused
tests passed, including a complete synthetic root's known values and exact
best responses under recursive/planned vanilla/DCFR. The reproducible replay
also passed 162 asymmetric stack configurations (914 action edges) and nine
benchmark fixtures. At source `b786b54`, the wide four-raise/five-size fixture
has 1,412 decisions and 4,234 public states; construction took 111.12 ms median
with 1,915,856 traced peak bytes. This measures tree construction, not strategy
accuracy or full-range solve performance. See [scope, reproduction and report](preflop-betting.md).

The next integration step is to attach independently verifiable physical flop
chance and postflop betting continuations while preserving position, hidden
cards, perfect recall and cumulative contributions. Avoid treating sampled
or conditional continuation values as unrestricted preflop equilibrium.
Keep turn/river production work isolated from their separate evaluating lane.

## Bounded preflop solving with physical flop chance

The additive `preflop_solver.py` now connects the merged blind-aware betting
component to physical flop chance and existing postflop templates. Global
SB/button and BB identities, BB-first postflop action, refunds and cumulative
whole-hand contributions survive the boundary. Flop order is canonical;
turn/river order remains physical. Selected outcomes condition one joint
hand/runout distribution, with blocker-induced private-prior shifts serialized
for external review. Full-deck preflop requests fail before rank/world allocation.

Luna implemented the bounded solver; lead review added an independently
implemented physical-world/ranking/numeric-state policy replay and exact legal
best responses. The oracle shares card/range grammar only. Its hidden-flop
anchor distinguishes a legal best response worth zero from an illegal
clairvoyant response worth 0.25 chips. Weighted asymmetric four-street histories,
minimum raises, stage overrides, short-blind refunds, action legality and
recursive/planned vanilla/DCFR are checked independently.

Seventeen focused tests passed locally. GitHub's initial complete 360-test suite passed
on Python 3.11, 3.12 and 3.13, including the Coach regressions; frontend checks
also passed. Existing turn/river, shared training-kernel and Coach production
source is unchanged. No external code, dependencies or solver outputs were
imported. See [model limits, provenance and reproduction](preflop-solver.md).

Source-frozen convergence checks at `7b5694f` compare recursive and planned
vanilla/DCFR at 100 and 1,000 iterations. At 1,000, NashConv is
0.00025/7.48876e-10 chips for the hidden-flop anchor,
0.0147832/5.99550e-7 for the live four-street fixture, and
0.00970026/7.55582e-7 for the weighted asymmetric fixture (vanilla/DCFR).
Each checkpoint's values and both legal BRs must agree with independent replay
within 1e-10, private-pair probabilities within 1e-12, and both traversals must
agree within 1e-10. All final gaps must be below 0.02 chips vanilla and
0.001 DCFR and improve from 100 iterations. Complete-call timing and separate
Python allocation measurements are in the linked versioned report; they do
not establish full-deck performance or a process-memory ceiling.

The next priority is measured flop/preflop efficiency and broader independent
chance/information-set validation within explicit resource limits. The selected
games establish complete-hand calculation in a finite abstraction; they are
not unconditional full-deck or unrestricted NLHE equilibrium certificates.

## Complete fixed-flop future deck and known Hold'em game value

The next independently validated fixture enumerates all 1,980 legal ordered
turn/river outcomes after `2c3c4d` with exact SB `AsAd` and BB `KsKd`.
Its preflop game is conditioned on that particular flop; future cards remain
hidden until revealed. At two-chip stacks/no preflop raises, the finite tree
has 8,106 decisions/information sets and 26,248 public states. A constructive
SB complete-then-shove/call policy and BB check/fold policy prove exact game
value +1/-1. Independently enumerated wins/losses/ties give a called-flop-shove
SB expectation of 272/165, while BB never adding chips caps SB at +1.

Luna's full-world regression and the independent constructive-profile replay
passed. At frozen source `b77a08f`, planned DCFR's learned NashConv drops from
0.185208 at 10 iterations to 0.008309 at 30; known-value error at 30 is 0.007162.
Both checkpoint values and exact legal BRs agree with independent replay to
2.23e-16. The reference profile has zero legal deviation gap. Three complete
timed calls give medians 5.896/9.562 seconds; a separate call at 10 iterations
uses 26,226,183 traced peak Python bytes. This is complete future-deck coverage
for one fixed flop/private pair, not all flops or full private ranges.
See [proof, reproduction and recorded limits](fixed-flop-complete-chance.md).
No production solver, shared kernel or Coach source changes are required.

## Bounded deeper complete fixed-flop convergence

Optional preflop `resource_model="public-vector"` uses an independent structural
vector-work census with prefix, dense-slot, information-set action and modeled
loop caps before vector view/training allocation. It requires public-vector
training and diagnostics; default admission and every other existing cap remain.
It admits DCFR350 and CFR+120 on the complete four-private-pair fixed-flop game,
which the conservative world-decision guard rejects. Shared kernels, postflop,
turn/river and Coach source remain unchanged.

At frozen `b8fe302`, independent replay checks all 17,620 policy rows, all 7,920
worlds, private-pair probabilities and both legal best responses. DCFR100/350
NashConv is 0.0254528/0.00790802 chips; CFR+120 reaches 0.00247911. Maximum scalar
disagreement is 1.67e-14. Every endpoint misses the predefined 0.001-chip target.
One observed complete call per checkpoint takes 78.348/283.792/135.961 seconds,
including estimator-only allocation tracing. Its approximately 2.02 MB traced
peak covers only resource preflight, not the complete solve or RSS. See
[scope, modeled ceilings, value intervals and provenance](preflop-vector-resources.md).

## Delayed preflop CFR+ meets the fixed-flop accuracy target

An isolated preflop adapter exposes published `max(t-delay,0)` CFR+ averaging
weights, retaining the existing completed-alternating-sweep own-reach convention.
Default delay zero and all resource ceilings remain unchanged. Recursive
requests reuse the existing generic delay implementation; a preflop-local
vector average pass reuses unchanged repository regret/aggregation helpers.
Shared CFR, postflop, turn/river, diagnostics and Coach source remain unchanged.

At frozen `1240dd0`, complete four-private-pair fixed-flop CFR+120 with delays
0/20/60 has NashConv 0.00247911/0.00137144/0.00118598 chips; every target misses.
An explicitly evidence-guided extension freezes 160 iterations with delays 0/80
at `2075cc6`. Independent replay verifies all 17,620 rows, all 7,920 worlds,
private-pair probabilities and both legal best responses. Delay zero has gap
0.00156941; delay 80 has **0.000798538**, meeting the unchanged 0.001 target under
the unchanged 490,881,772-entry workload estimate. Maximum scalar disagreement
is 1.58e-14. The padded SB game-value interval is [0.5182045061, 0.5190030442].

The observed uninstrumented full calls at 160 take 118.833/109.401 seconds,
including serialization; single shared-host samples establish no speedup.
Separate 20-iteration selected-game traced peaks are approximately 721/714 KB,
not full-fixed-flop memory or RSS evidence. Thirteen new tests include generic
parity, independent replay, known Kuhn/exhaustive legal BR accuracy and prompt
lifetime cleanup. Longer delays worsen the Kuhn gap, so the method stays opt-in.
See [measured scope, source hashes and provenance](preflop-averaging-delay.md).

## Complete fixed-flop chance with private-hand uncertainty

The full-chance regression now also covers two SB combinations and two BB
combinations (`AsAd,QsQd` versus `KsKd,JhJc`) with equal prior weights. After
`2c3c4d`, 2,352 requested public turn/river pairs yield 2,336 reachable public
outcomes and 7,920 compatible private-pair/future worlds. All four private-pair
probabilities and all learned information sets, values and exact legal best
responses are checked independently. This adds hidden opponent-hand uncertainty
to the earlier single-pair full-chance fixture, without invoking its +1/-1
known-value claim for a different game.

Luna's saved bounded test was recovered after its usage limit stopped the
agent. Lead review ran the focused test successfully and incorporated the
parallel turn/river publication on main before final validation. Requests
exceeding the world-iteration limit are checked to fail before ranking. This
10-iteration planned-vanilla check establishes exact policy replay and chance
coverage; it does not establish high-accuracy equilibrium convergence or new
runtime/memory performance. See the [expanded fixture scope](fixed-flop-complete-chance.md).

## Indexed preflop blocker filtering

A bounded per-card selected-runout index replaces both dense Python private-pair
blocker scans while preserving canonical outcome/world order and exact weights.
Candidate, selected-outcome, world-iteration and 30-million logical preflight
admission caps remain unchanged. No shared CFR, postflop, turn/river, public
diagnostic or AI Coach production source changes are required.

At frozen `2eb9f62`, three alternating paired calls preserve exact serialized
results for all 7,920 fixed-flop worlds and a weighted complete solve. The
all-blocked 300-pair/100,000-outcome fixture charges exactly 30 million admission
checks and rejects before ranking on both paths; median preflight time falls
from 21.061 to 3.090 seconds. This is setup scalability, not larger solved-game
coverage. Full fixed-flop enumeration medians are 0.436/0.372 seconds. The small
complete-solve raw timings overlap, so no general solver speedup is claimed.

The separate index-construction trace peaks at 13,923,944 Python bytes for
100,000 already-canonical outcomes, including helper validation/posting scratch;
this is not whole-solve memory or RSS. Eleven new helper/integration tests include
randomized brute-force comparison, exact world/policy parity, independent legal
BR replay and guard ordering. See [scope, provenance and reproduction](preflop-runout-index.md).

## Experimental preflop chance-sampled training with exact diagnostics

An opt-in isolated vanilla CFR trainer samples the conditioned joint physical
world law with exact-integer CDF support, frozen minibatches and own-reach
averaging. It retains full-game exact values and legal best responses. New
sampled node/action and sampler-entry/bit bounds explicitly replace full-world
iterative charges; construction/tree and exact-diagnostic guards remain.
Shared CFR, postflop, turn/river and Coach source are unchanged.

At frozen `b9ea214`, all three full-fixed-flop seeds improve from gaps
0.224-0.242 at 1,000 iterations to 0.0370-0.0387 at 10,000 with batch 32.
Every 0.001-chip target misses. Weighted selected-flop gaps 0.0115-0.0134
also miss their 0.01 target. Independent replay verifies every policy row,
posterior, value and legal BR with maximum scalar disagreement 2.13e-14.
The 10,000-iteration complete calls take 152-156 seconds; no controlled
speedup claim follows. A separate 100-iteration full-call trace peaks at
42,325,089 Python bytes, excluding process RSS and preallocated caller inputs.

Luna implemented/reviewed bounded core and storage slices; 28 new tests cover
exact weighted update expectations, hidden information, sampler support,
known-game legal BRs and admission/cleanup. This path remains experimental;
previous delayed exact CFR+ remains the strongest fixed-flop accuracy result.
See [method, all seeds, resource scope and provenance](preflop-chance-sampled.md).

## Exact full-board restricted preflop shove/fold

A separate SB fold/shove, BB fold/call API now prepares reusable full-board
equities for up to four compatible private pairs, under explicit pre-enumeration
rank/pair and full-requested training bounds. Existing selected-outcome preflop,
shared turn/river and Coach implementations are unchanged.

At frozen source `4650d65`, three weighted pairs covered 5,136,912 unordered
final boards. Independent best-five enumeration matched every integer W/T/L
count. Exact-fraction visible-information policy replay checked 27 checkpoints
and a rational mixed-equilibrium anchor, with maximum scalar disagreement
2.492e-16 chips. All fixed final accuracy gates passed: 3,000-iteration
exploitability was 0.002060 vanilla, 0.0007777 DCFR and 0.00003019 CFR+, and
CFR+ known-value error was 1.405e-8 chips. Both asymmetric stack directions
passed refund checks at the same effective stack.

One-time full preparation took 488.161 seconds on Python 3.12.14 / i7-7500U;
a separate complete prepared-call trace peaked at 19,437 Python bytes and
excludes equity preparation/RSS. No universal speed or full-call memory claim
follows. All 773 local regressions passed; bounded Luna reviews and the final
GitHub checks accompany the PR. See [scope, all results, provenance and limits](preflop-push-fold.md).

## Reuse full-board preflop counts under changed ranges

`reweight_preflop_equities` preserves immutable hand-pair W/T/L counts while
rebuilding exact globally conditioned priors and categorical masses. Covered
subsets, reordered hands and newly listed fully blocked hands are accepted;
uncovered compatible pairs are rejected. Existing solver and resource limits
remain in place.

At frozen `55cdb2a`, six 3,000-iteration CFR+ cases passed independent exact
small-game equilibrium and own-hand best-response replay. Changed ranges reach
distinct mixed/pure regimes; maximum production/replay scalar disagreement is
1.111e-16 chips. All final exploitability/known-value errors pass the declared
0.005-chip gates. Three complete warm-call medians range from 0.332 to 0.908
seconds, with ranking/enumeration disabled. A separate call trace peaks at
22,621 Python bytes excluding the source table, original preparation and RSS.
The original physical counts remain pinned to five verified PR #125 Git blobs;
this run adds no physical pair coverage or cold-call speed comparison.
See [API, all cases, provenance and measured limits](preflop-equity-reweight.md).

## Exact preflop suit-orbit transfers

A separate opt-in API reuses trusted ordered-pair W/T/L counts through one
global suit permutation. It preserves role and relative-suit relationships,
rejects uncovered or inconsistent source orbits, and reports every source,
target and suit map. Literal reweighting, default preparation and all caps stay
unchanged.

At frozen `695dd35`, 24 complete suit images and a four-pair/three-BB-hand
split game preserve the original rational equilibrium value. All 25 trained
2,000-iteration cases pass both 0.005-chip accuracy gates; exploitability is
1.464e-5 and known-value error is 4.202e-9 chips. Independent checks cover
76 pair transfers, exact matrix witnesses and serialized own-hand best responses,
with maximum scalar disagreement 1.324e-16 chips. A separate toy oracle checks
19,008 mapped boards; this is not new physical full-deck enumeration.

Complete warm-call medians are 0.653â€“1.105 seconds across the suit images and
1.215 seconds for the split game. A separate split-call trace peaks at 32,758
Python bytes excluding the source table, original preparation and RSS.
The four-pair request fits at 2,000 iterations, charges 493,147,312 modeled
entries and remains rejected at 3,000 under the original 500-million guard.
See [API, mathematical scope, sources and evidence](preflop-suit-remap.md).

## Explicit prepared-count preflop admission

Prepared shove/fold callers may opt into a versioned compact-table work model.
It replaces historical full-board preparation charges with bounded current
validation/setup, while retaining full requested training/diagnostic charges,
all structural caps and the 500-million limit. The default full payload matches
the merged golden result exactly; full solves still pre-admit source work before
enumeration.

At frozen `e8e70bc`, 18 independent checkpoints verify three algorithms through
10,000 iterations on the four-pair split-AK game. All final 0.005-chip gates pass;
CFR+ also passes 0.00005, with exploitability 6.882e-6 and value error 9.375e-10.
Intermediate increases remain recorded. Maximum production/replay scalar
disagreement is 2.512e-16 chips. Legacy 3,000+ requests still reject; each prepared
10,000 request charges 273,936,960 modeled entries.

Three-repeat final complete-call medians are 1.866/2.410/4.060 seconds for
vanilla/DCFR/CFR+. A separate complete 10,000-iteration CFR+ trace peaks at
24,251 Python bytes excluding the source table, original preparation and RSS.
This permits longer warm experiments and does not accelerate the kernels or
expand the betting model. All 823 local tests pass; see [scope, census and every checkpoint](preflop-prepared-budget.md).

## Broader weighted fixed-flop range and raise coverage

At frozen `2c6c858`, the existing direct-flop solver passed independently
enumerated hidden-board policy and legal best-response replay for eight weighted
hands per player: 58 compatible pairs and 114,840 ordered future worlds. Both
one-raise and two-raise flop trees meet the 0.005-chip NashConv gate at 4,000
CFR+ iterations, with measured gaps 0.0000143935 and 0.000104911 chips. Both
100-iteration points miss and remain recorded. The deeper tree exposes both a
non-all-in bet/raise/re-raise and a check/bet/check-raise/re-raise line.

Complete-call medians including ranking and JSON are 12.855 and 17.885 seconds;
separate full 4,000-iteration Python allocation traces peak at 294,858 and 418,715
bytes, not RSS. This slice adds fixture, benchmark and regression evidence;
production solver source and API remain unchanged. Future cards are integrated
exactly but forced to check down; later-street betting and full ranges remain
outside this result. See [all checkpoints, provenance and limits](flop-weighted-eight-hand.md).

## Reuse exact fixed-flop counts across weighted betting games

An immutable `FlopCheckdownEquities` table now separates bounded full-future
equity preparation from repeated flop solves. Covered-pair reweighting preserves
the fixed board, source counts, global collision conditioning and all existing
caps. The separate prepared entry point retains source-inclusive admission and
adds explicit zero-current-ranking metadata; the ordinary solver payload and
shared kernels are unchanged. Structural validation is not count authentication.

Frozen `9af1e75` passes all four predetermined fresh/prepared games, including
eight weighted hands each, two flop raises, reversed weights and a four-hand
subset. All 24 timed profiles have exact numerical-payload parity and pass
independent full-physical-chance/visible-information BR replay. Cold preparation
took 5.002 seconds; warm complete-call medians are 14.8%-32.4% below fresh calls
in this matrix. A full 4,000-iteration warm trace peaks at 418,997 Python bytes,
excluding cached inputs and RSS; its interrupted elapsed time remains recorded.
All 843 tests pass in frozen-source CI on Python 3.11/3.12/3.13. See
[API, every measurement and provenance](flop-equity-reuse.md).

## Transfer prepared fixed-flop counts through joint suit symmetry

A separate opt-in API transfers trusted integer counts when one global suit
bijection maps the flop and both role-ordered private hands together. It rejects
uncovered and inconsistent orbits, preserves exact target weighting and all
admission limits, and returns deterministic mapping provenance.

At frozen `e6af9e4`, all 81 profiles across 24 single-pair images, two eight-hand
whole-game images and a mixed two-pair target pass independent physical-board
and own-hand best-response replay. Both whole-game images reproduce the exact
published source payload after inverse label mapping. Maximum NashConv is
0.000104911 chips; warm calls perform no ranking or future-board enumeration.
A complete 4,000-iteration trace peaks at 523,805 Python bytes, excluding cached
inputs and RSS. Every timing observation is retained, including a 493.742-second
single-pair outlier; no comparative speedup is claimed. All 854 frozen-source CI
tests pass on Python 3.11/3.12/3.13. See [scope, measurements and raw evidence](flop-suit-equity.md).

## Explicit native full-board preflop preparation

The ordinary Python builder remains the reference/default. A separate locally
compiled, project-owned C helper now prepares the same immutable W/T/L table
under unchanged exact-prior and resource rules, with explicit source/compiler/
binary provenance and no silent fallback or third-party evaluator dependency.

Frozen `ee87737` passes all fifteen complete-call profiles against pinned
independent physical counts, exact full solver-payload parity and own-hand
best-response replay. Maximum exploitability is 0.0000146361 chips. For the
three-pair, 2,000-CFR+ fixture, median complete time is 1.57198 seconds native
versus 483.02199 seconds Python, a scoped observed 307.27Ã— ratio. Every raw sample
is retained, including a third Python call interrupted by recorded system sleep.
All 2,598,960 five-card rank tuples independently agree; six/seven-card exhaustion
is not claimed. A complete-call trace measures 347,984 Python bytes and excludes
native-process memory and RSS. See [build, full evidence and limits](native-preflop-equity.md).

## Full-board finite preflop betting with forced checkdown

A separate prepared-table adapter adds SB limps, the BB option, configured
raises/reraises, short all-ins and matched-wager refunds to full-board
preflop chance. All future cards remain hidden; closed betting lines force
checkdown and introduce no postflop decisions. Shared kernels and the existing
selected-outcome APIs are unchanged. Complete requested work is forecast and
admitted before tree construction, with explicit prepared-counts admission.
See [API, independent replay, convergence and measured status](preflop-full-checkdown.md).

The frozen four-case benchmark passes all final 3,000-CFR+ gates, with maximum
independent NashConv 0.0000921334 chips and scalar replay discrepancy below
4e-16. The early four-pair 100-sweep miss is retained. Three-repeat complete
prepared-call medians range from 1.84806 to 7.48936 seconds; a separate full
three-pair trace measures 53,615 Python bytes, excluding input tables/oracle/RSS.
These measurements add game coverage, with no claimed backend speedup.

## Opt-in preflop pair-mean worlds

Full-board preflop forced-checkdown can explicitly integrate each private pair's
hidden W/T/L categories into its signed conditional mean, while retaining all
separate hidden opponent-hand pairs and the default categorical path. The opt-in
budget charges P training/diagnostic worlds with original category validation,
extra collapse setup, unchanged source charges and all existing caps. See
[mathematical proof and paired measurement status](preflop-pair-mean.md).

The paired 96-call report observes median categorical/mean ratios of 2.0123 to
3.1017 on one host, with scalar mode discrepancies below 1.706e-13. Mean mode's
Python trace peak is 2,080 bytes higher. All CFR+ quality gates pass, while four
vanilla/DCFR 3,000-sweep profiles miss in both modes and remain explicitly
recorded. A separate predeclared 8,000-sweep follow-up passes all eight
quality calls, with maximum independent NashConv 0.00464177 and unchanged
original report/caps. See the dedicated record rather than treating speed as
equilibrium accuracy.

## Blocker-correlated river witness

A separate development fixture has independently proved exact value
-43339/1751 and zero exact NashConv with blocker-correlated private hands.
Six fixed-budget CFR+ policies retain full independent float/exact replay
and all target misses. Production and earlier-street paths are unchanged.
See [model, proof and executed evidence](river-blocker-equilibrium.md).

## Exact selected-river turn witness

A separate development-only two-street witness proves value 50 and zero exact
NashConv in a four-world conditioned game, with independent payoff/flow and
legal-response reconstruction. Literal negative controls detect future-card
peeking and cumulative-wager mistakes. The equilibrium folds on the turn;
river policies remain fully certified off-path. See [scope and evidence](turn-sequence-equilibrium.md).

## Weighted turn witness with on-path river play

A separate four-world conditioned game has two independently validated exact
policies at value 30 and zero NashConv, with river decisions reached with
probability 1. A hand-written policy was certified before the LP candidate;
the separate verifier checks all payoff/flow data and both legal responses.
See [fixed game, proof, reach and limits](turn-weighted-sequence-equilibrium.md).

## Production turn CFR+ against the value-30 anchor

Six complete production policies now have independent numeric and exact
normalized own-hand response checks against the proved weighted turn value.
Both backends miss 0.001-chip NashConv at 1,000/3,000 iterations and meet it
at 10,000 (about 0.000681). Every miss and full policy remains saved.
See [experiment, independent reconstruction and scope](turn-weighted-cfrplus.md).

## Compact blocker-conditioned turn witness

A separate six-world turn game with private blockers has exact value 115/7
and zero NashConv, certified through original full primal/dual equations and
independent legal responses. Fixing empty realization coordinates removes two
LP columns while preserving all existing resource caps; the rejected legacy
258-column admission and hidden-information controls remain recorded.
See [model, affine reduction, proof and limits](turn-blocker-sequence-equilibrium.md).

## Production turn CFR+ with private blockers

Six complete policies for the six-world blocker-conditioned turn game have
independent numeric and exact normalized own-hand response checks against
the proved 115/7 value. Both backends miss 0.001-chip NashConv at 1,000/3,000
iterations and meet it at 10,000 (about 0.000414). All four misses and full
policies remain saved. See [experiment, proof and limits](turn-blocker-cfrplus.md).

## Global suit symmetry of blocker-conditioned turn policies

Independent reconstruction preserves the exact 115/7 equilibrium through all
24 global suit bijections and replays 144 archived policy transports. Eight
fresh 1,000-iteration production calls pass the fixed 1e-9-chip symmetry gate;
all eight still miss the unchanged 0.001-chip NashConv target. Full policies
and misses remain saved. See [experiment and scope](turn-suit-equivariance.md).

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
See [reference, completed experiment and limits](full-deck-raised-turn.md).
A separate [checked chance-quotient audit](full-deck-raised-exact.md) certifies
all six explicitly normalized policies without changing the generic exact cap.
All six exact gaps still miss 1/1000 chips; this is fixed-policy evidence for
that full-deck game, not an equilibrium or arbitrary-policy certificate.

A separate [same-run averaging experiment](full-deck-raised-turn-tail.md)
completed one 1,500-sweep call per backend and reconstructed original-weight
tails over sweeps 1,001â€“1,500. Both tails meet the numeric 0.001-chip target;
all four prefix/full averages still miss and remain saved. Complete physical
replay and separate serialized-flow reconstruction passed. Numeric zero is
not an exact-equilibrium certificate, and the full training cost remains charged.
The [separate exact tail audit](full-deck-raised-turn-tail-exact.md) now accepts
all six normalized policies: both tails meet exact 1/1000 with small positive
gaps (about 2.290e-19 and 4.368e-19), while all four prefix/full profiles miss.
Every exact gap remains positive; no exact-zero witness follows for these tails.

## Derived full-deck raised turn equilibrium witnesses

Two separately saved [cleanup candidates](full-deck-raised-turn-clean-witness.md)
now have exact normalized-policy NashConv zero and value OOP -400/21 in that
same fixed 176-world finite raised game. Each retains all 2,404 policy rows and
passes complete physical replay plus the unchanged checked chance-class audit.
The declared cleanup changes no action probability by more than 6.364e-20;
it is not a general rounding guarantee or a production/default change.
Both original tail policies and their positive exact gaps remain immutable.

## Independent full-physical exact raised-turn replay

A separate [physical exact oracle and immutable report](full-physical-audit-wrapper.md)
replay both original numeric tails and both clean witnesses with all 48 river
cards separate. Its own Fraction normalization, showdown ranking, terminal
arithmetic and legal own-hand responses agree on every exact metric with the
preceding chance-class audit. Both witnesses retain zero NashConv and OOP value
`-400/21`; the original tails retain positive gaps. The handwritten check/call
anchor, illegal future-aware responses and a legal single-card policy deviation
provide distinct arithmetic, information and physical-chance controls. This is
fixed-game research evidence; production defaults and earlier streets are unchanged.

## Value-only false-positive control

A [deterministic negative control](raised-turn-argmax-control.md) now preserves the
proved -400/21 profile value while having exact NashConv 325/33. It comes from
choosing each clean witness row's most likely action with a fixed tie-break.
A single legal KhKs root bet gains 200/21; direct physical terminal sums and
independent numeric replay confirm the deviation. This guards the distinction
between matching a known game value and having no profitable unilateral response.

## Optional direct original-weight turn tail API

A separate [turn tail adapter](direct-turn-tail.md) directly accumulates completed
CFR+ sweeps after an explicit discard point using the original iteration weights.
It preserves old APIs and all full-request guards, adds bounded dense admission,
and keeps all state local. Eleven focused tests cover exact zero-discard parity,
independent positive-tail flows and legal responses, blockers, work limits and
Kuhn quality. Fixed full-deck 1500-sweep quality evidence is a separate experiment.

The [fixed direct-tail experiment](direct-turn-tail-experiment.md) freezes a
single full-deck T=1500,D=1000 call and saves the raw profile with independent
numeric, full-physical exact and checked chance-class audits. Quality outcomes
are recorded separately from validity. The raw trained policy now has exact
NashConv zero and OOP value -400/21 in this fixed 176-world game, with no
probability cleanup. Both independent exact auditors agree on all eight metrics;
older policies retain their original bytes and results.

## Optional direct original-weight river tail API

The separate [river tail adapter](direct-river-tail.md) exposes the same local
direct accumulator for complete five-card boards, with full requested work
admission and fresh legal-response diagnostics. Nine tests cover literal
zero-discard parity, independent tail flows and all eight metrics, dead-hand
indices, an actual dense-limit boundary, finite diagnostics and concurrency.
The exact one-bet response interval contains the known value 25, while the
T=1000,D=500 tail still misses 0.001 and has a larger gap than its full average.
Direct accumulation therefore carries no general convergence-improvement claim.

The separate [fixed river experiment](direct-river-tail-experiment.md) freezes
two T=10000,D=3000 calls, independent numeric/exact audits and comparison with
the preceding saved realization tails. The actual raw polarized profile misses
0.001 at exact NashConv about 0.0068727141; weighted raises meets it at about
0.0002232345. Both positive gaps and raw policies are retained. Independent
exact audits contain the known game values, and own-action flows agree with
the old tails within 1e-11. Direct accumulation shows no quality advantage here.

## Longer explicit direct river budgets

The [river-only admission extension](direct-river-long-tail.md) permits up to
100,000 requested sweeps under all original candidate/world, tree, prefix,
slot and full-request work guards. Requests through 10,000 retain literal
v1 output; longer requests use a separate version. Three complete payloads
match the frozen pre-change API byte-for-byte on the same interpreter, a genuine
10,001-sweep profile passes independent numeric/exact
response replay, and the real weighted 100k request rejects before training.
The turn API retains its 10,000 ceiling. A 100k direct-tail quality experiment
remains separate and has not run in this source slice.

The [fixed longer river experiment](direct-river-long-tail-experiment.md) defines
one actual T=100000,D=3000 call with no cleanup, unchanged exact 0.001 target,
strict generic/16x4 exact agreement and reconstruction of the preceding 10k
policy. The actual raw profile meets 0.001 at exact NashConv about
0.0008944742; OOP/IP response gains are about 0.0005500202/0.0003444540.
All eight metrics agree across independent exact audits, and the known value
25 lies inside the legal response interval. The 10k miss is preserved; the
positive 100k gap does not certify exact equilibrium or general convergence.

## Mixed physical AA/QQ-versus-KK validation

A frozen 72-pair trainer comparison combines both independently checked physical
count bases, preserves weighted own-hand uncertainty and legal reraises, and
requires independent exact replay plus final NashConv at most 0.005 chips.
Constructive value bounds are [1/2,1], not an exact equilibrium value.
See [method, evidence and publication status](preflop-mixed-physical-range.md).

## Exact mixed physical preflop witness

A bounded rank-type candidate is lifted onto every physical own hand, then
checked against fourteen independently written terminal paths and 792 legal
own-hand pure responses across all 72 AA/QQ-versus-KK pairs. Candidate LP output
is separate from the physical certificate. See
[method, evidence and publication status](preflop-mixed-exact-witness.md).

## Explicit native cold fixed-flop preparation

A separate source-built count producer fills the existing immutable fixed-flop
table under unchanged preparation caps. The frozen comparison isolates cold
Python versus native preparation while retaining the same native trainer,
independent physical counts and complete legal best-response checks. See
[method, evidence and publication status](native-flop-preparation.md).


The single-call `solve_native_flop_checkdown` entry point now composes both
explicit helpers through the same source-inclusive admission path. All tree,
slot, native-envelope and combined requested-work guards run before executable
lookup or count preparation. Its cold-count provenance is separate from native
training metadata; the existing Python and prepared-count APIs retain their
payloads and defaults. See [usage and guard order](native-flop-preparation.md).


## Native CFR+ policy refresh experiment

The public native trainer now has a bounded candidate that refreshes only the
updated player's CFR+ policy rows, retaining first-sweep initialization and all
original admission charges. The separately frozen experiment passes all 28
policy replays and exact old/new wire checks; complete-call median observed
ratios are 1.44 / 1.30 on the two weighted eight-by-eight games.
See [method and publication evidence](native-cfrplus-rematch.md).


## Weighted full-deck flop validation experiment

An independent literal-world/numeric-action validator now checks flop-start
policies with real later-street decisions, including weighted blockers and
hidden-future legal responses. A frozen 5,940-world recursive/planned vanilla/DCFR
experiment completed 36 timed calls and two separate allocation calls under all
unchanged caps. All 38 policies pass independent physical/action/legal-response
reconstruction and exact repeated/cross-backend agreement. Both 400-sweep algorithms
missed the original 0.005-chip target (vanilla 0.155975, DCFR 0.036804); every miss
and the interrupted timing outlier is retained. These timings support no controlled
speed claim. See [method and immutable evidence](weighted-full-deck-flop.md).


## Full-future flop CFR+ adapter candidate

The flop start can now select the existing recursive/public-batched CFR+
trainers under the unchanged full-request three-pass bound. Independent
full-deck and raised conditioned validation plus legacy payload comparisons
are required; convergence evidence remains separate from the adapter change.
See [scope and validation plan](flop-cfrplus.md).


## Opt-in delayed averaging for flop CFR+

A bounded candidate reuses existing delayed trainers for positive flop-start
averaging delays, preserving all regret sweeps and the full three-pass admission.
Zero delay keeps the established payload and dispatch. Independent replay,
hand-computed averaging controls and original-source default comparisons are
required; conditional differences at zero/tiny reach remain explicit. No new
convergence result is claimed. See [scope and evidence](flop-delayed-averaging.md).

The full-future flop CFR+ experiment is complete: all 20 candidate policies and
38 baseline policies reconstruct independently; both CFR+140 final NashConv
observations (~0.012538) still miss the original 0.005-chip gate. Raw repeats,
separate allocation calls and exact source identities remain immutable. See
[completed evidence](flop-cfrplus.md#completed-evidence-and-quality-misses).


## Flop-start public diagnostics independently checked

Final profile value and both own-hand legal best responses can use the existing
public-vector evaluator across both future-card reveals. Independent physical/
numeric-action replay passes on 5,940-world and weighted raised games; a separate
two-reveal pure-response oracle checks legal information and zero-marginal rows.
All 22 focused compatibility tests pass, including exact diagnostic-only policy
parity, prefix-cap boundaries and historical defaults. Flop target stopping
remains unsupported. See [validation and limits](flop-public-diagnostics.md).

## Independent three-hand TURN audit preparation

The [fixed three-hand physical audit](turn-three-hand-physical-audit.md) rebuilds
the weighted 3-by-3 game over 396 original physical worlds and all 48 river
cards. Its separate exact engine checks complete legal policies and aggregates
hidden opponent hands before each visible-information response. Closed-form
check/call anchors and a single-card deviation provide independent controls.
The old physical proof and generic exact limits remain unchanged; this slice
adds validation coverage without a trained-policy or equilibrium-quality claim.

The [three-hand direct-tail experiment](turn-three-hand-direct-tail-experiment.md)
predeclares one T=750, discard=250 call, original averaging weight 250250,
unchanged exact 0.001-chip target and separate valid-miss acceptance. Its
source-frozen runner independently reconstructs the complete raw-policy report
and preserves any rejected return; actual results follow the recorded call.
The sole actual call is now saved: exact NashConv about 0.01069549 misses
0.001, with OOP/IP gains about 0.01057780/0.00011769. Independent numeric and
exact physical replay pass; the raw positive-gap policy and miss are immutable.

The [seven-class equivalence audit](turn-three-hand-classes.md) retains all
396 physical worlds through exact aggregation into 45 private-pair/class
worlds. Complete subtree and policy-lift checks preserve hidden-information
boundaries and compare all eight compact and full-physical exact metrics.
Class-specific probabilities remain allowed; card-specific differences within
a class reject projection. No training or earlier-street/production change is
included, and the saved T750 miss is preserved.


## Alternating flop regret variants independently checked

Two explicit public-batched flop options add LCFR and alternating DCFR(3/2,0,2)
without changing existing simultaneous DCFR or CFR+ kernels. Both retain unfloored
regrets and pre-sweep own-reach averages, with full three-pass request admission.
All 47 focused compatibility tests pass, including abstract mathematical controls,
independent 5,940-world/weighted raised-game replay and exact archived-adapter
legacy payload parity. The frozen convergence experiment is now complete with
all three original target misses preserved, as recorded below. See
[algorithm equations, scope and validation](flop-alternating-cfr.md).
## Delayed flop averaging completes with six retained target misses

The fixed 140-sweep study now retains all 18 timed and two separate allocation
policies. Independent physical/numeric-action/own-hand response replay passes
for every candidate and both pinned baselines. All six final 0.005-chip gates
miss: delay zero reaches about 0.012538 NashConv, delay 70 about 0.015052, and
delay 100 about 0.026546 in both trainers. Positive delays do not improve this
fixed game. Exact repeats, complete-call observations, all raw probabilities,
source identity and the initial startup failure remain preserved. See
[completed evidence and reconstruction](flop-delayed-study.md#completed-corrected-study).

## Frozen comparison for alternating flop trainers

The preregistered study fixed CFR+, LCFR and alternating DCFR to the same
weighted 5,940-world game, 140 sweeps and full three-pass admission. It retained
nine rotating complete calls, three separate allocation traces and independent
physical/legal replay. Each method kept its own original 0.005-chip gate. See the
[protocol and completed evidence](flop-alternating-study.md).

## Alternating flop study completes with three retained target misses

All three original gates miss: independent NashConv is 0.012537880082180 for
CFR+, 0.090593278528127 for LCFR and 0.011508822247107 for alternating DCFR.
Within-method repeats are exact, and CFR+ matches its original 140-sweep payload.
All 12 candidate policies and both pinned historical baselines reconstruct
without training. The 15-file corpus preserves every row, action and positive
gap, with external raw-byte pins for the index, 626-file Git source attestation
and separate transient non-input scratch-incident receipt. Observed timings
retain the documented incidental-I/O qualification; they support no controlled
or general speed claim. The strict publication suite passed all five tests in
320.956 seconds, including full saved replay and tamper rejection. See
[results, source identity and reconstruction](flop-alternating-study.md#completed-frozen-measurement).
A no-training exact public-chance equivalence audit is the next bounded step;
compact training requires a separate full-tree and physical-response proof.

## Full-future flop public-chance equivalence checked without training

A [fixed-game audit](flop-public-classes.md) preserves the full weighted joint
physical law while grouping 5,940 worlds into 126 class worlds. Both reveal
layers retain posterior/signature multiplicities and every numeric betting
subtree. Four class-constant synthetic policies lift without probability
changes to every physical row; all eight exact metrics equal unrestricted
physical responses, and the separate numeric oracle agrees within 8.89e-16.
The complete compact policies, physical digests, source identity and initial
interruption receipt remain saved. Card-specific or near-normalized policies
reject; this adds no training, convergence result or general abstraction.
The three original alternating-study target misses remain preserved.


## Explicit fixed-game compact TURN tail adapter

A separate research entry point trains the proved three-hand turn game on seven
exact river classes, then lifts every physical row for fresh full-deck diagnostics.
Its explicit resource model reserves full requested training, fixed preparation,
logical storage and output costs before dispatch; ordinary APIs and caps remain
unchanged. Exact first-sweep controls and bounded physical/class replay are
separate from any longer-budget quality claim. See [API, proof and admission](turn-class-tail.md).


## Three positive-prior fixed-flop research games (2026-10-22)

The [separate range-prior adapter](flop-class-reweight-cfrplus.md) trained the
proved baseline/uniform/skew distributions at 560 zero-delay CFR+ sweeps. All
three normalized policies passed exact unrestricted physical response checks
and the 0.005 NashConv gate (0.0028924 / 0.00001296 / 0.0009931), followed by
three independent saved-policy replays without training. Raw policies, exact
metrics, source manifests and full immutable reports/replay receipts are retained.
This preserves fixed card/action support, existing shared sources and production
defaults. It establishes no general convergence rate, speed, memory or
unrestricted NLHE claim. Publication status is tracked in
[PR #207](https://github.com/ajpaulson18-design/openpoker-lab/pull/207).

## Positive-prior baseline call observation (2026-10-22)

The [separate frozen diagnostic](flop-class-reweight-baseline-diagnostic.md)
completed one phase call and one allocation call, both reproducing the complete
previously replayed baseline bytes. It retains 13 completed nested events,
exactly two training invocations, clean 35-source identities and a Python traced
peak of 401,901,644 bytes. The allocation call's large wall/CPU separation remains
recorded. This single warm-process observation establishes no runtime comparison,
RSS or stable memory advantage. Repeated full validation motivates a scoped
integrity investigation; no solver, proof, production or Coach default changed.

## Fresh second-board flop reference (2026-10-22)

The [separate no-training reference](flop-second-board-reference.md) independently
prepared the fixed `7c8d9h` finite game, retaining all 5,940 weighted worlds and
30,812 numeric public states with fresh hashes. Its explicit-board candidate
partition measured 13 turn classes, 17 river signatures and 170 aggregate worlds.
The same-ranker fresh-cache sign check is consistency evidence, not a second
independent ranking method. Clean source and actual call/error receipts plus
the complete lossless corpus are saved. Full class/tree and unrestricted
own-hand response equivalence remain required before training on this board;
this adds no strategy, convergence or performance result.

## Second-board exact quotient and response proof (2026-10-23 UTC)

The [separate frozen no-training audit](flop-second-board-equivalence.md)
completed full joint-mass/transport and both reveal-layer numeric subtree checks
for `7c8d9h`. It derives 170 compact worlds, 1,270 states and 608 own-hand policy
rows from the 5,940-world physical game. Four class-constant controls have exact
compact/unrestricted own-hand response equality and separate numeric gaps below
`9e-16` chips; within-class card variation and near-normalization reject.
All six complete policies and source/call/error receipts are retained. These
controls are not trained strategies; new-board convergence and any performance
comparison remain separate milestones. Publication status is in
[PR #213](https://github.com/ajpaulson18-design/openpoker-lab/pull/213).
