# Configurable river equilibrium: scope and validation

## Vocabulary (do not conflate)

1. **Equilibrium strategy** – produced by `pokerlab/solver.py` for one exact
   configured river tree; exposed through `pokerlab/equilibrium.py`.
2. **Heuristic strategy** – hand-designed behaviour used outside solved states.
   It is not solved.
3. **Opponent model** – beliefs about how a player behaves (`models.py`). The
   "balanced" archetype is a prior-opportunity profile, not an equilibrium.
4. **Deviation model** – a future layer describing how an opponent differs from
   equilibrium. It is not implemented.
5. **Best response** – a strategy optimized against a fixed opponent strategy.

Target pipeline: equilibrium → deviations → modeled opponent → best response.

## The game actually solved

The solver handles heads-up no-limit betting on one fixed five-card river board,
with two weighted private ranges over compatible hole-card pairs (exact card
removal). It uses a finite, configured action abstraction, no rake, and one
effective stack for both players. All compatible deals are enumerated.

The result is **an approximate equilibrium of the configured river action
abstraction**, measured by its best-response gap. It is not unrestricted river
GTO, does not solve earlier streets, and makes no profitability claim.

## Configuration

`pokerlab.river_config.RiverConfig` is immutable and serializable with
`to_dict()`; pass it (or that dictionary) as `config` to `solve()` or
`solve_equilibrium()`. Fractions are positive pot multipliers, not amounts
interpolated between a minimum and an all-in. The normalized configuration is
included in solver results.

```python
RiverConfig(
    pot=100,
    effective_stack=500,
    bet_sizes=(0.33, 0.75, 1.0),
    raise_sizes=(0.5, 0.75),
    max_raises=1,
    include_all_in=True,
)
```

- `pot`: chips already in the pot at the start of the river.
- `effective_stack`: maximum total commitment per player, including this
  street's bets. A scalar applies to both players; a two-item `(OOP, IP)` pair
  configures unequal stack caps.
- `bet_sizes`: first-bet pot fractions. Each configured fraction creates one
  action unless sizing and stack normalization make its chip action duplicate.
- `raise_sizes`: pot-after-call fractions for raises.
- `max_raises`: maximum number of raise actions after a first bet. A short
  all-in counts toward this depth; the supported range is 0–8.
- `include_all_in`: add a shove action where legal. A configured size that
  exceeds the stack is still clipped to an all-in even when this is false.

At least one first-bet size is required, and each size list supports at most
eight entries. Sizes are sorted, deduplicated, and serialized as ordinary
numeric fractions; public tree expansion has a 10,000 node cap and solving has
a 30-million deal-node-iteration work cap.

## Exact sizing and betting semantics

First bets are `fraction × current pot`, where current pot includes any
commitments already made on this street. The result is capped at the player's
effective stack. The configured opening wager establishes the previous full
raise increment for subsequent minimum-raise checks; this river abstraction
does not configure blinds or a separate minimum opening bet.

Facing a wager:

1. The call amount is the difference between the opponent's total commitment
   and the acting player's total commitment.
2. The pot after calling is the starting pot plus both current commitments plus
   the call amount.
3. A configured raise increment is `raise fraction × pot after calling`.
4. The raise-to total is the acting player's existing commitment + call amount
   + that increment.
5. The minimum full raise-to is the opponent's current total commitment plus
   the previous full raise increment. A sized action below this is normalized
   up to that minimum if the stack permits.
6. The total is capped at the effective stack. A stack-capped all-in below the
   minimum full raise remains a legal short all-in; other under-minimum raises
   are excluded. Duplicate resulting chip totals are represented once.

The solver tracks whether a raise is full. A short all-in raise does not reopen
raising. Full raises update the minimum increment. Once an opponent is all-in,
the tree has no further raise branch; there is no unmatched side-pot action in
this heads-up abstraction.

### Worked examples (pot starts at 100)

- **Normal first bet:** with `bet_sizes=(0.75,)`, the bet is `0.75 × 100 = 75`,
  so the raise-to/total commitment is 75.
- **Normal raise:** after that 75 bet, the caller faces 75. The pot after the
  call is `100 + 75 + 75 = 250`. A 75%-pot raise adds `0.75 × 250 = 187.5`;
  the raise-to total is `0 + 75 + 187.5 = 262.5`. The raise increment is 187.5.
- **Short-stack all-in:** with an effective stack of 120, the first player bets
  75 and the opponent shoves to 120. The raise increment is `120 - 75 = 45`,
  less than the previous full increment of 75. It is a legal short all-in,
  does not reopen raising, and the first bettor may only fold or call.
- **Raise clipped to all-in:** with an effective stack of 200 in the normal
  raise example, the configured raise-to 262.5 is clipped to 200. Its increment
  is `200 - 75 = 125`, at least the 75 minimum, so it is a full all-in raise.
- **Uncalled excess:** with `effective_stack=(500, 120)`, OOP can bet 300 into
  the 100 pot and IP can only call all-in for 120. At showdown, only 120 from
  each player is matched; OOP's uncalled excess 180 is returned. If OOP wins,
  the result is `100/2 + 120 = 170` chips relative to an even split of the
  starting pot.

These arithmetic examples may produce fractional chips: this is an analysis
abstraction, not a chip-denomination or rounding model.

## CFR, information sets, and measurement

The tree uses vanilla full-traversal CFR, simultaneous regret-matching updates,
and reach-weighted uniform strategy averaging (no CFR+/linear weighting).
Information sets are keyed by player, private hand, and public action history.
Bet and raise history keys include normalized chip totals (for example,
`bet@33` versus `bet@100`), so distinct sizes do not share an information set.
Irrelevant internal CFR data is not part of the public strategy interface.

`Action.amount` is the number of chips added now; `Action.raise_to` is the
player's total commitment after the action. `Action.history_key` is the
canonical token to append to `InfoSet.history` when querying a later node.
`legal_actions()` and `strategy_at()` expose only legal explicit actions and a
normalized distribution.

Terminal utilities are zero-sum and relative to half the starting pot. At
showdown or fold, only matched commitments remain in the pot; uncalled excess
is returned. Best responses aggregate compatible opponent hands before
maximizing at a private-hand information set, avoiding hidden-card peeking.
`nash_conv = BR_OOP + BR_IP` when each BR is measured in that player's own
utility; `exploitability = nash_conv / 2`. Values are in chips.

Legacy `solve(board, oop_range, ip_range, pot, bet, iterations)` calls map to a
single configured bet size with no raises and retain their prior strategy row
fields. Existing IP node locks are supported only on that one-size/no-raise
tree; with locks, the unrestricted gap is not a convergence certificate for
the locked game. Strategies at unreachable information sets are arbitrary.
Convergence is O(1/√T) in iterations, not monotone at every checkpoint.

## Validation

```sh
python -m unittest tests.test_solver_validation -v
python -m unittest tests.test_configurable_solver -v
python -m scripts.validate_solver [iterations ...]
```

The tests include independent hand evaluation and pure-strategy best-response
checks for the legacy game, Kuhn poker, a known bluff-catcher equilibrium,
configuration serialization, exact sizing and raise rules, short all-ins,
effective-stack and uncalled-chip settlement, duplicate normalization,
information-set separation, strategy normalization, multi-size best responses,
NashConv, and convergence.

The validation script compares one bet/no raises, several bets/no raises, and
several bets plus one raise level. It reports the configuration, tree size,
information-set count, runtime, iteration count, NashConv/exploitability, and
both best-response values. Tree size grows with configured actions and raises;
the explicit node/work caps prevent accidental unrestricted tree expansion.
