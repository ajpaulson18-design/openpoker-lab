"""Candidate-only rank-free pooling for AA, AK-suited and AK-offsuit vs KK.

The producer authenticates the saved AA and AK/KK count bases, then transports
their physical counts through joint suit bijections. It never ranks hands,
enumerates boards, builds a game, or trains a strategy. Candidate output is not
an independent proof; use the separately maintained transport verifier.
"""
from fractions import Fraction
import hashlib
import importlib
import json
import math
from pathlib import Path

from pokerlab import preflop_covered_equity as covered
from pokerlab.preflop_full_board_equity import BOARDS_PER_PAIR, FullBoardEquities, plan_preflop_equities
from scripts import validate_preflop_five_reference as five

ROOT = Path(__file__).resolve().parents[1]
AA_REPORT = ROOT / "benchmarks/results/preflop-five-basis-v1.json"
AA_REPORT_RAW_SHA256 = "bb906c0dac2deca79753e48548b5c3c1b7b9cedd92ba3574da934154713b5419"
AA_REPORT_ARTIFACT_SHA256 = "2ae377e0af6d55491c667d574f41482f2ea6911ba8565ade3b9c8406b54010f7"
AK_REPORT_RAW_SHA256 = "89f2720092e659ccd982665cf4fdaa1d33448e30bb25a9321f9111410942e7a7"
AK_REPORT_ARTIFACT_SHA256 = "4f64aea64d85a77153187dfb0b8c537b173674cc542d38200133c5e01aaed982"
AK_INDEX_RAW_SHA256 = "fb08e891b9879d1fb17671a6c71c6019cd0bbb1fdc21fc120737773a9c47ffad"
AA_REPORT_RELATIVE = "benchmarks/results/preflop-five-basis-v1.json"
AK_REPORT_RELATIVE = "benchmarks/results/preflop-ak-kk-basis-v1/report.json"
MAX_SOURCE_BYTES = 1_000_000
MAX_CANDIDATE_BYTES = 1_048_576
SB_RANGE = "AA,AKs,AKo"
BB_RANGE = "KK"
SUITS = "cdhs"


def expected_request():
    """Return a fresh, complete typed request and its fixed target census."""
    return {
        "schema_version": 1,
        "benchmark_id": "preflop-aa-ak-transport-v1",
        "sb_range": SB_RANGE,
        "bb_range": BB_RANGE,
        "weights": {"AA": "1", "AKs": "1", "AKo": "1", "KK": "1"},
        "hand_counts": {"AA": 6, "AKs": 4, "AKo": 12, "KK": 6},
        "target_census": {
            "sb_hands": 22, "bb_hands": 6, "raw_candidates": 132,
            "blocked_candidates": 48, "compatible_pairs": 84,
            "pair_cap": 128, "type_pair_counts": {"AA": 36, "AKs": 12, "AKo": 36},
            "source_classes": 6, "boards_per_pair": BOARDS_PER_PAIR,
        },
        "suit_class_census": {"AA": {"0": 6, "1": 24, "2": 6},
                              "AKs": {"0": 12}, "AKo": {"0": 12, "1": 24}},
        "exact_prior": {"per_pair": "1/84", "total": "1",
                        "type_masses": {"AA": "3/7", "AKs": "1/7", "AKo": "3/7"}},
    }


