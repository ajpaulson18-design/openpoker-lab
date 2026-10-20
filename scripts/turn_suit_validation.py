"""Generate and replay the predeclared global-suit equivariance study."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
import math
import os
import platform
import subprocess
import time
import uuid
from pathlib import Path

from scripts import turn_river_validation as rules
from scripts import turn_rational_certificate as exact_helper
from scripts import turn_suit_reference as reference
from scripts import turn_suit_transport as transport
from scripts import verify_turn_blocker_sequence as witness_verifier
from scripts.turn_blocker_sequence_fixture import FIXTURE
from scripts.benchmark_turn_river_independent import solve as solve_materialized
from pokerlab.matrix_free_turn import solve_matrix_free_turn

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "benchmarks/results/turn-suit-equivariance-v1.json"
POLICY_DIR = ROOT / "benchmarks/results/turn-suit-equivariance-policies-v1"
MAX_REPORT_BYTES, MAX_POLICY_BYTES = 2_000_000, 1_000_000
TARGET = F(1, 1000)
SYMMETRY_TARGET = F(1, 1_000_000_000)
KNOWN_VALUE = F(115, 7)
PERMUTATIONS = transport.SUIT_PERMUTATIONS
TRAINING_TARGETS = ("dcsh", "hscd", "shdc", "cdhs")
BACKENDS = ("materialized", "matrix-free")
GRID = tuple((target, backend, 1000) for target in TRAINING_TARGETS for backend in BACKENDS)
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
    "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability",
)
EXACT_REFERENCE_SHA256 = "8b70ad5460061cbbe479c135a33eec69f9a80ec66b3e9d19c24f6ee919635ced"
NEGATIVE_REFERENCE_SHA256 = "5781e203b988bf330b2ad9f8cc91320704fc96e0987616408a4c78ffd370f8f0"
SCOPE = "Global suit-isomorphism validation for one blocker-conditioned selected-river configured binary64-terminal turn game, including eight fixed CFR+ calls."
LIMITATIONS = (
    "Exact response bounds apply to row-normalized saved binary64 policies and configured binary64 terminal constants.",
    "The 24 archived transport checks reuse complete immutable source policies; they are not new training calls.",
    "Eight complete-call and replay observations make no general runtime, memory, RSS, or performance claim.",
    "Results apply only to this fixed selected-river turn fixture and do not establish unrestricted Hold'em equilibrium.",
)

# The independent verifier pins this same inventory as a set. Python sources are
# hashed after CRLF-to-LF normalization; frozen JSON and policy bytes stay strict.
REQUIRED_SOURCE_PATHS = tuple(sorted(set((
    *witness_verifier.REQUIRED_SOURCES,
    "scripts/turn_blocker_profiles.py",
    "scripts/verify_turn_blocker_profiles_independent.py",
    "tests/test_turn_blocker_profiles.py",
    "tests/test_turn_blocker_profiles_independent.py",
    "scripts/turn_suit_transport.py",
    "scripts/turn_suit_reference.py",
    "scripts/turn_suit_validation.py",
    "scripts/verify_turn_suit_equivariance.py",
    "scripts/benchmark_turn_river_independent.py",
    "tests/test_turn_suit_transport.py",
    "tests/test_turn_suit_reference.py",
    "tests/test_turn_suit_validation.py",
    "tests/test_verify_turn_suit_equivariance.py",
    "benchmarks/results/turn-blocker-sequence-equilibrium-v1.json",
    "benchmarks/results/turn-blocker-cfrplus-profiles-v1.json",
    "benchmarks/results/turn-suit-exact-reference-v1.json",
    "benchmarks/results/turn-suit-negative-reference-v1.json",
    *("benchmarks/results/turn-blocker-cfrplus-policies-v1/turn-blocker-%s-%d.json" % (backend, count)
      for backend in BACKENDS for count in (1000, 3000, 10000)),
))))


def _jsonable(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        if all(isinstance(key, str) for key in value):
            return {key: _jsonable(child) for key, child in value.items()}
        return {"key_value_entries": [
            {"key": _jsonable(key), "value": _jsonable(child)}
            for key, child in sorted(value.items(), key=lambda item: canonical(item[0]))
        ]}
    if isinstance(value, (list, tuple)):
        return [_jsonable(child) for child in value]
    if type(value) is float and not math.isfinite(value):
        raise ValueError("Nonfinite JSON float")
    return value


def canonical(value) -> bytes:
    return (json.dumps(_jsonable(value), sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def read_bounded(path: Path, cap: int) -> bytes:
    if path.stat().st_size > cap:
        raise ValueError("Input exceeds fixed byte cap: " + path.name)
    raw = path.read_bytes()
    if len(raw) > cap:
        raise ValueError("Input exceeds fixed byte cap: " + path.name)
    return raw


def source_fingerprints() -> dict[str, str]:
    inventory = set(REQUIRED_SOURCE_PATHS)
    inventory.update(path.relative_to(ROOT).as_posix() for path in (ROOT / "pokerlab").glob("*.py"))
    result = {}
    for relative in sorted(inventory):
        path = ROOT / relative
        if not path.is_file():
            raise ValueError("Required suit validation source/input is missing: " + relative)
        cap = MAX_POLICY_BYTES if "-policies-v1/" in relative else MAX_REPORT_BYTES
        raw = read_bounded(path, cap)
        if path.suffix == ".py":
            raw = raw.replace(b"\r\n", b"\n")
        result[relative] = sha(raw)
    return result


def assert_unchanged(saved_head: str, saved_sources: dict[str, str]) -> None:
    if head() != saved_head:
        raise ValueError("Git HEAD changed during suit validation")
    if source_fingerprints() != saved_sources:
        raise ValueError("Pinned suit validation source/input changed during generation")


def _verify_old_artifacts() -> tuple[dict, dict, bytes, bytes]:
    from scripts import verify_turn_blocker_profiles_independent as old_verifier
    old_verifier.reconstruct()
    witness = witness_verifier.verify_saved_artifact()
    witness_raw = read_bounded(ROOT / "benchmarks/results/turn-blocker-sequence-equilibrium-v1.json",
                               MAX_REPORT_BYTES)
    if sha(witness_raw) != "1da6f053f308aae7e6804c7c543c7c5f79d572d5104617d8368486e3704deaf4":
        raise ValueError("Frozen exact blocker witness hash differs")
    if F(witness["results"][0]["exact"]["metrics"]["value_oop"]) != KNOWN_VALUE:
        raise ValueError("Pinned exact blocker witness does not establish 115/7")
    report_path = ROOT / "benchmarks/results/turn-blocker-cfrplus-profiles-v1.json"
    old_raw = read_bounded(report_path, MAX_REPORT_BYTES)
    if sha(old_raw) != "5c5d4b60108af53256e9f58f21494967887fd91c8ac2871150c48f454f733e76":
        raise ValueError("Frozen source profile report hash differs")
    old_report = json.loads(old_raw)
    exact_ref_raw = read_bounded(ROOT / "benchmarks/results/turn-suit-exact-reference-v1.json",
                                 MAX_REPORT_BYTES)
    negative_ref_raw = read_bounded(ROOT / "benchmarks/results/turn-suit-negative-reference-v1.json",
                                    MAX_REPORT_BYTES)
    if sha(exact_ref_raw) != EXACT_REFERENCE_SHA256:
        raise ValueError("Frozen 24-suit exact reference hash differs")
    if sha(negative_ref_raw) != NEGATIVE_REFERENCE_SHA256:
        raise ValueError("Frozen one-sided suit negative reference hash differs")
    return old_report, witness, exact_ref_raw, negative_ref_raw


def _prepared(fixture: dict):
    # The separately frozen reference helper supplies the physical model and its
    # independent best-five rank cross-check, without invoking a trainer or LP.
    prepared = reference.game(fixture)
    config, worlds, root, decisions = prepared
    board = rules.cards(fixture["board"])
    selected_set = set(fixture["runouts"])
    selected = tuple(card for card in rules.DECK if card in selected_set)
    pair_count = len({(world["hands"][0], world["hands"][1]) for world in worlds})
    if len(worlds) != 6 or pair_count != 3 or len(decisions) != 28 or len(selected) != 2:
        raise ValueError("Transformed physical model census differs from fixed 6/3/28")
    return board, config, worlds, root, selected, prepared


def _profile_rows(rows: list[dict]) -> dict:
    policies = {}
    for row in rows:
        player = {"oop": 0, "ip": 1}.get(row.get("player"))
        if player is None:
            raise ValueError("Unknown policy player")
        key = player, row.get("hand"), tuple(row.get("history", ()))
        if key in policies:
            raise ValueError("Duplicate policy identity")
        actions = row.get("actions")
        if type(actions) is not list or not actions:
            raise ValueError("Policy row has no legal action list")
        values = tuple(action.get("probability") for action in actions)
        if any(type(value) is not float or not math.isfinite(value) for value in values):
            raise ValueError("Policy probabilities must be finite serialized binary64")
        policies[key] = values
    return policies


def _rational_rows(rows: list[dict]) -> dict:
    policies = {}
    for row in rows:
        player = {"oop": 0, "ip": 1}.get(row.get("player"))
        if player is None:
            raise ValueError("Unknown rational policy player")
        key = player, row["hand"], tuple(row["history"])
        if key in policies:
            raise ValueError("Duplicate rational policy identity")
        policies[key] = tuple(F(action["probability_fraction"]) for action in row["actions"])
    return policies


def _metrics_as_fractions(exact: dict) -> dict[str, F]:
    metrics = exact.get("metrics")
    if type(metrics) is not dict or set(metrics) != set(METRICS):
        raise ValueError("Exact certificate metric set differs")
    return {name: F(metrics[name]) for name in METRICS}


def _metrics_as_strings(metrics: dict[str, F]) -> dict[str, str]:
    return {name: str(metrics[name]) for name in METRICS}


def _float_metrics(exact: dict) -> dict[str, float]:
    result = {}
    for name, value in _metrics_as_fractions(exact).items():
        try:
            projected = float(value)
        except (OverflowError, ValueError) as exc:
            raise ValueError("Exact metric has no finite binary64 projection: " + name) from exc
        if not math.isfinite(projected):
            raise ValueError("Exact metric has no finite binary64 projection: " + name)
        result[name] = projected
    return result


def _check_float_replay(exact: dict, oracle: dict) -> dict[str, float]:
    exact_float = _float_metrics(exact)
    differences = {}
    for name in METRICS:
        expected = oracle.get(name)
        observed = exact_float[name]
        if type(expected) is not float or not math.isfinite(expected) or abs(observed - expected) > 1e-9:
            raise ValueError("Exact normalized policy differs from independent float replay: " + name)
        differences[name] = observed - expected
    return differences


def _replay_complete(result: dict, fixture: dict, prepared=None):
    board, config, worlds, root, selected, prepared = prepared or _prepared(fixture)
    replay_input = deepcopy(result)
    # The rules API canonicalizes selected subsets by deck order. Keep the mapped
    # immutable result intact, but supply the validator's canonical replay view.
    replay_input["runouts"] = list(selected)
    replay_input["reachable_runouts"] = [card for card in selected
                                         if any(world["river"] == card for world in worlds)]
    oracle = rules.replay_policy(
        replay_input, fixture["oop"], fixture["ip"], board=fixture["board"],
        config=fixture["config"], river_config=fixture["config"],
        runouts=fixture["runouts"])
    rules.compare_result(replay_input, oracle, tolerance=1e-9)
    exact = exact_helper.evaluate_exact(root, worlds, _profile_rows(replay_input["strategy"]),
                                        config.pot, result=replay_input)
    float_differences = _check_float_replay(exact, oracle)
    if not exact["lower_value_bound"] <= KNOWN_VALUE <= exact["upper_value_bound"]:
        raise ValueError("Exact interval excludes the independently known value 115/7")
    return oracle, exact, float_differences, prepared


def _player_index(value) -> int:
    if value == "oop":
        return 0
    if value == "ip":
        return 1
    raise ValueError("Unknown normalized policy player")


def _sorted_normalized_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: (_player_index(row["player"]), row["hand"],
                                         tuple(row["history"])))


def normalized_policy_rows_sha256(rows: list[dict]) -> str:
    return sha(canonical(_sorted_normalized_rows(rows)))


def _normalized_policy_map(rows: list[dict]) -> dict:
    result = {}
    for row in rows:
        key = (_player_index(row["player"]), row["hand"], tuple(row["history"]))
        if key in result:
            raise ValueError("Duplicate normalized row identity")
        result[key] = tuple(F(action["probability_fraction"]) for action in row["actions"])
    return result


def _maximum_policy_difference(left_rows: list[dict], right_rows: list[dict]) -> F:
    left, right = _normalized_policy_map(left_rows), _normalized_policy_map(right_rows)
    if set(left) != set(right):
        raise ValueError("Suit-transformed normalized policy identities differ")
    maximum = F(0)
    for identity in left:
        if len(left[identity]) != len(right[identity]):
            raise ValueError("Suit-transformed normalized legal action count differs")
        for a, b in zip(left[identity], right[identity]):
            maximum = max(maximum, abs(a - b))
    return maximum


def _tree_and_world_hashes(prepared, inverse: str) -> tuple[str, str]:
    inverse_table = str.maketrans(transport.SOURCE_SUITS, inverse)
    _config, worlds, root, _decisions = prepared
    return (sha(canonical(reference.structure(root, inverse_table))),
            sha(canonical(reference.world_law(worlds, inverse_table))))


def _validate_negative_control(raw: bytes, base_prepared):
    negative = json.loads(raw)
    wrong_oop = transport.map_explicit_range(FIXTURE["oop"], "sdhc")
    if (negative.get("candidate_training_run") is not False
            or negative.get("oop_only_target") != "sdhc"
            or negative.get("wrong_oop") != wrong_oop
            or negative.get("original_worlds") != 6
            or negative.get("wrong_worlds") != 8):
        raise ValueError("Frozen one-sided negative control identity differs")
    board = rules.cards(FIXTURE["board"])
    ranges = (rules.expand_range(wrong_oop, board),
              rules.expand_range(FIXTURE["ip"], board))
    worlds, selected = rules._worlds(board, ranges, FIXTURE["runouts"])
    pairs = {(world["hands"][0], world["hands"][1]) for world in worlds}
    if len(worlds) != 8 or len(pairs) != 4 or len(selected) != 2:
        raise ValueError("One-sided negative control did not create 8 worlds/4 pairs")
    aa = tuple(sorted(("Ac", "Ah")))
    opponent = tuple(sorted(("Ad", "As")))
    new_worlds = [world for world in worlds
                  if world["hands"] == (aa, opponent) or world["hands"] == (opponent, aa)]
    new_pair_mass = sum((world["weight"] for world in new_worlds), F(0))
    if (len(new_worlds) != 2 or {world["river"] for world in new_worlds} != set(selected)
            or any(world["sign"] != 0 for world in new_worlds)
            or new_pair_mass != F(1, 8)
            or new_pair_mass != F(negative["newly_compatible_aa_pair_mass"])):
        raise ValueError("Negative control's new AA matchup/rivers/mass/signs differ")
    base_worlds = base_prepared[1]
    identity = str.maketrans(transport.SOURCE_SUITS, transport.SOURCE_SUITS)
    if reference.world_law(worlds, identity) == reference.world_law(base_worlds, identity):
        raise ValueError("One-sided negative control unexpectedly preserves the physical law")
    return {
        "kind": negative["kind"],
        "candidate_training_run": False,
        "oop_only_target": "sdhc",
        "worlds": len(worlds),
        "compatible_pairs": len(pairs),
        "newly_compatible_aa_pair_mass": negative["newly_compatible_aa_pair_mass"],
        "new_pair_showdown_signs": [world["sign"] for world in new_worlds],
        "original_isomorphism_rejected": True,
        "reference_sha256": sha(raw),
    }


def _validate_24_exact_transports(witness: dict) -> list[dict]:
    base_prepared = reference.game(FIXTURE)
    base_tree_hash, base_world_hash = _tree_and_world_hashes(base_prepared, "cdhs")
    rational_rows = witness["results"][0]["rational_strategy"]
    summaries = []
    for target in PERMUTATIONS:
        fixture = transport.transform_fixture(FIXTURE, target)
        prepared = reference.game(fixture)
        tree_hash, world_hash = _tree_and_world_hashes(prepared, transport.inverse_target(target))
        if (tree_hash, world_hash) != (base_tree_hash, base_world_hash):
            raise ValueError("Transformed public tree or physical world law differs: " + target)
        rows = transport.transform_rows(rational_rows, target)
        reference_metrics = reference.replay(rows, fixture, prepared)
        if (reference_metrics["value_oop"] != "115/7"
                or reference_metrics["oop_best_response_value"] != "115/7"
                or reference_metrics["ip_best_response_value"] != "-115/7"
                or reference_metrics["ip_best_response_gain"] != "0"
                or reference_metrics["oop_best_response_gain"] != "0"
                or reference_metrics["nash_conv"] != "0"):
            raise ValueError("Independent exact witness replay differs for suit map " + target)
        board, config, worlds, root, selected, _ = _prepared(fixture)
        rational_policies = _rational_rows(rows)
        exact_result_rows = []
        for row in rows:
            exact_row = deepcopy(row)
            exact_row["actions"] = [{key: value for key, value in action.items()
                                      if key != "probability_fraction"}
                                     for action in row["actions"]]
            exact_result_rows.append(exact_row)
        replay_result = {
            "board": list(board), "runouts": list(selected),
            "runout_mode": "conditioned-subset",
            "reachable_runouts": [card for card in selected
                                  if any(world["river"] == card for world in worlds)],
            "strategy": exact_result_rows,
            "config": config.to_dict(),
            "river_config": config.to_dict(),
            "info_sets": len(rows), "compatible_world_count": len(worlds),
            "compatible_pairs": len({world["hands"] for world in worlds}),
            **{name: float(F(value)) for name, value in reference_metrics.items()},
        }
        # Admit the complete numeric projection before calling the exact helper;
        # its documented contract requires a successful independent float replay.
        oracle = rules.replay_policy(
            replay_result, fixture["oop"], fixture["ip"], board=fixture["board"],
            config=fixture["config"], river_config=fixture["config"],
            runouts=fixture["runouts"])
        rules.compare_result(replay_result, oracle, tolerance=1e-9)
        exact = exact_helper.evaluate_exact(root, worlds, rational_policies, config.pot,
                                            result=replay_result)
        metrics = _metrics_as_fractions(exact)
        if (metrics["value_oop"] != KNOWN_VALUE or
                metrics["oop_best_response_value"] != KNOWN_VALUE or
                metrics["ip_best_response_value"] != -KNOWN_VALUE or
                metrics["nash_conv"] != 0 or
                not exact["lower_value_bound"] <= KNOWN_VALUE <= exact["upper_value_bound"]):
            raise ValueError("Exact certificate replay differs for suit map " + target)
        reach = witness_verifier.equilibrium_reach({
            "results": [{"fixture": fixture, "rational_strategy": rows}]
        })
        if F(reach["river_decision_reach"]) != 1:
            raise ValueError("Exact witness does not reach a river decision for suit map " + target)
        summaries.append({
            "target": target,
            "tree_identity_sha256": tree_hash,
            "world_law_sha256": world_hash,
            "rational_strategy_sha256": sha(canonical(rows)),
            "exact_metrics_sha256": sha(canonical(_metrics_as_strings(metrics))),
            "known_value_interval": {
                "lower": str(exact["lower_value_bound"]),
                "upper": str(exact["upper_value_bound"]),
                "contains_115_over_7": True,
            },
            "river_decision_reach": str(F(reach["river_decision_reach"])),
        })
    return summaries


def _load_old_profiles(report: dict):
    results = report.get("results")
    if type(results) is not list or len(results) != 6:
        raise ValueError("Archived source profile report must contain all six profiles")
    indexed = {(row.get("backend"), row.get("iterations_completed")): row for row in results}
    expected = {(backend, count) for backend in BACKENDS for count in (1000, 3000, 10000)}
    if set(indexed) != expected:
        raise ValueError("Archived source profile grid differs")
    loaded = {}
    for backend, count in sorted(expected):
        relative = "benchmarks/results/turn-blocker-cfrplus-policies-v1/turn-blocker-%s-%d.json" % (backend, count)
        raw = read_bounded(ROOT / relative, MAX_POLICY_BYTES)
        result = json.loads(raw)
        if canonical(result) != raw:
            raise ValueError("Archived source policy is not canonical JSON: " + relative)
        loaded[(backend, count)] = (indexed[(backend, count)], result, relative, sha(raw))
    return loaded


def _archive_transports(old_report: dict, prepared_by_target: dict) -> tuple[list[dict], dict]:
    source_profiles = _load_old_profiles(old_report)
    source_game = _prepared(FIXTURE)
    # Reconstruct the six immutable source certificates once. The 144 target
    # rows below still each replay the independently transported full policy.
    source_cache = {}
    for key, (source_row, source_result, source_file, source_digest) in source_profiles.items():
        _source_oracle, source_exact, _source_float_diffs, _ = _replay_complete(
            source_result, FIXTURE, source_game)
        source_metrics = _metrics_as_fractions(source_exact)
        pinned_metrics = {name: F(source_row["exact"]["metrics"][name]) for name in METRICS}
        if source_metrics != pinned_metrics:
            raise ValueError("Pinned archived source exact metrics do not reconstruct")
        source_cache[key] = (source_exact, source_metrics, source_file, source_digest)
    archive_rows, training_baselines = [], {}
    for target in PERMUTATIONS:
        fixture = transport.transform_fixture(FIXTURE, target)
        prepared = prepared_by_target[target]
        for backend in BACKENDS:
            for count in (1000, 3000, 10000):
                source_row, source_result, source_file, source_digest = source_profiles[(backend, count)]
                source_exact, source_metrics, _source_file, _source_digest = source_cache[(backend, count)]
                transported = transport.transform_result(source_result, target)
                fixture = transport.transform_fixture(FIXTURE, target)
                oracle, exact, _float_diffs, _ = _replay_complete(transported, fixture, prepared)
                metrics = _metrics_as_fractions(exact)
                if metrics != source_metrics:
                    raise ValueError("Archived exact metrics changed under suit transport")
                normalized_rows = _sorted_normalized_rows(exact["normalized_policy_rows"])
                archive_rows.append({
                    "target": target,
                    "backend": backend,
                    "iterations_requested": count,
                    "source_policy_file": source_file,
                    "source_policy_sha256": source_digest,
                    "transported_policy_sha256": sha(canonical(transported)),
                    "exact_metrics_sha256": sha(canonical(_metrics_as_strings(metrics))),
                    "normalized_policy_rows_sha256": sha(canonical(normalized_rows)),
                    "exact_metrics_equal_source": True,
                    "worlds": oracle["world_count"],
                    "information_sets": oracle["checked_information_sets"],
                })
                if count == 1000:
                    training_baselines[(target, backend)] = {
                        "result": transported,
                        "exact": exact,
                        "normalized_rows": normalized_rows,
                        "source_policy_file": source_file,
                        "source_policy_sha256": source_digest,
                        "metrics": source_metrics,
                    }
    if len(archive_rows) != 144:
        raise ValueError("Expected exactly 24 x 6 archive transport checks")
    return archive_rows, training_baselines


def _solve(target: str, backend: str, fixture: dict) -> dict:
    if backend == "materialized":
        solve_fixture = {**fixture, "river_config": fixture["config"]}
        return solve_materialized(solve_fixture, backend, "cfrplus", 1000)
    if backend == "matrix-free":
        return solve_matrix_free_turn(
            fixture["board"], fixture["oop"], fixture["ip"], fixture["config"],
            river_config=fixture["config"], iterations=1000, algorithm="cfrplus",
            runouts=fixture["runouts"])
    raise ValueError("Unknown fixed training backend")


def _train_eight(prepared_by_target: dict, training_baselines: dict,
                 saved_head: str, saved_sources: dict[str, str]):
    fresh_rows, policy_outputs = [], []
    for target, backend, iterations in GRID:
        assert_unchanged(saved_head, saved_sources)
        fixture = transport.transform_fixture(FIXTURE, target)
        started = time.perf_counter()
        result = _solve(target, backend, fixture)
        payload = canonical(result)
        solve_seconds = time.perf_counter() - started
        if result.get("algorithm") != "cfrplus" or result.get("iterations") != iterations:
            raise ValueError("Actual solve algorithm/iteration count differs from predeclared call")
        if len(payload) > MAX_POLICY_BYTES:
            raise ValueError("Generated complete policy exceeds 1MB cap")
        relative = "benchmarks/results/turn-suit-equivariance-policies-v1/turn-suit-%s-%s-%d.json" % (target, backend, iterations)
        path = ROOT / relative
        digest = sha(payload)
        if path.exists() and read_bounded(path, MAX_POLICY_BYTES) != payload:
            raise ValueError("Refusing to rewrite differing immutable transported policy: " + relative)
        replay_started = time.perf_counter()
        oracle, exact, float_differences, _ = _replay_complete(
            result, fixture, prepared_by_target[target])
        replay_seconds = time.perf_counter() - replay_started
        metrics = _metrics_as_fractions(exact)
        baseline = training_baselines[(target, backend)]
        metric_differences = {name: metrics[name] - baseline["metrics"][name] for name in METRICS}
        symmetry_met = all(abs(value) <= SYMMETRY_TARGET for value in metric_differences.values())
        if not symmetry_met:
            raise ValueError("Fresh profile differs from its inverse-mapped source metrics: " + target + "/" + backend)
        normalized_rows = _sorted_normalized_rows(exact["normalized_policy_rows"])
        max_policy_difference = _maximum_policy_difference(normalized_rows, baseline["normalized_rows"])
        known_interval = {
            "lower": str(exact["lower_value_bound"]),
            "upper": str(exact["upper_value_bound"]),
            "known_value": str(KNOWN_VALUE),
            "contains_known_value": bool(exact["lower_value_bound"] <= KNOWN_VALUE <= exact["upper_value_bound"]),
        }
        if not known_interval["contains_known_value"]:
            raise ValueError("Fresh exact interval excludes 115/7: " + target + "/" + backend)
        miss = metrics["nash_conv"] > TARGET
        exact_float = _float_metrics(exact)
        row = {
            "target": target,
            "fixture": fixture,
            "backend": backend,
            "algorithm": "cfrplus",
            "iterations_requested": iterations,
            "iterations_completed": result.get("iterations"),
            "policy_file": relative,
            "policy_sha256": digest,
            "policy_bytes": len(payload),
            "policy_identity_sha256": sha(canonical(result["strategy"])),
            "normalized_policy_rows_sha256": normalized_policy_rows_sha256(normalized_rows),
            "source_policy_file": baseline["source_policy_file"],
            "source_policy_sha256": baseline["source_policy_sha256"],
            "worlds": oracle["world_count"],
            "compatible_pairs": oracle["compatible_pair_count"],
            "information_sets": oracle["checked_information_sets"],
            "policy_rows": len(result["strategy"]),
            "total_public_nodes": 63,
            "public_decision_nodes": oracle["public_node_count"],
            "known_game_value_fraction": str(KNOWN_VALUE),
            "known_value_interval": known_interval,
            "float_projection_oracle": oracle,
            "serialized_vs_float_replay_differences": rules.compare_result(result, oracle, tolerance=1e-9),
            "exact": _jsonable(exact),
            "exact_normalized_float_projection": exact_float,
            "exact_vs_float_replay_differences": float_differences,
            "exact_metric_differences_vs_source": {name: str(value) for name, value in metric_differences.items()},
            "symmetry_target_fraction": str(SYMMETRY_TARGET),
            "symmetry_met": symmetry_met,
            "maximum_policy_probability_difference": float(max_policy_difference),
            "target_met": not miss,
            "threshold_miss": miss,
            "timing_solve_plus_json_seconds": solve_seconds,
            "timing_replay_seconds": replay_seconds,
        }
        fresh_rows.append(row)
        policy_outputs.append((path, payload))
        print(f"{target} {backend} 1000: exact NashConv="
              f"{float(metrics['nash_conv']):.12g}; target_met={not miss}; "
              f"max_policy_delta={float(max_policy_difference):.12g}", flush=True)
        assert_unchanged(saved_head, saved_sources)
    if len(fresh_rows) != 8:
        raise ValueError("Fixed suit training call count changed")
    return fresh_rows, policy_outputs


def verify_saved_artifact(path: Path = REPORT):
    from scripts import verify_turn_suit_equivariance as independent
    return independent.verify_saved_artifact(path)


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Acquire exclusive creation before entering cleanup. If the path already
    # exists, this attempt owns nothing and must never unlink it.
    stream = path.open("xb")
    try:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
        stream.close()
    except BaseException:
        try:
            stream.close()
        finally:
            path.unlink(missing_ok=True)
        raise


def _atomic_restore(path: Path, payload: bytes) -> None:
    candidate = path.with_name(path.name + ".restore-" + uuid.uuid4().hex)
    try:
        _write_exclusive(candidate, payload)
        os.replace(candidate, path)
    finally:
        candidate.unlink(missing_ok=True)


def _publish(report_payload: bytes, policy_outputs: list[tuple[Path, bytes]],
             saved_head: str, saved_sources: dict[str, str]) -> None:
    if len(report_payload) > MAX_REPORT_BYTES:
        raise ValueError("Generated report exceeds 2MB cap")
    for path, payload in policy_outputs:
        if len(payload) > MAX_POLICY_BYTES:
            raise ValueError("Generated policy exceeds 1MB cap")
        if path.exists() and read_bounded(path, MAX_POLICY_BYTES) != payload:
            raise ValueError("Refusing to rewrite differing immutable suit policy bytes")
    assert_unchanged(saved_head, saved_sources)
    previous = read_bounded(REPORT, MAX_REPORT_BYTES) if REPORT.exists() else None
    stage = REPORT.with_name(REPORT.name + "." + uuid.uuid4().hex + ".candidate")
    created_policies, replaced = [], False
    try:
        for path, payload in policy_outputs:
            if not path.exists():
                _write_exclusive(path, payload)
                created_policies.append(path)
        _write_exclusive(stage, report_payload)
        verify_saved_artifact(stage)
        assert_unchanged(saved_head, saved_sources)
        os.replace(stage, REPORT)
        replaced = True
        verify_saved_artifact(REPORT)
        assert_unchanged(saved_head, saved_sources)
    except BaseException:
        stage.unlink(missing_ok=True)
        try:
            if replaced:
                if previous is None:
                    REPORT.unlink(missing_ok=True)
                else:
                    _atomic_restore(REPORT, previous)
        finally:
            for path in created_policies:
                path.unlink(missing_ok=True)
        raise
    finally:
        stage.unlink(missing_ok=True)


def generate() -> dict:
    saved_sources, saved_head = source_fingerprints(), head()
    old_report, witness, exact_reference_raw, negative_reference_raw = _verify_old_artifacts()
    base_prepared = _prepared(FIXTURE)
    prepared_by_target = {}
    base_tree, base_world = _tree_and_world_hashes(base_prepared[5], "cdhs")
    for target in PERMUTATIONS:
        fixture = transport.transform_fixture(FIXTURE, target)
        prepared = _prepared(fixture)
        target_tree, target_world = _tree_and_world_hashes(prepared[5], transport.inverse_target(target))
        if (base_tree, base_world) != (target_tree, target_world):
            raise ValueError("Pre-search model equivariance failed: " + target)
        prepared_by_target[target] = prepared
    negative_control = _validate_negative_control(negative_reference_raw, base_prepared[5])
    exact_transport_summaries = _validate_24_exact_transports(witness)
    archive_transports, training_baselines = _archive_transports(old_report, prepared_by_target)
    # All fixed archives, model identities, and exact reference policies pass before
    # the first of the eight predeclared production calls is allowed to start.
    assert_unchanged(saved_head, saved_sources)
    fresh_results, policy_outputs = _train_eight(
        prepared_by_target, training_baselines, saved_head, saved_sources)
    report = {
        "schema_version": 1,
        "certificate_id": "turn-suit-equivariance-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_git_commit": saved_head,
        "source_sha256": saved_sources,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "fixture": FIXTURE,
        "permutations": list(PERMUTATIONS),
        "training_targets": list(TRAINING_TARGETS),
        "grid": [{"target": target, "backend": backend, "iterations": count}
                 for target, backend, count in GRID],
        "target_nash_conv_fraction": str(TARGET),
        "symmetry_target_fraction": str(SYMMETRY_TARGET),
        "known_game_value_fraction": str(KNOWN_VALUE),
        "exact_reference_sha256": sha(exact_reference_raw),
        "negative_reference_sha256": sha(negative_reference_raw),
        "scope": SCOPE,
        "limitations": list(LIMITATIONS),
        "negative_control": negative_control,
        "exact_reference_summary": exact_transport_summaries,
        "archive_transports": archive_transports,
        "fresh_results": fresh_results,
    }
    report_payload = canonical(report)
    _publish(report_payload, policy_outputs, saved_head, saved_sources)
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify_saved_artifact()
    else:
        generate()
