"""Independently authenticate a candidate-only three-rank suit-transport table.

Transport reconstruction uses literal card combinatorics and saved count
publications, not the production pool/planner as its authority. Existing saved
source verifiers retain their own rank-free admission checks. This module never
looks up a rank, enumerates a board, or calls a solver/trainer. Passing
establishes count transport provenance only.
"""
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import re

from scripts import benchmark_preflop_qq_kk_basis as qq
from scripts import validate_preflop_five_reference as five
from scripts import verify_preflop_jj_kk_basis_publication as jj


ROOT = Path(__file__).resolve().parents[1]
MAX_REPORT_BYTES = 1_048_576
MAX_BASIS_BYTES = 1_000_000
MAX_FRACTION_CHARS = 128
MAX_FRACTION_BITS = 4096
RANKS = "23456789TJQKA"
SUITS = "cdhs"
DECK = tuple(rank + suit for rank in RANKS for suit in SUITS)
PAIR_ROWS = (("AdAs", "KdKs"), ("AdAs", "KcKd"), ("AdAs", "KcKh"),
             ("QdQs", "KdKs"), ("QdQs", "KcKd"), ("QdQs", "KcKh"),
             ("JdJs", "KdKs"), ("JdJs", "KcKd"), ("JdJs", "KcKh"))
SOURCE_PINS = {
    "aa": {"path": "benchmarks/results/preflop-five-basis-v1.json",
           "artifact_sha256": "2ae377e0af6d55491c667d574f41482f2ea6911ba8565ade3b9c8406b54010f7"},
    "qq": {"path": "benchmarks/results/preflop-qq-kk-basis-v1.json",
           "artifact_sha256": "d47fcbdca9cb84275adb8902636d8331bca8b6089e1d62e83cc2160ff09503b8"},
    "jj": {"publication_index_sha256": "9022673f0801fa1481af146f66392b2c7ea4d88c8576946735ecb5ced34bf5e1",
           "report_artifact_sha256": "1f80d95da14890be036c72772f6a88228beff936d05355875384dcc34d6d5156"},
}
EXPECTED_TOP = {"schema_version", "benchmark_id", "status", "source_basis", "admission",
                "rows", "row_count", "total_prior", "artifact_sha256"}
EXPECTED_ROW = {"sb_hand", "bb_hand", "wins", "ties", "losses", "boards",
                "prior_fraction", "source_sb_hand", "source_bb_hand", "suit_permutation"}
EXPECTED_ADMISSION = {
    "sb_range_weights": {"AA": "1", "QQ": "1/2", "JJ": "1/4"},
    "bb_range": "KK", "source_pair_count": 9,
    "target_pair_count": 108, "total_weight": "63",
}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite JSON number")
    return result


def _load_json(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant,
                      parse_float=_finite_float)


