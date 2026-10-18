# Exact weighted preflop equilibrium witness

This research certifies one finite heads-up preflop betting game with hidden
full-board outcomes and forced later checkdown. It strengthens the independent
accuracy targets for [prepared preflop betting](preflop-full-checkdown.md).
Production solving, defaults, selected-outcome APIs, native code, later-street
research, coaching and frontend behavior are unchanged.

## Frozen game and physical counts

The [predeclared specification](../benchmarks/preflop-weighted-sequence-v1.json)
fixes SB range `AsAd:1,QsQd:0.5`, BB range `AsKh:0.25,KsKd:1`, blinds 0.5/1,
starting stacks 4/3, pot-fraction raise sizes 0.5 and 1, one raise allowance,
and explicit all-ins. A limp preserves BB's check/raise option. BB calls a
4-chip shove with its remaining stack to 3; SB's unmatched chip is refunded.
No further betting follows a closed preflop line.

| SB hand | BB hand | Exact conditioned prior | Wins | Ties | Losses |
| --- | --- | --- | --- | --- | --- |
| AdAs | KdKs | 8/13 | 1,410,336 | 9,308 | 292,660 |
| QdQs | AsKh | 1/13 | 968,267 | 7,226 | 736,811 |
| QdQs | KdKs | 4/13 | 292,846 | 9,336 | 1,410,122 |

The fourth candidate pair shares As and is excluded. Compatible raw joint mass
is 13/8; conditioning occurs globally, before decisions. Each pair represents
all 1,712,304 five-card boards, or 5,136,912 physical boards overall. Three
previously published independent count artifacts are checked in full against
canonical SHA-256, normalized Git blob identity and exact W/T/L totals. They
are reused without ranking or enumeration. Structural integrity alone would
not establish the physical correctness of arbitrary caller-supplied counts.

A fold transfers the loser's matched commitment. A showdown transfers matched
commitment times the exact conditional mean `(wins-losses)/1712304`. This linear
integration keeps opponent hands hidden and never reveals W/T/L to a decision.
Amounts in this fixture are exact dyadic values; no general exact-decimal
identity across arbitrary configured betting quantization is asserted.

## Candidate and independent proof

The [candidate builder](../scripts/preflop_sequence_equilibrium.py) uses the
existing independent numeric preflop tree and project-owned rational simplex.
It represents every policy by actor, own hand and public history. The model has
19 public states (7 decisions, 6 folds, 6 showdowns), 6/8 information sets and
19 sequences per player. It checks this fixed census before allocating its
19-by-19 payoff matrix and checks LP shapes before constructing tableaux.

The lower LP has 26 rows / 82 columns / 2,241 cells; the upper has 28 / 80 /
2,349. Existing exact-solver limits remain 96 rows, 256 columns, 25,000 cells,
512 pivots, 10 million logical cell updates and 4,096-bit intermediate fractions.
These limits apply per LP and no cap is increased. The candidate's own status remains feasibility evidence;
its self-checksum or zero-gap assertion is not treated as a proof by itself.

The [independent verifier](../scripts/verify_preflop_sequence.py) reconstructs
the frozen legal tree, private blocker conditioning, flows and payoff matrix
without candidate, LP, production tree/trainer/evaluation or best-response
imports. It checks both original nonnegative realization plans, flow equations,
dual inequalities, complementary slackness and matching lower/upper bounds.
It also independently computes exact recursive profile EV and legal own-hand
best responses, keeping hidden opponent hands aggregated before each choice.
A [separate bounded terminal-history oracle](../scripts/preflop_sequence_pure_response.py)
evaluates every legal pure response for each own hand. These checks are required
in addition to LP optimality.

The saved preliminary candidate yields the exact SB net-transfer value
`100107990869/130471452826`. Both dual bounds, recursive SB profile value and
the SB value under each
player's legal response match; exact NashConv is zero. In each player's own
utility perspective, SB's value and response are positive V and BB's are negative V.

A separate illegal-information control allows a responder to choose a different
pure policy for each opponent holding. It increases SB's value to
`57581194636/65235726413` and decreases SB's value under BB's response to
`69522780619/391414358478`. These strict changes confirm that per-pair
maximization would answer a different game; neither value is a legal response.

This statement applies only to the frozen game. It does not certify unrestricted
preflop,
later-street betting, multiway equilibrium or finite-iteration CFR accuracy.

## Reproduction and publication status

The [raw regression witness](../tests/fixtures/preflop-weighted-sequence-candidate-v1.json)
is data for positive and adversarial verifier tests. It is explicitly a candidate,
not the clean-source publication report. The
[orchestrator](../scripts/certify_preflop_sequence.py) requires clean committed
source for a formal run, forbids production/ranking entry points, records full
source identities, reconstructs verification after JSON serialization, and
reopens the actual saved artifact for another fresh verification. Output stays
outside the checkout during measurement; existing observations are preserved.

```text
python -m scripts.certify_preflop_sequence --output ../preflop-weighted-sequence-v1-report.json
```

A feasibility run must explicitly add `--feasibility`. Its dirty-source identity
is retained and its phase cannot establish formal publication. All 19 focused
candidate, verifier, pure-response and publication tests pass.
The complete feasibility pipeline passes with stable source snapshots and zero
forbidden production/ranking calls, including fresh saved-file verification.
The candidate uses 41/61 pivots, 101,005/154,789 logical cell updates and a maximum
92-bit intermediate Fraction, within every unchanged cap. Formal saved artifact
generation, final CI and GitHub merge are pending at this source stage.

The method follows the published sequence-form representation and linear
constraints described by [von Stengel (1996)](https://doi.org/10.1006/game.1996.0050)
and [Koller, Megiddo and von Stengel (1996)](https://ai.stanford.edu/~koller/Papers/Koller%2Bal%3AGEB96.pdf).
Only mathematical ideas and existing project-owned numerical code are reused;
no third-party implementation, dependency or licensed solver output is added.
No license, visibility or distribution setting changes follow.
