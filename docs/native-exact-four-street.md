# Native exact-product four-street implementation boundary

Status: implementation in progress. The accepted Python exact-product and
quotient paths remain references. A bounded native rational conversion boundary
and offline pinned build are implemented; no native exact poker solver or speed
result is accepted yet. Conversion evidence and full-game implementation are
separate acceptance stages.

The [integrated whole-game candidate](native-exact-whole-game.md) now connects
the native kernel, verified public/Q plan and full learning loop in one explicit
process. Development complete-policy/eight-metric parity passes; frozen evidence
and publication CI remain separate acceptance gates.

The [quotient profiles](suit-quotient-storage-result.md) identify repeated exact
query preflights/arithmetic and learning-loop operations. The
[per-decision lookup](batched-suit-row-lookup-result.md) removes one measured
history bottleneck while preserving complete policies. The next implementation
moves exact callback arithmetic and the alternating CFR+ loop into one native
process, avoiding a Python/native round trip for every terminal query. Python
can remain the rule/topology preparer, API and independent diagnostic/reference
layer where justified; native computation must not retain Python world or pair
tables as its hidden preparation cost.

## One game, a new explicit protocol

Use a separate native protocol/executable from the legacy selected-DAG helper.
Inputs contain canonical role-ordered physical holdings with original binary64
weight bits; canonical flop plus ordered turn/river selections; the admitted
unique public DAG with complete ordered action fields and original terminal
money bits; Q representative keys/menus and verified suit group; requested
iterations; and complete resource/provenance limits. Public histories remain
full actor/own-hand/visible-history identities. No complete world table,
private-pair edge/mass table, trusted normalizer or Python rank vector is sent.

The first target is the same bounded four-street game with expanded complete
policy output. Native code computes global exact normalization, blocker-aware
mass/payoff vectors, on-demand own ranks, once-rounded callback values and the
full zero-delay alternating CFR+ trajectory. Python's existing physical
numeric/exact replay certifies saved complete outputs independently. Existing
public diagnostics can remain in Python initially; their cost and preparation
are part of complete-call measurement. This is not an instruction to preserve
Python merely for convenience or a claim that this boundary is optimal.

Do not mutate or silently replace old native wire formats, existing defaults,
probability guards, exact-product law or numerical trajectory. Unsupported
native combinations, builds, protocol versions, inputs and numerical/resource
failures reject explicitly without fallback.

## Exact arithmetic and conversion prerequisites

Evaluate a pinned Boost.Multiprecision standalone `cpp_int` header closure under
the Boost Software License with a project-owned bounded arithmetic layer.
Source/build identity and license must be retained, dependencies acquired into
an external build cache, and no system installation required. A successful
positive-integer probe is not a signed rational kernel or solver acceptance.
The project retains responsibility for width, scratch and modeled work admission
before arithmetic allocation; an arbitrary-precision library is not permission
to allocate without a cap.

Parsed binary64 weights are exact integer significands times powers of two.
Normalize one common exponent per seat, compute a single global integer Z over
all compatible selected-board occurrences with card-bucket exclusion, and never
renormalize a public prefix locally. Align each complete opponent reach vector
to one dyadic denominator. Signed fold/showdown sums use global seat identity,
original matched contribution, physical blockers and exact rank comparison.
Rank vectors may use an admitted solve-local board LRU; no pair-rank matrix is
retained. Current kernel/general query bit and full-request caps remain active.

Implement integer-only rational-to-binary64 round-to-nearest/ties-to-even,
packing the final bit pattern without intermediate floating arithmetic.
Exact zero maps to positive zero. A nonzero completed rational is accepted only
when its rounded value is finite and normal. In particular, an exact magnitude
slightly below the minimum normal can round to that normal and must be accepted;
checking the unrounded magnitude first would be wrong. Quotient/remainder tie
logic must cover carry into the next exponent, maximum finite/overflow and
normal/subnormal boundaries. Bound conversion temporaries separately rather
than silently widening the exact query cap when shifting a full-width operand.

