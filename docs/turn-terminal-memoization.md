# Research: bounded reuse of turn terminal values

## Motivation and model

The [full-deck accuracy experiment](full-deck-turn-accuracy.md) establishes
independent policy quality under existing resource limits. A short instrumented
profile then identified repeated ranked terminal evaluation as a major cost in
the two-hand full-deck fixture. A separate ten-sweep observation executed the
original function on every call and found 5,002 repeated exact requests among
16,560 calls, with zero fallback work. The observed and ordinary complete
solver payloads matched byte for byte. Those observations motivated this
experiment; they establish no speed improvement.

This development experiment is limited to matrix-free CFR+ on the existing
selected-two-river and full44 fixtures, with at most 1,000 fixed sweeps and two
original hands per range. Production source and public solver defaults remain
unchanged. The wrapper controls its own single-process calls and exposes no
kernel objects or user callbacks that could mutate model state.

## Reuse and numerical invariants

Within one solve, each original river's ranked kernel has fixed holdings,
weights, card ranks, pot and normalization factor. A terminal request depends
on that kernel identity, player, terminal kind, validated matched contribution,
fold winner and opponent reach vector. The experimental helper uses exact
binary64 bits for numeric keys, preserving signed zero. It reuses values only
within the same original kernel, with no cross-river equivalence assumption.
It changes neither chance ordering nor any floating-point utility computation.

Each lookup still runs the original terminal/player/reach validation. A cached
success must not admit an invalid winner, unmatched infinite contribution,
boolean reach, wrong vector length or another invalid request. On a miss the
original evaluator runs. An entry is eligible only when that successful call
consumed zero fallback-pair work. A call requiring fallback work always executes
again, preserving cumulative accounting and failure behavior. Cached vectors
are immutable internally; each hit returns a fresh list.

The original outer turn evaluator retains prefix checks, branch probabilities,
original-hand scattering and finite-output checks. The experiment explicitly
rejects exceptional conditioning before training and rejects activated exact
root-fold stability paths. It does not modify those production paths.

Scoped class substitutions affect only the controlled development call and are
restored on success or failure. A fresh cache belongs to one solve and is
cleared afterward. No private-pair or physical-world table is stored. The
required correctness gate is equality of the entire original serialized solver
payload, including every strategy row, diagnostic and resource field.

## Resource and measurement boundaries

The original solver still admits its complete requested hand/state work before
training. A separate experiment limit caps retained cache entries at 16,384,
globally across all branches, with eviction before insertion. Reach and return
vectors contain at most two values each. Logical retained numeric payload is
bounded separately from Python object/container/reference/LRU overhead and
temporary copies; no allocation or RSS claim follows from an entry cap.
At the hard entry cap this numeric payload is at most 655,360 bytes: two
reach values, two return values and one matched contribution per entry. The
remaining fixed key fields and every Python representation cost are excluded.

The independent tree census finds 720 river terminals in the full44 fixture and
96 in the selected fixture. Matrix CFR+ performs two target-player utility
passes per sweep; its final diagnostics evaluate one OOP profile vector and
two response vectors per terminal. The experiment conservatively reserves four
diagnostic calls, admitting `river_terminals*(2*T+4)` calls and twenty logical
cache-slot units per call under a separate 30-million cap. At full44 `T=1000`
this reserves 1,442,880 calls and 28,857,600 units. The twenty-unit model counts
bounded validation/key/copy/LRU slots; it is not an instruction count or CPU
time guarantee. Every measured count must remain within its reservation.

Parent reports and both archived 1,000-sweep policy byte hashes are pinned.
Candidate 1,000-sweep results must exactly match those complete archived
payloads, and independently replay all eight metrics. Paired performance calls
use 300 sweeps on each fixture, three alternating baseline/candidate pairs,
with construction, training, final diagnostics and cache cleanup included.
Result serialization is included as well. Ten-sweep warmup calls are explicit
and excluded from the paired samples.
Independent replay and file checks occur outside the timed calls. All raw
times, ordering, cache counters and threshold misses must be retained.

