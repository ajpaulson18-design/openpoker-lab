# Exact requested-accuracy stopping for bounded preflop games

`solve_preflop` accepts paired opt-in `target_nash_conv` and `convergence_check_interval` arguments for positive-delay CFR+ with public-vector training and diagnostics. `iterations` remains the requested ceiling. The solver checks the completed-sweep average at each interval and the final off-interval sweep, after averaging has positive weight. It stops when the configured-game exact visible-information best-response gap plus `1e-10` meets the requested target.

```python
result = solve_preflop(
    "AsAd,QsQd", "KsKd,JhJc", config={"starting_stack": 2, "max_raises": 0,
                                                "include_all_in": False},
    runouts=["2c3c4d7h8h"], iterations=90, averaging_delay=45,
    algorithm="cfrplus", traversal="public-batched", diagnostics="public-batched",
    resource_model="public-vector", target_nash_conv=0.005,
    convergence_check_interval=10,
)
```

This example is conditioned on one selected complete deal. It does not represent an unconditional flop or full-deck preflop solution. A target can remain unmet at the ceiling.

The averaging delay remains fixed when stopping. Fresh nonalias snapshots prevent callbacks from changing training state; snapshots are released promptly. Matching final diagnostics are reused. `completed_iterations`, actual regret/average pass counts, `convergence_checkpoints`, `convergence_target_reached`, `stopped_early` and `convergence_stop_reason` distinguish completed work from requested work. Default fixed-iteration paths and payloads remain unchanged.

Before training, the distinct `preflop-public-vector-convergence-budget-v3` envelope admits the entire requested ceiling, every scheduled snapshot, every possible positive-average exact check and one conservative extra final evaluation. The existing limits remain in force. A loose target cannot bypass admission even when an early stop is likely. These counters describe modeled loops and allocation slots, not elapsed-time or RSS guarantees.

The [frozen specification](../benchmarks/preflop-convergence-stop-v1.json) and [harness](../scripts/benchmark_preflop_convergence_stop.py) separate three questions:

- The existing complete two-flop game retains its 90-iteration/delay45 ceiling and 0.005-chip target. Each selected flop includes every ordered future deal, with joint physical conditioning and blockers.
- Three alternating complete-call timing pairs use a separate complete fixed-first-flop game, ceiling40/delay10, interval5 and a predeclared 0.05-chip target. Fixed calls always complete 40. Both policies are independently assessed against that same timing target; their final accuracy can differ. This timing target does not weaken the two-flop accuracy target.
- A weighted asymmetric selected game requests 1e-12, below the numerical padding, to preserve an explicit target miss and verify exact fixed-ceiling policy parity. A separate two-flop 10/delay5/interval5 trace measures Python allocations while checkpoint diagnostics coexist with live trainer state.

Each final policy is independently replayed from numeric poker rules, physical posteriors and complete legal visible-information best responses. Same-completed-iteration fixed-run policies must match exactly. Smaller integration tests independently reconstruct and replay every recorded checkpoint. Large-game checkpoint history contains production diagnostics; it is not a separate independent replay of every intermediate policy.

The [frozen report](../benchmarks/results/preflop-convergence-stop-v1.json) started clean at source `4efd3abfd5b1fb0295c696283a3487d7b4f1da1d`. Its 52 source hashes, specification hash and historical-report hash were rechecked unchanged after measurement.

| Fixture | Completed / ceiling | Independent NashConv chips | Target chips | Target met |
| --- | ---: | ---: | ---: | --- |
| Complete first flop, fixed | 40 / 40 | 0.0102805716162 | 0.05 | Yes |
| Complete first flop, accuracy stopped | 20 / 40 | 0.0256998756694 | 0.05 | Yes |
| Complete two flops | 80 / 90 | 0.00395041187793 | 0.005 | Yes |
| Weighted selected game | 35 / 35 | 0.00104129877443 | 1e-12 | No |
| Separate two-flop memory run | 10 / 10 | 0.0947992878543 | 0.005 | No |

The complete two-flop checks at iterations 50/60/70/80 reported gaps 0.0209177/0.0102317/0.00610575/0.00395041. All 30,128 final information sets and both complete best responses were independently checked. The stopped policy exactly matched a fixed 80/delay45 run. The requested 90-iteration ceiling plus all possible checks reserves **477,115,154 modeled loops**, below the unchanged 500-million limit. Its one complete adaptive call took 93.332 seconds; this is not a paired comparison against the historical 90-iteration time.

The three fixed-ceiling timing calls took 24.237/24.378/26.477 seconds, versus 13.177/14.067/14.481 seconds for accuracy stopping. Medians were 24.378 versus 14.067 seconds, ratio 1.733, or about 42.3% lower observed elapsed time on this fixture. Stopped policies met the requested target but had a larger gap than fixed-ceiling policies. Same-completed-iteration policy parity was exact. This measures saved work at a requested accuracy, not equal final-policy accuracy.

The separate complete ten-iteration two-flop peak was **80,467,842 traced Python bytes** (about 76.7 MiB). That short run missed the accuracy target, as expected; memory evidence is not evidence of convergence. No controlled memory improvement is claimed.

The local full suite passed 561 tests in 406.306 seconds; the final additional admission test passed in the six-test focused convergence suite. GitHub's frozen-source matrix passed 562 tests on Python 3.11/3.12/3.13, with the three established instrumentation skips on 3.11. Luna reviewed the frozen implementation and the measurement methodology.

Runtime includes complete solving and JSON serialization; pre-call garbage collection, independent replay and extra policy-parity calls are excluded. Allocation measurement includes complete solving and JSON, with runout arguments preallocated; independent replay, native allocations and RSS are excluded. Timing pairs share one host and establish no universal speedup. The ten-iteration memory trace supplies no high-iteration guarantee or controlled historical memory comparison.

A cProfile selection run on the prior two-flop10/delay5 implementation placed averaging at about 7.2% of complete instrumented solve time. This motivated requested-accuracy stopping before adding a new averaging traversal plan and its memory cost. The profile is not a runtime comparison.

Checkpoint orchestration was independently implemented around this repository's existing delayed CFR+ and exact diagnostics. The established completed-sweep own-reach delay schedule is unchanged. No third-party source, dependencies, commercial outputs or policies were incorporated. Luna implemented the bounded snapshot hook and budget tests, and reviewed integration; lead implemented solver admission/orchestration and independent measurements.

Exact best responses enumerate the configured binary64 finite game with floating-point tolerances. The `1e-10` target padding is conservative, not a formal floating-point error bound. Targets below it cannot be certified. Full-deck preflop, broad ranges, multiway and unrestricted NLHE remain outside scope. Shared postflop/turn/river kernels and AI Coach are unchanged.

```text
python -m unittest tests.test_preflop_convergence tests.test_preflop_delayed_cfrplus tests.test_preflop_vector_budget -v
python -m scripts.benchmark_preflop_convergence_stop
```
