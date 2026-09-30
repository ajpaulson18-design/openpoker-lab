# OpenPoker Lab

**Study poker decisions against the people who actually play them.**

OpenPoker Lab is an independent, open-source research app combining Hold'em
simulation, persistent opponent observations, transparent expected-value analysis,
and a working counterfactual regret minimization (CFR) river solver.

The destination is an opponent-aware poker decision engine. This first release
connects the pieces end to end while making the supported games and assumptions
explicit. It does **not** claim to solve unrestricted no-limit Hold'em.

## Run locally

Requires Python **3.11 or newer**. There are no runtime dependencies, API keys,
subscriptions, or external AI services.

```sh
git clone https://github.com/ajpaulson18-design/openpoker-lab.git
cd openpoker-lab
python -m pokerlab.server
```

Open **http://127.0.0.1:8765**. On Windows, `py -3 -m pokerlab.server` also works
when the Python launcher is installed. Stop the server with Ctrl+C.

Optional installation: `python -m pip install .`, then `openpoker`.
Choose another port with `--port 8766`, or another database with
`--database path/to/research.sqlite3`.

## What's included

| Workspace | Functionality |
| --- | --- |
| Decision lab | Heads-up fold/call or check/bet EV, with explicit current and calling ranges, a baseline comparison, and opponent-informed fold probabilities |
| Equity | Up to five opponents; weighted ranges; blockers; split pots; seeded Monte Carlo; exact heads-up river enumeration |
| Opponents | Named profiles; Bayesian updates from observed opportunities; street filtering; uncertainty intervals; notes and JSON export |
| River solver | Full-traversal CFR over compatible private hand pairs; mixed strategies; exact best-response gap; optional opponent node locks |
| Explanations | Deterministic short, normal, and beginner explanations of structured strategy results, with evidence and field-level provenance |
| Hand sandbox | 2–6 named players; positions and blinds; no-limit betting; short all-ins; side pots; odd-chip settlement; visible hole cards and named action history |

### A useful first session

1. Open **Equity**, run the default aces-versus-random example, then add another
   `random` line to see the multiway change.
2. Create an opponent in **Opponents**. The starting profile is a subjective prior,
   not a fact about that person.
3. Record actual fold-to-bet opportunities on a particular street. Both folds and
   non-folds matter. Never enter unobserved opportunities as “No.”
4. In **Decision lab**, select that opponent and enter a hand on the same street.
   Compare actions, read the assumptions, and try different calling ranges.
5. In **River solver**, solve the default compact game. Then lock the opponent's
   call frequency and observe how the out-of-position strategy changes.
6. In **Hand sandbox**, enter the players' names in clockwise order. Those names
   follow every action and pot award while seat numbers preserve table position.

## Model boundaries

### Equity and decision analysis

Equity is a share of the pot at showdown, including ties. Monte Carlo intervals
describe **sampling error only**, not range misspecification. They use a normal
approximation and can be misleading at extreme probabilities or small samples.
River heads-up equity is enumerated exactly under the supplied range weights.

Decision EV excludes rake, raises, stack caps, and later betting. Enter feasible
bet/call sizes yourself. Before the river this is a **checkdown model**, not a
multi-street solution. When facing a bet, the current pot includes that bet.
The comparison baseline uses an illustrative 45% fold frequency; it is not GTO.
A separate calling range is important because continuing hands are not generally
a random subset of the opponent's starting range. Fold rate and calling range
are independent scenario inputs here, not a jointly calibrated behavioral model.

### Opponent learning

Each tendency uses its own Beta prior with an effective sample size of 10 and
updates from explicitly counted opportunities. The model currently tracks VPIP,
PFR, 3-bet, fold-to-bet, aggression, and shown-hand bluff rates independently;
there is deliberately no global “fish score.” The shown interval is a clipped
normal approximation to the posterior. Confidence labels describe sample size,
not validated predictive accuracy.

Unknown/default, Calling Station, Nit, Maniac, Loose-Passive, Tight-Passive,
Overbluffer, and Underbluffer/Honest Player archetypes provide starting priors,
not fixed scripts. Sufficient contrary evidence outweighs every archetype.

