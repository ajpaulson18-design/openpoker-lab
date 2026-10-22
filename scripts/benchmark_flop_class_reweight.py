"""Run three no-training exact-prior controls on one fixed flop support."""
from contextlib import nullcontext
from datetime import datetime, timezone
from fractions import Fraction
import argparse
import gc
import gzip
import hashlib
import json
import platform
from pathlib import Path
import sys
import time
import traceback

from scripts import benchmark_flop_class_cost as cost
from scripts import benchmark_weighted_full_deck_flop as power
from scripts import flop_class_reweight_plan as planning
from scripts import flop_class_reweight_proof as reweighted
from scripts import flop_multistreet_validation as physical
from scripts import flop_public_classes as proof
from scripts import verify_flop_public_classes_publication as old_publication


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/flop-class-reweight-proof-v1.json"
SPEC_LF_SHA256 = "24b5f0cb29775f6b6615a03c27fb063b7fd885126d4e6808a69bcfa0fbc2fc97"
MAX_SPEC_BYTES = 64 * 1024
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_RAW_BYTES = 24 * 1024 * 1024
MAX_GZIP_BYTES = 8 * 1024 * 1024
CASE_IDS = ("baseline", "uniform", "skew")
CONTROLS = ("check-call", "bet-fold", "class-varying", "zero-reach")
BASELINE_FIELDS = ("exact_metrics", "exact_metric_count", "physical_rows_lifted",
                   "class_rows", "physical_strategy_sha256", "class_policy")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        proof._need(key not in result, "Duplicate reweight protocol/index field")
        result[key] = value
    return result


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _protocol():
    proof._need(SPEC.stat().st_size <= MAX_SPEC_BYTES,
                "Reweight protocol exceeds size bound")
    with SPEC.open("rb") as stream:
        raw = stream.read(MAX_SPEC_BYTES + 1)
    proof._need(len(raw) <= MAX_SPEC_BYTES and
                hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == SPEC_LF_SHA256,
                "Frozen reweight protocol bytes differ")
    spec = json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    proof._need(type(spec) is dict and
                spec.get("protocol_id") == "fixed-flop-class-reweight-proof-v1" and
                spec.get("controls") == list(CONTROLS) and
                [row.get("case_id") for row in spec.get("cases", ())] == list(CASE_IDS) and
                spec.get("scope") == {"board": list(planning.BOARD),
                    "oop_hands": list(planning.OOP_HANDS),
                    "ip_hands": list(planning.IP_HANDS),
                    "positive_exact_weights_only": True, "training_calls": 0},
                "Reweight protocol identity, scope, or case inventory differs")
    return spec


def _fraction(pair):
    proof._need(type(pair) is list and len(pair) == 2 and
                all(type(value) is int for value in pair) and pair[1] > 0,
                "Protocol weights must be exact [numerator, denominator] integers")
    return Fraction(pair[0], pair[1])


def _plans(spec):
    proof._need(type(spec.get("cases")) is list and len(spec["cases"]) == 3,
                "Exactly three reweight cases are required")
    plans = []
    for row, expected_id in zip(spec["cases"], CASE_IDS):
        proof._need(type(row) is dict and row.get("case_id") == expected_id and
                    set(row) == {"case_id", "oop_weights", "ip_weights"},
                    "Malformed reweight case inventory")
        oop = row["oop_weights"]
        ip = row["ip_weights"]
        proof._need(type(oop) is list and type(ip) is list and len(oop) == len(ip) == 2,
                    "Each fixed range requires exactly two protocol weights")
        plans.append((expected_id, planning.plan_weights(
            tuple(_fraction(value) for value in oop),
            tuple(_fraction(value) for value in ip))))
    expected = (
        ((Fraction(1), Fraction(1, 2)), (Fraction(1, 4), Fraction(1))),
        ((Fraction(1), Fraction(1)), (Fraction(1), Fraction(1))),
        ((Fraction(4), Fraction(1)), (Fraction(4), Fraction(1))),
    )
    proof._need(tuple((plan.oop_weights, plan.ip_weights) for _, plan in plans) == expected,
                "Protocol weights differ from the three frozen cases")
    return tuple(plans)


