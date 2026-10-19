"""Pinned inputs and full-artifact verification for the weighted preflop witness."""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from pathlib import Path

from pokerlab.cards import expand_range

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "benchmarks/preflop-weighted-sequence-v1.json"
SPEC_SHA256 = "5b4a79d0239a42c3911928b0ca5d0f53a54be228e68c62ad9a5f8a2925719fb3"
SOURCE_COMMIT = "a5e1b75ab424c97673f5126796b9d7eae14b0706"
BOARDS_PER_PAIR = 1_712_304
ARTIFACTS = (
    ("benchmarks/results/preflop-push-fold-v1-oracle-pair-0.json",
     "599c1360f321d845b335b798468c3c6af216951663e87b6812ecb56321895b40",
     "cc510379eed9484f30e59e428917a9e55ba027a7",
     "AdAs", "KdKs", 1_410_336, 9_308, 292_660),
    ("benchmarks/results/preflop-push-fold-v1-oracle-pair-1.json",
     "61cecc13d773b26496a14ffee1612dfaf5149981e4fcdb12bdbad65db2660160",
     "d639fecaee1c9f1ca1eaec95bb29e3162ddd00ff",
     "QdQs", "AsKh", 968_267, 7_226, 736_811),
    ("benchmarks/results/preflop-push-fold-v1-oracle-pair-2.json",
     "fc6ae5898eac160de79ed4d9c652c632d000966867f1b296bc7dbae682e98e52",
     "864c80c32739f6665b6010c200ad31bcb32e439f",
     "QdQs", "KdKs", 292_846, 9_336, 1_410_122),
)
EXPECTED_PRIORS = (Fraction(8, 13), Fraction(1, 13), Fraction(4, 13))
EXPECTED_CENSUS = {
    "decision_nodes": 7,
    "fold_terminals": 6,
    "showdown_terminals": 6,
    "public_states": 19,
    "information_sets": (6, 8),
    "sequences": (19, 19),
    "oop_lp": (26, 82, 2241),
    "ip_lp": (28, 80, 2349),
}


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _blob_sha1(path: Path) -> str:
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def load_pinned_fixture() -> tuple[dict, list[dict], tuple[dict, dict]]:
    """Load only the frozen fixture and three checked-in oracle pair artifacts.

    This path verifies artifact integrity and provenance without invoking any
    ranker, board iterator, solver, or production tree.
    """
    spec_bytes = SPEC_PATH.read_bytes()
    spec = json.loads(spec_bytes)
    if canonical_sha256(spec) != SPEC_SHA256:
        raise ValueError("Weighted sequence fixture differs from its frozen checksum")
    fixture = spec.get("fixture")
    if (type(fixture) is not dict or fixture.get("sb_range") != "AsAd:1,QsQd:0.5"
            or fixture.get("bb_range") != "AsKh:0.25,KsKd:1"
            or fixture.get("config") != {
                "small_blind": 0.5, "big_blind": 1,
                "starting_stack": [4, 3], "raise_sizes": [0.5, 1],
                "max_raises": 1, "include_all_in": True,
            }):
        raise ValueError("Unexpected weighted sequence fixture")
    source_rows = []
    table = []
    for row, (relative, expected_hash, expected_blob, sb, bb, wins, ties, losses) in zip(
            spec["chance"]["source_files"], ARTIFACTS):
        if row != relative:
            raise ValueError("Count source order differs from the frozen fixture")
        path = ROOT / relative
        data = json.loads(path.read_bytes())
        digest = data.get("artifact_sha256")
        if digest != expected_hash or canonical_sha256(
                {key: value for key, value in data.items() if key != "artifact_sha256"}) != expected_hash:
            raise ValueError(f"Count artifact checksum mismatch: {relative}")
        if _blob_sha1(path) != expected_blob:
            raise ValueError(f"Count artifact is not the pinned source blob: {relative}")
        counts = data.get("counts")
        wanted = {"sb_hand": sb, "bb_hand": bb, "wins": wins, "ties": ties,
                  "losses": losses, "boards": BOARDS_PER_PAIR}
        if (data.get("provenance", {}).get("git_revision") != "151c35a6739251bb280b5be4373c35a05daa2950"
                or data.get("phase") != "independent-full-board-oracle"
                or data.get("benchmark_id") != "preflop-push-fold-v1"
                or type(counts) is not dict
                or any(counts.get(key) != value for key, value in wanted.items())
                or wins + ties + losses != BOARDS_PER_PAIR):
            raise ValueError(f"Pinned full-board counts differ: {relative}")
        source_rows.append({
            "path": relative,
            "canonical_artifact_sha256": expected_hash,
            "pinned_git_blob_sha1": expected_blob,
            "source_commit": SOURCE_COMMIT,
            "sb_hand": sb, "bb_hand": bb,
            "wins": wins, "ties": ties, "losses": losses,
            "boards": BOARDS_PER_PAIR,
        })
        table.append({"sb_hand": sb, "bb_hand": bb,
                      "wins": wins, "ties": ties, "losses": losses,
                      "boards": BOARDS_PER_PAIR})
    if len(source_rows) != 3 or spec["chance"].get("source_commit") != SOURCE_COMMIT:
        raise ValueError("Incomplete pinned source provenance")

    ranges = (expand_range(fixture["sb_range"]), expand_range(fixture["bb_range"]))
    compatible = []
    raw = []
    for sb_hand, sb_weight in ranges[0].items():
        for bb_hand, bb_weight in ranges[1].items():
            if set(sb_hand).isdisjoint(bb_hand):
                pair = ("".join(sb_hand), "".join(bb_hand))
                mass = Fraction.from_float(sb_weight) * Fraction.from_float(bb_weight)
                compatible.append(pair)
                raw.append(mass)
    total = sum(raw, Fraction(0))
    priors = tuple(value / total for value in raw)
    expected_pairs = tuple((row[3], row[4]) for row in ARTIFACTS)
    if tuple(compatible) != expected_pairs or priors != EXPECTED_PRIORS:
        raise ValueError("Physical pair order or collision-conditioned priors changed")
    if tuple((r["sb_hand"], r["bb_hand"]) for r in table) != expected_pairs:
        raise ValueError("Oracle artifacts do not cover the compatible pair set")
    return spec, source_rows, ranges
