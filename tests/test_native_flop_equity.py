"""Admission, protocol, immutability and optional parity tests for native flop counts."""
from dataclasses import FrozenInstanceError
import json
from itertools import combinations
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from pokerlab import native_flop_equity as native_flop
from pokerlab import native_preflop_equity as native_base
from pokerlab import flop_checkdown_equity as equity
from pokerlab import flop_checkdown_solver as solver
from pokerlab import flop_checkdown_worlds as worlds
from pokerlab.cards import DECK


BOARD = "2c3c4d"
OOP_RANGE = "AsAd:0.5,QsQd:0.25,2c2d:1"
IP_RANGE = "KsKd:1,AhKh:0.5,QsQd:0.75"
ONE_OOP = "AsAd"
ONE_IP = "KsKd"


def make_response(board_ids, pair_rows, counts=None):
    if counts is None:
        counts = [[1000, 0, 980] for _ in pair_rows]
    return {
        "schema_version": 1,
        "mode": "flop",
        "board": list(board_ids),
        "pairs": [list(row) for row in pair_rows],
        "counts": [list(row) for row in counts],
        "unordered_boards_per_pair": 990,
        "ordered_outcomes_per_pair": 1980,
        "board_evaluations": 990 * len(pair_rows),
        "rank_calls": 1980 * len(pair_rows),
    }


