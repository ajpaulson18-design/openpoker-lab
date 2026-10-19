"""Bounded harness checks for the frozen full-deck raised-turn experiment."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts import benchmark_full_deck_raised_turn as benchmark
from scripts import full_deck_raised_fixture as fixture
from scripts.benchmark_turn_river_independent import solve


class FullDeckRaisedTurnBenchmarkTests(unittest.TestCase):
    def test_fixed_grid_work_and_original_cap_boundaries(self):
        census = fixture.census()
        self.assertEqual(benchmark.ITERATIONS, (100, 1000, 1500))
        self.assertEqual(benchmark.BACKENDS, ("materialized", "matrix-free"))
        self.assertEqual(benchmark.expected_work("materialized", 1500, census), 25_344_000)
        self.assertEqual(benchmark.expected_work("matrix-free", 1500, census), 27_369_234)
        self.assertEqual(benchmark.expected_work("materialized", 1775, census), 29_990_400)
        self.assertEqual(benchmark.expected_work("materialized", 1776, census), 30_007_296)
        self.assertEqual(benchmark.expected_work("matrix-free", 1644, census), 29_994_930)
        self.assertEqual(benchmark.expected_work("matrix-free", 1645, census), 30_013_164)

    def test_census_fixture_is_the_exact_frozen_full_deck_game(self):
        case = benchmark.frozen_case()
        census = fixture.census()
        physical = fixture.build_physical_worlds()
        self.assertNotIn("runouts", case)
        self.assertEqual((census.pairs, census.worlds, census.rivers_per_pair),
                         (4, 176, (44, 44, 44, 44)))
        self.assertEqual(census.information_rows, 2404)
        self.assertEqual(census.global_physical_mass, 1)
        self.assertEqual([str(pair.normalized_mass) for pair in physical.pairs],
                         ["4/21", "1/7", "8/21", "2/7"])
        self.assertEqual(census.public_tree_sha256,
                         "70d87064c6d7048b75784b6623a2dc6249f57ac61384a27d1724c3d53563bd61")

    def test_iteration_and_backend_inputs_reject_unsupported_values(self):
        census = fixture.census()
        for value in (True, 0, -1, 100.0):
            with self.subTest(iterations=value), self.assertRaises(ValueError):
                benchmark.expected_work("materialized", value, census)
        with self.assertRaises(ValueError):
            benchmark.expected_work("ranked", 100, census)
        self.assertFalse(benchmark._metric_map_close(
            {name: True for name in benchmark.METRICS},
            {name: 1.0 for name in benchmark.METRICS}))
        self.assertFalse(benchmark._metric_map_close(
            {name: 100.0 for name in benchmark.METRICS},
            {name: 0.0 for name in benchmark.METRICS}))

    def test_short_ten_iteration_harness_probes_replay_full_policies(self):
        # These two 10-sweep calls are harness probes, not the six fixed runs.
        case, census = benchmark.frozen_case(), fixture.census()
        for backend in benchmark.BACKENDS:
            with self.subTest(backend=backend):
                result = solve(case, backend, benchmark.ALGORITHM, 10)
                metrics, differences, oracle = benchmark.replay_profile(
                    result, case, backend, 10, census, allow_probe=True)
                self.assertEqual(set(metrics), set(benchmark.METRICS))
                self.assertTrue(all(abs(value) <= benchmark.TOLERANCE
                                    for value in differences.values()))
                self.assertEqual((oracle["worlds"], oracle["compatible_pair_count"],
                                  oracle["checked_information_sets"],
                                  oracle["public_node_count"]), (176, 4, 2404, 1254))

    def test_saved_verification_replays_six_records_without_trainer_calls(self):
        case, census = benchmark.frozen_case(), fixture.census()
        metrics = {name: 0.0 for name in benchmark.METRICS}
        oracle = {"worlds": 176, "compatible_pair_count": 4,
                  "checked_information_sets": 2404, "public_node_count": 1254}
        rows = []
        with tempfile.TemporaryDirectory(dir=benchmark.ROOT) as temporary:
            root = Path(temporary)
            policies = root / "policies"
            policies.mkdir()
            for iterations in benchmark.ITERATIONS:
                for backend in benchmark.BACKENDS:
                    name = benchmark._policy_name(backend, iterations)
                    payload = benchmark._canonical({"saved": True})
                    (policies / name).write_bytes(payload)
                    rows.append({
                        "iterations_requested": iterations, "iterations_completed": iterations,
                        "backend": backend, "algorithm": benchmark.ALGORITHM,
                        "target_exploitability": None, "threshold": benchmark.THRESHOLD,
                        "threshold_met": True, "metrics": metrics,
                        "oracle_metrics": metrics, "actual_metadata": {},
                        "scalar_differences": {},
                        "saved_policy_replayed": True, "worlds": 176,
                        "compatible_pairs": 4, "information_rows": 2404,
                        "independent_public_decisions": census.decisions,
                        "public_states": census.public_nodes,
                        "work_charge": benchmark.expected_work(backend, iterations, census),
                        "work_limit": fixture.REFERENCE_WORK_CAP,
                        "complete_call_seconds_uncontrolled": 1.0,
                        "independent_replay_seconds": 1.0,
                        "policy_file": name,
                        "policy_sha256": benchmark._sha(payload),
                    })
            report = {
                "schema_version": benchmark.SCHEMA_VERSION,
                "benchmark_id": benchmark.BENCHMARK_ID,
                "created_at_utc": "2026-10-19T00:00:00+00:00",
                "baseline_git_commit": "a" * 40,
                "python": "test", "platform": "test",
                "source_sha256": benchmark.fingerprints(),
                "reference_sha256": benchmark.REFERENCE_SHA256,
                "fixture": case,
                "census": json.loads(json.dumps(fixture.to_jsonable(census))),
                "methodology": benchmark._methodology(), "results": rows,
            }
            report_path = root / "report.json"
            report_path.write_bytes(benchmark._canonical(report))
            with patch.object(benchmark, "_verify_reference_pin",
                              return_value=benchmark.REFERENCE_SHA256), \
                 patch.object(benchmark, "solve", side_effect=AssertionError("trainer called")), \
                 patch.object(benchmark, "replay_profile",
                              return_value=(metrics, {}, oracle)):
                verified = benchmark.verify_saved_artifact(report_path, policies)
                self.assertEqual(verified["training_calls"], 0)
                report["results"][0]["threshold"] = 0.5
                report_path.write_bytes(benchmark._canonical(report))
                with self.assertRaisesRegex(ValueError, "threshold"):
                    benchmark.verify_saved_artifact(report_path, policies)
                report["results"][0]["threshold"] = benchmark.THRESHOLD
                report_path.write_bytes(benchmark._canonical(report))
                calls = []

                def change_earlier_policy_during_last_replay(*args, **kwargs):
                    calls.append(1)
                    if len(calls) == 6:
                        (policies / rows[0]["policy_file"]).write_bytes(b"changed after its replay")
                    return metrics, {}, oracle

                with patch.object(benchmark, "replay_profile", side_effect=change_earlier_policy_during_last_replay):
                    with self.assertRaisesRegex(ValueError, "changed during the full replay"):
                        benchmark.verify_saved_artifact(report_path, policies)

    def test_failed_staged_or_published_verification_rolls_back_only_owned_files(self):
        metrics = {name: 0.0 for name in benchmark.METRICS}
        oracle = {"worlds": 176, "compatible_pair_count": 4,
                  "checked_information_sets": 2404, "public_node_count": 1254}
        for fail_after_publication in (False, True):
            with self.subTest(fail_after_publication=fail_after_publication), \
                 tempfile.TemporaryDirectory(dir=benchmark.ROOT) as temporary:
                root = Path(temporary)
                policies = root / "policies"
                policies.mkdir()
                unrelated = policies / "unrelated.json"
                unrelated.write_bytes(b"preserved")
                report = root / "report.json"
                results = ([{"status": "staged-only"}, ValueError("forced verifier rejection")]
                           if fail_after_publication else [ValueError("forced verifier rejection")])
                with patch.object(benchmark, "fingerprints", return_value={"fixed": "a"}), \
                     patch.object(benchmark, "_head", return_value="a" * 40), \
                     patch.object(benchmark, "_verify_reference_pin", return_value=benchmark.REFERENCE_SHA256), \
                     patch.object(benchmark, "solve", return_value={"public_states": 3039}), \
                     patch.object(benchmark, "validate_profile_metadata", return_value=1), \
                     patch.object(benchmark, "replay_profile", return_value=(metrics, {}, oracle)), \
                     patch.object(benchmark, "verify_saved_artifact", side_effect=results):
                    with self.assertRaisesRegex(ValueError, "forced verifier rejection"):
                        benchmark.generate(report, policies)
                self.assertFalse(report.exists())
                self.assertEqual(list(policies.iterdir()), [unrelated])
                self.assertEqual(unrelated.read_bytes(), b"preserved")
                self.assertEqual(list(root.glob("*.candidate")), [])

    def test_source_or_head_drift_stops_after_first_call_before_publication(self):
        for changed in ("source", "head"):
            state = {"after_call": False}

            def sources():
                return {"fixed": "b" if state["after_call"] and changed == "source" else "a"}

            def head():
                return ("b" if state["after_call"] and changed == "head" else "a") * 40

            def solve(*args, **kwargs):
                state["after_call"] = True
                return {"public_states": 3039}

            with self.subTest(changed=changed), tempfile.TemporaryDirectory(dir=benchmark.ROOT) as temporary:
                report = Path(temporary) / "report.json"
                policies = Path(temporary) / "policies"
                with patch.object(benchmark, "fingerprints", side_effect=sources), \
                     patch.object(benchmark, "_head", side_effect=head), \
                     patch.object(benchmark, "_verify_reference_pin", return_value=benchmark.REFERENCE_SHA256), \
                     patch.object(benchmark, "solve", side_effect=solve) as mocked_solve:
                    with self.assertRaisesRegex(ValueError, "changed during operation"):
                        benchmark.generate(report, policies)
                self.assertEqual(mocked_solve.call_count, 1)
                self.assertFalse(report.exists())
                self.assertFalse(policies.exists())

    def test_oversized_saved_report_is_rejected_before_read(self):
        with tempfile.TemporaryDirectory(dir=benchmark.ROOT) as temporary:
            path = Path(temporary) / "oversized.json"
            path.write_bytes(b"x" * (benchmark.MAX_REPORT_BYTES + 1))
            with patch.object(Path, "read_bytes", side_effect=AssertionError("oversized file read")):
                with self.assertRaisesRegex(ValueError, "byte cap"):
                    benchmark.verify_saved_artifact(path)

    def test_immutable_publication_never_replaces_existing_different_bytes(self):
        with tempfile.TemporaryDirectory(dir=benchmark.ROOT) as temporary:
            path = Path(temporary) / "policy.json"
            path.write_bytes(b"accepted")
            created = []
            with self.assertRaisesRegex(ValueError, "Refusing to replace"):
                benchmark._atomic_exclusive(path, b"different", created)
            self.assertEqual(path.read_bytes(), b"accepted")
            self.assertEqual(created, [])


if __name__ == "__main__":
    unittest.main()
