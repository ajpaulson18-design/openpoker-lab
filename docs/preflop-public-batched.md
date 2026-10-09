# Exact private-hand vectors for conditioned preflop games

`solve_preflop(..., traversal="public-batched")` reuses the repository's
existing public-tree/private-hand vector trainer for vanilla, DCFR and CFR+.
It traverses each public betting node with private-hand vectors rather than
repeating the tree traversal for every complete world. Physical joint weights,
hidden future cards, own-hand information sets, histories, average-policy
serialization and exact legal best responses retain their original meanings.
Recursive remains the default; no shared trainer, postflop/turn/river or AI
Coach implementation was changed.

## Blinds, utility identity and memory tradeoff

The hand starts with zero chips before blinds, while the specialized vector
trainer requires a positive starting pot. The adapter solves this through a
bounded training-only copy of the public tree. Let `a` be the largest power of
two no greater than the minimum matched terminal contribution. It leaves every
player, action, history and chance branch unchanged, subtracts `a` from each
terminal contribution and passes `pot=2*a` to the unchanged trainer:

```text
pot/2 + min(c_sb-a, c_bb-a) = min(c_sb, c_bb)
```

The same identity covers signed fold and showdown payoffs, including unmatched
blind refunds. The binary anchor and raw subtraction introduce no additional
decimal quantization. The original tree stays intact for generic evaluation
and both exact legal responses; the training copy is released immediately
after training, including on failure. Terminal games without information sets
skip training and create no copy. Result metadata records the anchor, copied
state count and prefix-edge cap for the new backend only.

Original and copied trees coexist during training. Each is bounded by 250,000
public states, but their combined allocation is not a 250,000-state ceiling or
a process-memory limit. The unchanged vector trainer caps sparse joint
prefix/private-pair edges at 250,000 before training iterations. Existing
preflop world, candidate, decision and conservative world/decision work guards
remain in force, including three-pass accounting for CFR+. This integration
adds neither arbitrary utility callbacks nor fixed-policy locks.

## Independent verification and measured comparison

```text
python -m unittest tests.test_preflop_public_batched tests.test_preflop_full_private_chance
python -m scripts.benchmark_preflop_public_batched
```

The [specification](../benchmarks/preflop-public-batched-v1.json) compares
recursive and public-batched vanilla/DCFR at 10 and 100 iterations on a weighted
asymmetric eight-world fixture and all six AA versus all six KK combinations.
The latter has 36 private pairs, 72 compatible worlds and 1,014 information
sets. Three selected boards condition both games, including blocker-shifted
priors; this is not full-deck preflop or full practical poker ranges.

All 16 checkpoints in the
[report](../benchmarks/results/preflop-public-batched-v1.json) passed independent
numeric replay and exact legal response checks. Every serialized row and action
also matched between backends within `1e-10`; the largest policy probability
difference was `9.83e-15`, and the largest backend scalar difference was
`1.23e-15` chips. Private-pair probabilities matched the independent oracle
within `1e-12`. Both algorithms improved their endpoint best-response gaps.
No monotonic convergence theorem or universal equilibrium accuracy is claimed.

| Game / method | NashConv at 100 | Recursive / vector median seconds at 100 | Recursive / vector peak Python bytes at 10 |
| --- | ---: | ---: | ---: |
| Weighted asymmetric / vanilla | 0.0970026 | 0.974 / 1.130 | 689,058 / 661,239 |
| Weighted asymmetric / DCFR | 0.000745496 | 1.158 / 0.931 | 637,706 / 661,455 |
| All AA vs all KK / vanilla | 0.108254 | 7.954 / 2.866 | 1,778,133 / 1,808,589 |
| All AA vs all KK / DCFR | 0.000986374 | 8.966 / 3.201 | 1,775,717 / 1,720,869 |

The broader fixture was about 2.8 times faster at 100 iterations. The small
vanilla fixture was slower with vectors; no automatic backend selection was
added. At 100 iterations in the broader DCFR fixture, training consumed 8.827
seconds recursively versus 3.029 seconds with vectors, while template/graft
construction took about 0.018/0.022 seconds. This evidence prioritizes reducing
repeated training traversal over speculative template or rank caching.

Times are medians of three complete calls on a shared Windows/Python 3.12.14
machine at frozen source `d41ab5b378a7834ddaed5ae75928c36b2e488de0`; source,
configuration and oracle hashes are recorded, and the measured worktree was
clean. Complete calls include construction, the training view, training, exact
responses and serialization, excluding independent replay. Phase timers add
fixed wrapper overhead; their medians need not sum to the total median. Run
order is fixed recursive then vector, so small ordering effects are possible.
Separate uninstrumented tracemalloc calls measure **10 iterations only**;
100-iteration memory and RSS were not measured. Memory results do not support
a universal reduction claim. CFR+ parity is tested but not timed in this report.

Five focused tests compare every strategy row and scalar metric across all
three algorithms, including weighted multi-flop and shared-flop/turn prefixes,
fractional blinds/sizes, nonzero refund settlement, root folds, large utility
translation and prefix-edge failure without mutating the original tree. The
exhaustive regression additionally compares planned and vector policies for
all 7,920 worlds of a four-private-pair fixed-flop game with every legal future
deal. Its common policy and metrics are independently replayed; that fixture
does not establish equilibrium convergence at ten iterations.

## Recorded numerical limit

The separate [rounding-boundary reproduction](../benchmarks/preflop-rounding-boundary-v1.json)
records the old global checker expecting `raise@1.293095147` where the
configured local rounding order produces `raise@1.293095146`. The
[monetary replay repair](preflop-monetary-replay.md) validates that existing
configured game with exact serialized amount/target checks while retaining
the old global calculation as an explicit precision diagnostic. The frozen
vector benchmark above predates that checker repair. No production monetary
sizing was changed, and exact-decimal equivalence remains unproven.

To reproduce the historical diagnostic rejection (an `AssertionError` is expected):

```python
import json
from pathlib import Path
from pokerlab.preflop_solver import solve_preflop
from scripts.preflop_validation import replay_policy

fixture = json.loads(Path("benchmarks/preflop-rounding-boundary-v1.json").read_text())
kwargs = {key: fixture[key] for key in
          ("config", "runouts", "flop_config", "turn_config", "river_config")}
result = solve_preflop(fixture["sb"], fixture["bb"], iterations=10, **kwargs)
replay_policy(result, fixture["sb"], fixture["bb"],
              monetary_mode="global-rational", **kwargs)
```

## Implementation provenance

Luna implemented the adapter and focused/exhaustive parity tests; lead review
supplied the benchmark and numerical-boundary reproduction. Code is independently
authored in this repository with the standard library and its existing trainer.
No third-party source, dependencies, policies or commercial solver outputs were
added. Public/private vector traversal implements the same finite-game
[CFR formulation](https://webdocs.cs.ualberta.ca/~bowling/papers/07nips-regretpoker.pdf),
with repository [vector-trainer provenance](public-batched-cfr.md) and the
documented [CFR+ averaging schedule](preflop-cfrplus.md).
