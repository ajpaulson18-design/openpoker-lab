# GPT-6 Luna implementation prompt — first coaching evidence slice

## Objective

Implement a versioned, immutable, validated coaching evidence boundary and a pure adapter from existing `practice-ev-v3` results. A caller must be able to turn an already calculated practice decision into safe, precisely labeled structured evidence, serialize/deserialize it, and inspect it without invoking a solver, changing strategy or using an AI provider.

Implement **only this slice**. Stop after its tests, documentation and publication are complete. Do not design or build the next slice.

## Context and baseline

Work in `ajpaulson18-design/openpoker-lab` from current GitHub main. The architecture was inspected at `48f6803e474ce514c54da8916dd61cef57fd0ac4` on 2026-10-07. Recheck HEAD and relevant files before editing. The ChatGPT-project local `openpoker` checkout is on old `feature/exploit-solver` at `a75697d`; do not implement there on the assumption it is main. Preserve unrelated edits and use a current isolated checkout when needed. The `architecture/review-baseline` folder is an inspection fixture, not an implementation repository.

Read applicable `AGENTS.md`, `docs/human-aware-strategy.md`, `docs/solver-validation.md`, and the accompanying `ai-coach-architecture.md`. The application has no runtime dependencies. Reuse its standard-library/frozen-dataclass conventions.

Existing practice analysis returns a dictionary with `analysis_id`, `analysis_version`, `analysis_inputs`, `recommended`, `baseline_recommended`, `actions`, `baseline_actions`, `equity`, confidence, model metadata, warnings and deterministic prose. `analysis_inputs` stores visible cards, board, legal details, stacks/contributions, actor/button, ranges and calculator settings. Do not send that raw dictionary onward as coach context.

Practice EVs are estimates, not CFR output. The illustrative baseline uses a 45% fold assumption. The existing one-hot policy serialization is an argmax recommendation, not an equilibrium frequency. The `raise` estimate is for the minimum legal street-total raise only. Practice evaluates all live opponent ranges for showdown equity, but raise response remains simplified. Opponents' actual cards, deck and personal profile fields must never enter this new contract.

## Scope

1. Add the following new shared immutable dataclasses to `pokerlab/contracts.py` without changing existing contracts or behavior.
2. Create `pokerlab/coach_analysis.py` with one pure `adapt_practice_analysis` function, typed errors and explicit mapping.
3. Add strict `CoachDecisionAnalysis` dictionary/JSON round-trip support and deterministic evidence fingerprints.
4. Add externally meaningful contract/adapter regression tests and a short schema/semantics document.

## Out of scope

No provider/SDK/API key; no prompt generation, AI calls, conversation storage, new endpoints, streaming, frontend changes, database migration, solver/equilibrium/exploit adapters, gameplay refactor, chosen-action evaluation, decision ranking changes, range inference, formula correction or performance work. Do not replace `StrategyAnalysisResult`, `DecisionExplanation`, `OptionalAIAdapter` or existing exports. Do not wire the adapter into `/api/act` yet.

## Files/modules

Inspect `pokerlab/contracts.py`, `practice.py`, `game.py`, `equity.py`, `explanations.py`, `models.py`, and current tests in `test_core.py`, `test_practice.py`, `test_explanations.py`. Read `equilibrium.py` only to understand future scope; do not implement its adapter.

Modify: `pokerlab/contracts.py` additively.

Create: `pokerlab/coach_analysis.py`, `tests/test_coach_analysis.py`, `docs/coach-analysis-v1.md`.

A small link in `docs/human-aware-strategy.md` is allowed. No other production changes should be needed. Escalate to architectural review if real repository changes invalidate these boundaries; do not solve that ambiguity by expanding scope.

## Required interfaces

Use `@dataclass(frozen=True, slots=True)` and the existing `SerializableContract` mixin for every new shared type. Collections stored in contracts must be tuples, including nested collections. Reject mutable collections in direct construction; the adapter and reader convert accepted input arrays to fresh immutable tuples. The exact public fields are:

