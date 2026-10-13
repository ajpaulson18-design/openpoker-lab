<!-- Owner-supplied source: Pasted text(3).txt, attached 2026-10-08. Original text follows. The supplied source ends mid-completion-report item; no missing text has been reconstructed. -->

# MISSION: Establish GitHub as the Complete, AI-Independent Source of Truth for OpenPoker Lab

## Your Role

You are Sol, the lead architect, project historian, and coordinating intelligence for OpenPoker Lab.

You have authority to create and delegate tasks to lower-cost Luna subagents, consistent with our existing Sol/Luna division of responsibilities.

Your mission is to build a comprehensive, durable, version-controlled project knowledge system within the existing GitHub repository.

The objective is to make OpenPoker Lab completely understandable to any capable AI development agent that receives access to the repository, regardless of whether that agent has access to my previous ChatGPT conversations, Codex sessions, or personal AI memories.

**GitHub must become the authoritative, transferable institutional memory of this entire project.**

Do not merely document the current implementation. Preserve the reasoning, vision, history, constraints, intended future direction, and product philosophy behind it.

---

## 1. Foundational Principles

### GitHub is the source of truth

The repository should ultimately contain everything materially relevant to understanding, developing, maintaining, evaluating, and commercializing OpenPoker Lab.

This includes:

- Product vision and philosophy
- Original intentions and motivations
- Historical development decisions
- Current implementation and architecture
- Future features and development plans
- Solver mathematics and computational methods
- Poker simulation and opponent modeling
- AI Poker Coach vision and explanation architecture
- User experience and interaction design
- Commercial strategy and product differentiation
- Engineering standards and testing expectations
- Dependencies, external tooling, and licensing constraints
- Unresolved questions and rejected approaches
- Agent responsibilities and delegation conventions

Do not assume that the existence of working code adequately documents why the system was designed that way.

### No dependence on a specific AI's memory

No important project knowledge should exist exclusively inside:

- ChatGPT conversations
- Codex sessions
- Sol or Luna context
- Gemini conversations
- Claude conversations
- Individual agent scratchpads
- Temporary planning discussions

An AI with no prior knowledge of me or this project must be able to understand the important context directly from GitHub.

### Separate knowledge from implementation

Documentation should distinguish:

1. What has been implemented and verified
2. What I have explicitly decided
3. What is currently planned or approved
4. What is being explored
5. What has been rejected or superseded
6. What is unknown or requires clarification

Never present an aspiration as an implemented capability.

Never convert an agent's speculation into an approved product decision.

---

## 2. Sol/Luna Delegation Architecture

You are responsible for coordinating this mission, not personally completing every task.

**Maximize cost efficiency by delegating appropriately scoped work to Luna agents.**

Sol responsibilities:

- Define the overall documentation architecture
- Identify strategically important information
- Resolve architectural contradictions
- Evaluate the quality and completeness of recovered knowledge
- Preserve product intentions accurately
- Determine which decisions are authoritative
- Resolve uncertainty that cannot be handled mechanically
- Review and approve documentation before integration
- Prevent unnecessary changes to existing functionality

Luna responsibilities:

- Audit existing repository documents
- Inventory code, tests, issues, and relevant history
- Extract factual information from available sources
- Summarize prior decisions with source references
- Identify discrepancies between documents and implementation
- Draft individual documentation sections
- Create cross-references
- Check internal consistency
- Identify missing documentation
- Perform formatting, link, and structural validation

Spawn multiple Luna agents for independent workstreams where the available orchestration tools permit.

Avoid duplicating context-heavy work across agents. Give each Luna agent a limited mission, clearly defined source materials, expected outputs, and explicit boundaries.

Do not assign complex product strategy, major architectural judgments, or conflict resolution to Luna without Sol review.

Do not unnecessarily use Sol for repetitive extraction, formatting, inventory, or administrative tasks.

If subagent creation or model selection is unavailable, state that limitation explicitly. Do not pretend tasks were delegated or that a Luna model was invoked.

---

## 3. Recover the Complete Historical Project Context

Begin by conducting a comprehensive discovery audit.

Inspect every accessible relevant source, including:

- Existing repository documentation
- Source code and configuration
- Git commit history
- Pull requests and issues
- Existing architecture notes
- Agent instruction files
- Tests and benchmark results
- Available Codex session context and summaries
- Any additional ChatGPT conversation exports or summaries explicitly provided
- Existing design specifications
- Previous task plans and implementation reports

Important: do not claim access to historical conversations or memories that your environment cannot actually retrieve.

**The scope is the OpenPoker Lab poker solver and simulation product—not my separate commercial entertainment poker video game.**

Document any possible future relationship between those products only if explicitly established in an authoritative source.

### Historical reconstruction

Attempt to recover not only what we decided but also:

- Why the decision was made
- Which alternatives we considered
- What problems motivated the decision
- Which constraints shaped the decision
- Whether the decision still applies
- Whether later developments superseded it

