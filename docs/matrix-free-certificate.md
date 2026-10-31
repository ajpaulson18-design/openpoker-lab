# Independent matrix-free saved-policy certificate

Status: integrated research candidate, not yet accepted on the retained larger
policies. Forty-three development controls pass normally and with assertions
disabled (11.382 / 11.868 seconds), with stable source pins. The old literal
certificate and all its limits remain unchanged. No training or product route
selects this verifier automatically.

The [fold-class result](native-fold-classes-result.md) contains 28 completed
solver policies: 22 have old exact certificates, while six larger-range policies
remain exact-quality unknown. These six are both V4/V5 arms of unit 4×4, 8×8 and
2×16 T10. They are distinct from six native-rejected requests, which have no
policy to verify. Existing 4×4/8×8/2×16 payloads describe 88/368/176 physical
worlds and 2,400/4,912/5,596 rows. The old exact oracle's hand/world/row caps are
a demonstrated verification barrier; raising them is not this implementation.

## Representation and mathematical contract

Call `scripts.exact_selected_matrix_free_certificate.evaluate_exact(case, payload)`
with an inert complete compact policy for the selected-product four-street game.
It snapshots the inputs, independently rebuilds legal public betting/reveal
histories, validates every physically supported own-hand row/menu, normalizes
serialized binary64 policy rows as exact fractions and computes profile value
and both legal best responses. It imports no production tree, payoff, trainer or
ranker. Common card/range parsing and the independent numeric-rule/ranking
sources remain explicit dependencies.

For selected full boards S and positive binary64 priors wi/wj, the normalizer is
`Z = sum_B_in_S sum_compatible_i,j wi*wj`. Terminal vectors use exact blocker
buckets and rank sweeps, include the responder's prior once, and divide by this
one global Z. They sum all compatible still-hidden completions matching the
current ordered prefix; no street-local renormalization or extra branch mass
is applied. Early fold/all-in leaves retain hidden completions. Fold winner
and responder signs use original global SB/BB identity; matched money is the
existing independent configured binary64 snapshot before exact conversion.

Opponent reach begins at one and multiplies only that opponent's full-history
action probabilities. Profile evaluation mixes the responder's action values;
best response maximizes separately for each own hand after hidden outcomes have
been summed. A zero own-policy probability does not remove a legal deviation.
All physically supported rows are validated even behind zero-probability play;
only then can an all-zero opponent reach skip numeric propagation. An exact
negative response gain is rejected as an invariant violation, not clamped.

For example, equally likely hidden rivers where A pays +1/−1 and B pays −1/+1
have legal best response 0. Maximizing after privately inspecting each river
would incorrectly produce +1. A dedicated control preserves this boundary.

The public model carries full visible action/reveal histories and rule-state
money/reopening fields. A shared vertex is not substituted for information-set
identity. Flops canonicalize together in DECK order, turn/river remain ordered,
and holding names preserve the existing lexical tuple convention and range
insertion order.

## Storage and resource boundaries

There are no retained private-pair coefficient or complete-world arrays. The
public tree and complete serialized policy remain explicit. Range/board masks
and blocker buckets are linear in hands/selected boards; opponent mask classes
count union support without a pair table. The independent rank cache is bounded
by selected boards × individual hands, including bounded best-five scratch.
The true physical world/pair counts are diagnostics, not stored records.

| New research-path limit | Ceiling |
| --- | ---: |
| Hands per seat / selected full boards | 16 / 64 |
| Public occurrences / depth | 250,000 / 64 |
| Policy rows / action slots | 20,000 / 100,000 |
| Inert JSON nodes / depth | 2,000,000 / 40 |
| Each JSON text/encoded ASCII buffer | 64 MiB |
| Input field string / integer bits | 4,096 / 4,096 |
| Named logical work / cumulative logical entries | 500m / 8m |
| Fraction integer-width forecast | 65,536 bits |
| Cumulative Fraction operand/result bit forecast | 16,000,000,000 bits |

Limits are positive and reduce-only, specific to this new representation. They
do not alter the older literal oracle's limits. Cumulative entry/bit forecasts
are conservative logical construction/arithmetic ledgers, not observed live
heap, all CPython integer allocations, RSS or CPU instructions. Their practical
sufficiency on larger saved policies is not yet established; capacity failure
remains unknown quality.

Input JSON copying, character/key scans, sorted-key encoding, decimal Fraction
formatting, numeric conversion, public census and action/reveal helpers reserve
their declared work/storage before entering the operation. Rational operations
and comparisons check numerator/denominator growth before products. Fraction
output has a cumulative ASCII cap, independent of the input string cap. Work
counter metadata is bounded even for zero-work charges.

After bounded preparation and full policy validation, the verifier pre-admits
three complete public walks, all legal actions and end-of-call serialization.
The forecast separates two responder-0 walks and one responder-1 walk; it covers
reach products, own-hand action comparisons, opponent/chance sums, prefix scans,
all/lower/equal blocker buckets, per-board rank lookups/sorts, B×H cache misses,
vector/scratch references, metric fractions and repeated private-input hashes.
Actual named work families and cumulative entries must fit that forecast.
Width and cumulative Fraction-bit limits are still dynamic rejection gates.

## Executed development evidence and acceptance gates

The controls compare exact values, both best responses, all metric fractions,
normalized policy rows/hashes and unchanged thresholds against the untouched
literal v3 oracle. Cases include weighted hidden outcomes, blockers, fractional
money/local rounding, mixed-rank holdings, dead selected boards and blind all-in.
Other tests cover physical row completeness, unplayed legal deviations, forged
metadata, inert-input rejection, work/entry cap-minus-one before ranking/walks,
and pre-encoding/pre-decimal budget rejection. Terra independently challenged
the recurrence and the family forecast; source inspection is distinguished from
executed numerical evidence. Root substitutes for unavailable Sol architecture;
Luna owns public-rule integration and the saved runner, Terra the payoff/budget
and independent scalar review.

Development review corrected serialization and pre-helper reservation gaps,
and preserved the legacy holding/money conventions. A worker reported an initial
Fraction-versus-float money-type parity failure; it was corrected and final tests
pass, but that first tool output was not retained as a separate raw log. No
formal saved-policy result is claimed from this development history.

Next gates are a clean committed-source freeze, an immutable saved-only pass
over all 28 completed fold-study policies, comparison with all 22 earlier exact
certificates, and independent literal streaming response checks for the six
formerly unverified policies. The runner must authenticate both current and
producer source closures and every input artifact before mathematics, preserve
new errors/unknowns and all earlier receipts, and make zero solver/native calls.
It must not retrain a policy because verification changed.

Full-deck chance/reach/training, larger public-game/strategy storage, convergence
and commercial accuracy remain separate unresolved foundation requirements.