```python
from typing import Any, Literal, Mapping

@dataclass(frozen=True, slots=True)
class CoachDecisionRef(SerializableContract):
    hand_id: str
    decision_id: str
    state_revision: int | None

@dataclass(frozen=True, slots=True)
class CoachAction(SerializableContract):
    action_id: str
    name: Literal["fold", "check", "call", "bet", "raise"]
    amount: float | None
    amount_semantics: Literal["chips_added", "street_total"]
    minimum_total: float | None = None
    maximum_total: float | None = None

@dataclass(frozen=True, slots=True)
class CoachDecisionContext(SerializableContract):
    street: Literal["preflop", "flop", "turn", "river"]
    hero_cards: tuple[str, ...]
    board: tuple[str, ...]
    pot: float
    pot_basis: Literal["current_committed", "solver_initial"]
    actor_seat: int | None
    actor_role: Literal["oop", "ip"] | None
    button_seat: int | None
    stacks: tuple[int, ...] | None
    street_bets: tuple[int, ...] | None
    committed: tuple[int, ...] | None
    current_bet: float | None
    min_raise: float | None

@dataclass(frozen=True, slots=True)
class CoachPolicy(SerializableContract):
    kind: Literal["illustrative_argmax", "estimate_argmax",
                  "equilibrium_mix", "modeled_opponent_mix"]
    frequencies: tuple[ActionFrequency, ...]  # .action stores modeled action_id

@dataclass(frozen=True, slots=True)
class CoachActionValue(SerializableContract):
    action_id: str
    value: float | None

@dataclass(frozen=True, slots=True)
class CoachAnalysisQuality(SerializableContract):
    confidence_label: str
    opponent_uncertainty: Uncertainty | None
    equity_standard_error: float | None
    equity_exact: bool | None
    nash_conv: float | None
    exploitability: float | None
    iterations: int | None
    gap_semantics: str | None

@dataclass(frozen=True, slots=True)
class CoachProvenance(SerializableContract):
    path: str          # JSON Pointer inside CoachDecisionAnalysis
    origin: Literal["game_state", "analysis_output", "solver_output",
                    "opponent_model", "derived_application"]
    source_path: str   # logical producer-field reference; no local file paths

@dataclass(frozen=True, slots=True)
class CoachDecisionAnalysis(SerializableContract):
    ref: CoachDecisionRef
    analysis_id: str
    evidence_id: str
    adapter_version: str
    producer_version: str
    model_version: str
    source_kind: Literal["practice_estimate", "restricted_equilibrium",
                         "restricted_exploit"]
    context: CoachDecisionContext
    legal_actions: tuple[CoachAction, ...]
    modeled_actions: tuple[CoachAction, ...]
    reference_policy: CoachPolicy | None
    modeled_policy: CoachPolicy | None
    action_evs: tuple[CoachActionValue, ...]
    baseline_action_evs: tuple[CoachActionValue, ...]
    recommended_action_id: str | None
    baseline_recommended_action_id: str | None
    ev_basis: Literal["incremental_decision_chips", "half_initial_pot_utility"]
    opponent_ranges: tuple[str, ...]
    opponent_assumptions: tuple[OpponentAssumption, ...]
    quality: CoachAnalysisQuality
    limitations: tuple[str, ...]
    warnings: tuple[str, ...]
    unavailable_fields: tuple[str, ...]
    provenance: tuple[CoachProvenance, ...]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]: ...
    def to_json(self) -> str: ...
    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CoachDecisionAnalysis": ...
    @classmethod
    def from_json(cls, encoded: str) -> "CoachDecisionAnalysis": ...
```

These are type definitions, not a request for new producer implementations. Nullable fields support future honest missing facts. Constructors/readers must enforce the enum values at runtime; `Literal` annotations alone do not validate anything. Existing `ActionFrequency`, `Uncertainty`, `OpponentAssumption`, and `stable_analysis_id` are reused, not redefined.

Define `CoachAnalysisError` in `contracts.py` and import/re-export it from `coach_analysis.py`, so shared-contract validation does not import the adapter. The adapter interface in `coach_analysis.py` is:

```python
COACH_PRACTICE_ADAPTER_VERSION = "coach-practice-adapter-v1"

class CoachAnalysisError(ValueError):
    # fixed .code plus a safe field-oriented message; never include raw input
    code: str
    def __init__(self, code: str, message: str) -> None: ...

def adapt_practice_analysis(
    analysis: Mapping[str, Any], *, ref: CoachDecisionRef
) -> CoachDecisionAnalysis: ...
```

Public error codes: `unsupported_producer_version`, `invalid_analysis`, `unsupported_schema_version`, `invalid_contract`, `fingerprint_mismatch`. All new adapter/constructor/reader failures use `CoachAnalysisError` with the matching code. Existing contracts and their error behavior remain unchanged. Convert existing validation-helper exceptions at the new boundary, without echoing raw data. Do not add an error framework.

## Behavioral requirements and exact mapping

### Identity, versions and fingerprint

