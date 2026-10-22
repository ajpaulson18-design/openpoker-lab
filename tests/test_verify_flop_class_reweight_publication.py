import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_flop_class_reweight as runner
from scripts import flop_class_reweight_plan as planning
from scripts import flop_public_classes as proof
from scripts import verify_flop_public_classes_publication as old_publication
from scripts import verify_flop_class_reweight_publication as verify_saved


def _snapshot():
    return {"revision": verify_saved.EXPECTED_REVISION, "status": "",
            "source_lf_sha256": {"frozen.py": "b" * 64}}


def _audit(mode, strategy):
    metrics = {"value_oop": "1/3", "value_ip": "-1/3",
               "oop_best_response_value": "2/3", "ip_best_response_value": "1/3",
               "oop_best_response_gain": "1/3", "ip_best_response_gain": "2/3",
               "nash_conv": "1", "exploitability": "1/2"}
    numeric = {key: float(__import__("fractions").Fraction(value))
               for key, value in metrics.items()}
    return {"exact_metrics": metrics, "independent_numeric_metrics": numeric,
            "maximum_numeric_gap": 0.0, "exact_metric_count": 8,
            "physical_rows_lifted": 16912, "class_rows": 466,
            "physical_strategy_sha256": proof._digest(strategy),
            "class_policy": [[index % 2, f"hand{index}", [], [0.5, 0.5]]
                             for index in range(466)]}


def _old_report(audits):
    return {"training_calls": 0, "physical_worlds_sha256": "c" * 64,
            "physical_tree_sha256": "d" * 64,
            "source_lf_sha256": {"old.py": "e" * 64},
            "forbidden_production_calls": {f"old.{i}": 0 for i in range(41)},
            "controls": audits}


def _write_gzip(directory, filename, value):
    raw = runner.cost._canonical(value, newline=True)
    packed = gzip.compress(raw, mtime=0)
    (directory / filename).write_bytes(packed)
    return {"path": filename, "raw_bytes": len(raw), "gzip_bytes": len(packed),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "gzip_sha256": hashlib.sha256(packed).hexdigest()}


def _make_evidence(directory):
    spec = runner._protocol()
    plans, preflight = runner._preflight(spec)
    artifacts, cases, audits_by_mode = [], [], {mode: None for mode in runner.CONTROLS}
    all_plan_records = {case_id: runner._plan_record(plan) for case_id, plan in plans}
    snapshot = _snapshot()
    for case_id, plan in plans:
        strategy = [{"i": index} for index in range(16912)]
        audits = {mode: _audit(mode, strategy) for mode in runner.CONTROLS}
        if case_id == "baseline":
            audits_by_mode = audits
        canonical_prior = {(runner.reweighted._canonical_hand(a),
                            runner.reweighted._canonical_hand(b)): p
                           for a, b, p in plan.exact_pair_priors}
        pair_counts, pair_probabilities = [], []
        for index, (pair, prior) in enumerate(sorted(canonical_prior.items())):
            pair_counts.append({"oop_hand": pair[0], "ip_hand": pair[1],
                                "ordered_outcomes": 1980, "wins": 900 + index,
                                "ties": 300, "losses": 780 - index,
                                "pair_probability_fraction":
                                    f"{prior.numerator}/{prior.denominator}",
                                "pair_probability": float(prior)})
            pair_probabilities.append([pair[0], pair[1], float(prior)])
        preparation = {"case_id": case_id, "plan": all_plan_records[case_id],
                       "normalizer": [plan.global_blocker_normalizer.numerator,
                                      plan.global_blocker_normalizer.denominator],
                       "pair_counts": pair_counts, "pair_probabilities": pair_probabilities,
                       "worlds": 5940, "census": dict(runner.reweighted.EXPECTED_CENSUS),
                       "partition": {"test": True},
                       "census": {**runner.reweighted.EXPECTED_CENSUS,
                                  "compact_tree_sha256": "3" * 64,
                                  "physical_branch_subtrees_compared": 11787,
                                  "physical_nodes_checked": 30812},
                       "weighted_worlds_sha256": "c" * 64 if case_id == "baseline" else "1" * 64,
                       "physical_tree_sha256": "d" * 64,
                       "baseline_world_sha256": "c" * 64,
                       "baseline_tree_sha256": "d" * 64}
        prep_file = _write_gzip(directory, f"{case_id}-preparation.json.gz", preparation)
        artifacts.append(prep_file)
        control_rows = []
        for mode in runner.CONTROLS:
            payload = {"worlds": 5940, "compatible_pairs": 3, "deals": 3,
                       "strategy_schema": "postflop-strategy-v1",
                       "strategy": strategy}
            record = {"case_id": case_id, "control": mode,
                      "payload": payload, "audit": audits[mode]}
            file_row = _write_gzip(directory, f"{case_id}-{mode}.json.gz", record)
            artifacts.append(file_row)
            control_rows.append({"control": mode, "status": "complete",
                                 "evidence_file": file_row,
                                 "audit_summary": runner._audit_summary(audits[mode])})
        controls = [{**row, "started_at_utc": "2026-10-22T12:20:00+00:00",
                     "finished_at_utc": "2026-10-22T12:21:00+00:00",
                     "wall_seconds": 1.0, "process_seconds": 1.0}
                    for row in control_rows]
        cases.append({"case_id": case_id, "plan": all_plan_records[case_id],
                      "status": "complete", "source_before": snapshot,
                      "source_after": snapshot, "preparation_file": prep_file,
                      "started_at_utc": "2026-10-22T12:10:00+00:00",
                      "finished_at_utc": "2026-10-22T12:30:00+00:00",
                      "wall_seconds": 20.0, "process_seconds": 20.0,
                      "census": {**runner.reweighted.EXPECTED_CENSUS,
                                 "compact_tree_sha256": "3" * 64,
                                 "physical_branch_subtrees_compared": 11787,
                                 "physical_nodes_checked": 30812},
                      "controls": controls})
    old = _old_report(audits_by_mode)
    baseline_receipt = {
        "raw_sha256": old_publication.RAW_SHA256,
        "artifact_sha256": old_publication.ARTIFACT_SHA256,
        "interruption_sha256": old_publication.INTERRUPTION_SHA256,
        "physical_worlds_sha256": old["physical_worlds_sha256"],
        "physical_tree_sha256": old["physical_tree_sha256"],
        "source_lf_sha256": old["source_lf_sha256"],
        "training_calls": 0,
        "forbidden_production_calls": old["forbidden_production_calls"]}
    index = {"schema_version": 1, "protocol_id": "fixed-flop-class-reweight-proof-v1",
             "protocol": spec, "preflight": preflight, "status": "complete", "errors": [],
             "training_calls": 0, "forbidden_production_calls": old["forbidden_production_calls"],
             "source_before": snapshot, "source_after": snapshot,
             "baseline_receipt": baseline_receipt, "cases": cases, "files": artifacts,
             "runtime": {"python": "3.12.14 synthetic", "implementation": "CPython",
                         "platform": "Windows synthetic"},
             "execution_state": {"mode": "windows-benchmark-thread",
                                 "system_required": True, "previous_flags": 0x80000000,
                                 "requested_flags": 0x80000001},
             "created_at_utc": "2026-10-22T12:00:00+00:00",
             "finished_at_utc": "2026-10-22T12:40:00+00:00",
             "wall_seconds": 2400.0, "process_seconds": 2400.0}
    _resign(directory, index)
    return index, old


