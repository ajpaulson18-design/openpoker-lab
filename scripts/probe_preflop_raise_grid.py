"""Frozen structural coverage grid for non-all-in preflop raises; never trains."""
import gc
import json
import platform
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts import probe_preflop_raise_admission as probe

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-raise-admission-grid-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-raise-admission-grid-v1.json"


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    revision, dirty = probe.git_revision(None), probe.worktree_dirty()
    if dirty is not False or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("Freeze the grid source/spec in a clean commit before probing.")
    paths = tuple(dict.fromkeys((*probe.SOURCE_PATHS,
                 "scripts/probe_preflop_raise_grid.py", SPEC.relative_to(ROOT).as_posix())))
    hashes = {p: probe.file_sha256(ROOT / p) for p in paths}
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()):
        raise RuntimeError("Every frozen source/spec must have a valid hash.")
    assert spec["sb"] == probe.SB_RANGE and spec["bb"] == probe.BB_RANGE
    assert spec["flops"] == [list(flop) for flop in probe.FLOPS]
    assert all(stage == spec["postflop_actions"] for stage in probe.STAGES.values())
    assert spec["preflop_actions"] == {"raise_sizes": [0.5], "max_raises": 1, "include_all_in": False}
    assert spec["structural_checkpoints"] == [
        {"iterations": t, "delay": t // 2} for t in (10, 20, 40, 90)]
    outcomes = {n: probe.futures(probe.FLOPS[:n]) for n in spec["flop_counts"]}
    records = []
    for stack in spec["starting_stacks"]:
        config = probe.make_config(stack)
        boundary = probe.preflop_boundary(config)
        assert all(v > 0 for v in boundary["open_call_boundary"]["remaining_stacks"])
        for count in spec["flop_counts"]:
            print(f"structural probe stack={stack}, flops={count} start", flush=True)
            gc.collect()
            record = probe.probe(f"{count}-flop", outcomes[count], config)
            records.append({"starting_stack": stack, "config": config.to_dict(),
                            "preflop_tree_boundary": boundary, **record})
            print(f"  {record['status']}: {record.get('error', 'vector budget available')}", flush=True)
    if hashes != {p: probe.file_sha256(ROOT / p) for p in paths}:
        raise RuntimeError("Frozen source/spec changed during probe.")
    if probe.git_revision(None) != revision or probe.worktree_dirty() is not False:
        raise RuntimeError("Revision/worktree changed during probe.")
    report = {"schema_version": 1, "probe_id": spec["probe_id"],
              "source_revision": revision, "worktree_dirty_at_start": False,
              "source_hashes": hashes, "configuration_sha256": hashes[SPEC.relative_to(ROOT).as_posix()],
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "platform": platform.platform(),
              "specification": spec, "records": records,
              "scope": "Structural admission only; all listed fixtures retained. No training/view allocation, policy quality, convergence, runtime or memory measurement. Current guards and shared postflop kernels are unchanged; a smaller admitted stack does not resolve a larger rejected stack."}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"saved {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