- Accept only producer version `practice-ev-v3`. Fail closed for missing/other versions; do not migrate or recalculate older practice results.
- Copy the provided `CoachDecisionRef` and original `analysis_id`; copy producer/model versions without relabeling them.
- Set schema version 1, adapter version as above, source `practice_estimate`, EV basis `incremental_decision_chips`.
- `ref` IDs are nonempty opaque strings; revision is null or a nonnegative integer, never bool. The adapter must not generate identity or infer revision from the equity/deal seed. Null means a historical record lacks revision; live stale-state binding will require a non-null revision in a later integration slice.
- Build `evidence_id` with existing `stable_analysis_id(protected_dict, "coach-evidence-v1")`. `protected_dict` is the full serialized envelope excluding only top-level `ref` and `evidence_id`; it includes schema/adapter/producer/model versions, original `analysis_id`, all safe facts, quality, policies, provenance and caveats. No timestamp, personality, prose, raw seed, names or notes enters it. Hash calculation is fact normalization, not poker calculation.
- `from_dict` and `from_json` recompute and verify the fingerprint. For a direct constructed envelope, validate it likewise. Use a private canonical-payload helper to avoid recursive serialization/validation. Keeping the existing `analysis-` prefix returned by `stable_analysis_id` is intentional.
- Same source facts yield the same fingerprint across input dictionary ordering and across locator changes. Altering an authoritative included value changes the fingerprint. The fingerprint is integrity/version identity, not proof that browser-submitted data came from the solver.

### Context

Copy from `analysis_inputs`: `street`; `known_cards→hero_cards`; `public_cards→board`; `pot`; `actor→actor_seat`; `button→button_seat`; stacks, street_bets, committed, current_bet, min_raise. Set `pot_basis=current_committed`, `actor_role=None`. Copy `opponent_ranges` in their persisted order; do not reconstruct seats or ranges from actual hole cards.

Required context fields must exist. Validate canonical cards with existing card utilities, two hero cards, street/board-count consistency (0/3/4/5), no duplicates across visible cards, finite nonnegative pot/current bet, positive min raise, 2–6 stacks, equal lengths of contribution arrays, nonnegative integer chip entries (bool forbidden), valid actor/button indexes, street contribution not above total contribution, and pot equal to sum of committed chips. Do not validate settlement states as awaiting decisions; this adapter consumes pre-action analysis only. Do not claim an effective stack without folded/eligible information.

### Legal versus modeled actions

Canonical ordering is `fold, check, call, raise` filtered to legal entries. `analysis_inputs.legal_actions` must contain that same set once each, and both `analysis.actions` and `baseline_actions` must cover it exactly. `legal` contains the authoritative booleans for fold/check/raise and nonnegative integer call/raise limits. Reject conflicting or malformed action sets. Canonicalize order without changing the recommendation or numeric values.

Create legal actions:

| Producer name | Legal action ID / amount / semantics |
| --- | --- |
| fold/check | same name; amount 0; `chips_added`; no bounds |
| call | `call`; amount equals `legal.call`; `chips_added`; no bounds |
| raise | `raise`; amount null; `street_total`; minimum/maximum equal legal raise bounds |

The variable raise entry describes game legality only. Require positive legal call when call is listed. Legal raise bounds are integers with min ≤ max and compatible with actor street contribution/remaining stack; do not invent a new minimum raise rule.

Modeled actions copy fold/check/call entries unchanged. The modeled raise has ID **`raise:min`**, name `raise`, amount `legal.raise_min`, `street_total`, and null bounds. It represents exactly that one analyzed total, not every legal raise amount.

Map source `actions` unchanged into `action_evs` and `baseline_actions` unchanged into `baseline_action_evs`, using modeled IDs. Never round, choose, recompute, compare or adjust values. Copy recommendations through this mapping (`raise→raise:min`). If the upstream recommendation is not a legal/modeled name, fail. Do not check that it is numerically best or replace it; tests must prove preservation even for an intentionally non-argmax supplied recommendation.

Construct reference policy `illustrative_argmax` one-hot at the supplied `baseline_recommended`; construct modeled policy `estimate_argmax` one-hot at the supplied `recommended`. These are representations of supplied recommendations, not calculated solver frequencies. Each covers all modeled IDs exactly once and sums to one. Preserve ties through the supplied recommendation rather than resolving them again.

### Quality, assumptions, limitations and provenance

