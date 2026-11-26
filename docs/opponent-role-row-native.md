# Compact policy-role row arithmetic gate

Status: source design for an explicit native component, following the passed
[conditional moment gate](opponent-action-moment-gate.md). Execution acceptance
is separate. No shared trainer, History, Catalog, Store or default is changed.

The proven per-transcript role scales are `R/2^365` and `A/2^52`; canonical
expected/full-walk scales remain `2^625` and `2^364`. Multiplying every signed
regret coordinate by the same positive `2^260` preserves signs, positive
weights, exact quotients, remainder order and legal-order ties in Q52 regret
matching. The corresponding `2^312` average scale also preserves normalized
average images. Cumulative signed regrets remain unclipped. This identity
couples the same sampled raw increments; it does not equate sampled learning
with the full deterministic walk.

An explicit [row owner](../native/opponent_role_row.hpp) reuses the unchanged
native Q52 Quantizer, with a tighter 426-bit arithmetic allowance. At most two
steps per row and 204 rows are admitted before proportional allocations.
Each step checks exact centering on its frozen Q52 policy and requires average
increments to equal that policy or zero. Regret magnitude is at most sixteen,
average coordinates at most one, cumulative integer widths at most 371/54.
Failures poison the component. These numeric checks cannot certify which
History role was visited: a genuine two-target role lease is still required.

The frozen scalar envelope reserves 8,000 Quantizer work per step (the
unchanged separate kernel's 371-bit/four-action bound is below 5,200), plus
2,048 parent work, under a five-million component work allowance. Rows, steps,
entries and payload limits are reduce-only and smaller than the old general
Quantizer limits. The whole component envelope includes 13,312 entries and
882,352 payload bits. Fixed probe input/output bounds are 116,000/131,072
bytes; this is not whole-game admission or measured memory.
The shared process runner's 1,025-byte pipe-input limit remains unchanged:
the probe reads an explicitly named regular external file under its existing
116,000-byte input cap, with every raw payload and before/after identity saved.
The first attempt's guards pass, then its oversized pipe request refuses
before the matrix launches. Both original mode attempts remain preserved.

The probe must compare compact cumulative R/A and policy units with a second
unchanged native Quantizer using the canonical carriers. A separate Python
Fraction allocator then checks every emitted coordinate. Inputs retain all
85 role rows from the three-world/two-profile supported witnesses and twelve
two-step synthetic controls, including zero policy, tiny signed regrets,
negative cumulative coordinates and a zero update that preserves a frozen
nonuniform policy. A coprime full-width case reaches the 371-bit cumulative
bound without a common dyadic factor, including tiny positive regrets rounded
to zero. The first successful 96-row study is preserved before this additional
coverage; it does not exercise the maximum division width. Twenty native
failure guards and six negative child
requests preserve actual exits and private-output behavior. Both Python
modes must emit identical numeric frames.

The native Quantizer already cancels a common power of two before division.
Consequently smaller raw carriers need not reduce its division widths: any
claim of computation savings must identify the actual counters and eventually
measure complete work. This gate establishes arithmetic feasibility, not a
runtime speedup. Later native integration must preserve full-history keys,
true-joint physical chance, independent root estimates, separate regret/average
roles, complete resource accounting and the original lifetime/quality gates.

The [explicit build wrapper](../scripts/build_opponent_role_rows.py) retains
the unchanged compiler/dependency engine and captures every introduced source
against committed Git before compilation. The [study controller](../scripts/run_opponent_role_rows.py)
captures its complete source before mathematical imports and all eight native
calls. No archived source or RNG is used.
