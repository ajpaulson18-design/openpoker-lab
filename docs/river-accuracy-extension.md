# Longer-budget river CFR+ accuracy evidence

## Diagnosis and bounded design

The independent turn/river grid at 20/100/300 iterations validated the reported
diagnostics but missed its 0.001-chip NashConv target on every profile. CFR+ had
the smallest river gaps in that grid. Sol selected an evidence-guided extension
of the two existing complete river fixtures at fixed checkpoints
**1,000 / 3,000 / 10,000**, using both existing backends and the same target.
All 12 profiles remain in the record. This selection does not establish that
CFR+ is generally the best algorithm or that these budgets are sufficient.

The [extension harness](../scripts/benchmark_river_accuracy_extension.py)
performs complete fixed-iteration solves, serializes each policy and independently
replays its EV and legal visible-information best responses. No production
solver, trainer, resource guard, earlier-street implementation or Coach changes
are included. These are two synthetic small-range fixed-board finite games.

## Measured accuracy

The [original report](../benchmarks/results/river-cfrplus-accuracy-extension-v1.json)
records all calls, source fingerprints, fixture configurations, eight oracle
metrics, policy hashes and target outcomes. Rounded gaps below are shared by
both backends; their small binary64 differences remain in the report.

| River fixture | 1,000 iterations | 3,000 iterations | 10,000 iterations |
| --- | ---: | ---: | ---: |
| Polarised bluff-catcher | 0.0705657041 | 0.0182906265 | 0.00790056594 |
| Weighted raises | 0.00404474440 | **0.000848854325** | **0.000279553443** |

Four of the 12 calls meet the unchanged 0.001-chip target: weighted raises at
3,000 and 10,000 with both backends. The other eight miss. Lower measured gaps
with larger iteration budgets are evidence for these fixtures, not a general
convergence theorem. The bluff-catcher remains the next accuracy priority.

Each complete bluff-catcher profile has two physical pairs and six information
sets; each weighted-raise profile has four pairs and 36 information sets.
Every policy passes independent numeric-rule replay and exact legal BR search.
Maximum scalar disagreement is **1.7763568394002505e-14 chips**. Exact here means
complete legal response search in the configured finite game; the general
replay uses binary64 arithmetic and has no formal rounding interval guarantee.

Raw single-call solve-plus-JSON times are retained for transparency. The shared
host, different iteration budgets and absence of controlled paired timing or
allocation/RSS measurements support no speedup or memory claim. No turn quality,
broader ranges, arbitrary bet sizing or unrestricted Hold'em claim follows.

## Saved-policy audit and exact small-game witnesses

All [12 complete policies](../benchmarks/results/river-cfrplus-accuracy-policies-v1/river-polarised-bluffcatcher-materialized-1000.json)
are committed in that file's directory. Directory-local Git attributes preserve
LF bytes so that policy SHA-256 checks also work after a Windows checkout.
The [saved-policy replay harness](../scripts/replay_river_accuracy_extension.py)
verifies those byte hashes before invoking the hardened oracle from cycle 3.
Its [separate report](../benchmarks/results/river-cfrplus-accuracy-hardened-replay-v1.json)
records all eight scalar differences for every complete policy, actual physical
counts, and the validator/harness source hashes. All 12 pass; the maximum
disagreement remains 1.78e-14 chips.

For all six bluff-catcher profiles, a second witness uses the independent
[rational one-bet oracle](../scripts/river_analytical.py): five explicit terminal
histories and exhaustive 16 OOP / 4 IP pure legal responses. It admits only the
exact known fixture, translates the single capped `all_in@100` wager history
to the analytically equivalent `bet@100`, converts the serialized binary64
probabilities to exact Fractions, and normalizes each row exactly. The largest
probability adjustment is **9.3400035862457e-17**.

The report preserves exact Fraction strings for the normalized witness's EV,
both BR values, NashConv and the game-value interval `[-BR_ip, BR_oop]`.
Every interval contains the independently known exact game value **25 chips**;
every rational witness still misses the 0.001 target. This is an exact rational
certificate for that explicitly normalized one-bet profile, not a formal
interval proof for the original raw binary64 rows, the raised game or arbitrary
river games. Its EV and BR values agree with learned diagnostics within 1e-9.

## Provenance and reproduction

The 12 production calls were frozen against merged main
`119f96d10ad638a6e0bde02110d079fb8c22d00d` plus the new extension runner,
with all 53 relevant source-byte fingerprints checked before and after the run.
This was before cycle 3 hardened metadata/gain checks, so the original report
contains six scalar differences even though its oracle metric record has eight.
The saved policies were subsequently checked against merged cycle 3 main
`9a7f8b6686be7dd74a6b92f688a7a43c2234ee72`, without retraining. The second
report contains all eight differences and the exact rational witnesses.
Source fingerprints describe the recorded files' bytes, including historical
checkout line endings; they are distinct from Git's canonical blob hashes.

Audit the committed policies without another training run:

```text
python -m scripts.replay_river_accuracy_extension --report benchmarks/results/river-cfrplus-accuracy-extension-v1.json --policies-dir benchmarks/results/river-cfrplus-accuracy-policies-v1 --output work/river-extension-replay.json
```

Reproduce fresh training and its current hardened replay:

```text
python -m scripts.benchmark_river_accuracy_extension --output work/river-extension.json --policies-dir work/river-extension-policies
python -m scripts.replay_river_accuracy_extension --report work/river-extension.json --policies-dir work/river-extension-policies --output work/river-extension-replay.json
python -m unittest tests.test_replay_river_accuracy_extension tests.test_turn_river_independent_validation
python -m scripts.validate_docs
```

Current-source regeneration can have different timestamps, platform/source
hashes, timings and diagnostic roundoff. Preserve these historical records;
write fresh reports to `work/`.

Sol reviewed the complete artifacts, exact witness translation, row-normalization
scope, all target misses and source provenance. Luna implemented five focused
regressions: exact equilibrium EV/BR/gap, capped-wager history translation,
fixture mismatch, nonfinite/negative probabilities, and byte-hash tampering.
The combined focused suite passed all 23 tests in 6.199 seconds. Documentation
validation passed (91 Markdown files, 309 local links, 12 required entry points),
and the committed-policy hash/replay command passed for all 12 profiles.
Full final-head CI and remote blob hash/size
verification remain required merge gates. The next research candidate is
same-trajectory CFR+ tail averaging in realization space; it requires an exact
toy proof and a fixed four-case independent replay before any production option.
