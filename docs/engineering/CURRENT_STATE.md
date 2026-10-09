# Current engineering state

Baseline audited: commit [`65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce`](https://github.com/ajpaulson18-design/openpoker-lab/commit/65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce). This file describes that repository snapshot. It does not report a test run performed for this audit.

OpenPoker Lab is a standard-library Python 3.11+ research app with a plain JavaScript client. Its implemented surface includes weighted Hold'em range parsing and hand evaluation, sampled multiway equity and exact heads-up river equity, one-decision EV estimates, a locally persisted opponent tendency model, finite heads-up river and postflop CFR solvers, a hand-practice flow, deterministic explanations and presentation styles, and a loopback HTTP server. README.md and AGENTS.md define the intended research boundary: no unrestricted no-limit equilibrium or profitability claim.

## Implemented surface and boundaries

| Area | Implemented at baseline | Key constraints |
| --- | --- | --- |
| Cards and ranges | `pokerlab/cards.py`: card parsing, weighted range expansion, blocker removal and best-five hand ranking | Range tokens and override behavior are described in README.md. |
| Equity | `pokerlab/equity.py`: seeded Monte Carlo for one to five opponents; exact weighted enumeration for a heads-up five-card board | Monte Carlo interval is a normal-approximation sampling interval, not range uncertainty. Multiway draws use independent weighted draws with joint rejection on collisions. |
| Decision analysis | `pokerlab/analysis.py`: fold/call or check/bet one-decision EV using supplied ranges and fold rate | No rake, raises, stack caps, or subsequent betting. Pre-river results are checkdown estimates. The default comparison's 45% fold rate is illustrative, not equilibrium. |
| Opponent observations | `pokerlab/models.py`: independent Beta-prior tendencies, explicit opportunity counts, street/context filtering, SQLite persistence, immutable snapshots and legacy reads | Aggregate tendencies do not identify hidden-card ranges or hand-specific action frequencies. Showdown bluff evidence is selected and biased. |
| River solving | `pokerlab/solver.py`, `restricted_solver.py`, `river_tree.py`, `cfr.py`, and `equilibrium.py`: exact compatible private-hand traversal over a configured finite action tree; vanilla CFR default and optional DCFR | Fixed-board, heads-up, supplied ranges and bounded sizes/stack/depth. Legacy fixed-bet entry remains a compatibility path. No future street or unrestricted NLHE. Node locks make the unrestricted best-response gap a profile exploitability diagnostic, not a locked-game convergence certificate. |
| Postflop solving | `pokerlab/postflop_solver.py`, `turn_solver.py`, `planned_cfr.py`, `public_cfr.py`: finite flop/turn/river starts, exact requested physical worlds, recursive reference plus optional planned and public-batched Python traversal | Resource caps constrain ranges and trees. Selected runouts condition and renormalize the whole joint game. No preflop, multiway equilibrium, chance sampling, or unrestricted sizing. |
| Hand practice | `pokerlab/game.py`, `practice.py`, `decision_study.py`, and `server.py`: 2–6 seat hand mechanics, side pots, review and decision capture | Sandbox state is in memory; local observations and reports are persisted. Capture and persistence adapters are implemented in `practice.py` and `server.py`; there is no `decision_capture.py` module. Opponent cards are kept out of the human-facing decision serialization. |
| Explanations/coaching | `contracts.py`, `explanations.py`, `personalities.py`, `coach_*`, `situation_teaching.py`: structured facts, deterministic prose and local voices; optional external plan selector and bounded multi-turn coach | The external provider selects a validated reply plan; deterministic local rendering supplies the response. External AI is explicitly opt-in and allowlisted. See canonical coaching docs below. |
| HTTP/browser | `server.py` and `pokerlab/web/`: JSON endpoints, static interface and local session state | Server is loopback-only with Host/Origin checks, JSON mutation boundaries, concurrency controls and restrictive CSP. It is not an authenticated public service. |

## Validation evidence and its status

Validation statements have different evidentiary status and should not be conflated:

* **Implemented checks** are executable tests/scripts present in the repository. Their existence does not establish that they passed at this baseline or in a particular environment.
* **Historical documented runs** are claims recorded in docs or benchmark artifacts for their stated source revision, Python version, fixtures and machine. They are not a fresh run of commit `65c9ba7` unless the record says so.
* **Audit activity** here was source and documentation inspection only. No test command was run for this audit; no pass claim is made.

The source tree includes unit tests under `tests/` and validation/benchmark scripts under `scripts/`. Relevant map:

| Concern | Executable evidence in repository | Canonical detailed reference |
| --- | --- | --- |
| Evaluator, range parsing, equity, EV, game settlement | `tests/test_core.py`; `scripts/validate_evaluator.py` | README.md, “Tests” and “Range notation” |
| River CFR formulas, exact best responses, strategy interface | `tests/test_solver_validation.py`, `tests/test_solver_variants.py`, `tests/test_configurable_solver.py`; `scripts/validate_solver.py` | `docs/solver-validation.md`, `docs/configured-river-validation.md` |
| Turn/flop physical worlds, serialized policy replay, stack/chance semantics | `tests/test_turn_solver.py`, `tests/test_postflop_solver.py`, `tests/test_public_postflop.py`, `tests/test_postflop_budget.py` | `docs/turn-river-validation.md`, `docs/postflop-validation.md`, `docs/public-batched-cfr.md` |
| Planned/public traversal lifecycle and agreement | `tests/test_planned_cfr.py`, `tests/test_cfr_lifetime.py`, `tests/test_public_cfr.py` | `docs/planned-traversal.md`, `docs/public-batched-cfr.md` |
| Opponent estimates, persistence, deduplication, filtering, malformed legacy data | `tests/test_opponent_model.py`, `tests/test_core.py` | `docs/architecture.md`, `docs/human-aware-strategy.md` |
| Practice replay, decision capture, hidden-information constraints | `tests/test_practice.py`, `tests/test_decision_capture.py`, `tests/test_decision_study.py` | `docs/decision-capture-v1.md`, `docs/decision-study-v1.md` |
| Explanation facts, coach grounding/visibility, voices and bounded conversation | `tests/test_explanations.py`, `tests/test_coach_grounding.py`, `tests/test_coach_analysis.py`, `tests/test_coach_teaching.py`, `tests/test_personalities.py`, `tests/test_coach_provider.py`, `tests/test_coach_conversation.py`, `tests/test_current_coach.py`, `tests/test_current_coach_conversation.py`, `tests/test_coach_request.py` | `docs/ai-coach-architecture.md`, `docs/current-coach-conversation-v1.md`, `docs/coach-analysis-v1.md` |
| HTTP/security and front-end contract | `tests/test_core.py`, `tests/test_practice.py`, `scripts/test_frontend.cjs` | README.md, “Data and local access”; `docs/architecture.md` |

Some detailed docs contain explicit historical suite counts, benchmark timings, parity results, and source hashes. Read each claim together with its stated source commit, runtime and fixture. For example, `docs/public-batched-cfr.md` records v2 whole-call measurements at source `b6085fc` on Python 3.14.7, while `docs/postflop-validation.md` records earlier source-specific runs and later integrated runs. These are useful evidence for those snapshots, not proof of current-baseline execution. `benchmarks/results/` stores versioned measurements; benchmark files are experiments, not CI results.

## Documentation map and maintenance gaps

Use existing detailed docs as canonical, rather than copying their derivations into overview pages:

* Overall product assumptions and user-facing feature inventory: [README](../../README.md).
* Layers, contracts, EV and posterior conventions: [architecture](../architecture.md) and [human-aware strategy](../human-aware-strategy.md).
* River solver scope and independent mathematical validation: [solver validation](../solver-validation.md); configurable betting semantics: [configured river validation](../configured-river-validation.md).
* Turn and shared postflop contracts: [turn/rivers](../turn-river-validation.md), [postflop](../postflop-validation.md), [planned traversal](../planned-traversal.md), [public-batched CFR](../public-batched-cfr.md).
* External and deterministic coaching boundaries: [AI coach architecture](../ai-coach-architecture.md), [coach setup](../ai-coach-setup.md), [current conversation](../current-coach-conversation-v1.md).
* Hand capture and review: [decision capture](../decision-capture-v1.md), [decision study](../decision-study-v1.md).

The pre-existing `docs/architecture.md` remains valuable for mathematical and API detail but its introductory flow predates the current number of modules and its solver summary is less complete than the dedicated postflop docs. Keep it as a conventions reference; use [system overview](../architecture/SYSTEM_OVERVIEW.md) for the current module map. Several docs report validation results from historical source revisions without a single release-level validation ledger. Future changes should record exact full source SHA, Python version, command, outcome, and scope for any new validation claim. Do not convert presence of tests or a check that passed on another snapshot into a statement that this baseline passed.
