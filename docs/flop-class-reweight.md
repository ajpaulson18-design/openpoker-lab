# Fixed-support flop prior reweighting

This separate research path changes positive private-hand weights on the same
fixed flop card support and action tree. It is a **no-training** proof milestone;
no newly weighted equilibrium, convergence, speed or unrestricted NLHE claim
follows from the planner or synthetic tests.

## Model and early admission

The board is `2c3d4h`, OOP hands are `AsAd` / `QsQd`, and IP hands are `AsKh` /
`KsKd`. Pot 10, stack 5, half-pot betting, no raises and no optional all-in keep
the existing fixed numeric flop/turn/river tree. Existing street kernels and
Coach are unchanged. The overlapping `AsAd` / `AsKh` pair is removed before
one global normalization of the remaining hand-weight products.

The rank-free planner accepts two exact two-tuples of positive integers or
`Fraction` values; bools, floats, strings, zero, negatives and changed supports
are rejected. Input numerator/denominator components have at most 128 bits.
The common denominator of all normalized per-runout masses must fit the
unchanged 384-bit candidate envelope before any physical preparation. This
extra condition can reject otherwise valid 128-bit inputs. Planning establishes
neither card-ranking provenance nor quotient equivalence.

| Frozen case | OOP weights | IP weights | Global blocker normalizer | Compatible pair priors |
| --- | --- | --- | --- | --- |
| Baseline | 1, 1/2 | 1/4, 1 | 13/8 | 8/13, 1/13, 4/13 |
| Uniform | 1, 1 | 1, 1 | 3 | 1/3, 1/3, 1/3 |
| Skew | 4, 1 | 4, 1 | 9 | 4/9, 4/9, 1/9 |

Pair order is `AsAd`/`KsKd`, `QsQd`/`AsKh`, `QsQd`/`KsKd`. Physical records
canonicalize each hand's card order (for example `AsAd` becomes `AdAs`), while
retaining roles and physical identity. Every compatible pair has 45 x 44 =
1,980 ordered future reveals: 5,940 worlds in each full physical game.

## New-prior proof boundary

`WeightedClassModel` is distinct from the published old-prior `ClassModel`.
It holds a genuine authenticated old physical baseline and a separately built
weighted physical oracle. It checks exact world mass `pair_prior / 1980`,
normalizer, complete support, showdown signs, pair outcomes/probabilities,
source counters derived from support, numeric tree, node index and own-hand
visibility. The old world SHA authenticates the genuine baseline only; each
weighted oracle has its own reported world SHA.

A fresh candidate partition is independently checked against every weighted
physical row, per-pair river signature, turn posterior and reveal transport.
All 30,812 numeric public states are compared during collapse. Every model
consumption reauthenticates its physical data and rebuilds the quotient; it does
not rank the deck again. The admitted compact shape remains 126 worlds, 1,001
public states and 466 policy rows, versus 16,912 physical policy rows.

Four deterministic controls (`check-call`, `bet-fold`, `class-varying`,
`zero-reach`) exercise projection/lift and off-path responses. The audit requires
all eight exact compact metrics to equal unrestricted physical own-hand best
responses, independent numeric replay within 1e-10, and a bitwise policy lift
round trip. Hidden opponent hands and future cards are integrated before a
legal response maximizes. The old baseline controls must reproduce their
published exact metrics, class policy and physical strategy hash. Controls are
not trained strategies and have no equilibrium-quality target.

## Frozen execution and retention

The [protocol](../benchmarks/flop-class-reweight-proof-v1.json) admits all three
plans before any ranking, cheaply authenticates the immutable old proof and
preserves its interruption record. The single batch uses one baseline oracle
plus three independently prepared weighted oracles, for 23,760 enumerated
world rows and 12 control audits. At most the baseline and current case's
physical oracle are retained; references are released and GC runs between cases.
These are census/capacity admissions, not complete arithmetic/CPU, allocated
memory, elapsed-time or RSS bounds. Existing physical oracle caps remain intact.

The run requires clean committed source, with exact revision/status/LF manifests
before and after each case and overall. It reserves a new directory outside
source, saves active work before execution, and writes three preparation and
12 complete physical-policy/audit gzip files with raw/compressed hashes.
Failures retain partial files and tracebacks, stop later work and never retry.
The compact index omits duplicated policy rows but the complete rows remain in
the bounded gzip artifacts. All 41 forbidden production authorities must have
exact integer zero counters; no trainer is called. Wall/CPU/UTC/runtime and the
temporary Windows execution-state request are incidental receipts only.

