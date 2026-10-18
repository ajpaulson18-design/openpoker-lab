# Production turn CFR+ against an exact two-street value

This development audit checks six complete production policies against the
[weighted turn game's proved value 30](turn-weighted-sequence-equilibrium.md).
All legal-response intervals contain 30. Both backends miss the fixed
0.001-chip NashConv target at 1,000 and 3,000 iterations and meet it at 10,000.
The finite-iteration policies are approximations; the separate analytical/LP
witnesses establish the exact game value.

## Fixed experiment

The board, weighted private ranges, selected rivers and both street configs
are the frozen [fixture](../scripts/turn_weighted_sequence_fixture.py).
There are four globally conditioned worlds and 42 own-hand/public-history
rows. River payoffs carry turn wagers and unknown future cards cannot affect
turn choices. The predeclared grid is CFR+ at exactly 1,000, 3,000 and 10,000
iterations for materialized/public-batched training and diagnostics, and the
matrix-free turn solver. Every call completes its full requested budget.
No threshold or budget was changed after observing a result.

| Backend | Iterations | Exact normalized NC, float view | NC <= 0.001 | Solve + JSON seconds |
| --- | ---: | ---: | --- | ---: |
| materialized | 1000 | 0.00455323067102346 | Miss | 1.55894 |
| materialized | 3000 | 0.003388416673667847 | Miss | 5.68961 |
| materialized | 10000 | 0.0006806589003607314 | Meet | 17.45096 |
| matrix-free | 1000 | 0.004553230671048473 | Miss | 7.95313 |
| matrix-free | 3000 | 0.00338841667369852 | Miss | 24.35620 |
| matrix-free | 10000 | 0.000680658900359239 | Meet | 95.39234 |

Exact integer comparisons with 1/1000 determine target outcomes; the table
shows rounded float views of the retained fractions. Single-call timings
were observed on shared Windows 10/Python 3.12.14. Separate float-plus-exact
replay observations range from 0.0399 to 0.0599 seconds. These measurements
do not establish general speed, memory or RSS improvements.

Both longest-budget intervals are approximately
[29.99992164849574, 30.00060230739611]. Their exact endpoints remain in the
report. Maximum absolute difference between any of the eight normalized
exact metric float views and independent numeric replay is
1.4210854715202004e-14 chips, below the predeclared 1e-9 gate.
Agreement of these scalar diagnostics does not imply identical policies.

## Saved mathematical evidence

The [generator/replayer](../scripts/turn_weighted_profiles.py) first validates
complete original serialized policies with independent numeric rules and
checks all eight supplied metrics. The exact core then converts the saved
binary64 probabilities to Fractions and explicitly normalizes each row.
The report retains every input row sum, exact adjustment, normalized row,
eight-metric certificate and exact response interval. This exact certificate
applies to the normalized policy and configured binary64 terminal constants.
The original binary64 diagnostics remain separately replayed.

Each certificate uses 2,236 modeled work units, depth eight and at most
1,161 accepted Fraction bits. Caps remain 100,000 work, depth 64 and 65,536
bits. Logical counts do not bound CPU, library temporaries or allocations.

The separate [independent checker](../scripts/verify_turn_weighted_profiles_independent.py)
imports neither trainer, LP search nor the exact-policy evaluator. It freshly
rebuilds the physical model and hand-written value-30 reference, normalizes
all six original policies itself, recurses profile EV and both legal responses,
and reconstructs all eight Fractions, every normalization ledger/row and target
decision. It checks fixed policy paths/hashes, input bytes, current proof sources,
its own source bytes and HEAD before/after. Its tests still reconstruct every
profile when the exact-policy evaluator is disabled.

The [report](../benchmarks/results/turn-weighted-cfrplus-profiles-v1.json)
has 549,785 bytes, SHA256
106723429204401b0af99114c3a0b9b4d094d91db58331ee687c67a5eec7e372.
It retains 72 generation input/source fingerprints, Python/platform and the
verified main baseline f6ba5f3e52dfa4038f7e4aea4fba1b2da1cc46ce.
Each complete policy has its own byte count and SHA256:

- [materialized 1000](../benchmarks/results/turn-weighted-cfrplus-policies-v1/turn-weighted-materialized-1000.json)
- [materialized 3000](../benchmarks/results/turn-weighted-cfrplus-policies-v1/turn-weighted-materialized-3000.json)
- [materialized 10000](../benchmarks/results/turn-weighted-cfrplus-policies-v1/turn-weighted-materialized-10000.json)
- [matrix-free 1000](../benchmarks/results/turn-weighted-cfrplus-policies-v1/turn-weighted-matrix-free-1000.json)
- [matrix-free 3000](../benchmarks/results/turn-weighted-cfrplus-policies-v1/turn-weighted-matrix-free-3000.json)
- [matrix-free 10000](../benchmarks/results/turn-weighted-cfrplus-policies-v1/turn-weighted-matrix-free-10000.json)

Saved verification never trains. It recomputes complete rows, metadata,
normalization and target decisions, enforces 2 MB report/1 MB policy input
admission, and rejects source/HEAD/input drift. The generator refuses differing
existing policy bytes; report publication stages verification and restores
previous bytes after later rejection. Historical training inventory is recorded
as context; current mathematical proof inputs remain pins, with only Python
LF/CRLF representation tolerance. The generator and saved-policy auditor also guard the current training
inventory before/after each call.

## Executed validation and reproduction

The twelve primary adversarial tests passed in normal Python (26.766s) and
optimized Python (30.363s). Four additional independent reconstruction tests
passed normally (1.269s) and optimized (1.323s). Positive complete proofs run
before mutation tests. Coverage includes the full six-profile grid, source
pins, every threshold miss, normalization/false metrics, policy identity and
input changes, report/policy limits, no-training verification, source/HEAD drift,
and rollback preserving the prior report and preexisting policy files.

    python -m scripts.turn_weighted_profiles
    python -m scripts.turn_weighted_profiles --verify
    python -m scripts.verify_turn_weighted_profiles_independent
    python -m unittest tests.test_turn_weighted_profiles tests.test_turn_weighted_profiles_independent -v
    python -O -m unittest tests.test_turn_weighted_profiles tests.test_turn_weighted_profiles_independent -v
    python -m scripts.validate_docs

Luna implemented the bounded producer/replayer and primary tests. Sol corrected
census, source inventory and test assumptions, executed measurements, and wrote
and ran the separate arithmetic checker. Production implementations, earlier
streets, previous witnesses and policies remain unchanged. The next research
priority is a turn reference with blocker-correlated hidden hands on both sides,
retaining any resource admission failures and checking compact LP algebra
without increasing the existing caps.
