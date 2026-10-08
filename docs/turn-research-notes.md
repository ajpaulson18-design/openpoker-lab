# Turn-to-river solver research notes

Research snapshot: 2026-10-08. These notes summarize mathematical requirements and design references for an exact turn-to-river CFR extension. They do not reproduce or adapt third-party code and do not propose adding a dependency.

## Extensive-form game requirements

The original CFR result is stated for finite extensive-form games with imperfect information and perfect recall. In poker, an information set must keep hidden opponent holdings grouped, while separating states by every observation the acting player has received, including their own prior actions and public cards. The original paper defines counterfactual value using chance and opponent reach, and proves that minimizing immediate counterfactual regret at each information set bounds overall regret. See Zinkevich et al., [Regret Minimization in Games with Incomplete Information](https://papers.nips.cc/paper_files/paper/2007/hash/08d98638c6fcd194a4b1e6992063e944-Abstract.html) and its [paper PDF](https://martin.zinkevich.org/publications/regretpoker.pdf).

For this solver, an information-set identity should contain at least the acting player, that player's two private cards, the public turn board, the full public betting history through the turn, and (after it is revealed) the river card plus all public river actions. A player must be able to condition later decisions on the river card, while never conditioning on the opponent's private cards. A best response may choose different river actions on different observed river cards; at any one information set it must aggregate over compatible opponent holdings before maximizing. On a turn decision before the river is known, it must average future public chance outcomes and may use an optimal continuation strategy after each revealed river.

## River chance weights and selected runouts

Let (H_0,H_1) be two-card private holdings, (B) the four-card turn board, and (R) the 52-card deck. A private-hand pair is physically compatible only when the two hands are disjoint and neither overlaps (B). Every such pair leaves exactly 44 river cards. Given a pair, each remaining river has conditional chance probability (1/44).

With range weights (w_0(H_0)) and (w_1(H_1)), the unnormalized joint mass for a full physical world is:

```
mass(H0, H1, river)
    = w0(H0) * w1(H1) * (1/44)
```

for every compatible private pair and every river not in (B cup H_0 cup H_1). Normalize over the complete set of physical worlds. For the full 44-card runout set, marginalizing river restores the familiar compatible-pair weight (w_0(H_0)w_1(H_1)).

If the API's `runouts` argument means **condition on river belonging to a selected global set (S)**, restrict worlds to river cards in (S), keep the same pre-conditioning weight per surviving world, and normalize once across all surviving pair/runout combinations:

```
Z_S = sum_compatible_pairs w0(H0) * w1(H1) *
      count(S minus (B union H0 union H1)) / 44

P(H0,H1,r | river in S)
    = w0(H0) * w1(H1) / (44 * Z_S)
```

for each surviving `r` in that pair's available subset of (S). This makes the posterior pair mass proportional to range-product times the number of selected cards left after that pair's blockers. Do not independently normalize every pair's available subset and then give each pair its original mass: that would make each pair contribute the same total runout mass despite different blocker counts, changing the physical conditional game. If `runouts` is instead intended as a Monte Carlo sample schedule, define and report that different sampling contract explicitly, with the appropriate sampling correction.

The 44-card statement is conditional on both private holdings and the fixed four-card board. It is not valid to draw one per-pair river uniformly from a selected subset and silently call the resulting aggregate a globally conditioned deal.

## Reach, best response, and accounting

CFR's counterfactual reach for player (i)'s regret uses chance and the opponent's action reach, but not (i)'s own prior action reach. The own-reach probability weights the average strategy. At a river action node, the river is now public, so the information set is keyed by that card; opponent hole cards remain hidden and must be integrated out.

For each deal/runout world, betting utilities must carry forward all matched turn contributions. At the river, the pot used for pot-relative sizes is the original pot plus both players' matched turn commitments. If turn totals are unequal because of an all-in, return the unmatched excess before the river: it is not part of the matched pot and cannot be won by the opponent. River effective-stack caps must be applied to total street commitments, with any further unmatched river excess handled by the same rule. An all-in before the river has no river decisions, but its showdown is still evaluated over the legal runout cards and its existing matched contributions.

For best-response evaluation, recurse through the public tree and group chance/deal worlds by the BR player's private hand and visible history. Sum weighted continuation values over indistinguishable opponent hands at each information set before taking `max(action)`. Never let a maximizing choice depend on the opponent's actual private hand. Since the runout is public, different rivers form different decision information sets and a legitimate BR may choose differently on each one.

## Primary algorithm references

- Zinkevich et al. (NIPS 2007), [Regret Minimization in Games with Incomplete Information](https://papers.nips.cc/paper_files/paper/2007/hash/08d98638c6fcd194a4b1e6992063e944-Abstract.html). Foundation for counterfactual regret, perfect recall, and the information-set definition.
- Lanctot et al. (NIPS 2009), [Monte Carlo Sampling for Regret Minimization in Extensive Games](https://www.cs.cmu.edu/~kwaugh/publications/nips09b.pdf). Defines chance as explicit probability-bearing outcomes and shows how sampling blocks require probability correction to preserve expected counterfactual values. For a full exact turn-to-river traversal, enumerate the 44 legal public runouts per compatible private pair; sampling is a separate algorithm choice.
- Johanson et al. (AAMAS 2012), [Efficient Nash Equilibrium Approximation through Monte Carlo Counterfactual Regret Minimization](https://poker.cs.ualberta.ca/publications/AAMAS12-pcs.pdf). Separates private chance from public chance and studies public-chance sampling in poker. It supports treating a river as one shared public event in the public tree and reusing strategy computations across private holdings; it is not a license to sample different rivers independently for each hidden deal.
- Brown and Sandholm (AAAI 2019), [Solving Imperfect-Information Games via Discounted Regret Minimization](https://arxiv.org/abs/1809.04040). Useful for optional DCFR regret/average-strategy updates; chance and information-set correctness remain separate from the selected CFR variant.

## Open solver design references (conceptual only)

- [OpenSpiel's game concepts](https://github.com/google-deepmind/open_spiel/blob/master/docs/concepts.md) describe extensive-form state transitions and explicit chance actions. Its [CFR API](https://github.com/google-deepmind/open_spiel/blob/master/open_spiel/algorithms/cfr.h) documents baseline and CFR+ variants. Treat this as interface/design reading only; no dependency is proposed.
- [noambrown/poker_solver](https://github.com/noambrown/poker_solver) separates small-game validation (Kuhn/Leduc) from a river solver and exposes several CFR variants. Its public README is an algorithm-scope reference; do not copy its implementation.
- [amaster97/poker_solver README](https://github.com/amaster97/poker_solver/blob/main/README.md) describes a readable reference tier, a vector-form range solver, and differential checks between backends. This is a useful pattern for independent oracle and parity validation, not a source to port.
- The current project already defines a versioned [restricted river configuration](../pokerlab/river_config.py) and a full-traversal [configured river game](../pokerlab/solver.py). The turn extension should add the river chance layer without silently changing those river-only semantics or presenting the result as full Hold'em GTO.

## Independent tests to keep

Use small hand-computable fixtures, not only convergence tests:

- A fixed turn board and two noncolliding single-combo ranges: exactly 44 physical runout worlds, each conditional probability (1/44), with blocker cards excluded.
- A selected global runout set where one private pair blocks one selected card and another pair blocks none. Check the globally normalized joint-world probabilities and pair marginals from the formula above. This catches pair-by-pair renormalization.
- A manually enumerated toy policy where the opponent's preferred action differs by hidden holding. Confirm the BR integrates opponent holdings before maximizing and cannot realize the hidden-card oracle's larger value.
- A policy that differs by river card. Confirm that river is present in the post-reveal information-set key and the BR can respond separately after observing it.
- A turn decision whose action changes the matched contributions. Check river pot fractions use original pot plus twice the matched turn contribution; check excess from asymmetric all-in totals is refunded and unavailable for the opponent to win.
- An all-in turn line: verify no later betting action appears, legal rivers remain, and showdown utility carries matched contributions.
- A perfect-recall check: histories that differ by an earlier own action or a public board card must never merge into one information set; histories that differ only in opponent cards remain grouped for the player acting.

These are semantic oracles for the public API, not snapshots of a particular implementation.

