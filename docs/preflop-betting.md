# Heads-up preflop betting and continuation boundary

`pokerlab.preflop_tree` supplies the missing preflop betting state machine.
It reuses the existing action/node types, raise sizing helper and CFR-compatible
tree interface. Existing flop, turn, river and Coach source remains unchanged.
This is a game-construction component, not a preflop equilibrium solver.

Player 0 is the small blind/button; player 1 is the big blind. Starting stacks
include forced blinds. A small-blind completion leaves the big blind its
check/raise option; a call after a voluntary raise ends the betting round.
The initial minimum raise increment is the big blind; subsequent minimums
use the last full raise. Short all-ins do not reopen a prior player's action.
These choices follow the heads-up and betting provisions of the
[2026 Poker TDA rules](https://www.pokertda.com/view-poker-tda-rules/), rules
36-C, 45, 49 and 53-B. This implements numerical, in-turn betting states,
not the rules for ambiguous physical declarations or tournament disputes.

```python
from pokerlab.preflop_tree import PreflopConfig, build_preflop_tree

tree = build_preflop_tree(PreflopConfig(
    starting_stack=(40, 30), raise_sizes=(0.5, 1), max_raises=3,
))
```

Raise fractions apply to the additional raise increment using the pot after
calling. Blind posts do not count as voluntary raises. The configurable
0–8 raise cap and at most eight pot-relative sizes bound the abstraction;
they are computational restrictions, rather than no-limit poker rules.
Optional shoves share the same cap and deduplicate stack-clipped targets.
There is no ante, dead money, rake, straddle, multiway or tournament payout
model. Chip amounts follow the repository's nine-decimal action convention.
Blinds and the difference between them must exceed the shared 1e-9-chip
comparison tolerance; inputs are rounded to that action precision. Rescaling
chip units avoids configurations that are numerically indistinguishable.

Calls and blind posts are capped by each starting stack. A continuation returns
unmatched excess, carries equal `matched_contributions`, gives the total pot
and remaining stacks, and records each player's all-in flag. A live flop
continues with the big blind first; a settled all-in waits for a showdown
runout with no further betting. A live flop leaf contains no estimated equity
or hidden future cards. Fold terminals use the existing zero-sum payoff
function with initial pot zero; forced blinds are already in contributions.

`continuation_factory` receives a frozen `PreflopContinuation` and can attach
a future subtree supported by the generic CFR trainers. It must supply the
physical chance distribution, hidden-information keys, future betting,
payoff convention and its own resource guard. Leaving the callback absent
returns an explicit unsolved boundary. Neither exact preflop strategies nor
full preflop-to-river solving is available through this tree-builder API.

Every preflop decision, fold and continuation boundary is reserved before
allocation. Defaults permit at most 10,000 decisions and 250,000 public states;
smaller caller limits can reject work early. Callback-generated subtrees are
outside these counts. The builder releases recursive closure references on
success and failure; it does not retain constructed trees in a global cache.

Independent rule tests check blind losses, the limp option, raises, asymmetric
short calls, refunds, explicit continuations and allocation guards. A separate
rational replay checks every edge and settlement in nine versioned fixtures
without invoking production sizing helpers. Full-root synthetic CFR checks
verify compatibility with known values; synthetic utilities are not poker
equilibrium accuracy evidence.

```text
python -m unittest discover -s tests -p test_preflop_tree.py -v
python -m scripts.benchmark_preflop_tree --output benchmarks/results/preflop-tree-v1.json
```

The benchmark records complete config/tree construction time, a separate
traced Python memory peak, counts, independent replay results and source/config
hashes. It excludes strategy training and reports no convergence or
exploitability. No third-party source or dependency was incorporated; the rule
document informed semantics only. License and ownership settings are unchanged.

## Recorded construction evidence

[The report](../benchmarks/results/preflop-tree-v1.json) freezes the construction
and replay sources at `b786b54c3d192a2db33a12aef5d99e2fe7fa72f2`, Python
3.12.14 on Windows. All nine fixtures and the 162-configuration asymmetric
stack grid passed independent rational replay. The grid checks 914 action
edges; the wide fixture separately checks 4,233 edges, 1,412 decisions and
4,234 total public states. Reported API counts agree with the independent walk.

Complete construction medians range from about 0.05 ms for a forced all-in
boundary to 111.12 ms for the wide five-size/four-raise fixture. The latter
traced peak is 1,915,856 bytes; its ordinary minimum-raise fixture uses 54
decisions, 160 states, approximately 3.27 ms and 64,384 traced bytes. These
small, machine-dependent measurements are a first construction baseline.
They do not measure full preflop solving, training, chance enumeration or
best responses, and establish no speedup over an earlier implementation.
Source/config hashes stayed unchanged during measurement. The dirty flag
records the pre-existing untracked output report, not a change to solver source.

Nine focused tests passed, including full-root recursive/planned CFR wiring
under both algorithms, fail-closed unsolved leaves, and CPython release with
cyclic collection disabled on success and callback failure. Luna implemented
the bounded tree and rule fixtures; lead review supplied additional independent
replay, precision-boundary, release and integration checks. Turn and river
production source, application and explanation contracts are preserved.
