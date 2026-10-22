import math
import unittest
from fractions import Fraction

from scripts.flop_class_reweight_plan import plan_weights
from scripts.flop_class_reweight_proof import WeightedClassModel
from scripts.flop_multistreet_validation import _Chance, _Decision, _Terminal

from scripts import flop_class_owned_fingerprint as fingerprint_module
from scripts.flop_class_owned_fingerprint import FingerprintError, Limits, fingerprint
from unittest.mock import patch


def synthetic_model(*, signed_zero=0.0, shared=True):
    plan = plan_weights((1, 1), (1, 1))
    terminal = _Terminal((), "showdown", (signed_zero, 2.0), 0)
    root = _Decision((), 0, "flop", ("2c", "3d", "4h"),
                     ({"name": "check", "amount": 0},), (terminal, terminal))
    chance = _Chance((), 0, "turn", (("5s", root),))
    world = ("AsAd", "AsKh", Fraction(1, 3), ("5s", "6s"), ("2c", "3d", "4h"))
    common = [world]
    other = common if shared else [world]
    baseline = {"worlds": common, "signs": {"AsAd|AsKh": (1, -1, 0)},
                "tree": chance}
    physical = {"worlds": other, "pair_probabilities": {"AsAd|AsKh": Fraction(1, 3)},
                "tree": chance}
    turn_map = {"turn-class": ("5s", "6s")}
    partition = {"turn_classes": ("turn-class",), "river_classes": ("sig",),
                 "maps": turn_map, "node_index": {"own-hand-key": root},
                 "infos": {"own-hand-key": 2}}
    census = {"compact_public_states": 3, "physical_policy_rows": 2}
    return WeightedClassModel(plan, baseline, physical, partition, turn_map,
                              {"sig": ("7s",)}, (world,), chance, census)


