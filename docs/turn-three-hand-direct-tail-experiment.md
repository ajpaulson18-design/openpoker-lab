# Three-hand TURN direct-tail experiment

This is a separate single-call research experiment using the unchanged
[direct original-weight TURN API](direct-turn-tail.md) and the independently
checked [three-hand physical auditor](turn-three-hand-physical-audit.md).
The protocol and runner are reviewed and committed before training. The larger
fixture has no separately proved equilibrium value; its control-policy anchors
must not be presented as one.

## Frozen game and request

Board `Js8d4c2h`; OOP `AsAh:0.5,KsKh:1,QsQh:0.75`; IP
`AcAd:1,KcKd:0.75,QcQd:0.5`. Both streets use pot100, stacks220,
half-pot bets/raises, one raise and `include_all_in=False`. Nine compatible
private pairs retain their original global weights over 44 legal rivers each:
396 physical worlds and 48 public river cards. The complete raised public tree
has 3,039 states and 1,254 decisions, with 3,606 private information rows.

Call `solve_turn_tail` exactly once with `iterations=750, discard=250`.
Average completed sweeps251..750 with their original weights, totaling500
sweeps and250250 weight. This schedules1500 regret and500 averaging passes.
It is distinct from weighting the window by1..500.

| Full-request admission | Charge | Existing cap |
| --- | ---: | ---: |
| World/node work | 28,512,000 | 30,000,000 |
| Dense hand/state work | 20,540,601 | 30,000,000 |
| Information-action slots | 8,046 | 1,000,000 |
| Prefix-hand edges | 405 | 250,000 |

All candidate/world, tree and requested-iteration guards also remain active.
Discarding sweeps does not reduce requested-work admission. These are modeled
counts, not elapsed-time or resident-memory guarantees.

## Validation and acceptance

Freeze the committed source context and HEAD before constructing the independent
model or running the check/call control. The control's exact metrics must match
the closed-form anchors and independent numeric replay before the single API
call. Check the frozen sources again immediately before invoking the API.

The returned raw policy must match every fixed game, schedule and resource field
of the actual API. Independent numeric rules compare all eight API diagnostics
within1e-9. The separate exact auditor reconstructs legal rows/actions, exactly
normalizes the original binary64 values and computes both legal own-hand best
responses with all hidden opponent hands and future rivers aggregated correctly.
All eight exact metrics must agree with independent numeric replay within1e-9.
Keep exact gains, zero-sum/response identities and the legal interval
`[-BR_IP, BR_OOP]` separate from numerical diagnostics.

The unchanged quality target is exact normalized-policy NashConv<=1/1000 chip.
Record met/miss and exact-zero status separately. A valid target miss remains
accepted evidence. Save the raw policy without cleanup, window changes or an
adaptive retry. Earlier 176-world TURN and river evidence retains its original
scope and bytes. This is one configured finite heads-up game, with no unrestricted
Hold'em, speed or general convergence claim.

Time the entire API call starting before its lazy import, including the
immediate frozen-source check before invocation; independent pre/post
mathematical audits are outside that interval. The one uncontrolled observation supplies no
equal-cost comparison. Timing must be finite, nonnegative and nonboolean.

## Saved evidence and verification

The new canonical LF files are:

- `benchmarks/results/turn-three-hand-direct-tail-v1.json`
- `benchmarks/results/turn-three-hand-direct-tail-v1-policy.json`

Each has a4,000,000-byte pre-read and pre-stage ceiling. Generation uses exclusive
targets and staged files, retains descriptor-derived identities, verifies actual
stage and final bytes against the original validated bytes, and reconstructs the
complete report at both stages. Rollback removes only identities it created.
Source/HEAD checks precede the final bundle identity/byte check.

Producer fingerprints cover every top-level `pokerlab/*.py`, required adapter
and experiment tests, runner, pure publication helper and independent math
sources. Re-enumeration detects additions during generation. Verification pins
the complete independent reference/rules/rank/audit/helper graph and experiment
test sources. Current sources must match committed bytes before generation and
remain stable throughout.

Read-only verification executes no producer or trainer. It checks current
committed verification sources and stable HEAD, validates historical generation
context, rebuilds all metadata, controls, exact metrics, counters and target
decisions, and reconstructs the whole canonical report. Recorded numerical
observations require strict type/key/finite checks and the fixed1e-9 comparison
gate; exact quantities and structural counters remain strict. Historical Git
objects are not required merely to replay accepted files.

Any returned result rejected after the call is preserved under
`work/turn_three_hand_tail_rejected/` with source context, schedule, timing or
invalid-timing representation, reason, and raw bytes or a safe representation.
It is rejected evidence, not an accepted benchmark. Never silently rerun it.

Run `python -m scripts.benchmark_turn_three_hand_tail --verify` to replay saved
files. Generation uses `--generate` only after the reviewed source freeze.
Executed source identities, tests, raw hashes and quality results are recorded
after the corresponding work finishes; this protocol alone reports no run.

Before source freeze, all 21 integrated runner tests passed in normal Python
(56.412 seconds) and optimized Python (57.708 seconds). The mathematical
control and policy audits are real; generation/fault tests use explicit API
stubs and prohibit the trainer. A separate Sol source review found no blocking
issues. The earlier 2,449-second synthetic-suite timing outlier did not recur
in a bounded lifecycle profile (40.944 seconds); that profile exposed a test
cleanup error, fixed before these integrated passing runs. No performance
claim follows from those test timings.
