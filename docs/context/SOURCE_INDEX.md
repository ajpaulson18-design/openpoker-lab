# Project source index

This index points to repository sources that carry durable project context.
Commit IDs below are full Git object IDs from the history available at the
index's creation. They identify evidence snapshots; use each path at the current
revision for current behavior. See [project history](../history/PROJECT_HISTORY.md)
for chronology and limits on what the record can establish. This index includes only the partial supplied chat excerpts/memory summaries
identified below; full private project conversations were not retrieved.

## Owner and chat-context sources

| Source | Coverage / authority | Identifier |
| --- | --- | --- |
| [Owner mission](OWNER_MISSION_2026-10-08.md) | Supplied explicit instructions; original file ends mid-§13 | `Pasted text(3).txt`, supplied Oct 8, 2026 |
| [Recovered chat knowledge](RECOVERED_CHAT_KNOWLEDGE.md) | Partial supplied dated excerpts and memory summaries; no full transcript retrieval | `CTX-2026-10-08`, entries C001–C011 |
| Current session clarification | Direct owner says primary goal is transferring “poker simulation” chats/memories to GitHub | `CLARIFICATION-2026-10-08`, C012 |

## Authority and current constraints

The commit column below identifies the pre-mission audited source snapshot.
This knowledge-transfer change updates onboarding and delegation instructions;
read their current files for the resulting policy, retaining these baseline
references as historical provenance.

| Source | What it establishes | Key commit |
| --- | --- | --- |
| `AGENTS.md` | Current project scope, architecture invariants, validation commands, completion standard, and division of work | `65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce` |
| `README.md` | User-facing capabilities, limitations, local operation, data boundaries, development directions | `65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce` |
| `CONTRIBUTING.md` | Contribution and validation expectations | `65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce` |
| `LICENSE`, `pyproject.toml` | MIT declaration and package metadata | `3baaea841c883cc78f1df49ad9bee785f0e14fb5` |
| `.github/copilot-instructions.md` | Current Copilot repo guidance and division of labor; compare older automation artifacts before relying on them | `b7b27c681de75078e202f0fa4097f50ccd87f848` |
| `.github/agents/`, `.github/workflows/` | Present agent and workflow artifacts; their existence alone does not establish current use or precedence | `65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce` |

## Architecture and product contracts

| Source | Why it matters | Key commits |
| --- | --- | --- |
| `docs/architecture.md` | Product architecture and component boundaries | `3baaea841c883cc78f1df49ad9bee785f0e14fb5`; updated `946d65a65f914eb03c8e7d25e405170d5bda0201` |
| `docs/human-aware-strategy.md` | Ownership of strategic facts, human-aware adapters, explanation and presentation boundaries | `d3ec8bcc47c8e9dfe7e01607be33a01ed1d469e6`, `226b94d171c92b9ed15b4c9f03ebf06ff3765035` |
| `docs/decision-capture-v1.md` | Decision-time evidence and replay boundary | `250ba6a5d40fed3e951a6a61967172b63935e413`, implementation `cd4eb429b8fbf2700bcdc913d841200047698259` |
| `docs/decision-study-v1.md` | Deterministic saved-decision study contract | `2676dbcb46d8f1a56f86c224c5dfea6953807903` |
| `docs/coach-analysis-v1.md` | Versioned analysis evidence contract and provenance | `98806158e24d6da9acb183fedb4041de3cadbd77` |
| `docs/ai-coach-architecture.md` | Coach/provider boundaries, trusted grounding, data minimization | `7b4a1fb6ede1eed6da5102461d1f540e4dadc77f` |
| `docs/current-coach-conversation-v1.md` | Bounded current-decision conversation contract | `2b9999c07951b09d3feabe15b12bbbde235582a7`, implementation `c495e2343ddac11fd30615a1350267a69774ab73` |
| `docs/luna-*-slice.md` | Narrow coach implementation plans/handoffs and their constraints; check implementation and later commits for status | First slice `7b4a1fb6ede1eed6da5102461d1f540e4dadc77`; latest committed handoff `36fa36151fede3a874936b64cae0b3ca12869abd` |
| `docs/visual-interface.md` | Visual direction and interface constraints | `8e363243a6bdfc4a7eba6eca4e6d7561966c3165` |
| `docs/release-candidate-0.2.0.md` | Historical release integration, test claims, known limits at that point | `d6d39980b43035c4bd0a7336b692778b0aaa97dd` |

## Solver research and validation

