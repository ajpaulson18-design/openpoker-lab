# Persistent immutable policy session

The explicit `virtual-frozen-policy-session` target shares one catalog, History,
resident State policy import and Prepared Chance owner across two complete
[fixed-policy raw walks](native-frozen-grid-raw.md). Both results remain owned
until both walks finish. It echoes the complete policy once and publishes one
bounded response. It does not change policies, accumulate numerical State,
clip regrets, select random boards, train or evaluate quality.

This is a necessary setup-amortization gate for a future sampled architecture.
The existing exhaustive trainer and its [native walk profile](native-training-phase-profile.md)
remain separate: State staging/quantization and terminal work are still the
measured training bottlenecks. Sharing a frozen import does not resolve the
[eleven-card resource forecast](native-dyadic-storage-census.md).

## Lifetime and bounds

Both proposal/board selectors validate before shared owners are built. The
session imports/seals one complete Q52 image through the existing State owner.
Each raw walk borrows those same owners and independently evaluates both global
seats, including policy-zero actions and zero-full-target prefix averages.
Selectors may repeat; repeated selectors consume two complete raw lifetimes.
Prepared may reuse its existing bounded rank-plane cache across the walks;
the forecast still reserves each board's complete rank-fill/query allowance.
No per-board State, History or Chance meter resets.

The complete reservation is `C + V(B1) + V(B2)`: shared template/catalog,
input/import/seal, one policy echo and one Chance setup in C; each board's
raw traversal, policy reads, prefix/terminal contractions and retained stage
in V. State read lifetime is `24420 + 2*r1 + 2*r2`. Parent work includes the
catalog once, both six-family raw ledgers and 1,024 session metadata units.
Both retained stages and their scratch bounds count in peak entries/payload.
The 1,040,000-unit source/selector scanner fits inside the existing three-million
geometry family alongside the original 149,420-unit Forecast scanner.

The independent numeric-rule reference proves exact per-axis maxima over
25,401,600 ordered selector pairs (replacement allowed). Every axis separates
as C plus two board contributions, so `C + 2*max(V)` proves its maximum without
materializing the Cartesian product. Maxima need not occur on the same pair.

| Logical reservation | Pair maximum | Unchanged ceiling |
| --- | ---: | ---: |
| Whole work | 316,294,067 | 500,000,000 |
| History work | 39,784,400 | 42,000,000 |
| State work | 55,075,516 | 75,000,000 |
| Chance work | 2,579,498 | 110,000,000 |
| Parent work | 8,209,324 | 115,000,000 |
| Entries | 1,184,881 | 2,000,000 |
| Integer payload bits | 263,169,724 | 1,073,741,824 |
| Output bytes | 1,936,776 | 2,100,000 |

These are logical bounds, not allocator/RSS measurements or CPU shares.
The owner graph still materializes the complete 24,420-row/58,164-slot catalog.
Its conservative storage reservation is unchanged; no wider capacity credit
is taken for policy-only residency.

## Wire and validation

`OPLGEP01` introduces one 136-byte cumulative header, the complete 1,442,112-byte
policy body, two board records and a 208-byte global completion footer. Each
`OPLGBD01` record has a 256-byte reference-schedule header, 264-byte denominator
and roots, raw row/slot payload and a 208-byte delta footer. Its reference
schedule fields describe the existing single-board bound; cumulative admission
and actual totals live in the global frame. Total size is
`1,443,912 + 136*(r1+s1+r2+s2)`. Signed integers retain the existing 704-bit
two's-complement wire carrier and portable 32/64-bit Boost limb handling.

At source `677bf51`, local MSVC compilation and normal conformance pass.
Twelve independent requests cross two complete policy profiles with reversed
board order, repeated selectors, different compatible private pairs, a zero
full-target board with shared turn, a zero-at-flop board, and maximum retained
row/slot staging. All policies, regrets, prefix averages and roots match the
independent Fraction/rules/rank oracle. Per-board State/History read deltas and
all six raw family charges match independent equations; cumulative scope/work,
one import/echo and exact output bytes also match.

Seven further requests reject malformed second proposal/board, arity, extra
selector and late invalid policy partition with no stdout. Saved root-bit and
truncation corruptions reject independently of stream hashes. Maximum observed
modeled work is 223,700,123 and output is 1,936,776 bytes. Optimized conformance
also passes; all nineteen native stdout streams match exactly between modes.
The first source capture omitted the imported raw-reader metadata module.
Its successful numerical observations remain retained, and complete-source
normal/optimized matrices at `09a6309` pass after adding that dependency.
Both complete-source matrices also pass saved-only numerical replay, with
zero native calls. Cross-platform CI and immutable packaging remain separate
checks; no speed acceptance is inferred from logical resource counts.

