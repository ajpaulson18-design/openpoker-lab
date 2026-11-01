# Native public-chance probability and payoff boundary

Status: committed-source component conformance and all 14 publication workflow
groups pass; PR #281 is merged as `692c301`. This is a
native component for the future virtual-chance four-street path, not a sampler,
trainer, complete strategy, or full-deck quality certificate. Independent compiled
numerical controls and the complete source freeze are recorded below.
The [selected-game certificate result](matrix-free-certificate-result.md) is merged
separately in PR #279 as `e9739a3`; its two quality passes and 26 misses remain.

## Why this boundary changes

The selected native kernel owns at most 64 supplied boards and normalizes the
joint game over those boards. Constructing it with one sampled board would
condition the game on that board. Reweighting its already-rounded outputs also
adds a rounding boundary. `native/full_deck_public_chance.hpp` instead owns only
the two original ranges and a declared physical deck. It computes one compatible
private-pair normalizer Z with card buckets and same-holding addback, and accepts
public prefix or single-board terminal queries without retaining a board list,
private-pair coefficients or complete-world records. Showdown uses a rank sweep.

This is part of the coherent four-street architecture. Its consumers will be one
native virtual public traversal and bounded information-set pages, not separate
street equilibria. Existing selected kernels, Graph/Plan/Router and CFR+ defaults
stay unchanged; none silently selects this new component.

## Mathematical units and information boundary

Inputs are canonical numeric holdings (rank-major cards, c/d/h/s within rank),
with exact snapshots of their positive finite binary64 weight bits. Physical
overlap conditions the private-pair law globally:

`Z = sum_compatible_i,j wi*wj`.

The default declared deck is all 52 physical cards. A separately tagged reduced
proof deck may contain 9..52 sorted unique physical IDs. A reduced deck is never
reported as full52. For N cards and public prefix length k:

| k | Conditional chance divisor d_k |
| --- | --- |
| 0 | 1 |
| 3 | C(N−4,3) |
| 4 | C(N−4,3)(N−7) |
| 5 | C(N−4,3)(N−7)(N−8) |

Flop IDs are increasing; turn and river stay ordered. Prefix queries return
every original input row, exact own-hand masses and physical support, including
exact zeros. An unblocked own holding i has mass
`wi * sum_compatible_unblocked_j(wj) / (Z*d_k)`.
Both seats share the same total prefix mass. There is no local renormalization.

A single full-board terminal query returns an exact own-hand vector for
`wi * sum_compatible_j(wj * opponent_reach_j * utility_ij) / (Z*d_5*q(board))`.
Fold utility is signed for the queried original player. Showdown stake is
nonnegative, multiplied by win/tie/loss sign. Whole-hand matched contributions,
refunds and betting legality remain caller-owned. The complete opponent reach
vector is finite in [0,1]; it must include only opponent action reach. Own prior
appears once, own preceding action reach does not enter counterfactual values.

The supplied proposal q is an exact positive rational at most one. Its inverse
is applied to exact integer numerators/denominator before optional one-time
binary64 conversion. The component validates the number, not the provenance or
full-support law of a nonexistent sampler. Full52 uniform public-board sampling
would have 51,979,200 outcomes, versus 34,246,080 boards per compatible private
pair; its once-only correction would be 54145/35673.

An internally sampled future board may zero a numeric terminal contribution,
but must not alter an earlier policy row, menu, physical support or marginal.
This component has no policy/history routing API. Prefix masses and sampled
terminal vectors are separate types/operations so the later traversal can use
the visible-prefix mass, with q(prefix), for average-strategy updates. A zero
target full board must not be redrawn: earlier-prefix average increments can
still be nonzero. Taking a best-response maximum after inspecting hidden sampled
cards remains invalid.

## Exact arithmetic and admission

Native integer weights use one shared dyadic exponent per original seat. Exact
vector outputs contain input-order integer numerators and a common positive
denominator. The stored normalizer with its two denominator exponents reconstructs
the original physical Z. Optional `binary64()` uses the existing strict converter
after all chance/reach/payoff/proposal scaling; a nonzero result that cannot round
to a finite normal value rejects rather than dropping support or clamping.

| Reduce-only kernel ceiling | Maximum |
| --- | ---: |
| Holdings per original seat | 1,326 |
| Named logical work | 500,000,000 |
| Retained plus query scratch logical entries | 2,000,000 |
| Integer-value width | 65,536 bits |
| Integer payload width forecast | 1,073,741,824 bits |

Constructor input dimensions precede ownership/allocation. Input scans, deck
checks, queries, rank/bucket/sort/output scratch and integer products/shifts have
explicit pre-admission. Converter work composes its existing receipt: for largest
operand width b, reserve `2*(b+53)^2 + 16*(b+53)` per row before conversion; successful
receipts must fit. Converter scratch retains the extra 53 bits. Admission failure
is incomplete work, not a quality result. These are named logical operations,
entries and integer-value widths, not actual allocator limbs, CPU instructions,
runtime or RSS. Caller-owned inputs and retained output lifetimes are separate.

