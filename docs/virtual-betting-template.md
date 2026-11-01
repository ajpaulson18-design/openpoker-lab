# Card-free betting template for virtual public chance

Status: committed-source structural component conformance passes; final
publication CI remains pending. This is the
next structural boundary in the [unified foundation](foundation-first-audit.md),
after the [native chance component](native-full-deck-public-chance.md), merged
in [PR #281](https://github.com/ajpaulson18-design/openpoker-lab/pull/281).
It does not establish a sampler, regret-update estimator, trainer or policy.

## Observed barrier

Two separately authenticated reference attempts at committed source `32ddc174`
stopped at the unchanged 500,000,000 logical-work limit during the independent
public-tree dry census. Both used the nine-card proof deck's 60 positive-target
boards. The first used stack 8, preflop one pot-sized raise and explicit all-in,
and postflop half/full-pot bets, quarter-pot raises and explicit all-in. The
second retained the betting rules from `tests/test_four_street_validation.py`'s
existing `CASE`: one half-pot preflop raise, half-pot postflop bets, no postflop
raises and no explicit all-in option.

The first attempt failed in successor admission; the second failed in menu
admission. Neither constructed the public model, reached its proposed policy
fixture, ranked hands, trained or proved any update identity. The scripts did
enumerate the three compatible private pairs and tiny proof-deck board sets to
define their inputs. These preliminary counts are not a completed game census.
Both [first failures and source authentication](../benchmarks/results/update-proof-census-failures-v1/manifest.json)
remain immutable. A later
structural attempt must preserve their full betting configurations; reducing
the fixture again or raising the old limit would not resolve this barrier.

## Representation and information boundary

The new native compiler will own one immutable betting configuration and intern
numeric betting continuation states. Its input contains no deck, boards,
private ranges, ranks or selected-world probabilities. Reveals are symbolic
street transitions. Menus and settlement must match the independent configured
numeric rules, including global SB/BB identity, the initial limp/BB option,
local postflop ledgers, nine-decimal cleanup, short all-in reopening, matched
contributions and refunds.

A continuation key must retain every transition dependency: street/phase,
actor, exact binary64 commitments and increment, raises, reopened/check state,
origin and local-ledger presence, boundary pot, local commitments, and the
initial-history-empty flag. Null differs from zero. The fixed configuration
owns stacks, blinds and all stage sizes. Hash equality alone cannot establish
key equality. Configured money cleanup requires ties-to-even rounding of the
exact binary64 input at nine decimal places; scaling a double then calling
`round` does not implement that contract.

Shared continuation identity is never strategy identity. Future strategy rows
must still distinguish original actor, own holding and the complete ordered
visible history. Distinct action paths can share a betting continuation while
having distinct regrets and averages. A later history arena must preserve
parent identity and exact token bytes, including canonical flop and ordered
turn/river reveals. No future card may choose an earlier row or filter earlier
support. This compiler does not implement that history arena or lazy storage.

## Structural census

A checked acyclic dynamic program can propagate the number of distinct action
paths through shared continuations without retaining each path. Counts,
actor/street/menu-width distributions, action slots and sums of history token
lengths remain separate from the number of retained template nodes. Concrete
reveal tokens have 11/7/8 characters for flop/turn/river under the two-character
card encoding. The legacy independent fold terminal stores its history before
the fold token; comparison must distinguish that metadata convention from the
complete action path that includes the fold edge.

Card-independent betting-path counts may be combined with explicitly declared
unconditioned proposal-prefix counts: 1, C(N,3), C(N,3)(N-3), and
C(N,3)(N-3)(N-4). Those products are unfiltered public-history counts. They are
not exact physical-support counts, private information-set counts, visited
strategy rows, storage admission or solved quality. Arbitrary-range physical
support counting and bounded persistent strategy growth remain open.

Logical work, entries, integer widths, count overflow, transport and output
need explicit reduce-only admission before the corresponding operations. These
models do not measure CPU instructions, heap allocation or RSS. A compact
template does not make traversing all action histories or exporting a complete
policy free.

## Native boundary and admission model

`native/virtual_betting_template.hpp` exposes the immutable `Template`, numeric
`State`, ordered action edges, node/history counters and receipts. The constructor
checks supplied dimensions before copying the configuration. Its state index
compares the complete key with an ordered map. Native limits are reduce-only:

| Family | Ceiling |
| --- | ---: |
| Retained continuation nodes | 250,000 |
| Continuation edges | 1,000,000 |
| Logical retained plus maximum scratch entries | 2,000,000 |
| Named logical work | 500,000,000 |
| Maximum action/reveal depth | 64 |
| Summed symbolic node occurrences | 1,000,000,000,000 |

History token/byte sums use checked unsigned 64-bit integers and reject
overflow. Acyclicity and longest depth are checked in the complete DAG census;
node/edge/work/entry guards also bound compiler construction before that census.
The entry model reserves `64 + 4*size_count` for owned configuration, 192 per
node, 32 per retained edge, and five retained history counters per node.
Temporary menu/branch work has 1,024 logical scratch entries; DAG scratch uses
`12*nodes + 1024`. Entry units are named scalar/container/token allowances,
including growth allowances, rather than measurements of allocator bytes.

For a money input with magnitude below `2^-31`, exact nine-place cleanup is
zero. Other bounded inputs have at most an 83-bit scaled significand and an
84-bit denominator. The logical quantization model reserves 30,000 units before
integer work: `2*83*84` quotient/remainder width products, at most 7,028 from
the existing exact converter receipt, and bounded scans/bookkeeping. Nonzero
rounded decimal-grid integers fit 50 bits. These fixed bounds avoid a hidden
subnormal-width cost and do not assert a bound on Boost's machine work.

The optional supplied-state constructor and probe `STATE` mode inspect a
synthetic decision suffix. They require cleaned chip amounts and consistent
origin/local/global ledgers; the raise increment retains its unrounded binary64
subtraction bits. An empty-history state must be the actual initial decision.
Nonempty suffix mode does not authenticate an earlier action history or prove
reachability. Its receipt explicitly says `suffix-only`; history sums exclude
the caller's absent initial tokens. Terminal nodes preserve both posted
commitments and expose matched contribution separately, including blind all-in.

Build the explicit `virtual-betting-template` target through
`scripts.build_native_exact_four_street` into an external directory. The
`virtual-betting-template-controls` target checks fixed rounding anchors and
admission/ledger boundaries. Neither target is a selected-game engine fallback.
Both preserve source/compiler/executable and pinned Boost identities.

The bounded whitespace probe accepts at most 16,384 bytes and 512 tokens per
record, 256 records per process. It reserves response capacity
`4096 + 768*node_limit + 192*edge_limit`, capped at 64 MiB, then deducts
`8*request_bytes + 32*token_count + 8*response_capacity` work and 256 input
entries before constructing owned configuration. Kernel and transport receipts
must be assessed together. The initial fixed framing/grammar scan is outside
that caller work allowance. The probe deliberately needs smaller explicit
geometry than the native maximums; the development controls use 4,000 nodes
and 16,000 edges. Large pessimistic output forecasts reject without construction.

## Acceptance gates

The one development reference census on the existing six-runout `CASE`
completed at the old limits: 1,414 nodes, 628 decisions, 97 reveals, 156 reveal
edges, 315 folds, 374 showdowns, 1,257 action slots and depth 14. Projecting the
independent card-free template with prefix counts 1/2/4/6 reproduces those
counts, 14,582 legacy history tokens, 86,877 legacy history characters, and
6,187 action-token characters. Including fold edges gives 14,897 semantic
tokens and 88,137 characters. Reveal-node factors use the old visible street;
reveal-edge factors use the next street.

That development census authenticates six named source files and HEAD/status
before/after, not the entire introduced source closure. Its zero rank/training
fields describe the called builder's source contract; they are not measured
spies. The original attempt is not rerun to improve packaging/provenance.
Committed component controls and final publication checks remain separate.

The [development record](../benchmarks/results/virtual-betting-template-development-v1/manifest.json)
preserves the successful compiled rounding/admission controls, the 8,011-input
rounding comparison, earlier compile/environment errors, and both controller
attempts. The second controller's 15 normal and 15 optimized unit tests pass,
but its overall source-stability check fails because documentation changed
concurrently. That attempt remains failed. A later pre-import projection helper
correctly rejects the post-format native source; a separate saved-only projection
matches the eleven reference counts. Missing separate observations of an outer
controller's exit are not inferred from its own completion file.

The formatted native source changes whitespace only; every formatter replacement
was checked and original bytes preserved. The archive preserves historical
source pins and identifies gaps; current source copies do not relabel older runs.

### Committed-source result

Freeze `94b4f5fa48fa7388dcc0bf106b5f065ed84e7164` passes all **16 tests normally
and optimized, no skips**. Both explicit native targets compile and the rounding,
resource/ledger and rounding-mode controls pass. The complete 2,281-file project
matches captured committed HEAD before mathematics and remains byte-identical
afterward; 1,345 paths per side additionally match their Git-filtered blobs.
Both eight-input native build closures and all 198 actual extracted Boost
headers are checked. Root observed outer handle 96625 terminate with exit 0.

The [frozen record](../benchmarks/results/virtual-betting-template-v1/manifest.json)
retains source/Git maps, original build manifests/compiler logs, raw unit
streams/status, both original executables, the external stdlib controller and
its separate process observation. The controller is outside the committed
project closure. Its normal/optimized subprocess times are 2.828/1.781 seconds;
these are conformance observations, not performance comparisons. No archived
source or binary executes during publication.

Windows, Linux and ASan/UBSan component jobs pass on the frozen head. Final
publication checks are tracked in
[PR #283](https://github.com/ajpaulson18-design/openpoker-lab/pull/283).
These controls establish the stated structural boundary; the complete
regret/average update, physical row admission, lazy storage, training and
independent full-game quality remain open.

1. Compare native ordered menus, raw money bits, actions, terminal data and
   successors with independent numeric rules, including rounding boundaries,
   asymmetric stacks, first-call history, checks, short all-in and refunds.
2. Compare DAG multiplicities and history sums with an independently enumerated
   bounded public tree. Test reconvergent histories and card independence.
   Preserve any admission failure; do not retry a frozen reference producer.
3. Attempt the two preserved configurations through the new admitted structural
   representation. A structural receipt cannot turn the old failed reference
   attempts into successful full-game or update-proof results.
4. Prove the entire frozen-profile, per-history/own-hand/action regret increment
   and average numerator/denominator increments over every nine-card proposal
   outcome, including zero-target boards and zero-own-policy deviations.
5. Only then integrate actual sampling, staged failure-safe updates and bounded
   lazy rows in one native four-street training path. Complete policy semantics,
   variance, convergence and independent full-game quality remain further gates.

The existing selected-game kernels, defaults, caps, frozen policies, two quality
passes and 26 misses remain unchanged.