def _preflight(spec):
    plans = _plans(spec)
    expected = spec["preflight"]
    proof._need(type(expected) is dict and
                expected.get("oracle_builds") == 4 and
                expected.get("enumerated_physical_world_rows") == 23_760 and
                expected.get("maximum_live_physical_oracles") == 2 and
                expected.get("physical_worlds_per_oracle") == 5_940 and
                expected.get("physical_public_states_per_oracle") == 30_812 and
                expected.get("compact_worlds_per_case") == 126 and
                expected.get("compact_public_states_per_case") == 1_001 and
                expected.get("compact_policy_rows_per_case") == 466 and
                expected.get("control_audits") == 12,
                "Reweight preflight dimensions differ")
    proof._need(5_940 <= physical.MAX_WORLDS and 3 <= physical.MAX_PAIRS and
                30_812 <= physical.MAX_PUBLIC_STATES and 9_512 <= physical.MAX_DECISIONS,
                "Fixed physical oracle caps no longer admit the preregistered game")
    proof._need(planning.MAX_COMPONENT_BITS == spec["limits"]["weight_component_bits"] == 128
                and planning.MAX_CLASS_MASS_BITS == spec["limits"]["joint_world_mass_bits"]
                == reweighted.candidate.MAX_MASS_INTEGER_BITS == 384
                and len(str((1 << planning.MAX_CLASS_MASS_BITS) - 1))
                <= reweighted.candidate.MAX_MASS_COMPONENT_DIGITS,
                "Requested rational masses exceed the unchanged candidate envelope")
    dimensions = (planning.RUNOUTS_PER_PAIR, 5_940, 30_812, 1_001, 126, 466)
    proof._need(dimensions == (1_980, expected["physical_worlds_per_oracle"],
                expected["physical_public_states_per_oracle"],
                expected["compact_public_states_per_case"],
                expected["compact_worlds_per_case"], expected["compact_policy_rows_per_case"]),
                "Planner and protocol dimensions differ")
    return plans, {**expected, "scope_note": (
        "Census/capacity counts only; not complete CPU, arithmetic, time, byte, or RSS bounds.")}


def _source_snapshot():
    state = cost._source_snapshot()
    extras = ("scripts/flop_class_reweight_plan.py", "scripts/flop_class_reweight_proof.py",
              "scripts/benchmark_flop_class_reweight.py",
              "scripts/verify_flop_public_classes_publication.py",
              "benchmarks/flop-class-reweight-proof-v1.json")
    hashes = dict(state["source_lf_sha256"])
    for name in extras:
        path = ROOT / name
        proof._need(path.stat().st_size <= MAX_SOURCE_BYTES,
                    "Reweight source exceeds size bound")
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        proof._need(len(raw) <= MAX_SOURCE_BYTES,
                    "Reweight source exceeds size bound")
        hashes[name] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    state["source_lf_sha256"] = dict(sorted(hashes.items()))
    return state


def _plan_record(plan):
    return {"board": list(plan.board),
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
            "scope": plan.scope}


def _write_index(directory, report):
    unsigned = {key: value for key, value in report.items() if key != "index_sha256"}
    report["index_sha256"] = proof._digest(unsigned)
    raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    proof._need(len(raw) <= MAX_INDEX_BYTES, "Reweight index exceeds size bound")
    temp = directory / "index.json.tmp"
    temp.write_bytes(raw)
    temp.replace(directory / "index.json")


def _write_gzip(directory, filename, value):
    raw = cost._canonical(value, newline=True)
    proof._need(len(raw) <= MAX_RAW_BYTES, "Reweight evidence exceeds raw size bound")
    compressed = gzip.compress(raw, mtime=0)
    proof._need(len(compressed) <= MAX_GZIP_BYTES,
                "Reweight evidence exceeds gzip size bound")
    path = directory / filename
    with path.open("xb") as stream:
        stream.write(compressed)
    return {"path": filename, "raw_bytes": len(raw), "gzip_bytes": len(compressed),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "gzip_sha256": hashlib.sha256(compressed).hexdigest()}