class NativeFlopBoundaryTests(unittest.TestCase):
    def plan_call(self, board=BOARD, oop=OOP_RANGE, ip=IP_RANGE):
        return worlds.prepare_flop_worlds(board, oop, ip)

    def test_range_admission_precedes_executable_lookup(self):
        invalid = [
            ("not-a-flop", ONE_OOP, ONE_IP),
            (BOARD, "AsAs", ONE_IP),
            (BOARD, "AsAd", "AsKh"),
            (BOARD, "random", "random"),  # exceeds candidate-pair cap
            (BOARD, "AsAd", "AsAd"),  # no compatible positive private pair
        ]
        with patch.object(native_flop, "_invoke", side_effect=AssertionError("native invoked")) as invoke, \
             patch.object(native_flop.native, "_backend", side_effect=AssertionError("build lookup")) as backend:
            for board, oop, ip in invalid:
                with self.subTest(board=board, oop=oop, ip=ip), self.assertRaises(ValueError):
                    native_flop.prepare_native_flop_checkdown_equities(
                        board, oop, ip, build_directory="missing-explicit-build")
        invoke.assert_not_called()
        backend.assert_not_called()

    def test_weighted_blocker_request_preserves_plan_and_detaches_metadata(self):
        plan = self.plan_call()
        ids = {card: index for index, card in enumerate(DECK)}
        board_ids = [ids[card] for card in plan.board]
        pair_rows = [tuple(ids[card] for card in
                           plan.hands[0][i] + plan.hands[1][j])
                     for i, j, _prior in plan.pairs]
        response = make_response(board_ids, pair_rows)
        manifest = {"compiler": "test compiler", "build_tag": "valid"}
        with patch.object(native_flop, "_invoke", return_value=(response, manifest)) as invoke:
            prepared = native_flop.prepare_native_flop_checkdown_equities(
                BOARD, OOP_RANGE, IP_RANGE, build_directory="explicit-test-build")
        invoke.assert_called_once_with(board_ids, pair_rows, "explicit-test-build")
        self.assertEqual(len(prepared.equities.pairs), 5)
        self.assertEqual(prepared.equities.board, plan.board)
        self.assertEqual(prepared.equities.hands,
                         tuple(tuple(tuple(hand) for hand in hands) for hands in plan.hands))
        self.assertEqual(prepared.equities.pairs, tuple(plan.pairs))
        self.assertEqual(prepared.equities.budget, plan.budget)
        self.assertEqual(prepared.equities.counts, tuple((1000, 0, 980) for _ in pair_rows))
        self.assertEqual(prepared.metadata["backend"], "native-fixed-flop-counts-v1")
        self.assertEqual(prepared.metadata["rank_calls"], 1980 * len(pair_rows))
        self.assertEqual(prepared.metadata["board_evaluations"], 990 * len(pair_rows))
        metadata = prepared.metadata
        metadata["build"]["build_tag"] = "mutated"
        metadata["response"]["counts"][0][0] = -1
        self.assertEqual(prepared.metadata["build"]["build_tag"], "valid")
        self.assertEqual(prepared.metadata["response"]["counts"][0][0], 1000)
        with self.assertRaises(FrozenInstanceError):
            prepared.equities = None

    def test_rejects_wrong_echo_identity_work_counts_and_malformed_category_rows(self):
        plan = self.plan_call(BOARD, ONE_OOP, ONE_IP)
        ids = {card: index for index, card in enumerate(DECK)}
        board_ids = [ids[card] for card in plan.board]
        pair_rows = [tuple(ids[card] for card in plan.hands[0][i] + plan.hands[1][j])
                     for i, j, _ in plan.pairs]
        valid = make_response(board_ids, pair_rows)
        corruptions = (
            ({"schema_version": True}, "identity"),
            ({"mode": "count"}, "identity"),
            ({"board": [True, *board_ids[1:]]}, "echo"),
            ({"board": [board_ids[0], board_ids[0], board_ids[2]]}, "echo"),
            ({"pairs": [[*pair_rows[0][2:], *pair_rows[0][:2]]]}, "echo"),
            ({"pairs": [[pair_rows[0][0], pair_rows[0][1], pair_rows[0][2], True]]}, "echo"),
            ({"unordered_boards_per_pair": True}, "census"),
            ({"rank_calls": 1979}, "census"),
            ({"counts": [[1979, 1, 0]]}, "even"),
            ({"counts": [[1982, 0, 0]]}, "even"),
            ({"counts": [[True, 0, 1979]]}, "even"),
            ({"counts": [[1980, 0]]}, "even"),
            ({"extra": 0}, "unexpected fields"),
        )
        for mutation, message in corruptions:
            response = dict(valid)
            response.update(mutation)
            with self.subTest(mutation=mutation), \
                    patch.object(native_flop, "_invoke", return_value=(response, {})), \
                    self.assertRaisesRegex(ValueError, message):
                native_flop.prepare_native_flop_checkdown_equities(
                    BOARD, ONE_OOP, ONE_IP, build_directory="unused")

    def test_native_source_roles_and_full_parity_when_build_is_explicit(self):
        build_directory = os.environ.get("OPENPOKER_NATIVE_EQUITY_BUILD_DIR")
        if not build_directory:
            self.skipTest("OPENPOKER_NATIVE_EQUITY_BUILD_DIR is unset; no implicit build")

        python_table = equity.prepare_flop_checkdown_equities(BOARD, ONE_OOP, ONE_IP)
        native_prepared = native_flop.prepare_native_flop_checkdown_equities(
            BOARD, ONE_OOP, ONE_IP, build_directory=build_directory)
        native_table = native_prepared.equities
        self.assertEqual(native_table, python_table)
        self.assertEqual(native_table.counts, ((1782, 48, 150),))
        self.assertEqual(native_prepared.metadata["ordered_outcomes"], 1980)

        python_solve = solver.solve_prepared_flop_checkdown(
            python_table, iterations=10, algorithm="cfrplus")
        native_solve = solver.solve_prepared_flop_checkdown(
            native_table, iterations=10, algorithm="cfrplus")
        self.assertEqual(native_solve, python_solve)

        executable, _manifest = native_base._backend(build_directory)
        card_ids = {card: index for index, card in enumerate(DECK)}
        ordered_board = [card_ids[card] for card in python_table.board]
        oop = list(card_ids[card] for card in python_table.hands[0][python_table.pairs[0][0]])
        ip = list(card_ids[card] for card in python_table.hands[1][python_table.pairs[0][1]])
        def raw(payload):
            return subprocess.run([str(executable)], input=payload, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, check=False, timeout=120)
        prefix = native_base.PROTOCOL + " FLOP 1 " + " ".join(map(str, ordered_board)) + " "
        forward = raw((prefix + " ".join(map(str, oop + ip)) + "\n").encode("ascii"))
        reverse = raw((prefix + " ".join(map(str, ip + oop)) + "\n").encode("ascii"))
        self.assertEqual(forward.returncode, 0, forward.stderr.decode("utf-8", "replace"))
        self.assertEqual(reverse.returncode, 0, reverse.stderr.decode("utf-8", "replace"))
        forward_counts = json.loads(forward.stdout)["counts"][0]
        reverse_counts = json.loads(reverse.stdout)["counts"][0]
        self.assertEqual(reverse_counts, [forward_counts[2], forward_counts[1], forward_counts[0]])
        self.assertEqual(sum(forward_counts), 1980)

        # Exercise the protocol's full 128-pair bound. Use one fixed OOP hand
        # and 128 distinct IP hands, all disjoint from both the board and OOP.
        cap_oop = [card_ids[card] for card in ("As", "Ad")]
        blocked = set(ordered_board + cap_oop)
        cap_ip_hands = [pair for pair in combinations(range(len(DECK)), 2)
                        if not (set(pair) & blocked)][:128]
        self.assertEqual(len(cap_ip_hands), 128)
        self.assertEqual(len(set(cap_ip_hands)), 128)
        cap_pairs = [cap_oop + list(hand) for hand in cap_ip_hands]
        cap_request = (native_base.PROTOCOL + " FLOP 128 "
                       + " ".join(map(str, ordered_board)) + " "
                       + " ".join(str(card) for pair in cap_pairs for card in pair) + "\n")
        cap_result = raw(cap_request.encode("ascii"))
        self.assertEqual(cap_result.returncode, 0, cap_result.stderr.decode("utf-8", "replace"))
        cap_payload = json.loads(cap_result.stdout)
        self.assertEqual(cap_payload["board"], ordered_board)
        self.assertEqual(cap_payload["pairs"], cap_pairs)
        self.assertEqual(len(cap_payload["counts"]), 128)
        self.assertTrue(all(type(row) is list and len(row) == 3
                            and all(type(value) is int for value in row)
                            and sum(row) == 1980 and all(value % 2 == 0 for value in row)
                            for row in cap_payload["counts"]))
        self.assertEqual(cap_payload["unordered_boards_per_pair"], 990)
        self.assertEqual(cap_payload["ordered_outcomes_per_pair"], 1980)
        self.assertEqual(cap_payload["board_evaluations"], 126720)
        self.assertEqual(cap_payload["rank_calls"], 253440)

        invalid_requests = [
            (native_base.PROTOCOL + " FLOP 1 " + " ".join(map(str, ordered_board[:2])) + "\n"),
            (native_base.PROTOCOL + " FLOP 1 " + str(ordered_board[0]) + " "
             + str(ordered_board[0]) + " " + str(ordered_board[2]) + " "
             + " ".join(map(str, oop + ip)) + "\n"),
            (prefix + " ".join(map(str, oop + oop)) + "\n"),
            (prefix + " ".join(map(str, oop + ip)) + "\x1aTRAILING\n"),
            (native_base.PROTOCOL + " FLOP 129 " + " ".join(map(str, ordered_board)) + "\n"),
            (native_base.PROTOCOL + " FLOP 2 " + " ".join(map(str, ordered_board)) + " "
             + " ".join(map(str, oop + ip)) + " "
             + " ".join(map(str, [oop[1], oop[0], ip[1], ip[0]])) + "\n"),
        ]
        for request in invalid_requests:
            with self.subTest(request=request[:80]):
                result = raw(request.encode("ascii"))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