The predeclared research runtime gate is baseline median divided by candidate
median at least 1.10 on both fixtures. Shared-host measurements support only
these observed cases. A failed gate remains a failed experiment; source
inspection, cache-hit rates or short instrumentation are insufficient speed
evidence. Production integration and broader mutable-model admission require
separate review even if the experiment passes.

## Executed evidence

All 84 focused tests passed in 105.008 seconds, covering the original ranked
river kernel, turn kernel, matrix-free adapter, independent turn/river replay
and all new memoizer/harness/review tests. Sol's separate witnesses use closed
form dyadic vectors, an actual cumulative fallback failure, actual exceptional
conditioning and actual activation of the root-fold stability path.
The 17 new tests also passed with `python -O` in 4.121 seconds. Documentation
validation passed across 99 Markdown files, 366 links and 12 required entries.

The full-request admission regression rejects an insufficient cache-slot cap
even when a test-only lower runtime exhaustion limit would stop the call early.
The helper cannot use early failure to weaken requested-work admission.

Both 1,000-sweep candidates exactly match their pinned archived complete
payloads. The selected model retains eight physical worlds and 138 information
sets; full44 retains 176 worlds and 1,112 information sets, including all 44
legal rivers for every private pair. All six saved complete policies replay
all eight metrics before and after saving. Sol separately checked policy byte
hashes/LF encoding, archived equality, physical counts, counters, timing
arithmetic and all 62 frozen source/input fingerprints. Maximum scalar
disagreement is 1.42e-14 chips.

| Fixture | Sweeps | Independently replayed NashConv | Meets 0.001 |
| --- | ---: | ---: | --- |
| Selected two rivers, baseline and candidate | 300 | 0.046940230887631884 | No |
| Full44, baseline and candidate | 300 | 0.01611099682434869 | No |
| Selected two rivers, candidate/archive equality | 1,000 | 0.00423446838076913 | No |
| Full44, candidate/archive equality | 1,000 | 0.0014533696436025423 | No |

No convergence target was configured. Every saved profile misses the reporting
threshold; faster evaluation does not itself improve these strategies.

Paired 300-sweep complete calls ran in baseline/candidate, candidate/baseline,
baseline/candidate order. Each fixture reproduced the same complete payload
hash across all three repeats and both execution modes.

| Fixture | Pair | Baseline seconds | Candidate seconds |
| --- | ---: | ---: | ---: |
| Selected | 1 | 5.435431 | 3.971909 |
| Selected | 2 | 5.948460 | 3.906076 |
| Selected | 3 | 5.823449 | 3.850211 |
| Full44 | 1 | 37.555577 | 25.076141 |
| Full44 | 2 | 37.387661 | 26.272783 |
| Full44 | 3 | 35.456091 | 26.327492 |

Selected medians were 5.823449 / 3.906076 seconds, a baseline/candidate ratio
of 1.490869. Full44 medians were 37.387661 / 26.272783 seconds, ratio 1.423057.
Both meet the predeclared 1.10 research gate in this recorded environment.
These are uncontrolled, shape-specific observations; there is no production
integration or general runtime/memory claim.

Each selected 300-sweep candidate used 57,888 inner calls, with 54,714 hits,
3,174 misses, a maximum of 3,172 entries and no evictions. Full44 used 434,160
calls, 415,343 hits, 18,817 misses, at most 16,384 entries and 2,433 evictions.
At 1,000 sweeps actual selected/full44 call counts were 192,288 / 1,442,160,
below reserved ceilings of 192,384 / 1,442,880. Every cache was empty after
cleanup. The retained-entry cap is reached and eviction is exercised by the
full-deck experiment.

The complete machine-readable evidence is
[turn-terminal-memoization-v1.json](../benchmarks/results/turn-terminal-memoization-v1.json).
The [saved policies](../benchmarks/results/turn-terminal-memoization-policies-v1)
retain both 300-sweep modes and both 1,000-sweep candidates. Reproduce with
`python -m scripts.benchmark_turn_terminal_memoization --phase preflight` and
then `--phase measure`; the latter runs the complete pinned comparison.
