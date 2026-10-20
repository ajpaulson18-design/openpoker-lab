# Frozen delayed-averaging flop study

[The protocol](../benchmarks/weighted-full-deck-flop-delayed-cfrplus-v1.json)
pre-registers delays 0, 70 and 100 at 140 CFR+ sweeps on the existing weighted
5,940-world full-future flop game, with configured betting on all three streets.
Each delay has three alternating recursive/public-batched pairs: 18 timed calls.
Two separate 10-sweep delay-one allocation calls and two physical-world records
complete the planned 23-file corpus. No measurement or quality improvement is
claimed by publishing this protocol.

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
