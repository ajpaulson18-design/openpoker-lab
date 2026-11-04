# Integrated native frozen-update proof

Status: in development. The independent rank-free census and primitive controls
pass. Development whole-update admission now fits the unchanged limits,
but complete per-board comparison and expectation proof have not run. This is the next integration under the
[scalable foundation](foundation-first-audit.md), joining the merged
[full-deck chance seam](native-full-deck-public-chance.md) and
[card-free betting template](virtual-betting-template.md). It is not a sampler,
trainer, saved-policy quality result or full52 capacity claim.

## Fixed game and units

Preserve the first failed reference fixture's complete betting configuration:
stacks 8/8, blinds 0.5/1, preflop pot-sized raises with one raise and explicit
all-in; each later street has half/full-pot bets, quarter-pot raises, one raise
and explicit all-in. The second failed fixture remains a separate control.
Neither old 60-board public-tree census is retried or admitted by raising its cap.

The reduced proof deck is the sorted physical IDs
`16,17,24,32,33,35,37,43,48`. Original input-order ranges are:

| Seat | Holding IDs | Exact binary64 weight |
| --- | --- | --- |
| SB | 43,48 | 0.125 |
| SB | 32,43 | 0.75 |
| BB | 24,37 | 0.375 |
| BB | 16,32 | 1 |

These are the earlier inputs scaled by one half in each seat. The actual
compatible private-prior normalizer is **29/64**, and normalized pair priors are
3/29, 8/29 and 18/29. Do not mix this raw Z with unscaled 29/16 or the kernel's
internally scaled integer normalizer. There are 2,520 unconditioned public
proposal boards, 60 positive-target boards and 2,460 zero-target boards.

For prefix lengths 0/3/4/5, target divisors are 1/10/20/20 and compatible private
pair suffix counts are 20/2/1/1. Absolute own-hand prefix mass is
`wi*sum_compatible_unblocked(wj)/(Z*d_k)`, equivalently the suffix-weighted
product sum divided by `Z*20`. Proposal completion counts are 2520/30/5/1.
These three families are separate.

## Policy and proposals

The first profile is a complete deterministic test policy, not a learned policy.
Its version is `frozen-pow2-profile-v1`. FNV-1a64 hashes these exact bytes:
ASCII `OPL-FROZEN-POLICY-V1` followed by NUL, global actor byte, two increasing
numeric own-card IDs, little-endian uint16 history-token count, then each token's
little-endian uint16 ASCII byte length and exact bytes, then one menu-width byte.
Offset is 14695981039346656037, prime 1099511628211, with modulo-2^64 products.
Operational bounds are 64 history tokens, 64 bytes per token and 20 legal actions.
The hash selects probabilities; it never identifies an information set.

Rotate ordered actions by `(hash>>32)%m`. When m>1 and `(hash&3)==0`, give action
`(hash>>8)%m` probability zero. Remaining n cyclic actions receive probability 1
when n=1, otherwise `2^-min(j+1,n-1)` for positions j=0..n-1. They sum exactly
to one. Every nonzero action reach is a power of two and is admitted before
normal binary64 transport. Arbitrary products of general dyadic probabilities
can exceed 53 significand bits; this proof does not certify that broader case.

An owned proposal supports uniform public boards, or the explicitly reduced
nine-card river-weighted proof law. Uniform q at 0/3/4/5 is
1, 1/84, 1/504, 1/2520. For the second law let w(c) be one plus c's index in the
sorted proof deck. Then `q(B)=w(river)/12600`; each river appears 280 times.
At flop F, `q(F)=5*sum_outside_F(w)/12600`; after turn T,
`q(F,T)=sum_outside_F,T(w)/12600`; root q=1. Independent enumeration must verify
all prefix probabilities. Global card indices are not changing remaining-card
indices. No actual RNG or sampler is introduced.

## Whole-history update contract