## Build, probe and acceptance

`python -m scripts.build_native_full_deck_public_chance --output-dir <external-dir>`
selects the explicit new target in the existing source-authenticated strict C++20
builder. It records actual source/compiler/executable identities and pinned Boost
headers; outputs must remain outside the checkout. The native class is the
intended integration seam. Its bounded whitespace probe is a test transport,
not a service or production training protocol. Each record is independent; no
policy, RNG, cache or private state carries between records.

The probe has fixed input/output framing ceilings. Its bounded initial scan
validates syntax, dimensions, physical card/holding fields and reach/proposal
field ranges before owned range/reach arrays or arbitrary-width proposal integers.
Global compatible-mass and arithmetic-growth validity remain kernel checks,
after ownership has been admitted. This is not a claim that caller work limits
prevent the fixed-size initial read/grammar scan.

Before materializing numeric input, reserve
`16384 + 6*request_bytes + 16*request_tokens + 8*response_bytes_upper`
from the original work allowance. The response bound includes three maximum-width
integer scalars. Probe-owned input entries and integer payload are also reserved
separately and deducted before constructing the kernel. Combined receipts must
fit the original caller ceilings. Fixed grammar stack/text-buffer ceilings are
separate from these logical numeric-entry/payload models; no total-process heap
or RSS bound follows. An internal observer checks entry into named materialization
sites, not all allocator activity.

Seventeen development controls first passed normally and optimized (15.028 /
16.173 seconds), before review identified three probe-admission gaps. The corrected
18-control run passes normally and optimized (30.099 / 40.887 seconds), with no
skips and stable scoped source pins. Compiled observer controls verify early
duplicate/reach rejection and probe-owned payload/entry admission. Both versions
and the earlier capture gaps remain in the
[development manifest](../benchmarks/results/native-public-chance-development-v1/manifest.json).
The frozen test source adds per-board equality before expectation summation.
The controls cover
literal physical pair arithmetic with a separate best-five ranker,
the existing independent full52 prefix operator, full 1,326-by-1,326 combinatorial
mass anchors, ordered prefix partitions, zero-target boards, exact and binary64
terminal results, extreme priors, and rejection controls.

### Committed-source conformance result

Freeze `32ddc17409d7e56e012a9d749863af438a79a3d9` passes all 18 controls normally
(27.189 seconds) and assertions-disabled (26.579 seconds), with no skips or
failure. Each of 20,160 terminal results matches the independent literal
physical/best-five oracle before expectation summation. All 2,232 tracked project
raw/Git blobs, nine original compiled inputs and 198 actual Boost headers were
authenticated before component mathematics and remained stable after both modes.
The original executable is SHA-256
`3ca382a6c2b709115513aab01288e614733d77c658f1da5416dc13962a9b69ef`.
Outer process handle 63331 returned observed terminal exit 0.

The [frozen evidence manifest](../benchmarks/results/native-public-chance-v1/manifest.json)
binds the project closure, build identity, mode status/streams, named preflight
materialization controls and separate external-controller observation. The
external stdlib controller is captured separately from the committed project
closure. Archived code was not executed. Final-head Linux/Windows and sanitizer
component jobs, existing whole-game conformance, and Python 3.11/3.12/3.13 tests
pass. The fetched merge contains the exact tested publication tree; see
[PR #281](https://github.com/ajpaulson18-design/openpoker-lab/pull/281).

These results validate the declared component controls. They do not establish a
regret-update estimator, full-game policy, convergence, speed or measured RSS.

## Next integration gates

The [card-free betting template](virtual-betting-template.md) addresses two
subsequent reference dry-census failures before the full update proof. Neither
failed reference constructed its public model. Structural template counts are
distinct from admitted physical support, strategy rows and update correctness.

The reviewed reduced nine-card anchor has three compatible private pairs, each
with 20 legal canonical-flop/ordered-turn/river outcomes: exactly 60 target boards
out of 2,520 exogenous public proposal outcomes. Unequal priors and real physical
cards provide ties, wins and losses. Component terminal expectation and prefix
partition controls are prerequisites, not the complete estimator proof.

Before native training, compare the expected **entire per-row/action raw regret
increment** for both players and average numerator/denominator increments against
an independent full-history finite-game reference, enumerating every proposal
outcome for uniform and nonuniform q. Include zero-own-policy legal deviations,
early fold/all-in, zero-target boards with nonzero prefix averages, reconvergent
histories and explicit hidden-future leakage negative controls. Do not assume
CFR+ clipping commutes with expectation; start with one frozen-profile vanilla
update contract. Then implement bounded lazy history/strategy storage and one
native virtual-chance four-street traversal.

Growing row storage, complete policy export, sampling variance, finite-run
convergence and an independent full-game exploitability bound remain unsolved.
The current selected-game certificate and a sampled best response cannot certify
a full52 strategy. No component-only result satisfies the overall goal.
