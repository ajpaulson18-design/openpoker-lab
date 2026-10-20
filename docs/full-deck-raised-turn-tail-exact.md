# Exact audit of the same-run raised-turn profiles

This separate research audit reads the six complete policies from the
[same-run averaging experiment](full-deck-raised-turn-tail.md). It performs no
training and never changes those numeric policies or their report. The numeric
report SHA256 is fixed to
`9e51cbcf9f031f371806be06e6a23589e0dd27d5e3ffffcf36fc545eed5d6998`.

The [checked chance-class auditor](full-deck-raised-exact.md) independently
reconstructs the fixed 176-world physical game, complete policy and public
tree before exact evaluation. Its proof requires identical physical card sets
across supported private pairs within each class, equal showdown signs and
public subtrees, and exactly class-constant policy probabilities and metadata.
It preserves the legal full game's individual-card best responses and integrates
the hidden future before turn choices. This is a fixed-game reduction; it does
not condition the game onto five physical rivers or certify arbitrary policies.

The unchanged Fraction helper explicitly normalizes binary64 policy rows. Each
accepted profile records all eight exact metrics, legal-response bounds,
canonical normalized rows, normalization adjustments and work counters. A
profile rejected by the exact auditor has an explicit rejection and no partial
certificate. Exact threshold decisions compare Fractions with 1/1000; numeric
zero remains a separate observation. All prefix/full target misses remain saved.

The exact limits stay at 100,000 modeled work units, depth 64 and 65,536 fraction
bits. Full physical validation, quotient preparation and numeric replay are
outside that helper's work counter and retain their fixed envelopes of 176
worlds, 2,404 policy rows, 3,039 public nodes and depth nine. They are not RSS,
CPU or serialized-byte bounds.

The audit pins the reference, complete numeric report, all six policy hashes
and proof sources. Before and after each profile, source fingerprints, current
HEAD and every accepted input byte must remain stable. Numeric and exact reports
are bounded to 8,000,000 bytes and policies to 2,000,000 bytes before reading.
Publication is exclusive and atomic, verifies staged and published artifacts,
and removes only newly owned output files on failure. Saved verification
reconstructs exact certificates and ledgers without metric repair or training.
Only the two recorded floating diagnostic maps allow 1e-12 cross-platform
replay tolerance; exact certificates, ledgers and threshold decisions remain
strict.

## Recorded audit

The [immutable six-policy audit](../benchmarks/results/full-deck-raised-turn-tail-exact-v1.json)
is 7,858,950 bytes with SHA256
`f4901675fcb026fbac6713baf604650fd48f510c5ae4dc6be2c776c0a780c0c7`,
below the unchanged 8,000,000-byte cap. Generation was frozen at
`a9004d891a26f02f01f7e0ba56780f2304f488c3`; all 15 source pins match
committed Git bytes. All six profiles were accepted, with no training calls.

| Profile | Materialized exact NashConv, rounded | Matrix-free exact NashConv, rounded | Exact 1/1000 target met |
| --- | ---: | ---: | --- |
| Prefix | 0.0037309341770361214 | 0.003730934177036123 | No |
| Full | 0.0016587453303189687 | 0.0016587453303189693 | No |
| Tail | 2.2898589442074785e-19 | 4.367065158111689e-19 | Yes |

Every gap is strictly positive. Both tails meet the exact target but neither is
an exact-zero equilibrium witness. All four prefix/full misses remain saved.
Prefix/full certificates use 13,708 modeled exact-work units; materialized and
matrix-free tails use 12,458 and 12,782. The largest fraction encountered is
6,423 bits; the largest row-normalization adjustment is 1.424e-16. Maximum
exact-metric versus full physical numeric replay difference is 8.257e-15 chips.

Staged, published and saved verification passed. A separate Sol reconstruction
imported neither candidate exact auditor, used its own projection constructor
and a literal 12-world mass table, and matched all eight exact metrics for every
profile. That reconstruction shares the generic Fraction evaluator; full
physical numeric rules and the independent hand-written check/call anchors
remain separate checks. The accepted-report test binds the complete report
hash and disables production capture/training entry points.
It passed in normal Python (14.433 seconds) and optimized Python (14.263 seconds).

## Reproduction

The seven integrated focused tests passed in normal Python (166.621 seconds)
and optimized Python (167.739 seconds). They include acceptance of all six real
input profiles with their distinct backend version labels, complete synthetic
six-profile publication/replay without training, explicit exact rejection,
numeric diagnostic tolerance versus strict certificate/ledger checks,
late accepted-input/source/HEAD drift, and rollback preserving unrelated files.
These are harness checks; the actual pinned six-policy audit is separate.

Run `python -m unittest tests.test_turn_tail_exact -v` and repeat with `python -O`.
`python -m scripts.audit_turn_tail_exact --generate` publishes the separate
immutable audit after source freeze. `--verify` reconstructs it without training.
Production/default averaging, preflop/flop and the original numeric evidence
remain unchanged.
