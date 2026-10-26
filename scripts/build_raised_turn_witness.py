"""Research-only exact-zero witnesses from fixed raised-turn numeric tail policies.

No training occurs. Both accepted input reports are pinned before publication.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from scripts.historical_turn_sources import OPERATION_INPUTS, compatible_source_maps
import argparse
import json
import math
import os
from pathlib import Path
import tempfile

from scripts import audit_full_deck_raised_exact as exact_audit
from scripts import benchmark_turn_tail as numeric_tail
from scripts import full_deck_raised_reference as reference
from scripts.turn_river_validation import replay_policy

TAU = 1e-12
TARGET = Fraction(1, 1000)
NUMERIC_REPORT_SHA256 = "9e51cbcf9f031f371806be06e6a23589e0dd27d5e3ffffcf36fc545eed5d6998"
EXACT_TAIL_REPORT_SHA256 = "f4901675fcb026fbac6713baf604650fd48f510c5ae4dc6be2c776c0a780c0c7"
REFERENCE_REPORT_SHA256 = exact_audit.REFERENCE_SHA256
MAX_POLICY_BYTES = 2_000_000
MAX_REPORT_BYTES = 8_000_000
BACKENDS = ("materialized", "matrix-free")
POLICY_NAMES = {
    backend: f"full-deck-raised-turn-clean-witness-v1-{backend}.json"
    for backend in BACKENDS
}
REPORT = reference.ROOT / "benchmarks/results/full-deck-raised-turn-clean-witness-v1.json"
EXACT_TAIL_REPORT = reference.ROOT / "benchmarks/results/full-deck-raised-turn-tail-exact-v1.json"
POLICIES_DIR = reference.ROOT / "benchmarks/results/full-deck-raised-turn-clean-witness-policies-v1"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def sha(raw):
    return sha256(raw).hexdigest()


def capped(path, limit, label):
    path = Path(path)
    require(path.stat().st_size <= limit, f"{label} exceeds pre-read byte cap")
    raw = path.read_bytes()
    require(len(raw) <= limit, f"{label} grew beyond byte cap")
    return raw


def fraction_json(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {str(k): fraction_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [fraction_json(v) for v in value]
    return value


def cleanup_policy(source, *, tau=TAU):
    """Deep-copy and threshold a complete policy in stable action order."""
    require(type(tau) in (int, float) and math.isfinite(tau) and 0 < tau < 0.5,
            "Invalid cleanup threshold")
    candidate = deepcopy(source)
    require(type(candidate) is dict and type(candidate.get("strategy")) is list,
            "Policy has no complete strategy list")
    changes = []
    changed_rows = 0
    changed_actions = 0
    max_abs_delta = 0.0
    for row_index, row in enumerate(candidate["strategy"]):
        require(type(row) is dict and type(row.get("actions")) is list and row["actions"],
                "Malformed strategy row")
        row_changes = []
        raw = []
        for action in row["actions"]:
            p = action.get("probability")
            require(type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1,
                    "Invalid source action probability")
            raw.append(float(p))
        thresholded = [0.0 if p <= tau else (1.0 if p >= 1.0 - tau else p) for p in raw]
        total = math.fsum(thresholded)
        require(total > 0 and math.isfinite(total), "Cleanup produced a zero-sum row")
        normalized = [p / total for p in thresholded]
        for action_index, (action, before, after) in enumerate(zip(row["actions"], raw, normalized)):
            if before != after:
                delta = abs(after - before)
                changed_actions += 1
                max_abs_delta = max(max_abs_delta, delta)
                row_changes.append({
                    "action_index": action_index,
                    "history_key": action.get("history_key"),
                    "name": action.get("name"),
                    "before_hex": before.hex(),
                    "after_hex": after.hex(),
                    "absolute_delta_hex": delta.hex(),
                })
            action["probability"] = after
        if row_changes:
            changed_rows += 1
            changes.append({
                "row_index": row_index,
                "street": row.get("street"),
                "board": deepcopy(row.get("board")),
                "hand": row.get("hand"),
                "history": deepcopy(row.get("history")),
                "player": row.get("player"),
                "actions": row_changes,
            })
    return candidate, {
        "tau": tau,
        "method": "set p<=tau to 0; set p>=1-tau to 1; normalize remaining in original action order",
        "rows_total": len(candidate["strategy"]),
        "rows_changed": changed_rows,
        "actions_changed": changed_actions,
        "max_absolute_probability_change_hex": max_abs_delta.hex(),
        "changed_actions": changes,
    }


def _source_files():
    paths = set(exact_audit.SOURCES) | set(numeric_tail.REQUIRED_SOURCES)
    paths.update(OPERATION_INPUTS)
    paths.update({"scripts/build_raised_turn_witness.py",
                  "tests/test_build_raised_turn_witness.py"})
    files = {name: reference.ROOT / name for name in sorted(paths)}
    files["scripts/build_raised_turn_witness.py"] = Path(__file__)
    draft_tests = Path(__file__).resolve().parents[1] / "tests/test_build_raised_turn_witness.py"
    files["tests/test_build_raised_turn_witness.py"] = draft_tests
    return files


def source_map():
    return {name: sha(path.read_bytes().replace(b"\r\n", b"\n"))
            for name, path in _source_files().items()}


def current_head():
    return reference.head()


def _guards(sources, head, report_raw, input_raws, reference_raw, exact_raw):
    require(source_map() == sources and current_head() == head,
            "Source files or Git HEAD changed during witness operation")
    if report_raw is not None:
        require(capped(numeric_tail.REPORT, MAX_REPORT_BYTES, "Numeric tail report") == report_raw,
                "Numeric tail report changed during witness operation")
    if input_raws:
        for backend, raw in input_raws.items():
            path = numeric_tail.POLICIES_DIR / _numeric_policy_name(backend)
            require(capped(path, MAX_POLICY_BYTES, f"{backend} input policy") == raw,
                    f"{backend} input policy changed during witness operation")
    if reference_raw is not None:
        require(capped(exact_audit.reference.REPORT, exact_audit.reference.MAX_REPORT_BYTES,
                       "Accepted physical reference") == reference_raw,
                "Accepted physical reference changed during witness operation")
    if exact_raw is not None:
        require(capped(EXACT_TAIL_REPORT, MAX_REPORT_BYTES, "Accepted exact tail report") == exact_raw,
                "Accepted exact tail report changed during witness operation")


def _numeric_policy_name(backend):
    return f"full-deck-raised-turn-tail-v1-{backend}-tail.json"


def _check_pins():
    require(type(NUMERIC_REPORT_SHA256) is str and len(NUMERIC_REPORT_SHA256) == 64,
            "Refusing witness operation: numeric tail report SHA-256 pin is empty")
    require(all(c in "0123456789abcdef" for c in NUMERIC_REPORT_SHA256),
            "Invalid numeric tail report SHA-256 pin")
    require(type(EXACT_TAIL_REPORT_SHA256) is str and len(EXACT_TAIL_REPORT_SHA256) == 64,
            "Refusing witness operation: accepted exact tail report SHA-256 pin is empty")
    require(all(c in "0123456789abcdef" for c in EXACT_TAIL_REPORT_SHA256),
            "Invalid exact tail report SHA-256 pin")


def _load_inputs():
    _check_pins()
    report_raw = capped(numeric_tail.REPORT, MAX_REPORT_BYTES, "Numeric tail report")
    require(sha(report_raw) == NUMERIC_REPORT_SHA256,
            "Numeric tail report does not match the declared SHA-256 pin")
    report = json.loads(report_raw)
    require(report.get("benchmark_id") == "full-deck-raised-turn-tail-v1" and
            report.get("schema_version") == 1,
            "Unexpected numeric tail report identity")
    reference_raw = capped(exact_audit.reference.REPORT,
                           exact_audit.reference.MAX_REPORT_BYTES, "Accepted physical reference")
    require(sha(reference_raw) == REFERENCE_REPORT_SHA256,
            "Accepted physical reference report SHA-256 mismatch")
    tail_rows = [row for row in report.get("results", []) if row.get("profile") == "tail"]
    rows = {row.get("backend"): row for row in tail_rows}
    require(len(tail_rows) == 2 and len(rows) == 2 and set(rows) == set(BACKENDS),
            "Numeric report lacks exactly the two tail inputs")
    inputs = {}
    raws = {}
    for backend in BACKENDS:
        row = rows[backend]
        filename = _numeric_policy_name(backend)
        require(row.get("policy_file") == filename and row.get("iterations_completed") == 1500,
                f"Unexpected {backend} numeric tail profile identity")
        raw = capped(numeric_tail.POLICIES_DIR / filename, MAX_POLICY_BYTES,
                     f"{backend} input policy")
        require(sha(raw) == row.get("policy_sha256"), f"{backend} input policy hash mismatch")
        inputs[backend] = json.loads(raw)
        raws[backend] = raw
    exact_raw = capped(EXACT_TAIL_REPORT, MAX_REPORT_BYTES, "Accepted exact tail report")
    require(sha(exact_raw) == EXACT_TAIL_REPORT_SHA256,
            "Accepted exact tail report SHA-256 mismatch")
    return report_raw, report, inputs, raws, reference_raw, exact_raw


def _derived_candidate(backend, source, source_hash):
    candidate, ledger = cleanup_policy(source)
    clean_metrics = replay_policy(candidate, reference.FIXTURE["oop"], reference.FIXTURE["ip"],
                                  board=reference.rules.cards(reference.FIXTURE["board"]),
                                  config=reference.rules._config(reference.FIXTURE["config"], "config"))
    for metric in reference.METRICS:
        candidate[metric] = clean_metrics[metric]
    candidate['solver_version'] = 'research-raised-turn-clean-witness-v1'
    candidate['source_solver_version'] = source.get('solver_version')
    candidate['source_average_schedule'] = source.get('average_schedule')
    candidate['average_schedule'] = 'derived-cleaned-linear-tail-own-realization'
    candidate['source_research_profile'] = source.get('research_profile')
    candidate['research_profile'] = 'clean-witness'
    candidate['method'] = 'Deterministic cleanup of a frozen tail; exact normalized fixed-game certificate required'
    candidate['scope'] = 'Research witness for the fixed 176-world raised turn/river game'
    candidate["diagnostic_provenance"] = (
        "Research-only derived cleanup of a complete accepted numeric tail policy; "
        "all numeric metrics recomputed by full-physical independent rules replay; "
        "not production trainer output or a general rounding guarantee."
    )
    candidate["derived_provenance"] = {
        "schema": "full-deck-raised-turn-clean-witness-v1",
        "backend": backend,
        "source_policy_sha256": source_hash,
        "source_solver_version": source.get('solver_version'),
        "production_solver_version": source.get('source_solver_version'),
        "tau": TAU,
        "threshold_method": ledger["method"],
        "exact_zero_required": True,
        "training_calls": 0,
    }
    return candidate, ledger, clean_metrics


def _exact_zero(audit_result):
    gap = audit_result["certificate"]["metrics"]["nash_conv"]
    require(type(gap) is Fraction and gap == 0,
            "Cleaned candidate failed the required exact NashConv == 0 audit")


def _valid_commit(value):
    return type(value) is str and len(value) == 40 and all(c in "0123456789abcdef" for c in value)


def _compare_numeric_observations(saved, expected):
    def compare(actual, wanted, path):
        if type(actual) is dict and type(wanted) is dict:
            require(set(actual) == set(wanted), f"Saved numeric replay fields differ: {path}")
            for key in wanted:
                compare(actual[key], wanted[key], f"{path}.{key}")
        elif type(actual) is list and type(wanted) is list:
            require(len(actual) == len(wanted), f"Saved numeric replay list differs: {path}")
            for index, (left, right) in enumerate(zip(actual, wanted)):
                compare(left, right, f"{path}[{index}]")
        elif type(actual) in (int, float) and type(wanted) in (int, float):
            require(math.isfinite(actual) and math.isfinite(wanted) and
                    abs(actual - wanted) <= 1e-12,
                    f"Saved numeric replay observation differs: {path}")
        else:
            require(type(actual) is type(wanted) and actual == wanted,
                    f"Saved numeric replay observation differs: {path}")
    compare(saved, expected, "metrics")


def _compare_policy_observations(saved, expected):
    require(type(saved) is dict and type(expected) is dict and set(saved) == set(expected),
            "Saved witness policy fields differ")
    left, right = deepcopy(saved), deepcopy(expected)
    for metric in reference.METRICS:
        actual, wanted = left.pop(metric), right.pop(metric)
        require(type(actual) in (int, float) and math.isfinite(actual) and
                type(wanted) in (int, float) and math.isfinite(wanted) and
                abs(actual - wanted) <= 1e-12,
                f"Saved witness policy numeric observation differs: {metric}")
    require(canonical(left) == canonical(right),
            "Saved witness policy strategy, probabilities, or metadata differ")


def _compare_report(saved, expected):
    require(type(saved) is dict and type(expected) is dict and set(saved) == set(expected),
            "Saved witness report fields differ")
    left, right = deepcopy(saved), deepcopy(expected)
    require(compatible_source_maps(left.get("source_sha256"), right.get("source_sha256")),
            "Saved witness source differs from authenticated historical transition")
    # Preserve historical source identities in the immutable saved report.
    right["source_sha256"] = left["source_sha256"]
    require(type(left.get("results")) is list and type(right.get("results")) is list and
            len(left["results"]) == len(right["results"]) == len(BACKENDS),
            "Saved witness report profile count differs")
    for actual_row, wanted_row in zip(left["results"], right["results"]):
        require(type(actual_row) is dict and type(wanted_row) is dict and
                set(actual_row) == set(wanted_row), "Saved witness profile fields differ")
        _compare_numeric_observations(actual_row["full_physical_numeric_metrics"],
                                      wanted_row["full_physical_numeric_metrics"])
        actual_hash = actual_row.get("policy_sha256")
        require(type(actual_hash) is str and len(actual_hash) == 64 and
                all(c in "0123456789abcdef" for c in actual_hash),
                "Saved witness policy hash is invalid")
        # The raw saved policy is checked against this hash. Its metrics may
        # vary by a few binary64 ulps across runtimes, so only this observation
        # field is excluded from reconstructed-report byte equality.
        wanted_row["policy_sha256"] = actual_hash
    for index, actual_row in enumerate(left["results"]):
        wanted_row = right["results"][index]
        _compare_numeric_observations(actual_row["full_physical_numeric_metrics"],
                                      wanted_row["full_physical_numeric_metrics"])
        actual_row["full_physical_numeric_metrics"] = wanted_row["full_physical_numeric_metrics"]
    require(canonical(left) == canonical(right),
            "Saved witness report differs from strict reconstruction")


def _verify_observed_policy_bytes(policy_paths, observed):
    for name, previous in observed.items():
        current = capped(Path(policy_paths[name]), MAX_POLICY_BYTES, "Witness policy final reread")
        require(current == previous, f"Witness policy changed after verification: {name}")


def _reconstruct(*, generation_git_commit=None):
    sources, head = source_map(), current_head()
    generation_git_commit = head if generation_git_commit is None else generation_git_commit
    require(type(generation_git_commit) is str and len(generation_git_commit) == 40 and
            all(c in "0123456789abcdef" for c in generation_git_commit),
            "Invalid historical witness generation commit")
    report_raw, numeric_report, input_policies, input_raws, reference_raw, exact_raw = _load_inputs()
    _guards(sources, head, report_raw, input_raws, reference_raw, exact_raw)
    results = []
    policy_bytes = {}
    for backend in BACKENDS:
        _guards(sources, head, report_raw, input_raws, reference_raw, exact_raw)
        source = input_policies[backend]
        source_hash = sha(input_raws[backend])
        candidate, change_ledger, replay_metrics = _derived_candidate(backend, source, source_hash)
        # Full physical independent replay is repeated in the unchanged exact auditor.
        audit = exact_audit.audit_policy(candidate)
        _exact_zero(audit)
        policy_name = POLICY_NAMES[backend]
        payload = canonical(candidate)
        require(len(payload) <= MAX_POLICY_BYTES, f"{backend} witness policy exceeds byte cap")
        policy_bytes[policy_name] = payload
        certificate = fraction_json(audit["certificate"])
        results.append({
            "backend": backend,
            "source_policy_file": _numeric_policy_name(backend),
            "source_policy_sha256": source_hash,
            "policy_file": policy_name,
            "policy_sha256": sha(payload),
            "cleanup": change_ledger,
            "full_physical_numeric_metrics": {
                name: replay_metrics[name] for name in reference.METRICS
            },
            "physical_worlds": audit["physical_worlds"],
            "physical_rows": audit["physical_rows"],
            "quotient_worlds": audit["quotient_worlds"],
            "quotient_rows": audit["quotient_rows"],
            "exact_certificate": certificate,
            "canonical_normalized_rows": certificate["normalization_ledger"],
            "exact_nash_conv": certificate["metrics"]["nash_conv"],
            "threshold_fraction": str(TARGET),
            "threshold_met": True,
        })
        _guards(sources, head, report_raw, input_raws, reference_raw, exact_raw)
    require({row["backend"] for row in results} == set(BACKENDS),
            "Witness report does not contain both fixed backends")
    report = {
        "schema_version": 1,
        "benchmark_id": "full-deck-raised-turn-clean-witness-v1",
        "generation_git_commit": generation_git_commit,
        "source_sha256": sources,
        "numeric_tail_report_sha256": sha(report_raw),
        "physical_reference_report_sha256": sha(reference_raw),
        "exact_tail_report_sha256": sha(exact_raw) if exact_raw is not None else None,
        "fixture_id": reference.FIXTURE["id"],
        "tau": TAU,
        "target_fraction": str(TARGET),
        "training_calls": 0,
        "scope": "Exact zero applies only to the explicitly normalized binary64 candidates on this fixed 176-world game; no general rounding guarantee or production/default recommendation.",
        "work_limits": {
            "exact_work": 100_000,
            "tree_depth": 64,
            "fraction_bits": 65_536,
            "full_numeric_worlds": reference.rules.MAX_WORLD_COUNT,
            "full_numeric_oracle_work": reference.rules.MAX_ORACLE_WORK,
            "observed_physical_worlds": 176,
            "observed_physical_rows": 2404,
            "preparation": "Full-physical validation/replay and quotient preparation remain separately bounded by the unchanged auditor and numeric-validation envelopes.",
        },
        "numeric_tail_report_identity": numeric_report.get("benchmark_id"),
        "results": results,
    }
    _guards(sources, head, report_raw, input_raws, reference_raw, exact_raw)
    return canonical(report), policy_bytes


def verify_saved(report_path=REPORT, policies_dir=POLICIES_DIR):
    _check_pins()
    report_path, policies_dir = Path(report_path), Path(policies_dir)
    paths = {name: policies_dir / name for name in POLICY_NAMES.values()}
    return verify_bundle(report_path, paths)


def verify_bundle(report_path, policy_paths):
    """No-training reconstruction check for staged or published bundle files."""
    _check_pins()
    sources, head = source_map(), current_head()
    numeric_raw, _, _, input_raws, reference_raw, exact_raw = _load_inputs()
    raw_report = capped(report_path, MAX_REPORT_BYTES, "Witness report")
    saved = json.loads(raw_report)
    require(canonical(saved) == raw_report, "Witness report is not canonical JSON")
    generation = saved.get("generation_git_commit")
    require(_valid_commit(generation), "Invalid historical witness generation commit")
    expected_report, policy_bytes = _reconstruct(generation_git_commit=generation)
    expected = json.loads(expected_report)
    observed = {}
    saved_rows = {row.get("backend"): row for row in saved.get("results", [])
                  if type(row) is dict}
    expected_rows = {row.get("backend"): row for row in expected.get("results", [])}
    require(set(saved_rows) == set(BACKENDS) and set(expected_rows) == set(BACKENDS),
            "Saved witness report backend set differs")
    for name, rebuilt_bytes in policy_bytes.items():
        require(name in policy_paths, "Witness policy path map is incomplete")
        raw = capped(Path(policy_paths[name]), MAX_POLICY_BYTES, "Witness policy")
        backend = next((key for key, output_name in POLICY_NAMES.items() if output_name == name), None)
        require(backend in BACKENDS, "Unexpected witness policy filename")
        row = saved_rows[backend]
        require(row.get("policy_file") == name and sha(raw) == row.get("policy_sha256"),
                f"Saved witness policy byte hash differs: {name}")
        saved_policy = json.loads(raw)
        require(canonical(saved_policy) == raw, f"Saved witness policy is not canonical JSON: {name}")
        rebuilt_policy = json.loads(rebuilt_bytes)
        _compare_policy_observations(saved_policy, rebuilt_policy)
        audited = exact_audit.audit_policy(saved_policy)
        _exact_zero(audited)
        certificate = fraction_json(audited["certificate"])
        require(canonical(certificate) == canonical(row.get("exact_certificate")) and
                canonical(certificate["normalization_ledger"]) ==
                canonical(row.get("canonical_normalized_rows")),
                f"Saved exact certificate or normalized-row ledger differs: {name}")
        require(row.get("exact_nash_conv") == certificate["metrics"]["nash_conv"] and
                row.get("threshold_met") is True,
                f"Saved exact threshold observation differs: {name}")
        report_metrics = row.get("full_physical_numeric_metrics")
        _compare_numeric_observations(
            {metric: report_metrics[metric] for metric in reference.METRICS},
            audited["full_numeric_metrics"])
        _compare_numeric_observations({metric: saved_policy[metric] for metric in reference.METRICS},
                                      audited["full_numeric_metrics"])
        observed[name] = raw
        _guards(sources, head, numeric_raw, input_raws, reference_raw, exact_raw)
    _compare_report(saved, expected)
    _verify_observed_policy_bytes(policy_paths, observed)
    require(capped(report_path, MAX_REPORT_BYTES, "Witness report") == raw_report,
            "Witness report changed during verification")
    _guards(sources, head, numeric_raw, input_raws, reference_raw, exact_raw)
    _verify_observed_policy_bytes(policy_paths, observed)
    return {"status": "VERIFIED_RAISED_TURN_CLEAN_WITNESSES", "training_calls": 0,
            "profiles": len(observed), "report_sha256": sha(raw_report)}


def generate(report_path=REPORT, policies_dir=POLICIES_DIR):
    _check_pins()
    report_path, policies_dir = Path(report_path), Path(policies_dir)
    if report_path.exists():
        return verify_saved(report_path, policies_dir)
    expected_report, policy_bytes = _reconstruct()
    require(len(expected_report) <= MAX_REPORT_BYTES, "Witness report exceeds byte cap")
    require(not any((policies_dir / name).exists() for name in policy_bytes),
            "Refusing partial or conflicting immutable witness policy set")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    policies_dir.mkdir(parents=True, exist_ok=True)
    created = []
    staged = []
    try:
        for name, payload in policy_bytes.items():
            fd, temp = tempfile.mkstemp(prefix=".raised-witness-", suffix=".candidate", dir=policies_dir)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            staged.append((Path(temp), policies_dir / name))
        fd, temp_report = tempfile.mkstemp(prefix=".raised-witness-", suffix=".candidate", dir=report_path.parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(expected_report)
            stream.flush()
            os.fsync(stream.fileno())
        staged_report = Path(temp_report)
        # Reconstruct and validate staged content before publishing immutable names.
        for temp, target in staged:
            require(capped(temp, MAX_POLICY_BYTES, "Staged witness policy") == policy_bytes[target.name],
                    "Staged witness policy differs")
        require(capped(staged_report, MAX_REPORT_BYTES, "Staged witness report") == expected_report,
                "Staged witness report differs")
        # Reconstruct from the accepted input bytes again before publishing names.
        verify_bundle(staged_report, {target.name: temp for temp, target in staged})
        for temp, target in staged:
            os.link(temp, target)
            created.append(target)
        os.link(staged_report, report_path)
        created.append(report_path)
        return verify_saved(report_path, policies_dir)
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    finally:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)
        if "staged_report" in locals():
            staged_report.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--generate", action="store_true")
    commands.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = generate() if args.generate else verify_saved()
    print(json.dumps(result, sort_keys=True, allow_nan=False))
