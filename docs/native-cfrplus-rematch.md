# Native CFR+ targeted policy refresh

The [public native trainer](../native/fixed_street_train.c) keeps each player's
current policy as the deterministic regret match of that player's regrets.
After an alternating CFR+ update, only the updated player's regret rows change.
Refresh all of that player's rows, including zero-reach and zero-regret rows;
the other player's policy remains current. The final player-1 refresh leaves
both policies current for the next sweep, so only the first CFR+ sweep needs a
full initialization. The completed-sweep average pass changes sums, not regrets
or policies. This is an independently implemented cache of redundant arithmetic,
not a different update or averaging rule.

The old full rematch function, scalar path, vanilla and DCFR paths remain.
Targeted refresh preserves the exact compensated sum, action and hand order.
Every original protocol, heap, tree, slot and requested-work guard remains;
the old conservative rematch charge is retained. No larger game or iteration
request is admitted. Old source-built executables require explicit rebuilding.
The default Python paths and independent diagnostics are unchanged.

## Frozen experiment

The [specification](../benchmarks/native-cfrplus-rematch-v1.json) and
[runner](../scripts/benchmark_native_cfrplus_rematch.py) compare the preserved
previous trainer with the optimized source build through the single cold native
flop API. Both use the same count helper and identical compiler/flags/protocol.
The baseline source is reconstructed from a pinned Git commit and must reproduce
both raw and LF manifest hashes. Only the benchmark temporarily binds that source
file for the ordinary strict backend checks; production never accepts stale
source or falls back to an old executable.

Each of the two weighted 58-pair games receives three alternating old/new cold
complete-call pairs at 4,000 CFR+ sweeps, plus vanilla/DCFR controls at 10/100
sweeps: 28 full policies total. Complete timing includes the call, native counts,
training, exact Python diagnostics and canonical serialization/hash. Source/build
checks, GC, historical source binding and independent replay are outside timing.
Historical and optimized training each hash their actual source file through the
same backend code. All requested admissions finish before helper lookup.

Every paired policy wire must be byte-identical; complete output must match
exactly after removing only the trainer build manifest. All saved policies must
pass independent physical-count/numeric-rule/own-hand response replay at 1e-10.
The unchanged final CFR+ NashConv target is 0.005 chips, and each frozen complete
median ratio must be at least 1.02. Every sample, control and target miss is
retained. There is no allocation, RSS, general speed or unrestricted equilibrium
claim. Measurement results and GitHub publication are recorded separately.

[Checkpoint tests](../tests/test_native_cfrplus_rematch.py) cover repeated actor
decisions, sparse own-hand IDs, zero signed pair mass, zero regret and zero reach,
all three algorithms and 1/2/3/10/100/1,000/4,000 sweeps, with independent small-tree
value and legal best-response checks and deterministic native policy hashes.
[Harness tests](../tests/test_benchmark_native_cfrplus_rematch.py) reject dirty
source before lookups and enforce fixed pair order, exact parity and the
unchanged timing gate. The original trainer/count executables are preserved.


## Measured result

The [raw report](../benchmarks/results/native-cfrplus-rematch-v1.json) passes all
frozen gates from clean source `ecf0a49ac88b333a1320e5de6e498f4047f1b72a`.
All 578 LF-normalized source hashes match the frozen Git blobs. Both source
snapshots and all three build identities are unchanged. All 28 policies pass
independent replay; old/new policy wires are byte-identical, and full payloads
match exactly after removing only the trainer build manifest.

| Weighted range case | Baseline complete median, seconds | Targeted refresh complete median, seconds | Observed ratio |
| --- | ---: | ---: | ---: |
| Base eight-by-eight | 0.692805 | 0.481534 | 1.44 |
| Reversed weights | 0.601019 | 0.461630 | 1.30 |

These three-pair medians include native cold counts, training, exact diagnostics,
return construction and canonical serialization/hash on this Windows host.
They apply only to these frozen fixtures. No sample was removed; there is no
allocation/RSS or general speed claim. Independent final NashConv is unchanged
at 0.0001049110234 / 0.0000422279060 chips, below 0.005. All vanilla/DCFR
10/100-sweep controls also retain byte-identical native policy output.

The strict MSVC build passed, as did the existing 29 native adapter/protocol/API
tests and the three harness/checkpoint tests. The repeated-actor checkpoint
regression covers all three algorithms at seven sweep counts. [Publication
regressions](../tests/test_native_cfrplus_rematch_publication.py) replay the entire artifact and reject re-signed baseline/count
provenance and raw-policy metadata tampering. CI and merge are checked on the
final publication commit; local execution alone does not establish publication.

Canonical report SHA-256:
`653ef0b66dc58d318814a8337837823f70645f9d929599f71a53ba50ab18d241`.
Raw report SHA-256:
`12153fe30518badc681a5bcd7e9061a0630caec6a40f538f64ba1c3323f6dc1d`.
The preserved original trainer has executable SHA-256
`6f5573a8d24f645a3689ee3aeae05d09626677e88c518a8c71cbb327586265ef`;
the optimized build is
`d036f194c8d48181c7f615402a819db7ad13338d109ca4b60f4d2f4e0279bcc1`.
