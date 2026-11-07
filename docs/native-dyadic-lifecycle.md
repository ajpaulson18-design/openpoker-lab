# Bounded exact State lifecycle

The explicit `Lifecycle::bounded_v1` is a prerequisite for longer
[unified training](native-dyadic-two-sweep.md). It permits one through
eight requested sweeps for the existing ordered, shared-policy,
row-covered and paged State components under their legacy resource caps.
The existing two-sweep lifecycle remains the default. The named nine-card
three-sweep trainer below uses the bounded lifecycle.

The owner admits the complete requested horizon before allocation.
Per-sweep spill receipts use a bounded array sized for that horizon,
with additional entries and bytes included in the storage forecast.
The existing two-record receipt API rejects this lifecycle; the new
read-only span exposes all generations begun so far without truncating
them. The current generation's counters continue to change until its
consumers finish and may record a partially built or failed generation;
callers copy records when they need a frozen receipt. An opened build
and a successfully committed sweep remain separate counts.
Policy builds still truncate the sweep-local mixed-policy file and
freeze it before any consumer reads. Read limits apply separately to
each generation; State work and pager traffic remain cumulative.

The immutable directory cache stays fixed. Its logical lookup ceiling
is `(2 + 4 * requested_sweeps) * rows`, corresponding to registration
output, four training consumers per sweep and final export. The enclosing
driver must separately admit its actual physical page traffic. The new
lifecycle rejects the named ten-card geometry until a versioned whole-game
forecast establishes all work, precision and I/O bounds.

After a complete commit, a copied checkpoint epoch identifies the sweep,
current file slot and previous sweep/slot. Slot zero is `committed.bin`
and slot one is `staged.bin`; the first commit selects slot one. These
files retain the final two generations and can be overwritten by later
sweeps. An epoch is metadata, not an immutable snapshot or an integrity
certificate. A checkpoint sink must authenticate each generation
before reuse and retain the grids required for independent update replay.
At the first commit, previous sweep zero denotes the initial image.
`previous_is_virtual` identifies a virtual-zero initial image whose file
can be empty; callers must not treat that slot as a complete saved file.

Component acceptance requires independently replaying every generation
of three-, four- and eight-sweep controls, including clipping, mixed-grid
rounding, raw averages, image slot parity and final export. It also requires
rejecting incomplete commits, excess sweeps, early/repeated exports and
cumulative budget exhaustion after successful earlier commits. Compilation
and executed results are recorded separately. Development controls pass
for one, two, three, four and eight sweeps, with six failure cases after
two successful commits. The failed-flush case accepts one third-generation
field write before the cumulative physical-request cap stops commit;
the current committed image remains unchanged and epoch access rejects.
The committed source-only cohort at `95ddf64` passed all twenty-six
focused tests normally and optimized, including the unchanged whole-game
admission and independent wire guards. Both outer exits were zero, with
no skipped tests and all 2,518 tracked files unchanged. The
[component evidence](../benchmarks/results/native-dyadic-bounded-lifecycle-v1/manifest.json)
retains the original compilation, fixture-admission and pre-import cache
rejections. Cross-platform CI remains a separate gate.
These component results do not establish a longer whole-game training
run or a convergence result.

## Streamed checkpoint evidence

The opt-in `--ten-sweep-stream` runs the accepted ten-card two-sweep
game with a separate checkpoint transport. After each commit and root
value record, the driver emits an `OPLCPG01` frame with three little-endian
64-bit fields for the sweep number, committed slot and image length. It
copies the flushed image from the pager's open committed handle before
the next sweep can reuse that slot.

Admission reserves 47,403,552 image bytes across both frames, a 32 KiB
buffer and 32-byte header, and 11,943,624 modeled copy units. The native
work reservation is 2,141,357,150 units. The stream carries 57,236,692
bytes. The bounded controller retains the 9,833,076-byte numerical stream
and an ordered SHA-256 digest for each image. It also records the full
transient stream digest and checks frame positions, slot parity and extent.

The saved-only verifier reconstructs every compact average and regret
word from its own exact training replay. It hashes those words in file
order and compares each sweep's digest. It also verifies the policy grids,
root values, final average and visible-information best responses from the
retained numerical stream. The ten-card transport profile is scoped to
two sweeps.

The source-frozen run at `83d143d` matched both prior image hashes and the
entire numerical stream. Independent digest replay reproduced both updates,
the exported policy and both best responses. The controller and verifier
exited zero, with all 2,523 tracked source files unchanged. Reconstruction
from retained numerical bytes, headers and the two final image slots matched
the complete transient wire digest. The evidence packet retains the numerical
stream and digest receipts and references the existing identical packed images.

The single Windows run took 7.43 seconds with a 5.10 MB peak working set.
The preceding paged-directory run measured 6.81 seconds and 5.04 MB. These
observations quantify the added checkpoint transport on this fixture.
[Streamed checkpoint evidence](../benchmarks/results/native-dyadic-sweep-stream-ten-card-accepted-v1/manifest.json)

## Nine-card three-sweep profile

The named `--proof9-t3` mode runs three simultaneous CFR+ sweeps of the
fixed nine-card four-street game with paired traversal, virtual initial
zero, row-covered paging and the shared policy spill. It admits the
entire run before training. The 642-bit representation covers the
three-sweep regret and average bounds. The forecast separately charges
the third sweep's general regret quantization and reserves 3,669,084
copy units for checkpoint transport. Together the numerical work and
transport reserve 700,169,489 units within the 750-million-unit cap.

The pager schedule uses 930,624 logical requests and writes 1,820,190
words across the three generations, reaching the legacy word limit.
The transport emits 17,141,340 bytes. The controller retains the
2,579,724-byte numerical stream and all three ordered image digests.
The independent verifier regenerates all three compact images, including
the first image whose slot is reused in sweep three. The final file
checks bind `committed.bin` to sweep two and `staged.bin` to sweep three.
The first two numerical updates and image digests must match the
previously accepted nine-card split-checkpoint run.
