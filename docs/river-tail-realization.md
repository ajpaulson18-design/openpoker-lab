# Research: same-run river CFR+ tail realization

## Problem and fixed experiment

The [longer-budget river extension](river-accuracy-extension.md) left the
polarised bluff-catcher above the unchanged 0.001-chip NashConv target at
10,000 CFR+ sweeps. Sol specified a research-only conversion of a full average
and an earlier prefix from the **same training trajectory** into an average
over later sweeps. Luna implemented the pure conversion and exact proof tests.
After Luna reached its account usage limit, Sol implemented the observational
capture harness and its tests; no replacement worker/model was substituted.

The experiment was fixed before the poker runs: the two existing complete
river fixtures, both existing backends, discard checkpoint **D=3,000** and
full ceiling **T=10,000**. All four tail candidates and all prefix/full policies
are retained. No production solver, shared trainer, resource guard,
preflop/flop implementation, public API, UI or Coach changes are included.

## Derivation and preconditions

The current trainer averages completed CFR+ sweeps with weight `t`, using only
the acting player's own reach and fixed private-hand marginal. For a fixed
perfect-recall information set that marginal cancels in row normalization.
Let `W(n)=n(n+1)/2`. Multiplying only that player's ancestral conditional
probabilities reconstructs its average realization flow `R(n,s)`. Then

```text
R(n,s) = sum(t * r(t,s), t=1..n) / W(n)
R_tail(s) = (W(T)*R(T,s) - W(D)*R(D,s)) / (W(T)-W(D))
tail_probability(a | s) = R_tail(s.a) / R_tail(s)
```

Chance and opponent-action probabilities do not multiply that player's own
reach; keep private hands and visible histories separate. This is the
original-weight tail with weights `t` over **3,001 through 10,000**, not the
published delayed-weight convention `max(t-D,0)`. Subtracting normalized
conditional rows directly is incorrect. A zero-own-tail-reach row uses the
full snapshot's legal fallback; its policy cannot affect that player's
realization plan along the zero own sequence.

