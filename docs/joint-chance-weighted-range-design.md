# Weighted joint-ticket owner design

Status: source-only design. This is not an implemented mode, a native
admission, a benchmark, or a training-quality claim. It proposes a bounded
ticket-only purpose on the existing `PreparedPublicChance` owner for finite
full52 ranges with exact positive binary64 priors. Existing constructors and
contraction behavior remain the default compatibility path.

## Contract and scope

The new opt-in purpose, tentatively `Purpose::joint_tickets_v1`, owns a sealed
copy of both ordered input ranges and offers the existing borrowed joint-sample
certificate interface. It does not prepare contraction planes,
reach vectors, or prefix/query caches. Its operation is only:

1. Interpret a `uint64` private ticket as one exact compatible private pair
   under the input prior.
2. Interpret a `uint64` board rank as a canonical flop and ordered turn/river
   sampled uniformly from cards left after that pair.
3. Rank only those two selected hands and lend their original input indices,
   physical holdings, board, and seat-zero showdown sign to a callback.

This returns the physical joint law `q(i,j,B)=P(i,j,B)` exactly. The same
algorithm covers the accepted PROOF9 ranges and a full52 deck with ranges of at
most 1,326 holdings per seat. Other deck sizes can remain rejected until their
board-count and unranking bounds are explicitly admitted. This mode does not
call the full-deck contraction APIs.

The default legacy purpose retains its present prior-kernel, contraction,
cache, resource receipts, and output behavior. Unsupported purpose/range
combinations fail closed before constructing the legacy prior or allocating
the ticket CDF. There is no silent fallback. Existing N9 observations and
controls remain pinned regressions.

## Exact prior representation and rejection gates

Decode each positive finite binary64 weight with the existing
`detail::decode_parts` bit decoder. Do not compute probabilities with floating
point arithmetic. For each seat independently:

1. Strip powers of two from each decoded significand and record the adjusted
   exponent. Find the minimum adjusted exponent.
2. Align each significand to that exponent using a fixed-width temporary. An
   exponent shift of 64 or more cannot yield a 64-bit normalized weight after
   removing an odd common divisor; reject before allocating integer vectors.
3. Compute the exact per-seat gcd over aligned fixed 128-bit unsigned
   temporaries with no dynamic allocator, divide by it, and require every
   resulting positive weight to fit in 64 bits. The bounded temporary must be
   wide enough for the decoded significand plus at most 63 alignment bits.
   Reject any larger intermediate before creating `cpp_int` state.
4. Only after those checks, materialize the normalized `uint64` weight arrays.

Ticket mode must not retain a second raw `WeightedHand` vector plus separate
weight, mask, same-hand, and weight-bit arrays. Use one compact owned row per
input holding, such as `{Hand, uint64 value}`. During construction the value
field holds the exact original weight bits; after the three bounded decode/GCD
passes and all width checks, replace it in place with the normalized integer
weight and seal the owner. Keep a separate seat-0 cumulative row CDF and a
dense physical-pair index map, so both normalized seat weights remain directly
available and a positive-prior holding with zero compatible mass is preserved
without CDF inversion. Keep each exact per-seat normalization scale (minimum
adjusted power and 128-bit gcd) in the receipt so normalized
values remain auditable against captured input. The caller or immutable input
artifact owns original-byte provenance. Ticket mode exposes no API that can
observe a partially converted row. Existing legacy mode keeps its source
representation unchanged.

Independent positive scaling of either seat's weights leaves the joint law
unchanged. The exact integer normalizer is

`Z = sum_i w0[i] * sum_{j disjoint from i} w1[j]`.

For `H0,H1 <= 1326`, normalized per-row weights of at most 64 bits give the
conservative pre-check bound
`bits(Z) <= 64 + 64 + ceil(log2(H0)) + ceil(log2(H1)) <= 150`.
An inclusion-exclusion bucket uses 53 integers (one total and 52 card sums):
the total is at most 75 bits, each card sum at most 70 bits, and each
compatible-mass product at most 139 bits. Accumulating at most 1,326 products
fits the 150-bit bound. Reject `Z == 0` and reject `Z > UINT64_MAX` before
allocating the CDF. The ticket API remains `uint64`; larger exact normalizers
are outside this contract, even though the general chance kernel can represent
larger integers.

