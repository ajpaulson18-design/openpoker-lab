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
gate. Memory is unmeasured. Formal measurement and final CI/publication are
pending at this source stage.
