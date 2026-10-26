"""Immutable no-training report wrapper for the independent full-physical oracle."""
from fractions import Fraction
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from scripts.historical_foundation_sources import compatible_exact_source_maps, foundation_source_accepts, operation_fingerprints
import subprocess

from scripts import full_deck_raised_reference as reference
from scripts import full_physical_exact_oracle as oracle


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results"
NUMERIC_REPORT = RESULTS / "full-deck-raised-turn-tail-v1.json"
EXACT_TAIL_REPORT = RESULTS / "full-deck-raised-turn-tail-exact-v1.json"
WITNESS_REPORT = RESULTS / "full-deck-raised-turn-clean-witness-v1.json"
REFERENCE_REPORT = RESULTS / "full-deck-raised-turn-reference-v1.json"
TAIL_POLICY_DIR = RESULTS / "full-deck-raised-turn-tail-policies-v1"
WITNESS_POLICY_DIR = RESULTS / "full-deck-raised-turn-clean-witness-policies-v1"
REPORT = RESULTS / "full-deck-raised-turn-full-physical-v1.json"

NUMERIC_REPORT_SHA256 = "9e51cbcf9f031f371806be06e6a23589e0dd27d5e3ffffcf36fc545eed5d6998"
EXACT_TAIL_REPORT_SHA256 = "f4901675fcb026fbac6713baf604650fd48f510c5ae4dc6be2c776c0a780c0c7"
WITNESS_REPORT_SHA256 = "e9e44108b1158840383cd025dcd995b21d3fc35d902a59ab2bae3a5060bf88e6"
REFERENCE_REPORT_SHA256 = "bff6aaf4d2bf6038503645787d66cff9f57bcb1385e334364f72126a67211165"

MAX_REPORT_BYTES = 8_000_000
MAX_POLICY_BYTES = 2_000_000
MAX_INPUT_REPORT_BYTES = 8_000_000
SCHEMA = "full-deck-raised-turn-full-physical-v1"
BACKENDS = ("materialized", "matrix-free")
METRICS = oracle.METRICS
WEIGHTED_ROW_OPERATION_CAP = oracle.MAX_WEIGHTED_ROW_OPERATIONS

# These pins cover the independent physical model and every source that supplies
# its cards, tree, terminal reference sign, row legality, or own oracle logic.
SOURCES = tuple(sorted({
    "scripts/audit_raised_turn_full_physical.py",
    "scripts/full_physical_exact_oracle.py",
    "tests/test_raised_turn_full_physical.py",
    "tests/test_full_physical_exact_oracle.py",
    "scripts/full_deck_raised_reference.py",
    "scripts/turn_river_validation.py",
    "scripts/verify_turn_blocker_sequence.py",
    "scripts/turn_blocker_sequence_fixture.py",
    "pokerlab/cards.py",
    "scripts/preflop_validation.py",
}))

COUNTER_FIELDS = (
    "public_nodes", "decision_nodes", "depth", "physical_worlds",
    "physical_runouts", "chance_nodes", "physical_chance_edges",
    "chance_grouping", "policy_rows", "structural_node_visits",
    "weighted_row_operations", "maximum_weighted_row_operations",
    "max_fraction_bits", "independent_showdown_sign_checks",
    "normalization_adjusted_rows",
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _head(root):
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                   text=True).strip()


def _source_fingerprints(root):
    return {name: _sha((root / name).read_bytes().replace(b"\r\n", b"\n"))
            for name in SOURCES}


def _check_committed_sources(root, fingerprints):
    for name, current_hash in fingerprints.items():
        subprocess.check_output(["git", "ls-files", "--error-unmatch", "--", name],
                                cwd=root, text=True, stderr=subprocess.STDOUT)
        committed = subprocess.check_output(["git", "show", f"HEAD:{name}"],
                                            cwd=root)
        _require(_sha(committed.replace(b"\r\n", b"\n")) == current_hash,
                 "A pinned source is not committed at current HEAD: " + name)


def _read_capped(path, cap, label):
    path = Path(path)
    _require(path.stat().st_size <= cap, label + " exceeds pre-read byte cap")
    raw = path.read_bytes()
    _require(len(raw) <= cap, label + " exceeds byte cap")
    return raw


def _file_identity(path):
    stat = Path(path).stat()
    return stat.st_dev, stat.st_ino


