# Independent best-five physical-count reference

This is a fixed research tool for expanding the physically verified preflop
source-count basis used by [covered prepared ranges](preflop-covered-counts.md).
It is separate from production evaluator/preparation/solver APIs. No runtime
dependency, imported implementation, binary distribution, preparation-cap change
or later-street work is introduced.

## Reference construction and fixed work

The project-owned C source
[`preflop_five_card_reference.c`](../native/preflop_five_card_reference.c)
sorts five card ranks, classifies five-card multiplicity/straight/flush patterns,
and encodes category and descending kickers as six ordered nibbles. A seven-card
value takes the best of all 21 five-card subsets by excluding every distinct
pair of positions. It shares no production evaluator implementation or lookup
table. Its two command-line modes are fixed: every five-card hand, or three
full-board AA/KK pairs. It accepts no arbitrary count request or card stream.

The [frozen specification](../benchmarks/preflop-five-basis-v1.json) requires
exact comparison of every one of the 2,598,960 five-card category/kicker tuples
to the independent project-owned Python five-card oracle, plus all nine known
category totals. The fixed binary dump has six bytes per hand, or 15,593,760
bytes. The validator rejects a wrong byte census before calling the oracle.

Only after five-card conformance passes does the reference enumerate all
1,712,304 boards for each of `AdAs / KdKs`, `AdAs / KcKd`, `AdAs / KcKh`.
These are the same-two-suits, one-shared-suit and disjoint-suits AA/KK pair
classes. Actual counters must show 5,136,912 boards, 10,273,824 seven-card
rankings and 215,750,304 five-card subset calls. Five-card and seven-card calls
are different units; they are not comparable performance costs.

The first pair must match the previously pinned independent full-board census.
All three integer W/T/L rows must match a separate production native seven-card
enumeration. Its ordinary three-pair planning/rank/board caps are admitted before
any executable lookup. The best-five reference has its own fixed research work
census; it does not expand production preparation limits.

## Build and saved-file validation

Build explicitly with an installed compiler; no automatic installation occurs:

```sh
python -m scripts.build_preflop_five_reference --output-dir ../five-reference-build
python -m scripts.validate_preflop_five_reference --reference-build ../five-reference-build --candidate-build ../native-equity-build --output-dir ../five-reference-observation
```

The builder requires an empty external build directory and records source,
compiler/options and executable hashes. The validator requires a new external
observation directory and clean committed source. It retains raw binary output,
raw count JSON, all failures, source/build identities and a checksummed textual
report. Source and reference executable identities must remain unchanged.
Generated binaries and the binary dump stay outside the repository. Recorded
durations describe validation work; this is not a speed benchmark or memory/RSS
measurement. Successful compilation is feasibility evidence only.

[Boundary tests](../tests/test_preflop_five_reference.py) cover exact work/row
censuses, malformed/truncated observations, dirty-source rejection before any
executable or ranking, and preservation of previous build/output data.

## Frozen full conformance and source-count observations

The [published report](../benchmarks/results/preflop-five-basis-v1.json) passes
from clean source `293e61357497f39ae02a8e0c3f75207f8e455eb7`. All 478 recorded
normalized source hashes independently match normalized Git blob contents at
that revision. Source/reference build identities remain unchanged. All
2,598,960 five-card category/kicker tuples agree with zero mismatches and all
nine category totals agree. The fixed dump is 15,593,760 bytes, SHA-256
`7dfd1ff4ed2761fef77db70b170fdae750cf7c162932087e30163037e4e78e52`.
It is retained outside Git; no generated executable is distributed.

| SB | BB | Suit overlap | Wins | Ties | Losses |
| --- | --- | ---: | ---: | ---: | ---: |
| AdAs | KdKs | 2 | 1,410,336 | 9,308 | 292,660 |
| AdAs | KcKd | 1 | 1,399,204 | 7,923 | 305,177 |
| AdAs | KcKh | 0 | 1,388,072 | 6,538 | 317,694 |

Each row covers all 1,712,304 boards. Actual reference counters are exactly
5,136,912 boards, 10,273,824 seven-card rankings and 215,750,304 five-card
subset calls. The first row reproduces the original independent physical
anchor; all three rows exactly match separately retained production-native
seven-card counts. Fresh saved-file verification compares the raw candidate
and reference values, not a saved success flag. The final binary dump and
count JSON were reopened and their digest/data independently checked again.

The MSVC reference source SHA-256 is
`5deeeb861d70a333963afc0cb01435d87cc930e864f0e6e11e244050f61ffc05`;
executable SHA-256 is
`0d9ddc9af391553b8b859baf2742e8a8c19dd6a6f148cf5dcca8b2a4aa4a199e`.
The report retains compiler version/options and both counter build identities.
Five-card dump generation took 0.274110 seconds; full-board reference and
production count calls took 10.185131 / 0.605814 seconds. The Python exhaustive
comparison duration is not separately recorded. These are validation durations,
not paired speed or memory benchmarks.

Report canonical SHA-256:
`2ae377e0af6d55491c667d574f41482f2ea6911ba8565ade3b9c8406b54010f7`.
Raw report SHA-256:
`bb906c0dac2deca79753e48548b5c3c1b7b9cedd92ba3574da934154713b5419`.
The earlier successful observation is retained separately; the followup keeps
raw candidate values for independent saved-file comparison. Numerical C code,
acceptance gates and the three observed count rows are unchanged.

Both Linux and Windows CI execute the exhaustive five-card and full-board
comparisons. Initial CI computations passed but artifact upload rejected its
relative parent path; publication changes the report upload/output path to an
absolute runner-temp location. The initial jobs remain as evidence. Final CI
and GitHub merge status are recorded on the associated pull request. These
source rows can support broader covered ranges; they do not by themselves
establish an equilibrium strategy for those ranges.
