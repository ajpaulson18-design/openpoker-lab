"""Independent literal AA/AK versus KK count-transport reconstruction.

This oracle never calls the candidate or production pool/range/orbit helpers.
It authenticates saved source counts, constructs private cards literally, and
checks every physical pair and one joint four-suit bijection per row.
"""
from fractions import Fraction
import hashlib
import itertools
from pathlib import Path

from scripts import preflop_three_rank_transport_validation as io
from scripts import validate_preflop_five_reference as five

ROOT = Path(__file__).resolve().parents[1]
SUITS = "cdhs"
DECK = {r + s for r in "23456789TJQKA" for s in SUITS}
LIMIT = 1_048_576
SOURCE_PINS = {
    "aa": {"path": "benchmarks/results/preflop-five-basis-v1.json",
           "raw_sha256": "bb906c0dac2deca79753e48548b5c3c1b7b9cedd92ba3574da934154713b5419",
           "artifact_sha256": "2ae377e0af6d55491c667d574f41482f2ea6911ba8565ade3b9c8406b54010f7"},
    "ak": {"path": "benchmarks/results/preflop-ak-kk-basis-v1/report.json",
           "raw_sha256": "89f2720092e659ccd982665cf4fdaa1d33448e30bb25a9321f9111410942e7a7",
           "artifact_sha256": "4f64aea64d85a77153187dfb0b8c537b173674cc542d38200133c5e01aaed982",
           "publication_index_raw_sha256": "fb08e891b9879d1fb17671a6c71c6019cd0bbb1fdc21fc120737773a9c47ffad"},
}
SOURCE_ENDPOINTS = {
    "aa": {("AdAs", "KdKs"), ("AdAs", "KcKd"), ("AdAs", "KcKh")},
    "ak": {("AcKc", "KdKh"), ("AdKc", "KdKh"), ("AdKc", "KhKs")},
}
TOP = {"schema_version", "benchmark_id", "status", "source_basis", "admission",
       "rows", "row_count", "total_prior", "type_pair_counts", "artifact_sha256"}
ROW = {"sb_hand", "bb_hand", "wins", "ties", "losses", "boards", "prior_fraction",
       "source_sb_hand", "source_bb_hand", "suit_permutation", "source_identity_sha256"}
EXPECTED_ADMISSION = {
    "schema_version": 1, "benchmark_id": "preflop-aa-ak-transport-v1",
    "sb_range": "AA,AKs,AKo", "bb_range": "KK",
    "weights": {"AA": "1", "AKs": "1", "AKo": "1", "KK": "1"},
    "hand_counts": {"AA": 6, "AKs": 4, "AKo": 12, "KK": 6},
    "target_census": {"sb_hands": 22, "bb_hands": 6, "raw_candidates": 132,
                      "blocked_candidates": 48, "compatible_pairs": 84, "pair_cap": 128,
                      "type_pair_counts": {"AA": 36, "AKs": 12, "AKo": 36},
                      "source_classes": 6, "boards_per_pair": 1_712_304},
    "suit_class_census": {"AA": {"0": 6, "1": 24, "2": 6},
                          "AKs": {"0": 12}, "AKo": {"0": 12, "1": 24}},
    "exact_prior": {"per_pair": "1/84", "total": "1",
                    "type_masses": {"AA": "3/7", "AKs": "1/7", "AKo": "3/7"}},
}
need = io._need


def _hand(value):
    need(type(value) is str and len(value) == 4, "Private hand must contain exactly two cards")
    cards = value[:2], value[2:]
    need(all(c in DECK for c in cards) and len(set(cards)) == 2,
         "Private hand has an invalid or repeated card")
    need(cards == tuple(sorted(cards)), "Private hand must use lexical card serialization")
    return cards


def _type(hand):
    a, b = _hand(hand)
    if a[0] == b[0] == "A":
        return "AA"
    need({a[0], b[0]} == {"A", "K"}, "Unexpected target SB ranks")
    return "AKs" if a[1] == b[1] else "AKo"


def _physical_pairs():
    aces = tuple("A" + s for s in SUITS)
    kings = tuple("K" + s for s in SUITS)
    sb = sorted({"".join(sorted(h)) for h in itertools.combinations(aces, 2)} |
                {"".join(sorted((a, k))) for a in aces for k in kings})
    bb = sorted("".join(sorted(h)) for h in itertools.combinations(kings, 2))
    result = [(s, b) for s in sb for b in bb if not set(_hand(s)) & set(_hand(b))]
    need(len(sb) == 22 and len(bb) == 6 and len(result) == len(set(result)) == 84,
         "Literal private-card census changed")
    return result


