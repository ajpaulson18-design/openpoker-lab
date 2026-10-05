# GitHub Copilot repository instructions

Read and follow the root `AGENTS.md` before acting.

Preserve OpenPoker Lab's explicit model boundaries: standard-library local research app, restricted river game, transparent assumptions, deterministic calculations, and no profitability or unrestricted-GTO claims. Keep calculations and immutable structured results separate from explanatory prose and coach personalities.

Use the commands and completion standard in `AGENTS.md`. Prefer reproducible poker scenarios and externally meaningful regression tests. Never use personal opponent data in examples or commits.

For code review, focus on poker-rule correctness, hidden-information leaks, solver or EV errors, persistence/replay integrity, local HTTP security, model-assumption drift, regressions, and missing tests. Ignore trivial style already covered by automation.

Division of labor: Codex owns major features, architecture, hard debugging, large refactors, substantial product changes, and cross-repository decisions. Copilot agents provide focused QA, maintenance, documentation, and skeptical review. Surface ambiguous or high-impact decisions instead of making them silently.
