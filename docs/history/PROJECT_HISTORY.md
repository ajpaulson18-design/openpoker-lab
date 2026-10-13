# Project history and decision record

This is a repository-evidence summary of the history available in Git through
`65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce` (2026-10-08). It records changes
and stated project direction, not private conversations or unrecorded owner
intent. Commit subjects are clues; linked source documents and code define the
evidence. The companion [source index](../context/SOURCE_INDEX.md) maps the
important records to full commit IDs.

## Chronology

### September 30: initial application and explicit boundaries

The initial commit (`b3938103463c7b0bfc2417c81160f1496ee1cda1`) is followed by
the first full application commit (`3baaea841c883cc78f1df49ad9bee785f0e14fb5`).
That baseline combines Hold'em simulation, opponent observations, EV analysis,
explanations, a research UI, and a restricted river CFR solver. Early follow-up
commits add custom player names, human-aware strategy contracts, deterministic
explanations, multidimensional Bayesian opponent modeling, and a confidence-aware
river exploit adapter. See the implementation sequence in Git and the durable
boundaries in `AGENTS.md`, `README.md`, and `docs/human-aware-strategy.md`.

The project consistently describes itself as local research software. It does
not claim unrestricted no-limit Hold'em solving, calibrated opponent prediction,
or profitability. Those are important constraints, not incidental release
wording.

### October 1: replayable, privacy-conscious practice

The practice path adds coaching and session review, then tightens privacy,
opponent snapshots, and replay completeness. Deterministic coaching voices are
kept downstream of calculation. The release-candidate audit records the
single-hero flow, sanitized decision-time evidence, multi-opponent equity, and
the separation between stored choice and pre-action evidence
(`d6d39980b43035c4bd0a7336b692778b0aaa97dd`, with implementation milestones
`752e06b9f97a9d6c6079543fc896049444eceebd`,
`f4050489a3641a8f4ecc1a9f7d4c40ffa7615e83`, and
`a2992fcd36e826889f51c97bd4857fd63d6475c8`). The 0.2.0 document is a historical
integration report; its solver limitations predate later solver work and should
not be read as current solver capabilities.

### October 4–6: automation experiments and solver validation

The Git history records several iterations of GitHub Copilot agent and workflow
configuration from October 4–6. Those commits are historical repository
automation changes, not project product requirements. Current operating
guidance is in `AGENTS.md` and `.github/copilot-instructions.md`; some old agent
and workflow artifacts may still encode prior conventions. See the source index
for the configuration commit chain.

In parallel, the solver gains a batch Monte Carlo simulator, an audited
fixed-board river CFR interface, configurable river action trees, short all-in
and unequal-stack handling, deterministic explanation integration, and browser
validation. Key milestones are `898dff869fc4be86248f5747cca94e53fe2cd991`,
`48f6803e474ce514c54da8916dd61cef57fd0ac4`,
`504f05989dd5f88c0aec844ed3c61d8d22c95da6`,
`648156287ea244c79097ebf0a6c79225304606e3`, and
`4d75a761b203510296f7666e9aff7fb751e4d6de`. `docs/solver-validation.md` and
`docs/configured-river-validation.md` capture correctness scope and betting
semantics. A configurable tree is still only the configured heads-up game.

### October 7: structured study and bounded AI coaching

The work sequence first establishes a solver-grounded coach analysis contract
and trusted decision capture (`7b4a1fb6ede1eed6da5102461d1f540e4dadc77f`,
`b18481fec242a5c891b188251a92a5efa9ac4a39`,
`cd4eb429b8fbf2700bcdc913d841200047698259`). It then adds saved-decision study,
provider-safe grounding, a one-shot opt-in external coach, grounded teaching
notes, bounded follow-ups, and current-decision previews. Representative
milestones include `2676dbcb46d8f1a56f86c224c5dfea6953807903`,
`190a550fce7e19b339cf74d5b02a362d4cf99113`,
`80940452620c6d82d9d9ea7b6957dbb5404d2f2b`,
`7a7330797280ad05f3acec8d35cbeb5cfa66b6fe`,
`f6cc76ffca80b8257ca76e268dabe89cfcbcef9e`,
`128f6fc0dfda70b757e7a481b610d80f5fef722c`, and
`f0c7b619678c8244c67c71c77aadce04340260e2`.

