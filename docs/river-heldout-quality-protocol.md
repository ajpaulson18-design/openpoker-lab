# Held-out RIVER accuracy protocol v1

Status: preregistered fixed cases and no-training resource design. This specification precedes the four actual calls; results and any failure will be recorded separately.

## Purpose and scope

This is a new held-out fixed-board river slice beyond the two existing
small-range fixtures: the polarized bluff-catcher and weighted raise games in
`river-cfrplus-accuracy-extension-v1`. It broadens rank and action coverage
without changing the solver, oracle, shared CFR, or any earlier-street code.
Each case has exactly four weighted holdings per player on a complete board.
Both existing river backends would run fixed CFR+ for exactly 10,000 completed
iterations, with no solver stopping target. The reporting threshold is fixed at
absolute chip NashConv `<= 1/1000`; report all four profiles and retain misses.
No retries, tuning, or new cases may be selected after observing training.

These are synthetic finite-game cases. Their coverage and any eventual
finite-iteration policy quality do not imply unrestricted Hold'em or commercial
solver accuracy. No known equilibrium values are claimed for either case.

## Frozen candidate cases

Range weights are positive and unequal within each player. The grammar supports
weights up to 1; the values below are the frozen input text, not approximate
frequencies to be rescaled after seeing outcomes.

| ID | Complete board | OOP range | IP range | Pot / stacks | Bet / raise / cap |
|---|---|---|---|---|---|
| `river-unpaired-blocker-tie-raise` | `AhKdQcJs2d` | `AsTc:1,3c4c:0.25,9c9d:0.75,5c6c:0.5` | `AsKh:0.5,QhTh:0.75,8c8d:0.25,6c7d:1` | 100 / `(120,80)` | bet `0.33`, raise `0.25`, `max_raises=1`, all-in enabled |
| `river-paired-short-spr-rank-extremes` | `9h8h7h2c2d` | `6h5h:0.75,AhKh:0.25,9c9d:1,2h2s:0.5` | `JhTh:0.5,QhKh:1,8c8d:0.75,7c7d:0.25` | 100 / `(70,80)` | bet `0.25`, raise `0.25`, `max_raises=1`, all-in enabled |

The first case has an unpaired board, two cross-range blocker collisions, and a
physical `AsTc` versus `QhTh` tie under independent best-five ranking. The
second has a paired board, short SPR below 1 for both players, and independent
rank categories spanning flush, full house, quads, and straight flush. Both
trees include bet, raise, call, fold, check, and all-in actions. This gives
explicit tie/collision and short-stack/rank-extreme coverage without adding
range size or cap pressure.

## Solver and validation protocol

The two cases crossed with the two existing backends produce four immutable
profiles:

- `materialized`: `solve_postflop(..., algorithm="cfrplus", iterations=10000,
  traversal="public-batched", diagnostics="public-batched")`.
- `matrix-free`: `solve_matrix_free_river(..., algorithm="cfrplus",
  iterations=10000)`.

Run each fixed profile once in a source-frozen process. Keep complete-call
timings only as uncontrolled host observations, with no speed or memory claim.
Before and after the four calls, hash all production Python sources, the
numeric replay/rank references, exact Fraction helper, case manifest, and
runner. Any source drift invalidates the run. Keep complete UTF-8 LF policy
files and raw SHA-256 values; reload each saved file and replay again.

For every saved policy, first run `turn_river_validation.replay_policy` on the
original 4x4 weighted ranges, then `compare_result` on all eight published
metrics and independent counts at `1e-9` absolute chip tolerance. The oracle
must globally condition the exact physical compatible-pair masses and use
independent best-five ranks and visible-information legal best responses.
After the successful numeric replay, run the unchanged bounded exact helper
with its existing limits (100,000 logical work, depth 64, 65,536 Fraction bits)
on the explicitly normalized binary64 policy rows. The exact audit is
secondary arithmetic over the independently validated model; it is not a
second rules implementation and does not prove that raw float rows were exact
rationals. Recompute and check every result row after saving. A profile that
exceeds any existing admission or replay cap is a preserved rejection, not a
reason to raise a cap or omit the profile.

The threshold is a reporting threshold only, not a solver stop condition. A
miss remains in the report and in the policy folder. This design does not
promise any of the four profiles will meet it.

## No-training preflight evidence

