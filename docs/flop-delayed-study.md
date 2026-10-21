# Frozen delayed-averaging flop study

[The protocol](../benchmarks/weighted-full-deck-flop-delayed-cfrplus-v1.json)
pre-registers delays 0, 70 and 100 at 140 CFR+ sweeps on the existing weighted
5,940-world full-future flop game, with configured betting on all three streets.
Each delay has three alternating recursive/public-batched pairs: 18 timed calls.
Two separate 10-sweep delay-one allocation calls and two physical-world records
complete the 23-file corpus. The corrected run is complete: every saved policy
passes independent replay, while all six final quality gates miss. Positive
delays 70 and 100 have larger NashConv than delay zero in this fixed game.

The canonical specification SHA256 is
`2b1c01a7c9a403cacae691c35347cbfc56726be5aaab8b0b0ea98f952b7bc902`.
All main requests retain three passes and 29,937,600 world-node units; every
existing resource cap remains. Rank-free structural admission precedes baseline
reconstruction, independent preparation and candidate ranking/training. The
[runner](../scripts/benchmark_flop_delayed_cfrplus.py) records a clean candidate
Git revision and complete source hashes before/after measurement. That identity
is separate from the measured baseline source0661603 and its publication commit.

Before candidate calls, the runner authenticates and independently reconstructs
[the CFR+ publication](flop-cfrplus.md#completed-evidence-and-quality-misses),
including its 20 policies and the original 38-policy baseline. It pins that
publication's immutable index/spec/source identities and both exact 140-sweep
control payload hashes. All six new zero-delay calls must reproduce the existing
per-backend payload hash. The previously missed quality gates remain immutable.

## Comparisons and observations

Every candidate policy requires independent physical/numeric-action/legal-own-hand
response replay with production ranking/training/value/response helpers disabled,
including the isolated delayed trainer. Full profiles and physical records are
stored losslessly with hashes. Timed calls include setup, training, exact
diagnostics and canonical serialization/hash; gzip storage and independent replay
are outside timing. Separate allocation calls trace Python allocation, not RSS,
and are excluded from timed medians. No controlled cross-host speed claim follows.

Every matching information set and action participates in cross-backend scalar
and action-realization comparison at tolerance 1e-8. Realization weight is the
independently enumerated compatible own-hand/public-prefix chance mass times the
player's own visible-history action reach times the current action probability.
The comparison visits actual physical information keys, excluding no valid row
and introducing no reach threshold. Impossible blocker combinations are not
invented as information sets.

Raw conditional probabilities can differ at zero/tiny own reach, as established
in [the adapter controls](flop-delayed-averaging.md#conditional-rows-at-zero-reach).
The new protocol records their maximum, nonzero count and at most ten largest
full-key/action examples. Complete raw policies retain every probability. These
raw gaps are diagnostics; the new protocol gates every action's realization
weight and every scalar. The original CFR+ study's conditional-policy gate and
all its published observations remain unchanged.

Each delay/backend receives its own unchanged 0.005-chip final NashConv decision.
Overall status requires all six decisions, including the known zero-delay miss;
therefore a positive delay can meet its individual gate while the complete study
still reports `quality-miss`. All observations and errors remain preserved; no
delay is tuned or selected after seeing results. Saved verification recomputes
baseline authentication, independent policy replay, exact within-backend repeats,
order/census, comparisons, quality decisions, source consistency and file inventory.

[Tests](../tests/test_benchmark_flop_delayed_cfrplus.py) execute rank-free140/141
admission, independent selected-runout replay, known rational chance/reach masses,
zero-reach diagnostics and reached-action tampering, finite metadata guards, and
all blocked public prefixes of both full saved 140-sweep controls without training.
No unrestricted NLHE, multiway, general delay benefit or RSS claim is established.


## Preserved startup failure

The first attempt at source `4f1f23be294012fac072f9e38fc40e4e5c9eb2ef`
terminated before production physical enumeration or any timed/allocation solve.
The legacy physical-world comparator called `max(iterations)` on this protocol's
single integer, producing `TypeError: 'int' object is not iterable`. The
[original index](../benchmarks/results/weighted-full-deck-flop-delayed-cfrplus-initial-v1/index.json)
and independent physical-world record are preserved unchanged. Its raw index
SHA256 is `bdecdfad71411b776360d94680e9c1f4fd109ffb3c11f24fe4c8c05ab818c740`;
canonical unsigned artifact SHA256 is
`07a3188f632a356587cfae7904870ffe7e8603e17e86fd94ab601c9d4616010e`.
Before/after source snapshots are identical and clean; the
[602-file Git/LF source attestation](../benchmarks/results/weighted-full-deck-flop-delayed-cfrplus-initial-v1-git-source.json)
authenticates the measured revision. Strict baseline reconstruction completed,
but this failed attempt contains zero candidate policies and no convergence or
runtime result. The saved-study verifier correctly rejects it as incomplete.

The runner now adapts the single count to a checkpoint list only when calling
that legacy helper. The frozen protocol, solver, requested work, delay matrix,
quality decisions and original evidence remain unchanged. A full 5,940-world
physical-record regression executes the production/independent comparison and
checks that the original protocol is not mutated. The seven-test focused suite
passes. The replacement run must use a clean validated revision and a new output
directory; the failed attempt must never be overwritten or counted as a timed call.


## Completed corrected study

The [immutable index](../benchmarks/results/weighted-full-deck-flop-delayed-cfrplus-v1/index.json)
records 18 timed calls, two separate allocation calls, and two physical-world
records: 23 files containing 2,664,985 stored bytes. The corrected attempt ended
on October 20, 2026 with `quality-miss`, zero validation errors and matching clean
before/after source snapshots. The first failed attempt above remains separate.

| Delay | Recursive NashConv | Public-batched NashConv | Original 0.005-chip gate |
| --- | ---: | ---: | --- |
| 0 | 0.012537880082120978 | 0.012537880082179598 | Both miss |
| 70 | 0.015051556109582087 | 0.015051556109651365 | Both miss |
| 100 | 0.026546196149619394 | 0.026546196150753598 | Both miss |

All 20 candidate policies independently reconstruct 5,940 physical worlds and
numeric action amounts, with zero absolute gaps in all eight reported metrics.
The original 20-policy CFR+ publication and its 38-policy baseline are also
strictly authenticated and reconstructed. Each delay/backend's three timed
payloads repeat exactly. All six delay-zero calls match the originally pinned
per-backend CFR+140 payload hash. Neither positive delay improves equilibrium
accuracy on this fixed workload. This does not establish that delayed averaging
is ineffective in other games or at other iteration budgets.

All valid strategy rows and actions participate in cross-backend comparisons.
The largest scalar gap is 1.13420384195706e-12 and largest action-realization
weight gap is 1.822986206434507e-13, below the frozen 1e-8 tolerances. The largest
raw conditional-probability gap is 7.206624186295585e-12. Nonzero raw-gap counts
are 17,164 / 6,528 / 6,528 for delays 0 / 70 / 100; these count every differing
action, including floating-point differences. Only the displayed example list
is capped at ten. Complete policies retain every row; no reach threshold or
row exclusion is introduced. The separate earlier zero-own-reach controls and
original study's conditional-policy gate remain unchanged.

| Delay | Recursive median complete seconds | Public-batched median complete seconds |
| --- | ---: | ---: |
| 0 | 267.18729529999837 | 103.17742340000405 |
| 70 | 239.16481380000187 | 77.28662030000123 |
| 100 | 223.83289399999194 | 70.99863489999552 |

These are the raw untraced complete-call observations, including setup, training,
recursive exact diagnostics, canonical serialization and hashing. All 140 regret
sweeps remain, and every request reserves three full training passes. Wall times
are observations on the recorded host, not a controlled cross-study or universal
speed comparison. Independent replay and gzip storage occur outside the timer.
The separate ten-sweep delay-one calls trace 36,195,438 recursive and 36,195,435
public-batched Python bytes. They are not process RSS or high-iteration memory
measurements and do not enter timed medians.

## Immutable source and reconstruction

Measured source is `676d805106f05e654c5b2d0782ca2e16213c7f26`, before the later
public-diagnostics option. The [Git/LF attestation](../benchmarks/results/weighted-full-deck-flop-delayed-cfrplus-v1-git-source.json)
compares all 602 captured LF hashes against that revision's Git blobs. Its
captured raw/LF source-manifest digest is
`296696179d3d3480bdce25e42edac9872c9ed13ac40d029b1d10e134c773ef56`;
the LF-only Git manifest digest is
`b19a2d98c1677d8fb4f217f93f5ac1e66425fbd16dd87313340690e9e21e7215`.
Windows raw hashes may differ from Git LF hashes; every normalized hash matches.

The completed index's raw SHA256 is
`6acb8dc5744fd8e544440b7204dc8d9962b915adeb4a26764c9dfdab22abc85b`;
its canonical unsigned artifact SHA256 is
`e77afe349fe1440d83443687b137bea7f7cb44d7da8bbcb2c4cb43df2472411c`.
The [publication verifier](../scripts/verify_flop_delayed_publication.py) pins
that exact index and measured source revision, count and full manifest before
independent saved reconstruction. Re-signing metadata cannot replace the
published observations. The verifier retains the complete-study miss; its
`--require-quality` option rejects the original unmet target.

```powershell
python -B -m scripts.verify_flop_delayed_publication
python -B -m unittest tests.test_flop_delayed_publication -v
```

The [publication tests](../tests/test_flop_delayed_publication.py) reconstruct
the candidate and both baselines without production authority, preserve all six
quality decisions, and reject re-signed source/gate/status/baseline observations
and altered physical signs or positive-delay numeric action amounts. No solver,
resource cap, training default, coaching behavior or earlier raw evidence changes
in this publication. Full-deck future chance in this configured heads-up game
still does not establish unrestricted NLHE or multiway equilibrium accuracy.


Publication validation: the full three-test reconstruction/corruption suite
passed in 216.134 seconds. A separate attestation control pins the sidecar's
raw SHA256 and compares all 602 LF entries with the immutable source map,
without requiring historical Git objects on CI. A fresh local Git-blob replay
also matched all 602 normalized source hashes before publication. Documentation
and whitespace checks pass; GitHub CI validates the published head before merge.
