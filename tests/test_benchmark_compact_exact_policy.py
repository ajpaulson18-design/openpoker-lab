"""Fixed paired runner gates, actual spies and first-failure preservation."""
from copy import deepcopy
import hashlib
import json
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_compact_exact_policy as study

SOURCE={"commit":"frozen-test-head","status":"","sha256":{"solver.py":"frozen-raw-sha"}}


def payload(mode,full=False):
    pairs=0 if mode=="compact" else 4
    training=0 if full else 1
    h=1326 if full else 2
    ranks=2162 if full else 23
    retained={"whole_request_peak_upper":1000,"entry_limit":25000000,"compact_prior_snapshot_entries_upper":6*(2*h)+32 if mode=="compact" else 0}
    pair={"candidate_pairs_scanned":pairs,"board_scan_work_upper":pairs*154,"output_entry_upper":pairs*8,"quadratic_diagnostic_stage":mode=="expanded"}
    admit={"kernel":{"whole_request_upper_work":100000,"configured_limit":500000000},
        "combined_modeled_work_upper":200000,"whole_request_limit":500000000,"retained_storage":retained,
        "compact_input_snapshot_work_upper":4*(6*(2*h)+32) if mode=="compact" else 0}
    output={"chance_contract":"exact-product-selected-v1","conversion_contract":"exact-product-vectors-binary64-v1",
        "execution_backend":"exact-product-selected-direct-packed-python","info_sets":0 if full else 1200,
        "strategy":[] if full else [{"synthetic_test_row":i} for i in range(1200)],
        "worlds":1070190 if full else 22,"public_states":1 if full else 1462,"decisions":0 if full else 628,
        "candidate_private_pairs":h*h,"pair_runout_preflight_checks":0 if mode=="compact" else 24,
        "operator_census":{"stored_complete_worlds":0,"stored_prefix_pair_edges":0,
            "kernel":{"rank_calls":ranks,"work_units_cumulative":10000},"training":{"calls":training},
            "whole_request_admission":admit,"exact_pair_output":pair},
        **{key:0.0 for key in study.METRICS}}
    if mode=="compact":
        hands=["".join(sorted(hand)) for hand in combinations(tuple(r+s for r in "23456789TJQKA" for s in "cdhs"),2)] if full else ["AdAs","AcAh"]
        output.update(pair_diagnostics=study.FORMATS[mode],chance_input_snapshot={"contract":"exact-product-selected-v1",
            "ranges":[[{"hand":hand,"weight_hex":"0x1.0000000000000p+0"} for hand in hands] for _ in range(2)]})
    else:output.update(private_pair_probabilities=[{} for _ in range(4)],compatible_private_pairs=4)
    return output


def raw_child(name="original",mode="expanded",traced=False,**changes):
    rejected=name==study.FULL_RANGE and mode=="expanded"
    full=name==study.FULL_RANGE
    output={"case":name,"mode":mode,"output_format":study.FORMATS[mode],"iterations":10,"rank_cache_boards":64,
        "traced":traced,"seconds":1.0,"python_allocation_peak_bytes":2048 if traced else None,"python_process_peak_bytes":4096,
        "status":"pretraining-rejected" if rejected else "complete",
        "error":{"type":"ValueError","message":"pair output entry limit exceeded"} if rejected else None,
        "training_calls":0 if full else 1,"pair_query_calls":4 if mode=="expanded" and not full else 0,
        "rank_calls":0 if rejected else (2162 if full else 23),"native_calls":0,
        "payload":None if rejected else payload(mode,full)}
    output.update(changes)
    return output


def process(raw):
    return SimpleNamespace(returncode=0,stdout=json.dumps(raw).encode(),stderr=b"")


def certificate(data=None):
    return {"metrics":{key:"1/2" for key in study.EXACT_METRICS},"threshold":"1/1000","threshold_met":False,
            "source_identity":"four-street-independent-exact-v3","input_policy_canonical_sha256":study._canonical(data),
            "normalized_policy_sha256":"a"*64}


