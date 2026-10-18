"""Direct protocol conformance tests for the optional fixed-street C trainer.

Set OPENPOKER_NATIVE_TRAIN_BUILD_DIR to an existing V2 native build directory
for process-level checks. These tests never build the executable themselves.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "OPENPOKER_FIXED_TRAIN_V2"
MAX_INPUT_BYTES = 8 * 1024 * 1024


def _f64(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def _request(*, mode=0, algorithm=2, iterations=1, hands=(1, 1), nodes=None,
             worlds=None, slots=None, newline="\n") -> bytes:
    if nodes is None:
        nodes = ("D 0 2 1 2", "T " + _f64(0) + " " + _f64(0),
                 "T " + _f64(0) + " " + _f64(0))
    if worlds is None:
        worlds = ((0, 0, 1.0, 0.0),)
    if slots is None:
        slots = sum(int(row.split()[2]) * hands[int(row.split()[1])]
                    for row in nodes if row.startswith("D "))
    header = (f"{PROTOCOL} {mode} {algorithm} {iterations} {hands[0]} {hands[1]} "
              f"{len(nodes)} {len(worlds)} {slots}{newline}")
    body = "".join(row + newline for row in nodes)
    body += "".join(f"{h0} {h1} {_f64(mass)} {_f64(sign_or_signed_mass)}{newline}"
                    for h0, h1, mass, sign_or_signed_mass in worlds)
    return (header + body).encode("ascii")


def _binary_policy(stdout: bytes, expected_slots: int) -> list[float]:
    lines = stdout.decode("ascii").splitlines()
    if not lines or lines[0] != f"{PROTOCOL} POLICY {expected_slots}":
        raise AssertionError(f"unexpected native policy header: {lines[:1]!r}")
    if len(lines) != expected_slots + 1:
        raise AssertionError(f"expected {expected_slots} probabilities, got {len(lines)-1}")
    return [struct.unpack(">d", bytes.fromhex(line))[0] for line in lines[1:]]


def _wide_tree(node_count: int) -> tuple[list[str], int]:
    """Make a shallow, single-parent tree with exactly node_count rows."""
    if node_count < 2:
        raise ValueError("tree needs a decision and a terminal")
    rows: list[str | None] = [None]
    queue: list[tuple[int, int]] = [(0, 0)]
    slots = 0
    while len(rows) < node_count:
        node_index, depth = queue.pop(0)
        action_count = min(12, node_count - len(rows))
        children = list(range(len(rows), len(rows) + action_count))
        rows.extend([None] * action_count)
        rows[node_index] = f"D {depth % 2} {action_count} " + " ".join(map(str, children))
        slots += action_count
        queue.extend((child, depth + 1) for child in children)
    terminal = "T " + _f64(0) + " " + _f64(0)
    return [row if row is not None else terminal for row in rows], slots


class NativeFixedStreetProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get("OPENPOKER_NATIVE_TRAIN_BUILD_DIR")
        if not configured:
            raise unittest.SkipTest("set OPENPOKER_NATIVE_TRAIN_BUILD_DIR for native process conformance")
        build_dir = Path(configured)
        if not build_dir.is_absolute():
            build_dir = ROOT / build_dir
        filename = "native-fixed-street-train.exe" if sys.platform == "win32" else "native-fixed-street-train"
        cls.executable = (build_dir / filename).resolve()
        if not cls.executable.is_file():
            raise unittest.SkipTest(f"native executable not found: {cls.executable}")

    def invoke(self, payload: bytes) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run([str(self.executable)], input=payload,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=15, check=False)

    def assert_rejected_without_policy(self, payload: bytes):
        completed = self.invoke(payload)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, b"")
        self.assertTrue(completed.stderr)

    def test_equal_two_action_one_pair_matches_manual_policy_for_all_algorithms(self):
        for algorithm in range(3):
            with self.subTest(algorithm=algorithm):
                completed = self.invoke(_request(algorithm=algorithm, iterations=7))
                self.assertEqual(completed.returncode, 0, completed.stderr.decode("ascii", "replace"))
                self.assertEqual(_binary_policy(completed.stdout, 2), [0.5, 0.5])

    def test_crlf_records_are_accepted(self):
        completed = self.invoke(_request(newline="\r\n"))
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("ascii", "replace"))
        self.assertEqual(_binary_policy(completed.stdout, 2), [0.5, 0.5])

    def test_scalar_and_public_mode_match_weighted_single_pair_for_all_algorithms(self):
        nodes = (
            "D 0 2 1 2",
            "T " + _f64(0) + " " + _f64(0),
            "T " + _f64(0) + " " + _f64(1),
        )
        for algorithm in range(3):
            scalar = self.invoke(_request(mode=0, algorithm=algorithm, iterations=31,
                                          nodes=nodes, worlds=((0, 0, 1.0, 0.625),)))
            public = self.invoke(_request(mode=1, algorithm=algorithm, iterations=31,
                                          nodes=nodes, worlds=((0, 0, 1.0, 0.625),)))
            with self.subTest(algorithm=algorithm):
                self.assertEqual(scalar.returncode, 0, scalar.stderr.decode("ascii", "replace"))
                self.assertEqual(public.returncode, 0, public.stderr.decode("ascii", "replace"))
                scalar_policy = _binary_policy(scalar.stdout, 2)
                public_policy = _binary_policy(public.stdout, 2)
                self.assertEqual(public_policy, scalar_policy)
                self.assertGreater(public_policy[1], 0.5)

    def test_public_mode_preserves_zero_mean_signed_mass_for_fold_and_showdown(self):
        nodes = (
            "D 0 2 1 2",
            "T " + _f64(1) + " " + _f64(0),  # fixed fold-like payoff
            "T " + _f64(0) + " " + _f64(1),  # signed-mass showdown payoff
        )
        # Same hand pair, positive world masses, cancelling signed masses.
        scalar_worlds = ((0, 0, 0.5, 1.0), (0, 0, 0.5, -1.0))
        public_worlds = ((0, 0, 0.5, 0.5), (0, 0, 0.5, -0.5))
        for algorithm in range(3):
            scalar = self.invoke(_request(mode=0, algorithm=algorithm, iterations=31,
                                          nodes=nodes, worlds=scalar_worlds))
            public = self.invoke(_request(mode=1, algorithm=algorithm, iterations=31,
                                          nodes=nodes, worlds=public_worlds))
            with self.subTest(algorithm=algorithm):
                self.assertEqual(scalar.returncode, 0, scalar.stderr.decode("ascii", "replace"))
                self.assertEqual(public.returncode, 0, public.stderr.decode("ascii", "replace"))
                scalar_policy = _binary_policy(scalar.stdout, 2)
                public_policy = _binary_policy(public.stdout, 2)
                self.assertEqual(public_policy, scalar_policy)
                self.assertGreater(public_policy[0], 0.5)

    def test_ascii_numeric_world_and_complete_input_errors_fail_closed(self):
        good = _request()
        zero_mass = _request(worlds=((0, 0, 0.0, 0.0),))
        invalid_sign = _request(worlds=((0, 0, 1.0, 2.0),))
        invalid_signed_mass = _request(mode=1, worlds=((0, 0, 0.5, 0.5001), (0, 0, 0.5, 0.0)))
        nan_terminal = _request(nodes=("D 0 2 1 2", "T " + _f64(0) + " 7ff8000000000000",
                                       "T " + _f64(0) + " " + _f64(0)))
        malformed = [
            b"NOT_OPENPOKER_V2\n",
            good.replace(b"V2 0 2 1", b"V2 0 2 +1", 1),
            good.replace(b"V2 0 2 1", b"V2 0 2 184467440737095516160000", 1),
            good.replace(b"V2 0 2 1", b"V2\n0 2 1", 1),
            good.replace(b"V2 0 2", b"V2 9 2", 1),
            good.replace(b"D 0 2", b"D 0\n2", 1),
            good.replace(b"T " + _f64(0).encode() + b" " + _f64(0).encode(),
                         b"T " + _f64(0).encode() + b"\n" + _f64(0).encode(), 1),
            good.replace(b"0 0 " + _f64(1).encode(),
                         b"0\n0 " + _f64(1).encode(), 1),
            good[:-5],
            good + b"extra\n",
            good + b"\x1aTRAILING",
            good.replace(b"OPENPOKER_FIXED_TRAIN_V2", b"OPENPOKER_FIXED_TRAIN_V2\x00", 1),
            good + b"\xff",
            zero_mass,
            invalid_sign,
            invalid_signed_mass,
            nan_terminal,
            good + b" " * (MAX_INPUT_BYTES + 1),
        ]
        for index, payload in enumerate(malformed):
            with self.subTest(case=index):
                self.assert_rejected_without_policy(payload)

    def test_rooting_indegree_depth_and_slot_shape_reject_before_output(self):
        invalid = [
            _request(nodes=("T " + _f64(0) + " " + _f64(0), "D 0 1 0"), slots=1),
            _request(nodes=("D 0 2 1 1", "T " + _f64(0) + " " + _f64(0)), slots=2),
            _request(nodes=("D 0 1 3", "T " + _f64(0) + " " + _f64(0)), slots=1),
            # Acyclic, single-parent tree, but IDs run backward: root 0 -> node 2 -> terminal 1.
            _request(nodes=("D 0 1 2", "T " + _f64(0) + " " + _f64(0), "D 1 1 1"), slots=2),
            _request(slots=1),
        ]
        depth_rows = ["D 0 1 1"]
        for child in range(2, 34):
            depth_rows.append(f"D {child % 2} 1 {child}")
        depth_rows.append("T " + _f64(0) + " " + _f64(0))
        invalid.append(_request(nodes=tuple(depth_rows), slots=len(depth_rows) - 1))
        for index, payload in enumerate(invalid):
            with self.subTest(case=index):
                self.assert_rejected_without_policy(payload)

    def test_full_requested_work_cap_rejects_before_training(self):
        nodes, slots = _wide_tree(1000)
        worlds = tuple((0, 0, 1.0 / 384.0, 0.0) for _ in range(384))
        payload = _request(mode=0, algorithm=0, iterations=10_000, nodes=tuple(nodes),
                           worlds=worlds, slots=slots)
        completed = self.invoke(payload)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, b"")
        self.assertIn(b"500,000,000", completed.stderr)

    def test_public_vector_work_cap_is_stricter_than_scalar_for_same_shape(self):
        # C-modeled totals for this shape are 461,235,136 (mode 0) and
        # 769,395,136 (mode 1). The scalar request passes work admission,
        # allocates its bounded buffers, then reaches the truncated node table;
        # public mode rejects at the work guard before allocation/training.
        header = (f"{PROTOCOL} {{mode}} 0 10000 128 128 12 128 1408\n").encode("ascii")
        scalar = self.invoke(header.replace(b"{mode}", b"0"))
        public = self.invoke(header.replace(b"{mode}", b"1"))
        self.assertNotEqual(scalar.returncode, 0)
        self.assertEqual(scalar.stdout, b"")
        self.assertIn(b"truncated node table", scalar.stderr.lower())
        self.assertNotIn(b"500,000,000", scalar.stderr)
        self.assertNotEqual(public.returncode, 0)
        self.assertEqual(public.stdout, b"")
        self.assertIn(b"500,000,000", public.stderr)


class NativeFixedStreetProtocolEncodingTests(unittest.TestCase):
    def test_builder_encodes_signed_mass_not_conditional_mean_for_public_mode(self):
        worlds = ((0, 0, 0.5, 0.5), (0, 0, 0.5, -0.5))
        payload = _request(mode=1, worlds=worlds)
        self.assertIn(_f64(0.5).encode("ascii"), payload)
        self.assertIn(_f64(-0.5).encode("ascii"), payload)
        self.assertNotIn(_f64(1.0).encode("ascii"), payload)


if __name__ == "__main__":
    unittest.main()
