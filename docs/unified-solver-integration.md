# Unified OpenPoker Lab solver: architecture review

**Current authority update (D036, October 24, 2026):** the owner revoked the pause
for their review, delegated architectural and implementation acceptance to the
agent, and requested continuous goal-driven integration work until instructed
otherwise. The audit below preserves the initial review snapshot. Its references
to waiting for owner approval are superseded by [D036](decisions/DECISION_LOG.md).
Architecture, independent validation and implementation reviews remain mandatory
and are performed autonomously by the Sol-led team.

October 24, 2026. **Status: audit complete; architecture and implementation tasks
proposed for owner review. Implementation has not launched.**

Audited repository main is `ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251`.
Sol led the architecture audit; Luna inventoried reusable components and validation.
The review records the owner's integration priority; it does not record approval
of the proposed technical design.

## Main finding

The repository already contains a mathematically coupled, bounded four-street
game in `preflop_solver.solve_preflop(postflop_scope="all-streets")`. It builds
one combined preflop/postflop action-and-chance tree and trains one complete
strategy profile. Its independent replay and selected-game quality evidence
already exist. Integration should establish one supported contract around that
path, preserve its kernels, and strengthen whole-game acceptance rather than
start another solver implementation.

The existing game conditions on selected complete board outcomes. It is not
full-deck preflop with live betting on every street. A new facade alone would
not remove that limit or establish a new equilibrium certificate.

## Review decisions requested

1. Adopt the existing all-streets combined-root path as the reference integration
   foundation, retaining recursive CFR as the first compatibility oracle.
2. Approve additive solver contracts and explicit adapters for SB/BB identity,
   cumulative monetary history, joint physical chance/reach, and strategy output.
   Reuse the current internal tree types; defer simulator migration and kernel
   replacement.
3. Make the first implementation milestone a small conditioned four-street game
   with independent whole-game replay, legal best responses and a declared quality
   gate. Keep exact equilibrium/value certification separate from floating replay.
4. Keep native, matrix-free, class and sampled paths behind capability checks;
   admit them into a whole-hand solve only after proving their operator semantics
   match the enclosing game. Existing standalone policies are not continuation
   value functions.
5. Use the milestone/task sequence below: Luna performs bounded implementation
   and tests; Terra handles difficult implementation/debugging; Sol decides
   architecture. Major refactors and implementation assignments wait for review.

## Current evidence and publication boundary

The focused baseline passed **196 tests in 189.438 seconds** on bundled Python
3.12.14. The local full suite, evaluator sweep and native builds were not rerun.
The original test command had one incorrect module name; the corrected complete
run passed. The validation record preserves both facts.

Open PRs #229, #230, #231 and #232 remain unmerged at this snapshot; their
candidate count/audit/quality tools are not included in audited-main capability.
The review does not require or perform those merges. Legacy commit-status lists
were empty and are not check-run success evidence.

No solver, test, native source, action rule, algorithm, resource guard or
benchmark artifact changes are part of this documentation proposal.

## Audited source census

The machine-readable inventory covers 68 library
Python modules, 237 script modules,
308 test modules, 3 native
source files, and 623 benchmark artifacts
(527 under results). It indexes source
definitions and lines, records raw checkout hashes separately from Git identity,
and preserves benchmark snapshots. Native signature extraction is a bounded text
scan, not a C parser; source inventory is not correctness validation.

See the [component inventory](architecture/unified-solver-components.md), [machine-readable source and benchmark inventory](architecture/unified-solver-inventory.json), and [executed validation record](architecture/unified-solver-validation.md).

# Sol architecture review: one bounded four-street solver

Status: audit and design proposal, 2026-10-24. No implementation or new solver experiment was launched by this review. Baseline is GitHub main `ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251`, checked out in the isolated integration checkout. Every source reference below is to that revision. Root owns current executed validation, active-work inventory, decision-register changes and publication. Root reports 196 focused baseline tests passing in 189.438 seconds across 19 modules on this pin, including preflop shared-prefix/weighted/monetary controls, known Kuhn quality, recursive/planned/public CFR and matrix-free/ranked tails. This review did not independently rerun those tests. Historical test/benchmark records below are identified as historical.

