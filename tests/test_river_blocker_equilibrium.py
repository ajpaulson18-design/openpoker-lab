"""Independent blocker-law anchors and saved-witness adversarial checks."""
import copy
import json
import unittest
import uuid
from fractions import Fraction as F
from pathlib import Path
from unittest.mock import patch
from scripts import turn_river_validation as rules
from scripts import verify_river_blocker_equilibrium as verify
from scripts.river_blocker_fixture import FIXTURE

ROOT = Path(__file__).resolve().parents[1]

class BlockerLawTests(unittest.TestCase):
    def setUp(self):
        board = rules.cards(FIXTURE["board"])
        self.worlds, selected = rules._worlds(
            board, tuple(rules.expand_range(FIXTURE[p], board) for p in ("oop","ip")), None)
        self.assertEqual(selected, ())
        self.joint = {tuple("".join(h) for h in w["hands"]):(w["weight"],w["sign"]) for w in self.worlds}

    def test_literal_compatible_mass_and_showdown_signs(self):
        self.assertEqual(F(1,2)*F(3,4)+1+F(3,4), F(17,8))
        self.assertEqual(self.joint, {
            ("AhAs","KcKd"):(F(3,17),1),
            ("KhKs","AdAs"):(F(8,17),-1),
            ("KhKs","KcKd"):(F(6,17),0)})
        self.assertEqual(sum((v[0] for v in self.joint.values()),F(0)),1)
        self.assertNotIn(("AhAs","AdAs"),self.joint)

    def test_marginals_and_all_own_hand_posteriors(self):
        marginals=[{},{}]
        for pair,(mass,_) in self.joint.items():
            for p in (0,1):
                marginals[p][pair[p]]=marginals[p].get(pair[p],F(0))+mass
        self.assertEqual(marginals,[{"AhAs":F(3,17),"KhKs":F(14,17)},
                                    {"AdAs":F(8,17),"KcKd":F(9,17)}])
        for marginal in marginals: self.assertEqual(sum(marginal.values()),1)
        actual={}
        for p in (0,1):
            for hand,marginal in marginals[p].items():
                actual[p,hand]={pair[1-p]:mass/marginal for pair,(mass,_) in self.joint.items() if pair[p]==hand}
        self.assertEqual(actual,{
            (0,"AhAs"):{"KcKd":F(1)},
            (0,"KhKs"):{"AdAs":F(4,7),"KcKd":F(3,7)},
            (1,"AdAs"):{"KhKs":F(1)},
            (1,"KcKd"):{"AhAs":F(1,3),"KhKs":F(2,3)}})
        for posterior in actual.values(): self.assertEqual(sum(posterior.values()),1)

    def test_factorized_conditioned_marginals_are_wrong(self):
        left={"AhAs":F(3,17),"KhKs":F(14,17)}
        right={"AdAs":F(8,17),"KcKd":F(9,17)}
        product={(a,b):x*y for a,x in left.items() for b,y in right.items()}
        self.assertEqual(sum(product.values()),1)
        self.assertEqual(product["AhAs","AdAs"],F(24,289))
        compatible=sum(v for key,v in product.items() if key!=("AhAs","AdAs"))
        self.assertEqual(compatible,F(265,289))
        conditioned={key:v/compatible for key,v in product.items() if key!=("AhAs","AdAs")}
        self.assertEqual(conditioned,{("AhAs","KcKd"):F(27,265),
            ("KhKs","AdAs"):F(112,265),("KhKs","KcKd"):F(126,265)})
        self.assertNotEqual(conditioned,{key:v[0] for key,v in self.joint.items()})

class WitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Positive proof runs before negative cases: malformed input must not
        # appear to pass merely because an unrelated provenance check fails.
        cls.report=verify.verify_saved_artifact()

    def reject(self, edit):
        report=copy.deepcopy(self.report)
        edit(report)
        path=ROOT/("river-blocker-test-"+uuid.uuid4().hex+".json")
        try:
            path.write_text(json.dumps(report),encoding="utf-8")
            with self.assertRaises((ValueError,KeyError,TypeError,IndexError)):
                verify.verify_saved_artifact(path)
        finally:
            path.unlink(missing_ok=True)

    def test_untouched_witness_and_information_scope(self):
        row=self.report["results"][0]
        self.assertEqual(row["exact"]["metrics"]["nash_conv"],"0")
        self.assertEqual(len(row["rational_strategy"]),36)
        keys=[(r["player"],r["hand"],tuple(r["history"])) for r in row["rational_strategy"]]
        self.assertEqual(len(set(keys)),36)
        self.assertEqual({r["hand"] for r in row["rational_strategy"] if r["player"]=="ip"},{"AdAs","KcKd"})

    def test_false_zero_metrics(self):
        def edit(r):
            row=r["results"][0]
            for name in row["exact"]["metrics"]: row["exact"]["metrics"][name]="0"
            for name in ("lower_value_bound","upper_value_bound"): row["exact"][name]="0"
            for name in ("lower_lp","upper_lp"):
                row[name]["objective"]=row[name]["objective_bound_fraction"]="0"
                row[name]["dual_flow_values"]["fractions"]=["0"]*len(row[name]["dual_flow_values"]["fractions"])
        self.reject(edit)

    def test_each_payoff_and_flow_matrix(self):
        for name in ("payoff_matrix","flow_matrix"):
            with self.subTest(matrix=name):
                def edit(r):
                    r["results"][0][name][0][0]="999"
                self.reject(edit)
        def change_ip_flow(r):
            row=r["results"][0]
            offset=sum(label["player"]==0 for label in row["flow_labels"])
            row["flow_matrix"][offset][0]="999"
        self.reject(change_ip_flow)

    def test_blocked_pair_fixture_substitution(self):
        self.reject(lambda r:r["results"][0]["fixture"].update(ip="AcAd:1,KcKd:0.75"))

    def test_hidden_opponent_split_row_is_rejected(self):
        def edit(r):
            rows=r["results"][0]["rational_strategy"]
            source=next(row for row in rows if row["player"]=="ip" and row["hand"]=="KcKd")
            leaked=copy.deepcopy(source)
            # A second different decision for the same own-hand/public-history
            # identity cannot be stored as a separate hidden-opponent policy.
            for i,action in enumerate(leaked["actions"]):
                action["probability_fraction"]=str(F(i==0))
                action["probability"]=float(i==0)
            rows.append(leaked)
        self.reject(edit)

    def test_bad_realization_and_dual_slack(self):
        for field in ("own_realization","inequality_slacks","dual_flow_values"):
            with self.subTest(field=field):
                self.reject(lambda r:r["results"][0]["lower_lp"][field]["fractions"].__setitem__(0,"-999"))

    def test_noncanonical_rational(self):
        self.reject(lambda r:r["results"][0]["lower_lp"].update(objective="0/2"))

    def test_invalid_typed_resource_counter(self):
        for value in (True,-1,10000001):
            self.reject(lambda r:r["results"][0]["lower_lp"].update(logical_cell_updates=value))

    def test_missing_and_duplicate_games(self):
        self.reject(lambda r:r.update(results=[]))
        self.reject(lambda r:r["results"].append(copy.deepcopy(r["results"][0])))

    def test_missing_source_pin(self):
        self.reject(lambda r:r["source_sha256"].pop("scripts/river_blocker_fixture.py"))

    def test_historical_commit_does_not_require_local_git_object(self):
        report=copy.deepcopy(self.report)
        report["baseline_git_commit"]="a"*40
        path=ROOT/("river-blocker-test-"+uuid.uuid4().hex+".json")
        try:
            path.write_text(json.dumps(report),encoding="utf-8")
            verify.verify_saved_artifact(path)
        finally:
            path.unlink(missing_ok=True)

    def test_verification_rejects_head_drift(self):
        with patch.object(verify.subprocess,"check_output",side_effect=["a"*40+"\n","b"*40+"\n"]):
            with self.assertRaisesRegex(ValueError,"HEAD changed"):
                verify.verify_saved_artifact()

    def test_changed_frozen_model_is_rejected(self):
        self.reject(lambda r:r["results"][0]["uniform_crosscheck"].update(value_fraction="999"))

if __name__=="__main__":
    unittest.main()