def _read_json(raw, label, *, canonical=False):
    _require(b"\r" not in raw, label + " must use LF newlines")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(label + " is not valid JSON") from error
    if canonical:
        _require(_canonical(value) == raw, label + " is not canonical JSON")
    return value


def _report_paths(root):
    results = root / "benchmarks" / "results"
    return {
        "numeric_report": results / "full-deck-raised-turn-tail-v1.json",
        "exact_tail_report": results / "full-deck-raised-turn-tail-exact-v1.json",
        "witness_report": results / "full-deck-raised-turn-clean-witness-v1.json",
        "reference_report": results / "full-deck-raised-turn-reference-v1.json",
    }


def _policy_path(root, family, backend, filename):
    _require(type(filename) is str and Path(filename).name == filename and
             filename.endswith(".json"), "Unsafe policy filename in pinned report")
    base = (root / "benchmarks" / "results" /
            ("full-deck-raised-turn-tail-policies-v1" if family == "tail" else
             "full-deck-raised-turn-clean-witness-policies-v1"))
    expected = (f"full-deck-raised-turn-tail-v1-{backend}-tail.json" if family == "tail"
                else f"full-deck-raised-turn-clean-witness-v1-{backend}.json")
    _require(filename == expected, "Pinned report references an unexpected policy")
    return base / filename


def _load_inputs(root):
    report_paths = _report_paths(root)
    report_pins = {
        "numeric_report": NUMERIC_REPORT_SHA256,
        "exact_tail_report": EXACT_TAIL_REPORT_SHA256,
        "witness_report": WITNESS_REPORT_SHA256,
        "reference_report": REFERENCE_REPORT_SHA256,
    }
    accepted = {}
    reports = {}
    for key, path in report_paths.items():
        raw = _read_capped(path, MAX_INPUT_REPORT_BYTES, key.replace("_", " "))
        _require(_sha(raw) == report_pins[key], "Pinned " + key + " digest differs")
        accepted[str(path.relative_to(root)).replace("\\", "/")] = raw
        reports[key] = _read_json(raw, key, canonical=True)

    numeric = reports["numeric_report"]
    exact = reports["exact_tail_report"]
    witness = reports["witness_report"]
    ref_raw = accepted[str(report_paths["reference_report"].relative_to(root)).replace("\\", "/")]
    _require(type(numeric) is dict and numeric.get("benchmark_id") == "full-deck-raised-turn-tail-v1",
             "Unexpected pinned numeric report")
    _require(type(exact) is dict and exact.get("audit", {}).get("numeric_report_sha256") ==
             NUMERIC_REPORT_SHA256, "Exact-tail report does not bind pinned numeric report")
    _require(type(witness) is dict and witness.get("benchmark_id") ==
             "full-deck-raised-turn-clean-witness-v1" and
             witness.get("exact_tail_report_sha256") == EXACT_TAIL_REPORT_SHA256 and
             witness.get("numeric_tail_report_sha256") == NUMERIC_REPORT_SHA256 and
             witness.get("physical_reference_report_sha256") == REFERENCE_REPORT_SHA256,
             "Clean-witness report does not bind the accepted physical inputs")
    reference.require(_sha(ref_raw) == REFERENCE_REPORT_SHA256,
                      "Physical reference report digest differs")

    exact_rows = exact.get("audit", {}).get("profiles")
    witness_rows = witness.get("results")
    _require(type(exact_rows) is list and type(witness_rows) is list,
             "Pinned exact reports lack profile rows")
    exact_by_backend = {row.get("backend"): row for row in exact_rows
                        if row.get("profile") == "tail"}
    witness_by_backend = {row.get("backend"): row for row in witness_rows}
    _require(set(exact_by_backend) == set(BACKENDS) and
             set(witness_by_backend) == set(BACKENDS),
             "Pinned reports do not contain both supported backends")

    policies = {}
    for backend in BACKENDS:
        for family, row in (("tail", exact_by_backend[backend]),
                            ("witness", witness_by_backend[backend])):
            rel = _policy_path(root, family, backend, row.get("policy_file"))
            raw = _read_capped(rel, MAX_POLICY_BYTES, family + " policy")
            expected_hash = row.get("policy_sha256")
            _require(type(expected_hash) is str and len(expected_hash) == 64 and
                     _sha(raw) == expected_hash,
                     "Pinned " + family + " policy digest differs for " + backend)
            policy = _read_json(raw, family + " policy", canonical=True)
            _require(type(policy) is dict and type(policy.get("strategy")) is list,
                     "Saved policy has unsupported structure")
            path_key = str(rel.relative_to(root)).replace("\\", "/")
            accepted[path_key] = raw
            policies[(family, backend)] = {
                "path": rel, "relative_path": path_key, "raw": raw,
                "policy": policy, "source_report_row": row,
            }
    return {"accepted": accepted, "reports": reports, "policies": policies}


