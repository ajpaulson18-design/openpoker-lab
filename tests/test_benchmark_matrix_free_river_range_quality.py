"""No-training contract and failure controls for the fixed16x16 study."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import benchmark_matrix_free_river_range_quality as r
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=json.loads(r.MANIFEST_PATH.read_text(encoding="utf-8"))

class Runtime(r.ProductionRuntime):
    def source_snapshot(self,head):return {"head":head,"status":"synthetic-no-training"}
    def baseline_snapshot(self):return {"synthetic":True}

class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rt=Runtime(ROOT,ROOT/"benchmarks/results/native-river-range-quality-v1",ROOT/"benchmarks/results/native-river-controls-v1")
        cls.cases={c["id"]:c for c in MANIFEST["cases"]}
        cls.admissions=[];cls.results=[];cls.stub_calls=[]
        def uniform(root,infos,iterations,algorithm="cfrplus",**kwargs):
            cls.stub_calls.append(("old",iterations))
            return {key:[1.0/count]*count for key,count in infos.items()}
        def tail_uniform(root,infos,iterations,discard,**kwargs):
            cls.stub_calls.append(("tail",iterations,discard))
            return {key:[1.0/count]*count for key,count in infos.items()}
        with patch.object(cls.rt.mf,"train_ranked_river",uniform),patch.object(cls.rt.tail,"_train_tail",tail_uniform):
            for cell in MANIFEST["calls"]:
                case=cls.cases[cell["case"]]
                admission=cls.rt.preflight(case,cell)
                r._validate_admission(admission,cell)
                cls.admissions.append(admission)
                result=cls.rt.call(case,cell)
                r._validate_return(result,case,cell,admission)
                cls.results.append(result)

    def runtime(self,fail=None,bad=False,reject=False):
        rt=self.rt
        class Synthetic:
            root=ROOT
            def __init__(self):self.calls=0;self.audits=0
            source_snapshot=staticmethod(lambda head:{"head":head})
            baseline_snapshot=staticmethod(lambda:{"fixture":True})
            def preflight(self,case,cell):return copy.deepcopy(LifecycleTests.admissions[MANIFEST["calls"].index(cell)])
            def call(self,case,cell):
                self.calls+=1
                if self.calls==fail:raise RuntimeError("synthetic trainer failure")
                result=copy.deepcopy(LifecycleTests.results[self.calls-1])
                if bad and self.calls==1:result["iterations"]=True
                return result
            def audit(self,result,case,cell):
                self.audits+=1
                if self.calls!=4:raise AssertionError("audit before raw4")
                if reject:
                    admission=LifecycleTests.admissions[MANIFEST["calls"].index(cell)]
                    return {"world_count":admission["compatible_pairs"],"information_sets":admission["information_sets"],"public_decision_nodes":admission["public_nodes"],"independent_physical_model":admission["independent_physical_model"],"numeric_metrics":{m:result[m] for m in r.METRICS},"exact_audit":{"status":"admission-rejected","target_met":None},"quality_gate":None}
                return rt.audit(result,case,cell)
        return Synthetic()

    def run_fixture(self,rt):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"attempt"
            report=r.run_with_runtime(rt,MANIFEST,out,"a"*40)
            self.assertEqual(len(list((out/"policies").glob("*.json"))),4)
            self.assertTrue(all(p["bytes"]>0 for p in report["profiles"]))
            return report

    def test_real_api_uniform_profiles_pass_physical_exact_lifecycle(self):
        rt=self.runtime();report=self.run_fixture(rt)
        self.assertEqual(rt.calls,4);self.assertEqual(rt.audits,4)
        self.assertEqual(report["status"],"completed",[(p["backend"],p["independent_audit"].get("failure")) for p in report["profiles"]])
        self.assertTrue(all(p["independent_audit"]["blocked_production_helper_calls"]==[] for p in report["profiles"]))
        self.assertTrue(all(x["kind"]=="descriptive-only-different-schedules-and-budgets" for x in report["descriptive_comparisons"]))
        self.assertEqual(self.stub_calls,[("old",10000),("tail",20000,10000)]*2)

    def test_serializable_bad_metadata_retained_other_audits_continue(self):
        rt=self.runtime(bad=True);report=self.run_fixture(rt)
        self.assertEqual(report["status"],"completed-with-audit-errors")
        self.assertEqual(rt.audits,3);self.assertEqual(rt.calls,4)
        self.assertIsNone(report["profiles"][0]["exact_target_met"])

    def test_exact_capacity_rejection_is_unknown(self):
        report=self.run_fixture(self.runtime(reject=True))
        self.assertTrue(all(p["exact_target_met"] is None for p in report["profiles"]))

    def test_trainer_failure_preserves_first_raw_without_retry(self):
        rt=self.runtime(fail=2)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"attempt"
            with self.assertRaisesRegex(RuntimeError,"synthetic trainer failure"):
                r.run_with_runtime(rt,MANIFEST,out,"a"*40)
            self.assertEqual(rt.calls,2);self.assertEqual(rt.audits,0)
            self.assertEqual(len(list((out/"policies").glob("*.json"))),1)
            self.assertIs(json.loads((out/"failure.json").read_text())["retry_permitted"],False)
            with self.assertRaises(FileExistsError):r.run_with_runtime(rt,MANIFEST,out,"a"*40)

    def test_retained_baselines_authenticate_from_current_checkout(self):
        snap=r.ProductionRuntime.baseline_snapshot(self.rt)
        self.assertEqual(len(snap["policies"]),4)
        self.assertEqual(snap["retained_controls"]["policy_count"],16)
        self.assertIs(snap["live_native_build_requested"],False)

    def test_comparison_failure_keeps_all_independent_accuracy_results(self):
        rt=self.runtime(reject=True)
        with patch.object(r,"_descriptive_difference",side_effect=ValueError("comparison fixture")):
            report=self.run_fixture(rt)
        self.assertEqual(report["status"],"completed")
        self.assertTrue(all(p["independent_audit"]["replay_status"]=="valid" for p in report["profiles"]))
        self.assertTrue(all(c["kind"]=="invalid-comparison" for c in report["descriptive_comparisons"]))

    def test_manifest_and_admission_type_tampering_rejected(self):
        changed=copy.deepcopy(MANIFEST);changed["calls"][0]["iterations"]=9999
        with self.assertRaises(ValueError):r._validate_manifest(changed)
        bad=copy.deepcopy(self.admissions[0]);bad["hand_state_pass_work"]=True
        with self.assertRaises(ValueError):r._validate_admission(bad,MANIFEST["calls"][0])
        result=copy.deepcopy(self.results[1]);result["average_weight_sum"]=True
        with self.assertRaises(ValueError):r._validate_return(result,self.cases[MANIFEST["calls"][1]["case"]],MANIFEST["calls"][1],self.admissions[1])

if __name__=="__main__":unittest.main()