## Decision recommended for owner review

Use the existing selected-outcome `solve_preflop(..., postflop_scope="all-streets")` composition as the first integrated four-street engine. Add a small, explicit request/result contract and a thin facade around it, then establish a single frozen integration/certificate corpus. Do not replace the recurrence, introduce another graph engine, or splice independently optimized street policies into a purported whole-game equilibrium.

This is a continuation of verified work. The existing engine already couples preflop, flop, turn and river in one extensive-form game. The missing integration work concerns a canonical supported entry point, explicit identity/money/chance/reach semantics, coherent whole-game acceptance evidence, and a controlled expand-then-optimize roadmap. Broader full-deck coverage and stronger accuracy remain separate goals.

The current audit satisfies the planning stage only. Stop before changing core solver ownership, numerical rules, public schemas, admission rules or kernel implementations; present the concrete proposed implementation and evidence gates for owner review.

## What the pinned implementation establishes

1. **One complete game is built before one trainer runs.** `preflop_solver.py` enumerates a single physical joint world distribution, constructs the blind-aware preflop tree, grafts every live continuation/flop to the existing postflop builder, and then constructs all information sets. The trainer receives the combined root and the same world list. This is not an independent preflop solve followed by detached flop/turn/river solves. [Preparation and infos](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/preflop_solver.py#L677-L710), [grafting](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/preflop_solver.py#L415-L530), [training and whole-game diagnostics](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/preflop_solver.py#L794-L903).

2. **The postflop part contains live later-street decisions.** In all-streets mode `_build_public_tree(3, ...)` receives independent flop/turn/river action specifications. Settled flop betting reveals a turn, settled turn betting reveals a river, and all-in continuations preserve the hidden remaining chance integration. Cumulative matched commitments carry forward rather than granting another stack each street. [Postflop composition](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/postflop_solver.py#L171-L279).

3. **Identity is already translated across the position change.** Preflop player 0 is SB/button and player 1 is BB. Postflop templates locally use OOP=BB and IP=SB. `_clone_template` reverses actor/winner identity and converts local terminal commitments and sized targets back to the whole-hand SB/BB ledger; the world rank sign is reversed for the temporary template. [Translation](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/preflop_solver.py#L307-L351), [local world mapping](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/preflop_solver.py#L472-L511).

4. **Private information and earlier-street learning are globally coupled.** A decision key is `(global_actor, actor_own_hand_index, complete_public_history)`. Future cards and the opponent hand are absent. The recursive trainer traverses all downstream actions before accumulating the earlier action's counterfactual value; regrets use opponent reach and averages use own reach. Public-batched traversal preserves the same separation with private-hand vectors. [Keys and visible prefixes](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/preflop_solver.py#L230-L289), [recursive recurrence](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/cfr.py#L33-L89), [vector reach and values](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/public_cfr.py#L379-L499).

5. **Chance is one globally conditioned physical law.** Initial independent range weights are multiplied for compatible private pairs, each selected canonical-flop/ordered-turn/ordered-river world receives its physical deal mass, and the entire selected joint distribution is normalized once. Blocking selected worlds can change private-pair priors before any betting. Public chance nodes partition that law; they do not invent independent per-street probabilities. [World construction](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/preflop_solver.py#L137-L227).

6. **Whole-game legal responses already exist.** Production BR groups worlds by the responder's own hand, sums public chance branches, and maximizes over actions without seeing hidden opponent/future cards. The independent preflop verifier replays serialized rows from separate numeric rules and best-five ranking. [Production BR](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/cfr.py#L111-L153), [independent rules boundary](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/scripts/preflop_validation.py#L124-L162), [independent action validation and hidden-hand BR](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/scripts/preflop_validation.py#L270-L294), [whole-game metrics](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/scripts/preflop_validation.py#L399-L452).

7. **Meaningful integration evidence is already present.** `tests/test_preflop_solver.py:163-195` uses shared flop/turn prefixes with opposite river winners and independently replays the result. `tests/test_preflop_validation.py:50-64` covers a weighted asymmetric live game with raises and separate street sizes. `tests/test_preflop_public_batched.py:59-80,143-150` checks weighted/multiflop/shared-prefix backend agreement for vanilla/DCFR/CFR+. These are existing tests, not evidence gaps. Root is rerunning the relevant baseline modules separately. The historical preflop benchmark retained 24 checkpoints and independent value/BR comparisons, including live four-street games; its old source, machine, finite-iteration quality and timing qualifications remain attached. [Historical benchmark and oracle record](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/docs/preflop-solver.md#L123-L159).

## Exact remaining gaps and boundaries

- **Coverage:** full-deck preflop with live postflop betting is explicitly rejected. One compatible pair already has 34,246,080 canonical-flop/ordered-turn/river outcomes. Selected outcomes are a conditional game, not an unbiased full-deck approximation. [Fail-closed boundary](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/preflop_solver.py#L152-L163).
- **Abstraction:** finite heads-up action menus, raise depths and stack caps define the game; no rake or multiway equilibrium. The current postflop builder has no blind-sized minimum opening bet. Calling it general legal NLHE would silently change the model. [Declared limits](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/docs/preflop-solver.md#L85-L107).
- **Canonical external boundary:** current preflop rows already cover four streets but use a preflop-named API/schema. Postflop/river APIs use local OOP/IP identity, different root-pot conventions and different result envelopes. The shared graph types are private imports. A small explicit facade and contract should explain these differences and preserve old payloads, rather than creating an unrelated graph representation. [Shared types](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/river_tree.py#L18-L44), [preflop result envelope](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/preflop_solver.py#L920-L1001).
- **Money:** the configured implementation uses binary64 and nine-decimal local action quantization before whole-hand translation. Exact-decimal/global-rational arithmetic is not equivalent at every boundary. Preserve the configured model and the existing historical diagnostic; do not silently impose one new quantizer. [Canonical monetary specification](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/docs/preflop-monetary-replay.md#L3-L23).
- **Acceptance:** historical quality and current small tests are useful but do not establish a newly declared unified acceptance gate, full-range convergence, or performance after consolidation. Add explicit whole-game posterior/reach, upstream/downstream dependence and exact-normalized certificate checks to the existing evidence rather than claiming no end-to-end validation exists.
- **Specialized tails:** matrix-free/ranked river, turn, fixed-flop symmetry, checkdown counts and selected-runout adapters have separate proven scopes. A direct call to an isolated equilibrium tail solver is not automatically a valid leaf evaluator for the coupled whole game. A tail adapter would have to preserve the actual conditioned joint law, player reach, public history, commitments and units, and participate in the same global updates.
- **Simulator and product contracts:** `game.py` is a mutable integer-chip sandbox with street-total raises and side pots; `contracts.py` includes validated analysis/Coach evidence; `models.py` stores observations and decision evidence. None is currently the canonical equilibrium-game request or training state. Do not force them into the solver internals during this milestone. [Simulator scope](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/game.py#L1-L5), [analysis contract](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/contracts.py#L291-L325), [decision persistence](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/models.py#L479-L524).

## Canonical interfaces to approve

These are semantic boundaries and additive validated views, not a proposal for another state machine. Keep existing `_Node`, `_Chance`, `_Terminal`, action order and trainer callbacks as the implementation representation initially.

| Boundary | Required meaning | Minimal first integration |
| --- | --- | --- |
| Game request | Heads-up global seats SB=0/BB=1, total starting stacks before blinds, explicit blind amounts, action-only menu per street, selected chance model, algorithm/backend, requested budget, diagnostics and numerical model version | A frozen request contract in a small solver-specific module and a `solve_four_street` facade calling existing `solve_preflop` with all-streets scope; defaults/old APIs unchanged |
| Public state | Actor, street, revealed board, complete public history, cumulative whole-hand commitments, remaining stacks, last-full-raise/reopening context where needed | Validated read-only state/replay view derived from existing history and numeric rules; no mutable simulator object in training |
| History and actions | Perfect-recall public history; unsized tokens remain check/fold/call; sized tokens carry the existing whole-hand `raise_to`; reveal tokens preserve canonical flop then ordered turn/river; `amount` is chips added | Keep existing token format and raw serialization. Any typed event view must round-trip exact existing tokens and amounts |
| Prior ranges | Concrete physical two-card hands, positive supported prior weights, explicit canonical hand order and blocker compatibility | Preserve `expand_range` parsing and its zero/duplicate semantics; provenance records the original expressions plus normalized hand order, not a different range grammar |
| Chance law | One immutable joint physical support and mass law for `(SB hand, BB hand, flop, turn, river)`, conditioned once on selected outcomes | Preserve the current seven-field world rows internally; label conditional scope and include a canonical support/mass identity in the new envelope |
| Reach at a boundary | Base joint world law plus separate SB and BB sequence reach along the complete action history; public chance prefix uses absolute joint prefix mass | A documented/read-only reach receipt for validation first. Do not replace correlated joint support with two independent posterior marginal ranges |
| Policy | One row per `(global actor, own physical hand, complete public history)`, fixed ordered action slots, no opponent/future keys, normalized probabilities and complete zero-reach rows | Reuse `preflop-strategy-v1` rows unchanged. New envelope may say `four-street-solve-v1` while retaining the actual underlying solver version and schema |
| Value/quality | Whole-hand chip EV from before blinds, zero-sum SB/BB values; full-game legal BRs; NashConv and NashConv/2 explicitly named; numerical/certificate scope | Preserve current raw metrics. Add evidence status and certificate identity, never overwrite raw policy or relabel approximate floating diagnostics as exact proof |
| Resource admission | Full requested training and diagnostics budget, graph/world/view/transient bounds and separately bounded exact replay work | Reuse existing admission and expose a consolidated receipt. No relaxed cap, speculative whole-solver speed claim or RSS guarantee |
| Product evidence | Deterministic immutable solver result and provenance consumed by adapters | Existing Coach/analysis/store boundaries stay separate; any later UI uses explicit unavailable states for unsupported contexts |

The reach distinction is essential: at public history `h`, the reached joint mass is proportional to `base_mass(world) * reach_SB(own_hand,h) * reach_BB(own_hand,h)`. Blockers and selected cards already correlate the base support. Multiplying two independently normalized marginal posterior ranges generally changes that joint game. Counterfactual values additionally use the opponent's reach rather than both players' reached posterior. Preserve this distinction throughout the facade and any future tail optimization.

Any terminal optimization must reproduce the existing whole-hand payoff. The public-batched positive-pot view already preserves that payoff by a power-of-two shift of terminal contributions; reuse its identity and its separate copy admission. Do not delete the shift merely because a single unified facade looks cleaner. [Utility-preserving view](https://github.com/ajpaulson18-design/openpoker-lab/blob/ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251/pokerlab/preflop_solver.py#L359-L412).

## First frozen integration fixture

Proposed candidate `four-street-weighted-shared-future-v1`; not executed or admitted during this audit. Existing weighted/shared-prefix fixtures remain mandatory controls.

```text
SB range: AsAd:0.5,QsQd:0.25
BB range: KsKd:0.75,JhJd:0.25
Blinds: 0.5 / 1
Starting stacks: 8 / 8, including blinds
Preflop: raise_sizes=[0.5], max_raises=1, include_all_in=False
Flop/turn/river: bet_sizes=[0.5], raise_sizes=[], max_raises=0,
                 include_all_in=False
postflop_scope="all-streets"
runouts:
  2c3c4d7h8h
  2c3c4d7hKc
  2c3c4dKc8h
  2c3c4dQd8h
  5c6d7s8c9h
  5c6d7s8cJc
```

Analytic support expectation: four compatible private pairs, two public flops, 22 legal physical worlds. `Qd` blocks one outcome for each SB QQ pair. With relative pair weights 6:2:3:1, the joint conditional normalizer is proportional to 68; pair probabilities in the logical order AA/KK, AA/JJ, QQ/KK, QQ/JJ are `36/68, 12/68, 15/68, 5/68`. Independent enumeration must verify these anchors before production training. These are mathematical predictions for the proposed input, not measured receipts.

This combines live blind decisions/raises with multiple flop branches, distinct turns, and opposite-winner hidden rivers under the same flop/turn prefix. The unraised branch can place half-pot investments on all three postflop streets: matched whole-hand amounts `1 -> 2 -> 4 -> 8`. Under the raised preflop boundary, the different pot/remaining-stack context must survive into subsequent sizing. Clipped sizes can become all-in even with `include_all_in=False`; that flag disables an extra shove option, not stack clipping of configured bets.

Tests must validate these properties, not require any guessed strategy frequency:

- Every street has legal action rows; at least one structurally legal line has live decisions through river. An equilibrium that folds earlier does not remove required off-path rows.
- Worlds sharing own hand and visible history map to one row even when the hidden next card changes the winner. A clairvoyant per-world response is an invalid oracle and must be rejected or demonstrably exceed the legal response in a hand-computable adversarial control.
- Complete public action histories distinguish reached postflop contexts. Independently prescribed hand-dependent earlier policies produce the correct downstream joint posterior and counterfactual reach. Include an asymmetric, blocker-correlated existing control so marginal-factorization errors cannot pass this check by accidental independence.
- For a fixed legal earlier policy, changing only a legal river continuation policy changes the independently computed upstream action value on a selected common prefix. This establishes actual cross-street dependence without assuming a monotonic training trace or changed argmax. Build the difference from two explicit rational control profiles, compute its nonzero rational anchor before training, and freeze it with the fixture.
- Numeric replay checks cumulative amounts, pot/stack conservation, refunds, stage reset/reopening semantics, unchanged SB/BB ownership, and every serialized zero-reach row.
- Keep separate short-blind, unequal-stack, fractional-rounding, blocker-shift and hidden-flop adversarial controls already present. The dyadic integration fixture cannot replace the fractional monetary boundary control.

Proposed fixed quality run after independent admission: exactly one `T=1000`, CFR+, zero-delay, full public-batched training/diagnostics, explicit public-vector resource model, existing legacy tree admission and all other defaults fixed. No early stopping, chance sampling, private compaction, hidden-future grouping or new optimization. Full requested three-pass work and diagnostics must be admitted first. Recursive/public-batched short controls compare the same algorithm/game within existing documented tolerances; planned controls use vanilla/DCFR because planned CFR+ is unsupported.

Predeclare exact-normalized whole-game NashConv `<= 1/1000` big blind as the quality gate (`BB=1` here). One failed gate is a recorded miss, not authorization to increase iterations or change the fixture. One resource rejection is an unknown quality result, not a pass and not permission to raise caps. A higher fixed budget or a new model requires a separate reviewed version with the original result retained.

## Whole-game independent certificate

First retain configured numeric replay using `scripts/preflop_validation.py`, whose oracle shares only input parsing with production and independently reconstructs ranking, betting and hidden-information responses. Existing backend parity alone is insufficient.

Then add a separately versioned bounded exact-normalized audit for saved complete four-street policies. Reuse the existing exact-audit protocol and arithmetic/normalization principles from `scripts/turn_rational_certificate.py:14-79,111-178,320-389`; that helper is currently tied to its independent turn validator and OOP/IP row schema, so it cannot simply be passed a production preflop tree. Any adapter must expose independent preflop numeric states/rows with explicit SB/BB identities and retain that independence. Do not globally monkey-patch the old helper or rewrite old artifacts.

Required certificate definition:

1. Authenticate committed source, complete request, raw serialized result and all fixture identities before replay; preserve the raw bytes and source map after replay.
2. Enumerate legal physical private-pair/runout support independently. Define exact conditional world masses from the declared dyadic priors and integer support, not rounded display probabilities. Compare production masses and metrics with separately declared float tolerances.
3. Reconstruct configured terminal constants using the independent monetary rules and convert their binary64 values explicitly to exact fractions. The integration fixture is dyadic; other money controls retain their configured quantization semantics.
4. Convert each finite nonnegative serialized binary64 probability to its exact rational image, divide by the exact row sum, and preserve every raw-to-normalized adjustment, action identity and canonical normalized-policy hash. The certificate concerns this normalized policy; it is not a raw-binary64 interval proof.
5. Replay the entire four-street profile and legal best responses with hidden opponent hands and future cards integrated before action maximization. Require exact `L <= V <= U`, where `L=-BR_BB`, `U=BR_SB`, exact nonnegative unilateral gains, `NashConv=U-L`, and exploitability `(U-L)/2`. Report exact fractions and the exact threshold decision.
6. Check all physical rows, including zero-reach/off-path rows. Require rejection of altered reveal histories, whole-hand targets, actor identities, masses, omitted/duplicate rows and source changes.
7. Use explicit validation exceptions for certificate-critical checks. The existing development preflop replay relies on assertions; a new publication authenticator must not become permissive under `python -O`.
8. Retain hard pre-admitted tree/depth/world/policy/output/work/Fraction-width bounds. Begin with the established exact-helper ceilings (100,000 modeled work, depth 64, 65,536 Fraction bits) as constraints to assess, not a claim that this new fixture fits. An inability to admit the full audit leaves its gate unknown and triggers Sol review. No silent sampling, partial-row audit, cap increase or surrogate smaller-game certificate.

An independently constructed sequence-form primal/dual witness could later prove an exact equilibrium/value for a hand-computable four-street anchor. Reuse existing bounded simplex/witness knowledge only after independently constructing the complete four-street flow/payoff model. This is optional stronger evidence, not a prerequisite to the first normalized gap certificate and not a production LP engine. A certified low gap on the full configured game is sufficient for the proposed finite-game accuracy gate; a zero-gap or general full-deck claim is not implied.

## Milestones and bounded Luna assignments

| Milestone | Deliverable and acceptance | Luna scope | Sol decision/review |
| --- | --- | --- | --- |
| M0: audit and integration decision | Current pinned inventory, architecture/reuse plan, current baseline tests, D035 intent record, explicit owner review gate | Inventory/extraction and exact test receipts only; no engine implementation | Confirm selected-outcome composition as canonical first engine and approve next bounded scope |
| M1: additive canonical boundary | Small frozen request/result metadata contract and facade; existing call/payload behavior preserved; units, chance scope, global identity and provenance explicit | Own new facade/contract files and bounded adapter tests; do not edit shared kernels, simulator, Coach or admission | Approve exact schema/name/defaults and review round-trip/legacy parity evidence |
| M2: integration corpus and numeric proof | Freeze the exact candidate plus existing controls; independent support/ledger/reach/upstream-value anchors; all guards and complete-row replay pass | Own fixture/protocol/tests and independent numeric extensions; no training optimization or quality-driven fixture tuning | Review physical support, numerical boundary, reach factorization prohibition and pre-admissions before any frozen quality run |
| M3: saved-policy accuracy certificate | One admitted fixed run, raw policy saved before audit, exact-normalized whole-game interval/gap, threshold meet/miss/unknown, immutable report and independent review | One worker implements the bounded certificate adapter; a separate bounded review task reconstructs certificate identities without importing its reporter | Review oracle independence, normalization/caps, first failure, all target misses; decide whether any follow-up budget is justified |
| M4: condensation/efficiency | Profile complete calls, then one measured change preserving the same game/policies/quality; compare complete runtime and allocations separately | Extract duplicated orchestration or remove a measured allocation only after a bounded proposal; preserve recursive reference and old schemas | Select one real bottleneck; approve moving shared private types only if evidence warrants it; reject wholesale graph replacement |
| M5: expand and repeat | One new range/action/chance dimension at a time, new admitted fixture and whole-game evidence, then another measured optimization | Bounded support expansion, transport, profiling or validation tasks with fixed source/model ownership | Prioritize full-deck feasibility versus larger selected games; decide sampling/symmetry/native boundaries and stronger evidence requirements |

Each implementation handoff must specify baseline commit, owned files, exclusions, exact input/configuration, requested full budget, required tests, raw artifacts, source hashes, quality threshold and stop conditions. A worker report is evidence to review, not validation by assignment. Publish ordinary completed repository work through the owner's established GitHub workflow after checks; root handles this audit's publication.

### Escalation and ownership

**Sol owns** game semantics, schema decisions, algorithm/backend selection, fixture/target freezes, chance/reach invariants, numerical boundaries, evidence interpretation, cross-worker integration and publication judgment.

**Luna owns bounded implementation/research/validation only after the next scope is approved.** Stop and return the minimal repro plus first failure when the task exceeds owned files, changes an old default/schema, needs a new abstraction, cannot preserve the oracle's independence, or hits an admitted resource/quality boundary. Do not silently route around a miss.

**Terra handles difficult implementation and debugging.** Escalate a bounded task when Luna cannot isolate or repair a reproducible reach, money/identity, serialization, arithmetic or certificate mismatch within the approved design. Supply the pinned sources, minimal failing case, expected invariant, actual result and attempted fixes. Terra may implement and test the repair within that scope. If resolving it requires changing game semantics, public contracts, numerical boundaries, resource policy or solver decomposition, return that architectural decision to Sol before proceeding. If the Terra route is unavailable, report that limitation rather than silently substituting another model generation.

A resource miss or slow runtime by itself calls for Sol profiling/admission review, not an immediate mathematical escalation. No model assignment is proof, and no isolated-street success establishes whole-game convergence.

### Proposed implementation tickets after review

Names below are proposed ownership boundaries, not files already implemented.
Each ticket is sequentially gated by its prerequisites; none is launched here.

| Ticket | Owned files | Required result and stop condition |
| --- | --- | --- |
| U1: canonical contracts | New `pokerlab/solver_contracts.py`, `tests/test_solver_contracts.py` | Immutable request/result/action/history views with explicit seats, amount basis, chance scope, numerical version and source identity. Existing history/action rows round-trip; invalid or unsupported scope rejects before solve. No changes to `contracts.py`, simulator or existing schemas. |
| U2: one public entry | New `pokerlab/four_street_solver.py`, `tests/test_four_street_solver.py` | Thin all-streets delegation to `solve_preflop`; complete underlying rows/metrics and admissions preserved; no independent street solve calls. Compare existing weighted, shared-prefix, short-blind and monetary controls. U1 must pass first. |
| U3: integration fixture and physical replay | New `benchmarks/four-street-integration-v1.json`, `scripts/four_street_validation.py`, `tests/test_four_street_validation.py`, and the fixture protocol document | Freeze support, monetary/reach and nonzero upstream-dependence anchors from independent numeric reconstruction. Reuse `scripts/preflop_validation.py` read-only; no production tree/rank/value/BR helper becomes an oracle. Pre-admit the complete requested training and audit footprint before any quality run. U2 must pass first. |
| U4: exact saved-policy certificate | New `scripts/four_street_certificate.py`, `tests/test_four_street_certificate.py` | Bounded independently reconstructed whole-game value/BR interval, complete normalized-policy ledger and explicit errors under normal/optimized Python. Known-value controls, hidden-card cheating controls and malformed/off-path policies must behave correctly. Preserve existing certificate sources; U3 must pass first. |
| U5: one frozen acceptance run | New bounded runner/protocol and new `benchmarks/results/four-street-integration-v1/` artifacts only | After clean source freeze and successful full admission, retain the single fixed T1000 complete policy before independent replay/certificate. Publish meet/miss/unknown, all raw evidence and source identities. No retry, fixture tuning, cap increase, isolated benchmark optimization or claim of general convergence. U4 plus lead review must pass first. |

Completion of U5 means the frozen run has a preserved meet/miss/unknown outcome.
Solver-quality acceptance additionally requires that its declared whole-game gate
passes. Only that pass supports calling the named conditioned game solved to the
declared tolerance. The longer-term full-deck objective remains open. M4/M5 require
separate scoped tickets after reviewing that evidence.

## What remains explicitly deferred

Full-deck preflop with live betting; unrestricted NLHE; multiway/rake; learned leaf approximations; replacing global training with independent street equilibria; automatic simulator/solver state unification; changes to Coach, UI or opponent inference; transporting finite-game equilibrium claims through count-only/symmetry artifacts; raising old resource caps; broad file condensation before measured evidence.

This proposal produces a reviewable bounded four-street integration first, then alternates one supported expansion with one measured efficiency step. Existing verified mathematics remains the foundation, with its original scope and failed gates preserved.
