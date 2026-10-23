# River original-weight tail extension: design and no-training preflight

Status: preregistered follow-up protocol. The design/admission review used no new solver or training call. Actual outcomes will be recorded separately after the executable source freeze.

## Frozen baseline and scope

The baseline is `river-heldout-quality-v1`, from source commit
`df02381625ce72d7922461b97d7c7d238258523e`. Its `report.json` has SHA-256
`5b26d6e9275b4962df4c67be1822594caa3d46291d196f863fe3b65f4353b578`.
Its `run-claim.json` has SHA-256
`f9a6bdd53d71bb4a995e3c5be5be15faa6f25f7d145dcb75e04e76900256279c`. The
four authenticated baseline policy hashes are:

| Policy | SHA-256 |
|---|---|
| Unpaired, materialized, T=10,000 | `f2e4e2d15ba9f2c65cb11e04ed2644196dd4b1df9ae03abff30a015f9f0e4cad` |
| Unpaired, matrix-free, T=10,000 | `ab9e7539cb4f424534c01a630a8f769a834273b286d258b820c976d7a41a5bc3` |
| Paired, materialized, T=10,000 | `81913dc5389c3f52a33fae67c40dc130c9768d8849835752ea087293b9381bfd` |
| Paired, matrix-free, T=10,000 | `c29c5a24f0b0a8e3f86849bc1792b2d422155aaa9b51c6815c36ae33b44c490e` |

The already-added saved-artifact regression authenticated the report/claim and
four policy byte hashes, then replayed all four saved policies through the
independent numeric and exact evaluators with solver/tree/trainer/evaluator
entry points disabled. That replay retained all four failures against the
fixed reporting threshold `1/1000`:

| Case | Backend | T=10,000 NashConv | Exact audit work / max bits |
|---|---|---:|---:|
| Unpaired blocker/tie/raise | Materialized | 0.0017425086114033483 | 4,848 / 1,812 |
| Unpaired blocker/tie/raise | Matrix-free | 0.0017425086114579713 | 4,848 / 1,863 |
| Paired short-SPR/rank extremes | Materialized | 0.0023249852685438555 | 5,115 / 1,387 |
| Paired short-SPR/rank extremes | Matrix-free | 0.0023249852685900407 | 5,115 / 1,288 |

The baseline policies remain immutable. This extension would make four new
materialized-only calls against the same two cases:

| Case | Full T | Discard D | Returned averaging window | Average weight sum |
|---|---:|---:|---|---:|
| Each frozen case | 10,000 | 5,000 | 5,001 through 10,000 | 37,502,500 |
| Each frozen case | 50,000 | 25,000 | 25,001 through 50,000 | 937,512,500 |

The existing adapter uses original sweep weights `t`, not `t-D`. The
predeclared acceptance target remains exact NashConv `<= 1/1000`, for reporting
only; it does not stop training. Preserve and publish every miss. These runs
do not compare equal training budgets: T=50,000 performs five times the full
regret sweeps of the old T=10,000 baseline. Tail averaging may improve or may
not; no improvement is assumed, and no runtime or speed claim follows from
these budgets.

## Source-backed resource check

The adapter is `pokerlab/river_tail_adapter.py` at the baseline commit; its
frozen report records normalized-LF SHA-256
`0963a8df65d432415157a164618923bd2fcfede98ef0ed328ea8f1867e384e7d` and Git
blob `edbae3538470067317c2996a92fb21f4c02a7911`. The adapter admits
10 through 100,000 iterations and passes the full requested T to
`_enumerate_worlds` and all subsequent guards. It does not discount admission
cost by D.

The frozen preflight/report gives four private hands per player, 14 compatible
physical pairs/worlds for the unpaired case, 15 for the paired case, 10
world-traversal nodes, 10 public decision nodes, 27 public states, 40
information sets, and 26 public tree actions. The 10,000-sweep reports show
materialized world-node work of 4,200,000 and 4,500,000 respectively and dense
hand-state work of 3,240,324 for both. Applying the adapter's source formulas
to T=50,000 gives:

