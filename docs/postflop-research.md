# Postflop solver research notes

## Current model and limits

`solve_postflop` represents a finite, heads-up game beginning on the flop, turn, or river. Its betting tree is the configured action abstraction: the supplied bet sizes, raise sizes, raise limit, and stack caps define which actions exist. A converged strategy is therefore an approximate equilibrium of that configured game, not an unrestricted no-limit solution. The implementation does not cover preflop, multiway play, or rake.

The current solver enumerates compatible private-hand pairs and physical public runouts. On a full-deck flop, each compatible pair has 45 turn cards followed by 44 rivers (1,980 ordered outcomes); on a turn, 44 rivers. Range-product and physical-deal weights are normalized jointly once. A selected runout set conditions this joint distribution and must be described as a conditional game, not as a full-deck approximation. CFR training and best-response evaluation traverse the resulting explicit tree; the current engine does not use chance sampling.

The information-state boundary is public history plus the acting player's own private hand. Opponent cards and unrevealed future cards do not key a decision. Best response groups worlds by the responder's hand and sums public chance branches before maximizing, so it cannot choose an action with knowledge of a hidden runout. Contributions carry between streets under the shared pot and total-stack caps; unmatched excess is returned at settlement. These choices are part of the game definition and need independent regression coverage when the tree builder changes.

The exact physical tree has strict resource gates: candidate hand-pair iterations and world iterations are each capped at three million, public decision nodes at ten thousand, total decision/chance/terminal public states at 250,000, recursive world-node work at 30 million, and planned traversal operations at 250,000. These are acceptance limits, not performance claims. A full-deck, one-hand-per-player flop fixture has 1,980 worlds and fits the current gates with a short stack and small action tree; a larger tree can be rejected before allocation.

## Algorithm references

Counterfactual regret minimization (CFR) gives a method for minimizing regret at information sets in imperfect-information extensive-form games. Its equilibrium guarantees depend on the game and information-state assumptions; it does not make an arbitrary action abstraction equivalent to unrestricted poker. See [Zinkevich et al., “Regret Minimization in Games with Incomplete Information” (NeurIPS 2007)](https://papers.neurips.cc/paper_files/paper/2007/file/08d98638c6fcd194a4b1e6992063e944-Paper.pdf).

Monte Carlo CFR (MCCFR) replaces full traversal with sampled traversals and estimators designed to preserve counterfactual-regret estimates in expectation. Sampling can reduce work per iteration, while adding variance and requiring a specified sampling distribution and correction factors. It is a possible future algorithmic direction, not a description of this exact-enumeration engine. See [Lanctot et al., “Monte Carlo Sampling for Regret Minimization in Extensive Games” (NeurIPS 2009)](https://papers.nips.cc/paper/2009/file/00411460f7c92d2124a67ea0f4cb5f85-Paper.pdf).

Discounted CFR (DCFR) changes how prior regrets and strategy averages are weighted across iterations. It is a defined CFR variant, not merely a traversal optimization; comparisons should hold the game, stopping budget, and quality metric constant. See [Brown and Sandholm, “Solving Imperfect-Information Games via Discounted Regret Minimization”](https://arxiv.org/abs/1809.04040).

DeepStack combines continual re-solving with learned value estimates at lookahead boundaries. Its result does not support simply truncating this solver's tree: a depth limit needs a value model and an algorithm that controls the error introduced at the boundary. See [Moravčík et al., “DeepStack: Expert-Level Artificial Intelligence in Heads-Up No-Limit Poker”](https://arxiv.org/abs/1701.01724).

[Johanson et al., Public Chance Sampling CFR (AAMAS 2012)](https://webdocs.cs.ualberta.ca/~mbowling/papers/12aamas-pcs.pdf) describes traversals with private-hand reach/value vectors that share work across the public tree. That motivates an independently implemented exact batching experiment before introducing chance sampling. Its sampling algorithm and measured speedups are not claims about the current per-world Python backends.

## Public implementation concepts to investigate

The following are ideas visible in public project documentation. They are pointers for independent experiments, not evidence that the claims have been independently reproduced here, and no code from these projects was copied or integrated.

- [noambrown/poker_solver](https://github.com/noambrown/poker_solver) documents small-game validation, multiple CFR variants, and Python reference/C++ performance tiers. Keep algorithm comparisons and independent small-game checks separate from street coverage.
- [amaster97/poker_solver](https://github.com/amaster97/poker_solver) documents reference/optimized tiers and differential validation. Preserve a tested reference when experimenting with range-vector traversal or compiled kernels.
- [TexasSolver](https://github.com/bupticybee/TexasSolver) publishes matched-configuration solver comparisons. Adopt equivalent-game benchmarking discipline; its published timings are not reproduced OpenPoker results. Its source is not integrated.
- [PokerKit](https://github.com/uoftcprg/pokerkit) documents explicit dealing/betting sequences and simulation validation. Those are useful concepts for future isolated legal-action cross-checks, while the current engine uses its own card and betting modules.
- The [ucsandman/postflop README](https://github.com/ucsandman/postflop#readme) describes a flat arena representation, shared chance tables, suit-isomorphism support, and a separate best-response exploitability measure. These suggest profiling arena/index-based storage, reuse of card-dependent work, and carefully validated suit canonicalization. Any suit reduction must preserve blocker effects, range weights, and strategy remapping.
- The [kfg021/Postflop-Poker-Solver README](https://github.com/kfg021/Postflop-Poker-Solver#readme) documents per-street action configuration, tree-size estimation, and interactive chance/terminal nodes. These concepts suggest making preflight size estimates and tree inspection part of the solver workflow; the current implementation instead enforces hard allocation limits during construction.

## Research sequence

1. Keep the recursive traversal as the reference and compare any storage or traversal optimization against it on small games, including serialized strategy rows, values, exact best responses, and blocker-sensitive weighted ranges.
2. Profile whole-call time and peak memory separately. Include tree construction, training, and exact best-response evaluation; an iteration-only speedup does not establish an end-to-end improvement.
3. If exact full-deck traversal remains too costly, prototype MCCFR as a separate, explicitly named backend. Specify sampling probabilities, importance weighting, reproducible seeds, and an uncertainty-aware comparison against exact small-game oracles before using sampled metrics in user-facing results.
4. Treat suit-isomorphism and learned leaf evaluation as separate model changes. Validate card remapping and range asymmetry for the former; quantify value error and its effect on exploitability for the latter.

The present architecture is an independent Python implementation built around this repository's card, range, betting-tree, and CFR modules. The academic papers above inform algorithm boundaries; the public repositories above are README-level concept references only. No external source code or dependency is part of this implementation. Repository license, ownership and visibility are unchanged. These research records do not establish patent clearance for future specialized methods; any such adoption needs a method-specific review.
