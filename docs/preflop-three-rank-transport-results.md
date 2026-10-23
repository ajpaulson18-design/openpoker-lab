# Authenticated three-rank preflop count transport

The single [planned transport observation](preflop-three-rank-transport.md)
passed from clean source `2198f1f23ddb9d1d24c08ec4182afeedb60c28b5`.
Its [original report](../benchmarks/results/preflop-three-rank-transport-v1/report.json)
and [complete candidate table](../benchmarks/results/preflop-three-rank-transport-v1/candidate.json)
are retained byte-for-byte. The prerequisite JJ/KK publication
[PR #216](https://github.com/ajpaulson18-design/openpoker-lab/pull/216)
had merged, and both its reviewed head and the original advance-solver commit
were verified on actual `main` before this observation.

## What was verified

The candidate pool reuses the authenticated AA/KK, QQ/KK and JJ/KK source
counts for SB `AA:1,QQ:0.5,JJ:0.25` versus BB `KK`: 18 SB hands, six BB
hands, 108 compatible physical pairs and 324 positive W/T/L categories.
The independent checker reconstructs literal private combinations, authenticates
all nine source classes, and checks that one global suit bijection maps both
ordered source hands to each target pair. The same bijection maps the unused
deck, preserving the complete five-card board set and W/T/L counts.

Each rank has six pairs with two shared suits, 24 with one and six with none.
The exact global normalizer is 63. Each AA pair has prior 1/63, each QQ pair
1/126 and each JJ pair 1/252; rank masses are 4/7, 2/7 and 1/7 and total mass
is exactly one. No row-local or hidden-opponent normalization is used.

The original four-pair count cap and 128-pair prepared-pool cap are unchanged.
The 184,928,832 represented board outcomes are coverage information; none was
newly enumerated. There were no new physical counts, five-card ranking,
native/reference builds, training calls or strategy searches. This is count
transport evidence only, with no equilibrium or policy claim.

## Single attempt and saved replay

The formal runner made one candidate attempt and two independent checks:
one in memory and one from the actual saved candidate file. Both receipts
agree exactly. All eleven named forbidden-calculation counters are integer
zero, errors are empty, and the clean HEAD/status and eight measured source
identities are unchanged before and after the observation. The independent
phase disables the candidate producer, production pool and its range planner.
Saved basis authentication retains its separate rank-free metadata checks.

The batch ran on CPython 3.12.14 / Windows from
2026-10-23T19:18:33.621294Z to 19:19:37.853695Z, completing with exit code zero.
The external process receipt records 64.2292424 seconds including startup and
saved authentication. This is an uncontrolled observation, with no speed or
memory/RSS bound. There was no retry or fallback.

The two-file corpus totals 46,100 bytes. Its immutable identities are:

| File | Bytes | Raw SHA-256 | Canonical artifact SHA-256 |
| --- | ---: | --- | --- |
| candidate.json | 37,639 | fdbd5640a53e5f3e9d5ec2ee0756b1ad5cfa658fc4e4747c373b87d088091e90 | fc98072bef74e1570a13db5c876d36226bcec1b3a2f7959c361872feb3abdbb9 |
| report.json | 8,461 | 8a061e42337ea2e7931b9877e966f680f02d407c32f7d6fb58fe07e08a53547a | 9d73cbc63bda40a4e51afda03d89af79258a350df4ab42960dbe5e1f7a0f16f9 |

The [saved-publication verifier](../scripts/verify_preflop_three_rank_transport_publication.py)
authenticates original bytes, source identities,
attempts, guards and both receipts, then freshly repeats the independent
transport check. Its result reuses saved physical counts and does not repeat
the numerical source-count experiments. GitHub checks and merge are verified
separately from the mathematical observation.

## Next boundary

A subsequent finite preflop betting game needs its own complete action
specification, serialized physical own-hand policy and exact legal responses.
The older 72-pair mixed-range witness does not certify these 108 pairs or new
priors. Arbitrary suit-dependent responses must remain legal in that proof.
The existing three-chip tree forecasts 864 SB plus 216 BB pure-response
candidates, but this transport observation executes none of them.

Implementation is original project code using suit invariance and exact joint
weights. No third-party source, package or new dependency is incorporated.
Full-deck later-street betting, general ranges, multiway play and unrestricted
Hold'em remain outside this evidence. Coach and explanation work are separate.
