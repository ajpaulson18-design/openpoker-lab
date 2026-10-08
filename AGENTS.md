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
- `pokerlab/turn_solver.py` adds finite heads-up turn-to-river games through the shared `cfr.py` kernel and `river_tree.py` betting builder. Preserve physical joint hand/runout weights, perfect recall, hidden future cards, cumulative stack accounting and `postflop-strategy-v1`. Selected runouts condition the entire joint game; they are not an unconditional full-deck approximation. Flop/preflop and unrestricted NLHE remain future work.
- `pokerlab/models.py` persists local observations. Preserve explicit opportunity denominators, idempotent observation IDs, street/context filtering, transactions, and legacy-data error handling.
- `pokerlab/practice.py` must store every live opponent range and enough decision-time state to replay a decision exactly.
- Explanation and personality layers may change prose, never recommendations, EVs, frequencies, confidence, analysis IDs, or protected facts.
- The server remains loopback-only with Host/Origin validation, JSON mutation boundaries, concurrency limits, and a restrictive CSP unless a deliberate architecture change is approved.
- Never commit `data/`, SQLite databases, credentials, personal opponent records, proprietary solver output, or copied commercial interfaces.
- Prefer synthetic examples. Avoid silently changing poker rules, probability meanings, model assumptions, or public API shapes.

## Completion standard

Keep changes narrow and reviewable. For defects and model changes, add a reproducible case and externally meaningful regression test or measurable benchmark. Run the smallest relevant tests while working and the full applicable suite before completion. Record commands actually run and limitations. Surface ambiguous poker rules, statistical assumptions, security decisions, and architecture changes instead of guessing.

Codex is the primary builder and senior engineer for features, architecture, difficult debugging, large refactors, and cross-repository decisions. Copilot specialists support testing, automated remediation, documentation, and independent review; they should not compete for major implementation work.
