# Selected-runout operator four-street foundation

Owner direction, October 26, 2026: Sol leads architecture, Terra challenges
mathematics and resource claims, and Luna implements. This follows the
[foundation audit](foundation-first-audit.md) and
[execution record](foundation-first-execution.md). The overall goal remains open.

## Implemented boundary

`pokerlab.selected_operator_solver.solve_four_street_operator(request)` takes
the existing immutable `FourStreetSolveRequest` with public-batched training and
diagnostics and public-vector resources. It returns the complete replay-compatible
`preflop-strategy-v1` payload. It shares the original betting builders,
positive-pot translation, CFR/CFR+/DCFR kernels, averaging schedule and
visible-information best-response diagnostics. Original defaults and historical
benchmark source files are unchanged.

The provider retains hands, weights and masks plus selected board tokens/masks:
O(H0 + H1 + R) input storage, with one board's per-hand rank vectors cached.
It stores no complete private-pair/board worlds or prefix/private-pair edges.
Queries reduce one pair's compatible board masses at a time. The O(R) public
topology projection has dummy hand/mass fields used only by the shared tree
builder for board tokens. Actual support and work are established separately.

The public tree, information-set rows, regret/average arrays and serialized
policy remain explicit. The compatible output also emits O(P) private-pair
probabilities, counted separately. The **whole solver does not have linear total
memory**. Full-deck, sampled and delayed-average operator modes remain unsupported.
Later explicit [native selected](native-selected-operator.md) and
[native direct-DAG](native-selected-dag-protocol.md) backends have separate
protocols, admission and measured evidence.

## Mathematical and game contracts

Each compatible private pair and selected board has the reference binary64
raw range product divided by the constant physical runout count. A global
`fsum` normalizer integrates every compatible pair/board occurrence. Each
normalized occurrence passes the original positive-normal mass guard. Absolute
prefix mass sums occurrences extending that prefix; there is no local
renormalization. Unequal blockers change preflop pair probabilities. The
full-deck prefix research operator cannot substitute for this selected law.

Pair order and within-pair binary64 `+=` reductions precede payoff/reach
multiplication, matching the reference. Equivalent real-arithmetic reductions
can differ at near-zero regret branches; no general bitwise equivalence is
claimed. Exact conditioning of finite support is distinct from binary64 training
and exact rational saved-policy certification.

Terminal vectors contain joint chance mass once and opponent sequence reach
once. Own reach enters averaging with the own-hand prefix marginal. SB/button
is player zero; BB is player one. Public chance children sum without a second
chance multiplier. Early all-in terminals integrate still-hidden boards.
Information-set keys contain only own hand and visible public history.

The existing finite betting menus, local nine-decimal monetary quantization,
stack/refund and short-all-in semantics remain. No omitted action, rake or
real-world rules expansion is implied. See [model boundary](preflop-solver.md)
and [independent numerical rules](four-street-integration-protocol.md).

## Admission and next bottlenecks

`census_four_street_operator(request)` performs bounded rank-free preparation.
It reports worlds represented, zero stored complete worlds/edges, public states,
decisions, terminals, information sets, action slots, regret/average scalar
slots and pair-output capacity. Existing candidate/world/iteration and public
tree/template limits remain. Support scans receive incremental preparation
admission. A separate conservative 500-million requested scan envelope is
checked before training/ranking. It includes prefix filtering, candidate pairs,
board checks, support/output queries and public-topology filtering. Counts are
logical entries, not instructions, allocation bytes or RSS guarantees.

Next limiting structures are explicit public histories and per-hand action
storage, plus repeated mass/rank queries. The measurement runner varies selected
support and stack depth. Exact compression and native operator integration each
need a measured independent acceptance; prior isolated native speedups do not
activate them automatically.

## Validation and evidence protocol

Tests compare complete policies and metrics with the original 22-world game and
weighted/shared-prefix, tie, raised, short-stack and blind-all-in controls across
vanilla CFR, DCFR and CFR+. Tripwires forbid complete-world enumeration and
prefix-edge materialization on the new production path. Independent tests use
physical cards, exact fractions, a separate best-five ranker and asymmetric
reaches. Complete serialized policies are replayed under independent numeric
rules and legal own-hand best responses.

Run `python -B -m scripts.benchmark_selected_operator --output <fresh-external-dir>`
from clean committed source. It retains three complete untraced calls and one
allocation-traced call per backend in fresh processes. Complete-call timing
includes preparation, training, diagnostics and serialization-ready payloads.
Traced timing includes instrumentation. Process lifetime peak working set
includes interpreter/imports; Python traced allocation is measured separately.

