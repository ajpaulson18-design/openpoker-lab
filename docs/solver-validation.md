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
±(pot/2 + bet). Information sets: (player, private hand, public history), four
decision nodes per hand: OOP root, IP after check, IP facing bet, OOP facing a
check-bet. Variant: vanilla full-traversal CFR with regret matching, simultaneous
updates and reach-weighted uniform averaging (no CFR+/linear weighting).

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
