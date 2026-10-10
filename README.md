# OpenPoker Lab

**Study poker decisions against the people who actually play them.**

OpenPoker Lab is an independent, open-source research app combining Hold'em
simulation, persistent opponent observations, transparent expected-value analysis,
and working counterfactual regret minimization (CFR) river and finite postflop solvers.

The destination is an opponent-aware poker decision engine. This first release
connects the pieces end to end while making the supported games and assumptions
explicit. It does **not** claim to solve unrestricted no-limit Hold'em.

## Run locally

Requires Python **3.11 or newer**. There are no runtime dependencies. The app
works offline with external AI disabled; an API key is only needed if you
explicitly configure the optional one-shot coach described below.

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

## Optional one-shot AI coach

External AI is disabled unless you set `OPENPOKER_AI_COACH_ENABLED=1`,
`OPENAI_API_KEY`, and `OPENAI_MODEL` before starting the server. The saved-decision
panel also requires you to select **Use external AI for this question** for each
request. That sends the question, hero cards, board, and other allowlisted facts
for the selected decision to the configured OpenAI service. Opponent hole cards,
the deck, names, and notes are excluded. It does not send the raw hand event or
persist a conversation. The request uses the Responses API with structured output and
`store: false`; see [local coach setup](docs/ai-coach-setup.md) for details.

## What's included

| Workspace | Functionality |
| --- | --- |
| Decision lab | Heads-up fold/call or check/bet EV, with explicit current and calling ranges, a baseline comparison, and opponent-informed fold probabilities |
| Equity | Up to five opponents; weighted ranges; blockers; split pots; seeded Monte Carlo; exact heads-up river enumeration |
| Opponents | Named profiles; Bayesian updates from observed opportunities; street filtering; uncertainty intervals; notes and JSON export |
| River solver | Full-traversal CFR over configurable river bet/raise sizes and compatible private hands; mixed strategies; exact best-response gap; confidence-weighted legacy node locks |
| Turn-to-river solver library | Configured betting on both streets; exact physical river chance, card blockers, full-history policies and exact best-response gaps; Python API |
| Shared postflop solver library | Flop, turn or river starts; ordered physical turn/river chance; per-street sizing with cumulative commitments; bounded exact best responses |
| Explanations | Deterministic short, normal, and beginner explanations of structured strategy results, with evidence and field-level provenance |
| Hand sandbox | 2–6 named players; live or hidden coaching; reproducible decision history and session review; short all-ins, side pots, and odd-chip settlement |
| Coach voices | Five offline deterministic presentation styles; every voice preserves the same recommendation, EVs, frequencies, confidence, and analysis ID |

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
   Toggle Live Coach without changing the saved calculation, and choose a coach
   voice to change delivery without changing strategy.

Version 0.2.0 is the appropriate next minor release: it adds backward-compatible
opponent-aware analysis, coaching, review, and presentation capabilities while the
public API remains pre-1.0.

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
The immutable `RiverConfig` supports pot-relative first-bet and raise sizes,
effective stacks, optional all-ins, and an explicit maximum raise depth. It
solves only the configured heads-up river action abstraction; it does not solve
future streets or claim unrestricted river GTO.

The solver enumerates compatible deals, preserving private information and card
removal. Bet fractions multiply the current pot. A raise fraction multiplies
the pot after calling; the resulting raise-to total includes the player's
existing commitment and call amount. Minimum full raises, short all-ins,
reopening, stack caps, duplicate actions, and returned uncalled excess are
modeled explicitly. See [`configured river validation`](docs/configured-river-validation.md)
for the exact configuration semantics and worked examples. `effective_stack`
can be a shared scalar or an `(OOP, IP)` pair for unequal stack caps.

Expanded configurations are available through the Python `solve` and
`solve_equilibrium` APIs. The browser's fixed-bet form uses the optimized
compatibility path. Vanilla CFR remains the default; `algorithm="dcfr"`
selects DCFR(1.5,0,2). Both return exact best-response gaps and the versioned
`river-strategy-v1` profile. DCFR is not uniformly faster or more accurate at
every checkpoint; measured results are in [solver progress](docs/solver-progress.md).

Average strategies are reported by information set, with different chip-size
histories kept separate. Utilities are zero-sum chip values relative to half
the starting pot. `nash_conv` is the sum of both players' improvements from
exact best responses to the average strategies; `exploitability` is half that
sum. Best responses aggregate indistinguishable opponent hands **before**
choosing an action.

Node locks may be uniform or hand-specific. With opponent node locks, the
unrestricted gap measures the exploitability of the resulting profile, not
convergence in the locked game. The separate
`oop_best_response_gain` measures remaining improvement for the unlocked player.
Strategies at unreachable information sets need not be meaningful.

For responsiveness, range-size product times iterations is capped at 3 million;
public trees and deal-node work are also bounded. Full 1,326-combination range
solving and unrestricted no-limit GTO are outside this release. See
`docs/solver-validation.md` for the exact scope, validation, the
`pokerlab.equilibrium` strategy interface, and `python -m scripts.validate_solver`.

### Turn-to-river library

