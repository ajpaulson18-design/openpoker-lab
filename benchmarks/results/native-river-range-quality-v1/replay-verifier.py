"""Authenticate and independently replay the one retained 8x8 river batch.

This verifier reads the frozen source, build, control corpus, and attempt. It
writes one exclusive receipt outside those directories. It never trains,
compiles, looks up a backend, or executes the native program.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


EXPECTED_HEAD = "7371b450976a8b904afb7c7583070db4d5b84595"
EXPECTED_CLAIM = "9399dbdbf6de4d7397295c05269140de"
EXPECTED_EVIDENCE_SHA256 = {
    "report.json": "e348d38048f2dc235caa7a8c1674cd92b56490cf6196152a7268b1b0badb52f5",
    "claim.json": "5244c65f875b57816b4602d850969a4c1eed921dd5a2c7849022143da8c64e00",
    "status.json": "9e4b41653b0153e2036efe716bbd72f74ce79f8f0a6d27006c325b382efb93b9",
}
TARGET = Fraction(1, 1000)
APPENDED_AUDIT_FIELDS = frozenset((
    "replay_status", "numeric_target_met", "exact_target_met",
))
COUNT_MAP = {
    "worlds": "worlds", "worlds_materialized": "worlds",
    "deals": "compatible_pairs", "compatible_pairs": "compatible_pairs",
    "info_sets": "information_sets", "public_nodes": "public_nodes",
    "public_states": "public_states", "terminal_nodes": "terminal_nodes",
    "chance_nodes": "chance_nodes",
    "world_traversal_nodes": "world_traversal_nodes",
    "tree_actions": "tree_actions",
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def _pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def _constant(token):
    raise ValueError("Nonfinite JSON constant: " + token)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _read_json(path, *, compact=False):
    if not path.is_file() or path.is_symlink():
        raise ValueError("Missing or linked evidence file: " + str(path))
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"), parse_constant=_constant,
                       object_pairs_hook=_object)
    expected = _canonical(value) if compact else _pretty(value)
    if raw != expected:
        raise ValueError("Evidence is not canonical UTF-8 LF JSON: " + str(path))
    return value, raw


def _same(left, right, label):
    if _canonical(left) != _canonical(right):
        raise ValueError(label + " differs")


def _receipt(path, raw):
    return {"file": path, "bytes": len(raw), "sha256": _sha(raw)}


def _write_exclusive(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def _execution_forbidden(driver, runtime):
    """Block solve/train/compile/backend APIs and all subprocess execution.

    Source authentication uses read-only Git commands outside this context.
    The independent audit adds its own broader production-model tripwires.
    """
    calls = []
    entries = [
        (driver, "run"), (driver, "run_with_runtime"),
        (type(runtime), "call"), (type(runtime), "preflight"),
        (runtime.native, "solve_native_river"),
        (runtime.river, "solve_river_tail"),
        (runtime.turn, "solve_turn_tail"),
        (runtime.turn, "_train_original_weight_tail"),
        (runtime.fixed, "train_native_fixed_street"),
        (runtime.fixed, "_backend"), (runtime.fixed, "validate_backend"),
    ]
    build = importlib.import_module("scripts.build_native_train")
    entries.extend(((build, "build"), (build, "main")))
    for module in (runtime.public, runtime.post):
        for name, value in vars(module).items():
            if callable(value) and ("train" in name.lower() or "solve" in name.lower()):
                entries.append((module, name))
    entries.extend((subprocess, name) for name in (
        "Popen", "run", "call", "check_call", "check_output",
    ))
    entries.append((os, "system"))

    def blocker(name):
        def fail(*_args, **_kwargs):
            calls.append(name)
            raise RuntimeError("Saved-only replay called forbidden execution: " + name)
        return fail

    seen = set()
    with ExitStack() as stack:
        for owner, name in entries:
            identity = (id(owner), name)
            if identity in seen:
                continue
            seen.add(identity)
            if not hasattr(owner, name):
                raise RuntimeError("Required execution tripwire target absent: " + name)
            label = getattr(owner, "__name__", type(owner).__name__) + "." + name
            stack.enter_context(patch.object(owner, name, new=blocker(label)))
        yield calls


def _validate_envelope(attempt, driver, claim, report, status):
    if (claim.get("schema") != "native-river-range-quality-claim-v1" or
            report.get("schema") != "native-river-range-quality-report-v1" or
            claim.get("claim_id") != EXPECTED_CLAIM or
            report.get("claim_id") != EXPECTED_CLAIM or
            status.get("claim_id") != EXPECTED_CLAIM or
            claim.get("source", {}).get("head") != EXPECTED_HEAD or
            report.get("status") != "completed" or
            status.get("status") != "completed" or status.get("phase") != "done" or
            claim.get("retry_permitted") is not False or
            status.get("retry_permitted") is not False or
            claim.get("target_nash_conv") != "1/1000"):
        raise ValueError("Attempt identity/completion/no-retry envelope is invalid")
    if Path(claim.get("output", "")).resolve() != attempt:
        raise ValueError("Attempt path differs from its original claim")
    if (attempt / "failure.json").exists():
        raise ValueError("Completed attempt contains a failure receipt")
    manifest = claim.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError("Claim omitted its frozen manifest")
    driver._validate_manifest(manifest)
    manifest_raw = driver.CASE_MANIFEST.read_bytes()
    if driver._sha(driver._lf(manifest_raw)) != driver.CASE_MANIFEST_LF_SHA256:
        raise ValueError("Frozen manifest LF digest differs")
    parsed = json.loads(manifest_raw.decode("utf-8"), parse_constant=_constant,
                        object_pairs_hook=_object)
    _same(parsed, manifest, "Claim/current manifest")
    for field in ("source", "build", "control_authentication", "preflight_admissions"):
        _same(claim.get(field), report.get(field), "Claim/report " + field)
    admissions = claim.get("preflight_admissions")
    if not isinstance(admissions, list) or len(admissions) != 4:
        raise ValueError("Claim does not preserve four full-request admissions")
    for cell, admission in zip(manifest["calls"], admissions):
        driver._validate_admission(admission)
        if (admission["case_id"] != cell["case"] or
                admission["backend_cell"] != cell["backend"]):
            raise ValueError("Preflight/call order differs")
    return manifest, admissions


def _read_profiles(attempt, driver, manifest, report, status):
    profiles = report.get("profiles")
    if not isinstance(profiles, list) or len(profiles) != 4:
        raise ValueError("Report does not contain all four saved profiles")
    expected_names = {
        f"{cell['case']}-{cell['backend']}-T{manifest['iterations']}.json"
        for cell in manifest["calls"]
    }
    directory = attempt / "policies"
    entries = list(directory.iterdir())
    if (any(not p.is_file() or p.is_symlink() for p in entries) or
            {p.name for p in entries} != expected_names):
        raise ValueError("Policies directory differs from the exact four-file grid")
    loaded = []
    receipts = []
    for cell, profile in zip(manifest["calls"], profiles):
        name = f"{cell['case']}-{cell['backend']}-T{manifest['iterations']}.json"
        relative = "policies/" + name
        for field, expected in (("case", cell["case"]), ("backend", cell["backend"]),
                                ("iterations", manifest["iterations"]), ("file", relative)):
            if profile.get(field) != expected:
                raise ValueError("Profile receipt identity differs: " + relative)
        if type(profile.get("bytes")) is not int or profile["bytes"] <= 0:
            raise ValueError("Policy size receipt is not a positive integer")
        result, raw = _read_json(attempt / relative, compact=True)
        receipt = {**_receipt(relative, raw), "case": cell["case"],
                   "backend": cell["backend"], "iterations": manifest["iterations"]}
        for key, value in receipt.items():
            if profile.get(key) != value:
                raise ValueError("Saved raw policy hash/size/identity differs: " + relative)
        receipts.append(receipt)
        loaded.append((receipt, result, raw, profile))
    _same(receipts, status.get("saved_policies"), "Status/saved raw receipts")
    completed = [{"case": r["case"], "backend": r["backend"], "replay_status": "valid"}
                 for r in receipts]
    _same(completed, status.get("completed_audits"), "Status/completed audit grid")
    return loaded, receipts


def _fraction_checks(driver, audit, stored, profile, result):
    if audit.get("blocked_production_helper_calls") != []:
        raise ValueError("Independent audit reported production helper calls")
    numeric = audit.get("numeric_metrics", {})
    if set(numeric) != set(driver.METRICS):
        raise ValueError("Independent audit omitted one of eight numeric metrics")
    for value in numeric.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("Independent numeric metric is nonfinite or invalid")
    numeric_met = float(numeric["nash_conv"]) <= float(TARGET)
    if stored.get("numeric_target_met") is not numeric_met or profile.get("numeric_target_met") is not numeric_met:
        raise ValueError("Stored numeric accuracy flag differs from direct comparison")
    exact = audit["exact_audit"]
    if exact.get("nash_conv_target_fraction") != str(TARGET):
        raise ValueError("Exact target differs from the fixed protocol")
    if exact.get("status") == "admission-rejected":
        for owner, key in ((audit, "quality_gate"), (stored, "exact_target_met"),
                           (profile, "exact_target_met"), (profile, "quality_gate")):
            if owner.get(key) is not None:
                raise ValueError("Exact capacity rejection does not retain unknown accuracy")
        return {"status": "admission-rejected", "target_met": None}
    if exact.get("status") != "admitted":
        raise ValueError("Unrecognized exact audit status")
    groups = exact.get("chance_groupings", {})
    if set(groups) != {"scan", "partition"} or any(groups[k].get("status") != "admitted" for k in groups):
        raise ValueError("Exact replay did not admit both grouping modes")
    _same(groups["scan"]["metrics_fraction"], groups["partition"]["metrics_fraction"],
          "Exact scan/partition metric fraction maps")
    _same(exact["metrics_fraction"], groups["scan"]["metrics_fraction"],
          "Exact summary/group fraction maps")
    metrics = {key: Fraction(value) for key, value in exact["metrics_fraction"].items()}
    if set(metrics) != set(driver.METRICS):
        raise ValueError("Exact replay omitted one of eight metrics")
    lower = Fraction(exact["lower_value_bound_fraction"])
    upper = Fraction(exact["upper_value_bound_fraction"])
    value = metrics["value_oop"]
    nc = metrics["nash_conv"]
    if (metrics["value_ip"] != -value or lower != -metrics["ip_best_response_value"] or
            upper != metrics["oop_best_response_value"] or not lower <= value <= upper or
            metrics["oop_best_response_gain"] != upper - value or
            metrics["ip_best_response_gain"] != value - lower or
            min(metrics["oop_best_response_gain"], metrics["ip_best_response_gain"]) < 0 or
            nc != upper - lower or nc != metrics["oop_best_response_gain"] + metrics["ip_best_response_gain"] or
            metrics["exploitability"] != nc / 2):
        raise ValueError("Exact value/response interval/gain/zero-sum identities fail")
    met = nc <= TARGET
    for owner, key in ((exact, "target_met"), (audit, "quality_gate"),
                       (stored, "exact_target_met"), (profile, "exact_target_met"),
                       (profile, "quality_gate")):
        if owner.get(key) is not met:
            raise ValueError("Exact accuracy flag differs from direct Fraction comparison")
    for mode, group in groups.items():
        if (group.get("nash_conv_target_met") is not met or
                Fraction(group["lower_value_bound_fraction"]) != lower or
                Fraction(group["upper_value_bound_fraction"]) != upper):
            raise ValueError("Exact grouping interval/target differs: " + mode)
    for key, value in metrics.items():
        if abs(float(value) - float(result[key])) > 1e-9:
            raise ValueError("Exact metric differs from serialized metric: " + key)
    return {"status": "admitted", "target_met": met,
            "nash_conv_fraction": str(nc),
            "lower_value_bound_fraction": str(lower),
            "upper_value_bound_fraction": str(upper)}


def verify(source_root, build_directory, attempt_directory, output_path):
    source_root = Path(source_root).resolve()
    build_directory = Path(build_directory).resolve()
    attempt = Path(attempt_directory).resolve()
    output = Path(output_path).resolve()
    verifier = Path(__file__).resolve()
    verifier_raw = verifier.read_bytes()
    if output.exists():
        raise FileExistsError(output)
    if (attempt.is_relative_to(source_root) or attempt.is_relative_to(build_directory) or
            any(output.is_relative_to(parent) for parent in (source_root, build_directory, attempt))):
        raise ValueError("Attempt and exclusive replay output must be outside protected source/build paths")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source_root))
    driver = importlib.import_module("scripts.benchmark_native_river_range_quality")
    if Path(driver.__file__).resolve() != source_root / "scripts" / "benchmark_native_river_range_quality.py":
        raise ValueError("Imported driver resolved outside the frozen source checkout")
    runtime = driver.ProductionRuntime(source_root, build_directory)
    claim, claim_raw = _read_json(attempt / "claim.json")
    report, report_raw = _read_json(attempt / "report.json")
    status, status_raw = _read_json(attempt / "status.json")
    for name, raw in (("claim.json", claim_raw), ("report.json", report_raw),
                      ("status.json", status_raw)):
        if _sha(raw) != EXPECTED_EVIDENCE_SHA256[name]:
            raise ValueError("Original completed evidence digest differs: " + name)
    manifest, admissions = _validate_envelope(attempt, driver, claim, report, status)
    source = runtime.source_snapshot(EXPECTED_HEAD)
    build = runtime.build_snapshot()
    controls = driver.authenticate_control_corpus(claim["control_authentication"]["root"])
    _same(source, claim["source"], "Current/claimed complete source snapshot")
    _same(build, claim["build"], "Current/claimed complete build snapshot")
    _same(controls, claim["control_authentication"], "Current/claimed retained controls")
    loaded, policy_receipts = _read_profiles(attempt, driver, manifest, report, status)
    protected = {"claim.json": claim_raw, "report.json": report_raw, "status.json": status_raw}
    protected.update({r["file"]: raw for r, _, raw, _ in loaded})
    cases = {case["id"]: case for case in manifest["cases"]}
    audits = {}
    results = []
    with _execution_forbidden(driver, runtime) as blocked_calls:
        for (receipt, result, raw, profile), admission in zip(loaded, admissions):
            case = cases[receipt["case"]]
            driver._validate_return(result, case, receipt["backend"], manifest["iterations"])
            for field, expected in COUNT_MAP.items():
                if result[field] != admission[expected]:
                    raise ValueError("Saved result/preflight count differs: " + field)
            if receipt["backend"] == "native":
                driver._validate_native_receipt(result, build, admission["native_shape_admission"])
            audit = runtime.audit(result, case, manifest["exact_limits"])
            stored = profile.get("independent_audit")
            if not isinstance(stored, dict) or stored.get("replay_status") != "valid":
                raise ValueError("Saved profile does not claim a valid independent replay")
            deterministic = {key: value for key, value in stored.items()
                             if key not in APPENDED_AUDIT_FIELDS}
            _same(audit, deterministic, "Whole deterministic saved/recomputed independent audit")
            fraction = _fraction_checks(driver, audit, stored, profile, result)
            if (audit["world_count"] != admission["worlds"] or
                    audit["compatible_pairs"] != admission["compatible_pairs"] or
                    audit["information_sets"] != admission["information_sets"] or
                    audit["public_decision_nodes"] != admission["public_nodes"]):
                raise ValueError("Independent physical audit/preflight counts differ")
            _same(audit["action_rows"], result["strategy"], "Independent audit/raw action rows")
            audits[(receipt["case"], receipt["backend"])] = audit
            results.append({**receipt, "independent_replay": "matched",
                            "numeric_nash_conv": audit["numeric_metrics"]["nash_conv"],
                            "exact_fraction_check": fraction,
                            "whole_deterministic_audit_sha256": _sha(_canonical(audit)),
                            "blocked_production_helper_calls": audit["blocked_production_helper_calls"]})
        parity = []
        for case in manifest["cases"]:
            selected = {receipt["backend"]: result for receipt, result, _, _ in loaded
                        if receipt["case"] == case["id"]}
            check = driver._policy_parity(
                selected["native"], selected["python-materialized-D0"],
                audits[(case["id"], "native")], audits[(case["id"], "python-materialized-D0")],
                manifest["policy_probability_tolerance"], manifest["metric_tolerance"])
            parity.append({"case": case["id"], **check})
        _same(parity, report.get("parity"), "Saved/recomputed parity")
        _same(parity, status.get("parity"), "Status/recomputed parity")
        if blocked_calls:
            raise RuntimeError("Saved replay attempted forbidden execution")
    _same(source, runtime.source_snapshot(EXPECTED_HEAD), "Final complete source snapshot")
    _same(build, runtime.build_snapshot(), "Final complete build snapshot")
    _same(controls, driver.authenticate_control_corpus(controls["root"]), "Final retained controls")
    for relative, original in protected.items():
        if (attempt / relative).read_bytes() != original:
            raise RuntimeError("Attempt evidence changed during replay: " + relative)
    if verifier.read_bytes() != verifier_raw:
        raise RuntimeError("Verifier source changed during replay")
    receipt = {
        "schema": "native-river-range-quality-saved-replay-v1", "status": "verified",
        "claim_id": EXPECTED_CLAIM, "source_head": EXPECTED_HEAD,
        "verifier": _receipt(str(verifier), verifier_raw),
        "attempt": str(attempt), "source_root": str(source_root), "build_directory": str(build_directory),
        "protected_evidence": [_receipt(name, raw) for name, raw in sorted(protected.items())],
        "source_snapshot": source, "build_snapshot": build, "control_authentication": controls,
        "policies": policy_receipts, "profiles": results, "parity": parity,
        "production_training_calls": 0, "native_process_calls": 0, "compile_calls": 0,
        "backend_lookup_calls": 0, "blocked_execution_attempts": blocked_calls,
        "all_protected_bytes_unchanged": True,
        "scope": "Saved policies only; independent physical numeric and exact replay of two fixed 8x8 river games. Accuracy misses remain misses; parity is separate from accuracy.",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write_exclusive(output, _pretty(receipt))
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--attempt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = verify(args.source_root, args.build_dir, args.attempt, args.output)
    print(json.dumps({"status": result["status"], "policies": len(result["profiles"]),
                      "training_calls": result["production_training_calls"],
                      "output": str(args.output.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
