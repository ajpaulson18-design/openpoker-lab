# Recovered project-chat knowledge

## Purpose and coverage

The owner clarified on October 8, 2026 in the current session that the primary
purpose is to make necessary knowledge from the ChatGPT project called **poker
simulation**, including its chats and memories, accessible in GitHub for other AI
platforms. This is a knowledge transfer mission, not merely a code documentation
exercise. The existing GitHub target is `ajpaulson18-design/openpoker-lab`.

Source `CTX-2026-10-08`: conversation excerpts and memory summaries explicitly
provided to the coordinating agent in this session. These are partial secondary
records, not retrieved full conversations or a complete project export. Dates
below are the supplied conversation labels. Quoted user fragments were visible
in those excerpts; summarized memory is identified separately. Only relevant
project context is preserved; unrelated personal information is excluded.

Source `CLARIFICATION-2026-10-08`: direct owner message in this session identifying
the chat/memory transfer objective. The source text says the goal is for necessary
memories to be accessible on GitHub for other artificial intelligence platforms.

## Extracted intent, decisions and rationale

| ID | Date / source label | Recovered knowledge | Evidence and status |
| --- | --- | --- | --- |
| C001 | Oct 1, Building An Xbox Game | OpenPoker Lab and the entertainment poker video game are separate products; no assumed integration | Visible owner excerpt: “These are two seperate things that I am creating to be clear”; repeated in current mission. Confirmed owner decision |
| C002 | Oct 2, Poker App Revenue Estimates | Commercial success within the poker products' niches is a primary goal; development should have commercial meaning | Visible owner excerpts: “commercial success in my niche is my goal” and “It all should have commercial meaning”; current mission §6 confirms for OpenPoker Lab. No revenue or pricing evidence supplied |
| C003 | Oct 8, Poker Coach Product Philosophy | Help users understand their situation, why it is difficult and how to think through it, beyond optimal moves | Visible owner asks to make this a “golden” part of the app; current mission §4 preserves the exact principle. Confirmed owner decision |
| C004 | Oct 8, Poker Coach Product Philosophy | Personal default use is the quality benchmark: preferring another app or YouTube to understand poker signals a product gap | Supplied memory summary; corroborated by mission §4. Owner-established quality direction, not measured user research |
| C005 | Oct 8, AI Coach Explanation System | Coach is not intended as a newly developed LLM or inherently a chatbot; comprehensive contextual explanations should follow solver/game-state facts through rules, logic and reusable templates | Supplied memory summary; corroborated by current mission §4. Existing optional conversations do not replace this defining principle |
| C006 | Oct 8, AI Coach Explanation System | Solver improvement and AI Coach development should proceed without getting in each other's way | Visible owner excerpt: “none of this conflicts with the current project I have going of creating the ai coach as they shouldn't get in each others way”; current mission §4 confirms. Preserve independent implementation boundaries |
| C007 | Oct 8, AI Coach Explanation System | Study other solvers and consider downloads/reuse when useful, while ensuring legitimate commercial integration | Visible owner supports studying other solvers and asks whether building from scratch is right. Owner says ideally no citations; current mission §6 explicitly retains required attribution/license compliance. Preference does not waive obligations |
| C008 | Oct 8, Generative Imagine Prototyping | Use a “generative imagine prototyping phase”: generate and refine visual targets, then work toward implementing the approved vision without sacrificing system integrity | Visible owner phrase and “without losing the integrity of the system for visuals”; supplied cross-project memory. Applicable design philosophy, not an instruction to import entertainment-game characters/assets. Repository visual approval is separately recorded in docs/visual-interface.md |
| C009 | Oct 7, Codex Workflow Update | Luna within Codex replaced the attempted Copilot support layer; added platforms should justify coordination/interface friction | Supplied memory summary and visible reflection on learning from Copilot. Historical workflow preference; existing Copilot repository artifacts remain implementation records, not proof of current availability |
| C010 | Oct 6, Codex Agent Costs | Prefer GPT-6.1 Sol for Sol-tier work and GPT-6 Luna for routine work; treat GPT-5.6 selections as likely accidental unless explicitly overridden | Supplied memory summary. Optional model-selection adapter, not a requirement for other AI providers to understand the repository |
| C011 | Oct 1, GitHub authorization workflow | Ordinary repository work, implementation choices, research and routine repository cleanup are delegated without repeated permission requests; preserve genuine blockers/platform controls | Supplied memory summary. Scope is repository development; it does not authorize unrelated account or document modifications |
| C012 | Oct 8, current session clarification | Transfer important “poker simulation” project chats/memories into GitHub for other AI platforms | Direct current owner message. Primary mission outcome; current repository audit alone cannot satisfy full historical recovery |

