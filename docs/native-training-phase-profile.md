# Bounded native training phase diagnostics

The ten-card bounded-division T2 fixture has a separate diagnostic build.
The standard trainer compiles without phase hooks. This is a measurement
tool for the existing finite game, with no additional capacity or quality claim.

## Build and request boundary

Build the standard executable with target `virtual-dyadic-training`
and the diagnostic executable with target `virtual-dyadic-training-profile`
using `scripts.build_native_exact_four_street`.
Only the latter target defines `OPENPOKER_TRAINING_PHASE_DIAGNOSTICS`.
Its manifest names the target, flags, compiler, executable and source closure.

The diagnostic executable accepts the existing bounded-division training
request, an absolute fresh `page-images` scratch path and the third argument
`--profile-phases`. The host cohort selects the diagnostic target only when
`--profile-phases` accompanies `--train --ten-bounded-division`.
Other requests and unknown flags are rejected before scratch preparation.
The standard executable rejects the profiling argument.

An independent comparison against source `927e4a3` found the normal
Driver header and probe main token-identical after selecting the normal
preprocessor branches. The normal constructor and train signatures are
restored; compile-time assertions guard the differing signatures. This
is source-level hook separation, not proof of identical machine code.

## Bounded measurement contract

The recorder has 64 fixed event slots and permits at most 80 clock reads.
This fixture uses 36 events and 43 reads, including the origin and six
outer timestamps. The object occupies 1,064 bytes on the measured Windows
build; the resource bridge reserves 2,048 bytes, 256 logical entries and
8,192 work units. It adds those diagnostics to the inherited composed
budgets before admission and leaves the solver's ledgers unchanged.

The phases cover Plan preflight; Chance and other owner setup; row
registration; freeze; prelude; per-sweep policy construction, policy
emission, inclusive walk, commit and checkpoint streaming; average
export; and footer extraction. Checkpoint intervals include stream
flushing. There are no per-row, per-contract or arithmetic clock calls.

Driver includes Plan. The verifier reports Plan and the remaining
Driver interval without counting Plan twice. It partitions the training
interval into non-overlapping leaf phases and a nonnegative residual,
and reports outer output work separately. State/Chance/History cleanup
after the last phase remains in the training residual.

The measurement excludes startup and request parsing, sidecar writing,
Driver destruction and process exit. The independent complete-call
timing includes process execution and streamed transport. These are
different intervals and should not be compared as equal durations.

The strict independent verifier checks the bounded sidecar's schema,
finite integer types, exact event order/sweeps, clock census, monotonic
and hierarchical timestamps, nonnegative residuals, and resource
derivation. It makes no native producer calls.

## Frozen studies and limits

The [immutable packet](../benchmarks/results/native-dyadic-phase-profile-v1/manifest.json)
retains both source-frozen studies and all timing observations.

The first study used one executable with hooks disabled or enabled.
Instrumentation's median paired ratio was 0.99002, while the disabled
hooked executable versus the pristine baseline measured 1.01857.
The latter missed the predeclared 1.01 limit. Its phase ranking was
provisional and the study was not accepted. A separate diagnostic build
was then introduced; the limit was unchanged.

The revised study at `53a4072` uses eight alternating pairs for each
comparison. Diagnostic instrumentation measured a median paired ratio
of 1.00327 (0.33 percent overhead). The standard trainer versus the pristine
baseline measured 0.99392; this passes the overhead limit and is not
claimed as a causal speedup. Both comparisons passed the unchanged
1.01 limit, and every one of the 32 complete training calls reproduced
the reference artifacts. Walk ranked first in all eight enabled runs.
Its median fraction of the measured interval was 69.05 percent, followed
by checkpoint streaming at 12.88 percent and policy construction at
8.40 percent. These are wall-time observations on one Windows host;
other host load was uncontrolled.

Both studies reproduce the pristine baseline's complete compact and
expanded outputs, policy spill, row directory, checkpoint images and
visible-information best responses. Enabled and disabled saved-only
replays enter no native producer. The second study archives one raw
checkpoint pair; duplicate timed outputs are represented by their exact
identities against the archived reference.

All 89 focused controls pass in normal and optimized Python, with no
skips. Native deterministic vectors verify all 26 fake-clock events and
failure guards. The packet preserves the initial temporary-directory test
failure and its test-only correction, the first auxiliary vector-operator
failure and correction, and a timing-operator syntax failure before any
timed calls. These are distinct from the completed timing studies.

## CPU samples inside the walk

The [CPU evidence packet](../benchmarks/results/native-dyadic-walk-cpu-v1/manifest.json)
captures three complete calls of the standard bounded-division trainer at
`53a4072`, using the same Windows executable as the earlier code-layout
control. Each call reproduced the 50,507,464-byte training stream, both
checkpoint files, the policy spill, and the row directory byte for byte.
The collector requested 4,000 CPU samples per second and reported no lost
events or buffers.

The replay counts samples whose native stack contains `Walk::visit`.
Each row below counts a function entry anywhere in that stack. Nested
functions share samples, so the percentages cannot be added.

