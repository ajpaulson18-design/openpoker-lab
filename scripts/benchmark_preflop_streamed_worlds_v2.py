"""Corrected admission comparison; reuse the unchanged fixed eight-arm harness."""
import json
import subprocess
from scripts import benchmark_preflop_streamed_worlds as comparison

ROOT = comparison.ROOT
SPEC = ROOT / "benchmarks/preflop-streamed-worlds-v2.json"
OUTPUT = ROOT / "benchmarks/results/preflop-streamed-worlds-v2.json"


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8-sig"))
    old_spec = json.loads(comparison.SPEC.read_text(encoding="utf-8-sig"))
    allowed = {"benchmark_id", "prior_streamed_report", "prior_streamed_source_revision", "correction_reason"}
    if {k: v for k, v in spec.items() if k not in allowed} != {k: v for k, v in old_spec.items() if k not in allowed}:
        raise ValueError("Corrected comparison changed a fixed gate or measurement plan")
    prior_path = "benchmarks/results/preflop-streamed-worlds-v1.json"
    if spec["prior_streamed_report"] != prior_path or not spec["correction_reason"]:
        raise ValueError("Missing fixed preliminary provenance or correction reason")
    prior = json.loads((ROOT / prior_path).read_text(encoding="utf-8"))
    if (prior["source_revision"] != spec["prior_streamed_source_revision"]
            or not prior["promotion_gate_met"] or prior["specification"] != old_spec):
        raise ValueError("Preliminary comparison provenance differs")
    if subprocess.run(["git", "merge-base", "--is-ancestor", prior["source_revision"], "HEAD"], cwd=ROOT, check=False).returncode:
        raise ValueError("Preliminary measured source is not an ancestor")
    original_paths = comparison._paths
    comparison._paths = lambda: tuple(dict.fromkeys((*original_paths(),
        "scripts/benchmark_preflop_streamed_worlds_v2.py", "benchmarks/preflop-streamed-worlds-v2.json",
        prior_path, "tests/test_preflop_streamed_reachability.py")))
    comparison.SPEC, comparison.OUTPUT = SPEC, OUTPUT
    comparison.main()


if __name__ == "__main__":
    main()
