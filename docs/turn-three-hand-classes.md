# Exact river classes for the fixed three-hand TURN game

This is an independent research audit of the [three-hand physical game](turn-three-hand-physical-audit.md). It checks when a policy on seven public river classes can represent that same 396-world game. It does not train a policy or change a production API.

The [auditor](../scripts/turn_three_hand_classes.py) exposes `build_model`, `validate_model`, `project_policy`, `lift_policy`, and `audit_policy`. Projection accepts original finite binary64 probability fields from a complete fixed-fixture physical policy. The compact strategy is an internal row object; it is not a serialized selected-runout solver result. Lifting constructs fresh physical metadata and carries no old training provenance or diagnostic claims into a new policy.

The board remains `Js8d4c2h`, with OOP `AsAh:0.5,KsKh:1,QsQh:0.75` and IP `AcAd:1,KcKd:0.75,QcQd:0.5`. Pot, stack, and both streets' actions remain the fixed physical reference's configuration. In AA/KK/QQ order, the exact private-pair mass matrix is `[[8,6,4],[16,12,8],[12,9,6]]/81`. Each compatible pair has 44 legal physical rivers, each with mass equal to that pair's mass divided by 44.

## Class law

A class uses one global public-card mapping, shared by both players and every private hand. Its signature retains the complete supported private-pair identities, original joint mass per card, and showdown sign. Cards may share a class only when these signatures and their complete mapped public betting subtrees agree.

| Representative | Physical members | Multiplicity | Compatible pairs | Total joint mass |
| --- | --- | ---: | ---: | ---: |
| `2c` | All 36 remaining cards outside A/K/Q | 36 | 9 | 9/11 |
| `Qc` | `Qc,Qd` | 2 | 6 | 7/198 |
| `Qh` | `Qh,Qs` | 2 | 6 | 1/33 |
| `Kc` | `Kc,Kd` | 2 | 6 | 1/33 |
| `Kh` | `Kh,Ks` | 2 | 6 | 5/198 |
| `Ac` | `Ac,Ad` | 2 | 6 | 5/198 |
| `Ah` | `Ah,As` | 2 | 6 | 7/198 |

Each pair supports the neutral class and four two-card classes, giving 45 pair-class worlds. Their weights are the exact sums of original physical weights, including multiplicity. The total remains one, and every original private-pair marginal is retained. Selecting seven physical runouts and conditioning on that subset would produce a different game.

At all five chance nodes, the audit compares every physical card's complete mapped subtree, including actors, public histories and boards, ordered actions and amounts, raise targets, terminal kinds, winners, and contributions. The reduced public tree must equal the class-collapsed physical tree.

| Quantity | Physical model | Class model |
| --- | ---: | ---: |
| Worlds | 396 | 45 |
| Public nodes | 3,039 | 456 |
| Decisions | 1,254 | 188 |
| Terminals | 1,780 | 263 |
| Chance nodes / edges | 5 / 240 | 5 / 35 |
| Decision edges | 2,798 | 420 |
| Depth | 9 | 9 |
| Own-hand policy rows | 3,606 | 486 |
| Action slots | 8,046 | 1,086 |

## Policy and response boundary

Projection requires the complete legal physical policy. Every probability vector merged into a class row must agree; the auditor rejects card-specific differences instead of averaging them. Lifting restores all physical boards and `river@card` histories and preserves every own-hand identity and legal action. The resulting physical strategy has all 3,606 rows and 8,046 action slots.

For a class-constant opponent policy, observing a member card gives the same hidden-hand posterior and payoff/action problem as observing another member of its class. A legal responder can therefore attain the same conditional optimum with a class-constant response. The audit aggregates hidden opponent hands before choosing an action and sums future classes before any TURN choice. It compares full profile value and both unrestricted physical-game best responses, rather than only showdown totals or a restricted class-response gap.

The unchanged generic exact helper evaluates the validated class model, while the separate fixed physical exact oracle evaluates the lifted full policy. All eight rational metrics must agree exactly. Original binary64 probabilities are converted to Fractions and explicitly normalized by their exact row sums in both evaluations. Generic work/depth/bit limits remain 100,000/64/65,536; the physical oracle retains its separate existing limits.

The check/call control has exact OOP value `-9500/891`, OOP response `6925/891`, IP response `57550/891`, and NashConv `64475/891`. Uniform and nontrivial mixed controls exercise full legal action support. A single IP `KcKd` deviation after `check,check,river@2c,check` is a complete valid physical policy but fails class-constant projection.

The [saved T750/D250 experiment](turn-three-hand-direct-tail-experiment.md) also happens to be exactly class-constant. Auditing its projection must retain its original positive NashConv `0.010695489887132394` and its miss of the unchanged `0.001` target. The old report, raw policy, source fingerprints, and physical audit remain unchanged.

This fixed-game equivalence adds no convergence, exact equilibrium-value, runtime, memory, or unrestricted Hold'em claim. Any future compact trainer needs its own reviewed complete resource admission and a separate frozen quality experiment.

## Verification

The [focused tests](../tests/test_turn_three_hand_classes.py) check literal class masses and counts, both generic exact traversal modes, the full physical controls, independently constructed mixed class policies, and the pinned saved target miss. They also check that projection/lifting leave inputs unchanged, that corrupt class laws and legal metadata reject, and that work/bit or numeric discrepancies cannot pass silently. Production trainer, tree and value helpers are disabled during saved-policy replay.

```powershell
python -B -m unittest discover -s tests -p test_turn_three_hand_classes.py -v
python -B -O -m unittest discover -s tests -p test_turn_three_hand_classes.py -v
python -B -m scripts.validate_docs
```
