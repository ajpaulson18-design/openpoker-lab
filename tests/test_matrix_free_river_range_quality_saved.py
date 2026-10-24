"""Saved-only independent replay of the immutable four-policy16x16 study."""
import json,hashlib,unittest
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch
from contextlib import ExitStack
from scripts import benchmark_matrix_free_river_range_quality as r
ROOT=Path(__file__).resolve().parents[1]
ARTIFACT=ROOT/"benchmarks/results/matrix-free-river-range-quality-v1"
HEAD="db6cff583563072938c62e732078988b65e6e0d7"
CLAIM="a3738a714e284468b02fcc96daf3e25c"
EXPECTED_HASHES={
    "report.json": "384a63f99e0d8f99b27236f083fc066ce3160c9d4deb43269816c40e96ac57da",
    "claim.json": "59234ac2515a69084c2b164ec8c88cd60ccc625386724f9d74bdb2e8b6ce615e",
    "status.json": "493124f3cb8fd65cca06af30a8bdd6698c9833222c2e097f08afde981b83cb39",
    "policies/river-unpaired-club-16x16-fractional-short-refund-matrix-free-D0-T10000-D0.json": "22be9a53ed250919f5a6e353474504507e433d4109b110aa1b4c6902f3f7942f",
    "policies/river-unpaired-club-16x16-fractional-short-refund-matrix-free-tail-T20000-D10000.json": "a417c62b110da8ebe6f315dda76b38f8b8d25b01d9309694476d3347a6320da9",
    "policies/river-paired-heart-16x16-rank-extremes-short-refund-matrix-free-D0-T10000-D0.json": "1318525d959cb24a48c830e62559efa1c666a40939900895be9ae829eedbc715",
    "policies/river-paired-heart-16x16-rank-extremes-short-refund-matrix-free-tail-T20000-D10000.json": "861238338321c14231076440f96dfc8fe54741d381aa84cd0c601932b7e9524a"
}
SUPPLEMENT_HASHES={
    "supplemental-ranked-verifier.py": "b09034deb8885199f149f89bcda68c561aa760e05f6eea7506e6248f5fbe5b84",
    "supplemental-ranked-equivalence.json": "c6e26bc57da5646dd111eacaa59a0b182c77fa56d7bb0a33618f83aad7feada1"
}
class SavedMatrixFreeRangeQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if len(EXPECTED_HASHES)!=7:raise AssertionError("All seven primary artifact pins required")
        cls.raw={n:(ARTIFACT/n).read_bytes() for n in EXPECTED_HASHES}
        for n,d in EXPECTED_HASHES.items():
            if hashlib.sha256(cls.raw[n]).hexdigest()!=d:raise AssertionError("artifact digest differs:"+n)
        cls.claim,cls.report,cls.status=(json.loads(cls.raw[n]) for n in ("claim.json","report.json","status.json"))
        cls.manifest=cls.claim["manifest"];r._validate_manifest(cls.manifest)
        cls.cases={c["id"]:c for c in cls.manifest["cases"]}
        cls.runtime=r.ProductionRuntime(ROOT,ROOT/"benchmarks/results/native-river-range-quality-v1",ROOT/"benchmarks/results/native-river-controls-v1")
        cls.policies={};cls.audits={}
        forbidden=[(r,"run"),(r,"run_with_runtime"),(cls.runtime,"call"),(cls.runtime,"preflight"),(cls.runtime,"source_snapshot"),(cls.runtime.native,"validate_backend"),(cls.runtime.native,"train_native_fixed_street")]
        with ExitStack() as stack:
            for owner,name in forbidden:stack.enter_context(patch.object(owner,name,side_effect=AssertionError("saved-only forbidden:"+name)))
            for row in cls.report["profiles"]:
                result=json.loads(cls.raw[row["file"]]);key=(row["case"],row["backend"])
                cls.policies[key]=result
                cls.audits[key]=cls.runtime.audit(result,cls.cases[row["case"]],row)

    def test_all_bytes_fixed_grid_schedule_no_retry_and_complete_raws(self):
        self.assertEqual(len(self.report["profiles"]),4)
        for doc in (self.claim,self.report,self.status):self.assertEqual(doc["claim_id"],CLAIM)
        self.assertEqual(self.report["status"],"completed");self.assertEqual(self.status["phase"],"done")
        self.assertIs(self.claim["retry_permitted"],False);self.assertIs(self.status["retry_permitted"],False)
        for cell,row,admission in zip(self.manifest["calls"],self.report["profiles"],self.claim["preflight_admissions"]):
            for k,v in cell.items():self.assertEqual(row[k],v)
            r._validate_admission(admission,cell)
            result=self.policies[(row["case"],row["backend"])]
            r._validate_return(result,self.cases[row["case"]],cell,admission)
            self.assertEqual(r._json_bytes(result),self.raw[row["file"]])
            self.assertEqual(len(self.raw[row["file"]]),row["bytes"])
            self.assertEqual(hashlib.sha256(self.raw[row["file"]]).hexdigest(),row["sha256"])
            self.assertEqual(result["worlds_materialized"],0)
        self.assertEqual(self.claim["preflight_admissions"],self.report["preflight_admissions"])
        self.assertEqual(self.status["saved_policies"],[{k:row[k] for k in (*self.manifest["calls"][0].keys(),"file","bytes","sha256")} for row in self.report["profiles"]])

    def test_historical_source_and_relevant_audit_helpers_are_pinned(self):
        source=self.claim["source"]
        self.assertEqual(source["head"],HEAD);self.assertEqual(source["status"],"clean")
        self.assertEqual(source,self.report["source"])
        for relative in ("scripts/turn_river_validation.py","scripts/preflop_validation.py","scripts/turn_rational_certificate.py","scripts/benchmark_river_heldout_quality.py","scripts/river_heldout_preflight.py",*r.OWN_FILES):
            raw=(ROOT/relative).read_bytes().replace(b"\r\n",b"\n").replace(b"\r",b"\n")
            self.assertEqual(hashlib.sha256(raw).hexdigest(),source["files"][relative]["normalized_lf_sha256"],relative)
        self.assertGreaterEqual(len(source["files"]),84)
        base=self.runtime.baseline_snapshot()
        self.assertEqual(len(base["policies"]),4);self.assertEqual(base["retained_controls"]["policy_count"],16)
        for field in ("claim_id","evidence_sha256","policies","historical_build_receipt_only","live_native_build_requested"):
            self.assertEqual(base[field],self.claim["baselines"][field])

    def test_all_physical_numeric_and_exact_audits_match_immutable_report(self):
        for row in self.report["profiles"]:
            key=(row["case"],row["backend"]);audit=self.audits[key];stored=row["independent_audit"]
            self.assertEqual(stored["replay_status"],"valid")
            for k,v in audit.items():self.assertEqual(r._json_bytes(v),r._json_bytes(stored[k]),(key,k))
            self.assertEqual(audit["blocked_production_helper_calls"],[])
            self.assertEqual(audit["numeric_metrics"]["nash_conv"]<=.001,row["numeric_target_met"])
            exact=audit["exact_audit"]
            if exact["status"]=="admission-rejected":self.assertIsNone(row["exact_target_met"])
            else:
                self.assertEqual(exact["status"],"admitted")
                m={k:Fraction(v) for k,v in exact["metrics_fraction"].items()}
                r._legal_metric_identities(m,tolerance=Fraction())
                met=m["nash_conv"]<=Fraction(1,1000)
                self.assertEqual(row["exact_target_met"],met)
                self.assertEqual(exact["target_met"],met)
                for mode in ("scan","partition"):
                    g=exact["chance_groupings"][mode]
                    self.assertEqual(g["metrics_fraction"],exact["metrics_fraction"])
                    self.assertLessEqual(g["work"],100000);self.assertLessEqual(g["tree_depth"],64);self.assertLessEqual(g["maximum_fraction_bits"],65536)

    def test_supplemental_ranked_receipt_keeps_original_auditor_separate(self):
        supplement=json.loads((ARTIFACT/"supplemental-ranked-equivalence.json").read_text(encoding="utf-8"))
        for name,expected_digest in SUPPLEMENT_HASHES.items():
            self.assertEqual(hashlib.sha256((ARTIFACT/name).read_bytes()).hexdigest(),expected_digest)
        index=json.loads((ARTIFACT/"index.json").read_text(encoding="utf-8"))
        for entry in index["files"]:
            path=(ARTIFACT/entry["file"]).resolve()
            self.assertTrue(path.is_relative_to(ARTIFACT.resolve()))
            raw=path.read_bytes()
            self.assertEqual(len(raw),entry["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),entry["sha256"])
        self.assertEqual(supplement["status"],"verified")
        self.assertEqual(supplement["source_head"],"949060275f00bbd2f174a05a6de247ece1852e73")
        self.assertEqual(supplement["original_study_claim"],CLAIM)
        self.assertEqual(supplement["training_calls"],0)
        self.assertEqual(supplement["blocked_production_calls"],[])
        self.assertEqual(len(supplement["profiles"]),4)
        for actual,expected in zip(supplement["profiles"],self.report["profiles"]):
            self.assertEqual(actual["policy_sha256"],expected["sha256"])
            self.assertIs(actual["all_eight_metrics_exactly_match_scan_and_partition"],True)
            self.assertIs(actual["all_normalization_rows_and_ledgers_match"],True)
            self.assertEqual(actual["worlds_materialized"],0)
            self.assertLessEqual(actual["work"],100000)

    def test_differences_are_descriptive_and_recomputed_independently(self):
        comparisons=[]
        for case in self.manifest["cases"]:
            old=(case["id"],r.BACKENDS[0]);tail=(case["id"],r.BACKENDS[1])
            c=r._descriptive_difference(self.policies[tail],self.policies[old],self.audits[tail],self.audits[old])
            self.assertEqual(c["kind"],"descriptive-only-different-schedules-and-budgets")
            comparisons.append({"case":case["id"],**c})
        self.assertEqual(comparisons,self.report["descriptive_comparisons"])
        self.assertEqual(comparisons,self.status["descriptive_comparisons"])

if __name__=="__main__":unittest.main()
