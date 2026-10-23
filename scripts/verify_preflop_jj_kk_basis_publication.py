"""Authenticate the saved JJ/KK count corpus without rebuilding or recounting."""
import hashlib
import json
import math
from pathlib import Path
from datetime import datetime

from scripts import benchmark_preflop_jj_kk_basis as evidence
from scripts import preflop_five_count_reference as reference
from scripts import validate_preflop_five_reference as five
from scripts import benchmark_preflop_qq_kk_basis as qq
from pokerlab.preflop_full_board_equity import plan_preflop_equities

PUBLICATION = evidence.ROOT / "benchmarks/results/preflop-jj-kk-basis-v1"
INDEX_SHA256 = "9022673f0801fa1481af146f66392b2c7ea4d88c8576946735ecb5ced34bf5e1"
INDEX_ARTIFACT_SHA256 = "9bda60a970d566b0f48640ae67c44accfa37f04d584fe179f649edd145957d22"
INDEX_BYTES = 4318
REPORT_SHA256 = "f276da203ce73de024b1e2ae79558e78c8fe589cf82f2032f3aae4910cacadc5"
REPORT_ARTIFACT_SHA256 = "1f80d95da14890be036c72772f6a88228beff936d05355875384dcc34d6d5156"
MAX_INDEX_BYTES = 1_000_000
MAX_REPORT_BYTES = 1_000_000
MAX_STREAM_BYTES = 16_777_216
FROZEN_REVISION = "cfe53c8e9a96993f32740dea1bf3f03405f3701b"
PAIR_ROWS = (("JdJs", "KdKs"), ("JdJs", "KcKd"), ("JdJs", "KcKh"))
AA_PAIR_ROWS = (("AdAs", "KdKs"), ("AdAs", "KcKd"), ("AdAs", "KcKh"))
STAGES = ("reference-all-five", "reference-aa-calibration", "native-aa-calibration",
          "reference-jj", "native-jj")


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


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite JSON number")
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject_constant,
                      parse_float=_finite_float)


