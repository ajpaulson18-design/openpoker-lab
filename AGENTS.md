# Repository agent instructions

## Project

OpenPoker Lab is a standard-library Python research application with a plain JavaScript browser UI. It combines poker simulation, persistent opponent observations, transparent EV analysis, deterministic explanations, practice/review flows, and a deliberately restricted river CFR solver. It does not solve unrestricted no-limit Hold'em and makes no profitability claims.

## Setup and validation

Use Python 3.11 or newer. There are no runtime dependencies.

- Run the application with `python -m pokerlab.server`.
- Run the full unit suite with `python -m unittest discover -s tests -v`.
- Run the exhaustive evaluator validation with `python -m scripts.validate_evaluator` when card-evaluation logic changes; it is intentionally slower.
- CI runs the unit suite on Python 3.11, 3.12, and 3.13.

## Architecture and constraints

- Keep calculation, immutable contracts, opponent-model snapshots, explanations, and presentation voices separate.
- `pokerlab/contracts.py` defines shared structured boundaries. Preserve deterministic serialization and provenance.
- `pokerlab/solver.py` dispatches the fixed-board river solver: the optimized fixed-bet compatibility kernel in `restricted_solver.py`, or the finite configured bet/raise/stack tree. Both expose `river-strategy-v1` and vanilla CFR or optional DCFR. Never present either as unrestricted Hold'em GTO or earlier-street solving.
- `pokerlab/postflop_solver.py` handles finite heads-up flop, turn and river starts through shared `cfr.py`/`planned_cfr.py` kernels and the `river_tree.py` betting builder. `turn_solver.py` preserves its established API as a thin facade. Preserve physical joint hand/runout weights, ordered future reveals, perfect recall, hidden future cards, cumulative stack accounting and `postflop-strategy-v1`. Selected runouts condition the entire joint game; they are not an unconditional full-deck approximation. Full-deck flop coverage is limited by strict resource guards; preflop, multiway equilibrium and unrestricted NLHE remain future work.
- `planned_cfr.py` is an optional static-world Python traversal backend; recursive remains the default/reference. Preserve callback/lock semantics, deterministic constant terminal utilities, local plan lifetime and the 250,000-operation guard. Measure full-call runtime and memory independently; do not describe this as native compilation or chance sampling.
- `public_cfr.py` is an optional exact public-tree/private-hand-vector trainer selected by postflop `traversal="public-batched"`. It specializes fold/showdown payoffs and has no lock or arbitrary-utility callback API. Preserve joint physical edge weights, opponent reach in regrets, own reach in averaging, simultaneous CFR/DCFR updates, hidden-card histories, the 250,000 prefix-edge cap, and prompt recursive-closure release. Keep recursive as the reference and measure complete calls including exact best responses.
- `scripts/cfr_quality.py` validates the three production training kernels on a known Kuhn game using independent terminal-history payoffs and exhaustive pure-policy best responses. Production evaluation/BR are candidates, never the oracle. Preserve rational anchors, visible-information policies and quantitative finite-iteration gates; a Kuhn result does not certify Hold'em equilibrium accuracy.
- `pokerlab/models.py` persists local observations. Preserve explicit opportunity denominators, idempotent observation IDs, street/context filtering, transactions, and legacy-data error handling.
- `pokerlab/practice.py` must store every live opponent range and enough decision-time state to replay a decision exactly.
- Explanation and personality layers may change prose, never recommendations, EVs, frequencies, confidence, analysis IDs, or protected facts.
- The server remains loopback-only with Host/Origin validation, JSON mutation boundaries, concurrency limits, and a restrictive CSP unless a deliberate architecture change is approved.
- Never commit `data/`, SQLite databases, credentials, personal opponent records, proprietary solver output, or copied commercial interfaces.
- Prefer synthetic examples. Avoid silently changing poker rules, probability meanings, model assumptions, or public API shapes.

## Completion standard

Keep changes narrow and reviewable. For defects and model changes, add a reproducible case and externally meaningful regression test or measurable benchmark. Run the smallest relevant tests while working and the full applicable suite before completion. Record commands actually run and limitations. Surface ambiguous poker rules, statistical assumptions, security decisions, and architecture changes instead of guessing.

Codex is the primary builder and senior engineer for features, architecture, difficult debugging, large refactors, and cross-repository decisions. Copilot specialists support testing, automated remediation, documentation, and independent review; they should not compete for major implementation work.
