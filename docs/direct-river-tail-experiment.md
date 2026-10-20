# Fixed direct river tail experiment

`scripts/benchmark_river_direct_tail.py` defines a separate fixed experiment for
the opt-in `solve_river_tail` API. It completes one actual materialized call for
each of the two historical river fixtures at `T=10000,D=3000`. The average retains
original sweep weights 3,001 through 10,000, totaling 45,503,500 over 7,000 sweeps.
Both returned policies are saved without cleanup.

The polarized game is board `2c7d9hJsKd`, OOP `AsAh,3c4c`, IP `QsQh`, pot/stack
100 and a single pot bet. The weighted raised game is board `Js8d4c2h2s`, OOP
`AsAh:0.5,KsKh:1`, IP `AcAd:1,KcKd:0.75`, pot 100, stacks `[220,120]`, opening
fractions `[0.33,0.75]`, raise fractions `[0.5,1]`, two raises and all-in sizing.
The exact fixture dictionaries and prior materialized tail files are bound to
the immutable historical tail report and policy hashes.

## Admission and audit

The full requested budget is charged before training, independently of discard.

| Game | Worlds | Public states / decisions | Information sets / action slots | World-node charge | Dense hand-state charge |
| --- | ---: | ---: | ---: | ---: | ---: |
| Polarized | 2 | 9 / 4 | 6 / 12 | 240,000 | 540,054 |
| Weighted raises | 4 | 51 / 18 | 36 / 100 | 2,160,000 | 3,060,306 |

Both work limits remain 30 million, the slot limit one million, and original
candidate/world, public-tree and prefix-edge guards remain in force. These
modeled charges do not bound every instruction, elapsed time or RSS.

Independent numeric rules reconstruct all eight saved metrics within 1e-9.
The unchanged generic Fraction auditor evaluates each legal policy with caps
of 100,000 work units, depth 64 and 65,536 Fraction bits. The polarized profile
also receives the independent five-terminal-history calculation enumerating
all 16 OOP/four IP pure responses; its eight exact metrics must match strictly.
Each binary64 row is interpreted as exact Fractions normalized by its exact sum.

The legal response intervals must contain reference game values 25 and
`-43339/2163`, respectively. These references are not forced trained-profile
values. Exact NashConv at most 1/1000 and exact zero are recorded outcomes;
neither is a gate for accepting otherwise valid evidence. Every miss is retained.

The runner independently validates the old saved materialized tail policies
and compares exact own-action realization flows with the direct profiles at
maximum error 1e-11. Opponent and chance reach do not enter this comparison.
Zero-own-reach conditional fallbacks may differ. The preceding policies and
their outcomes remain unchanged; no convergence advantage is assumed.

## Reproducibility and publication

Generation requires committed producer and mathematical verification sources.
It records source fingerprints, generation commit and complete-call timings,
then guards those sources, current HEAD and accepted input bytes around the
calls and each audit phase. Timings include the complete API calls and initial
lazy producer import; JSON encoding, independent audits and publication run
afterward. A single uncontrolled observation establishes no general speedup.

The new report and two policy files use canonical LF JSON, with respective
8-million/2-million-byte caps. Existing targets cause refusal before training.
Three exclusive stages are checked against the original validated bytes and
reconstructed before publication. Published bytes are reconstructed again;
rollback removes only descriptor-derived file identities owned by the invocation.
Foreign replacements remain intact. Returned unaccepted raw policies and source/
timing context are preserved separately if a later phase fails.

Saved replay checks current committed mathematical sources and accepted inputs,
rebuilds the entire report, and finishes with a bundle-byte guard after the final
source/input checks. Historical producer hashes and commit stay as saved context;
replay requires neither the historical Git object nor producer execution. The
accepted report hash separately binds that historical provenance.

Run `python -m scripts.benchmark_river_direct_tail --generate` only from the
committed source freeze. Run it with `--verify` to reconstruct an existing bundle
without training. A complete saved-bundle hash regression is added after actual
generation, outside the pinned source sets to avoid a circular hash.

## Recorded results

Pending reviewed source freeze and actual full-budget calls. The genuine
T10/D5 probes validate integration only and make no T10,000 quality claim.
