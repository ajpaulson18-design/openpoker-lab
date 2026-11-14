# Candidate AA/AK versus KK count transport

This research-only slice prepares a rank-free physical-count table for SB
`AA,AKs,AKo` versus BB `KK`, with unit range weights. The fixed support has 22
SB hands, six BB hands, 132 raw combinations, 48 blocked combinations and 84
compatible ordered pairs. The 128-pair prepared-table cap remains unchanged.
The support consists of six AA hands, four AK-suited hands, twelve AK-offsuit
hands and six KK hands. Its suit-overlap census is AA 6/24/6 for 0/1/2 shared
suits, AK-suited 12 with zero shared suits, and AK-offsuit 12/24 for 0/1 shared
suits.

The exact global mass is 84, so each retained pair has prior `1/84`. AA has 36
pairs and mass `3/7`, AK-suited has 12 and mass `1/7`, and AK-offsuit has 36 and
mass `3/7`. The six source classes are three AA/KK suit-overlap representatives,
one suited AK/KK representative and two offsuit AK/KK representatives. Each
candidate row retains the source endpoints, source-report identity and one joint
four-suit bijection for both hands, along with the full physical W/T/L counts.
The row's `source_identity_sha256` is the authenticated source report's
canonical artifact digest (AA report for AA rows, AK report for either AK type).

The candidate producer checks the complete literal request and existing caps
before reading source files. It then authenticates the saved AA/KK and AK/KK
publications using their pinned raw and canonical identities and existing saved
verifiers before constructing source tables. It pools only those prepared
counts. It performs no hand ranking, board enumeration, solver build, LP or
training call. Candidate output is not independent proof; a separate literal
transport verifier and a later formal observation are required.

The [independent oracle](../scripts/preflop_aa_ak_transport_validation.py)
constructs all physical private hands from literal ace/king cards, removes
collisions, and searches all 24 joint global suit bijections against the six
authenticated source endpoints. It does not call the producer, pool, range or
canonical-orbit helpers. It checks every source and target endpoint, all integer
counts, original report identities, exact global priors, the six orbit
multiplicities and total mass. Malformed requests, source identities, duplicate
pairs and suit maps reject before source I/O. Synthetic integration and mutation
tests are separate from a real physical-source observation.

The [single-observation harness](../scripts/certify_preflop_aa_ak_transport.py)
admits the complete fixed request before source/Git/output access. A caller must
first verify that the exact prerequisite AK publication merge is on GitHub main
and pass that 40-character commit; the harness independently requires local
ancestry and the pinned source index at that commit. It does not independently
contact GitHub or treat an arbitrary ancestor as proof of merge.

The harness requires a fresh external output directory and clean committed
source. It records ten measured source files before and after, one candidate
attempt, independent memory verification and fresh saved-file verification,
and sixteen distinct forbidden-entry counters. Build, rank, enumeration, LP
and training entry points are disabled throughout; production transport helpers
are additionally disabled during oracle checks. It saves complete candidate
bytes before verification, retains the earliest error and any later source
error, and does not retry a failed batch. Both result files have independent
1,048,576-byte limits. No formal observation or successful physical transport
is claimed by staging this code.

The W/T/L rows describe transported physical counts for this fixed support.
They do not establish a strategy, equilibrium, convergence, speed, memory use
or unrestricted Hold'em result. This slice adds no rules, later-street game or
Coach behavior.

This method is an original project implementation of literal card combinations
and a global suit bijection. Such a bijection preserves card distinctness,
relative suits, ranks and the unordered board set, giving a one-to-one mapping
of complete physical outcomes for a fixed ordered private pair. Independent
source enumeration and the separate oracle remain required evidence. No
third-party source or dependency is incorporated.

Validation before the source freeze: 21 synthetic producer, independent-oracle
and orchestration tests pass under bundled CPython 3.12.14. Controls include
all 84 source-linked rows, swapped offsuit source counts, invalid priors/maps,
pre-I/O rejection, source rereads, direct forbidden-entry restoration, strict
baseline ancestry/index bytes and retained early errors plus later source drift.
The actual observation remains deferred until prerequisite publication merges.