def _source_rows():
    # Each raw/canonical identity is checked independently of producer parsing.
    paths = {name: ROOT / pin["path"] for name, pin in SOURCE_PINS.items()}
    raws = {name: io._bounded_file(path, LIMIT) for name, path in paths.items()}
    for name, raw in raws.items():
        need(hashlib.sha256(raw).hexdigest() == SOURCE_PINS[name]["raw_sha256"],
             "Source report raw pin differs")
    parsed = {}
    for name, raw in raws.items():
        pin = SOURCE_PINS[name]
        data = io._load_json(raw)
        need(type(data) is dict and data.get("artifact_sha256") == pin["artifact_sha256"]
             and io._artifact(data) == pin["artifact_sha256"], "Source report canonical pin differs")
        parsed[name] = data
    need(five.verify_saved(paths["aa"]).get("status") == "passed", "Published AA saved counts failed")
    from scripts import verify_preflop_ak_kk_basis_publication as ak
    receipt = ak.verify(paths["ak"].parent)
    need(receipt.get("status") == "authenticated-saved-counts-only" and
         receipt.get("report_artifact_sha256") == SOURCE_PINS["ak"]["artifact_sha256"],
         "Published AK source authentication failed")
    index_path = paths["ak"].parent / "index.json"
    index_raw = io._bounded_file(index_path, 65_536)
    need(hashlib.sha256(index_raw).hexdigest() == SOURCE_PINS["ak"]["publication_index_raw_sha256"],
         "Published AK index raw pin differs")
    result = {}
    for name, data in parsed.items():
        rows = data.get("independent_physical_count_rows")
        need(type(rows) is list and len(rows) == 3, "Source basis must contain exactly three classes")
        seen = set()
        for row in rows:
            need(type(row) is dict and set(row) == {"sb_hand", "bb_hand", "wins", "ties", "losses", "boards"},
                 "Source physical row schema differs")
            pair = row["sb_hand"], row["bb_hand"]
            _hand(pair[0]); _hand(pair[1])
            need(pair in SOURCE_ENDPOINTS[name] and pair not in seen, "Source endpoint is unexpected or duplicate")
            seen.add(pair)
            counts = tuple(row[k] for k in ("wins", "ties", "losses"))
            need(all(type(c) is int and c >= 0 for c in counts) and
                 type(row["boards"]) is int and row["boards"] == sum(counts) == 1_712_304,
                 "Source physical count type or board total differs")
            result[pair] = (*counts, row["boards"], SOURCE_PINS[name]["artifact_sha256"])
        need(seen == SOURCE_ENDPOINTS[name], "Source basis endpoint coverage differs")
    for name, path in paths.items():
        need(io._bounded_file(path, LIMIT) == raws[name], "Source report changed during authentication")
    need(io._bounded_file(index_path, 65_536) == index_raw, "Source index changed during authentication")
    return result


def _joint_map(source, target, permutation):
    mapping = dict(zip(SUITS, permutation))
    mapped = [set(card[0] + mapping[card[1]] for card in _hand(hand)) for hand in source]
    return all(a == set(_hand(b)) for a, b in zip(mapped, target))