Across these slices, the stable design is that calculations and trusted
evidence own strategy facts; coach plans select bounded intents and known facts;
rendering owns prose. Provider use is explicit and opt-in, and sensitive hidden
cards, opponent names and notes, raw histories, and databases are excluded from
provider payloads. Read the individual `docs/luna-*-slice.md` handoffs as
implementation records, not as proof that every proposed future slice remains
active.

### October 8: teaching, interface baseline, and solver breadth

The coaching UI adds contextual beginner teaching and accessible saved-action
evidence (`f2e5c43eaf245ce9ebae68d21e2a92bfd08277c5`,
`477d07395ae3b21e37c3c1745bee594d202b34be`,
`f0f13a858bccfcdb7f38ad07557c259667acaffe`). The espresso interface is
implemented, refined, and recorded as the visual baseline in
`642a8f2ea94e53c5a648236ee53ef30e70991eac`,
`5478cd78d2193ec8bd0d9ad408097e74717fb726`, and
`8e363243a6bdfc4a7eba6eca4e6d7561966c3165`.

The solver history expands from the fixed river engine to shared CFR and betting
tree kernels, exact turn-to-river chance, optional planned traversal, lifetime
cleanup, shared flop/turn/river solving, resource guards, and exact public-batched
training. Key decisions and validations are documented at
`76facc252992ddf9fc489ebb0a0f27a81b1ce4da`,
`b093c9965f6e6f49ef1e5cf452f2c19345ebf543`,
`f6f46a28ea7333f43be0cc5dd1b07eba0c04e453`,
`e18510d5dfedfc0660811b74bec89c5596dfa8f5`,
`3a8a78ae2984a304444466604193daebaa1aa38f`,
`bac5e474b94a8e01e5b0c625a6557c6bb5f39bbb`, and
`9d2d66fc72a10b796c6d6153c6c5fa92ad66b460`. The final recorded main commit is
`65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce`.

Current solver contracts preserve exact physical joint chance weights and
ordered reveals, hidden future cards, perfect recall, and bounded resource use.
Recursive traversal remains the reference; planned and public-batched are
optional backends with stated constraints. Benchmarks are tied to source,
configuration, and harness revisions and must not be generalized beyond their
fixtures.

## Direction recorded in repository documents

The README and solver records describe continued work on conditional opponent
models, structured history import, held-out calibration, broader solver games,
and strategy benchmarking. The latest solver-progress record also calls out
commercial full-NLHE as an objective while warning that action-tree and street
coverage do not establish equilibrium accuracy (`docs/solver-progress.md`,
latest milestone in `e6659398fc913e24f37ea70e215424932689c686`). These are
documented directions, not a ranked or owner-approved roadmap. Git contains no
conversation transcript establishing priority, commitment, schedule, or the
owner's intent among them.

Licensing documentation is also present: the repository declares MIT, and
`docs/solver-research.md` and `docs/postflop-research.md` record public-source
license observations and explicitly limit their scope. Those notes say they are
not a complete code audit, patent clearance, or legal advice. They state that
third-party code, dependencies, proprietary solver output, and license changes
were not introduced in the recorded solver work. Any broader license review or
future third-party integration remains unverified here.

## What Git does not establish

Git establishes committed artifacts, authorship metadata, parentage, and recorded
validation claims. It does not grant access to private chat, prove that an old
branch remains active, or reveal unstated owner intent. Branch names and stale
handoff language are not evidence of current commitments. Where a document says
“next,” treat that as the author's planning language at that commit unless a
later source reaffirms it.

## Tracker snapshot supplied for this audit

An accompanying GitHub API snapshot dated 2026-10-09 shows quality-review
budget issue #64 open: the workflow skipped its agent after rolling 24-hour
usage reached 80 AI Credits against a configured 70-credit threshold. The issue
says the workflow should resume after the window resets; this records a workflow
budget event, not an application defect. See
[#64](https://github.com/ajpaulson18-design/openpoker-lab/issues/64).

That snapshot also lists maintenance PRs #18 and #19 about stale 0.2.0 release
wording and PR #14 about native Copilot routing as open. The records have `merged_at` null: they were unmerged at capture time.
A populated `merge_commit_sha` on an open PR can represent a provisional merge
commit and does not establish a merge. Treat these as open tracker items, not
proof that the changes have shipped or are approved priorities. See
[#18](https://github.com/ajpaulson18-design/openpoker-lab/pull/18),
[#19](https://github.com/ajpaulson18-design/openpoker-lab/pull/19), and
[#14](https://github.com/ajpaulson18-design/openpoker-lab/pull/14). The checked
out source was not changed based on tracker state alone.
