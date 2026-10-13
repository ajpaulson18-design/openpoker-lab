# Independent turn and river validation

## Sol diagnosis and cycle 1 specification

Baseline: `46e142be8e9585005e5de70bb32bf4a76f731a1c`, dedicated
`solver/turn-river-validation-20261013` branch. The owner explicitly assigned
turn/river to this session and preflop/flop to a separate workstream.

Matrix-free turn integration currently replays serialized policies through
production world construction, betting-tree construction and best-response
evaluation. This detects representation/backend discrepancies but can miss a
shared betting-rule, utility, information-set or chance-law error. Existing
Fraction payoff tests and synthetic no-peek tests cover important components;
they do not independently replay a complete raised turn/river policy.

Implement a development-only `scripts/turn_river_validation.py` numeric replay.
Share only the established card/range grammar and the independent best-five
ranker in `scripts/preflop_validation.py`. Do not import production betting,
utility, solver, CFR, terminal kernel or diagnostic helpers. Do not change
preflop/flop code, shared kernels, public contracts, defaults, UI or Coach.

### Mathematical requirements

For each board-compatible disjoint private pair and legal selected river,
assign its original binary64 range-weight product as an exact Fraction. Normalize
once over all physical deals. The constant 1/44 cancels in a conditioned turn
game. Full deck means all 48 board-excluded public candidates, with 44 legal
rivers per compatible pair. Complete river boards have no future chance.

Rebuild actions from numeric state: original pot, each player's cumulative
commitment/cap, prior full-raise increment, raise count, reopened flag, checks,
public history and current public board. Match configured binary64 sizing and
nine-decimal amount cleanup deliberately; do not call the production builder.
Opening fractions use original pot plus cumulative commitments. Raises use
pot after calling and the minimum full increment, with stack clipping and
short-all-in reopening rules. Calls settle, unmatched excess is refunded,
river begins OOP first, and an all-in settlement has no subsequent actions.
Payoff is signed `(original_pot / 2 + matched_contribution)`, or zero on a tie.

Validate every serialized row, including off-policy rows: own hand, player,
street, exact board/history, ordered legal action names/amounts/targets/tokens,
finite nonnegative probabilities summing to one. Reject missing, duplicate,
extra, malformed or future-card-leaking rows; use explicit exceptions, not
assertions that disappear with `python -O`. Keep zero-reach worlds for auditing.

Replay profile EV and both exact legal best responses. Separate responding
private hands at the root, integrate hidden opponent hands before maximizing,
and partition public rivers only after the reveal. At OOP response nodes choose
max of integrated OOP values; IP chooses min, then negate the final expectation.
Report values, BRs, NashConv, exploitability, checked row/world counts and
private-pair/public-river probabilities. Add a comparison function with explicit
absolute tolerance, finite checks and count checks supporting both existing
materialized and matrix-free result schemas.

### Acceptance and independent review

- Replay both entry points across vanilla/DCFR/CFR+ on weighted blocker games.
- Cover river raises, unequal stacks, short all-ins, distinct river sizing,
  turn all-in continuation, selected-river posterior shifts and all 44 legal
  rivers of a single compatible pair. Scalar agreement within `1e-9` chips.
- Check the known one-bet polarised river Fraction equilibrium and zero gap
  independently. Add exhaustive pure-policy BR cross-check for a tiny game.
- Deliberately corrupt policy probabilities, metadata, actions, rows and metrics;
  the oracle must reject each corruption. Future card and hidden-hand identities
  cannot create legal decision conditioning.
- Meaningful focused tests, full repository suite, documentation validation,
  exact GitHub head/CI checks, and Sol source/mathematical review before merge.
- Record actual measurements and target misses; this is verification of a
  finite abstraction, not unrestricted Hold'em or a formal binary64 error bound.

