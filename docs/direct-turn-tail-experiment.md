# Fixed full-deck direct tail experiment

The separate `scripts/benchmark_turn_direct_tail.py` experiment calls
`pokerlab.turn_tail_adapter.solve_turn_tail` once for the fixed raised turn game:
board `Js8d4c2h`, OOP `AsAh:0.5,KsKh:1`, IP `AcAd:1,KcKd:0.75`, pot 100,
stacks 220, half-pot bets/raises, one raise and no all-in sizing on both streets.
All 176 joint physical worlds and 48 public river cards remain in the game.

The call completes 1,500 alternating CFR+ sweeps and averages sweeps 1,001–1,500
directly with their original weights. Their weight sum is 625,250. The saved
policy receives no cleanup. Complete-call elapsed time includes preparation,
training, diagnostics and output construction; JSON encoding and independent audits run afterward.
Timing is a single uncontrolled observation, with no general speed or RSS claim.

## Acceptance and reproducibility

Before training, the runner requires committed producer and verification sources,
pins the accepted historical inputs, and refuses existing output paths. Full
requested resource admission remains in force. The original world-node charge
is 25,344,000 and the separate dense hand-state charge is 27,369,234, each below
its unchanged 30-million limit. There are 5,364 information-action slots and
180 prefix-hand edges.

After training, independent numeric rules reconstruct all eight metrics within
1e-9. The full-physical exact oracle and checked chance-class certificate must
agree on every exact metric. Each interprets binary64 rows as exact Fractions
normalized by their exact row sum. The physical oracle keeps all actual river
cards separate and optimizes only legal visible-information responses.

The runner separately compares each player's own action-sequence realization
flows with the immutable original materialized tail. It uses exact normalized
Fractions and requires maximum absolute error at most 1e-11. This comparison
excludes opponent reach and public chance; it is a trajectory consistency
check, separate from poker legality and exact response evaluation.

Exact NashConv at most 1/1000 and exact NashConv zero are recorded outcomes.
Neither is required to publish an otherwise valid experiment. Misses remain
visible. The old reports and policies retain their original bytes.

Canonical LF policy/report files have respective 2-million/8-million-byte caps.
The runner reconstructs staged and published bundles, guards sources and inputs
around audits, and publishes through exclusive hard links. Rollback removes
only file identities created by that invocation. A failed post-call audit keeps
the unaccepted raw policy separately for diagnosis.

Saved replay requires the current committed mathematical verification sources
and accepted input bytes. Historical producer hashes and generation commit stay
as provenance bound by the saved report hash; replay does not require the old
Git object or call the producer. This supports shallow CI checkouts without
treating a provenance string as an independent reconstruction of training.

Run `python -m scripts.benchmark_turn_direct_tail --generate` once from frozen
committed sources. Run `python -m scripts.benchmark_turn_direct_tail --verify`
to reconstruct the saved result without training.

## Recorded result

The completed run at generation commit
`c64dc02694388c9ff0b1101f4b4cae57802af3e9` saved the unmodified adapter result.
Both exact auditors agree on all eight metrics:

| Metric | Exact value |
| --- | ---: |
| OOP / IP profile value | -400/21 / 400/21 |
| OOP / IP best-response value | -400/21 / 400/21 |
| OOP / IP response gain | 0 / 0 |
| NashConv / exploitability | 0 / 0 |

The exact 1/1000-chip target is met. This is a new raw trained-policy result;
the earlier subtraction-based tails retain their positive exact gaps and the
separately derived clean witnesses remain separate artifacts. Direct averaging
is not guaranteed to reach exact equilibrium for another game or window.

The [complete policy](../benchmarks/results/full-deck-raised-turn-direct-tail-v1-materialized.json)
is 1,690,215 bytes, SHA256
`18553678c7d6cda7d8425d268bd79cdcb8e7add31f8d36a35ede8b1a67ba4d5c`.
The [independent report](../benchmarks/results/full-deck-raised-turn-direct-tail-v1.json)
is 392,804 bytes, SHA256
`ea7b5c9d8eafbec0aa99ebaf8c6f2e4e76cf9d9d93cea57226a0ad9f8d7c46b3`.
It pins 63 producer files, 16 verification files (77 distinct files in their
union), and eight accepted historical input files. Separate parent verification
matched all source pins against committed generation bytes and current files,
recomputed full-physical exact metrics, and independently reconstructed the
maximum own-realization flow error, about 1.72752e-15, below 1e-11.

The complete adapter call took 87.456834 seconds on this host. JSON encoding,
audits and publication are outside that interval. This observation does not
establish a controlled speed comparison. The physical audit visits 18,234
structural nodes and 3,756 weighted rows; maximum stored Fraction size is 392
bits. It exactly normalizes 708 probability rows without modifying the policy
file. The full physical and checked quotient audits keep their existing limits.

Nine focused runner tests passed in normal/optimized Python (3.997 / 4.074
seconds). They include a genuine ten-sweep adapter call, the real eight-file
input guard, exact-certificate disagreement, strict metadata, finite timing,
staging failure, late byte drift and preservation of a foreign replacement.
The accepted-bundle hash regression disables seven producer/trainer entry
points and reconstructs the complete report without training; it passed in
normal/optimized Python (7.556 / 7.414 seconds).