This deduction relies on perfect recall, identical legal tree/action metadata,
and same-run snapshots. The conceptual own-reach aggregation cross-check is
[OpenSpiel's policy aggregator](https://github.com/google-deepmind/open_spiel/blob/master/open_spiel/python/algorithms/policy_aggregator.py).
No external implementation was copied. The independent exact toy proof below
is the acceptance evidence for this subtraction, rather than an inference
that all averaging methods improve convergence.

## Exact proof, numerical limits and capture evidence

[The pure helper](../scripts/river_tail_realization.py) interprets each float
as its exact binary64 Fraction, exactly normalizes its row, reconstructs own
ancestor flows from exact action history keys, and performs exact subtraction.
Complete independent poker legality replay is an explicit caller precondition;
the helper validates matching row/action identity rather than implementing
another poker tree. It rejects bool/nonfinite/out-of-range probabilities,
row-sum errors above 1e-12, changed metadata/order, duplicate/missing rows,
wrong ancestor action tokens and invalid checkpoint integers/bounds.

The predeclared negative-realization tolerance is **1e-12**, with an overall
reconstructed parent/child flow discrepancy gate of **1e-11**. Materially
invalid flow rejects. Positive parent flows are retained even when very small.
Tiny negative children may be projected to zero with surviving mass normalized;
zero or tolerated negative parents require tiny child flows and a documented
legal fallback. Every changed/fallback row records raw flows, the local
adjustment and actual reconstructed output flow discrepancies. Global totals
separately count raw negatives, positive-parent projections and fallback
negatives. These are experimental numerical gates, not a formal error bound
for the original floating-point trainer or a general tail-equivalence proof
after serialized rounding. Actual serialized float profiles receive separate
independent game replay and legal BR evaluation.

Eleven [pure-helper tests](../tests/test_river_tail_realization.py) derive
averaged snapshots directly from explicit rational iteration flows in an
independent toy tree. They verify every reachable final-sweep row, two own
decisions separated by opponent/chance branches, unequal private-hand mass
invariance, zero-tail fallback, float round-trip and negative correction ledgers.
The conditional-row counterexample recovers exactly `7/10`; naive row subtraction
and including opponent/chance reach produce different answers. Adversarial
tests cover the rejection conditions above. Sol also compared every output
probability in four historical saved-policy pairs with a separate feasibility
reference; this preliminary comparison was not same-run acceptance evidence.

[The capture harness](../scripts/benchmark_river_tail.py) temporarily wraps each
solver module's existing imported trainer with an observational callback.
It copies D/T snapshots and always returns false, leaving updates unchanged.
Callbacks occur at 3,000 / 6,000 / 9,000 / 10,000; only D and T are retained.
Hand-index mapping follows `expand_range` insertion order, with per-row
player/hand/history and action-count checks. Every T callback probability must
exactly match the returned solver result. Complete T results and complete D
strategy rows must also exactly match the byte-hash-checked historical baselines.

Six [capture tests](../tests/test_river_tail_capture.py) exercise both backends
and both fixtures at cheap 20-sweep ceilings. They verify complete unwrapped
payload parity, off-interval callbacks at 7/14/20, independent prefix replay,
nonlexical hand-index identity, nonalias snapshot copies, invalid/target-mode
rejection and function restoration after success, callback error and trainer
error. The combined 17 tests passed in 0.693 seconds. The full research call
still admits/trains T=10,000 sweeps; averaging 7,000 later sweeps is no claim
of a 7,000-sweep solve. Prefix/tail policies have explicit research versions
and independent-derived diagnostic provenance, rather than production labels.

## Recorded experiment

The [source-frozen report](../benchmarks/results/river-cfrplus-tail-realization-v1.json)
and saved policy directory preserve all twelve complete prefix/full/tail
profiles, byte hashes, exact Fraction correction ledgers, independent metrics,
target outcomes, raw timings and source/baseline fingerprints. Source calls
were frozen at implementation commit `af5da71`; source-byte hashes include the
actual checkout line endings and differ from Git's canonical blob hashes.

All four tails pass the predeclared legality/correction gates and improve their
measured gap. Rounded NashConv below applies to both backends; exact binary64
differences are retained in the report.

| Fixture | Prefix through 3,000 | Full through 10,000 | Original-weight tail 3,001..10,000 |
| --- | ---: | ---: | ---: |
| Polarised bluff-catcher | 0.0182906265 | 0.00790056594 | 0.00687271407 |
| Weighted raises | 0.000848854325 | 0.000279553443 | 0.000223234524 |

Both weighted-raise tails meet the unchanged 0.001-chip target, which their
prefix/full profiles already met. Both bluff-catcher tails still miss. Across
all twelve recorded profiles, six meet and six miss. No case was discarded.
Full complete payloads and prefix strategy rows exactly match the historical
baselines; every final snapshot exactly matches the unchanged production return.

Raw negative child counts are 2/2/29/12 and zero-or-tolerated-negative parent
fallback counts are 1/1/5/2 (bluff-catcher materialized/matrix-free, then weighted
raises materialized/matrix-free). The largest negative child magnitude is
2.63e-20; the largest final reconstructed-flow discrepancy is **3.39e-20**.
All local and propagated discrepancies are retained as exact Fraction strings.
The largest prefix/full per-probability normalization adjustment is 9.59e-17.
These small observed numbers do not replace the stated admission/rejection gates.

The [separate saved-policy audit](../benchmarks/results/river-cfrplus-tail-hardened-replay-v1.json)
byte-checks and independently replays every profile with all eight metrics and
physical counts, then adds six exact normalized one-bet witnesses. Maximum
scalar disagreement is **1.7763568394002505e-14 chips**, attributable to full
production diagnostics; derived prefix/tail metrics are explicitly labelled.
Every exact one-bet BR interval contains the known game value 25, and all six
witnesses miss the unchanged target. Their maximum exact-normalization
probability adjustment is 8.33e-17. The general raised-game replay is binary64;
the witnesses certify only their explicitly normalized one-bet profiles.

The 69 recorded fingerprints cover the relevant sources/configuration and
frozen baseline report/policies. The combined focused unit suite (conversion,
capture, original witness and complete turn/river replay) passed **40 tests in
7.445 seconds**. The actual four complete calls, including observational
snapshots, took 2.359 / 7.365 / 14.244 / 57.073 seconds respectively on this host.
No runtime, memory or general convergence claim follows from four finite-game
candidates. Capture/full-call, conversion and independent replay time are
recorded separately as single shared-host observations; allocation/RSS was
not measured. This remains research-only even if every legality/correction
gate passes or a tail improves the measured gap.

## Reproduction

```text
python -m unittest tests.test_river_tail_realization tests.test_river_tail_capture
python -m scripts.benchmark_river_tail --output work/river-tail.json --policies-dir work/river-tail-policies
python -m scripts.replay_river_accuracy_extension --report work/river-tail.json --policies-dir work/river-tail-policies --output work/river-tail-audit.json
python -m scripts.validate_docs
```

Audit the committed profiles without training again:

```text
python -m scripts.replay_river_accuracy_extension --report benchmarks/results/river-cfrplus-tail-realization-v1.json --policies-dir benchmarks/results/river-cfrplus-tail-policies-v1 --output work/river-tail-audit.json
```

The shared audit verifies policy bytes before hardened complete replay and
adds exact normalized rational witnesses for the six one-bet profiles. Prefix
and tail scalar diagnostics originate in the independent replay; their scalar
agreement is a serialization/consistency check, not a separate production
diagnostic implementation. The exact one-bet witnesses provide a separate
terminal-history/pure-response calculation with the scope stated in the
[original witness documentation](river-accuracy-extension.md).
