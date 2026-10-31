"""Host admission and protocol checks for the explicit native fold-class path."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pokerlab import native_exact_four_street as native
from pokerlab import exact_selected_solver as solver
from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from pokerlab.shared_public_topology import TerminalVertex
from scripts.benchmark_suit_quotient_solver import METRICS, _protected_verification, case_for, request_for
from tests.test_native_active_frames import _AuthenticatedControls


def _prepared():
    hands = ((('As', 'Ah'), ('Ks', 'Kh')), (('Qs', 'Qh'), ('Js', 'Jh')))
    boards = ((('As', '3c', '4c'), '5c', '6c'), (('2d', '3d', '4d'), '5d', '6d'))
    vertices = (TerminalVertex('fold', (1.0, 1.0), 0),)
    occurrences = (
        SimpleNamespace(vertex_id=0, history=()),
        SimpleNamespace(vertex_id=0, history=('flop@As3c4c',)),
    )
    topology = SimpleNamespace(vertices=vertices, iter_occurrences=lambda: iter(occurrences))
    kernel = SimpleNamespace(hands=hands, hand_counts=(2, 2), selected=boards)
    return SimpleNamespace(kernel=kernel, topology=topology)


class NativeFoldClassHostTests(unittest.TestCase):
    def test_board_masks_and_crossover_census_are_deterministic(self):
        prepared = _prepared()
        first = native._fold_class_expectation(prepared, 10)
        self.assertEqual(first, native._fold_class_expectation(prepared, 10))
        self.assertEqual(first['classes_sb'], 2)
        self.assertEqual(first['classes_bb'], 1)
        self.assertEqual(first['fold_occurrences'], 2)
        self.assertEqual(first['class_calls_sb'] + first['literal_calls_sb'], 20)
        self.assertEqual(first['class_calls_bb'] + first['literal_calls_bb'], 20)
        self.assertEqual(first['setup_work_upper'], 2048 * 4 + 8 * 2 * 4 + 65536)
        self.assertEqual(first['setup_entries_upper'], 10 * 4 + 128)

    def test_fold_receipt_binds_exact_counts_and_shared_whole_request(self):
        prepared = _prepared()
        expected = native._fold_class_expectation(prepared, 10)
        fold = {name: expected.get(name, 0) for name in native.FOLD_FIELDS}
        fold.update(buckets_sb=3, buckets_bb=2, own_checks=10,
                    retained_pair_entries=0, query_allowance_retained=1,
                    combined_work=700, combined_entries=900)
        done = {'modeled_work_upper': 700, 'retained_entries_upper': 900}
        route = {'combined_work': 700, 'combined_entries': 900}
        admission = {'combined_work': 700, 'combined_entries': 900,
                     'plan_setup_work': expected['setup_work_upper']}
        self.assertEqual(native._validate_fold_receipt(
            fold, prepared=prepared, iterations=10, done=done,
            route=route, admission=admission), fold)
        forged = dict(fold, class_calls_sb=fold['class_calls_sb'] + 1)
        with self.assertRaisesRegex(ValueError, 'independent mask/crossover census'):
            native._validate_fold_receipt(forged, prepared=prepared, iterations=10,
                done=done, route=route, admission=admission)
        underreserved = dict(admission, plan_setup_work=expected['setup_work_upper'] - 1)
        with self.assertRaisesRegex(ValueError, 'bucket/query allowance'):
            native._validate_fold_receipt(fold, prepared=prepared, iterations=10,
                done=done, route=route, admission=underreserved)

    def test_fold_record_requires_exact_order_and_version(self):
        valid = ['FOLD', 'mask-classes-v1'] + [f'{name}=0' for name in native.FOLD_FIELDS]
        self.assertEqual(tuple(native._parse_fold_record('\t'.join(valid))), native.FOLD_FIELDS)
        reordered = list(valid)
        reordered[2], reordered[3] = reordered[3], reordered[2]
        with self.assertRaisesRegex(ValueError, 'Malformed, unordered'):
            native._parse_fold_record('\t'.join(reordered))
        wrong_version = list(valid)
        wrong_version[1] = 'mask-classes-v2'
        with self.assertRaisesRegex(ValueError, 'Missing or wrong'):
            native._parse_fold_record('\t'.join(wrong_version))
        too_wide = list(valid)
        too_wide[2] = f'{native.FOLD_FIELDS[0]}={(1 << 64)}'
        with self.assertRaisesRegex(ValueError, 'exceeds uint64'):
            native._parse_fold_record('\t'.join(too_wide))

    def test_low_whole_work_remainder_rejects_before_group_or_fold_masks(self):
        request = request_for(case_for("mixed-stabilizer"), 10)
        prepared = solver._prepare_exact_selected(request, rank_cache_boards=64,
            pair_diagnostics="compact", exact_arithmetic="dyadic",
            training_reduction="suit-equivariant", strategy_storage="suit-quotient",
            quotient_lookup="per-decision", execution_profile="native-indexed-v1")
        prepared.admission["whole_request_limit"] = prepared.admission["combined_modeled_work_upper"] + 1
        with patch("pokerlab.suit_quotient_plan._group") as group, \
             patch("pokerlab.native_exact_four_street._fold_class_expectation") as masks:
            with self.assertRaisesRegex(ValueError, "host group/I/O admission exceeded"):
                native.admit(prepared, traversal="active-frames",
                    native_payoffs="fold-mask-classes-v1")
            group.assert_not_called()
            masks.assert_not_called()

    def test_new_mode_rejects_incomplete_native_stack_before_build_or_preparation(self):
        with patch('pokerlab.native_exact_four_street.executable_identity') as identity, \
             patch('pokerlab.exact_selected_solver._prepare_exact_selected') as prepare:
            with self.assertRaisesRegex(ValueError, 'complete explicit native'):
                solve_four_street_exact_selected(None, native_executable='not-a-built-executable',
                    native_payoffs='fold-mask-classes-v1')
            identity.assert_not_called()
            prepare.assert_not_called()

    def test_unknown_payoff_mode_rejects_before_build_or_preparation(self):
        with patch('pokerlab.native_exact_four_street.executable_identity') as identity, \
             patch('pokerlab.exact_selected_solver._prepare_exact_selected') as prepare:
            with self.assertRaisesRegex(ValueError, 'Unsupported exact native payoff mode'):
                solve_four_street_exact_selected(None, native_payoffs='fallback')
            identity.assert_not_called()
            prepare.assert_not_called()


class NativeFoldClassesEngineTests(_AuthenticatedControls, unittest.TestCase):
    """Whole-call parity and strict FOLD parsing against the compiled V5 engine."""
    target = "engine"
    environment = "OPENPOKER_NATIVE_FOLD_CLASSES_ENGINE_EXE"
    prefix = "opl-native-fold-classes-engine-"

    @staticmethod
    def _options(executable):
        return dict(rank_cache_boards=64, pair_diagnostics="compact", exact_arithmetic="dyadic",
            training_reduction="suit-equivariant", strategy_storage="suit-quotient",
            quotient_lookup="per-decision", native_executable=executable,
            native_routing="indexed", native_admission="indexed-v1",
            native_traversal="active-frames")

    def _compare_case(self, case, *, require_group=None):
        request = request_for(case, 10)
        options = self._options(self.executable)
        value = solve_four_street_exact_selected(request, **options)
        with patch("pokerlab.suit_quotient_cfr.train_suit_quotient",
                   side_effect=AssertionError("Python quotient fallback")), \
             patch("pokerlab.equivariant_packed_cfr.train_equivariant_packed",
                   side_effect=AssertionError("Python CFR fallback")), \
             patch("pokerlab.native_selected_dag.train_native_selected_dag",
                   side_effect=AssertionError("legacy native fallback")), \
             patch("pokerlab.native_public_cfr.train_native_public",
                   side_effect=AssertionError("legacy native fallback")):
            classes = solve_four_street_exact_selected(request, **options,
                native_payoffs="fold-mask-classes-v1")
        self.assertEqual(classes["training_backend"], "native-exact-four-street-fold-classes-v5")
        self.assertEqual(classes["native_payoffs"], "fold-mask-classes-v1")
        self.assertEqual(classes["native_traversal"], "active-frames")
        self.assertEqual(classes["native_routing"], "indexed")
        self.assertEqual(classes["native_admission"], "indexed-v1")
        self.assertEqual(classes["strategy"], value["strategy"])
        self.assertEqual([classes[name].hex() for name in METRICS],
                         [value[name].hex() for name in METRICS])
        exact = classes["operator_census"]["native_exact"]
        fold = exact["fold_classes"]
        self.assertEqual(fold["mode"], "mask-classes-v1")
        self.assertEqual(fold["retained_pair_entries"], 0)
        self.assertEqual(fold["query_allowance_retained"], 1)
        self.assertEqual(fold["combined_work"], exact["modeled_work_upper"])
        self.assertEqual(fold["combined_entries"], exact["retained_entries_upper"])
        if require_group is not None:
            self.assertEqual(exact["active_frames"]["group_size"], require_group)
        verification = _protected_verification(case, classes)
        self.assertTrue(verification["payload_metrics_within_tolerance"], verification)
        return classes

    def test_v5_matches_v4_complete_policies_metrics_and_replay(self):
        names = ("payoff-varied-t10", "blocker-18", "asymmetric-weighted",
                 "mixed-stabilizer", "original-22-t10")
        for name in names:
            with self.subTest(case=name):
                self._compare_case(case_for(name))

    def test_v5_physical_g6_and_blind_all_in(self):
        g6 = dict(case_for("original-22-t10"), id="fold-classes-physical-s3-v1",
            sb_range="AdAh,AdAs,AhAs", bb_range="KdKh,KdKs,KhKs",
            runouts=["2c3c4c7c8c"])
        self._compare_case(g6, require_group=6)
        blind = dict(case_for("payoff-varied-t10"), id="fold-classes-blind-all-in-v1",
            config={"starting_stack": [0.5, 1.0]})
        payload = self._compare_case(blind)
        self.assertEqual(payload["strategy"], [])
        self.assertEqual(payload["info_sets"], 0)

    def test_v5_missing_forged_and_wrong_mode_fold_proofs_reject(self):
        case = case_for("mixed-stabilizer")
        request = request_for(case, 10)
        prepared = solver._prepare_exact_selected(request, rank_cache_boards=64,
            pair_diagnostics="compact", exact_arithmetic="dyadic",
            training_reduction="suit-equivariant", strategy_storage="suit-quotient",
            quotient_lookup="per-decision", execution_profile="native-indexed-v1")
        reservation = native.admit(prepared, traversal="active-frames",
            native_payoffs="fold-mask-classes-v1")
        before = native.executable_identity(self.executable)
        wire = native.wire(prepared, prepared.iterations, rank_cache_boards=64,
            native_work=reservation["native_work_limit"],
            native_entries=reservation["native_entries_limit"], routing="indexed",
            traversal="active-frames", native_payoffs="fold-mask-classes-v1")
        raw = native._invoke(before["executable"], wire)
        self.assertEqual(native.executable_identity(self.executable), before)
        native.parse_policy(raw, prepared, routing="indexed", traversal="active-frames",
            native_payoffs="fold-mask-classes-v1")
        lines = raw.splitlines()
        self.assertEqual(lines[-1].split(b"\t", 2)[:2], [b"FOLD", b"mask-classes-v1"])
        forged = lines[-1].replace(b"classes_sb=", b"classes_sb=9", 1)
        no_fold = b"\n".join(lines[:-1]) + b"\n"
        bad_fold = b"\n".join([*lines[:-1], forged]) + b"\n"
        for bad in (no_fold, bad_fold):
            with self.subTest(tail=bad.splitlines()[-1][-100:]), self.assertRaises(ValueError):
                native.parse_policy(bad, prepared, routing="indexed", traversal="active-frames",
                    native_payoffs="fold-mask-classes-v1")
        with self.assertRaisesRegex(ValueError, "Wrong native exact result protocol"):
            native.parse_policy(raw, prepared, routing="indexed", traversal="active-frames",
                native_payoffs="board-sweep")
        self.assertEqual(native.executable_identity(self.executable), before)

if __name__ == '__main__':
    unittest.main()
