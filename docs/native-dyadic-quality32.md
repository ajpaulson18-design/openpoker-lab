# Named nine-card 32-sweep quality study

This opt-in development profile keeps the existing N9 game, ranges, betting
rules and 52-bit policy grid. It requests exactly 32 simultaneous CFR+ sweeps
with equal own-reach average weights. Its command is
`--proof9-quality32`. The old two-, three- and four-sweep profiles retain
their existing bounds and wire formats.

The predeclared final quality target is exact saved-policy exploitability at
most **1/10 big blind** in this fixed game, with BB=1. Exploitability is half
the sum of the two visible-information best-response gains (NashConv/2).
The verifier returns the exact rational value and a separate pass or miss.
A successful numerical replay does not imply that this quality target passed.

## Width and storage admission

Write `D = 580 * 2^625`. Every global unnormalized row event has mass at most
one. Action counterfactual values have magnitude at most `8D`; frozen-policy
mixes have the same bound. Each regret increment is at most `16D`.
Clipping with CFR+ gives `R_t <= 16tD`, so at sweep 32 the retained regret
bound is `D << 9`, with bit length 644. Equal-weight average masses are at most
`D << 5`, with bit length 640. Arithmetic retains a 702-bit allowance.

The existing average and regret row shifts remain valid for all later grid
policies. The independently recomputed 644-bit census is 258,694 average limbs
and 348,036 regret limbs, or 606,730 image words. Full visible history remains
part of information-set identity. No posterior renormalization, delayed
averaging or policy-dependent precision assumption is introduced.

Q32 uses sparse pair contractions, the three-plane linear board-set cache,
whole-row staging, a paged row directory and shared policy spill.
The named lifecycle keeps every owner and cumulative meter alive for all 32
sweeps. It reserves 32 generation receipts plus a separate caller copy.
Its State payload uses the conservative legacy formula and extra row codec
storage; the ten-card phase payload formula is not applied.

The complete rank-free forecast calibrates every component against the
accepted N9 four-sweep study before projecting the longer lifecycle.
New Q32 ceilings are 400 million Chance work, 220 million history work,
725 million State work and 1.87 billion quantizer work. State's combined
owner ceiling is 2.60 billion. The complete numerical and transport request
has a 5.80 billion ceiling. These are modeled operations, not CPU instructions
or wall-clock promises. Existing owner profiles retain their previous caps.

## Checkpoint and quality acceptance

Every completed sweep emits an ordered frame and digest. Replay independently
reconstructs all 32 grid policies, regret and average recurrences, checkpoint
digests and root values before the final policy and legal best responses.
Only the final two mutable images remain in the page store.

The transport admits 171,408,812 bytes, including 32 frames of 4,853,840 bytes,
32-byte frame headers, and the 16,084,908-byte retained numerical stream.
Its separate checkpoint copy charge is 39,136,896 modeled operations.
Whole-row paging admits 3,931,620 logical requests, 30,657,954 physical read
words, 19,415,360 write words and 63,264 write runs. The row directory admits
3,174,600 reads and 18,942 cache misses.

The 72 focused controls pass both normally and with Python optimization enabled.
They include compiled Q32 preflight, short storage and precision rejection,
legacy admission snapshots, policy division, page crossings, checkpoint capture
and independent replay transport. The initial compiler diagnostics and harness
failures are preserved separately. A source-frozen native run with saved-only
replay remains the next acceptance gate. A target
miss will be preserved. This profile establishes no unrestricted Hold'em
accuracy or full-deck admission.