def _guard_inputs(root, accepted):
    for relpath, original in accepted.items():
        path = root / Path(relpath)
        cap = MAX_POLICY_BYTES if "-policies-v1/" in relpath else MAX_INPUT_REPORT_BYTES
        current = _read_capped(path, cap, relpath)
        _require(current == original, "Accepted input changed during physical audit: " + relpath)


def _guard_sources(root, fingerprints, initial_head):
    _require(_head(root) == initial_head, "Physical-audit current HEAD changed")
    current = _source_fingerprints(root)
    changed = sorted(name for name in fingerprints
                     if current.get(name) != fingerprints[name])
    _require(not changed,
             "Pinned physical-audit source changed: " + ", ".join(changed))


def _metric_strings(metrics):
    _require(set(metrics) == set(METRICS), "Oracle did not return all eight exact metrics")
    return {name: str(Fraction(metrics[name])) for name in METRICS}


def _compare_report_metrics(actual, expected, label):
    _require(set(expected) == set(METRICS), label + " report metric set differs")
    for name in METRICS:
        _require(Fraction(actual[name]) == Fraction(expected[name]),
                 label + " exact Fraction differs for " + name)


def _counter_record(counters):
    _require(set(COUNTER_FIELDS) <= set(counters), "Oracle counters are incomplete")
    record = {name: counters[name] for name in COUNTER_FIELDS}
    _require(all(type(record[name]) is int for name in COUNTER_FIELDS
                 if name != "chance_grouping") and
             type(record["chance_grouping"]) is bool,
             "Physical oracle counter types are malformed")
    _require(record["public_nodes"] == 3039 and record["decision_nodes"] == 1254 and
             record["depth"] == 9 and record["physical_worlds"] == 176 and
             record["physical_runouts"] == 48 and record["physical_chance_edges"] ==
             48 * record["chance_nodes"] and record["chance_grouping"] is False and
             record["policy_rows"] == 2404 and record["structural_node_visits"] ==
             6 * 3039 and record["weighted_row_operations"] <=
             WEIGHTED_ROW_OPERATION_CAP and record["max_fraction_bits"] <=
             oracle.MAX_FRACTION_BITS,
             "Physical oracle counters violate fixed declared bounds")
    return record


def _case_record(case, backend, policy_ref, result, expected):
    metrics = _metric_strings(result["metrics"])
    _compare_report_metrics(result["metrics"], expected, case)
    return {
        "case": case,
        "backend": backend,
        "policy_path": policy_ref["relative_path"] if policy_ref else None,
        "policy_sha256": _sha(policy_ref["raw"]) if policy_ref else None,
        "metrics_fraction": metrics,
        "counters": _counter_record(result["counters"]),
    }


def _expected_anchor():
    return {
        "value_oop": Fraction(-2500, 231),
        "value_ip": Fraction(2500, 231),
        "oop_best_response_value": Fraction(2350, 231),
        "ip_best_response_value": Fraction(14975, 231),
        "oop_best_response_gain": Fraction(4850, 231),
        "ip_best_response_gain": Fraction(12475, 231),
        "nash_conv": Fraction(75),
        "exploitability": Fraction(75, 2),
    }


