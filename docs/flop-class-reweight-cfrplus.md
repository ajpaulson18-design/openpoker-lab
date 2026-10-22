# Positive-prior fixed-flop CFR+ research adapter

This separate research entry trains only the three positive range distributions
covered by the [completed no-training proof](flop-class-reweight.md): baseline,
uniform and skew. It preserves the literal `2c3d4h` board, two hands per player,
three blocker-compatible pairs, ordered full-deck future reveals and finite
half-pot/no-raise action tree. Shared street kernels, old research sources,
production APIs/defaults and AI Coach are unchanged. This does not solve
unrestricted Hold'em or imply an equilibrium for untested priors.

## Admission and model boundary

`solve_reweighted(case_id, iterations=560)` accepts exactly those three case
strings and an exact integer T in `[1, 560]`; bool/float/unknown-case requests
fail before publication authentication, ranking or training. `case_plan` reuses
the strict exact rational planner and one global blocker-conditioned joint prior.
The existing compact admission authenticates the unchanged shared recurrence.
The new admission keeps that nested forecast unchanged and separately charges
126 binary64 mass-sum entries. At 560 sweeps, named training work is 75,046,160,
old fixed work 61,670 and new fixed work 126, for total 75,107,956 under the
explicit 76-million combined cap. These named loop entries are not all arithmetic,
CPU, elapsed time, allocated bytes or RSS. A separate physical census admits two
fresh oracles / 11,880 enumerated rows per standalone call and at most two live
physical games. Detailed proof arithmetic remains outside the named-loop model.

After complete admission, the call authenticates the immutable no-training proof,
reduces the old 560-sweep pilot to a small historical receipt, then independently
prepares a genuine baseline and weighted physical model. The distinct weighted
validator rebuilds/authenticates the quotient; the old fixed-prior validator is
never used on a new distribution. Before training it checks 126 exact positive
joint masses summing to one, positive finite binary64 conversion, 466 binary
information rows, per-player row counts and at most 33 visited states per world.
The converted world mass is used once by the unchanged shared CFR+ recurrence;
this conversion does not claim exact-rational training.

Exactly one zero-delay shared CFR+ call follows. All 466 raw average rows are
retained. The existing output rule normalizes their exact ratios onto the 2^-52
binary grid with exact complements, and records perturbations/lost support.
The normalized policy is lifted to all 16,912 physical rows. Independent guarded
checks compare eight exact class/physical own-hand best-response metrics, numeric
replay within 1e-10 and a bitwise physical lift round trip. Both preparation and
diagnostics retain all 41 forbidden-authority counters as exact integer zero.
Every completed report records exact priors, physical/baseline world hashes,
census, sources, admission, raw/normalized policies, full audit and the actual
`NashConv <= 1/200` result. A miss remains a miss.

## Independent saved policy replay

`python -B -m scripts.verify_flop_class_reweight_cfrplus --path REPORT.json.gz`
accepts a bounded full saved report (raw JSON or gzip), substituting its actual
retained path. It checks the content checksum, exact admission/priors, source and
proof receipts, every raw row and normalization record, all eight saved metric
identities/gaps and both authority inventories before physical reconstruction.
It then freshly builds the weighted model and independently recomputes exact
own-hand responses without training. Exact metric/class-policy/strategy identities
must match; saved and fresh numeric replays are each bounded by 1e-10, with tiny
runtime differences allowed within that tolerance. Clean HEAD/status and source
identities plus report content must remain stable. This is fresh physical replay,
separate from authenticating an immutable publication index. No actual saved
new-prior training policy exists or has been replayed at this checkpoint.

## Frozen pilot and status

The [pilot protocol](../benchmarks/flop-class-reweight-cfrplus-pilot-v1.json)
requires one 560-sweep solve each for baseline, uniform and skew, in that order.
All three requests are admitted before any authentication/preparation/training;
the named total is 225,323,868 under a separate 230-million batch reservation,
plus six physical oracle builds / 35,640 enumerated rows as a census reference.
The baseline must reproduce the authenticated old pilot's raw policy,
normalization, census/path, exact audit, class policy and physical strategy hash.
Adapter/provenance tags differ and are not byte-parity targets. Each newly built
physical-world hash must match the authenticated no-training case's hash.

The harness reserves a new external directory, requires clean committed stable
source before/after every call, and retains full gzip reports and a hashed index.
A reversible wrapper counts actual shared-trainer invocations before delegation
and restores the original callable on every exit. Returned reports are saved
before downstream acceptance; failures retain the original traceback and stop
later calls without retry. Quality misses continue to the next frozen request.
Wall/CPU/runtime/UTC and execution-state receipts include instrumentation and
serialization; they are incidental, not performance comparisons.

No actual new-prior training pilot or saved physical policy replay has run at
this implementation checkpoint. Focused tests are synthetic admission/lifecycle
checks. Execution waits for the no-training proof's final CI/merge, reviewed
source/protocol and a frozen clean checkpoint. Saved authentication and a fresh
no-training physical replay remain distinct validation layers. No third-party
source, asset or dependency is incorporated; conceptual CFR+ provenance follows
the [existing adapter](flop-class-cfrplus.md) and
[commercial boundary](research/LICENSING.md).


The proof dependency is now merged as
[PR #206](https://github.com/ajpaulson18-design/openpoker-lab/pull/206), with both
full Python 3.11/3.12/3.13 matrices passing. Lead and Luna reviewed this new
adapter/harness/replay source. All 49 combined focused tests and documentation
checks passed before the clean source freeze; actual pilot results remain pending.
