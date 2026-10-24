# Decision register

Stable IDs identify decisions, not implementation milestones. Sources and statuses
are explicit. Historical alternatives without evidence remain unknown.

| ID | Decision | Authority / status | Source |
| --- | --- | --- | --- |
| D001 | GitHub is transferable institutional memory across AI providers | Confirmed owner decision, current | [Mission](../context/OWNER_MISSION_2026-10-08.md), §§1, 7–10 |
| D002 | Teach situation, difficulty and reasoning beyond optimal moves | Confirmed owner decision, current | Mission §4; [vision](../product/VISION.md) |
| D003 | Separate solver, evidence, explanations and presentation; coach does not calculate strategy | Owner direction plus implemented contract boundaries | Mission §4; [human-aware architecture](../human-aware-strategy.md), [coach evidence](../coach-analysis-v1.md) |
| D004 | External conversational AI is optional; structured explanations are central | Confirmed owner decision, current; optional provider implemented separately | Mission §4; [setup](../ai-coach-setup.md), [current turns](../current-coach-conversation-v1.md) |
| D005 | Entertainment poker game is outside scope; no assumed integration | Confirmed owner decision, current | Mission §3 |
| D006 | Commercial value and legitimate reuse matter; license obligations remain | Confirmed owner decision, current | Mission §6; [licensing](../research/LICENSING.md) |
| D007 | Recursive exact CFR remains default/reference; optional DCFR/planned/public-batched are measured candidates | Recorded engineering decision, implemented at baseline | [solver progress](../solver-progress.md), [public-batched](../public-batched-cfr.md), PR #63 |
| D008 | Selected runouts condition the joint game; no unrestricted NLHE claims | Implemented mathematical boundary, current | [postflop validation](../postflop-validation.md), AGENTS.md |
| D009 | Preserve approved espresso front face; minor visual changes thereafter | Repository-recorded owner decision; original chat unavailable | [visual interface](../visual-interface.md), commit `8e36324`, PR #61 |
| D010 | Lead owns architectural/product judgment; bounded Luna workers extract/draft/validate | Confirmed owner decision, current | Mission §2; [task protocol](../agents/TASK_PROTOCOL.md) |
| D011 | Knowledge mission is additive and protects active development | Confirmed owner decision, current | Mission §11 |
| D012 | Use the “generative imagine prototyping phase” while preserving system integrity and approved visual targets | Owner direction recovered from supplied dated excerpt and saved-memory summary | [Recovered context](../context/RECOVERED_CHAT_KNOWLEDGE.md), C008; [vision](../product/VISION.md) |
| D013 | Personal preference for OpenPoker Lab over other apps/videos is the coaching quality benchmark | Saved owner-memory summary, also explicit current mission; aspirational acceptance direction | Recovered context C004; mission §4 |

## Superseded and unresolved context

Older root/Copilot agent instructions appointed Copilot specialists as the support
layer. The current supplied mission establishes Sol/Luna delegation for this work;
provided owner context also reports a later preference for Luna over Copilot.
Legacy `.github/agents/` and compiled workflows still exist. Their existence does
not prove current subscription availability or successful execution. Preserve them
as implementation/history and audit separately; this mission does not authorize
workflow deletion, budget changes or billing changes.

[Coach architecture](../ai-coach-architecture.md) is explicitly a dated architecture
record, with an early baseline and future slices. Subsequent slice specifications,
code and commits establish what shipped. Do not rewrite that historical baseline
as if it described today's complete solver or coach.

## Adding a decision

D014 (2026-10-16): engineering decision under the owner's authorized compiled
backend development scope: implement bounded native preflop count preparation as
a separate explicit source-built API. Preserve the default Python reference,
progress callbacks, immutable table, all admission limits and solver payloads.
This isolates compiler/protocol failures and permits complete-call comparison
without implicit tool installation. Third-party evaluator reuse and a default
backend switch were not selected. Implementation and evidence status are tracked
in [native preparation](../native-preflop-equity.md); no toolchain distribution
clearance or broader game coverage is implied. No earlier decision is superseded.

D015 (2026-10-16): engineering decision under the owner's ongoing preflop/flop
solver scope: extend the reusable full-board preflop table through a separate
finite preflop betting adapter with forced hidden future checkdown. Reuse the
existing betting builder and scalar CFR/CFR+ kernels, with an independent
configuration-derived pre-build admission envelope and numeric replay oracle.
This adds limps and finite raises without changing selected-outcome APIs or
later-street work. Full-deck postflop betting is deferred; the existing pair
caps remain. See [scope and evidence](../preflop-full-checkdown.md) for actual
validation/publication status. This decision adds a model, not a claim of
unrestricted NLHE or an exact finite-iteration equilibrium. No prior decision
is superseded.

