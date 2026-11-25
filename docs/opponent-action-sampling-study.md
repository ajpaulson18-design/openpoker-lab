# Opponent-action sampling: work, storage and mathematical gates

Status: design and source-frozen structural worksheet. No sampled update
operator, RNG, native trainer, longer lifetime or quality admission yet.
This continues the shared four-street foundation and preserves the old
eleven-card refusal, rather than creating separate street solvers.

## Why examine branch work

The [accepted CPU observer](joint-thread-cycles.md) attributes only about one
fifth of walk cycles to frozen-policy reads on its named fixture. Staging is
also substantial. Both finer arithmetic observers fail their unchanged overhead
gates, so their helper shares cannot justify a kernel rewrite. Separately,
the [lifetime worksheet](joint-learning-lifetime.md) projects about 427 million
encountered rows at one million uniform worlds even on this small betting
template. Fewer visited branches could reduce both walk and staging work and
slow encounter growth. That is a hypothesis to measure, not an algorithm adoption.

[Lanctot et al.](https://proceedings.neurips.cc/paper/2009/hash/00411460f7c92d2124a67ea0f4cb5f85-Abstract.html)
give an expectation-correct block-sampling framework and a policy-proportional
external sampler. The uniform menu proposal below is a different importance
proposal. Their constant-factor external-sampling result does not directly
admit it or our quantized solver. Published theory does not replace our
all-coordinate expectation, variance and saved-policy quality gates.

## Fixed structural proposal

Keep the same exact globally conditioned joint private-pair/board law and
freeze the whole Q52 policy. For each target seat, expand all of its actions
and choose one opponent action uniformly from its legal menu, with `q=1/K`.
Reveal the same preselected board in order. The two target passes share the
world, with independent proposal draws at distinct complete histories.

Policy keys remain actor, original own holding and full visible public history.
Hidden opponent cards and future board cards never enter a key. A sampled
public history still includes the whole money/action history; shared numeric
continuations are not merged information sets.

The new [worksheet](../scripts/forecast_opponent_action_sampling.py) computes
expected visits, reads, terminals, reveals, action traversals and target-row
encounters by a memoized recurrence on the independent numeric betting rules:
sum child costs at target nodes, average child costs at opponent nodes. Worst
bounds replace the opponent average with a maximum. These are componentwise
upper bounds; their maxima need not occur on one common transcript. A separate
literal-history inclusion calculation must agree with the expected counts.

Let `s0(h)` and `s1(h)` be the products of inverse menu sizes for previous
actions of each seat along a public history. The inclusion probabilities in
the target-zero and target-one passes are `s1` and `s0`. Thus a read row is
encountered in their union with probability `g=s0+s1-s0*s1`. That union is
different from the sum of policy reads and from target-update encounters.

For iid **uniform physical worlds** and this fixed menu proposal, a path's
own-hand/visible-prefix identity is uniform over the existing `K` physical
cells. Its expected distinct seen rows after T world observations are
`K*(1-(1-g/K)^T)`. Public-block encounters use the corresponding public-prefix
cell count. No independence between different paths or seats is needed to sum
expectations. Independence across observations and between the two proposal
draw sets is required. These are encounter counts, not nonzero numerical
retention, RSS or native lifetime admission. They do not apply to arbitrary
weighted ranges or evolving policy-proportional proposals.

The worksheet uses two-term Bonferroni and Cauchy lower bounds and a union
upper bound, then rounds each path outward before summing. This deliberately
keeps arithmetic bounded; short-lifetime intervals may be loose. Four
reference controls must compare the DP with literal histories, enclose exact
small occupancy, refuse reduced budgets before preparation and preserve false
training/admission flags. Source preparation and scalar work share a prepaid
80-million-work envelope within existing global caps. The fixed source is
388 vertices, 410 edges and 1,105 logical occurrences.

## Raw updates require a separate proof

For a uniform proposal target pass, an opponent node's continuation would
return `sigma_opponent(a)/q(a) * child_value`. At a reached target row,
counterfactual regret would multiply the sampled action-value difference by
`opponent_prefix_reach / proposal_prefix_probability`. Target-pass own-reach
averages would instead multiply by `1/proposal_prefix_probability`; inserting
opponent policy reach into that average would bias the current raw target.
Even a selected zero-opponent-policy branch may need traversal for averages.
Own zero-policy branches also remain expanded for counterfactual regrets.

An alternative is policy-proportional opponent draws with regret and average
updates assigned to different traversal roles. A target-regret pass can then
cancel opponent policy/proposal factors, while a player's average is collected
in the other target's pass, where that player's own past reach is sampled.
This could avoid large inverse-proposal factors. It is a separate candidate
whose all-row expectation and zero-policy behavior need explicit proof; do not
silently substitute it for the uniform worksheet's law or occupancy numbers.

The worksheet reports only hypothetical integer carrier envelopes for the
uniform proposal: multiply the existing `16*2^625` regret bound and `2^364`
average bound by the largest applicable inverse menu product. Width compatibility
does not admit a raw operator, intermediate multiplication bound, work,
leases, storage or training. Quantized next policies and normalized averages
are not made unbiased merely by unbiased raw increments.

Two target-sampled roots need only be opposite **in expectation**. Forcing
independent noisy roots to sum to zero per draw would change the estimator.
All proofs must retain global SB/BB identity and the same whole-hand payoff.

The current Store expects a fixed one- or two-read count for every staged row.
Two partial traversals instead have a varying read/role union, including rows
read only as opponent-policy inputs. A future explicit lease contract must
authenticate those roles, preserve observed-row coverage, fuse both frozen
passes before publication and reject missing/duplicated/stale stages. No
weakening of the existing contract or silent fallback is authorized by this study.

## Gates before implementation or adoption

First compare every expected raw R/A coordinate and both expected roots with
the unchanged literal four-street authority, including zero own/opponent reach,
zero policies, hidden-future and shared-prefix witnesses. Validate selected
small transcript enumerations independently of any moment recurrence. Derive
second moments, proposal support, worst work and complete-lifetime storage.
Then consider a separately admitted native contract with exact integer and
source-inclusive evidence. RNG, evolving-policy learning and independently
replayed saved-policy quality remain later gates. Adoption needs cost to the
same quality on the same game, including setup/diagnostics and every preserved
miss; fewer nodes or cheaper iterations alone do not establish improvement.
