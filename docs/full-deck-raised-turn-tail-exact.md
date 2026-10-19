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