`scripts/river_heldout_preflight.py` constructs the finite public action trees but does not invoke a
solver/trainer. It cross-checks decision/terminal/action counts between the
production public tree constructor and independent numeric replay tree; it
enumerates the exact positive compatible-pair support; it independently ranks
all eight holdings per case; it builds a uniform complete test policy solely
to exercise replay and exact-audit dimensions; and it computes the unchanged
10,000-sweep CFR+ admission formula. This uniform policy's large NashConv is
only a harness smoke value, not quality evidence.

The original no-training design receipt (2026-10-23) established the following dimensions, reproduced against current source before implementation. The portable preflight must reconstruct and retain them afresh before any solver call:

| Case | Compatible pairs | Decisions / public states | Info rows / action slots | Matrix-free 10k charge | Materialized 10k charge | Exact smoke work / depth / max bits |
|---|---:|---:|---:|---:|---:|---:|
| Unpaired blocker/tie/raise | 14 | 10 / 27 | 40 / 104 | 3,240,324 | 4,200,000 | 5,024 / 5 / 56 |
| Paired short-SPR/rank-extremes | 15 | 10 / 27 | 40 / 104 | 3,240,324 | 4,500,000 | 5,305 / 5 / 56 |

The matrix-free formula is `max_hand_count * public_states * (3*T + 3)`;
the materialized formula is `compatible_pairs * decision_nodes * T * 3`.
Both remain below the unchanged 30,000,000 ceilings at `T=10,000`. Public
states, decisions, action slots, fallback-pair checks, independent physical
world/work limits, and exact work/depth/Fraction-bit limits are also recorded
in the receipt. The exact smoke profile used the unchanged 100,000 / 64 /
65,536 caps and stayed far below them; actual trained profiles still must pass
the same caps dynamically.

Preflight assertions passed using the bundled Python runtime. No CFR call,
training run, solver output, or retrospective case selection occurred. This is
capacity evidence only; it does not predict NashConv or guarantee future
profiles will pass every dynamic exact-arithmetic guard.


## Executable and evidence lifecycle

The separate scripts/river_heldout_preflight.py constructs both cases without training. It checks the complete production and independently reconstructed legal tree/action metadata and refund-aware terminal model, then replays a synthetic complete production-tree policy through the independent numeric rules and bounded exact helper. Literal board, range and sizing identities must match this specification; equal counts or retained case IDs alone are insufficient. This smoke policy is not quality evidence.

The separate scripts/benchmark_river_heldout_quality.py requires an explicit expected forty-character source commit. Every production Python module, numeric/rank/exact reference, preflight, runner and this specification must match that committed Git snapshot, with raw and normalized LF identities recorded. HEAD, tracked/untracked status and source inventories must remain stable before and after calls and validation. All four requests pass the original complete-work admission before the first actual solver call.

An exclusive durable run claim permits one batch in its attempt location. Store raw canonical LF policies immediately after each API returns and before validation; keep first errors and partial receipts on any later failure, without retry. Use ignored workspace output during the frozen run; publication copies are separate after acceptance. Reload each saved policy for independent replay. The final target_met flag uses exact normalized-binary64 Fraction NashConv <=1/1000 when the exact audit admits, and remains null if exact admission or validation fails. A separately named numeric flag may report the floating-point replay result. Keep raw numeric and exact misses distinct, and never replace a failed batch with a successful rerun at the same claim.

Actual runtime observations cannot establish controlled speed comparisons or memory bounds. A passed finite-game target is not an exact equilibrium-value certificate or commercial solver parity. These case definitions and the four T10000 budgets must remain unchanged after learned output is observed.

## Running and validation status

Use Python 3.11 or later. After reviewing, committing and publishing the complete executable/protocol source, verify the clean frozen snapshot and then run one batch:

    python -B -m scripts.benchmark_river_heldout_quality --expected-source-commit <reviewed-40-character-commit> --attempts-dir <new-directory-outside-checkout>

The attempt directory must be outside the production checkout and must not contain an earlier claim or result. This keeps source status clean throughout all four calls. Source authentication compares the full production Python inventory and every required helper/spec/runner byte against committed Git blobs, normalizing only line endings, and retains raw SHA-256 identities separately.

Eight lifecycle, exact-replay, model-identity and actual Git source-authentication regressions pass in normal and optimized Python. They use synthetic uniform policies and mocked solver returns, with no actual CFR training. The production and independent complete trees match for both cases, including decimal 0.33 sizing and unmatched-wager refunds. Trained policy outcomes remain pending; preserve all target misses and errors in the later result record.
