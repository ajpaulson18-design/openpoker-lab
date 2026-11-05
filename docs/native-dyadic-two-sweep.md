# Fixed PROOF9 two-sweep training path

The explicit `virtual-dyadic-training` target joins the accepted
[fixed-profile proof](virtual-frozen-update-study.md) with the
[prepared chance, compact history and persistent state](native-dyadic-training-foundation.md).
It accepts only the pinned reduced nine-card game, exhaustive physical reveals
with q=1, and two simultaneous CFR+ sweeps. No existing solver entry dispatches
to this candidate. The admission-only development check passed; a source-frozen
trained-policy result and independent saved replay remain separate gates.

The driver visits all legal actions and prunes only a visible prefix with zero
physical prior support. Each target pass consumes the same exact ordered row
catalog, checking full history, global actor, original holding, and menu extent
before using a policy row. A frozen policy stays in force across both targets.
After both passes, the owner commits one complete regret and average update.
Average increments use only own past reach, own current action probability and
prior visible-prefix mass. Both sweeps have equal weight in this profile.

Early all-ins settle with no future decisions. The payoff routine streams their
remaining physically supported boards, adds the exact unscaled rank contractions,
and applies the fixed money stake and scale once. Those hidden completions never
become history tokens or strategy rows. The first rank-free admission correctly
rejected the earlier terminal forecast because it omitted these completions.
The corrected census has 17,356 visible showdown occurrences per target pass,
18,180 full-board showdown contractions and 22,168 hidden completion candidates.
It plans 140 hand ranks across 60 ordered-board planes; some unblocked holdings
have no compatible opponent on that board. No ranks ran during admission.

The complete planned workload is 473,271,268 named work units, 1,132,473
entries, 255,006,160 integer payload bits and exactly 22,587,756 output bytes.
These caps cover the declared implementation and fixture, with every owner and
parent work family separately bounded. They do not measure wall time or process
memory. The 500-million work ceiling, two-million entry ceiling, 65,536-bit
integer ceiling and `2^30`-bit payload ceiling are unchanged. The build-only and
`ADMIT` CI controls never launch `TRAIN`. The
[development evidence](../benchmarks/results/native-dyadic-two-sweep-admission-development-v1/manifest.json)
retains the first rejected build and admission, the strict final MSVC build,
the normal/optimized controls and the independent reference preview.

The binary stream saves the literal skeleton, ordered visible row keys, both
frozen current grids, both complete regret/average arrays and root holding
values, and the separately quantized final average grid. The reader independently
reconstructs ordered legal histories and replays all updates with literal joint
worlds. It evaluates the saved grid and chooses each best response after summing
all worlds indistinguishable by visible history and own holding. The production
driver does not retain those literal worlds. The independent oracle agrees with
every clipped regret and average slot in the accepted saved fixed-profile study.

`scripts.run_virtual_dyadic_training_cohort` requires the trusted source-only
launcher and a clean expected commit. It binds the full committed source to
actual build inputs, vendored headers and executable, observes an admission-only
child, and enters a single native training child only with explicit `--train`.
The independent replay runs after that child exits and after source and output
identity checks. Observe the outer controller exit and final bootstrap too.
An existing evidence directory cannot be reused. Repair a verifier or packaging
failure from its saved output; do not rerun a frozen numerical producer to fix it.
An exact two-sweep replay would establish feedback and a measured finite-game
policy, with no convergence or wider solver-quality claim.
