# Provisional Q52 raw-update architecture envelope

This forecast-only native target examines the next step after
[immutable policy import](native-frozen-policy-state.md). It does not implement
or admit a raw-update producer. Its separate `feasible` flag means only that
the proposed logical schedule fits the existing numerical reservations.
`update_admitted` is always false. No import, rank, contraction, update or
training owner is entered by the preflight executable.

## Exact geometry and support

The native card-free template and independent numeric rules each count 1,105
literal occurrences: 434 decisions, 1,039 decision edges, 65 reveal edges,
303 folds and 303 showdowns. Actor route maxima are six and seven decisions;
maximum total is twelve. For each target decision, opponent moves before it
plus **all** future moves have maximum eleven. Counting only future target
moves gives seven and omits future opponent reach. That narrower diagnostic
cannot justify a smaller common denominator.

The independent oracle groups the 2,520 public proposal outcomes by visible
prefix and derives positive joint-mass prefix counts 1, 25, 56 and 60 at lengths
0, 3, 4 and 5. It reproduces all eight complete public catalog counts without
ranking or physical-world enumeration: 61,099 visits; 57,363 actions; 3,735
reveals; 15,662 candidates; 16,631 folds; 17,356 showdowns; 24,420 strategy rows;
58,164 slots.

Sixty complete boards have positive target mass. All other 2,460 still have
positive earlier-prefix rows. Across all boards there are 107,080 supported row
occurrences and 267,540 action slots. The proposed two-target walk retains those
prefix averages even when every complete-board terminal value is zero.

## Proposed complete schedule

The retained import/read reservation remains intact, including complete policy
readback. Each board adds two exact value walks over the card-free action tree,
two reads of each supported-prefix row, terminal contractions at the selected
complete board even for early folds/all-ins, and averages when the current actor
is the target. The same native State row directory remains the only strategy
index. Average generation may share the walks but must never be suppressed by
zero full-board target mass.

Reach uses the existing exact numerator/exponent representation. Prepared
blocker-bucket contractions use both original two-row ranges; query input,
weighted products, bucket initialization, compatible masses, copies, full old
64-plane lookup bound, one board-plane fill, all four possible ranks and both
sorts are reserved. No sampled payoff or private-pair world table is retained.
Proposal, money, signs and the common denominator remain parent responsibilities.

Eight additional unit-reach fold queries derive prefix marginal masses and
divisors at four visible lengths for both actors. They reserve 5,040 work units
using the existing conservative two-by-two query bound, plus 512 parent units
for copies/identity checks, 64 entries and 5,104 payload bits for retained
masses and metadata. These queries are separate from complete-board terminals.

The word ledger independently reserves every reach advance, terminal scale,
child mixture, exact Q52 division/check, signed regret, prefix mass/denominator,
average slot, row staging and traversal. Magnitude bounds remain 648 bits for
regret, 699 before mixture division, 383 for average numerators and 381 for
their denominators, within the existing 704-bit arithmetic carrier. No old
384-bit probe is reused or expanded.

The candidate wire reservation retains complete policy readback plus a raw
stage: 256 header/footer bytes, an 88-byte common denominator, two 88-byte
root values, 136 bytes per staged row and 136 per slot. Row data contains five
uint64 identity/extent fields and two 48-byte average fields; each slot has an
88-byte signed regret and 48-byte average numerator. This is a proposed fixed
layout, not an implemented update protocol. The 648-bit regret magnitude and
its sign fit the 704-bit wire. Temporary frames, stage numeric payload and
metadata have separate reservations. Logical payload is not allocator or RSS
measurement.

## Results and limits

The initial V1 native preflight and independent saved-wire calculation agreed
on every field of all 5,040 cases, but the lifecycle audit identified the missing
prefix queries described below. The corrected V2 maxima below are source-derived;
its executed controls are recorded separately. Uniform and weighted proposals
deliberately share the conservative weighted-width envelope.

| Complete request quantity | Maximum across all cases | Unchanged ceiling |
| --- | ---: | ---: |
| Modeled work | 312,947,940 | 500,000,000 |
| State work | 54,600,636 | 75,000,000 |
| History work | 39,631,840 | 42,000,000 |
| Chance work | 1,322,517 | 110,000,000 |
| Logical entries | 1,176,285 | 2,000,000 |
| Payload bits | 260,024,658 | 1,073,741,824 |
| Candidate output bytes | 1,689,272 | 2,100,000 |

