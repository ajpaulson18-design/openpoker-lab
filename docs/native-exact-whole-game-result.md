# Native exact four-street integration: frozen results

The [integrated backend](native-exact-whole-game.md) runs exact blocker-conditioned
normalization, physical ranking/payoffs, procedural suit-orbit planning and all
alternating CFR+ phases in one native process. It uses no materialized private-pair
or complete-world table. Python legal preparation, independent diagnostics and
expanded policy output remain part of the complete solve.

## Two separate committed-source studies

The fixed runner completes all 18 prescribed fresh children in each study, without
retry. The first source is `52aa21f343aa769c4aeabf6fb7eb7c6be6816f96`;
the corrected source is `c6508947ad12a51db87bf2b41616c966ee5d339a`.
The latter replaces implicit byte-vector comparisons with an explicit bounded
lexicographic comparator after Ubuntu GCC 13 rejects the former under strict
warnings. Both compiler failures and their complete artifacts are retained.
No warnings were disabled. Each source has its own build, measurements and replay;
the two batches do not establish a performance difference between source versions.

| Complete-call measurement | First source | Corrected source |
| --- | ---: | ---: |
| Python original-22 T10 median, three calls | 6.961624 s | 9.497666 s |
| Native original-22 T10 median, three calls | 1.491316 s | 2.398221 s |
| Python separate traced allocation peak | 3,271,804 bytes | 3,272,783 bytes |
| Native-mode separate traced Python allocation peak | 4,903,906 bytes | 4,922,742 bytes |

The corrected-source ratio is about 3.96 for this frozen fixture only. Timing
includes complete API work and canonical result serialization/hash; compilation
and independent replay are excluded. The observer retains native wire bytes
through diagnostics. Python allocation tracing includes those bytes and excludes
native heap. Python child lifetime process peaks are separate recorded values,
not whole-solve RSS. No total-memory reduction or general speedup is established.

Each batch has eight complete Python/native policy pairs with bitwise-identical
probabilities, menus and all eight numeric diagnostics. Separate exact-certificate
metrics and threshold flags agree. Sixteen independently reconstructed saved-only
policy/visible-information best-response replays pass, with maximum numeric gap
8.326672684688674e-17. Fourteen T10 policies miss the unchanged exact 1/1000-BB
quality target; only the two private-flush T100 policies pass. Original T1000
requests in both modes reject before ranking, training or native launch, with
quality absent. Capacity rejection is not a solved result.

Source authentication checks all 2,031 captured raw/Git files before mathematical
imports and checks them again afterward, plus the complete build/dependency closure
and immutable artifacts. Review makes zero candidate/native calls. A separate
cross-source receipt confirms identical eight native policies and diagnostic bits;
it makes no timing or memory comparison.

## Independent input and structural checks

The native wire is checked against independently reconstructed physical priors,
legal decisions, visible histories and whole-hand terminal money. Strict graph
isomorphism fails: native/Python preparation explicitly reveals remaining cards
after an all-in while the independent numeric model settles early. The original
strict failure and all 32 original-fixture frontier differences remain archived.

The accepted, narrower proof checks every such tail: no further decision, correct
ordered positive physical branch partition, unique compatible-world leaf, unchanged
terminal kind/winner/contribution bits, and equal exact per-private-pair mass and
payoff sum. This establishes physical-game equivalence for these tails. It does
not establish identical branchwise rounded callbacks or training trajectories
between the different graph representations. The producer comparison uses the
same explicit graph. The independent model has no `full_raise` classification;
that wire Boolean is structurally/source authenticated, not independently derived.

The original game retains 1,200 physical rows and 2,402 action slots with identity
stabilizer, so Q storage gives no symmetry saving there. Private-flush and blocker
fixtures have two-member orbits; mixed stabilizer has both one- and two-member
orbits (28 physical rows, 16 Q rows, 33 Q slots). Four Q action buffers are used
during learning, then three buffers and phase masks are released before streaming
expanded rows. Whole-request work, storage, exact-integer payload, callback and
transport guards remain binding. These structural counts are not allocator bytes.

## Preserved evidence and review scope

The [publication manifest](../benchmarks/results/native-exact-whole-v1/manifest.json)
indexes both lossless archives and compact reports/receipts. Archives contain the
full raw policies, requests/stdout/stderr, source captures, build manifests/logs,
fresh independent certificates, reviewer helpers, first failures and later fixes.
Historical archived source is evidence only; reviewers never execute it.

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| [First source](../benchmarks/results/native-exact-whole-v1/native-exact-whole-evidence-v1.zip) | 9,757,262 | `a79accd124248fdf0a02328b00a81923690143952d608caad6c7bdc06640f507` |
| [Corrected source](../benchmarks/results/native-exact-whole-v1/native-exact-whole-evidence-v2.zip) | 7,163,502 | `d9ec90169f9406d54daa42b4a6a39241f364cddfc6701a77dcc9a51ac0f14d1b` |

Sol reviews architecture and corrects trainer admission; Luna implements the graph;
Terra finds graph/admission defects and independently completes saved-policy and
physical input-tail proofs. Root integrates the API/process, fixes cross-platform
comparison, and packages both studies. Terra's second direct CFR source audit was
usage-limited; saved-only proof completion must not be relabeled as that audit.
Early summarized development failures with unavailable raw streams remain marked
as capture gaps. The first packaging assertion error is preserved separately;
no producer was rerun because of reviewer or packaging failures.

Corrected-source dedicated CI passes actual Windows/Linux builds and Linux
ASan/UBSan controls. Final publication-head CI and merge provenance are checked
separately. Optional skipped AI review is not a completed review.

## Next limiting structures

This is a bounded, selected-runout four-street integration. Full-deck chance,
commercial accuracy and unrestricted NLHE remain unsupported. Asymmetric/history
strategy growth, expanded Python output/diagnostics, conservative work admission,
duplicate preparation, complete-process memory measurement and scalable independent
certification remain open. The larger original T1000 work rejection and preserved
quality misses guide the next integration work. The overall foundation goal stays
active; the benchmark does not complete it.
