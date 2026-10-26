"""Clean-source, paired complete calls and saved-only independent replay.

Run with --output outside the checkout. Measurements use fresh child processes;
traced Python allocation and process peak working set are reported separately.
No speed, memory or convergence threshold is inferred from a small fixture.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc

from pokerlab.preflop_solver import solve_preflop
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.selected_operator_solver import census_four_street_operator, solve_four_street_operator
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from scripts.four_street_certificate_v3 import evaluate_exact
from scripts.preflop_validation import replay_policy, compare_result

ROOT = Path(__file__).resolve().parents[1]


def _request(case, iterations):
    return FourStreetSolveRequest(
        case["sb_range"], case["bb_range"], tuple(case["runouts"]),
        preflop_config=PreflopConfig.from_dict(case["config"]),
        flop_actions=PostflopActions(**case["flop_config"]),
        turn_actions=PostflopActions(**case["turn_config"]),
        river_actions=PostflopActions(**case["river_config"]),
        iterations=iterations, algorithm="cfrplus", traversal="public-batched",
        diagnostics="public-batched", resource_model="public-vector")


def _reference(request):
    return solve_preflop(
        request.sb_range, request.bb_range, request.preflop_config,
        runouts=request.runouts, flop_config=request.flop_actions.to_dict(),
        turn_config=request.turn_actions.to_dict(), river_config=request.river_actions.to_dict(),
        iterations=request.iterations, algorithm=request.algorithm,
        traversal=request.traversal, diagnostics=request.diagnostics,
        resource_model=request.resource_model)


def _rss():
    if os.name != "nt":
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage")]
    counter = Counters()
    counter.cb = ctypes.sizeof(counter)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counter), counter.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counter.PeakWorkingSetSize


def _git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def _identity():
    files = _git("ls-files").splitlines()
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in files if (ROOT / name).is_file()}
    return {"commit": _git("rev-parse", "HEAD"),
            "status": _git("status", "--porcelain"), "sha256": hashes}


def _write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _retain_or_compare(path, value):
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError(f"Saved audit changed: {path.name}")
    else:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")


def run_child(backend, traced, iterations):
    case = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text())["case"]
    request = _request(case, iterations)
    if traced:
        tracemalloc.start()
    before = time.perf_counter()
    payload = (solve_four_street_operator if backend == "operator" else _reference)(request)
    seconds = time.perf_counter() - before
    allocation = tracemalloc.get_traced_memory()[1] if traced else None
    if traced:
        tracemalloc.stop()
    return {"backend": backend, "traced": traced, "seconds": seconds,
            "python_peak_allocation_bytes": allocation,
            "process_lifetime_peak_working_set_bytes": _rss(), "payload": payload}


def verify_saved(directory, expected_manifest_sha256):
    manifest_raw = (directory / "manifest.json").read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != expected_manifest_sha256:
        raise ValueError("Saved manifest does not match the externally supplied hash.")
    manifest = json.loads(manifest_raw)
    snapshots = {}
    for name, digest in manifest["sha256"].items():
        if Path(name).name != name:
            raise ValueError("Saved artifact name must be a basename.")
        raw = (directory / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Saved artifact changed before independent replay.")
        snapshots[name] = raw
    source = json.loads(snapshots["source.json"])
    current = _identity()
    if source != current or current["status"]:
        raise ValueError("Saved replay requires the same clean committed source.")
    case = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text())["case"]
    ledger = []
    for name in ("reference-0.json", "operator-0.json"):
        raw = snapshots[name]
        payload = json.loads(raw)["payload"]
        numeric = replay_policy(payload, case["sb_range"], case["bb_range"], config=case["config"],
                                runouts=case["runouts"], flop_config=case["flop_config"],
                                turn_config=case["turn_config"], river_config=case["river_config"])
        differences = compare_result(payload, numeric)
        certificate = evaluate_exact(case, payload)
        _retain_or_compare(directory / (name[:-5] + "-certificate.json"), certificate)
        ledger.append({"artifact": name, "sha256": hashlib.sha256(raw).hexdigest(),
                       "numeric_differences": differences, "exact_metrics": certificate["metrics"],
                       "exact_target_met": certificate["threshold_met"]})
    if _identity() != source:
        raise ValueError("Source changed during saved replay.")
    if any((directory / name).read_bytes() != raw for name, raw in snapshots.items()):
        raise ValueError("Saved artifacts changed during independent replay.")
    result = {"training_calls": 0, "native_calls": 0, "audits": ledger,
              "certificate_scope": "Index zero for each backend; all measured sample bytes authenticated.",
              "manifest_sha256": expected_manifest_sha256, "source_unchanged": True}
    _retain_or_compare(directory / "saved-replay.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--child", choices=("reference", "operator"))
    parser.add_argument("--traced", action="store_true")
    parser.add_argument("--verify-saved", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    if args.child:
        print(json.dumps(run_child(args.child, args.traced, args.iterations), allow_nan=False))
        return
    if args.verify_saved:
        if not args.expected_manifest_sha256:
            parser.error("--expected-manifest-sha256 is required for saved replay")
        print(json.dumps(verify_saved(args.verify_saved, args.expected_manifest_sha256)))
        return
    if args.output is None:
        parser.error("--output is required")
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Measurements must be saved outside the checkout.")
    if output.exists():
        raise ValueError("Use a fresh output directory; retained evidence is immutable.")
    source = _identity()
    if source["status"]:
        raise ValueError("Commit source before measurements.")
    output.mkdir(parents=True)
    _write(output / "source.json", source)
    samples = []
    for traced in (False, True):
        for backend in ("reference", "operator"):
            for index in range(1 if traced else 3):
                process = subprocess.run([sys.executable, "-B", "-m", __package__ + ".benchmark_selected_operator",
                                          "--child", backend, "--iterations", str(args.iterations),
                                          *(["--traced"] if traced else [])], cwd=ROOT,
                                         capture_output=True, text=True, check=True)
                sample = json.loads(process.stdout)
                name = f"{backend}-{'traced' if traced else index}.json"
                _write(output / name, sample)
                samples.append({k: v for k, v in sample.items() if k != "payload"} | {"artifact": name})
    case = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text())["case"]
    censuses = []
    for count in (1, 2, 4, 6):
        changed = dict(case, runouts=case["runouts"][:count])
        censuses.append({"selected": count, "census": census_four_street_operator(_request(changed, args.iterations))})
    for stack in (2, 4, 8):
        changed = dict(case, config=dict(case["config"], starting_stack=[stack, stack]))
        censuses.append({"stack": stack, "census": census_four_street_operator(_request(changed, args.iterations))})
    if source != _identity():
        raise ValueError("Source changed during measurements; retain failure output.")
    report = {"schema_version": 1, "source_commit": source["commit"], "iterations": args.iterations,
              "platform": platform.platform(), "python": sys.version, "samples": samples,
              "censuses": censuses, "medians_seconds": {
                  backend: statistics.median(s["seconds"] for s in samples if s["backend"] == backend and not s["traced"])
                  for backend in ("reference", "operator")},
              "scope": "Paired bounded-game observation. Trace timings include allocation instrumentation. Process peaks include imports and interpreter. No full-deck or commercial-scale claim."}
    _write(output / "measurements.json", report)
    manifest = {"sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(output.iterdir()) if p.is_file()}}
    _write(output / "manifest.json", manifest)
    manifest_hash = hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()
    verify_saved(output, manifest_hash)
    print(json.dumps({"output": str(output), "manifest_sha256": manifest_hash,
                      "medians_seconds": report["medians_seconds"]}))


if __name__ == "__main__":
    main()
