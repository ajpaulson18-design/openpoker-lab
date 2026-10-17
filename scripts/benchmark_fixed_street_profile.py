"""Coarse complete-call profiling for pinned prepared preflop and flop games.

No card ranking or board enumeration is performed. Each case records one
unwrapped serialized reference and three instrumented complete calls. Only the
solver's top-level training and diagnostic calls are timed as coarse phases.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from contextlib import ExitStack, contextmanager, nullcontext
import functools
import gc
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "benchmarks" / "fixed-street-profile-v1.json"
EXPECTED_SPEC_SHA256 = "8b905b854099cfb843e6479ce8ef1277e11e0c2af1ae31d39fd403da554f24b6"


def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _status():
    return _git("status", "--porcelain", "--untracked-files=all").splitlines()


def _source_paths():
    paths = set()
    for directory in (ROOT / "pokerlab", ROOT / "scripts", ROOT / "tests"):
        paths.update(path for path in directory.rglob("*.py") if path.is_file())
    paths.update(path for path in (ROOT / "docs").rglob("*.md") if path.is_file())
    paths.update({
        ROOT / "AGENTS.md",
        ROOT / "benchmarks" / "preflop-pair-mean-v1.json",
        ROOT / "benchmarks" / "flop-equity-reuse-v1.json",
        SPEC_PATH,
    })
    return tuple(sorted(path for path in paths if path.is_file()))


def _source_hashes():
    result = {}
    for path in _source_paths():
        raw = path.read_bytes()
        result[path.relative_to(ROOT).as_posix()] = {
            "raw_sha256": _sha256(raw),
            "lf_sha256": _sha256(raw.replace(b"\r\n", b"\n")),
        }
    return result


def _identity():
    return {"revision": _git("rev-parse", "HEAD"),
            "status": _status(), "source_hashes": _source_hashes()}


def validate_spec(spec):
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise ValueError("Unsupported fixed-street profiling specification")
    if _sha256(_canonical_bytes(spec)) != EXPECTED_SPEC_SHA256:
        raise ValueError("Fixed-street profiling specification hash changed")
    if (spec.get("benchmark_id") != "fixed-street-profile-v1"
            or spec.get("algorithm") != "cfrplus"
            or spec.get("timed_repeats") != 3):
        raise ValueError("Frozen profiling case or repeat count changed")
    pre = spec.get("preflop", {})
    flop = spec.get("flop", {})
    if (pre.get("case_id") != "weighted-three-pairs-pair-mean-3000"
            or pre.get("iterations") != 3000
            or pre.get("resource_model") != "prepared-counts"
            or pre.get("world_indexing") != "pair-mean"
            or pre.get("fixture_id") != "weighted-three-pairs"
            or pre.get("compatible_pairs") != 3 or pre.get("world_rows") != 3):
        raise ValueError("Frozen preflop profile fixture changed")
    if (flop.get("case_id") != "base-8x8-stack24-raises2-cfrplus-4000"
            or flop.get("iterations") != 4000
            or flop.get("compatible_pairs") != 58
            or flop.get("ordered_worlds") != 114840
            or flop.get("exact_prior_normalizer") != "1185/64"):
        raise ValueError("Frozen flop profile fixture changed")
    return spec


def _canonical_result(result):
    encoded = _canonical_bytes(result)
    return encoded, {"serialized_bytes_utf8": len(encoded),
                     "payload_sha256": _sha256(encoded)}


class _PhaseContext:
    """Install non-nested phase wrappers and restore them on every exit."""
    def __init__(self, targets):
        self.targets = targets
        self.totals = {name: 0.0 for name, _, _ in targets}
        self.calls = {name: 0 for name, _, _ in targets}
        self.saved = []
        self.depth = 0

    def __enter__(self):
        try:
            for name, owner, attribute in self.targets:
                original = getattr(owner, attribute)
                self.saved.append((owner, attribute, original))

                @functools.wraps(original)
                def wrapper(*args, __name=name, __original=original, **kwargs):
                    if self.depth:
                        raise AssertionError("Profile phase wrappers unexpectedly nested")
                    self.depth += 1
                    started = perf_counter()
                    try:
                        return __original(*args, **kwargs)
                    finally:
                        self.totals[__name] += perf_counter() - started
                        self.calls[__name] += 1
                        self.depth -= 1

                setattr(owner, attribute, wrapper)
        except BaseException:
            self._restore()
            raise
        return self.totals, self.calls

    def _restore(self):
        for owner, attribute, original in reversed(self.saved):
            setattr(owner, attribute, original)
        self.saved.clear()

    def __exit__(self, exc_type, exc, tb):
        self._restore()
        return False


@contextmanager
def _rank_guard():
    """Fail closed if a timed prepared call tries to rank or enumerate boards."""
    from unittest.mock import patch
    from pokerlab import flop_checkdown_worlds as flop_worlds
    from pokerlab import preflop_full_board_equity as preflop_equity
    from pokerlab.flop_checkdown_worlds import FlopCheckdownPlan

    calls = {"preflop_rank_hand": 0, "preflop_board_combinations": 0,
             "flop_rank_hand": 0, "flop_board_combinations": 0,
             "flop_plan_build": 0}

    def forbidden(name):
        def fail(*args, **kwargs):
            calls[name] += 1
            raise AssertionError("Prepared profiling call attempted forbidden ranking: " + name)
        return fail

    with ExitStack() as stack:
        stack.enter_context(patch.object(preflop_equity, "rank_hand", forbidden("preflop_rank_hand")))
        stack.enter_context(patch.object(preflop_equity, "_board_combinations", forbidden("preflop_board_combinations")))
        stack.enter_context(patch.object(preflop_equity, "combinations", forbidden("preflop_board_combinations")))
        stack.enter_context(patch.object(flop_worlds, "rank_hand", forbidden("flop_rank_hand")))
        stack.enter_context(patch.object(flop_worlds, "combinations", forbidden("flop_board_combinations")))
        stack.enter_context(patch.object(FlopCheckdownPlan, "build", forbidden("flop_plan_build")))
        yield calls


def _profile_one(solver, targets, repeats, *, rank_guard_factory=_rank_guard):
    """Retain a full raw payload and every wrapped call, including failures."""
    def one_call(instrumented):
        gc.collect()
        phase_seconds = {name: 0.0 for name, _, _ in targets}
        phase_calls = {name: 0 for name, _, _ in targets}
        rank_calls = {}
        result = None
        encoded = None
        meta = {}
        error = None
        stack = ExitStack()
        try:
            # Install guards/wrappers outside the complete-call time boundary.
            rank_calls = stack.enter_context(rank_guard_factory())
            if instrumented:
                phase_seconds, phase_calls = stack.enter_context(_PhaseContext(targets))
            started_utc = datetime.now(timezone.utc).isoformat()
            started = perf_counter()
            try:
                result = solver()
                encoded, meta = _canonical_result(result)
                if any(rank_calls.values()):
                    raise AssertionError("Prepared call invoked ranking or board enumeration")
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            elapsed = perf_counter() - started
            ended_utc = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            started_utc = datetime.now(timezone.utc).isoformat()
            ended_utc = started_utc
            elapsed = 0.0
        finally:
            stack.close()
        phase_total = sum(phase_seconds.values())
        if phase_total > elapsed + 1e-12:
            error = error or "Nonoverlapping phase timers exceed complete-call time"
        row = {
            "started_at_utc": started_utc,
            "ended_at_utc": ended_utc,
            "complete_seconds": elapsed,
            "phase_seconds": dict(phase_seconds),
            "phase_calls": dict(phase_calls),
            "rank_guard_calls": dict(rank_calls),
            "uninstrumented_remainder_seconds": max(0.0, elapsed - phase_total),
            **meta,
        }
        if result is not None:
            row["payload"] = result
        if error is not None:
            row["error"] = error
        return row, encoded

    reference, reference_bytes = one_call(False)
    reference.pop("phase_seconds", None)
    reference.pop("phase_calls", None)
    samples = []
    for repeat in range(repeats):
        sample, encoded = one_call(True)
        equal = reference_bytes is not None and encoded == reference_bytes
        sample["repeat"] = repeat + 1
        sample["payload_equal_unwrapped_reference"] = equal
        if sample.get("error") is None and reference_bytes is not None and not equal:
            sample["error"] = "Wrapped serialized payload differs from the unwrapped reference"
        samples.append(sample)
    passed = ("error" not in reference and all("error" not in sample for sample in samples)
              and all(sample["payload_equal_unwrapped_reference"] for sample in samples))
    return {"status": "passed" if passed else "error",
            "unwrapped_reference": reference,
            "samples": samples,
            "wrapped_payloads_equal_unwrapped_reference": passed}


def _load_preflop_table(spec):
    from scripts import benchmark_preflop_pair_mean as pair_mean

    source_spec = json.loads(pair_mean.SPEC.read_text(encoding="utf-8"))
    pair_mean.validate_spec(source_spec)
    if _sha256(_canonical_bytes(source_spec)) != spec["preflop"]["source_spec_sha256"]:
        raise ValueError("Preflop source specification hash differs from fixed profile spec")
    if source_spec["historical_source"]["commit"] != spec["preflop"]["historical_count_source_commit"]:
        raise ValueError("Pinned preflop count source differs from fixed profile spec")
    prepared, provenance = pair_mean.prepare_cases(source_spec)
    matches = [item for item in prepared
               if item["case"]["id"] == spec["preflop"]["fixture_id"]]
    if len(matches) != 1:
        raise ValueError("Pinned preflop weighted-three-pair fixture was not found")
    item = matches[0]
    case = item["case"]
    fixed = spec["preflop"]
    if (case["sb_range"] != fixed["sb_range"] or case["bb_range"] != fixed["bb_range"]
            or case["config"] != fixed["config"] or len(item["table"].pairs) != fixed["compatible_pairs"]):
        raise ValueError("Pinned preflop fixture differs from fixed profile spec")
    item["pinned_provenance"] = provenance
    return item


def _load_flop_table(spec):
    from pokerlab.flop_checkdown_equity import FlopCheckdownEquities
    from pokerlab.flop_checkdown_worlds import prepare_flop_worlds
    from scripts import benchmark_flop_equity_reuse as reuse

    source_spec = json.loads(reuse.SPEC_PATH.read_text(encoding="utf-8"))
    reuse.validate_spec(source_spec)
    fixed = spec["flop"]
    if _sha256(_canonical_bytes(source_spec)) != fixed["source_spec_sha256"]:
        raise ValueError("Flop source specification hash differs from fixed profile spec")
    source = source_spec["historical_count_source"]
    if (source["commit"] != fixed["historical_count_source_commit"]
            or source["path"] != fixed["historical_count_source_path"]
            or source["blob"] != fixed["historical_count_source_blob"]):
        raise ValueError("Pinned flop count source differs from fixed profile spec")
    fixture = next((row for row in source_spec["fixtures"]
                    if row["id"] == "base-8x8-stack24-raises2"), None)
    if fixture is None:
        raise ValueError("Pinned flop fixture was not found")
    oop_range, ip_range = reuse._ranges(source_spec, fixture)
    case = reuse._case(source_spec, fixture)
    if (case["board"] != fixed["board"] or oop_range != fixed["oop_range"]
            or ip_range != fixed["ip_range"] or case["config"] != fixed["config"]):
        raise ValueError("Pinned flop fixture differs from fixed profile spec")
    plan = prepare_flop_worlds(case["board"], oop_range, ip_range)
    historical = reuse._historical_counts()
    by_key = {(row["oop_hand"], row["ip_hand"]): row for row in historical}
    counts = []
    count_rows = []
    expected_keys = set()
    for oop_index, ip_index, _ in plan.pairs:
        key = ("".join(plan.hands[0][oop_index]), "".join(plan.hands[1][ip_index]))
        expected_keys.add(key)
        row = by_key.get(key)
        if row is None or row.get("ordered_outcomes") != 1980:
            raise ValueError("Pinned flop report does not cover a compatible private pair")
        counts.append((row["wins"], row["ties"], row["losses"]))
        count_rows.append({key: row[key] for key in ("oop_hand", "ip_hand", "wins", "ties", "losses", "ordered_outcomes")})
    if expected_keys != set(by_key) or len(counts) != fixed["compatible_pairs"]:
        raise ValueError("Pinned flop count report has missing or extra pair rows")
    table = FlopCheckdownEquities(
        board=tuple(plan.board),
        hands=tuple(tuple(tuple(hand) for hand in player_hands) for player_hands in plan.hands),
        pairs=tuple((i, j, prior) for i, j, prior in plan.pairs),
        counts=tuple(counts),
        _budget_items=tuple(plan.budget.items()),
    )
    table.validate()
    reuse._verify_exact_priors(table, case["board"], oop_range, ip_range, fixed["exact_prior_normalizer"])
    if table.budget["physical_worlds"] != fixed["ordered_worlds"]:
        raise ValueError("Pinned flop table physical-world count changed")
    return {"case": case, "table": table, "counts": count_rows, "pinned_provenance": {
        "commit": source["commit"], "path": source["path"], "blob": source["blob"]}}


def _preflop_targets():
    from pokerlab import cfr
    from pokerlab import preflop_checkdown_solver as solver
    return [("train_cfrplus", solver, "train_cfrplus"),
            ("evaluate", cfr, "evaluate"),
            ("best_response", cfr, "best_response")]


def _flop_targets():
    from pokerlab import flop_checkdown_solver as solver
    return [("train_public_batched", solver, "train_public_batched"),
            ("evaluate_profile", solver, "evaluate_profile")]


def _check_phase_counts(profile, expected):
    if profile["status"] == "passed":
        for sample in profile["samples"]:
            if sample["phase_calls"] != expected:
                sample["error"] = "Unexpected top-level phase call census"
                profile["status"] = "error"
                profile["wrapped_payloads_equal_unwrapped_reference"] = False
                break


def _run_preflop(spec, item):
    from pokerlab.preflop_checkdown_solver import solve_prepared_preflop_checkdown
    from scripts.preflop_checkdown_validation import replay
    fixed = spec["preflop"]

    def solve():
        return solve_prepared_preflop_checkdown(
            item["table"], config=fixed["config"], iterations=fixed["iterations"],
            algorithm=spec["algorithm"], resource_model=fixed["resource_model"],
            world_indexing=fixed["world_indexing"])

    result = _profile_one(solve, _preflop_targets(), spec["timed_repeats"])
    _check_phase_counts(result, {"train_cfrplus": 1, "evaluate": 1, "best_response": 2})
    if result["unwrapped_reference"].get("payload") is None:
        result["independent_replay"] = {"status": "skipped", "reason": "Unwrapped reference call produced no payload"}
    else:
        try:
            checked = replay(result["unwrapped_reference"]["payload"], fixed["sb_range"], fixed["bb_range"],
                             fixed["config"], item["counts"], tolerance=1e-10)
            result["independent_replay"] = {"status": "passed", "metrics": checked}
        except Exception as exc:
            result["independent_replay"] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    result["same_payload_replay_applies_to"] = (["unwrapped_reference"]
        if result["unwrapped_reference"].get("payload") is not None else []) + [
        f"instrumented_sample_{sample['repeat']}" for sample in result["samples"]
        if sample.get("payload_equal_unwrapped_reference")]
    result.update({"fixture_id": fixed["case_id"], "iterations": fixed["iterations"],
                   "algorithm": spec["algorithm"],
                   "compatible_pairs": len(item["table"].pairs),
                   "pinned_count_provenance": item["pinned_provenance"]})
    return result


def _run_flop(spec, item):
    from pokerlab.flop_checkdown_solver import solve_prepared_flop_checkdown
    from scripts.flop_checkdown_validation import prepare_oracle_from_counts, replay
    fixed = spec["flop"]

    def solve():
        return solve_prepared_flop_checkdown(
            item["table"], config=fixed["config"], iterations=fixed["iterations"],
            algorithm=spec["algorithm"])

    result = _profile_one(solve, _flop_targets(), spec["timed_repeats"])
    _check_phase_counts(result, {"train_public_batched": 1, "evaluate_profile": 1})
    if result["unwrapped_reference"].get("payload") is None:
        result["independent_replay"] = {"status": "skipped", "reason": "Unwrapped reference call produced no payload"}
    else:
        try:
            oracle = prepare_oracle_from_counts(fixed["board"], fixed["oop_range"],
                                                fixed["ip_range"], fixed["config"],
                                                item["counts"])
            checked = replay(result["unwrapped_reference"]["payload"], oracle, tolerance=1e-10)
            result["independent_replay"] = {"status": "passed", "metrics": checked}
        except Exception as exc:
            result["independent_replay"] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    result["same_payload_replay_applies_to"] = (["unwrapped_reference"]
        if result["unwrapped_reference"].get("payload") is not None else []) + [
        f"instrumented_sample_{sample['repeat']}" for sample in result["samples"]
        if sample.get("payload_equal_unwrapped_reference")]
    result.update({"fixture_id": fixed["case_id"], "iterations": fixed["iterations"],
                   "algorithm": spec["algorithm"],
                   "compatible_pairs": len(item["table"].pairs),
                   "pinned_count_provenance": item["pinned_provenance"]})
    return result


def run(spec):
    validate_spec(spec)
    before = _identity()
    errors = []
    if before["status"]:
        errors.append("Worktree is not clean at profiling start")
        after = _identity()
        report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
                  "status": "error", "errors": errors,
                  "git_before": before, "git_after": after, "cases": {}}
    else:
        try:
            preflop_table = _load_preflop_table(spec)
            flop_table = _load_flop_table(spec)
            preflop_result = _run_preflop(spec, preflop_table)
            flop_result = _run_flop(spec, flop_table)
            cases = {"preflop": preflop_result, "flop": flop_result}
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            cases = locals().get("cases", {})
            if "preflop_result" in locals():
                cases.setdefault("preflop", preflop_result)
            if "flop_result" in locals():
                cases.setdefault("flop", flop_result)
        after = _identity()
        if before != after:
            errors.append("Source, revision, or worktree status changed during profiling")
        for name, value in cases.items():
            if value.get("status") == "error":
                errors.append(f"{name} wrapped/reference call or phase validation failed")
            if value.get("independent_replay", {}).get("status") == "error":
                errors.append(f"{name} independent replay failed")
        report = {
            "schema_version": 1,
            "benchmark_id": spec["benchmark_id"],
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "specification": spec,
            "spec_sha256": _sha256(_canonical_bytes(spec)),
            "status": "passed" if not errors else "error",
            "errors": errors,
            "git_before": before,
            "git_after": after,
            "runtime": {"python": sys.version, "executable": sys.executable,
                        "platform": platform.platform()},
            "method": {
                "complete_call": "Prepared solver invocation, canonical JSON UTF-8 encoding, and SHA-256 payload hashing, inclusive.",
                "phase_timing": "Top-level training and diagnostic function wrappers only; wrapper and rank-guard installation is outside complete-call timing and restored in finally. Phase intervals are checked as non-nested and non-overlapping; remainder includes other solver work, serialization, and hashing.",
                "warm_calls": "One unwrapped serialized reference followed by three instrumented complete calls per fixture; all call times, phase observations, UTC boundaries, payload hashes and raw payloads are retained.",
                "physical_counts": "Pinned validated Git artifacts only. Each reference and instrumented call is guarded against ranking and board enumeration. Independent numeric-rule replay uses pinned rows outside all timed calls.",
                "limitations": "Two fixed prepared cases, one Python runtime, and coarse instrumented timings; no general speed, native, allocation, or RSS claim.",
            },
            "cases": cases,
        }
    report["artifact_sha256"] = _sha256(_canonical_bytes(report))
    return report


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(data + b"\n")
    temp.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        help="Optional report file; defaults to canonical JSON on stdout")
    args = parser.parse_args(argv)
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    report = run(spec)
    rendered = json.dumps(report, indent=2, allow_nan=False).encode("utf-8")
    if args.output:
        _atomic_write(args.output, rendered)
    else:
        sys.stdout.buffer.write(rendered + b"\n")
    if report.get("status") != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
