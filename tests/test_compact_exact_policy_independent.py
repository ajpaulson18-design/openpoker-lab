"""Independent compact-policy witness, pair-free production and replay controls."""
from contextlib import ExitStack
from copy import deepcopy
import json
import hashlib
from zipfile import ZipFile
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from scripts import exact_selected_compact_certificate as compact_certificate
from scripts import four_street_certificate_v3 as unchanged_certificate
from scripts import four_street_validation as physical
from tests.test_exact_selected_solver import request_from_case

ROOT=Path(__file__).resolve().parents[1]
METRICS=("value_sb","value_bb","sb_best_response_value","bb_best_response_value",
         "sb_gain","bb_gain","nash_conv","exploitability")


class CompactExactPolicyIndependentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base=json.loads((ROOT/"benchmarks/four-street-integration-v1.json").read_text())["case"]
        cls.case=dict(base,id="compact-independent-weighted-control",sb_range="AsAd:1,AhAc:.25",bb_range="KsKd:1,KcKh:.5",
                      runouts=["2c3c4d7h8h","2c3c4d7hKc"])
        req=request_from_case(cls.case)
        cls.expanded=solve_four_street_exact_selected(req)
        with patch.object(ExactSelectedRunoutKernel,"pair_probability_exact",side_effect=AssertionError("production pair scan")):
            cls.compact=solve_four_street_exact_selected(req,pair_diagnostics="compact")

    def test_compact_preserves_complete_weighted_policy_and_metrics_without_pairs(self):
        self.assertEqual(self.compact["strategy"],self.expanded["strategy"])
        for key in METRICS:
            self.assertEqual(self.compact[key],self.expanded[key],key)
        self.assertNotIn("private_pair_probabilities",self.compact)
        self.assertNotIn("compatible_private_pairs",self.compact)
        output=self.compact["operator_census"]["exact_pair_output"]
        self.assertEqual(output["candidate_pairs_scanned"],0)
        self.assertEqual(output["board_scan_work_upper"],0)
        self.assertEqual(output["output_entry_upper"],0)
        self.assertFalse(output["quadratic_diagnostic_stage"])
        self.assertGreater(self.expanded["operator_census"]["exact_pair_output"]["candidate_pairs_scanned"],0)
        self.assertEqual(sum(map(len,self.compact["chance_input_snapshot"]["ranges"])),4)

    def test_unchanged_exact_oracle_metrics_and_actual_model_build_count(self):
        original=physical.build_model
        builds=[]
        def counted(*args,**kwargs):
            builds.append(1)
            return original(*args,**kwargs)
        forbidden=("pokerlab.exact_selected_solver.solve_four_street_exact_selected",
            "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact",
            "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.terminal_values_exact",
            "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.joint_marginals_exact",
            "pokerlab.selected_operator_solver.solve_four_street_operator",
            "pokerlab.preflop_solver.solve_preflop","pokerlab.packed_operator_cfr.train_packed","subprocess.Popen")
        with ExitStack() as stack:
            for target in forbidden:
                stack.enter_context(patch(target,side_effect=AssertionError("production call during compact certificate")))
            stack.enter_context(patch.object(physical,"build_model",new=counted))
            actual=compact_certificate.evaluate_exact(self.case,self.compact)
        reference=unchanged_certificate.evaluate_exact(self.case,self.expanded)
        self.assertEqual(actual["exact_certificate"]["metrics"],reference["metrics"])
        self.assertEqual(actual["exact_certificate"]["normalized_policy_sha256"],reference["normalized_policy_sha256"])
        self.assertEqual(len(builds),3)
        self.assertEqual(actual["physical_model_builds"],len(builds))
        self.assertEqual(actual["production_pair_rows"],0)
        self.assertEqual(actual["training_calls"],0)
        self.assertEqual(actual["native_calls"],0)

    def test_compact_and_reconstructed_hashes_bind_actual_payload_bytes(self):
        canonical=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
            ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()
        actual=compact_certificate.evaluate_exact(self.case,self.compact)
        self.assertEqual(actual["compact_input_canonical_sha256"],canonical(self.compact))
        self.assertEqual(actual["verification_expansion_canonical_sha256"],actual["exact_certificate"]["input_policy_canonical_sha256"])
        self.assertNotEqual(actual["compact_input_canonical_sha256"],actual["verification_expansion_canonical_sha256"])
        changed=deepcopy(self.compact)
        changed["scope"] += " Independent review provenance mutation."
        recertified=compact_certificate.evaluate_exact(self.case,changed)
        self.assertEqual(recertified["compact_input_canonical_sha256"],canonical(changed))
        self.assertNotEqual(recertified["compact_input_canonical_sha256"],actual["compact_input_canonical_sha256"])
        self.assertNotEqual(recertified["verification_expansion_canonical_sha256"],actual["verification_expansion_canonical_sha256"])
        self.assertEqual(recertified["exact_certificate"]["normalized_policy_sha256"],actual["exact_certificate"]["normalized_policy_sha256"])

    def test_expanded_default_preserves_frozen_original_study_policy(self):
        archive=ROOT/"benchmarks/results/exact-product-selected-v1/exact-selected-study-v1.zip"
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),
            "9f14a749dab150dc1f676ea3c88eab66faa951c91386b289ab0152df9da702e6")
        with ZipFile(archive) as zipped:
            prior=json.loads(zipped.read("original-t10-0.json"))["payload"]
        case=json.loads((ROOT/"benchmarks/four-street-integration-v1.json").read_text())["case"]
        actual=solve_four_street_exact_selected(request_from_case(case),rank_cache_boards=64)
        for key in ("strategy","private_pair_probabilities","compatible_private_pairs","worlds","info_sets",*METRICS):
            self.assertEqual(actual[key],prior[key],key)
        self.assertNotIn("pair_diagnostics",actual)
        self.assertNotIn("chance_input_snapshot",actual)

    def test_malformed_compact_witness_rejects_before_physical_model(self):
        variants=[]
        p=deepcopy(self.compact);p["chance_input_snapshot"]["ranges"][0].append(deepcopy(p["chance_input_snapshot"]["ranges"][0][0]));variants.append(p)
        p=deepcopy(self.compact);p["chance_input_snapshot"]["ranges"][0][0]["weight_hex"]=(.5).hex();variants.append(p)
        p=deepcopy(self.compact);p["chance_input_snapshot"]["ranges"][0][0]["weight_hex"]="0x1p+0";variants.append(p)
        p=deepcopy(self.compact);p["chance_input_snapshot"]["ranges"][0][0]["weight_hex"]="x"*65;variants.append(p)
        p=deepcopy(self.compact);p["chance_input_snapshot"]["ranges"][0][0]["hand"]="AsAs";variants.append(p)
        p=deepcopy(self.compact);p["chance_input_snapshot"]["ranges"][0]=p["chance_input_snapshot"]["ranges"][0]*3;variants.append(p)
        p=deepcopy(self.compact);p["chance_input_snapshot"]["ranges"]=[[{}]]*3;variants.append(p)
        p=deepcopy(self.compact);p["chance_input_snapshot"]["extra"]="unaudited";variants.append(p)
        p=deepcopy(self.compact);p["private_pair_probabilities"]=[];variants.append(p)
        for index,payload in enumerate(variants):
            with self.subTest(index=index),patch.object(physical,"build_model",side_effect=AssertionError("physical allocation before invalid witness rejected")):
                with self.assertRaises(ValueError):
                    compact_certificate.evaluate_exact(self.case,payload)

    def test_oversize_or_hostile_payload_rejects_before_any_physical_build(self):
        oversized=deepcopy(self.compact);oversized["strategy"]=[{}]*(physical.MAX_ROWS+1)
        nested=deepcopy(self.compact)
        child={};nested["unknown_nested"]=child
        for _ in range(45):
            child["next"]={};child=child["next"]
        longtext=deepcopy(self.compact);longtext["unknown_long_string"]="x"*20000
        for payload in (oversized,nested,longtext):
            with self.subTest(keys=list(payload)),patch.object(physical,"build_model",side_effect=AssertionError("model built before payload boundedness")):
                with self.assertRaises(ValueError):
                    compact_certificate.evaluate_exact(self.case,payload)

    def test_forged_boards_future_card_reveal_and_duplicate_policy_cannot_certify(self):
        variants=[]
        payload=deepcopy(self.compact);payload["selected_runouts"][0][-1]="9s";variants.append(payload)
        payload=deepcopy(self.compact);payload["reachable_runouts"]=[];variants.append(payload)
        payload=deepcopy(self.compact);payload["strategy"][0]["revealed_board"]=["2c","3c","4d","7h","8h"];variants.append(payload)
        payload=deepcopy(self.compact);payload["strategy"][-1]=deepcopy(payload["strategy"][0]);variants.append(payload)
        payload=deepcopy(self.compact);payload["strategy"][0]["actions"][0]["amount"]+=1;variants.append(payload)
        for index,payload in enumerate(variants):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    compact_certificate.evaluate_exact(self.case,payload)

    def test_tiny_common_scale_remains_independently_certifiable(self):
        tiny=dict(self.case,id="compact-independent-tiny",sb_range="AsAd:1e-200,AhAc:1e-200",bb_range="KsKd:1e-200,KcKh:1e-200")
        with patch.object(ExactSelectedRunoutKernel,"pair_probability_exact",side_effect=AssertionError("production pair scan")):
            payload=solve_four_street_exact_selected(request_from_case(tiny),pair_diagnostics="compact")
        result=compact_certificate.evaluate_exact(tiny,payload)
        self.assertEqual(result["contract"],"compact-exact-product-certificate-v1")
        self.assertEqual(result["exact_certificate"]["source_identity"],"four-street-independent-exact-v3")
        self.assertTrue(all(item["absolute_difference"]<=1e-9 for item in result["exact_certificate"]["floating_comparison"].values()))


if __name__=="__main__":unittest.main()
