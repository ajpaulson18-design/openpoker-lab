# Conditional opponent-action moments and role contracts

Status: original conditional mathematical experiment passed in both Python
modes at `a8df89a33eda4399aa420d60f9fde3b10947b746`. Its immutable packet is
preserved; saved replay acceptance and native implementation remain separate
gates. This is a conditional operator result, not a quality certificate.

The [structural worksheet](opponent-action-sampling-study.md) justifies this
test: a two-target proposal could visit far fewer branches than the current
single-global full walk. Lower per-iteration work is insufficient evidence
of improved solving. This gate compares every raw first moment and exposes
second moments before selecting an action-sampling contract.

## Two explicit candidates

Both candidates keep the same selected physical world, Q52 frozen profile,
whole-hand money rules, full visible history and global SB/BB identity.

* **Uniform target averages:** expand every target action; draw the opponent
  uniformly from its legal menu. A sampled opponent continuation multiplies
  by `sigma/q`. At a target row, regret multiplies the value difference by
  opponent prefix reach divided by proposal prefix probability; averages
  multiply own prefix reach and current policy by inverse proposal prefix.
  Selected zero-opponent-policy branches remain traversed for averages.
* **Policy role averages:** expand every target action and sample opponent
  actions with their frozen policy. Prefix and continuation opponent factors
  cancel for regret. Collect a player's average during the other target's
  pass, where that player's own prior actions are sampled. A visited average
  increment is the current policy vector. Own zero-policy branches stay
  expanded in the target-regret traversal.

