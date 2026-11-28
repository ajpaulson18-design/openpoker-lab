# Longer-run state and transport frontier

The current full52 role trainer supports exactly two deterministic epochs.
The new rank-free worksheet identifies the first obstacles to extending it:
ticket framing and repeated full snapshots fail before regret widths at
three epochs. Smaller integers alone cannot establish practical training.
No longer run, transport change, resource increase or quality is admitted.

This reassesses the next step after the
[native compact Store](compact-role-persistent-store.md) and
[structural row-carrier proof](role-row-depth-carriers.md), using the current
complete native/reference reservations rather than increasing their caps.

## Frozen framing and width equations

For a hypothetical `N` worlds, use the existing per-world conservative bounds:
204 raw/retained rows and 816 action slots. Distinct-world overlap can reduce
actual storage; these are upper projections, not expected occupancy.

- Existing u64 ticket input: `32 + 1664*N` bytes. Per world this reserves
  two selectors, two u64 counts and at most 204 Q52 tickets across both roles.
- Existing canonical snapshots after every world:
  `368 + 82456*N + 125664*N*(N+1)/2` bytes. The triangular term retains all
  prior rows/slots again; this is a framing cost, not new information sets.
- Compact retained R/A magnitude widths are bounded by
  `365 + bit_length(16*N)` and `52 + bit_length(N)`, from per-world raw
  bounds `16*2^365` and `2^52`. The current 371/54 widths still cover N=3;
  N=4 requires 372/55. Full native lifetime remains exactly two.
- With the current conservative Catalog geometry `B=M=204*N`, each lookup
  costs `5800 + 32*bit_length(B+1)`, with setup `1024+16*B`. Repeated
  snapshots require `612*N + 204*N*(N+1)/2` lookups.

At N=2 these reproduce 3,360 input bytes, 542,272 worst framed output bytes,
11,185,120 Catalog work and 371/54 compact widths. The actual reservations
remain 4,096 input and 549,280 output bytes. The unchanged full native work
and independent reference reservations are 124,410,460 and 499,975,808.
No tree, hand, rank, world, policy or producer preparation is executed.

| Projected N | Current ticket bytes | Repeated canonical snapshots | Catalog work |
| --- | ---: | ---: | ---: |
| 2 | 3,360 | 542,272 | 11,185,120 |
| 3 | 5,024 | 1,001,720 | 18,738,016 |
| 4 | 6,688 | 1,586,832 | 27,480,640 |
| 5 | 8,352 | 2,297,608 | 37,471,744 |
| 6 | 10,016 | 3,134,048 | 48,965,920 |

Thus N=3 exceeds current input/output reservations. N=5 exceeds the existing
shared 2.1M output ceiling; N=6 exceeds the 42M Catalog ceiling. Under the
same fixed full1326 law/template plus per-byte accounting, source plus I/O
alone reaches 506,229,696 at N=3, before any sampled-update charge, against
500M reference work. This is a partial accounting consequence of the frozen
composition, not a lower bound on every possible reference algorithm or CPU.
At N=4 the generic 2,564-slot Store ceiling also fails (3,264 projected slots).
The current role profile and epoch contract reject earlier regardless.

## Hypotheses clarify the design; they are not implemented

Packing each Q52 ticket into 52 bits and each target count into one byte
would give `32+1344*N` input bytes: N=3 would require 4,064, but N=4 still
requires 5,408. It postpones a limit rather than providing a long-run stream.

Keeping raw world/receipt records but only a final compact snapshot would
give `400 + N*(90584+816*S)` bytes, where
`S=8*(ceil((Rbits+1)/64)+ceil(Abits/64)+1)` includes signed R, unsigned A
and one Q52 unit. At N=2/3, S=64 bytes and output is 286,016/428,824.
Final-only Catalog lookup work is linear (`816*N` lookups): N=8 projects
40,187,392, while N=9 projects 45,210,688 and still exceeds 42M.

These are unimplemented layout hypotheses. They omit complete future
read/stage/commit/History/chance/Quantizer/native lifetime and oracle-sample
proofs, so **every future-admission flag remains false**, including rows whose
partial flags pass. There is no T3 special-case implementation.

At one million hypothetical worlds, the final-only layout still projects
155,864,000,400 bytes when every raw record is retained and all rows are
distinct. That is a worst geometry/width projection, not measured memory or
policy-dependent encounter probability. It explains why bit packing alone
does not create a practical full52 training/checkpoint contract.

## Original evidence and next foundation gate

Source `2a49afeffa5174ab8239a026c02be51761a88a74` captures all 20 introduced
Python/native source files before computation. Four bounded original Python
children run three exact accounting/domain/no-preparation methods and the
complete twelve-point worksheet in normal/optimized modes. All exits pass;
worksheet bytes match SHA256
`d650137bae9c36ee30b2d8f3e40cac45dfd5f9f0c1127874ae5d5280d64e697e`.
Every exact argv, observed cwd and Python executable hash precedes its child;
the executable/raw sources/HEAD are rechecked afterward. The environment is
explicitly uncaptured. Native, rank, RNG and preparation calls are zero.

The [immutable packet](../benchmarks/results/role-training-frontier-v1/manifest.json)
preserves all four processes and full sources. Manifest size is 1,485 bytes,
SHA256 `70914a08a2b67ad02b3aba9a4a8975c5f96251df9a6fa2cc6c69541cab316314`;
22 pooled objects preserve 371,798 stored expanded bytes under existing caps.
`python -m scripts.replay_role_training_frontier` authenticates all sources,
commands and exits before current rank-free reproduction. Reader execution
and cross-platform acceptance must be recorded separately.

The next architectural priority is an explicit bounded training/state/
checkpoint contract with complete component accounting and reproducible
random-stream ownership. Preserve complete history and averaging semantics,
atomic state publication, all failures and independently replayable policies.
Distinguish ideal independent-bit estimator arguments from finite seeded
generator assumptions. A smaller value carrier inside the native walk remains
a cost-tested arithmetic candidate, not a substitute for this lifetime work.

The historical [eleven-card exhaustive refusal](native-dyadic-storage-census.md)
is unchanged: State 662,607,040/300M, Quantizer 1,014,146,272/520M and composed
work 5,954,402,351/2,150M. Its parent work alone exceeds the composed ceiling.
No full52 sampled T2 result or partial worksheet overturns that refusal.
Useful longer learning, independent saved-policy quality and practical
realistic heads-up NLHE remain the larger acceptance objectives.