D016 (2026-10-16): engineering decision under the owner's efficiency scope:
provide explicit per-private-pair signed-mean world indexing for full-board
preflop forced-checkdown. The hidden category is never available to a decision,
and terminal payoff is linear in sign; retain hidden opponent-hand distinctions
and full pair mass. Preserve the categorical default and independently validate
floating-point and finite-iteration effects. Admit the complete requested P-world
work with unchanged structural/source caps and retained category setup. See
[proof, boundaries and measured status](../preflop-pair-mean.md). No default switch,
third-party implementation or broader game model is authorized by this choice;
no prior decision is superseded.

D017 (2026-10-17): engineering decision under the owner's authorized compiled
backend scope: provide separate explicit source-built fixed-public-tree native
training for the prepared preflop and forced-checkdown flop models. The
[measured prepared-call profile](../fixed-street-profile.md) identifies training
as the dominant cost. Preserve Python rules/diagnostics/default payloads, all
historical admission and a separate complete native work/storage envelope.
A static C scalar traversal is the first experiment. Its fixed-flop DCFR policy
gate miss is retained in the initial report. The followup uses compiled
public-hand-vector reduction for flop, while preserving preflop scalar math,
original acceptance gates and the failed evidence. A Python default switch,
third-party solver implementation, public-chance support and compiled diagnostics
were not selected. See [scope and evidence](../native-fixed-street.md) for actual
validation/publication status. No earlier decision is superseded.

D018 (2026-10-18): engineering decision under the owner's continuing independent
solver-validation scope: establish an exact weighted preflop forced-checkdown
equilibrium anchor before expanding private-pair or future-betting coverage.
Reuse the project-owned bounded rational simplex without changing its limits;
independently reconstruct physical-count payoffs, legal histories, primal/dual
witnesses and own-information responses. A separate pure-response check guards
hidden-information mistakes. This adds a research certificate and validation
target, not production behavior or broader equilibrium coverage. See
[scope and publication status](../preflop-weighted-sequence.md). No earlier
decision is superseded.

D019 (2026-10-18): engineering decision under the owner's ongoing accuracy and
efficiency scope: compare prepared Python/native preflop strategies to the
separately certified weighted exact game value. Keep exact reference proof,
finite-strategy legal best responses, quality targets, cross-backend agreement,
complete-call timing and Python allocation traces distinct. A policy-distance
gate to one LP equilibrium would penalize legitimate alternate or unreachable
policies, so legal exploitability and exact value containment govern accuracy.
No production algorithm or default changes are selected. See
[protocol and measurement status](../preflop-exact-anchor-comparison.md).
No earlier decision is superseded.

D020 (2026-10-18): engineering decision under the owner's ongoing broader-range
solver scope: pool already covered full-board count sources through joint suit
bijections into a separately bounded prepared table and explicit solving entry.
This removes the enumeration cap from the prepared-data representation without
changing enumeration itself, and reuses the existing betting/training body.
All full-request solve limits remain; missing or conflicting source coverage
rejects. Raising global preparation limits or merging private information sets
was not selected. See [scope and evidence](../preflop-covered-counts.md).
No prior decision is superseded.

D021 (2026-10-18): engineering decision under the owner's independent validation
and compiled-computation scope: add an isolated project-owned exhaustive best-five
reference to establish new physical preflop source rows without reusing the
production direct-seven-card evaluator. Require complete five-card tuple parity,
known category totals, fixed full-board counters, the existing independently
enumerated anchor and independent production count agreement. The tool has only
fixed finite modes and no solver/backend/default integration. See
[method, work units and publication status](../preflop-five-card-reference.md).
No prior decision is superseded.

D022 (2026-10-18): engineering decision under the owner's independent validation
and broader-range scope: extend the project-owned best-five reference with a
strictly bounded explicit private-pair argv mode. Require current-build exhaustive
conformance before each source query, retain all original production query caps,
and physically verify missing QQ/KK suit classes for later mixed-range work.
Source/evaluator/solver defaults remain separate; generic unbounded enumeration
and imported evaluators were not selected. See
[method, caps and publication status](../preflop-generic-five-reference.md).
No prior decision is superseded.

Record ID, date, authority, source, rationale, considered alternatives where known,
status, affected interfaces and superseded IDs. A new ADR is useful for a major
tradeoff; minor entries belong here. Never invent rationale to fill a template.
Materially conflicting owner intent stays open in [knowledge gaps](../context/KNOWLEDGE_GAPS.md).

