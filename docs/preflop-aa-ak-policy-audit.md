# Blocker-sensitive preflop policy audit

The separate [exact policy checker](../scripts/preflop_aa_ak_pure_response.py)
is staged for SB AA/AK-suited/AK-offsuit at unit weights versus BB KK. It uses
22 SB hands, six BB hands and 84 collision-free private pairs with exact global
prior 1/84. Physical counts must authenticate from the six saved source classes.
The [transport publication](preflop-aa-ak-transport.md) is a separate milestone;
these tools do not claim a newly transported table or a real-source strategy.

The betting game is fixed: blinds 0.5/1, stacks 3/3, pot-fraction sizes 0.5 and
1, at most two raises, and all-ins. Every closed nonfolded line forces hidden
full-board checkdown. Fourteen literal terminal paths and their net transfer
coefficients come from the project's independent physical numeric rules, not
the production betting tree. No later-street decision is present.

Every supplied policy must include all 112 legal own-hand/public-history rows,
including off-path rows. Exact action menus and canonical rational-string
probabilities are checked before source authentication. Opponent-hand/future
fields, duplicate or omitted rows, boolean player aliases, unbounded or
noncanonical rational tokens, and non-normalized probabilities reject.

The reference enumerates every complete pure policy for each responding own
hand: 1,056 SB choices and 216 BB choices, or 1,272 total. Each choice's value
first sums all compatible hidden opponent hands under their exact joint priors.
Only then is the best legal choice selected. Suit-dependent responding policies
remain legal; the checker does not assume a type-symmetric policy is optimal.
It returns the exact profile, response values/gains, NashConv and complete
per-hand response witnesses. A nonzero gap or an incorrect claimed value remains
a recorded failure of the exact mutual-response target, not a source/parser
exception. No finite-iteration or unrestricted NLHE guarantee follows.

## Candidate terminal-partition calculation

The [optional response calculation](../scripts/preflop_aa_ak_response_partition.py)
is a separate research helper, with the exhaustive literal scan retained as
the reference. Given an already validated policy and physical game, it first
sums hidden-opponent reach-weighted utility for each own hand and terminal
history. A complete own-hand pure policy then includes a terminal exactly when
all of its own prescribed public actions match. This replaces repeated pair
scans across pure choices with one terminal-coefficient accumulation per pair.
It preserves response utility sign, all off-path choices, exact fractions and
first-policy tie handling. It never maximizes separately per opponent hand.

The helper admits at most 84 pairs and 22/6 responding hands. It uses the fixed
menus/terminal set and rejects intermediate exact values above 65,536 bits.
The bit check follows each exact arithmetic operation; it is not a preallocation
byte bound for that operation. These logical caps and checks establish no elapsed-time or allocated
memory guarantee. It performs no source authentication and is not connected
to a production solver or used as the independent policy authority.

Synthetic controls compare both exact response values and complete selected
policies against the exhaustive scan for weighted, mixed and zero-reach cases.
An illegal clairvoyant control gives strictly more value when an action can
condition on the hidden opponent, demonstrating the information boundary.
No real-source policy, LP, count, training or performance observation is claimed
by this staged implementation. A later measurement must pin its clean source,
disclose whether it covers only the response subroutine or a whole call, retain
all samples and measure allocations separately from untraced timing.

All code reuses or independently implements the project's original exact
finite-game arithmetic and card-combination methods. No third-party source or
dependency is added. Earlier measured sources, shared solver defaults, turn and
river work, AI Coach and explanations remain unchanged.
