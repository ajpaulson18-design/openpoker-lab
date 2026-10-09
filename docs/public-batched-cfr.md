# Exact public-batched CFR

`solve_postflop(..., traversal="public-batched")` selects a specialized training
backend for the existing finite heads-up flop, turn or river game. The turn
facade accepts the same option. Recursive remains the default and mathematical
reference; the established configured river API and node-lock kernel are unchanged.

The backend groups weighted physical worlds into sparse private-pair edges at
each revealed public-card prefix. It traverses each public node once per
iteration, carrying each player's own-hand reach vector. Fold terminals use
joint edge mass; showdown terminals use mass multiplied by the independently
computed rank sign. Opponent reach determines counterfactual values and regret;
own reach and the prefix's own-hand chance marginal weight average strategies.
Chance branches sum values, and decisions key only the acting hand and visible
history. Vanilla CFR and DCFR use the same simultaneous update recurrence as
the reference.

This is exact enumeration of supplied chance worlds. The private-vector idea
is informed by [Johanson et al., Public Chance Sampling CFR](https://webdocs.cs.ualberta.ca/~mbowling/papers/12aamas-pcs.pdf);
the implementation does not sample public chance or implement that paper's
structured terminal sweep. Terminals still scan sparse private-pair edges.
No third-party code, runtime dependency or license change is introduced.

All existing postflop world, tree and work guards remain in force. A further
250,000 unique `(public prefix, oop hand, ip hand)` edge cap is reserved before
aggregation allocation. Results identify `public-batched-python` and report
`public_batch_edge_limit`; other backends report `None` for that field. Recursive
visitor closures are cleared on success and failure. The specialized trainer
supports the repository's static fold/showdown utilities; use the shared CFR
kernel for generic callbacks or strategy locks.

Eight added regressions compare weighted blocker-sensitive policies through
100 iterations, vanilla/DCFR and flop/turn/river starts, asymmetric stacks,
street sizing, raises and all-ins. An independent serialized-policy replay
checks flop value and both information-set best responses. Further tests cover
zero-reach fallback, input and edge limits, and CPython immediate release with
cyclic collection disabled on success and failure. These tests establish
backend agreement for their fixtures; they do not certify unrestricted GTO.
The complete repository suite passed all 331 tests in 105.342 seconds,
including the separate coaching regressions.

Global joint-world normalization uses `math.fsum`. The older left-to-right
float sum shifted four normalized fixture weights by up to `2.78e-17`, creating
tiny positive regret at an exact tie and changing finite-iteration policies.
A regression emulates that arithmetic through fixture construction and both
trainers at 20/100 iterations, preserving the original policy tolerance.
[Python's summation documentation](https://docs.python.org/3.12/library/functions.html#sum)
records the float-sum change in 3.12; [math.fsum](https://docs.python.org/3.12/library/math.html#math.fsum)
provides the accurate accumulation used here. This addresses the reproduced
normalization trigger; it does not guarantee bit-identical arithmetic on every
platform. CFR/DCFR recurrence and regret matching remain unchanged.

The controlled whole-call benchmark is:

```sh
python -m scripts.benchmark_public_cfr --algorithm vanilla --output benchmarks/results/public-batched-v2-vanilla.json
python -m scripts.benchmark_public_cfr --algorithm dcfr --output benchmarks/results/public-batched-v2-dcfr.json
```

Each run rotates backend order over independent full solves, including world
and tree construction, training, exact evaluation/best responses, and JSON
serialization. It separately traces complete-call allocation peaks. Explicit
garbage collection runs before each call and is excluded from timed intervals.
Reports record all solver, config and harness hashes and reject source changes
or policy/value/BR differences above `1e-10`. Selected runouts condition the
joint game; measurements apply to their recorded machine and source revision.

## Recorded whole-call comparison

The v2 vanilla and DCFR reports use frozen source `b6085fc`, Python 3.14.7
(`C:\Users\pauls\AppData\Local\Python\pythoncore-3.14-64\python.exe`) and
the same versioned config. Each player has 18 combinations; 324 compatible
pairs and three selected ordered runouts produce 864 physical worlds, 3,075
information sets and 466 public states. Three interleaved timed calls per
backend include JSON serialization; memory uses separate traced calls.

| Algorithm, 20 iterations | Recursive median | Public-batched median | Paired ratio | Recursive traced peak | Public traced peak | NashConv, chips |
|---|---:|---:|---:|---:|---:|---:|
| Vanilla | 9.225 s | 1.580 s | 5.84x | 6.47 MB | 6.66 MB | 6.1505 |
| DCFR | 10.965 s | 1.668 s | 6.57x | 6.50 MB | 6.70 MB | 2.8662 |

MB is decimal; these are traced Python allocation peaks, not process RSS.
Maximum serialized-policy/value/BR differences are `5.33e-15` for vanilla and
`4.66e-15` for DCFR. Both reports independently match all eight solver module
hashes, config and harness. This supports selecting the optional backend for
this game; it does not establish universal gains or a near-equilibrium
solution. The default remains recursive. Local full-suite validation used
Python 3.12.14, with GitHub validation on 3.11, 3.12 and 3.13.

The v1 vanilla report retains its original `9d2d66f` source and machine
measurement. It predates the normalization fix and is historical evidence;
its timing is not a controlled comparison against v2. The v2 reports are the
adoption measurements for the fixed source.

The wider commercial objective remains active: this backend does not add
preflop, multiway equilibrium, sampling, suit reduction or unrestricted bet sizes.