| Function on the walk stack | Capture 1 | Capture 2 | Capture 3 |
| --- | ---: | ---: | ---: |
| Walk samples | 16,327 | 16,407 | 14,054 |
| Terminal evaluation | 31.2% | 31.2% | 31.3% |
| State row staging | 30.7% | 28.7% | 28.9% |
| Prepared Chance contraction | 15.3% | 15.4% | 14.6% |
| Pager dirty-page flush | 13.4% | 12.6% | 12.3% |
| History visit action | 0.3% | 0.5% | 0.5% |
| History visit reveal | 0.1% | 0.1% | 0.1% |

Terminal evaluation or State row staging appears in 59.9–62.0% of the
walk samples. Dirty-page flushing belongs to the staging path and
prepared contraction belongs to the Chance path. These observations
prioritize reducing packed State staging and pager work, then separating
terminal contraction from the remaining payoff and parent arithmetic.
An owner-level change must reproduce the exact output and checkpoint
images and improve complete-call elapsed time in a matched comparison.
The eleven-card resource forecast still projects work above the current
State, quantizer, and composed ceilings.

To reproduce the capture, authenticate the source-built standard target
at the packet's source revision and attach the Visual Studio command-line
collector to the trainer before supplying the manifest's request, with
a fresh absolute `page-images` path. Use `CpuUsageHigh.json` and stop
the collector after the trainer exits. Extract the auxiliary ETL from
the diagnostic session and use `xperf -a dumper` on that ETL. Relink the
same object with MSVC `/MAP`, and compare the native `.text` bytes and
section address with the sampled executable before using the map. The
packet's `normalize.py` takes the xperf CSV, linker map, and a fresh output
path. `replay.py` recounts the three archived captures without running or
compiling the trainer.

The archive keeps only the trainer's relative instruction addresses,
relative timestamps, sample counts, and matched linker names. Symbol
attribution uses the preceding function entry and retains aliases at the
same address. Inlined work may belong to the surrounding named function.
CPU samples describe one host and one finite ten-card fixture. The
earlier elapsed measurements use different intervals, including time
waiting for I/O.

## Staged-page reuse

The [staged-page study](../benchmarks/results/native-dyadic-staged-pages-v1/manifest.json)
tested a read cache of seven pages per field and a two-page dirty buffer
per field, evicting the least recently used dirty page. The baseline has
eight read pages and one dirty page per field. Both layouts retain 18 pages
in total across the two fields. The candidate uses 1,022 additional bytes
for dirty coverage metadata. The measured executable enables the layout
only for the bounded-division ten-card fixture through the explicit
`virtual-dyadic-training-staged-pages` build target.

| Ten-card T2 pager measure | Baseline | Candidate |
| --- | ---: | ---: |
| Physical write requests | 18,836 | 2,390 |
| Physical read requests | 1,498 | 1,495 |
| Physical read words | 6,130,244 | 6,115,174 |
| Physical write words | 5,925,444 | 5,925,444 |
| Pager resident bytes | 591,008 | 592,030 |

An independent rank-free model predicts the same counts from row extents
and traversal order. The native pager kept the existing request and word
ceilings and added a bookkeeping allowance for the extra buffer lookup
within the existing composed work ceiling. Every complete call reproduced
the numerical stream, checkpoint images, policy spill, and row directory.
The eight changed stream footer fields match the predeclared differences
in resource bookkeeping exactly.

The candidate was faster in every one of the eight alternating pairs.
Its median paired elapsed ratio was 0.85721 on the measured Windows host.
Both executables used the same fixed request and file capture procedure.
The published protocol keeps both warmups and all paired observations.

For the eleven-card fixture the rank-free model projects 8,040 writes
instead of 59,328, and 20,578,900 physical read words instead of 20,750,932.
The projection preserves all stage coverage. Eleven-card exhaustive
training still exceeds the composed, State, and quantizer ceilings.
The next measured work is to separate Chance contraction from the other
terminal costs and check which operations can be reused without changing
signed values, blocker conditioning, or full-history row identity.

## Caller-owned Chance output

The [contraction output study](../benchmarks/results/native-dyadic-contraction-output-v1/manifest.json)
compared the staged-page trainer with an explicit build that supplies
output storage for each exact Chance contraction. Both paths use the same
admission, ranking, blocker filtering and exact arithmetic. The owning
interface remains available. Borrowed output rejects a mismatched size
or overlap with the reach before query allocation or ranking and clears
stale values on an admitted call.

Every complete call reproduced the previous 50,507,464-byte training
stream, both checkpoint images, policy spill, directory and pager receipt.
The eight alternating pairs gave a median elapsed ratio of 0.94101.
The candidate was faster in five pairs, short of the predeclared six.
The benchmark remains opt-in. The packet preserves all timed observations
and both warmups.

The independent literal evaluator checked 135,096 reduced-deck results
with reused output, across the sparse-pair and blocker-bucket kernels.
It also checked 5,304 saved row values for one physical river, with all
1,326 holdings on each side, heterogeneous prior and reach numerators,
both player perspectives, and fold and signed showdown contractions.
The saved-only full-deck check compares individual row values to a
literal enumeration of compatible opposing holdings.

