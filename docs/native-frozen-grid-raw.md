# Native fixed-policy per-board raw operator

The explicit `virtual-frozen-grid-raw-update` study now executes the schedule
behind the [V2 envelope](frozen-grid-update-envelope.md). It imports one complete
Q52 policy through the [shared native owners](native-frozen-grid-shared-owners.md),
walks all four betting streets for both global seats at one selected latent
board, and returns exact signed action regrets, prefix averages and root values.
It does not clip regrets, update numerical State, choose random boards, train,
or evaluate strategy quality. It is not a general solver backend.

## Computation and identity

The front door accepts only a snapshot path, one of `uniform`/`river_weighted`,
and five original card IDs from the fixed PROOF9 deck. Unknown arguments,
foreign/duplicate cards and noncanonical flops reject before private policy
preparation. Complete import must seal before any raw walk or output begins.
The Factory derives the forecast, History and State from the same source,
board and proposal. Policy reads use the owned full-history cursor, actor and
original holding; no parallel strategy index or hidden-future policy callback
is introduced. Future cards are appended to visible History only at reveals.

Eight Prepared unit-reach fold queries derive marginal masses at lengths
0/3/4/5. Terminal queries use the selected complete board for both folds and
showdowns, including early all-ins. Signed integer reach remains in the shared
trainer representation. Parent scaling uses `D_B=580*n*2^625`, raw proposal
`n/d`, exact configured stake parts and global SB/BB signs.

At target decisions the canonical kernel multiplies child values by Q52 units,
sums, verifies exact divisibility and restores the signed quotient. Child values
for zero-policy actions are still computed for their regrets. Opponent decisions
sum children after exact opponent-reach advancement. The two root values must
cancel globally. No binary64 probability conversion, GCD normalization or
sampled CFR+ clipping claim is introduced.

Average rows use physical prefix marginal mass, target own reach and the
prefix proposal. A zero complete-board target retains earlier-prefix averages.
All counterfactual histories under the fixed board are traversed; policy-zero
paths are not silently removed. The raw stage is separate from State numerical
regrets/averages, which remain absent and immutable.

## Complete-request bounds

The committed all-board V2 maximum is reserved before template/catalog
construction. The selected request then recomputes and checks its forecast
before History/State/private policy allocation. Native component meters enforce
the cumulative lifetime, including readback after both raw passes.

The existing three-million-unit geometry family also reserves 1,020,000 units
for the added request scanner and metadata: at most 1,105 literal occurrences
and twelve decision-ancestor suffix scans per occurrence need
`128*1105+64*12*1105=990080`; the forecast/selector ledger reserves another
16,384. These and the original native Forecast are guarded together, without
changing the geometry ceiling. Setup, numeric work and I/O are summed in the
final whole-request receipt.

All 20 tested cases remain below their independently derived forecasts. Maximum
observed modeled work is 217,037,204 units; the global forecast remains at most
312,947,940 under the unchanged 500-million cap. The observed integer peak is
698 magnitude bits, within the existing 704-bit carrier. The historical 384-bit
probe and its recorded rejection remain unchanged. Logical work/payload bounds
are not CPU, allocator or RSS guarantees.

## Wire and portability

`OPLGRW01` begins a 256-byte header (magic plus 31 uint64 fields): version,
complete policy dimensions, raw-stage dimensions, proposal/board, Q52 scale,
all resource reservations and route/scope declarations. The complete policy
readback carries the same actor/holding/ordinal/slot/menu-size identities and
units as the prior import test. An 88-byte common denominator and two signed
88-byte roots follow. Each raw row has five uint64 identity/extent fields,
48-byte average denominator and mass, then an 88-byte signed regret and
48-byte unsigned average numerator per action. A 26-word footer records actual
work, scopes, counts and completion. Total bytes match the V2 reservation.

Integers are little-endian; signed values use fixed-width two's complement on
the wire. Boost's internal signed-magnitude limbs may be 32 or 64 bits. The
first build rejected an incorrect 64-bit-only assertion before any raw call;
the corrected serializer packs either backend into the same uint64 wire.
Width checks inspect the normalized top limb without making absolute-value
copies. The build refusal is preserved, not classified as numerical success.

## Executed validation

