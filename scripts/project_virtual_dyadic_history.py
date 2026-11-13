"""Reprice the checked History schedule against a pinned rank-free forecast."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

from scripts.project_virtual_dyadic_eleven import require, template

ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ROOT / "benchmarks/results"


def decision_literals():
    """Count literal occurrences, expanding shared template edges in order."""
    decision = Counter()

    def walk(node_id):
        node = template.nodes[node_id]
        if node.phase == "decision":
            decision[node.street] += 1
        for edge in node.edges:
            walk(edge.child)

    walk(template.root)
    require(dict(decision) == {0: 6, 3: 32, 4: 116, 5: 280},
            "literal decision geometry differs")
    return dict(decision)


def history_schedule(projection, fused_visit):
    shape = projection["shape"]
    decisions = sum(projection["supported_prefixes"][str(street)] * count
                    for street, count in decision_literals().items())
    charges = {
        "construction_and_root": 4096 * 1105 + 1288,
        "action_edges": 3 * 40 * shape["actions"],
        "reveals": 3 * 72 * shape["reveals"],
        "visits": 3 * (8 if fused_visit else 16) * shape["visits"],
        "learning_ordinals": 2 * 32 * decisions,
        "ordered_catalog_rows": 64 * shape["rows"],
        "sealed_menus": 24 * 146 + 16 * 371,
    }
    return {"decisions_per_walk": decisions, "charges": charges, "work": sum(charges.values())}


def project():
    forecast_path = BENCHMARKS / "native-dyadic-eleven-card-forecast-v1/forecast.json"
    forecast_bytes = forecast_path.read_bytes()
    forecast = json.loads(forecast_bytes)
    accepted_dir = BENCHMARKS / "native-dyadic-factored-training-v1"
    accepted = json.loads((accepted_dir / "manifest.json").read_bytes())
    archive = accepted_dir / "verification.zip"
    require(sha256(archive.read_bytes()).hexdigest() == accepted["archive"]["sha256"],
            "accepted factored archive identity differs")
    with ZipFile(archive) as evidence:
        prior = json.loads(evidence.read("cohort/saved-review/stdout.bin"))
    ten = forecast["n10_reproduced"]
    older = history_schedule(ten, False)
    checked = history_schedule(ten, True)
    require(older["work"] == prior["work_actual"]["history"] == 69_825_664 and
            ten["component_work"]["history"] == prior["work_plan"]["history"] == 99_754_616 and
            checked["work"] == 62_890_960, "ten-card schedule calibration differs")
    eleven = forecast["n11_prospective"]
    prospective = history_schedule(eleven, True)
    prospective["prior_conservative_work"] = eleven["component_work"]["history"]
    prospective["prior_exact_schedule"] = history_schedule(eleven, False)["work"]
    prospective["history_cap"] = 100_000_000
    prospective["history_work_to_remove"] = max(0, prospective["work"] - prospective["history_cap"])
    return {
        "status": "rank_free_projection_only",
        "hand_rank_calls": 0, "native_producer_calls": 0,
        "forecast_sha256": sha256(forecast_bytes).hexdigest(),
        "factored_source_head": accepted["source_head"],
        "literal_decisions_by_street": decision_literals(),
        "n10": {"previous_actual": older, "checked": checked,
                "removed_forecast_work": ten["component_work"]["history"] - checked["work"]},
        "n11": prospective,
    }


if __name__ == "__main__":
    print(json.dumps(project(), indent=2, sort_keys=True))
