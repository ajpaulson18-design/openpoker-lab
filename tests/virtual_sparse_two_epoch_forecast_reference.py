"""Independent fixed-domain resource forecast for two sparse PROOF9 epochs.

This composes rank-free board geometry with the already independent per-board
envelope. It is a logical reservation model, not native admission, execution,
training, or a memory/RSS measurement.
"""
from __future__ import annotations

from functools import lru_cache

from tests.virtual_frozen_grid_envelope_reference import envelope
from tests.virtual_frozen_grid_preflight_reference import boards, census, geometry


WORK_CAP = 500_000_000
ENTRY_CAP = 2_000_000
PAYLOAD_CAP_BITS = 1 << 30
HISTORY_CAP = 42_000_000
CHANCE_CAP = 110_000_000
PARENT_CAP = 115_000_000
COMPONENT_CAP = 75_000_000
TEMPLATE_CAP = 43_000_000
OUTPUT_CAP_BYTES = 2_100_000

BOARD_COUNT = 2520
PAIR_COUNT = BOARD_COUNT * BOARD_COUNT
MAX_ROWS = 530
MAX_SLOTS = 1282
ROWS = 2 * MAX_ROWS
SLOTS = 2 * MAX_SLOTS
READS = 2120
CATALOG_BLOCKS = 1060
CATALOG_MENUS = 434
HOLDINGS = 2
CATALOG_INFO_ROWS = 1060
CATALOG_ACTION_SLOTS = 2564
CATALOG_LOOKUPS = 7950
MAX_ACTIONS = 4


def _bits_words(bits: int) -> int:
    return (bits + 63) // 64


def _copy(bits: int) -> int:
    return 1 + 2 * _bits_words(bits)


def _add(bits: int) -> int:
    return 2 + 3 * _bits_words(bits)


def _multiply(a: int, b: int) -> int:
    return 2 + 2 * (_bits_words(a) + _bits_words(b)) + _bits_words(a) * _bits_words(b)


def _row_map(rows: int) -> int:
    return 128 + 32 * (rows + 1).bit_length()


def _store_forecast() -> dict[str, int]:
    # Mirrors bounded operations in the component contract using explicit
    # fixed domain maxima; it does not import or call native forecast code.
    constructor = 2048
    lease = 2 * 128
    read = READS * (160 + 32 * MAX_ACTIONS + 2 * _row_map(ROWS)) + 2 * MAX_ROWS * 128
    slot_work = (48 + _copy(649) + _add(649) + _multiply(383, 317) + _add(382) + 64
                 + _multiply(648, 53) + _add(703) + 2 * _multiply(383, 53)
                 + _add(383) + 2 * _copy(436) + 32)
    stage = 2 * (1024 + MAX_ROWS * (512 + 2 * _row_map(MAX_ROWS) +
                                   2 * _row_map(ROWS) + MAX_ACTIONS * slot_work))
    commit = 2 * (2048 + MAX_ROWS * (256 + _row_map(ROWS) + 32 * MAX_ACTIONS + 256))
    enumeration = 2 * MAX_ROWS * (256 + _row_map(MAX_ROWS))
    export = 256 + 3 * MAX_ROWS * (256 + MAX_ACTIONS * (_copy(649) + _copy(382) + 8))
    quantizer = 2 * MAX_ROWS * 12_000
    own = constructor + lease + read + stage + commit + enumeration + export
    component = own + quantizer
    # The component's borrowed history/catalog receipts are composed by the
    # request exactly once below, rather than repeated as component work.
    entries = 256 + 48 * ROWS + 16 * SLOTS + 2048
    payload = 2 * SLOTS * (649 + 382 + 64) + 2 * ROWS * 2048 + 64 * 64_000
    return {"constructor": constructor, "lease": lease, "read": read, "stage": stage,
            "commit": commit, "enumeration": enumeration, "export": export,
            "quantizer": quantizer, "own": own, "component": component,
            "entries": entries, "payload_bits": payload}


