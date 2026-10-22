"""Research-only CFR+ training over three authenticated fixed-flop priors.

Each call admits the full compact request, authenticates saved no-training
evidence, builds a distinct weighted physical game, trains once, and checks the
normalized output against unrestricted physical responses. This is not a
production API or a broader-game/equilibrium claim.
"""
from fractions import Fraction
import hashlib
import math
import platform
from pathlib import Path

from pokerlab import cfr_plus
from scripts import flop_class_compact_budget as budget
from scripts import flop_class_cfrplus as legacy
from scripts import flop_class_policy as policy
from scripts import flop_class_reweight_plan as planning
from scripts import flop_class_reweight_proof as reweighted
from scripts import flop_public_classes as proof
from scripts import verify_flop_class_compact_cfrplus_publication as compact_publication
from scripts import verify_flop_class_reweight_publication as publication


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = "fixed-flop-class-reweight-cfrplus-v1"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_ITERATIONS = 560
CASE_WEIGHTS = {
    "baseline": ((Fraction(1), Fraction(1, 2)), (Fraction(1, 4), Fraction(1))),
    "uniform": ((Fraction(1), Fraction(1)), (Fraction(1), Fraction(1))),
    "skew": ((Fraction(4), Fraction(1)), (Fraction(4), Fraction(1))),
}

# Pin every existing executable dependency that determines the fixed-game
# model, shared recurrence, normalization, or historical publication checks.
_SOURCE_PATHS = (
    "scripts/flop_public_classes.py",
    "scripts/flop_public_classes_candidate.py",
    "scripts/flop_multistreet_validation.py",
    "scripts/preflop_validation.py",
    "scripts/benchmark_weighted_full_deck_flop.py",
    "scripts/benchmark_flop_alternating.py",
    "scripts/flop_class_cfrplus.py",
    "scripts/flop_class_policy.py",
    "scripts/verify_flop_public_classes_publication.py",
    "scripts/verify_flop_class_cfrplus.py",
    "scripts/verify_flop_class_compact_cfrplus.py",
    "scripts/verify_flop_class_cfrplus_publication.py",
    "scripts/flop_class_compact_cfrplus.py",
    "scripts/flop_class_compact_budget.py",
    "scripts/verify_flop_class_compact_cfrplus_publication.py",
    "scripts/flop_class_reweight_plan.py",
    "scripts/flop_class_reweight_proof.py",
    "scripts/benchmark_flop_class_reweight.py",
    "scripts/verify_flop_class_reweight_publication.py",
    "scripts/flop_class_reweight_cfrplus.py",
    "scripts/benchmark_flop_class_cost.py",
    "scripts/flop_class_call_measurement.py",
    "pokerlab/cfr.py",
    "pokerlab/cfr_plus.py",
    "benchmarks/flop-class-cfrplus-pilot-v1.json",
    "benchmarks/flop-class-compact-cfrplus-pilot-v1.json",
    "benchmarks/flop-class-reweight-proof-v1.json",
    "benchmarks/flop-class-call-cost-v1.json",
)


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def case_plan(case_id):
    """Return a fresh strict plan for one of the three frozen priors."""
    if type(case_id) is not str or case_id not in CASE_WEIGHTS:
        raise ValueError("case_id must be exactly baseline, uniform, or skew")
    oop, ip = CASE_WEIGHTS[case_id]
    return planning.plan_weights(tuple(oop), tuple(ip))


def _plan_record(plan):
    return {
        "board": list(plan.board),
        "oop_weights": [[v.numerator, v.denominator] for v in plan.oop_weights],
        "ip_weights": [[v.numerator, v.denominator] for v in plan.ip_weights],
        "compatible_pair_raw_products": [[a, b, v.numerator, v.denominator]
                                          for a, b, v in plan.compatible_pair_raw_products],
        "global_blocker_normalizer": [plan.global_blocker_normalizer.numerator,
                                      plan.global_blocker_normalizer.denominator],
        "exact_pair_priors": [[a, b, v.numerator, v.denominator]
                              for a, b, v in plan.exact_pair_priors],
        "ordered_runouts_per_pair": plan.ordered_runouts_per_pair,
        "physical_world_forecast": plan.physical_world_forecast,
        "scope": plan.scope,
    }