def _preflight(candidate):
    need(type(candidate) is dict and set(candidate) == TOP, "Candidate transport schema differs")
    need(type(candidate["schema_version"]) is int and candidate["schema_version"] == 1 and
         candidate["benchmark_id"] == "preflop-aa-ak-transport-v1" and
         candidate["status"] == "candidate-only" and
         type(candidate["row_count"]) is int and candidate["row_count"] == 84 and
         type(candidate["total_prior"]) is str and candidate["total_prior"] == "1" and
         io._typed_json_equal(candidate["type_pair_counts"], {"AA": 36, "AKs": 12, "AKo": 36}),
         "Candidate transport identity, count or prior differs")
    need(io._typed_json_equal(candidate["source_basis"], SOURCE_PINS), "Candidate source basis pins differ")
    need(io._typed_json_equal(candidate["admission"], EXPECTED_ADMISSION),
         "Candidate complete literal request/admission differs")
    need(type(candidate["rows"]) is list and len(candidate["rows"]) == 84, "Candidate physical row census differs")
    need(type(candidate["artifact_sha256"]) is str and io._artifact(candidate) == candidate["artifact_sha256"],
         "Candidate transport canonical digest differs")
    expected_pairs = set(_physical_pairs())
    seen = set()
    for row in candidate["rows"]:
        need(type(row) is dict and set(row) == ROW, "Candidate physical row schema differs")
        target = row["sb_hand"], row["bb_hand"]
        source = row["source_sb_hand"], row["source_bb_hand"]
        for hand in (*target, *source):
            _hand(hand)
        need(target in expected_pairs and target not in seen,
             "Candidate physical pair is extra or repeated")
        seen.add(target)
        name = "aa" if _type(target[0]) == "AA" else "ak"
        need(source in SOURCE_ENDPOINTS[name] and
             type(row["source_identity_sha256"]) is str and
             row["source_identity_sha256"] == SOURCE_PINS[name]["artifact_sha256"],
             "Candidate source endpoint or report identity differs")
        need(not set(_hand(target[0])) & set(_hand(target[1])), "Candidate contains a blocked pair")
        need(all(type(row[k]) is int and row[k] >= 0 for k in ("wins", "ties", "losses", "boards"))
             and row["boards"] == row["wins"] + row["ties"] + row["losses"] == 1_712_304,
             "Candidate integer W/T/L counts differ")
        need(type(row["prior_fraction"]) is str and row["prior_fraction"] == "1/84",
             "Candidate exact global pair prior differs")
        perm = row["suit_permutation"]
        need(type(perm) is list and len(perm) == 4 and all(type(s) is str for s in perm)
             and set(perm) == set(SUITS), "Candidate suit map is not one global bijection")
        need(_joint_map(source, target, perm), "Candidate suit map does not preserve both ordered hands")
    need(seen == expected_pairs, "Candidate physical support is incomplete")


def verify(candidate):
    """Authenticate exactly 84 literal compatible pairs; no equity/policy claim."""
    _preflight(candidate)  # Schema, bounded rational spelling and all maps before source I/O.
    source_rows = _source_rows()
    expected = set(_physical_pairs())
    seen, type_counts = set(), {"AA": 0, "AKs": 0, "AKo": 0}
    prior = Fraction()
    orbits = {}
    for row in candidate["rows"]:
        pair = row["sb_hand"], row["bb_hand"]
        need(pair in expected and pair not in seen, "Candidate physical pair is extra or repeated")
        seen.add(pair)
        supplied = row["source_sb_hand"], row["source_bb_hand"]
        need(supplied in source_rows, "Candidate names an unauthenticated source pair")
        matching = {key for key in source_rows for perm in itertools.permutations(SUITS)
                    if _joint_map(key, pair, perm)}
        need(supplied in matching and len(matching) == 1, "Literal source-orbit reconstruction differs")
        reference = source_rows[supplied]
        need(tuple(row[k] for k in ("wins", "ties", "losses", "boards", "source_identity_sha256")) == reference,
             "Candidate physical source counts or source identity differ")
        kind = _type(pair[0])
        type_counts[kind] += 1
        orbits[supplied] = orbits.get(supplied, 0) + 1
        prior += Fraction(1, 84)
    need(seen == expected and prior == 1 and type_counts == {"AA": 36, "AKs": 12, "AKo": 36},
         "Literal physical support or total prior differs")
    expected_orbits = {("AdAs", "KdKs"): 6, ("AdAs", "KcKd"): 24, ("AdAs", "KcKh"): 6,
                       ("AcKc", "KdKh"): 12, ("AdKc", "KdKh"): 24, ("AdKc", "KhKs"): 12}
    need(orbits == expected_orbits, "Literal six-class orbit census differs")
    return {"status": "transport-authenticated-candidate-only", "benchmark_id": "preflop-aa-ak-transport-v1",
            "candidate_artifact_sha256": candidate["artifact_sha256"], "source_basis_pins": SOURCE_PINS,
            "physical_pair_rows_authenticated": 84, "source_classes_authenticated": 6,
            "board_outcomes_per_pair": 1_712_304, "represented_boards_informational_only": 143_833_536,
            "type_pair_counts": type_counts, "type_prior_masses": {"AA": "3/7", "AKs": "1/7", "AKo": "3/7"},
            "source_orbit_members": [{"sb_hand": s, "bb_hand": b, "members": n}
                                     for (s, b), n in sorted(orbits.items())],
            "exact_global_prior_mass": str(prior), "rank_calls": 0, "board_enumerations": 0,
            "training_calls": 0, "equilibrium_or_policy_claim": False,
            "scope": "authenticated blocker-sensitive source count transport only"}


def verify_candidate_report(path):
    raw = io._bounded_file(path, LIMIT)
    result = verify(io._load_json(raw))
    need(io._bounded_file(path, LIMIT) == raw, "Saved candidate changed during authentication")
    return result
