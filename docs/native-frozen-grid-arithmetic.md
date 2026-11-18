# Native frozen-grid arithmetic contract audit

Status: source-reviewed arithmetic design, not an implemented native mode or
complete resource admission. The [Q52 reference](frozen-grid-update-reference.md)
proved whole-game fixed-policy raw-update expectations and retained a 421-bit
one-board value. This audit determines a viable representation before a native
walk can be benchmarked. It preserves the old probe and its 384-bit cap.

The audited native source is unchanged from `0862087`. The game remains PROOF9
with normalized integer private priors `((1,6),(3,8))`, compatible-pair normalizer
`Z=29`, twenty ordered public completions per pair, maximum stake eight, and
at most twelve decisions along a route. The accepted trainer independently
asserts actor decision depths `{6,7}` and the same numeric betting geometry.

## Reuse the exact trainer carrier

`virtual_frozen_walk.hpp` stores power exponents and creates `double` reaches
with `ldexp`. That is appropriate for its historical profile. General Q52
sequence products must not pass through this boundary.

`virtual_dyadic_training.hpp::Reach` already stores an integer numerator vector
over `2^e`. Its `advance` multiplies by ordered uint64 policy units, adds 52
denominator bits and cancels only common powers of two. At most seven own
actions require exponent at most 364 and numerator width at most 365.

The trainer's actual reuse seam is
`PreparedPublicChance::contraction(target,prefix,kind,numerators,e)`. It returns
raw prior-weighted exact integers, a prefix divisor and the supplied exponent.
The parent owns normalization, configured money, proposal correction and fixed
game scaling. Prepared has neither `prefix` nor `terminal_exact_reach`; those
belong to the separate `full_deck_public_chance` kernel API. Do not conflate
their admission receipts.

For a sampled complete board, use complete-board contractions for folds and
showdowns, including early all-ins. The hidden completion is a latent sampled
chance outcome, not a new visible information set. Prefix averaging remains
a separate walk and cannot be suppressed by zero complete-board target mass.

## Common denominator and exact mixing

For unreduced board proposal `q(B)=n/d`, choose
`D_B = 29 * 20 * n * 2^625`, with `625=52*12+1`.
For a terminal stake `s*2^p`, the pinned money exponent is in `[-1,3]`.
A prepared raw contraction `C` at opposite reach exponent e is scaled to
`C*s*d << (625-e+p)` on `D_B`. No binary64 probability or decimal rounding is
introduced. Both utility signs remain global SB/BB signs.

At a target decision, the opposite past decisions and target future decisions
in each child action value are disjoint and exclude the current target move.
Their total is at most eleven. Every child common numerator therefore retains
at least 52 powers of two for the current target mixture. Multiplying by the
Q52 units, summing and dividing by `2^52` is exact. Opponent decisions sum child
values, without a target-policy division. Native code must check divisibility
and bind this argument to the actual route census before admitting a request.

Physical complete-board mass is at most `1/20`; opposite reach is at most one.
Action advantage is at most sixteen in magnitude. Consequently
`|N_regret| <= 16*29*d*2^625`, independent of n.

| Quantity | Uniform proposal | Weighted-river proposal |
| --- | ---: | ---: |
| Common denominator width | 635 bits | at most 638 bits |
| Raw regret magnitude width | at most 646 bits | at most 648 bits |
| Child utility magnitude width | at most 645 bits | at most 647 bits |
| Pre-division mixture magnitude width | at most 697 bits | at most 699 bits |

The mixture bound uses the sum of nonnegative units equal to `2^52`, including
partial sums. Packed signed two's-complement storage needs a separate sign bit;
the existing multiprecision carrier uses a separate sign. The existing
`factored_dyadic.hpp` 704-bit expanded/intermediate cap can represent these
arithmetic bounds. This does not establish work, payload, I/O or State admission.
No old arithmetic limit is changed by this audit.

## Prefix averages

For prefix proposal `q(P)=a/b`, prefix divisor `c` in `{1,10,20,20}`, prior
mass numerator m and own reach `r/2^e`, an average-action contribution is
`m*b*r*unit / (29*c*a*2^(e+52))`. Before the current action, e is at most 312;
including that action gives at most 364 bits of probability denominator.

The raw prefix prior sum m is a subset of the same compatible-pair prior sum,
so `m<=29`. Weighted prefix numerators are at most 195 and denominators at
most 12,600. Hence a row's unreduced average denominator has at most 381 bits,
and average-action/mass numerator has at most 383 bits. These are conservative
joint bounds, not observed maxima. Multiplying by all completion proposal
masses cancels `a/b` only after including zero-full-target futures.

## Required native gates

Validate a complete immutable snapshot by actor, original own holding, full
ordered visible history and ordered legal menu; include zero units and
zero-reach rows. No policy callback may inspect hidden future cards. Reuse the
compact History key only with independent full-history reconstruction and
physical prefix support checks.

Before compiling a candidate study mode, derive the whole request's work,
entry, retained/temporary payload, integer, snapshot input and staged output
forecasts. Include prepared-query validation, q/stake scaling, target mixtures,
signed subtraction, prefix averages and export. Existing 704-bit arithmetic
support is not permission to reuse the old 384-bit probe's forecasts or to
increase resource ceilings. If those forecasts reject, improve the computation
or representation and preserve the rejection.

Then compare complete native per-board rows to the independent Q52 oracle,
including zero-target boards and earlier-prefix averages. Only after exact
conformance may paired complete-call measurements determine whether this
schedule improves terminal and State costs. Evolving-policy learning, unvisited
State behavior, sampled CFR+ clipping and independently replayed policy quality
remain later gates. None of this establishes eleven-card or full-deck training.
