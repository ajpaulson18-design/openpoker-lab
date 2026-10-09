# Product vision and owner-established principles

Authority: [supplied owner mission](../context/OWNER_MISSION_2026-10-08.md),
sections 1, 4, 6, 9 and 11. These are **confirmed owner decisions**, not claims
that the destination is already implemented.

OpenPoker Lab is a commercially oriented poker simulation, solver and educational
product. Work should contribute to customer value and commercial success. Its
purpose extends beyond returning a mathematically optimal action:

> You're describing something bigger than an AI that tells people what the mathematically optimal poker move is. You're describing an AI that helps people understand the situation they're in, why it's difficult, and how to think through it.

This is the foundational coaching principle. The coach should explain the
situation, identify why a choice is difficult, expose relevant strategic factors,
and teach reasoning transferable to similar situations across experience levels.
The owner's quality benchmark is personally preferring OpenPoker Lab over other
apps or videos when seeking to understand a poker situation. This is an aspiration
and acceptance direction, not evidence of measured competitive superiority.

## Boundaries that must survive future work

- Computing strategy, assessing a specific choice and explaining that assessment
  are distinct functions. Solver and coach workstreams must not interfere or gain
  unnecessary coupling. Versioned evidence contracts join them.
- Structured game-state/solver-grounded decision logic and reusable explanations
  are an approved direction. A chatbot or a newly trained language model is not
  inherently required. Optional conversations already exist; they remain downstream.
- The separate commercial entertainment poker video game is a separate product.
  No integration or shared-product roadmap is established by this mission.
- Before substantial specialized custom implementation, audit mature tools,
  libraries and legitimate reusable solutions. Record why reuse or independent
  implementation best serves the technical and commercial requirements.
- Studying research or other solvers does not authorize copying proprietary code,
  interfaces, datasets or output. Preserve licensing obligations.
- Repository knowledge must be transferable across AI providers. Separate owner
  decisions, implementation evidence, plans, experiments and unknowns.
- Preserve the existing project and parallel development goals. This knowledge
  mission does not approve solver rewrites or coach feature expansion.

## Visual decision already recorded in the repository

[Visual interface](../visual-interface.md), supported by commit `8e36324` and
merged PR #61, reports owner approval on October 8, 2026 of the implemented
espresso front face and minor refinements thereafter. Treat it as a recorded
owner decision. Its original conversation is not available in this audit.
The committed blueprint and real data/presentation boundaries remain canonical.