A manifest pins raw measurements before replay. Saved-only verification requires
its externally supplied SHA-256, checks bytes before parsing and after mathematics,
and checks clean source/HEAD throughout. Existing audits are compared, never
overwritten. Numeric and v3 rational certificates cover sample zero of each
backend; all sample bytes are authenticated. Low-iteration quality misses remain
in evidence. This is a representation milestone, not commercial accuracy proof.

From the original clean measurement revision:

```text
python -B -m scripts.benchmark_selected_operator --verify-saved <directory> --expected-manifest-sha256 <published-digest>
```

## Retained result at source a3f289e

The [receipt](../benchmarks/results/selected-operator-four-street-v1/receipt.json)
pins the source revision, all compressed raw artifacts, manifests, policies,
exact certificates, intermediate failures and independent review. Archive
members were compared byte-for-byte with originals after compression. The
original 22-world fixture has 1,462 public states, 1,200 information sets,
2,402 action slots and 4,804 regret/average scalar slots. The new path stores
zero complete worlds and zero prefix/private-pair edges.

| Fixed experiment | Reference | Operator |
| --- | ---: | ---: |
| T10 complete-call median, three fresh processes | 0.304908 s | 1.715155 s |
| T10 Python traced peak allocation, separate call | 2,553,239 bytes | 2,780,711 bytes |
| T10 numeric NashConv | 0.658088258 BB | 0.658088258 BB |
| T1000 complete-call time, one call each | 31.159303 s | 126.437054 s |
| T1000 numeric NashConv | 0.0003997388151442405 BB | 0.0003997388151442405 BB |
| T1000 independent exact target <= 1/1000 BB | pass | pass |

Complete strategy rows and independently replayed exact metric maps agree
between backends in both experiments. The T10 miss is preserved. The T1000
operator made 7,547,036 observed post-constructor pair/board checks and 991,485
ranking calls with peak four rank-vector entries. Its modeled scan ceiling is
400,915,862/500,000,000; that ceiling is not an observed operation count. One
separate saved-only process repeated numeric/exact replay with zero training
and compared existing audits without rewriting them. Terra independently
checked manifests, artifact hashes, policy equality and exact target outcomes.

The operator is slower and has slightly higher measured total memory on this
tiny fixture. Process peak working sets at T1000 were 26,451,968 bytes reference
and 26,550,272 bytes operator; these are descriptive process-lifetime peaks,
not live retained operator storage. No speed or RSS improvement is established.

With fixed six-board support, raising stacks from two to eight increases
information sets from 100 to 1,200 and action slots from 202 to 2,402. The
[range-growth census](../benchmarks/results/selected-operator-four-street-v1/range-census-v1.json)
keeps disjoint private pools and public topology fixed: 1/2/4/8 hands per seat
are admitted, with action slots 1,377/2,754/5,508/11,016. The 8x8 case represents
384 worlds without storing them. The 16/32/64-hand cases reject the unchanged
500-million scan ceiling; no larger-range training or quality is inferred.

Next work must reduce repeated probability/rank scans and explicit public-tree
and information-set/action storage. The operator seam establishes a replaceable
boundary for that work. It is not a full-deck migration, native integration,
general convergence result or completion of the overall foundation goal.

The T10 manifest is
`f8addb799553b5df7c7597ec24ca2681ff328853d5bd7f3f189aed311e1b6889`;
the T1000 manifest is
`06d6b9aef226fde11ad473ceaf1bab02bbe373d3059763ccbcc757339af19a76`.
Extract the respective archive into a fresh external directory. Replaying the
source-gated runner requires clean source revision `a3f289eeccff6f7357801d543872b11f632e3b61`
and the captured checkout bytes, including line endings. Evolved source is
intentionally rejected. The two additional rank-free/accuracy orchestration
scripts are retained beside the archives with self-hashes in their records.

Local validation: 46 focused/operator/evidence/reference/contract tests pass
normally (7.822 s) and optimized (7.003 s); 43 non-temporary-folder tests also
pass from committed source (8.249 s). All 19 numerical/operator integration
tests passed in the initial restricted final-source run; its three evidence
tests encountered Windows temporary-folder access errors. The normal-access
runs discharge those three checks. Documentation links pass. Final PR CI and
merge state are separate live checks, not inferred from these local results.
