# Preflop CFR+ nonnegative normalization probe

This experiment tests one preflop-local hypothesis: CFR+ regret rows are initialized at zero and every update clamps them with `max(0, old + delta)`, so the adapter may normalize those rows by summing the already nonnegative values directly. The prototype changes only the strategy alias used by the preflop delayed-CFR+ adapter. Shared CFR, public traversal, postflop, turn, river, and Coach code remain outside its scope.

## Frozen experiment

- Source revision: `5b5159e0805b5e4a3fafe59d5eb750bba8ae2e8f`
- Python/platform: `Python 3.12.14 on Windows 10 (10.0.19045)`
- Source/specification hashes: `71` verified hashes; see the raw report.
- Fixture: the weighted 10-chip, three-combo-per-player, two-flop game from `preflop-weighted-range-coverage-v1.json`, with 27,720 compatible physical worlds and forced checkdown after flop betting.
- Timed work: three alternating baseline/candidate pairs, each at 500 iterations and averaging delay 250. Timing includes one complete `solve_preflop` call and JSON serialization; options and runouts are prepared before timing, and GC runs before each arm.
- Separate allocation check: one 10-iteration, delay-5 call per arm under `tracemalloc`. This reports Python-traced peak allocations, not RSS or high-iteration memory.

The candidate normalizer is first checked against the shared strategy on uniform, singleton, sparse, ordinary, scaled, and subnormal nonnegative rows. Negative inputs are outside the CFR+ invariant. The comparison requires exact equality of the full serialized output across all six timed arms, and separately between the two allocation arms. The different iteration ceilings are not compared against each other.

## Independent checks and gates

Every arm is checked against the existing independent replay over original physical worlds, including legal visible-information best responses. The replay reports NashConv against the frozen `0.005` target with `1e-10` padding and checks all `728` information sets. Joint private-pair posteriors are compared to the rational blocker audit. The maximum replay metric difference across the six timed arms was `0.0`; the separate 10-iteration allocation arm differed by at most `1.1102230246251565e-16`; the maximum posterior differences were `0.0` for solver output and `1.021405182655144e-14` for the replay, against a `1e-12` tolerance. Per-arm target misses remain in the report.

Promotion requires all of the following: exact full-payload parity, target success in every timed arm, a faster candidate in all three pairs, median timing reduction of at least 5%, exact allocation-arm payload parity, and a separate candidate traced peak no greater than 1.01 times the baseline peak. The traced-peak rule is a nonregression gate only; it does not establish a general memory gain. The observed peaks were 12,474,692 bytes for baseline and 12,474,652 bytes for candidate, a 40-byte difference that is not evidence of a memory improvement. Measured paired reductions are `6.218348%, -8.165972%, 22.550057%`, median `6.218348%`; the gate result is **false**: the second candidate arm took 13.9793023 seconds versus 12.9239372 seconds for baseline, violating the requirement that the candidate win every pair.

The existing vector-work budget remains unchanged: 49,064,575 modeled loop entries at 500 iterations and 2,366,595 at the separate 10-iteration allocation check, both under the existing 500,000,000 limit. The candidate removes a clamp pass and temporary positive-regret list while preserving the normalization output for nonnegative rows. The existing row-work envelope therefore remains conservative; no budget or admission limit is reduced. Any later integration would still require exact policy checks and a separate review of loop/allocation accounting.

## Interpretation and limits

The candidate was not promoted. Serialized output was exactly identical across all six timing arms and separately across both allocation arms, and all six timed runs met the replay target. However, one paired run was slower, so the preregistered promotion gate failed despite a 6.218348% median reduction. The separate 10-iteration allocation run missed the 0.005 quality target at NashConv 0.42379217181374507 for both arms. This is a finite conditioned heads-up game with weighted exact ranges, two selected flops, and forced flop checkdown. It is not full-deck preflop, all-streets, broad-range, multiway, unrestricted no-limit Hold'em, or a universal convergence result.

The experiment is research-only. A passing gate would support considering an adapter-local change; it would not establish a general speedup or justify edits to shared solver kernels. A failed gate remains useful negative evidence.

## Provenance and reproduction

The prior profile revision `62b6e9d0123456cdf73dfac9f59f866860ddba58` is an ancestor of the frozen probe revision, and every source hash in that prior profile manifest was rechecked against the frozen files. The probe also hashes its complete imported source set, the weighted fixture and prior report, its own script, and its specification; all hashes are recorded in `benchmarks/results/preflop-nonnegative-normalization-v1.json`.

After checking out the frozen revision with a clean worktree, reproduce with:

```powershell
python -m scripts.benchmark_preflop_nonnegative_normalization
```

The harness saves the report before exiting with status 1 when a promotion gate fails. That is the expected result for this frozen experiment; it is not a request to rerun or adopt the candidate.

The raw report is [benchmarks/results/preflop-nonnegative-normalization-v1.json](../benchmarks/results/preflop-nonnegative-normalization-v1.json); the frozen specification is [benchmarks/preflop-nonnegative-normalization-v1.json](../benchmarks/preflop-nonnegative-normalization-v1.json).
