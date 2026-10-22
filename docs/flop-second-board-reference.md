# Second flop board: fresh physical reference

The original class solver and weighted-prior evidence use `2c3d4h`.
This separate no-training experiment prepares `7c8d9h` with fresh physical
worlds, public tree and hashes. Its candidate partition is a starting point
for a subsequent full equivalence audit. It admits no training and supplies
no new strategy or convergence result.

## Fixed fixture and prior conditioning

The literal ranges remain OOP `AsAd:1, QsQd:1/2` and IP
`AsKh:1/4, KsKd:1`. The `AsAd`/`AsKh` collision is excluded before global
normalization. Compatible raw products are `1`, `1/8`, `1/2`, with normalizer
`13/8` and exact pair priors `8/13`, `1/13`, `4/13`. Hand identities use the
existing physical parser's lexical card order; literal input labels are retained
separately. The strict immutable planner rejects other boards, weights, support
or type aliases before preparation.

Each private pair leaves 45 future cards and 1,980 ordered turn/river outcomes:
5,940 physical worlds in total. The union of available turns has 49 cards.
The fixed betting configuration is pot 10, stacks 5 each, half-pot bets, no
raises and no explicit all-in sizing. A stack-capped half-pot bet can still
have the numeric action name `all_in`. These are the original finite action
choices on a new board, rather than general no-limit betting.

## Full admission before physical work

The [frozen protocol](../benchmarks/flop-second-board-reference-v1.json)
admits one physical build and one candidate partition, no best responses and
no training. Preparation and fresh-cache rechecking each have a separate
11,880-ranker-call allowance. Each seven-card reference rank uses 21 best-five
combinations: the combined named reservation is 23,760 rank calls and 498,960
five-card combinations. Actual attempts and calls are counted separately;
the preparation wrapper restores the original ranker on every exit.

The existing physical caps remain 10,000 decisions and 250,000 public states.
The fresh tree walk also has depth 128, stack 8,192, at most 64 actions per
node and at most 49 public chance branches. It rejects cycles, multiple-parent
aliases, malformed public histories, incorrect decision-index aliases and
action/child history discontinuity. The complete rooted view and fresh
structure hash are constructed only after the bounded walk. The fixed game
requires two choices per decision; no old board's tree/class counts are assumed.

Before saved prerequisite authentication, the complete request also reserves
44 named dependency files at 2 MiB each, an index at 2 MiB, an incrementally
encoded raw payload at 64 MiB and compressed output at 16 MiB. These are named
work, traversal and output bounds, not all arithmetic, allocation, runtime or
RSS. Output must be a new directory outside the measured checkout.

## Fresh evidence and limits

The reference validates every world against the exact pair priors, blockers,
unique full ordered support and pair/sign metadata. Produced signs are reranked
through a fresh canonical-board cache with the **same established independent
reference ranker**. This is a consistency check against the reference used
in preparation, not a second independent ranking algorithm. The project-owned
physical implementation remains separate from production parsing, trees,
utilities and trainers.

The physical world hash covers rows
`[canonical_oop, canonical_ip, mass_numerator, mass_denominator, sign, board5]`.
The tree hash uses the existing generic typed numeric structure serializer;
the retained flat rooted view also includes all actions and child references.
The candidate receives the explicit new board and freshly checked physical
rows. Its original `candidate_only=true`, `physical_provenance=false` and
`unverified-caller-supplied-records` flags remain unchanged. Recorded linkage
to this producer does not establish a full public-chance quotient.

The single batch authenticates the saved [D030 census](flop-owned-fingerprint.md),
then retains clean identical committed HEAD/status and all 44 LF dependency
hashes before and after. The complete 41-entry production-authority guard
must remain zero. First errors, actual partial progress and partial output
are retained without retry, replacement or discarded observations.

The implementation uses project-owned code and the Python standard library.
It changes no published experiment, shared turn/river kernel, production
default, Coach surface or third-party dependency. Full joint-mass/reveal/tree
equivalence, class-constant projection/lift and unrestricted physical own-hand
best responses remain necessary before any new-board class training.

## Execution status

The single admitted batch completed at source
`a373c6e874b962ebf3d673ee4a95d8f301ae7ca5`, from
2026-10-22 22:31:57.030310 to 22:32:09.796121 UTC, on CPython 3.12.14 / Windows.
One physical build and one candidate partition completed, with 4,134 actual
rank calls in preparation and another 4,134 in the same-ranker fresh-cache
recheck. All 5,940 signs were compared. All 41 authority counters remained zero,
44 named sources/clean HEAD/status matched before and after, and no errors,
retries or training occurred. The UTC interval is an execution receipt,
not a controlled runtime comparison.

| Fresh observation | Measured value |
| --- | ---: |
| Physical ordered worlds | 5,940 |
| Public states / tree edges | 30,812 / 30,811 |
| Decisions / chances / terminals | 9,512 / 248 / 21,052 |
| Maximum depth / traversal stack | 10 / 111 |
| Candidate turn classes / river signatures | 13 / 17 |
| Candidate aggregate class worlds | 170 |

| Canonical pair | OOP wins | Ties | OOP losses | Exact pair prior |
| --- | ---: | ---: | ---: | --- |
| `AdAs` / `KdKs` | 1,718 | 96 | 166 | `8/13` |
| `QdQs` / `AsKh` | 1,442 | 64 | 474 | `1/13` |
| `QdQs` / `KdKs` | 198 | 64 | 1,718 | `4/13` |

Fresh world SHA256 is
`4ea9c186e4ba524da66b3363ad2a0d8a6851081ca41275a92d2c576a038879ab`;
fresh typed numeric tree SHA256 is
`1b327471df5591e48d50a1db305e0ea32ad3b45c2ff0354df2ddbe4025684173`.
These new anchors describe this board only. Matching any old tree counts
does not substitute for fresh hashes or full equivalence proof.

The complete [index](../benchmarks/results/flop-second-board-reference-v1/index.json)
and [lossless reference corpus](../benchmarks/results/flop-second-board-reference-v1/reference.json.gz)
retain every world, numeric node/action/child view and candidate record.
The index is 19,914 bytes, raw SHA256
`46236f56d92c0b546c52b00339f84d202b51b5913031c0fdafedb4b43eb3d01c`,
with self-digest
`17be8d509916853b7e24ec2cf73f86567b5b8029083432fd04a2bed0e096d583`.
The 373,923-byte gzip expands to 7,978,451 raw bytes (SHA256
`4435d50308efbbe21203f166e6c4f2ccc185bae9dc54578eef56169b0e18b3fe`).

`python -m scripts.verify_flop_second_board_reference_publication` authenticates
both bounded files, protocol, clean current source inventory and recorded
receipts. It reconstructs the typed tree structure from all saved JSON node
views to check the tree hash, without creating numeric game nodes, ranking,
training or best responses. Its observed build/rank counters are labelled
`recorded_*`; current work counters remain zero. The 40 focused tests include
admission/failure paths, explicit flop-root validation, complete authority
receipts, saved-source/progress tampering and zero-work authentication.

No full class/tree, policy or physical best-response equivalence has been
performed on this board. The 13/17/170 candidate dimensions do not authorize
new-board training. Publication is tracked in
[PR #212](https://github.com/ajpaulson18-design/openpoker-lab/pull/212).