No weighted per-pair table is needed. The unordered pair code
`a*(103-a)/2 + (b-a-1)` for `0<=a<b<52` bijects the 1,326 physical holdings to
dense indices `[0,1326)`. Independently check this bijection over all
`itertools.combinations(range(52),2)` in the reference. Store one
`uint16_t` original-index map with 1,326 slots and sentinel 65,535. Validate
each seat's canonical physical holdings and reject duplicates, reusing this
map for both seat checks. Fill it for seat 1 and retain it; each stored value
is the original input row index, not the dense pair code.

Build one 53-cell weighted bucket from seat 1 and retain it as immutable owner
state. Compute each seat-0 compatible mass by inclusion-exclusion, adding back
an exactly identical hand through the dense map. First accumulate only scalar
`Z` and reject it before CDF allocation if it is zero or exceeds
`UINT64_MAX`. Then allocate the separate 1,326-entry `uint64_t` CDF and make a
second seat-0 pass, accumulating each `w0[i] * compatible_mass[i]`. Keep the
normalized seat weights, map, CDF, and bucket after construction. At ticket
time the retained bucket and map give compatible mass in constant time. A
repeated CDF prefix represents a positive-weight own holding with zero
compatible opponent mass; it is never selected by a valid ticket, but its
source row remains intact.

At sampling time, binary-search the row CDF for the owner index. Use the
retained bucket and dense map to get compatible mass in constant time. Divide
the remaining ticket by the stored seat-0 weight to obtain the opponent-prior
ticket, then scan the opponent's original ordered rows once, skipping hands
blocked by the selected owner hand. This uses `O(log H0 + H1)` work and no
conditional pair table. Retain input row order throughout so certificate
indices remain the original policy holding identities.

Admission rejects invalid/duplicate holdings, nonpositive or nonfinite
weights, incompatible ranges, excessive aligned weight widths, zero or
over-64-bit `Z`, foreign ticket/rank values, and unsupported deck modes. It
must reserve all work and temporary storage before allocation. It must never
truncate, wrap, renormalize approximately, or fall back to floating-point
sampling.

## Full52 board ticket and accounting

For a compatible private pair, 48 cards remain. The full52 board ticket count
is

`C(48,3) * 45 * 44 = 34,246,080`.

For a board rank `r`, split it into a flop-combination rank using the `45*44`
suffix count, and a suffix rank in `[0,45*44)`. Unrank the flop lexicographically
from the 48 remaining cards; then map the suffix quotient and remainder to two
distinct cards among the 45 cards left after the flop. The flop is sorted and
the turn and river remain ordered. A complete board consumes fixed arrays of
at most 48 cards; no board table or per-range rank vector is retained. The
PROOF9 case has five remaining cards and 20 completions and uses the same
general count/unranking rules.

The current 16,384 work bound belongs to the two-by-two PROOF9 call and must
not be reused as the weighted full-range bound. A candidate full-range call
ledger can reserve `8,192` for two seven-card ranks, `4,096` for board
unranking and validation, `64*H1` for the one opponent selection scan, and
`256*ceil(log2(H0+1))` for CDF search and ticket decode.
At `H0=H1=1326`, this is 99,968 units per ticket. This is a candidate logical-operation envelope;
the implementation must replace each term with source-derived operation
charges and prove the fixed-array accesses and integer widths before freeze.

Constructor work is separately charged for three-pass binary64 decoding,
gcd/alignment, range validation, fixed-map initialization and use, bucket
construction, compatible-mass products, the `Z` check, and CDF construction.
Its terms are all `O(H0+H1+2704)`, not `O(H0*H1)`. Derive and reserve their
actual source-ledger coefficients. The existing `PreparedPublicChance`
constructor has a `6*H0*H1` same-hand scan and retains a nested
`PublicChanceKernel`; those costs and arrays must be bypassed in the opt-in
ticket-only purpose. The existing `PublicChanceKernel` already demonstrates
the direct 2,704-key lookup and O(H) bucket-normalizer structure, but its
general output and temporary storage forecasts are not the ticket-only
admission.

