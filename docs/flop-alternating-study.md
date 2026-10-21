# Preregistered flop algorithm comparison

This is a preregistered, not-yet-run comparison of CFR+, LCFR, and alternating DCFR on one bounded heads-up flop game. The protocol is fixed in [`weighted-full-deck-flop-alternating-v1.json`](../benchmarks/weighted-full-deck-flop-alternating-v1.json). No convergence or performance result is available yet. Do not tune iterations, schedules, gates, or the fixture after observing results.

## Fixed game

The board is `2c3d4h`. OOP holds `AsAd` with weight 1 or `QsQd` with weight 1/2. IP holds `AsKh` with weight 1/4 or `KsKd` with weight 1. Three of the four candidate private-hand pairs are compatible. After global blocker conditioning, the exact priors are `AdAs/KdKs: 8/13`, `QdQs/AsKh: 1/13`, and `QdQs/KdKs: 4/13`; the raw joint-weight normalizer is `13/8`.

The configuration has a 10-chip pot, 5-chip effective stack, one half-pot bet size, no raise sizes, no all-in option, and no raises. The fixed flop game includes configured betting on the flop, turn, and river, with all future cards enumerated. It has 5,940 physical ordered-card worlds. The rank-free census is 9,512 decision nodes, 30,812 public states, 248 chance nodes, 21,052 terminal nodes, 12 visited decision nodes per world, and 6,078 public-prefix/private-hand edges.

Each 140-sweep request reserves three complete training passes: one averaging pass and two target-player regret passes. That is 831,600 world-iterations and 29,937,600 world-node iterations per call. All 9 timed calls and all 3 separate 10-sweep allocation calls must pass rank-free admission before independent physical-world enumeration begins.

## Compared schedules

The control is the existing CFR+ public-batched path with zero averaging delay, linear post-sweep own-reach averaging, and its positive-regret floor. Its 140-sweep payload must exactly match the previously recorded zero-delay CFR+ payload.

The new methods retain the exact unfloored, pre-sweep averaging recurrences in
[the algorithm specification](flop-alternating-cfr.md#algorithms-and-update-order):
LCFR uses linear regret and averaging weights; alternating DCFR uses the
(3/2,0,2) discounts and quadratic averaging, updating OOP before IP.
Brown and Sandholm's [primary paper](https://arxiv.org/abs/1809.04040)
provides the discounting/weighting mathematics and also uses alternating updates.
The repository's arithmetic, indexing, own-reach convention and fixture require
their own validation and measurements; no external implementation is imported.

## Calls and evidence

There are three timed complete calls per method, in these rotating orders: CFR+ / LCFR / alternating DCFR; alternating DCFR / CFR+ / LCFR; then LCFR / alternating DCFR / CFR+. The timer includes the complete solve, canonical JSON serialization, and payload digest. Independent physical preparation and policy replay occur outside the timed interval.

Three separate 10-sweep calls use Python `tracemalloc`, one per method. These are allocation observations, not RSS measurements; independent replay is outside tracing. The complete artifact set is nine timed policy payloads, three allocation-call policy payloads, two physical-world records, and one index: 15 files total. Every repeat payload is retained and must match exactly within its method.

The run reconstructs and replays the immutable earlier CFR+ publication: 20 policies from the measured full-deck study and the original 38-policy source baseline. The historical baseline's quality miss is retained, and the CFR+ control is checked against its recorded 140-sweep payload hash. The current run records its source snapshot before and after execution; a later immutable publication wrapper must pin the committed source identity and completed index after the run exists.

All candidate payloads are independently replayed against a separately reconstructed physical-world and legal-action oracle. Every information-set row and action remains in the saved policies, including zero-reach rows. Each method has its own unchanged quality decision: final NashConv must be at most 0.005 chips. Cross-method raw probabilities, own-reach action realizations, and scalar metric differences are diagnostics only; the three schedules are not required to produce equal policies or metrics. A result is a quality miss if any method misses its gate. Do not discard misses or describe this as an equal-work convergence ranking or a universal algorithm comparison.

## Reproduction commands

After both the trainer and protocol changes pass CI and merge, use a clean committed checkout. Run from its root with a new evidence directory outside the checkout and immutable baseline directory:

```powershell
python -m scripts.benchmark_flop_alternating --output <new-evidence-directory> --baseline <immutable-baseline-directory>
python -m scripts.benchmark_flop_alternating --output <new-evidence-directory> --baseline <immutable-baseline-directory> --verify
```

The run must retain its source revision, complete raw/LF file manifest and original target. A terminal quality miss is a completed measurement, not a passed accuracy gate. Saved verification replays evidence without training; the later publication wrapper must authenticate the measured Git sources and index. Newer verifying checkouts need not equal the recorded historical source.

## Protocol validation before measurement

The canonical specification SHA-256 is
`738e8f123a3bdb844efdfe78638ce4954dfcb65fd0979e351e28ff853d72192d`.
The installed protocol passed all 18 focused tests in 52.068 seconds:

```powershell
python -B -m unittest tests.test_benchmark_flop_alternating -v
```

These include actual rank-free admission with ranking/training disabled, the
real archived CFR+140 metadata/hash contract, legacy physical-helper API shape,
trainer-alias guards, numeric-action/census corruption and retained failure
records. A complete temporary 15-file save/verify rehearsal uses archived policy
data and stubbed training/oracle preparation; it verifies from a newer stable
checkout without retraining and rejects a rechecksummed boolean counter.
That rehearsal is bookkeeping validation, not a new solver measurement.
