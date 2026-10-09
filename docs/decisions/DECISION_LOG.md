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

Record ID, date, authority, source, rationale, considered alternatives where known,
status, affected interfaces and superseded IDs. A new ADR is useful for a major
tradeoff; minor entries belong here. Never invent rationale to fill a template.
Materially conflicting owner intent stays open in [knowledge gaps](../context/KNOWLEDGE_GAPS.md).