The ticket-only purpose must preserve the current entry-accounting meaning; it
cannot redefine existing source rows as smaller entries. Reuse the existing
three-entry-per-row source admission for compact `{Hand, value}` records: at
`h=H0+H1=2652`, this is `3h+64=8,020` retained entries. The 1,326-entry map,
1,326-entry CDF, and 53-cell bucket coexist with those rows in the fully
conservative phase. Add 128 entries for bucket descriptors and scalar/ticket
temporaries. The peak is
`3h+64+1326+1326+53+128=10,853`, below the existing 12,000-entry chance
fixture cap. The implementation must verify every overlapping buffer against
this sum; it must not count the map or CDF as smaller logical entries based on
their byte representation.

The row value fields contain at most `h*64=169,728` bits of normalized
weights. The CDF adds at most `H0*64=84,864` bits, the `uint16_t` map adds
`1326*16=21,216` bits if map values are included in integer payload, the
physical hand-card fields add a conservative `16*h=42,432` bits, and the
retained bucket adds at most 3,975 bits. Bounded owner scalars add fewer than
1,000 bits, totaling less than 330,000 live integer payload bits. A per-ticket
scratch allowance of 8,192 bits covers bounded CDF products/scalars; report it
separately from retained owner payload. The existing
chance payload cap is
`1,048,576` **bits** (128 KiB), not bytes. A conservative ticket-purpose
reservation of 524,288 bits fits that cap. The existing whole-request payload
cap is `1,073,741,824` **bits** (128 MiB), not 1 GiB; the prospective whole
forecast below remains far under it. The owner must report measured receipt
peaks against these forecasts. These bounds assume the ticket-only layout
above; the current generic `PreparedPublicChance` layout does not fit them.

## Reuse for frozen Q52 observations

Because the sampler draws the exact normalized private-pair prior and then
uniformly draws a legal complete board, `q(i,j,B)=P(i,j,B)` for every supported
world. Proposal correction cancels exactly. The regret and average
denominators therefore stay `2^625` and `2^364` for the accepted fixed betting
tree, maximum stake eight, twelve decisions, and Q52 policy. They do not depend
on the private-prior normalizer or the deck size. Recheck terminal signs and
exact divisibility against the route proof; this denominator argument does
not admit arbitrary betting trees, stakes, or policies.

The same `History` representation supports full52 visible boards and keeps
hidden future cards out of decision identity. Its current encoded ordinal is
`(literal path << 33) | visible-board-code`; the fixed source has 1,105 paths,
so raw IDs remain below `2^44`. `Catalog::RowId` already carries the full
ordinal, actor block, and original holding index. `Catalog` supports up to
1,326 holdings and charges the larger per-block seen bitmap.

The two-observation sparse store can retain its existing row/slot ceilings
because one sample ticket selects one original holding per actor. The current
source shape is 434 policy rows and 1,039 action slots per complete walk, so
two observations touch at most 868 rows and 2,078 slots. Unvisited holdings
remain implicit uniform rows. The Store constructor must stop hard-coding
`{2,2}` and accept declared counts that match Catalog up to 1,326; the frozen
walk must also remove its `<2` holding checks and bind the full52 source and
ticket owner. Its `true_joint_proof9` arithmetic label also needs an explicit
weighted fixed-tree contract, bound to the validated ticket-purpose range
origin, exact source geometry, and Q52 grid. Do not materialize all 1,326 rows
at each information set.

An illustrative two-observation scalar envelope from current source formulas,
parameterized with `Catalog` holding count 1,326, is:

| Component | Forecast |
| --- | ---: |
| Catalog | 39,852,640 work; 185,908 metadata entries |
| History | 5,803,168 work |
| Store plus quantizer | 18,160,320 work |
| Raw walk | 1,142,852 work per observation |
| Parent and row joins | 3,774,216 work for both observations |
| Output upper bound | 502,720 bytes |

