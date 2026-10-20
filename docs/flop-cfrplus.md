# CFR+ for full-future flop starts

The flop adapter now permits the existing alternating CFR+ kernels through
`solve_postflop(..., algorithm="cfrplus", traversal="recursive")` or
`traversal="public-batched"`. It uses the existing physical ordered future
worlds, blocker-conditioned joint weights and own-hand/public-history keys.
All 20 saved full-deck candidate policies pass independent replay; both final
140-sweep backends still miss the original 0.005-chip NashConv target.
It does not change the default vanilla algorithm or recursive diagnostics.

The implementation removes the flop-only rejection from the adapter. Shared
CFR/CFR+ trainers, rules, ranking, evaluation and turn/river code paths remain.
The original 30-million world-node admission already reserves three training
passes per requested CFR+ sweep: OOP update, IP update, and completed-sweep
linear own-reach averaging. Every old world/candidate/tree/public-state guard
remains, as does the public trainer's separate prefix-edge guard. No new request
is admitted by weakening any cap. Planned CFR+ traversal, flop public diagnostics
and flop target-based early stopping remain explicitly unsupported.

For the independently checked weighted 5,940-world fixture in
[the baseline experiment](weighted-full-deck-flop.md), the public tree has 12
decision visits per world. A full 140-sweep CFR+ request reserves
`5940 * 12 * 140 * 3 = 29,937,600` world-node units and fits. A 141-sweep
request requires 30,151,440 and rejects before either trainer. This is a logical
admission count, not a timing or RSS bound. All policies still optimize a finite
configured heads-up game, not unrestricted NLHE or multiway equilibrium.

[Integration tests](../tests/test_flop_cfrplus.py) compare both trainers against
the independent physical/numeric all-street validator on full-deck and weighted
conditioned raised games. They cover cumulative street sizing, refunds and hidden
future information; check full requested three-pass admission; preserve explicit
unsupported options; and compare sixteen legacy flop/turn/river payloads plus the
default invocation against checksum-authenticated pre-change adapter source.
An updated prior rejection test retains the unchanged deeper full-deck tree cap.

## Frozen validation design

The completed frozen comparison retains the same weighted full-deck game and
0.005-chip final NashConv target, with CFR+ checkpoints 10/50/140 and three paired
recursive/public-batched repeats. Full profiles require independent physical
sign/prior/action/own-hand response replay. Complete-call time includes setup,
training, exact diagnostics and canonical serialization/hash; separate short
allocation calls stay out of timing medians. Preserve every profile and miss.

The baseline's vanilla/DCFR 400-sweep request and CFR+ 140-sweep request both
fit the unchanged 30-million cap, but their charged work differs (28,512,000
versus 29,937,600). They must not be described as identical work budgets.
Hardware and interpreter differences must be disclosed; cross-host timing is
not a controlled speed comparison. The source, baseline evidence and protocol
will be pinned before measuring the new candidate.