def _preflight_saved_report(root, report):
    """Reject obvious report or counter tampering before full exact replay."""
    _require(type(report) is dict and report.get("schema") == SCHEMA and
             report.get("benchmark_id") == SCHEMA and
             type(report.get("audit_head")) is str and
             len(report["audit_head"]) == 40 and
             all(char in "0123456789abcdef" for char in report["audit_head"]),
             "Unsupported saved physical audit report")
    loaded = _load_inputs(root)
    current_sources = _source_fingerprints(root)
    _require(compatible_exact_source_maps(report.get("source_sha256"), current_sources, root),
             "Saved physical audit source fingerprints differ")
    expected_input_hashes = {
        relpath: _sha(raw) for relpath, raw in loaded["accepted"].items()
        if relpath.endswith(".json") and "policies-v1/" not in relpath
    }
    _require(report.get("input_report_sha256") == expected_input_hashes,
             "Saved physical audit input report pins differ")

    exact = loaded["reports"]["exact_tail_report"]
    witness = loaded["reports"]["witness_report"]
    tails = {row["backend"]: row["certificate"]["metrics"]
             for row in exact["audit"]["profiles"] if row["profile"] == "tail"}
    witnesses = {row["backend"]: row["exact_certificate"]["metrics"]
                 for row in witness["results"]}
    expected_cases = [("handwritten-check-call-anchor", None, _expected_anchor()),
                      ("constructed-single-row-river-control", None, None)]
    for backend in BACKENDS:
        expected_cases.append(("original-saved-numeric-tail", backend, tails[backend]))
        expected_cases.append(("saved-clean-witness", backend, witnesses[backend]))
    cases = report.get("profiles")
    _require(type(cases) is list and len(cases) == len(expected_cases),
             "Saved physical audit profile count differs")
    for case, (name, backend, expected) in zip(cases, expected_cases):
        _require(type(case) is dict and case.get("case") == name and
                 case.get("backend") == backend,
                 "Saved physical audit profile order differs")
        actual = case.get("metrics_fraction")
        _require(type(actual) is dict and set(actual) == set(METRICS),
                 "Saved exact metric map is malformed")
        for metric in METRICS:
            try:
                fraction = Fraction(actual[metric])
            except (TypeError, ValueError, ZeroDivisionError) as error:
                raise ValueError("Saved exact metric Fraction is malformed") from error
            _require(str(fraction) == actual[metric],
                     "Saved exact metric Fraction is not canonical for " + metric)
            if expected is not None:
                _require(fraction == Fraction(expected[metric]),
                         "Saved exact metric differs from pinned report for " + metric)
        if name == "constructed-single-row-river-control":
            _require(actual["value_oop"] == "-4925/462" and
                     case.get("construction", {}).get("value_identity") ==
                     "-2500/231 + 50/308 = -4925/462" and
                     type(case.get("policy_sha256")) is str and
                     len(case["policy_sha256"]) == 64,
                     "Constructed control provenance or value is malformed")
        _counter_record(case.get("counters", {}))
    controls = report.get("controls", {}).get("illegal_future_aware_check_call_control", {})
    _require(controls.get("oop_br_fraction") == "2825/231" and
             controls.get("ip_br_fraction") == "15325/231" and
             controls.get("expected_oop_br_fraction") == "2825/231" and
             controls.get("expected_ip_br_fraction") == "15325/231",
             "Saved future-aware control is malformed")
    return loaded


