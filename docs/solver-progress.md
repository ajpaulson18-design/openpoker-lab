# Solver progress record

## 2026-10-09 ranked river terminal work

Branch `solver/ranked-river-20261009`, base merged `5c712f8`: added an optional
fixed-board ranked payoff backend for public-batched river training and
diagnostics. Blocker-aware rank sweeps, compensated accumulation and direct
summation on ill-conditioned cases preserve physical range products and
short-stack refunds. Rational pair-loop tests caught and prevented two
cancellation defects. No earlier-street or Coach behavior is changed.

Cached-sparse terminal phase comparisons show 1.22–15.19x speedups across
64–512 hands per player, with increased working allocation. Complete-call
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
All four CFR+ benchmark fixtures reached 0.1 chips in 100–240 iterations;
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
21–28% across eight synthetic fixture/checkpoint comparisons with pre-optimization
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
- Work limits: 10–10,000 iterations and at most three million nominal
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
up to eight configured opening sizes and eight raise sizes, 0–8 raises per
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
optimized fixture and 24.9–44.0/24.9–44.1 KB for the configured fixtures.
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
