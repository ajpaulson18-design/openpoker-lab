# Frozen trainer-grid update reference

The [staged-walk observation](native-staged-walk-observation.md) identified
terminal computation and State among the largest observed walk contexts.
The [eleven-card forecast](native-dyadic-storage-census.md#parent-work-inside-the-eleven-card-forecast)
still exceeds State, quantizer and combined work caps. Additional sampled
traversal therefore needs a whole-game mathematical bridge before it can
justify a new State schedule or production optimization.

The new reference accepts the trainer's ordered nonnegative integer policy
units, summing exactly to `2^52` at each visible row. It preserves all 24,420
full-history/own-holding rows and 58,164 action slots in the unchanged four-street
PROOF9 game, including zero-policy actions and zero-reach rows. This is a
reference-only fixed-policy experiment. Native frozen-update input still uses
the older power-of-two profile; no native grid ingestion or learner is added.

## Separate calculations

The immutable grid factory copies and validates every row/menu/partition and
hashes canonical ordered records. Both paths check the snapshot origin; the
proposal walker also checks exact `Fraction(unit,2^52)` equality at each used
row. Identity checks are internal provenance guards, not a Python object
security boundary.

The proposal oracle uses the independent card-free template snapshot, exact
Fraction reaches, literal compatible private pairs and independent seven-card
ranking. Raw regret uses `pair_prior / Z / 20 / q(B)` times opponent reach.
A separate own-reach walk uses `mu_i(P) / q(P)` and stops before the next
unseen reveal. Both players keep global SB/BB utility signs.

The q-free target uses the separately written literal-world
`Fixture.sweep` reference, not the proposal walker or native trainer. To recover
signed deltas from its CFR+ output without modifying historical source, every
prior regret receives `16D`. Utilities lie in `[-8,8]`; each world visits a
full-history row at most once, and the sum of nonnegative world mass times
opponent reach over the row's worlds is at most one. Thus each raw action delta
is at least `-16`, clipping leaves `16D + D*delta` unchanged, and subtracting
`16D` recovers the exact signed delta. Average state begins at zero.
The existing reference still checks exact fixed-denominator divisibility and
integer width. This translation is an oracle technique, not a learning rule.

## Complete proposal coverage by prefix factorization

For each law, explicitly sum all 2,520 positive proposal probabilities to every
visible prefix, checking the independently prepared `q(P)` and total one.
Exactly 60 complete boards have positive physical joint target; the other
2,460 have identically zero full-board regret. Evaluate those 60 regret walks,
multiply by `q(B)` and sum every signed action contribution.

The average contribution at a row with visible prefix P depends only on P,
own holding and visible history. Obtain a representative from a compatible
completion and multiply its `mu_i(P)/q(P)` contribution by the sum of **all**
proposal completion probabilities `q(P)`. Require exact agreement of repeated
representatives and complete final row coverage. This includes zero-full-target
futures analytically; it does not redraw or discard them. Executable witnesses
compare positive and zero-target completions at preflop, flop and turn.

This new algebraic reference protocol does not replace or reclassify the
[historical 5,040-native-call study](virtual-frozen-update-study.md). That
study, its source pins and its power-profile wire remain unchanged.

## Resource and evidence boundaries

Each profile/law experiment has one cumulative reduce-only meter with the
existing 500-million work, eight-million logical-entry, 65,536 integer-bit and
16-billion created-bit ceilings. Context setup is reserved once; a
source-reviewed static envelope covers literal Fixture setup, one q-free sweep,
snapshot and translated outputs. Proposal census reservations precede its
allocation, then every proposal-oracle Fraction operation and inserted row is
guarded cumulatively. No counter is reset inside an experiment. Four separate
experiments each pay the complete setup/reference reservation.

These are conservative modeled charges, not CPU instructions, RSS or CPython
allocation measurements. They are static component reservations plus dynamic
cumulative guards, **not a complete a priori composition proof** for an
arbitrary grid study or native solver admission. Saved rows are streamed under
a 32-MiB uncompressed ceiling per experiment. The saved replayer is for the
locally produced evidence packet; its metadata JSON is not a general untrusted
artifact ingestion interface.

The runner requires clean committed source, captures all tracked Python/C++
raw source hashes and committed blob identities, and checks them again after
execution. Saved-only verification authenticates that source closure, rebuilds
the separate q-free target and compares every saved expected/candidate field,
menu, grid unit and root value. It makes zero candidate-estimator or native
calls. All failed experiments must remain separate from accepted evidence.

Run an explicit experiment with:

```text
python -B -m scripts.run_frozen_grid_update_study --output-dir FRESH_DIRECTORY --profile uniform --law uniform
python -B -m scripts.run_frozen_grid_update_study --output-dir FRESH_DIRECTORY --verify
python -B -m unittest tests.test_virtual_grid_update_reference -v
python -O -B -m unittest tests.test_virtual_grid_update_reference -v
```

For later checkouts, use the maintained saved-only replay:

```text
python -B -m scripts.replay_frozen_grid_packet
```

The original runner's strict whole-checkout guard remains part of its frozen
protocol. The maintained replayer instead authenticates the pinned archive,
all 1,034 member hashes, the complete 998-file historical source closure and
its committed blob map before importing the current q-free oracle. Its thirteen
executed oracle dependencies must match archived raw bytes, the exact frozen
committed blob, or that LF-only blob's exact uniform CRLF checkout. The
candidate source is never normalized; other mixed endings and code changes
reject. Unrelated
source additions are permitted. Archived code is never imported or executed.
Both checkout forms are exercised by a separate Windows/Linux workflow with
full Git history. Native and candidate-estimator calls remain zero.

At source `e2c8820`, all four maintained replays passed, six focused controls
passed normally and optimized, and independent source/workflow review found
no material defect. The [replay evidence](../benchmarks/results/frozen-q52-maintained-replay-v1/manifest.json)
retains the actual results, source identities and control logs. Cross-platform
CI acceptance is recorded separately from the local result.

The first Linux CI replays passed, while both Windows jobs at `aaf8ca0`
rejected `tests/test_native_dyadic_policy.py` before mathematical replay.
Its frozen working-tree bytes contained a historical mixture of line endings;
a fresh Git checkout produced uniform CRLF, which matched neither the captured
raw bytes nor the LF committed blob. At `c60398d`, authentication also accepts
the exact uniform CRLF form derived from that pinned LF blob, without changing
or normalizing candidate source. A fresh Windows worktree reproduced the old
rejection and passed all four full replays with the correction; seven controls
passed normally and optimized. The [preserved correction evidence](../benchmarks/results/frozen-q52-crlf-replay-fix-v1/manifest.json)
retains the CI failure, exact source-form comparison and actual results.

## Next architectural gates

Frozen raw-update equality does not imply sampled CFR+ convergence:
`E[max(0,R+delta)]` generally differs from `max(0,R+E[delta])`.
An evolving-policy algorithm must separately specify iteration snapshots,
unvisited State, signed updates, averaging schedule, numerical admission and
independent saved-policy quality checks. Native arbitrary-grid ingestion and
denominator/transport bounds remain prerequisites to comparing actual sampled
walk costs. No quality, runtime gain, eleven-card training capacity or realistic
full-deck HU NLHE capability follows from this reference result.

## Frozen result and width blocker

At committed source `0c94835`, both uniform and sparse/skewed Q52 profiles
passed under uniform and river-weighted proposals. Each experiment matched
every signed regret, average slot and root exactly; each saved-only replay
independently matched all 24,420 rows and 58,164 slots. Eleven controls passed
normally and with optimized Python; four corrupted packets were rejected after
transport hashes were updated, including signed-regret, policy-unit,
missing-row and source-hash changes. Independent source and evidence reviews
found no remaining material defect within the declared scope.

| Profile | Law | Modeled work | Logical entries | Created-bit charge |
| --- | --- | ---: | ---: | ---: |
| Uniform | Uniform | 363,592,026 | 5,561,518 | 14,604,707,871 |
| Uniform | River-weighted | 363,592,026 | 5,561,518 | 14,606,724,545 |
| Zero/skew | Uniform | 363,592,026 | 5,561,518 | 14,447,289,158 |
| Zero/skew | River-weighted | 363,592,026 | 5,561,518 | 14,448,026,258 |

The uniform expectation has 28,902 negative and 29,262 positive regret slots.
The zero/skew expectation retains 48,081 zero regret slots and 47,782 zero
average slots. Saved reduced fractions reach 419 bits in the uniform aggregate.
A separate source-bound one-board reference witness on
`[16,17,32,33,35]` contains a **421-bit** preflop SB raw regret. This exceeds
the historical `virtual_frozen_update_probe.cpp` 384-bit cap even before
attempting native grid ingestion. It is one observed lower bound, not a
worst-case width forecast. The cap and old wire are unchanged.

Native work must therefore begin with a distinct, fully accounted trainer-grid
input and arithmetic contract, rather than just changing the old profile
selector or increasing its limit. Reuse of the trainer's existing factored
integer representation is a candidate to assess; no feasibility or speed
acceptance follows yet. A complete width/work/storage forecast and independent
per-board comparisons precede any native benchmark or evolving-policy learner.
The [native arithmetic contract audit](native-frozen-grid-arithmetic.md)
proves a possible common scale and identifies the existing exact carrier;
its resource and implementation gates remain open.

The [immutable evidence manifest](../benchmarks/results/frozen-q52-update-reference-v1/manifest.json)
links the complete saved rows, source closure, replay/control logs, corruption
witnesses and width observation. The exploratory development TypeError and its
correction are retained separately from the accepted frozen runs.