def _construct_report(root, loaded, fingerprints, generation_head, guard):
    model = reference.model()
    guard()
    cases = []
    anchor_policy = oracle.make_check_call_policy(model)
    guard()
    anchor_result = oracle.audit_policy(anchor_policy, model)
    guard()
    anchor_expected = _expected_anchor()
    _compare_report_metrics(anchor_result["metrics"], anchor_expected, "check-call anchor")
    cases.append({
        "case": "handwritten-check-call-anchor", "backend": None,
        "policy_path": None, "policy_sha256": None,
        "metrics_fraction": _metric_strings(anchor_result["metrics"]),
        "counters": _counter_record(anchor_result["counters"]),
    })

    constructed_policy = deepcopy(anchor_policy)
    changed = [row for row in constructed_policy["strategy"]
               if row["player"] == "ip" and row["hand"] == "KcKd" and
               row["history"] == ["check", "check", "river@2c", "check"]]
    _require(len(changed) == 1, "Constructed control target row is missing or duplicated")
    target_actions = changed[0]["actions"]
    selected = [index for index, action in enumerate(target_actions)
                if action["history_key"] == "bet@50"]
    _require(len(selected) == 1 and any(action["history_key"] == "check"
                                         for action in target_actions),
             "Constructed control does not have the expected check/bet row")
    for index, action in enumerate(target_actions):
        action["probability"] = 1.0 if index == selected[0] else 0.0
    guard()
    constructed_result = oracle.audit_policy(constructed_policy, model)
    guard()
    _require(constructed_result["metrics"]["value_oop"] == Fraction(-4925, 462),
             "Single-row river-control value identity differs")
    constructed_raw = _canonical(constructed_policy)
    cases.append({
        "case": "constructed-single-row-river-control", "backend": None,
        "construction": {
            "player": "ip", "hand": "KcKd",
            "history": ["check", "check", "river@2c", "check"],
            "changed_action": "bet@50",
            "value_identity": "-2500/231 + 50/308 = -4925/462",
        },
        "policy_path": None,
        "policy_sha256": _sha(constructed_raw),
        "metrics_fraction": _metric_strings(constructed_result["metrics"]),
        "counters": _counter_record(constructed_result["counters"]),
    })

    exact_report = loaded["reports"]["exact_tail_report"]
    witness_report = loaded["reports"]["witness_report"]
    exact_rows = {row["backend"]: row for row in exact_report["audit"]["profiles"]
                  if row["profile"] == "tail"}
    witness_rows = {row["backend"]: row for row in witness_report["results"]}
    for backend in BACKENDS:
        tail = loaded["policies"][("tail", backend)]
        guard()
        tail_result = oracle.audit_policy(tail["policy"], model)
        guard()
        _require(tail_result["metrics"]["nash_conv"] > 0,
                 "Original saved numeric tail lost its positive exact gap")
        cases.append(_case_record("original-saved-numeric-tail", backend, tail,
                                  tail_result,
                                  exact_rows[backend]["certificate"]["metrics"]))

        witness = loaded["policies"][("witness", backend)]
        guard()
        witness_result = oracle.audit_policy(witness["policy"], model)
        guard()
        witness_metrics = witness_result["metrics"]
        _require(witness_metrics["value_oop"] == Fraction(-400, 21) and
                 witness_metrics["nash_conv"] == 0 and
                 witness_metrics["exploitability"] == 0 and
                 witness_metrics["oop_best_response_gain"] == 0 and
                 witness_metrics["ip_best_response_gain"] == 0,
                 "Saved clean witness is not exact value -400/21 with zero gap")
        cases.append(_case_record("saved-clean-witness", backend, witness,
                                  witness_result,
                                  witness_rows[backend]["exact_certificate"]["metrics"]))

    guard()
    oop_control = oracle.future_aware_best_response(anchor_policy, model, 0)
    guard()
    ip_control = oracle.future_aware_best_response(anchor_policy, model, 1)
    guard()
    controls = {
        "illegal_future_aware_check_call_control": {
            "oop_br_fraction": str(oop_control),
            "ip_br_fraction": str(ip_control),
            "expected_oop_br_fraction": "2825/231",
            "expected_ip_br_fraction": "15325/231",
        },
    }
    _require(controls["illegal_future_aware_check_call_control"]["oop_br_fraction"] ==
             "2825/231" and
             controls["illegal_future_aware_check_call_control"]["ip_br_fraction"] ==
             "15325/231", "Future-aware negative control anchor differs")
    guard()

    historical_commits = {
        "numeric_report": loaded["reports"]["numeric_report"].get(
            "generation_git_commit"),
        "exact_tail_report": loaded["reports"]["exact_tail_report"].get(
            "generation_git_commit"),
        "numeric_generation_for_exact_tail": loaded["reports"][
            "exact_tail_report"].get("audit", {}).get(
                "numeric_generation_git_commit"),
        "witness_report": loaded["reports"]["witness_report"].get(
            "generation_git_commit"),
        "reference_baseline": loaded["reports"]["reference_report"].get(
            "baseline_git_commit"),
    }
    return {
        "schema": SCHEMA,
        "benchmark_id": SCHEMA,
        "audit_head": generation_head,
        "scope": {
            "fixture": "full-deck-raised-turn-v1",
            "worlds": 176, "physical_runouts": 48,
            "chance_grouping": False,
            "generic_exact_work_cap_changed": False,
        },
        "source_sha256": fingerprints,
        "input_report_sha256": {
            relpath: _sha(raw) for relpath, raw in loaded["accepted"].items()
            if relpath.endswith(".json") and "policies-v1/" not in relpath
        },
        "input_historical_generation_commits": historical_commits,
        "profiles": cases,
        "controls": controls,
    }


def _audit(root, *, generation_head=None, output_path=None, require_committed=True):
    root = Path(root).resolve()
    initial_head = _head(root)
    fingerprints = _source_fingerprints(root)
    if require_committed:
        _check_committed_sources(root, fingerprints)
    loaded = _load_inputs(root)

    def guard():
        _guard_sources(root, fingerprints, initial_head)
        _guard_inputs(root, loaded["accepted"])

    guard()
    report_head = initial_head if generation_head is None else generation_head
    _require(type(report_head) is str and len(report_head) == 40 and
             all(char in "0123456789abcdef" for char in report_head),
             "Invalid audit generation HEAD")
    payload = _construct_report(root, loaded, fingerprints, report_head, guard)
    guard()
    raw = _canonical(payload)
    _require(len(raw) <= MAX_REPORT_BYTES, "Physical audit report exceeds byte cap")
    if output_path is not None:
        _publish(root, Path(output_path), raw, payload, guard)
    return payload


