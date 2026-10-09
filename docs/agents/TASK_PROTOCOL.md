# Agent contribution, delegation and handoff protocol

The authoritative knowledge is ordinary Markdown and source code. No particular
model or provider is necessary to use it. The owner prefers a lead Sol-tier agent
for architecture/judgment and bounded Luna workers for inventories, extraction,
drafting, links and validation. Where available, use GPT-6.1 Sol and GPT-6 Luna;
do not silently substitute GPT-5.6. If model selection or delegation is unavailable,
state that limitation. Model preferences are an optional execution adapter, not
a requirement for understanding the project.

## Scoped work

1. Read [onboarding](../START_HERE.md), root agent rules and relevant specs.
2. Pin the baseline commit, inspect worktree/active work, and identify ownership
   boundaries. Use an isolated branch. Avoid editing another workstream's files.
3. State objective, sources, files owned, exclusions and expected validation for
   each worker. Do not duplicate context-heavy research. Workers distinguish
   extraction from architectural judgment; the lead reviews before integration.
4. Preserve contracts/provenance, private-information boundaries and limitations.
   Audit tools before substantial specialized custom work.
5. Update canonical knowledge when changing architecture, capability status,
   approved decisions, limitations or dependencies. Minor edits need no history
   rewrite. Retain superseded records and link the replacing evidence.
6. Run meaningful checks, record commands actually run and results, and report
   unavailable evidence. Source inspection alone is not executed validation.

## Knowledge maintenance

[Current state](../engineering/CURRENT_STATE.md) maps shipped behavior;
[decision register](../decisions/DECISION_LOG.md) holds authority;
[source index](../context/SOURCE_INDEX.md) holds provenance;
[gaps](../context/KNOWLEDGE_GAPS.md) hold unknowns. Existing deep technical specs
remain canonical; link rather than maintain duplicate versions.
Run `python -m scripts.validate_docs` on documentation changes. CI checks local
Markdown file links and required entry points. The checker does not verify truth,
remote URLs or semantic consistency; reviewers must do that.

## Handoff / cold-start acceptance

A new agent should explain from repository evidence alone: purpose/differentiation,
implemented scope, solver and simulation workings, coaching intent and current
limits, unfinished priorities, decisions to preserve, licensing boundaries and
safe contribution steps. Each answer must cite its canonical repository source.
Missing facts remain gaps rather than invented answers.

A completion handoff records baseline and final commit/PR, files changed, exact
checks/results, documentation status, unresolved questions and next bounded task.
Never imply historical tests were rerun or that a plan has shipped. Read task-relevant
current files again before later edits; the audit snapshot is not permanently fresh.
