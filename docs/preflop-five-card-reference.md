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

Formal exhaustive conformance, full-board comparison and publication are pending
at this source stage. No new physical count row is certified until those checks
pass from a frozen revision and the saved report is verified.
