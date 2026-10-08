# Solver progress record

Snapshot: 2026-10-08. Mathematical calculation only; the AI Coach workstream
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

## Next implementation milestone

Introduce explicit public chance nodes and a small heads-up turn-to-river
game, reusing the public action tree and information-set policy boundary.
Condition runout probabilities on both private hands, preserve perfect recall,
carry commitments/stacks consistently between streets, and independently
enumerate tiny-game values and legal best responses. Then increase range and
tree coverage before selecting a compiled backend based on profiling.
Action-tree expansion and street support alone do not prove full NLHE accuracy.
