# Linear sweep averaging in the nine-card study

The named `--proof9-linear32` profile accumulates the frozen policy at sweep
`t` with own-reach weight `t`, for exactly 32 simultaneous CFR+ sweeps. It
uses the game and update recurrence from the [equal-weight study](native-dyadic-quality32.md).
The target is exact saved-policy exploitability at most 0.1 big blinds. The
equal-weight result was 0.3969423992 big blinds.

For a row event with unnormalized mass at most one and payoff denominator
`D = 580 * 2^625`, the weighted average mass is at most
`(1 + ... + 32)D = 528D`. The coefficient `528 * 580 = 306240` lies between
`2^18` and `2^19`, so the retained width remains 644 bits. Multiplication by
an integer sweep weight preserves the existing per-row shifts. The trainer
applies the weight to a checked scalar marginal before multiplying by own
reach. Each frozen walk owns one immutable sweep weight for all four streets.

The independent rank-free census projects 5,654,252,293 modeled work units
including checkpoint transport. Compiled admission matches the forecast with
270,172 entries, 255,885,592 payload bits, and a 171,408,812-byte wire allowance.
The estimate includes weighted averaging and final average quantization.
The fixed pager and row directory geometry is shared with the equal-weight
profile.

The independent replay checks all 32 current policies, root values and
checkpoint digests, reconstructs the complete wire hash, and computes the
final policy and visible-information best responses. The comparison with
the equal-weight study checks every current policy and root block. The
accuracy outcome awaits a frozen run.
