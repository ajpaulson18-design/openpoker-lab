"""External pre-fix builder lifetime probe; never a solver quality benchmark."""
import gc
import hashlib
import json
from pathlib import Path
import sys
import weakref
from unittest.mock import patch

REPO = Path(r"C:\Users\pauls\Documents\Codex\2026-10-26\files-pasted-by-the-user-i\work\direct-topology-repo")
sys.path.insert(0, str(REPO))
from pokerlab import direct_shared_topology as direct
from pokerlab.preflop_solver import _stage_configs
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.selected_runout_operator import SelectedRunoutOperator
from scripts.benchmark_selected_operator import _identity


def main():
    output = Path(sys.argv[1])
    if output.exists():
        raise FileExistsError("Preserve existing probe receipts.")
    source = _identity()
    if source["commit"] != "afd1afc45a62d07c2b1beb120bd9891e5858dece" or source["status"]:
        raise RuntimeError("Use the original clean direct-study source only.")
    case = json.loads((REPO / "benchmarks/four-street-integration-v1.json").read_text())["case"]
    config = PreflopConfig.from_dict(case["config"])
    specs = _stage_configs(case["flop_config"], case["turn_config"], case["river_config"])
    operator = SelectedRunoutOperator(case["sb_range"], case["bb_range"], case["runouts"])
    selected = operator.reachable_selected()
    refs = []
    original = direct._DirectBuilder.__init__

    def capture(self, *args, **kwargs):
        original(self, *args, **kwargs)
        refs.append(weakref.ref(self))

    def successful_build():
        return direct.build_direct_shared_topology(config, specs, selected)

    def failing_build():
        try:
            with patch.object(direct._DirectBuilder, "finish", side_effect=RuntimeError("injected finish failure")):
                direct.build_direct_shared_topology(config, specs, selected)
        except RuntimeError:
            return
        raise AssertionError("Failure injection did not run.")

    was_enabled = gc.isenabled()
    gc.collect()
    gc.disable()
    try:
        with patch.object(direct._DirectBuilder, "__init__", capture):
            topology, receipt = successful_build()
            alive_success = refs[-1]() is not None
            collected_success = gc.collect()
            dead_after_collection = refs[-1]() is None
            failing_build()
            alive_failure = refs[-1]() is not None
            collected_failure = gc.collect()
            failure_dead_after_collection = refs[-1]() is None
        result = {
            "source": source, "source_after": _identity(),
            "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "automatic_cyclic_gc_enabled_during_probe": False,
            "success_builder_alive_before_manual_gc": alive_success,
            "success_builder_dead_after_manual_gc": dead_after_collection,
            "success_manual_collected_objects": collected_success,
            "failure_builder_alive_before_manual_gc": alive_failure,
            "failure_builder_dead_after_manual_gc": failure_dead_after_collection,
            "failure_manual_collected_objects": collected_failure,
            "retained_result_vertices": len(topology.vertices),
            "training_calls": 0, "native_calls": 0,
            "scope": "Lifetime with automatic cyclic GC disabled; not a measurement of memory gain or causation of the formal peak.",
        }
        if result["source_after"] != source:
            raise RuntimeError("Source changed during probe.")
        with output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
        print(json.dumps({k: v for k, v in result.items() if k not in ("source", "source_after")}))
    finally:
        if was_enabled:
            gc.enable()


if __name__ == "__main__":
    main()
