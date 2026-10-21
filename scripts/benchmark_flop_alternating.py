"""Compare CFR+, LCFR, and alternating DCFR on one fixed flop game.

The timed run requires a committed, clean source snapshot. The output index
records a content checksum; immutable publication pins belong to the later evidence
wrapper, after this generic runner has completed.
"""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "benchmarks" / "weighted-full-deck-flop-alternating-v1.json"
SPEC_SHA256 = "738e8f123a3bdb844efdfe78638ce4954dfcb65fd0979e351e28ff853d72192d"
MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_RAW_GAP_EXAMPLES = 10
METRICS = ("value_oop", "value_ip", "oop_best_response_value",
           "ip_best_response_value", "oop_best_response_gain",
           "ip_best_response_gain", "nash_conv", "exploitability")
METHOD_IDS = ("cfrplus-control", "lcfr", "alternating-dcfr-3/2-0-2")
METHOD_FILE_SLUGS = {
    "cfrplus-control": "cfrplus-control",
    "lcfr": "lcfr",
    "alternating-dcfr-3/2-0-2": "alternating-dcfr-3_2-0-2",
}

def _source_modules():
    from pokerlab import alternating_public_cfr, postflop_solver
    from scripts import benchmark_flop_cfrplus as previous
    from scripts import benchmark_flop_delayed_cfrplus as delayed
    from scripts import benchmark_weighted_full_deck_flop as base
    return alternating_public_cfr, postflop_solver, previous, delayed, base


def _checksum(value):
    from scripts.benchmark_preflop_covered_counts import checksum
    return checksum(value)


def _canonical(value):
    from scripts.benchmark_preflop_covered_counts import canonical
    return canonical(value)


def load_spec():
    raw = SPEC_PATH.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("Alternating comparison spec exceeds its size bound")
    spec = json.loads(raw)
    return validate_spec(spec)


def validate_spec(spec, *, expected_digest=None):
    if type(spec) is not dict:
        raise ValueError("Alternating comparison spec must be an object")
    if expected_digest is None:
        expected_digest = SPEC_SHA256
    if (not isinstance(expected_digest, str) or not expected_digest
            or expected_digest.startswith("__")):
        raise ValueError("Comparison spec digest is not frozen")
    if _checksum(spec) != expected_digest:
        raise ValueError("Alternating comparison spec hash changed")
    if (spec.get("benchmark_id") != "weighted-full-deck-flop-alternating-v1"
            or spec.get("iterations") != 140
            or spec.get("timed_repeats") != 3
            or spec.get("training_passes_per_iteration") != 3
            or spec.get("traversal") != "public-batched"
            or spec.get("diagnostics") != "recursive"):
        raise ValueError("Alternating comparison protocol dimensions changed")
    if tuple(row.get("id") for row in spec.get("algorithms", ())) != METHOD_IDS:
        raise ValueError("Frozen method order or algorithm IDs changed")
    expected_orders = [
        [METHOD_IDS[0], METHOD_IDS[1], METHOD_IDS[2]],
        [METHOD_IDS[2], METHOD_IDS[0], METHOD_IDS[1]],
        [METHOD_IDS[1], METHOD_IDS[2], METHOD_IDS[0]],
    ]
    if spec.get("method_orders") != expected_orders:
        raise ValueError("Frozen rotating method orders changed")
    if spec.get("evidence_files") != {
            "timed_policy_payloads": 9, "allocation_policy_payloads": 3,
            "physical_world_records": 2, "index_files": 1, "total_files": 15}:
        raise ValueError("Frozen evidence inventory changed")
    if spec.get("expected", {}).get("max_world_node_iterations") != 29_937_600:
        raise ValueError("Full three-pass work reservation changed")
    if spec.get("baseline", {}).get("quality_gate_met") is not False:
        raise ValueError("Historical baseline quality miss must remain explicit")
    return spec


def _source_snapshot():
    _, _, _, delayed, _ = _source_modules()
    state = delayed.snapshot()
    raw = SPEC_PATH.read_bytes()
    state["source_hashes"][SPEC_PATH.relative_to(ROOT).as_posix()] = {
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "lf_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
    }
    return state


def _require_source_unchanged(expected):
    if _source_snapshot() != expected:
        raise ValueError("Source changed during benchmark or saved verification")


def _validate_recorded_source(before, after):
    """Validate the source record made by that run, not today's checkout."""
    if (type(before) is not dict or before != after or before.get("status")
            or type(before.get("source_hashes")) is not dict
            or not before["source_hashes"] or len(before["source_hashes"]) > 4096):
        raise ValueError("Recorded measurement source was dirty or changed during the run")
    revision = before.get("revision")
    if (type(revision) is not str or len(revision) != 40
            or any(char not in "0123456789abcdef" for char in revision.lower())):
        raise ValueError("Recorded measurement revision is malformed")
    if type(before.get("status")) is not list or before["status"]:
        raise ValueError("Recorded measurement source was dirty")
    for path, hashes in before["source_hashes"].items():
        if (type(path) is not str or not path or len(path) > 512 or "\\" in path
                or path.startswith("/") or any(part in ("", ".", "..")
                                                  for part in path.split("/"))
                or type(hashes) is not dict
                or set(hashes) != {"raw_sha256", "lf_sha256"}):
            raise ValueError("Recorded source hash manifest has an invalid path or shape")
        for digest in hashes.values():
            if (type(digest) is not str or len(digest) != 64
                    or any(char not in "0123456789abcdef" for char in digest)):
                raise ValueError("Recorded source hash manifest has an invalid digest")