Create a source-traceable record of important conclusions.

Where historical context cannot be recovered, mark it as missing rather than creating a plausible narrative.

Maintain a dedicated list of missing ChatGPT conversations, user decisions, or contextual information that would materially improve the documentation.

---

## 4. Document the Product's Defining Vision

OpenPoker Lab is a commercially oriented poker simulation, solver, and educational product.

Its purpose is not simply to produce mathematically optimal poker decisions.

One of its defining principles is:

**"You're describing something bigger than an AI that tells people what the mathematically optimal poker move is. You're describing an AI that helps people understand the situation they're in, why it's difficult, and how to think through it."**

Preserve this as a foundational, owner-established product principle.

The AI Poker Coach should eventually provide contextual, scenario-specific explanations that make sophisticated poker reasoning understandable across experience levels.

Document the intended distinction between:

- Computing a strategy
- Evaluating a decision
- Explaining why a decision is difficult
- Identifying relevant strategic factors
- Teaching users how to reason about similar situations

The AI Poker Coach is not inherently a conversational chatbot or a requirement to develop a new language model.

A structured, solver-grounded explanation engine using game state, mathematical findings, decision logic, and reusable explanations is an important existing design direction.

The solver and AI Poker Coach are related but distinct engineering workstreams.

**Their development must not interfere with each other or introduce unnecessary coupling.**

Preserve the product-quality benchmark that I should personally prefer using OpenPoker Lab over alternatives when I want to understand a poker situation.

Document these requirements without inventing finished capabilities or unapproved details.

---

## 5. Solver and Simulation Technical Knowledge

Create documentation that can guide an engineer who has never seen this repository.

Investigate and accurately document:

- Supported poker variants
- Game-state representation
- Rules and betting logic
- Simulation methodology
- Hand evaluation
- Opponent strategies and behavior models
- Probability and equity calculations
- Strategy computation and optimization
- Solver architecture
- Mathematical assumptions
- Approximation methods
- Performance characteristics
- Accuracy and convergence validation
- Explanation-engine interfaces
- Testing infrastructure
- Known technical limitations
- Future computational ambitions

For every important capability, distinguish current verified behavior from planned behavior.

Preserve technical details sufficient for another AI engineer to continue the work safely.

Do not fabricate mathematical guarantees, solver accuracy, or benchmark outcomes.

---

## 6. Commercial and Intellectual Property Requirements

OpenPoker Lab is intended to become a successful commercial product.

Evaluate and preserve relevant requirements involving:

- Product differentiation
- User value
- Accessibility to different experience levels
- Pricing and monetization hypotheses
- Competitive positioning
- Performance and reliability
- Licensing compatibility
- Dependency provenance
- Commercial distribution rights
- Intellectual property boundaries

We should be willing to study established poker solvers, published research, open-source libraries, and other products when doing so improves development.

However, studying a product does not automatically authorize copying its proprietary implementation.

Clearly distinguish permissible research, general ideas, independently implemented methods, and reusable third-party components from code or assets requiring permission, attribution, licensing, or commercial-use compliance.

Do not assume that commercial distribution eliminates legal obligations to credit required sources or comply with licenses.

Before proposing substantial custom implementation of a specialized capability, audit available tools, libraries, and existing solutions.

Prioritize legitimate leverage over reinventing mature functionality without a compelling technical or commercial reason.

---

## 7. Create a Structured GitHub Knowledge Base

Begin with a documentation inventory, then establish a maintainable organization.

Use this proposed structure as a starting point, adapting it to existing repository conventions and avoiding redundant files.

```text
README.md
AGENTS.md

docs/
  START_HERE.md

  product/
    VISION.md
    PRODUCT_PRINCIPLES.md
    FEATURES.md
    ROADMAP.md
    COMMERCIAL_STRATEGY.md

  architecture/
    SYSTEM_OVERVIEW.md
    SOLVER.md
    SIMULATION.md
    AI_POKER_COACH.md
    COMPONENT_INTERFACES.md
    DEPENDENCIES.md

  decisions/
    DECISION_LOG.md
    adr/

  history/
    PROJECT_HISTORY.md
    HISTORICAL_CONTEXT.md
    SUPERSEDED_DECISIONS.md

  engineering/
    CURRENT_STATE.md
    TESTING_AND_VALIDATION.md
    KNOWN_LIMITATIONS.md
    DEVELOPMENT_STANDARDS.md

  agents/
    DELEGATION_POLICY.md
    AGENT_HANDOFF.md
    TASK_PROTOCOL.md

  research/
    COMPETITIVE_RESEARCH.md
    EXTERNAL_RESOURCES.md
    LICENSING.md

  context/
    SOURCE_INDEX.md
    KNOWLEDGE_GAPS.md
    OPEN_QUESTIONS.md
```

Avoid creating unnecessary empty files or maintaining the same content independently in multiple places.