## Saved-memory transfer: preserved meaning

The owner explicitly reaffirmed in this session that saved memories can transfer
the essence of the project even without the original chats. Treat the available
project-specific summaries as usable intent evidence; transcripts are not a
prerequisite for preserving that meaning. These summaries do not prove execution,
and the available set is not a verified inventory of every saved project memory.

The following mapping ensures that memories are usable constraints in canonical
project guidance, rather than isolated archival notes.

| Available memory | Meaning future AI agents should preserve | Canonical destination |
| --- | --- | --- |
| C001: separate poker products | Do not turn the solver into an entertainment-game feature or assume integration | [Vision](../product/VISION.md), D005 in [decisions](../decisions/DECISION_LOG.md) |
| C002: commercial meaning | Prioritize customer value, differentiation, retention and sustainable revenue; technical interest alone is insufficient | Vision, D006, [roadmap/commercial direction](../product/ROADMAP.md) |
| C003: golden coaching principle | Explain the situation, why the choice is difficult and how to reason; an optimal action alone is insufficient | Vision, D002 |
| C004: personal default-use benchmark | If the owner prefers another app or YouTube to understand a spot, investigate the remaining product gap | Vision, D013 |
| C005: contextual explanation engine | Ground comprehensive scenario-specific explanations in game state and solver facts, using structured rules/logic/templates; no requirement to build a new LLM | Vision, D004, [system overview](../architecture/SYSTEM_OVERVIEW.md) |
| C006: parallel workstreams | Improve solver and coach without interfering with each other; preserve explicit evidence interfaces | Vision, D003, [task protocol](../agents/TASK_PROTOCOL.md) |
| C007: research and legitimate reuse | Study established solvers and audit reusable solutions; preserve commercial compatibility and mandatory notices | Vision, D006, [licensing/reuse](../research/LICENSING.md) |
| C008: visual prototype philosophy | Preserve the exact phrase “generative imagine prototyping phase”; approve visual targets and implement toward them without compromising system integrity | Vision, D012, [approved visual baseline](../visual-interface.md) |
| C009: workflow experiment and lesson | Copilot was tried and replaced with Luna; integration/coordination cost matters when adding platforms | D010 and supersession notes, task protocol |
| C010: model preferences | Prefer GPT-6.1 Sol and GPT-6 Luna where available; flag likely accidental GPT-5.6 choices | Task protocol optional provider adapter |
| C011: delegated repository work | Continue ordinary authorized development/research/cleanup without repeated permission requests; stop at real blockers | Task protocol |
| C012 and current reaffirmation | GitHub must carry important project intent and reasoning for other AI platforms; use available saved memories now | [Onboarding](../START_HERE.md), this source record |

Full original conversations would add provenance, nuance and missing decisions.
They are additional evidence, not a reason to withhold the relevant saved memories
already available. Future updates should integrate newly available memories using
this same authority/status distinction, without requiring a raw transcript first.

## Conflicts and interpretation

The commercial goal does not turn future solver ambitions into shipped capability.
The educational explanation direction does not prohibit the already shipped
optional conversation adapter. Preserve both intent and implementation separately.
The visual prototype philosophy does not approve a new redesign of the accepted
espresso front face. Later explicit license-compliance language in the supplied
mission controls reuse despite the earlier preference for avoiding citations.

Earlier Copilot workflow experiments and current legacy configuration should be
kept traceable. Later Luna preference is recorded here; retirement, authentication,
spending and migration of existing automation are separate tasks.

## Missing coverage

Full project conversation retrieval was attempted through available personal
context search in this run; conversation search returned an error, and only the
mission artifact surfaced. No full “poker simulation” project listing, transcripts,
original message identifiers or chat export was retrieved. The relevant project memories supplied in this session are transferred and mapped
above. This does not certify that every saved memory or historical decision has
been retrieved; no complete memory inventory was exposed. Missing full-chat
coverage is distinct from the completed transfer of the available memory summaries.

## Importing additional project chats

For each supplied export or accessible source: record stable identifier/title/date,
extract decisions/rationale/alternatives/constraints, distinguish owner instruction
from assistant suggestion, identify supersession, map facts to canonical product,
architecture or decision docs, and update the coverage/gap register. Sanitize
secrets and unrelated personal data. Preserve source excerpts only where relevant.
Do not bulk-publish private raw chats without reviewing their contents.
