# Exact-zero witnesses for the fixed full-deck raised game

This separate research builder derives two complete candidates from the
[accepted numeric tails](full-deck-raised-turn-tail.md), whose
[original exact audit](full-deck-raised-turn-tail-exact.md) records small
positive gaps. Those original policies and gaps remain immutable.

The cleanup rule is declared before generation: `tau=1e-12`; set probabilities
at or below tau to zero, at or above `1-tau` to one, then normalize each row
in its original action order using `math.fsum`. A deep copy preserves every
legal row and non-probability row/action field. New root provenance identifies
the derived witness, its source policy, original averaging schedule and complete
inherited training cost. All eight numeric metrics are recomputed through full
physical rules. This candidate is not an unchanged trainer return.

Cleanup alone proves nothing about equilibrium. Each candidate must pass the
unchanged [checked chance-class auditor](full-deck-raised-exact.md) and have
exact Fraction NashConv equal to zero; a positive gap, however small, rejects
publication. The certificate applies to the explicitly normalized binary64
candidate for this fixed 176-world game with finite turn/river raises. There is
no general rounding guarantee or production/default recommendation.

The numeric report is pinned to SHA256
`9e51cbcf9f031f371806be06e6a23589e0dd27d5e3ffffcf36fc545eed5d6998`;
the accepted exact tail report is pinned to
`f4901675fcb026fbac6713baf604650fd48f510c5ae4dc6be2c776c0a780c0c7`.
Both pins are required before reading inputs or creating outputs. The physical
reference, complete source policies and proof/capture/test sources are pinned
and checked before and after each backend. Policy files remain bounded to
2,000,000 bytes and the report to 8,000,000 bytes before reading.

Exact helper limits remain 100,000 modeled work units, depth 64 and 65,536
fraction bits. Full physical validation, quotient preparation and numeric replay
retain their separate fixed envelopes and remain outside that helper's counter.
These counts do not bound CPU, Python storage or RSS.

Generation publishes two new complete candidate policies and one report,
including per-action hexadecimal cleanup changes, all exact metrics,
normalization ledgers, canonical normalized rows and resource evidence.
Publication is exclusive and atomic, verifies staged and published bundles,
and removes only newly owned files on failure. Saved verification accepts a
valid historical generation commit while guarding the current HEAD and sources;
it checks saved policy byte hashes, reconstructs candidates without training,
and rereads all report/input/output bytes after the last audit. Exact certificates,
cleanup ledgers, strategy probabilities and metadata are strict. Only numeric
replay observations allow 1e-12 tolerance; stored metrics are not repaired.

## Recorded witnesses

The [immutable witness report](../benchmarks/results/full-deck-raised-turn-clean-witness-v1.json)
is 1,709,045 bytes with SHA256
`e9e44108b1158840383cd025dcd995b21d3fc35d902a59ab2bae3a5060bf88e6`.
Generation was frozen at `eb8b228e2f298bdffab74d5a547b619a88ec2eb8`;
all 26 proof/capture/test source fingerprints match committed Git bytes.
Both complete policies retain all 2,404 rows and are below 2,000,000 bytes.

| Source backend | Changed rows | Changed actions | Maximum probability change | Exact NashConv | Exact value OOP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Materialized | 243 | 246 | 6.363731946721238e-20 | 0 | -400/21 |
| Matrix-free | 165 | 167 | 3.28454299504272e-20 | 0 | -400/21 |

Each certificate uses 9,444 modeled exact-work units. Maximum fraction sizes
are 439 and 432 bits respectively. Both legal-response gains are exactly zero;
the opponent's exact value is 400/21. These are equilibrium witnesses for this
fixed full-deck finite raised game, not for unrestricted Hold'em. Original tail
gaps remain positive and are preserved in the preceding audit.

Staged, published and saved verification passed without training. Separate Sol
review independently reconstructed every cleanup probability and non-probability
row/action identity, replayed complete physical policies, checked all 26 source
pins against Git, and matched all eight exact metrics through a separately
constructed chance projection. That review shares the generic Fraction
evaluator; the full numeric rules and handwritten anchors remain separate checks.
The accepted-report test binds the report hash, disables all production training
entry points, and passed in normal Python (9.010 seconds) and optimized Python
(9.134 seconds).

## Reproduction

The 13 integrated focused tests passed in normal Python (46.629 seconds) and
optimized Python (46.833 seconds), including complete real two-policy bundle
publication and replay under a later current HEAD with training disabled,
both read-only cleanup candidates, exact-zero rejection, strict
policy/certificate tampering, late drift and owned-file rollback.

Run `python -m unittest tests.test_build_raised_turn_witness -v` and repeat with
`python -O`. After source freeze, `python -m scripts.build_raised_turn_witness --generate`
creates the immutable bundle; `--verify` replays it without training.
Production/default behavior, preflop/flop and earlier proofs remain unchanged.

A later [independent full-physical exact replay](full-physical-audit-wrapper.md)
now checks both saved witnesses without chance grouping or the generic Fraction
certificate helper, with all eight exact metrics agreeing.