CFR+ uses established regret-matching-plus and strategy averaging concepts from
[Tammelin, 2014](https://arxiv.org/abs/1407.5042), implemented independently in the
existing project kernels. No external source, solver dependency or proprietary
result is incorporated. This adapter change does not itself establish improved
convergence, broad stack/range coverage, sampling, native chance traversal or RSS.

## Historical turn evidence

The adapter's new bytes differ from the source recorded in four immutable
turn-proof bundles. Their policies, reports, original source identities and
quality gates remain byte-for-byte preserved. Historical replay admits only the
seven exact old/current SHA256 pairs in
[the transition registry](../scripts/historical_turn_sources.py): the flop-only
adapter admission and the four verifier edits needed to compare that explicit
transition, and two synthetic test fixtures updated to use approved protected
source endpoints rather than arbitrary dummy hashes. Other mismatches still reject, including a re-signed unknown adapter
hash, missing sources and a reverse transition. New measurements and operation
guards retain actual current hashes; historical compatibility does not assert
source byte equality. Complete no-training replay and witness reconstruction
remain required. [Regression tests](../tests/test_historical_turn_sources.py)
authenticate the current files and reject unregistered changes.

## Frozen candidate protocol

[The CFR+ protocol](../benchmarks/weighted-full-deck-flop-cfrplus-v1.json) freezes
10/50/140 sweeps, three alternating recursive/public-batched pairs, separate
10-sweep allocation calls, and the original 0.005-chip final gate. Its canonical
SHA256 is `035b8c8732741311a7166163516cd710c4471c1fe4776c67b0c00441db618461`.
[The runner](../scripts/benchmark_flop_cfrplus.py) requires the completed baseline
bundle first, authenticates its 3963e3c source revision and full 584-file source
manifest, independently replays all 38 baseline policies, and pins its immutable
index and final quality observations. A baseline quality miss is retained and
allowed; incomplete or altered evidence refuses before candidate ranking.

The runner admits 29,937,600 charged world-node units and 6,078 public prefix/
private-pair edges before ranking. It retains 18 timed policies, two separate
allocation policies and two physical-world records, with lossless hashes and
source-before/source-after identity. Saved reconstruction repeats the independent
physical/action/own-hand response checks for every policy and reauthenticates the
baseline bundle. Completed measurements and their original quality misses are retained below.

The baseline prerequisite also binds the published raw index SHA256
`8d259315fcc280020bf59039d5557620f0115efd05ee2996627dad14c28d7b88`
through the [publication verifier](../scripts/verify_weighted_flop_publication.py).
A re-signed replacement observation still refuses before candidate ranking; the
candidate cannot quietly substitute a different baseline timing or quality record.


## Completed evidence and quality misses

[The immutable corpus](../benchmarks/results/weighted-full-deck-flop-cfrplus-v1/index.json)
contains 18 timed policies, two separate traced allocation policies and two
physical-world records: 23 files and 2,793,089 stored bytes. All 20 policies pass
independent physical/numeric-action/own-hand-response replay on 5,940 worlds and
16,912 information rows, with every scalar replay gap zero. Repeated policy hashes
are exact within each backend. Maximum cross-backend conditional-policy and
scalar gaps are 6.924e-12 and 1.248e-13 respectively.

| Sweeps | Recursive NashConv | Public NashConv | Recursive median seconds | Public median seconds |
| --- | ---: | ---: | ---: | ---: |
| 10 | 0.2704368826157162 | 0.2704368826157242 | 17.994625 | 7.609677 |
| 50 | 0.0400945403817885 | 0.04009454038191329 | 81.279338 | 30.836078 |
| 140 | 0.012537880082120978 | 0.012537880082179598 | 224.811227 | 85.565438 |

Both final observations fail the unchanged 0.005-chip gate. The original process
exits 1 with `quality-miss`, no validation errors, and successful saved replay.
The final CFR+ residual is below baseline DCFR400 (0.03680413245381331), but
charged work differs (29,937,600 versus 28,512,000 units). This establishes no
unrestricted NLHE result or equal-work comparison.

Times are untraced complete calls including setup, training, exact diagnostics
and canonical serialization/hash, with three alternating pairs on the recorded
Windows/Python host. They support no controlled baseline/cross-host speed claim;
the baseline interruption outlier remains preserved. Separate 10-sweep traced
peaks are 36,311,606 recursive and 36,311,603 public bytes. These are Python
allocations, not RSS or high-iteration bounds, and are excluded from timed medians.
The temporary Windows system-required execution state is restored on exit.

Measured source `06616039f4fea3904614132f31c91c406ca90c1a` has identical clean
before/after snapshots of 593 source files. All 593 LF hashes match actual Git
blobs; CRLF normalization applies only to this Git/LF comparison. The
[source attestation](../benchmarks/results/weighted-full-deck-flop-cfrplus-v1-git-source.json)
records the first-party audit. Complete captured-manifest SHA256 is
`411777c7df5f78623ce760e14d384c9e5f451e5527205662ea0be3ee666a64b7`;
Git/LF-only manifest SHA256 is
`d381299a8ca71c4e5917f440a156b5fb7edf891d8ef7514a987a36f1121b45dd`.

Raw index SHA256 is
`6308cf6c9f5636123014355a328279fbc037c5ab0366ba3378909d52086ddaef`;
canonical unsigned artifact SHA256 is
`c62308b10f095eb356449d35a10ffffb7cedefe2511e5118862f68d01720500d`.
[The strict publication verifier](../scripts/verify_flop_cfrplus_publication.py)
pins the immutable raw index and source identity, reconstructs all 20 candidate
policies and reauthenticates/replays all 38 baseline policies. Re-signed metadata
cannot replace this observation; `--require-quality` correctly refuses it.
[Publication tests](../tests/test_flop_cfrplus_publication.py) disable production
training/ranking/value/response helpers during full reconstruction, preserve
quality misses and reject re-signed source/gate/status/baseline, physical-sign
and numeric-action corruption.
