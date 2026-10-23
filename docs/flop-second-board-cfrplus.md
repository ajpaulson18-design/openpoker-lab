# Second-board flop CFR+ pilot

This is a separate research adapter for the fixed weighted `7c8d9h` flop game
whose complete no-training equivalence proof is published in
[PR #213](https://github.com/ajpaulson18-design/openpoker-lab/pull/213).
It reuses the existing configurable betting tree and unchanged project-owned
alternating CFR+ recurrence. It does not change production defaults, shared
turn/river implementations, the Coach surface or prior published experiments.

## Fixed game and prerequisite

The literal ranges remain OOP `AsAd:1,QsQd:1/2` and IP
`AsKh:1/4,KsKd:1`. Global blocker conditioning excludes the colliding
`AsAd/AsKh` pair and gives compatible pair priors `8/13,1/13,4/13`.
The pot is 10 chips, stacks are 5 chips, each street offers a half-pot bet,
with no raises or separately offered all-in action. Stack-capped bets can
still have an `all_in` action name.

Authenticate the complete saved proof before each fresh model preparation.
The proof establishes 5,940 physical worlds and all 30,812 physical numeric
states; the compact game has 170 worlds, 1,270 states, 400 decisions,
68 chance nodes, 802 terminals and 608 own-hand information rows (304/304).
The exact compact numeric tree SHA256 is
`5b8b6d504a35e0023c9150476ba9bb91d10615eae9ec6bb0305071745ab98152`.
These are fresh second-board authorities; original-board dimensions and
quality results do not authenticate this game.

## Admission and resource meaning

Admit the entire requested integer iteration count before saved-proof
authentication or fresh ranking/model preparation. Booleans, floats,
nonpositive counts and counts above 560 reject. Authenticate the unchanged
CFR+ and strategy-kernel LF hashes. A distinct versioned logical-work forecast
uses 170 worlds, 608 two-action own-hand rows and a maximum 33-node all-action
path per world. All two regret passes and the completed-profile average pass
are charged; averaging delay is zero.

The named forecast is 180,227 units per sweep plus 65,368 setup/output units,
including the explicit 170-entry binary64 mass sum. T140 reserves 25,297,148
units and T560 reserves 100,992,488 units. Each request must fit the separate
110,000,000-unit second-board envelope. This does not widen the original
76,000,000-unit adapter cap or any production resource policy. The fixed
two-call batch reserves 126,289,636 named logical units under its separate
140,000,000-unit aggregate ceiling.

Proof-pass, exact-response, numeric-replay, row-table, rank, source and output
limits are admitted as separate families. Logical training units are not a
bound on those operations, all internal arithmetic, elapsed time, allocated
Python bytes or process RSS. Partial storage bookkeeping counts action slots,
not bytes. Board and iteration differences do not support a controlled speed
comparison with earlier experiments.

## Training and independent output checks

Each call constructs a fresh proof-owned model and validates the full model
before training inputs are admitted. All exact joint masses must be positive
and sum to one; binary64 conversion must preserve positive support and its
sum must remain within the stated numerical tolerance. Validate all 608
information keys and two-action counts, the player split, numeric tree hash
and every deterministic-chance/all-action world path before training.

Call the unchanged shared trainer exactly once, outside the complete
41-authority preparation and diagnostic guards. Retain every raw average row,
then apply the existing explicit binary output-grid normalization and retain
its receipt. The published normalizer's 466-row cap is preserved: after cheap
validation of the complete raw output, normalize two 304-row player batches
and combine the count and exact maximum-distance receipts. Lift the normalized
rows into all 16,912 physical own-hand rows,
including zero-reach rows, with all 33,824 action probabilities. Projection
must preserve all compact binary64 probabilities bitwise.

Compute all eight rational metrics separately for the compact game and the
full physical game. The unrestricted physical response sums hidden opponent
hands and future chance before maximizing separately for the responder's own
hand; it cannot observe those hidden variables. Require exact compact/full
agreement and separate numeric physical replay within `1e-10` chips. The
fixed pot-10 game supports the existing generic exact metric routine's
5-chip half-pot constant. Revalidate the full model on exit, including failure
paths, and preserve the original error if a cleanup check also fails.

## Frozen pilot and retained outcomes

The pilot requests fresh independent T140 and T560 calls, in that order.
Every normalized output receives its own exact physical NashConv quality
gate of `1/200` chip (`0.005`). Retain a failed gate; do not discard or rerun
it. Two budget observations are not a convergence theorem, a guarantee of
monotonic improvement or evidence about unrestricted NLHE. Exact responses
describe the normalized output, without asserting parity with raw averages.

Freeze the executable, protocol and clean committed source inventory before
the single batch. Retain each complete adapter report losslessly, including
raw averages, normalized physical policy, normalization, exact/numeric metrics,
guard counts, partial observations and errors. Capture wall/CPU durations as
execution receipts only. Stop after the first failed call and preserve all
available output without retry; output fallback and nondurable in-memory
retention must be identified explicitly.

The pre-measurement review passed 37 focused tests on bundled CPython 3.12,
including a direct load/admission of the actual protocol with poker computation
and saved-proof authentication forbidden. The protocol LF SHA256 is
`75c0e30819a0632594b93bc29994ef764559eac33245b44d321dcef6eb261f87`.
Run `python -m scripts.benchmark_flop_second_board_cfrplus --output-dir PATH`
only from a clean frozen checkout, with a new output directory outside the
repository. Complete reports are retained independently of quality-gate misses.

At this implementation stage no second-board training has run and no quality
result is claimed. The actual frozen batch must precede any reported result.
This independently written adapter
uses project-owned components and the Python standard library; no third-party
source or dependency is incorporated. Method provenance remains the existing
[CFR+ documentation](flop-class-cfrplus.md) and the published second-board proof.
