# Joint walk CPU protocol

Status: first execution at `fb4e8f3` stopped at collector startup. Windows WPR
returned `0xc5585011`, "Failed to enable the policy to profile system
performance." Both unprofiled warmups exited zero with the pinned complete
wire; no profiled call ran. A subsequent status check confirmed WPR was not
recording. The refusal and process receipts are preserved; no CPU attribution
or overhead acceptance is established. The protocol below remains frozen.
The [driver](../scripts/profile_joint_two_epoch_cpu.py) measures the accepted
same-world N9 two-observation request with selectors `0 0 0 0`. The independent
saved observation has 335,744 bytes and SHA256
`8e9c31ade82ee4e047be42a99189ddb71b8038cc456f02a97a8c7cf412b2596f`.
The candidate must have a current source-authenticated standard build. The
driver does not execute archived source or treat native values as a math oracle.

After two warmups, execute eight alternating profiled/control pairs, each
containing eight fresh complete processes: 64 profiled and 64 control calls.
Compare every complete stdout byte and actual exit, including resource fields.
WPR's installed CPU profile starts before each profiled batch and stops after
it; collector startup/stop is outside the measured native interval. The elapsed
interval includes the existing bounded process observer and stream capture in
both modes. Keep every observation, including misses. No automatic retry,
collector-setting change or resource-cap increase is authorized by this driver.

Predeclared acceptance requires at least 10,000 samples containing the joint
`Walk::visit` frame across profiled batches and at least 1,000 in every batch,
zero lost events and buffers, and median paired complete-call elapsed ratio
at most 1.05. A collected trace alone cannot pass attribution. A collector
refusal, insufficient samples, unresolved symbols or excess interference
remains a failed measurement gate.

Raw system ETL and xperf CSV stay outside the repository. Normalize only the
recorded candidate process IDs and matching module into relative code addresses.
Before attributing symbols, relink the exact object with a linker map and
verify identical `.text` bytes, virtual extent and RVA to the sampled original
image. Do not sample the relinked image as if it were the original. Record
inclusive family counts separately from a disjoint deepest-project-frame
partition; retain inlined/unresolved residuals.

The new path has no Chance contractions, but ticket selection still costs CPU.
`with_joint_ticket` encloses the entire callback; its inclusive stack cannot
be labelled Chance-exclusive cost. Distinguish policy/Catalog calls within
the walk from the post-walk joins/staging and commit. The old ten-card pager,
terminal and contraction percentages from [PR313's profile](native-training-phase-profile.md)
do not transfer to this unpaged two-observation path. Logical work allowances
also do not measure CPU shares.

If stacks cannot distinguish inner costs, a separately source-frozen diagnostic
build may record a few phase boundaries per epoch, with exact standard-output
parity and a measured overhead gate. Per-row timers are excluded. Such coarse
timing cannot establish an inner-walk owner split.

## Frozen coarse fallback

The separate `virtual-weighted-joint-two-epoch-profile` target enables only
`OPENPOKER_JOINT_PHASE_PROFILE` beyond its standard weighted target. It records
22 phase boundaries with 23 clock reads and no row timers. Its explicit extra
reservation is 73,728 work, 256 entries, 16,384 payload bits and at most 4,096
stderr bytes; all fit inside the existing whole-request caps. Standard output
and resource fields stay byte-exact to the standard target; diagnostic costs
are separately declared in its stderr receipt, not hidden in standard counters.

The [paired driver](../scripts/benchmark_joint_phase_profile.py) first
independently replays the saved full52 weighted same-world request. It freezes
eight alternating pairs of eight complete calls, after two warmups per target:
64 timed standard calls, 64 timed diagnostic calls and four warmups. Every
actual exit and complete output wire must match. The median paired elapsed
ratio must be at most 1.05 before phase wall-time observations are accepted.
All pairs and misses remain evidence. Recorder/source/compiler identities must
stay unchanged. This is wall time on one host and named finite-tree request;
it cannot attribute inclusive/exclusive CPU costs inside the walk.

The first coarse attempt at `3eb31c6` completed all 132 actual native calls
with exact full output parity. Its median paired elapsed ratio was
`1.064411483346797`, missing the unchanged `1.05` gate. Its phase percentages
are retained as unaccepted observations and must not drive a CPU optimization.
The next source revision moves the same bounded recorder off the core stack
and keeps clock/formatting bodies out of its inlining budget. It retains the
same request, call count, output identities, recorder allowance and overhead
threshold. This change is a diagnostic-layout experiment, not a solver speedup.

The second attempt completed all 132 calls and exact wires but also missed:
median ratio `1.0798650063384851`. The two standard targets have identical
`.text` bytes, extent and RVA, so the standard solver did not change between
these attempts. Their observations remain unaccepted. Source inspection then
identified fragmented `std::cerr` formatting: the unit-buffered stream flushed
each insertion. The next diagnostic formats one fixed 1,280-byte record and
writes it once. Its 24-event recorder plus overlapping JSON scratch still fit
the same 2,048-byte/256-word metadata reserve; no allowance or gate is raised.

The third attempt at `f756eaf` completes all 132 calls with exact complete
wire parity and passes the unchanged overhead gate: median paired elapsed ratio
`1.04213734326561`. All three standard images have identical `.text` bytes,
extent and RVA. On this one host and weighted full52 same-world request, the
accepted median phase shares are walk 34.01%, row joining/staging 25.83%,
template 12.81%, publication 8.08% and snapshot export 6.85%. These are
separately calculated wall-time medians, not additive CPU percentages. The
inner-walk CPU split remains open. Keep both earlier misses and the WPR
policy refusal alongside this acceptance.
