import copy
import unittest
from unittest.mock import patch

from scripts import benchmark_preflop_exact_anchor as bench


class ExactAnchorRunnerTests(unittest.TestCase):
    def setUp(self):
        self.spec = bench.validate_spec(
            __import__("json").loads(bench.SPEC_PATH.read_text(encoding="utf-8")))

    def test_frozen_spec_rejects_mutation(self):
        altered = copy.deepcopy(self.spec)
        altered["fixture"]["world_indexing"] = "categorical"
        with self.assertRaises(ValueError):
            bench.validate_spec(altered)

    def test_count_table_build_is_rank_free_and_exact(self):
        from pokerlab import preflop_full_board_equity as equity

        reference = {
            "fixture": {"sb_range": "AsAd:1,QsQd:0.5", "bb_range": "AsKh:0.25,KsKd:1",
                        "config": self.spec["fixture"]["config"]},
            "counts": [
                {"sb_hand": "AdAs", "bb_hand": "KdKs", "wins": 1_410_336,
                 "ties": 9_308, "losses": 292_660, "boards": 1_712_304},
                {"sb_hand": "QdQs", "bb_hand": "AsKh", "wins": 968_267,
                 "ties": 7_226, "losses": 736_811, "boards": 1_712_304},
                {"sb_hand": "QdQs", "bb_hand": "KdKs", "wins": 292_846,
                 "ties": 9_336, "losses": 1_410_122, "boards": 1_712_304},
            ],
            "identity": {"fixture": "test-only"},
            "verification": {"status": "passed", "artifact_sha256": "test-only"},
        }

        def forbidden(*args, **kwargs):
            raise AssertionError("Prepared table loader must not rank or enumerate boards")

        with (patch.object(equity, "rank_hand", forbidden),
              patch.object(equity, "_board_combinations", forbidden),
              patch.object(equity, "combinations", forbidden)):
            item = bench._load_inputs(self.spec, reference)
        self.assertEqual(len(item["table"].pairs), 3)
        self.assertEqual(item["table"].counts,
                         ((1_410_336, 9_308, 292_660),
                          (968_267, 7_226, 736_811),
                          (292_846, 9_336, 1_410_122)))
        self.assertEqual(item["table"].budget["physical_worlds_upper_bound"], 5_136_912)

    def test_preflight_census_has_twelve_profiles_and_two_trace_requests(self):
        calls = []

        def fake(item, algorithm, iterations):
            calls.append((algorithm, iterations))
            return {"python_complete_admission": {"ok": True},
                    "native_complete_admission": {"ok": True}}

        with patch.object(bench, "_preflight", fake):
            rows = bench._preflight_all(self.spec, {"table": object()})
        self.assertEqual(len(rows), 14)
        self.assertEqual(len(calls), 14)
        self.assertEqual(sum(row.get("profile_id", "").startswith("trace-") for row in rows), 2)
        self.assertTrue(all(row["status"] == "admitted" for row in rows))

    def test_valid_run_preflights_all_requests_before_build_lookup_or_profiles(self):
        events = []
        reference = {"fixture": {"sb_range": self.spec["fixture"]["sb_range"],
                                 "bb_range": self.spec["fixture"]["bb_range"]},
                     "identity": {"fixture": "test"},
                     "verification": {"status": "passed"}}
        table = type("Table", (), {"budget": {"compatible_pairs": 3,
                                                "physical_worlds_upper_bound": 5_136_912}})()
        item = {"table": table, "pinned_provenance": {}}
        identity = {"revision": "test", "status": [], "source_hashes": {}}

        def preflights(spec, prepared):
            events.append("all-preflights")
            return [{"status": "admitted", "profile_id": str(i)} for i in range(14)]

        def profile_run(spec, prepared, ref, algorithm, iterations, build, errors):
            events.append("profile")
            final = iterations == 8000
            repeat_count = 3 if final else 1
            samples = [{"backend": backend,
                        "independent_assessment": {"exact_anchor_contained": True,
                                                    "quality_pass": True}}
                       for _ in range(repeat_count) for backend in bench.BACKENDS]
            return {"algorithm": algorithm, "iterations": iterations,
                    "samples": samples,
                    "paired_comparisons": [{"status": "passed"} for _ in range(repeat_count)],
                    "quality_passed_by_backend": {"python": True, "native": True},
                    "deterministic_final_payloads": {"python": final, "native": final}}

        traces = {"python": {"payload": {}, "independent_assessment": {"exact_anchor_contained": True}},
                  "native": {"payload": {}, "independent_assessment": {"exact_anchor_contained": True}},
                  "cross_backend_comparison": {"status": "passed"}}

        def build_identity(build):
            events.append("build-lookup")
            return {"build": "fixed"}

        with (patch("scripts.preflop_exact_anchor_validation.load_reference", return_value=reference),
              patch.object(bench, "_identity", return_value=identity),
              patch.object(bench, "_require_baseline_ancestor"),
              patch.object(bench, "_load_inputs", return_value=item),
              patch.object(bench, "_preflight_all", side_effect=preflights),
              patch.object(bench.native_profile, "_build_identity", side_effect=build_identity),
              patch.object(bench, "_run_profile", side_effect=profile_run),
              patch.object(bench, "_run_traces", return_value=traces)):
            report = bench.run(self.spec, "external-build")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(events[0:2], ["all-preflights", "build-lookup"])
        self.assertGreater(events.index("profile"), events.index("build-lookup"))

    def test_early_quality_miss_is_nonfatal_and_has_no_median(self):
        item = {"case": {}, "table": object()}
        reference = {}
        errors = []

        def sample(item, reference, spec, algorithm, iterations, backend, build,
                   *, repeat, kind, trace=False):
            return {"backend": backend, "repeat": repeat, "sample_kind": kind,
                    "complete_seconds": 1.0, "payload_sha256": backend,
                    "payload": {"backend": backend}, "phase_call_census_passed": True,
                    "independent_assessment": {"quality_pass": False,
                                                "exact_anchor_contained": True}}

        with (patch.object(bench, "_sample", side_effect=sample),
              patch.object(bench, "_paired_comparison", return_value={
                  "meets_metric_gate": True, "meets_policy_gate": True})):
            early = bench._run_profile(self.spec, item, reference, "vanilla", 100,
                                       "external-build", errors)
            final = bench._run_profile(self.spec, item, reference, "vanilla", 8000,
                                       "external-build", errors)
        self.assertEqual(early["median_complete_seconds"], {"python": None, "native": None})
        self.assertFalse(any(early["quality_passed_by_backend"].values()))
        self.assertFalse(any(error.get("phase") == "final-quality" for error in errors))
        self.assertEqual(final["median_complete_seconds"], {"python": 1.0, "native": 1.0})

    def test_solver_callable_uses_pair_mean_for_both_backends(self):
        from pokerlab import preflop_checkdown_solver as solver
        item = {"case": {"config": {"small_blind": 0.5}}, "table": object()}
        for backend in ("python", "native"):
            captured = {}

            def fake(table, **kwargs):
                captured.update(kwargs)
                return {"ok": True}

            with patch.object(solver, "solve_prepared_preflop_checkdown", fake):
                call = bench.native_profile._solver_callable(
                    item, "preflop", "cfrplus", 10, backend, "external-build")
                self.assertEqual(call(), {"ok": True})
            self.assertEqual(captured["world_indexing"], "pair-mean")
            self.assertEqual(captured["training_backend"], backend)
            self.assertEqual(captured["resource_model"], "prepared-counts")
            self.assertEqual(captured["build_directory"], "external-build" if backend == "native" else None)

    def test_rejected_preflights_happen_before_native_build_lookup(self):
        reference = {"fixture": {"sb_range": self.spec["fixture"]["sb_range"],
                                 "bb_range": self.spec["fixture"]["bb_range"]},
                     "identity": {"fixture": "test"}}
        table = type("Table", (), {"budget": {"compatible_pairs": 3,
                                                "physical_worlds_upper_bound": 5_136_912}})()
        item = {"table": table, "pinned_provenance": {}}
        rejected = [{"status": "rejected", "profile_id": "one", "error": "test rejection"}]
        identity = {"revision": "test", "status": [], "source_hashes": {}}
        with (patch("scripts.preflop_exact_anchor_validation.load_reference", return_value=reference),
              patch.object(bench, "_identity", return_value=identity),
              patch.object(bench, "_require_baseline_ancestor"),
              patch.object(bench, "_load_inputs", return_value=item),
              patch.object(bench, "_preflight_all", return_value=rejected),
              patch.object(bench.native_profile, "_build_identity") as build_lookup):
            report = bench.run(self.spec, "unused")
        build_lookup.assert_not_called()
        self.assertEqual(report["status"], "error")
        self.assertFalse(report["all_fourteen_preflights_passed"])
        self.assertEqual(report["profiles"], [])


    def test_saved_report_replay_checks_full_census_and_rejects_resigned_tampering(self):
        import json
        from pathlib import Path
        import tempfile
        assessment = {"quality_pass": True, "exact_anchor_contained": True}
        comparison = {"metric_absolute_gaps": {}, "maximum_metric_absolute_gap": 0.0,
                      "maximum_policy_probability_gap": 0.0,
                      "meets_metric_gate": True, "meets_policy_gate": True}
        def sample(item, reference, spec, algorithm, iterations, backend, build,
                   *, repeat, kind, trace=False):
            payload = {"algorithm": algorithm, "iterations": iterations, "backend": backend}
            encoded = bench._canonical_bytes(payload)
            trainer = ("native_train" if backend == "native" else
                       "train_cfrplus" if algorithm == "cfrplus" else "train_cfr")
            return {"backend": backend, "repeat": repeat, "payload": payload,
                    "payload_sha256": bench._sha(encoded), "serialized_bytes_utf8": len(encoded),
                    "complete_seconds": float(repeat), "phase_call_census_passed": True,
                    "phase_calls": {trainer: 1, "evaluate": 1, "best_response": 2},
                    "rank_guard_calls": {"rank": 0}, "independent_assessment": assessment}
        from contextlib import redirect_stdout
        from io import StringIO
        with (redirect_stdout(StringIO()), patch.object(bench, "_sample", side_effect=sample),
              patch.object(bench, "_paired_comparison", side_effect=lambda *a: comparison.copy())):
            profiles = [bench._run_profile(self.spec, {}, {}, a, n, "unused", [])
                        for a in bench.ALGORITHMS for n in self.spec["checkpoints"]]
            traces = bench._run_traces(self.spec, {}, {}, "unused", [])
        identity = {"revision": "frozen", "status": []}
        data = {"status": "passed", "errors": [], "specification": self.spec,
                "profiles": profiles, "separate_traces": traces,
                "source_before": identity, "source_after": identity,
                "native_build_before": {}, "native_build_after": {},
                "preflights": [{"status": "admitted"} for _ in range(14)],
                "all_fourteen_preflights_passed": True, "source_unchanged": True,
                "native_build_unchanged": True}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            def save(value):
                value.pop("artifact_sha256", None)
                value["artifact_sha256"] = bench.checksum(value)
                path.write_text(json.dumps(value), encoding="utf-8")
            with (patch("scripts.preflop_exact_anchor_validation.load_reference", return_value={}),
                  patch("scripts.preflop_exact_anchor_validation.assess", return_value=assessment),
                  patch.object(bench, "_paired_comparison", return_value=comparison)):
                save(data)
                verified = bench._verify_serialized_report(path)
                self.assertEqual(verified["reopened_payloads_replayed"], 38)
                self.assertEqual(verified["fresh_comparisons_checked"], 19)
                altered = copy.deepcopy(data)
                altered["profiles"][0]["samples"][0]["payload_sha256"] = "forged"
                save(altered)
                with self.assertRaisesRegex(ValueError, "digest"):
                    bench._verify_serialized_report(path)
                altered = copy.deepcopy(data)
                altered["profiles"][0]["median_complete_seconds"]["python"] = 1.0
                save(altered)
                with self.assertRaisesRegex(ValueError, "timing summaries"):
                    bench._verify_serialized_report(path)
                altered = copy.deepcopy(data)
                altered["profiles"][0]["samples"][0]["independent_assessment"] = {"quality_pass": False}
                save(altered)
                with self.assertRaisesRegex(ValueError, "saved sample assessment"):
                    bench._verify_serialized_report(path)


if __name__ == "__main__":
    unittest.main()
