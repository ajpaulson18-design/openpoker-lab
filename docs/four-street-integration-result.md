# First complete four-street integration result

The fixed conditioned heads-up game passed its declared whole-game quality gate
on October 25, 2026. One coupled CFR+ solve produced a complete policy spanning
preflop, flop, turn and river. Independent numeric replay and an exact normalized
policy certificate reconstructed the entire game and both legal best responses.
A separate saved-only replay authenticated the source and all results without
calling a solver or trainer.

This result covers two weighted physical hands per seat and six selected boards
across two flops, with the finite betting menus in the
[frozen fixture](../benchmarks/four-street-integration-v1.json). Selected outcomes
condition one joint hand/board law. It establishes the named finite game's
accuracy; full-deck chance, realistic unrestricted ranges and unrestricted NLHE
remain future work. The [preregistered protocol](four-street-integration-protocol.md)
and fixture retain their original pre-run status text as immutable execution
inputs; this document records the completed outcome.

## Whole-game result

The displayed decimals approximate the exact fractions retained in the
[complete certificate](../benchmarks/results/four-street-integration-v1/attempt/exact-certificate.json).
Values use global SB/BB identities and whole-hand big blinds, before blinds are
posted. The certificate concerns exact normalization of the returned binary64
policy, with the complete adjustment ledger; it is not a raw-floating interval.

| Metric | Big blinds |
| --- | ---: |
| SB profile value | 0.245057763853449 |
| Lower value bound, `-BR_BB` | 0.244808253631219 |
| Upper value bound, `BR_SB` | 0.245207992446363 |
| NashConv, `BR_SB + BR_BB` | 0.000399738815144135 |
| Exploitability, NashConv/2 | 0.000199869407572068 |
| Declared NashConv target | <= 0.001 |

The exact threshold comparison passes. Both responses integrate hidden opponent
hands and future cards before maximizing at legal visible-information rows.
They may deviate across the complete game. This is a single equilibrium-game
audit; it does not combine independent street equilibria.

All 1,200 information rows and 2,402 action slots were audited, including off-path
rows: 8 preflop, 48 flop, 270 turn and 874 river rows. The physical law has 22
worlds and four compatible private pairs. Independent and production graphs
respectively contain 1,414 and 1,462 states because of independently collapsed
all-in chance. Exact work was 92,534 against forecast 98,298 and the unchanged
100,000 cap. The 65,536-bit and other admission limits remain unchanged.

The fixed request used 1,000 zero-delay CFR+ iterations, public-batched training
and diagnostics, public-vector admission and the original decision-count tree
guard. The runner entered production once. The solver returned 3,000 training
passes in metadata; a separate completed-iteration counter was absent, and the
receipt labels 1,000 completion as an inference from the pinned fixed loop.
This observation establishes no general convergence or performance guarantee.

## Immutable evidence

The [publication index](../benchmarks/results/four-street-integration-v1/publication.json)
lists all twelve original artifacts, totaling 3,420,018 bytes. They were copied
byte for byte, with Git text conversion disabled for this corpus. The raw facade's
unrecorded inner source fields remain intact. Its companion claim and identical
before/after 314-file source snapshots authenticate the frozen execution.

- Frozen source: [bf1c21b17e84162dea3a3a68104e785b19269b40](https://github.com/ajpaulson18-design/openpoker-lab/commit/bf1c21b17e84162dea3a3a68104e785b19269b40).
- Attempt: `04f675c5-8222-4a11-9139-5c2dfc1e8bc9`.
- Original [raw envelope](../benchmarks/results/four-street-integration-v1/attempt/raw-envelope.json): 475,233 bytes, SHA256 `37b3c61cbca982dd44078da22b9c8e1c3acd3ef5171c01272def8cdf4580596e`.
- Pinned [report](../benchmarks/results/four-street-integration-v1/attempt/report.json): SHA256 `c2f905ab698b086d96abbaae46b120c6202e95e65990a745a6d1cc703ced9a8e`.
- Fresh [saved-only verification](../benchmarks/results/four-street-integration-v1/verification.json): SHA256 `3240cf44fd1f88bcf9f98e32f55c44756a59ce908af5c9a7677d1ba85c5bd7fc`, source verified, complete policy replayed, zero verifier production calls.

Before execution, all 24 checks passed on the frozen source, including full unit
discovery on Python 3.11, 3.12 and 3.13. The seventeen lifecycle controls also
passed locally normally and with optimized Python. The earlier exact-census
rejection and historical street-specific quality misses remain preserved.

## Saved-only reproduction

Use the exact frozen source so later development cannot change the mathematical
authorities. From a checkout containing this published corpus, PowerShell can
retain its absolute path while opening a separate frozen worktree:

```powershell
$attemptDirectory = (Resolve-Path 'benchmarks/results/four-street-integration-v1/attempt').Path
git worktree add --detach ../four-street-v1-source bf1c21b17e84162dea3a3a68104e785b19269b40
Push-Location ../four-street-v1-source
python -B -m scripts.verify_four_street_integration_publication --directory $attemptDirectory --expected-index-sha256 c2f905ab698b086d96abbaae46b120c6202e95e65990a745a6d1cc703ced9a8e
Pop-Location
```

The saved-only verifier is read-only and requires no training. Its successful
replay authenticates the full exact ledger and original report pin. The next
support expansion receives a new joint law, fresh admissions and a separate
experiment; this corpus and the original caps remain fixed.