def admit_request(case_id, iterations=560):
    """Validate case, full T, exact plan and named-work budget before auth."""
    plan = case_plan(case_id)
    if type(iterations) is not int or not 1 <= iterations <= MAX_ITERATIONS:
        raise ValueError(f"Reweighted fixed-flop CFR+ requires integer iterations in [1, {MAX_ITERATIONS}].")
    compact = budget.admit_compact_request(iterations)
    weighted_setup = {"binary64_mass_sum_world_entries": 126}
    weighted_setup_work = sum(weighted_setup.values())
    fixed_work = compact["fixed_setup_and_output_work"] + weighted_setup_work
    total_work = compact["total_training_work"] + fixed_work
    combined_cap = compact["cap"]["maximum_total_admitted_logical_work"]
    _need(total_work <= combined_cap,
          "Weighted compact fixed setup exceeds the combined logical-work cap")
    return {
        "version": ADAPTER + ":admission-v1",
        "case_id": case_id,
        "requested_iterations": iterations,
        "averaging_delay": 0,
        "total_admitted_work": total_work,
        "total_training_work": compact["total_training_work"],
        "fixed_setup_and_output_work": fixed_work,
        "compact_fixed_setup_and_output_work": compact["fixed_setup_and_output_work"],
        "weighted_setup_work": weighted_setup,
        "weighted_setup_work_total": weighted_setup_work,
        "weighted_setup_work_interpretation": (
            "Named 126-entry binary64 mass-sum input count only; not a complete arithmetic, "
            "CPU-time, allocated-byte, or RSS bound."),
        "combined_logical_work_cap": combined_cap,
        "compact_logical_admission": compact,
        "weighted_proof_preparation_census": {
            "physical_oracle_builds": 2,
            "physical_world_rows_enumerated_total": 2 * plan.physical_world_forecast,
            "maximum_live_physical_oracles": 2,
            "physical_worlds_per_oracle": plan.physical_world_forecast,
            "physical_public_states_per_oracle": 30_812,
            "compact_worlds": 126,
            "compact_public_states": 1_001,
            "compact_policy_rows": 466,
            "physical_policy_rows": 16_912,
            "interpretation": (
                "Census/capacity counts only. The compact logical-work forecast "
                "does not model all proof arithmetic, elapsed time, allocated bytes, or RSS."),
        },
        "plan": _plan_record(plan),
    }


def source_hashes():
    """Bounded LF-normalized source identities for this exact adapter call."""
    hashes = {}
    for relative in _SOURCE_PATHS:
        path = ROOT / relative
        try:
            if path.stat().st_size > MAX_SOURCE_BYTES:
                raise ValueError(f"Source exceeds bound: {relative}")
            with path.open("rb") as stream:
                raw = stream.read(MAX_SOURCE_BYTES + 1)
        except OSError as exc:
            raise ValueError(f"Cannot read bounded source: {relative}") from exc
        _need(len(raw) <= MAX_SOURCE_BYTES, f"Source exceeds bound: {relative}")
        hashes[relative] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    return dict(sorted(hashes.items()))


def _training_inputs(model):
    """Validate the weighted quotient and prepare only joint-mass CFR inputs."""
    census = reweighted.validate_model(model)
    class_rows = reweighted._class_rows(model)
    infos = {key: len(node.actions) for key, node in class_rows.items()}
    _need(len(class_rows) == len(infos) == 466 and
          all(type(count) is int and count == 2 for count in infos.values()),
          "Weighted compact policy dimensions differ")
    masses = [world[2] for world in model.worlds]
    _need(len(masses) == 126 and all(type(mass) is Fraction and mass > 0
                                     for mass in masses) and
          sum(masses, Fraction()) == 1,
          "Weighted compact joint-world masses must be exact, positive, and sum to one")

    worlds = []
    for world in model.worlds:
        mass = float(world[2])
        _need(math.isfinite(mass) and mass > 0,
              "Binary64 conversion loses positive weighted chance support")
        worlds.append((world[0], world[1], mass, world[3], world[4]))
    _need(math.isclose(math.fsum(world[2] for world in worlds), 1.0,
                       rel_tol=1e-12, abs_tol=1e-12),
          "Binary64 weighted chance masses do not sum to one")

    max_visits = 0
    for world in worlds:
        stack = [model.root]
        visits = 0
        while stack:
            node = stack.pop()
            visits += 1
            _need(visits <= budget.MAX_WORLD_VISITS,
                  "Weighted compact per-world traversal exceeds the admitted bound")
            child = legacy._chance_child(node, world)
            if child is not None:
                stack.append(child)
            elif isinstance(node, reweighted.physical._Decision):
                _need(legacy._node_key(node, world) in infos,
                      "Weighted compact decision exposes an unadmitted information set")
                stack.extend(node.children)
        max_visits = max(max_visits, visits)
    budget.validate_observed_dimensions(census, max_visits, infos)
    return tuple(worlds), infos, max_visits


def _guard_receipt(calls, authenticated_old):
    expected = authenticated_old.get("forbidden_production_calls")
    _need(type(expected) is dict and len(expected) == 41 and
          type(calls) is dict and set(calls) == set(expected) and
          all(type(key) is str and type(value) is int and value == 0
              for key, value in calls.items()),
          "No-training/preparation guard inventory is incomplete or nonzero")
    return dict(sorted(calls.items()))


