"""Independent exact certificate using bounded signed terminal groups (v3)."""
from fractions import Fraction
from math import isfinite

from scripts import four_street_certificate as shared
from scripts import four_street_validation as numeric

MAX_EXACT_WORK = shared.MAX_EXACT_WORK
MAX_CENSUS_WORK = shared.MAX_CENSUS_WORK
MAX_FRACTION_BITS = shared.MAX_FRACTION_BITS
MAX_EXACT_DEPTH = shared.MAX_EXACT_DEPTH
THRESHOLD = shared.THRESHOLD
SOURCE_IDENTITY = "four-street-independent-exact-v3"
BUDGET_SCHEDULE_VERSION = "four-street-exact-work-v3"
CENSUS_SETUP_ENTRIES = 32
CENSUS_OUTPUT_ENTRIES = 64


def _effective_sign(node, world):
    return (1 if node.winner == 0 else -1) if node.kind == "fold" else world["sign"]


def _terminal_group_signed(node, group, budget, contribution_label, sum_label):
    """Sum signed masses then convert and multiply the common payoff once."""
    matched = min(node.contributions)
    try:
        payoff_base = float(matched)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("exact terminal payoff is nonfinite") from exc
    if not isfinite(payoff_base):
        raise ValueError("exact terminal payoff is nonfinite")
    budget.charge("br_terminal_group_scans", len(group))
    retained = None
    retained_sign = None
    for world, mass in group:
        sign = _effective_sign(node, world)
        if sign == 0:
            continue
        checked = budget.fraction(mass, contribution_label)
        if retained is None:
            retained = checked
            retained_sign = sign
            continue
        if sign == retained_sign:
            retained = budget.named_add("br_terminal_fraction_operations", retained,
                                        checked, sum_label)
        else:
            retained = budget.named_subtract("br_terminal_fraction_operations", retained,
                                             checked, sum_label)
    if retained is None:
        return Fraction(0)
    signed_payoff = float(retained_sign) * payoff_base
    if not isfinite(signed_payoff):
        raise ValueError("exact terminal payoff is nonfinite")
    budget.charge("br_terminal_conversions")
    payoff = shared.rational._input_fraction(signed_payoff, budget, "binary64 terminal payoff")
    return budget.named_multiply("br_terminal_fraction_operations", retained, payoff,
                                 contribution_label)


def _new_group_census():
    """Collect grouped-terminal counts during the shared all-positive BR walk."""
    budget = shared._Counter(MAX_CENSUS_WORK)
    budget.charge("setup_entries", CENSUS_SETUP_ENTRIES)
    budget.charge("output_entries", CENSUS_OUTPUT_ENTRIES)
    counts = {"groups": 0, "entries": 0, "tie_only_groups": 0,
              "zero_sign_entries": 0, "nonzero_groups": 0,
              "nonzero_entries": 0, "signed_add_subtract_operations": 0,
              "payoff_conversions": 0, "payoff_multiplications": 0}

    def observe(node, group, worlds):
        budget.charge("setup_entries")
        budget.charge("group_frame_entries")
        budget.charge("world_reference_entries", len(group))
        budget.charge("output_entries")
        counts["groups"] += 1
        counts["entries"] += len(group)
        nonzero = 0
        for world_id in group:
            if _effective_sign(node, worlds[world_id]) == 0:
                counts["zero_sign_entries"] += 1
            else:
                nonzero += 1
        if nonzero == 0:
            counts["tie_only_groups"] += 1
            return 0
        counts["nonzero_groups"] += 1
        counts["nonzero_entries"] += nonzero
        counts["signed_add_subtract_operations"] += nonzero - 1
        counts["payoff_conversions"] += 1
        counts["payoff_multiplications"] += 1
        return nonzero

    def receipt():
        _need(counts["groups"] > 0, "terminal group census is empty")
        return {**counts, "work": budget.work,
                "work_by_kind": dict(sorted(budget.counts.items())),
                "work_limit": MAX_CENSUS_WORK, "admitted": budget.work <= MAX_CENSUS_WORK,
                "scope": "Fresh census piggybacked on the shared all-positive BR traversal. Fixed setup/output reservations cover aggregate counts, counter, closure, receipt and preparation mapping slots; per-group setup/frame/reference/output counts are also charged. Logical entries are not bytes, Python allocations, runtime or RSS."}

    return observe, receipt


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _forecast_terminal_group_signed(counter, group_size, *, node, group, worlds, nonzero=None):
    size = group_size
    counter.charge("br_terminal_group_scans", size)
    if nonzero is None:
        nonzero = 0
        for world_id in group:
            if _effective_sign(node, worlds[world_id]) != 0:
                nonzero += 1
    if nonzero:
        counter.charge("br_terminal_conversions")
        counter.charge("br_terminal_fraction_operations", nonzero)