class CompactExactPolicyBenchmarkTests(unittest.TestCase):
    def run_fake(self,out,child_mutation=None,exact_mutation=None,identities=None):
        def child(command,**kwargs):
            name=command[command.index("--child")+1];mode=command[command.index("--mode")+1]
            raw=raw_child(name,mode,"--traced" in command)
            if child_mutation is not None:raw=child_mutation(raw)
            return process(raw)
        def compact(case,data):
            if case["sb_range"]=="random":raise ValueError("each range must contain at most 4 hands")
            exact=certificate(data)
            if exact_mutation is not None:exact=exact_mutation(exact)
            return {"exact_certificate":exact,"physical_model_builds":3,"training_calls":0,"native_calls":0,"production_pair_rows":0,
                "compact_input_canonical_sha256":study._canonical(data),"verification_expansion_canonical_sha256":exact["input_policy_canonical_sha256"]}
        identity_patch=patch.object(study,"_identity",return_value=deepcopy(SOURCE)) if identities is None else patch.object(study,"_identity",side_effect=identities)
        with identity_patch,patch.object(study.subprocess,"run",side_effect=child) as calls, \
             patch.object(study,"expanded_exact",side_effect=lambda case,data:certificate(data)),patch.object(study,"compact_exact",side_effect=compact):
            result=study.run(out)
        return result,calls.call_count

    def test_fixed_alternation_and_separate_traced_and_forced_game_pairs(self):
        self.assertEqual([(name,mode,sample,traced) for name,mode,sample,traced in study.schedule()],
            [("original","expanded",0,False),("original","compact",0,False),
             ("original","compact",1,False),("original","expanded",1,False),
             ("original","expanded",2,False),("original","compact",2,False),
             ("original","expanded","traced",True),("original","compact","traced",True),
             (study.FULL_RANGE,"expanded",0,False),(study.FULL_RANGE,"compact",0,False)])
        full=study.case_for(study.FULL_RANGE)
        self.assertEqual(full["runouts"],["2c3d4h5s6c"])
        self.assertEqual(full["config"]["starting_stack"],[.5,1])
        self.assertEqual(full["sb_range"],full["bb_range"])

    def test_full_pairs_preserve_quality_miss_and_zero_choice_rejections(self):
        with TemporaryDirectory(dir=study.ROOT.parent) as parent:
            out=Path(parent)/"study";result,calls=self.run_fake(out)
            self.assertEqual(result["outcome"],"complete")
            self.assertEqual(calls,10)
            report=json.loads((out/"report.json").read_text())
            self.assertEqual(report["training_calls"],8)
            self.assertEqual(report["pair_query_calls"],16)
            self.assertEqual(report["native_calls"],0)
            self.assertTrue(all(report["checks"].values()))
            self.assertFalse(report["certificates"]["expanded"]["threshold_met"])
            self.assertFalse(report["certificates"]["compact"]["threshold_met"])
            self.assertEqual(report["full_range_certificate_rejection"]["physical_model_builds"],0)
            self.assertEqual(report["structural_comparison"]["compact"]["pair_output"]["candidate_pairs_scanned"],0)
            manifest=json.loads((out/"manifest.json").read_text())
            for name,digest in manifest["sha256"].items():self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),digest)
            self.assertEqual(hashlib.sha256((out/"manifest.json").read_bytes()).hexdigest(),result["manifest_sha256"])

    def test_first_child_failure_and_malformed_json_finish_raw_failure_without_retry(self):
        for response in (SimpleNamespace(returncode=2,stdout=b"partial",stderr=b"first failure"),
                         SimpleNamespace(returncode=0,stdout=b"{broken",stderr=b"json warning")):
            with self.subTest(response=response),TemporaryDirectory(dir=study.ROOT.parent) as parent:
                out=Path(parent)/"study"
                with patch.object(study,"_identity",return_value=deepcopy(SOURCE)),patch.object(study.subprocess,"run",return_value=response) as calls:
                    result=study.run(out)
                self.assertEqual(result["outcome"],"failed");self.assertEqual(calls.call_count,1)
                self.assertEqual((out/"original-expanded-0.json").read_bytes(),response.stdout)
                self.assertEqual((out/"original-expanded-0.stderr.txt").read_bytes(),response.stderr)
                report=json.loads((out/"report.json").read_text())
                self.assertEqual(report["samples"],[]);self.assertIsNone(report["medians_seconds"]["expanded"])
                self.assertTrue((out/"manifest.json").exists())

    def test_child_metadata_and_spy_counter_forgery_reject_before_certification(self):
        changes=({"status":"unknown"},{"native_calls":1},{"training_calls":0},{"pair_query_calls":0},
            {"rank_calls":False},{"output_format":study.FORMATS["compact"]},{"seconds":True},{"python_allocation_peak_bytes":1})
        for changeset in changes:
            with self.subTest(changes=changeset),TemporaryDirectory(dir=study.ROOT.parent) as parent:
                out=Path(parent)/"study"
                def mutate(raw):raw.update(changeset);return raw
                with patch.object(study,"_certificate",side_effect=AssertionError("math before valid child")):
                    result,calls=self.run_fake(out,mutate)
                self.assertEqual(result["outcome"],"failed");self.assertEqual(calls,1)

    def test_compact_actual_pair_query_counter_must_be_zero(self):
        with TemporaryDirectory(dir=study.ROOT.parent) as parent:
            def mutate(raw):
                if raw["mode"]=="compact":raw["pair_query_calls"]=1
                return raw
            result,calls=self.run_fake(Path(parent)/"study",mutate)
            self.assertEqual(result["outcome"],"failed");self.assertEqual(calls,2)

    def test_paired_policy_gain_and_normalized_hash_mismatches_fail(self):
        for kind in ("policy","gain","hash"):
            with self.subTest(kind=kind),TemporaryDirectory(dir=study.ROOT.parent) as parent:
                def mutate(raw):
                    if raw["case"]=="original" and raw["mode"]=="compact":
                        if kind=="policy":raw["payload"]["strategy"][0]={"changed":"policy"}
                        if kind=="gain":raw["payload"]["sb_gain"]=1.0
                    return raw
                def exact_mutation(exact):
                    if kind=="hash":exact["normalized_policy_sha256"]="b"*64
                    return exact
                result,calls=self.run_fake(Path(parent)/"study",mutate,exact_mutation)
                self.assertEqual(result["outcome"],"failed");self.assertEqual(calls,10)

    def test_source_change_before_math_stops_after_raw_call(self):
        with TemporaryDirectory(dir=study.ROOT.parent) as parent:
            out=Path(parent)/"study";changed=dict(SOURCE,commit="changed")
            with patch.object(study,"_certificate",side_effect=AssertionError("math on changed source")):
                result,calls=self.run_fake(out,identities=[deepcopy(SOURCE),changed,changed])
            self.assertEqual(result["outcome"],"failed");self.assertEqual(calls,1)
            report=json.loads((out/"report.json").read_text())
            self.assertEqual(report["failure"]["stage"],"source-changed")
            self.assertIn("source changed before",report["failure"]["prior_failure"]["error"])
            self.assertTrue((out/"original-expanded-0.json").exists())

    def test_certificate_target_metadata_and_input_hash_forgery_reject(self):
        data=payload("expanded")
        for changes in ({"threshold":"1/10"},{"threshold_met":"false"},{"metrics":{"nash_conv":"0"}},
                {"input_policy_canonical_sha256":"b"*64},{"normalized_policy_sha256":"not-a-hash"}):
            with self.subTest(changes=changes),patch.object(study,"expanded_exact",return_value=certificate(data)|changes):
                with self.assertRaises(ValueError):study._certificate("expanded",study.case_for("original"),data)
        compact=payload("compact");exact=certificate(compact)
        forged={"exact_certificate":exact,"physical_model_builds":3,"training_calls":0,"native_calls":0,"production_pair_rows":0,
            "compact_input_canonical_sha256":"b"*64,"verification_expansion_canonical_sha256":exact["input_policy_canonical_sha256"]}
        with patch.object(study,"compact_exact",return_value=forged):
            with self.assertRaisesRegex(ValueError,"hash binding"):study._certificate("compact",study.case_for("original"),compact)

    def test_full_range_symmetry_and_complete_uniform_witness_are_required(self):
        for field in ("value_bb","sb_best_response_value","bb_best_response_value","sb_gain","bb_gain","exploitability"):
            raw=raw_child(study.FULL_RANGE,"compact");raw["payload"][field]=.125
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"symmetry"):
                study._validate_child(raw,study.FULL_RANGE,"compact",False)
        raw=raw_child(study.FULL_RANGE,"compact")
        raw["payload"]["chance_input_snapshot"]["ranges"][0][0]["weight_hex"]=(.5).hex()
        with self.assertRaisesRegex(ValueError,"weight mismatch"):study._validate_child(raw,study.FULL_RANGE,"compact",False)
        raw=raw_child(study.FULL_RANGE,"compact")
        raw["payload"]["chance_input_snapshot"]["ranges"][0][0]=deepcopy(raw["payload"]["chance_input_snapshot"]["ranges"][0][1])
        with self.assertRaisesRegex(ValueError,"holdings"):study._validate_child(raw,study.FULL_RANGE,"compact",False)

    def test_real_small_child_smoke_counts_actual_training_pair_and_rank_calls(self):
        from tests.test_four_street_certificate import _case
        case=_case(sb="AsAd:.7,QsQd:.3",bb="KsKd:.4,JhJd:.6",stacks=[2,2])
        with patch.object(study,"case_for",return_value=case):
            expanded=study.child("original","expanded",False)
            compact=study.child("original","compact",False)
        self.assertEqual(expanded["training_calls"],compact["training_calls"])
        self.assertEqual(compact["training_calls"],1)
        self.assertEqual(expanded["pair_query_calls"],4)
        self.assertEqual(compact["pair_query_calls"],0)
        self.assertEqual(expanded["rank_calls"],compact["rank_calls"])
        self.assertGreater(compact["rank_calls"],0)
        self.assertEqual(expanded["native_calls"],compact["native_calls"])
        self.assertEqual(compact["native_calls"],0)
        self.assertEqual(expanded["payload"]["strategy"],compact["payload"]["strategy"])
        for key in study.METRICS:self.assertEqual(expanded["payload"][key],compact["payload"][key])

    def test_unrelated_value_error_is_not_full_range_admission_evidence(self):
        with patch.object(study,"solve_four_street_exact_selected",side_effect=ValueError("bad terminal identity")):
            with self.assertRaisesRegex(ValueError,"bad terminal identity"):study.child(study.FULL_RANGE,"expanded",False)
        with patch.object(study,"solve_four_street_exact_selected",side_effect=ValueError("serialized pair output entry limit exceeded")):
            result=study.child(study.FULL_RANGE,"expanded",False)
        self.assertEqual(result["status"],"pretraining-rejected")
        self.assertTrue(all(result[key]==0 for key in ("pair_query_calls","training_calls","rank_calls","native_calls")))

    def test_compact_child_pair_spy_detects_a_real_attempt(self):
        def sneaky(request,**kwargs):
            from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
            ExactSelectedRunoutKernel.pair_probability_exact(None,0,0)
        with patch.object(study,"solve_four_street_exact_selected",new=sneaky):
            with self.assertRaisesRegex(AssertionError,"private-pair query"):study.child("original","compact",False)


if __name__=="__main__":unittest.main()
