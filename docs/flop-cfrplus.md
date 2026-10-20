# CFR+ for full-future flop starts

The flop adapter now permits the existing alternating CFR+ kernels through
`solve_postflop(..., algorithm="cfrplus", traversal="recursive")` or
`traversal="public-batched"`. It uses the existing physical ordered future
worlds, blocker-conditioned joint weights and own-hand/public-history keys.
This is an opt-in capability candidate; independent full-deck convergence and
full-call evidence must be completed before reporting a quality improvement.
It does not change the default vanilla algorithm or recursive diagnostics.

The implementation removes the flop-only rejection from the adapter. Shared
CFR/CFR+ trainers, rules, ranking, evaluation and turn/river code paths remain.
The original 30-million world-node admission already reserves three training
passes per requested CFR+ sweep: OOP update, IP update, and completed-sweep
linear own-reach averaging. Every old world/candidate/tree/public-state guard
remains, as does the public trainer's separate prefix-edge guard. No new request
is admitted by weakening any cap. Planned CFR+ traversal, flop public diagnostics
and flop target-based early stopping remain explicitly unsupported.

For the independently checked weighted 5,940-world fixture in
[the baseline experiment](weighted-full-deck-flop.md), the public tree has 12
decision visits per world. A full 140-sweep CFR+ request reserves
`5940 * 12 * 140 * 3 = 29,937,600` world-node units and fits. A 141-sweep
request requires 30,151,440 and rejects before either trainer. This is a logical
admission count, not a timing or RSS bound. All policies still optimize a finite
configured heads-up game, not unrestricted NLHE or multiway equilibrium.

[Integration tests](../tests/test_flop_cfrplus.py) compare both trainers against
the independent physical/numeric all-street validator on full-deck and weighted
conditioned raised games. They cover cumulative street sizing, refunds and hidden
future information; check full requested three-pass admission; preserve explicit
unsupported options; and compare sixteen legacy flop/turn/river payloads plus the
default invocation against checksum-authenticated pre-change adapter source.
An updated prior rejection test retains the unchanged deeper full-deck tree cap.

## Validation plan

The next frozen comparison will retain the same weighted full-deck game and
0.005-chip final NashConv target, with CFR+ checkpoints 10/50/140 and three paired
recursive/public-batched repeats. Full profiles require independent physical
sign/prior/action/own-hand response replay. Complete-call time includes setup,
training, exact diagnostics and canonical serialization/hash; separate short
allocation calls stay out of timing medians. Preserve every profile and miss.

The baseline's vanilla/DCFR 400-sweep request and CFR+ 140-sweep request both
fit the unchanged 30-million cap, but their charged work differs (28,512,000
versus 29,937,600). They must not be described as identical work budgets.
Hardware and interpreter differences must be disclosed; cross-host timing is
not a controlled speed comparison. The source, baseline evidence and protocol
will be pinned before measuring the new candidate.

CFR+ uses established regret-matching-plus and strategy averaging concepts from
[Tammelin, 2014](https://arxiv.org/abs/1407.5042), implemented independently in the
existing project kernels. No external source, solver dependency or proprietary
result is incorporated. This adapter change does not itself establish improved
convergence, broad stack/range coverage, sampling, native chance traversal or RSS.
