# Proposed bounded whole-process native exact four-street slice

This is a source-based implementation design, not a completed solver, independent certificate, or speed result. Reviewed checkout: `work/native-exact-four-street-repo`; reviewed `docs/native-exact-four-street.md`, the exact selected kernel and dyadic arithmetic helper, equivariant reference, quotient plan/trainer, legacy selected-DAG adapter/C++, and the new bounded binary64 converter header. The checkout already contained the root's converter/build/documentation work. This review changes no production file.

## Recommendation and smallest coherent deliverable

Implement one new native executable that owns exact chance arithmetic, on-demand ranking, procedural Q lookup, and the complete alternating CFR+ loop. Retain Python rule/DAG preparation and unchanged post-training physical/public diagnostics initially, charging them in complete-call evidence. Run one native process per solve, never one process or request per callback.

The first accepted native slice should cover the existing selected, finite, four-street game rather than a single street or an arithmetic-only probe. Use compact input diagnostics, exact dyadic callbacks, the published sorted-chance binary64 trajectory, and either the identity suit group (unquotiented storage) or a verified nontrivial group (Q storage). Start with the meaningful club/diamond control whose private holdings actually exchange under the suit map, then the original 22-world T10 fixture and asymmetric/weight-broken controls. Preserve every existing admission rejection and quality miss. A converter or positive-integer probe is a prerequisite, not this deliverable.

## Boundary: a distinct versioned request

Do not extend `OPENPOKER_SELECTED_DAG_V1` in place. Its Python `wire()` sends a floating normalizer and per-board rank vectors, its C++ query law uses rounded pair normalization, and its terminal serialization reconstructs scale through the old anchor representation. Those are materially different contracts. Reuse its bounded parsing/process/manifest ideas only after reviewing their meaning for the new law.

Use a new protocol/executable, with a length-delimited request, explicit counts, and checked integer sizes. A compact binary encoding with fixed little-endian unsigned fields and length-prefixed ASCII tokens avoids floating text parsing. An audited bounded ASCII encoding is also viable, but doubles should still travel as exactly 16 hexadecimal bit-pattern digits, not decimal values. Specify one encoding before implementing both ends.

Required sections:

| Section | Fields and independent native validation |
| --- | --- |
| Header | Magic/version; exact-product law ID; strict completed-query conversion ID; sorted-reduction ID; iterations; rank-cache request; counts; bounded byte lengths; requested group/mode; complete declared admission counters and limits. Reject unknown flags, trailing bytes, overflow and duplicate sections. |
| Ranges | Global player 0=SB and 1=BB; each seat's ordered canonical two-card holdings; original positive finite binary64 weight bits. Preserve input hand-index order. Validate distinct cards, duplicate holdings, and weight bits. Python's lexical ordering within a holding differs from DECK order; never silently renumber hands. |
| Selected outcomes | Canonical three-card flop, ordered turn and river, each encoded as card IDs in the documented DECK mapping. Validate five distinct cards, canonical flop, unique complete outcomes, and canonical full-outcome ordering by all five DECK indices. Turn and river are never interchangeable. |
| Public graph | Root ID and complete initial history; unique tagged vertices; ordered full action records and children at decisions; street/card index and unique labeled branches at chance nodes; kind, winner and original global contribution bits at terminals. Include full action name/amount/raise-to/full-raise/token, not only child IDs. Validate child IDs, schemas, acyclicity, reachability and bounded depth. |
| Suit group | At most 24 explicit bijections of `cdhs`; identity/inverses/composition; exact role-specific weighted-prior and selected-outcome invariance; exact public-graph signature closure. Native verification must reproduce these checks. A Python success receipt is not authority. |
| Optional Q witness | Q representative `(global player, original own-hand index, complete visible-history tokens)`, menu, distinct-member count/mask and offsets. Prefer deriving Q natively. If Python sends this compact Q witness, treat it as an assertion: independently stream every supported native row, reconstruct its representative/member ordinal, and prove exact coverage and menus before allocating numeric state. Do not send or retain an R-to-Q table. |

Forbidden request sections: trusted Z, pair probabilities/edges, complete private deals, Python hand ranks, precomputed terminal/marginal vectors, policies, regrets, current strategies, average sums, or expanded R row/lookup tables. Parsing a supplied policy as the answer would defeat the whole-native boundary.