D023 (2026-10-21): under the owner's autonomous flop/preflop detour, add an
isolated fixed-game class CFR+ research adapter after the full no-training proof.
Retain the 140-sweep physical reference envelope, unchanged shared recurrence,
raw average rows, explicit exact-grid output normalization and unrestricted
physical own-hand responses. Require a frozen first pilot and separate evidence
for any later budget or performance claim. No prior decision is superseded. See
[scope and admission](../flop-class-cfrplus.md).

D024 (2026-10-21): under the ongoing autonomous flop/preflop detour, add a
separate opt-in compact-work fixed-flop research entry after the 140-sweep
physically verified quality miss. Charge named compact recurrence/setup/output
loops under pinned shared sources and a separately versioned 76-million cap,
with at most 560 requested sweeps and unchanged fixed physical preparation/BR
checks. Preserve the legacy adapter and its source-pinned result literally.
This is a new explicit resource policy, not a silent relaxation of defaults or
a convergence/performance claim. See [scope](../flop-class-compact-cfrplus.md).
No prior decision is superseded.

D025 (2026-10-21): after the independently replayed fixed-flop 560-sweep
quality pass, prioritize complete-call runtime and allocation evidence before
choosing another performance architecture. Freeze three paired timed rounds
and one separate allocation call per entry, retaining every payload, miss,
failure and source identity. Both entries already use the same representation;
comparison across 140/560 sweeps describes different quality/work budgets, not
a same-work speedup. See [measurement scope](../flop-class-call-cost.md).
No prior decision is superseded.

The D025 eight-call study completed on 2026-10-22 with all policies and source
identities retained, zero recorded errors and saved verification passing. Its
[observations](../flop-class-call-cost.md) qualify runtime variation and Python
allocation scope; phase profiling is the next diagnostic, not a speed claim.

D026 (2026-10-22): after the completed fixed-flop eight-call study, add one
separate instrumented 560-sweep compact call to locate time allocation before
selecting another performance architecture. Require full-request admission,
clean source snapshots, pilot-semantic equality, lossless report retention, and
reversible nested wrappers around existing boundaries. Inclusive phase times
overlap and include instrumentation overhead; they do not replace primary
medians or establish a speed, memory, or bottleneck claim. No solver/proof/
recurrence source or default changes are selected. See [profile scope and status](../flop-class-phase-profile.md). No earlier decision is superseded.

The D026 single-call profile completed on 2026-10-22 with 21 retained events
and the unchanged passing pilot policy. The observed largest root interval is
publication verification; no prepared-reuse or production architecture has
been implemented by this measurement.


D027 (2026-10-22): after the merged runtime/phase studies, prioritize a new
family of fixed-support range-prior games rather than optimizing certification
cost alone. First require a separate no-training proof for baseline, uniform
and skewed positive rational weights, including global blocker conditioning,
fresh weighted physical reconstruction and exact legal response equivalence.
Keep old-prior anchors/sources unchanged, all request/resource guards explicit,
and all failed/partial work retained. Training under new priors remains a later
milestone. See [scope and evidence](../flop-class-reweight.md). No previous
decision is superseded.


The D027 single frozen proof batch completed on 2026-10-22 with all three
positive-prior cases, twelve exact-response controls, fifteen retained artifacts,
zero errors/training and stable committed sources. Saved authentication is
separate from fresh physical replay. New-prior training remains the next bounded
milestone; these controls make no convergence claim.


D028 (2026-10-22): after the completed D027 no-training proof, implement a
separate three-prior CFR+ research adapter with the unchanged shared recurrence,
positive joint masses, its own explicit setup charge and fresh unrestricted
physical responses. Freeze one 560-sweep call per prior; require exact historical
baseline calibration and retain every quality miss/failure without tuning or
retry. Actual training waits for the proof merge and clean reviewed source.
See [scope and pending evidence](../flop-class-reweight-cfrplus.md). No prior
decision is superseded.


The D028 single pilot and all three fresh saved-policy replays completed on
2026-10-22 at frozen e1. Baseline calibration passed; normalized-policy exact
NashConv was 0.002892400528, 0.000012958529 and 0.000993121225 for baseline,
uniform and skew, each below 0.005. All raw policies, normalization records and
exact response metrics are retained, with no lost positive probabilities, errors
or retries. Training count was three; subsequent physical replay count was three
with zero training. These finite-game results do not select a performance or
broader-card-support claim.


D029 (2026-10-22): after the three-prior quality pilot and independent physical
replays, locate baseline call time and Python allocation scope before choosing
another efficiency architecture. Freeze one phase call and one separate traced
call at 560 sweeps, requiring full published report byte equality, complete
admission, reversible instrumentation and no retries. Inclusive events and one
Python peak are diagnostics, not comparative speed/RSS or general bottleneck
claims. See [scope and pending status](../flop-class-reweight-baseline-diagnostic.md).
No earlier decision is superseded.

