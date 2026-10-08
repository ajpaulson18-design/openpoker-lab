# Solver algorithm and provenance research

Research snapshot: 2026-10-08. This is a design note for an original, bounded improvement to the existing fixed-board river solver. It does not incorporate third-party source code or recommend adding a dependency. Public repository and patent records are not legal advice, a complete license audit, or patent clearance.

## Current implementation and best bounded candidate

`pokerlab/solver.py` implements exact full-traversal, simultaneous vanilla CFR over compatible weighted private-hand pairs. It gets current action frequencies by regret matching cumulative regrets, accumulates own-reach-weighted uniform average strategies, then computes best responses after aggregating indistinguishable opponent hands. The game scope is already deliberately narrow: fixed five-card board, two supplied ranges, one fixed bet size, check/bet/fold/call, no raises or rake. Its 3-million hand-pair-iteration guard caps work.

The strongest small algorithm experiment is to add a selectable **Discounted CFR (DCFR)** variant while retaining the exact traversal and current CFR path as the comparison baseline. Start with the Brown–Sandholm default parameters `alpha=1.5, beta=0, gamma=2`. This changes only regret history discounting and average-strategy weights; it does not expand the game, change utility, infer ranges, or require sampling. The paper reports this default consistently strong across its tested games, but that is motivation for a local benchmark, not evidence that it wins on this particular small river abstraction.

Let `t=1,2,...` be the one-based iteration. At the beginning of iteration `t`, compute each current strategy from the stored regret vector using the existing regret-matching rule: normalize positive regrets, or use uniform action mass if none is positive. Traverse every compatible deal exactly as now and accumulate that iteration's counterfactual regret deltas `delta_t[I,a]` using the existing chance/opponent reach weights.

After the traversal, first form the cumulative regret including this iteration's delta, then discount its positive and negative parts once:

```
Q_t[I,a] = R_(t-1)[I,a] + delta_t[I,a]
R_t[I,a] = (t^alpha / (t^alpha + 1)) * max(Q_t[I,a], 0)
         + (t^beta  / (t^beta  + 1)) * min(Q_t[I,a], 0)
```

Use the full delta as computed; do not clip updated regret at zero. With the defaults, positive regrets are discounted by `t^1.5/(t^1.5+1)`, negative regrets by `1/2`, and the average-strategy weight is `t^2`. For `t=1`, both regret factors are one half, so the first iteration's nonzero delta is also discounted by one half. The current strategy at iteration `t` is still derived from the stored, already-discounted regrets from the previous iteration. Apply the discount once per information-set action per iteration, after the traversal delta is known. Do not discount once per private-hand pair. This order follows the paper's statement that linear CFR is equivalent to multiplying the accumulated regret by `t/(t+1)`: adding the current delta before discounting yields per-iteration weights proportional to `t`; discounting only the previous cumulative regret and then adding the current delta would instead shift them to `t+1`.

Accumulate the weighted average strategy during the same traversal, using the paper-equivalent per-iteration weight `t^gamma`:

```
S[I,a] += t^gamma * own_reach(I) * sigma_t[I,a]
W[I]   += t^gamma * own_reach(I)
sigma_bar[I,a] = S[I,a] / W[I]
```

Here `own_reach` is the acting player's own prior-action reach, matching the current solver's `own` factor. Standard average-strategy weighting excludes chance and opponent reach. The implementation may hoist deal aggregation into a per-private-hand marginal: that marginal is constant across iterations for the hand-indexed information set and therefore cancels when the row is normalized. It is not an extra iteration-dependent strategy weight. Keep all compatible-deal contributions to an information set aggregated before normalization. Retain exact best responses against the resulting averaged profile, and retain existing output labels for game scope and node-lock caveat while making the reported variant and averaging rule explicit.

This is a variant choice from published CFR literature, not a claim of algorithmic novelty. Avoid importing or translating source code from any reference repository.

## Validation needed before changing a default

