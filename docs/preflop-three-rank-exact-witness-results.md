# Exact physical three-rank preflop witness

The single [planned finite-game witness](preflop-three-rank-exact-witness.md)
passed from clean frozen source `58ccc8d886a22428efe26c8ba9447a596659db29`.
The exact SB value is **`1464215/2330174` chips**. Independent legal own-hand
best responses have SB value `1464215/2330174` and BB own-utility value
`-1464215/2330174`. Both unilateral gains and exact **NashConv are zero**.

This certifies one complete mutual-response profile for SB
`AA:1,QQ:0.5,JJ:0.25` versus BB `KK`, blinds 0.5/1, stacks 3/3, raise sizes
0.5 and 1, two raises and all-ins. Every nonfolded closed betting line forces
hidden full-board checkdown. There are no later-street betting decisions.
This is neither an unrestricted Hold'em solution nor a claim about all
equilibrium policies or production trainer convergence.

## Independent physical authority

The candidate uses a three-SB-type/one-BB-type rank-mean sequence-form game.
The proof independently authenticates all nine physical source classes and
rebuilds 108 literal private pairs with priors 1/63, 1/126 and 1/252.
It retains all 18 SB hands and six BB hands, and uses fourteen independently
written terminal histories and chip transfers. It checks all 96 own-hand /
public-history policy rows and 258 action probabilities, including off-path
rows. Candidate matrices, numeric trees and LP output are not the proof authority.

For each own hand, the checker evaluates all complete legal pure policies
against the hidden opponents before selecting the best response: 864 SB plus
216 BB policies, or **1,080** in total. Responses may depend on suits; the
proof imposes no candidate symmetry. Neither player may condition its response
on the hidden opponent hand or future board.

The recorded candidate shoves AA and JJ at the root. QQ folds with probability
`288653/332882` and shoves with `44229/332882`. Every BB own hand folds to a
shove with probability `36739/75655` and calls with `38916/75655`. These facts
describe the saved finite-game witness. They are not live coaching advice.
All off-path policies are explicitly retained and independently normalized.

## Original observation and publication

[PR #222](https://github.com/ajpaulson18-design/openpoker-lab/pull/222) merged
before this dependent experiment. Its actual merge
`23beb4b8983d8c6549c33ff0b07a741c2674555b` is the recorded baseline, verified
as an ancestor before candidate construction. Latest parallel river evidence
was integrated without changing its implementation or counts.

One candidate attempt made exactly two prescribed LP calls, then both memory
and actual saved-file physical response checks agreed exactly. The source
snapshot contains fifteen measured files, with identical clean HEAD/status and
hashes before and after the complete call. All fourteen named forbidden-call
counters are integer zero. Errors and cleanup errors are empty. There was no
retry, new board enumeration, ranking, build or strategy training.

The original [complete candidate](../benchmarks/results/preflop-three-rank-exact-witness-v1/candidate.json)
and [audit report](../benchmarks/results/preflop-three-rank-exact-witness-v1/report.json)
are retained byte-for-byte, totaling 196,387 bytes:

| File | Bytes | Raw SHA-256 | Canonical artifact SHA-256 |
| --- | ---: | --- | --- |
| candidate.json | 84,330 | dd0345efdf388638ad3e359baeb84b0872f1701ab942549f4a0d257b0d141e85 | 18933598b5410e926440773351cf53d9c1990835b68fa8c2129f7c82e99cb6c4 |
| report.json | 112,057 | 3f3aacce30283e3db474771fa396fa92f566b39332399358b8680830a772239b | 792820c701099e02213e715e777224405572e719e114555a9fae3d7485c0202a |

The [saved-publication authenticator](../scripts/verify_preflop_three_rank_sequence_publication.py)
checks raw pins before parsing, original call/source/guard receipts and candidate
links, then freshly repeats the exact physical response proof with candidate,
tree, LP, pool, rank and trainer entry points disabled. A later current clean
HEAD is attested separately and retains the measured calculation LF identities.
The sole changed helper in that fifteen-file map has an explicit archived
[publication-only transition](preflop-publication-source-history.md); every
other measured file remains exact. Neither original report is rewritten to
describe publication edits.

The batch ran once on CPython 3.12.14 / Windows from
2026-10-23T19:57:33.259407Z to 19:58:47.934226Z. The external process receipt
records 74.6746523 seconds; the runner records 72.7118983 seconds inside its
call boundary. These are uncontrolled observations, not a speed or memory/RSS
bound. The LPs recorded 50 and 103 pivots, under the unchanged 512-pivot cap;
their model diagnostics remain separate from the physical proof.

## Remaining work and provenance

The old 72-pair witness and all historical quality misses remain unchanged.
Larger games, blocker-sensitive unpaired ranges, later-street betting and trained
policy accuracy require separate evidence. Any future trained-policy comparison
must independently admit its complete request and retain all target misses.
Runtime, memory and general convergence remain unproved. GitHub CI and actual merge are verified separately
from this mathematical observation.

The implementation reuses the project's original bounded Fraction LP and
literal-response method. Published mathematical provenance is linked from the
[prior witness](preflop-mixed-exact-witness.md#research-provenance). No third-party
implementation or new dependency is added. Coach and explanation work remain separate.