def _read(path, limit):
    path = Path(path)
    _need(not path.is_symlink() and path.is_file() and path.stat().st_size <= limit,
          f"Missing, symlinked, or oversized saved file: {path.name}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _need(len(raw) <= limit, f"Saved file changed beyond bound while reading: {path.name}")
    return raw


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _artifact(report):
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    return _digest(unsigned)


def _inventory(root, index):
    _need(not root.is_symlink() and root.is_dir(), "Publication directory missing or symlinked")
    files = index.get("files")
    _need(type(files) is list and len(files) == 11, "Expected exactly eleven mapped corpus files")
    expected = {"report.json", "aa-conformance-report.json"}
    expected.update({f"streams/{stage}.{ext}" for stage in STAGES
                     for ext in ("stdout.json", "stderr.txt")
                     if not (stage == "reference-all-five" and ext == "stdout.json")})
    mapped = set()
    total = 0
    for row in files:
        _need(type(row) is dict and set(row) == {"bytes", "original_path", "path", "sha256"},
              "Malformed index file entry")
        relative = row["path"]
        _need(type(relative) is str and relative in expected and relative not in mapped,
              "Unexpected or duplicate corpus path")
        _need(type(row["bytes"]) is int and 0 <= row["bytes"] <= MAX_STREAM_BYTES and
              type(row["sha256"]) is str and len(row["sha256"]) == 64,
              "Invalid corpus size or digest metadata")
        mapped.add(relative)
        total += row["bytes"]
        _need(total <= MAX_REPORT_BYTES + MAX_STREAM_BYTES * 10,
              "Aggregate saved corpus bytes exceed the bounded inventory")
        raw = _read(root / relative, max(row["bytes"], 1))
        _need(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"],
              f"Saved file bytes differ: {relative}")
    _need(mapped == expected, "Corpus inventory is incomplete")
    actual = {"index.json", "report.json", "aa-conformance-report.json", "streams"}
    for entry in root.iterdir():
        _need(entry.name in actual, "Unexpected publication entry")
        _need(not entry.is_symlink(), "Publication entry is symlinked")
    streams = root / "streams"
    _need(streams.is_dir() and {item.name for item in streams.iterdir()} ==
          {Path(name).name for name in expected if name.startswith("streams/")},
          "Stream directory inventory differs")
    _need((root / "aa-conformance-report.json").is_file(), "Conformance report is missing")
    return {row["path"]: row for row in files}


def _validate_index(root):
    raw = _read(root / "index.json", MAX_INDEX_BYTES)
    _need(len(raw) == INDEX_BYTES and hashlib.sha256(raw).hexdigest() == INDEX_SHA256,
          "Pinned raw index bytes differ")
    index = _json(raw)
    _need(type(index) is dict and index.get("artifact_sha256") == INDEX_ARTIFACT_SHA256,
          "Index artifact identity differs")
    unsigned = {key: value for key, value in index.items() if key != "artifact_sha256"}
    _need(_digest(unsigned) == INDEX_ARTIFACT_SHA256, "Index canonical checksum differs")
    _need(index.get("benchmark_id") == "preflop-jj-kk-basis-publication-v1" and
          type(index.get("schema_version")) is int and index["schema_version"] == 1 and
          index.get("frozen_source_commit") == FROZEN_REVISION and
          index.get("protocol_canonical_sha256") == evidence.SPEC_SHA256 and
          index.get("report_artifact_sha256") == REPORT_ARTIFACT_SHA256,
          "Index protocol/source/report linkage differs")
    execution = index.get("execution")
    _need(type(execution) is dict and execution.get("source_commit") == FROZEN_REVISION and
          type(execution.get("exit_code")) is int and execution["exit_code"] == 0,
          "Recorded execution source or exit status differs")
    started = _utc(execution.get("started_at_utc"))
    finished = _utc(execution.get("finished_at_utc"))
    _need(started <= finished, "Recorded run chronology is reversed")
    dump = index.get("external_binary_dump")
    _need(type(dump) is dict and dump.get("published") is False and
          dump.get("bytes") == five.FIVE_BYTES and type(dump.get("sha256")) is str and
          dump.get("reason"), "External binary dump disclosure differs")
    return raw, index


def _utc(value):
    _need(type(value) is str, "Timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _need(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
          "Timestamp must be timezone-aware UTC")
    return parsed


def _validate_rows(rows, *, stage, expected_pairs=PAIR_ROWS):
    _need(type(rows) is list and len(rows) == len(expected_pairs), f"{stage} row count differs")
    for row, (sb, bb) in zip(rows, expected_pairs):
        _need(type(row) is dict and type(row.get("sb_hand")) is str and
              type(row.get("bb_hand")) is str and row.get("sb_hand") == sb and row.get("bb_hand") == bb,
              f"{stage} row identity/order differs")
        _need(all(type(row.get(name)) is int and row[name] >= 0
                  for name in ("wins", "ties", "losses", "boards")) and
              row["boards"] == 1_712_304 and
              row["wins"] + row["ties"] + row["losses"] == 1_712_304,
              f"{stage} row census differs")


def _validate_report(report, index, files, root):
    _need(type(report) is dict and report.get("artifact_sha256") == REPORT_ARTIFACT_SHA256 and
          _artifact(report) == REPORT_ARTIFACT_SHA256, "Report artifact checksum differs")
    _need(type(report.get("schema_version")) is int and report["schema_version"] == 1 and
          report.get("status") == "passed" and report.get("benchmark_id") == "preflop-jj-kk-basis-v1" and
          report.get("protocol_sha256") == evidence.SPEC_SHA256 and report.get("errors") == [] and
          report.get("native_capture_errors") == [], "Saved run status/protocol/errors differ")
    _need(report.get("stage_order") == list(STAGES) and
          report.get("source_unchanged") is True and report.get("reference_build_unchanged") is True and
          report.get("candidate_build_unchanged") is True and
          report.get("aa_calibration_match") is True and
          report.get("all_three_jj_kk_censuses_agree") is True,
          "Saved completion gates differ")
    spec = report.get("specification")
    admission = report.get("admission")
    _need(type(spec) is dict and type(admission) is dict and
          evidence.planner._typed_equal(admission, evidence.planner.admit_plan().to_record()) and
          evidence.planner._typed_equal(spec, evidence._expected_protocol(admission)) and
          admission.get("status") == "admitted-plan-only" and
          admission.get("provenance", {}).get("candidate_only") is True and
          admission.get("provenance", {}).get("independently_authenticated") is False,
          "Saved request/admission differs")
    aa_plan = plan_preflop_equities("AdAs", "KdKs,KcKd,KcKh")
    aa_plan.validate()
    ref_pairs, ref_admission = reference.pair_admission("JdJs", "KdKs,KcKd,KcKh")
    jj_plan = plan_preflop_equities("JdJs", "KdKs,KcKd,KcKh")
    jj_plan.validate()
    _need(evidence.planner._typed_equal(report.get("aa_calibration_admission"), aa_plan.budget) and
          evidence.planner._typed_equal(report.get("jj_reference_admission"), ref_admission) and
          evidence.planner._typed_equal(report.get("jj_native_admission"), jj_plan.budget) and
          len(ref_pairs) == 3 and
          set(("".join(a), "".join(b)) for a, b in ref_pairs) == set(PAIR_ROWS),
          "Saved full-work admissions differ from current rank-free plans")
    before, after = report.get("source_before"), report.get("source_after")
    _need(type(before) is dict and type(after) is dict and before == after and
          before.get("revision") == FROZEN_REVISION and before.get("status") == [] and
          type(before.get("source_hashes")) is dict and len(before["source_hashes"]) == 746,
          "Historical source checkpoint or 746-file identity map differs")
    _need(all(type(path) is str and type(value) is dict and
              set(value) == {"raw_sha256", "lf_sha256"} and
              all(type(digest) is str and len(digest) == 64 and
                  all(ch in "0123456789abcdef" for ch in digest)
                  for digest in value.values())
              for path, value in before["source_hashes"].items()),
          "Historical source hash map is malformed")
    _validate_build_pair(report.get("reference_build_before"), report.get("reference_build_after"),
                         report.get("reference_build_unchanged"), expected_source="native/preflop_five_card_reference.c",
                         historical=before["source_hashes"])
    _validate_build_pair(report.get("candidate_build_before"), report.get("candidate_build_after"),
                         report.get("candidate_build_unchanged"), expected_source="native/preflop_equity.c",
                         historical=before["source_hashes"])
    _validate_rows(report.get("independent_physical_count_rows"), stage="Reference counts")
    _validate_rows(report.get("native_physical_count_rows"), stage="Native counts")
    _need(report["independent_physical_count_rows"] == report["native_physical_count_rows"],
          "Reference/native exact W/T/L rows differ")
    raw_rows = report.get("reference_physical_count_rows_raw_order")
    _need(type(raw_rows) is list and sorted((r.get("sb_hand"), r.get("bb_hand")) for r in raw_rows) ==
          sorted(PAIR_ROWS), "Raw reference row order/set differs")
    normalized = evidence._rows_in_admitted_order(
        raw_rows, tuple((row["sb_hand"], row["bb_hand"]) for row in raw_rows), PAIR_ROWS)
    _need(normalized == report["independent_physical_count_rows"],
          "Normalized JJ rows differ from raw-reference row mapping")
    conformance = report.get("current_build_conformance")
    _need(type(conformance) is dict and conformance.get("status") == "passed" and
          conformance.get("artifact_sha256") == "09ff4e0a4df90180e5942f9619006ab2525a822dd4ff58998b56358496d59761" and
          conformance.get("reference_build_unchanged") is True and
          conformance.get("five_card_exhaustive", {}).get("status") == "passed" and
          conformance.get("five_card_exhaustive", {}).get("rank_tuples_checked") == five.FIVE_TOTAL,
          "Saved current-build exhaustive conformance evidence differs")
    _need(type(report.get("runtime")) is dict and
          type(report["runtime"].get("python")) is str and
          type(report["runtime"].get("implementation")) is str and
          type(report["runtime"].get("platform")) is str,
          "Saved runtime receipt is malformed")
    _need(report.get("aa_calibration_admission", {}).get("candidate_pairs") == 3 and
          report.get("jj_reference_admission", {}).get("compatible_pairs") == 3 and
          report.get("jj_native_admission", {}).get("compatible_pairs") == 3,
          "Recorded AA/JJ count admissions differ")
    _validate_calls(report.get("numerical_subprocess_calls"), files, report, root)


def _validate_build_pair(before, after, unchanged, *, expected_source, historical):
    _need(type(before) is dict and before == after and unchanged is True,
          "Saved build identity changed or completion flag differs")
    manifest = before.get("manifest")
    _need(type(manifest) is dict and type(manifest.get("schema_version")) is int and
          manifest.get("schema_version") == 1 and
          type(manifest.get("flags")) is list and type(manifest.get("compiler")) is str and
          manifest.get("executable_sha256") == before.get("executable_sha256") and
          type(before.get("manifest_sha256")) is str and
          len(before["manifest_sha256"]) == 64,
          f"Malformed build identity for {expected_source}")
    _need(all(ch in "0123456789abcdef" for ch in before["manifest_sha256"]) and
          type(manifest.get("source_sha256")) is str and
          manifest.get("source_sha256") == historical[expected_source]["raw_sha256"] and
          manifest.get("source_lf_sha256") == historical[expected_source]["lf_sha256"],
          f"Build manifest source linkage differs for {expected_source}")


def _validate_calls(calls, files, report, root):
    _need(type(calls) is list and len(calls) == 5, "Expected exactly five numerical subprocess receipts")
    for ordinal, (call, stage) in enumerate(zip(calls, STAGES), start=1):
        _need(type(call) is dict and type(call.get("ordinal")) is int and
              call.get("ordinal") == ordinal and call.get("stage") == stage and
              call.get("status") == "returned" and type(call.get("returncode")) is int and
              call["returncode"] == 0 and "capture_error" not in call,
              "Numerical subprocess receipt order/status differs")
        for label, ext in (("stdout", "stdout.json"), ("stderr", "stderr.txt")):
            receipt = call.get(label)
            _need(type(receipt) is dict and receipt.get("over_bound") is False and
                  type(receipt.get("bytes_retained")) is int and
                  type(receipt.get("sha256")) is str and len(receipt["sha256"]) == 64 and
                  receipt.get("capture_source") in ("captured-pipe", "seekable-stream", "file-backed-stream"),
                  "Raw stream receipt is incomplete")
            observed = call.get("stdout" if label == "stdout" else "stderr", {}).get(
                "bytes_observed_at_most_limit_plus_one")
            limit = 65_536 if label == "stderr" else MAX_STREAM_BYTES
            _need(type(observed) is int and observed == receipt["bytes_retained"] and
                  0 <= observed <= limit,
                  "Raw stream observed-byte count is malformed")
            if stage == "reference-all-five" and label == "stdout":
                dump = receipt
                _need(dump["bytes_retained"] == five.FIVE_BYTES and
                      dump["sha256"] == "7dfd1ff4ed2761fef77db70b170fdae750cf7c162932087e30163037e4e78e52",
                      "External all-five dump receipt differs")
                continue
            relative = f"streams/{stage}.{ext}"
            entry = files[relative]
            _need(receipt.get("path") == f"captured-native-streams/{stage}-{label}.bin" and
                  receipt.get("bytes_retained") == entry["bytes"] and
                  receipt.get("sha256") == entry["sha256"],
                  "Captured raw subprocess stream differs from mapped artifact")
            raw = _read(root / relative, MAX_STREAM_BYTES)
            if label == "stdout" and stage in ("reference-aa-calibration", "reference-jj"):
                parsed = _json(raw)
                protocol = ("preflop-five-card-basis-v1" if stage == "reference-aa-calibration"
                            else "preflop-five-card-pairs-v2")
                _need(type(parsed) is dict and set(parsed) == {
                      "schema_version", "reference", "pairs", "boards_total",
                      "five_card_rank_calls", "seven_card_rank_calls"} and
                      parsed.get("reference") == protocol and
                      type(parsed.get("schema_version")) is int and parsed["schema_version"] == 1 and
                      all(type(parsed.get(field)) is int for field in
                          ("boards_total", "five_card_rank_calls", "seven_card_rank_calls")) and
                      parsed.get("boards_total") == 5_136_912 and
                      parsed.get("five_card_rank_calls") == 215_750_304 and
                      parsed.get("seven_card_rank_calls") == 10_273_824,
                      "Saved best-five stream census differs")
                expected = (report["current_build_conformance"]["reference_raw_counts"]
                            if stage == "reference-aa-calibration"
                            else report["reference_metadata"]["raw_reference_result"])
                _need(parsed == expected, "Best-five stdout differs from saved full report")
                if stage == "reference-aa-calibration":
                    _need(tuple(five.verify_count_result(parsed)) == tuple(
                        {"sb_hand": row["sb_hand"], "bb_hand": row["bb_hand"],
                         "wins": row["wins"], "ties": row["ties"],
                         "losses": row["losses"], "boards": row["boards"]}
                        for row in report["current_build_conformance"]["independent_physical_count_rows"]),
                        "Raw AA calibration counts differ from conformance")
                else:
                    raw_order = report["reference_physical_count_rows_raw_order"]
                    pairs = tuple(((row["sb_hand"][:2], row["sb_hand"][2:]),
                                   (row["bb_hand"][:2], row["bb_hand"][2:]))
                                  for row in raw_order)
                    expected_rows = tuple((row["sb_hand"], row["bb_hand"], row["wins"], row["ties"],
                                           row["losses"], row["boards"])
                                          for row in raw_order)
                    _need(reference.verify_rows(parsed, pairs) == expected_rows,
                          "Raw JJ stdout rows differ from independently reported rows")
            if label == "stdout" and stage in ("native-aa-calibration", "native-jj"):
                parsed = _json(raw)
                _need(type(parsed) is dict and set(parsed) == {
                      "schema_version", "mode", "counts", "boards_per_pair", "rank_calls"} and
                      type(parsed.get("schema_version")) is int and parsed["schema_version"] == 1 and
                      parsed.get("mode") == "count" and
                      type(parsed.get("boards_per_pair")) is int and parsed.get("boards_per_pair") == 1_712_304 and
                      type(parsed.get("rank_calls")) is int and
                      parsed.get("rank_calls") == 10_273_824,
                      "Saved native stream census differs")
                _need(type(parsed.get("counts")) is list and len(parsed["counts"]) == 3 and
                      all(type(row) is list and len(row) == 3 and
                          all(type(value) is int and value >= 0 for value in row)
                          for row in parsed["counts"]),
                      "Saved native W/T/L count rows are malformed")
                if stage == "native-aa-calibration":
                    expected_counts = report["current_build_conformance"]["candidate_equity_table"]["counts"]
                    _need(parsed["counts"] == [[row["wins"], row["ties"], row["losses"]]
                                                 for row in expected_counts],
                          "Native AA stdout differs from saved conformance")
                else:
                    expected_counts = report["native_physical_count_rows"]
                    _need(parsed.get("counts") == [[row["wins"], row["ties"], row["losses"]]
                                                     for row in expected_counts],
                          "Native JJ stdout differs from saved physical rows")


def _current_source_check(historical):
    state = five.snapshot()
    _need(type(state) is dict and state.get("status") == [] and
          type(state.get("source_hashes")) is dict, "Current checkout must be committed and clean")
    for relative, expected in historical.items():
        path = evidence.ROOT / relative
        _need(not path.is_symlink(), f"Historical source became symlinked: {relative}")
        raw = _read(path, 32 * 1024 * 1024)
        value = {"raw_sha256": hashlib.sha256(raw).hexdigest(),
                 "lf_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
        _need(value["lf_sha256"] == expected["lf_sha256"],
              f"Frozen measured source LF bytes changed: {relative}")
        if relative in state["source_hashes"]:
            _need(state["source_hashes"][relative].get("lf_sha256") == value["lf_sha256"],
                  f"Current identity snapshot differs: {relative}")


def verify(directory=PUBLICATION):
    root = Path(directory)
    raw_index, index = _validate_index(root)
    files = _inventory(root, index)
    _need(files["report.json"]["sha256"] == REPORT_SHA256 and
          files["report.json"]["bytes"] == 753_320 and
          index.get("report_artifact_sha256") == REPORT_ARTIFACT_SHA256,
          "Pinned report raw identity differs")
    report_raw = _read(root / "report.json", MAX_REPORT_BYTES)
    _need(hashlib.sha256(report_raw).hexdigest() == REPORT_SHA256,
          "Pinned report bytes differ")
    report = _json(report_raw)
    _validate_report(report, index, files, root)
    aa_path = evidence.ROOT / "benchmarks/results/preflop-five-basis-v1.json"
    qq_path = evidence.ROOT / "benchmarks/results/preflop-qq-kk-basis-v1.json"
    aa_raw, qq_raw = _read(aa_path, 1_000_000), _read(qq_path, 1_000_000)
    aa_data, qq_data = _json(aa_raw), _json(qq_raw)
    auth = report["basis_authentication"]
    _need(hashlib.sha256(aa_raw).hexdigest() == auth["aa"]["raw_sha256"] and
          hashlib.sha256(qq_raw).hexdigest() == auth["qq"]["raw_sha256"] and
          aa_data.get("artifact_sha256") == auth["aa"]["artifact_sha256"] and
          qq_data.get("artifact_sha256") == auth["qq"]["artifact_sha256"],
          "Saved AA/QQ source report linkage differs")
    _need(five.verify_saved(aa_path).get("status") == "passed" and
          qq.verify_saved(qq_path).get("status") == "passed",
          "Published AA/KK or QQ/KK saved verification failed")
    _validate_linkages(report, aa_data)
    conformance_path = root / "aa-conformance-report.json"
    conformance_raw = _read(conformance_path, MAX_REPORT_BYTES)
    conformance_data = _json(conformance_raw)
    _need(conformance_data == report["current_build_conformance"] and
          _artifact(conformance_data) == conformance_data.get("artifact_sha256") and
          five.verify_saved(conformance_path).get("status") == "passed",
          "Current-build conformance report failed saved verification")
    _need(hashlib.sha256(_read(root / "index.json", MAX_INDEX_BYTES)).hexdigest() ==
          hashlib.sha256(raw_index).hexdigest(), "Index changed during saved verification")
    _inventory(root, index)
    _current_source_check(report["source_before"]["source_hashes"])
    return {"status": "authenticated-saved-counts-only", "benchmark_id": index["benchmark_id"],
            "report_artifact_sha256": REPORT_ARTIFACT_SHA256,
            "source_revision": FROZEN_REVISION, "source_file_count": 746,
            "numerical_subprocess_calls_recorded": 5,
            "physical_pair_censuses_recorded": 4,
            "current_build_all_five_replay_performed": False,
            "physical_counts_recomputed": False, "training_calls": 0}


def _validate_linkages(report, aa_data):
    conformance = report["current_build_conformance"]
    reference_meta = report["reference_metadata"]
    candidate_meta = report["candidate_metadata"]
    ref_build = report["reference_build_before"]
    candidate_build = report["candidate_build_before"]
    raw_rows = report["reference_physical_count_rows_raw_order"]
    by_pair = {(row["sb_hand"], row["bb_hand"]): row for row in raw_rows}
    _need(len(raw_rows) == len(by_pair) == 3 and set(by_pair) == set(PAIR_ROWS) and
          [by_pair[pair] for pair in PAIR_ROWS] == report["independent_physical_count_rows"],
          "Normalized JJ rows differ from the original raw reference row values")
    _need(reference_meta.get("build") == ref_build and
          reference_meta.get("conformance_report_sha256") == conformance.get("artifact_sha256") and
          evidence.planner._typed_equal(reference_meta.get("admission"), report["jj_reference_admission"]),
          "Best-five JJ metadata is not linked to its build/conformance/admission")
    _need(conformance.get("reference_build_before") == ref_build and
          conformance.get("reference_build_after") == ref_build and
          conformance.get("reference_build_unchanged") is True and
          conformance.get("candidate_metadata", {}).get("build") == candidate_build.get("manifest") and
          candidate_meta.get("build") == candidate_build.get("manifest") and
          type(candidate_meta.get("compatible_pairs")) is int and candidate_meta["compatible_pairs"] == 3 and
          type(candidate_meta.get("board_evaluations")) is int and
          candidate_meta["board_evaluations"] == 5_136_912 and
          type(candidate_meta.get("rank_calls")) is int and candidate_meta["rank_calls"] == 10_273_824,
          "Native build identity or physical-work metadata linkage differs")
    _validate_rows(aa_data.get("independent_physical_count_rows"), stage="Published AA counts",
                   expected_pairs=AA_PAIR_ROWS)
    _validate_rows(conformance.get("independent_physical_count_rows"), stage="Conformance AA counts",
                   expected_pairs=AA_PAIR_ROWS)
    _need(aa_data["independent_physical_count_rows"] ==
          conformance["independent_physical_count_rows"],
          "Current-build AA calibration differs from authenticated published AA rows")
    table = report.get("candidate_equity_table")
    _need(type(table) is dict and type(table.get("counts")) is list and len(table["counts"]) == 3,
          "Candidate physical table counts are missing")
    for saved, row in zip(table["counts"], report["native_physical_count_rows"]):
        _need(type(saved) is dict and saved.get("sb_hand") == row["sb_hand"] and
              saved.get("bb_hand") == row["bb_hand"] and
              all(type(saved.get(field)) is int and saved[field] == row[target]
                  for field, target in (("wins", "wins"), ("ties", "ties"), ("losses", "losses"),
                                        ("board_outcomes", "boards"))) and
              type(saved.get("pair_probability")) is float and math.isfinite(saved["pair_probability"]),
              "Candidate table rows differ from saved native W/T/L results")


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default=str(PUBLICATION))
    args = parser.parse_args(argv)
    result = verify(args.directory)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