| Guarded quantity | Unpaired case | Paired case | Existing limit |
|---|---:|---:|---:|
| Candidate private-hand products: 4 x 4 x T | 800,000 | 800,000 | 3,000,000 |
| Compatible worlds x T | 700,000 | 750,000 | 3,000,000 |
| World-node work: worlds x 10 x T x 3 | 21,000,000 | 22,500,000 | 30,000,000 |
| Dense hand-state passes: 4 x 27 x (3T + 3) | 16,200,324 | 16,200,324 | 30,000,000 |

These are modeled source-guard quantities, not timing or memory measurements.
Tree dimensions and info/action counts do not depend on T; the recorded 40
information sets and 26 actions imply at most 104 action slots with four hands
per player, well below the 1,000,000 cap. The old 250,000 prefix-edge cap and
all public-tree/world/fallback caps remain in force. A future runner must
recompute and record fresh preflight values for all four calls at the exact
requested T before creating the run claim; this projection does not replace
that gate. The fixed v1 baseline preflight and source receipt must be
authenticated before any new attempt starts.

## Harness boundary and evidence requirements

The frozen `scripts/benchmark_river_heldout_quality.py` is intentionally
fixed to T=10,000. In particular, `_audit_policy` rejects any other iteration
count, so it cannot validate T=50,000 by simply being called unchanged. Leave
the old runner, report, claim, and policies unchanged. A separate extension
wrapper/auditor should accept only the four fixed `(case, T, D)` tuples above,
call the existing research-only `pokerlab.river_tail_adapter.solve_river_tail`
with no target/checkpoint feature, and reuse the existing independent
`turn_river_validation` and `turn_rational_certificate` numeric/exact rules.
It should parameterize only expected iteration metadata; it must not reuse
production tree construction, solver utility evaluation, or trainer output as
the independent oracle. Save complete LF policies with raw-byte hashes, then
reload and replay each saved file, compare all eight numeric metrics within
the declared `1e-9` tolerance, and require exact scan/partition equality,
response interval identities, physical counts, work/depth/bit caps, and the
unchanged `1/1000` target result. Preserve each target miss and each failed
attempt. Keep source/policy/report artifacts and the new run claim separate
from the frozen v1 corpus.

No claim about a general game, unrestricted Hold'em, or convergence follows
from these two finite configured games.

## Fixed execution and acceptance

Authenticate the [complete immutable baseline](../benchmarks/results/river-heldout-quality-v1/report.json) and all four original saved policies through independent numeric/exact replay before starting this new study. The new source snapshot must include the unchanged v1 benchmark helpers and every production module, plus the new runner and this protocol. Match working bytes to the explicit clean committed source, keep baseline bytes fixed and check source before/after every call and saved reload.

The new batch has a distinct exclusive claim and output directory outside its source checkout. Preserve raw complete canonical LF returns before replay and retain partial failures without retry. Every returned tail must disclose the exact requested T, D, source window, triangular original-weight sum and actual regret/average pass schedule; full-request admission never shrinks with discard. All four candidates must pass the original guards before the first trainer.

Validate each serialized policy from independent physical worlds/ranks, numeric betting rules and legal own-hand responses. Use the existing exact normalized-binary64 scan/partition helper under its unchanged work/depth/Fraction-bit caps. The exact target flag comes from Fraction NashConv<=1/1000, with numeric flags separate and null exact results on explicit admission misses. Saved replays must reproduce every available exact metric/interval/count. Neither unchanged priors nor agreement with a prior policy supplies a separately known equilibrium value.

This is an evidence-guided follow-up on the same cases, rather than a new held-out case sample. Preserve the four original misses alongside all new outcomes. The higher-budget profiles and different average windows do not establish an equal-cost method comparison or a general convergence guarantee.
