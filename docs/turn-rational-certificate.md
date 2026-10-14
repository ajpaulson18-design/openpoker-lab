# Exact arithmetic certificates for normalized turn policies

## Model and purpose

The [selected-turn accuracy experiment](turn-selected-accuracy.md) saved six
complete CFR+ policies for one finite conditional turn/river game. Its independent
replay rebuilds numeric betting rules, physical worlds and legal best responses,
but finishes EV and response sums in floating-point arithmetic. This development
audit evaluates an explicitly normalized version of each saved policy using
exact rational arithmetic throughout those sums.

The model remains the weighted, asymmetric-stack, raised game on `Js8d4c2h`,
conditioned jointly on selected rivers `3c,5h`, with distinct turn and river
sizings. It has eight physical worlds and 138 information sets. No training or
production algorithm changes are needed to audit the saved policies.

The arithmetic audit deliberately shares the existing independent numeric-rule
tree, physical-world construction and independent card ranks. It is a second
arithmetic check of that configured model, rather than an independently written
second betting-rules implementation. Payoff constants are exact rational images
of the numeric oracle's configured binary64 terminal constants. This does not
establish equivalence to arbitrary decimal sizing intent.

## Normalization and legal response bounds

Convert each admitted serialized probability to its exact binary64 Fraction.
For each complete information-set row, divide these values by their exact row
sum. Record every correction as an exact fraction, and hash the resulting
canonical complete normalized policy. The old validator still rejects invalid
metadata, missing rows, illegal actions, negative/nonfinite probabilities and
rows outside its admitted sum tolerance. The certificate applies to this
separately normalized legal policy. It is not an interval proof for the raw
floating-point row arithmetic used by the original solver.

World masses use exact input-weight products and one global physical-deal
normalizer. For a best response, group all compatible hidden worlds by the
responding player's own hand and visible history. Choose one action for that
entire information set. Integrate unrevealed river outcomes before optimizing
an earlier turn decision; observed river branches may have different later
responses. Opponent actions use their same visible-information normalized rows.
The responding player's original action probabilities do not restrict a best
response, including at rows the original policy never reaches.

Let `V` be OOP's exact value under both normalized policies, `U` OOP's exact
best response against normalized IP, and `L` OOP's value when IP best responds
against normalized OOP. Thus IP's own response value is `-L`. Exact arithmetic
must establish `L <= V <= U`, without negative-gain clipping. The two unilateral
gains are `U-V` and `V-L`, so NashConv is exactly `U-L`; exploitability is half
that gap. The finite zero-sum game's value is also between `L` and `U`: fixed
OOP secures at least `L`, while fixed IP limits OOP to at most `U`. A separately
known closed-form turn-game value is unnecessary for these supplied-policy
bounds.

