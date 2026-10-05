---
description: Detect material documentation drift in OpenPoker Lab pull requests.
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    paths:
      - "pokerlab/**"
      - "scripts/**"
      - "web/**"
      - "README.md"
      - "docs/**"
permissions:
  contents: read
  issues: read
  pull-requests: read
engine: pi
model: copilot/gpt-4o
network: defaults
tools:
  github:
    mode: gh-proxy
    toolsets: [default]
  cli-proxy: true
safe-outputs:
  submit-pull-request-review:
    footer: if-body
  report-failed-jobs: false
max-turns: 20
max-ai-credits: 40
timeout-minutes: 10
---

# OpenPoker Lab documentation drift review

Read `AGENTS.md`, `.github/copilot-instructions.md`, and `.github/agents/documentation.agent.md`. Inspect the triggering pull request for documentation that became inaccurate, incomplete, unverifiable, or misleading because of the changed behavior.

Pay special attention to setup commands, public API behavior, persistence and replay guarantees, security boundaries, solver limitations, probability meanings, and any GTO or profitability claim. Do not request documentation for internal details that users and maintainers do not need. Do not invent features, evidence, or benchmarks.

If no material drift exists, submit no review. Otherwise submit one concise actionable review with exact files or sections that require correction.
