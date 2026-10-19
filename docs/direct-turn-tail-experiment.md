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

Pending the frozen full run. No quality outcome is inferred from the small
adapter tests or the preceding subtraction-based experiment.