def _publish(root, output_path, raw, payload, guard):
    output_path = Path(output_path)
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staged = output_path.with_name(output_path.name + ".staged")
    stage_owned = published_owned = False
    staged_identity = published_identity = None
    try:
        with staged.open("xb") as stream:
            stage_owned = True
            staged_identity = (os.fstat(stream.fileno()).st_dev,
                               os.fstat(stream.fileno()).st_ino)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        staged_raw = _read_capped(staged, MAX_REPORT_BYTES, "Staged physical report")
        _require(_file_identity(staged) == staged_identity,
                 "Staged physical report file identity changed")
        staged_payload = _read_json(staged_raw, "Staged physical report", canonical=True)
        _require(staged_raw == raw and staged_payload == payload,
                 "Staged physical report reconstruction differs")
        staged_verified = verify_report(staged, root=root)
        _require(staged_verified == payload,
                 "Staged physical report full reconstruction differs")
        _require(_read_capped(staged, MAX_REPORT_BYTES,
                              "Verified staged physical report reread") == raw,
                 "Staged physical report changed after reconstruction")
        guard()
        os.link(staged, output_path)
        published_owned = True
        published_identity = staged_identity
        _require(_file_identity(output_path) == published_identity,
                 "Published report is not the staged file")
        published_raw = _read_capped(output_path, MAX_REPORT_BYTES,
                                     "Published physical report")
        _require(published_raw == raw and _read_json(
            published_raw, "Published physical report", canonical=True) == payload,
            "Published physical report verification differs")
        published_verified = verify_report(output_path, root=root)
        _require(published_verified == payload,
                 "Published physical report full reconstruction differs")
        guard()
        final_raw = _read_capped(output_path, MAX_REPORT_BYTES,
                                 "Final physical report reread")
        _require(final_raw == raw and _read_json(
            final_raw, "Final physical report reread", canonical=True) == payload,
            "Final physical report reread differs")
        guard()
        _require(_file_identity(staged) == staged_identity,
                 "Staged report identity changed before cleanup")
        staged.unlink()
        stage_owned = False
    except BaseException:
        if published_owned and output_path.exists() and \
                _file_identity(output_path) == published_identity:
            output_path.unlink(missing_ok=True)
        if stage_owned and staged.exists() and \
                _file_identity(staged) == staged_identity:
            staged.unlink(missing_ok=True)
        raise


def generate(root=ROOT, output_path=None):
    """Audit six saved/constructed cases and exclusively publish an immutable report."""
    target = REPORT if output_path is None else Path(output_path)
    return _audit(root, output_path=target, require_committed=True)


def verify_report(report_path=REPORT, root=ROOT):
    """Reconstruct an existing report against current pins, allowing historical HEADs."""
    root = Path(root).resolve()
    report_path = Path(report_path)
    if not report_path.is_absolute():
        report_path = root / report_path
    initial_head = _head(root)
    initial_sources = _source_fingerprints(root)
    operation_before = operation_fingerprints(())
    raw = _read_capped(report_path, MAX_REPORT_BYTES, "Physical audit report")
    report = _read_json(raw, "Physical audit report", canonical=True)
    loaded = _preflight_saved_report(root, report)
    expected = _audit(root, generation_head=report["audit_head"],
                       require_committed=True)
    expected["source_sha256"] = report["source_sha256"]
    _require(_canonical(expected) == raw,
             "Saved physical audit report differs from complete reconstruction")
    final_raw = _read_capped(report_path, MAX_REPORT_BYTES,
                             "Final verified physical report reread")
    _require(final_raw == raw,
             "Saved physical audit report changed during reconstruction")
    _guard_sources(root, initial_sources, initial_head)
    _guard_inputs(root, loaded["accepted"])
    _require(operation_fingerprints(()) == operation_before, "Bridge source changed during saved verification")
    return expected


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    result = verify_report(args.report) if args.verify else generate(output_path=args.report)
    print(json.dumps({"report": str(args.report), "profiles": len(result["profiles"]),
                      "audit_head": result["audit_head"]}, sort_keys=True))