def _real_baseline_contract():
    path = Path(__file__).parent / "fixtures" / "flop_class_reweight_baseline_contract.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _resign(directory, index):
    index.pop("index_sha256", None)
    index["index_sha256"] = proof._digest(index)
    raw = json.dumps(index, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    (directory / "index.json").write_bytes(raw)
    verify_saved.INDEX_RAW_SHA256 = hashlib.sha256(raw).hexdigest()
    verify_saved.INDEX_SHA256 = index["index_sha256"]


class SavedReweightPublicationTests(unittest.TestCase):
    def setUp(self):
        self.old_raw_pin = verify_saved.INDEX_RAW_SHA256
        self.old_index_pin = verify_saved.INDEX_SHA256
        self.addCleanup(setattr, verify_saved, "INDEX_RAW_SHA256", self.old_raw_pin)
        self.addCleanup(setattr, verify_saved, "INDEX_SHA256", self.old_index_pin)

    def _run(self, directory, index, old):
        _resign(directory, index)
        with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
             patch.object(old_publication, "authenticate", return_value=old):
            return verify_saved.verify(directory)

    def test_portable_fixture_matches_completed_real_baseline_contract(self):
        fixture = _real_baseline_contract()
        self.assertEqual(fixture["source_revision"], verify_saved.EXPECTED_REVISION)
        self.assertEqual(fixture["metric_keys"], sorted(verify_saved.METRICS))
        self.assertEqual(fixture["case_id"], "baseline")
        plans = verify_saved._plan_records(runner._protocol())
        prep = {key: fixture[key] for key in (
            "case_id", "plan", "normalizer", "worlds", "census",
            "weighted_worlds_sha256", "physical_tree_sha256",
            "baseline_world_sha256", "baseline_tree_sha256")}
        plan = verify_saved._check_plan(prep, plans["baseline"], "baseline")
        sign_counts = verify_saved._check_pair_metadata(
            {"pair_counts": fixture["pair_counts"],
             "pair_probabilities": fixture["pair_probabilities"]}, plan)
        self.assertEqual(len(sign_counts), 3)
        self.assertEqual(fixture["audit"]["exact_metric_count"], 8)
        self.assertEqual(fixture["audit"]["physical_rows_lifted"], 16912)
        self.assertEqual(fixture["audit"]["class_rows"], 466)
        self.assertEqual(fixture["payload"]["strategy_schema"], "postflop-strategy-v1")
        exact = fixture["audit"]["exact_metrics"]
        numeric = fixture["audit"]["independent_numeric_metrics"]
        observed_gap = max(abs(float(__import__("fractions").Fraction(exact[key])) - numeric[key])
                           for key in verify_saved.METRICS)
        self.assertLessEqual(observed_gap, 1e-10)
        self.assertEqual(observed_gap, fixture["audit"]["maximum_numeric_gap"])

    def test_complete_synthetic_inventory_authenticates_without_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            index, old = _make_evidence(directory)
            with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
                 patch.object(old_publication, "authenticate", return_value=old), \
                 patch.object(runner.reweighted, "audit_policy",
                              side_effect=AssertionError("saved verifier must not replay")), \
                 patch.object(runner.physical, "prepare_oracle",
                              side_effect=AssertionError("saved verifier must not prepare")):
                result = verify_saved.verify(directory)
            self.assertEqual(result["status"], "saved-reweight-publication-authenticated")
            self.assertEqual(result["cases"], 3)
            self.assertEqual(result["controls"], 12)
            self.assertEqual(result["files"], 15)

    def test_tampered_index_rejected_even_when_resigned(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            index, old = _make_evidence(directory)
            index["cases"][0]["status"] = "not-run"
            index["index_sha256"] = proof._digest(
                {key: value for key, value in index.items() if key != "index_sha256"})
            raw = json.dumps(index, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
            (directory / "index.json").write_bytes(raw)
            with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
                 patch.object(old_publication, "authenticate", return_value=old):
                with self.assertRaisesRegex(ValueError, "immutable pin"):
                    verify_saved.verify(directory)

    def test_re_signed_wrong_pair_prior_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            index, old = _make_evidence(directory)
            row = index["files"][0]
            path = directory / row["path"]
            preparation = json.loads(gzip.decompress(path.read_bytes()))
            preparation["normalizer"] = [1, 1]
            replacement = _write_gzip(directory, row["path"], preparation)
            index["files"][0] = replacement
            index["cases"][0]["preparation_file"] = replacement
            with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
                 patch.object(old_publication, "authenticate", return_value=old):
                with self.assertRaisesRegex(ValueError, "normalizer"):
                    self._run(directory, index, old)

    def test_extra_artifact_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            index, old = _make_evidence(directory)
            (directory / "unregistered.json.gz").write_bytes(b"unused")
            with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
                 patch.object(old_publication, "authenticate", return_value=old):
                with self.assertRaisesRegex(ValueError, "unregistered evidence"):
                    verify_saved.verify(directory)

    def test_compressed_payload_tamper_fails_before_json_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            index, old = _make_evidence(directory)
            path = directory / index["files"][0]["path"]
            content = bytearray(path.read_bytes())
            content[-1] ^= 1
            path.write_bytes(content)
            with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
                 patch.object(old_publication, "authenticate", return_value=old):
                with self.assertRaisesRegex(ValueError, "Compressed evidence size or checksum"):
                    verify_saved.verify(directory)

    def test_re_signed_numeric_gap_over_bound_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            index, old = _make_evidence(directory)
            row = next(item for item in index["files"]
                       if item["path"] == "uniform-check-call.json.gz")
            path = directory / row["path"]
            record = json.loads(gzip.decompress(path.read_bytes()))
            record["audit"]["maximum_numeric_gap"] = 1.0
            replacement = _write_gzip(directory, row["path"], record)
            file_index = index["files"].index(row)
            index["files"][file_index] = replacement
            control = next(c for case in index["cases"] if case["case_id"] == "uniform"
                           for c in case["controls"] if c["control"] == "check-call")
            control["evidence_file"] = replacement
            with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
                 patch.object(old_publication, "authenticate", return_value=old):
                with self.assertRaisesRegex(ValueError, "numeric metric gap"):
                    self._run(directory, index, old)

    def test_guard_alias_names_reject_even_with_41_zero_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            index, old = _make_evidence(directory)
            index["forbidden_production_calls"] = {f"alias.{i}": 0 for i in range(41)}
            with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
                 patch.object(old_publication, "authenticate", return_value=old):
                with self.assertRaisesRegex(ValueError, "guard keys"):
                    self._run(directory, index, old)

    def test_recorded_source_revision_drift_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            index, old = _make_evidence(directory)
            for source in (index["source_before"], index["source_after"]):
                source["revision"] = "c" * 40
            for case in index["cases"]:
                case["source_before"]["revision"] = "c" * 40
                case["source_after"]["revision"] = "c" * 40
            with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
                 patch.object(old_publication, "authenticate", return_value=old):
                with self.assertRaisesRegex(ValueError, "frozen source checkpoint"):
                    self._run(directory, index, old)

    def test_current_full_snapshot_drift_during_verification_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            index, old = _make_evidence(directory)
            changed = {**_snapshot(), "revision": "c" * 40}
            with patch.object(runner, "_source_snapshot", side_effect=[_snapshot(), changed]), \
                 patch.object(old_publication, "authenticate", return_value=old):
                with self.assertRaisesRegex(ValueError, "Full current source snapshot changed"):
                    verify_saved.verify(directory)


if __name__ == "__main__":
    unittest.main()
