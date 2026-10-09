# Known small-game quality gates

The standalone Kuhn reference in the existing tests checks a separate teaching
implementation. This validation instead trains the production recursive,
planned and public-batched kernels, then measures their learned policies with
an independent oracle.

Kuhn poker deals two distinct private ranks from J, Q and K. Each player antes
one chip, and one additional chip may be bet. The known first-player equilibrium
value is `-1/18`; the family of equilibrium policies is described in
[Hoehn et al., Effective Short-Term Opponent Exploitation in Simplified Poker](https://webdocs.cs.ualberta.ca/~holte/Publications/aaai2005poker.pdf),
pages 1–2. The adapter uses the repository betting builder with pot two, stack
one and a half-pot bet. It has four public decisions and twelve information
sets. Synthetic private rank indices validate the kernels, independently of
Hold'em hand evaluation or physical runout generation.

The oracle writes terminal payoffs directly from Kuhn's rules and enumerates all
64 pure private-hand-contingent policies per responding player. The responder
may condition on its own rank and visible action history; the hidden opponent
rank remains integrated. It does not use production strategy evaluation or
best-response traversal to calculate its answer. Exact rational equilibrium
profiles at three family points reproduce `-1/18` and zero improvement for both
players. A uniform-policy anchor independently gives value `1/8`, first-player
best response `1/2` and second-player best response `5/12`.

Learned policies are measured at 100, 1,000 and 10,000 iterations under vanilla
CFR and DCFR. The versioned config requires the final NashConv to be below
0.01 chips for vanilla and 0.003 for DCFR, value error below 0.001 chips, and
at least a five-fold gap reduction from the first checkpoint. Production
evaluation and best-response results must independently agree with the oracle
within `1e-12`. Exact rational replay of the represented, row-normalized float
policy separately checks the reported value's rounding error.

Run the complete quality check with:

```sh
python -m scripts.validate_cfr_quality --output benchmarks/results/cfr-quality-v1.json
```

The report records game/config/source/harness hashes, actual runtime and
environment, and every checkpoint's value error and information-set
best-response gains. Timing is a single training call, excluding oracle work;
it is not the whole-call performance benchmark. Source changes during the run
invalidate the record. Thresholds are empirical regression gates for this
known game, rather than a mathematical bound for arbitrary games.

This validates a small game's equilibrium behavior and traversal metrics. It
does not certify configured Hold'em solutions, unrestricted bet sizes,
preflop or multiway equilibrium. Independent physical-world, hidden-chance and
betting-accounting checks remain necessary for those paths. No external source
code or dependency is integrated.

## Published measurements

The [versioned report](../benchmarks/results/cfr-quality-v1.json) records 18
checkpoints at source commit `e9d9339831966cc573094d0e25f1cc79be48bdb0` on
Python 3.12.14. All gates passed. At 10,000 iterations every backend measured
NashConv approximately 0.00463557 chips for vanilla CFR and 0.00165554 for
DCFR; value errors were approximately 0.00000915973 and 0.00000116705 chips.
Production value and best-response metrics differed from the independent
oracle by at most floating-point rounding. Exact rational anchors had zero
deviation gains. The source/config hashes were unchanged throughout the run.

The report truthfully marks the checkout dirty because it contained untracked
scratch work. All validation sources and configuration were committed before
measurement; no production solver source was modified for this milestone.
Four focused quality tests passed again during takeover. The recovered prior
full-suite log records 335 passing tests in 280.180 seconds on these sources;
the publication's GitHub matrix separately checks Python 3.11, 3.12 and 3.13.
Luna independently reviewed the oracle, anchors, comparisons and provenance
without finding a blocking defect.
