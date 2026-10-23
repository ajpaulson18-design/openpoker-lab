# Proposed JJ/KK physical source basis

This separate research study prepares three full-board source rows for pocket
jacks against pocket kings. It extends the existing project-owned
[best-five reference](preflop-generic-five-reference.md) through new orchestration;
it adds no evaluator, dependency, production backend, betting action or trainer.
The [frozen protocol](../benchmarks/preflop-jj-kk-basis-v1.json) and
[rank-free planner](../scripts/preflop_jj_kk_basis_plan.py) distinguish intended
work from completed physical evidence. No JJ/KK count is authenticated yet.

The [runner](../scripts/benchmark_preflop_jj_kk_basis.py) composes those existing
APIs without changing their sources. Its
[synthetic boundary tests](../tests/test_preflop_jj_kk_basis_benchmark.py) check
admission, stream retention, failure handling and no retry; they do not enumerate
physical boards. Commit the clean executable, protocol and tests before the
single observation batch. Keep its output and both builds outside the checkout.

## Fixed request and admission

The ordered SB/BB queries are `JdJs/KdKs`, `JdJs/KcKd` and `JdJs/KcKh`, covering
two, one and zero shared suits. Each pair has 1,712,304 unordered five-card boards.
The complete literal request rejects aliases, missing/extra pairs, changed order,
blockers and malformed cards before source reports or executables are resolved.
An exposed example dictionary cannot redefine the private fixed authority.

Both the reference and native production preparation retain their four-pair
per-request caps. The separate versioned aggregate ledger admits the entire
scheduled study before computation:

| Stage | Physical boards | Seven-card calls | Five-card subset calls |
| --- | ---: | ---: | ---: |
| Reference AA/KK calibration | 5,136,912 | 10,273,824 | 215,750,304 |
| Reference JJ/KK query | 5,136,912 | 10,273,824 | 215,750,304 |
| Native AA/KK calibration | 5,136,912 | 10,273,824 | Not applicable |
| Native JJ/KK recount | 5,136,912 | 10,273,824 | Not applicable |

The reference additionally compares all 2,598,960 five-card rank tuples against
the existing independent Python rules, producing exactly 15,593,760 raw bytes.
The current-build conformance API requires the AA/KK calibration; it is an
explicit validation cost, not a new AA/KK source-count result. There is no extra
AA/KK request beyond that calibration. Per method, the two physical count queries
total 10,273,824 boards and 20,547,648 seven-card calls; the best-five reference
also performs 431,500,608 subset calls. These named counts do not bound CPU,
elapsed time, allocated bytes or process RSS.

## Evidence required before reuse

Authenticate the pinned published AA/KK and QQ/KK count reports before counting.
Use explicit source builds in fresh external directories and record compiler,
flags, source, manifest and executable identities. No tool installation or binary
distribution is part of this study. The five-card conformance and AA calibration
must pass for the exact current reference build before the JJ query runs.

Require complete integer W/T/L coverage and exact best-five/native agreement for
each ordered JJ pair. Retain bounded raw stdout/stderr for all five numerical
subprocesses, complete result rows, stage/call receipts, source/build identities,
partial failures and original errors. Do not retry or substitute a fallback.
Source/build identities must be checked on error exits as well as success.
Compilation and structurally valid counts alone do not establish physical truth.

## Future scope

The rank-free forecast combines six AA, six QQ and six JJ SB hands against six
KK BB hands: 108 compatible physical pairs, within the existing prepared pool's
128-pair cap. This remains a forecast. An independently authenticated source
basis, joint suit transport, exact global priors and a new legal own-hand game
certificate are required before claiming that larger game's accuracy. The
existing 72-pair mixed-game witness does not automatically extend to 108 pairs.
There are no later-street decisions or equilibrium, convergence, runtime or
memory results in this plan. Shared turn/river kernels and the Coach workstream
remain separate.