1. Preserve the existing CFR behavior as a selectable baseline and add a synthetic fixture with independently known terminal utilities and exact information-set best responses. Check regret deltas by a hand-worked one-iteration case, including incompatible card pairs, weighted ranges, ties, and both players' reach factors.
2. Verify DCFR recurrence/order directly: strategy at iteration `t` uses only already-discounted regrets from earlier traversals; each regret first receives the current delta and then its positive/negative total is discounted once; average mass uses own reach and `t^2`; average rows normalize to one (uniform only when their mass is zero).
3. Compare vanilla CFR and DCFR on the same deterministic board/range/pot/bet fixtures at equal traversal budgets (e.g. 10, 100, 500, and 1,000 iterations). Report exact exploitability / NashConv, elapsed time, and per-fixture deltas, including cases where DCFR is worse. Expand to a repeatable synthetic spot sweep before changing the default. Keep the solver's 10,000-iteration and 3-million-pair ceilings.
4. Run current independent solver validation (brute-force pure-strategy best responses, evaluator checks, Kuhn CFR reference as applicable) plus the full unit suite because this changes numerical calculation. Independently verify lock behavior: fixed strategy at a lock; output still marked as a locked-game profile; unrestricted best-response gap remains explicitly not a convergence certificate.
5. Preserve reproducibility: include variant/parameters in output provenance, keep deterministic ordering/serialization, and verify unchanged default CFR output for existing callers if DCFR remains opt-in.

## Algorithm design references (read for concepts only)

- Brown and Sandholm, [Solving Imperfect-Information Games via Discounted Regret Minimization](https://arxiv.org/abs/1809.04040), AAAI 2019. The paper defines DCFR by discounting positive and negative accumulated regrets separately and weighting average strategies; it identifies `(alpha,beta,gamma)=(3/2,0,2)` as a strong default in its experiments. The paper's results do not establish performance on OpenPoker's restricted river game.
- The [AAAI proceedings record](https://ojs.aaai.org/index.php/AAAI/article/view/4007) provides publication and citation details.
- [amaster97/poker_solver README](https://github.com/amaster97/poker_solver/blob/main/README.md) describes a Python reference/Rust core, tabular DCFR, paper defaults, and differential testing. Its `DEVELOPER.md` documents design boundaries and validation. Use as an algorithm-design/validation reference only.
- [noambrown/poker_solver README](https://github.com/noambrown/poker_solver) documents CFR, CFR+, external-sampling MCCFR, fictitious play, and DCFR, with a Python reference implementation and C++ performance tier. Its public license is MIT.
- [tjennings/poker_solver README](https://github.com/tjennings/poker_solver) describes CFR+ regret flooring, regret matching, counterfactual values, and averaged strategies. Its README reports MIT.
- [bupticybee/TexasSolver README](https://github.com/bupticybee/TexasSolver/blob/master/README.md) describes a C++ postflop solver and reports AGPL-3.0. The README says commercial licensing is needed to integrate its source or provide its service; do not incorporate it or its code.
- [uoftcprg/pokerkit](https://github.com/uoftcprg/pokerkit) is a poker simulation/evaluation library rather than a CFR solver reference. It documents rules/state APIs, extensive tests, and MIT licensing; useful only as a rules-validation reference, not as a new runtime dependency.
- The current OpenPoker Lab repository declares [MIT in LICENSE](../LICENSE) and `pyproject.toml`. That fact does not clear patents or settle obligations for third-party material.

## Targeted patent search and limits

A targeted public search for patents mentioning poker/CFR/MCCFR found [US11077368B2, “Determining action selection policies of an execution device”](https://patents.google.com/patent/US11077368B2/en), with a related [WO2020098821A2 publication](https://patents.google.com/patent/WO2020098821A2/en). Google Patents lists the US grant as active, Alipay Hangzhou Information Technology as current assignee, and describes MCCFR sampling, counterfactual-value baselines, and variance-reduction techniques. The page itself warns that its legal status and assignee information may be inaccurate and are not legal conclusions. The family appears to describe particular sampled-MCCFR and baseline techniques; this read does not determine whether any claim reaches any implementation here.

Search also surfaced Chinese-language CFR/incomplete-information-game patent publications, including [CN110222874A](https://patents.google.com/patent/CN110222874A/en) and [CN110826717A](https://patents.google.com/patent/CN110826717A/en). Search results alone do not establish grant, current enforceability, relevant jurisdiction, claim scope, or applicability. This was a narrow keyword search, not a freedom-to-operate review; it cannot establish that DCFR, exact full traversal, poker software, or any contemplated commercial product is patent-clear. Do not make a patent-safety claim based on this note. Any product launch decision needing that assurance requires qualified counsel and a jurisdiction/claim-specific review.

## Public license observations (not a complete code audit)

The reviewed repository pages report: amaster97/poker_solver — MIT; noambrown/poker_solver — MIT; tjennings/poker_solver — MIT; uoftcprg/pokerkit — MIT; bupticybee/TexasSolver — AGPL-3.0, with separate commercial integration terms described in its README. Public license facts are limited to the pages/HEADs observed on 2026-10-08; check exact files and versions before any future use. No third-party code, trained solver output, dependency, or license change is proposed here.
