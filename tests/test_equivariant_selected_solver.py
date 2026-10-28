"""Whole-game controls for the explicit equivariant reference trajectory."""
from copy import deepcopy
from unittest import TestCase, main
from unittest.mock import patch

from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from scripts.exact_selected_compact_certificate import evaluate_exact
from tests.test_four_street_certificate import _case
from tests.test_selected_operator_solver import request

METRICS=("value_sb","value_bb","sb_best_response_value","bb_best_response_value",
         "sb_gain","bb_gain","nash_conv","exploitability")


def symmetric_case():
    case=_case(sb="AcAh:1,AdAh:1",bb="KcKh:1,KdKh:1",stacks=[2,2])
    case["runouts"]=["2c3c4h5s6h","2d3d4h5s6h"]
    return case


def mapped_row_key(row):
    swap={"c":"d","d":"c","h":"h","s":"s"}
    def card(c):return c[0]+swap[c[1]]
    from pokerlab.cards import DECK
    index={c:i for i,c in enumerate(DECK)}
    history=[]
    for text in row["history"]:
        if text.startswith("flop@"):
            history.append("flop@"+"".join(sorted((card(text[i:i+2]) for i in (5,7,9)),key=index.__getitem__)))
        elif text.startswith("turn@"):
            history.append("turn@"+card(text[5:]))
        elif text.startswith("river@"):
            history.append("river@"+card(text[6:]))
        else:history.append(text)
    holding="".join(sorted((card(row["hand"][:2]),card(row["hand"][2:]))))
    return row["player"],holding,tuple(history)


class EquivariantSelectedSolverTests(TestCase):
    def test_default_payload_and_trainer_remain_unchanged_with_explicit_default(self):
        case = symmetric_case()
        with patch("pokerlab.equivariant_packed_cfr.train_equivariant_packed", side_effect=AssertionError("new trainer")):
            implicit = solve_four_street_exact_selected(request(case), pair_diagnostics="compact")
            explicit = solve_four_street_exact_selected(request(case), pair_diagnostics="compact",
                training_reduction="default")
        self.assertEqual(implicit, explicit)
        self.assertNotIn("training_reduction", implicit)
        self.assertNotIn("equivariant_additional_admission", implicit["operator_census"]["whole_request_admission"])

    def test_complete_reference_is_bitwise_equivariant_for_exchanged_private_hands(self):
        case=symmetric_case()
        result=solve_four_street_exact_selected(request(case),pair_diagnostics="compact",
            exact_arithmetic="dyadic",training_reduction="suit-equivariant")
        rows={(r["player"],r["hand"],tuple(r["history"])):r for r in result["strategy"]}
        for row in result["strategy"]:
            partner=rows[mapped_row_key(row)]
            self.assertEqual([{k:v for k,v in a.items() if k!="probability"} for a in row["actions"]],
                             [{k:v for k,v in a.items() if k!="probability"} for a in partner["actions"]])
            self.assertEqual([a["probability"].hex() for a in row["actions"]],
                             [a["probability"].hex() for a in partner["actions"]])
        self.assertEqual(result["training_reduction"],"suit-equivariant-sorted-chance-binary64-v1")
        admission=result["operator_census"]["whole_request_admission"]
        self.assertEqual(admission["equivariant_additional_admission"]["setup_census_passes_reserved"],3)
        self.assertLessEqual(admission["combined_modeled_work_upper"],admission["whole_request_limit"])
        certificate=evaluate_exact(case,result)["exact_certificate"]
        self.assertEqual(certificate["threshold"],"1/1000")
        self.assertEqual(certificate["source_identity"],"four-street-independent-exact-v3")

    def test_fraction_and_integer_callbacks_preserve_same_equivariant_policy_bits(self):
        case=symmetric_case()
        fraction=solve_four_street_exact_selected(request(case),pair_diagnostics="compact",
                                                   training_reduction="suit-equivariant")
        dyadic=solve_four_street_exact_selected(request(case),pair_diagnostics="compact",
            training_reduction="suit-equivariant",exact_arithmetic="dyadic")
        for field in ("strategy",*METRICS):self.assertEqual(fraction[field],dyadic[field],field)

    def test_additional_work_rejects_before_rows_rank_pair_and_training(self):
        from pokerlab.equivariant_packed_cfr import equivariant_additional_census
        def excessive(*args,**kwargs):
            value=deepcopy(equivariant_additional_census(*args,**kwargs))
            value["modeled_work_upper"]=500_000_001
            return value
        with patch("pokerlab.equivariant_packed_cfr.equivariant_additional_census",side_effect=excessive), \
             patch("pokerlab.equivariant_packed_cfr.train_equivariant_packed",side_effect=AssertionError("training")), \
             patch("pokerlab.equivariant_packed_cfr.equivariant_layout_census",side_effect=AssertionError("rows")), \
             patch("pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.legal_hands",side_effect=AssertionError("row support")), \
             patch("pokerlab.exact_selected_kernel.rank_hand",side_effect=AssertionError("ranking")):
            with self.assertRaisesRegex(ValueError,"whole-request additional work"):
                solve_four_street_exact_selected(request(symmetric_case()),pair_diagnostics="compact",
                                                  training_reduction="suit-equivariant")

    def test_unsupported_reduction_rejects_before_input_preparation(self):
        with patch("pokerlab.exact_selected_solver.ExactSelectedRunoutKernel",side_effect=AssertionError("kernel")):
            for value in (None,True,"native",1):
                with self.subTest(value=value),self.assertRaisesRegex(ValueError,"training_reduction"):
                    solve_four_street_exact_selected(request(symmetric_case()),training_reduction=value)

    def test_changed_layout_receipt_rejects_before_training(self):
        from pokerlab.equivariant_packed_cfr import equivariant_layout_census
        def changed(*args, **kwargs):
            result = equivariant_layout_census(*args, **kwargs)
            result["equivariant_additional_admission"]["setup_work_upper"] += 1
            return result
        with patch("pokerlab.equivariant_packed_cfr.equivariant_layout_census", side_effect=changed), \
             patch("pokerlab.equivariant_packed_cfr.train_equivariant_packed", side_effect=AssertionError("training")):
            with self.assertRaisesRegex(RuntimeError, "layout changed after pre-row"):
                solve_four_street_exact_selected(request(symmetric_case()), pair_diagnostics="compact",
                    training_reduction="suit-equivariant")


if __name__=="__main__":main()
