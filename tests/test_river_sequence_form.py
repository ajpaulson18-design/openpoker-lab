"""Adversarial checks for exact fixed-river sequence-form witnesses."""
import copy
from fractions import Fraction as F
import json
import subprocess
from pathlib import Path
import unittest
from unittest import mock
from uuid import uuid4
from scripts import river_sequence_form as search
from scripts import verify_river_sequence as proof

class SequenceWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = proof.verify_saved_artifact(search.OUTPUT)

    def test_committed_certificate_reconstructs_both_exact_equilibria(self):
        verified = proof.verify_saved_artifact(search.OUTPUT)
        values = {row["scenario"]: F(row["exact"]["metrics"]["value_oop"])
                  for row in verified["results"]}
        self.assertEqual(values, {"river-polarised-bluffcatcher": F(25),
                                 "river-weighted-raises": F(-43339,2163)})

    def _reject(self, mutate):
        saved = copy.deepcopy(self.saved)
        mutate(saved)
        directory = search.REPO / "work" / ("sequence-test-" + uuid4().hex)
        directory.mkdir(parents=True)
        path = directory / "candidate.json"
        try:
            path.write_text(json.dumps(saved),encoding="utf-8")
            with self.assertRaises((ValueError,KeyError,IndexError)):
                proof.verify_saved_artifact(path)
        finally:
            path.unlink(missing_ok=True)
            directory.rmdir()

    def test_duplicate_and_missing_games_reject(self):
        self._reject(lambda s: s["results"].append(copy.deepcopy(s["results"][0])))
        self._reject(lambda s: s["results"].pop())

    def test_altered_payoff_and_flow_equations_reject(self):
        self._reject(lambda s: s["results"][1]["payoff_matrix"][0].__setitem__(0,"1"))
        self._reject(lambda s: s["results"][1]["flow_matrix"][0].__setitem__(0,"0"))

    def test_internally_consistent_fake_zero_value_rejects(self):
        def mutate(saved):
            row=saved["results"][1]
            row["exact"]["metrics"]={key:"0" for key in row["exact"]["metrics"]}
            for name in ("lower_lp","upper_lp"):
                row[name]["objective"]="0"
                row[name]["objective_bound_fraction"]="0"
                row[name]["dual_flow_values"]["fractions"]=["0"]*len(row[name]["dual_flow_values"]["fractions"])
        self._reject(mutate)

    def test_altered_realization_and_dual_slacks_reject(self):
        self._reject(lambda s: s["results"][1]["lower_lp"]["own_realization"]["fractions"].__setitem__(0,"0"))
        self._reject(lambda s: s["results"][1]["upper_lp"]["inequality_slacks"]["fractions"].__setitem__(0,"-1"))

    def test_negative_and_missing_rational_strategy_reject(self):
        self._reject(lambda s: s["results"][1]["rational_strategy"][0]["actions"][0].__setitem__("probability_fraction","-1/2"))
        self._reject(lambda s: s["results"][1]["rational_strategy"].pop())

    def test_exact_simplex_degeneracy_and_redundant_zero_row(self):
        # x=1, a redundant 0=0 row; no artificial variable may survive.
        rows=[[F(1),F(1),F(0)],[F(0),F(0),F(1)]]
        lp=search._Simplex(rows,[F(1),F(0)],["x","art0","art1"],[F(1),F(0),F(0)],[1,2],"tiny")
        result=lp.solve([F(1),F(0),F(0)])
        self.assertEqual(result["objective"],1)
        self.assertEqual(result["values"][0],1)
        self.assertEqual(result["phase_one_objective"],0)

    def test_infeasible_and_unbounded_lp_reject(self):
        # -x=1 is infeasible for x>=0.
        lp=search._Simplex([[F(-1),F(1)]],[F(1)],["x","art"],[F(0),F(0)],[1],"infeasible")
        with self.assertRaisesRegex(search._Limit,"infeasible"):
            lp.solve([F(0),F(0)])
        # Only redundant 0=0 remains; maximize unconstrained x.
        lp=search._Simplex([[F(0),F(1)]],[F(0)],["x","art"],[F(1),F(0)],[1],"unbounded")
        with self.assertRaisesRegex(search._Limit,"unbounded"):
            lp.solve([F(1),F(0)])

    def test_work_pivot_bit_and_allocation_caps_fail_closed(self):
        def tiny():
            return search._Simplex([[F(1),F(1)]],[F(1)],["x","art"],[F(1),F(0)],[1],"bounded")
        with mock.patch.dict(search.CAPS,updates=0):
            with self.assertRaises(search._Limit): tiny()
        with mock.patch.dict(search.CAPS,pivots=0):
            with self.assertRaises(search._Limit): tiny().solve([F(1),F(0)])
        with mock.patch.dict(search.CAPS,cells=0):
            with self.assertRaises(search._Limit): tiny()
        with mock.patch.dict(search.CAPS,bits=1):
            with self.assertRaises(search._Limit):
                search._Simplex([[F(2),F(1)]],[F(1)],["x","art"],[F(1),F(0)],[1],"bits")

    def test_saved_scope_and_resource_counter_tampering_reject(self):
        self._reject(lambda s: s.__setitem__("certificate_id","unrestricted"))
        self._reject(lambda s: s["results"][1]["lower_lp"].__setitem__("pivots",513))


    def test_metadata_and_normalization_tampering_reject(self):
        self._reject(lambda s: s["results"][1]["information_sets"].pop())
        self._reject(lambda s: s["results"][1]["sequences"][0][1].__setitem__("parent","forged"))
        self._reject(lambda s: s["results"][1]["exact"]["normalization_ledger"][0]["actions"][0].__setitem__("adjustment_fraction","1"))
        self._reject(lambda s: s["results"][1]["lower_lp"].__setitem__("pivots",-1))
        self._reject(lambda s: s["results"][1]["lower_lp"].__setitem__("pivots",True))
        self._reject(lambda s: s["results"][1]["rational_strategy"][0]["actions"][0].__setitem__("probability_fraction",False))

    def test_verification_detects_source_and_head_changes_during_full_proof(self):
        inputs=proof._inputs()
        with mock.patch.object(proof,"_inputs",side_effect=[inputs,{**inputs,"late-change":"0"*64}]):
            with self.assertRaisesRegex(ValueError,"Sources changed"):
                proof.verify_saved_artifact(search.OUTPUT)
        head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=search.REPO,text=True).strip()
        with mock.patch.object(proof.subprocess,"check_output",side_effect=[head,"f"*40]):
            with self.assertRaisesRegex(ValueError,"HEAD changed"):
                proof.verify_saved_artifact(search.OUTPUT)

    def test_generation_source_and_head_guards_preserve_saved_report(self):
        def cached(model,kind):
            row=next(item for item in self.saved["results"] if item["scenario"]==model["fixture"]["id"])
            lp=copy.deepcopy(row["lower_lp" if kind=="oop_guarantee" else "upper_lp"])
            for name in ("objective","phase_one_objective"): lp[name]=F(lp[name])
            return (lp,[F(v) for v in lp["own_realization"]["fractions"]],
                    [F(v) for v in lp["dual_flow_values"]["fractions"]],
                    [F(v) for v in lp["inequality_slacks"]["fractions"]])
        original=search.OUTPUT.read_bytes()
        inputs=search._inputs()
        with mock.patch.object(search,"_solve_lp",side_effect=cached), mock.patch.object(
                search,"_inputs",side_effect=[inputs,{**inputs,"late-change":"0"*64}]):
            with self.assertRaisesRegex(RuntimeError,"inputs/source changed"):
                search.run_feasibility()
        self.assertEqual(search.OUTPUT.read_bytes(),original)
        head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=search.REPO,text=True).strip()
        with mock.patch.object(search,"_solve_lp",side_effect=cached), mock.patch.object(
                search.subprocess,"check_output",side_effect=[head,"f"*40]):
            with self.assertRaisesRegex(RuntimeError,"HEAD changed"):
                search.run_feasibility()
        self.assertEqual(search.OUTPUT.read_bytes(),original)

    def test_historical_generation_commit_does_not_need_to_exist(self):
        saved=copy.deepcopy(self.saved)
        saved["baseline_git_commit"]="a"*40
        directory=search.REPO/"work"/("sequence-history-"+uuid4().hex)
        directory.mkdir(parents=True)
        path=directory/"candidate.json"
        try:
            path.write_text(json.dumps(saved),encoding="utf-8")
            self.assertEqual(proof.verify_saved_artifact(path)["baseline_git_commit"],"a"*40)
        finally:
            path.unlink(missing_ok=True)
            directory.rmdir()

    def test_oversized_matrix_rejects_before_dense_conversion(self):
        self._reject(lambda s: s["results"][1]["payoff_matrix"].append(["not-a-fraction"]))


    def test_prior_certificate_bytes_are_pinned(self):
        prior=search.REPO/"benchmarks/results/river-rational-certificate-v1.json"
        original=Path.read_bytes
        def changed(path):
            raw=original(path)
            return raw+b" " if path==prior else raw
        with mock.patch.object(Path,"read_bytes",new=changed):
            with self.assertRaisesRegex(ValueError,"Prior river certificate hash differs"):
                proof.verify_saved_artifact(search.OUTPUT)

if __name__ == "__main__":
    unittest.main()