Public-history tokens need exact canonical comparison semantics. Arbitrary interned token IDs do not preserve Python tuple/string ordering. Either compare actual bounded token strings or assign canonical lexical ranks. Q member ordinals must sort/deduplicate the same `(player, hand-index, full token sequence)` images as Python; occurrence sharing must never replace full-history row identity.

## Native exact kernel

Decode binary64 bits into integer significands and powers of two without floating normalization. Choose one admitted exponent per seat and construct integer weight vectors `W0,W1`. Build card masks/card IDs and bounded prefix-to-selected-board indices. Do not enumerate complete deals or a cross-seat rank matrix.

Compute the global normalizer integer once. For each selected board, filter each seat's holdings by the complete board mask, bucket one seat by total/card/exact-holding mass, and use `total-card[a]-card[b]+exact[own_hand]` to obtain compatible opposite-seat mass. Sum own weight times compatible mass across boards. The normalizer is global across all compatible selected-board occurrences, not recomputed at a visible prefix.

Physical support for a visible prefix is the union over compatible complete selected outcomes under that prefix. It is not simply absence of overlap with currently exposed cards, and it cannot condition on one unrevealed selected outcome. Use integer/unit buckets for rank-free support. A zero current strategy reach never removes an otherwise supported row.

For each terminal query, snapshot the complete opponent-reach vector as exact dyadics; preflight before shifts, products, rank requests or vectors. Align to a common reach denominator. For a signed dyadic payoff `P/2^ep` and common reach exponent `er`, accumulate integer numerators over matching complete boards, then convert each completed component with denominator `Z_integer * 2^(er+ep)`. The common seat-weight denominators cancel. Preserve the Python fold sign convention: global SB payoff is signed by the declared winner, with opposite sign for BB; showdown uses the original matched contribution and physical rank comparison. No pot-anchor subtraction/addition or root correction is introduced.

Showdown uses on-demand per-board/per-seat ranks and lower/equal/higher rank buckets with card exclusion, matching the Python helper's semantics. Equal-rank hands are ties, not suit tie-breaks. Add meaningful private-flush and both-seat tests; board-only or private-rank-only controls are inadequate. A bounded solve-local rank LRU retains O(B_cache*(H0+H1)) scalar ranks, with explicit active/evicted overlap; no H0*H1 matrix.

General normalized callback outputs are rational, even though input weights/reaches/payoffs are dyadic. Use the exact integer converter on the final numerator/positive denominator, round-to-nearest/ties-to-even, and return canonical +0 for exact zero. Reject a nonzero result only if its *rounded* bits are subnormal/zero/nonfinite. A just-below-normal rational that rounds to minimum normal must pass. Keep the 65536-bit query cap distinct from the converter's explicitly bounded extra scratch; do not silently widen query admission.

## Public graph and Q proof without expanded histories

Use bottom-up exact signature interning: terminal `(kind,winner,contribution_bits)`; decision `(global player,full ordered action records,child signature IDs)`; chance `(street,card_index,sorted(label,child signature ID))`. For each suit transformation, transform reveal labels (canonicalizing flops only), look up transformed keys in the *same identity interner without insertion*, and require transformed root equality plus fixed initial history. One transformation's V-sized map may be released before the next. Charge identity keys, Kahn/order/depth arrays, transformed IDs and maximum branch-sort scratch before allocation.

This proves the supplied labeled graph's unfolded public-history symmetry. It does not independently establish betting legality. Weighted priors, ordered selected boards, legal hand support and the actual poker rank law must separately be equivariant. Do not describe structural interning as merging information rows.

Native Q planning streams supported full-history rows and retains one representative/menu/offset/count/expected mask per Q record. Procedural distinct-image ordinals account for row stabilizers. Per-decision lookup may transform a history once and reuse it across that decision's own hands, as the accepted Python batched lookup does; no persistent per-decision R lookup cache is introduced. Every transformed row must exist in the public decision structure with the same actor/menu and positive support. Identity-group fallback is an explicit requested mode, never silent recovery from a failed nontrivial symmetry proof.

## Complete native learning phases

Initialize all four Q numeric buffers to +0 and use uniform regret matching. Keep action iteration and multiplication association identical to Python. At **every** chance target-vector node, canonicalize/validate all finite per-hand child components, sort each hand's complete multiset numerically, then explicitly add left-to-right from +0. No reassociation, implicit FMA, compensated library sum, parallel reduction, local chance normalization or omitted zero branch.

For each iteration:

