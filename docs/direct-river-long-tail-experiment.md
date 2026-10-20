# Fixed longer direct river-tail experiment

This separate experiment uses the [longer direct river API](direct-river-long-tail.md)
on the existing polarized fixture: board `2c7d9hJsKd`, OOP `AsAh,3c4c`,
IP `QsQh`, pot and stack 100, one pot-sized bet and no extra all-in option.
It performs exactly one complete materialized CFR+ call at T=100000,D=3000.
The raw result receives no probability cleanup or adaptive stopping.

The earlier [10k/3k direct experiment](direct-river-tail-experiment.md) retained
NashConv about 0.0068727141 despite value within roughly 0.00000033 chips of
the known value 25. Its positive response gains motivate the longer trajectory.
The old 100k full-average matrix-free result is a different backend/window;
it does not predict this direct-tail result or supply a controlled timing ratio.

## Schedule and admission

Original sweep weights 3001 through 100000 total 4,995,548,500 over 97,000
averaged sweeps. Both alternating regret updates still run for all 100,000
sweeps: 200,000 regret passes plus 97,000 average passes. The full-request
admission remains conservative and independent of discard:

| Dimension | Fixed value / charge |
| --- | ---: |
| Physical worlds / information rows | 2 / 6 |
| Public states / decisions / terminals | 9 / 4 / 5 |
| Information action slots / prefix edges | 12 / 2 |
| Full world-node work | 2,400,000 |
| Full dense hand-state-pass work | 5,400,054 |

All existing work, tree, world and slot limits remain unchanged. These modeled
charges do not bound actual instructions, elapsed time or RSS.

## Independent evidence

Independent numeric rules reconstruct all eight value/response metrics within
1e-9. The generic exact auditor retains its 100,000-work, depth-64 and
65,536-bit Fraction caps. A separate five-terminal-history oracle enumerates
all 16 OOP and four IP pure legal responses; all eight exact metrics must agree
strictly with the generic certificate. Both normalize each serialized binary64
row as exact Fractions, without changing the policy file.

The exact response interval must contain 25. Exact NashConv at most 1/1000 and
exact zero are recorded separately from evidence validity; all target misses
remain accepted observations. The known game value is not imposed on the
trained profile. The report retains individual response gains and reconstructs
the earlier 10k raw policy's exact metrics before recording old/new differences.
Different trajectory lengths do not require equal rows or realization flows.

The runner pins the preceding direct report and polarized policy bytes,
committed generation sources and mathematical verification sources. The single
call time includes lazy producer import and the full API call; encoding,
independent audits and publication occur afterward. One uncontrolled timing
establishes no general speed or memory improvement.

## Saved files and replay

The runner produces a canonical LF report and policy at
`benchmarks/results/river-direct-long-tail-v1.json` and
`benchmarks/results/river-direct-long-tail-v1-polarised.json`, with caps of
four million and two million bytes. Generation refuses existing targets before
training, checks actual staged and published bytes against the original
validated raw files, and reconstructs the complete report before and after
exclusive publication. Rollback removes owned file identities only. Returned
unaccepted raw output and provenance are retained after a later failure.

Read-only replay requires current committed math sources and unchanged inputs,
then reconstructs the entire canonical report without producer execution. The
historical producer map and commit remain context; replay does not require the
historical Git object. The accepted-bundle hash regression is added separately
after generation to avoid a circular source hash.

Run `python -m scripts.benchmark_river_direct_long_tail --generate` only after
the source freeze is committed. Run with `--verify` to reconstruct saved data
without training. The certificate concerns this finite game and these exact
normalized serialized rows; it proves no unrestricted solver convergence.

## Recorded results

The actual complete call ran from committed generation source
`0450ff9fbfa434f1ad59b88606e7ed347cd90ab6`. No probabilities were cleaned up.
The exact normalized-policy outcomes are:

| Quantity | Earlier T=10000,D=3000 | New T=100000,D=3000 |
| --- | ---: | ---: |
| OOP value | 24.999999669238388 | 25.000000007578205 |
| OOP legal response gain | 0.005318046178756876 | 0.0005500202430588356 |
| IP legal response gain | 0.0015546678930386947 | 0.0003444539581166081 |
| NashConv | 0.006872714071795571 | 0.0008944742011754436 |
| Exploitability | 0.0034363570358977853 | 0.0004472371005877218 |
| Exact 0.001 target | Miss | Meet |
| Exact zero | No | No |

The printed decimals approximate exact Fraction strings in the report. New
NashConv is exactly
`72568368512557894921003008575/81129638414606677192189377773568`.
Its legal response interval is approximately
`[24.999655553620087,25.000550027821262]`, containing 25. The observed gap
decreases by about 0.005978239870620127 chips; the old miss remains immutable.
More sweeps and a longer averaging window are different work, so this is no
equal-cost algorithm or speed comparison.

The [raw policy](../benchmarks/results/river-direct-long-tail-v1-polarised.json)
is 6,664 bytes, SHA256
`b82aad9c8eeaeb1fa475c7501f3d9665aedc26d5051231bb273bf2973f068442`.
The [complete report](../benchmarks/results/river-direct-long-tail-v1.json)
is 20,451 bytes, SHA256
`94542aa030f36aac4e84fbaa24e0261c1b3556e701033dab31b7eff97308bbdf`.
Both exact auditors agree on all eight metrics. The generic auditor used 282
work units, depth four and a maximum 110-bit Fraction, under unchanged limits.
Its exact normalization ledger remains separate from the unmodified raw file.

The complete API call took 18.2794134 seconds on this host. It includes the lazy
producer import after preflight; JSON, audits and publication are outside this
interval. Separate lead verification matched all 65 producer and 11 verifier
fingerprints (73 distinct paths) to working files and committed generation
bytes, and checked both accepted input hashes. A third standalone terminal-sum
and backward-response calculation, importing no repository math helpers,
matched all eight exact metrics for both the old and new policies.

All 19 integrated focused tests passed in normal/optimized Python (0.610/0.512
seconds). They include genuine cheap math probes plus explicitly synthetic
source-drift, timing, serialization, publication and rollback faults. The actual
100k report also reconstructed in a fresh read-only process without training.
An accepted-file hash and trainer-disabled replay regression is added outside
the pinned source sets after generation, avoiding a circular hash.

The integrated accepted-file test disables nine solver/trainer entry points
and also derives all eight exact metrics directly from the six serialized rows
using terminal sums, OOP own-hand backward maxima and IP hidden-world weighted
minima. Both old and new policy metrics agree exactly; the independent gains
are checked without clipping. Together with the preceding saved river and turn
regressions, three no-training reconstructions passed in 26.775 seconds. The
new test also passed alone under optimized Python in 17.049 seconds.
