"""Rank-free admission and mocked structural tests for the three-rank LP candidate."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import preflop_three_rank_sequence_candidate as candidate


def synthetic_rows():
    rows = []
    for rank, prior in (("A", "1/63"), ("Q", "1/126"), ("J", "1/252")):
        sb_hands = [(rank + a + rank + b) for i, a in enumerate("cdhs")
                    for b in "cdhs"[i + 1:]]
        bb_hands = ["K" + a + "K" + b for i, a in enumerate("cdhs")
                    for b in "cdhs"[i + 1:]]
        for sb in sb_hands:
            for bb in bb_hands:
                rows.append({"sb_hand": sb, "bb_hand": bb, "wins": 1_712_304,
                             "ties": 0, "losses": 0, "boards": 1_712_304,
                             "prior_fraction": prior})
    return rows


class ThreeRankSequenceCandidateTests(unittest.TestCase):
    def test_modified_whole_request_rejects_before_source_tree_or_lp_access(self):
        bad = deepcopy(candidate.expected_request())
        bad["own_hand_counts"]["sb"] = True
        with patch.object(candidate, "_load_authenticated_transport") as source, \
                patch.object(candidate.rules, "_build") as tree, \
                patch.object(candidate.lp, "_solve_lp") as solve:
            with self.assertRaisesRegex(ValueError, "entire fixed"):
                candidate.build_candidate(bad)
        source.assert_not_called()
        tree.assert_not_called()
        solve.assert_not_called()

    def test_request_constants_are_not_mutable_through_returned_defaults(self):
        first = candidate.expected_request()
        first["candidate_lp_shapes"]["oop"][0] = 999
        first["public_tree"]["decision_nodes"] = 999
        first["lp_caps"]["rows"] = 999
        self.assertEqual(candidate.expected_request()["candidate_lp_shapes"],
                         {key: list(value) for key, value in candidate.EXPECTED_SHAPES.items()})
        self.assertEqual(candidate.expected_request()["public_tree"], candidate.EXPECTED_TREE)
        self.assertEqual(candidate.expected_request()["lp_caps"], candidate.EXPECTED_CAPS)
        with patch.object(candidate, "_load_authenticated_transport") as source:
            with self.assertRaisesRegex(ValueError, "entire fixed"):
                candidate.build_candidate(first)
        source.assert_not_called()

    def test_fraction_lexical_rejection_precedes_fraction_parser(self):
        for bad in ("1e100", "1.5", "+1", "1/01", "2/4", "1/1"):
            with self.subTest(value=bad), patch.object(candidate, "Q",
                                                      side_effect=AssertionError("parsed")):
                with self.assertRaisesRegex(ValueError, "fraction"):
                    candidate._fraction(bad)

    def test_transport_file_is_bounded_and_rechecked_after_authentication(self):
        raw = b"synthetic bounded candidate"
        report = {"artifact_sha256": candidate.TRANSPORT_SHA256, "rows": [{}] * 108}
        receipt = {"candidate_artifact_sha256": candidate.TRANSPORT_SHA256,
                   "physical_pair_rows_authenticated": 108}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            path.write_bytes(raw)

            def verify(saved_path):
                self.assertEqual(saved_path, path)
                path.write_bytes(raw + b" changed")
                return receipt

            with patch.object(candidate, "TRANSPORT_PATH", path), \
                    patch.object(candidate.transport, "_bounded_file",
                                 wraps=candidate.transport._bounded_file) as bounded, \
                    patch.object(candidate.transport, "_load_json", return_value=report), \
                    patch.object(candidate.transport, "_artifact",
                                 return_value=candidate.TRANSPORT_SHA256), \
                    patch.object(candidate.transport, "verify_candidate_report",
                                 side_effect=verify) as authenticate:
                with self.assertRaisesRegex(ValueError, "changed during"):
                    candidate._load_authenticated_transport()
            self.assertEqual(bounded.call_count, 2)
            self.assertTrue(all(call.args[1] == candidate.transport.MAX_REPORT_BYTES
                                for call in bounded.call_args_list))
            authenticate.assert_called_once_with(path)

    def test_oversized_sparse_transport_rejects_before_authentication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            with path.open("wb") as stream:
                stream.truncate(candidate.transport.MAX_REPORT_BYTES + 1)
            with patch.object(candidate, "TRANSPORT_PATH", path), \
                    patch.object(candidate.transport, "verify_candidate_report") as authenticate:
                with self.assertRaisesRegex(ValueError, "oversized"):
                    candidate._load_authenticated_transport()
            authenticate.assert_not_called()

    def test_changed_existing_lp_cap_rejects_before_transport_or_tree(self):
        changed = {**candidate.lp.CAPS, "rows": candidate.lp.CAPS["rows"] + 1}
        with patch.object(candidate.lp, "CAPS", changed), \
                patch.object(candidate, "_load_authenticated_transport") as source, \
                patch.object(candidate.rules, "_build") as tree:
            with self.assertRaisesRegex(ValueError, "LP caps changed"):
                candidate.build_candidate()
        source.assert_not_called()
        tree.assert_not_called()

    def test_synthetic_transport_builds_complete_candidate_without_solving_lp(self):
        rows = synthetic_rows()

        def fake_lp(model, kind):
            player = 0 if kind == "oop_guarantee" else 1
            size = len(model["sequences"][player])
            realization = [Fraction(0)] * size
            realization[0] = Fraction(1)
            # Each flow row after the root is one information-set conservation
            # equation. Split parent realization evenly among its child ids.
            # The model stores each player's flow blocks consecutively; locate
            # rows by their unique unit root and then propagate each constraint.
            me = len(model["infos"][0]) + 1
            block = model["flows"][:me] if player == 0 else model["flows"][me:]
            for flow in block[1:]:
                parent = next(i for i, value in enumerate(flow) if value == -1)
                children = [i for i, value in enumerate(flow) if value == 1]
                for child in children:
                    realization[child] = realization[parent] / len(children)
            opposing = 1 - player
            return ({"kind": kind}, realization, [Fraction(0)],
                    [Fraction(0)] * len(model["sequences"][opposing]))

        with patch.object(candidate, "_load_authenticated_transport",
                          return_value=(rows, {"status": "synthetic-authenticated"})), \
                patch.object(candidate, "_payoff",
                             return_value=[[Fraction(0)] * 11 for _ in range(34)]), \
                patch.object(candidate.lp, "_solve_lp", side_effect=fake_lp) as solve:
            report = candidate.build_candidate()
        self.assertEqual(solve.call_count, 2)
        self.assertEqual(report["status"], "candidate-only")
        self.assertEqual(report["certificate_id"], candidate.CERTIFICATE_ID)
        self.assertEqual(len(report["policies"]), 96)
        self.assertEqual(report["candidate_details"]["candidate_lp_shapes"],
                         candidate.EXPECTED_SHAPES)
        self.assertEqual(report["candidate_details"]["sequence_counts"],
                         {"sb": 34, "bb": 11})
        self.assertEqual(report["candidate_details"]["flow_counts"],
                         {"sb": 13, "bb": 5})
        unsigned = dict(report)
        digest = unsigned.pop("artifact_sha256")
        canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), digest)
        self.assertLessEqual(len(canonical), candidate.MAX_OUTPUT_BYTES)


if __name__ == "__main__":
    unittest.main()