def _record_error(report, phase, exc, *, case=None, control=None):
    entry = {"phase": phase, "case_id": case, "control": control,
             "error": f"{type(exc).__name__}: {exc}",
             "traceback": traceback.format_exc()}
    report["errors"].append(entry)
    return entry


def _case_preparation(case_id, model, plan):
    oracle = model.physical
    return {"case_id": case_id, "plan": _plan_record(plan),
            "normalizer": [oracle["normalizer"].numerator, oracle["normalizer"].denominator],
            "pair_counts": oracle["pair_counts"],
            "pair_probabilities": [[a, b, value] for (a, b), value in
                                   sorted(oracle["pair_probabilities"].items())],
            "worlds": len(oracle["worlds"]), "census": model.census,
            "partition": model.partition,
            "weighted_worlds_sha256": proof._digest(proof._world_rows(oracle["worlds"])),
            "physical_tree_sha256": proof._digest(proof._structure(oracle["root"])),
            "baseline_world_sha256": proof._digest(proof._world_rows(model.baseline["worlds"])),
            "baseline_tree_sha256": proof._digest(proof._structure(model.baseline["root"]))}


def _compare_old_baseline(case_id, mode, audit, old_report):
    if case_id != "baseline":
        return
    saved_controls = old_report.get("controls")
    proof._need(type(saved_controls) is dict and set(saved_controls) == set(CONTROLS),
                "Authenticated old publication lacks all four baseline controls")
    proof._need(mode in CONTROLS, "Unknown baseline control")
    saved = saved_controls[mode]
    proof._need(all(proof._typed(audit[key]) == proof._typed(saved[key])
                    for key in BASELINE_FIELDS),
                "Reweighted baseline differs from authenticated old control: " + mode)


def _audit_summary(audit):
    proof._need(type(audit) is dict, "Control audit must be a mapping")
    return {key: value for key, value in audit.items() if key != "class_policy"}


def _valid_guard_census(calls):
    return (type(calls) is dict and len(calls) == 41 and
            all(type(value) is int and value == 0 for value in calls.values()))


def _control_record(case_id, mode, payload, audit):
    return {"case_id": case_id, "control": mode, "payload": payload, "audit": audit}


def _execution_state(state):
    state = state or {"mode": "direct-call", "system_required": False}
    proof._need(type(state) is dict, "Execution state must be a mapping")
    if state.get("mode") in ("direct-call", "ordinary-process"):
        proof._need(state == {"mode": state["mode"], "system_required": False},
                    "Malformed ordinary execution state")
    else:
        proof._need(state.get("mode") == "windows-benchmark-thread" and
                    state.get("system_required") is True and
                    type(state.get("requested_flags")) is int and
                    state["requested_flags"] == 0x80000001 and
                    type(state.get("previous_flags")) is int and state["previous_flags"] > 0 and
                    set(state) == {"mode", "system_required", "previous_flags", "requested_flags"},
                    "Malformed Windows execution state")
    return state