def _typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            type(key) is str and _typed_equal(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_typed_equal(a, b) for a, b in zip(left, right))
    if type(left) is tuple:
        return len(left) == len(right) and all(_typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def admit(request=None):
    """Validate the complete fixed request and existing pair cap before source I/O."""
    if request is not None and not _typed_equal(request, expected_request()):
        raise ValueError("Requires the complete literal AA/AK vs KK transport request")
    _need(_typed_equal(expected_request()["target_census"]["pair_cap"], covered.MAX_PAIRS),
          "Existing prepared-pair cap changed")
    _need((covered.MAX_HANDS, covered.MAX_CANDIDATES, covered.MAX_SOURCES) ==
          (128, 4096, 32), "Existing prepared-pool caps changed")
    hands, pairs = covered._ranges(SB_RANGE, BB_RANGE)
    census = expected_request()["target_census"]
    _need((len(hands[0]), len(hands[1]), len(hands[0]) * len(hands[1]), len(pairs)) ==
          (census["sb_hands"], census["bb_hands"], census["raw_candidates"],
           census["compatible_pairs"]), "Literal blocker-sensitive pair census changed")
    _need(census["compatible_pairs"] <= covered.MAX_PAIRS,
          "Complete target support exceeds the unchanged prepared-pair cap")
    _need({name: sum(1 for i, _, _ in pairs if _hand_type(hands[0][i]) == name)
           for name in ("AA", "AKs", "AKo")} == census["type_pair_counts"],
          "Literal type support differs from the admitted census")
    class_census = {name: {} for name in ("AA", "AKs", "AKo")}
    for i, j, _ in pairs:
        sb, bb = hands[0][i], hands[1][j]
        kind = _hand_type(sb)
        overlap = len({card[1] for card in sb} & {card[1] for card in bb})
        label = str(overlap)
        class_census[kind][label] = class_census[kind].get(label, 0) + 1
    _need(class_census == expected_request()["suit_class_census"],
          "Joint suit-class census differs from the literal admitted support")
    _need(all(prior == Fraction(1, 84) for _, _, prior in pairs) and
          sum((prior for _, _, prior in pairs), Fraction()) == 1,
          "Global unit-weight prior differs from exact 1/84 support")
    return hands, pairs


def _hand_type(hand):
    a, b = hand
    if a[0] == b[0]:
        return "AA"
    return "AKs" if a[1] == b[1] else "AKo"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _artifact(report):
    return hashlib.sha256(_canonical({key: value for key, value in report.items()
                                     if key != "artifact_sha256"})).hexdigest()


def _bounded_read(path, limit):
    path = Path(path)
    _need(not path.is_symlink() and path.is_file() and path.stat().st_size <= limit,
          f"Missing, symlinked or oversized source: {path.name}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _need(len(raw) <= limit, f"Source exceeded its read bound: {path.name}")
    return raw


def _pairs_no_duplicates(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_json(raw):
    def reject_constant(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Nonfinite JSON number")
        return result
    return json.loads(raw, object_pairs_hook=_pairs_no_duplicates,
                      parse_constant=reject_constant, parse_float=finite_float)


def source_basis():
    return {
        "aa": {"path": AA_REPORT_RELATIVE,
               "raw_sha256": AA_REPORT_RAW_SHA256,
               "artifact_sha256": AA_REPORT_ARTIFACT_SHA256},
        "ak": {"path": AK_REPORT_RELATIVE,
               "raw_sha256": AK_REPORT_RAW_SHA256,
               "artifact_sha256": AK_REPORT_ARTIFACT_SHA256,
               "publication_index_raw_sha256": AK_INDEX_RAW_SHA256},
    }


def _source_rows():
    """Authenticate both saved reports before extracting their six source rows."""
    ak = importlib.import_module("scripts.verify_preflop_ak_kk_basis_publication")
    ak_report_path = ak.PUBLICATION / "report.json"
    ak_index_path = ak.PUBLICATION / "index.json"
    aa_raw = _bounded_read(AA_REPORT, MAX_SOURCE_BYTES)
    ak_raw = _bounded_read(ak_report_path, MAX_SOURCE_BYTES)
    ak_index_raw = _bounded_read(ak_index_path, MAX_SOURCE_BYTES)
    _need(hashlib.sha256(aa_raw).hexdigest() == AA_REPORT_RAW_SHA256 and
          hashlib.sha256(ak_raw).hexdigest() == AK_REPORT_RAW_SHA256 and
          hashlib.sha256(ak_index_raw).hexdigest() == AK_INDEX_RAW_SHA256,
          "Saved raw count report pin differs")
    aa_data, ak_data = _parse_json(aa_raw), _parse_json(ak_raw)
    _need(aa_data.get("artifact_sha256") == AA_REPORT_ARTIFACT_SHA256 and
          _artifact(aa_data) == AA_REPORT_ARTIFACT_SHA256 and
          ak_data.get("artifact_sha256") == AK_REPORT_ARTIFACT_SHA256 and
          _artifact(ak_data) == AK_REPORT_ARTIFACT_SHA256,
          "Saved canonical count report pin differs")
    aa_receipt = five.verify_saved(AA_REPORT)
    _need(type(aa_receipt) is dict and aa_receipt.get("status") == "passed",
          "Published AA/KK physical basis authentication failed")
    ak_receipt = ak.verify()
    _need(type(ak_receipt) is dict and
          ak_receipt.get("status") == "authenticated-saved-counts-only" and
          ak_receipt.get("report_artifact_sha256") == AK_REPORT_ARTIFACT_SHA256,
          "Published AK/KK physical basis authentication failed")
    _need(_bounded_read(AA_REPORT, MAX_SOURCE_BYTES) == aa_raw and
          _bounded_read(ak_report_path, MAX_SOURCE_BYTES) == ak_raw and
          _bounded_read(ak_index_path, MAX_SOURCE_BYTES) == ak_index_raw,
          "Saved physical source changed during authentication")

    rows_aa = _exact_rows(aa_data.get("independent_physical_count_rows"),
                          {("AdAs", "KdKs"), ("AdAs", "KcKd"), ("AdAs", "KcKh")})
    rows_ak = _exact_rows(ak_data.get("independent_physical_count_rows"),
                          {("AcKc", "KdKh"), ("AdKc", "KdKh"), ("AdKc", "KhKs")})
    aa_by_pair = {(row["sb_hand"], row["bb_hand"]): row for row in rows_aa}
    ak_by_pair = {(row["sb_hand"], row["bb_hand"]): row for row in rows_ak}
    return (aa_by_pair, ak_by_pair,
            {"aa": AA_REPORT_ARTIFACT_SHA256, "ak": AK_REPORT_ARTIFACT_SHA256})


def _exact_rows(rows, expected):
    _need(type(rows) is list and len(rows) == len(expected),
          "Saved source report has an unexpected physical row count")
    by_pair = {}
    for row in rows:
        _need(type(row) is dict and set(row) ==
              {"sb_hand", "bb_hand", "wins", "ties", "losses", "boards"},
              "Saved physical source row shape differs")
        key = (row["sb_hand"], row["bb_hand"])
        _need(key not in by_pair and key in expected,
              "Saved physical source endpoint is duplicated or unexpected")
        _need(all(type(row[name]) is int and row[name] >= 0
                  for name in ("wins", "ties", "losses", "boards")) and
              row["boards"] == BOARDS_PER_PAIR and
              sum(row[name] for name in ("wins", "ties", "losses")) == BOARDS_PER_PAIR,
              "Saved physical source row has invalid exact counts")
        by_pair[key] = dict(row)
    _need(set(by_pair) == expected, "Saved physical source endpoints are incomplete")
    return [by_pair[key] for key in sorted(expected)]


def _as_table(sb_hand, bb_range, rows):
    plan = plan_preflop_equities(sb_hand, bb_range)
    plan.validate()
    by_pair = {(row["sb_hand"], row["bb_hand"]): row for row in rows}
    expected_pairs = {("".join(plan.hands[0][i]), "".join(plan.hands[1][j]))
                      for i, j, _ in plan.pairs}
    _need(set(by_pair) == expected_pairs, "Authenticated source rows differ from rank-free plan")
    counts, worlds = [], []
    for i, j, prior in plan.pairs:
        row = by_pair[("".join(plan.hands[0][i]), "".join(plan.hands[1][j]))]
        triple = tuple(row[name] for name in ("wins", "ties", "losses"))
        counts.append(triple)
        for sign, count in zip((-1, 0, 1), (triple[2], triple[1], triple[0])):
            if count:
                worlds.append((i, j, float(prior * Fraction(count, BOARDS_PER_PAIR)), sign))
    result = FullBoardEquities(plan.hands, plan.pairs, tuple(counts), tuple(worlds),
                               plan._budget_items)
    result.validate()
    return result


def _report_from_table(table, pins):
    table.validate()
    rows = []
    type_counts = {name: 0 for name in ("AA", "AKs", "AKo")}
    for (i, j, prior), counts, proof in zip(table.pairs, table.counts, table.coverage):
        sb, bb = table.hands[0][i], table.hands[1][j]
        type_counts[_hand_type(sb)] += 1
        source_artifact = (pins["aa"]["artifact_sha256"] if _hand_type(sb) == "AA"
                           else pins["ak"]["artifact_sha256"])
        rows.append({
            "sb_hand": "".join(sb), "bb_hand": "".join(bb),
            "wins": counts[0], "ties": counts[1], "losses": counts[2],
            "boards": BOARDS_PER_PAIR, "prior_fraction": str(prior),
            "source_sb_hand": "".join(proof[1]), "source_bb_hand": "".join(proof[2]),
            "suit_permutation": list(proof[3]), "source_identity_sha256": source_artifact,
        })
    expected = expected_request()
    _need(len(rows) == 84 and type_counts == expected["target_census"]["type_pair_counts"] and
          all(row["prior_fraction"] == "1/84" for row in rows),
          "Pooled physical rows or exact target priors changed")
    report = {
        "schema_version": 1,
        "benchmark_id": expected["benchmark_id"],
        "status": "candidate-only",
        "source_basis": source_basis(),
        "admission": expected,
        "rows": rows,
        "row_count": len(rows),
        "total_prior": "1",
        "type_pair_counts": type_counts,
    }
    report["artifact_sha256"] = _artifact(report)
    _need(len(_canonical(report)) <= MAX_CANDIDATE_BYTES,
          "Candidate output exceeds its separate byte bound")
    return report


def build_candidate(request=None):
    """Build a candidate table from authenticated saved classes after full admission."""
    hands, pairs = admit(request)
    aa_rows, ak_rows, _pins = _source_rows()
    sources = [
        _as_table("AdAs", "KdKs,KcKd,KcKh", list(aa_rows.values())),
        _as_table("AcKc", "KdKh", [ak_rows[("AcKc", "KdKh")]]),
        _as_table("AdKc", "KdKh,KhKs", [ak_rows[("AdKc", "KdKh")],
                                         ak_rows[("AdKc", "KhKs")]]),
    ]
    table = covered.pool_preflop_equities_by_suit(sources, SB_RANGE, BB_RANGE)
    table.validate()
    _need(table.hands == hands and table.pairs == pairs and len(table.coverage) == 84,
          "Pooled target dimensions or exact priors differ from admission")
    return _report_from_table(table, source_basis())


if __name__ == "__main__":
    print(json.dumps(build_candidate(), sort_keys=True, indent=2), flush=True)
