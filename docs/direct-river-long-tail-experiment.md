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

Pending reviewed source freeze and the actual fixed 100k call. Cheap T10/D5
probes verify integration only and supply no 100k quality evidence.
