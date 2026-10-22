"""Synthetic auth/tamper checks for the immutable saved pilot verifier."""
import gzip
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import benchmark_flop_class_reweight as evidence
from scripts import benchmark_flop_class_cost as cost
from scripts import benchmark_flop_class_reweight_cfrplus as runner
from scripts import flop_public_classes as proof
from scripts import flop_class_policy as policy
from scripts import verify_flop_class_reweight_cfrplus_publication as verifier


def _source():
    return {"revision": verifier.EXPECTED_REVISION, "status": "",
            "source_lf_sha256": {f"source-{n}.py": f"{n:064x}" for n in range(31)}}


class PilotPublicationTests(unittest.TestCase):
    def _fixture(self, directory):
        files, cases = [], []
        summaries, reports = {}, {}
        sources = {f"source-{n}.py": f"{n:064x}" for n in range(31)}
        for i, case_id in enumerate(runner.CASES):
            name = f"{case_id}-560.json.gz"
            nc = (Fraction(1, 100), Fraction(1, 1000), Fraction(1, 200))[i]
            values = {"value_oop": "0", "value_ip": "0",
                      "oop_best_response_value": str(nc / 2),
                      "ip_best_response_value": str(nc / 2),
                      "oop_best_response_gain": str(nc / 2),
                      "ip_best_response_gain": str(nc / 2), "nash_conv": str(nc),
                      "exploitability": str(nc / 2)}
            raw_rows = []
            for player, count, hand in ((0, 232, "AdAs"), (1, 234, "KdKs")):
                for j in range(count):
                    hist = [] if player == 0 and j == 0 else [f"h{player}-{j}"]
                    raw_rows.append([player, hand, hist, [0.5, 0.5]])
            raw_rows.sort(key=lambda row: (row[0], row[1], tuple(row[2])))
            rows = {(p, hand, tuple(hist)): tuple(probs)
                    for p, hand, hist, probs in raw_rows}
            normalized, norm_audit = policy.canonicalize_binary_rows(rows)
            class_policy = [[p, hand, list(history), list(probs)]
                            for (p, hand, history), probs in sorted(normalized.items())]
            strategy = [{} for _ in range(16912)]
            payload = {"iterations": 560, "algorithm": "cfrplus", "averaging_delay": 0,
                       "research_adapter": "fixed-flop-class-reweight-cfrplus-v1",
                       "prior_case": case_id, "compact_resource_model": "budget-v1",
                       "worlds": 5940, "compatible_pairs": 3, "deals": 3,
                       "strategy_schema": "postflop-strategy-v1", "strategy": strategy}
            numeric = {key: float(Fraction(value)) for key, value in values.items()}
            gap = max(abs(float(Fraction(values[k])) - numeric[k]) for k in values)
            audit = {"exact_metrics": values, "independent_numeric_metrics": numeric,
                     "maximum_numeric_gap": gap, "exact_metric_count": 8,
                     "physical_rows_lifted": 16912, "class_rows": 466,
                     "physical_strategy_sha256": proof._digest(strategy),
                     "class_policy": class_policy}
            met = nc <= Fraction(1, 200)
            body = {"case_id": case_id, "iterations": 560, "training_calls": 1,
                    "physical_policy": payload, "raw_class_policy": raw_rows,
                    "normalization": norm_audit, "audit": audit,
                    "quality_target": 0.005, "quality_target_met": met,
                    "proof_receipt": {"status": "saved-authenticated"},
                    "source_lf_sha256": sources,
                    "preparation_forbidden_calls": {f"authority-{n}": 0 for n in range(41)},
                    "diagnostic_forbidden_calls": {f"authority-{n}": 0 for n in range(41)}}
            body["artifact_sha256"] = proof._digest(body)
            raw = cost._canonical(body, newline=True)
            compressed = gzip.compress(raw, mtime=0)
            (directory / name).write_bytes(compressed)
            file_row = {"path": name, "raw_bytes": len(raw), "gzip_bytes": len(compressed),
                        "raw_sha256": hashlib.sha256(raw).hexdigest(),
                        "gzip_sha256": hashlib.sha256(compressed).hexdigest()}
            files.append(file_row)
            summary = {"exact_metrics": values, "maximum_numeric_gap": gap,
                       "physical_strategy_sha256": audit["physical_strategy_sha256"],
                       "quality_target_met": met}
            summaries[case_id] = summary
            reports[case_id] = body
            cases.append({"case_id": case_id, "iterations": 560,
                          "admission": {"request": case_id}, "status": "complete",
                          "training_calls": 1, "source_before": _source(),
                          "source_after": _source(),
                          "started_at_utc": f"2026-10-22T10:{i*2:02d}:00+00:00",
                          "finished_at_utc": f"2026-10-22T10:{i*2+1:02d}:00+00:00",
                          "wall_seconds": 60.0, "process_seconds": 59.0,
                          "evidence_file": file_row, "audit_summary": summary})
            if case_id == "baseline":
                cases[-1]["old_baseline_semantics_equal"] = True
        index = {"schema_version": 1, "protocol_id": "fixed-flop-prior-cfrplus-pilot-v1",
                 "status": "complete", "errors": [], "training_calls": 3,
                 "solve_calls_started": 3, "solve_calls_completed": 3,
                 "protocol": {"preflight": {}, "cases": []}, "preflight": {}, "cases": cases,
                 "files": files, "source_before": _source(), "source_after": _source(),
                 "created_at_utc": "2026-10-22T09:59:00+00:00",
                 "finished_at_utc": "2026-10-22T10:05:00+00:00",
                 "wall_seconds": 180.0, "process_seconds": 175.0,
                 "runtime": {"python": "3.14", "implementation": "CPython", "platform": "test"},
                 "execution_state": {"mode": "ordinary-process", "system_required": False}}
        index["index_sha256"] = proof._digest(index)
        raw_index = json.dumps(index, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
        (directory / "index.json").write_bytes(raw_index)
        return index, raw_index, summaries, reports

    def _receipt(self, index, reports, pilot_raw_sha):
        rows = []
        for i, case_id in enumerate(runner.CASES):
            report = reports[case_id]
            exact_nc = Fraction(report["audit"]["exact_metrics"]["nash_conv"])
            rows.append({
                "case_id": case_id, "status": "complete",
                "started_at_utc": f"2026-10-22T10:{6+i*2:02d}:00+00:00",
                "finished_at_utc": f"2026-10-22T10:{7+i*2:02d}:00+00:00",
                "wall_seconds": 100.0, "process_seconds": 90.0,
                "source_before": index["source_before"],
                "source_after": index["source_after"],
                "input_file": index["files"][i],
                "result": {"status": "saved-reweighted-policy-physically-verified",
                           "training_calls": 0, "case_id": case_id, "iterations": 560,
                           "class_rows": 466, "physical_rows": 16912,
                           "nash_conv": float(exact_nc),
                           "quality_target_met": report["quality_target_met"],
                           "artifact_sha256": report["artifact_sha256"]}})
        receipt = {"schema_version": "fixed-flop-prior-saved-replay-v1",
                   "status": "complete", "errors": [], "blocked_training_attempts": 0,
                   "training_calls": 0,
                   "created_at_utc": "2026-10-22T10:06:00+00:00",
                   "finished_at_utc": "2026-10-22T10:12:00+00:00",
                   "wall_seconds": 360.0,
                   "pilot_index_raw_sha256": pilot_raw_sha,
                   "pilot_index_sha256": verifier.INDEX_SHA256,
                   "execution_method": "Sequential saved verification with training blocked",
                   "runtime": {"python": "3.14", "implementation": "CPython", "platform": "test"},
                   "source_before": index["source_before"],
                   "source_after": index["source_after"], "replays": rows}
        receipt["receipt_sha256"] = proof._digest(receipt)
        return receipt

    def _patches(self, index, summaries, reports, current_revisions=None):
        requests = [(name, 560, {"request": name}) for name in runner.CASES]
        spec = {"preflight": {}, "cases": []}
        historical_guard = {f"authority-{i}": 0 for i in range(41)}
        historical = {"forbidden_production_calls": historical_guard}
        sources = index["source_before"]["source_lf_sha256"]
        source = _source()
        if current_revisions is None:
            current_revisions = [verifier.EXPECTED_REVISION, verifier.EXPECTED_REVISION]
        current = [dict(source, revision=revision) for revision in current_revisions]
        stack = [
            patch.object(runner, "_protocol", return_value=spec),
            patch.object(runner, "_preflight", return_value=requests),
            patch.object(runner, "_proof_world_identities", return_value={k: "b" * 64 for k in runner.CASES}),
            patch.object(runner, "_baseline_reference", return_value={}),
            patch.object(runner, "_snapshot", side_effect=current),
            patch.object(runner, "_validate_report",
                         side_effect=lambda case_id, *args: summaries[case_id]),
            patch.object(runner, "_compare_baseline"),
            patch.object(runner.publication, "verify", return_value=reports["baseline"]["proof_receipt"]),
            patch.object(runner.publication.old_publication, "authenticate", return_value=historical),
        ]
        for item in stack:
            item.start()
            self.addCleanup(item.stop)
        return stack

    def test_complete_three_report_index_authenticates_and_keeps_quality_misses(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            index, raw, summaries, reports = self._fixture(directory)
            self._patches(index, summaries, reports, current_revisions=["f" * 40, "f" * 40])
            with patch.object(verifier, "INDEX_RAW_SHA256", hashlib.sha256(raw).hexdigest()), \
                 patch.object(verifier, "INDEX_SHA256", index["index_sha256"]):
                result = verifier.verify(directory, replay_receipt_path=None)
            self.assertEqual(result["status"], "saved-reweighted-cfrplus-pilot-authenticated")
            self.assertEqual(result["training_calls"], 0)
            self.assertEqual(result["quality_target_met"],
                             {"baseline": False, "uniform": True, "skew": True})

    def test_current_revision_may_advance_but_must_remain_stable(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            index, raw, summaries, reports = self._fixture(directory)
            self._patches(index, summaries, reports, current_revisions=["c" * 40, "d" * 40])
            with patch.object(verifier, "INDEX_RAW_SHA256", hashlib.sha256(raw).hexdigest()), \
                 patch.object(verifier, "INDEX_SHA256", index["index_sha256"]):
                with self.assertRaisesRegex(ValueError, "HEAD/status/source snapshot"):
                    verifier.verify(directory, replay_receipt_path=None)

    def test_resigned_incomplete_call_inventory_rejects_before_payload_auth(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            index, _, summaries, reports = self._fixture(directory)
            index["training_calls"] = 2
            index["index_sha256"] = proof._digest(
                {k: v for k, v in index.items() if k != "index_sha256"})
            raw = json.dumps(index, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
            (directory / "index.json").write_bytes(raw)
            self._patches(index, summaries, reports)
            with patch.object(verifier, "INDEX_RAW_SHA256", hashlib.sha256(raw).hexdigest()), \
                 patch.object(verifier, "INDEX_SHA256", index["index_sha256"]), \
                 patch.object(verifier, "_read_gzip",
                              side_effect=AssertionError("inventory before payload")):
                with self.assertRaisesRegex(ValueError, "call counts"):
                    verifier.verify(directory, replay_receipt_path=None)

    def test_modified_gzip_rejected_by_pinned_file_hash(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            index, raw, summaries, reports = self._fixture(directory)
            path = directory / "baseline-560.json.gz"
            data = path.read_bytes()
            path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
            self._patches(index, summaries, reports)
            with patch.object(verifier, "INDEX_RAW_SHA256", hashlib.sha256(raw).hexdigest()), \
                 patch.object(verifier, "INDEX_SHA256", index["index_sha256"]):
                with self.assertRaisesRegex(ValueError, "Compressed report"):
                    verifier.verify(directory, replay_receipt_path=None)

    def test_wrong_source_revision_rejected_before_reports(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            index, raw, summaries, reports = self._fixture(directory)
            index["source_before"]["revision"] = "f" * 40
            index["index_sha256"] = proof._digest(
                {k: v for k, v in index.items() if k != "index_sha256"})
            raw = json.dumps(index, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
            (directory / "index.json").write_bytes(raw)
            self._patches(index, summaries, reports)
            with patch.object(verifier, "INDEX_RAW_SHA256", hashlib.sha256(raw).hexdigest()), \
                 patch.object(verifier, "INDEX_SHA256", index["index_sha256"]), \
                 patch.object(verifier, "_read_gzip",
                              side_effect=AssertionError("source before payload")):
                with self.assertRaisesRegex(ValueError, "source snapshot"):
                    verifier.verify(directory, replay_receipt_path=None)

    def test_full_saved_replay_receipt_binds_reports_without_running_replay(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            index, pilot_raw, _, reports = self._fixture(directory)
            pilot_sha = hashlib.sha256(pilot_raw).hexdigest()
            index["index_sha256"] = verifier.INDEX_SHA256
            receipt = self._receipt(index, reports, pilot_sha)
            raw = json.dumps(receipt, sort_keys=True, indent=2).encode() + b"\n"
            path = directory / "replay-receipt.json"
            path.write_bytes(raw)
            with patch.object(verifier, "REPLAY_RECEIPT_RAW_SHA256", hashlib.sha256(raw).hexdigest()), \
                 patch.object(verifier, "REPLAY_RECEIPT_SHA256", receipt["receipt_sha256"]):
                loaded_raw, loaded = verifier._read_replay_receipt(path)
                result = verifier._validate_replay_receipt(loaded, pilot_raw, index, directory)
            self.assertEqual(loaded_raw, raw)
            self.assertEqual(result["replays"], 3)
            self.assertEqual(result["training_calls"], 0)

    def test_replay_receipt_mutations_fail_report_binding(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            index, pilot_raw, _, reports = self._fixture(directory)
            index["index_sha256"] = verifier.INDEX_SHA256
            receipt = self._receipt(index, reports, hashlib.sha256(pilot_raw).hexdigest())
            for mutation, error in (
                (lambda r: r["replays"][0]["result"].update(training_calls=1), "training"),
                (lambda r: r["replays"][0]["input_file"].update(raw_sha256="0" * 64), "input file"),
                (lambda r: r["replays"][0]["result"].update(artifact_sha256="0" * 64), "result differs"),
                (lambda r: r["source_before"].update(revision="f" * 40), "source snapshot"),
            ):
                altered = json.loads(json.dumps(receipt))
                mutation(altered)
                with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                    verifier._validate_replay_receipt(altered, pilot_raw, index, directory)

    def test_receipt_requires_exact_zero_calls_and_well_formed_runtime(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            index, pilot_raw, _, reports = self._fixture(directory)
            index["index_sha256"] = verifier.INDEX_SHA256
            receipt = self._receipt(index, reports, hashlib.sha256(pilot_raw).hexdigest())
            for mutate, message in (
                (lambda value: value.pop("training_calls"), "training call"),
                (lambda value: value.update(training_calls=1), "training call"),
                (lambda value: value.update(training_calls=True), "training call"),
                (lambda value: value.update(runtime={"python": "3.14"}), "runtime"),
            ):
                altered = json.loads(json.dumps(receipt))
                mutate(altered)
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    verifier._validate_replay_receipt(altered, pilot_raw, index, directory)


if __name__ == "__main__":
    unittest.main()