1. Rematch from Q regrets with explicit ordered sums.
2. Traverse all physical supported members for responder SB. Stage the first member's complete action increment; compare subsequent increments by bits; reject duplicate member bits or missing expected bits. Prevalidate every prospective persistent update, then apply one unchanged increment per Q action once. No orbit multiplication, averaging or clipping before equality checks.
3. Rematch, perform the identical BB phase, then rematch.
4. Traverse averaging with the exact left-associated `own_mass * own_reach * current_probability * float(iteration)` sequence. Stage/compare all member increments and complete masks, prevalidate prospective sums, then commit once per Q action.

All supported members participate even at zero reach. Dense holes retain the same uniform fallback and vector positions as Python. Local subnormal intermediates remain IEEE binary64; the strict completed-query boundary is separate and may still reject a later subnormal exact callback output. Check rounding mode and FTZ/DAZ behavior, compiler flags, IEEE double format and contraction/reassociation settings; source/build provenance must record them. A native bitwise mismatch is failure, not permission for tolerance or legacy fallback.

After training, normalize Q average output with the same ordered operations. Release regret/current/delta/seen and the training average buffers before R expansion; explicitly charge any surviving compact Q policy vector as output-phase storage. Stream complete supported R rows from graph/support, copying Q probabilities into the old result contract. The native process need not buffer an R policy dictionary. Python may materialize expanded policies for unchanged diagnostics and serialization after native training storage is gone. Input bytes, captured stdout, parsed R dictionaries, Q output vectors and Python diagnostics still overlap and need separate output/complete-call admission.

## Admission and transport obstacles to resolve before training

Preserve existing old whole-request, dense layout, row/action, history, callback integer and Q/graph caps. No Q memory saving may bypass an existing rejection. Native recomputation must reject declared/recomputed census discrepancies; supplied declaration fields are witnesses, not allocation authority. Native's own scalar-operation model must be named separately where it does not exactly reproduce the existing Python logical model.

Preflight stages need an explicit live-allocation schedule: bounded header/body parser; graph validation before dictionaries/arrays; exact decoding/setup; group and signature proof; support/Q plan; four Q arrays plus nested sorted-child/action vectors; integer query/rank cache scratch; compact Q normalization; then output/diagnostics. Reserve width and payload before every arbitrary-precision shift/product/division. cpp_int's allocator, division temporaries and expression-template evaluations are not bounded by a peak mathematical integer-width counter alone. Avoid unchecked arithmetic expressions that allocate hidden intermediates before guards, and distinguish modeled units from CPU/RSS guarantees.

Use checked count/byte multiplication and explicit source ceilings; reject requests exceeding input/output caps before ranks/training. Preserve raw first stdout/stderr and failure stage, never retry a failed policy computation automatically. Require one-shot success only after validated result lengths, requested row coverage, finite bit values, nonnegative probabilities, agreed ordering, complete census and executable identity before/after. Keep the legacy transport/defaults unchanged.

## Independent acceptance and evidence

Layered diagnostic tests can compare vectors, but acceptance must reach a complete root-to-output four-street solve. Keep the physical Fraction oracle independent of native math. Required gates:

- converter hardcoded anchors and bounded randomized Fraction differential checks, including signed cancellation, ties, carry, overflow and normal/subnormal boundaries;
- exact native Z/marginals/payoff vectors versus literal bounded physical enumeration, including blockers, shared futures, non-power-of-two Z, actual private flushes, all-in early terminals and asymmetric global money;
- identity-group native complete-policy bits versus literal equivariant Python R, then nontrivial native Q versus Python Q/R for all expanded rows and all eight diagnostics; callbacks/cache behavior must not change policies;
- broken-weight/asymmetric G1 cases, nontrivial row stabilizers, holes, zero reach, duplicate/missing members, tampered Q keys/menus, signed-zero and nonfinite rejection, each before inappropriate persistent mutation;
- unchanged bounded saved-policy numeric and exact best-response replay, preserving actual target misses and old T1000 admission rejection rather than relabeling capacity as quality;
- frozen full introduced source/header/Boost/license closure, compiler/flags/executable identity, raw request/result hashes, all failed attempts and sanitizer/native/Python compatibility CI.

Only after these gates should a source-frozen complete-call comparison measure the new path. Profile observations suggest where to investigate; they do not establish a native speedup or remove the R output/diagnostic bottleneck. The first deliverable is one coherent bounded whole-game engine with explicit rejection and independently reproduced policies, not unrestricted full-deck solving.
