# Equilibrium baseline: scope and validation

## Vocabulary (do not conflate)

1. **Equilibrium strategy** – produced by `pokerlab/solver.py` for the exact
   restricted game below; exposed through `pokerlab/equilibrium.py`.
2. **Heuristic strategy** – hand-designed behaviour used outside solved states
   (e.g. the illustrative comparison baselines in `exploit.py`). Not solved.
3. **Opponent model** – beliefs about how a player behaves (`models.py`).
   The "balanced" archetype is a prior-opportunity profile, **not** GTO or an
   equilibrium.
4. **Deviation model** – future layer describing how an opponent differs from
   equilibrium. It should wrap `EquilibriumStrategy`; not implemented.
5. **Best response** – a strategy optimised against a fixed opponent strategy.

Target pipeline: equilibrium → deviations → modeled opponent → best response.

## The game actually solved

Heads-up, river only, fixed five-card board, two weighted private ranges over
all compatible hole-card pairs (exact card removal). Out-of-position (OOP)
checks or bets one fixed size; after a check, in-position (IP) checks or bets
that size; a bet is answered by fold or call. No raises, no other bet sizes,
no rake, no stack limits (bet is always affordable), pot fixed at the input.
Utilities are zero-sum chips relative to half the starting pot: a fold is
±pot/2, a showdown with no bet is ±pot/2 (0 on ties), a called bet is
±(pot/2 + bet). Information sets are keyed by player, private hand, and public history. Each OOP
hand has two decision nodes (root and facing a bet after checking); each IP hand
also has two (after an OOP check and facing an OOP bet). Variant: vanilla full-traversal CFR with regret matching, simultaneous
updates and reach-weighted uniform averaging by default. The opt-in
`algorithm="dcfr"` uses DCFR(1.5,0,2), simultaneous updates, and own-reach
quadratic strategy averaging. It solves the same game and reports the same
exact information-set best-response diagnostics.

## Exploitability

Best responses are computed against the *average* strategies at the information
set level (opponent hands are aggregated before the max, so hidden cards are not
peeked). `nash_conv` = (BR_OOP − V) + (BR_IP + V); `exploitability` = nash_conv/2.
Values are in chips.

## What can and cannot be claimed

Can: an approximate equilibrium (to the reported NashConv) of this restricted
game. Cannot: unrestricted no-limit Hold'em GTO, solutions for multiple sizes,
raises, earlier streets, or any profitability claim. Locked-node solves are not
equilibria. Strategies at unreachable information sets are arbitrary.
Convergence is O(1/√T) in iterations, not monotone per checkpoint.

## Interface

`solve_equilibrium(...)` returns an `EquilibriumStrategy`;
`strategy_at(InfoSet(player, hand, history))` returns `((Action, probability), ...)`
over legal actions only; `legal_actions(infoset)` lists them with explicit chip
sizing. Histories: `()`, `("check",)`, `("bet",)`, `("check", "bet")`.

## Validation

`python -m unittest tests.test_solver_validation -v` (independent evaluator,
brute-force pure-strategy best responses, Kuhn poker reference CFR, a
bluff-catcher game with known equilibrium, convergence) and
`python -m scripts.validate_solver [iterations ...]` for diagnostics.

## Algorithm and traversal improvement (restricted-river-v2)

The default remains vanilla CFR. `solve(..., algorithm="dcfr")` and
`solve_equilibrium(..., algorithm="dcfr")` select an independently implemented
variant from [Brown and Sandholm (2019)](https://arxiv.org/abs/1809.04040).
For iteration t, first add the complete simultaneous regret delta, then
multiply positive totals by t^1.5/(t^1.5+1) and negative totals by 1/2.
Do not clip negative regret or discount per deal. Average strategies use t^2
times the player's own reach. Exact best responses evaluate that average.
DCFR can be worse at a given checkpoint; it does not change the default or
carry a universal performance or convergence-speed claim.

The binary-action traversal derives regrets directly from each node's two
action values. Constant per-hand chance marginals allow average accumulation
once per hand rather than once per compatible deal. Only OOP's response node
has a previous own action (checking). An independent recursive traversal
checks both algorithms on weighted ranges, overlapping private cards, ties,
and a polarized game; exhaustive pure-strategy best responses independently
verify the reported gap. Existing utility and card-evaluator logic is reused
without changes.

Run `python -m unittest tests.test_solver_variants tests.test_solver_validation -v`
and `python -m scripts.benchmark_solver --algorithm vanilla` (or `dcfr`).
Versioned synthetic scenarios live in `benchmarks/solver-v1.json`. Timings are
median wall times of independent calls; traced Python peak memory is measured
in a separate untimed call and is not process RSS. The benchmark records exact
gap, ranges, compatible deals, information sets, algorithm and revision
provenance. See `docs/solver-progress.md` for measured results and scope.