Native source `40470425ce55602245cb83abfde580f45b3dd85e` and test source
`4c643855b83f09e3c9e92a18dd3204d2b502679b` passed normal and optimized
conformance. Each mode observed twenty successful independent requests:
three compatible private-pair boards and two zero-target boards, crossed with
two complete policy profiles and both proposal laws. Every global policy unit,
supported raw row, signed regret, average action/mass, both roots, output bytes
and cumulative scope/resource counter matched independent numeric rules,
Fraction arithmetic and the independent ranker. All twenty native output
streams are byte-identical between modes.

Six additional invocations per mode rejected unknown proposal, duplicate card,
foreign card, unsorted flop, wrong arity and a late invalid policy partition.
Each observed an actual exit and exposed no partial output. Saved-wire
truncation and one-bit regret corruptions reject without native calls.
Each case is an independent bounded request; the controller records their
aggregate reservation and does not pretend the matrix is one training admission.

The optimized controller completed during a tool-host interruption. All 26
native exits were rechecked and the numerical outputs compared after reconnection;
its wall interval is not used as a benchmark. No retry or timing acceptance
was introduced.

`scripts.replay_native_grid_raw` authenticates the entire captured introduced
source closure against its committed tree and the current numerical dependencies
before importing the oracle. It checks saved commands, input bytes, stream hashes,
actual process exits, private-pair/prefix coverage and all raw rows with zero
candidate calls. Archived source is never executed. The Windows/Linux/sanitizer
workflow performs both conformance modes and saved replay.

The dedicated raw-operator jobs at source `296836f25b38810c30f27b2fc3aadd7ae58fea2d`
passed on Windows, Linux and sanitized Linux, for both push and PR events.
This is separate from the broader component Windows History-control build:
jobs 137009031447 and 137009021643 failed with compiler exit `0xc00000fd`;
isolated retry 137011053813 failed too. The History sources are unchanged from
PR #330. Those failures are not numerical passes and remain under investigation.

The [immutable packet manifest](../benchmarks/results/native-frozen-grid-raw-v1/manifest.json)
pins separate normal/optimized archives to preserve the existing per-archive
byte ceilings. Each contains all twenty successes, six rejections, original
source/build/input/output/exit receipts and the successful directory replay.
The development archive retains the first positive case and refused 64-bit-only
build. No failed record is replaced by its successor.

| Archive | Bytes | Members | SHA256 |
| --- | ---: | ---: | --- |
| normal.zip | 4,606,322 | 234 | `527f77a5bbce5faf365b16c89006a865ea792f2289534907b2a23aed1df3d9b2` |
| optimized.zip | 4,606,418 | 234 | `6039823ffa32b1f1c930895d94f5d0eb5bb2fe8c69e6fa5519e8d576b012199b` |
| development.zip | 1,020,556 | 63 | `c17c6c8f17b98d7892730f2f889049b4c1b7288dad2c0c4c7c60281210246e2c` |

`python -B -m scripts.replay_native_grid_raw_packet` authenticates every member
and the saved executable bytes, then replays both matrices with current
independent math and zero native calls. The same entrypoint under `-O` remains
a required saved-replay check. Both [normal](../benchmarks/results/native-frozen-grid-raw-v1/archive-replay-v2-normal.json)
and [optimized](../benchmarks/results/native-frozen-grid-raw-v1/archive-replay-v2-optimized.json)
archive replays pass. Saved-evidence controls also reject malformed commit
identity, missing source, forged blob/source bytes (including a self-consistent
replacement digest), unobserved/retried exits and altered stream bytes before
numerical replay; both interpreter modes pass. Review found the first archive
wrapper did not authenticate its current outer helpers. The maintained V2
entrypoint now checks its own committed bytes and all outer helpers before
project imports, rechecks them after replay, and reports their hashes. V2 also
checks each independently feasible request and all 26 cross-mode stream hashes.
The earlier replay records remain retained. Dedicated platform job/step results
are pinned in the [CI receipt](../benchmarks/results/native-frozen-grid-raw-v1/ci-296836f.json).
The development packet is historical evidence,
not an additional numerical acceptance claim.

This proves fixed-policy raw arithmetic only. Evolving policies,
sampled learning/clipping, sparse/paged State lifetimes, independent quality,
eleven-card admission and realistic heads-up NLHE remain unresolved. The next
architectural gate must address repeated full-policy setup and storage instead
of raising the existing limits or interpreting this finite game as the goal.
