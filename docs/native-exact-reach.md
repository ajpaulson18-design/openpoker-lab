# Exact opponent-reach transport

Status: implemented with source-only development conformance. Committed-source
component acceptance and final CI remain pending. This is a prerequisite for the
unchanged four-street training objective; changing-policy training, policy
quality and unrestricted full-deck solving remain unfinished.

`PublicChanceKernel::terminal_exact_reach` in
`native/full_deck_public_chance.hpp` accepts the original opponent holding order,
integer reach numerators and one common positive denominator. Each sequence
reach is exactly `n_j / D`, with `0 <= n_j <= D`. Caller-owned input storage and
construction of the common denominator require separate parent admission.
No reach value is converted to binary64 inside this entry point.

## Units and shared evaluation

For the original queried player i, the exact returned terminal vector is

`wi * sum_compatible_j(wj * (n_j/D) * utility_ij) / (Z*d5*q(board))`.

Own prior appears once and own preceding action reach is absent. The board is a
canonical flop and ordered turn/river; fold payoff carries the queried player's
sign, while showdown stake is nonnegative. The declared deck and joint prior
are exactly the existing [public-chance contract](native-full-deck-public-chance.md).
Every numerator is validated, including blocked holdings and off-path zeros.
Inputs may use unreduced fractions. A positive exact reach can be smaller than
the smallest binary64 value without losing its contribution.

With integer prior normalizer Zint, common reach denominator D, signed binary64
payoff significand s and exponent e, output integers represent

`numerator_i = Wi * compatible_sum(Wj*n_j*sign_ij) * s * qden * 2^max(e,0)`

`denominator = Zint * d5 * D * qnum * 2^max(-e,0)`.

The existing double-reach API and the new exact entry share one blocker/rank
evaluator. The old path retains its original aligned reach exponent in the
payoff shift and its nonzero-input test before board blockers. Raw compatibility
checks cover its outputs and every serialized receipt field. Existing entry
points, defaults and numerical limits retain their behavior. Neither path
retains a private-pair coefficient table, board list or complete-world table.

## Admission

All original reduce-only ceilings remain: 500 million modeled work, two million
logical entries, 65,536 integer bits and 2^30 integer payload bits. Constructor
and prior queries consume the same owner allowance. Exact input scans/comparisons
are additionally charged before execution. Complete numerator, denominator and
bucket-intermediate width forecasts precede query arrays and ranking.

Let h be total original holdings, B the admitted maximum integer width and
L = ceil(B/64). The new query keeps the old fixed query/rank/sort charge and adds
`(4096 + 64*h) * L^2` logical word-width-product work. Input comparisons add
`16*max(qnum_bits,qden_bits,D_bits,1)` and `16*(n_j_bits+D_bits)` per holding,
after the fixed dimension/board scan charge. Query scratch remains `24*h+2048`
entries; the parent separately admits retained inputs and output lifetimes.
These are logical accounting models, not measured machine instructions, Boost
allocation bounds, CPU time or process RSS. No whole-training admission follows.

## Executed development evidence

A strict MSVC build and 22 combined controls pass normally and optimized through
the trusted one-buffer source-only loader. All project raw files remain stable
across both modes, final compiled-byte receipts are retained and both observed
outer exits are zero. This development checkout includes uncommitted changes;
the result is not labelled committed-source acceptance.

Each mode compares all 2,520 physical public boards for six exact reach vectors,
both original players and four signed/payoff cases: **120,960 terminal vectors**.
A literal physical-pair oracle uses a separate best-five ranker and exact
Fractions throughout. Fixtures include a 106-bit product from binary64 action
probabilities, an odd common denominator, all-zero reach, unity, reach below
binary64 range, and a positive raw payoff exponent. Thirteen invalid-input and
resource controls enter no rank call or completed terminal query. Source review
confirms their checks precede query scratch allocation; these counters are not
an allocator-wide observation.

For **10,464 requests per mode**, raw legacy responses match a fresh source-built
active baseline at `9dbf1ef9f42c0e63be96c4391f7084b8444e009f`. This includes all
boards, folded/showdown values, zero and blocked reach, extreme reach exponents,
large positive payoff exponents and binary64 conversion. Requests, stdout,
stderr and observed exits are saved before comparison. The baseline is the
active pre-change source, with compiled-input/compiler/executable identities;
archived historical repair sources are not executed.

The first 90,720-vector development version and its 13 guards are preserved. Its
new build target initially inherited an overly broad default manifest scope;
the current explicit scope corrects that metadata. The later version also adds
the positive-exponent fixture and raw compatibility check. Neither version is
an engine or complete-game result. See the
[development manifest](../benchmarks/results/native-exact-reach-development-v1/manifest.json).

Windows/Linux and sanitizer CI now build both exact-reach controls and the
explicit active baseline. Their actual final-head outcomes remain a separate
publication gate. The full fixed-profile study continues in its unchanged source
freeze, with [saved-only acceptance](virtual-frozen-saved-review.md) queued.

## Committed component procedure

The source-only entry `scripts.run_native_exact_reach_conformance` captures the
complete candidate and active-baseline committed/raw source trees before
mathematics. It builds fresh current exact/legacy probes and a separately
source-only baseline probe. Every declared compiled source digest is bound to
the corresponding captured tree immediately after its build, with exact input
set, extracted-header and executable/compiler checks.

The controller runs 34 controls in each mode: the 22 numerical/build controls
and 12 controller/process guards. It rejects skipped or incomplete suites,
preserves first errors and never retries an output directory. Each native call
has executable identities recorded before/after. Legacy probe batches stream
bounded logs: at most 128 independent records, each at most 1,025 LF-framed
bytes, aggregate request at most 65,536 bytes, stdout 2.1 MB, stderr 64 KiB and
120 seconds. The original single-request observation API retains its 1,025-byte
ceiling. This aggregate test transport does not admit a training owner.

Before launch, five controller and seven process controls pass, including
compiled-source mismatch before binary admission and an actual oversized child
stream stopped at the batch output ceiling. The complete committed cohort has
not yet launched. An 8 GiB evidence allowance covers both source trees, fixed
test streams and build artifacts; kernel ceilings are unchanged. Invoke through
the trusted one-buffer bootstrap with `--output`, `--expected-head` and
`--baseline-repo` pointing to the clean active `9dbf1ef` checkout. The final outer
exit and bootstrap receipt remain required after the inner terminal claim.

## Next integration

The generic rational input API alone does not solve policy/value denominator
growth. The next proposed deterministic trainer uses exact dyadic policy units
on a declared 2^52 grid, with largest-remainder allocation from nonnegative
regret integers and deterministic legal-action tie breaks. Keep cumulative
regret and average masses on a fixed game denominator. This is an explicit
finite-grid numerical contract; small positive action weights can quantize to
zero, so independent exported-policy and visible-information best-response
quality remain required.

For exhaustive reveals with proposal q=1, a fixed denominator based on
`Zint*d5*2^(52*H+money_shift)` can cover terminal opponent reach and subsequent
own-action mixing, where H bounds all decisions on a full history. Early folds
need a visible-prefix payoff query with divisor d_k, scaled by d5/d_k. Pruning
may use zero prior physical mass at the current prefix, independently of policy;
zero-policy actions and counterfactual rows remain. These further operations,
persistent row storage and a full-request training forecast are not implemented
or admitted here. Training runs remain gated on the complete frozen identity.