Perfect recall and legal fixed-opponent response optimization are discussed in
[Koller, Megiddo and von Stengel, section 2](https://ai.stanford.edu/~koller/Papers/Koller%2Bal%3AGEB96.pdf).
This audit performs exact policy replay and response evaluation; it does not
implement that paper's sequence-form equilibrium solver.

## Provenance and resource limits

The public auditor accepts only the frozen selected-turn fixture and the six
reviewed saved policies. It checks a pinned canonical parent-report SHA256 and
six pinned raw policy SHA256 values before replay. A modified parent report
cannot redefine approved policy identities. Runtime source hashes are retained
before and after the audit, and changes fail the audit. These pins are provenance
checks anchored in the reviewed repository revision.
The archived comparison covers the relevant independent card/rule/rank and
fixture dependencies, allowing only path-separator and LF/CRLF checkout
representation differences. Unrelated production files are covered by strict
current-run before/after fingerprints; they are not permanently frozen to the
historical parent report.

The fixed model is checked before floating replay or model construction. The
exact core additionally preflights tree depth iteratively and counts recursive
node visits and scanned/copied world-group entries, including chance filters
and opponent reach propagation, plus charged Fraction arithmetic. Limits are
depth 64, 100,000 counted work units
and 65,536 bits per accepted Fraction numerator or denominator. Width checks
apply to input masses, probabilities, terminal constants, intermediate results,
partial sums and final metrics. Exhaustion rejects rather than approximates.
The width cap does not bound Fraction-library temporaries, gcd cost, elapsed
time, Python allocation or RSS; the work counter is not a CPU instruction count.
Generic synthetic tests exercise the exact core, not arbitrary poker-model
admission through the public auditor.

Each saved result must first pass unchanged independent floating replay and
`compare_result` for all eight serialized metrics. All eight exact witness float
views must separately agree with that replay within `1e-9` chips. Agreement is a
numerical cross-check; exact fraction inequalities and the rational `1/1000`
reporting threshold determine the normalized certificate. Keep every meet and
miss, with no threshold relabeling or inferred convergence theorem.

## Executed evidence

The [certificate artifact](../benchmarks/results/turn-rational-certificate-v1.json)
retains all six exact eight-metric profiles, lower/upper bounds, per-row exact
normalization ledgers, normalized-policy hashes, input-policy hashes, parent
report hash, all eight floating differences, work counters and 55 source
fingerprints. The arithmetic engine is
[turn_rational_certificate.py](../scripts/turn_rational_certificate.py); the
[public auditor](../scripts/audit_turn_rational_certificate.py) pins the approved
inputs before constructing the exact model. The baseline is merged main
`f0ce1e877b83fb9b96210bd5d35dcff6dcf2ab53`.

| Backend | Sweeps | Exact normalized NashConv, float view | Exact `1/1000` threshold |
| --- | ---: | ---: | --- |
| Materialized | 1,000 | 0.004234468380772026 | Miss |
| Materialized | 3,000 | 0.000470810046557014 | Meet |
| Materialized | 10,000 | 0.00004238279021250672 | Meet |
| Matrix-free | 1,000 | 0.004234468380772089 | Miss |
| Matrix-free | 3,000 | 0.00047081004655702104 | Meet |
| Matrix-free | 10,000 | 0.00004238279021250735 | Meet |

All four meets and two misses agree with the parent experiment. Exact integer
fraction comparisons determine these decisions; the table displays rounded
float views. The two 10,000-sweep certificates bound the configured game's value
at approximately `[-19.047634645102352, -19.04759226231214]` OOP chips. Exact
endpoints are retained in the artifact. These are supplied-policy response
bounds, not an assertion that either policy is an exact equilibrium.

The maximum absolute difference across all eight exact float views versus
independent floating replay is `1.4998202332860977e-14` chips, below the
predeclared `1e-9` gate. Maximum row adjustment is approximately
`1.1616093738752017e-16`; every adjustment is also recorded exactly. Each profile
uses 11,890 modeled work units, tree depth eight, and between 2,210 and 2,502
observed Fraction bits, under the fixed hard caps. Conservative copy reservations
may exceed actual copied entries; counters make no runtime or allocation claim.

All 32 focused tests passed after the final source freeze: five core tests,
three public-auditor tests, six separate Sol review tests and the existing
eighteen independent replay tests. Coverage includes a complete independently
validated one-bet value-25 profile with exhaustive 16/4 pure responses, a
nonuniform unrevealed-chance toy, hidden-opponent-hand toys for both players,
exact normalization corrections, resource exhaustion, and a separate correlated
hidden-hand game checked against every legal 4/16 response and a directly
written terminal-history equation. The review tests also reject an intermediate
fraction exceeding the cap even when the final EV would fit, reject wide trees
before child expansion, reject changed policy bytes/relabelled parent reports
before replay, and reject source changes during an otherwise completed audit.

Sol's separate process reconstructed every exact ledger and canonical normalized
policy hash from the six original policies without importing the exact core.
It verified all eight fraction identities, response inequalities, thresholds,
work sums/caps, all 55 raw source fingerprints and the nonempty common interval
across the six certificates. Review corrected policy-key and parent-digest
errors, strengthened precharges, and replaced two initial toy constructions
whose purported clairvoyance gaps were absent. The final adversarial fixtures
explicitly distinguish legal from peeking responses.

Reproduction:

```text
python -m unittest tests.test_turn_rational_certificate tests.test_audit_turn_rational_certificate tests.test_turn_rational_certificate_review tests.test_turn_river_independent_validation
python -m scripts.audit_turn_rational_certificate
python -m scripts.validate_docs
```

The auditor needs the pinned historical independent-model dependencies and six
policy files, and permits only line-ending representation differences when
checking those archived source identities. The report records the actual raw
source bytes of its measured checkout. No production, shared, preflop or flop
source changed in this slice, and no policy was retrained or overwritten.

This arithmetic audit preserves the selected-runout conditioning scope. Broader
full-deck turn accuracy, arbitrary ranges, a formal raw-binary64 interval proof,
and unrestricted Hold'em equilibrium claims remain separate work.