The largest whole reservation is only 3,345,103 above the retained import/read
request. This identifies startup/catalog/I/O reservation as the dominant part
of this proposed one-board request; it says nothing about CPU shares or the
number of samples needed for useful strategy quality. Ceiling-byte I/O charges
remain unchanged. Actual-counter headroom is never substituted for an upper bound.

The executable's own forecast request is separately bounded before construction:
162,175,360 work units, 409,956 entries and 21,920,896 payload bits. It constructs
only the card-free template, scalar geometry and bounded forecast text. All
5,040 candidate reservations are reported, never executed.

Static independent review found no concrete undercharge or unsafe admission;
independent numeric equations subsequently matched all recorded fields. A first
controller source-cleanliness check rejected before native launch while the
independent census addition was still uncommitted; that refusal is retained.
Formal source-frozen normal/optimized controls and cross-platform CI are recorded
separately as they complete.

V2 source `510576a56fc0ef077d7ac22034ea29d5d2ffb4dc` subsequently passed both
source-frozen normal and optimized two-test suites. Each suite observed one
native preflight exit, verified all 5,040 reservations against the independent
geometry and operator equations, and rejected outcome-order, framing and scope
corruptions. The executable SHA256 is
`7bc08329cecd655dc71f17be63b34d1c89a802c2cddfecd0bb28cd765979f3d7`.
There were no native policy imports, ranks, contractions, updates or training
iterations; only the forecast program itself executed.

The [immutable V2 packet](../benchmarks/results/frozen-grid-update-envelope-v2/manifest.json)
has 262 members and 4,081,505 bytes, SHA256
`dce1e6d5f59773d3e540c1f365664af88e1bf43edd7e44ebb6db4cc42392f4ac`.
It retains both original V1 and V2 source/build closures, binaries, observed
exits, complete forecast text, source-cleanliness refusal and equation reports.
Every member and CRC was verified. The earlier PR329 Windows compiler failure
artifact is also retained; its same-source paired job and isolated retry passed.

Run `python -B -m scripts.replay_frozen_grid_envelope_packet` to authenticate
the complete archive and replay both extracted V2 records using current frozen
math sources. Normal and optimized
[archive replay records](../benchmarks/results/frozen-grid-update-envelope-v2/archive-replay-normal.json)
pass with zero candidate calls; archived source is never executed. The generic
archive-reader change also passed the original PR329 policy packet regression.
Source and observed stream corruption checks remain separate from execution
attestation: saved command/exit records are controller observations.

At [PR330](https://github.com/ajpaulson18-design/openpoker-lab/pull/330) source
`30214c30a932d56a940d4eb490a2ad644221838b`, dedicated
[Windows](https://github.com/ajpaulson18-design/openpoker-lab/actions/runs/44448469872/job/135306278479),
[Linux](https://github.com/ajpaulson18-design/openpoker-lab/actions/runs/44448469872/job/135306278762)
and [sanitizer](https://github.com/ajpaulson18-design/openpoker-lab/actions/runs/44448469872/job/135306278277)
jobs passed both complete control suites and saved replay. Decoded job logs
are stored beside the archive with line endings converted to LF. The immutable
archive itself is unchanged by later job records or source repairs.

The V1 design omitted the eight prefix-marginal queries and their retained
results. Its original compiled observations, source copies and successful
equation checks remain superseded development evidence: agreement between two
implementations of an incomplete ledger was not complete admission. V2 includes
these named costs. Both versions keep update admission false. V1 is not silently
accepted by the maintained V2 verifier.

Next implement the declared schedule with cumulative meters and bind actual
operations, storage and wire bytes to these terms before granting update
admission. Then compare every per-board raw row to the independent Q52 oracle,
including zero-full-target boards. No changing-policy CFR+ clipping proof,
convergence, speedup, eleven-card capacity or independently replayed quality
follows from this envelope. The eleven-card State/quantizer/parent failures
remain unchanged, and resident complete snapshots still require paged/lazy
architecture work before realistic heads-up games are practical.