D029 observation: the one admitted batch completed without errors/retries and
both full reports match the previously replayed baseline exactly. Thirteen phase
events include four repeated full model validations. The separate trace records
401,901,644 new Python allocation bytes and a large retained wall/CPU gap; no
comparative or general performance claim follows. Investigate call-owned model
integrity before considering validation reuse; a mutable flag/cache alone is
insufficient. The existing checks remain required. See the completed evidence
and its qualifications in the linked diagnostic document.

D030 (2026-10-22): before a validation-reuse performance experiment, test complete
call-owned model integrity coverage separately, retaining unchanged independent
validation before and after six bounded graph fingerprints. Require exact stable
and restored digests/censuses, action and rooted-index alias mutation detection,
39 clean source hashes, zero guarded authorities and first-error retention.
A digest is not model validity, immutability or permission to bypass validators.
No real fit, performance or memory claim exists yet. See
[the no-training investigation](../flop-owned-fingerprint.md).

D030 observation: the one admitted fresh baseline model fits the declared graph
caps. All six fingerprints complete, both mutations change the digest, and both
restorations/repeat return exactly to the original digest and census. Stable
tracked objects/edges are 318,280/1,608,777; 39 sources are clean/stable and all
41 authority counters remain zero, with two unchanged full validations and no
training/errors/retries. This does not authorize reuse or select a performance
architecture. Broader flop-board support remains a separate independently proved
slice with freshly measured partitions and tree dimensions.

D031 (2026-10-22): broaden flop correctness evidence to the fixed `7c8d9h`
board before choosing a validation-reuse performance architecture. First freeze
one admitted no-training physical-reference build and candidate partition, with
fresh complete world/tree views and hashes. Keep exact global blocker priors,
bounded and counted reference ranking, full source/error receipts and unchanged
candidate-only flags. New class dimensions are measured, not inherited from
`2c3d4h`. This preparation does not establish full class/tree or best-response
equivalence; that separate proof must precede training. See
[the reference protocol and pending status](../flop-second-board-reference.md).
No earlier decision is superseded.

D031 observation: the one frozen reference batch completed without errors or
retries, with one physical build/candidate partition, 4,134 preparation and
4,134 same-ranker recheck calls, all 5,940 world signs compared, clean stable
44-source identities and all 41 guarded authorities at zero. Fresh candidates
have 13 turn classes, 17 river signatures and 170 class worlds. Complete
physical world/tree views and hashes are retained. These measured dimensions
establish a new reference; they do not prove public-chance equivalence or
authorize training. Across-class variation is a valid future control; physical
card-specific variation within a class must reject projection.

D032 (2026-10-23 UTC): independently prove the fixed second-board quotient
before training. Freeze one complete no-training batch with fresh physical
anchors, full joint support/masses/signs and both numeric reveal subtrees.
Require exact compact/unrestricted own-hand responses and separate numeric
replay for four positive class-constant controls, preserving all rows/actions.
Across-class variation is valid; within-class card variation and near-normalized
floats must reject. Admit every proof/response/output family before any ranking,
retain source/error/policy receipts and change no shared or published source.
See [the full protocol and pending execution status](../flop-second-board-equivalence.md).
No earlier decision is superseded.

D032 observation: the one frozen batch passed all joint-mass and complete
two-reveal numeric subtree checks, all four positive exact/numeric response
controls and both intended projection rejections. It derives 170 compact worlds,
1,270 numeric states and 608 own-hand rows, retaining all six complete policies.
Ten model proofs, eight exact metric calls, four numeric replays, six projections,
one fresh physical build and 4,134 rank calls completed without errors/retries.
Clean 49-source identities and all 41 zero authority counters are preserved.
The controls are not trained strategies and establish no quality target,
convergence, speed, memory or unrestricted NLHE result. Publication authentication
and CI must finish before a separate new-board trainer is admitted.

D033 (2026-10-23 UTC): stage a separate fixed second-board CFR+ pilot after
D032 publication validation. Keep a distinct versioned 110M named logical-work
envelope and the unchanged shared recurrence; the old 76M cap is preserved.
Freeze fresh T140/T560 calls and exact physical NashConv<=0.005 checks, retaining
all target misses. Validate the complete model before/after, all positive joint
masses, own-hand information rows, both response domains and separate numeric
replay. Keep raw averages, normalized full policies, errors and source identities.
No training or quality result is claimed by this staging decision. See
[the pilot and its limits](../flop-second-board-cfrplus.md). No earlier decision
is superseded.