The information-set and best-response design follows the original
[CFR paper](https://papers.nips.cc/paper_files/paper/2007/hash/08d98638c6fcd194a4b1e6992063e944-Abstract.html)
and [public-tree best-response paper](https://johanson.ca/publications/poker/2011-ijcai-abr/2011-ijcai-abr.pdf),
reviewed October 13, 2026. No third-party solver implementation is incorporated.

## Prioritized backlog

1. Independently replay complete configured turn/river policies and diagnostics.
2. Investigate cancellation, probability-support loss and convergence labels
   under adversarial range weights, after an independent replay is available.
3. Measure equal-wall-time accuracy on broader turn/river ranges; investigate
   turn training bottlenecks only after values/BRs have independent validation.
4. Consider additional sizing coverage or averaging schedules with fixed
   quality/cost criteria; retain default/reference behavior and existing caps.

## Sol cycle 2 specification: nonnegative diagnostic gains

An injected accepted-roundoff reproduction at the baseline exposes an internal
diagnostic inconsistency in both isolated matrix-free entry points. At pot 100,
an evaluator returning `(value=0, BR0=1e-9, BR1=-1e-9)` passes the existing
`1e-10 * scale` legal-BR guard. Each result reports OOP gain `1e-9` and IP gain
zero, but sums the signed gains first and reports NashConv/exploitability zero.
A requested zero target therefore stops after ten iterations as `target-reached`.
This is a fault-injected tolerated-roundoff case, not a measured natural failure.

In an exact zero-sum game both unilateral deviation gains are nonnegative.
If small negative floating-point BR differences are accepted under the existing
guard, clamp each unilateral gain separately before summing. Keep materially
invalid/nonfinite diagnostics rejected, preserve all training, probability,
action, admission and default/reference behavior, and edit only
`matrix_free_turn.py`, `matrix_free_river.py` plus their tests. Do not change
shared postflop/preflop/flop diagnostics in this isolated cycle; record that
shared follow-up explicitly for its owners.

Require fixed and target modes to satisfy `NashConv = OOP_gain + IP_gain` and
`exploitability = NashConv / 2`. Test both signs of tolerated negative error,
both adapters, a true nonnegative profile, and material/nonfinite rejection.
A positive gain must prevent a zero target being certified. Re-run independent
full-policy replay and normal strategies/metrics against baseline; disclose any
roundoff-level metric changes rather than inventing bitwise identity. This
clamping consistency rule is not a rigorous floating-point error bound.

## Development record

Sol inspected current main, active worktrees/PRs, matrix-free implementations
and existing component/integration tests. Luna implemented the independent
oracle and 13 tests; Sol reviewed the physical law, numeric betting semantics,
hidden-information best responses, input rejection and resource guards. The
implementation was frozen at `431db6f261a3df21c1ccf5be17b96af485c1770c`, based
on main `323ce3030dfa10d2a11dbeb314b7a76ca222d984` after a documentation-only
main update. No production, shared CFR, preflop or flop source changes occur
in cycle 1.

### Executed cycle 1 validation, October 13, 2026

The [complete machine-readable report](../benchmarks/results/turn-river-independent-v1.json)
records 52 unchanged source/specification SHA-256 hashes, interpreter/platform,
all fixtures, scalar differences, and raw timing samples. Run with:

```text
python -m scripts.benchmark_turn_river_independent --output benchmarks/results/turn-river-independent-v1.json
```

Four fixtures, two backends, three algorithms, three iteration ceilings
(20/100/300), and three repeats produce 216 complete calls and 72 rows.
Every complete serialized policy, value and both legal best responses passed
independent replay at the predeclared absolute tolerance of `1e-9` chips.
Repeated complete payloads were identical. The maximum scalar disagreement
was `3.907985046680551e-14` chips. Full turn checks cover 176 physical worlds
and 1,112 information sets; the conditioned raised turn covers eight worlds
and 138 information sets. All policies, including off-policy rows, are checked.

Every measured profile missed the unchanged `0.001`-chip NashConv target.
The following independently measured gaps at 300 iterations apply to both
backends up to the scalar agreement above:

| Fixture | Vanilla | DCFR | CFR+ |
| --- | ---: | ---: | ---: |
| Full 44-river blocked game | 1.47715512 | 0.02149704 | 0.01611100 |
| Two conditioned rivers, asymmetric multisize | 3.23491921 | 1.81179328 | 0.04694023 |
| Polarised river bluffcatcher | 2.87361498 | 2.29465832 | 0.20754699 |
| Weighted river raises | 2.91977182 | 0.51274093 | 0.04211258 |

Complete-call timing includes deterministic JSON serialization; replay is
timed separately. Other work ran on this shared Windows host. These are raw
observations, not controlled speedup, equal-cost quality or memory evidence.
No RSS or allocation peak was measured. Accuracy here means agreement with
an independent finite-game replay, not achievement of the quality target,
a formal floating-point bound, larger-game coverage or commercial parity.

The 13 new tests passed normally and with `python -O`. They include a known
rational one-bet equilibrium, exhaustive tiny-game pure-policy BR comparison,
future-card no-peek, weighted blockers, full deck, short all-ins, decimal
sizes and corrupted-policy rejection. Documentation validation passed.
The full Python suite passed in GitHub CI on 3.11, 3.12 and 3.13 at the frozen
implementation head. A normal local baseline suite ran 629 tests with 14
Windows temporary-file/SQLite permission errors. The affected 35 tests passed
outside that sandbox with a unique project-local TEMP/TMP directory; no
persistence production changes were made to disguise an environment failure.

The oracle bounds physical-world preallocation, public-tree construction and
modeled world/node passes, plus separate exact-BR work counters. These are
development admission guards, not wall-time/RSS guarantees. Card/range grammar
and the independent ranker are shared as stated above. Optional result labels
`runout_mode` and `reachable_runouts` were not checked in cycle 1; numeric input law,
selected rivers, actual worlds and policy rows are checked. Metadata hardening
is a later validation slice. Cycle 2 changes diagnostics after this frozen run
and requires its own acceptance evidence.

### Cycle 2: preserve each unilateral gain

Both isolated adapters now compute `max(0, BR0 - value)` and
`max(0, BR1 + value)` separately, then sum them for NashConv and divide by two
for exploitability. The finite-value and legal-response lower-bound guards,
their tolerance, all trainers, policies and resource admissions are unchanged.
The accepted-roundoff example in the specification now reports gap `1e-9`
and exploitability `5e-10`; a zero target continues through both checkpoints
at iterations 10 and 20 and ends at the iteration limit. Both orientations of
the error are covered. This is diagnostic consistency under the existing
tolerance, not a proved error bound or a naturally observed convergence bug.

Luna implemented the two small adapter edits and eight new tests. Sol reviewed
the complete diff, both error orientations and stopping behavior. The combined
two matrix-free test modules and independent replay module passed 42 tests in
103.841 seconds; after strengthening iteration assertions, the six targeted
diagnostic tests passed in 15.353 seconds. The regressions check fixed/target
modes, accepted negatives, positive deviation preservation, true-zero early
stopping, material negative responses and NaN/positive/negative infinity in
every evaluator component. Real unpatched profiles also satisfy the metric
identities. Full final-head CI passed on Python 3.11/3.12/3.13 at
`7563bc3618fa4eb10b6a9ad9170c53f8ed6e9b7e`; PR111 merged and that head was
verified as an ancestor of main `119f96d10ad638a6e0bde02110d079fb8c22d00d`.

The [ordinary-profile parity report](../benchmarks/results/turn-river-gains-parity-v1.json)
checks four existing fixtures, all three algorithms, and fixed/zero-target
modes at 20 iterations: 24 old/new profile pairs. Every complete result is
identical to the frozen baseline adapter, and every new profile passes
independent replay, with maximum scalar disagreement `3.91e-14` chips.
This result covers these ordinary fixtures; the deliberate accepted-negative
injections change diagnostic values and stopping as described above.
No performance improvement is claimed.

Reproduce on this slice's checkout with unchanged shared dependencies:

```powershell
New-Item -ItemType Directory -Force work/gain-baseline
git show 431db6f:pokerlab/matrix_free_turn.py | Set-Content -Encoding utf8 work/gain-baseline/baseline_matrix_free_turn.py
git show 431db6f:pokerlab/matrix_free_river.py | Set-Content -Encoding utf8 work/gain-baseline/baseline_matrix_free_river.py
python -m scripts.validate_turn_river_gain_parity --baseline-dir work/gain-baseline --output work/gain-parity.json
python -m unittest tests.test_matrix_free_turn tests.test_matrix_free_river tests.test_turn_river_independent_validation
```

The parity harness verifies canonical historical adapter fingerprints before
import, uses the current checkout's unchanged shared dependencies, and records
all current source hashes plus supplied historical file hashes. It refuses a
different historical adapter or source mutation during the run. This is a
bounded development comparison, not a new production solver option.
Shared postflop diagnostics have the analogous signed-sum pattern; their
follow-up is explicitly deferred to the shared/preflop/flop owners. No shared
diagnostic or earlier-street source was modified here.

### Cycle 3: complete-result metadata and gain validation

Complete-result replay now requires the public board, selected runouts,
runout mode and physically reachable runouts, plus `info_sets` and a physical
deal-count alias appropriate to the starting street. Optional config fields
retain their existing compatibility. Deliberately stripped legacy fragments
are no longer accepted as complete solver results. Every present world/pair
count alias must be a matching nonnegative integer; bool and float lookalikes
are rejected. Counts of materialized storage are not confused with logical
physical-world counts.

Mode follows whether the input selected runouts were omitted or explicitly
provided; an explicitly complete candidate set remains `conditioned-subset`.
Reachability derives from independently enumerated positive-mass physical
worlds, so an everywhere-blocked selected card remains in `runouts` and is
absent from `reachable_runouts`. The existing matrix-free serializer uses
lexical reachable-card order while the materialized serializer uses DECK
order. Both documented canonical orders are accepted; incorrect support,
duplicates, invalid types and other permutations are rejected. Production
serializers remain unchanged.

`compare_result` checks eight scalar fields, adding both published unilateral
gains, and verifies nonnegative gains/gaps, zero-sum values, NashConv=sum gains
and exploitability=NashConv/2 within the caller's absolute tolerance. All count
aliases are checked rather than stopping at the first one. Before clipping,
independently computed BR values receive finite and material lower-bound
sanity checks under the documented scale-relative tolerance. This is a sanity
check, not a formal floating-point error bound.

Luna implemented the bounded oracle/test changes, and Sol reviewed the code,
mixed-rank serializer ordering, every alias and tolerance-isolated identity
tests. Five new test methods extend the focused suite to 18 tests: all passed
normally (6.558 seconds) and under `python -O` (6.487 seconds). Corruptions cover
missing/current metadata, zero-support reachability, explicit full selection,
both serializer/street variants, bool/float/negative/mismatching counts, both
gain fields, metric identities and independent-BR lower bounds.

The [hardened replay report](../benchmarks/results/turn-river-independent-hardened-v1.json)
retains all 24 complete 20-iteration profiles (four fixtures, two backends,
three algorithms), source hashes, all eight scalar differences and every
quality-target miss. Every full policy passes replay, with maximum scalar
disagreement `3.907985046680551e-14` chips. Every 0.001-chip target misses.
Single raw timings are retained for transparency, without a performance or
memory claim. Historical 216-call measurements remain pinned to the cycle 1
source; this is fresh acceptance evidence for the hardened oracle only.

```text
python -m unittest tests.test_turn_river_independent_validation
python -O -m unittest tests.test_turn_river_independent_validation
python -m scripts.benchmark_turn_river_independent --iterations 20 --repeats 1 --output benchmarks/results/turn-river-independent-hardened-v1.json
```

Full final-head CI and remote blob verification remain merge gates. No
production solver, trainer, preflop/flop, UI or Coach changes are included.
