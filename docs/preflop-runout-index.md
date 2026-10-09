# Indexed blockers for selected preflop outcomes

The preflop physical-world enumerator indexes selected outcomes by card before
counting or building worlds. For each four-card private pair, the union of four
card postings identifies blocked outcomes. Complementing against the bounded
selected-outcome mask gives the exact valid set; `bit_count()` counts it without
a Python disjoint-set test for every pair/outcome. Enumeration scans packed
bytes and their set bits in ascending canonical index order, preserving ordered
turn/river outcomes and the previous world/ranking/normalization order.

This is deterministic exact blocker filtering, not chance sampling or an
approximation. Private-pair conditioning, showdown signs, range weights,
probabilities, learned policies and legal best responses remain unchanged.
There is no new solver argument or result field.

## Admission and storage

The existing candidate-pair, world-iteration, selected-outcome, public-tree,
vector-work and ranking preflight limits remain unchanged. Each private pair
still incurs the original `len(selected)` logical admission charge before
counting its valid worlds, followed by the same world-iteration guard. The
existing `pair_runout_preflight_checks` field records this conservative charge;
it no longer denotes actual Python disjoint-set calls. No 30-million admission
ceiling is raised or replaced. World/rank arrays are allocated only after the
exact valid-world count passes admission.

The index validates at most 300,000 canonical outcomes and builds 52 bytearray
postings, then converts each to an integer. Building bytes avoids repeatedly
copying ever-growing integers once per input card. Each posting has at most
`ceil(N/8)` packed bytes. At the maximum input size the logical packed payload
is 1,950,000 bytes. The conversion overlap estimate doubles that payload only;
it excludes Python integer limb padding, headers, the helper's bounded
normalization and duplicate-validation data, the all-outcomes mask and query
scratch. It is not an allocation or process-memory bound.

The index retains no normalized runout copy after construction and stores no
private-pair masks across all pairs. One query creates bounded temporary masks;
index enumeration scans at most `ceil(N/8)` bytes plus the returned valid bits.
The index is released before final world normalization. Candidate/world/tree
storage has its own existing limits. Index-only traced memory is measured
separately rather than inferred from packed payload estimates.

## Verification and benchmark scope

Six helper tests compare counts, masks and index order against independent
brute-force filtering over reproducible randomized inputs. They cover dense,
sparse and partial final bytes, swapped future cards, malformed/duplicate cards,
noncanonical flops, and capacity rejection before posting allocation. Five
integration tests compare every returned enumeration field exactly against a
test-only scalar disjoint-set reference, including all 7,920 complete-fixed-flop
worlds and four pair probabilities. All three training algorithms retain exact
policy/result equality in a weighted hidden-information fixture; independent
configured policy replay verifies values and both legal best responses. Early
preflight/world guard ordering and wholly blocked rejection are tested before
ranking. Twenty-four focused helper/integration/related preflop tests pass.

The [specification](../benchmarks/preflop-runout-index-v1.json) compares three
alternating paired calls for physical enumeration on the complete four-pair
fixed-flop fixture, a fully blocked preflight at exactly 30 million logical
checks, and a small weighted complete solve. The scalar reference retains both
original Python disjoint-set blocker scans inside the new integration. It is
not a separate historical checkout, and digest parity is a differential check,
not an independent proof of the shared ranker or training algorithm.

The blocked fixture has one SB hand `AsAd`, 300 compatible BB combinations and
100,000 unique selected outcomes containing `As`. Both paths reject with no
compatible physical deals and never rank cards. Its timing measures preflight
scalability, not a solved game. The other fixtures exercise admitted worlds and
an independently replayed complete solve. A blocker-heavy speedup does not imply
a faster whole solver when training dominates or the input is small.

Timings include input normalization, ranking when applicable and JSON
serialization. Explicit pre-call GC and independent replay are excluded. Three
paired medians on one shared host support fixture-specific observations only.
Memory tracing covers a separate index construction and blocked-count query
with 100,000 canonical outcomes already allocated, including helper validation,
postings and conversion. It excludes solver input normalization, worlds/ranks,
tree, training, diagnostics and RSS; no whole-solve memory reduction is claimed.

```text
python -m unittest tests.test_preflop_runout_index tests.test_preflop_indexed_worlds -v
python -m scripts.benchmark_preflop_runout_index
```

## Recorded observations

The [report](../benchmarks/results/preflop-runout-index-v1.json) passed at frozen
source `2eb9f6276e7d0ebe36076d2d8af9e24ff6a46548` on Windows/Python 3.12.14,
starting with a clean worktree. All 20 listed source hashes and the configuration
hash stayed fixed. Exact serialized result digests matched at every paired call.

| Scenario | Scalar / indexed median seconds | Scope |
| --- | ---: | --- |
| Four private pairs, complete fixed-flop enumeration | 0.436 / 0.372 | Setup and serialization, not training |
| Exactly 30 million logical checks, all outcomes blocked | 21.061 / 3.090 | Same rejection before ranking |
| Weighted selected-game complete CFR+20 solve | 0.200 / 0.161 | 214 policy rows independently replayed |

The blocked-case median ratio is approximately 6.82; its samples are
20.824/21.061/21.922 seconds scalar and 3.090/3.216/2.969 indexed. This supports
substantially cheaper preflight on this blocker-heavy fixture, not admitting or
solving a larger game. Raw small complete-solve samples overlap substantially;
its median ratio should not be interpreted as an established solver speedup.
The small game's independent scalar differences are zero and its legal deviation
gap is zero, which verifies that fixture rather than broad convergence quality.

The 100,000-outcome index construction/query traced peak is **13,923,944 bytes**,
including helper normalization and duplicate-validation scratch. Its packed
posting payload is 650,000 bytes and logical conversion overlap 1,300,000 bytes.
The measured peak is much larger than those payloads, demonstrating why they
are not allocation bounds. Existing canonical solver input was allocated before
tracing; whole-solve allocations and RSS remain unmeasured by this trace.

## Provenance and limits

Luna independently authored the standalone bitset helper and randomized tests.
Lead review removed retained normalized inputs, clarified logical-payload versus
actual allocation accounting, integrated filtering and supplied independent
replay tests and the frozen paired benchmark. Luna reviewed integration and
measurement scope. This is an independently written standard-library indexing
technique; no third-party source, dependencies, commercial outputs or trained
policies were incorporated. The shared CFR, postflop, turn/river, public
diagnostic and AI Coach production files remain unchanged by this slice.

The work builds on main after the parallel turn/river publications and PR77.
Twenty-seven existing preflop delay/resource compatibility tests passed on that
updated main before implementation. The earlier delayed fixed-flop convergence
report stays tied to its recorded source and is not rebranded as a new
performance measurement. Broader full-deck preflop, practical ranges, multiway
and unrestricted action solving remain outside the supported finite games.