The role distinction is essential. Sampling a zero-opponent-reach branch with
zero probability while trying to collect target-pass averages can omit a
positive own-reach average. A literal small control must expose that bias and
verify the opposite-role repair. This is our contract proof, not a claim that
the published [MCCFR framework](https://proceedings.neurips.cc/paper/2009/hash/00411460f7c92d2124a67ea0f4cb5f85-Abstract.html)
automatically admits our integer storage, quantized policy or native interfaces.

## First and second moments

Condition on one world. Future draws below distinct public histories are
independent. Terminal utilities are deterministic; reveals retain the same
world. If child means and second moments are `m[a]` and `s[a]`, an opponent
node has mean `sum(sigma[a]*m[a])` and second moment
`sum(sigma[a]^2/q[a]*s[a])`, omitting only zero-policy, zero-proposal terms.
An own node's mixed-value variance is `sum(sigma[a]^2*Var(child[a]))`.
The variance of action a minus the mixed value is
`Var(mixed)+(1-2*sigma[a])*Var(child[a])`.

For uniform proposals, a target-row regret second moment multiplies that
centered-action second moment by `opponent_prefix^2/proposal_prefix`.
Its average second moment is `(own_prefix*sigma[a])^2/proposal_prefix`.
For policy-proportional role sampling, the regret multiplier reduces to
opponent prefix reach, and an opposite-role average second moment is
`own_prefix*sigma[a]^2`. Zero prefixes are handled explicitly, never divided.
These are marginal, conditional-world moments, not all covariances or global
chance variance, and not a convergence or quality certificate.

The analytic oracle must compare all first-moment R/A coordinates and both
expected roots with the unchanged literal four-street raw authority. A
different small implementation enumerates pure opponent maps and evaluates
actual partial transcripts, checking every first and second coordinate without
using the analytic variance recurrence. Both target roots are opposite in
expectation; their realized roots and second moments need not be opposites.

## Physical and information scope

Three named full52 worlds use the established tie/loss/win physical witnesses
and the same common flop. Each literal reference range contains its selected
physical hand only, so its existing bounded law can independently seal and
rank that **conditional** world. Its single-pair prior never weights the
operator comparison. This does not claim a full1326-range moment-law admission.
Composition with the separately verified full-range joint chance producer
requires the conditional raw target to be preserved.

Two frozen profiles are tested: exact Q52 uniform defaults and the existing
own-hand/visible-history hash profile with zeros. A moment adapter consumes
the literal authority's frozen units, menus and identity descriptors, but
never its regrets/averages as computed moments. Full-history paths remain
distinct even when numeric source continuations share a vertex. Aliased
information keys within one selected world reject; the variance calculation
must not silently correlate sibling draws through a shared source-node ID.

Earlier policy and average inputs are compared across changed hidden
opponents and tails with the same own hand and flop. Raw regrets may change
when future continuations change; they must not be forced equal.

## Nonmaterialized probability and compact carriers

Deterministic first/last supported transcript witnesses exercise the raw
operator. They are not draws from q and are not learning iterations. Retain
the separate proposal factor at every visited opponent decision. Do not form
a global product over an entire branched partial tree: even 128 individual
Q52 factors would need a 6,656-bit denominator. A stress control must exceed
that hypothetical product width while retaining every factor and keeping all
actual route arithmetic under the existing 4,096-bit ceiling.

For the current fixed betting skeleton, a target makes at most seven own
decisions along a route and payoffs have at most one denominator bit.
Policy-role sampled continuation values therefore admit denominator `2^365`;
sampled regrets are differences of such values and need no opponent-reach
factor. Opposite-role sampled averages are Q52 policy units and admit `2^52`.
A separate seven-decision carrier control must attain the 365-bit denominator,
so this is not merely a loose observed width. Realized regret magnitude is
at most sixteen, average coordinates at most one, and roots at most eight.

The moment evidence still uses canonical `2^625`/`2^364` carriers for expected
values and their squared scales for second moments. Expectations include
prefix visitation probabilities and can require those larger canonical
denominators. Never confuse a per-transcript compact carrier with the
denominator of the exact full raw expectation. A native compact Store and
variable read/role lease contract are not implemented by this reference gate.

## Frozen execution and preservation plan

The unchanged global reference ceilings remain 500 million modeled work,
eight million entries, sixteen billion cumulative bit cells and 4,096 bits
per integer. The moment case itself keeps its original one-billion-bit-cell
arithmetic allowance; an attempted local increase was rejected and is not
used. Full source preparation, moment allowance and bounded frame/side/summary
I/O are included before preparation. The complete three-case modeled envelope
must fit the original global ceilings. If it refuses, retain the failure;
do not reset receipts or increase a ceiling to label progress.

Eight independent controls cover literal moments, the averaging bias,
nonopposite sampled roots, aliases/scheme refusal, actual transcripts, the
compact/nonmaterialized stress, all four-street means and budget refusal.
Then three case emitters preserve all four policy/scheme tables: every raw
policy unit, R/A mean and second moment, root moment and complete descriptor.
Separate bounded binary witnesses preserve all selected roles and proposal
factors. Both Python modes must agree byte for byte, with complete committed
source capture, original child exits and raw-byte drift checks.

## Executed original result

All eight original Python children exited zero: eight independent tests and
three case emitters in each mode. The complete source capture contains 28
files. Every saved frame, witness and summary agrees byte for byte between
normal and optimized modes. Across three physical worlds, two profiles and
two schemes, all 24,936 first-moment R/A coordinates equal the unchanged
literal authority. The same number of marginal second moments is preserved.
The small pure-map enumerator separately checks the analytic recurrence;
three-world second moments alone are not an independent enumeration proof.

| Named world | Sign | Moment work | Cumulative bit cells | Witness bytes |
| --- | ---: | ---: | ---: | ---: |
| 0 | tie | 219,552 | 104,148,092 | 30,320 |
| 1 | SB loss | 219,610 | 104,552,426 | 30,704 |
| 2 | SB win | 219,529 | 104,473,695 | 30,320 |

Each case records 450,002 logical moment entries, maximum integer forecast
2,688 bits, and a 1,767,712-byte full table frame. The complete three-case
source/math/I/O reservation is 477,785,568 work, 3,183,731 entries and
10,498,244,736 bit cells, inside the original global ceilings. The rejected
allowance increase was unnecessary: actual moment bit-cell use is below the
original one-billion allowance in every case. These are modeled counters,
not measured memory or wall time.

On the visible-hash profile, the role candidate's conditional sum of regret
variances divided by the uniform candidate's is approximately 0.6642, 0.6655
and 0.5586. Average variance ratios are 0.2061, 0.2717 and 0.2816. Expected
role traversal visits are about 43.67, 41.96 and 41.11. These specific fixed
profiles support pursuing the role contract; they do not prove universally
lower variance or lower cost to equal learning quality. The uniform-profile
average variance ratio is about 0.2675. Policy-dependent encounter counts
must not replace the prior uniform proposal's million-world worksheet.

The original raw tables, proposal-factor witnesses, all 28 captured sources,
receipts, and original packaging source are in
[`opponent-action-moments-v1`](../benchmarks/results/opponent-action-moments-v1/manifest.json).
The maintained [saved reader](../scripts/replay_opponent_action_moments.py)
authenticates its literal packet pin, Git objects, every original raw source
and all eight process exits before importing current numerical code. A
separate stdlib decoder checks physical headers, complete sorted row/slot
coverage, coordinate variances, Q52 centering, average ratios, compact
divisibility and every saved proposal factor. Fresh current mathematics must
then reconstruct all bytes; archived source is never executed.

No RNG, native training, larger lifetime, improved wall time, unrestricted
heads-up NLHE readiness or saved-policy quality is established. The next
justified milestone is an explicit native policy-role contract and complete
resource forecast, then independent raw transcript parity and measured cost
to the same independently verified quality.
