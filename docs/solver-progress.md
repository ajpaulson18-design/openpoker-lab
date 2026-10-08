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

## Next integration milestone

Existing PR #23 contains a real stack-aware multi-size/raise river tree.
Independent review identified a stack-clipped scalar-bet metadata defect and
the need for complete pure-policy best-response tests. Integrate that existing
work after repair and regression validation, preserving this optimized
restricted entry point and optional algorithm selection. Then introduce
explicit chance nodes in a small independently solvable multi-street game.
Neither action-tree expansion nor street support alone proves full NLHE
equilibrium accuracy.
