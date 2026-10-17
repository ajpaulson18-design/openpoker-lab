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
Measurement results and the resulting engineering decision are pending.
