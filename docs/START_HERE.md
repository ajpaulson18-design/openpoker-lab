# OpenPoker Lab: start here

This is the repository's model-neutral institutional memory. Its primary purpose
is transferring important knowledge from the owner's ChatGPT **poker simulation**
project chats and memories into GitHub for other AI platforms. Read the partial
[recovered chat knowledge](context/RECOVERED_CHAT_KNOWLEDGE.md) and its coverage limits. Read this page and
root [agent instructions](../AGENTS.md) before implementation. Audit snapshot:
`65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce` (2026-10-09 UTC).

## Read in this order

1. [Owner vision and principles](product/VISION.md): purpose and decisions that constrain development.
2. [Current implementation](engineering/CURRENT_STATE.md): what exists and what does not.
3. [System map](architecture/SYSTEM_OVERVIEW.md), then the linked existing technical specifications.
4. [Decision register](decisions/DECISION_LOG.md) and [history](history/PROJECT_HISTORY.md).
5. [Roadmap](product/ROADMAP.md), [knowledge gaps](context/KNOWLEDGE_GAPS.md), and [contribution protocol](agents/TASK_PROTOCOL.md).
6. [Commercial and dependency boundaries](research/LICENSING.md) before external reuse.

## Evidence rules

| Label | Meaning |
| --- | --- |
| Confirmed owner decision | Explicit supplied owner instruction, or repository record reporting an owner decision; distinguish those two sources |
| Verified implementation | Source inspection establishes behavior at a pinned revision; execution validation is separately recorded |
| Documented historical plan | A dated design/handoff; does not prove implementation or continuing approval |
| Research or proposal | Candidate approach without owner approval or shipped behavior |
| Inference requiring validation | Interpretation that must not become an approved requirement |
| Unknown | Evidence unavailable or insufficient |

The supplied [mission](context/OWNER_MISSION_2026-10-08.md) is authoritative for
product intent, not proof of implementation. Historical architecture files remain
valuable, but their baseline assessments and future slices are dated snapshots.
Later explicit owner decisions control current intent; implementation is checked
against code. Record contradictions rather than quietly deleting their history.

## Core distinctions

OpenPoker Lab is a commercial-intent educational solver/simulation product,
currently delivered as an MIT-licensed local research application. The separate
entertainment poker video game is outside this repository's product scope.
The coach helps users understand a situation and why it is difficult; calculating
strategy, evaluating a decision and explaining it are separate responsibilities.
A conversational provider is optional, not the product's mathematical authority.

The finite heads-up postflop Python solver is broader than the browser's fixed-bet
river form. Practice EV is a simplified estimate, not a solve of the live hand.
Selected runouts define a conditional joint game. Exact chance enumeration is not
a guarantee that a finite-iteration strategy is equilibrium, and no current
component solves unrestricted NLHE. Never fill unavailable UI facts with guesses.

## Cold-start handoff

Before a scoped change, locate its producer, contract, consumer, tests and latest
relevant decision. Explain supported scope, assumptions, validation evidence and
unknowns from repository sources alone. Use the [handoff checklist](agents/TASK_PROTOCOL.md)
and leave unresolved history in the gap register. No provider account or personal
chat memory is needed to understand these documents.
