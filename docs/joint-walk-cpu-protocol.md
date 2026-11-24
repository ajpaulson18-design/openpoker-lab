# Joint walk CPU protocol

Status: frozen measurement protocol, not an executed CPU attribution result.
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