class FingerprintTests(unittest.TestCase):
    def test_repeated_fingerprint_is_stable_and_reports_named_bounds(self):
        model = synthetic_model()
        first = fingerprint(model)
        second = fingerprint(model)
        self.assertEqual(first, second)
        self.assertEqual(first[1]["objects"] > 0, True)
        self.assertEqual(first[1]["edges"] > 0, True)
        self.assertIn("stream_bytes", first[1])

    def test_nested_value_and_signed_zero_mutations_change_digest(self):
        original = fingerprint(synthetic_model())[0]
        self.assertNotEqual(original, fingerprint(synthetic_model(signed_zero=-0.0))[0])
        changed = synthetic_model()
        changed.physical["pair_probabilities"]["AsAd|AsKh"] = Fraction(2, 3)
        self.assertNotEqual(original, fingerprint(changed)[0])

    def test_shared_object_topology_is_part_of_fingerprint(self):
        self.assertNotEqual(fingerprint(synthetic_model(shared=True))[0],
                            fingerprint(synthetic_model(shared=False))[0])

    def test_dict_order_is_significant_and_supported_set_order_is_stable(self):
        self.assertNotEqual(fingerprint({"a": 1, "b": 2})[0],
                            fingerprint({"b": 2, "a": 1})[0])
        self.assertEqual(fingerprint({"items": {"x", "y", "z"}})[0],
                         fingerprint({"items": {"z", "x", "y"}})[0])
        with self.assertRaises(FingerprintError):
            fingerprint({1, (2, 3)})

    def test_exact_types_nonfinite_values_and_extra_model_fields_reject(self):
        class ListSubclass(list):
            pass

        with self.assertRaises(FingerprintError):
            fingerprint(ListSubclass([1]))
        with self.assertRaises(FingerprintError):
            fingerprint(math.inf)
        with self.assertRaises(FingerprintError):
            fingerprint(float("nan"))
        model = synthetic_model()
        object.__setattr__(model, "unexpected", 1)
        with self.assertRaises(FingerprintError):
            fingerprint(model)

    def test_fraction_alias_topology_and_action_child_changes_are_seen(self):
        value = Fraction(1, 3)
        shared = [value, value]
        separate = [Fraction(1, 3), Fraction(1, 3)]
        self.assertNotEqual(fingerprint(shared)[0], fingerprint(separate)[0])
        model = synthetic_model()
        before = fingerprint(model)[0]
        model.physical["tree"].branches["5s"].children[0].kind = "fold"
        self.assertNotEqual(before, fingerprint(model)[0])

    def test_every_owned_model_region_and_node_field_is_included(self):
        changes = (
            lambda m: object.__setattr__(m.plan, "scope", "mutated"),
            lambda m: m.baseline["signs"].__setitem__("AsAd|AsKh", (0, 1, 0)),
            lambda m: m.physical["worlds"].append(("QsQd", "KsKd", Fraction(1, 2), (), ())),
            lambda m: m.partition["infos"].__setitem__("own-hand-key", 3),
            lambda m: m.turns.__setitem__("turn-class", ("6s",)),
            lambda m: m.rivers.__setitem__("sig", ("8s",)),
            lambda m: m.root.branches.__setitem__("6s", m.root.branches["5s"]),
            lambda m: setattr(m.root.branches["5s"], "player", 1),
            lambda m: setattr(m.root.branches["5s"].children[0], "winner", 1),
            lambda m: m.census.__setitem__("compact_public_states", 4),
        )
        for change in changes:
            model = synthetic_model()
            before = fingerprint(model)[0]
            change(model)
            self.assertNotEqual(before, fingerprint(model)[0])

    def test_caps_reject_before_oversized_sequence_or_text_encoding(self):
        limits = Limits(objects=20, edges=4, depth=8, string_chars=4,
                        integer_bits=8, output_bytes=1024, stack=20)
        with self.assertRaisesRegex(FingerprintError, "edge count exceeds"):
            fingerprint([1, 2, 3, 4, 5], limits=limits)
        with self.assertRaisesRegex(FingerprintError, "String exceeds"):
            fingerprint("12345", limits=limits)
        with self.assertRaisesRegex(FingerprintError, "bit length"):
            fingerprint(1 << 8, limits=limits)
        with self.assertRaisesRegex(FingerprintError, "output bound"):
            fingerprint("1234", limits=Limits(output_bytes=10))

    def test_depth_and_object_caps_are_enforced(self):
        with self.assertRaisesRegex(FingerprintError, "nesting"):
            fingerprint([[[1]]], limits=Limits(depth=2))
        with self.assertRaisesRegex(FingerprintError, "object count"):
            fingerprint([[], []], limits=Limits(objects=2))

    def test_cyclic_graph_terminates_and_aliases_are_encoded(self):
        value = []
        value.append(value)
        digest, census = fingerprint(value)
        self.assertEqual(len(digest), 64)
        self.assertEqual(census["objects"], 1)
        self.assertGreater(census["token_counts"].get("R", 0), 0)

    def test_set_edge_and_output_reservations_precede_member_encoding(self):
        with patch.object(fingerprint_module, "_atomic_bytes",
                          side_effect=AssertionError("encoded before admission")):
            with self.assertRaisesRegex(FingerprintError, "edge count"):
                fingerprint({"a", "b", "c"}, limits=Limits(edges=2))
            with self.assertRaisesRegex(FingerprintError, "output bound"):
                fingerprint({"a"}, limits=Limits(output_bytes=16))

    def test_aggregate_temporary_set_bytes_are_reserved_before_encoding(self):
        with patch.object(fingerprint_module, "_atomic_bytes",
                          side_effect=AssertionError("encoded before admission")):
            with self.assertRaisesRegex(FingerprintError, "temporary encoding"):
                fingerprint({"aaaa", "bbbb", "cccc"}, limits=Limits(set_bytes=20))

    def test_mutated_limits_are_revalidated_as_exact_positive_integers(self):
        for bad in (True, -1, 1.5):
            limits = Limits()
            limits.edges = bad
            with self.subTest(bad=bad), self.assertRaisesRegex(FingerprintError, "Mutated Limits"):
                fingerprint([1], limits=limits)

    def test_in_traversal_limit_error_carries_partial_census(self):
        with self.assertRaises(FingerprintError) as caught:
            fingerprint([[1], 2, 3], limits=Limits(edges=3))
        partial = caught.exception.partial_census
        self.assertIs(partial["partial"], True)
        self.assertEqual(partial["objects"], 2)
        self.assertGreater(partial["stream_bytes"], 0)
        self.assertIn("limits", partial)


if __name__ == "__main__":
    unittest.main()

    def test_set_exact_output_reservations_precede_atomic_encoding(self):
        for value in (1.25, Fraction(2, 3)):
            required = fingerprint({value})[1]["stream_bytes"]
            limits = Limits(output_bytes=required - 1)
            with self.subTest(value=value), patch.object(
                    fingerprint_module, "_atomic_bytes",
                    side_effect=AssertionError("encoded before output admission")):
                with self.assertRaisesRegex(FingerprintError, "output bound"):
                    fingerprint({value}, limits=limits)

    def test_empty_set_closing_token_is_reserved_at_exact_boundary(self):
        required = fingerprint(set())[1]["stream_bytes"]
        self.assertEqual(fingerprint(set(), limits=Limits(output_bytes=required))[1]["stream_bytes"],
                         required)
        with self.assertRaisesRegex(FingerprintError, "output bound"):
            fingerprint(set(), limits=Limits(output_bytes=required - 1))
