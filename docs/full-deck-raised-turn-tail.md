# Same-run raised-turn CFR+ averaging experiment

This research experiment uses the [fixed full-deck raised turn/river
game](full-deck-raised-turn.md). The window is declared before training:
discard D=1,000, complete T=1,500 sweeps, retain original CFR+ weights t on
sweeps 1,001–1,500. Run both materialized and matrix-free backends with no
stopping target. The reporting target remains NashConv <=0.001 chips; retain
every miss. Both actual calls completed at the source checkpoint below.

## Capture and realization identity

Each backend executes one complete production call. Observational callbacks
capture completed-sweep average policies at D and T and return false. The final
callback must match the returned production policy exactly. Hand indices retain
range insertion order, and every serialized private-hand/history/action identity
must match its trainer key across both streets and river reveals. Callback
bindings are restored on success and exceptions.

The current same-run full payload must match that backend's immutable
1,500-sweep baseline bytes. Its captured prefix strategy must match the saved
1,000-sweep baseline strategy. Those historical policies are comparison anchors;
only the two snapshots from the current single trajectory feed conversion.

At an information row, CFR+ accumulates
`fixed_own_mass * t * own_action_reach * action_probability`. The physical
marginal is fixed across sweeps and cancels from row normalization. Public
chance does not multiply own action reach. Perfect recall therefore lets products
of the averaged own-action probabilities recover averaged realization flows,
including across a river reveal. Opponent reach must not enter that product.

For each own-sequence flow, with W_D=500,500, W_T=1,125,750 and
W_tail=625,250:

`tail_flow = (W_T * full_flow - W_D * prefix_flow) / W_tail`.

The existing river realization helper supplies exact Fraction subtraction,
normalization and correction ledgers. This turn wrapper first establishes its
chance/perfect-recall preconditions with a separate exact synthetic oracle and
complete independent physical-policy replay. The helper's existing rejection
tolerances and zero-reach fallbacks are unchanged. All legal rows remain present.
The synthetic oracle varies both players' own reach, opponent policies, fixed
row marginals and river policies. It checks direct original-weight tail sums;
fixed chance mass cancels a local behavioral row but would give the wrong scale
for own realization flow.

## Cost, evidence and scope

The full 1,500-sweep request retains the unchanged production work admission:
25,344,000 materialized units and 27,369,234 matrix-free units, each below
30,000,000. A tail containing 500 averaged sweeps still costs the complete
1,500-sweep training call. The derived prefix explicitly carries inherited full
request resource metadata. These modeled counts do not bound callback overhead,
CPU, serialized bytes or RSS.

Full production returns remain untouched. Derived prefix/tail profiles use
research provenance and independently derived metrics. Save all six complete
prefix/full/tail policies, all eight metrics, hashes, correction ledgers, full
call observations and separate conversion/replay timings. Before long calls,
freeze and commit the implementation and test sources. Sources, current HEAD and
accepted file bytes must remain stable across generation and saved replay.
Accepted baseline/reference bytes are checked before and after each complete
capture, so input drift prevents the next expensive call. Generation records all
current Python solver fingerprints. Saved verification requires current critical
proof sources to match; broad historical solver entries remain validated context,
allowing unrelated earlier-street additions. Separate review checks every
generation pin against its committed revision, and the accepted-report test binds
the complete published report hash.

Correction ledgers live in the report rather than being duplicated into policy
payloads. Each policy is bounded to 2,000,000 bytes and the report to 8,000,000 bytes before
reading. Publication is exclusive and atomic; staged and published verification
must pass. Failed generation removes only files created by that attempt. Saved
verification reconstructs complete derived payloads and ledgers without training
and without repairing stored metrics. The accepted baseline is immutable.

Cheap ten-sweep probes and synthetic publication fixtures test the harness;
they are separate from the completed 1,000/1,500-sweep experiment. Numeric tail replay is not
an exact certificate. The [separate checked quotient auditor](full-deck-raised-exact.md)
may audit a later class-constant tail under its own validation requirements.
Production averaging/defaults, earlier streets and all existing proofs remain
unchanged.

## Reproduction

The 22 integrated checks passed in normal Python (229.456 seconds) and optimized
Python (235.691 seconds). They include cheap real ten-sweep captures, an exact
turn/chance realization oracle, complete synthetic publication fixtures with zero
new long training, saved-data mutation checks and owned-file rollback. Separate
read-only review found no remaining blocker in the artifact guards, file ownership
or provenance checks. These preflight checks preceded the two long calls.

## Recorded numeric experiment

Generation was frozen at `0040b6fb5ee936ac1c18d10e5a48e2f3b7d4c4cf`.
Both production calls completed all 1,500 sweeps without a stopping target.
All 75 source fingerprints match that committed revision. The
[immutable report](../benchmarks/results/full-deck-raised-turn-tail-v1.json)
is 4,556,002 bytes with SHA256
`9e51cbcf9f031f371806be06e6a23589e0dd27d5e3ffffcf36fc545eed5d6998`.
All six complete policies remain saved, each below the unchanged 2,000,000-byte cap.

| Profile | Averaged sweeps | Materialized numeric NashConv | Matrix-free numeric NashConv | Target met |
| --- | ---: | ---: | ---: | --- |
| Prefix | 1–1,000 | 0.0037309341770424 | 0.0037309341770424 | No |
| Full | 1–1,500 | 0.001658745330324507 | 0.001658745330324507 | No |
| Tail | 1,001–1,500 | 0 | 0 | Yes |

All four prefix/full misses are retained. Numeric zero is not a formal exact-zero
claim. Full policies match the immutable original 1,500-sweep bytes; prefix
strategies match their original 1,000-sweep anchors. Each backend performed
exactly one trainer call with completed-sweep callbacks at 1,000 and 1,500.
Complete calls with observations took 159.226 and 594.151 seconds respectively;
tail conversion took 1.940 and 2.028 seconds. These uncontrolled observations
provide no general runtime or RSS claim.

Exact subtraction records small negative raw child flows caused by serialized
input rounding: 935 materialized and 814 matrix-free, with largest magnitude
4.402e-20 and 2.485e-20 respectively. Existing helper projection/fallback rules
remain unchanged, and complete correction ledgers are saved. A separate Sol
reconstruction of the serialized own-sequence flows, without importing the
candidate capture or conversion modules, found maximum discrepancies of
1.613e-17 and 2.169e-17, below its predeclared 1e-11 check. It independently
replayed all six complete physical policies; the largest production/replay
metric difference was 3.553e-15 chips.

Staged, published and separate saved replay passed with no further training.
The accepted-report test binds the complete report hash and disables production
training entry points. The separate exact audit remains necessary for stronger
claims about explicitly normalized policies.
The accepted-report test passed in normal Python (19.165 seconds) and optimized
Python (18.483 seconds), with all capture/training entry points disabled.

Run `python -m unittest tests.test_turn_tail_capture tests.test_turn_tail_realization tests.test_benchmark_turn_tail tests.test_turn_tail_artifacts -v`
and repeat with `python -O`. After source freeze,
`python -m scripts.benchmark_turn_tail --generate` executes the fixed two-call
experiment. `--verify` replays accepted saved artifacts without training.