| Source | Why it matters | Key commits |
| --- | --- | --- |
| `docs/solver-validation.md` | River CFR correctness scope, independent validation, API and limits | `10ef980a5e18e393bad1ce3b55d64599ca7231bf`, audit `48f6803e474ce514c54da8916dd61cef57fd0ac4` |
| `docs/configured-river-validation.md` | Betting-tree semantics, stack accounting, short all-ins and refunds | `45f5baabe6f9d598d8be9f1d31d1fc51d2de04d0`, updates `6d9ca2258801dc4eabd11ee03a9b6e770466f5df`, `648156287ea244c79097ebf0a6c79225304606e3` |
| `docs/solver-progress.md` | Milestone chronology, validation and benchmark provenance; newest solver source-frozen comparison | `0f10524e844b64c4b9f672d157209220f33b5aad`, latest `e6659398fc913e24f37ea70e215424932689c686` |
| `docs/solver-research.md` | Solver algorithm research, public references, limited license observations | `0f10524e844b64c4b9f672d157209220f33b5aad` |
| `docs/turn-research-notes.md` | Research rationale for exact public chance and turn-to-river architecture | `21240845cb0627e8e23790957faa37fe6bc8ff11` |
| `docs/turn-river-validation.md` | Exact turn-to-river API, chance conditioning, independent parity and benchmark scope | `21240845cb0627e8e23790957faa37fe6bc8ff11`, `e7300cd56b74c9cddff78a87251276e056857c41` |
| `docs/planned-traversal.md` | Optional static Python traversal semantics, parity, memory/runtime limitations | `9872961d7f69075039f7f7c5150331ad68b1c7a8`, measurement `834a8e92878e60e21041e99358291ec57adda522` |
| `docs/postflop-research.md` | Broader postflop research context and explicit limitations of public/license review | `41784507f4d37d563b514da0600b931bb3c0bc3e` |
| `docs/postflop-validation.md` | Shared flop/turn/river API, guards, ordered chance, independent validation | `41784507f4d37d563b514da0600b931bb3c0bc3e`, integrated measurements `786c110086c517387d773e096535d47f58d10876` |
| `docs/public-batched-cfr.md` | Exact public-batched backend contract, parity and source-frozen measurements | `9d2d66fc72a10b796c6d6153c6c5fa92ad66b460`, normalization trigger `b6085fc26ca22b03d6755a05e5ffed3767021c98`, comparative report `e6659398fc913e24f37ea70e215424932689c686` |
| `benchmarks/*.json`, `benchmarks/results/*.json` | Machine-readable configurations/results; pair with the documentation and source hashes before comparison | Introduced across solver milestones; current public-batched reports `b6085fc26ca22b03d6755a05e5ffed3767021c98` and `e6659398fc913e24f37ea70e215424932689c686` |

## Licensing evidence and limits

The repository's license declaration is MIT (`LICENSE`). Research notes capture
observations about selected public repositories and state that they are not a
complete code audit, legal advice, or patent clearance. The solver research
record explicitly limits its source observations to the pages/versions viewed
at the time; the postflop research record also says no external implementation
or dependency was incorporated. Relevant records are `docs/solver-research.md`
at `0f10524e844b64c4b9f672d157209220f33b5aad` and
`docs/postflop-research.md` at
`41784507f4d37d563b514da0600b931bb3c0bc3e`. These sources support only the
stated, bounded claims. They do not establish comprehensive licensing clearance
or current third-party license status.

## Automation history and stale-convention warning

The Copilot system changed repeatedly in October 2026. The history includes
initial agent setup (`fbfdb79a0f43408a291d92ad1804f6a505d9baa8`), workflow
configuration (`ea389907a41685e53a6856385090e77ce5f6624`), backend/model routing
experiments (`22950cb755ff0bccf92acb61770e433d92475156`,
`0f1cb67b762355eaf2b754f94f7a12088a3f5fd6`), and a restoration of documented
configuration (`7163f8de3abeec1471ffea3628d5393779f5950c`). Later commits adjusted
the system again, including `.github` agent files and the repository guidance.
Do not treat every workflow, lock file, agent prompt, branch name, or older
commit message as a live mandate. `AGENTS.md` is the repository's present
primary instruction; `.github/copilot-instructions.md` supplies current
Copilot-specific guidance. The historical changes do not reveal which legacy
automation conventions the owner intends to retire.

## Evidence limits

This index was built from the checked-out tree, Git commit metadata, committed
documentation, and a dated GitHub API snapshot supplied for this audit. The
tracker details are summarized in [project history](../history/PROJECT_HISTORY.md)
and do not prove activity beyond the capture time. No conversation archive was
available. Commit IDs identify source snapshots and do not prove owner approval,
business priority, or completion of future goals.
