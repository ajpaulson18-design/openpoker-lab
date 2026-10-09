# Knowledge-transfer validation and remaining coverage

Run date: October 8, 2026 America/New_York (October 9 UTC).
Baseline application source: `65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce`.
The knowledge-transfer branch changes documentation, agent entry points and a
stdlib documentation checker/CI job; application, solver and coach code is unchanged.

## Commands actually run

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests` | 331 tests passed in 64.730 seconds, Python 3.12.14 |
| `node scripts/test_frontend.cjs` | 8 frontend contract checks passed |
| `node --check pokerlab/web/app.js` | Passed |
| `python -m scripts.validate_docs` | Passed; checks Markdown local file targets and required entry points |
| Temporary synthetic validator exercise | Detected a broken link and a missing required file; ignored external URLs, fragment-only links and fenced examples |
| `git diff --check` (including staged added files before commit) | Passed |
| Source-reference review | New module/test paths checked for existence; historical commit IDs resolved with Git |

No new live-provider request, browser visual review, exhaustive evaluator run,
benchmark or third-party legal/market research was performed. No application logic
changed. Historical benchmark measurements remain attached to their own revisions.
GitHub CI outcome is separate from the local results above.

## Independent cold-start review

A bounded GPT-6 Luna reviewer read the new entry points and linked repository
specifications. The lead reviewed the resulting findings and corrected the root
solver description, release-version wording and baseline-source labels.

| Cold-start question | Repository evidence |
| --- | --- |
| What is OpenPoker Lab? | [Vision](../product/VISION.md), [current state](CURRENT_STATE.md) |
| Why does it exist? | Vision and [recovered chat knowledge](../context/RECOVERED_CHAT_KNOWLEDGE.md), C002–C005 |
| What differentiates it? | Contextual teaching and opponent-aware transparent analysis in vision; comparative market superiority remains unverified |
| What is implemented? | Current state, source and linked tests |
| How does the solver work? | [System overview](../architecture/SYSTEM_OVERVIEW.md) and finite-game validation specifications |
| How does simulation work? | System overview: weighted equity, card/game mechanics and replay boundaries |
| How is coaching intended to work? | Vision, immutable evidence and bounded provider-plan specifications; intent separated from implemented scope |
| What remains unfinished? | [Roadmap](../product/ROADMAP.md) and [gaps](../context/KNOWLEDGE_GAPS.md) |
| What decisions must be preserved? | [Decision register](../decisions/DECISION_LOG.md), AGENTS.md and approved visual boundary |
| What commercial/license constraints apply? | [Licensing](../research/LICENSING.md), roadmap and repository LICENSE |
| What is next? | Roadmap maps documented workstreams and safe next actions; no invented ranking or launch commitments |
| How should agents contribute? | [Task and maintenance protocol](../agents/TASK_PROTOCOL.md) |

## Primary mission remains partial

Structural onboarding passes do not establish complete chat recovery. Relevant
provided chat excerpts/memory summaries and the owner's current instructions are
transferred with explicit source labels. The full ChatGPT **poker simulation**
project chats were not retrieved: conversation search returned an error and only
the mission artifact surfaced. Historical rationale, alternatives and owner
choices absent from those partial sources remain missing. Additional source
exports or working retrieval are needed for a complete project-chat transfer.