def _utc_timestamp(value, label):
    if type(value) is not str or not value or len(value) > 64:
        raise ValueError("Invalid UTC timestamp: " + label)
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Invalid UTC timestamp: " + label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("Timestamp must be explicitly UTC: " + label)
    return parsed


def _require_sha256(value, label):
    if (type(value) is not str or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError("Invalid SHA-256 field: " + label)


def _validate_run_census(samples, allocations, spec):
    """Require the complete, typed frozen request inventory before replay."""
    if type(samples) is not list or len(samples) != 9:
        raise ValueError("Saved timed-call inventory must contain exactly nine calls")
    if type(allocations) is not list or len(allocations) != 3:
        raise ValueError("Saved allocation-call inventory must contain exactly three calls")

    methods = {row["id"]: row for row in spec["algorithms"]}
    expected_timed = _expected_timed_order(spec)
    observed = []
    timed_fields = {
        "kind", "method", "algorithm", "iterations", "repeat", "started_at_utc",
        "elapsed_seconds", "finished_at_utc", "file", "raw_bytes", "gzip_bytes",
        "payload_sha256", "gzip_sha256", "independent_replay",
        "forbidden_production_calls",
    }
    for row in samples:
        if type(row) is not dict:
            raise ValueError("Saved timed-call records must be objects")
        if set(row) != timed_fields:
            raise ValueError("Saved timed-call record fields changed")
        method = row.get("method")
        method_spec = methods.get(method) if type(method) is str else None
        if method_spec is None:
            raise ValueError("Saved timed call names an unknown method")
        repeat = row.get("repeat")
        iterations = row.get("iterations")
        if type(repeat) is not int or type(iterations) is not int:
            raise ValueError("Saved repeat and iteration counts must be exact integers")
        if (row.get("kind") != "timed" or type(row.get("kind")) is not str
                or row.get("algorithm") != method_spec["solver_algorithm"]
                or type(row.get("algorithm")) is not str
                or iterations != spec["iterations"]):
            raise ValueError("Saved timed-call kind, method, or iteration census changed")
        observed.append((method, repeat))
        if "error" in row or "replay_error" in row:
            raise ValueError("Saved timed-call inventory contains a failed observation")
        elapsed = row.get("elapsed_seconds")
        if (type(elapsed) not in (int, float) or not math.isfinite(elapsed)
                or elapsed <= 0 or elapsed >= 86400):
            raise ValueError("Saved complete-call duration is invalid")
        started = _utc_timestamp(row.get("started_at_utc"), "started_at_utc")
        finished = _utc_timestamp(row.get("finished_at_utc"), "finished_at_utc")
        if finished < started:
            raise ValueError("Saved timed-call UTC bounds are reversed")
        _validate_payload_receipt(
            row, expected_file=f"{_method_file_slug(method)}-{iterations}-{repeat}.json.gz")
        if (method == "cfrplus-control"
                and row["payload_sha256"] != spec["baseline"]["zero_cfrplus_140_public_batched_payload_sha256"]):
            raise ValueError("CFR+ control receipt differs from immutable zero-delay payload")
    if observed != expected_timed:
        raise ValueError("Saved timed-call method/repeat census changed")

    expected_allocations = [
        (method, spec["separate_allocation_calls"]["iterations"])
        for method in spec["separate_allocation_calls"]["methods"]
    ]
    observed_allocations = []
    allocation_fields = {
        "kind", "method", "algorithm", "iterations", "started_at_utc",
        "python_traced_peak_bytes", "finished_at_utc", "file", "raw_bytes",
        "gzip_bytes", "payload_sha256", "gzip_sha256", "independent_replay",
        "forbidden_production_calls",
    }
    for row in allocations:
        if type(row) is not dict:
            raise ValueError("Saved allocation-call records must be objects")
        if set(row) != allocation_fields:
            raise ValueError("Saved allocation-call record fields changed")
        method = row.get("method")
        method_spec = methods.get(method) if type(method) is str else None
        iterations = row.get("iterations")
        if method_spec is None or type(iterations) is not int:
            raise ValueError("Saved allocation method and iterations must be exact")
        if (row.get("kind") != "allocation" or type(row.get("kind")) is not str
                or row.get("algorithm") != method_spec["solver_algorithm"]
                or type(row.get("algorithm")) is not str):
            raise ValueError("Saved allocation kind or method metadata changed")
        observed_allocations.append((method, iterations))
        if "error" in row or "replay_error" in row:
            raise ValueError("Saved allocation inventory contains a failed observation")
        peak = row.get("python_traced_peak_bytes")
        if type(peak) is not int or peak <= 0:
            raise ValueError("Saved traced allocation peak must be a positive integer")
        started = _utc_timestamp(row.get("started_at_utc"), "started_at_utc")
        finished = _utc_timestamp(row.get("finished_at_utc"), "finished_at_utc")
        if finished < started:
            raise ValueError("Saved allocation UTC bounds are reversed")
        _validate_payload_receipt(
            row, expected_file=f"allocation-{_method_file_slug(method)}.json.gz")
    if observed_allocations != expected_allocations:
        raise ValueError("Saved allocation method/iteration census changed")


def _validate_payload_receipt(row, *, expected_file):
    if row.get("file") != expected_file or type(row.get("file")) is not str:
        raise ValueError("Saved payload filename does not match its frozen request")
    for field in ("raw_bytes", "gzip_bytes"):
        value = row.get(field)
        if type(value) is not int or value <= 0:
            raise ValueError("Saved payload byte count is invalid: " + field)
    for field in ("payload_sha256", "gzip_sha256"):
        _require_sha256(row.get(field), field)


def _check_control_payload_hash(payload, spec, method_id, iterations):
    if method_id == "cfrplus-control" and iterations == spec["iterations"]:
        expected = spec["baseline"]["zero_cfrplus_140_public_batched_payload_sha256"]
        actual = hashlib.sha256(_canonical(payload)).hexdigest()
        if actual != expected:
            raise ValueError("CFR+ control differs from immutable zero-delay payload")


def _rank_free_census(iterations):
    _, _, previous, _, _ = _source_modules()
    old = previous.load_spec()
    old["iterations"] = [iterations]
    old["expected"]["max_world_iterations"] = old["expected"]["worlds"] * iterations
    old["expected"]["max_world_node_iterations"] = (
        old["expected"]["worlds"] * old["expected"]["world_traversal_nodes"] * iterations * 3)
    return previous.preflight(old)


def preflight(spec):
    spec = validate_spec(spec)
    _, production, _, _, _ = _source_modules()
    census = _rank_free_census(spec["iterations"])
    for key, expected in spec["expected"].items():
        if key not in ("pair_priors", "raw_joint_weight_normalizer") and census[key] != expected:
            raise ValueError("Rank-free public-tree census changed: " + key)
    requests = []
    for repeat, order in enumerate(spec["method_orders"], 1):
        for method_id in order:
            requests.append({
                "kind": "timed", "repeat": repeat, "method": method_id,
                "algorithm": next(row["solver_algorithm"] for row in spec["algorithms"]
                                   if row["id"] == method_id),
                "iterations": spec["iterations"], "training_passes_per_iteration": 3,
                "world_node_iterations": census["max_world_node_iterations"],
            })
    for method_id in spec["separate_allocation_calls"]["methods"]:
        iters = spec["separate_allocation_calls"]["iterations"]
        trace_census = _rank_free_census(iters)
        requests.append({
            "kind": "allocation", "repeat": None, "method": method_id,
            "algorithm": next(row["solver_algorithm"] for row in spec["algorithms"]
                               if row["id"] == method_id),
            "iterations": iters, "training_passes_per_iteration": 3,
            "world_node_iterations": trace_census["max_world_node_iterations"],
        })
    if len(requests) != 12 or any(row["training_passes_per_iteration"] != 3 for row in requests):
        raise ValueError("All 12 requested calls must reserve three complete passes")
    if any(row["world_node_iterations"] > production._MAX_WORLD_NODE_WORK for row in requests):
        raise ValueError("A full requested three-pass solve exceeds the unchanged work cap")
    return {"rank_free": True, "census": census, "requests": requests,
            "requested_calls": 12, "training_passes_per_iteration": 3}


def _method_spec(spec, method_id):
    for row in spec["algorithms"]:
        if row["id"] == method_id:
            return row
    raise ValueError("Unknown algorithm method")


def _method_file_slug(method_id):
    slug = METHOD_FILE_SLUGS.get(method_id)
    if type(slug) is not str or not slug or "/" in slug or "\\" in slug:
        raise ValueError("Method has no safe frozen evidence filename")
    return slug


def _typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return (left.keys() == right.keys()
                and all(_typed_equal(left[key], right[key]) for key in left))
    if type(left) is list:
        return len(left) == len(right) and all(
            _typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def _check_candidate(payload, spec, method_id, iterations):
    method = _method_spec(spec, method_id)
    common = {
        "algorithm": method["solver_algorithm"],
        "iterations": iterations,
        "strategy_schema": "postflop-strategy-v1",
        "execution_backend": "public-batched-python",
        "plan_operation_limit": None,
        "public_batch_edge_limit": 250_000,
        "update_schedule": "alternating-oop-then-ip",
        "training_passes_per_iteration": 3,
    }
    for key, value in common.items():
        if not _typed_equal(payload.get(key), value):
            raise ValueError("Candidate execution identity differs: " + key)
    if (method_id == "cfrplus-control"):
        expected = {"solver_version": "configured-postflop-v1",
                    "average_schedule": "linear-post-sweep-own-reach"}
    else:
        expected = {"solver_version": "configured-postflop-alternating-v1",
                    "average_schedule": method["average_schedule"],
                    "regret_schedule": method["regret_schedule"],
                    "regret_floor": method["regret_floor"],
                    "training_kernel": method["training_kernel"]}
    for key, value in expected.items():
        if not _typed_equal(payload.get(key), value):
            raise ValueError("Candidate algorithm schedule metadata differs: " + key)
    if not _typed_equal(payload.get("board"), ["2c", "3d", "4h"]):
        raise ValueError("Candidate fixed board changed")
    if (not _typed_equal(payload.get("runout_mode"), "full-deck")
            or type(payload.get("worlds")) is not int or payload.get("worlds") != 5940):
        raise ValueError("Candidate physical game scope changed")
    if not _typed_equal(payload.get("config"), spec["config"]):
        raise ValueError("Candidate betting configuration changed")
    if "diagnostics_backend" in payload:
        raise ValueError("Comparison requires recursive diagnostics")
    if any(key in payload for key in ("averaging_delay", "averaging_positive_sweeps")):
        raise ValueError("No averaging delay is part of this comparison")
    rows = payload.get("strategy")
    if type(rows) is not list or not rows:
        raise ValueError("Candidate omitted serialized strategy rows")
    keys = set()
    for row in rows:
        if type(row) is not dict or set(row) != {
                "player", "hand", "street", "board", "history", "actions"}:
            raise ValueError("Candidate strategy row has unexpected fields")
        if (row.get("player") not in ("oop", "ip")
                or type(row.get("player")) is not str
                or type(row.get("hand")) is not str or len(row["hand"]) != 4
                or type(row.get("street")) is not str
                or type(row.get("board")) is not list
                or any(type(card) is not str for card in row["board"])
                or type(row.get("history")) is not list
                or any(type(token) is not str for token in row["history"])):
            raise ValueError("Candidate strategy identity fields are invalid")
        key = (row.get("player"), row.get("hand"), row.get("street"),
               tuple(row.get("board", ())), tuple(row.get("history", ())))
        if key in keys:
            raise ValueError("Duplicate candidate information-set row")
        keys.add(key)
        actions = row.get("actions")
        if type(actions) is not list or not actions:
            raise ValueError("Candidate information set has no actions")
        if any(type(action) is not dict or set(action) != {
                "name", "amount", "raise_to", "history_key", "probability"}
               for action in actions):
            raise ValueError("Candidate action has unexpected or missing numeric fields")
        for action in actions:
            if (type(action["name"]) is not str or type(action["history_key"]) is not str
                    or any(type(action[field]) not in (int, float)
                           or not math.isfinite(action[field])
                           for field in ("amount", "raise_to"))):
                raise ValueError("Candidate legal action identity or numeric fields are invalid")
        probs = [action.get("probability") for action in actions]
        if any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
               for value in probs):
            raise ValueError("Candidate policy probability is invalid")
        if abs(sum(probs) - 1.0) > 1e-10:
            raise ValueError("Candidate action probabilities do not normalize")
    for key in METRICS:
        value = payload.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Candidate scalar is not finite: " + key)


def _forbid_new_trainers(stack, alternating_module, calls):
    from pokerlab import public_cfr
    from pokerlab import preflop_delayed_cfrplus
    targets = (
        ("pokerlab.alternating_public_cfr", alternating_module,
         ("train_public_lcfr", "train_public_alternating_dcfr",
          "_train_alternating", "_weighted_average_sweep",
          "_cfrplus_target_deltas", "_aggregate_prefixes")),
        ("pokerlab.preflop_delayed_cfrplus", preflop_delayed_cfrplus,
         ("train_delayed_public_cfrplus",)),
        ("pokerlab.public_cfr", public_cfr,
         ("_cfrplus_target_deltas", "_aggregate_prefixes")),
    )
    patch = __import__("unittest.mock", fromlist=["patch"]).patch
    for module_name, module, names in targets:
        for name in names:
            key = module_name + "." + name
            calls[key] = 0
            def fail(*_args, __name=name, __key=key, **_kwargs):
                calls[__key] += 1
                raise AssertionError("Independent code invoked training helper: " + __name)
            stack.enter_context(patch.object(module, name, side_effect=fail))


def _guarded_reference(spec):
    alternating, _, _, _, base = _source_modules()
    calls = {}
    with ExitStack() as stack:
        _forbid_new_trainers(stack, alternating, calls)
        oracle, production_calls = base.prepare_reference(spec)
    if any(calls.values()) or any(production_calls.values()):
        raise ValueError("Independent physical preparation called candidate code")
    return oracle, {"legacy_production_helpers": production_calls,
                    "candidate_trainer_calls": calls}


def _assess(payload, oracle, spec):
    alternating, _, _, _, base = _source_modules()
    calls = {}
    with ExitStack() as stack:
        _forbid_new_trainers(stack, alternating, calls)
        checked, production_calls = base.assess(payload, oracle, spec)
    if any(calls.values()) or any(production_calls.values()):
        raise ValueError("Independent replay called candidate production code")
    return checked, {"legacy_production_helpers": production_calls,
                     "candidate_trainer_calls": calls}


def _row_key(row):
    return (row["player"], row["hand"], row["street"],
            tuple(row["board"]), tuple(row["history"]))


def _cross_method(left, right, spec, oracle, left_id, right_id):
    ignored = set(METRICS) | {
        "strategy", "algorithm", "solver_version", "average_schedule",
        "regret_schedule", "regret_floor", "training_kernel",
    }
    if ({key: value for key, value in left.items() if key not in ignored}
            != {key: value for key, value in right.items() if key not in ignored}):
        raise ValueError("Methods changed common game or strategy-schema metadata")
    left_rows = {_row_key(row): row for row in left["strategy"]}
    right_rows = {_row_key(row): row for row in right["strategy"]}
    if (len(left_rows) != len(left["strategy"]) or len(right_rows) != len(right["strategy"])
            or set(left_rows) != set(right_rows)):
        raise ValueError("Methods do not serialize identical information-set coverage")
    for key in left_rows:
        a, b = left_rows[key], right_rows[key]
        if {k: v for k, v in a.items() if k != "actions"} != {
                k: v for k, v in b.items() if k != "actions"}:
            raise ValueError("Method row metadata differs")
        if len(a["actions"]) != len(b["actions"]):
            raise ValueError("Method action count differs")
        for x, y in zip(a["actions"], b["actions"]):
            if {k: v for k, v in x.items() if k != "probability"} != {
                    k: v for k, v in y.items() if k != "probability"}:
                raise ValueError("Methods expose different legal numeric actions")

    _, _, _, delayed, _ = _source_modules()
    paths = delayed._decision_paths(oracle)
    reach_left = delayed._own_reach_masses(left, oracle, paths)
    reach_right = delayed._own_reach_masses(right, oracle, paths)
    max_raw = 0.0
    max_realization = 0.0
    count_nonzero = 0
    examples = []
    for key in sorted(left_rows):
        a, b = left_rows[key], right_rows[key]
        player_index = 0 if key[0] == "oop" else 1
        row_key = (player_index, key[1], key[4])
        own_a = reach_left[row_key]
        own_b = reach_right[row_key]
        for index, (x, y) in enumerate(zip(a["actions"], b["actions"])):
            raw_gap = abs(x["probability"] - y["probability"])
            realization_gap = abs(own_a * x["probability"] - own_b * y["probability"])
            max_raw = max(max_raw, raw_gap)
            max_realization = max(max_realization, realization_gap)
            if raw_gap:
                count_nonzero += 1
                example = {"row": {"player": key[0], "hand": key[1],
                                    "street": key[2], "board": list(key[3]),
                                    "history": list(key[4])},
                           "action_index": index,
                           "action": x.get("history_key"),
                           "left_probability": x["probability"],
                           "right_probability": y["probability"],
                           "absolute_gap": raw_gap}
                examples.append(example)
                examples.sort(key=lambda item: (-item["absolute_gap"], item["row"]["player"],
                                                item["row"]["hand"], item["row"]["history"],
                                                item["action_index"]))
                del examples[MAX_RAW_GAP_EXAMPLES:]
    scalar_gaps = {field: abs(left[field] - right[field]) for field in METRICS}
    return {
        "left_method": left_id, "right_method": right_id,
        "aligned_information_sets": len(left_rows),
        "aligned_action_rows": sum(len(row["actions"]) for row in left_rows.values()),
        "maximum_raw_conditional_probability_gap": max_raw,
        "nonzero_raw_conditional_probability_gap_count": count_nonzero,
        "maximum_own_reach_action_realization_gap": max_realization,
        "scalar_absolute_gaps": scalar_gaps,
        "largest_raw_probability_gap_examples": examples[:MAX_RAW_GAP_EXAMPLES],
        "policy_probability_and_cross_method_metric_gaps_are_diagnostic_only": True,
    }


def _compare_all_methods(payloads, spec, oracle):
    return [
        _cross_method(payloads[left], payloads[right], spec, oracle, left, right)
        for left, right in ((METHOD_IDS[0], METHOD_IDS[1]),
                            (METHOD_IDS[0], METHOD_IDS[2]),
                            (METHOD_IDS[1], METHOD_IDS[2]))
    ]


def _store(directory, filename, payload):
    _, _, _, _, base = _source_modules()
    return base.store_payload(directory, filename, payload)


def _compare_production_physical(spec, oracle):
    """Adapt the legacy producer census API without changing this protocol's scalar iteration field."""
    _, _, _, _, base = _source_modules()
    structural = dict(spec)
    iterations = spec["iterations"]
    structural["iterations"] = iterations if type(iterations) is list else [iterations]
    return base.compare_physical_worlds(structural, oracle)


def _timed_call(spec, directory, oracle, method_id, repeat):
    from time import perf_counter
    import gc
    _, production, _, _, _ = _source_modules()
    method = _method_spec(spec, method_id)
    gc.collect()
    started_at = datetime.now(timezone.utc).isoformat()
    start = perf_counter()
    row = {"kind": "timed", "method": method_id,
           "algorithm": method["solver_algorithm"], "iterations": spec["iterations"],
           "repeat": repeat, "started_at_utc": started_at}
    payload = None
    try:
        payload = production.solve_postflop(
            spec["board"], spec["oop_range"], spec["ip_range"],
            config=spec["config"], iterations=spec["iterations"],
            algorithm=method["solver_algorithm"], traversal=spec["traversal"],
            diagnostics=spec["diagnostics"])
        canonical_bytes = _canonical(payload)
        digest = hashlib.sha256(canonical_bytes).hexdigest()
        row["elapsed_seconds"] = perf_counter() - start
        row["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        artifact = _store(directory,
                           f"{_method_file_slug(method_id)}-{spec['iterations']}-{repeat}.json.gz",
                           payload)
        row.update(artifact)
        row["payload_sha256"] = digest
        _check_candidate(payload, spec, method_id, spec["iterations"])
        _check_control_payload_hash(payload, spec, method_id, spec["iterations"])
        checked, guard = _assess(payload, oracle, spec)
        row["independent_replay"], row["forbidden_production_calls"] = checked, guard
    except Exception as exc:
        row.setdefault("elapsed_seconds", perf_counter() - start)
        row["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        row["error"] = f"{type(exc).__name__}: {exc}"
        if payload is not None and "payload_sha256" not in row:
            try:
                row["payload_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
            except Exception:
                pass
    return row


def _allocation_call(spec, directory, oracle, method_id):
    import gc
    import tracemalloc
    _, production, _, _, _ = _source_modules()
    method = _method_spec(spec, method_id)
    options = spec["separate_allocation_calls"]
    gc.collect()
    started_at = datetime.now(timezone.utc).isoformat()
    row = {"kind": "allocation", "method": method_id,
           "algorithm": method["solver_algorithm"], "iterations": options["iterations"],
           "started_at_utc": started_at}
    payload = None
    try:
        tracemalloc.start()
        try:
            payload = production.solve_postflop(
                spec["board"], spec["oop_range"], spec["ip_range"],
                config=spec["config"], iterations=options["iterations"],
                algorithm=method["solver_algorithm"], traversal=spec["traversal"],
                diagnostics=spec["diagnostics"])
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        row["python_traced_peak_bytes"] = peak
        row["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        row.update(_store(directory,
                          f"allocation-{_method_file_slug(method_id)}.json.gz", payload))
        row["payload_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
        _check_candidate(payload, spec, method_id, options["iterations"])
        checked, guard = _assess(payload, oracle, spec)
        row["independent_replay"], row["forbidden_production_calls"] = checked, guard
    except Exception as exc:
        row["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def _expected_timed_order(spec):
    return [(method, repeat) for repeat, order in enumerate(spec["method_orders"], 1)
            for method in order]


def _summarize(directory, samples, spec, oracle):
    expected = _expected_timed_order(spec)
    actual = [(row["method"], row["repeat"]) for row in samples]
    if actual != expected or any(row.get("kind") != "timed" for row in samples):
        raise ValueError("Frozen rotating method order/call census changed")
    payloads, summary, quality = {}, [], []
    for method in METHOD_IDS:
        rows = [row for row in samples if row["method"] == method]
        if (len(rows) != 3 or len({row.get("payload_sha256") for row in rows}) != 1
                or any("error" in row for row in rows)):
            raise ValueError("A method lacks three exact completed payloads")
        payload = None
        for row in rows:
            raw = _read_payload(directory, row)
            _check_candidate(raw, spec, method, spec["iterations"])
            _check_control_payload_hash(raw, spec, method, spec["iterations"])
            checked, guard = _assess(raw, oracle, spec)
            if checked != row.get("independent_replay") or guard != row.get("forbidden_production_calls"):
                raise ValueError("Saved candidate replay changed")
            if payload is None:
                payload = raw
            elif raw != payload:
                raise ValueError("Repeated method payloads are not byte-exact after decoding")
        payloads[method] = payload
        nc = rows[0]["independent_replay"]["nash_conv"]
        met = nc <= spec["acceptance"]["final_nash_conv_chip_limit"]
        item = {"method": method, "algorithm": rows[0]["algorithm"],
                "iterations": spec["iterations"], "median_complete_seconds": statistics.median(
                    row["elapsed_seconds"] for row in rows),
                "nash_conv": nc,
                "quality_target": spec["acceptance"]["final_nash_conv_chip_limit"],
                "quality_target_met": met, "payload_sha256": rows[0]["payload_sha256"]}
        summary.append(item)
        quality.append({"method": method, "algorithm": rows[0]["algorithm"],
                        "iterations": spec["iterations"], "nash_conv": nc,
                        "target": spec["acceptance"]["final_nash_conv_chip_limit"],
                        "met": met})
    return summary, quality, _compare_all_methods(payloads, spec, oracle)


def _read_payload(directory, row):
    _, _, _, _, base = _source_modules()
    return base.read_payload(directory, row)


def _write_index(directory, report):
    from scripts.benchmark_preflop_covered_counts import checksum
    report.pop("artifact_sha256", None)
    report["artifact_sha256"] = checksum(report)
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    if len(raw) > MAX_INDEX_BYTES:
        raise ValueError("Alternating comparison index exceeds its size bound")
    path = directory / "index.json"
    tmp = directory / "index.json.tmp"
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    return raw


def run(directory, baseline_directory, *, execution_state=None):
    directory = Path(directory).resolve()
    baseline_directory = Path(baseline_directory).resolve()
    if (directory.exists() or directory == ROOT or ROOT in directory.parents
            or directory in baseline_directory.parents or baseline_directory in directory.parents):
        raise ValueError("Use a new evidence directory outside source and immutable baseline")
    spec = load_spec()
    before = _source_snapshot()
    report = {
        "schema_version": 1, "benchmark_id": spec["benchmark_id"],
        "specification": spec, "spec_sha256": SPEC_SHA256,
        "source_before": before, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution_state": execution_state or {"mode": "direct-call", "system_required": False},
        "runtime": {"python": platform.python_version(), "executable": sys.executable,
                    "platform": platform.platform()},
        "samples": [], "separate_allocation_calls": [], "validation_errors": [],
    }
    directory.mkdir(parents=False, exist_ok=False)
    try:
        if before.get("status"):
            raise ValueError("Commit a clean frozen candidate source before measurement")
        if not SPEC_SHA256 or SPEC_SHA256.startswith("__"):
            raise ValueError("Protocol spec digest is not frozen")
        subprocess.run(["git", "merge-base", "--is-ancestor",
                        spec["baseline"]["measured_source_revision"], "HEAD"],
                       cwd=ROOT, check=True)
        report["phase"] = "complete-rank-free-preflight"
        report["preflight"] = preflight(spec)
        if len(report["preflight"]["requests"]) != 12:
            raise ValueError("All method and allocation requests must preflight before oracle work")
        report["phase"] = "immutable-cfrplus-baseline-reconstruction"
        _, _, _, delayed, _ = _source_modules()
        baseline_spec = delayed.load_spec()
        report["baseline"] = delayed.verify_baseline(baseline_directory, baseline_spec)
        if (report["baseline"]["publication_index_sha256"]
                != spec["baseline"]["publication_index_sha256"]
                or report["baseline"]["quality_gate_met"] is not False):
            raise ValueError("Original measured CFR+ baseline identity/quality miss changed")
        report["phase"] = "independent-physical-oracle-preparation"
        oracle, calls = _guarded_reference(spec)
        report["oracle_forbidden_production_calls"] = calls
        report["oracle_physical_evidence"] = _store(
            directory, "independent-physical-worlds.json.gz",
            {"worlds": _source_modules()[4]._world_projection(oracle["worlds"])})
        report["production_physical_evidence"] = _store(
            directory, "production-physical-worlds.json.gz",
            _compare_production_physical(spec, oracle))
        for repeat, order in enumerate(spec["method_orders"], 1):
            for method in order:
                report["phase"] = "timed-method-call"
                report["active_request"] = {"method": method, "repeat": repeat,
                                             "iterations": spec["iterations"]}
                _write_index(directory, report)
                report["samples"].append(_timed_call(spec, directory, oracle, method, repeat))
                _write_index(directory, report)
        for method in spec["separate_allocation_calls"]["methods"]:
            report["phase"] = "separate-allocation-call"
            report["active_request"] = {"method": method,
                "iterations": spec["separate_allocation_calls"]["iterations"]}
            _write_index(directory, report)
            report["separate_allocation_calls"].append(
                _allocation_call(spec, directory, oracle, method))
            _write_index(directory, report)
        if any("error" in row for row in
               [*report["samples"], *report["separate_allocation_calls"]]):
            raise RuntimeError("At least one requested solver call failed")
        _validate_run_census(report["samples"], report["separate_allocation_calls"], spec)
        report["phase"] = "saved-policy-reconstruction"
        report["summary"], report["final_quality"], report["cross_method_diagnostics"] = \
            _summarize(directory, report["samples"], spec, oracle)
        report["quality_gate_met"] = all(row["met"] for row in report["final_quality"])
        report["status"] = "passed" if report["quality_gate_met"] else "quality-miss"
        report.pop("active_request", None)
        report["phase"] = "complete"
    except Exception as exc:
        report["validation_errors"].append(f"{type(exc).__name__}: {exc}")
        report["traceback"] = traceback.format_exc()
        report.setdefault("status", "error")
    finally:
        try:
            report["source_after"] = _source_snapshot()
        except Exception as exc:
            report["source_after"] = None
            report["source_after_error"] = f"{type(exc).__name__}: {exc}"
            report["validation_errors"].append("Unable to capture final source identity")
            report["status"] = "error"
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        if (report.get("source_after") is not None
                and report["source_after"] != report["source_before"]):
            report["validation_errors"].append("Candidate source changed during comparison")
            report["status"] = "error"
        try:
            _write_index(directory, report)
        except Exception as exc:
            report["index_write_error"] = f"{type(exc).__name__}: {exc}"
            raise
    return report


def verify_saved(directory, baseline_directory):
    verification_source_before = _source_snapshot()
    directory = Path(directory)
    path = directory / "index.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INDEX_BYTES:
        raise ValueError("Invalid bounded alternating comparison index")
    raw = path.read_bytes()
    try:
        report = json.loads(raw, object_pairs_hook=_unique_json_object)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Saved alternating comparison index is invalid JSON") from exc
    unsigned = dict(report)
    digest = unsigned.pop("artifact_sha256", None)
    spec = load_spec()
    if (_checksum(unsigned) != digest or not _typed_equal(report.get("specification"), spec)
            or report.get("spec_sha256") != SPEC_SHA256 or report.get("validation_errors")):
        raise ValueError("Saved alternating comparison checksum/spec/validation failed")
    _validate_saved_header(report, spec)
    _validate_run_census(report.get("samples"), report.get("separate_allocation_calls"), spec)
    before = report.get("source_before")
    after = report.get("source_after")
    _validate_recorded_source(before, after)
    admission = preflight(spec)
    if report.get("preflight") != admission:
        raise ValueError("Saved full-request rank-free preflight changed")
    _, _, _, delayed, base = _source_modules()
    if report.get("baseline") != delayed.verify_baseline(baseline_directory, delayed.load_spec()):
        raise ValueError("Immutable CFR+ control reconstruction changed")
    if report["baseline"]["quality_gate_met"] is not False:
        raise ValueError("Historical CFR+ quality miss must remain preserved")
    records = [report["oracle_physical_evidence"], report["production_physical_evidence"],
               *report["samples"], *report["separate_allocation_calls"]]
    names = [row["file"] for row in records]
    if (len(names) != 14 or len(set(names)) != 14
            or {item.name for item in directory.iterdir()} != set(names) | {"index.json"}):
        raise ValueError("Comparison evidence must contain exactly 15 files")
    oracle, guarded = _guarded_reference(spec)
    if guarded != report.get("oracle_forbidden_production_calls"):
        raise ValueError("Independent producer guard census changed")
    if _read_payload(directory, report["oracle_physical_evidence"]) != {
            "worlds": base._world_projection(oracle["worlds"])}:
        raise ValueError("Independent 5,940-world record changed")
    base._check_physical_record(_read_payload(directory, report["production_physical_evidence"]),
                                oracle, spec)
    for row in [*report["samples"], *report["separate_allocation_calls"]]:
        payload = _read_payload(directory, row)
        _check_candidate(payload, spec, row["method"], row["iterations"])
        checked, calls = _assess(payload, oracle, spec)
        if checked != row.get("independent_replay") or calls != row.get("forbidden_production_calls"):
            raise ValueError("Saved independent physical/legal replay changed")
        if "error" in row:
            raise ValueError("Completed publication contains an errored candidate call")
    summary, quality, cross = _summarize(directory, report["samples"], spec, oracle)
    gate = all(row["met"] for row in quality)
    if (summary != report.get("summary") or quality != report.get("final_quality")
            or cross != report.get("cross_method_diagnostics")
            or report.get("quality_gate_met") is not gate
            or report.get("status") != ("passed" if gate else "quality-miss")):
        raise ValueError("Saved three-method summaries or per-method quality decisions changed")
    if path.read_bytes() != raw:
        raise ValueError("Saved comparison index changed during verification")
    _require_source_unchanged(verification_source_before)
    return {"timed_and_allocation_policies_replayed": 12,
            "worlds_reenumerated": len(oracle["worlds"]),
            "file_count": 15, "quality_gate_met": gate,
            "raw_index_sha256": hashlib.sha256(raw).hexdigest(),
            "measurement_source_revision": before["revision"],
            "measurement_source_files": len(before["source_hashes"])}


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _validate_saved_header(report, spec):
    if type(report) is not dict:
        raise ValueError("Saved benchmark index must be an object")
    expected_report_fields = {
        "schema_version", "benchmark_id", "specification", "spec_sha256",
        "source_before", "created_at_utc", "runtime", "execution_state", "samples",
        "separate_allocation_calls", "validation_errors", "phase", "baseline",
        "preflight", "oracle_forbidden_production_calls", "oracle_physical_evidence",
        "production_physical_evidence", "summary", "final_quality",
        "cross_method_diagnostics", "quality_gate_met", "status", "source_after",
        "finished_at_utc", "artifact_sha256",
    }
    if set(report) != expected_report_fields:
        raise ValueError("Saved benchmark report fields changed")
    if (type(report.get("schema_version")) is not int or report["schema_version"] != 1
            or report.get("benchmark_id") != spec["benchmark_id"]
            or type(report.get("benchmark_id")) is not str):
        raise ValueError("Saved benchmark identity changed")
    if report.get("status") not in ("passed", "quality-miss") or type(report.get("status")) is not str:
        raise ValueError("Saved benchmark status is invalid")
    if type(report.get("quality_gate_met")) is not bool:
        raise ValueError("Saved quality-gate field must be boolean")
    if type(report.get("validation_errors")) is not list or report["validation_errors"]:
        raise ValueError("Saved report contains validation errors")
    if report.get("status") == "passed" and report.get("quality_gate_met") is not True:
        raise ValueError("Passed report must have a met quality gate")
    if report.get("status") == "quality-miss" and report.get("quality_gate_met") is not False:
        raise ValueError("Quality-miss status must preserve a failed gate")
    if report.get("phase") != "complete" or "active_request" in report:
        raise ValueError("Saved benchmark did not reach a completed terminal phase")
    _require_sha256(report.get("spec_sha256"), "spec_sha256")
    _utc_timestamp(report.get("created_at_utc"), "created_at_utc")
    _utc_timestamp(report.get("finished_at_utc"), "finished_at_utc")
    execution = report.get("execution_state")
    ordinary = ({"mode": "direct-call", "system_required": False},
                {"mode": "ordinary-process", "system_required": False})
    if not any(_typed_equal(execution, expected) for expected in ordinary):
        if (type(execution) is not dict
                or set(execution) != {"mode", "system_required", "previous_flags", "requested_flags"}
                or execution.get("mode") != "windows-benchmark-thread"
                or execution.get("system_required") is not True
                or type(execution.get("previous_flags")) is not int
                or not 0 < execution["previous_flags"] <= 0xffffffff
                or type(execution.get("requested_flags")) is not int
                or execution["requested_flags"] != 0x80000001):
            raise ValueError("Saved measurement execution state changed")
    runtime = report.get("runtime")
    if (type(runtime) is not dict
            or set(runtime) != {"python", "executable", "platform"}
            or any(type(runtime.get(key)) is not str or not runtime[key] or len(runtime[key]) > 512
                   for key in ("python", "executable", "platform"))):
        raise ValueError("Saved runtime identity is incomplete")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--require-quality", action="store_true",
                        help="Return failure when a verified run preserves a quality miss")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            result = verify_saved(args.output, args.baseline)
            output = {
                "status": "verified",
                "quality_gate_met": result.get("quality_gate_met"),
                "raw_index_sha256": result.get("raw_index_sha256"),
                "timed_and_allocation_policies_replayed": result.get(
                    "timed_and_allocation_policies_replayed"),
                "worlds_reenumerated": result.get("worlds_reenumerated"),
                "file_count": result.get("file_count"),
            }
            print(json.dumps(output, sort_keys=True))
            return 1 if args.require_quality and result.get("quality_gate_met") is not True else 0
        base = _source_modules()[4]
        with base.measurement_execution_state() as execution_state:
            result = run(args.output, args.baseline, execution_state=execution_state)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"},
                         sort_keys=True))
        return 2
    output = {key: result.get(key) for key in
              ("status", "quality_gate_met", "finished_at_utc", "artifact_sha256",
               "validation_errors")}
    print(json.dumps(output, sort_keys=True))
    if result.get("status") == "passed":
        return 0
    return 1 if result.get("status") == "quality-miss" else 2


if __name__ == "__main__":
    raise SystemExit(main())
