# Independent turn and river validation

## Sol diagnosis and cycle 1 specification

Baseline: `46e142be8e9585005e5de70bb32bf4a76f731a1c`, dedicated
`solver/turn-river-validation-20261013` branch. The owner explicitly assigned
turn/river to this session and preflop/flop to a separate workstream.

Matrix-free turn integration currently replays serialized policies through
production world construction, betting-tree construction and best-response
evaluation. This detects representation/backend discrepancies but can miss a
shared betting-rule, utility, information-set or chance-law error. Existing
Fraction payoff tests and synthetic no-peek tests cover important components;
they do not independently replay a complete raised turn/river policy.

Implement a development-only `scripts/turn_river_validation.py` numeric replay.
Share only the established card/range grammar and the independent best-five
ranker in `scripts/preflop_validation.py`. Do not import production betting,
utility, solver, CFR, terminal kernel or diagnostic helpers. Do not change
preflop/flop code, shared kernels, public contracts, defaults, UI or Coach.

### Mathematical requirements

For each board-compatible disjoint private pair and legal selected river,
assign its original binary64 range-weight product as an exact Fraction. Normalize
once over all physical deals. The constant 1/44 cancels in a conditioned turn
game. Full deck means all 48 board-excluded public candidates, with 44 legal
rivers per compatible pair. Complete river boards have no future chance.

Rebuild actions from numeric state: original pot, each player's cumulative
commitment/cap, prior full-raise increment, raise count, reopened flag, checks,
public history and current public board. Match configured binary64 sizing and
nine-decimal amount cleanup deliberately; do not call the production builder.
Opening fractions use original pot plus cumulative commitments. Raises use
pot after calling and the minimum full increment, with stack clipping and
short-all-in reopening rules. Calls settle, unmatched excess is refunded,
river begins OOP first, and an all-in settlement has no subsequent actions.
Payoff is signed `(original_pot / 2 + matched_contribution)`, or zero on a tie.

Validate every serialized row, including off-policy rows: own hand, player,
street, exact board/history, ordered legal action names/amounts/targets/tokens,
finite nonnegative probabilities summing to one. Reject missing, duplicate,
extra, malformed or future-card-leaking rows; use explicit exceptions, not
assertions that disappear with `python -O`. Keep zero-reach worlds for auditing.

Replay profile EV and both exact legal best responses. Separate responding
private hands at the root, integrate hidden opponent hands before maximizing,
and partition public rivers only after the reveal. At OOP response nodes choose
max of integrated OOP values; IP chooses min, then negate the final expectation.
Report values, BRs, NashConv, exploitability, checked row/world counts and
private-pair/public-river probabilities. Add a comparison function with explicit
absolute tolerance, finite checks and count checks supporting both existing
materialized and matrix-free result schemas.

### Acceptance and independent review

- Replay both entry points across vanilla/DCFR/CFR+ on weighted blocker games.
- Cover river raises, unequal stacks, short all-ins, distinct river sizing,
  turn all-in continuation, selected-river posterior shifts and all 44 legal
  rivers of a single compatible pair. Scalar agreement within `1e-9` chips.
- Check the known one-bet polarised river Fraction equilibrium and zero gap
  independently. Add exhaustive pure-policy BR cross-check for a tiny game.
- Deliberately corrupt policy probabilities, metadata, actions, rows and metrics;
  the oracle must reject each corruption. Future card and hidden-hand identities
  cannot create legal decision conditioning.
- Meaningful focused tests, full repository suite, documentation validation,
  exact GitHub head/CI checks, and Sol source/mathematical review before merge.
- Record actual measurements and target misses; this is verification of a
  finite abstraction, not unrestricted Hold'em or a formal binary64 error bound.

The information-set and best-response design follows the original
[CFR paper](https://papers.nips.cc/paper_files/paper/2007/hash/08d98638c6fcd194a4b1e6992063e944-Abstract.html)
and [public-tree best-response paper](https://johanson.ca/publications/poker/2011-ijcai-abr/2011-ijcai-abr.pdf),
reviewed October 13, 2026. No third-party solver implementation is incorporated.

## Prioritized backlog

1. Independently replay complete configured turn/river policies and diagnostics.
2. Investigate cancellation, probability-support loss and convergence labels
   under adversarial range weights, after an independent replay is available.
3. Measure equal-wall-time accuracy on broader turn/river ranges; investigate
   turn training bottlenecks only after values/BRs have independent validation.
4. Consider additional sizing coverage or averaging schedules with fixed
   quality/cost criteria; retain default/reference behavior and existing caps.

## Sol cycle 2 specification: nonnegative diagnostic gains

An injected accepted-roundoff reproduction at the baseline exposes an internal
diagnostic inconsistency in both isolated matrix-free entry points. At pot 100,
an evaluator returning `(value=0, BR0=1e-9, BR1=-1e-9)` passes the existing
`1e-10 * scale` legal-BR guard. Each result reports OOP gain `1e-9` and IP gain
zero, but sums the signed gains first and reports NashConv/exploitability zero.
A requested zero target therefore stops after ten iterations as `target-reached`.
This is a fault-injected tolerated-roundoff case, not a measured natural failure.

In an exact zero-sum game both unilateral deviation gains are nonnegative.
If small negative floating-point BR differences are accepted under the existing
guard, clamp each unilateral gain separately before summing. Keep materially
invalid/nonfinite diagnostics rejected, preserve all training, probability,
action, admission and default/reference behavior, and edit only
`matrix_free_turn.py`, `matrix_free_river.py` plus their tests. Do not change
shared postflop/preflop/flop diagnostics in this isolated cycle; record that
shared follow-up explicitly for its owners.

Require fixed and target modes to satisfy `NashConv = OOP_gain + IP_gain` and
`exploitability = NashConv / 2`. Test both signs of tolerated negative error,
both adapters, a true nonnegative profile, and material/nonfinite rejection.
A positive gain must prevent a zero target being certified. Re-run independent
full-policy replay and normal strategies/metrics against baseline; disclose any
roundoff-level metric changes rather than inventing bitwise identity. This
clamping consistency rule is not a rigorous floating-point error bound.

## Development record

Sol inspected current main, active worktrees/PRs, prior Sol/Luna instructions,
matrix-free implementations and existing component/integration tests. Luna is
assigned bounded implementation and adversarial validation. Acceptance and
executed results will be recorded after review; this specification is a plan.
