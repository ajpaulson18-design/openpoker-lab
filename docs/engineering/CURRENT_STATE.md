# Current engineering state

Current source snapshot: merged main [`46e142be8e9585005e5de70bb32bf4a76f731a1c`](https://github.com/ajpaulson18-design/openpoker-lab/commit/46e142be8e9585005e5de70bb32bf4a76f731a1c) (Oct. 13, 2026). This is a source/documentation update only; it does not report a test run performed for this snapshot. The original Oct. 8–9 knowledge audit at `65c9ba7a9ddba67f2bababe51e4d6c5eed8696ce` is retained as historical evidence in [the transfer validation record](KNOWLEDGE_TRANSFER_VALIDATION.md).

OpenPoker Lab is a standard-library Python 3.11+ research app with a plain JavaScript client. Its implemented surface includes weighted Hold'em range parsing and hand evaluation, sampled multiway equity and exact heads-up river equity, one-decision EV estimates, a locally persisted opponent tendency model, finite heads-up river/postflop solvers, bounded heads-up preflop models, a separate fixed-flop checkdown game, hand practice, deterministic explanations, optional coaching and a loopback HTTP server. README.md, AGENTS.md and the detailed solver references define the limits: no unrestricted no-limit equilibrium, no multiway equilibrium, and no full-deck preflop solution with later-street betting.

## Implemented surface and boundaries

| Area | Implemented at baseline | Key constraints |
| --- | --- | --- |
| Cards and ranges | `pokerlab/cards.py`: card parsing, weighted range expansion, blocker removal and best-five hand ranking | Range tokens and override behavior are described in README.md. |
| Equity | `pokerlab/equity.py`: seeded Monte Carlo for one to five opponents; exact weighted enumeration for a heads-up five-card board | Monte Carlo interval is a normal-approximation sampling interval, not range uncertainty. Multiway draws use independent weighted draws with joint rejection on collisions. |
| Decision analysis | `pokerlab/analysis.py`: fold/call or check/bet one-decision EV using supplied ranges and fold rate | No rake, raises, stack caps, or subsequent betting. Pre-river results are checkdown estimates. The default comparison's 45% fold rate is illustrative, not equilibrium. |
| Opponent observations | `pokerlab/models.py`: independent Beta-prior tendencies, explicit opportunity counts, street/context filtering, SQLite persistence, immutable snapshots and legacy reads | Aggregate tendencies do not identify hidden-card ranges or hand-specific action frequencies. Showdown bluff evidence is selected and biased. |
| River solving | `pokerlab/solver.py`, `restricted_solver.py`, `river_tree.py`, `cfr.py`, and `equilibrium.py`: exact compatible private-hand traversal over a configured finite action tree; vanilla CFR default and optional DCFR | Fixed-board, heads-up, supplied ranges and bounded sizes/stack/depth. Legacy fixed-bet entry remains a compatibility path. No future street or unrestricted NLHE. Node locks make the unrestricted best-response gap a profile exploitability diagnostic, not a locked-game convergence certificate. |
| Postflop solving | `pokerlab/postflop_solver.py`, `turn_solver.py`, `planned_cfr.py`, `public_cfr.py`, `matrix_free_turn.py`: finite flop/turn/river starts with exact configured chance and optional Python traversal paths | Resource caps constrain ranges and trees. Selected runouts condition and renormalize the whole joint game. Matrix-free turn solving is a separate optional API. No unrestricted sizing or multiway equilibrium. |
| Preflop and fixed-flop | `preflop_tree.py`, `preflop_solver.py`, `flop_checkdown_solver.py`, `flop_checkdown_worlds.py`: bounded blind-aware heads-up trees, selected-outcome preflop solving and isolated fixed-flop forced-checkdown integration | The existing selected-outcome preflop API rejects full-deck chance. Direct fixed-flop solving integrates all legal future cards only under forced checkdown, not later-street decisions. No multiway equilibrium. See [preflop solver](../preflop-solver.md) and [direct fixed-flop solver](../direct-flop-checkdown.md). |
| Specialized river paths | `matrix_free_river.py`, `ranked_river.py`, `cfr_plus.py` | Optional library paths have distinct action, utility and admission constraints; see [matrix-free river](../matrix-free-river.md), [ranked river](../ranked-river.md) and [CFR+ validation](../turn-river-quality.md). |
| Hand practice | `pokerlab/game.py`, `practice.py`, `decision_study.py`, and `server.py`: 2–6 seat hand mechanics, side pots, review and decision capture | Sandbox state is in memory; local observations and reports are persisted. Capture and persistence adapters are implemented in `practice.py` and `server.py`; there is no `decision_capture.py` module. Opponent cards are kept out of the human-facing decision serialization. |
| Explanations/coaching | `contracts.py`, `explanations.py`, `personalities.py`, `coach_*`, `situation_teaching.py`: structured facts, deterministic prose and local voices; optional external plan selector and bounded multi-turn coach | The external provider selects a validated reply plan; deterministic local rendering supplies the response. External AI is explicitly opt-in and allowlisted. See canonical coaching docs below. |
| HTTP/browser | `server.py` and `pokerlab/web/`: JSON endpoints, static interface and local session state | Server is loopback-only with Host/Origin checks, JSON mutation boundaries, concurrency controls and restrictive CSP. It is not an authenticated public service. |

## Validation evidence and its status

Validation statements have different evidentiary status and should not be conflated:

* **Implemented checks** are executable tests/scripts present in the repository. Their existence does not establish that they passed at this baseline or in a particular environment.
* **Historical documented runs** are claims recorded in docs or benchmark artifacts for their stated source revision, Python version, fixtures and machine. They are not a fresh run of the current source snapshot unless the record says so.
* **Audit activity** here was source and documentation inspection only. No test command was run for this audit; no pass claim is made.

The source tree includes unit tests under `tests/` and validation/benchmark scripts under `scripts/`. Relevant map:

| Concern | Executable evidence in repository | Canonical detailed reference |
| --- | --- | --- |
| Evaluator, range parsing, equity, EV, game settlement | `tests/test_core.py`; `scripts/validate_evaluator.py` | README.md, “Tests” and “Range notation” |
| River CFR formulas, exact best responses, strategy interface | `tests/test_solver_validation.py`, `tests/test_solver_variants.py`, `tests/test_configurable_solver.py`; `scripts/validate_solver.py` | `docs/solver-validation.md`, `docs/configured-river-validation.md` |
| Turn/flop physical worlds, serialized policy replay, stack/chance semantics | `tests/test_turn_solver.py`, `tests/test_postflop_solver.py`, `tests/test_public_postflop.py`, `tests/test_postflop_budget.py` | `docs/turn-river-validation.md`, `docs/postflop-validation.md`, `docs/public-batched-cfr.md` |
| Bounded preflop and fixed-flop games | `tests/test_preflop_solver.py`, `tests/test_preflop_validation.py`, `tests/test_preflop_public_batched.py`, `tests/test_preflop_vector_budget.py`, `tests/test_flop_checkdown_solver.py`, `tests/test_flop_checkdown_worlds.py` | `docs/preflop-betting.md`, `docs/preflop-solver.md`, `docs/preflop-public-batched.md`, `docs/preflop-vector-resources.md`, `docs/preflop-flop-checkdown.md`, `docs/direct-flop-checkdown.md` |
| Optional matrix-free and ranked river paths | `tests/test_matrix_free_river.py`, `tests/test_matrix_free_turn.py`, `tests/test_ranked_river.py` | `docs/matrix-free-river.md`, `docs/matrix-free-turn.md`, `docs/ranked-river.md` |
| Planned/public traversal lifecycle and agreement | `tests/test_planned_cfr.py`, `tests/test_cfr_lifetime.py`, `tests/test_public_cfr.py` | `docs/planned-traversal.md`, `docs/public-batched-cfr.md` |
| Opponent estimates, persistence, deduplication, filtering, malformed legacy data | `tests/test_opponent_model.py`, `tests/test_core.py` | `docs/architecture.md`, `docs/human-aware-strategy.md` |
| Practice replay, decision capture, hidden-information constraints | `tests/test_practice.py`, `tests/test_decision_capture.py`, `tests/test_decision_study.py` | `docs/decision-capture-v1.md`, `docs/decision-study-v1.md` |
| Explanation facts, coach grounding/visibility, voices and bounded conversation | `tests/test_explanations.py`, `tests/test_coach_grounding.py`, `tests/test_coach_analysis.py`, `tests/test_coach_teaching.py`, `tests/test_personalities.py`, `tests/test_coach_provider.py`, `tests/test_coach_conversation.py`, `tests/test_current_coach.py`, `tests/test_current_coach_conversation.py`, `tests/test_coach_request.py` | `docs/ai-coach-architecture.md`, `docs/current-coach-conversation-v1.md`, `docs/coach-analysis-v1.md` |
| HTTP/security and front-end contract | `tests/test_core.py`, `tests/test_practice.py`, `scripts/test_frontend.cjs` | README.md, “Data and local access”; `docs/architecture.md` |

Detailed docs and `benchmarks/results/` contain source-specific suite counts, parity, accuracy, runtime and allocation records. Read each with its recorded commit, interpreter, harness and fixture; a benchmark is not CI. The 331-test count in the Oct. 8–9 transfer audit applies to `65c9ba7`, not this later main snapshot. The current README, [solver progress](../solver-progress.md), and linked versioned solver reports describe capabilities merged after that historical baseline. No unfinished or unpublished worktree experiment is counted as shipped here.

## Documentation map and maintenance gaps

Use existing detailed docs as canonical, rather than copying their derivations into overview pages:

* Overall product assumptions and user-facing feature inventory: [README](../../README.md).
* Layers, contracts, EV and posterior conventions: [architecture](../architecture.md) and [human-aware strategy](../human-aware-strategy.md).
* River solver scope and independent mathematical validation: [solver validation](../solver-validation.md); configurable betting semantics: [configured river validation](../configured-river-validation.md).
* Turn and shared postflop contracts: [turn/rivers](../turn-river-validation.md), [postflop](../postflop-validation.md), [planned traversal](../planned-traversal.md), [public-batched CFR](../public-batched-cfr.md).
* External and deterministic coaching boundaries: [AI coach architecture](../ai-coach-architecture.md), [coach setup](../ai-coach-setup.md), [current conversation](../current-coach-conversation-v1.md).
* Hand capture and review: [decision capture](../decision-capture-v1.md), [decision study](../decision-study-v1.md).

The pre-existing `docs/architecture.md` remains valuable for mathematical and API detail; use [system overview](../architecture/SYSTEM_OVERVIEW.md), [solver progress](../solver-progress.md) and the preflop specifications for the current source map. Historical October 8 knowledge files remain pinned snapshots and do not supersede these current records. Validation results must retain full source SHA, Python version, command, outcome and scope; do not convert tests present or passes on another snapshot into a fresh current-baseline result.

## Full-board restricted preflop addition

The separate [preflop shove/fold API](../preflop-push-fold.md) adds full-deck final-board
chance to a bounded heads-up SB fold/shove and BB fold/call game, with at most
four compatible private pairs. Its prepared equity tables can be reused. This
does not expand the existing selected-outcome preflop API to a full-deck game,
or add limps, non-all-in raises, later-street betting or multiway equilibrium.
Read the dedicated specification for work admission and independent evidence.

A separate source-built [native preparation adapter](../native-preflop-equity.md)
retains that exact table and scope, with explicit compiler/binary provenance.
Python remains the reference/default. Read its current validation and benchmark
status before asserting performance; native-process memory is outside Python
allocation tracing.

The separate [prepared full-board preflop betting API](../preflop-full-checkdown.md)
adds finite limps, checks, configured raises and reraises using those same
immutable W/T/L tables. Future boards remain hidden and all postflop action is
forced checkdown. Its own configuration-derived tree/work admission precedes
building/training, and its independent replay rebuilds numeric rules and exact
own-hand best responses. See the dedicated record for measured status; this
does not enable full-deck later-street betting in the selected-outcome API.

## Optional turn terminal cache addition

The separate matrix-free turn API accepts explicit `terminal_cache="ranked-lru"`
for admitted fixed CFR+ calls with at most two original hands per player and
48 reachable branches. Its default remains `"none"`. Per-solve branch proxies
preserve the original outer kernel, exact root-fold paths, fallback limits and
all legacy result fields, with separate full-request cache admission and
cleanup accounting. Target mode and exceptional conditioning reject before
training. See [the cache specification and measured evidence](../turn-terminal-cache.md)
for exact parity, independent replay, concurrency/failure checks and the
fixture-specific timing/resource limits. This adds no earlier-street, UI,
general speed or RSS claim.

## Exact normalized archived river certificates

The development [river certificate audit](../river-rational-certificate.md)
reconstructs all fifteen saved extension/long-budget river policies, including
weighted raises. It records exact normalized EV/legal-response intervals,
all five target meets and ten misses, normalization ledgers and pinned inputs.
Saved-file verification freshly recomputes the mathematical rows. Its scope
is the configured numeric model and separately normalized policies; it adds
no production API, unrestricted equilibrium or raw-binary64 interval claim.

## Exact fixed-river equilibrium reference

The research [sequence-form witness](../river-sequence-equilibrium.md)
establishes exact configured-game values 25 for the polarised fixture and
-43339/2163 for weighted raises, with complete rational policies and zero
legal-response gap. Independent saved-file verification rebuilds the physical
numeric model, flow/payoff matrices and both responses. This supplies a
stronger small-game validation anchor; it changes no production solver,
earlier-street API or archived trained profile.
