# Monetary rules in independent preflop replay

The preflop verifier now independently reconstructs the solver's configured
monetary model, including its rounding order. Production betting trees,
trainers, values, best responses and AI Coach behavior are unchanged.

`replay_policy(..., monetary_mode="configured")` is the default. Before the
flop it tracks whole-hand contributions. At the first flop it records the
matched preflop contribution as a fixed origin, a starting postflop pot twice
that origin, cleaned remaining stacks and local contributions initially zero.
The same local ledger carries through turn and river; it is not reset every
street. Binary64 sizing uses the full configured coefficients, canonical
sorted/deduplicated sizes and the configured `1e-9` comparison tolerance.
Actions are quantized to nine decimal places locally before their targets
are translated to whole-hand history and settlement amounts.

Configured replay requires **exact equality** for each serialized amount and
raise-to target, plus exact action names and history tokens. It still checks
all structurally reachable rows, including zero-probability branches, and
derives values and legal best responses while grouping hidden worlds by the
responding player's own hand and revealed history. It never reads the
production tree, ranker, utilities, training, evaluation or best-response
helpers. Only the established card/range input parser is shared.

## Why the recorded boundary differed

The [original fixture](../benchmarks/preflop-rounding-boundary-v1.json) records
matched preflop contributions `M=0.691357802`, initial postflop pot
`P=1.382715604` and a rounded local flop bet `b=0.170705629`. The exact
quarter-pot raise target after calling is:

```text
local: b + 0.25 * (P + 2*b) = 0.6017373445
whole hand before quantization: M + local = 1.2930951465
```

The configured local binary64 arithmetic evaluates just below its midpoint:
`0.60173734449999993767477235451224260032176971435546875`. It rounds locally
to `0.601737344`, then adds the preflop origin, producing the serialized
`raise@1.293095146`. The old checker accumulated a Fraction-backed global
target and converted that midpoint to binary64 before rounding, producing
`raise@1.293095147`. The sizing formula was algebraically the same; the
quantization order and intermediate representation differed.

The historical model remains explicitly available as
`monetary_mode="global-rational"`. It retains the old Fraction/global-state
calculation, including binary64 conversion during nine-decimal cleanup and
the old scalar-field tolerance. It is a separate diagnostic, **not an exact
decimal quantizer or a replacement for configured validation**. The original
fixture still fails that diagnostic at the specifically recorded token. The
repair does not assert universal equivalence between the configured game and
an exact-decimal poker model.

## Frozen verification evidence

```text
python -m unittest tests.test_preflop_monetary_replay tests.test_preflop_validation
python -m scripts.preflop_monetary_validation
```

The [specification](../benchmarks/preflop-monetary-replay-v1.json) covers the
recorded boundary, sizing coefficients with more than nine decimals, and an
independently known hidden-flop root response. Each uses six routes: recursive
vanilla, planned DCFR, recursive CFR+, and public-batched
vanilla/DCFR/CFR+. The
[report](../benchmarks/results/preflop-monetary-replay-v1.json) records all
18 configured checkpoints passing at source
`450e78e51362cecfe59a3f147526cf6d56b25b17`, Windows/Python 3.12.14, with a
clean measured worktree and source/configuration hashes. The two fractional
games each check 640 information sets per route. Maximum candidate/oracle
scalar difference was `1.67e-16` chips, with independently checked joint
private-pair probabilities and agreement between backends of the same method.
The report observed rejection of both fractional fixtures and acceptance of
the known dyadic hidden-flop fixture on all six routes. Rejection at the
original stored boundary and acceptance at the known root are explicit
diagnostic gates; the full-precision fixture's historical outcome is recorded
without making rejection a success requirement. Configured verification is
required for every checkpoint.

The new regression tests also independently hand-check the recorded targets,
retain one postflop origin through later streets, check full-precision size
coefficients and unsorted duplicates, and reject separate one-nanounit
mutations of an amount, raise-to field or history token. Existing rational
anchors for blockers, blind refunds and hidden-card best responses remain.

These ten-iteration checks certify replay consistency for the listed finite
conditioned games. They do not certify convergence to equilibrium: the
fractional fixtures still have substantial best-response gaps. No runtime or
memory comparison was measured in this correctness milestone. Earlier
benchmark reports retain their frozen source revisions and original checker
semantics; this report adds the stricter configured monetary validation.

The independent rules and tests were authored in this repository by Luna,
with lead numerical review, midpoint analysis and publication validation.
No production numeric helpers, third-party source, dependencies, commercial
policies or proprietary outputs were incorporated into the checker.