def _forecast_model_signed(model, passes):
    observe_census, census_receipt = _new_group_census()

    def combined_terminal_forecast(counter, group_size, *, node, group, worlds):
        nonzero = observe_census(node, group, worlds)
        _forecast_terminal_group_signed(counter, group_size, node=node, group=group, worlds=worlds, nonzero=nonzero)

    forecast = shared._forecast_model(model, combined_terminal_forecast,
                                      normalization_action_factor=3)
    census = census_receipt()
    graph = shared._structural_preparation_receipt(forecast, passes)
    _need(graph["total_entries_upper_bound"] + census["work"] <= MAX_CENSUS_WORK,
          "combined signed preparation exceeds its 8000000-entry limit")
    forecast["preparation_receipts"] = {
        "terminal_group_census": census,
        "structural_graph_validation": graph,
        "aggregate_preparation": {
            "graph_validation_entries_upper_bound": graph["total_entries_upper_bound"],
            "terminal_group_census_entries": census["work"],
            "total_entries_upper_bound": graph["total_entries_upper_bound"] + census["work"],
            "entry_limit": MAX_CENSUS_WORK, "admitted": True,
            "scope": "Logical preparation entries only; no Python object size, allocation, runtime or RSS guarantee."}}
    return forecast


def forecast_exact(case):
    safe = shared._snapshot_case(case)
    model = numeric.build_model(safe)
    forecast = _forecast_model_signed(model, 2)
    signed_preparation = forecast["preparation_receipts"]
    result = shared._forecast_model_record(model, forecast, SOURCE_IDENTITY,
                                           BUDGET_SCHEDULE_VERSION)
    result["preparation_receipts"]["terminal_group_census"] = signed_preparation["terminal_group_census"]
    result["preparation_receipts"]["aggregate_preparation"] = signed_preparation["aggregate_preparation"]
    graph = result["preparation_receipts"]["structural_graph_validation"]
    census = result["preparation_receipts"]["terminal_group_census"]
    _need(graph["total_entries_upper_bound"] + census["work"] <= graph["entry_limit"],
          "combined signed preparation exceeds its 8000000-entry limit")
    return result


def _normalizer(model, payload, checked, budget):
    return shared._normalise_policy(model, payload, checked, budget, row_extremum=True)


def evaluate_exact(case, payload):
    result = shared._evaluate_with_operators(
        case, payload, terminal_group_operator=_terminal_group_signed,
        terminal_group_forecast_operator=_forecast_terminal_group_signed,
        normalizer=_normalizer, source_identity=SOURCE_IDENTITY,
        budget_schedule_version=BUDGET_SCHEDULE_VERSION,
        model_forecaster=_forecast_model_signed)
    prep = result["forecast"]["preparation_receipts"]
    result["preparation_receipts"]["terminal_group_census"] = prep["terminal_group_census"]
    result["preparation_receipts"]["aggregate_preparation"] = prep["aggregate_preparation"]
    # Shared result construction records the same three-pass graph envelope.
    result["preparation_receipts"]["structural_graph_validation"] = prep["structural_graph_validation"]
    return result