- Copy confidence into `quality.confidence_label`. Copy `equity.standard_error` and `equity.exact` (finite nonnegative numeric and actual bool). Exact equity may have zero sampling error; never treat it as exact action EV or solver convergence.
- Set nash_conv, exploitability, iterations and gap_semantics to null. Do not map confidence or simulation trials into these fields.
- No profile or no modeled raise: assumptions empty and opponent uncertainty null. Confidence still copies the producer label. If there is a modeled raise and a provided opponent-model snapshot, copy only the consumed `fold_to_bet` metric as one `OpponentAssumption`: tendency ID `fold_to_bet`, `TendencyContext(street=analysis_inputs.street)`, value from `analysis_inputs.fold_to_bet`, evidence_count from snapshot metric `observations`, and `Uncertainty` from `interval95`, level .95, interval_method, confidence. Validate matching snapshot street and matching metric mean/value; do not invent missing counts or intervals. No other metric is claimed as causal.
- No snapshot means no opponent assumption, even though illustrative fold input is used. Its source is a scenario assumption reflected in the practice source/limitations, not empirical evidence.
- Preserve input warnings exactly and in order. Add three fixed limitations: `Practice action EVs are simplified estimates, not equilibrium solver output.`; `Practice policies encode supplied argmax recommendations, not equilibrium mixing frequencies.`; `The modeled raise evaluates only the minimum legal street total; other raise sizes are unassessed.`
- Set `unavailable_fields` in fixed order to `action_history`, `folded_flags`, `effective_stack`, `chosen_action`, `solver_convergence`, `conditional_ranges`. Even a caller attaching these as unknown raw keys does not make them certified available. The new envelope represents analysis, not an accepted player action.
- Provenance must cover every leaf numeric/boolean/card/action/recommendation/policy/assumption/quality fact and each opponent range with a resolvable envelope JSON Pointer and logical source path. Context uses `game_state` and paths such as `analysis_inputs/pot`; copied EVs/recommendations/quality use `analysis_output` (equity is part of analysis output); consumed assumption fields use `opponent_model` (with `analysis_inputs/fold_to_bet` referenced for the consumed value); normalized action identities/amount semantics and one-hot policies use `derived_application`. There must be **no `solver_output` origins** for this adapter. Emit canonical deterministic ordering by destination pointer. Identity/version/caveat strings need not each receive leaf provenance.
- Do not serialize the raw snapshot, raw inputs, producer prose, profile/name/opponent ID, notes, timestamps, deck, other hole cards, seed/trials, file paths, credentials or arbitrary extra fields. Original opaque analysis/decision IDs are allowed locally; external provider projection is future work.

### Serialization and validation

`to_dict` returns fresh JSON-ready arrays/objects. Mutating them or the original input after adaptation cannot mutate the contract. `to_json` uses sorted keys, compact separators and `allow_nan=False`. JSON round-trips reconstruct all nested dataclasses and tuples, including all currently defined `OpponentAssumption` fields; do not reuse the lossy old `analysis_from_dict`/`_assumption` helpers.

Readers reject unknown envelope/nested fields, missing required fields, incorrect scalar types, duplicate IDs, non-finite numerics and unsupported schema versions. Numeric booleans are always invalid. Null means unavailable, not zero. Action estimates cover every modeled ID exactly once (nullable values allow future producer absence); policies, when supplied, cover the same set with bounded probabilities summing to one. Recommendations, when non-null, must refer to modeled IDs. Every modeled action must be compatible with a legal action of the same name and amount/bounds. Provenance destination pointers must resolve and be unique; reject undeclared source kinds/policy kinds/basis/amount semantics. This first adapter always supplies non-null EVs/recommendations.

For `practice_estimate`, enforce argmax policy kinds, the incremental/current-committed basis, and absent solver gaps. Generic types may represent future kinds, but do not build adapters or invent populated values for them. Do not promise forward compatibility with unrecognized versions; document explicit version checks and reader migration expectations.

Use allowlist construction: raw producer extras may be ignored, but cannot be echoed in output or included in fingerprints. Strict contract reader extras must be rejected. Error messages identify a field/category without echoing raw personal input or the whole analysis.

## Architectural constraints

- Engine/calculators remain authoritative. No model, solver, simulation, database or network calls occur inside the adapter.
- Do not call `analyze_decision`, `analyze_recorded_decision`, `_calculate_analysis`, `simulate`, `solve`, `solve_equilibrium`, `explain`, `max` to select recommendations, or private equilibrium internals. Card parsing/type validation and stable hashing are allowed.
- Existing `practice-ev-v3` values, IDs, versions, APIs and deterministic renderers remain byte-for-byte behavior-compatible. Do not correct larger-raise EV or existing losses here.
- Shared contracts live in `contracts.py`; mapping/error handling live at the adapter boundary. Avoid circular imports. No new runtime dependencies or schema framework.
- No hidden information or profile psychology enters evidence. A future external provider must receive a separate safe projection, not the entire local envelope by default.

