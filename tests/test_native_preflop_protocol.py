"""Direct protocol tests for the optional native preflop rank helper.

These tests never invoke the full-board COUNT operation with valid input.
Set OPENPOKER_NATIVE_BUILD_DIR to a directory containing the already-built
project helper to enable them; ordinary unit-test discovery skips cleanly.
"""
import json
import os
from pathlib import Path
import random
import subprocess
import unittest

from pokerlab.cards import DECK
from scripts.preflop_validation import independent_rank


def _card_id(card):
    return DECK.index(card)


def _padded_rank(rank):
    return tuple(rank) + (0,) * (6 - len(rank))


def _rank_record(hand):
    return f"{len(hand)} " + " ".join(str(_card_id(card)) for card in hand)


def _rank_input(hands):
    return (f"OPENPOKER_NATIVE_V1 RANK {len(hands)}\n" +
            "\n".join(_rank_record(hand) for hand in hands) + "\n").encode("ascii")


class NativePreflopProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_dir = os.environ.get("OPENPOKER_NATIVE_BUILD_DIR")
        if not build_dir:
            raise unittest.SkipTest("OPENPOKER_NATIVE_BUILD_DIR is unset")
        filename = "native-preflop-equity.exe" if os.name == "nt" else "native-preflop-equity"
        cls.binary = Path(build_dir) / filename
        if not cls.binary.is_file():
            raise AssertionError(f"configured native helper is not built at {cls.binary}")

    @classmethod
    def _run(cls, payload):
        return subprocess.run(
            [str(cls.binary)], input=payload, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=30, check=False,
        )

    @classmethod
    def _rank(cls, hands):
        completed = cls._run(_rank_input(hands))
        if completed.returncode != 0:
            raise AssertionError(
                f"native RANK failed ({completed.returncode}): "
                f"{completed.stderr.decode('utf-8', errors='replace')}"
            )
        payload = json.loads(completed.stdout)
        if set(payload) != {"schema_version", "mode", "ranks"}:
            raise AssertionError(f"unexpected native rank response keys: {payload!r}")
        if payload["schema_version"] != 1 or payload["mode"] != "rank":
            raise AssertionError(f"unexpected native rank response header: {payload!r}")
        ranks = payload["ranks"]
        if type(ranks) is not list or len(ranks) != len(hands):
            raise AssertionError(f"unexpected native rank row count: {payload!r}")
        for rank in ranks:
            if (type(rank) is not list or len(rank) != 6
                    or any(type(value) is not int for value in rank)):
                raise AssertionError(f"native rank row is not six integers: {rank!r}")
        return tuple(tuple(rank) for rank in ranks)

    def test_rank_vectors_and_random_hands_match_independent_best_five(self):
        vectors = (
            ("As", "Kd", "Qc", "Jh", "9s"),
            ("As", "Ad", "Kc", "Qh", "Js", "8d"),
            ("As", "Kd", "Qc", "Jh", "9s", "7d", "4c"),
            ("As", "Ad", "Kc", "Qh", "Js", "8d", "4s"),
            ("As", "Ad", "Kc", "Kh", "Qs", "8d", "4c"),
            ("As", "Ad", "Ac", "Kc", "Qh", "8d", "4s"),
            ("As", "Kd", "Qc", "Jh", "Ts", "8d", "4c"),
            ("As", "Js", "9s", "6s", "3s", "Kd", "Qh"),
            ("As", "Ad", "Ac", "Kc", "Kd", "Kh", "2s"),
            ("As", "Ad", "Ac", "Ah", "Kd", "Qc", "Js"),
            ("As", "Ks", "Qs", "Js", "Ts", "9s", "2d"),
            # Wheel and six-high straight; repeated trips and three pairs.
            ("Ac", "2d", "3h", "4s", "5c", "9d", "Kh"),
            ("2c", "3d", "4h", "5s", "6c", "Ad", "Kh"),
            ("As", "Ad", "Ac", "Ks", "Kd", "Kc", "2h"),
            ("As", "Ad", "Ks", "Kd", "Qs", "Qd", "2h"),
            # Kicker distinctions for flush, quads, trips and one pair.
            ("As", "Js", "9s", "6s", "3s", "Kd", "Qh"),
            ("Ah", "Jh", "9h", "6h", "3h", "Kd", "Qh"),
            ("As", "Ad", "Ac", "Ah", "Kd", "Qc", "Js"),
            ("As", "Ad", "Ac", "Ah", "Qd", "Kc", "Js"),
            ("As", "Ad", "Ac", "Kd", "Qh", "Js", "8c"),
            ("As", "Ad", "Ac", "Kd", "Qh", "Ts", "8c"),
            ("As", "Ad", "Kc", "Qh", "Js", "8d", "4s"),
            ("As", "Ad", "Kc", "Qh", "Ts", "8d", "4s"),
        )
        rng = random.Random(20261016)
        random_hands = tuple(tuple(rng.sample(DECK, 7)) for _ in range(1000))
        hands = vectors + random_hands
        actual = self._rank(hands)
        expected = tuple(_padded_rank(independent_rank(hand)) for hand in hands)
        self.assertEqual({rank[0] for rank in actual[:11]}, set(range(9)))
        self.assertEqual(actual, expected)

    def test_rank_protocol_rejects_malformed_input_without_partial_stdout(self):
        good = _rank_record(("As", "Kd", "Qc", "Jh", "9s", "7d", "4c"))
        valid_prefix = b"OPENPOKER_NATIVE_V1 RANK 1\n" + good.encode("ascii") + b"\n"
        malformed = (
            b"OPENPOKER_NATIVE_V1 RANK 0\n",
            b"OPENPOKER_NATIVE_V1 RANK 4097\n",
            b"BAD_MAGIC RANK 1\n" + good.encode("ascii") + b"\n",
            b"OPENPOKER_NATIVE_V1 RANK \xff1\n",
            b"OPENPOKER_NATIVE_V1 RANK \x001\n" + good.encode("ascii") + b"\n",
            b"OPENPOKER_NATIVE_V1 RANK 1\n" + good.encode("ascii") + b"\n" + b" " * (256 * 1024 + 1),
            b"OPENPOKER_NATIVE_V1 RANK 2\n" + good.encode("ascii") + b"\n7 0 1 2 3 4 5 5\n",
            b"OPENPOKER_NATIVE_V1 RANK +1\n" + good.encode("ascii") + b"\n",
            b"OPENPOKER_NATIVE_V1 RANK -1\n",
            b"OPENPOKER_NATIVE_V1 RANK 184467440737095516160\n",
            b"OPENPOKER_NATIVE_V1 RANK 1\n4 0 1 2 3\n",
            b"OPENPOKER_NATIVE_V1 RANK 1\n8 0 1 2 3 4 5 6 7\n",
            b"OPENPOKER_NATIVE_V1 RANK 1\n5 0 1 2 3\n",
            b"OPENPOKER_NATIVE_V1 RANK 1\n7 0 1 2 3 4 5 52\n",
            b"OPENPOKER_NATIVE_V1 RANK 1\n7 0 1 2 3 4 5 5\n",
            b"OPENPOKER_NATIVE_V1 RANK 1\n7 0 1 2 3 4 5",
            b"OPENPOKER_NATIVE_V1 RANK 1\n" + good.encode("ascii") + b"\n0\n",
            b"OPENPOKER_NATIVE_V1 RANK 1\n" + good.encode("ascii") + b"\ntrailing\n",
            b"OPENPOKER_NATIVE_V1 RANK 1\n" + good.encode("ascii") + b"\n\x1aTRAILING\n",
        )
        for payload in malformed:
            with self.subTest(payload=payload[:80]):
                result = self._run(payload)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")

    def test_rank_protocol_accepts_crlf_records(self):
        hand = ("As", "Kd", "Qc", "Jh", "9s")
        record = _rank_record(hand)
        payload = ("OPENPOKER_NATIVE_V1 RANK 1\r\n" + record + "\r\n").encode("ascii")
        completed = self._run(payload)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", errors="replace"))
        response = json.loads(completed.stdout)
        self.assertEqual(response["mode"], "rank")
        self.assertEqual(response["ranks"], [list(_padded_rank(independent_rank(hand)))])
    def test_count_protocol_rejects_bad_shape_and_cards_without_result(self):
        malformed = (
            b"OPENPOKER_NATIVE_V1 COUNT 0\n",
            b"OPENPOKER_NATIVE_V1 COUNT 5\n",
            b"OPENPOKER_NATIVE_V1 COUNT +1\n",
            b"OPENPOKER_NATIVE_V1 COUNT -1\n",
            b"OPENPOKER_NATIVE_V1 COUNT 184467440737095516160\n",
            b"OPENPOKER_NATIVE_V1 COUNT 1\n0 0 1 2\n",
            b"OPENPOKER_NATIVE_V1 COUNT 1\n0 1 1 2\n",
            b"OPENPOKER_NATIVE_V1 COUNT 1\n0 1 2 52\n",
            b"OPENPOKER_NATIVE_V1 COUNT 1\n0 1 2",
            b"OPENPOKER_NATIVE_V1 COUNT 1\n0 1 2 3 4\n",
            b"OPENPOKER_NATIVE_V1 COUNT 1\n0 1 2 3\ntrailing\n",
        )
        for payload in malformed:
            with self.subTest(payload=payload[:80]):
                result = self._run(payload)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
