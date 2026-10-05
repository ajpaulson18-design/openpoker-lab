---
description: Focused QA review for substantial OpenPoker Lab pull requests.
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    paths:
      - "pokerlab/**"
      - "tests/**"
      - "scripts/**"
      - "web/**"
permissions:
  contents: read
  issues: read
  pull-requests: read
engine: copilot
network: defaults
tools:
  github:
    toolsets: [default]
safe-outputs:
  submit-pull-request-review:
    footer: if-body
  report-failed-jobs: false
max-turns: 30
max-ai-credits: 60
timeout-minutes: 15
---

# OpenPoker Lab QA review

Read `AGENTS.md`, `.github/copilot-instructions.md`, and `.github/agents/qa-testing.agent.md`. Review only the triggering pull request.

Concentrate on externally meaningful defects, poker-rule correctness, hidden-information leaks, deterministic replay and serialization, persistence integrity, solver boundaries, malformed inputs, local HTTP security, regressions, and missing tests. Treat ambiguous poker or modeling behavior as a finding rather than deciding it.

Do not duplicate lint feedback, repeat the general Copilot review, or comment on trivial style. If there is no material QA finding, submit no review. Otherwise submit one concise review that separates blocking problems from optional improvements and cites concrete files or functions.