One owner constructs the template and chance kernel from the same immutable
configuration, deck and original range snapshots. Foreign or reordered hand
lists cannot relabel vector rows. Only the original empty-history preflop root
is accepted. Collision-safe parent/token ownership keeps different action paths
distinct when their numeric betting continuations reconverge. Reveals append
only a canonical flop followed by ordered turn/river cards. A new owner at a
recycled address must reject the old owner's cursors.

The two frozen responder walks retain all legal alternatives, including
zero-own-policy actions. Terminal counterfactual vectors already include
`wi*sum_j(wj*opponent_reach_j*utility_ij)/(Z*d5*q(B))`. Own preceding reach is
absent from regret increments. Own decisions mix future values using the
visible-history policy; opponent decisions propagate only opponent action reach.
No maximum may condition an earlier action on hidden sampled cards.

Only the target player's walk stages averages at its own rows. The denominator
increment is `own_reach_i*absolute_prefix_mass_i(P)/q(P)` and its action numerator
also multiplies by the action probability. Opponent reach never filters average
rows. Include every currently physically supported row, even at zero policy
reach. A zero-target complete board is not redrawn and can still contribute
positive earlier-prefix averages. Do not use future support to prune earlier rows.

Return a detached, fully owned staged update. Complete keys are original actor,
own holding and full visible token history; local node IDs from different calls
cannot be compared as global row identities. Admission or arithmetic failure
must not publish partial learning state. Experimental proof owners are single-use
and retain failed work consumption; that restriction is not an admitted reusable
training loop.

## Admission and current census

All setup, history copying/lookup, policy hashing, recursion, exact arithmetic,
chance queries, retained integers, output and cleanup need a composed parent
request allowance before the walks. Existing 500-million work, two-million
logical-entry and integer/payload caps remain reduce-only. Child owners cannot
each receive the whole parent allowance or reset a cumulative kernel meter.
Logical models do not measure CPU instructions, heap bytes or RSS.

The independent test-only reference enumerates 3,109 proof-deck prefixes and
literal action skeletons, without retaining card-expanded row keys. Its current
derived geometry is:

| Family | Count |
| --- | ---: |
| Shared betting states / edges | 388 / 410 |
| Symbolic node / edge occurrences | 1,105 / 1,104 |
| Maximum depth / menu width | 15 / 4 |
| Positive target prefixes at 0/3/4/5 | 1 / 25 / 56 / 60 |
| Unique supported rows | 24,420 |
| Unique supported action slots | 58,164 |
| Unfiltered per-board row / action-slot upper bounds | 868 / 2,078 |
| Estimated row-record visits across all proposals, per law | 107,080 |
| Estimated row-record visits across both laws | 214,160 |

The per-street supported rows are 12/880/6,728/16,800. Multiplying them by
proposal completion counts 2520/30/5/1 gives the row-record estimate. This is a
counting result: staging remains null/not attempted. This census alone does not admit a complete update. See the separately
measured development preflight below.

## Development verification checkpoint, November 4

The native proof transport builds with strict MSVC warnings and floating-point
settings. Its `virtual-frozen-update` target has an explicit 384-bit integer
transport ceiling and a 2,135,476-byte response bound reserved before setup.
Windows uses binary stream mode to preserve exact LF framing. The host parser
bounds raw bytes before decoding, checks framing and numeric widths before
conversion, retains full keys and verifies exact local row identities. Three
synthetic parser tests pass normally and optimized; all ten saved native
admission/error frames also parse. These checks do not prove poker semantics.

The latest development uniform admission forecasts 425,732,928 native logical
work plus 34,185,248 transport work. The weighted worst-law fixture forecasts
430,142,208 plus 34,185,360. Both fit 500 million, with zero chance/rank/conversion
callbacks and no staged rows. Width forecasts are 328/333 bits; retained-entry
upper bound is 270,260. These two observed admissions still require an
independent dominance argument covering all proposal requests before the study.
The earlier 651,743,744-work rejection remains preserved.