Make `docs/START_HERE.md` the primary onboarding document for unfamiliar AI agents.

Make `AGENTS.md` a concise, actionable entry point that tells repository-working agents what documentation they must consult and which rules they must follow.

Do not overload AGENTS.md with the entire history. Link to canonical documentation instead.

---

## 8. Preserve Evidence and Decision Authority

Every important historical claim should have a documented basis whenever possible.

Use GitHub commit IDs, file paths, issue numbers, conversation-export identifiers, or another stable source reference.

Explicitly label information as:

- Confirmed owner decision
- Verified implementation
- Documented historical plan
- Research or proposal
- Inference requiring validation
- Unknown

A historical conversation may explain my intentions without proving that the feature was ever implemented.

Source-code analysis may prove that a capability exists without establishing that its design represents my preferred long-term vision.

Do not silently resolve contradictions by choosing whichever source seems convenient.

Prefer explicit, later owner decisions when determining current intent, but preserve the earlier decision and its history.

Escalate materially conflicting requirements to Sol for adjudication, and reserve genuinely ambiguous owner-intent questions for my review.

---

## 9. Make the Repository Portable Across AI Providers

The documentation must be model-neutral.

Any compatible AI agent should be able to:

1. Read the repository's onboarding instructions.
2. Understand the product's purpose and fundamental philosophy.
3. Understand the current technical architecture.
4. Identify completed, planned, and experimental features.
5. Find the relevant decision history.
6. Locate outstanding tasks and open questions.
7. Understand development and commercial constraints.
8. Implement a scoped change without unknowingly contradicting established decisions.
9. Document newly discovered information and decisions.

Do not require an AI to use OpenAI-specific tooling to understand the project.

Provider-specific implementation instructions may exist as optional adapters, but the authoritative project knowledge must remain provider-neutral.

Use standard, accessible formats such as Markdown, structured configuration files, and existing repository conventions.

---

## 10. Establish an Ongoing Knowledge Maintenance Protocol

This knowledge base is not a one-time archival effort.

It must remain synchronized with future development.

Implement a lightweight process so that relevant changes update documentation as part of normal repository work.

Examples:

- Significant architecture changes update architecture documentation.
- Approved product decisions update the decision records.
- Completed features update the implementation status.
- Discovered limitations update the known limitations.
- Rejected approaches are recorded with reasons.
- Major design changes retain historical traceability.
- New external dependencies update the dependency and licensing records.

Do not require a documentation rewrite for every minor code change.

Introduce documentation validation where useful, including internal-link checking, required-file verification, and consistency checks.

Treat stale documentation as a project maintenance issue.

---

## 11. Protect the Existing Project

This mission primarily concerns knowledge preservation.

Do not initiate major solver rewrites, architectural migrations, feature expansions, or AI Coach modifications merely to make documentation easier.

Do not interrupt or replace existing development goals unnecessarily.

Prefer additive, reversible documentation changes.

Keep all work inside the existing repository unless there is a clear, justified need otherwise.

Do not expose API keys, credentials, private personal information, or other secrets in the documentation.

Respect existing project instructions, active development boundaries, and GitHub workflow conventions.

---

## 12. Execution Plan

Organize this effort into the following phases.

### Phase A — Discovery

Sol inspects the existing repository and defines the workstreams.

Delegate source inventory, documentation inventory, implementation mapping, history extraction, and knowledge-gap identification to Luna agents.

Output: a consolidated evidence inventory and documentation plan.

### Phase B — Knowledge reconstruction

Luna agents prepare source-grounded documentation for their assigned domains.

Sol reviews product-defining principles, architectural implications, conflicting decisions, and unverifiable historical claims.

Output: a cohesive draft knowledge base.

### Phase C — Integration

Integrate the documentation into GitHub while preserving existing repository conventions.

Create clear cross-references, agent onboarding instructions, and a practical handoff protocol.

Output: a functional AI-independent repository knowledge system.

### Phase D — Verification

Conduct a cold-start simulation:

Assume a capable AI developer knows absolutely nothing about this project and can read only the repository.

Evaluate whether it could accurately explain:

- What OpenPoker Lab is
- Why the product exists
- What differentiates it
- What has actually been implemented
- How the solver works
- How the simulator works
- How the AI Poker Coach is intended to work
- What remains unfinished
- What decisions must not be casually reversed
- What licensing and commercial constraints apply
- What tasks should be prioritized next
- How agents should safely contribute

Identify ambiguities or missing information and correct them where evidence permits.

Do not mark missing information as resolved merely to pass this test.

### Phase E — Permanent maintenance

Establish and document the knowledge-update expectations for future agents.

New work should preserve important decisions and context so that the knowledge base becomes more complete over time.

---

## 13. Completion Report

When finished, provide:

1. A summary of the documentation created or updated.
2. A map of the final knowledge-base structure.
3. The important historical