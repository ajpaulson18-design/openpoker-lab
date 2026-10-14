# Longer-budget full-deck turn-to-river accuracy

## Fixed model and experiment

The [selected-runout experiment](turn-selected-accuracy.md) and its
[normalized rational certificates](turn-rational-certificate.md) do not measure
full remaining-deck turn quality. This slice returns to the existing
`full44-blocked-runouts` fixture, with every physically possible river after
each compatible private deal. It changes no production solver or earlier-street
source.

Freeze turn `Js8d4c2h`, OOP `AsAh:0.5,KsKh:1`, IP
`AcAd:1,KcKd:0.75`, pot 100, stack cap 220, one 0.75-pot opening size,
no raises and no optional all-in action. Turn and river use that same sizing
configuration. Both existing materialized/public-batched and matrix-free
backends run CFR+ for fixed 1,000, 1,500 and 3,000 completed sweeps. No solver
stopping target is configured. Keep every meet/miss of the predeclared
0.001-chip **NashConv** reporting threshold, distinct from exploitability,
which is half NashConv.

The input omits `runouts`, preserving full-deck semantics. There are 48 public
candidate cards outside the four-card board. Once a compatible pair of private
hands is fixed, four more cards are blocked, leaving 44 equally likely rivers
for that pair. Four compatible pairs therefore create 176 physical worlds.
The union of reachable river cards across these pairs is all 48 candidates;
neither 48 rivers per pair nor 44 globally reachable cards is the correct count.

## Admission and validation boundaries

The fixture has 1,112 information sets and 1,305 aggregate public states,
including chance and terminal states. Its independent validator counts 580
decision nodes; conservative replay admission is `580*176*4 = 408,960`, below
its existing 8-million modeled-work cap. The materialized solver's per-world
traversal count is 16. These three different tree dimensions must not be
substituted for each other.

| Sweeps | Matrix-free fixed hand/state work | Materialized fixed world/node work |
| --- | ---: | ---: |
| 1,000 | 7,837,830 | 8,448,000 |
| 1,500 | 11,752,830 | 12,672,000 |
| 3,000 | 23,497,830 | 25,344,000 |

Matrix-free work is `2*1305*(3*T+3)`, with at most two original hands, three
CFR+ passes per sweep and one final diagnostic. Materialized work is
`176*16*3*T`. Both remain under their unchanged 30-million limits at every
requested budget. Other public-state, hand-slot, action-slot and fallback
limits remain enforced. These are existing modeled-work guards, not CPU
instruction or memory/RSS bounds.

Before the fixed experiment, actual loose-target admission probes requested
all three ceilings on both APIs and stopped at ten sweeps. The matrix-free
3,000-ceiling probe reserved 25,846,830 work because target mode plans repeated
diagnostics. That is admission evidence only, not a completed long solve, and
does not replace the fixed-call 23,497,830 work charge above.

The new [runner](../scripts/benchmark_full_deck_turn_accuracy.py) freezes the
fixture, both backends and all three budgets. It checks complete sweeps, absence
of a stop target, exact full-deck board/runout declarations, either existing
canonical reachability order, both street configurations, algorithm schedules,
physical counts and backend-specific work/limits. It independently replays all
eight metrics and complete rows/actions using the unchanged numeric-rule,
physical-card, independent-rank and legal visible-information response oracle.
Replay also omits `runouts`; a manually selected substitute is rejected.

Each complete result is saved as portable UTF-8/LF JSON, byte-hashed, reloaded
and independently replayed again. The runner's own source and all protected
production/helper/fixture fingerprints must remain unchanged across the grid.
Single complete-call timings are uncontrolled shared-host observations. They
are not a speed comparison, performance improvement or memory measurement.

## Executed evidence

| Backend | 1,000-sweep independent NashConv | 1,500-sweep independent NashConv | 3,000-sweep independent NashConv |
| --- | ---: | ---: | ---: |
| Materialized/public-batched | 0.0014533696435989896 | 0.0006461572343958721 | 0.00016159313709351864 |
| Matrix-free | 0.0014533696436025423 | 0.0006461572343994249 | 0.00016159313709351864 |

Both 1,000-sweep profiles miss the unchanged 0.001 reporting threshold. Both
backends meet it at 1,500 and 3,000: four meets and two misses, all retained.
Each result completes exactly its requested fixed sweeps, with no stop target.
The [complete report](../benchmarks/results/full-deck-turn-accuracy-v1.json)
records all eight metrics and replay differences, physical/public dimensions,
backend work charges, all 53 protected source fingerprints, policy hashes and
raw uncontrolled single-call times. The
[policy folder](../benchmarks/results/full-deck-turn-accuracy-policies-v1)
holds all six complete portable LF JSON profiles.

Every profile passes independent replay before saving and after reloading.
Sol separately reloaded all six policies in another process, verified LF bytes
and raw hashes, replayed all eight metrics, reconstructed the physical deal law,
checked exactly 44 rivers for each of the four private pairs and unit total
exact Fraction mass, and verified all 53 source fingerprints. Maximum absolute
disagreement across all eight metrics is `2.842170943040401e-14` chips. All six
backend-specific work charges match the formulas above and stay within the
existing caps.

All 24 focused tests passed: six new harness tests and eighteen existing
independent replay tests. The harness caches actual ten-sweep profiles from
both APIs, then mutates copies to reject wrong full-deck conditioning, sizing,
counts, work/limit aliases, bool counts, policy rows and stopping targets.
Tests explicitly distinguish the three tree dimensions and accept both existing
canonical reachability orders. Sol ran the new six-test harness separately
before the long grid, then reran the combined suite against the final sources.

The raw materialized 3,000-call wall time is an extreme outlier,
`5669.696428199997` seconds, versus 33.18/51.91 seconds for its 1,000/1,500
calls. It is retained unchanged. The long session also experienced an agent
application-permission interruption; the original benchmark process survived
and was recovered rather than restarted. The cause of the wall-time outlier
was not independently established, so these observations support no runtime
comparison. The three matrix-free times are also uncontrolled single-call
observations, rather than speed evidence.

Baseline is merged main `825ae45fcf8b9b858be8b4dd422b1645f11e7cbb`. No production,
shared, earlier-street or old policy source changed. Only the new development
runner/tests, six policies, report and canonical documentation were added.

Reproduction:

```text
python -m unittest tests.test_benchmark_full_deck_turn_accuracy tests.test_turn_river_independent_validation
python -m scripts.benchmark_full_deck_turn_accuracy
python -m scripts.validate_docs
```

The model integrates the full remaining deck within one finite heads-up betting
abstraction and two weighted hands per range. It does not solve unrestricted
Hold'em, establish general convergence, or supply a closed-form game value.
The existing exact rational auditor remains pinned to the six earlier selected
policies; this slice does not silently extend that certificate's model scope.
A subsequent, separate [full-deck rational audit](full-deck-turn-rational-certificate.md)
now adds exact normalized legal-response bounds for these six saved policies.
