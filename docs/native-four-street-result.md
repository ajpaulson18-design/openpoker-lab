# Native four-street CFR+ result

The source-frozen `native-four-street-v1` comparison completed on October 26,
2026 with six full T1000 calls, no errors/retries and unchanged source before
and after. Both backends trained the same 22-world, two-hand-per-player,
conditioned four-street game. Preparation, training, numeric diagnostics and
complete envelope serialization are included in each timed call. Independent
numeric replay is performed outside the timer for every returned policy.

| Repetition | Order | Python seconds | Native seconds | Maximum policy probability difference |
| --- | --- | --- | --- | --- |
| 1 | Python, native | 54.243413 | 0.814282 | 0 |
| 2 | Native, Python | 53.295125 | 0.638642 | 0 |
| 3 | Python, native | 54.846224 | 0.838863 | 0 |
| Median | | 54.243413 | 0.814282 | 0 |

The ratio of medians is **66.6150** on this fixture and local environment.
These are three observations per backend, with alternating order and all samples
retained. They establish this bounded complete-call comparison, not a universal
language ranking, larger-support speedup or general convergence rate. No RSS
or memory-saving measurement is claimed.

## Independent quality

All six numeric replays pass their 1e-10 metric tolerance. Every Python/native
pair has identical serialized policy probabilities across all 1,200 rows and
2,402 action slots. The first native raw policy was separately authenticated
and passed the unchanged independent rational whole-game certificate:

- Exact normalized NashConv approximately **0.000399738815144135 BB**, below
  the exact **1/1000 BB** target.
- All 1,200 physical own-hand/public-history rows, including off-path rows,
  checked with independent legal best responses and normalization ledger.
- 92,534 exact work entries under the unchanged 100,000 limit; maximum observed
  fraction width 22,456 bits under the existing limit.
- Saved certification performed zero production, native or training calls.

The full [rational certificate](../benchmarks/results/native-four-street-v1/first-native-exact-certificate.json)
retains exact fractions, normalized rows, ledgers and independent numeric
comparison. The original [Python quality evidence](four-street-integration-result.md)
is unchanged. This is still a finite selected-outcome heads-up game, not a
full-deck or unrestricted no-limit Hold'em result.

## Provenance and replay

Source freeze: commit
[`0985645ff222e0294961d137ee3589da89197171`](https://github.com/ajpaulson18-design/openpoker-lab/commit/0985645ff222e0294961d137ee3589da89197171).
The [report](../benchmarks/results/native-four-street-v1/report.json) and
[attempt receipt](../benchmarks/results/native-four-street-v1/attempt.json)
pin all Python sources under `pokerlab/` and `scripts/`, the C++ source, protocol,
manifest, compiler, flags and executable. Source hashes normalize CRLF to LF;
policy/report hashes cover exact bytes. All six complete policies and numeric
replays are retained beside the report.

Report SHA256:
`ccb7d22f65dcb6da9a6b007efdae0d997a284085e744541dd16052c048ae7877`.
Exact-certificate SHA256:
`fa5eacaa93b4bf8e217cc4ab84ab8c36915ce61990ce60c3ab7ec96a5507260b`.

The environment was Windows x64, CPython 3.12.14 and MSVC 19.44.35229 with C++20,
optimization and strict floating-point flags. The runtime selected compensated
float reductions. Native v2 admission counted 60,486,194 logical entries under
500 million and reserved 134,838,101 modeled bytes under 256 MiB. This includes
conservative parser reserve, not measured usage. Python guards separately apply.

With the frozen source closure present, replay without any executable:

```sh
python -m scripts.verify_native_four_street_sample --directory benchmarks/results/native-four-street-v1 --report-sha256 ccb7d22f65dcb6da9a6b007efdae0d997a284085e744541dd16052c048ae7877 --output /absolute/fresh-exact-replay.json
```

## Acceptance and remaining work

Twenty-four focused native/selection/benchmark/saved-authentication controls pass
normally and with assertions disabled; 53 existing interface, solver, traversal,
budget and diagnostic controls pass. Independent Sol source review accepted the
corrected recurrence and resource accounting. Linux compiled controls pass on
Python 3.11, 3.12 and 3.13, as does ASan/UBSan; final PR checks govern publication.

The [architecture decision](native-four-street-architecture.md) is implemented
for the repeated CFR+ computation. Python remains the prepared-game/API and
independent verification layer. Native game construction, other algorithms,
delayed/convergence modes, realistic support scaling, parallel execution and
actual process-memory comparisons remain separate work. A development T1000
native probe returned successfully before the frozen comparison but its payload
was not retained; it contributes no quality or timing evidence here.
