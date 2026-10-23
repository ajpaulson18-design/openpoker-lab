# Configurable matrix-free TURN original-weight tail

The opt-in research API pokerlab.matrix_free_turn_tail.solve_matrix_free_turn_tail solves one configured heads-up TURN-to-river game with fixed CFR+ sweeps and direct original-sweep tail averaging. It reuses the existing turn range kernel and public tree, carries private hands as vectors, and does not materialize joint hand/runout worlds.

## Call shape

    from pokerlab.matrix_free_turn_tail import solve_matrix_free_turn_tail
    from pokerlab.river_config import RiverConfig

    config = RiverConfig(
        pot=20,
        effective_stack=(18, 32),
        bet_sizes=(0.5,),
        raise_sizes=(0.5,),
        max_raises=1,
        include_all_in=True,
    )
    result = solve_matrix_free_turn_tail(
        "2c5d9hJc",
        "AsAh:0.7,KsKh:0.3,QsQh:0.5",
        "AsKc:0.2,AhKd:0.6,QcQd:1,TcTh:0.4",
        config,
        river_config=config,
        runouts=("3c", "4d", "7s", "8h"),
        iterations=10,
        discard=3,
    )

The board must contain four cards. Range strings use the existing explicit weighted-range parser. With runouts=None, the solver uses all board-legal rivers; an explicit iterable selects a conditioned subset. The result lists requested physical cards under runouts in deck order and compatible branches under reachable_runouts in the matrix-free backend's established lexical order. Policy rows use postflop-strategy-v1: player, private hand, street, public board, public history, and ordered action rows with probabilities. Impossible hand/history combinations are omitted. The result records worlds_materialized=0 and refreshes all eight configured-game metrics: both values, both best-response values, both gains, NashConv, and exploitability.

## Tail and admission semantics

For requested iteration count T and discard D, CFR+ performs the same two alternating regret passes for every sweep from 1 through T. After each completed sweep t>D, its current strategy enters the final average with original weight t, own-player reach, and the original joint-range marginal for that public prefix. The example averages sweeps 4 through 10 with total weight 49. It does not renumber retained sweeps or weight them as t-D; D=0 is intended to preserve the existing matrix-free CFR+ policy exactly.

The accepted input is integer iterations from 10 through 10,000 and integer discard with 0 <= discard < iterations. Discard changes only the average window. Admission accounts for the whole requested schedule and the existing conservative three-pass allowance: 3*T + 3 passes even when D is large. Existing caps remain: 30 million hand-state-pass operations, 1 million information-set action slots, 250,000 public states, 10,000 public decision nodes, 120,000 hand slots, 30 million fallback pair checks, at most 100,000 stable-root pair checks (also restricted by the existing dynamic integer-size guard), and a 7,500-bit stable-root integer bound. Exceptional-conditioning surcharge is included in admission. Exceeding a bound rejects the request before training.

The output distinguishes the admitted three-pass allowance (admitted_training_passes_per_iteration) from the executed schedule: 2*T regret passes and T-D average passes.

This API offers no alternate target or convergence stopping rule, cache, range abstraction, or new frontend/default behavior. It is fixed-sweep CFR+ for the configured finite game only; it makes no general Hold'em equilibrium or convergence claim. Matrix-free storage and zero materialized worlds describe the representation, not a measured speed or memory advantage. No RSS or throughput claim is made.

## Validation status and next work

Focused T=10 contract tests are authored for D=0 comparison, a positive-discard materialized control, blocker and selected-runout cases, all-in and separate street configs, exceptional conditioning, full-schedule admission, and concurrent-call isolation. These twelve new tests and twenty-eight existing matrix-free/materialized-tail regressions passed together under normal Python (40 tests, 90.345 seconds). After clarifying the admission metadata, the twelve new tests plus four immutable T6000 saved-policy regressions passed (16 tests, 13.515 seconds). All forty integrated tests also passed under optimized Python (98.816 seconds), with the three candidate/test source hashes identical before and after execution. After requiring exact admission for both fixtures and removing test-order dependence, all three independent tests passed again under optimized Python (4.321 seconds). The full hosted CI matrix remains pending at this revision. Independent source review found no blocking averaging, information-boundary, chip-transition or admission defect.

The independent tests use a second board with blockers, flush/straight possibilities, unequal stacks, short all-ins, distinct street sizing, three selected rivers and the full deck. They compare every legal action, own sequence realization and globally weighted action flow against the materialized tail; all eight metrics replay through independent numeric rules within 1e-9. Both fixtures passed exact scan/partition replay under the existing 100,000-work, depth-64, 65,536-bit caps; the exact eight-metric maps agree across chance grouping and project within 1e-9 of independent numeric replay. For the matrix-free selected fixture, scan/partition used 7,643/7,481 work and at most 976 Fraction bits; the full-deck fixture used 70,400/33,880 work and at most 274 bits. Both reached depth 8. These fixed controls now require exact-auditor admission; a future capacity regression fails the test with its retained error. These bounded T=10 controls execute real training and do not measure convergence.

Run python -B -m unittest tests.test_matrix_free_turn_tail tests.test_matrix_free_turn_tail_independent tests.test_matrix_free_turn tests.test_turn_tail_adapter -v, and repeat with -O. The [materialized direct-tail specification](direct-turn-tail.md) describes the independent training control; [the fixed T6000 experiment](turn-class-tail-T6000-experiment.md) remains unchanged. Next measure preregistered accuracy on held-out river games, then assess broader turn convergence. Performance and memory measurements need separate experiments.