The profile dashboard pools streets; decision analysis uses only the matching
street. Programmatic observations may also carry position, action context, and
explicit qualifiers when those facts were actually observed. Unspecified
observations remain in the pooled dashboard. The
human-aware river adapter consumes an immutable, street-filtered model snapshot.
It confidence-blends supported posteriors toward the reference node frequencies
and records the exact node-lock assumptions. Aggregated aggression does not
identify betting frequency conditional on a check, and aggregate fold data does
not identify a hidden-card range or hand-specific calling frequencies.

Showdown bluff observations are selection-biased. VPIP, PFR, and related summary
statistics cannot by themselves recover an opponent's hidden-card range.
There is no automatic poker-site hand-history parser in this release: observations
and notes are recorded manually. Export is available; bulk import is future work.

### Solver game

The solver begins on a fixed five-card board with two supplied weighted ranges.
Out of position can check or bet one fixed size. After a check, in position can
check or bet that size. A player facing a bet can fold or call. There are **no
raises, future streets, rake, stack constraints, or multiway solver branches**.

The solver enumerates compatible deals, preserving private information and card
removal. Average strategies are reported by information set. Utilities are
zero-sum chip values relative to half the existing pot. `nash_conv` is the sum of
both players' improvements from exact best responses to the average strategies;
`exploitability` is half that sum. Best responses aggregate indistinguishable
opponent hands **before** choosing an action.

Node locks may be uniform or hand-specific. With opponent node locks, the
unrestricted gap measures the exploitability of the resulting profile, not
convergence in the locked game. The separate
`oop_best_response_gain` measures remaining improvement for the unlocked player.
Strategies at unreachable information sets need not be meaningful.

For responsiveness, range-size product times iterations is capped at 3 million.
Full 1,326-combination range solving and full-game GTO are outside this release.

## Range notation

Separate tokens with spaces or commas:

- `AA`: six combinations; `TT+`: tens through aces.
- `AKs`: suited; `AKo`: offsuit; `AK`: both.
- `AJs+`: AJs, AQs, AKs. Higher rank first.
- `AsKh`: one exact combination.
- `AA:0.5`: every AA combination has weight 0.5.
- `random`: every legal combination with weight 1.

Known cards are removed. Later overlapping tokens override earlier tokens.
Weight zero removes a combination. Dash intervals and percentage ranges are
not supported. Multiway simulation independently draws weighted opponent hands
and rejects colliding deals to avoid sequential-renormalization bias.

## Data and local access

Opponent observations and decision reports are stored in `data/pokerlab.sqlite3`.
Use **Export local research** to download a JSON copy. Sandbox hands are held
in memory and are not persisted across server restarts. Local data is ignored
by Git and is never included in the repository.

The app binds only to `127.0.0.1`, validates Host and Origin headers, accepts JSON
mutations, limits concurrent computations, and uses a restrictive content security
policy. This is a local research app, not an authenticated public hosting service.

## Tests

```sh
python -m unittest discover -s tests -v
python -m scripts.validate_evaluator
```

Tests cover hand categories and kickers, seven-card versus best-five ranking,
weighted ranges, exact ties and equity, seeded simulations, model persistence,
duplicate observation handling, side pots, short raises, random legal hands,
solver convergence and node locks, and local HTTP access controls.

The optional exhaustive evaluator check enumerates all 2,598,960 five-card hands
and compares category totals against the known combinatorial counts. CI runs the
unit suite on Python 3.11, 3.12, and 3.13.

## Reading the code

Start with [`docs/architecture.md`](docs/architecture.md). The human-aware layer
boundaries and shared contracts are documented in
[`docs/human-aware-strategy.md`](docs/human-aware-strategy.md). The implementation
uses Python's standard library, plain JavaScript, HTML, and CSS so the algorithms
and assumptions stay visible. No proprietary solutions, interfaces, or poker
databases are included.

## Development direction

- Conditional opponent models by street, position, sizing, and action history.
- Structured history import with explicit opportunity definitions.
- Range inference with calibration and held-out evaluation.
- Larger solver abstractions, multiple bet sizes, raises, and additional streets.
- Strategy benchmarks and repeated-match evaluation against documented policies.

Contributions should include a reproducible scenario, the modeled assumptions,
and tests that measure poker correctness or statistical behavior. See
[`CONTRIBUTING.md`](CONTRIBUTING.md).

MIT licensed. Research software; no performance or profitability claims.
