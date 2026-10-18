"""Independent toy regression tests for compact sequence-form LPs."""
import copy
import unittest
from fractions import Fraction as F
from unittest.mock import patch

from scripts import river_sequence_form as legacy
from scripts import turn_sequence_compact_lp as compact


def toy_model():
    seqs = [
        [{"id": "oop:empty", "parent": None}, {"id": "oop:a", "parent": "oop:empty"}, {"id": "oop:b", "parent": "oop:empty"}],
        [{"id": "ip:empty", "parent": None}, {"id": "ip:a", "parent": "ip:empty"}, {"id": "ip:b", "parent": "ip:empty"}],
    ]
    infos = [{"one": {}}, {"one": {}}]
    flow = [[F(1),F(0),F(0)],[F(-1),F(1),F(1)]]
    labels = [
        {"id":"oop:root","player":0,"kind":"root","parent_sequence":"oop:empty","rhs":"1"},
        {"id":"oop:one","player":0,"kind":"information_set","parent_sequence":"oop:empty","rhs":"0"},
        {"id":"ip:root","player":1,"kind":"root","parent_sequence":"ip:empty","rhs":"1"},
        {"id":"ip:one","player":1,"kind":"information_set","parent_sequence":"ip:empty","rhs":"0"},
    ]
    return {"A":[[F(2),F(5),F(-4)],[F(3),F(-9),F(-2)],[F(-2),F(-6),F(5)]],
            "flows":flow+flow,"flow_labels":labels,"infos":infos,
            "sequences":seqs,"empty":("oop:empty","ip:empty")}


class CompactSequenceLPTests(unittest.TestCase):
    def test_matching_pennies_exact_anchor_and_full_lp_agreement(self):
        model = toy_model()
        expected = [F(1),F(1,2),F(1,2)]
        lower, x, q, lower_slack = compact.solve_lp(model,"oop_guarantee")
        upper, y, p, upper_slack = compact.solve_lp(model,"ip_ceiling")
        self.assertEqual(x,expected)
        self.assertEqual(y,expected)
        self.assertEqual(q,[F(0),F(-5,2)])
        self.assertEqual(p,[F(0),F(-5,2)])
        self.assertEqual(lower_slack,[F(0)]*3)
        self.assertEqual(upper_slack,[F(0)]*3)
        self.assertEqual(q[0],p[0])
        self.assertEqual(lower["objective"],q[0])
        self.assertEqual(upper["objective"],-p[0])
        self.assertEqual(compact._check_original(model,"oop_guarantee",x,q,lower_slack),F(0))
        self.assertEqual(compact._check_original(model,"ip_ceiling",y,p,upper_slack),F(0))
        full_lower, full_x, full_q, full_lower_slack = legacy._solve_lp(model,"oop_guarantee")
        full_upper, full_y, full_p, full_upper_slack = legacy._solve_lp(model,"ip_ceiling")
        self.assertEqual((full_x,full_q,full_lower_slack),(x,q,lower_slack))
        self.assertEqual((full_y,full_p,full_upper_slack),(y,p,upper_slack))
        self.assertEqual(full_lower["objective"],lower["objective"])
        self.assertEqual(full_upper["objective"],upper["objective"])
        self.assertEqual(sum((a*b for a,b in zip(x,upper_slack)),F(0)),F(0))
        self.assertEqual(sum((a*b for a,b in zip(y,lower_slack)),F(0)),F(0))
        self.assertEqual(_matrix_value(model,x,y),F(0))

    def test_affine_rhs_signs_and_root_dual_coordinates(self):
        model=toy_model()
        lower,*_=compact.solve_lp(model,"oop_guarantee")
        upper,*_=compact.solve_lp(model,"ip_ceiling")
        lower_signs=[row["row_sign"] for row in lower["constraint_labels"] if row["id"].startswith("cover:")]
        upper_signs=[row["row_sign"] for row in upper["constraint_labels"] if row["id"].startswith("cover:")]
        self.assertEqual(lower_signs,[-1,-1,1])
        self.assertEqual(upper_signs,[1,1,-1])
        self.assertIn("ip:root",lower["dual_flow_values"]["flow_labels"])
        self.assertIn("oop:root",upper["dual_flow_values"]["flow_labels"])
        self.assertTrue(lower["empty_sequence_reduction"]["root_free_flow_coordinate_retained"])

    def test_rejects_bad_empty_coordinate_or_root_equation(self):
        model=toy_model()
        model["sequences"][0][0]["id"]="oop:not-empty"
        with self.assertRaises(ValueError): compact.solve_lp(model,"oop_guarantee")
        model=toy_model()
        model["flows"][0]=[F(0),F(1),F(0)]
        with self.assertRaises(ValueError): compact.solve_lp(model,"ip_ceiling")

    def test_preflight_fails_before_tableau_allocation(self):
        model=toy_model()
        extra=300
        model["sequences"][1].extend({"id":f"ip:extra:{i}","parent":"ip:empty"} for i in range(extra))
        model["A"]=[row+[F(0)]*extra for row in model["A"]]
        model["flows"][2]=[F(1)]+[F(0)]*(len(model["sequences"][1])-1)
        model["flows"][3]=[F(-1)]+[F(1)]*(len(model["sequences"][1])-1)
        with patch.object(compact.legacy,"_Simplex") as simplex:
            with self.assertRaises(legacy._Limit): compact.solve_lp(model,"oop_guarantee")
            simplex.assert_not_called()

    def test_redundant_own_flow_is_removed_and_full_flow_is_reconstructed(self):
        model=toy_model()
        model["infos"][0]["duplicate"]={}
        duplicate_label=copy.deepcopy(model["flow_labels"][1])
        duplicate_label["id"]="oop:duplicate-flow"
        model["flow_labels"].insert(2,duplicate_label)
        model["flows"].insert(2,list(model["flows"][1]))
        record,x,q,slacks=compact.solve_lp(model,"oop_guarantee")
        self.assertEqual(compact._check_original(model,"oop_guarantee",x,q,slacks),F(0))
        self.assertLess(record["tableau_rows"],record["initial_tableau_forecast"]["rows"])
        self.assertEqual(record["tableau_cells_including_rhs_and_objective"],
                         (record["tableau_rows"]+1)*(record["tableau_columns"]+1))

    def test_reduced_blocker_fixture_admission_forecast(self):
        # Counts are frozen by the independent full model; this tests only arithmetic.
        self.assertEqual(compact._preflight("oop_guarantee",29,29,57,57),(85,256,22102))
        self.assertEqual(compact._preflight("ip_ceiling",29,29,57,57),(85,256,22102))
        with self.assertRaises(legacy._Limit): compact._preflight("oop_guarantee",29,29,57,57+2)


def _matrix_value(model,x,y):
    return sum((x[i]*model["A"][i][j]*y[j] for i in range(len(x)) for j in range(len(y))),F(0))


if __name__=="__main__": unittest.main()
