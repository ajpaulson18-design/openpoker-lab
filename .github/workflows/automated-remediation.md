---
description: Weekly and on-demand low-risk repository remediation for OpenPoker Lab.
on:
  schedule: weekly on monday
  workflow_dispatch:
permissions:
  contents: read
  actions: read
  issues: read
  pull-requests: read
engine: copilot
model: auto
network: defaults
tools:
  github:
    mode: gh-proxy
    toolsets: [default]
  cli-proxy: true
  bash: ["*"]
safe-outputs:
  create-pull-request:
    draft: true
    max: 1
    title-prefix: "[maintenance] "
    max-patch-files: 12
    max-patch-size: 512
    protected-files: blocked
    if-no-changes: ignore
  report-failed-jobs: false
max-turns: 50
max-ai-credits: 100
max-daily-ai-credits: 100
timeout-minutes: 25
---

# OpenPoker Lab automated remediation

Read `AGENTS.md`, `.github/copilot-instructions.md`, and `.github/agents/automated-remediation.agent.md`, then inspect repository health and recent CI results.

Only fix a concrete, reproducible, low-risk maintenance defect whose intended behavior is unambiguous. Prefer a failing check, broken link, obvious implementation defect, configuration inconsistency, cross-platform test failure, or stale factual documentation. Do not change poker strategy, probability meanings, solver scope, modeling assumptions, public product direction, architecture, source data, or security boundaries. Do not perform dependency upgrades with meaningful behavioral risk.

Reproduce or verify the problem, inspect nearby context, make the smallest root-cause fix, and run the directly relevant checks. Check open CI-failure issues and existing maintenance pull requests first so work is not duplicated. Create at most one focused draft pull request and reference the issue or failed run it resolves. If there is no worthwhile fix, invoke the safe-output `noop` tool with a concise explanation. Never create a status issue or a trivial cleanup PR merely to show activity.