def run(output, *, execution_state=None):
    output, root = Path(output).resolve(), ROOT.resolve()
    proof._need(not output.exists() and output != root and root not in output.parents and
                output not in root.parents,
                "Reweight output must be new and outside the source checkout")
    output.mkdir(parents=True, exist_ok=False)
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    report = {"schema_version": 1, "protocol_id": "fixed-flop-class-reweight-proof-v1",
              "status": "preparing", "created_at_utc": _utc(), "errors": [],
              "files": [], "cases": [], "training_calls": 0,
              "execution_state": _execution_state(execution_state),
              "runtime": {"python": sys.version,
                          "implementation": platform.python_implementation(),
                          "platform": platform.platform()}}
    plans = ()
    baseline = None
    old_report = None
    calls = {}
    current_snapshot = None
    try:
        spec = _protocol()
        plans, forecast = _preflight(spec)  # all three cases admitted before any oracle/ranking
        current_snapshot = _source_snapshot()
        report.update(protocol=spec, preflight=forecast, source_before=current_snapshot,
                      cases=[{"case_id": case_id, "plan": _plan_record(plan),
                              "status": "not-run", "controls": [
                                  {"control": mode, "status": "not-run"}
                                  for mode in CONTROLS]}
                             for case_id, plan in plans])
        _write_index(output, report)
        old_report = old_publication.authenticate()  # cheap immutable receipt only
        proof._need(type(old_report) is dict and old_report.get("training_calls") == 0,
                    "Old no-training publication authentication differs")
        report["baseline_receipt"] = {
            "raw_sha256": old_publication.RAW_SHA256,
            "artifact_sha256": old_publication.ARTIFACT_SHA256,
            "interruption_sha256": old_publication.INTERRUPTION_SHA256,
            "physical_worlds_sha256": old_report["physical_worlds_sha256"],
            "physical_tree_sha256": old_report["physical_tree_sha256"],
            "source_lf_sha256": old_report["source_lf_sha256"],
            "training_calls": old_report["training_calls"],
            "forbidden_production_calls": old_report["forbidden_production_calls"]}
        _write_index(output, report)
        if _source_snapshot() != current_snapshot:
            raise ValueError("Source snapshot changed during preflight/authentication")
        with proof.independent_guard() as calls:
            try:
                report["active_phase"] = "baseline-oracle-preparation"
                _write_index(output, report)
                baseline = physical.prepare_oracle(proof.BOARD, proof.OOP, proof.IP, proof.CONFIG)
                proof._physical_anchor(baseline)
                report.pop("active_phase", None)
                _write_index(output, report)
                if _source_snapshot() != current_snapshot:
                    raise ValueError("Source snapshot changed during baseline preparation")
                for case_row, (case_id, plan) in zip(report["cases"], plans):
                    case_row.update(status="active", started_at_utc=_utc())
                    report["active_case"] = case_id
                    _write_index(output, report)
                    case_snapshot = _source_snapshot()
                    case_row["source_before"] = case_snapshot
                    if case_snapshot != current_snapshot:
                        case_row.update(status="error", finished_at_utc=_utc(),
                                        source_after=case_snapshot)
                        report["errors"].append({"phase": "case-preflight-source-check",
                            "case_id": case_id,
                            "error": "Source snapshot changed before case preparation"})
                        report.pop("active_case", None)
                        _write_index(output, report)
                        raise ValueError("Source snapshot changed before case preparation")
                    case_started_wall, case_started_cpu = time.perf_counter(), time.process_time()
                    model = None
                    try:
                        model = reweighted.build_model(plan, baseline=baseline)
                        prep = _case_preparation(case_id, model, plan)
                        artifact = _write_gzip(output, f"{case_id}-preparation.json.gz", prep)
                        report["files"].append(artifact)
                        case_row["preparation_file"] = artifact
                        case_row["census"] = model.census
                        _write_index(output, report)
                        for mode, control_row in zip(CONTROLS, case_row["controls"]):
                            control_row.update(status="active", started_at_utc=_utc())
                            report["active_control"] = mode
                            _write_index(output, report)
                            control_started_wall, control_started_cpu = time.perf_counter(), time.process_time()
                            try:
                                payload = reweighted.control_policy(model, mode)
                                audit = reweighted.audit_policy(payload, model)
                                _compare_old_baseline(case_id, mode, audit, old_report)
                                artifact = _write_gzip(output, f"{case_id}-{mode}.json.gz",
                                                       _control_record(case_id, mode, payload, audit))
                                report["files"].append(artifact)
                                control_row.update(status="complete", finished_at_utc=_utc(),
                                                   wall_seconds=time.perf_counter()-control_started_wall,
                                                   process_seconds=time.process_time()-control_started_cpu,
                                                   evidence_file=artifact,
                                                   audit_summary=_audit_summary(audit))
                                _write_index(output, report)
                                if _source_snapshot() != case_snapshot:
                                    raise ValueError("Source snapshot changed during control audit")
                            except BaseException as exc:
                                control_row.update(status="error", finished_at_utc=_utc())
                                case_row.update(status="error", finished_at_utc=_utc())
                                _record_error(report, "control-audit", exc,
                                              case=case_id, control=mode)
                                raise
                            finally:
                                payload = None
                                audit = None
                                control_record = None
                        case_row.update(status="complete", finished_at_utc=_utc(),
                                        wall_seconds=time.perf_counter()-case_started_wall,
                                        process_seconds=time.process_time()-case_started_cpu)
                    except BaseException as exc:
                        if case_row["status"] != "error":
                            case_row.update(status="error", finished_at_utc=_utc())
                            _record_error(report, "case", exc, case=case_id)
                        raise
                    finally:
                        model = None
                        prep = None
                        gc.collect()
                        report.pop("active_control", None)
                        report.pop("active_case", None)
                        report.pop("active_phase", None)
                        try:
                            case_row["source_after"] = _source_snapshot()
                            if ("source_before" in case_row and
                                    case_row["source_after"] != case_row["source_before"]):
                                report["errors"].append({"phase": "case-source-check",
                                    "case_id": case_id,
                                    "error": "Source snapshot changed during case"})
                                case_row["status"] = "error"
                        except BaseException as source_exc:
                            case_row["source_after_error"] = (
                                f"{type(source_exc).__name__}: {source_exc}")
                            report["errors"].append({"phase": "case-source-check",
                                "case_id": case_id, "error": case_row["source_after_error"],
                                "traceback": traceback.format_exc()})
                            case_row["status"] = "error"
                        _write_index(output, report)
                    if case_row["status"] != "complete":
                        raise ValueError("Case did not complete cleanly: " + case_id)
                    if _source_snapshot() != current_snapshot:
                        raise ValueError("Source snapshot changed after case")
            except BaseException:
                raise
    except BaseException as exc:
        if not report["errors"]:
            _record_error(report, "run", exc)
        active_case = report.pop("active_case", None)
        report.pop("active_control", None)
        report.pop("active_phase", None)
        if active_case is not None:
            for row in report.get("cases", []):
                if row.get("case_id") == active_case and row.get("status") == "active":
                    row.update(status="error", finished_at_utc=_utc())
        report["status"] = "error"
        for row in report.get("cases", []):
            if row["status"] == "not-run":
                row["not_run_reason"] = "stopped-after-earlier-failure"
    finally:
        try:
            report["source_after"] = _source_snapshot()
            if current_snapshot is not None and report["source_after"] != current_snapshot:
                report["errors"].append({"phase": "final-source-check",
                    "error": "Source snapshot changed during run"})
                report["status"] = "error"
        except BaseException as exc:
            _record_error(report, "final-source-check", exc)
            report["status"] = "error"
        report["forbidden_production_calls"] = calls
        if not _valid_guard_census(calls):
            report["errors"].append({"phase": "authority-guard",
                                      "error": "Forbidden production guard census is incomplete or nonzero"})
            report["status"] = "error"
        report["training_calls"] = 0
        report["finished_at_utc"] = _utc()
        report["wall_seconds"] = time.perf_counter() - started_wall
        report["process_seconds"] = time.process_time() - started_cpu
        if (not report["errors"] and len(report.get("cases", [])) == 3 and
                all(row.get("status") == "complete" and
                    len(row.get("controls", [])) == 4 and
                    all(control.get("status") == "complete" for control in row["controls"])
                    for row in report["cases"]) and report["training_calls"] == 0):
            report["status"] = "complete"
        elif report["status"] != "error":
            report["status"] = "error"
        _write_index(output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    context = (power.measurement_execution_state() if sys.platform == "win32" else
               nullcontext({"mode": "ordinary-process", "system_required": False}))
    with context as state:
        report = run(args.output, execution_state=state)
    print(json.dumps({"status": report["status"], "cases": len(report.get("cases", [])),
                      "files": len(report.get("files", [])),
                      "training_calls": report["training_calls"]}, sort_keys=True))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