Hardcoded expected bit patterns and independent Python Fraction conversion must
agree on ties, `1/3`, cancellation, both signs, minimum-normal midpoint, tiny
rejection and maximum-finite overflow. Randomized bounded differential vectors
supplement those anchors. Admission rejection must occur before expensive
ranking or training for unsupported requests.

## Learning and row-storage invariants

Keep fixed action arithmetic and sorted finite chance components with canonical
positive zero. Preserve local subnormal intermediate operations where the Python
numerical contract allows them, while retaining strict completed-query conversion.
Reject nonfinite intermediates and incompatible binary64/toolchain behavior.
Compiler options must prohibit reassociation/contraction that changes the
published trajectory.

Native Q storage retains four numeric arrays and no expanded R-member lookup.
Procedural distinct-image ordinals handle stabilizers. Every responder and
average phase includes all supported members, including zero-reach rows, stages
one unchanged increment and validates bits/menus/complete masks before persistent
commit. Summing or averaging orbit increments changes the reference trajectory.
Only after numeric buffers release may complete R policy output expand. Output
and diagnostics can remain the next storage bottleneck.

## Implemented converter prerequisite

[`exact_binary64.hpp`](../native/exact_binary64.hpp) uses pinned standalone
Boost integers to compute exact quotient/remainder and pack binary64 bits.
Input integer magnitudes are capped at 65,536 bits; separately admitted
conversion scratch values are capped at 65,589 bits. Callers may lower those
limits. Every conversion shift is checked before allocation. These are integer
value widths and logical work receipts, not a Boost allocator or runtime bound.
The extra 53 conversion bits do not widen the exact poker query cap.

The versioned [`probe`](../native/exact_binary64_probe.cpp) is a bounded boundary
test driver. It is not a registered solver backend. It accepts signed/positive
hexadecimal numerator/denominator records, bounds tokens before integer growth,
and terminates immediately on an overlong line. Its integer input does not
authorize trusting Python-precomputed poker payoff or probability vectors in a
future native solver.

The [offline builder](../scripts/build_native_exact_four_street.py) authenticates
all 198 packaged upstream headers, the license, source manifest and project
source before compiling outside the checkout. It rejects changed cache bytes
and records compiler, strict flags, complete source and executable hashes.
There is no network fetch or global dependency installation. Native compilation
and explicit provided-binary provenance failures fail tests; only the absence
of both a compiler and an explicitly selected executable may skip them.
The [dedicated CI](../.github/workflows/native-exact-boundary.yml) requires built
Windows/Linux tests and Linux ASan/UBSan controls. Its results remain a gate until
observed on the final published source.

Development checks cover exact expected rounding bits, 192 seeded Fraction
comparisons, hostile input, maximum widths and reduced/non-raising limits.
Terra's separate authenticated control compares 5,966 signed boundary and skewed
large-integer cases against Python Fraction, finding no counterexample. These
checks establish conversion behavior on the recorded MSVC build only. They do
not establish mass/payoff, ranking, traversal, policy quality or performance.
The [frozen conversion record](native-exact-conversion-result.md) retains the
complete raw protocol streams and authenticates all 1,988 committed source files
before a second saved-only Fraction replay, with no candidate execution.
Preserved initial driver-error classification and stale-build rejection notes
are summaries; the original first failure streams were not retained. That
development evidence gap is not reconstructed as a raw log.

## Acceptance sequence

1. Verify pinned dependency/compiler/license closure and bounded signed integer
   operations; compile conversion tests with strict floating settings.
2. Compare completed native mass/payoff vectors with independent physical
   Fractions, including blockers, shared futures, non-power-of-two Z, ties,
   cancellation, both seats and meaningful private-flush payoffs.
3. Connect the native queries to the same admitted complete four-street root and
   native alternating/Q learning loop. Compare all complete policies and eight
   metrics; independently replay saved policies and exact best responses.
4. Freeze source/build/inputs, measure complete calls and separately scoped
   memory, preserve every miss/rejection/failed attempt, and run native/sanitizer
   and Python compatibility CI before accepting publication.

Capacity, successful training, policy quality and general scalability remain
distinct. Existing original-game T1000 admission rejection, broader convergence,
asymmetric row growth and scalable independent certification remain unresolved.
