# Exact response bounds for normalized full-deck turn policies

## Scope and model

The [full-deck accuracy experiment](full-deck-turn-accuracy.md) saves six complete
CFR+ policies at 1,000, 1,500 and 3,000 sweeps on both existing backends. This
separate development audit evaluates those saved policies with exact rational
arithmetic. It performs no new training and changes no production solver,
earlier-street model, public API, stopping target or resource limit.

The configured model retains four compatible private pairs and all 44 legal
rivers for each pair: 176 globally weighted physical worlds, 48 reachable
public rivers, 580 public decisions, 1,305 total tree nodes and 1,112 private
information sets. Original joint card-removal conditioning remains intact.
Neither player may condition a turn decision on a future river or a hidden
opponent hand.

## Equivalent bounded chance partition

The existing exact helper scans a response's whole world group separately for
each river. On the pinned full44 1,000-sweep matrix-free policy, that default
path correctly rejects at its existing 100,000-unit work limit. Before rejection
it charged 22,968 scan units and 22,968 copy units for repeated chance filtering.
The rejection is retained; no partial certificate is treated as successful.

The optional `chance_grouping="partition"` mode replaces those filter passes
with one stable partition per chance invocation. For each river, the resulting
bucket contains exactly the original world/reach pair references in the same
order as the original filter. Every child is visited in original branch order,
including empty buckets. World masses are neither combined nor normalized.
The player decision nodes still maximize or minimize only after recursively
summing all public chance outcomes; opponent policy rows still depend on that
opponent's own hand and visible history.

Before any partition-map/list allocation or group iteration, the helper charges
`2*branches + 3*group_entries`: branch-map/bucket slots, scans, lookups and
retained entry references. The unchanged budget also charges tree, profile,
response, normalization and Fraction operations. Work remains capped at
100,000 units, recursion depth at 64 and accepted Fraction width at 65,536 bits.
These are modeled bookkeeping/arithmetic/reference counts, not Python byte,
CPU, allocation or RSS bounds. Independent model construction retains its
separate numeric-validator limits.

The default `chance_grouping="scan"` path retains its complete outputs and
counters. Sol captured all six selected-turn exact returns before this change
and compared every field afterward; each is unchanged. The partition path also
matches their exact metrics, normalization ledgers, normalized rows and model
counts. Production training and floating diagnostics use neither audit path.

## Meaning of the bounds

As in the [selected-turn exact audit](turn-rational-certificate.md), each stored
binary64 policy probability is converted to a Fraction and its row is explicitly
normalized. Exact evaluation uses the independent validator's original rational
global physical masses and binary64 terminal payoff constants. The complete
row-adjustment ledger and canonical normalized-policy hash identify the policy
actually audited.

For that normalized profile, write `V` for its OOP value, `U=BR_OOP` and
`L=-BR_IP` for the two legal response bounds. The audit checks exact
`L <= V <= U`, nonnegative unilateral gains, `NashConv=U-L` and
`exploitability=(U-L)/2`. The same configured zero-sum game value lies between
the legal response bounds. Exact width comparisons use `1/1000`, while the
unchanged floating replay checks all eight serialized metrics separately.

This is an exact-arithmetic audit of explicitly normalized saved policies under
the independent numeric rules. It is not an exact equilibrium computation,
a second poker-rules implementation, or a formal interval certificate for the
unmodified binary64 rows.

## Executed evidence

All six saved policies pass mandatory floating replay before exact evaluation.
Each exact run uses 82,950 modeled work units and depth eight. Maximum accepted
Fraction width ranges from 2,663 to 2,940 bits. The original hard caps remain
unchanged. There is no retraining or target-based early acceptance.

| Backend | Sweeps | Exact normalized NashConv, decimal view | Meets exact 1/1000 |
| --- | ---: | ---: | --- |
| Materialized | 1,000 | 0.0014533696435952712 | No |
| Materialized | 1,500 | 0.0006461572343943444 | Yes |
| Materialized | 3,000 | 0.0001615931370919545 | Yes |
| Matrix-free | 1,000 | 0.0014533696435952695 | No |
| Matrix-free | 1,500 | 0.0006461572343943436 | Yes |
| Matrix-free | 3,000 | 0.00016159313709195432 | Yes |

The report retains the actual fractions; the table shows floating decimal
views for readability. The four meets and two misses agree with the parent
accuracy experiment. The six legal-response intervals have nonempty
intersection, approximately `[-18.041228380742034, -18.04106678760494]` OOP
chips, with exact interval endpoints in the report. This intersection is a
bound for the shared configured game, not a closed-form equilibrium value.

Maximum exact-versus-independent-floating metric difference is 1.07e-14 chips.
Maximum serialized-versus-floating difference across all eight metrics is
2.84e-14 chips. Maximum policy-row adjustment is 1.46e-16. Sol's separate
artifact checker imports neither the exact helper nor the audit adapter: it
reconstructs all 6,672 normalization rows from original policy bytes, verifies
both ledger/normalized-policy hashes, eight Fraction identities and threshold
decisions, physical counts, resource dimensions, common interval and all 65
source/input fingerprints. All checks passed.

All 47 focused tests passed in 9.800 seconds, covering the old exact audit,
independent replay and new partition/audit/review tests. A separate 20-test
group passed with `python -O`. Sol's adversarial correlated hand/river game
independently enumerates four OOP and sixteen IP legal responses; future-aware
responses give strictly different values for both players. Additional tests
reject partial-budget allocation, invalid modes/cap overrides, an arithmetic
intermediate wider than the final answer, changed policy bytes, self-consistent
false certificate bounds and sources changed after all six rows pass.

The LF report is
[full-deck-turn-rational-certificate-v1.json](../benchmarks/results/full-deck-turn-rational-certificate-v1.json).
It includes raw-policy pins, exact metrics/intervals, every normalization ledger,
normalized-policy hashes, work counters, width limits and strict source/input
fingerprints. Reload verification independently repeats the floating replay and
full exact calculation and compares every saved row field. Parent policies and
reports are unchanged.

Reproduce with:

```text
python -m scripts.audit_full_deck_turn_rational
python -m unittest tests.test_turn_rational_partition tests.test_audit_full_deck_turn_rational tests.test_turn_rational_partition_review
python -m scripts.validate_docs
```
