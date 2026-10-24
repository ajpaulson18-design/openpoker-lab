# Physical blocker-sensitive AA/AK count transport

The single frozen [transport observation](../benchmarks/results/preflop-aa-ak-transport-v1/report.json)
passed for unit-weight SB AA/AK-suited/AK-offsuit versus BB KK. All 84 physical
private-pair rows reconstruct from six independently enumerated source classes.
An independent literal-card oracle checked each ordered pair, full integer
W/T/L counts, source report identity, exact global prior and one joint four-suit
bijection. Independent memory and fresh saved-file receipts agree exactly.

This establishes count-transport provenance for one fixed support. It does not
establish a strategy, equilibrium, convergence, later-street betting, speed,
memory savings or unrestricted no-limit Hold'em solving.

## Collision conditioning and six source orbits

The literal support has 22 SB hands (six AA, four AK-suited and twelve AK-offsuit)
and six BB hands. Of 132 raw combinations, 48 collide on a physical king card.
The remaining 84 pairs each have exact globally conditioned prior 1/84. AA,
AK-suited and AK-offsuit therefore have masses 3/7, 1/7 and 3/7. No hand-type
prior is normalized separately before combining the game.

| Authenticated source pair | Physical members |
| --- | ---: |
| AdAs / KdKs | 6 |
| AdAs / KcKd | 24 |
| AdAs / KcKh | 6 |
| AcKc / KdKh | 12 |
| AdKc / KdKh | 24 |
| AdKc / KhKs | 12 |

The distinct offsuit classes preserve the opponent's relative ace-suit blocker.
A single global suit map acts on both private hands; each target pair has exactly
one matching authenticated source orbit. Its source identity, endpoints and
full cdhs-ordered permutation are retained. The oracle constructs literal
combinations and searches all 24 suit permutations without invoking producer,
pool, range or canonicalization helpers.

Each row describes 1,712,304 physical final boards, representing 143,833,536
outcomes across this table as an informational census. The experiment performs
zero new board enumeration or ranking and makes no strategy/training call.
The prepared pool's 128-pair cap and every existing work guard are unchanged;
the 156-pair AA/QQ/JJ/AK combination still exceeds that cap.

## Immutable observation and saved publication

The source freeze was pushed commit
`573b615aae77c554e58b71f8ff256699f954a66a`, after prerequisite AK source
[PR #226](https://github.com/ajpaulson18-design/openpoker-lab/pull/226) actually
merged at `ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251`. That exact merge is the
recorded baseline and an independently checked ancestor of the observation.
The actual merged-main AK saved authenticator passed before this publication.

One candidate attempt and two independent verifications passed. All sixteen
forbidden-calculation counters are exact integer zero, errors are empty, and
the ten measured source identities plus clean HEAD/status are identical before
and after. There was no retry, build, LP solve or training.

The [complete candidate](../benchmarks/results/preflop-aa-ak-transport-v1/candidate.json)
and original report retain 49,741 byte-exact bytes:

| File | Bytes | Raw SHA-256 | Canonical artifact SHA-256 |
| --- | ---: | --- | --- |
| candidate.json | 38,864 | 9033666cf0fe07c43e2484d8b3df5127b59cbf2f079869a7121415949b03e8fb | 7bf39179d001c39d7872b28f1f2584820f344ecd631fa75630cbc99e0ced38c4 |
| report.json | 10,877 | 5a4b191e776e6037a0c142aeab42c85d192deb376134916219826c76d25a2284 | 6ddb80afae0aeb0be152c4ba76e18e675ac2199396b1777d044544f4cb27f9e4 |

The [saved-publication authenticator](../scripts/verify_preflop_aa_ak_transport_publication.py)
pins both raw files before parsing, checks the original complete source, call,
guard, baseline and receipt metadata, then freshly repeats independent saved
candidate verification with producer/pool/range/canonicalization, rank, build,
LP and trainer entry points disabled. Later clean current HEADs are recorded
separately and must retain all ten measured LF source identities. Original
reports are never rewritten to describe publication edits.

The observation ran once on CPython 3.12.14 / Windows from
2026-10-24T01:13:16.640102Z to 01:14:50.200844Z. The external receipt records
93.5605712 seconds. This is one uncontrolled complete observation, including
saved prerequisite authentication and both literal transport checks; it supplies
no runtime or RSS bound. All 21 core producer/oracle/orchestration controls and
ten saved-publication controls pass under bundled CPython 3.12.14. The latter
include actual fresh saved-candidate replay with dirty-status metadata isolated,
raw-before-parse mutation rejection, boolean aliases, later-HEAD/source drift,
and successful math followed by source change. Actual clean-source saved CLI
verification and final-head CI are separately recorded before merge.

## Next accuracy boundary and provenance

An independently replayed real-source policy, exact mutual-response witness
and finite-iteration convergence remain separate milestones. The staged
[own-hand policy audit](https://github.com/ajpaulson18-design/openpoker-lab/pull/231)
must validate the whole physical game before any claim about a solver result.
The existing physical source counts and all older target misses remain intact.

This is an original project implementation of literal card combinations and
joint global suit bijections, reusing the project's prepared-count pool. The
[preregistered method and scope](preflop-aa-ak-transport.md) remain unchanged.
No third-party source or dependency is incorporated. Shared solver kernels,
production defaults, separate turn/river work, AI Coach and explanations are
unchanged.
