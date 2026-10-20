# Public diagnostics for flop-start games

`solve_postflop(..., diagnostics="public-batched")` now accepts flop starts,
using the existing public-tree/private-hand-vector evaluator. It computes profile
value and both legal own-hand best responses over the supplied configured
physical game. Recursive, planned vanilla/DCFR and public-batched training retain
their existing arithmetic. Default recursive diagnostics and all turn/river
payloads remain unchanged. Flop target stopping remains unsupported.

The evaluator traverses both turn and river chance prefixes. Terminal edges
already include joint physical mass and mass-times-showdown-sign, so chance
children are summed before maximizing at a responder decision. Policies are keyed
by player, own hand and visible public history. A blocked hand with zero prefix
marginal can use a uniform placeholder that contributes no value; missing policy
at a positive-marginal information set rejects. Responders cannot use an opponent's
private cards or an unrevealed future card to select a present action.

## Admission and provenance

New flop requests reserve the same 250,000 prefix/private-pair edge cap before
tree construction and training, after physical-world enumeration. This guard
checks each distinct coordinate before inserting it and does not rank again.
Initial ranking precedes this guard. The evaluator retains its own prefix guard.
Existing candidate/world/tree/iteration/planned-operation and three-pass CFR+
charges remain. Default and later-street admission remain unchanged.

An explicit public diagnostic result identifies `diagnostics_backend` as
`public-batched-python` and records `diagnostics_prefix_hand_edges` and
`diagnostics_prefix_edge_limit` for the new flop option. Training backend metadata
retains its existing meaning. This option does not certify early stopping, change
the configured game, or establish end-to-end speed, memory/RSS bounds or improved
convergence.

## Independent validation

[Integration controls](../tests/test_flop_public_diagnostics.py) compare all eight
profile/value/response/gain/NashConv/exploitability scalars against the independent
literal-world/numeric-action validator at tolerance 1e-10. The full-deck fixture
has 5,940 physical worlds and 6,078 prefix/private-pair edges. It covers recursive
and public-batched CFR+ training at delays zero and two. Weighted selected games
exercise blockers, raised/refunded amounts, asymmetric stacks, street-specific
sizing and all-in settlement across seven algorithm/trainer/delay combinations.
Changing only diagnostics preserves the exact serialized strategy list. Production
ranking, tree, training, value and response helpers, including the isolated
delayed trainer, are disabled during independent preparation/replay.

A two-reveal abstract game independently enumerates pure legal responses. It
checks profile value 0.42, OOP response value 0.55, IP response value 0.775 and
NashConv 1.325. Present decisions cannot inspect the second future reveal. A truly
zero-marginal hand/prefix row contributes nothing even when its policy changes
or is omitted; omission at a positive-marginal row rejects.

Resource controls reject one edge below the exact requirement before tree or
trainer allocation, accept the exact reservation across ten dispatch combinations,
and retain planned-CFR+/flop-target restrictions. Historical payload controls and
the explicit current adapter hash in the
[source transition registry](../scripts/historical_turn_sources.py) protect
unchanged defaults and earlier evidence. The final focused compatibility run
passed all 22 tests in 110.556 seconds:

```powershell
python -B -m unittest tests.test_flop_public_diagnostics tests.test_flop_cfrplus tests.test_flop_delayed_cfrplus tests.test_public_diagnostics tests.test_historical_turn_sources -v
```

The option remains bounded to configured heads-up finite games. Full-deck
physical chance does not imply unrestricted no-limit Hold'em coverage. The frozen
CFR+ and delayed-averaging experiments retain their original recursive diagnostic
settings and measured source identities.