def catalog_forecast() -> dict[str, int]:
    words = 1024 + 32 * CATALOG_BLOCKS + 320 * CATALOG_MENUS + CATALOG_BLOCKS * ((HOLDINGS + 63) // 64)
    lookup_cost = (512 + 256 * 20 + 32 * (CATALOG_BLOCKS + 1).bit_length() +
                   8 * ((HOLDINGS + 63) // 64))
    work = 1024 + 8 * CATALOG_BLOCKS + 8 * CATALOG_MENUS + CATALOG_LOOKUPS * lookup_cost
    return {"words": words, "lookup_cost": lookup_cost, "lookups": CATALOG_LOOKUPS, "work": work}


def history_forecast() -> int:
    g = geometry()
    shape = census(next(boards()))
    # Per-call cost is explicitly partitioned: initial source/template visit,
    # two raw walks, all store policy reads, then parent row-id/menu joins.
    edges = sum(item["decision_action_slots"] for item in g["by_street"].values())
    reveals = sum(item["reveals"] for item in g["by_street"].values())
    return (4096 * g["literal_occurrences"] + 1280 +
            2 * (2 * (48 * edges + 80 * reveals + 8)) +
            READS * 288 + ROWS * 640)


def output_upper_bytes() -> int:
    return (336 + 2 * (136 + 176 + 256) + 256 +
            40 * (3 * MAX_ROWS) + 144 * (3 * MAX_SLOTS))


@lru_cache(maxsize=1)
def _per_board_maxima() -> dict[str, object]:
    maximum = {"rows": 0, "slots": 0, "chance_delta": 0,
               "raw_families": [0] * 6, "raw_family_sum": 0,
               "staged_payload_bits": 0, "full_target_zero": 0}
    seen = 0
    for board in boards():
        e = envelope(board)
        case = census(board)
        seen += 1
        maximum["rows"] = max(maximum["rows"], e[0])
        maximum["slots"] = max(maximum["slots"], e[1])
        maximum["chance_delta"] = max(maximum["chance_delta"], e[5] - 65_536)
        family = tuple(e[6:12])
        maximum["raw_families"] = [max(old, value) for old, value in
                                    zip(maximum["raw_families"], family)]
        maximum["raw_family_sum"] = max(maximum["raw_family_sum"], sum(family))
        maximum["staged_payload_bits"] = max(maximum["staged_payload_bits"], e[16])
        maximum["full_target_zero"] += int(not case["full_target_positive"])
    if seen != BOARD_COUNT:
        raise ArithmeticError("board generator did not produce all 2,520 selectors")
    maximum["raw_family_sum_from_axis_maxima"] = sum(maximum["raw_families"])
    return maximum


def pair_forecast(first_board, second_board) -> dict[str, int]:
    """Compose the additive variable terms for a concrete ordered selector pair."""
    first = envelope(tuple(first_board))
    second = envelope(tuple(second_board))
    return {
        "chance_work": first[5] + second[5] - 65_536,
        "raw_family_work": sum(first[6:12]) + sum(second[6:12]),
        "staged_payload_bits": max(first[16], second[16]),
        "supported_rows": first[0] + second[0],
        "supported_slots": first[1] + second[1],
    }


def check_caps(result: dict[str, object], caps: dict[str, int] | None = None) -> bool:
    """Apply explicit ceilings, useful for checking strict rejection edges."""
    limits = {"total_work": WORK_CAP, "history_work": HISTORY_CAP,
              "chance_work": CHANCE_CAP, "parent_numeric_work": PARENT_CAP,
              "store_component_work": COMPONENT_CAP, "catalog_work": COMPONENT_CAP,
              "total_entries": ENTRY_CAP, "total_payload_bits": PAYLOAD_CAP_BITS,
              "output_bytes": OUTPUT_CAP_BYTES}
    if caps:
        limits.update(caps)
    values = result["components"]
    return all(values[name] <= limit for name, limit in limits.items())


def forecast() -> dict[str, object]:
    """Return the complete additive worst-case two-selector request ledger."""
    g = geometry()
    c = census(next(boards()))
    maxima = _per_board_maxima()
    store = _store_forecast()
    catalog = catalog_forecast()
    history = history_forecast()
    chance = 65_536 + 2 * maxima["chance_delta"]
    parent_numeric = (1_040_000 + 4096 + 512 * ROWS +
                      2 * maxima["raw_family_sum_from_axis_maxima"])
    out_bytes = output_upper_bytes()
    # The fixed 43M template/source allowance includes the existing bounded
    # 3M geometry allowance, including selector parsing and trace metadata.
    total_work = (TEMPLATE_CAP + catalog["work"] + history + chance + store["component"] +
                  parent_numeric + 16 * out_bytes)

    raw_stage_entries = (8 * MAX_ROWS + 2 * MAX_SLOTS + 64 * 19 + 64)
    entries = (131_072 + catalog["words"] + store["entries"] + 12_000 +
               (32 * g["literal_occurrences"] + 1) + 16_384 + raw_stage_entries +
               out_bytes + 4096)
    payload_bits = (131_072 * 64 + 64 * catalog["words"] + store["payload_bits"] +
                    (1 << 20) + 8 * (1 << 20) + (1 << 22) +
                    maxima["staged_payload_bits"] + 8 * out_bytes + 4096 * 64 +
                    32 * 181)  # source integer scratch, independent of row payload

    components = {
        "template_work": TEMPLATE_CAP,
        "catalog_work": catalog["work"],
        "history_work": history,
        "chance_work": chance,
        "store_component_work": store["component"],
        "parent_numeric_work": parent_numeric,
        "output_serialization_work": 16 * out_bytes,
        "total_work": total_work,
        "catalog_words": catalog["words"],
        "store_entries": store["entries"],
        "chance_entries": 12_000,
        "history_entries": 32 * g["literal_occurrences"] + 1,
        "parent_entries": 16_384,
        "raw_stage_entries": raw_stage_entries,
        "output_bytes": out_bytes,
        "total_entries": entries,
        "template_payload_bits": 131_072 * 64,
        "catalog_payload_bits": 64 * catalog["words"],
        "store_payload_bits": store["payload_bits"],
        "chance_payload_bits": 1 << 20,
        "history_payload_bits": 8 << 20,
        "parent_payload_bits": 4 << 20,
        "raw_stage_payload_bits": maxima["staged_payload_bits"],
        "output_payload_bits": 8 * out_bytes,
        "metadata_payload_bits": 4096 * 64,
        "source_integer_scratch_bits": 32 * 181,
        "total_payload_bits": payload_bits,
    }
    cap_results = {
        "template_work": TEMPLATE_CAP <= 43_000_000,
        "catalog_work": catalog["work"] <= COMPONENT_CAP,
        "history_work": history <= HISTORY_CAP,
        "chance_work": chance <= CHANCE_CAP,
        "store_component_work": store["component"] <= COMPONENT_CAP,
        "parent_numeric_work": parent_numeric <= PARENT_CAP,
        "total_work": total_work <= WORK_CAP,
        "entries": entries <= ENTRY_CAP,
        "payload_bits": payload_bits <= PAYLOAD_CAP_BITS,
        "output_bytes": out_bytes <= OUTPUT_CAP_BYTES,
    }
    return {
        "scope": "logical uniform-PROOF9 two-epoch request forecast; no producer/admission/training claim",
        "selectors": BOARD_COUNT,
        "ordered_pairs_with_replacement": PAIR_COUNT,
        "proposal_law": "uniform public board only",
        "geometry": {"literal_occurrences": g["literal_occurrences"],
                     "max_actor_decisions": g["max_actor_decisions"],
                     "max_total_decisions": g["max_total_decisions"],
                     "target_mix_future_bound": g["max_opponent_past_plus_all_future_decisions_excluding_current"],
                     "max_rows_per_board": maxima["rows"], "max_slots_per_board": maxima["slots"],
                     "first_board_census": {"rows": c["supported_rows"], "slots": c["supported_action_slots"]}},
        "maxima": maxima,
        "store": store,
        "catalog": catalog,
        "components": components,
        "caps_pass": cap_results,
        "forecast_passes_caps": all(cap_results.values()),
        "assumptions": {
            "template_entry_guard": "131072 entries is a reservation; source API does not prove this is a complete allocation census",
            "payload": "static component payload reservation, not RSS",
            "buffering": "one raw walk at a time; epoch one serialized into bounded owned output until epoch two validates",
            "unmodeled": "no native execution, wall-time measurement, policy quality, convergence, or training claim",
        },
    }
