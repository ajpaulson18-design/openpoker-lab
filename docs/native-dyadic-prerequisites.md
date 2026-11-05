# Finite-grid policy and visible-prefix fold prerequisites

These explicit native components prepare the virtual four-street training path.
They do not activate a trainer or change existing solver defaults. The complete
frozen update and its independent saved-only acceptance remain required before
changing-policy training. The [exact reach boundary](native-exact-reach.md)
carries opponent sequence reach without a binary64 round trip.

## Policy representation

`native/dyadic_policy.hpp` allocates each legal row on the fixed grid
`n_a / 2^52`, with nonnegative units summing exactly to `2^52`. For current
policies it takes positive cumulative integer regrets. For exported averages
it takes nonnegative cumulative integer average masses; negative masses reject.
Each row must have one shared positive input scale and original legal-action
order. Different scales within a row are invalid caller input.

Allocation uses exact integer quotient and remainder, then assigns the remaining
units by largest remainder, breaking ties by earlier legal-action order. A
common power of two may cancel exactly. For positive total mass S, each unit
has `abs(n_a*S - w_a*2^52) < S`. A zero-total row has a separately tagged
deterministic near-uniform grid fallback; no raw-ratio error bound applies there.
Small positive weights may receive zero units. Conversion of grid probabilities
to binary64 is exact and does not renormalize the row.

Current-regret and exported-average images have distinct tags. Preserve raw
average masses separately: the saved grid is not exactly realization-equivalent
to their normalized ratios. Independent visible-information best responses must
certify the saved grid itself, using unnormalized counterfactual action values.
No exploitability claim transfers from an unquantized raw average.

The quantizer has a cumulative, noncopyable/nonmovable work owner. A failed
allocation poisons it, and no partial policy image escapes. Limits can only be
reduced: 500 million named word-work units, 65,536 integer bits, 2 million entries
and `2^30` integer payload bits. Input values and retained policy copies are
caller-owned and need separate parent admission. These modeled bounds are not
CPU or process-memory measurements.

## Fold before the full board

`fold_prefix_exact_reach` accepts visible prefixes of length 0, 3, 4 or 5, exact
common-denominator opponent reaches, and a signed whole-hand binary64 payoff.
It integrates only current blockers and uses divisor d_k, with proposal q=1:

`value_i = own_weight_i * compatible_sum(opponent_weight_j * reach_numerator_j)
           * signed_payoff / (Zint * d_k * reach_denominator)`.

Flop cards are canonical; turn and river stay ordered. It neither enumerates
hidden completions nor ranks a hand. Summing exhaustive legal reveal siblings
accounts for future chance without another chance multiplier. Full-board APIs
continue using d5, including the original double-reach API.

The caller must authenticate that this is a fold at exactly that visible betting
history and supply the correct whole-hand payoff. The component does not prove
history reachability. Preserve all physically supported rows and legal actions,
including zero policy/opponent reach. Only zero prior physical prefix mass may
prune the exhaustive traversal. A training owner must aggregate every kernel
setup/query and policy allocation; separate component owners do not establish
one cumulative whole-game admission.

## Executed development controls

Strict MSVC builds and independent exact Fraction controls pass. Each mode covers
149,232 fold vectors over all 3,109 visible prefixes, six exact reach profiles,
both seats and four signed/payoff modes, plus 22 rejection guards. Existing
full-board controls retain 120,960 vectors and 13 guards. All 10,464 raw legacy
requests per mode remain byte-identical to the active `9dbf1ef` baseline,
including serialized receipts. The policy controls cover 360 images, exact row
bounds/binary64 bits, all menu widths 1–20, 2,000-bit weights, zero/tiny-positive
weights, legal-order ties and 24 rejection/owner controls.

The 41 checks pass normally and optimized. Normal validation is split: the first
child passed 34 and skipped seven compiler-dependent checks because its compiler
environment was absent; only those seven were subsequently run and passed.
The optimized child passed all 41 with zero skips in 88.545 seconds. Complete
raw source inventories stayed stable and final source-only compiled-byte receipts
were checked. These are development controls on the captured uncommitted tree,
not a committed-source training acceptance. The
[manifest and original streams](../benchmarks/results/native-dyadic-prerequisites-v1/manifest.json)
retain the skipped first child, early copyable quantizer source and correction.
Windows/Linux and sanitizer CI include both new components; final results are
a separate publication check.

The [prepared chance, compact history and persistent state](native-dyadic-training-foundation.md)
now have independent component controls. Cumulative whole-request admission,
actual whole-game T>=2 feedback and independent saved-policy quality remain open.
No cap was lifted and no frozen numerical study was restarted.
