---
description: Combined QA and documentation review for meaningful OpenPoker Lab pull requests.
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    paths:
      - ".github/**"
      - "pokerlab/**"
      - "tests/**"
      - "scripts/**"
      - "docs/**"
      - "README.md"
      - "pyproject.toml"
permissions:
  contents: read
  copilot-requests: write
  issues: read
  pull-requests: read
engine: copilot
model: gpt-5-mini
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
  report-failure-as-issue:
    - "!inference_access_error"
    - "!ai_credits_rate_limit_error"
max-turns: 35
max-ai-credits: 70
max-daily-ai-credits: 70
timeout-minutes: 16
---

# OpenPoker Lab quality review

Read `AGENTS.md`, `.github/copilot-instructions.md`, `.github/agents/qa-testing.agent.md`, and `.github/agents/documentation.agent.md`. Review only the triggering pull request.

Perform one integrated review covering:

- poker-rule correctness, hidden-information leaks, EV or solver errors, malformed inputs, regressions, and missing tests;
- deterministic replay and serialization, persistence integrity, local HTTP security, and documented solver boundaries;
- documentation made inaccurate, incomplete, unverifiable, or misleading by the changed behavior;
- setup commands, public API behavior, probability meanings, and any GTO or profitability claim.

Do not duplicate lint feedback or the general Copilot review. Do not comment on trivial style, request documentation for irrelevant internals, invent evidence, or decide ambiguous poker or modeling behavior.

If there is no material finding, invoke the safe-output `noop` tool with a concise explanation. Otherwise submit one concise review that separates blocking defects from optional improvements and cites exact files, functions, or documentation sections.