Six independent sampled-reference controls pass normally and optimized. They
cover wins, ties, losses, exact proposal rescaling, prefix averages behind a
zero-target board, future-card independence and admission/context rejection.
The first zero-target test failed because its first-zero-board selector did not
require positive intermediate-prefix support. Its source/logs are retained;
the corrected selector explicitly requires positive turn-prefix mass. No native
producer was rerun for that test-only fixture correction. The separate seven
q-free expected-reference controls and nine census controls passed previously;
those older tool-output observations do not have durable raw test streams.

The standard `virtual-frozen-update-controls` build now passes bounded exact
arithmetic, parent-limit, stale-address, failed-owner and zero-target tests.
The strengthened same-player zero-action witness was absent from two 2-chip
control fixtures; both failures are retained. A separate 4-chip control supplies
a qualifying continuation and passes. The complete PROOF9/v1 study fixture
remains stacks 8/8. These are component tests, not a smaller substitute study.

The [development manifest](../benchmarks/results/virtual-frozen-update-development-v1/manifest.json)
authenticates selected raw streams, first-failure sources and build identities.
It is not a complete frozen experiment source closure.

The complete experiment, evidence exporter and aggregation resource envelope
are still under implementation. None of these controls establishes all-outcome
update equivalence, training, quality or performance. Development receipts are
kept outside the checkout pending a source-frozen publication cohort.

The [complete-study protocol](virtual-frozen-update-study.md) now has an
executable rank-free two-law admission census. Every board's proposal widths
are bounded by the declared worst-law scope, and exact summation verifies all
prefix probabilities. This closes the proposal-width dominance obligation at
the inspected development source; native frozen-source admissions, aggregation,
q-free oracle and serialization still precede the full producer.

The first new compiled CI run passes Windows but fails both Linux builds.
Raw remote logs are unavailable through anonymous access; failure annotations
are retained. Native files are now formatted with all non-whitespace bytes
verified against the original sources. The local formatting investigation
briefly removed a used prefix-index variable, producing two retained build
errors; that edit is restored. Formatted MSVC controls build and run successfully.
The [portability evidence](../benchmarks/results/virtual-frozen-native-portability-development-v1/manifest.json)
retains these attempts. New CI diagnostics expose compiler errors directly;
at source `b0fa38e`, all three native jobs now pass: Windows, Linux and
ASan/UBSan. Both the probe and bounded controls compile, and the controls run
successfully. These jobs do not run the all-proposal numerical proof.

The saved-only exact comparator now checks every complete physical key, ordered
menu, policy exponent and regret/average rational against the independent sampled
reference snapshot. Equivalent unreduced fractions are accepted. Six synthetic
mutations pass wire invariants but fail semantic comparison. Three controls
pass normally and optimized; no native or reference producer executes during
these controls. The [comparison development receipt](../benchmarks/results/virtual-frozen-comparison-development-v1/manifest.json)
pins raw test streams, comparison allowances and the successful three-job native
CI observation. Real full-row equivalence and mutation witnesses remain open.

## Remaining acceptance

First preserve the complete v1 whole-request forecast and its outcome. If it
rejects, improve the representation or derive justified component bounds;
changing the game or lifting old caps does not resolve the barrier. Authenticate
and freeze all mathematical, reference, build and protocol source before the
real all-proposal proof batch. Admit the entire 2,520-outcome, two-law experiment
separately from each single-use proof request.

Compare every exact per-history/hand/action raw regret and average numerator and
denominator against independent numeric betting rules, physical private deals,
best-five ranks, policy encoding and proposal sums. Compare per-board results
before summing expectations. Detect omitted q/d5, selected normalization,
duplicated prior/reach, hidden-future filtering/maxima, wrong role, zero-action
omission, history aliasing and wrong average q(P). Inject budget, ownership,
overflow and conversion failures before publishing staged results.

Only after those gates can evolving-policy reach representation, actual sampling,
bounded persistent strategy storage and one native four-street training path be
accepted. Unbiasedness under evolving policies, variance, convergence, complete
policy exports and independent whole-game quality remain separate obligations.
The selected-game result of two passes and 26 misses remains unchanged.
