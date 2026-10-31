// Explicit one-process exact-product four-street trainer. Integration pending.
#include "exact_selected_cfr.hpp"
#include <charconv>
#include <iomanip>
#include <iostream>
#include <sstream>

namespace {
namespace graph = openpoker::exact_public_graph;
namespace cfr = openpoker::exact_selected_cfr;
constexpr std::size_t input_cap = 64U << 20;
constexpr std::size_t output_cap = 32U << 20;
void need(bool condition, const char* text) { if (!condition) throw std::invalid_argument(text); }
bool space(char c) { return c == ' ' || c == '\n' || c == '\r' || c == '\t'; }
class Parser {
public:
    explicit Parser(std::string text) : text_(std::move(text)) {}
    std::string_view token() {
        while (position_ < text_.size() && space(text_[position_])) ++position_;
        const auto start = position_;
        while (position_ < text_.size() && !space(text_[position_])) ++position_;
        need(position_ > start && position_ - start <= 64, "missing or oversized engine token");
        return std::string_view(text_).substr(start, position_ - start);
    }
    std::string text() { return std::string(token()); }
    std::uint64_t number(std::uint64_t maximum, int base = 10) {
        const auto value = token(); std::uint64_t result = 0;
        need(base != 16 || value.size() == 16, "binary64 field requires sixteen hexadecimal digits");
        const auto parsed = std::from_chars(value.data(), value.data() + value.size(), result, base);
        need(parsed.ec == std::errc{} && parsed.ptr == value.data() + value.size() && result <= maximum,
             "invalid or capped engine unsigned integer");
        return result;
    }
    std::size_t size(std::size_t maximum) { return static_cast<std::size_t>(number(maximum)); }
    std::uint64_t bits() { return number(UINT64_MAX, 16); }
    void finish() {
        while (position_ < text_.size()) need(space(text_[position_++]), "trailing engine request bytes");
    }
private:
    std::string text_; std::size_t position_ = 0;
};
class Writer {
public:
    void token(std::string_view text, bool newline = false) {
        need(text.size() + 1 <= output_cap - written_, "engine result byte ceiling exceeded");
        std::cout << text << (newline ? '\n' : '\t'); written_ += text.size() + 1;
    }
    void number(std::uint64_t value, bool newline = false) { token(std::to_string(value), newline); }
    void probability(double value, bool newline) {
        std::ostringstream formatted;
        formatted << std::hex << std::setw(16) << std::setfill('0') << std::bit_cast<std::uint64_t>(cfr::finite(value));
        token(formatted.str(), newline);
    }
private:
    std::size_t written_ = 0;
};

int run() {
    std::string input; input.reserve(4096);
    for (int ch; (ch = std::cin.get()) != std::char_traits<char>::eof();) {
        need(input.size() < input_cap && ch > 0 && ch < 128, "engine input byte/ASCII ceiling exceeded");
        input.push_back(static_cast<char>(ch));
    }
    Parser parser(std::move(input));
    const auto protocol = parser.token();
    const bool active_frames = protocol == "OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4";
    const bool indexed_admission = active_frames || protocol == "OPENPOKER_NATIVE_EXACT_FOUR_STREET_INDEXED_ADMISSION_V3";
    const bool routed_v2 = protocol == "OPENPOKER_NATIVE_EXACT_FOUR_STREET_ROUTED_V2";
    const bool routed = routed_v2 || indexed_admission;
    need(routed || protocol == "OPENPOKER_NATIVE_EXACT_FOUR_STREET_V1", "unsupported exact engine protocol");
    const auto route = indexed_admission ? std::string("indexed") :
        routed_v2 ? parser.text() : std::string("full-history");
    need((!routed && route == "full-history") || (routed && (route == "shadow" || route == "indexed")),
         "unsupported exact engine routing mode");
    const auto iterations = static_cast<unsigned>(parser.size(10'000));
    const auto cache = parser.size(64);
    const std::array<std::size_t, 2> hands_count{parser.size(1326), parser.size(1326)};
    const auto board_count = parser.size(64), vertex_count = parser.size(250'000), edge_count = parser.size(1'000'000);
    graph::Graph public_graph;
    public_graph.root_id = parser.size(vertex_count ? vertex_count - 1 : 0);
    const auto initial_count = parser.size(256);
    need(iterations >= 10 && cache && hands_count[0] && hands_count[1] && board_count && vertex_count,
         "zero or unsupported exact engine dimensions");
    graph::Limits limits;
    limits.kernel.max_integer_bits = parser.size(65536);
    limits.kernel.max_modeled_work = parser.number(500'000'000);
    limits.kernel.max_storage_entries = parser.size(2'000'000);
    limits.kernel.max_integer_payload_bits = parser.size(1U << 30);
    limits.max_modeled_work = parser.number(500'000'000);
    limits.max_retained_entries = parser.size(2'000'000);
    limits.max_history_bytes = parser.size(16'000'000);
    cfr::Limits training_limits;
    training_limits.max_modeled_work = parser.number(500'000'000);
    training_limits.max_entries = parser.size(25'000'000);
    training_limits.max_action_slots = parser.size(1'000'000);
    training_limits.max_output_values = parser.size(2'000'000);
    // Parser storage is separately bounded by the header and input byte ceiling.
    // No original rank, normalizer, Q witness, pair/world or policy section exists.
    std::array<std::vector<graph::WeightedHand>, 2> hands;
    for (std::size_t side = 0; side < 2; ++side) {
        hands[side].reserve(hands_count[side]);
        for (std::size_t i = 0; i < hands_count[side]; ++i) {
            graph::WeightedHand row;
            row.hand.first = static_cast<std::uint8_t>(parser.size(51));
            row.hand.second = static_cast<std::uint8_t>(parser.size(51));
            row.binary64_weight_bits = parser.bits(); hands[side].push_back(row);
        }
    }
    std::vector<graph::SelectedBoard> boards(board_count);
    for (auto& board : boards) for (auto& card : board.cards) card = static_cast<std::uint8_t>(parser.size(51));
    public_graph.initial_history.reserve(initial_count);
    for (std::size_t i = 0; i < initial_count; ++i) public_graph.initial_history.push_back(parser.text());
    public_graph.vertices.reserve(vertex_count);
    std::size_t parsed_edges = 0;
    for (std::size_t i = 0; i < vertex_count; ++i) {
        const auto kind = parser.token();
        if (kind == "D") {
            const auto actor = static_cast<std::uint8_t>(parser.size(1));
            const auto count = parser.size(edge_count - parsed_edges);
            need(count, "empty native decision");
            parsed_edges += count;
            std::vector<graph::Action> actions; actions.reserve(count);
            std::vector<std::size_t> children; children.reserve(count);
            for (std::size_t j = 0; j < count; ++j) {
                graph::Action action;
                action.name = parser.text(); action.amount_bits = parser.bits(); action.raise_to_bits = parser.bits();
                action.full_raise = parser.size(1) != 0; action.token = parser.text();
                children.push_back(parser.size(vertex_count - 1)); actions.push_back(std::move(action));
            }
            public_graph.vertices.push_back(graph::Vertex::decision(actor, std::move(actions), std::move(children)));
        } else if (kind == "C") {
            const auto street = parser.size(3), card_index = parser.size(6);
            need(street, "zero native street");
            const auto count = parser.size(edge_count - parsed_edges);
            need(count && count <= 64, "empty or oversized selected chance");
            parsed_edges += count;
            std::vector<graph::Branch> branches; branches.reserve(count);
            for (std::size_t j = 0; j < count; ++j) {
                const auto label = parser.text();
                const auto child_text = parser.token();
                std::uint64_t child = 0;
                const auto parsed = std::from_chars(child_text.data(), child_text.data() + child_text.size(), child);
                need(parsed.ec == std::errc{} && parsed.ptr == child_text.data() + child_text.size() && child < vertex_count,
                     "invalid chance child");
                branches.push_back(graph::Branch{label, static_cast<std::size_t>(child)});
            }
            public_graph.vertices.push_back(graph::Vertex::chance(static_cast<graph::Street>(street), card_index, std::move(branches)));
        } else if (kind == "F" || kind == "S") {
            const auto winner = static_cast<std::uint8_t>(kind == "F" ? parser.size(1) : 2);
            const std::array<std::uint64_t, 2> money{parser.bits(), parser.bits()};
            public_graph.vertices.push_back(graph::Vertex::terminal(kind == "F" ? graph::TerminalKind::fold : graph::TerminalKind::showdown,
                winner, money));
        } else throw std::invalid_argument("unknown native graph vertex tag");
    }
    parser.finish(); need(parsed_edges == edge_count, "native edge declaration mismatch");
    graph::Plan plan(std::move(public_graph), std::move(hands[0]), std::move(hands[1]), std::move(boards), iterations, cache, limits,
        indexed_admission ? graph::AdmissionProfile::indexed_v1 : graph::AdmissionProfile::legacy);
    const auto& census = plan.graph_census();
    const auto output_upper = graph::detail::checked_add(census.row_history_bytes_upper,
        graph::detail::checked_add(graph::detail::checked_mul(64, census.decision_hand_slots_upper),
                                  graph::detail::checked_mul(32, census.action_slots_upper)));
    need(output_upper <= output_cap - 8192, "native complete output byte admission exceeded");
    cfr::Trainer trainer(plan, training_limits);
    auto result = active_frames ? trainer.run_active_frames() : route == "shadow" ? trainer.run_indexed_shadow() :
                  route == "indexed" ? trainer.run_indexed() : trainer.run();
    need(result.receipt.final_numeric_workspace_slots == 0, "native numeric buffers remain before R output");
    Writer writer;
    writer.token(active_frames ? "OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_RESULT_V4" :
                 indexed_admission ? "OPENPOKER_NATIVE_EXACT_FOUR_STREET_INDEXED_ADMISSION_RESULT_V3" :
                 routed ? "OPENPOKER_NATIVE_EXACT_FOUR_STREET_ROUTED_RESULT_V2" :
                         "OPENPOKER_NATIVE_EXACT_FOUR_STREET_RESULT_V1", true);
    std::size_t rows = 0, slots = 0;
    plan.for_each_supported_row([&](const graph::RowKey& key, const std::vector<graph::Action>& menu) {
        const auto location = plan.locate(key);
        writer.token("ROW"); writer.number(key.actor); writer.number(key.hand_index); writer.number(key.history.size());
        for (const auto& token : key.history) writer.token(token);
        writer.number(menu.size());
        for (std::size_t a = 0; a < menu.size(); ++a) writer.probability(result.quotient_policy.at(location.offset + a), a + 1 == menu.size());
        ++rows; slots += menu.size();
    });
    writer.token("DONE"); writer.number(rows); writer.number(slots); writer.number(plan.group().size());
    writer.number(plan.rows().size()); writer.number(result.receipt.action_slots);
    writer.number(result.receipt.member_checks); writer.number(result.receipt.expected_member_checks);
    const auto modeled_work = result.receipt.indexed_shadow ?
        result.receipt.indexed_shadow->routing.combined_modeled_work_upper : result.receipt.modeled_work_upper;
    const auto retained_entries = result.receipt.indexed_shadow ?
        result.receipt.indexed_shadow->routing.combined_logical_entries_upper : result.receipt.retained_entries_upper;
    writer.number(modeled_work); writer.number(result.receipt.kernel_work_upper);
    writer.number(retained_entries); writer.number(result.receipt.maximum_numeric_workspace_slots);
    writer.number(result.receipt.final_numeric_workspace_slots); writer.number(plan.kernel().receipt().rank_calls, true);
    if (routed) {
        need(result.receipt.indexed_shadow.has_value(), "routed protocol requires an explicit indexed proof");
        const auto& proof = *result.receipt.indexed_shadow;
        const auto& r = proof.routing;
        writer.token("ROUTE"); writer.token(proof.mode);
        const auto field = [&](std::string_view name, std::uint64_t value, bool last = false) {
            writer.token(std::string(name) + "=" + std::to_string(value), last);
        };
        field("q_rows", r.original_q_rows);
        field("map_entries", r.numeric_map_entries_actual);
        field("map_upper", r.numeric_map_entries_upper);
        field("r_lookup_entries", r.r_lookup_entries);
        field("old_q_histories_retained", r.original_q_histories_retained ? 1 : 0);
        field("q_routes", r.history_route_calls_actual);
        field("q_routes_upper", r.history_route_calls);
        field("q_tokens", r.history_route_tokens_actual);
        field("q_tokens_upper", r.history_route_tokens_upper);
        field("roots", r.root_cursor_calls_actual);
        field("roots_upper", r.root_cursor_calls);
        field("edges", r.edge_advance_calls_actual);
        field("edges_upper", r.edge_advance_calls);
        field("decisions", r.decision_lookup_calls_actual);
        field("decisions_upper", r.decision_lookup_calls_upper);
        field("prefixes", r.prefix_lookup_calls_actual);
        field("prefixes_upper", r.prefix_lookup_calls_upper);
        field("decision_comparisons", proof.decision_comparisons);
        field("prefix_comparisons", proof.prefix_comparisons);
        field("legacy_extensions", proof.legacy_training_history_extensions);
        field("legacy_rows", proof.legacy_training_row_lookups);
        field("legacy_prefixes", proof.legacy_training_prefix_lookups);
        field("router_work", r.router_query_work_actual);
        field("router_work_upper", r.router_query_work_upper);
        field("index_work", r.index_query_work_actual);
        field("index_work_upper", r.index_query_work_upper);
        field("index_entries", r.index_query_entries_actual);
        field("index_entries_upper", r.index_query_entries_upper);
        field("router_retained", r.router_retained_entries_actual);
        field("router_retained_upper", r.router_retained_entries_upper);
        field("setup_scratch_upper", r.router_setup_scratch_entries_upper);
        field("query_scratch_upper", r.router_query_scratch_entries_upper);
        field("cursor_fields", r.cursor_logical_entries_upper);
        field("cursor_frames_upper", proof.cursor_frame_entries_upper);
        field("combined_work", r.combined_modeled_work_upper);
        field("combined_entries", r.combined_logical_entries_upper);
        field("caller_work", proof.caller_work_upper);
        field("caller_entries", proof.caller_entries_upper);
        field("old_kernel_overlap", proof.plan_kernel_forecast_retained_overlap);
        field("old_history_forecast", proof.legacy_full_history_work_forecast_retained);
        field("final_router_entries", proof.final_router_entries, true);
    }
    if (indexed_admission) {
        need(result.receipt.admission_contract == "indexed-v1" &&
             plan.receipt().admission_contract == "indexed-v1" && result.receipt.indexed_shadow &&
             result.receipt.indexed_shadow->mode == "indexed", "indexed-v1 admission identity mismatch");
        const auto& r = result.receipt.indexed_shadow->routing;
        writer.token("ADMISSION"); writer.token("indexed-v1");
        const auto field = [&](std::string_view name, std::uint64_t value, bool last = false) {
            writer.token(std::string(name) + "=" + std::to_string(value), last);
        };
        field("plan_legacy_lookup_removed", plan.receipt().legacy_training_lookup_work_removed);
        field("plan_legacy_action_removed", plan.receipt().legacy_training_action_work_removed);
        field("trainer_legacy_history_removed", result.receipt.legacy_training_history_work_removed);
        field("plan_setup_work", plan.receipt().modeled_work_upper);
        field("index_setup_work", result.receipt.indexed_shadow->index_setup_work_upper);
        field("router_setup_work", r.router_setup_work_upper);
        field("trainer_history_retained", result.receipt.full_history_lookup_work_upper);
        field("marginal_calls_upper", result.receipt.marginal_calls_upper);
        field("marginal_calls_actual", result.receipt.marginal_calls_actual);
        field("marginal_reuse", 1);
        field("combined_work", r.combined_modeled_work_upper);
        field("combined_entries", r.combined_logical_entries_upper, true);
    }
    if (active_frames) {
        need(result.receipt.active_frames.has_value() && result.receipt.indexed_shadow.has_value(),
             "missing active frame owner proof");
        const auto& f = *result.receipt.active_frames;
        const auto& r = result.receipt.indexed_shadow->routing;
        need(r.active_frames && f.final_active_frames == 0 && f.final_workspace_entries == 0 &&
             f.value_cursor_learning_calls == 0, "active frame ownership/cleanup proof mismatch");
        writer.token("FRAME"); writer.token("active-v1");
        const auto field = [&](std::string_view name, std::uint64_t value, bool last = false) {
            writer.token(std::string(name) + "=" + std::to_string(value), last);
        };
        field("group_size", plan.group().size());
        field("frames", f.workspace.frame_count);
        field("image_slots", f.workspace.image_slots);
        field("header_entries", f.workspace.header_entries);
        field("workspace_entries", f.workspace.retained_entries_upper);
        field("workspace_setup_work", f.workspace.setup_work_upper);
        field("view_fields", openpoker::exact_public_history_index::kFrameViewLogicalEntries);
        field("lease_fields", openpoker::exact_public_history_index::kFrameLeaseLogicalEntries);
        field("borrowed_entries_upper", f.borrowed_entries_upper);
        field("flow_per_visit", f.flow_per_visit);
        field("flow_work_upper", f.flow_work_upper);
        field("validation_work_upper", f.validation_work_upper);
        field("activations", f.actual.activations);
        field("activations_upper", f.activations_upper);
        field("released_frames", f.actual.released_frames);
        field("release_calls", f.actual.release_calls);
        field("final_active_frames", f.final_active_frames);
        field("final_workspace_entries", f.final_workspace_entries);
        field("value_cursor_learning_calls", f.value_cursor_learning_calls);
        field("router_owned_workspace", 1);
        field("combined_work", r.combined_modeled_work_upper);
        field("combined_entries", r.combined_logical_entries_upper, true);
    }
    return 0;
}
} // namespace
int main() {
    try { return run(); }
    catch (const std::exception& error) { std::cerr << "native exact four-street rejected: " << error.what() << '\n'; return 2; }
}