## Error/failure behavior

Unsupported producer version returns the specified typed error without fallback calculations. Missing/malformed state/action/EV/quality/consumed evidence returns `invalid_analysis`. Bad contract input is rejected before use; altered serialized facts without a matching fingerprint are rejected. Missing required historical fields remain unsupported in this slice; do not pretend to fill them. Unknown extra raw producer metadata is ignored via allowlist. None of these failures mutates the input, game or persistence.

## Tests to create and run

Use synthetic data only, with both manually specified fixtures and real existing `analyze_decision(Game(...))` results generated **before** adaptation. Cover these meaningful boundaries:

1. Correct practice source, versions, EV/pot basis, argmax policy kinds and absent convergence. No claim of solver output, even with exact river equity.
2. Both existing EV maps/recommendations copy exactly; intentionally non-argmax recommendations are preserved, and ties are not reselected.
3. Canonical legal/modeled ordering and stable fingerprints despite dictionary/key/action-map ordering; changed ref leaves evidence_id unchanged; changed EV/context/quality/caveat/version-safe fact changes it.
4. `raise` legal interval versus `raise:min` modeled amount; a different potential chosen raise is never represented as evaluated. Raise-to total differs explicitly from chips added; validate short-all-in legal bounds using the engine's emitted legal state.
5. No snapshot, a valid modeled-raise snapshot, and snapshot on fold/call-only decision. Check exact consumed value/count/uncertainty, no unsupported tendency causal claims, and malformed/conflicting consumed evidence rejection.
6. Multiway output preserves every persisted range without reconstructing hidden hands or attributing unavailable seats; hero-only cards and board remain the sole private/public cards.
7. Poison raw input with distinct names, notes, actual opponent cards, deck, paths, seeds and extra fields. Assert those values/keys are absent from serialized output and fingerprint inputs. Exercise both snapshot and top-level unknown fields.
8. Deep immutability against mutation of nested original lists/dicts, outputs and directly supplied mutable contract collections; dictionary and JSON round-trips preserve equal values/types/IDs and all assumption metadata.
9. Reject unsupported producer/schema versions; missing fields; nonfinite values; numeric booleans; duplicate/mismatched action IDs; illegal recommendations; malformed visible cards/street/array/pot/seat/raise state; invalid policy sums; unknown fields/enums; bad provenance references and altered fingerprints. Keep messages free of raw sensitive values.
10. Mock calculation, persistence, explanation and network boundaries to raise if called **during adaptation**; adaptation still succeeds on precomputed valid input. No downstream dependency required.
11. Existing practice/explanation/contract behavior remains unchanged, including exact saved replay IDs and legal play.

Run focused new tests while implementing, then the full repository unit suite:

```text
python -m unittest discover -s tests -p test_coach_analysis.py -v
python -m unittest discover -s tests -v
```

CI uses Python 3.11–3.13. No exhaustive card evaluator rerun is necessary unless card logic changes, which is outside scope. If Windows temporary-directory ACL failures occur, record the normal failure and rerun through a unique writable project-local test fixture/harness; do not weaken assertions or count blocked tests as passing. Existing `test_practice.py` demonstrates a workspace-safe fixture. Avoid committing test data or temporary artifacts.

## Acceptance criteria

- The exact new imports and adapter signature exist and work with actual current practice results.
- The contract faithfully and safely distinguishes legal actions, evaluated sizes, illustrative recommendations, estimates, uncertainties and missing solver facts.
- Strict deterministic serialization and fingerprint verification pass the tests above; adaptation requires no downstream system.
- Documentation states field/source/basis semantics, null/missing behavior, privacy allowlist, version/error policy and the known minimum-raise evaluation limit.
- Existing behavior and the full applicable suite pass; no unrelated production changes or optional AI dependency appears.

## Definition of done and routing

Inspect the diff for unintended changes, run/record actual checks, commit the narrow tested slice, and publish it to a short-lived GitHub branch/PR according to the user's standing repository workflow. Attach the PR to the chat. Merge only after required checks and applicable repository rules permit it; explicitly report any real publication blocker. Do not commit local databases, personal data or the inspection fixture. Summarize implementation, tests, unresolved issues and exactly what was pushed.

Length alone is not an escalation reason. Use GPT-6 Luna for routine work; use GPT-6 Terra only for genuinely difficult implementation/debugging, and GPT-6.1 Sol only for architectural problems or major ambiguity. If a requested escalation tier is unavailable in the implementation environment, report that limitation before choosing a substitute. Stop after this slice is complete; later slice design depends on its real tested result.
