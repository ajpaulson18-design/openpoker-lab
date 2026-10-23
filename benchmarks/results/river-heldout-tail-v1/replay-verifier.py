"""Re-audit a completed river-tail attempt without production solve helpers."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch


HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
TOLERANCE = 1e-9


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True,
                       allow_nan=False) + "\n").encode("utf-8")


def _read_json(path: Path):
    raw = path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise ValueError(f"Expected canonical LF artifact: {path.name}")
    value = json.loads(raw.decode("utf-8"))
    if _json_bytes(value) != raw:
        raise ValueError(f"Artifact is not in canonical JSON form: {path.name}")
    return value, raw


def _blocked_patches(driver, base, postflop, public_cfr, public_diagnostics,
                     tail, turn_tail, river_tree, ranked_river):
    calls = []

    def blocked(name):
        def fail(*_args, **_kwargs):
            calls.append(name)
            raise RuntimeError(f"Production helper called during independent replay: {name}")
        return fail

    entries = (
        (driver, "_preflight_all"), (driver, "_case_preflight"),
        (driver, "_solve"), (base, "_preflight_all"),
        (postflop, "_enumerate_worlds"), (postflop, "_build_postflop_tree"),
        (postflop, "_prefix_hand_index"), (postflop, "solve_postflop"),
        (postflop, "train_public_batched"),
        (postflop, "train"), (postflop, "train_plus"),
        (postflop, "train_planned"), (postflop, "evaluate"),
        (postflop, "evaluate_profile"), (postflop, "best_response"),
        (postflop, "RankedRiverPayoffs"),
        (public_cfr, "_validate_inputs"), (public_cfr, "_aggregate_prefixes"),
        (public_cfr, "train_public_batched"), (public_cfr, "train_ranked_river"),
        (public_cfr, "train_ranked_turn"),
        (public_diagnostics, "evaluate_profile"),
        (river_tree, "_build_tree"), (river_tree, "_terminal_value"),
        (ranked_river, "RankedRiverPayoffs"),
        (tail, "solve_river_tail"), (tail, "_enumerate_worlds"),
        (tail, "_build_postflop_tree"), (tail, "_prefix_hand_index"),
        (tail, "_validate_inputs"), (tail, "_aggregate_prefixes"),
        (tail, "_train_original_weight_tail"), (tail, "evaluate_profile"),
        (turn_tail, "_train_original_weight_tail"),
    )
    return calls, entries, blocked


def _profile_paths(attempts: Path, driver, report):
    rows = report.get("results")
    if not isinstance(rows, list) or len(rows) != len(driver.GRID):
        raise ValueError("Report does not contain the exact four saved profiles")
    paths = []
    expected_names = {
        f"{case_id}-T{iterations}-D{discard}.json"
        for case_id, iterations, discard in driver.GRID
    }
    policy_dir = attempts / "policies"
    if not policy_dir.is_dir():
        raise ValueError("Attempt has no policies directory")
    actual_names = {entry.name for entry in policy_dir.iterdir() if entry.is_file()}
    if actual_names != expected_names or any(entry.is_dir() for entry in policy_dir.iterdir()):
        raise ValueError("Policies directory does not contain exactly the four frozen files")
    for identity, row in zip(driver.GRID, rows):
        case_id, iterations, discard = identity
        expected_identity = driver._identity(case_id, iterations, discard)
        expected_name = f"{case_id}-T{iterations}-D{discard}.json"
        if any(row.get(key) != value for key, value in expected_identity.items()):
            raise ValueError("Report profile identity differs from the frozen grid")
        if row.get("policy_file") != f"policies/{expected_name}":
            raise ValueError("Report policy path differs from the frozen grid")
        path = attempts / "policies" / expected_name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Saved policy is missing: {expected_name}")
        paths.append((path, expected_identity, row))
    return paths


def _direct_fraction_checks(audit, stored_row, result, driver):
    summary = audit["exact_audit"]
    if summary.get("nash_conv_target_fraction") != "1/1000":
        raise ValueError("Exact replay target fraction differs from the frozen protocol")
    if summary.get("status") != "admitted":
        if stored_row.get("exact_target_met") is not None:
            raise ValueError("Exact capacity miss must retain a null target flag")
        return {"status": summary.get("status"), "target_met": None}

    groups = summary.get("chance_groupings", {})
    if set(groups) != {"scan", "partition"}:
        raise ValueError("Exact replay lacks both scan and partition results")
    if groups["scan"].get("metrics_fraction") != groups["partition"].get("metrics_fraction"):
        raise ValueError("Exact scan and partition Fraction maps differ")
    metrics = {key: Fraction(value) for key, value in summary["metrics_fraction"].items()}
    if set(metrics) != set(driver.base.METRICS):
        raise ValueError("Exact replay did not report all eight metrics")
    lower = Fraction(summary["lower_value_bound_fraction"])
    upper = Fraction(summary["upper_value_bound_fraction"])
    value = metrics["value_oop"]
    nc = metrics["nash_conv"]
    target = Fraction(1, 1000)
    if (metrics["value_ip"] != -value or
            lower != -metrics["ip_best_response_value"] or
            upper != metrics["oop_best_response_value"] or
            not lower <= value <= upper or
            upper - lower != metrics["oop_best_response_gain"] + metrics["ip_best_response_gain"] or
            metrics["oop_best_response_gain"] != upper - value or
            metrics["ip_best_response_gain"] != value - lower or
            min(metrics["oop_best_response_gain"], metrics["ip_best_response_gain"]) < 0 or
            nc != metrics["oop_best_response_gain"] + metrics["ip_best_response_gain"] or
            metrics["exploitability"] != nc / 2):
        raise ValueError("Exact Fraction value, gains, or response interval identities fail")
    exact_met = nc <= target
    if summary.get("target_met") is not exact_met or stored_row.get("exact_target_met") is not exact_met:
        raise ValueError("Exact Fraction target flag differs from direct target comparison")
    if audit.get("exact_vs_result_differences") is None:
        raise ValueError("Admitted exact replay lacks serialized-metric comparisons")
    for key, exact_value in metrics.items():
        numeric = result.get(key)
        if isinstance(numeric, bool) or not isinstance(numeric, (int, float)):
            raise ValueError(f"Serialized metric is not numeric: {key}")
        if abs(float(exact_value) - float(numeric)) > TOLERANCE:
            raise ValueError(f"Exact Fraction metric differs from policy metric: {key}")
    return {"status": "admitted", "target_met": exact_met,
            "lower_value_bound_fraction": str(lower),
            "upper_value_bound_fraction": str(upper),
            "nash_conv_fraction": str(nc)}


def _check_report_envelope(attempts: Path, driver, report, claim, status):
    expected_calls = [driver._identity(*row) for row in driver.GRID]
    if (report.get("benchmark_id") != driver.RESULT_ID or
            report.get("status") != "completed" or
            claim.get("benchmark_id") != driver.RESULT_ID or
            status.get("status") != "completed" or
            report.get("claim_id") != claim.get("claim_id") or
            status.get("claim_id") != claim.get("claim_id") or
            report.get("source_head") != claim.get("expected_source_commit") or
            report.get("fixed_grid", {}).get("calls") != expected_calls or
            report.get("fixed_grid", {}).get("algorithm") != "cfrplus" or
            claim.get("fixed_grid") != expected_calls or
            report.get("fixed_grid", {}).get("threshold_nash_conv_fraction") != "1/1000" or
            report.get("fixed_grid", {}).get("threshold_is_reporting_only") is not True or
            claim.get("target_nash_conv_fraction") != "1/1000" or
            claim.get("target_is_reporting_only") is not True or
            claim.get("retry_permitted") is not False or
            status.get("retry_permitted") is not False or
            status.get("completed_profiles") != [row.get("policy_file") for row in report.get("results", [])]):
        raise ValueError("Attempt report, claim, status, or fixed-grid metadata disagree")
    if (claim.get("baseline_report_sha256") != driver.BASELINE_REPORT_SHA256 or
            not claim.get("claim_id")):
        raise ValueError("Attempt does not bind the frozen v1 baseline identity")
    if (attempts / "failure.json").exists():
        raise ValueError("A completed attempt must not contain a failure receipt")


def verify(source_root: Path, attempts_dir: Path, receipt_path: Path):
    verifier_path = Path(__file__).resolve()
    verifier_before = verifier_path.read_bytes()
    verifier_hash = _sha(verifier_before)
    source_root = source_root.resolve()
    attempts = attempts_dir.resolve()
    receipt_path = receipt_path.resolve()
    if not (source_root / "scripts" / "benchmark_river_heldout_tail.py").is_file():
        raise ValueError("--source-root does not contain the integrated tail driver")
    if attempts.is_relative_to(source_root) or receipt_path.is_relative_to(source_root):
        raise ValueError("Attempt and replay receipt must be outside the source checkout")
    if receipt_path.is_relative_to(attempts):
        raise ValueError("Replay receipt must not modify the original attempt directory")
    if receipt_path.exists():
        raise FileExistsError(receipt_path)

    sys.path.insert(0, str(source_root))
    from pokerlab import postflop_solver as postflop
    from pokerlab import public_cfr, public_diagnostics
    from pokerlab import river_tail_adapter as tail
    from pokerlab import ranked_river, river_tree
    from pokerlab import turn_tail_adapter as turn_tail
    from scripts import benchmark_river_heldout_tail as driver

    if driver.ROOT.resolve() != source_root:
        raise ValueError("Imported driver resolved to a different source checkout")
    head = subprocess.check_output(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True,
        stderr=subprocess.STDOUT).strip()
    if not HEAD_RE.fullmatch(head):
        raise ValueError("Source checkout HEAD is malformed")
    report, report_raw = _read_json(attempts / "report.json")
    claim, claim_raw = _read_json(attempts / "run-claim.json")
    status, status_raw = _read_json(attempts / "run-status.json")
    _check_report_envelope(attempts, driver, report, claim, status)
    if claim.get("expected_source_commit") != head:
        raise ValueError("Current source HEAD differs from the attempt claim")

    source_before = driver._source_guard(head)
    if report.get("source_state") != source_before:
        raise ValueError("Current complete source/baseline pins differ from the saved report")
    if (report.get("preflight") is None or
            report["preflight"] != driver._validate_preflight_receipt(report["preflight"])):
        raise ValueError("Saved four-call preflight receipt is invalid")
    baseline = driver._baseline_check(source_before)
    if baseline != report.get("baseline_authentication"):
        raise ValueError("Frozen baseline authentication differs from the report")
    fresh_preflight = driver._preflight_all()
    if driver._json_bytes(fresh_preflight) != driver._json_bytes(report.get("preflight")):
        raise ValueError("Saved preflight counts/work differ from fresh no-training preflight")
    if driver._source_guard(head) != source_before:
        raise RuntimeError("Source or baseline artifacts changed during preflight verification")

    profiles = _profile_paths(attempts, driver, report)
    raw_policies = {}
    parsed_policies = {}
    for path, identity, row in profiles:
        raw = path.read_bytes()
        if (b"\r" in raw or not raw.endswith(b"\n") or
                _sha(raw) != row.get("policy_sha256") or
                len(raw) != row.get("policy_bytes")):
            raise ValueError(f"Saved policy hash/length/LF check failed: {path.name}")
        policy = json.loads(raw.decode("utf-8"))
        if driver._json_bytes(policy) != raw:
            raise ValueError(f"Saved policy is not canonical JSON: {path.name}")
        raw_policies[path.name] = {"bytes": len(raw), "sha256": _sha(raw)}
        parsed_policies[path.name] = (policy, identity, row)

    protected_files = {
        "report.json": report_raw,
        "run-claim.json": claim_raw,
        "run-status.json": status_raw,
        **{name: (attempts / "policies" / name).read_bytes() for name in raw_policies},
    }
    blocked_calls, blocked_entries, blocked_factory = _blocked_patches(
        driver, driver.base, postflop, public_cfr, public_diagnostics, tail,
        turn_tail, river_tree, ranked_river)
    results = []
    with ExitStack() as stack:
        for owner, name in blocked_entries:
            if not hasattr(owner, name):
                raise RuntimeError(f"Expected production entry point is unavailable: {name}")
            stack.enter_context(patch.object(owner, name,
                                             new=blocked_factory(f"{owner.__name__}.{name}")))
        # The v1 policies are re-authenticated via independent helpers under
        # the same production-call tripwires before the new tail policies.
        baseline_again = driver._baseline_check(source_before)
        if baseline_again != baseline:
            raise ValueError("Baseline replay changed during verifier execution")
        for path, identity, report_row in profiles:
            policy, _, _ = parsed_policies[path.name]
            case = driver.base._case_by_id(identity["scenario"])
            preflight = next(
                row for row in report["preflight"]["tail_calls"]
                if row["identity"] == identity
            )
            if report_row.get("preflight") != preflight:
                raise ValueError(f"Profile preflight copy differs from batch receipt: {path.name}")
            replay = driver._tail_audit_policy(
                policy, case, identity["iterations"], identity["discard"],
                preflight=preflight)
            direct = _direct_fraction_checks(replay, report_row, policy, driver)
            expected_fields = (
                "metrics", "numeric_differences", "numeric_target_met", "exact_target_met",
                "worlds", "compatible_pairs", "information_sets",
                "public_decision_nodes", "exact_audit",
                "exact_vs_result_differences", "exact_vs_numeric_differences",
            )
            for field in expected_fields:
                if replay.get(field) != report_row.get(field):
                    raise ValueError(f"Saved replay differs from report field {field}: {path.name}")
            if (report_row.get("saved_reload_replay") != "passed" or
                    report_row.get("source_iteration_window") != [identity["discard"] + 1,
                                                                      identity["iterations"]] or
                    report_row.get("average_weight_sum") != (
                        identity["iterations"] * (identity["iterations"] + 1) -
                        identity["discard"] * (identity["discard"] + 1)) // 2):
                raise ValueError(f"Saved row schedule metadata differs: {path.name}")
            results.append({
                **identity, "policy_file": report_row["policy_file"],
                "policy_sha256": raw_policies[path.name]["sha256"],
                "exact_target_met": replay["exact_target_met"],
                "numeric_target_met": replay["numeric_target_met"],
                "exact_interval": direct,
                "metrics": replay["metrics"],
            })

    if blocked_calls:
        raise RuntimeError(f"Production helper calls were observed: {blocked_calls}")
    source_after = driver._source_guard(head)
    if source_after != source_before:
        raise RuntimeError("Source or baseline artifacts changed during saved replay")
    if subprocess.check_output(["git", "-C", str(source_root), "rev-parse", "HEAD"],
                               text=True, stderr=subprocess.STDOUT).strip() != head:
        raise RuntimeError("Source HEAD changed during saved replay")
    after_artifacts = {
        "report.json": (attempts / "report.json").read_bytes(),
        "run-claim.json": (attempts / "run-claim.json").read_bytes(),
        "run-status.json": (attempts / "run-status.json").read_bytes(),
        **{name: (attempts / "policies" / name).read_bytes() for name in raw_policies},
    }
    if after_artifacts != protected_files:
        raise RuntimeError("Original attempt bytes changed during verifier run")

    verifier_raw = verifier_path.read_bytes()
    if verifier_raw != verifier_before:
        raise RuntimeError("Verifier source changed during saved replay")
    receipt = {
        "schema": "river-heldout-tail-independent-replay-v1",
        "status": "passed", "source_head": head,
        "source_state": source_before,
        "verifier": {"path_name": verifier_path.name,
                     "bytes": len(verifier_raw), "sha256": verifier_hash},
        "attempt": {
            "path_name": attempts.name,
            "report_sha256": _sha(report_raw), "claim_sha256": _sha(claim_raw),
            "status_sha256": _sha(status_raw), "policies": raw_policies,
        },
        "baseline_authentication": baseline,
        "fresh_no_training_preflight": True,
        "blocked_production_calls_during_saved_replay": blocked_calls,
        "training_calls": 0,
        "replayed_profiles": results,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Saved finite configured river policies only; no training or convergence claim.",
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_json_bytes(receipt))
        stream.flush()
        os.fsync(stream.fileno())
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--attempts-dir", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    receipt = verify(args.source_root, args.attempts_dir, args.receipt)
    print(json.dumps({"status": receipt["status"],
                      "replayed_profiles": len(receipt["replayed_profiles"]),
                      "receipt": str(args.receipt.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
