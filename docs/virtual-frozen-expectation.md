# Exact frozen-update expectation accumulation

Status: development component, with partial-stream controls only. The complete
[5,040-call study](virtual-frozen-update-study.md) has not run. This component
consumes saved raw responses and separate sampled-reference snapshots; it never
invokes a native executable, ranker, betting builder or update producer.

## Exact denominator structure

For one law let the unreduced board proposal be n/d. A native regret row uses
`D = Z_integer * 20 * n * 2^E`, with the same admitted E for this complete
fixed template. Multiplying a returned numerator N/D by q(B) cancels n, giving
`N / (Z_integer * 20 * d * 2^E)`. Thus one law-wide denominator supports exact
integer regret accumulation. Every call must give that same corrected denominator;
non-divisibility or drift rejects and consumes the owner.

An average row's own reach, policy exponents, target prefix denominator and q(P)
are fixed by its complete visible history and own holding. The raw denominator
A therefore stays fixed across all complete boards contributing to that row
under one law. Its expected mass increment is `mass_num * n / (A*d)`; ordered
average-action numerators use the same factor n and row denominator A*d.
The accumulator verifies raw denominator, action-menu and exponent stability.
This boundary deliberately requires the current native canonical representation;
the per-board comparator separately accepts semantically equal unreduced ratios.

It does not multiply arbitrary denominators at every addition. The previous
saved-only comparator must first prove every incoming row against the independent
sampled reference. Final normalized values are compared against the separate
q-free joint-world expected update. Agreement between proposal laws is insufficient.

## Complete owner and resource contract

Each owner belongs to one fixed PROOF9 proposal law. Every add rejects duplicate
boards, and any failed add consumes the owner. Finalization also consumes it,
including failure. No public method exports a partial expectation. Success
requires 2,520 distinct canonical boards, 107,080 row-record visits, 24,420 unique
full physical rows and 58,164 unique ordered action slots. Valid distinct boards
of that count exhaust the known proposal universe. Full keys are retained;
local native history IDs never identify rows across calls.

A raw native integer has at most 384 bits. Board numerators are at most 9,
board denominators at most 12,600, and there are 2,520 contributions. Corrected
retained denominators need at most 398 bits. Summed weighted numerators need
fewer than 400 bits, including signed regret partial sums by absolute-value
bounds. A checked 512-bit storage ceiling leaves room while rejecting before
any integer sum or product whose conservative width exceeds it. The enclosing
exact Budget admits up to 8,192-bit intermediates for comparison with q-free
reference scalars bounded to 4,096-bit numerator/denominator inputs.

The complete owner reserves row-record upper Rv=107,080, action-record upper
Sv=4*Rv, final rows R=24,420, slots S=58,164 and full-history tokens H=249,662.
Let Vv=2*Sv+Rv and V=2*S+R=140,748.

- Named work reserves `64*15*Rv + 32*Sv + 12*Vv + 8*V + 100000`.
- Retained logical entries reserve `32*R + 8*S + 4*H + 8*2520 + 8192`.
- Cumulative created integer bits reserve `6000*Vv + 32768*V + 2048*Rv + 8192*2520 + 1000000`.

The 6,000-bit term covers checked integer input, optional small-factor multiply
and signed accumulation for each visited scalar; 32,768 covers each final exact
ratio/input/cross-product comparison. Separate row-denominator and board-level
cancellation terms are charged explicitly. Named-loop scans, Fraction operations
and bounded integer forecasts are logical models, not CPU, heap or RSS bounds.
The dynamic receipt is checked after every add and again before final success.
The meter persists for the entire law and is never reset. Both owners must be
included separately in the eventual whole-study allowance.

Raw parsing and per-board exact comparison retain their own separately composed
allowances. Reference setup, q-free computation, numeric export, all logs and
artifact/source preservation still need the complete experiment's admission.
This component does not increase any native game limit.

## Executed controls and limits

Four controls pass normally and optimized: exact partial sums under both laws,
board-numerator cancellation, duplicate and denominator-drift rejection with
failed-owner reuse rejection, incomplete-coverage finalization rejection, and
reduce-only full-owner admission. The controls use saved synthetic frames and
inspect partial internal state only to check exact arithmetic; they never call
a producer. There is no successful complete-stream finalization test yet. That
positive gate is required in the real all-outcome proof, along with independent
q-free expectation identity and real saved corruption witnesses.

Actual sampling, changing-policy reach, bounded persistent learning storage,
convergence and whole-game saved-policy/best-response validation remain open.