D033 observation: the one frozen v1 batch stopped after T140 on an adapter
schema check that wrongly excluded replay audit metadata. T560 never ran;
the original quality gate is null. Retain the complete failed report, raw and
normalized policies, identical compact/physical exact metrics, original error,
all zero guard counters and clean source identities. Final model validation
passed, but the numeric replay return was not saved and the case is not a
completed verified policy. Preserve frozen v1 sources and require a distinct
reviewed correction/protocol before further measurement. See the
[retained failure](../flop-second-board-cfrplus.md).

D034 (2026-10-23 UTC): stage a distinct
[replay-boundary v2](../flop-second-board-cfrplus-replay-v2.md) rather than alter
the frozen D033 failure. Authenticate the stopped-v1 saved evidence, wrap one
unchanged independent replay call, retain/validate its full thirteen-field
return, and expose the eight numeric metrics to the preserved adapter. Require
restoration on every exit, exact-once counting, stable 58/54 source identities
and the unchanged exact/numeric/model guards. Keep the same fresh T140/T560
quality protocol and separate named resource envelopes; no v2 actual training
or quality result is claimed by this staging decision. No earlier decision is
superseded.

D034 observation: the single frozen replay-v2 batch completed T140/T560
without execution errors, retries or fallbacks. Exact compact and unrestricted
physical metric maps agree, numeric gaps remain below 7e-16, both full replay
receipts are retained and source/model/authority checks passed. Keep T140's
0.014166984012911272 NashConv miss and T560's 0.0016464625267553663 pass as
separate finite-game observations. Two models/training calls, six proof passes,
four exact calls, two replays/projections and 8,268 ranks are recorded. The v1
failure stays unchanged; saved-data authentication/CI still gate publication.
See [the complete outcomes and limits](../flop-second-board-cfrplus-replay-v2.md).

D035 (2026-10-24): **confirmed owner instruction in the integration chat**:
temporarily pause independent preflop/flop and turn/river development and make one
coherent game model spanning all four streets the primary solver objective. Audit
existing engines/state/ranges/actions/transitions/validation first; maximize reuse
of verified implementations; preserve accuracy benchmarks; demonstrate a complete
small four-street game before gradual realistic heads-up NLHE expansion. Connecting
independent street policies does not establish a complete-game equilibrium. Sol
leads audit, architecture, milestones and task scoping; Luna handles routine
implementation/tests, Terra difficult implementation/debugging, and Sol architectural
decisions. Pause for review before major refactors. Unrelated features and isolated
benchmark optimization are out of this phase unless necessary for integration.

The [pinned integration audit and proposed design](../unified-solver-integration.md)
records an existing selected-outcome combined-root four-street path and separates
that verified implementation from new contracts, evidence gates and future work.
The owner has approved the priority and workflow, **not yet the proposed technical
architecture or implementation launch**. This instruction takes precedence over
earlier isolated-street development priorities while retaining their mathematical
constraints and immutable evidence.

D036 (2026-10-24): **confirmed subsequent owner instruction in the same chat**:
the owner revoked the pause for their review, requested continuous work as an
active goal, and delegated review responsibility to the agent until instructed
otherwise. This supersedes D035's owner-review/implementation-launch gate and
the initial audit's waiting status. The integration objective, Sol architectural
lead, Luna bounded implementation/tests, Terra difficult implementation/debugging,
independent mathematical validation and preservation of existing evidence remain.
The agent performs architecture/implementation reviews, advances scoped milestones,
resolves ordinary defects, and publishes completed changes through GitHub without
waiting for the owner. A failed quality gate remains a miss; a capacity rejection
remains unknown. These are inputs to autonomous review and a separately justified
next step, not reasons to silently change the old experiment or stop for approval.

D037 (2026-10-24): Sol architectural review under D036 approves the additive
[four-street request/result boundary](../four-street-solver.md): reuse the current
all-streets `solve_preflop` engine through one exact delegation, frozen input
contracts and a complete immutable JSON result snapshot. Keep existing graph,
numerical, admission, strategy-row and history semantics. Ordinary calls explicitly
report unknown source revision; authenticated source and exact-normalized quality
certificates belong to the later frozen integration runner. Exclude advanced
sampling/grouping/compaction/delay/stopping options from this initial facade.
Existing analysis/Coach contracts and simulator state remain separate. The lead
reviewed the implementation and executed the combined 50-test boundary/legacy
suite; the new contract-only suite also passes with optimized Python. This is an
interface milestone, not the final whole-game quality gate or full-deck coverage.
