"""Host-side V4 selector and active-frame proof contract controls."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pokerlab import exact_selected_solver as solver
from pokerlab import native_exact_four_street as native


def _receipt(group=2, *, iterations=10, visits=7, depth=2, max_hands=3,
             decisions=60, prefixes=60):
    activations = 3 * iterations * visits
    roots = 3 * iterations
    edges = roots * (visits - 1)
    frames = depth + 1
    image_slots = frames * group
    workspace = 64 + 3 * frames + 8 * image_slots
    borrowed = 4 * (depth + 4) * 6
    flow_per_visit = 64 + 4 * 6 + 8 * group
    flow = workspace + activations * flow_per_visit
    validation = decisions * 32 * (1 + group + max_hands * (1 + group)) + prefixes * 64
    total_work, total_entries = 987654, 456789
    route = {
        "roots": roots, "edges": edges, "decisions": decisions, "prefixes": prefixes,
        "cursor_fields": 3, "cursor_frames_upper": workspace + borrowed,
        "caller_entries": workspace + borrowed,
        "caller_work": flow, "router_work_upper": validation, "combined_work": total_work,
        "combined_entries": total_entries,
    }
    done = {"group_size": group, "modeled_work_upper": total_work,
            "retained_entries_upper": total_entries}
    admission = {"combined_work": total_work, "combined_entries": total_entries}
    frame = {
        "group_size": group,
        "frames": frames,
        "image_slots": image_slots,
        "header_entries": 3 * frames,
        "workspace_entries": workspace,
        "workspace_setup_work": workspace,
        "view_fields": 3,
        "lease_fields": 3,
        "borrowed_entries_upper": borrowed,
        "flow_per_visit": flow_per_visit,
        "flow_work_upper": flow,
        "validation_work_upper": validation,
        "activations": activations,
        "activations_upper": activations,
        "released_frames": activations,
        "release_calls": activations,
        "final_active_frames": 0,
        "final_workspace_entries": 0,
        "value_cursor_learning_calls": 0,
        "router_owned_workspace": 1,
        "combined_work": total_work,
        "combined_entries": total_entries,
    }
    return frame, route, done, admission, (iterations, visits, depth, max_hands)


def _line(frame):
    return "\t".join(("FRAME", "active-v1", *(
        f"{name}={frame[name]}" for name in native.FRAME_FIELDS)))


class ActiveFrameWireContractTests(unittest.TestCase):
    def test_flow_and_validation_are_bound_to_their_separate_owners(self):
        frame, route, done, admission, dimensions = _receipt()
        iterations, visits, depth, max_hands = dimensions
        arguments = dict(iterations=iterations, visits=visits, depth=depth,
                         max_hands=max_hands, done=done, admission=admission)
        native._validate_active_frame_receipt(frame, route=route, **arguments)
        for field in ("caller_work", "router_work_upper", "caller_entries"):
            with self.subTest(owner=field), self.assertRaises(ValueError):
                native._validate_active_frame_receipt(frame,
                    route={**route, field: route[field] - 1}, **arguments)

    def test_frame_record_is_exact_ordered_decimal_schema(self):
        frame, *_ = _receipt(group=6)
        parsed = native._parse_frame_record(_line(frame))
        self.assertEqual(parsed, frame)
        self.assertEqual(tuple(parsed), native.FRAME_FIELDS)

    def test_frame_record_rejects_missing_forged_unordered_or_oversized_fields(self):
        frame, *_ = _receipt()
        valid = _line(frame).split("\t")
        invalid = [
            "\t".join(valid[:-1]),
            "\t".join(("FRAME", "active-v1", *valid[3:], valid[2])),
            "\t".join((*valid[:-1], "unknown=0")),
            "\t".join((*valid[:-1], "combined_entries=+1")),
            "\t".join((*valid[:-1], "combined_entries=" + "9" * 21)),
            "\t".join(("FRAME", "active-v2", *valid[2:])),
        ]
        for record in invalid:
            with self.subTest(record=record[-50:]):
                with self.assertRaises(ValueError):
                    native._parse_frame_record(record)

    def test_frame_receipt_binds_group_sizes_zero_decisions_and_combined_owner(self):
        for group in (1, 2, 6):
            frame, route, done, admission, dimensions = _receipt(group=group)
            t, visits, depth, max_hands = dimensions
            self.assertEqual(native._validate_active_frame_receipt(
                frame, iterations=t, visits=visits, depth=depth, max_hands=max_hands,
                done=done, route=route, admission=admission), frame)

        frame, route, done, admission, dimensions = _receipt(
            group=1, visits=1, depth=0, max_hands=1, decisions=0, prefixes=20)
        t, visits, depth, max_hands = dimensions
        native._validate_active_frame_receipt(frame, iterations=t, visits=visits,
            depth=depth, max_hands=max_hands, done=done, route=route, admission=admission)

        frame, route, done, admission, dimensions = _receipt()
        t, visits, depth, max_hands = dimensions
        bad = dict(frame)
        bad["value_cursor_learning_calls"] = 1
        with self.assertRaises(ValueError):
            native._validate_active_frame_receipt(bad, iterations=t, visits=visits,
                depth=depth, max_hands=max_hands, done=done, route=route, admission=admission)
        with self.assertRaises(ValueError):
            native._validate_active_frame_receipt(frame, iterations=t, visits=visits,
                depth=depth, max_hands=max_hands, done=done,
                route={**route, "combined_work": route["combined_work"] + 1}, admission=admission)
        with self.assertRaises(ValueError):
            native._validate_active_frame_receipt(frame, iterations=t, visits=visits,
                depth=depth, max_hands=max_hands, done=done,
                route={**route, "caller_work": 1}, admission=admission)
        for field, changed in (("visits", visits + 1), ("depth", depth + 1),
                               ("max_hands", max_hands + 1)):
            kwargs = {"visits": visits, "depth": depth, "max_hands": max_hands}
            kwargs[field] = changed
            with self.subTest(host_census=field), self.assertRaises(ValueError):
                native._validate_active_frame_receipt(frame, iterations=t,
                    done=done, route=route, admission=admission, **kwargs)
        missing = dict(frame)
        missing.pop("release_calls")
        with self.assertRaises(ValueError):
            native._validate_active_frame_receipt(missing, iterations=t, visits=visits,
                depth=depth, max_hands=max_hands, done=done, route=route, admission=admission)

    def test_active_selector_rejects_unsupported_paths_before_prepare_or_build(self):
        untouched = object()
        with patch.object(solver, "_prepare_exact_selected", side_effect=AssertionError("prepared")), \
             patch.object(native, "executable_identity", side_effect=AssertionError("built")):
            cases = (
                {"native_traversal": "active-frames"},
                {"native_traversal": "active-frames", "native_executable": untouched,
                 "native_admission": "legacy", "native_routing": "indexed"},
                {"native_traversal": "active-frames", "native_executable": untouched,
                 "native_admission": "indexed-v1", "native_routing": "full-history"},
                {"native_traversal": "active-frames", "native_executable": untouched,
                 "native_admission": "indexed-v1", "native_routing": "indexed",
                 "pair_diagnostics": "expanded"},
                {"native_traversal": True},
            )
            for kwargs in cases:
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises((TypeError, ValueError)):
                        solver.solve_four_street_exact_selected(None, **kwargs)

    def test_active_wire_rejects_legacy_preparation_without_fallback(self):
        with self.assertRaisesRegex(ValueError, "Active frames require indexed"):
            native.wire(SimpleNamespace(execution_profile="legacy"), 10,
                        routing="indexed", traversal="active-frames")


if __name__ == "__main__":
    unittest.main()