def solve_reweighted(case_id, iterations=560):
    """Train once under one frozen prior and audit its physical output."""
    admission = admit_request(case_id, iterations)
    plan = case_plan(case_id)
    sources = source_hashes()

    # Authentication happens only after strict full-request admission.
    proof_receipt = publication.verify()
    _, compact_raw, compact_report = compact_publication._read(
        compact_publication.PUBLICATION)
    compact_historical_baseline = {
        "raw_sha256": compact_publication.RAW_SHA256,
        "artifact_sha256": compact_publication.ARTIFACT_SHA256,
        "iterations": compact_report["physical_policy"]["iterations"],
        "nash_conv": compact_report["physical_policy"]["nash_conv"],
        "quality_target_met": compact_report["quality_target_met"],
    }
    del compact_raw, compact_report
    historical = publication.old_publication.authenticate()

    with proof.independent_guard() as preparation_calls:
        model = reweighted.build_model(plan)
        worlds, infos, max_visits = _training_inputs(model)
    preparation_calls = _guard_receipt(preparation_calls, historical)

    raw_rows = cfr_plus.train(
        model.root, worlds, infos, iterations,
        terminal_value=legacy._terminal_value,
        node_key=legacy._node_key,
        chance_child=legacy._chance_child,
    )
    _need(type(raw_rows) is dict and set(raw_rows) == set(infos),
          "Weighted trainer output omits or adds a compact information set")
    rows, normalization = policy.canonicalize_binary_rows(raw_rows)
    _need(set(rows) == set(infos), "Normalized weighted policy dimensions differ")

    with proof.independent_guard() as diagnostic_calls:
        payload = reweighted.lift_policy(rows, model)
        payload.update(algorithm="cfrplus", iterations=iterations,
                       research_adapter=ADAPTER, averaging_delay=0,
                       prior_case=case_id,
                       compact_resource_model=admission["compact_logical_admission"]["version"])
        audit = reweighted.audit_policy(payload, model)
    diagnostic_calls = _guard_receipt(diagnostic_calls, historical)

    current_sources = source_hashes()
    _need(current_sources == sources, "Source changed during reweighted fixed-flop solve")
    exact_nash_text = audit["exact_metrics"]["nash_conv"]
    _need(type(exact_nash_text) is str, "Exact weighted NashConv must be a rational string")
    exact_nash_conv = Fraction(exact_nash_text)
    gap = audit.get("maximum_numeric_gap")
    _need(exact_nash_conv >= 0 and
          type(audit.get("exact_metric_count")) is int and audit["exact_metric_count"] == 8 and
          type(audit.get("physical_rows_lifted")) is int and audit["physical_rows_lifted"] == 16_912 and
          type(audit.get("class_rows")) is int and audit["class_rows"] == 466 and
          type(gap) in (int, float) and math.isfinite(gap) and 0 <= gap <= 1e-10,
          "Weighted physical audit dimensions or numeric replay differ")

    weighted_world_sha = proof._digest(reweighted._world_rows(model.physical["worlds"]))
    baseline_world_sha = proof._digest(reweighted._world_rows(model.baseline["worlds"]))
    report = {
        "schema_version": ADAPTER,
        "status": "trained-policy-physically-verified",
        "case_id": case_id,
        "source_lf_sha256": sources,
        "proof_receipt": proof_receipt,
        "compact_historical_baseline": compact_historical_baseline,
        "runtime": {"python": platform.python_version(),
                    "implementation": platform.python_implementation()},
        "admission": admission,
        "plan": _plan_record(plan),
        "physical_worlds_sha256": weighted_world_sha,
        "baseline_worlds_sha256": baseline_world_sha,
        "maximum_world_path_states": max_visits,
        "census": dict(model.census),
        "normalization": normalization,
        "raw_class_policy": [[p, hand, list(history), list(values)]
                             for (p, hand, history), values in sorted(raw_rows.items())],
        "physical_policy": payload,
        "audit": audit,
        "preparation_forbidden_calls": preparation_calls,
        "diagnostic_forbidden_calls": diagnostic_calls,
        "training_calls": 1,
        "quality_target": 0.005,
        "quality_target_met": exact_nash_conv <= Fraction(1, 200),
        "scope": (
            "One exact positive-prior fixed-support flop game under the unchanged "
            "alternating CFR+ recurrence. Physical metrics describe the normalized "
            "output policy. No broader game, general convergence, speed, byte, or RSS claim."),
    }
    report["artifact_sha256"] = proof._digest(report)
    return report
