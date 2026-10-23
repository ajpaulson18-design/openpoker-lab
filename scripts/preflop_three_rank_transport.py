"""Candidate-only prepared-count pooling for one fixed three-rank preflop range.

No enumeration or strategy training is available here. The independent checker
must authenticate every physical target and exact prior before reuse.
"""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from pokerlab import preflop_covered_equity as covered
from pokerlab.preflop_full_board_equity import FullBoardEquities, plan_preflop_equities
from scripts import verify_preflop_jj_kk_basis_publication as jj

ROOT = Path(__file__).resolve().parents[1]
SB_RANGE = "AA:1,QQ:0.5,JJ:0.25"
BB_RANGE = "KK"
MAX_REPORT_BYTES = 1_048_576


def expected_request():
    return {"schema_version": 1, "benchmark_id": "preflop-three-rank-transport-v1",
            "sb_range": SB_RANGE, "bb_range": BB_RANGE}


def expected_admission():
    return {"sb_range_weights": {"AA": "1", "QQ": "1/2", "JJ": "1/4"},
            "bb_range": "KK", "source_pair_count": 9,
            "target_pair_count": 108, "total_weight": "63"}


def source_basis():
    return {"aa": {"path": "benchmarks/results/preflop-five-basis-v1.json",
                   "artifact_sha256": jj.evidence.AA_ARTIFACT_SHA256},
            "qq": {"path": "benchmarks/results/preflop-qq-kk-basis-v1.json",
                   "artifact_sha256": jj.evidence.QQ_ARTIFACT_SHA256},
            "jj": {"publication_index_sha256": jj.INDEX_SHA256,
                   "report_artifact_sha256": jj.REPORT_ARTIFACT_SHA256}}


def admit(request=None):
    """Validate the full literal request and covered capacity before source I/O."""
    request = expected_request() if request is None else request
    if not jj.evidence.planner._typed_equal(request, expected_request()):
        raise ValueError("Requires the entire fixed three-rank transport request")
    if (covered.MAX_PAIRS != 128 or covered.MAX_HANDS != 128
            or covered.MAX_CANDIDATES != 4096 or covered.MAX_SOURCES != 32):
        raise ValueError("Existing covered preparation caps changed")
    hands, pairs = covered._ranges(SB_RANGE, BB_RANGE)
    if (len(hands[0]), len(hands[1]), len(pairs)) != (18, 6, 108):
        raise ValueError("Three-rank physical target admission changed")
    expected = {"A": Fraction(1, 63), "Q": Fraction(1, 126), "J": Fraction(1, 252)}
    if any(prior != expected[hands[0][i][0][0]] for i, _, prior in pairs):
        raise ValueError("Three-rank exact target priors changed")
    return hands, pairs


def _source_tables():
    # This saved-data authentication also checks the published AA/QQ sources.
    # Its clean measured-source guard remains mandatory outside isolated tests.
    jj.verify()
    basis = source_basis()
    paths = [ROOT / basis[rank]["path"] for rank in ("aa", "qq")]
    paths.append(jj.PUBLICATION / "report.json")
    tables = []
    for rank, path, pin in zip(("A", "Q", "J"), paths,
                              (basis["aa"]["artifact_sha256"], basis["qq"]["artifact_sha256"],
                               basis["jj"]["report_artifact_sha256"])):
        raw = jj._read(path, 1_000_000)
        data = jj._json(raw)
        if data.get("artifact_sha256") != pin or jj._artifact(data) != pin:
            raise ValueError("Authenticated source basis changed before pooling")
        rows = data["independent_physical_count_rows"]
        expected_pairs = tuple((rank + "d" + rank + "s", bb)
                               for bb in ("KdKs", "KcKd", "KcKh"))
        by_pair = {(row["sb_hand"], row["bb_hand"]): row for row in rows}
        if len(rows) != len(by_pair) or set(by_pair) != set(expected_pairs):
            raise ValueError("Candidate source does not contain the three exact ordered pairs")
        jj._validate_rows([by_pair[pair] for pair in expected_pairs], stage="Candidate source",
                          expected_pairs=expected_pairs)
        plan = plan_preflop_equities(rank + "d" + rank + "s", "KdKs,KcKd,KcKh")
        plan.validate()
        counts, worlds = [], []
        for i, j, prior in plan.pairs:
            key = ("".join(plan.hands[0][i]), "".join(plan.hands[1][j]))
            row = by_pair[key]
            triple = tuple(row[field] for field in ("wins", "ties", "losses"))
            counts.append(triple)
            for sign, count in zip((-1, 0, 1), (triple[2], triple[1], triple[0])):
                if count:
                    worlds.append((i, j, float(prior * Fraction(count, 1_712_304)), sign))
        table = FullBoardEquities(plan.hands, plan.pairs, tuple(counts), tuple(worlds), plan._budget_items)
        table.validate()
        tables.append(table)
    return tables


def build_candidate(request=None):
    """Produce all physical rows; this producer is never the proof authority."""
    hands, pairs = admit(request)
    table = covered.pool_preflop_equities_by_suit(_source_tables(), SB_RANGE, BB_RANGE)
    table.validate()
    if table.hands != hands or table.pairs != pairs or len(table.worlds) != 324:
        raise ValueError("Candidate pooled dimensions or exact priors changed")
    rows = []
    for (i, j, prior), counts, proof in zip(table.pairs, table.counts, table.coverage):
        rows.append({"sb_hand": "".join(table.hands[0][i]), "bb_hand": "".join(table.hands[1][j]),
                     "wins": counts[0], "ties": counts[1], "losses": counts[2],
                     "boards": 1_712_304, "prior_fraction": str(prior),
                     "source_sb_hand": "".join(proof[1]), "source_bb_hand": "".join(proof[2]),
                     "suit_permutation": list(proof[3])})
    report = {"schema_version": 1, "benchmark_id": "preflop-three-rank-transport-v1",
              "status": "candidate-only", "source_basis": source_basis(),
              "admission": expected_admission(), "rows": rows,
              "row_count": 108, "total_prior": "1"}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > MAX_REPORT_BYTES:
        raise ValueError("Candidate report exceeds its separate output bound")
    report["artifact_sha256"] = hashlib.sha256(encoded).hexdigest()
    return report
