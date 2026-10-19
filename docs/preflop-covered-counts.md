# Covered prepared preflop ranges

This explicit path extends the number of private-hand pairs whose **already
prepared** full-board counts can be used in finite preflop betting. It adds no
new board enumeration. The original `FullBoardEquities` preparation/solver APIs
retain their four-compatible-pair and ranking caps, literal defaults and payloads.
The shared CFR/CFR+, native backend and betting kernels remain unchanged.

## Inputs and information boundaries

`pool_preflop_equities_by_suit(sources, sb_range, bb_range)` in
[`preflop_covered_equity.py`](../pokerlab/preflop_covered_equity.py) accepts up to
32 ordinary validated source tables. Before orbit lookup or output allocation,
it admits up to 128 hands per player, 4,096 candidate pairs and 128 compatible
pairs. It validates source tables and rejects conflicting counts within an
ordered joint suit orbit. Every requested pair must be covered; no missing
pair is estimated, dropped or enumerated.

A **single bijection of all four suits** maps both ordered private hands and
all possible boards. It preserves blockers and W/T/L totals, while target range
weights are conditioned globally after collisions. Private hands and pair priors
remain distinct. There is no assumption that asymmetric weighted ranges are
strategically interchangeable. The existing project-owned 24-permutation
canonicalizer supplies the map; no external source code or dependency is used.
[Waugh's published treatment](https://www.cs.cmu.edu/~waugh/publications/isomorphism13.pdf)
provides mathematical context for suit-isomorphism indexing.

The returned frozen `CoveredPreflopEquities` records counts, exact Fraction
priors, categorical worlds, detached budget metadata and source/target endpoints,
full suit permutations and source count identities. Structural checks and
fingerprints are not physical authentication: callers must supply trusted
counts. Ordinary source table validation alone likewise cannot prove ranking
correctness. Tables retain no live mutable references to their sources.

## Shared solving and full-request admission

`solve_covered_preflop_checkdown(table, ...)` in
[`preflop_checkdown_solver.py`](../pokerlab/preflop_checkdown_solver.py) accepts
only the separate covered type. It uses prepared-count admission, default
pair-mean world indexing, and the existing betting/training/evaluation body.
Categorical indexing and explicitly source-built native training remain optional.
The original solver rejects covered tables, and the covered entry rejects an
ordinary table. Native limits are unchanged.

The separate covered work-budget versions retain the existing 10,000-decision,
250,000-state, one-million-action-slot and 500-million-loop ceilings. The full
requested training, exact diagnostics, table validation and provenance/output
work must be admitted before betting-tree allocation or native invocation.
Prepared tables report zero current rank calls and board combinations. A
physical coverage count above the preparation cap authorizes no new enumeration.
Modeled work counts are neither CPU-time predictions nor allocated-memory/RSS
bounds. No source-inclusive preparation bypass is exposed on the new entry.

Output adds only explicit `equity_coverage` and `count_provenance` metadata to
the existing preflop row schema. Policies depend on own hand/public betting
history; future cards and opponent hands remain hidden. All closed nonfolded
lines force full-board checkdown. Later-street betting and multiway equilibrium
remain unsupported.

## Independent validation and preregistered physical fixture

The numeric-rule replay has an explicit `covered_counts=True` mode, preserving
its old four-pair mode by default. It checks full endpoint suit maps and validates
all actions, counts and global priors against separately supplied physical
inputs before computing exact rational profile values and legal own-hand best
responses. Provenance never supplies a payoff or chance probability to replay.

[Focused tests](../tests/test_preflop_covered_equity.py) distinguish a synthetic
36-pair AA/KK routing test from real physical evidence. Synthetic values check
all three relative-suit overlap classes and known-value mechanics; they are
not poker-equity measurements. Additional tests retain every compatible pair,
check exact weighted blocker conditioning, reject conflicting/unsupported
sources, prove caps precede orbit work, preserve old admission, reject work
before tree construction, and independently replay both Python/native outputs.

The [frozen benchmark](../benchmarks/preflop-covered-counts-v1.json) uses SB
`AdAs:1,QdQs:.5` and BB `AsKh:.25,AsKc:.5,AdKh:.75,AdKc:1,KdKs:1`.
The four AK candidates collide with AA but remain compatible with QQ, giving
six physical pairs and five BB private hands. Three pinned independent count
rows cover every pair through joint suit maps, representing 10,273,824 boards
without a new rank call. Blinds 0.5/1, stacks 4/3 and two configured raises
retain limps, the BB option, all-ins and refunds.

The [runner](../scripts/benchmark_preflop_covered_counts.py) requires clean
committed source and all four Python/native full-request admissions before
native build lookup/training. CFR+ checkpoints are 10, 100, 1,000 and 3,000;
three alternating final pairs must be deterministic, independently replayed,
and meet 0.005-chip NashConv. Backend metric/probability gates remain `1e-8` /
`1e-6`, replay tolerance `1e-10`. Early misses and all failures are retained.
The changed weighted game has no separately claimed exact equilibrium value.
Complete-call timings include canonical serialization/hash and have no speed
gate. Memory is unmeasured.

## Clean-source physical evidence

The [raw report](../benchmarks/results/preflop-covered-counts-v1.json) passes
from clean source `e5dea4ea0193b682bb856c9b3eb7df9f3a53891c` on Python 3.12.14 /
Windows and the identified strict MSVC native V2 build. Source/build identities
remain unchanged. All 471 LF source hashes independently match normalized Git
blob contents at that freeze. All four full-request Python/native preflights
pass before build lookup, with maximum modeled totals 301,442,176 / 113,217,104
under the unchanged 500-million ceiling.

The six priors are exactly `4/11`, `1/22`, `1/11`, `3/22`, `2/11`, `2/11` in
the report's retained pair order. There are 25 actual public states, nine betting
decisions and 33 own-hand information rows. Histories include both
`call / raise@2 / all_in@4` and `raise@2 / all_in@3`, demonstrating actual
reraises rather than only a configured cap.

| CFR+ iterations | Independent Python NashConv, chips | Target met by both backends | Final median complete Python / native seconds |
| --- | ---: | --- | ---: |
| 10 | 0.0154701572 | No, retained early miss | unavailable, one sample |
| 100 | 0.000168486861 | Yes | unavailable, one sample |
| 1,000 | 0.00000170001727 | Yes | unavailable, one sample |
| 3,000 | 0.000000189016694 | Yes | 3.529355 / 0.040915 |

All 12 complete-call payloads pass fresh saved-file exact numeric-rule replay;
all six paired comparisons pass unchanged gates. Final payload hashes are
identical within each backend across three repeats. Maximum scalar gap is zero
in the retained binary64 metrics; maximum action-probability gap is `4.441e-16`.
Every measured ranking/enumeration guard is zero. The final independently
replayed SB equilibrium-value bracket is approximately
`[0.540488844470152, 0.5404890334868454]`, with exact fractions in the report.
No exact equilibrium-value certificate for the changed weighted game is claimed.

Native complete calls are faster at the final checkpoint on this fixture; at
10 iterations the measured native process overhead makes it slower. Allocation
and RSS were not measured. No general performance claim follows.

Canonical report SHA-256:
`a0a8644de32cead9f081c88ae50e980bc958bc4b611f175b887676b4463984eb`.
Raw saved-file SHA-256:
`0f436faa5c7909617db2ead4ec39a23fafe1876ae56c6365f37283af0489eaf6`.
The numerical source/specification were committed before measurement. Publication
adds only this evidence, documentation and a saved-artifact regression; final
cross-platform CI and GitHub merge state are recorded on the pull request.
