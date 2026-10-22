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