`pokerlab.turn_solver.solve_turn_river` extends the configured action tree across
both streets, enumerating 44 physical river cards per compatible private pair.
It carries matched commitments and stack caps, preserves full public history,
and reports exact information-set best responses under `postflop-strategy-v1`.
Optional selected runouts explicitly condition the entire joint physical game.
See [turn-to-river validation and examples](docs/turn-river-validation.md).
Optional `traversal="planned"` prepares static traversal operations to reduce
repeated training work, with bounded plan storage; recursive is the default.
See [traversal comparison](docs/planned-traversal.md).
This Python API is additive; the browser's solver remains its fixed river form.
The compatible turn entry point now delegates to the shared postflop engine.

### Shared postflop library

`pokerlab.postflop_solver.solve_postflop` accepts three-, four- or five-card
boards. A flop start enumerates 45 then 44 physical future cards for each
compatible private pair. It reuses the configured betting builder and the CFR
backends, and hides each future card until its public reveal. Full-deck flop
solving currently fits only small games under the resource limits; selected
ordered runouts define a conditional study game. See [postflop examples and
validation](docs/postflop-validation.md). Full-deck preflop, broader practical ranges and
eventually multiway equilibrium remain development goals.

Optional `traversal="public-batched"` shares exact training work across private
hands at each public node. Recursive remains the default and reference. This
backend retains physical chance weights and adds a 250,000 prefix/hand-edge
storage cap; it specializes the postflop fold/showdown utilities. See
[public-batched validation and measurements](docs/public-batched-cfr.md).

The three production training kernels also have a
[known small-game accuracy check](docs/cfr-known-quality.md), with independently
enumerated best responses and quantitative convergence gates. Run
`python -m scripts.validate_cfr_quality --output benchmarks/results/cfr-quality-v1.json`
to reproduce it. This checks the kernels on Kuhn poker, alongside the separate
Hold'em physical-world and betting validation.

An additive [heads-up preflop betting component](docs/preflop-betting.md)
constructs blind-aware actions and explicit flop/all-in continuation boundaries.
It reuses the existing action and CFR interfaces, including the big blind's
option after a limp. Continuation leaves remain unsolved; this component does
not itself supply preflop equilibrium strategies. The additive
[bounded preflop solver](docs/preflop-solver.md) now connects it to physical
flop chance and the existing postflop trees, with independent serialized-policy
replay and exact legal best responses. Selected five-card outcomes condition
the whole joint game; this is not an unconditional full-deck preflop solution.
Optional recursive [preflop CFR+](docs/preflop-cfrplus.md) has independently
replayed best responses and measured comparisons with vanilla/DCFR; existing
defaults are retained.
Optional [delayed CFR+ averaging](docs/preflop-averaging-delay.md) exposes the
published weight schedule through isolated preflop adapters, with independent
reference/replay checks. Delay zero remains the default.
Optional [preflop private-hand vectors](docs/preflop-public-batched.md) preserve
the configured game and exact responses, with measured range comparisons and
explicit memory and numerical limits.
Optional [vector value and best-response diagnostics](docs/preflop-public-diagnostics.md)
reuse that utility-preserving view to compute the configured game's legal
responses, with independent replay validation. Recursive diagnostics remain
the default.
An opt-in [vector workload model](docs/preflop-vector-resources.md) bounds
shared public traversal and scratch dimensions before admitting deeper
complete fixed-flop solves. Legacy resource admission remains the default;
independent legal best responses measure each checkpoint's actual accuracy.
The [independent monetary replay](docs/preflop-monetary-replay.md) checks the
configured local rounding order exactly and retains a separate historical
precision diagnostic.

[Indexed selected-outcome blockers](docs/preflop-runout-index.md) reduce preflop
physical-world setup work while retaining the existing admission ceilings and
exact conditioned-game outputs. Optional [chance-sampled CFR](docs/preflop-chance-sampled.md) records exact final diagnostics, resource limits and multi-seed accuracy misses.

Explicit [two-flop structural admission](docs/preflop-two-complete-flops.md) covers two selected flops with every legal ordered future deal, independently replayed policies and exact legal responses. Its preflop-local delayed CFR+ optimization preserves policy numbers while removing redundant work; full-deck preflop remains outside scope.

Optional [exact requested-accuracy stopping](docs/preflop-convergence-stop.md) checks legal best responses to completed delayed-CFR+ average policies and reports actual completed iterations, checkpoint history and target misses. Admission still reserves the full requested ceiling and all possible checks before training; default fixed-iteration behavior is unchanged.

A [target-delta plan experiment](docs/preflop-target-plan-prototype.md) preserved exact policies but failed its predeclared runtime gate and increased traced allocations. It remains a reproducible research helper; production solvers do not use it.

Opt-in [private-index compaction](docs/preflop-private-compaction.md) removes globally inactive hand slots for delayed public-vector CFR+, with original policy identities, independent replay and versioned copy/work admission. Its frozen two-flop benchmark recorded about30% lower median complete-call time on a shape with globally inactive hands, essentially equal traced Python peaks, and an independently replayed higher-iteration policy meeting the stated accuracy target; the feature remains opt-in and model limits are explicit.

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
Additional tests cover zero and tiny samples, contradictory and extreme evidence,
blocked cards, personality invariants, hidden-information safety, session
reproducibility, coaching visibility, all-ins, and side pots.

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

Non-all-in preflop raise coverage and retained structural admission limits: [probe evidence](docs/preflop-raised-coverage.md).
