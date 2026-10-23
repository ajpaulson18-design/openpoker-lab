"""Compatibility adapter for the stopped second-board CFR+ pilot.

This wrapper preserves the v1 solver and its source files. It validates and
retains the full numeric-replay receipt, then supplies the eight metric fields
that the v1 adapter expects from its replay boundary.
"""
import hashlib
import importlib
import math
from pathlib import Path

from scripts import flop_second_board_cfrplus as v1
from scripts import flop_second_board_equivalence as proof


ROOT = v1.ROOT
VERSION = "fixed-second-board-cfrplus-replay-v2"
MAX_SOURCE_BYTES = v1.MAX_SOURCE_BYTES
EXPECTED_COUNTS = {
    "checked_information_sets": 16_912,
    "checked_physical_worlds": 5_940,
    "checked_public_nodes": 9_512,
    "checked_public_states": 30_812,
}
REPLAY_EXTRA = (
    ("scripts/verify_flop_second_board_cfrplus_failure_publication.py",
     ROOT / "scripts/verify_flop_second_board_cfrplus_failure_publication.py"),
    ("scripts/flop_second_board_cfrplus_replay_v2.py", Path(__file__)),
    ("scripts/benchmark_flop_second_board_cfrplus_replay_v2.py",
     ROOT / "scripts/benchmark_flop_second_board_cfrplus_replay_v2.py"),
    ("benchmarks/flop-second-board-cfrplus-replay-v2.json",
     ROOT / "benchmarks/flop-second-board-cfrplus-replay-v2.json"),
)


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _source_snapshot():
    """Extend the authenticated v1 inventory with four separately versioned files."""
    state = v1._source_snapshot()
    hashes = dict(state["source_lf_sha256"])
    _need(len(hashes) == 54 and state.get("status") == "",
          "Inherited v1 source inventory is dirty or incomplete")
    for relative, path in REPLAY_EXTRA:
        _need(relative not in hashes and not path.is_symlink(),
              f"Duplicate or symlinked v2 source: {relative}")
        _need(path.stat().st_size <= MAX_SOURCE_BYTES,
              f"V2 source exceeds byte bound: {relative}")
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        _need(len(raw) <= MAX_SOURCE_BYTES,
              f"V2 source exceeded read bound: {relative}")
        hashes[relative] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    _need(len(hashes) == 58, "V2 source inventory differs")
    return {**state, "source_lf_sha256": dict(sorted(hashes.items()))}


def source_hashes():
    return dict(_source_snapshot()["source_lf_sha256"])


def admit_request(iterations=560):
    """Expose the identical v1 work admission with a versioned replay contract."""
    forecast = v1.admit_request(iterations)
    result = dict(forecast)
    result["adapter_version"] = VERSION
    result["numeric_replay_contract"] = {
        "metric_keys": list(proof.METRICS),
        "scalar_absolute_gaps_max": 1e-10,
        "counts": dict(EXPECTED_COUNTS),
        "raw_result_key_count": len(proof.METRICS) + 1 + len(EXPECTED_COUNTS),
        "interpretation": "Strict saved numeric-replay receipt; no additional game or speed claim.",
    }
    return result


def _validate_replay_result(raw, observation):
    """Retain before validating; return the legacy-compatible metric projection."""
    observation["numeric_replay_raw"] = raw
    expected_keys = set(proof.METRICS) | {"scalar_absolute_gaps"} | set(EXPECTED_COUNTS)
    _need(type(raw) is dict and set(raw) == expected_keys and len(raw) == 13,
          "Numeric replay result must contain exactly the 13 v2 fields")
    metrics = {key: raw[key] for key in proof.METRICS}
    _need(all(type(value) is float and math.isfinite(value) for value in metrics.values()),
          "Numeric replay metric values must be finite exact floats")
    gaps = raw["scalar_absolute_gaps"]
    _need(type(gaps) is dict and set(gaps) == set(proof.METRICS) and
          all(type(value) is float and math.isfinite(value) and 0 <= value <= 1e-10
              for value in gaps.values()),
          "Numeric replay scalar gaps must be finite and within tolerance")
    for key, expected in EXPECTED_COUNTS.items():
        _need(type(raw[key]) is int and raw[key] == expected,
              f"Numeric replay count differs: {key}")
    receipt = {"numeric_metrics": metrics, "scalar_absolute_gaps": dict(gaps),
               "counts": dict(EXPECTED_COUNTS), "raw_result_key_count": 13}
    observation["numeric_replay_receipt"] = receipt
    return metrics


