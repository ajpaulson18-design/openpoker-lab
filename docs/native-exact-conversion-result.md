# Frozen native exact conversion prerequisite

The [implemented converter](native-exact-four-street.md) is frozen at
`015d20f5f37173333a0a4cdbe7954ecbd2588b5b`. Its
[publication receipt](../benchmarks/results/native-exact-conversion-v1/receipt.json)
retains the exact build manifest, raw integer inputs, candidate outputs/errors,
independent reviewer, source snapshots and saved-only replay. The 40-entry
archive is 1,094,318 bytes, SHA256
`06980116071fcbb99269cf497f8cd5670f621019987a08e5103da036bea5a7bf`.
Its manifest SHA256 is
`72e20d9180aeda36c66d46f12249c95d7ee5a57992424387c17ddfdd21db47a4`.

The current-source MSVC 19.44 x64 C++20 build uses strict floating-point flags
and the complete pinned offline Boost header/license closure. Executable SHA256
is `3594d700380eb4127a12a6ff56ba723b2b6ea1baa5aa83797b48cb18d27059e5`;
build-manifest SHA256 is
`493389b14dc53aa5485714241cf4762a4e871fc5970fb25f206b59aea2769102`.
Twelve compiled/provenance/build-input controls pass normally (9.331 seconds)
and optimized (7.165 seconds). Test durations are validation observations,
not a solver benchmark.

Terra's separate exact Fraction oracle checks 5,966 signed cases: 5,956 accepted
results match exact binary64 bits and ten required normal/overflow rejections
match. Coverage includes adjacent-float ties with perturbations, both signs,
the minimum-normal and maximum-finite boundaries, and skewed integer operands
up to 65,536 bits. The focused controls additionally check exact zero, malformed
records, overlong termination, reduced/non-raising limits and maximum conversion
scratch. Source, binary and manifest remain unchanged across the review.

Sol/root then authenticates all 1,988 captured raw files against the frozen
committed Git closure before independently replaying every saved input/output
with Fraction. That saved-only replay invokes no candidate or archived project
code and imports no production mathematics. Both raw and committed source hashes
are retained; line-ending normalization is used only for equality comparison.

The first driver error-classification failure and stale-binary rejection have
contemporaneous summaries; their original raw streams were not retained. A
separate reviewer smoke fails its final source recheck due to a local variable
shadowing the source-key set after all arithmetic comparisons. Its exact first
input, stdout, stderr, status and traceback, superseded reviewer helpers, and
the repaired review remain in the archive. The production converter is unchanged.

This is the conversion boundary only. It does not establish native poker
normalization, blocker-aware vectors, ranking, Q learning, complete policies or
quality, complete-call performance, or general scalability. Dedicated
Windows/Linux and Linux sanitizer checks pass at the first published code head;
all checks on the final evidence-publication head still govern acceptance.
