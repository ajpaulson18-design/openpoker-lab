import copy, importlib.util, json, tempfile, unittest
from unittest.mock import patch
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_native_river_range_quality.py"
spec = importlib.util.spec_from_file_location("native_river_quality", SCRIPT)
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
MANIFEST = json.loads((SCRIPT.parents[1] / "benchmarks" / "native-river-range-quality-v1.json").read_text(encoding="utf-8"))


class MockRuntime:
    def __init__(self, base, fail_at=None, parity_miss=False, exact_reject=False, bad_metadata_at=None, tamper_after_audits=False, bad_admission=False):
        self.root=base/"source"; self.build=base/"build"; self.root.mkdir(); self.build.mkdir()
        self.events=[]; self.fail_at=fail_at; self.parity_miss=parity_miss; self.exact_reject=exact_reject; self.bad_metadata_at=bad_metadata_at; self.tamper_after_audits=tamper_after_audits; self.bad_admission=bad_admission; self.calls=0; self.audits=0; self.output=None
    def source_snapshot(self, expected): self.events.append("source"); return {"head":expected,"status":"clean","files":{"pinned":"x"}}
    def build_snapshot(self): self.events.append("build"); return {"manifest_sha256":"mh","manifest":{"compiler":"c","compiler_version":"v","executable":"native.exe","executable_sha256":"eh","flags":["f"],"platform":"p","protocol":"proto","schema_version":1,"source_sha256":"sh","source_lf_sha256":"lh","work_model":"wm"}}
    def preflight(self, case, iterations):
        self.events.append("preflight:"+case["id"])
        if self.output and self.output.exists(): raise AssertionError("claim/output created before all admissions")
        is_a=case["id"]==MANIFEST["cases"][0]["id"]
        worlds,states,nodes,terms,infos,slots,work=(59,24,9,15,72,184,358163824) if is_a else (60,27,10,17,80,208,406411888)
        native={"active_hand_counts":[8,8],"requested_iterations":iterations,"algorithm":"cfrplus","reduction":"public-batched","public_states":states,"world_rows":worlds,"information_action_slots":slots,"total_loop_entries_upper_bound":10,"total_loop_entry_limit":500000000,"native_heap_bytes_upper_bound":10,"native_heap_byte_limit":67108864,"wire_bytes_upper_bound":10,"wire_byte_limit":8388608}
        if self.bad_admission:
            bad={"case_id":case["id"],"iterations":iterations,"candidate_hand_pair_iterations":640000,"world_iterations":600000,"world_node_work":18000000,"dense_hand_state_pass_work":6480648,"worlds":60,"compatible_pairs":60,"public_states":27,"public_nodes":10,"terminal_nodes":17,"information_sets":80,"information_action_slots":208,"prefix_hand_edges":60,"independent_world_count":60,"independent_numeric_modeled_work":3000,"independent_numeric_modeled_work_limit":8000000,"native_tree_nodes":44,"native_tree_max_depth":5,"native_tree_max_actions":4,"native_active_hand_counts":[8,8],"native_shape_admission":native,"trainer_or_build_lookup_called":False}
            if self.bad_admission=="boolean": bad["candidate_hand_pair_iterations"]=True
            elif self.bad_admission=="missing": bad.pop("candidate_hand_pair_iterations")
            else: bad["candidate_hand_pair_iterations"]=-1
            return bad
        return {"case_id":case["id"],"iterations":iterations,"candidate_hand_pair_iterations":640000,"world_iterations":worlds*iterations,"world_node_work":15930000 if is_a else 18000000,"dense_hand_state_pass_work":5760576 if is_a else 6480648,"worlds":worlds,"compatible_pairs":worlds,"public_states":states,"public_nodes":nodes,"terminal_nodes":terms,"information_sets":infos,"information_action_slots":slots,"prefix_hand_edges":worlds,"independent_world_count":worlds,"independent_numeric_modeled_work":3000,"independent_numeric_modeled_work_limit":8000000,"native_tree_nodes":states+terms,"native_tree_max_depth":5,"native_tree_max_actions":4,"native_active_hand_counts":[8,8],"chance_nodes":0,"world_traversal_nodes":7,"tree_actions":18 if is_a else 20,"native_shape_admission":native,"trainer_or_build_lookup_called":False}
    def call(self, case, backend, iterations):
        self.calls+=1; self.events.append("call:"+backend+":"+case["id"])
        if self.fail_at==self.calls: raise RuntimeError("mock trainer failed")
        row={"player":"oop","hand":"AsTc","street":"river","board":[case["board"][i:i+2] for i in range(0,len(case["board"]),2)],"history":[],"actions":[{"name":"check","amount":0,"raise_to":0,"history_key":"check","probability":0.5},{"name":"bet","amount":1,"raise_to":1,"history_key":"bet@1","probability":0.5}]}
        if self.parity_miss and backend=="native": row["actions"][0]["probability"]=0.6; row["actions"][1]["probability"]=0.4
        result={"algorithm":"cfrplus","solver_version":("research-native-river-cfrplus-v1" if backend=="native" else "research-river-tail-adapter-v1"),"strategy_schema":"postflop-strategy-v1","board":[case["board"][i:i+2] for i in range(0,len(case["board"]),2)],"config":case["config"],"iterations":iterations,"requested_iterations":iterations,"discard":0,"source_iteration_window":[1,iterations],"averaged_sweeps":iterations,"average_weight_sum":iterations*(iterations+1)//2,"requested_average_passes":iterations,"requested_regret_passes":2*iterations,"requested_total_traversal_passes":3*iterations,"average_schedule":("native-linear-completed-sweep-own-reach" if backend=="native" else "direct-original-linear-sweep-weight-own-reach-tail"),"update_schedule":"alternating-oop-then-ip","value_oop":0.0,"value_ip":0.0,"oop_best_response_value":0.1,"ip_best_response_value":0.1,"oop_best_response_gain":0.1,"ip_best_response_gain":0.1,"nash_conv":0.2,"exploitability":0.1,"strategy":[row],"worlds":60,"worlds_materialized":60,"deals":60,"compatible_pairs":60,"info_sets":80,"public_nodes":10,"public_states":27,"terminal_nodes":17,"chance_nodes":0,"world_traversal_nodes":7,"tree_actions":20,"training_calls":1,"resource_usage":{"admission":"ok"},"execution_backend":"native-fixed-street-public-batched-river","native_training":{"backend":"native-fixed-street-v1","reduction":"public-batched","native_world_rows":60,"input_sha256":"a"*64,"output_sha256":"b"*64,"admission":{"active_hand_counts":[8,8],"requested_iterations":iterations,"algorithm":"cfrplus","reduction":"public-batched","public_states":27,"world_rows":60,"information_action_slots":208,"total_loop_entries_upper_bound":10,"total_loop_entry_limit":500000000,"native_heap_bytes_upper_bound":10,"native_heap_byte_limit":67108864,"wire_bytes_upper_bound":10,"wire_byte_limit":8388608},"build":{"compiler":"c","compiler_version":"v","executable":"native.exe","executable_sha256":"eh","flags":["f"],"platform":"p","protocol":"proto","schema_version":1,"source_sha256":"sh","source_lf_sha256":"lh","work_model":"wm"}}}
        if backend=="native":
            result["native_training"]["admission"].update({"public_states":24 if case["id"]==MANIFEST["cases"][0]["id"] else 27,"world_rows":59 if case["id"]==MANIFEST["cases"][0]["id"] else 60,"information_action_slots":184 if case["id"]==MANIFEST["cases"][0]["id"] else 208})
            result["native_training"]["native_world_rows"]=59 if case["id"]==MANIFEST["cases"][0]["id"] else 60
        if case["id"]==MANIFEST["cases"][0]["id"]: result.update({"worlds":59,"worlds_materialized":59,"deals":59,"compatible_pairs":59,"info_sets":72,"public_nodes":9,"public_states":24,"terminal_nodes":15,"tree_actions":18})
        if self.bad_metadata_at==self.calls: result["requested_iterations"]=iterations-1
        return result
    def audit(self, result, case, limits):
        self.audits+=1; self.events.append("audit:"+case["id"])
        exact={"status":"admission-rejected","chance_groupings":{"scan":{"status":"admission-rejected"},"partition":{"status":"admission-rejected"}},"target_met":None} if self.exact_reject else {"status":"admitted","chance_groupings":{"scan":{"status":"admitted"},"partition":{"status":"admitted"}},"target_met":True}
        if self.tamper_after_audits and self.audits==4:
            target=next((self.output/"policies").glob("*.json")); target.write_bytes(target.read_bytes()+b" ")
        return {"replay_status":"valid","numeric_metrics":{m:0.0 for m in runner.METRICS},"exact_audit":exact,"exact_audits":exact["chance_groupings"],"quality_gate":exact["target_met"],"world_count":3,"compatible_pairs":3,"information_sets":1,"public_decision_nodes":1,"rank_census":{"ties":0},"action_rows":result["strategy"]}


class NativeRiverRangeQualityTests(unittest.TestCase):
    def run_batch(self, base, rt):
        output=base/"attempt"; rt.output=output
        report=runner.run_with_runtime(rt,MANIFEST,output,"a"*40,rt.build,{"report_sha256":"control","policy_count":16})
        return output,report

    def test_control_corpus_authenticates_report_claim_status_and_sixteen_policies(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); (base/"policies").mkdir(); profiles=[]
            for i in range(8):
                profile={}
                for backend in ("python","native"):
                    name=f"p{i}-{backend}.json"; raw=("policy-"+name).encode(); (base/"policies"/name).write_bytes(raw)
                    profile[backend+"_policy"]={"file":"policies/"+name,"bytes":len(raw),"sha256":runner._sha(raw)}
                profiles.append(profile)
            claim={"claim_id":"claim-x","retry_permitted":False}
            status={"claim_id":"claim-x","status":"completed","retry_permitted":False}
            report={"schema":"compiled-river-conformance-report-v1","status":"completed","claim_id":"claim-x","profiles":profiles}
            rb=runner._pretty(report); cb=runner._pretty(claim); sb=runner._pretty(status)
            (base/"report.json").write_bytes(rb);(base/"claim.json").write_bytes(cb);(base/"status.json").write_bytes(sb)
            with patch.object(runner,"CONTROL_REPORT_SHA256",runner._sha(rb)), patch.object(runner,"CONTROL_CLAIM_SHA256",runner._sha(cb)), patch.object(runner,"CONTROL_STATUS_SHA256",runner._sha(sb)):
                auth=runner.authenticate_control_corpus(base); self.assertEqual(auth["policy_count"],16)
                (base/"policies"/"p7-native.json").write_bytes(b"changed")
                with self.assertRaisesRegex(RuntimeError,"policy hash/size"):
                    runner.authenticate_control_corpus(base)

    def test_boolean_config_and_build_schema_cannot_alias_integer_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            rt=MockRuntime(Path(tmp)); case=MANIFEST["cases"][0]
            result=rt.call(case,"native",10000)
            result["config"]=copy.deepcopy(result["config"])
            result["config"]["max_raises"]=True
            with self.assertRaisesRegex(ValueError,"identity/schema"):
                runner._validate_return(result,case,"native",10000)
            result=rt.call(case,"native",10000)
            expected=copy.deepcopy(result["native_training"]["admission"])
            result["native_training"]["build"]["schema_version"]=True
            with self.assertRaisesRegex(ValueError,"build identity"):
                runner._validate_native_receipt(result,rt.build_snapshot(),expected)

    def test_four_calls_all_admit_and_raw_save_precedes_any_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); rt=MockRuntime(base); output,report=self.run_batch(base,rt)
            self.assertEqual(rt.calls,4); self.assertEqual(rt.audits,4,report["profiles"])
            first_audit=next(i for i,e in enumerate(rt.events) if e.startswith("audit:"))
            last_call=max(i for i,e in enumerate(rt.events) if e.startswith("call:"))
            self.assertGreater(first_audit,last_call)
            self.assertEqual(len(list((output/"policies").glob("*.json"))),4)
            self.assertEqual(report["status"],"completed")
            self.assertEqual(len(report["preflight_admissions"]),4)

    def test_parity_miss_does_not_cancel_independent_target_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); rt=MockRuntime(base,parity_miss=True); _,report=self.run_batch(base,rt)
            self.assertTrue(all(p["quality_gate"] is True for p in report["profiles"]))
            self.assertTrue(all(p["status"]=="failed" for p in report["parity"]))
            self.assertEqual(rt.audits,4)

    def test_exact_capacity_rejection_keeps_target_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); rt=MockRuntime(base,exact_reject=True); _,report=self.run_batch(base,rt)
            self.assertTrue(all(p["quality_gate"] is None for p in report["profiles"]))
            self.assertTrue(all(p["independent_audit"]["exact_audit"]["status"]=="admission-rejected" for p in report["profiles"]))

    def test_trainer_failure_stops_without_retry_and_keeps_prior_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); rt=MockRuntime(base,fail_at=2); output=base/"attempt"; rt.output=output
            with self.assertRaisesRegex(RuntimeError,"mock trainer failed"):
                runner.run_with_runtime(rt,MANIFEST,output,"a"*40,rt.build,{"report_sha256":"control","policy_count":16})
            self.assertEqual(rt.calls,2); self.assertEqual(rt.audits,0)
            self.assertEqual(len(list((output/"policies").glob("*.json"))),1)
            failure=json.loads((output/"failure.json").read_text(encoding="utf-8"))
            status=json.loads((output/"status.json").read_text(encoding="utf-8"))
            self.assertFalse(failure["retry_permitted"]); self.assertFalse(status["retry_permitted"])
            self.assertEqual(len(failure["saved_policies"]),1)

    def test_bad_metadata_is_saved_then_other_policies_still_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); rt=MockRuntime(base,bad_metadata_at=1); output=base/"attempt"; rt.output=output
            report=runner.run_with_runtime(rt,MANIFEST,output,"a"*40,rt.build,{"report_sha256":"control","policy_count":16})
            self.assertEqual(rt.calls,4); self.assertEqual(rt.audits,3)
            self.assertEqual(len(list((output/"policies").glob("*.json"))),4)
            self.assertEqual(report["status"],"completed-with-audit-errors")
            self.assertEqual(report["profiles"][0]["independent_audit"]["replay_status"],"invalid")
            self.assertTrue(all(p["independent_audit"]["replay_status"]=="valid" for p in report["profiles"][1:]))

    def test_negative_boolean_and_missing_admission_stop_before_claim(self):
        for mode in (True,"boolean","missing"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp); rt=MockRuntime(base,bad_admission=mode); output=base/"attempt"; rt.output=output
                with self.assertRaisesRegex(ValueError,"admission"):
                    runner.run_with_runtime(rt,MANIFEST,output,"a"*40,rt.build,{"report_sha256":"control","policy_count":16})
                self.assertFalse(output.exists()); self.assertEqual(rt.calls,0)

    def test_tampered_raw_policy_after_audit_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); rt=MockRuntime(base,tamper_after_audits=True); output=base/"attempt"; rt.output=output
            with self.assertRaisesRegex(RuntimeError,"raw policy receipt changed"):
                runner.run_with_runtime(rt,MANIFEST,output,"a"*40,rt.build,{"report_sha256":"control","policy_count":16})
            self.assertEqual(rt.calls,4); self.assertEqual(rt.audits,4)
            self.assertTrue((output/"failure.json").is_file()); self.assertFalse((output/"report.json").exists())


if __name__ == "__main__": unittest.main()