def _canonical_sha(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _artifact(report):
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    return _canonical_sha(unsigned)


def _bounded_file(path, limit):
    path = Path(path)
    _need(not path.is_symlink() and path.is_file() and path.stat().st_size <= limit,
          f"Missing, symlinked, or oversized source: {path.name}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _need(len(raw) <= limit, f"Source exceeded its read bound: {path.name}")
    return raw


def _fraction(value, *, positive=False):
    _need(type(value) is str and 0 < len(value) <= MAX_FRACTION_CHARS,
          "Fraction must be a bounded canonical string")
    _need(re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?", value) is not None,
          "Fraction must use a plain integer or rational token")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("Malformed fraction") from exc
    _need(result.numerator.bit_length() <= MAX_FRACTION_BITS and
          result.denominator.bit_length() <= MAX_FRACTION_BITS,
          "Fraction exceeds the exact arithmetic bit bound")
    _need(str(result) == value, "Fraction string is not canonical")
    _need(not positive or result > 0, "Fraction must be positive")
    return result


def _hand(value, rank=None):
    _need(type(value) is str and len(value) == 4,
          "Hand must be an exact two-card string")
    cards = (value[:2], value[2:])
    order = {card: index for index, card in enumerate(DECK)}
    _need(all(card in order for card in cards) and cards[0] != cards[1],
          "Hand contains invalid or repeated cards")
    _need(tuple(sorted(cards, key=order.__getitem__)) == cards,
          "Hand cards are not in literal canonical order")
    if rank is not None:
        _need(cards[0][0] == rank and cards[1][0] == rank,
              "Hand has the wrong pocket rank")
    return cards


def _expected_pairs():
    result = []
    for rank in "AQJ":
        sb_hands = tuple(tuple(sorted(hand, key=DECK.index))
                         for hand in itertools.combinations(tuple(rank + s for s in SUITS), 2))
        bb_hands = tuple(tuple(sorted(hand, key=DECK.index))
                         for hand in itertools.combinations(tuple("K" + s for s in SUITS), 2))
        for sb in sb_hands:
            for bb in bb_hands:
                _need(not set(sb) & set(bb), "Different-rank fixture unexpectedly blocks")
                result.append(("".join(sb), "".join(bb)))
    _need(len(result) == 108 and len(set(result)) == 108,
          "Literal target pair census changed")
    return result


def _source_rows():
    paths = {"aa": ROOT / SOURCE_PINS["aa"]["path"],
             "qq": ROOT / SOURCE_PINS["qq"]["path"],
             "jj": jj.PUBLICATION / "report.json"}
    raws = {name: _bounded_file(path, MAX_BASIS_BYTES) for name, path in paths.items()}
    parsed = {name: _load_json(raw) for name, raw in raws.items()}
    _need(parsed["aa"].get("artifact_sha256") == SOURCE_PINS["aa"]["artifact_sha256"] and
          parsed["qq"].get("artifact_sha256") == SOURCE_PINS["qq"]["artifact_sha256"] and
          _artifact(parsed["aa"]) == SOURCE_PINS["aa"]["artifact_sha256"] and
          _artifact(parsed["qq"]) == SOURCE_PINS["qq"]["artifact_sha256"] and
          parsed["jj"].get("artifact_sha256") == SOURCE_PINS["jj"]["report_artifact_sha256"] and
          _artifact(parsed["jj"]) == SOURCE_PINS["jj"]["report_artifact_sha256"],
          "Saved source artifact pin differs")
    _need(five.verify_saved(paths["aa"]).get("status") == "passed",
          "Saved AA basis authentication failed")
    _need(qq.verify_saved(paths["qq"]).get("status") == "passed",
          "Saved QQ basis authentication failed")
    jj_receipt = jj.verify()
    _need(jj_receipt.get("status") == "authenticated-saved-counts-only" and
          jj_receipt.get("report_artifact_sha256") == SOURCE_PINS["jj"]["report_artifact_sha256"],
          "Saved JJ basis authentication failed")
    index_path = jj.PUBLICATION / "index.json"
    jj_index = _bounded_file(index_path, 1_000_000)
    _need(hashlib.sha256(jj_index).hexdigest() == SOURCE_PINS["jj"]["publication_index_sha256"],
          "Saved JJ publication index pin differs")
    basis = {}
    for rank, name in (("A", "aa"), ("Q", "qq")):
        basis[rank] = parsed[name]["independent_physical_count_rows"]
    basis["J"] = parsed["jj"]["independent_physical_count_rows"]
    result = {}
    expected = {"A": "AdAs", "Q": "QdQs", "J": "JdJs"}
    for rank, rows in basis.items():
        _need(type(rows) is list and len(rows) == 3,
              f"Saved {rank} basis must have exactly three rows")
        mapping = {}
        for row in rows:
            _need(type(row) is dict and
                  set(row) == {"sb_hand", "bb_hand", "wins", "ties", "losses", "boards"},
                  f"Saved {rank} row shape differs")
            sb, bb = row["sb_hand"], row["bb_hand"]
            _hand(sb, rank); _hand(bb, "K")
            _need((sb, bb) in PAIR_ROWS and sb == expected[rank],
                  f"Saved {rank} source endpoint differs")
            key = (sb, bb)
            _need(key not in mapping, f"Duplicate saved {rank} source endpoint")
            counts = tuple(row[k] for k in ("wins", "ties", "losses"))
            _need(all(type(count) is int and count >= 0 for count in counts) and
                  type(row["boards"]) is int and row["boards"] == 1_712_304 and
                  sum(counts) == row["boards"], f"Saved {rank} physical row is malformed")
            mapping[key] = {"wins": counts[0], "ties": counts[1],
                            "losses": counts[2], "boards": row["boards"]}
        _need(set(mapping) == {(expected[rank], bb) for _, bb in PAIR_ROWS[:3]},
              f"Saved {rank} three-row basis is incomplete")
        result[rank] = mapping
    for name, path in paths.items():
        _need(hashlib.sha256(_bounded_file(path, MAX_BASIS_BYTES)).digest() ==
              hashlib.sha256(raws[name]).digest(),
              f"Saved {name} source changed during authentication")
    _need(hashlib.sha256(_bounded_file(index_path, 1_000_000)).digest() ==
          hashlib.sha256(jj_index).digest(),
          "Saved JJ index changed during authentication")
    return result


def _source_rank(sb):
    return sb[0]


def _joint_permutation(source_sb, source_bb, target_sb, target_bb, permutation):
    src = (_hand(source_sb), _hand(source_bb))
    tgt = (_hand(target_sb), _hand(target_bb))
    mapping = dict(zip(SUITS, permutation))
    transformed = tuple(tuple(card[0] + mapping[card[1]] for card in hand)
                        for hand in src)
    return all(set(left) == set(right) for left, right in zip(transformed, tgt))


def _typed_json_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            type(k) is str and _typed_json_equal(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(_typed_json_equal(a, b)
                                                for a, b in zip(left, right))
    return left == right


def _preflight_shape(report):
    _need(type(report) is dict and set(report) == EXPECTED_TOP,
          "Candidate report top-level schema differs")
    _need(type(report["schema_version"]) is int and report["schema_version"] == 1 and
          type(report["benchmark_id"]) is str and type(report["status"]) is str and
          report["benchmark_id"] == "preflop-three-rank-transport-v1" and
          report["status"] == "candidate-only" and
          _typed_json_equal(report["source_basis"], SOURCE_PINS) and
          _typed_json_equal(report["admission"], EXPECTED_ADMISSION) and
          type(report["row_count"]) is int and report["row_count"] == 108 and
          type(report["total_prior"]) is str and report["total_prior"] == "1",
          "Candidate fixed request/admission envelope differs")
    _need(type(report["rows"]) is list and len(report["rows"]) == 108,
          "Candidate row count is malformed")
    for row in report["rows"]:
        _need(type(row) is dict and set(row) == EXPECTED_ROW,
              "Candidate physical row schema differs")
        for key in ("sb_hand", "bb_hand", "source_sb_hand", "source_bb_hand"):
            _need(type(row[key]) is str and len(row[key]) == 4,
                  "Candidate hand token exceeds its fixed bound")
        _need(type(row["prior_fraction"]) is str and
              0 < len(row["prior_fraction"]) <= MAX_FRACTION_CHARS,
              "Candidate prior token exceeds its fixed bound")
        _need(type(row["suit_permutation"]) is list and len(row["suit_permutation"]) == 4 and
              all(type(suit) is str and len(suit) == 1 for suit in row["suit_permutation"]),
              "Candidate suit permutation exceeds its fixed bound")
        _need(all(type(row[name]) is int and row[name].bit_length() <= 64
                  for name in ("wins", "ties", "losses", "boards")),
              "Candidate count is not a bounded exact integer")
    _need(type(report["artifact_sha256"]) is str and len(report["artifact_sha256"]) == 64 and
          all(c in "0123456789abcdef" for c in report["artifact_sha256"]),
          "Candidate artifact digest shape differs")


def _validate_envelope(report):
    _preflight_shape(report)
    _need(type(report["artifact_sha256"]) is str and
          report["artifact_sha256"] == _artifact(report),
          "Candidate canonical artifact digest differs")
    _need(type(report["schema_version"]) is int and report["schema_version"] == 1 and
          report["benchmark_id"] == "preflop-three-rank-transport-v1" and
          report["status"] == "candidate-only", "Candidate report identity/status differs")
    _need(_typed_json_equal(report["admission"], EXPECTED_ADMISSION),
          "Candidate fixed admission differs")
    _need(_typed_json_equal(report["source_basis"], SOURCE_PINS),
          "Candidate source basis pins differ")
    _need(type(report["row_count"]) is int and report["row_count"] == 108,
          "Candidate row count is malformed")
    _need(report["total_prior"] == "1" and type(report["total_prior"]) is str,
          "Candidate total exact prior differs")


def verify_candidate_report(report_or_path):
    """Authenticate and validate a serialized candidate table, without counting.

    A mapping can be supplied by a trusted caller; paths are bounded and parsed
    with duplicate-key and nonfinite-number rejection. Fixed request/admission
    fields are rejected before any saved source is read.
    """
    saved_path = None
    saved_raw = None
    if isinstance(report_or_path, (str, Path)):
        saved_path = Path(report_or_path)
        saved_raw = _bounded_file(saved_path, MAX_REPORT_BYTES)
        report = _load_json(saved_raw)
    else:
        report = report_or_path
    _validate_envelope(report)
    basis = _source_rows()
    expected = _expected_pairs()
    _need(len(expected) == 108, "Literal target support has the wrong size")
    seen = set()
    overlap_counts = {"A": {0: 0, 1: 0, 2: 0},
                      "Q": {0: 0, 1: 0, 2: 0},
                      "J": {0: 0, 1: 0, 2: 0}}
    total_prior = Fraction(0, 1)
    for row, (target_sb, target_bb) in zip(report["rows"], expected):
        _need(type(row) is dict and set(row) == EXPECTED_ROW,
              "Candidate physical row schema differs")
        _need(row["sb_hand"] == target_sb and row["bb_hand"] == target_bb and
              type(row["sb_hand"]) is str and type(row["bb_hand"]) is str,
              "Candidate endpoint or row order differs from literal support")
        key = (target_sb, target_bb)
        _need(key not in seen, "Duplicate target pair")
        seen.add(key)
        rank = target_sb[0]
        sb_cards, bb_cards = _hand(target_sb, rank), _hand(target_bb, "K")
        overlap = len({card[1] for card in sb_cards} & {card[1] for card in bb_cards})
        overlap_counts[rank][overlap] += 1
        source_sb, source_bb = row["source_sb_hand"], row["source_bb_hand"]
        _need(source_sb == {"A": "AdAs", "Q": "QdQs", "J": "JdJs"}[rank] and
              type(source_sb) is str and type(source_bb) is str,
              "Candidate source endpoint is not the pinned rank representative")
        source_key = (source_sb, source_bb)
        _need(source_key in basis[rank], "Candidate references a missing source basis row")
        permutation = row["suit_permutation"]
        _need(type(permutation) is list and len(permutation) == 4 and
              all(type(suit) is str and suit in SUITS for suit in permutation) and
              len(set(permutation)) == 4 and
              _joint_permutation(source_sb, source_bb, target_sb, target_bb, permutation),
              "Candidate suit mapping does not jointly map both hands bijectively")
        counts = basis[rank][source_key]
        _need(all(type(row[name]) is int and row[name] == counts[name]
                  for name in ("wins", "ties", "losses", "boards")),
              "Candidate W/T/L counts differ from authenticated source")
        _need(sum(row[name] for name in ("wins", "ties", "losses")) == row["boards"] and
              row["boards"] == 1_712_304, "Candidate physical board coverage differs")
        prior = _fraction(row["prior_fraction"], positive=True)
        expected_prior = {"A": Fraction(1, 63), "Q": Fraction(1, 126),
                          "J": Fraction(1, 252)}[rank]
        _need(prior == expected_prior, "Candidate conditional pair prior differs")
        total_prior += prior
    _need(seen == set(expected), "Candidate target table is incomplete")
    _need(overlap_counts == {rank: {0: 6, 1: 24, 2: 6} for rank in "AQJ"},
          "Literal joint-suit overlap census differs")
    _need(total_prior == 1 and _fraction(report["total_prior"]) == 1,
          "Candidate global exact prior does not normalize")
    result = {
        "status": "transport-authenticated-candidate-only",
        "benchmark_id": "preflop-three-rank-transport-v1",
        "candidate_artifact_sha256": report["artifact_sha256"],
        "source_basis_pins": SOURCE_PINS,
        "physical_pair_rows_authenticated": len(seen),
        "board_outcomes_per_pair": 1_712_304,
        "represented_board_count_informational_only": 184_928_832,
        "overlap_census_by_rank": {rank: {str(k): v for k, v in overlap_counts[rank].items()}
                                    for rank in "AQJ"},
        "exact_global_prior_mass": str(total_prior),
        "rank_calls": 0,
        "board_enumerations": 0,
        "training_calls": 0,
        "equilibrium_or_policy_claim": False,
        "scope": "authenticated source-orbit count transport only; no board enumeration or solver claim",
    }
    if saved_path is not None:
        final_raw = _bounded_file(saved_path, MAX_REPORT_BYTES)
        _need(final_raw == saved_raw and
              hashlib.sha256(final_raw).digest() == hashlib.sha256(saved_raw).digest(),
              "Saved candidate file changed during verification")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    args = parser.parse_args()
    print(json.dumps(verify_candidate_report(args.report), sort_keys=True), flush=True)
