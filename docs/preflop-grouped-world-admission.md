# Bounded higher-iteration admission for grouped flop-checkdown solves

`solve_preflop(..., world_admission="grouped-vector", ...)` is an explicit alternative to the legacy world-count times requested-iterations admission proxy. It requires `postflop_scope="flop-checkdown"`, `future_indexing="flop-sign"`, positive-delay CFR+, public-batched training and exact diagnostics, and the public-vector resource model. Invalid modes/dependencies reject before enumeration. The default `world_admission="world-iterations"` retains the previous guard, numerical path and payload.

This option changes admission only. It does not remove physical outcomes, change actions/payoffs, sample chance, reduce the requested training ceiling or weaken an accuracy target. Enumeration, ranking, normalization and tree construction do not repeat once per training sweep; vector training already has a separate requested-iteration work envelope. The legacy proxy was preventing longer runs of a game whose actual vector envelope remained well below its own ceiling.

The new construction charge is `physical_worlds * 10 <= 3,000,000`, so at most **300,000 physical worlds** can be materialized. Ten is the minimum legal solver iteration count: this preserves the largest physical construction previously admissible at that count. Compatible-world counts are checked in the existing preflight before the raw world list, rank cache or normalized copy is allocated. This is a count bound, not a memory-byte or RSS guarantee. The legacy `candidate_private_pairs * requested_iterations <= 3,000,000` guard still uses the full requested ceiling.

Only the opted-in worlds-times-requested-iterations proxy is replaced. Selected outcomes, pair/runout preflight checks, tree/template/public states, prefix edges, dense dimensions, information/action slots, grouping references/work and compact-copy limits remain enforced. The original-world vector estimator still sees the **full requested iteration ceiling**, original world rows and every possible convergence snapshot/diagnostic. Its complete envelope plus grouping construction must pass the unchanged 500,000,000 modeled-loop cap **before** grouping, compact copies, vector views or training. Early stopping cannot bypass this admission. Original worlds remain authoritative for selected/reachable outcomes, private-pair priors and result counts.

The result names `world_admission="grouped-vector"`, `world_construction_admission_iterations=10`, and version `preflop-public-vector-grouped-world-budget-v6` with its v5 reference. `limits.world_iterations` is **null**, because the legacy requested-iteration proxy is not enforced in this mode; `reference_world_iterations` preserves 3,000,000 and `constructed_worlds` reports 300,000. Candidate-pair iteration admission remains active. These fields distinguish replaced reference limits from enforced limits rather than silently raising a constant.

The [predeclared experiment](../benchmarks/preflop-grouped-world-admission-v1.json) extends the [richer flop matrix](preflop-flop-raise-coverage.md), whose six-chip 250/delay125 policy missed the 0.005-chip target. The same six-chip game keeps half-pot/pot flop bets, half-pot raises, one raise, all-in flop actions, the existing preflop opening model, two private hands per player, two flops, all 4,704 ordered future candidates and **11,880 compatible worlds**. Grouped training still has 16 rows; all future decisions remain forced checkdown.

Before any training, both admission modes were probed at all four fixed checkpoints. Legacy admission accepts 250 sweeps but rejects 500, 1,000 and 2,000 at the unchanged world-iteration guard. The new mode admits all four with a fixed physical construction charge of **118,800**, while full requested-iteration vector work increases with the training ceiling.

| Iterations / delay | Legacy world-product charge | Combined vector/grouping loop envelope | Independent NashConv | 0.005 target |
| ---: | ---: | ---: | ---: | --- |
| 250 / 125 | 2,970,000 — admitted | 4,698,667 | 0.0116322490163 | Miss |
| 500 / 250 | 5,940,000 — rejected | 8,813,667 | 0.00119957468674 | Met |
| 1,000 / 500 | 11,880,000 — rejected | 17,043,667 | 0.0000589253241483 | Met |
| 2,000 / 1,000 | 23,760,000 — rejected | 33,503,667 | 0.00000122078318121 | Met |

Every admitted policy and the legacy 250-sweep reference independently replay all original physical worlds using numeric poker rules, independent card ranks and exact legal visible-information best responses. Maximum production-versus-oracle scalar discrepancy is **3.34e-16**. The unchanged target is `NashConv + 1e-10 <= 0.005`; the 250-sweep miss remains visible. Both admission paths use grouped futures for the reference comparison: their **250-sweep serialized strategies, physical outputs and scalar diagnostics match exactly**. This confirms admission-only parity, not a new bitwise equivalence claim between grouped and ungrouped summation.

One descriptive complete-call-plus-JSON timing is recorded per opted-in checkpoint: **2.935, 3.356, 5.332 and 9.210 seconds**. Each includes original enumeration/ranking, trees, admission, grouping, training, exact diagnostics and serialization. Preallocated inputs, pre-call garbage collection and independent replay are outside timing. No prior parsed policy is retained; the 250 reference temporarily retains serialized strategy and physical/scalar fields for parity. There is no speedup comparison, statistical runtime claim, memory experiment or RSS guarantee in this slice.

The [raw report](../benchmarks/results/preflop-grouped-world-admission-v1.json) starts clean at source `b6589cca496b0476f5a6b61a2211b954127c638c`, records all 58 source/specification hashes, both sets of admissions, all target outcomes, replay results, full payload digests and explicit limit metadata. The [harness](../scripts/benchmark_preflop_grouped_world_admission.py) rechecks revision/hashes before saving; it does not simplify rejected cases or stop after the first target success.

Focused validation passed **31 tests**, including eight new admission cases: exact default/explicit-legacy parity, early eligibility validation, construction-cap boundary and one-over before ranking, requested-iteration candidate-pair charging, requested-ceiling vector rejection before copies despite an easy early-stop target, and independent compact/checkpoint replay. A separate case actually renumbers a globally blocked leading hand (`[2,2]` original dimensions to `[1,2]` compact), checking restored policy identities and checkpoint values. The full applicable suite and final-head CI must pass before merge.

Luna implemented/tested the bounded production option and reviewed the frozen harness/spec; lead reviewed the admission proof, strengthened actual-renumbering and public boundary regressions, and froze/measured the unchanged game. All implementation uses this repository's own standard-library code. No third-party source/dependencies, proprietary solver output, shared postflop/turn/river kernel or AI Coach changes.

These results show that this particular richer six-chip game reaches its stated target with more admitted sweeps. They do not establish broad-range/full-deck preflop, all-streets, multiway, unrestricted NLHE or general convergence accuracy. The separate turn/river workstream and earlier all-streets template rejection remain outside this milestone.

```text
python -m unittest tests.test_preflop_grouped_world_admission tests.test_preflop_future_indexing tests.test_preflop_future_groups tests.test_preflop_flop_checkdown tests.test_preflop_active_prefixes -v
python -m scripts.benchmark_preflop_grouped_world_admission
```