def _failure_publication_receipt():
    """Authenticate the immutable stopped v1 run before invoking its solver."""
    module = importlib.import_module(
        "scripts.verify_flop_second_board_cfrplus_failure_publication")
    return module.verify()


def solve_second_board(iterations=560, *, observation=None):
    """Run one v1 call with a reversible, strict compatibility replay boundary."""
    if observation is None:
        observation = {}
    _need(type(observation) is dict, "Observation must be an exact dict")
    observation.clear()
    observation.update(status="running", phase="v2-admission", primary_error=None)
    before = after = None
    admission = None
    publication_receipt = None
    numeric_raw = None
    original_replay = proof.physical.replay
    wrapped_replay_calls = 0
    result = None
    primary = None
    v1_call_count = 0
    v1_observation = {}
    try:
        admission = admit_request(iterations)
        observation["v2_admission"] = admission
        before = _source_snapshot()
        observation["v2_source_before"] = before
        publication_receipt = _failure_publication_receipt()
        observation["v1_failure_publication_receipt"] = publication_receipt

        def replay_compat(*args, **kwargs):
            nonlocal numeric_raw, wrapped_replay_calls
            wrapped_replay_calls += 1
            _need(wrapped_replay_calls == 1,
                  "V2 adapter permits exactly one numeric replay per call")
            raw = original_replay(*args, **kwargs)
            numeric_raw = raw
            v1_observation["numeric_replay_raw"] = raw
            return _validate_replay_result(raw, v1_observation)

        # Patching the function object used by v1 composes with the outer
        # harness's counting wrapper when one is already installed.
        from unittest.mock import patch
        with patch.object(proof.physical, "replay", replay_compat):
            v1_call_count += 1
            result = v1.solve_second_board(iterations, observation=v1_observation)
        _need(wrapped_replay_calls == 1, "V1 adapter did not invoke numeric replay once")
        v1_report = result
        report = dict(v1_report)
        old_sources = report.get("source_lf_sha256")
        _need(type(old_sources) is dict and len(old_sources) == 54 and
              all(path in before["source_lf_sha256"] and
                  before["source_lf_sha256"][path] == digest
                  for path, digest in old_sources.items()) and
              report.get("source_revision") == before["revision"],
              "Wrapped v1 source receipt differs from the admitted 54-source subset")
        old_digest = report.pop("artifact_sha256", None)
        report.update({
            "schema_version": VERSION,
            "wrapped_v1_artifact_sha256": old_digest,
            "wrapped_v1_source_lf_sha256": dict(v1_report["source_lf_sha256"]),
            "source_lf_sha256": dict(before["source_lf_sha256"]),
            "v1_failure_publication_receipt": publication_receipt,
            "numeric_replay_raw_receipt": numeric_raw,
            "numeric_replay_v2_receipt": v1_observation["numeric_replay_receipt"],
        })
        report["artifact_sha256"] = proof._digest(report)
        observation["v2_report"] = report
        observation["status"] = "complete"
        observation["phase"] = "complete"
        return report
    except BaseException as exc:
        primary = exc
        raise
    finally:
        observation.update(v1_observation)
        if admission is not None:
            observation["v2_admission"] = admission
        if before is not None:
            observation["v2_source_before"] = before
        if publication_receipt is not None:
            observation["v1_failure_publication_receipt"] = publication_receipt
        # patch.object restores replay even on any BaseException. Preserve the
        # underlying v1 observation keys while appending only v2 receipts.
        observation["v2_wrapper"] = {
            "version": VERSION,
            "wrapped_v1_call_count": v1_call_count,
            "numeric_replay_wrapper_calls": wrapped_replay_calls,
            "failure_publication_authenticated": publication_receipt is not None,
            "raw_numeric_result_retained": "numeric_replay_raw" in observation,
        }
        if primary is not None:
            observation["status"] = "error"
            observation["primary_error"] = observation.get("primary_error") or f"{type(primary).__name__}: {primary}"
        elif result is not None:
            observation["status"] = "complete"
            observation["phase"] = "complete"
        if before is not None:
            try:
                after = _source_snapshot()
                observation["v2_source_after"] = after
                _need(before["revision"] == after["revision"] and
                      before["status"] == after["status"] == "" and
                      before["source_lf_sha256"] == after["source_lf_sha256"],
                      "V2 sources changed during wrapped solve")
            except BaseException as source_error:
                observation["v2_source_after_error"] = f"{type(source_error).__name__}: {source_error}"
                if primary is not None:
                    try:
                        setattr(primary, "v2_source_after_error", observation["v2_source_after_error"])
                    except Exception:
                        pass
                else:
                    observation["status"] = "error"
                    observation["primary_error"] = observation["v2_source_after_error"]
                    raise