These yield `118,633,864 + W_chance` whole work, where `W_chance` is the new
weighted ticket constructor plus two full-range ticket calls. The candidate
ticket-call envelope contributes about 200,000 units. Work must be recomputed
from the final owner ledger and show `W_chance <= 110,000,000`, with the whole
request below 500,000,000. The conservative whole forecast is about 971,715
entries and 53.6 million payload bits under the current 2-million-entry and
1,073,741,824-bit payload caps. Catalog's work remains below its 75-million
component cap; the Store plus quantizer, History, and parent also remain below
their existing component caps under this fixed two-observation shape. These are prospective
scalar bounds, not a completed admission or execution.

## Longer-learning architecture gate

Admission of two selected worlds would leave a much larger storage problem.
For the current fixed betting template, the independent numeric-rule census
has both-seat decision-path counts `(6,32,116,280)` and action-slot counts
`(15,84,288,652)` at preflop/flop/turn/river. With complete positive full52
ranges, every own hand avoiding a visible board has some compatible opponent
and legal completion. The visible prefix counts are
`(1,C(52,3),C(52,3)*49,C(52,3)*49*48)` and supported own holdings per
prefix are `(C(52,2),C(49,2),C(48,2),C(47,2))`.

| Street | Exact row universe | Exact action-slot universe |
| --- | ---: | ---: |
| Preflop | 7,956 | 19,890 |
| Flop | 831,667,200 | 2,183,126,400 |
| Turn | 141,695,299,200 | 351,795,225,600 |
| River | 15,733,064,256,000 | 36,635,563,910,400 |
| Total | 15,875,591,230,356 | 36,989,542,282,290 |

The [reproducible scalar worksheet](../scripts/forecast_joint_information_universe.py)
derives the betting-path counts from the independent numeric rules. These are
scalar products, not an enumeration or native allocation. Eight
bytes per action unit alone would be 295,916,338,258,320 bytes, before regrets,
averages or metadata. This is not an information-theoretic storage minimum:
implicit uniform rows and sparse storage already avoid the dense allocation.
Even an optimistic division of row count by all 24 suit permutations would
leave at least 661,482,967,932 orbits; that bound only applies to suit-symmetric
inputs, not arbitrary weighted ranges.

Before a longer-learning admission, measure retained row/slot union growth
and exact-integer growth over observations, then forecast the complete
requested lifetime. Reassess action/information abstraction or independently
validated compression when that forecast fails. Preserve perfect recall,
original holding identity and hidden-future exclusions in any such change.
A full52 two-observation witness must not be presented as a practical
full-game learner.

## Required independent gates

1. Preserve existing legacy constructor/probe bytes and the current N9 ticket
   census. Exercise the opt-in weighted owner with independent exact Fraction
   references on small weighted ranges. Verify normalized weight ratios,
   exact `Z`, every ticket-to-original-ID CDF boundary, blocker exclusions,
   board-rank bijection, and seat-zero signs. A bounded pair census is useful;
   never enumerate the full private-pair-by-board product.
2. For full52, use a one-world witness: independently construct a canonical
   pair from the ticket, unrank its board, evaluate the two hands with an
   independent ranker, and calculate all raw rows for that literal board from
   the numeric betting rules and uniform Q52 policy. Compare roots, row keys,
   action menus, signed regrets, and average contributions. Keep the policy
   sparse and default-uniform; the test does not build a 1,326-hand-per-row
   dense fixture.
3. Independently audit the proposal law. For small weighted ranges enumerate
   compatible private pairs and check exact `q(P)`/`q(B)` against physical
   support. For full52 uniform ranges, verify the closed-form normalization
   and blocker-conditioned prefix masses; no enumeration of 34-million-board
   sets per pair is needed.
4. Admit before allocation using actual source-derived constructor, per-ticket,
   owner-entry, integer-payload, Catalog bitmap, History, Store, output, and
   parent formulas. Keep all current ceilings unchanged. Reject any range
   whose normalized weights or `Z` exceed the ticket contract.
5. Only after independent conformance and source freeze, run paired complete
   two-observation measurements. Report CPU/runtime separately from logical
   work. Catalog's roughly 40 million logical-work allowance is not evidence
   that Catalog is the CPU bottleneck; profile the complete call and its
   per-component wall time before choosing another optimization. Two frozen
   observations establish neither stochastic convergence nor
   CFR+ clipping equivalence, unvisited-state quality, or unrestricted NLHE
   readiness.
