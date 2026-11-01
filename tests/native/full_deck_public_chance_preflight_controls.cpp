#define main full_deck_public_chance_probe_cli_main
#include "../../native/full_deck_public_chance_probe.cpp"
#undef main

#include <iostream>
#include <string>

namespace {
bool require(bool condition, const char* label) {
    if (!condition) std::cerr << "FAIL " << label << '\n';
    return condition;
}
bool is_zero(const MaterializationReceipt& r) {
    return r.range_vector_allocation_sites == 0 && r.reach_vector_allocation_sites == 0 &&
        r.proposal_integer_parse_calls == 0 && r.kernel_constructor_calls == 0;
}
std::string prefix_request(const std::string& limits, const std::string& ranges) {
    return "OPENPOKER_FULL_DECK_PUBLIC_CHANCE_V1 deck FULL52 limits " + limits +
        " ranges " + ranges + " query PREFIX prefix exact 0";
}
std::string terminal_request(const std::string& limits, const std::string& reach_bits,
                             const std::string& proposal_num = "1",
                             const std::string& proposal_den = "1") {
    return "OPENPOKER_FULL_DECK_PUBLIC_CHANCE_V1 deck FULL52 limits " + limits +
        " ranges 1 1 sb 0 5 3fd0000000000000 bb 15 20 3fe8000000000000"
        " query TERMINAL terminal exact 0 FOLD 3ff0000000000000 " + proposal_num + " " +
        proposal_den + " 1 " + reach_bits + " 24 28 32 36 40";
}
}

int main() {
    bool ok = true;
    const std::string default_limits = "1326 65536 500000000 2000000 1073741824";
    const std::string one_pair = "1 1 sb 0 5 3fd0000000000000 bb 15 20 3fe8000000000000";

    MaterializationReceipt duplicate{};
    const auto duplicate_result = process(prefix_request(default_limits,
        "2 1 sb 0 5 3fd0000000000000 0 5 3fd0000000000000 bb 15 20 3fe8000000000000"), &duplicate);
    ok &= require(duplicate_result == "ERR invalid_range\n" && is_zero(duplicate),
                  "duplicate same-seat holding rejects before materialization");

    MaterializationReceipt reach{};
    const auto high_reach = process(terminal_request(default_limits, "3ff199999999999a"), &reach);
    ok &= require(high_reach == "ERR invalid_query\n" && is_zero(reach),
                  "reach above one rejects before vectors proposal integers or kernel");

    const std::string long_num = "1" + std::string(14999, '0');
    const std::string long_den = "2" + std::string(14999, '0');
    MaterializationReceipt payload{};
    const auto low_payload = process(terminal_request(
        "1326 65536 500000000 2000000 60000", "3ff0000000000000", long_num, long_den), &payload);
    ok &= require(low_payload == "ERR integer_payload_limit\n" && is_zero(payload),
                  "proposal and numeric payload reserve rejects before bigint parse");

    MaterializationReceipt entries{};
    const auto low_entries = process(prefix_request("1326 65536 500000000 100 1073741824", one_pair), &entries);
    ok &= require(low_entries == "ERR storage_limit\n" && is_zero(entries),
                  "input ownership entries reject before range vectors");

    MaterializationReceipt same_cross_seat{};
    const auto overlap = process(prefix_request(default_limits,
        "2 2 sb 0 5 3ff0000000000000 15 20 3ff0000000000000 "
        "bb 0 5 3ff0000000000000 24 28 3ff0000000000000"), &same_cross_seat);
    ok &= require(overlap.rfind("OPENPOKER_FULL_DECK_PUBLIC_CHANCE_RESULT_V1\n", 0) == 0 &&
                  same_cross_seat.range_vector_allocation_sites == 2 &&
                  same_cross_seat.kernel_constructor_calls == 1,
                  "same physical holding across seats remains legal");

    MaterializationReceipt positive{};
    const auto zero_reach = process(terminal_request(default_limits, "8000000000000000"), &positive);
    ok &= require(zero_reach.rfind("OPENPOKER_FULL_DECK_PUBLIC_CHANCE_RESULT_V1\n", 0) == 0 &&
                  positive.range_vector_allocation_sites == 2 &&
                  positive.reach_vector_allocation_sites == 1 &&
                  positive.proposal_integer_parse_calls == 2 &&
                  positive.kernel_constructor_calls == 1,
                  "valid negative zero reach keeps mathematical zero and reaches materialization");

    if (!ok) return 1;
    std::cout << "ALL FULL DECK PUBLIC CHANCE PREFLIGHT CONTROLS PASSED\n";
    return 0;
}
