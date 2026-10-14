# Bounded longer-budget matrix-free river accuracy

## Why this slice exists

The [earlier river extension](river-accuracy-extension.md) left the polarised
bluff-catcher fixture at `0.00790056594` NashConv after 10,000 CFR+ iterations,
above the predeclared 0.001-chip benchmark threshold. The separate
[same-run tail experiment](river-tail-realization.md) improved that gap to
`0.00687271407` while still missing. The isolated matrix-free river adapter
also imposed a 10,000-iteration hard ceiling even when its existing modeled
resource envelope could admit a longer request for this small game.

Sol designed a ceiling-only admission change; Luna implemented it and the
bounded tests/experiment. The isolated adapter now accepts exact integer
requests from 10 through 100,000, subject to every existing resource guard.
Its default, algorithms, averaging, stopping rules and ordinary serializer
remain the same. Shared postflop/materialized, turn, preflop/flop, ranked
terminal, training, Coach and UI source remain outside this slice. The
materialized solver's separate 10,000 ceiling is unchanged.

## Full requested admission

The same 30-million modeled hand/state/pass cap applies before information-row
allocation and training. It reserves the entire requested ceiling plus the
conservatively planned diagnostic checks, regardless of hoped-for early
stopping. In target mode the existing formula uses
`iterations // check_interval + 1`; when the ceiling divides evenly by the
interval, that intentionally overcounts one check. It is a conservative
admission charge, not the actual callback count.

For the polarised fixture, the maximum hand count is two and the public tree
has nine states. Fixed 100,000-iteration CFR+ therefore charges
`2*9*(100000*3+3) = 5,400,054`. With target checks every ten iterations it
charges `2*9*(100000*3+3*(100000//10+1)) = 5,940,054`. Both fit the unchanged
cap. A hypothetical ten-iteration early stop would charge only 648 under the
same formula. Tests use an intermediate cap to prove the full requested
ceiling controls admission before training. Many larger games still reject;
increasing the hard ceiling does not bypass their resource limits.

These counts describe the existing abstract vector-work model. They are not
elapsed-time, instruction-count, memory-allocation or resident-memory bounds.

## Predeclared experiment and interpretation

Use only the existing `river-polarised-bluffcatcher` fixture, unchanged from
the original quality specification: board `2c7d9hJsKd`, OOP `AsAh,3c4c`, IP
`QsQh`, pot and stack 100, one pot-sized wager, no extra all-in option. Run
matrix-free CFR+ for fixed 10,000, 30,000 and 100,000 completed sweeps. There
is no solver stopping target in these fixed runs. The separate 0.001-chip
NashConv threshold reports benchmark meets/misses; retain every result.

The 10,000 complete payload must exactly equal the previously published
matrix-free 10,000 policy, whose saved bytes are hash-checked against its
report. Every complete new profile passes independent physical-world,
numeric-rule and legal visible-information best-response replay across all
eight metrics and metadata/counts. Save full UTF-8 LF policies with byte
hashes, reload them and independently replay again.

A separate exact rational witness converts the learned binary64 probabilities
to Fractions and explicitly normalizes each row. It enumerates five terminal
histories and all 16/4 legal pure-policy responses, with the known 25-chip
game value inside the legal response interval. Record its exact normalized
NashConv and probability adjustment. This validates those explicitly
normalized witness profiles; it is not a formal interval proof of all raw
binary64 trainer diagnostics or an exact general Hold'em solution.

All relevant production, fixture, runner, oracle and archived baseline files
are fingerprinted before and after measurement. Timings are single complete
calls on a shared host. Additional sweeps change training cost; this is not
an equal-cost algorithm comparison, speedup, allocation or RSS claim.

## Executed results

| Completed CFR+ sweeps | Independent NashConv | Exploitability (NashConv/2) | 0.001 NashConv threshold | Modeled hand/state passes |
| ---: | ---: | ---: | :--- | ---: |
| 10,000 | 0.00790056593995 | 0.00395028296997 | Miss | 540,054 |
| 30,000 | 0.00265815977077 | 0.00132907988539 | Miss | 1,620,054 |
| 100,000 | 0.000907974712149 | 0.000453987356074 | Meets | 5,400,054 |

Every call completed its fixed request and passed independent replay. The
10,000 complete result exactly equals the archived hash-checked payload.
Maximum eight-metric disagreement is `1.0658141036401503e-14` chips. The
100,000 result meets the unchanged threshold; both earlier misses are kept.
The exactly normalized rational witnesses give the same meet/miss decisions
under an exact Fraction comparison with `1/1000`.

At 100,000 sweeps, the normalized witness has NashConv approximately
`0.0009079747121455163`; its response interval is approximately
`[24.999640477379614, 25.00054845209176]`, containing the known 25-chip value.
Exact fraction strings are saved, rather than treating these printed rounded
bounds as a formal raw-binary64 interval certificate. Maximum per-row
normalization adjustment across all three witnesses is `5.55130564670886e-17`.

All three complete policies, their hashes, all eight metrics, witnesses and
57 protected source/baseline fingerprints are retained in the
[long-budget report](../benchmarks/results/river-cfrplus-long-budget-v1.json)
and [policy folder](../benchmarks/results/river-cfrplus-long-budget-policies-v1).
The [runner](../scripts/benchmark_river_long_budget.py) writes LF policy bytes,
reloads and independently replays them before accepting the report. Sol also
reloaded every saved policy in a separate process, verified its raw byte hash,
replayed all eight metrics, recomputed the rational witness and checked every
protected source fingerprint. Single-call observations of approximately
6.51/19.20/58.74 seconds are retained as descriptive timing only.

All 41 focused matrix-free river, independent turn/river replay and saved
accuracy-replay tests passed in 19.334 seconds. A real 10,001-sweep run passes
independent replay and the known-value witness. Invalid ceilings/types reject
before kernel construction/training, and the independently calculated
100,000-request charge rejects under the intermediate cap before training or
diagnostics. Source review confirms information rows are allocated after this
admission guard.

The [ordinary parity harness](../scripts/validate_river_long_parity.py) loads
the fingerprinted old isolated river module from baseline `3ea3ea3`, requiring
all shared production source and fixture specifications to match that commit.
All 12 complete ordinary results exactly equal the old module across two
river fixtures, three algorithms and fixed/zero-target modes at 20 sweeps.
Each complete policy independently replays, with maximum metric disagreement
`1.4210854715202004e-14`. Every short-run 0.001 reporting threshold misses;
the configured stop settings are explicitly None/zero exploitability instead.
See the [complete parity report](../benchmarks/results/river-long-budget-ordinary-parity-v1.json).

Reproduction:

```text
python -m unittest tests.test_matrix_free_river tests.test_turn_river_independent_validation tests.test_replay_river_accuracy_extension
python -m scripts.benchmark_river_long_budget
python -m scripts.validate_river_long_parity --baseline-dir PATH --output benchmarks/results/river-long-budget-ordinary-parity-v1.json
python -m scripts.validate_docs
```

For parity, `PATH` contains a byte-preserving extraction of
`pokerlab/matrix_free_river.py` at the pinned baseline. The benchmark uses the
already committed archived report/policy. These finite synthetic results do
not establish quality on broader ranges, other bet trees or unrestricted
Hold'em. More iteration admission does not guarantee a requested accuracy.
