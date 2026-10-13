# Expanded weighted preflop/flop coverage

This experiment expands the earlier weighted fixture to four exact private hands per seat and four selected flops. It verifies a finite heads-up game with preflop and flop betting followed by forced checkdown. It does not solve full-deck preflop, later-street betting, broad ranges, multiway play or unrestricted no-limit Hold'em.

## Fixed game and independent counts

The [specification](../benchmarks/preflop-expanded-range-v1.json) fixes a 10-chip stack, SB range `AsAd:1,QhJh:0.5,7s6s:0.25,Tc9c:0.75`, BB range `KsKd:0.75,AhKh:1,8s7s:0.5,QcQd:0.25`, and flops `2c3c4d`, `5h6sJc`, `9cTh2d`, `Ks3dQh`. Preflop raises use `[0.5,1.0]`, at most three raises and all-ins; flop bets use `[0.5,1.0]`, raises `[0.5]`, at most one raise and all-ins. Both checkpoints use CFR+ with half-delay averaging, public-vector training/diagnostics, hidden-future grouping and grouped-vector world admission.

Independent rational card counting finds 16 candidate pairs, 15 disjoint pairs, 9,408 ordered future candidates and 91,080 compatible physical worlds. SB `7s6s` overlaps BB `8s7s`. The harness separately checks all four hand/flop blockers from both seats, including the `QhJh`/`KsKd` pair whose fourth flop is blocked by both hands. Each unblocked pair/flop has `45*44 = 1,980` ordered future deals. Pair probabilities use the weight product times the legal deal count, normalized over the entire conditioned joint game; the full rational table has denominator 310. Flop conditioning must therefore retain asymmetric legal masses rather than renormalizing each pair or surviving flop separately.

## Measured accuracy and admission

| Iterations / delay | Full requested modeled work | Independent NashConv | Target met | Complete call plus JSON |
|---|---:|---:|---|---:|
| 500 / 250 | 119,936,982 | 0.000873320081884 | yes | 35.7362464 s |
| 1,000 / 500 | 235,369,982 | 0.000238879222273 | yes | 63.3749922 s |

The unchanged target is `NashConv + 1e-10 <= 0.005`. Padding is conservative, not a formal floating-point error bound. Both policies are independently replayed over all original physical worlds using numeric betting rules and exact legal visible-information best responses. All 1,744 information sets are checked. Maximum production/replay metric difference is `2.220446049250313e-16`. Maximum posterior difference from rational priors is `1.3877787807814457e-17` for production and `2.5618396293225487e-14` for replay, below the `1e-12` tolerance.

Both calls have 1,300 public states and 494 decisions. Hidden-future grouping uses 108 rows keyed by private pair, public flop and discrete showdown sign; future cards remain hidden. Full original-world counts still govern outputs and requested-iteration vector/grouping admission. Both cases were preflighted before any training, and actual budgets match those preflights below the existing 500,000,000 loop-entry cap. The existing grouped-vector option replaces only the old world-count-times-requested-iterations construction proxy with the ten-iteration-per-world guard; this experiment changes no limits. These modeled counts are not memory or runtime guarantees.

Action coverage is checked separately for each completed case: both SB opening sizes (2 and 3), BB 3-bets, regular SB 4-bets, all-ins and the three-raise cap. Each case checks 40 serialized cap rows; these repeat across private hands and are not 40 unique betting histories. Each also includes flop check/call/bet/raise/all-in actions and root bets of 1 and 2. Per-case flop action counts are 420 checks, 1,204 calls, 336 bets, 112 raises and 756 all-ins. These are legal action rows, not frequencies of play.

The timing is one descriptive complete call and JSON serialization per checkpoint on Python 3.12.14, Windows 10. Input preparation, pre-call garbage collection and independent replay are outside the timer. The changed game cannot serve as a paired speed comparison with earlier fixtures. No memory trace or RSS claim is made, and these two checkpoints do not establish general convergence.

## Provenance and reproduction

The frozen source is `ea33dc498f4723f5dd3f832ccbeb2ec60a56da9e`. The [raw report](../benchmarks/results/preflop-expanded-range-v1.json) retains 67 source/specification hashes, full admission records, numeric replay and rational posterior checks, individual case coverage, target results and payload hashes. Source hashes and clean revision were checked at the start and end. Rejected cases and target misses would remain visible; neither case was simplified or retried.

Luna drafted the bounded fixture/harness and reviewed it; the lead independently counted priors and blockers, checked admission wiring, froze and measured the experiment. This adds research artifacts only. Production, shared postflop/turn/river kernels, Coach and dependencies are unchanged. No third-party source was incorporated.

Check out the frozen source with a clean worktree and run:

```powershell
python -m scripts.benchmark_preflop_expanded_range
```
