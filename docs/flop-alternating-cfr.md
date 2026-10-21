# Opt-in alternating flop LCFR and DCFR

`solve_postflop` accepts `algorithm="lcfr"` and `algorithm="dcfr-alternating"`
only for flop starts with `traversal="public-batched"`. Both train the same
configured physical heads-up game and return ordinary postflop policy rows.
The new options use a separate project-owned trainer; existing vanilla,
simultaneous DCFR, CFR+ and delayed CFR+ schedules retain their current paths.

## Algorithms and update order

At sweep t, save the current policy and accumulate its average with joint
own-hand/public-prefix mass times the acting player's own action reach. Use
weight t for LCFR and t squared for alternating DCFR. Then compute OOP regret
deltas, update OOP cumulative regrets, rematch OOP, and compute IP's deltas
against that updated OOP policy. Update IP regrets and rematch for the next sweep.
Averaging before the sweep records each player's own policy used for that
player's regret update: changing OOP's policy does not change IP's own reach.
Opponent reach belongs in regret deltas, not in the own-reach average.

LCFR adds t times the instantaneous counterfactual regret to cumulative regret.
Alternating DCFR adds the unweighted instantaneous regret and discounts each
updated positive entry by t^(3/2)/(t^(3/2)+1), and each nonpositive entry by 1/2.
Both retain negative cumulative regrets and use ordinary regret matching; they
do not apply the CFR+ zero floor. The public helper shares existing physical
prefix aggregation and counterfactual-delta traversal. Its independent average
pass traverses all legal public branches without revealing future cards early.

The research basis is Brown and Sandholm's
[Solving Imperfect-Information Games via Discounted Regret Minimization](https://arxiv.org/html/1809.04040):
LCFR weights both regret and strategy contributions linearly; DCFR(3/2,0,2)
uses the stated discounts and quadratic averaging. The paper's experiments use
alternating updates. The project's established `dcfr` uses simultaneous deltas
from one frozen profile, so the new explicit option is distinct from that
previously measured preset. The paper discusses additional theory issues with
alternating updates; these implementations do not transfer its convergence
guarantees or benchmark outcomes to this configured poker game.

All code is independently written for this repository from published mathematics
and existing project-owned kernels. No external implementation, dependency or
proprietary solver output is imported. Repository licensing is unchanged; this
provenance record is not a claim of patent clearance.

## Admission and metadata

Each new sweep reserves three complete passes: one own-reach average and two
player regret updates. Every existing candidate/world/tree/state/iteration guard
remains, including the 30-million world-node work limit and 250,000 prefix/pair
edge limit. New options reserve prefix edges after physical enumeration/ranking
and before tree construction; the trainer also retains its prefix cap. Positive
CFR+ averaging delay, earlier/later street starts, recursive/planned training and
flop target stopping remain outside the new options.

For the existing weighted 5,940-world game, 140 sweeps reserve
`5940 * 12 * 140 * 3 = 29,937,600` units; 141 require 30,151,440 and reject before
training. These logical work charges are separate from measured time or RSS.
Comparisons with the one-pass vanilla/simultaneous-DCFR algorithms must report
that equal sweep counts do not represent equal charged work.

Only new results identify `solver_version="configured-postflop-alternating-v1"`,
`update_schedule="alternating-oop-then-ip"`, `regret_floor=false` and
`training_passes_per_iteration=3`. The average schedule is
`linear-pre-sweep-own-reach` or `quadratic-pre-sweep-own-reach`; the regret
schedule is `linear-weighted-unfloored` or `discounted-3/2-0-2-unfloored`.
`training_kernel` distinguishes the two public Python trainers. Diagnostics
remain separately selected; default recursive diagnostics remain the reference.
The independent replay validator requires this exact new metadata contract.

## Validation and remaining evidence

[Abstract mathematical controls](../tests/test_alternating_public_cfr.py)
independently check the 2x2 utility matrix `[[1,-1],[0,2]]`. Three-sweep LCFR
pre-sweep averages are OOP `(11/24,13/24)` and IP `(2/3,1/3)`. Alternating DCFR
averages are OOP `(29/56,27/56)` and IP `(9/14,5/14)`; a separate fourth-sweep
closed form checks the positive-discount exponent. A literal weighted-world
reference checks both players, repeated own decisions, chance branches, dense
private-index holes and zero-marginal rows. The reference's opponent continuation
values are probability weighted independently from its counterfactual-reach
weights. All eight mathematical controls pass in the installed module.

[Legal poker integration](../tests/test_flop_alternating.py) independently replays
all eight diagnostics on the 5,940-world full-deck fixture and weighted selected
raised/refund games with asymmetric stacks and street-specific sizing. It checks
exact strategy equality when only diagnostics change, early scope/resource
rejection, forged new metadata, and exact legacy payload equality against the
actual archived merged adapter at source
`35a00f29f1d86d95dae218f8880f697822fac3fc6563c01824677b428f9d7891`.
That archive predates both new methods; it is project-owned source, not a
reconstructed approximation. Legacy comparison covers recursive/planned/public
training where supported, both diagnostics choices, flop/turn/river starts and
positive flop CFR+ delay. No legacy payload field changes in those controls.

The root compatibility run passed all 47 tests in 180.552 seconds, including the
mathematical and integration controls, existing independent flop validation,
historical-source checks, turn/river quality, CFR+, delays and public diagnostics:

```powershell
python -B -m unittest tests.test_alternating_public_cfr tests.test_flop_alternating tests.test_flop_multistreet_validation tests.test_historical_turn_sources tests.test_turn_river_quality tests.test_flop_cfrplus tests.test_flop_delayed_cfrplus tests.test_flop_public_diagnostics -v
```

A frozen quality experiment remains separate from those passed controls. Until
it is complete, neither new option establishes better equilibrium accuracy,
runtime or memory use. The prior CFR+ and delayed-averaging quality misses remain
the authoritative observations for those methods.