## Completed no-training evidence

The single frozen batch completed on 2026-10-22, from 12:41:28.985926 to
13:02:04.497087 UTC on CPython 3.12.14 / Windows. Source checkpoint
`b43bacbf2bd19b37ac6c7b0f8d4d5b115f9d2e13` and all 26 LF source identities
were clean and stable before/after every case and overall. All three cases and
12 controls completed, with zero errors, retries, discarded cases or training
calls; all 41 forbidden-authority counters are exact integer zero. All eight
compact/physical exact metrics matched in every control. Maximum independent
numeric replay gaps were 8.882e-16 (baseline), 1.777e-15 (uniform) and 8.882e-16
(skew). Every class-constant policy passed a bitwise physical lift round trip.

The [immutable index](../benchmarks/results/flop-class-reweight-proof-v1/index.json)
registers three complete preparation and twelve full physical-policy/audit gzip
files, totalling 1,238,567 compressed bytes. Raw index SHA256 is
`4fe70ce71d09b5c41816917e2297ab8027e0f2b5c3e536ff6b473c3e695136f6`;
canonical unsigned index SHA256 is
`166e877f68cc8ab7cf027ce6e80e18eb4ec952b5918aa26c85e4076bf6185dcb`.
Each gzip has its compressed/raw size and hash retained. The index also retains
actual world hashes, source manifests, exact plans, sign counts, complete census,
per-control summaries, wall/CPU intervals and execution-state/runtime receipts.
The 1,235.511555 s wall / 936.562500 s process totals are incidental execution
receipts, not a performance comparison or resource guarantee.

These deliberately untrained controls retain the following exact NashConv values;
they have no convergence-quality target:

| Control | Baseline | Uniform | Skew |
| --- | --- | --- | --- |
| check-call | `4534/1287` | `1619/594` | `673/162` |
| bet-fold | `599/143` | `170/33` | `251/99` |
| class-varying | `268531/119808` | `100459/33792` | `2177405/912384` |
| zero-reach | `10` | `10` | `10` |

Authenticate the immutable saved publication from a clean checkout:

```console
python -B -m scripts.verify_flop_class_reweight_publication
```

This bounded verifier checks immutable bytes/hashes, exact inventories and plans,
source identities, historical anchors, metric identities/gaps and all zero
counters. It performs no ranking, tree construction, fresh policy replay or
training. Its successful saved verification is separate from the physical proof
performed during the batch. A reproducible optional fresh replay follows below.
No third-party source or dependency was incorporated. See the [licensing boundary](research/LICENSING.md),
[old quotient proof](flop-public-classes.md),
[primary cost study](flop-class-call-cost.md) and
[phase attribution](flop-class-phase-profile.md).


## Optional fresh replay of one saved reweight control

The publication verifier authenticates the saved bytes, exact prior metadata,
audits, source snapshot, and historical baseline. Its command does not prepare
physical worlds, rank hands, build a tree, replay a strategy, or train. A fresh
physical replay is a separate opt-in check and can take minutes because it
repeats ranking and unrestricted best-response work.

This example replays only the saved `uniform-check-call` payload. Run it from a
clean repository checkout with the published immutable pins:

```python
from scripts import benchmark_flop_class_reweight as runner
from scripts import flop_class_reweight_proof as reweighted
from scripts import flop_public_classes as proof
from scripts import verify_flop_class_reweight_publication as publication

_, index = publication._read_index(publication.PUBLICATION / "index.json")
file_row = next(row for row in index["files"]
                if row["path"] == "uniform-check-call.json.gz")
_, saved = publication._read_gzip(publication.PUBLICATION, file_row)
plan_by_id = dict(runner._plans(runner._protocol()))

with proof.independent_guard() as production_calls:
    model = reweighted.build_model(plan_by_id["uniform"])
    replayed_audit = reweighted.audit_policy(saved["payload"], model)

assert runner._valid_guard_census(production_calls)
for field in ("exact_metrics", "exact_metric_count", "physical_rows_lifted",
              "class_rows", "physical_strategy_sha256", "class_policy"):
    assert proof._typed(replayed_audit[field]) == proof._typed(saved["audit"][field])
```

`build_model` creates fresh baseline and uniform physical oracles. The guarded
audit independently checks the weighted quotient and unrestricted physical
policy, then the comparisons bind the replay to the saved exact metrics, full
class policy, lifted row count, and physical strategy digest. This replay was
not performed by the saved-publication verifier.
