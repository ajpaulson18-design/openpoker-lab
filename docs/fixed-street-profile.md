# Fixed-street prepared-call profiling

This measurement identifies where time is spent after physical equity counts
have already been prepared. It does not change a solver, action tree, admission
limit or default backend.

The frozen [specification](../benchmarks/fixed-street-profile-v1.json) selects two
existing games: the weighted three-pair [preflop pair-mean](preflop-pair-mean.md)
case at 3,000 CFR+ iterations, and the 58-compatible-pair, eight-hand-per-player
[fixed-flop](flop-equity-reuse.md) case at 4,000 CFR+ iterations. Both use pinned
Git artifacts containing independently enumerated physical win/tie/loss counts.
No ranking or board enumeration belongs in these profiling calls.

The [runner](../scripts/benchmark_fixed_street_profile.py) records one unwrapped
reference followed by three instrumented calls per case. A complete-call timer
includes the prepared solver and canonical JSON serialization to UTF-8 bytes plus payload hashing.
Coarse wrappers time the top-level trainer and diagnostics, returning the
original values and restoring references on every exit. Every instrumented
payload must equal the unwrapped reference. The flop diagnostic phase combines
profile evaluation and both own-hand best responses; it does not time them
separately. The remaining time includes setup, tree construction, formatting,
serialization and instrumentation overhead.

Independent policy replay runs outside the complete and phase timers. The
count-fed replay trusts the pinned counts but independently reconstructs legal
betting rules and visible-information best responses. Structural table checks
alone do not authenticate caller-supplied counts.

Formal measurement requires clean committed source. Run with Python 3.12:

```text
python -m scripts.benchmark_fixed_street_profile --output ../fixed-street-profile-v1.json
```

Record all observations, source/input identities and failures. Instrumented
phase fractions identify a bottleneck in these two cases; they do not establish
a native speedup, general performance, allocation savings or process RSS.
The [saved report](../benchmarks/results/fixed-street-profile-v1.json) was measured
on Python 3.12.14 from committed source `73e6636caae1989ca862a2d5c42480a41f7790c3`.
Its clean before/after revision, source hashes and status match. All eight
complete payloads pass their current-reference identity and independent replay
checks, with zero guarded ranking calls. The largest independent scalar gap
is 2.53e-16 chips. Raw samples, timestamps and policies remain in the artifact.

| Prepared game | Three complete instrumented calls, seconds | Median, seconds | Training fraction in each call |
| --- | --- | --- | --- |
| Preflop weighted three-pair pair-mean, 3k CFR+ | 2.575649, 2.408508, 2.581133 | 2.575649 | 99.9182%, 99.9280%, 99.9459% |
| Flop weighted eight-by-eight, 58 pairs, 4k CFR+ | 26.035567, 23.865632, 26.262805 | 26.035567 | 99.8931%, 99.8553%, 99.8482% |

These coarse measurements identify training as the next optimization target
for both fixtures. A separate explicit source-built native trainer is the next
engineering experiment; Python will retain game construction and diagnostics.
The experiment has not shipped and this report establishes no native speedup.

The artifact canonical SHA-256 is
`ecc20be10f163eb1b5e085b882ecba398f3e6493446d3c8bc713651f5ff74e78`.
The frozen specification canonical SHA-256 is
`8b905b854099cfb843e6479ce8ef1277e11e0c2af1ae31d39fd403da554f24b6`.