### Repeated all-in completion work

The [rank-free census](../benchmarks/results/native-dyadic-contraction-output-v1/early-terminal-census.json)
counts the calls grouped by early terminal and visible prefix in the
current betting tree. Each group shares an immutable opposite reach.
No decisions occur while enumerating the group's hidden completions.

| Deck and range fixture | Early groups per seat pass | Hidden board calls | Calls beyond the first per group |
| --- | ---: | ---: | ---: |
| Ten cards, pinned ranges | 9,070 | 23,800 | 14,730 |
| Eleven cards, pinned ranges | 19,412 | 78,400 | 58,988 |
| Full deck, all physical holdings | 58,786,002 | 3,638,544,000 | 3,579,757,998 |

The full-deck row is projected geometry for this fixed betting tree
before zero-reach effects. It carries no training admission or speed
claim. The counts measure the opportunity to compute the opponent's
integer weight times its reach once per group. Board blockers and
hand ranks must still be evaluated for every included completion,
and the common reach exponent must remain exact. This change would
avoid a repeated weighting pass without retaining a pair-by-board
payoff table. Eleven-card exhaustive admission still requires larger
reductions in the State and policy quantization work.

Recount the geometry with
`python -m scripts.census_virtual_dyadic_terminal_reuse`.
The matched Windows operator is
`python -m scripts.benchmark_native_terminal_buffers --help`.
Build `virtual-dyadic-training-staged-pages` and
`virtual-dyadic-training-terminal-buffer` at the manifest's training
source. Use the previous staged-page candidate's warmup directory as
the reference to authenticate the complete stream and sidecars.

## Prepared reach across hidden showdowns

The [weighted-reach study](../benchmarks/results/native-dyadic-allin-weighted-reach-v1/manifest.json)
prepares the exact integer product of prior weight and reach once per
opposing holding. One scope owns both weighted vectors and their original
dyadic exponents. Each completion still excludes that board's blocked
holdings, applies private blockers, and uses its own signed rank relation.
Rank planes and ordered public history retain their existing rules.
The scope admits both live vectors before allocation and releases them
when the family ends. It retains no pair-by-board payoff table.

The ten-card study compared an all-early selector with a selector that
requires at least four physical completions for any compatible private
pair. A fixed private pair has six possible ordered completions on a
ten-card flop and two on a ten-card turn. The four-completion selector
therefore prepares 1,292 families and serves 21,760 showdown contractions
during the paired two-sweep run. Both selectors reproduced all numerical
bytes, checkpoint images, policy, pager receipt and row directory.
Only the admitted and observed Chance work and scratch fields could
differ in the complete stream footer.

| Ten-card comparison | Observed Chance work | Forecast Chance work | Median elapsed ratio | Pairs faster |
| --- | ---: | ---: | ---: | ---: |
| Same-source staged-page baseline | 70,637,650 | 132,742,404 | | |
| Prepare at every early all-in | 71,012,170 | 132,636,514 | 0.99505 | 5 of 8 |
| Prepare at four or more completions | 70,462,886 | 132,404,050 | 1.00267 | 4 of 8 |

Both ten-card selectors missed the preset timing gate of 0.96 and six
faster pairs. The rank-free model reproduced both native forecast
differences. Its eleven-card forecast projects a Chance reduction of
1,421,968 work units for the four-completion rule, with no new training
admission. The existing State, quantizer, and composed work ceilings
remain binding for exhaustive eleven-card training.

The full-width component used two 1,326-holding ranges, a fixed turn,
12 legal rivers, and 16 repeated scope lifetimes. It completed 384
showdowns per child under the existing work and storage limits.
Modeled work fell from 342,447,725 to 333,253,837. Peak live integer
payload rose from 3,683,728 to 4,187,977 bits. The median complete-call
elapsed ratio was **0.87223**, with six of eight pairs faster. All 18
children emitted identical numerical captures. The independent saved-only
verifier checked 31,824 captured values by literal hand-pair enumeration
and independent ranking across all 12 rivers and both seats. This
measurement covers the Chance component for one fixed turn on one host.

The prepared-reach trainer remains available only through the explicit
`virtual-dyadic-training-allin-reach` study target. The packet keeps all
timing pairs and both misses. The native Chance suite passed all 17
focused tests, including small-range sparse and bucket kernels, both
full-width ranges, reveal-order rank-cache reuse, and scope guards.

Run the operators with `python -m scripts.benchmark_native_allin_reach --help`
and `python -m scripts.benchmark_native_wide_reach --help`. Build at each
study revision listed in the manifest. The ten-card comparison expects
the staged-page study's `warm-reuse` capture as its exact reference.
Recount the forecast with `python -m scripts.forecast_virtual_dyadic_allin_reach`
and verify the compressed numerical capture with
`python -m scripts.verify_virtual_dyadic_wide_reach PATH`.
