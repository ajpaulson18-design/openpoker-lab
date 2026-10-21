# Preregistered flop algorithm comparison

This preregistered comparison is complete: CFR+, LCFR and alternating DCFR all miss the original 0.005-chip target on this bounded heads-up flop game. The protocol is fixed in [`weighted-full-deck-flop-alternating-v1.json`](../benchmarks/weighted-full-deck-flop-alternating-v1.json). The original protocol and all three misses are retained below. Do not tune iterations, schedules, gates or the fixture within this recorded study.

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

## Completed frozen measurement

The single recorded run finished on October 21, 2026 at 18:31:25 UTC with
`status="quality-miss"` and no validation errors. Every method has three exact
140-sweep payload repeats. All three original per-method 0.005-chip gates miss:

| Method | Independent NashConv, chips | Original target | Result | Median observed complete-call seconds |
| --- | ---: | ---: | --- | ---: |
| cfrplus-control | 0.012537880082180 | 0.005 | Miss | 68.974115 |
| lcfr | 0.090593278528127 | 0.005 | Miss | 58.180124 |
| alternating-dcfr-3/2-0-2 | 0.011508822247107 | 0.005 | Miss | 59.044988 |

Alternating DCFR has a smaller saved gap than the CFR+ control on this fixture;
LCFR has a larger gap. Neither new method meets the target. These are finite-game
profile observations, not an unrestricted equilibrium or general algorithm ranking.
Defaults, caps, schedules and the fixed fixture are unchanged.

The corpus retains all nine timed policies, all three separate allocation
policies, both physical-world records and the index: **15 files, 1,931,087 bytes**.
Each saved policy is independently reconstructed against the 5,940 ordered
physical worlds, legal numeric actions and own-hand best responses. The pinned
20-policy CFR+ and original 38-policy baselines remain part of reconstruction.
The maximum recorded gap across all eight scalar checks and 12 candidate files is `0.0`.

All three CFR+ control hashes exactly equal the original public-batched
CFR+140 payload `db80b4bd394d935ac3fd6b7fea9fd7ca4530fb3766102433ae7e5fef9908c41b`.
The LCFR repeat hash is
`ed45dc39a604cb725300c6b204062eabe0476f3e95bb9b044916035db85f6505`;
alternating DCFR is
`86d548a207f2cbc1f47bf2cac87fd416bb3a37565f66f425d02e3778e1947c1e`.

Cross-method comparisons scan every one of the 16,912 aligned information sets
and 33,824 action rows. Their raw conditional-probability nonzero counts are
26,092 (CFR+/LCFR), 31,376 (CFR+/alternating DCFR) and 31,336
(LCFR/alternating DCFR). The index keeps all scalar/own-reach realization maxima
and ten largest raw examples per pair; raw policy files keep every probability,
including zero-reach rows. These differences remain diagnostics, not equality gates.

Separate 10-sweep Python allocation peaks are 36,311,603 bytes for CFR+,
36,322,743 for LCFR and 36,322,735 for alternating DCFR. They do not describe
140-sweep allocation, native memory or RSS.

### Source identity and timing qualification

The measured revision is
`481e7ec508724be5012a895f6e53b5b3d375034a`. The captured 626-file source map
has SHA-256 `0d77d79d310231833ff25414205df12c845de1261b7c583c9c7f801e67920b81`;
its Git-LF map is
`dc48bb7a6c7335549788988b82169adfcc40e7a1da8a699610415fc1b98cc866`.
Every normalized captured source file was matched to its committed Git blob.
The recorded source revision, input hashes and clean Git status are identical
before and after the measurement.

During the run, an untracked non-input Markdown planning draft was accidentally
created under the checkout's `work/` directory, then moved outside it. Git status
was briefly dirty. It was outside the executable/configuration/documentation
input paths, and all 626 captured input hashes remained identical to prelaunch.
The [immutable incident receipt](../benchmarks/results/weighted-full-deck-flop-alternating-v1-scratch-incident.json)
preserves the event and correction; this is not a claim of clean status throughout.
The observed call times may include incidental draft I/O and correction checks.
They are retained without a controlled timing or general speed claim. No call
was restarted, dropped or rewritten.

### Immutable saved-file reconstruction

The [15-file index](../benchmarks/results/weighted-full-deck-flop-alternating-v1/index.json),
[Git source attestation](../benchmarks/results/weighted-full-deck-flop-alternating-v1-git-source.json)
and incident receipt have external raw-byte pins in the
[publication verifier](../scripts/verify_flop_alternating_publication.py).
The raw index SHA-256 is
`32b549df30ce3ac13a12b1fdd32c2cefda795feb7ed0364f6eb1960bfd5c1088`;
the canonical unsigned artifact is
`aee1a69f9e88fe2b35a3bb7ea85df045958fc315087daef4df0e14b21d7c5e90`.
Reconstruction re-enumerates physical worlds and replays the candidate and
historical policies without training:

```powershell
python -B -m scripts.verify_flop_alternating_publication
```

`--require-quality` rejects the retained target misses. Published evidence does
not establish a successful convergence result for either new trainer. A future
exact public-chance quotient requires a separate no-training full-tree and
physical-response equivalence audit before any compact training is considered.