The session's `domain_*` component values describe the independently proven
axis maxima. Runtime admission enforces its cumulative component forecasts and
original global caps, with additional domain checks for whole work, entries,
payload and output. Neither diagnostic maxima nor per-board reference header
fields reset a shared owner or extend its lifetime allowance.

## Matched cold-setup comparison

The committed operator `scripts.benchmark_native_policy_session` at source
`49b989d1ff90bf62b28d0d6d8c9653998530132f` compared the `zero-skew` profile
on the fixed different-private-pairs selector pair: first uniform, second
weighted river. Its protocol was written before warmup: one warmup group,
eight alternating-order pairs, median ratio at most 0.96 and at least six
faster pairs, zero retries. Baseline time sums two independent existing raw
children; candidate time measures one complete session child. Independent
numerical replay is outside timing. This compares the same two raw results,
including complete native setup and captured output, with one policy echo
instead of two duplicate echoes.

| Observed named workload | Cold pair | Shared session |
| --- | ---: | ---: |
| Actual logical work | 432,087,356 | 221,426,179 |
| Output bytes | 3,292,048 | 1,850,280 |
| Median paired elapsed ratio | 1 | 0.5105145 |
| Pairs faster | | 8 of 8 |

All 27 child exits were observed. Warmups match independent Fraction/rules/rank
replay; every timed complete wire is byte-identical to its verified warmup.
Both old raw payloads and shared policy bytes also match directly across the
two wire layouts. All pairs, including misses if any, are retained. The timing
gate passes on this host/workload. This is cold setup amortization, not a
training-throughput, allocator/RSS, unrestricted-game or universal speed claim.
The two baseline children have separate existing request budgets; their sum
is not presented as one admission. The session has one cumulative admission.

## Immutable evidence and portability

The [packet manifest](../benchmarks/results/native-frozen-policy-session-v1/manifest.json)
pins separate normal, optimized and benchmark archives, plus both superseded
development captures. Each archive stays within the existing 8 MiB compressed
and 80 MiB expanded reader limits. The benchmark archive is 8,339,732 bytes;
no archive limit was increased. Both
[normal](../benchmarks/results/native-frozen-policy-session-v1/archive-replay-normal.json)
and [optimized](../benchmarks/results/native-frozen-policy-session-v1/archive-replay-optimized.json)
maintained packet replays pass: every policy/raw row and all 27 timing-child
streams and durations are checked/recounted with zero candidate calls.
`python -B -m scripts.replay_native_policy_session_packet` authenticates current
bootstrap/helper source before project imports and uses a fresh empty bytecode
cache prefix. Archived source and executables are evidence only.

At source `392cc8bc1ba74c808dfd134ef032dde17d1a8a69`, dedicated Windows,
Linux and sanitizer jobs pass both full conformance modes and saved-file replay.
Windows/Linux immutable packet jobs also pass both modes. The
[job and step receipt](../benchmarks/results/native-frozen-policy-session-v1/ci-392cc8b.json)
records these separately from the broader Windows History-control compiler
failure; this is not a claim that all repository checks pass.

The first Linux/sanitizer builds rejected one misleadingly laid-out footer
loop/check line under the existing warnings-as-errors configuration. Original
[failure artifacts and whitespace-only source comparison](../benchmarks/results/native-frozen-policy-session-v1/portability-repair.json)
are preserved. Splitting the statements changes no tokens or checks.
The repaired local executable has identical `.text`, `.data`, `.pdata`,
`.fptable` and `.reloc` sections; `.rdata` differs, so this is not full binary
reproducibility. All nineteen stdout/stderr pairs match the canonical normal
matrix exactly. The bounded [portability regression record](../benchmarks/results/native-frozen-policy-session-v1/portability-regression.json)
references those already preserved canonical streams and retains the new
binary/build/exit evidence. Historical timing acceptance remains pinned to
its measured source rather than being silently relabeled.

## Next architectural gate

The scoped amortization measurement justifies continuing beyond cold import.
Replace repeated dense immutable import with a
validated changing-policy epoch and sparse/paged numerical ownership. Keep
raw importance-weighted regret estimation distinct from nonlinear CFR+
clipping: unbiased raw updates alone do not prove sampled CFR+ correctness.
Changing-policy quality needs independent saved-policy evaluation and legal
visible-information best responses. Realistic heads-up NLHE, full-deck
capacity, convergence and product readiness remain unresolved.
