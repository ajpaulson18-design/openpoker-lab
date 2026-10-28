"""No-solving storage census and conservative suit-stabilizer opportunities."""
from unittest import TestCase, main
from unittest.mock import patch
import json
from pathlib import Path

from pokerlab.exact_storage_census import census_exact_selected_storage, ExactStorageCensusLimits
from pokerlab.exact_storage_census import _history
from pokerlab.exact_selected_solver import _prepare_exact_selected
from pokerlab.shared_public_topology import DecisionVertex
from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from tests.test_four_street_certificate import _case
from tests.test_selected_operator_solver import request


class ExactStorageCensusTests(TestCase):
    def test_original_supported_rows_slots_contexts_without_training_pairs_or_rank(self):
        case=json.loads((Path(__file__).resolve().parents[1]/"benchmarks/four-street-integration-v1.json").read_text())["case"]
        with patch("pokerlab.exact_selected_solver.train_packed",side_effect=AssertionError("training")), \
             patch("pokerlab.exact_selected_kernel.rank_hand",side_effect=AssertionError("ranking")), \
             patch("pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact",side_effect=AssertionError("pair")):
            result=census_exact_selected_storage(request(case))
        self.assertEqual((result["unique_vertices"],result["logical_visits"]),(99,1462))
        self.assertEqual((result["vertex_prefix_contexts"],result["context_edges"]),(259,321))
        self.assertEqual((result["information_rows"],result["action_slots"]),(1200,2402))
        self.assertEqual(result["four_packed_numeric_buffers_payload_bytes"],4*2402*8)
        self.assertEqual(sum(row["information_rows"] for row in result["per_street_player"]),1200)
        self.assertEqual(result["rank_free_kernel_receipt"]["rank_calls"],0)
        self.assertIsNone(result["quality_gate"])

    def test_small_live_solve_has_exact_same_row_slot_and_full_history_counts(self):
        case=_case(sb="AsAd:.7,QsQd:.3",bb="KsKd:.4,JhJd:.6",stacks=[2,2])
        result=census_exact_selected_storage(request(case))
        policy=solve_four_street_exact_selected(request(case),pair_diagnostics="compact")
        self.assertEqual(result["information_rows"],len(policy["strategy"]))
        self.assertEqual(result["action_slots"],sum(len(row["actions"]) for row in policy["strategy"]))
        self.assertEqual(result["history_token_entries"],sum(len(row["history"]) for row in policy["strategy"]))
        self.assertEqual(result["history_token_bytes"],sum(sum(len(t.encode()) for t in row["history"]) for row in policy["strategy"]))

    def test_weighted_whole_game_suit_stabilizer_requires_prior_and_board_invariance(self):
        # Swapping clubs/diamonds preserves both pair holdings and paired boards.
        symmetric=_case(sb="AcAd:1,AsAh:1",bb="KcKd:1,KsKh:1",stacks=[2,2])
        symmetric["runouts"]=["2c3c4h5s6h","2d3d4h5s6h"]
        first=census_exact_selected_storage(request(symmetric))
        group=first["suit_symmetry"]
        self.assertIn("dchs",group["permutations"])
        self.assertLess(group["supported_row_orbits"],first["information_rows"])
        # Lose only one selected board: that global swap is no longer admitted.
        asymmetric=dict(symmetric,runouts=[symmetric["runouts"][0]])
        second=census_exact_selected_storage(request(asymmetric))
        self.assertNotIn("dchs",second["suit_symmetry"]["permutations"])
        swapped=_case(sb="AcAh:1,AdAh:1",bb="KcKh:1,KdKh:1",stacks=[2,2])
        swapped["runouts"]=symmetric["runouts"]
        self.assertIn("dchs",census_exact_selected_storage(request(swapped))["suit_symmetry"]["permutations"])
        broken=dict(swapped,sb_range="AcAh:.7,AdAh:.3",bb_range="KcKh:.4,KdKh:.6")
        self.assertNotIn("dchs",census_exact_selected_storage(request(broken))["suit_symmetry"]["permutations"])

    def test_additional_census_bounds_reject_before_support_or_orbit_growth(self):
        with patch("pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.legal_hands",side_effect=AssertionError("support allocation")):
            with self.assertRaisesRegex(ValueError,"additional work/retained-entry"):
                census_exact_selected_storage(request(_case()),limits=ExactStorageCensusLimits(max_additional_entries=1))

    def test_repeat_is_deterministic_and_orbit_disabled_changes_no_supported_counts(self):
        req=request(_case())
        a=census_exact_selected_storage(req)
        self.assertEqual(a,census_exact_selected_storage(req))
        b=census_exact_selected_storage(req,suit_orbits=False)
        for field in ("information_rows","action_slots","history_token_entries","context_edges","vertex_prefix_contexts"):
            self.assertEqual(a[field],b[field])
        self.assertIsNone(b["suit_symmetry"]["supported_row_orbits"])

    def test_shared_vertex_never_erases_distinct_action_histories(self):
        from itertools import permutations
        prepared=_prepare_exact_selected(request(_case()),pair_diagnostics="compact")
        by_vertex={}
        pair=None
        for occurrence in prepared.topology.iter_occurrences():
            if not isinstance(prepared.topology.vertices[occurrence.vertex_id],DecisionVertex):continue
            actions=tuple(t for t in occurrence.history if not t.startswith(("flop@","turn@","river@")))
            previous=by_vertex.get(occurrence.vertex_id)
            if previous and previous[0]!=actions:
                pair=(previous[1],occurrence.history)
                break
            by_vertex[occurrence.vertex_id]=(actions,occurrence.history)
        self.assertIsNotNone(pair)
        for image in permutations("cdhs"):
            self.assertNotEqual(_history(pair[0],dict(zip("cdhs",image))),pair[1])

    def test_suit_mapping_preserves_ordered_turn_and_river_and_bet_tokens(self):
        mapping=dict(zip("cdhs","dchs"))
        history=("raise@2","flop@2c3d4h","turn@5c","check","river@6d","all_in@8")
        self.assertEqual(_history(history,mapping),
                         ("raise@2","flop@2d3c4h","turn@5d","check","river@6c","all_in@8"))

    def test_optional_witness_retains_unique_graph_and_inputs_without_expanded_rows(self):
        req=request(_case())
        plain=census_exact_selected_storage(req)
        captured=census_exact_selected_storage(req,include_witness=True)
        self.assertNotIn("structural_witness",plain)
        witness=captured["structural_witness"]
        self.assertEqual(witness["contract"],"exact-selected-structural-witness-v1")
        self.assertEqual(len(witness["vertices"]),captured["unique_vertices"])
        self.assertEqual([len(side) for side in witness["ranges"]],captured["hand_counts"])
        self.assertEqual(len(witness["selected_runouts"]),captured["selected_boards"])
        self.assertNotIn("strategy",witness)
        self.assertNotIn("worlds",witness)
        self.assertNotIn("histories",witness)
        self.assertEqual(witness,json.loads(json.dumps(witness,allow_nan=False)))
        self.assertGreater(captured["additional_census_admission"]["witness_entries_upper"],0)
        self.assertGreater(captured["additional_census_admission"]["retained_entries_upper"],
                           plain["additional_census_admission"]["retained_entries_upper"])


if __name__=="__main__":main()
