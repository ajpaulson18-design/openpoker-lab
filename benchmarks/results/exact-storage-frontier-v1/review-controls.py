"""Synthetic-only external controls; no repository or saved-study imports."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
PATH = Path(__file__).with_name("exact-storage-independent-review.py")
SPEC = importlib.util.spec_from_file_location("independent_storage_review", PATH)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def action(name="check", amount=0., target=0.):
    return {"name": name, "amount_hex": float(amount).hex(), "raise_to_hex": float(target).hex(),
        "full_raise": False, "token": name if name in ("fold", "check", "call") else name + "@1"}


def terminal(kind="showdown", winner=None):
    return {"kind": "terminal", "terminal_kind": kind, "winner": winner,
        "contributions_hex": [float(1).hex(), float(1).hex()]}


def base():
    request = review.fixture_request("AsAd", "KsKd", ["2c3d4h5s6c"])
    vertices = [{"kind": "decision", "player": 0, "actions": [action("fold"), action("call", .5, 1)], "children": [1, 2]},
        terminal("fold", 1),
        {"kind": "chance", "street": "flop", "card_index": 4, "branches": [["2c3d4h", 3]]},
        {"kind": "chance", "street": "turn", "card_index": 5, "branches": [["5s", 4]]},
        {"kind": "chance", "street": "river", "card_index": 6, "branches": [["6c", 5]]}, terminal()]
    witness = {"contract": "exact-selected-structural-witness-v1", "root_id": 0, "initial_history": [],
        "vertices": vertices, "ranges": [[{"hand": "AdAs", "weight_hex": float(1).hex()}],
            [{"hand": "KdKs", "weight_hex": float(1).hex()}]],
        "selected_runouts": [["2c", "3d", "4h", "5s", "6c"]], "scope": "Synthetic conditional graph."}
    return witness, request


class ExternalStructuralReviewControls(unittest.TestCase):
    def reject(self, witness, request, reason):
        with self.assertRaisesRegex(ValueError, reason):review.replay(witness, request)

    def test_minimal_one_board_counts_and_supported_shape(self):
        witness, request = base();result = review.replay(witness, request)
        self.assertEqual({key: result["counts"][key] for key in ("logical_visits", "maximum_depth", "information_rows", "action_slots",
            "history_token_entries", "support_pair_board_occurrences")},
            {"logical_visits": 6, "maximum_depth": 4, "information_rows": 1, "action_slots": 2,
             "history_token_entries": 0, "support_pair_board_occurrences": 1})
        self.assertTrue(result["s4_supported_row_menu_closure"])
        self.assertTrue(result["s4_full_public_graph_closure"])
        self.assertIsNone(result["quality_gate"])
        gates, passes = review.shape_screen({}, result["counts"], 2)
        self.assertEqual(gates["action_slots"]["observed"], 2)
        self.assertTrue(passes)

    def test_shape_holes_use_conservative_dense_upper_without_changing_actual_counts(self):
        witness, request = base();counts = review.replay(witness, request)["counts"]
        counts["action_slots"] = 2402
        gates, passes = review.shape_screen({}, counts, 2514)
        self.assertEqual(counts["action_slots"], 2402)
        self.assertEqual(gates["action_slots"]["observed"], 2514)
        self.assertNotEqual(gates["action_slots"]["observed"], counts["action_slots"])
        self.assertLessEqual(counts["action_slots"], review.CAPS["action_slots"])
        self.assertTrue(gates["action_slots"]["passes_shape_screen"])
        self.assertTrue(passes)

    def test_cycle_rejected(self):
        witness, request = base();witness["vertices"][0]["children"][0] = 0
        self.reject(witness, request, "cyclic")

    def test_unreachable_vertex_rejected(self):
        witness, request = base();witness["vertices"].append(terminal())
        self.reject(witness, request, "unreachable")

    def test_duplicate_chance_branch_rejected(self):
        witness, request = base();witness["vertices"][2]["branches"].append(["2c3d4h", 3])
        self.reject(witness, request, "duplicate chance")

    def test_duplicate_action_token_rejected(self):
        witness, request = base();witness["vertices"][0]["actions"][1] = action("fold")
        self.reject(witness, request, "duplicate action")

    def test_exponential_path_forecast_rejects_before_stream(self):
        witness, request = base()
        witness["vertices"] = [{"kind": "decision", "player": 0, "actions": [action("check"), action("call")],
            "children": [index + 1, index + 1]} for index in range(20)] + [terminal()]
        self.reject(witness, request, "expanded path|expanded logical")

    def test_depth_forecast_rejected(self):
        witness, request = base()
        witness["vertices"] = [{"kind": "decision", "player": 0, "actions": [action()], "children": [index + 1]}
            for index in range(257)] + [terminal()]
        self.reject(witness, request, "depth bound")

    def test_invalid_prior_exponent_rejected(self):
        witness, request = base();request["sb_range"] = "AsAd:1e1000000"
        self.reject(witness, request, "invalid private weight")

    def test_nonfinite_prior_rejected(self):
        witness, request = base();request["sb_range"] = "AsAd:nan"
        self.reject(witness, request, "invalid private weight")

    def test_forged_input_weight_rejected(self):
        witness, request = base();witness["ranges"][0][0]["weight_hex"] = float(.5).hex()
        self.reject(witness, request, "private inputs differ")

    def test_zero_prior_rejected(self):
        witness, request = base();request["sb_range"] = "AsAd:0"
        self.reject(witness, request, "empty private range")

    def test_large_hex_exponent_rejected(self):
        witness, request = base();witness["vertices"][0]["actions"][0]["amount_hex"] = "0x1p+1000000"
        self.reject(witness, request, "invalid binary64")

    def test_negative_money_rejected(self):
        witness, request = base();witness["vertices"][1]["contributions_hex"][0] = float(-1).hex()
        self.reject(witness, request, "negative binary64")

    def test_terminal_money_above_stack_rejected(self):
        witness, request = base();witness["vertices"][1]["contributions_hex"][0] = float(9).hex()
        self.reject(witness, request, "role-specific starting stacks")

    def test_noncanonical_flop_rejected(self):
        witness, request = base();witness["vertices"][2]["branches"][0][0] = "4h3d2c"
        self.reject(witness, request, "noncanonical flop")

    def test_duplicate_selected_outcome_rejected(self):
        witness, request = base();request["runouts"].append(request["runouts"][0])
        self.reject(witness, request, "duplicate canonical")

    def test_shuffled_complete_boards_normalize_by_deck_order_without_swapping_turn_river(self):
        self.assertEqual(review.boards(["4d3c2cKc8h", "2c3c4dQd8h", "2c3c4d7hKc"]),
            (("2c", "3c", "4d", "7h", "Kc"), ("2c", "3c", "4d", "Qd", "8h"),
             ("2c", "3c", "4d", "Kc", "8h")))

    def test_reveal_order_rejected(self):
        witness, request = base();witness["vertices"][2].update(street="turn", card_index=5, branches=[["5s", 3]])
        self.reject(witness, request, "future cards out of sequence")

    def test_future_card_in_action_token_rejected(self):
        witness, request = base();witness["vertices"][0]["actions"][0]["token"] = "river@6c"
        self.reject(witness, request, "impersonates public reveal")

    def test_chance_branch_not_in_requested_board_rejected(self):
        witness, request = base();witness["vertices"][3]["branches"][0][0] = "Ts"
        self.reject(witness, request, "chance branches differ")

    def test_initial_history_tamper_rejected(self):
        witness, request = base();witness["initial_history"] = ["call"]
        self.reject(witness, request, "unexpected initial history")

    def test_shared_child_context_edges_preserve_action_labels(self):
        witness, request = base()
        witness["vertices"] = [{"kind": "decision", "player": 0, "actions": [action("check"), action("call")], "children": [1, 1]}, terminal()]
        result = review.replay(witness, request)
        self.assertEqual(result["counts"]["context_edges"], 2)
        self.assertEqual(result["counts"]["vertex_prefix_contexts"], 2)
        self.assertEqual(result["counts"]["logical_visits"], 3)

    def test_suit_group_without_supported_menu_closure_rejected(self):
        request = review.fixture_request("AcAh,AdAh", "KcKh,KdKh", ["2c3c4h5s6h", "2d3d4h5s6h"], stacks=(2, 2))
        witness = {"contract": "exact-selected-structural-witness-v1", "root_id": 0, "initial_history": [],
            "vertices": [{"kind": "chance", "street": "flop", "card_index": 4, "branches": [["2c3c4h", 1], ["2d3d4h", 2]]},
                {"kind": "decision", "player": 0, "actions": [action("check")], "children": [3]},
                {"kind": "decision", "player": 0, "actions": [action("call")], "children": [3]}, terminal()],
            "ranges": [[{"hand": "AcAh", "weight_hex": float(1).hex()}, {"hand": "AdAh", "weight_hex": float(1).hex()}],
                [{"hand": "KcKh", "weight_hex": float(1).hex()}, {"hand": "KdKh", "weight_hex": float(1).hex()}]],
            "selected_runouts": [["2c", "3c", "4h", "5s", "6h"], ["2d", "3d", "4h", "5s", "6h"]], "scope": "Synthetic closure counterexample."}
        self.reject(witness, request, "not closed")

    def test_json_preparse_depth_and_scalar_caps(self):
        with self.assertRaisesRegex(ValueError, "nesting"):review.json_envelope(b"[" * 513 + b"]" * 513)
        with self.assertRaisesRegex(ValueError, "scalar"):review.json_envelope(b'"' + b"x" * 16385 + b'"')

    def test_suit_varying_terminal_payoff_rejected_despite_identical_menus(self):
        request = review.fixture_request("AcAh,AdAh", "KcKh,KdKh", ["2c3c4h5s6h", "2d3d4h5s6h"], stacks=(2, 2))
        changed_terminal = terminal();changed_terminal["contributions_hex"] = [float(1.5).hex()] * 2
        witness = {"contract": "exact-selected-structural-witness-v1", "root_id": 0, "initial_history": [],
            "vertices": [{"kind": "chance", "street": "flop", "card_index": 4, "branches": [["2c3c4h", 1], ["2d3d4h", 2]]},
                {"kind": "decision", "player": 0, "actions": [action("check")], "children": [3]},
                {"kind": "decision", "player": 0, "actions": [action("check")], "children": [4]}, terminal(), changed_terminal],
            "ranges": [[{"hand": "AcAh", "weight_hex": float(1).hex()}, {"hand": "AdAh", "weight_hex": float(1).hex()}],
                [{"hand": "KcKh", "weight_hex": float(1).hex()}, {"hand": "KdKh", "weight_hex": float(1).hex()}]],
            "selected_runouts": [["2c", "3c", "4h", "5s", "6h"], ["2d", "3d", "4h", "5s", "6h"]], "scope": "Synthetic payoff counterexample."}
        self.reject(witness, request, "full public graph signatures/terminal payoffs")

    def test_rejection_classifier_is_whole_word_only(self):
        self.assertFalse(review.resource_rejection("cannot escape malformed graph"))
        self.assertFalse(review.resource_rejection("invalid config"))
        self.assertTrue(review.resource_rejection("whole-request work admission exceeded"))
        self.assertTrue(review.resource_rejection("existing cap exceeded"))


if __name__ == "__main__":
    print("review_helper_sha256=" + hashlib.sha256(PATH.read_bytes()).hexdigest(), flush=True)
    unittest.main(verbosity=2)
