"""Independent failure and acceptance controls for the fixed exact-solver study."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_exact_selected_solver as study


SOURCE = {"commit": "frozen-review-head", "status": "", "sha256": {"solver.py": "sha"}}


def valid_child(name="original", iterations=10, traced=False, **changes):
    raw = {"case": name, "iterations": iterations, "traced": traced,
        "status": "complete", "error": None, "seconds": 1.0,
        "python_allocation_peak_bytes": 1024 if traced else None,
        "python_process_peak_bytes": 4096, "training_calls": 1,
        "rank_calls": 2, "native_calls": 0,
        "payload": {"strategy": [], "private_pair_probabilities": [], "chance_contract": "exact-product-selected-v1",
            "conversion_contract": "exact-product-vectors-binary64-v1",
            **{key: 0.0 for key in study.METRICS}}}
    raw.update(changes)
    return SimpleNamespace(returncode=0, stdout=json.dumps(raw).encode(), stderr=b"")


class ExactSolverStudyIndependentReviewTests(unittest.TestCase):
    def run_with_child(self, output, process, *, source_after=None):
        identities = [dict(SOURCE), dict(SOURCE) if source_after is None else source_after]
        with patch.object(study, "_identity", side_effect=identities), \
             patch.object(study.subprocess, "run", return_value=process) as run:
            result = study.run(output)
        return result, run.call_count

    def verify_preserved_failure(self, directory, process):
        self.assertEqual((directory/"original-t10-0.json").read_bytes(),process.stdout)
        self.assertEqual((directory/"original-t10-0.stderr.txt").read_bytes(),process.stderr)
        report=json.loads((directory/"report.json").read_text())
        self.assertEqual(report["outcome"],"failed")
        self.assertIsNotNone(report["failure"])
        self.assertEqual(report["samples"],[])
        manifest=json.loads((directory/"manifest.json").read_text())
        for name,digest in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256((directory/name).read_bytes()).hexdigest(),digest)

    def test_first_child_failure_retains_raw_bytes_and_finishes_failure_record(self):
        process=SimpleNamespace(returncode=2,stdout=b"partial raw output",stderr=b"first child failure")
        with TemporaryDirectory(dir=study.ROOT.parent) as parent:
            output=Path(parent)/"study"
            result,calls=self.run_with_child(output,process)
            self.assertEqual(result["outcome"],"failed")
            self.assertEqual(calls,1)
            self.verify_preserved_failure(output,process)

    def test_malformed_json_retains_first_streams_and_does_not_retry(self):
        process=SimpleNamespace(returncode=0,stdout=b"{broken-json",stderr=b"warning before malformed output")
        with TemporaryDirectory(dir=study.ROOT.parent) as parent:
            output=Path(parent)/"study"
            result,calls=self.run_with_child(output,process)
            self.assertEqual(result["outcome"],"failed")
            self.assertEqual(calls,1)
            self.verify_preserved_failure(output,process)

    def test_unknown_status_and_native_or_training_call_mismatch_reject_first_sample(self):
        for process in (valid_child(status="unknown"),valid_child(native_calls=1),valid_child(training_calls=0),
                        valid_child(python_allocation_peak_bytes=512)):
            with self.subTest(process=process.stdout), TemporaryDirectory(dir=study.ROOT.parent) as parent:
                output=Path(parent)/"study"
                with patch.object(study,"evaluate_exact",side_effect=AssertionError("certification before valid child identity")):
                    result,calls=self.run_with_child(output,process)
                self.assertEqual(result["outcome"],"failed")
                self.assertEqual(calls,1)
                self.verify_preserved_failure(output,process)

    def test_unrelated_value_error_is_not_admission_evidence(self):
        with patch.object(study,"solve_four_street_exact_selected",side_effect=ValueError("corrupt terminal identity")):
            with self.assertRaisesRegex(ValueError,"corrupt terminal identity"):
                study.child("original",1000,False)

    def test_explicit_pretraining_admission_rejection_preserves_zero_call_evidence(self):
        with patch.object(study,"solve_four_street_exact_selected",side_effect=ValueError("whole-request work admission limit exceeded")):
            result=study.child("original",1000,False)
        self.assertEqual(result["status"],"pretraining-rejected")
        self.assertIsNone(result["payload"])
        self.assertEqual(result["error"],{"type":"ValueError","message":"whole-request work admission limit exceeded"})
        self.assertEqual(result["training_calls"],0)
        self.assertEqual(result["rank_calls"],0)
        self.assertEqual(result["native_calls"],0)

    def test_complete_study_records_quality_misses_and_exact_requested_admission_rejection(self):
        def child(command, **kwargs):
            name=command[command.index("--child")+1]
            iterations=int(command[command.index("--iterations")+1])
            traced="--traced" in command
            if name=="original" and iterations==1000:
                return valid_child(name,iterations,traced,status="pretraining-rejected",training_calls=0,rank_calls=0,
                    payload=None,error={"type":"ValueError","message":"whole-request work admission exceeded"})
            if name=="full-range-census":
                return valid_child(name,iterations,traced,training_calls=0,rank_calls=0,
                    payload={"expected_pair_board_occurrences":1070190})
            return valid_child(name,iterations,traced)
        certificate={"threshold_met":False,"metrics":{key:"1/2" for key in study.METRICS},
                     "normalized_policy_sha256":"independent-control-policy"}
        with TemporaryDirectory(dir=study.ROOT.parent) as parent:
            output=Path(parent)/"study"
            with patch.object(study,"_identity",return_value=dict(SOURCE)), \
                 patch.object(study.subprocess,"run",side_effect=child) as run, \
                 patch.object(study,"evaluate_exact",return_value=certificate) as exact:
                result=study.run(output)
            self.assertEqual(result["outcome"],"complete")
            self.assertEqual(run.call_count,10)
            self.assertEqual(exact.call_count,5)
            report=json.loads((output/"report.json").read_text())
            self.assertEqual(report["training_calls"],8)
            self.assertEqual(report["native_calls"],0)
            self.assertTrue(all(value["threshold_met"] is False for value in report["exact_certificates"].values()))
            rejected=[row for row in report["samples"] if row["status"]=="pretraining-rejected"]
            self.assertEqual(len(rejected),1)
            self.assertEqual(rejected[0]["training_calls"],0)
            self.assertEqual(rejected[0]["rank_calls"],0)
            self.assertTrue((output/"original-t10-0-certificate.json").exists())
            self.assertFalse((output/"original-t1000-0-certificate.json").exists())

    def test_metamorphic_metric_or_complete_policy_difference_cannot_be_accepted(self):
        for mutation in ("metric", "gain", "policy", "pairs"):
            def child(command, **kwargs):
                name=command[command.index("--child")+1]
                iterations=int(command[command.index("--iterations")+1])
                traced="--traced" in command
                if name=="original" and iterations==1000:
                    return valid_child(name,iterations,traced,status="pretraining-rejected",training_calls=0,rank_calls=0,
                        payload=None,error={"type":"ValueError","message":"whole-request work admission exceeded"})
                if name=="full-range-census":
                    return valid_child(name,iterations,traced,training_calls=0,rank_calls=0,
                        payload={"expected_pair_board_occurrences":1070190})
                result=valid_child(name,iterations,traced)
                if name=="tiny":
                    raw=json.loads(result.stdout)
                    if mutation=="metric":
                        raw["payload"]["value_sb"]=1.0
                    elif mutation=="gain":
                        raw["payload"]["sb_gain"]=1.0
                    elif mutation=="policy":
                        raw["payload"]["strategy"]=[{"different":"complete row"}]
                    else:
                        raw["payload"]["private_pair_probabilities"]=[{"different":"pair mass"}]
                    result.stdout=json.dumps(raw).encode()
                return result
            certificate={"threshold_met":False,"metrics":{key:"1/2" for key in study.METRICS},
                         "normalized_policy_sha256":"independent-control-policy"}
            with self.subTest(mutation=mutation), TemporaryDirectory(dir=study.ROOT.parent) as parent:
                output=Path(parent)/"study"
                with patch.object(study,"_identity",return_value=dict(SOURCE)), \
                     patch.object(study.subprocess,"run",side_effect=child) as run, \
                     patch.object(study,"evaluate_exact",return_value=certificate):
                    result=study.run(output)
                self.assertEqual(result["outcome"],"failed")
                self.assertEqual(run.call_count,10)
                report=json.loads((output/"report.json").read_text())
                self.assertEqual(report["failure"]["stage"],"metamorphic-policy-checks")
                check={"metric":"common_scale_all_metrics_identical", "gain":"common_scale_all_metrics_identical", "policy":"common_scale_complete_strategy_identical",
                       "pairs":"common_scale_pair_probabilities_identical"}[mutation]
                self.assertFalse(report["checks"][check])
                self.assertTrue((output/"tiny-t10-0.json").exists())

    def test_source_change_before_certificate_prevents_math_and_retains_raw_call(self):
        process=valid_child()
        changed=dict(SOURCE,commit="changed-before-math")
        with TemporaryDirectory(dir=study.ROOT.parent) as parent:
            output=Path(parent)/"study"
            with patch.object(study,"_identity",side_effect=[dict(SOURCE),changed,changed]), \
                 patch.object(study.subprocess,"run",return_value=process) as run, \
                 patch.object(study,"evaluate_exact",side_effect=AssertionError("math entered on changed source")) as exact:
                result=study.run(output)
            self.assertEqual(result["outcome"],"failed")
            self.assertEqual(run.call_count,1)
            exact.assert_not_called()
            report=json.loads((output/"report.json").read_text())
            self.assertEqual(len(report["samples"]),1)
            self.assertEqual(report["failure"]["stage"],"source-changed")
            self.assertIn("source changed before",report["failure"]["prior_failure"]["error"])
            self.assertEqual((output/"original-t10-0.json").read_bytes(),process.stdout)

    def test_source_change_is_preserved_alongside_first_child_failure(self):
        process=SimpleNamespace(returncode=2,stdout=b"partial",stderr=b"first failure")
        changed=dict(SOURCE,commit="changed-after-child")
        with TemporaryDirectory(dir=study.ROOT.parent) as parent:
            output=Path(parent)/"study"
            result,calls=self.run_with_child(output,process,source_after=changed)
            self.assertEqual(result["outcome"],"failed")
            self.assertEqual(calls,1)
            self.assertEqual(json.loads((output/"source-after.json").read_text()),changed)
            report=json.loads((output/"report.json").read_text())
            self.assertEqual(report["failure"]["stage"],"source-changed")
            self.assertIsNotNone(report["failure"]["prior_failure"])


if __name__=="__main__":
    unittest.main()
