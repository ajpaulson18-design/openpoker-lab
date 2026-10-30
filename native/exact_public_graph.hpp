#pragma once

// Validated shared public DAG, exact suit closure, and procedural Q-row plan.
// This module stores Q representatives only; logical R occurrences are streamed.

#include "exact_selected_kernel.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <limits>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>
#include <vector>

namespace openpoker::exact_public_graph {

using Card = std::uint8_t;
using History = std::vector<std::string>;
using Hand = exact_selected_kernel::Hand;
using WeightedHand = exact_selected_kernel::WeightedHand;
using SelectedBoard = exact_selected_kernel::SelectedBoard;

inline constexpr std::size_t kMaximumVertices = 250'000;
inline constexpr std::size_t kMaximumEdges = 1'000'000;
inline constexpr std::size_t kMaximumLogicalVisits = 250'000;
inline constexpr std::size_t kMaximumDepth = 256;
inline constexpr std::size_t kMaximumTokenBytes = 64;
inline constexpr std::size_t kMaximumHistoryBytes = 16'000'000;
inline constexpr std::uint64_t kMaximumModeledWork = 500'000'000;
inline constexpr std::size_t kMaximumRetainedEntries = 2'000'000;

enum class ErrorCode {
    invalid_limits, invalid_graph, graph_cycle, graph_unreachable,
    graph_capacity, history_capacity, group_invalid, group_not_closed,
    graph_not_invariant, unsupported_row, invalid_query,
    work_limit, storage_limit, history_limit
};

class PlanError final : public std::runtime_error {
public:
    PlanError(ErrorCode code, const char* message)
        : std::runtime_error(message), code_(code) {}
    [[nodiscard]] ErrorCode code() const noexcept { return code_; }
private:
    ErrorCode code_;
};

struct Action {
    std::string name;
    std::uint64_t amount_bits = 0;
    std::uint64_t raise_to_bits = 0;
    bool full_raise = false;
    std::string token;
    friend bool operator==(const Action&, const Action&) = default;
};

struct Branch {
    std::string label;
    std::size_t child = 0;
    friend bool operator==(const Branch&, const Branch&) = default;
};

enum class VertexKind : std::uint8_t { decision = 1, chance = 2, terminal = 3 };
enum class TerminalKind : std::uint8_t { fold = 1, showdown = 2 };
enum class Street : std::uint8_t { flop = 1, turn = 2, river = 3 };

struct Vertex {
    VertexKind kind = VertexKind::terminal;
    std::uint8_t actor = 0;
    std::vector<Action> actions;
    std::vector<std::size_t> children;
    Street street = Street::flop;
    std::size_t card_index = 0;
    std::vector<Branch> branches;
    TerminalKind terminal_kind = TerminalKind::showdown;
    std::uint8_t winner = 2; // fold winner 0/1; showdown uses 2
    std::array<std::uint64_t, 2> contribution_bits{};

    static Vertex decision(std::uint8_t actor, std::vector<Action> actions,
                           std::vector<std::size_t> children) {
        Vertex out; out.kind = VertexKind::decision; out.actor = actor;
        out.actions = std::move(actions); out.children = std::move(children); return out;
    }
    static Vertex chance(Street street, std::size_t card_index,
                         std::vector<Branch> branches) {
        Vertex out; out.kind = VertexKind::chance; out.street = street;
        out.card_index = card_index; out.branches = std::move(branches); return out;
    }
    static Vertex terminal(TerminalKind kind, std::uint8_t winner,
                           std::array<std::uint64_t, 2> contribution_bits) {
        Vertex out; out.kind = VertexKind::terminal; out.terminal_kind = kind;
        out.winner = winner; out.contribution_bits = contribution_bits; return out;
    }
};

struct Graph {
    std::size_t root_id = 0;
    History initial_history;
    std::vector<Vertex> vertices;
};

struct SuitMap { std::array<std::uint8_t, 4> image{}; };

struct Limits {
    std::size_t max_vertices = kMaximumVertices;
    std::size_t max_edges = kMaximumEdges;
    std::size_t max_logical_visits = kMaximumLogicalVisits;
    std::size_t max_depth = kMaximumDepth;
    std::size_t max_token_bytes = kMaximumTokenBytes;
    std::size_t max_history_bytes = kMaximumHistoryBytes;
    std::uint64_t max_modeled_work = kMaximumModeledWork;
    std::size_t max_retained_entries = kMaximumRetainedEntries;
    exact_selected_kernel::Limits kernel{};
};

struct GraphCensus {
    std::size_t vertices = 0;
    std::size_t edges = 0;
    std::size_t logical_visits = 0;
    std::size_t decision_occurrences = 0;
    std::size_t chance_occurrences = 0;
    std::size_t terminal_occurrences = 0;
    std::size_t maximum_depth = 0;
    std::size_t history_token_work = 0;
    std::size_t history_bytes = 0;
    std::size_t decision_hand_slots_upper = 0;
    std::size_t action_slots_upper = 0;
    std::size_t history_token_entries_upper = 0;
    std::size_t row_history_bytes_upper = 0;
};

struct Receipt {
    std::string admission_contract = "legacy";
    std::uint64_t legacy_training_lookup_work_removed = 0;
    std::uint64_t legacy_training_action_work_removed = 0;
    std::string version = "native-exact-public-graph-q-plan-v1";
    std::size_t graph_vertices = 0;
    std::size_t graph_edges = 0;
    std::size_t logical_visits = 0;
    std::size_t decision_occurrences = 0;
    std::size_t chance_occurrences = 0;
    std::size_t terminal_occurrences = 0;
    std::size_t maximum_depth = 0;
    std::size_t history_token_work = 0;
    std::size_t history_bytes = 0;
    std::size_t history_token_entries_upper = 0;
    std::size_t row_history_bytes_upper = 0;
    std::size_t group_size = 0;
    std::size_t support_prefixes = 0;
    std::size_t quotient_rows = 0;
    std::size_t quotient_action_slots = 0;
    std::uint64_t modeled_work_upper = 0;
    std::size_t retained_entries_upper = 0;
    std::size_t peak_scratch_entries_upper = 0;
    std::string work_scope =
        "Conservative logical preparation/training-lookup admission units; not CPU, allocator bytes or RSS.";
};

struct RowKey {
    std::uint8_t actor = 0;
    std::size_t hand_index = 0;
    History history;
    friend bool operator==(const RowKey&, const RowKey&) = default;
    friend bool operator<(const RowKey& a, const RowKey& b) {
        return std::tie(a.actor, a.hand_index, a.history) <
               std::tie(b.actor, b.hand_index, b.history);
    }
};

struct QRow {
    RowKey key;
    std::vector<Action> menu;
    std::size_t offset = 0;
    std::size_t count = 0;
    std::size_t size = 0;
    std::size_t orbit_size = 0;
    std::uint32_t expected_mask = 0;
};

struct RowLocation {
    std::size_t q = 0;
    std::size_t offset = 0;
    std::uint32_t member_bit = 0;
    friend bool operator==(const RowLocation&, const RowLocation&) = default;
};

// Borrowed immutable support. The owning Plan must outlive every view.
struct PrefixSupportView {
    std::span<const std::size_t> board_indexes;
    std::array<std::span<const std::size_t>, 2> hands;
    // Stable key for existing vector-keyed marginal caches; no query copy.
    const std::vector<std::size_t>* board_index_key = nullptr;
};

namespace detail {

// Prefixes contain at most five cards. Compare that exact bounded domain
// directly, avoiding vector<uint8_t>'s implicit three-way/memcmp path, which
// GCC 13 diagnoses with an impossible overread bound at -O3 -Werror.
struct PrefixLess {
    using is_transparent = void;
    bool operator()(const std::vector<Card>& left, const std::vector<Card>& right) const {
        return compare(left, right);
    }
    bool operator()(const std::vector<Card>& left, std::span<const Card> right) const {
        return compare(left, right);
    }
    bool operator()(std::span<const Card> left, const std::vector<Card>& right) const {
        return compare(left, right);
    }
    bool operator()(const std::vector<Card>& left, std::initializer_list<Card> right) const {
        return compare(left, std::span<const Card>(right.begin(), right.size()));
    }
    bool operator()(std::initializer_list<Card> left, const std::vector<Card>& right) const {
        return compare(std::span<const Card>(left.begin(), left.size()), right);
    }
private:
    static bool compare(std::span<const Card> left, std::span<const Card> right) {
        if (left.size() > 5 || right.size() > 5)
            throw PlanError(ErrorCode::invalid_query, "oversized card-prefix comparison");
        for (std::size_t i = 0; i < 5; ++i) {
            if (i == left.size() || i == right.size()) return left.size() < right.size();
            if (left[i] != right[i]) return left[i] < right[i];
        }
        return false;
    }
};

[[noreturn]] inline void fail(ErrorCode code, const char* message) { throw PlanError(code, message); }

inline std::uint64_t checked_add(std::uint64_t a, std::uint64_t b) {
    if (b > std::numeric_limits<std::uint64_t>::max() - a)
        fail(ErrorCode::work_limit, "modeled work arithmetic overflow");
    return a + b;
}

inline std::uint64_t checked_mul(std::uint64_t a, std::uint64_t b) {
    if (a && b > std::numeric_limits<std::uint64_t>::max() / a)
        fail(ErrorCode::work_limit, "modeled work arithmetic overflow");
    return a * b;
}

inline std::size_t checked_entries(std::size_t a, std::size_t b) {
    if (b > std::numeric_limits<std::size_t>::max() - a)
        fail(ErrorCode::storage_limit, "retained-entry arithmetic overflow");
    return a + b;
}

inline bool utf8_valid(std::string_view s) {
    std::size_t i = 0;
    while (i < s.size()) {
        const auto c = static_cast<unsigned char>(s[i]);
        if (c <= 0x7f) { ++i; continue; }
        std::size_t length = 0; std::uint32_t code = 0;
        if ((c & 0xe0U) == 0xc0U) { length = 2; code = c & 0x1fU; }
        else if ((c & 0xf0U) == 0xe0U) { length = 3; code = c & 0x0fU; }
        else if ((c & 0xf8U) == 0xf0U) { length = 4; code = c & 0x07U; }
        else return false;
        if (i + length > s.size()) return false;
        for (std::size_t j = 1; j < length; ++j) {
            const auto d = static_cast<unsigned char>(s[i + j]);
            if ((d & 0xc0U) != 0x80U) return false;
            code = (code << 6) | (d & 0x3fU);
        }
        if ((length == 2 && code < 0x80U) || (length == 3 && code < 0x800U) ||
            (length == 4 && code < 0x10000U) || code > 0x10ffffU ||
            (code >= 0xd800U && code <= 0xdfffU)) return false;
        i += length;
    }
    return true;
}

inline std::size_t token_bytes(const std::string& value, std::size_t max_bytes) {
    if (value.empty() || value.size() > max_bytes || !utf8_valid(value))
        fail(ErrorCode::invalid_graph, "invalid or oversized UTF-8 graph token");
    return value.size();
}

inline bool finite_nonnegative_bits(std::uint64_t bits) {
    const bool negative = (bits >> 63) != 0;
    const auto exponent = (bits >> 52) & 0x7ffU;
    const auto fraction = bits & ((std::uint64_t{1} << 52) - 1);
    if (exponent == 0x7ffU) return false;
    if (exponent == 0 && fraction == 0) return true; // signed zero identity is retained
    return !negative;
}

inline std::uint16_t holding_key(Hand hand) {
    const auto a = std::min(hand.first, hand.second);
    const auto b = std::max(hand.first, hand.second);
    return static_cast<std::uint16_t>((static_cast<unsigned>(a) << 6) | b);
}

inline std::array<Card, 2> mapped_hand(Hand hand, const SuitMap& mapping) {
    const auto map_card = [&mapping](Card card) {
        return static_cast<Card>((card / 4U) * 4U + mapping.image[card % 4U]);
    };
    std::array<Card, 2> result{map_card(hand.first), map_card(hand.second)};
    if (result[1] < result[0]) std::swap(result[0], result[1]);
    return result;
}

inline std::uint8_t suit_from_char(char suit) {
    switch (suit) {
        case 'c': return 0; case 'd': return 1; case 'h': return 2; case 's': return 3;
        default: fail(ErrorCode::invalid_graph, "unknown suit in public reveal token");
    }
}

inline char suit_char(std::uint8_t suit) {
    constexpr char suits[] = "cdhs";
    if (suit > 3) fail(ErrorCode::invalid_graph, "invalid suit mapping index");
    return suits[suit];
}

inline char rank_char(Card card) {
    constexpr char ranks[] = "23456789TJQKA";
    if (card >= 52) fail(ErrorCode::invalid_graph, "card id outside 0..51");
    return ranks[card / 4U];
}

inline std::string card_text(Card card) {
    std::string result(2, ' ');
    result[0] = rank_char(card); result[1] = suit_char(static_cast<std::uint8_t>(card % 4U));
    return result;
}

inline Card parse_card(std::string_view text) {
    if (text.size() != 2) fail(ErrorCode::invalid_graph, "card token must have two characters");
    constexpr std::string_view ranks = "23456789TJQKA";
    const auto rank = ranks.find(text[0]);
    if (rank == std::string_view::npos) fail(ErrorCode::invalid_graph, "invalid card rank token");
    return static_cast<Card>(rank * 4U + suit_from_char(text[1]));
}

inline std::string map_card_text(std::string_view text, const SuitMap& mapping) {
    const auto card = parse_card(text);
    return std::string{rank_char(card), suit_char(mapping.image[card % 4U])};
}

inline std::array<Card, 5> mapped_board(const SelectedBoard& board, const SuitMap& mapping) {
    std::array<Card, 5> result{};
    for (std::size_t i = 0; i < result.size(); ++i)
        result[i] = static_cast<Card>((board.cards[i] / 4U) * 4U + mapping.image[board.cards[i] % 4U]);
    std::sort(result.begin(), result.begin() + 3);
    return result;
}

inline std::string transform_reveal(std::string_view token, const SuitMap& mapping) {
    const auto at = token.find('@');
    if (at == std::string_view::npos) return std::string(token);
    const auto street = token.substr(0, at);
    const auto label = token.substr(at + 1);
    if (street == "flop") {
        if (label.size() != 6) fail(ErrorCode::invalid_graph, "malformed flop history token");
        std::array<std::string, 3> cards{
            map_card_text(label.substr(0, 2), mapping),
            map_card_text(label.substr(2, 2), mapping),
            map_card_text(label.substr(4, 2), mapping)};
        std::sort(cards.begin(), cards.end(), [](const auto& a, const auto& b) {
            return parse_card(a) < parse_card(b);
        });
        return "flop@" + cards[0] + cards[1] + cards[2];
    }
    if (street == "turn" || street == "river")
        return std::string(street) + "@" + map_card_text(label, mapping);
    return std::string(token);
}

inline std::vector<Card> revealed_cards(std::span<const std::string> history) {
    std::vector<Card> result;
    std::array<bool, 52> seen{};
    const auto push = [&](Card card) {
        if (seen[card]) fail(ErrorCode::invalid_query, "duplicate card in public history");
        seen[card] = true; result.push_back(card);
    };
    for (const auto& token : history) {
        if (token.starts_with("flop@")) {
            const std::string_view payload(token.data() + 5, token.size() - 5);
            if (payload.size() != 6) fail(ErrorCode::invalid_query, "malformed flop history");
            if (!result.empty()) fail(ErrorCode::invalid_query, "flop reveal must precede turn/river");
            const auto a = parse_card(payload.substr(0, 2));
            const auto b = parse_card(payload.substr(2, 2));
            const auto c = parse_card(payload.substr(4, 2));
            if (!(a < b && b < c)) fail(ErrorCode::invalid_query, "flop history must use canonical DECK order");
            push(a); push(b); push(c);
        } else if (token.starts_with("turn@")) {
            if (result.size() != 3) fail(ErrorCode::invalid_query, "turn reveal must follow flop");
            push(parse_card(std::string_view(token).substr(5)));
        } else if (token.starts_with("river@")) {
            if (result.size() != 4) fail(ErrorCode::invalid_query, "river reveal must follow turn");
            push(parse_card(std::string_view(token).substr(6)));
        }
    }
    if (result.size() != 0 && result.size() != 3 && result.size() != 4 && result.size() != 5)
        fail(ErrorCode::invalid_query, "revealed history must expose 0, 3, 4 or 5 cards");
    return result;
}

inline std::vector<std::string> edge_labels(const Vertex& vertex) {
    std::vector<std::string> result;
    if (vertex.kind == VertexKind::decision) {
        result.reserve(vertex.actions.size());
        for (const auto& action : vertex.actions) result.push_back(action.token);
    } else if (vertex.kind == VertexKind::chance) {
        result.reserve(vertex.branches.size());
        const char* prefix = vertex.street == Street::flop ? "flop@" :
                             vertex.street == Street::turn ? "turn@" : "river@";
        for (const auto& branch : vertex.branches) result.push_back(std::string(prefix) + branch.label);
    }
    return result;
}

inline std::vector<std::size_t> children(const Vertex& vertex) {
    if (vertex.kind == VertexKind::decision) return vertex.children;
    if (vertex.kind == VertexKind::chance) {
        std::vector<std::size_t> result; result.reserve(vertex.branches.size());
        for (const auto& branch : vertex.branches) result.push_back(branch.child);
        return result;
    }
    return {};
}

struct GraphMetrics {
    GraphCensus census;
    std::vector<std::size_t> topological;
    std::vector<std::size_t> occurrence_counts;
    std::vector<std::size_t> history_token_sums;
    std::vector<std::size_t> history_byte_sums;
    std::vector<std::size_t> max_depths;
};

inline std::uint64_t bits_from_size(std::size_t value) {
    return static_cast<std::uint64_t>(value);
}

inline std::size_t sat_size_add(std::size_t a, std::size_t b) {
    return b > std::numeric_limits<std::size_t>::max() - a
        ? std::numeric_limits<std::size_t>::max() : a + b;
}

} // namespace detail

enum class AdmissionProfile { legacy, indexed_v1 };

class Plan final {
public:
    Plan(Graph graph, std::vector<WeightedHand> sb, std::vector<WeightedHand> bb,
         std::vector<SelectedBoard> boards, unsigned iterations,
         std::size_t rank_cache_boards = 1, Limits limits = {},
         AdmissionProfile admission_profile = AdmissionProfile::legacy)
        : graph_(std::move(graph)), ranges_{std::move(sb), std::move(bb)},
          boards_(std::move(boards)), iterations_(iterations),
          rank_cache_boards_(rank_cache_boards), limits_(std::move(limits)), admission_profile_(admission_profile) {
        if (admission_profile_ != AdmissionProfile::legacy && admission_profile_ != AdmissionProfile::indexed_v1)
            detail::fail(ErrorCode::invalid_limits, "unsupported native Plan admission profile");
        validate_limits();
        if (graph_.vertices.empty() || graph_.vertices.size() > limits_.max_vertices ||
            graph_.root_id >= graph_.vertices.size())
            detail::fail(ErrorCode::invalid_graph, "graph root or vertex dimension is invalid");
        if (iterations_ < 10 || iterations_ > 10'000 || rank_cache_boards_ < 1 || rank_cache_boards_ > 64)
            detail::fail(ErrorCode::invalid_limits, "iterations/rank-cache request is outside admitted bounds");
        if (graph_.initial_history.size() > limits_.max_depth)
            detail::fail(ErrorCode::history_limit, "initial public history exceeds bounded token count");
        if (ranges_[0].empty() || ranges_[1].empty() ||
            ranges_[0].size() > exact_selected_kernel::kMaximumHandsPerSide ||
            ranges_[1].size() > exact_selected_kernel::kMaximumHandsPerSide ||
            ranges_[0].size() > limits_.kernel.max_hands_per_side ||
            ranges_[1].size() > limits_.kernel.max_hands_per_side ||
            boards_.empty() || boards_.size() > exact_selected_kernel::kMaximumBoards ||
            boards_.size() > limits_.kernel.max_boards)
            detail::fail(ErrorCode::invalid_graph, "range/selected-board dimensions outside kernel caps");
        const auto raw_hands = ranges_[0].size() + ranges_[1].size();
        const auto range_work = 24ULL * (16ULL * raw_hands + 32ULL * boards_.size());
        charge_admission_work(range_work);
        charge_admission_entries(8ULL * raw_hands + 8ULL * boards_.size() + 256ULL);
        validate_ranges_and_boards();
        derive_group();

        // Reserve graph signature/topology arrays from the supplied dimensions
        // before graph-sized scratch is created. The scan itself has a fixed cap.
        charge_admission_work(4ULL * graph_.vertices.size());
        std::uint64_t raw_edges = 0;
        for (const auto& v : graph_.vertices) {
            raw_edges = detail::checked_add(raw_edges, v.children.size());
            raw_edges = detail::checked_add(raw_edges, v.branches.size());
        }
        if (raw_edges > limits_.max_edges) detail::fail(ErrorCode::graph_capacity, "graph edge cap exceeded");
        charge_admission_work(8ULL * raw_edges);
        charge_admission_work(graph_.initial_history.size());
        std::uint64_t graph_text_bytes = 0;
        for (const auto& t : graph_.initial_history) graph_text_bytes = detail::checked_add(graph_text_bytes, t.size());
        for (const auto& v : graph_.vertices) {
            for (const auto& a : v.actions) graph_text_bytes = detail::checked_add(graph_text_bytes, a.name.size() + a.token.size());
            for (const auto& b : v.branches) graph_text_bytes = detail::checked_add(graph_text_bytes, b.label.size());
        }
        if (graph_text_bytes > limits_.max_history_bytes)
            detail::fail(ErrorCode::history_limit, "graph token text exceeds bounded graph-plan history envelope");
        graph_input_text_bytes_ = graph_text_bytes;
        const auto preliminary_entries = 48ULL * graph_.vertices.size() + 32ULL * raw_edges + 8192ULL;
        charge_admission_entries(preliminary_entries);
        charge_admission_work(16ULL * graph_.vertices.size() + 8ULL * raw_edges + graph_text_bytes);
        graph_metrics_ = validate_and_census_graph();
        graph_census_ = graph_metrics_.census;
        verify_group_graph_closure();

        // Prefix and Q upper bounds are computed from the exact logical graph
        // census before the owned exact kernel or support maps are allocated.
        preflight_q_plan();
        collect_prefixes_and_q_bounds();
        instantiate_owned_kernel();
        validate_chance_coverage();
        build_support_cache();
        build_q_rows();
        finalize_receipt();
    }

    Plan(const Plan&) = delete;
    Plan& operator=(const Plan&) = delete;

    [[nodiscard]] const Graph& graph() const noexcept { return graph_; }
    [[nodiscard]] exact_selected_kernel::ExactSelectedKernel& kernel() noexcept { return *kernel_; }
    [[nodiscard]] const exact_selected_kernel::ExactSelectedKernel& kernel() const noexcept { return *kernel_; }
    [[nodiscard]] const std::vector<SuitMap>& group() const noexcept { return group_; }
    [[nodiscard]] const std::vector<QRow>& rows() const noexcept { return rows_; }
    [[nodiscard]] const std::array<std::size_t, 2>& hand_counts() const noexcept { return hand_counts_; }
    [[nodiscard]] unsigned iterations() const noexcept { return iterations_; }
    [[nodiscard]] AdmissionProfile admission_profile() const noexcept { return admission_profile_; }
    [[nodiscard]] std::uint64_t kernel_setup_support_work_upper() const noexcept {
        return kernel_setup_support_work_upper_;
    }
    [[nodiscard]] std::size_t selected_board_count() const noexcept { return boards_.size(); }
    [[nodiscard]] const GraphCensus& graph_census() const noexcept { return graph_census_; }
    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }

    [[nodiscard]] std::size_t mapped_hand_index(std::uint8_t actor, std::size_t map_index,
                                               std::size_t hand_index) const {
        if (actor > 1 || map_index >= group_.size() || hand_index >= hand_counts_[actor])
            detail::fail(ErrorCode::invalid_query, "hand-map actor, suit map or original hand index is invalid");
        return hand_maps_[actor][map_index][hand_index];
    }

    [[nodiscard]] PrefixSupportView prefix_support(std::span<const Card> prefix) const {
        if (prefix.size() != 0 && prefix.size() != 3 && prefix.size() != 4 && prefix.size() != 5)
            detail::fail(ErrorCode::invalid_query, "typed prefix must contain zero, three, four or five cards");
        for (std::size_t i = 0; i < prefix.size(); ++i) {
            if (prefix[i] >= 52)
                detail::fail(ErrorCode::invalid_query, "typed prefix contains an invalid card");
            for (std::size_t j = 0; j < i; ++j)
                if (prefix[i] == prefix[j])
                    detail::fail(ErrorCode::invalid_query, "typed prefix contains a duplicate card");
        }
        if (prefix.size() >= 3 && !(prefix[0] < prefix[1] && prefix[1] < prefix[2]))
            detail::fail(ErrorCode::invalid_query, "typed flop prefix must use canonical DECK order");
        const auto found = support_.find(prefix);
        if (found == support_.end())
            detail::fail(ErrorCode::invalid_query, "typed prefix was not admitted by this public graph");
        return {std::span<const std::size_t>(found->second.board_indexes),
            {std::span<const std::size_t>(found->second.hands[0]),
             std::span<const std::size_t>(found->second.hands[1])}, &found->second.board_indexes};
    }

    [[nodiscard]] const std::vector<std::size_t>& prefix_board_indexes(
        std::span<const std::string> history) const {
        validate_query_history(history);
        const auto prefix = detail::revealed_cards(history);
        const auto found = support_.find(prefix);
        if (found == support_.end()) detail::fail(ErrorCode::invalid_query, "history prefix was not admitted by this public graph");
        return found->second.board_indexes;
    }

    [[nodiscard]] static History extend_history(const History& history, const Action& action) {
        History result = history; result.push_back(action.token); return result;
    }
    [[nodiscard]] static History extend_history(const History& history, Street street,
                                                std::string_view label) {
        History result = history;
        const char* prefix = street == Street::flop ? "flop@" :
                             street == Street::turn ? "turn@" : "river@";
        result.push_back(std::string(prefix) + std::string(label)); return result;
    }

    [[nodiscard]] RowLocation locate(const RowKey& key) const {
        validate_query_history(key.history);
        validate_row_key(key);
        const auto images = row_images(key);
        const auto q = locations_.find(images.front());
        if (q == locations_.end()) detail::fail(ErrorCode::unsupported_row, "row is outside the admitted Q support");
        const auto ordinal = static_cast<std::size_t>(std::lower_bound(images.begin(), images.end(), key) - images.begin());
        const auto& row = rows_[q->second];
        if (row.orbit_size != images.size() || row.menu != menu_at_history(key.actor, key.history))
            detail::fail(ErrorCode::unsupported_row, "row orbit or ordered menu differs from admitted Q record");
        return {q->second, row.offset, static_cast<std::uint32_t>(1U << ordinal)};
    }

    [[nodiscard]] std::vector<std::optional<RowLocation>> locate_decision_rows(
        std::uint8_t actor, std::span<const std::string> history,
        std::span<const Action> menu) const {
        validate_query_history(history);
        if (actor > 1) detail::fail(ErrorCode::invalid_query, "invalid global actor");
        const auto& vertex = decision_at_history(history);
        if (vertex.actor != actor || !std::equal(vertex.actions.begin(), vertex.actions.end(), menu.begin(), menu.end()))
            detail::fail(ErrorCode::invalid_query, "history actor or complete ordered menu mismatch");
        History own_history(history.begin(), history.end());
        const auto prefix = detail::revealed_cards(history);
        const auto support_it = support_.find(prefix);
        if (support_it == support_.end()) detail::fail(ErrorCode::unsupported_row, "decision prefix lacks admitted support");
        std::vector<History> transformed;
        transformed.reserve(group_.size());
        for (const auto& mapping : group_) transformed.push_back(transform_history(own_history, mapping));
        std::vector<std::vector<Card>> transformed_prefixes;
        transformed_prefixes.reserve(transformed.size());
        for (const auto& value : transformed) {
            auto p = detail::revealed_cards(value);
            if (!support_.contains(p)) detail::fail(ErrorCode::unsupported_row, "suit image prefix lacks admitted support");
            transformed_prefixes.push_back(std::move(p));
        }
        std::vector<std::optional<RowLocation>> result(hand_counts_[actor]);
        for (const auto hand : support_it->second.hands[actor]) {
            RowKey original{actor, hand, own_history};
            auto images = row_images(original, &transformed);
            for (std::size_t g = 0; g < group_.size(); ++g) {
                const auto mapped_hand = hand_maps_[actor][g][hand];
            const auto& image_support = support_.at(transformed_prefixes[g]).hands[actor];
                if (!std::binary_search(image_support.begin(), image_support.end(), mapped_hand))
                    detail::fail(ErrorCode::unsupported_row, "suit image loses positive physical support");
            }
            const auto found = locations_.find(images.front());
            if (found == locations_.end()) detail::fail(ErrorCode::unsupported_row, "decision row is outside admitted Q support");
            const auto q = found->second;
            if (rows_[q].orbit_size != images.size() || rows_[q].menu.size() != menu.size() ||
                !std::equal(rows_[q].menu.begin(), rows_[q].menu.end(), menu.begin(), menu.end()))
                detail::fail(ErrorCode::unsupported_row, "decision row image changed orbit size or ordered menu");
            const auto ordinal = static_cast<std::size_t>(std::lower_bound(images.begin(), images.end(), original) - images.begin());
            result[hand] = RowLocation{q, rows_[q].offset, static_cast<std::uint32_t>(1U << ordinal)};
        }
        return result;
    }

    template<class Function>
    void for_each_supported_row(Function&& function) const {
        for_each_occurrence([&](std::size_t vertex_id, const History& history) {
            const auto& vertex = graph_.vertices[vertex_id];
            if (vertex.kind != VertexKind::decision) return;
            const auto prefix = detail::revealed_cards(history);
            const auto found = support_.find(prefix);
            if (found == support_.end()) detail::fail(ErrorCode::unsupported_row, "logical decision prefix has no support cache");
            for (const auto hand : found->second.hands[vertex.actor])
                function(RowKey{vertex.actor, hand, history}, vertex.actions);
        });
    }

private:
    struct PrefixSupport {
        std::vector<std::size_t> board_indexes;
        std::array<std::vector<std::size_t>, 2> hands;
    };
    struct QBuild { std::vector<Action> menu; std::size_t orbit_size = 0; std::uint32_t mask = 0; };
    struct OccurrenceFrame {
        std::size_t vertex = 0;
        std::size_t next_child = 0;
        std::size_t restore_history = 0;
        bool entered = false;
    };

    void validate_limits() const {
        if (!limits_.max_vertices || limits_.max_vertices > kMaximumVertices ||
            !limits_.max_edges || limits_.max_edges > kMaximumEdges ||
            !limits_.max_logical_visits || limits_.max_logical_visits > kMaximumLogicalVisits ||
            !limits_.max_depth || limits_.max_depth > kMaximumDepth ||
            !limits_.max_token_bytes || limits_.max_token_bytes > kMaximumTokenBytes ||
            !limits_.max_history_bytes || limits_.max_history_bytes > kMaximumHistoryBytes ||
            !limits_.max_modeled_work || limits_.max_modeled_work > kMaximumModeledWork ||
            !limits_.max_retained_entries || limits_.max_retained_entries > kMaximumRetainedEntries)
            detail::fail(ErrorCode::invalid_limits, "graph-plan limits must be positive reduce-only values");
        const auto& k = limits_.kernel;
        if (!k.max_hands_per_side || k.max_hands_per_side > exact_selected_kernel::kMaximumHandsPerSide ||
            !k.max_boards || k.max_boards > exact_selected_kernel::kMaximumBoards ||
            !k.max_integer_bits || k.max_integer_bits > exact_selected_kernel::kMaximumIntegerBits ||
            !k.max_modeled_work || k.max_modeled_work > exact_selected_kernel::kMaximumModeledWork ||
            !k.max_storage_entries || k.max_storage_entries > exact_selected_kernel::kMaximumStorageEntries ||
            k.max_integer_payload_bits > exact_selected_kernel::kMaximumIntegerPayloadBits)
            detail::fail(ErrorCode::invalid_limits, "nested exact-kernel limits must be reduce-only values");
    }
    std::size_t total_hands() const noexcept { return hand_counts_[0] + hand_counts_[1]; }
    void charge_admission_work(std::uint64_t units) {
        if (units > limits_.max_modeled_work - admission_work_)
            detail::fail(ErrorCode::work_limit, "whole graph-plan modeled-work admission exceeded");
        admission_work_ += units;
    }
    void charge_admission_entries(std::uint64_t entries) {
        if (entries > limits_.max_retained_entries || admission_entries_ > limits_.max_retained_entries - entries)
            detail::fail(ErrorCode::storage_limit, "whole graph-plan retained-entry admission exceeded");
        admission_entries_ += static_cast<std::size_t>(entries);
    }

    void validate_ranges_and_boards() {
        if (ranges_[0].empty() || ranges_[1].empty() ||
            ranges_[0].size() > exact_selected_kernel::kMaximumHandsPerSide ||
            ranges_[1].size() > exact_selected_kernel::kMaximumHandsPerSide ||
            ranges_[0].size() > limits_.kernel.max_hands_per_side ||
            ranges_[1].size() > limits_.kernel.max_hands_per_side ||
            boards_.empty() || boards_.size() > exact_selected_kernel::kMaximumBoards ||
            boards_.size() > limits_.kernel.max_boards)
            detail::fail(ErrorCode::invalid_graph, "range/selected-board dimensions outside kernel caps");
        hand_counts_ = {ranges_[0].size(), ranges_[1].size()};
        for (std::size_t side = 0; side < 2; ++side) {
            std::set<std::uint16_t> seen;
            for (const auto& row : ranges_[side]) {
                if (row.hand.first >= 52 || row.hand.second >= 52 || row.hand.first == row.hand.second ||
                    !detail::finite_nonnegative_bits(row.binary64_weight_bits) ||
                    ((row.binary64_weight_bits >> 52) & 0x7ffU) == 0x7ffU ||
                    ((row.binary64_weight_bits & ~(1ULL << 63)) == 0))
                    detail::fail(ErrorCode::invalid_graph, "invalid physical holding or positive finite weight bits");
                if (!seen.insert(detail::holding_key(row.hand)).second)
                    detail::fail(ErrorCode::invalid_graph, "duplicate physical hand after canonicalization");
            }
        }
        std::set<std::array<Card, 5>> seen_boards;
        std::array<Card, 5> previous{}; bool have_previous = false;
        for (const auto& board : boards_) {
            auto sorted = board.cards; std::sort(sorted.begin(), sorted.end());
            if (sorted.back() >= 52 || std::adjacent_find(sorted.begin(), sorted.end()) != sorted.end() ||
                !(board.cards[0] < board.cards[1] && board.cards[1] < board.cards[2]))
                detail::fail(ErrorCode::invalid_graph, "selected board must contain five distinct cards and canonical flop");
            if (!seen_boards.insert(board.cards).second || (have_previous && !(previous < board.cards)))
                detail::fail(ErrorCode::invalid_graph, "selected outcomes must be unique and canonically ordered");
            previous = board.cards; have_previous = true;
        }
    }

    void derive_group() {
        // Search all 24 suit permutations under a precharged full-range/board
        // envelope. Hand indices remain the original seat ordering.
        std::map<std::uint16_t, std::size_t> indices[2];
        for (std::size_t side = 0; side < 2; ++side)
            for (std::size_t i = 0; i < ranges_[side].size(); ++i)
                indices[side].emplace(detail::holding_key(ranges_[side][i].hand), i);
        std::array<std::uint8_t, 4> permutation{0, 1, 2, 3};
        std::set<std::array<Card, 5>> selected;
        for (const auto& board : boards_) selected.insert(board.cards);
        do {
            SuitMap mapping{permutation};
            bool preserves = true;
            for (std::size_t side = 0; side < 2 && preserves; ++side) {
                for (std::size_t i = 0; i < ranges_[side].size(); ++i) {
                    const auto mapped = detail::mapped_hand(ranges_[side][i].hand, mapping);
                    const auto found = indices[side].find(detail::holding_key(Hand{mapped[0], mapped[1]}));
                    if (found == indices[side].end() ||
                        ranges_[side][found->second].binary64_weight_bits != ranges_[side][i].binary64_weight_bits) {
                        preserves = false; break;
                    }
                }
            }
            if (preserves) {
                std::set<std::array<Card, 5>> transformed;
                for (const auto& board : boards_) transformed.insert(detail::mapped_board(board, mapping));
                preserves = transformed == selected;
            }
            if (preserves) group_.push_back(mapping);
        } while (std::next_permutation(permutation.begin(), permutation.end()));
        if (group_.empty() || group_.size() > 24)
            detail::fail(ErrorCode::group_invalid, "weighted range/board stabilizer lacks identity");
        std::sort(group_.begin(), group_.end(), [](const auto& a, const auto& b) { return a.image < b.image; });
        auto contains = [&](const std::array<std::uint8_t, 4>& image) {
            return std::any_of(group_.begin(), group_.end(), [&](const SuitMap& item) { return item.image == image; });
        };
        const std::array<std::uint8_t, 4> identity{0, 1, 2, 3};
        if (!contains(identity)) detail::fail(ErrorCode::group_invalid, "weighted stabilizer lacks identity");
        for (const auto& a : group_) {
            std::array<std::uint8_t, 4> inverse{};
            for (std::size_t s = 0; s < 4; ++s) inverse[a.image[s]] = static_cast<std::uint8_t>(s);
            if (!contains(inverse)) detail::fail(ErrorCode::group_not_closed, "weighted suit stabilizer lacks inverse");
            for (const auto& b : group_) {
                std::array<std::uint8_t, 4> composition{};
                for (std::size_t s = 0; s < 4; ++s) composition[s] = a.image[b.image[s]];
                if (!contains(composition)) detail::fail(ErrorCode::group_not_closed, "weighted suit stabilizer is not closed");
            }
        }
    }

    detail::GraphMetrics validate_and_census_graph();
    void verify_group_graph_closure();
    void collect_prefixes_and_q_bounds();
    void preflight_q_plan();
    void instantiate_owned_kernel();
    void validate_chance_coverage();
    void build_support_cache();
    void build_q_rows();
    void finalize_receipt();
    template<class Function> void for_each_occurrence(Function&& function) const;
    const Vertex& decision_at_history(std::span<const std::string> history) const;
    const std::vector<Action>& menu_at_history(std::uint8_t actor,
                                               std::span<const std::string> history) const;
    void validate_row_key(const RowKey& key) const;
    void validate_query_history(std::span<const std::string> history) const;
    std::vector<RowKey> row_images(const RowKey& key,
                                   const std::vector<History>* transformed = nullptr) const;
    History transform_history(std::span<const std::string> history, const SuitMap& mapping) const;
    std::vector<std::size_t> indexes_for_prefix(const std::vector<Card>& prefix) const;

    Graph graph_;
    std::array<std::vector<WeightedHand>, 2> ranges_;
    std::vector<SelectedBoard> boards_;
    std::array<std::size_t, 2> hand_counts_{};
    unsigned iterations_ = 0;
    std::size_t rank_cache_boards_ = 1;
    Limits limits_{};
    AdmissionProfile admission_profile_ = AdmissionProfile::legacy;
    std::size_t edge_count_ = 0;
    std::uint64_t graph_input_text_bytes_ = 0;
    detail::GraphMetrics graph_metrics_{};
    GraphCensus graph_census_{};
    std::vector<SuitMap> group_;
    std::array<std::vector<std::vector<std::size_t>>, 2> hand_maps_;
    std::vector<std::vector<Card>> prefixes_;
    std::vector<bool> positive_selected_boards_;
    std::map<std::vector<Card>, PrefixSupport, detail::PrefixLess> support_;
    std::unique_ptr<exact_selected_kernel::ExactSelectedKernel> kernel_;
    std::map<RowKey, std::size_t> locations_;
    std::vector<QRow> rows_;
    Receipt receipt_{};
    std::uint64_t admission_work_ = 0;
    std::size_t admission_entries_ = 0;
    std::uint64_t q_work_upper_ = 0;
    std::uint64_t legacy_training_lookup_work_removed_ = 0;
    std::uint64_t legacy_training_action_work_removed_ = 0;
    std::uint64_t kernel_setup_support_work_upper_ = 0;
    std::size_t q_entries_upper_ = 0;
};

namespace detail {

inline void append_u64(std::string& out, std::uint64_t value) {
    for (unsigned i = 0; i < 8; ++i) out.push_back(static_cast<char>((value >> (i * 8)) & 0xffU));
}
inline void append_text(std::string& out, std::string_view value) {
    append_u64(out, value.size()); out.append(value);
}
inline std::string vertex_signature(const Vertex& v, std::span<const std::size_t> child_ids) {
    std::string key; key.reserve(64 + v.actions.size() * 64 + v.branches.size() * 32);
    key.push_back(static_cast<char>(v.kind));
    if (v.kind == VertexKind::decision) {
        key.push_back(static_cast<char>(v.actor)); append_u64(key, v.actions.size());
        for (std::size_t i = 0; i < v.actions.size(); ++i) {
            const auto& a = v.actions[i]; append_text(key, a.name); append_u64(key, a.amount_bits);
            append_u64(key, a.raise_to_bits); key.push_back(static_cast<char>(a.full_raise));
            append_text(key, a.token); append_u64(key, child_ids[i]);
        }
    } else if (v.kind == VertexKind::chance) {
        key.push_back(static_cast<char>(v.street)); append_u64(key, v.card_index);
        std::vector<std::pair<std::string, std::size_t>> branches;
        branches.reserve(v.branches.size());
        for (std::size_t i = 0; i < v.branches.size(); ++i)
            branches.emplace_back(v.branches[i].label, child_ids[i]);
        std::sort(branches.begin(), branches.end()); append_u64(key, branches.size());
        for (const auto& [label, child] : branches) { append_text(key, label); append_u64(key, child); }
    } else {
        key.push_back(static_cast<char>(v.terminal_kind)); key.push_back(static_cast<char>(v.winner));
        append_u64(key, v.contribution_bits[0]); append_u64(key, v.contribution_bits[1]);
    }
    return key;
}

} // namespace detail

inline detail::GraphMetrics Plan::validate_and_census_graph() {
    if (graph_.vertices.empty() || graph_.vertices.size() > limits_.max_vertices ||
        graph_.root_id >= graph_.vertices.size())
        detail::fail(ErrorCode::invalid_graph, "graph root or vertex dimension is invalid");
    const auto n = graph_.vertices.size();
    std::vector<std::size_t> indegree(n, 0);
    edge_count_ = 0;
    for (std::size_t i = 0; i < n; ++i) {
        const auto& v = graph_.vertices[i];
        if (v.kind == VertexKind::decision) {
            if (v.street != Street::flop || v.card_index != 0 || !v.branches.empty() ||
                v.terminal_kind != TerminalKind::showdown || v.winner != 2 ||
                v.contribution_bits != std::array<std::uint64_t, 2>{0, 0} ||
                v.actor > 1 || v.actions.empty() || v.actions.size() != v.children.size())
                detail::fail(ErrorCode::invalid_graph, "decision vertex actor/menu/child dimensions invalid");
            std::set<std::string> tokens;
            for (const auto& a : v.actions) {
                detail::token_bytes(a.name, limits_.max_token_bytes);
                detail::token_bytes(a.token, limits_.max_token_bytes);
                if (a.token.starts_with("flop@") || a.token.starts_with("turn@") || a.token.starts_with("river@") ||
                    !tokens.insert(a.token).second || !detail::finite_nonnegative_bits(a.amount_bits) ||
                    !detail::finite_nonnegative_bits(a.raise_to_bits))
                    detail::fail(ErrorCode::invalid_graph, "decision actions have duplicate tokens or invalid money bits");
            }
        } else if (v.kind == VertexKind::chance) {
            const auto required_card_index = v.street == Street::flop ? 4U :
                v.street == Street::turn ? 5U : v.street == Street::river ? 6U : 0U;
            if (v.actor != 0 || !v.actions.empty() || !v.children.empty() ||
                v.terminal_kind != TerminalKind::showdown || v.winner != 2 ||
                v.contribution_bits != std::array<std::uint64_t, 2>{0, 0} ||
                v.street < Street::flop || v.street > Street::river ||
                v.card_index != required_card_index || v.branches.empty())
                detail::fail(ErrorCode::invalid_graph, "chance vertex street/branches invalid");
            std::set<std::string> labels;
            for (const auto& b : v.branches) {
                detail::token_bytes(b.label, limits_.max_token_bytes);
                if (!labels.insert(b.label).second)
                    detail::fail(ErrorCode::invalid_graph, "duplicate chance outcome label");
                if (v.street == Street::flop) {
                    if (b.label.size() != 6) detail::fail(ErrorCode::invalid_graph, "flop branch must contain three cards");
                    const auto a = detail::parse_card(std::string_view(b.label).substr(0, 2));
                    const auto c = detail::parse_card(std::string_view(b.label).substr(2, 2));
                    const auto d = detail::parse_card(std::string_view(b.label).substr(4, 2));
                    if (!(a < c && c < d)) detail::fail(ErrorCode::invalid_graph, "flop branch must use canonical DECK order");
                } else {
                    if (b.label.size() != 2) detail::fail(ErrorCode::invalid_graph, "turn/river branch must contain one card");
                    (void)detail::parse_card(b.label);
                }
            }
        } else if (v.kind == VertexKind::terminal) {
            if (v.actor != 0 || !v.actions.empty() || !v.children.empty() ||
                v.street != Street::flop || v.card_index != 0 || !v.branches.empty() ||
                (v.terminal_kind != TerminalKind::fold && v.terminal_kind != TerminalKind::showdown) ||
                (v.terminal_kind == TerminalKind::fold && v.winner > 1) ||
                (v.terminal_kind == TerminalKind::showdown && v.winner != 2))
                detail::fail(ErrorCode::invalid_graph, "terminal kind/winner invalid");
            for (const auto bits : v.contribution_bits) {
                if (!detail::finite_nonnegative_bits(bits)) detail::fail(ErrorCode::invalid_graph, "terminal contribution is not finite/nonnegative");
                const auto positive_bits = bits & ~(std::uint64_t{1} << 63);
                constexpr auto maximum_money_bits = std::bit_cast<std::uint64_t>(1'000'000'000'000.0);
                if (positive_bits > maximum_money_bits)
                    detail::fail(ErrorCode::invalid_graph, "terminal contribution exceeds 1e12 envelope");
            }
        } else detail::fail(ErrorCode::invalid_graph, "unknown vertex kind");
        const auto child_ids = detail::children(v);
        edge_count_ = detail::checked_entries(edge_count_, child_ids.size());
        if (edge_count_ > limits_.max_edges) detail::fail(ErrorCode::graph_capacity, "graph edge cap exceeded");
        for (const auto child : child_ids) {
            if (child >= n) detail::fail(ErrorCode::invalid_graph, "graph edge references absent vertex");
            if (indegree[child] == std::numeric_limits<std::size_t>::max()) detail::fail(ErrorCode::graph_capacity, "indegree overflow");
            ++indegree[child];
        }
    }
    for (const auto& token : graph_.initial_history) detail::token_bytes(token, limits_.max_token_bytes);
    (void)detail::revealed_cards(graph_.initial_history);
    if (edge_count_ > limits_.max_edges) detail::fail(ErrorCode::graph_capacity, "graph edge cap exceeded");

    std::vector<std::size_t> queue; queue.reserve(n);
    for (std::size_t i = 0; i < n; ++i) if (indegree[i] == 0) queue.push_back(i);
    std::vector<std::size_t> topo; topo.reserve(n);
    for (std::size_t cursor = 0; cursor < queue.size(); ++cursor) {
        const auto id = queue[cursor]; topo.push_back(id);
        for (auto child : detail::children(graph_.vertices[id])) if (--indegree[child] == 0) queue.push_back(child);
    }
    if (topo.size() != n) detail::fail(ErrorCode::graph_cycle, "public graph must be acyclic");

    std::vector<bool> reachable(n, false); std::vector<std::size_t> stack{graph_.root_id}; reachable[graph_.root_id] = true;
    while (!stack.empty()) {
        const auto id = stack.back(); stack.pop_back();
        for (const auto child : detail::children(graph_.vertices[id])) if (!reachable[child]) {
            reachable[child] = true; stack.push_back(child);
        }
    }
    if (std::find(reachable.begin(), reachable.end(), false) != reachable.end())
        detail::fail(ErrorCode::graph_unreachable, "all supplied vertices must be reachable from the root");

    detail::GraphMetrics out; out.topological = topo;
    out.occurrence_counts.assign(n, 0); out.history_token_sums.assign(n, 0);
    out.history_byte_sums.assign(n, 0); out.max_depths.assign(n, 0);
    out.occurrence_counts[graph_.root_id] = 1;
    std::size_t initial_bytes = 0;
    for (const auto& token : graph_.initial_history) initial_bytes = detail::sat_size_add(initial_bytes, token.size());
    out.history_token_sums[graph_.root_id] = graph_.initial_history.size();
    out.history_byte_sums[graph_.root_id] = initial_bytes;
    for (const auto id : topo) {
        const auto& v = graph_.vertices[id]; const auto occ = out.occurrence_counts[id];
        if (occ > limits_.max_logical_visits) detail::fail(ErrorCode::graph_capacity, "logical visit cap exceeded");
        if (out.max_depths[id] > limits_.max_depth) detail::fail(ErrorCode::graph_capacity, "graph depth cap exceeded");
        const auto kids = detail::children(v); const auto labels = detail::edge_labels(v);
        for (std::size_t i = 0; i < kids.size(); ++i) {
            const auto child = kids[i];
            out.occurrence_counts[child] = detail::sat_size_add(out.occurrence_counts[child], occ);
            out.history_token_sums[child] = detail::sat_size_add(out.history_token_sums[child],
                detail::sat_size_add(out.history_token_sums[id], occ));
            out.history_byte_sums[child] = detail::sat_size_add(out.history_byte_sums[child],
                detail::sat_size_add(out.history_byte_sums[id], occ * labels[i].size()));
            out.max_depths[child] = std::max(out.max_depths[child], out.max_depths[id] + 1);
        }
    }
    auto& c = out.census; c.vertices = n; c.edges = edge_count_;
    c.history_token_work = graph_.initial_history.size(); c.history_bytes = initial_bytes;
    for (std::size_t id = 0; id < n; ++id) {
        const auto& v = graph_.vertices[id]; const auto occ = out.occurrence_counts[id];
        c.logical_visits = detail::sat_size_add(c.logical_visits, occ);
        c.maximum_depth = std::max(c.maximum_depth, out.max_depths[id]);
        c.history_token_work = detail::sat_size_add(c.history_token_work, out.history_token_sums[id]);
        c.history_bytes = detail::sat_size_add(c.history_bytes, out.history_byte_sums[id]);
        if (v.kind == VertexKind::decision) {
            c.decision_occurrences = detail::sat_size_add(c.decision_occurrences, occ);
            c.action_slots_upper = detail::sat_size_add(c.action_slots_upper, occ * v.actions.size());
            c.decision_hand_slots_upper = detail::sat_size_add(c.decision_hand_slots_upper, occ * hand_counts_[v.actor]);
            c.history_token_entries_upper = detail::sat_size_add(c.history_token_entries_upper,
                out.history_token_sums[id] + occ * v.actions.size());
            c.row_history_bytes_upper = detail::sat_size_add(c.row_history_bytes_upper,
                out.history_byte_sums[id] + occ * v.actions.size() * limits_.max_token_bytes);
        } else if (v.kind == VertexKind::chance) c.chance_occurrences = detail::sat_size_add(c.chance_occurrences, occ);
        else c.terminal_occurrences = detail::sat_size_add(c.terminal_occurrences, occ);
    }
    if (c.logical_visits > limits_.max_logical_visits || c.maximum_depth > limits_.max_depth ||
        c.history_bytes > limits_.max_history_bytes)
        detail::fail(ErrorCode::graph_capacity, "logical graph/depth/history cap exceeded");
    return out;
}

inline void Plan::verify_group_graph_closure() {
    const auto closure_work = static_cast<std::uint64_t>(group_.size()) *
        (24ULL * graph_.vertices.size() + 24ULL * edge_count_ + 2ULL * graph_input_text_bytes_);
    if (closure_work > limits_.max_modeled_work - admission_work_)
        detail::fail(ErrorCode::work_limit, "suit-closure signature work exceeds graph-plan cap");
    charge_admission_work(closure_work);

    std::map<std::string, std::size_t> ids;
    std::vector<std::size_t> original(graph_.vertices.size());
    std::size_t next = 1;
    for (const auto id : graph_metrics_.topological) {
        const auto kids = detail::children(graph_.vertices[id]);
        std::vector<std::size_t> child_sig; child_sig.reserve(kids.size());
        for (auto child : kids) child_sig.push_back(original[child]);
        auto key = detail::vertex_signature(graph_.vertices[id], child_sig);
        auto [it, inserted] = ids.emplace(std::move(key), next);
        if (inserted) ++next;
        original[id] = it->second;
    }
    for (const auto& mapping : group_) {
        std::vector<std::size_t> mapped(graph_.vertices.size());
        for (const auto id : graph_metrics_.topological) {
            const auto& v = graph_.vertices[id]; const auto kids = detail::children(v);
            std::vector<std::size_t> child_sig; child_sig.reserve(kids.size());
            for (auto child : kids) child_sig.push_back(mapped[child]);
            Vertex transformed = v;
            if (v.kind == VertexKind::chance) {
                for (auto& branch : transformed.branches) {
                    const auto text = detail::transform_reveal(
                        (v.street == Street::flop ? std::string("flop@") : v.street == Street::turn ? std::string("turn@") : std::string("river@")) + branch.label,
                        mapping);
                    branch.label = text.substr(text.find('@') + 1);
                }
            }
            const auto key = detail::vertex_signature(transformed, child_sig);
            const auto found = ids.find(key);
            if (found == ids.end()) detail::fail(ErrorCode::graph_not_invariant, "suit image has no matching public graph signature");
            mapped[id] = found->second;
        }
        if (mapped[graph_.root_id] != original[graph_.root_id])
            detail::fail(ErrorCode::graph_not_invariant, "initial public graph is not fixed by full weighted stabilizer");
        auto transformed_history = transform_history(graph_.initial_history, mapping);
        if (transformed_history != graph_.initial_history)
            detail::fail(ErrorCode::graph_not_invariant, "initial history is not fixed by full weighted stabilizer");
    }
}

inline History Plan::transform_history(std::span<const std::string> history, const SuitMap& mapping) const {
    History out; out.reserve(history.size());
    for (const auto& token : history) out.push_back(detail::transform_reveal(token, mapping));
    return out;
}

inline void Plan::collect_prefixes_and_q_bounds() {
    std::set<std::vector<Card>, detail::PrefixLess> prefixes;
    std::uint64_t occurrence_steps = 0;
    for_each_occurrence([&](std::size_t id, const History& history) {
        occurrence_steps = detail::checked_add(occurrence_steps, 1);
        const auto& vertex = graph_.vertices[id];
        if (vertex.kind == VertexKind::chance) {
            const auto revealed = detail::revealed_cards(history).size();
            const auto expected_revealed = vertex.street == Street::flop ? 0U :
                vertex.street == Street::turn ? 3U : 4U;
            const auto expected_index = vertex.street == Street::flop ? 4U :
                vertex.street == Street::turn ? 5U : 6U;
            if (revealed != expected_revealed || vertex.card_index != expected_index)
                detail::fail(ErrorCode::invalid_graph, "chance street/index does not follow the current revealed-board depth");
        }
        if (graph_.vertices[id].kind == VertexKind::decision || graph_.vertices[id].kind == VertexKind::terminal ||
            graph_.vertices[id].kind == VertexKind::chance) prefixes.insert(detail::revealed_cards(history));
    });
    prefixes_.assign(prefixes.begin(), prefixes.end());
    if (occurrence_steps > graph_census_.logical_visits || prefixes_.size() > occurrence_steps)
        detail::fail(ErrorCode::invalid_graph, "streamed occurrence census exceeded its rank-free bound");
    for (const auto& prefix : prefixes_) {
        bool matched = false;
        for (const auto& board : boards_) {
            bool yes = prefix.size() <= 5;
            for (std::size_t j = 0; yes && j < prefix.size(); ++j) yes = prefix[j] == board.cards[j];
            matched = matched || yes;
        }
        if (!matched) detail::fail(ErrorCode::invalid_graph, "public graph reveal prefix is absent from selected outcomes");
    }
}

inline void Plan::preflight_q_plan() {
    const auto prefix_upper = static_cast<std::uint64_t>(graph_census_.logical_visits);
    const auto lookup = static_cast<std::uint64_t>(group_.size()) *
        (128ULL * graph_census_.history_token_work + 256ULL * graph_census_.decision_hand_slots_upper);
    const bool indexed = admission_profile_ == AdmissionProfile::indexed_v1;
    // The fixed eight envelopes remain intact for real input/group/support,
    // Q-history/menu construction and output preparation. Only the named
    // per-iteration legacy Plan lookups/menu checks are absent in indexed
    // learning; Index/Router separately pre-admit their complete schedule.
    const auto lookup_passes = indexed ? 8ULL : 3ULL * iterations_ + 8ULL;
    const auto action_passes = indexed ? 8ULL : 6ULL * iterations_ + 8ULL;
    if (indexed) {
        legacy_training_lookup_work_removed_ = detail::checked_mul(3ULL * iterations_, lookup);
        legacy_training_action_work_removed_ = detail::checked_mul(6ULL * iterations_, 32ULL * graph_census_.action_slots_upper);
    }
    q_work_upper_ = detail::checked_mul(lookup_passes, lookup);
    q_work_upper_ = detail::checked_add(q_work_upper_,
        detail::checked_mul(action_passes, 32ULL * graph_census_.action_slots_upper));
    q_work_upper_ = detail::checked_add(q_work_upper_,
        24ULL * (16ULL * total_hands() + 32ULL * boards_.size()));
    q_work_upper_ = detail::checked_add(q_work_upper_, graph_census_.logical_visits *
        (2ULL + graph_.initial_history.size()));
    q_work_upper_ = detail::checked_add(q_work_upper_, 2ULL * prefix_upper * boards_.size());
    q_work_upper_ = detail::checked_add(q_work_upper_,
        static_cast<std::uint64_t>(graph_census_.chance_occurrences) * boards_.size());
    const auto h = static_cast<std::uint64_t>(total_hands());
    const auto b = static_cast<std::uint64_t>(boards_.size());
    const auto kernel_setup = 32ULL * h + 16ULL * b + 512ULL + b * (40ULL * h + 512ULL);
    const auto one_board_support = 36ULL * h + 512ULL + 2ULL * h + 32ULL;
    const auto kernel_support = prefix_upper * (b * (36ULL * h + 512ULL) + 2ULL * h + 32ULL) +
        b * one_board_support;
    kernel_setup_support_work_upper_ = detail::checked_add(kernel_setup, kernel_support);
    const auto graph_q_work = detail::checked_add(admission_work_, q_work_upper_);
    const auto estimated_work = detail::checked_add(graph_q_work, kernel_setup_support_work_upper_);
    q_entries_upper_ = prefix_upper * (2ULL * total_hands() + boards_.size() + 16ULL) + boards_.size() +
        static_cast<std::uint64_t>(group_.size()) * (4ULL * total_hands() + 32ULL) +
        40ULL * graph_census_.decision_hand_slots_upper + 3ULL * graph_census_.history_token_entries_upper +
        2ULL * graph_census_.action_slots_upper + static_cast<std::uint64_t>(group_.size()) *
        (8ULL * graph_census_.maximum_depth + 2ULL * graph_census_.history_bytes + 64ULL) + 1024ULL;
    if (estimated_work > limits_.max_modeled_work)
        detail::fail(ErrorCode::work_limit, "graph plus quotient-plan modeled-work admission exceeded");
    if (q_entries_upper_ > limits_.max_retained_entries - admission_entries_)
        detail::fail(ErrorCode::storage_limit, "graph plus quotient-plan retained-entry admission exceeded");
    admission_work_ = estimated_work;
    admission_entries_ += static_cast<std::size_t>(q_entries_upper_);
    // The kernel counter is its own cumulative account. Reserve the graph/Q
    // portion first, then leave its constructor/support estimate plus all
    // remaining shared allowance available to later CFR vector calls.
    const auto kernel_allowance = limits_.max_modeled_work - graph_q_work;
    if (limits_.kernel.max_modeled_work > kernel_allowance)
        limits_.kernel.max_modeled_work = kernel_allowance;
    if (limits_.kernel.max_modeled_work < kernel_setup_support_work_upper_)
        detail::fail(ErrorCode::work_limit, "kernel constructor/support forecast exceeds its admitted counter");
    if (admission_entries_ >= limits_.max_retained_entries)
        detail::fail(ErrorCode::storage_limit, "no retained-entry allowance remains for the owned exact kernel");
    const auto kernel_allowance_entries = limits_.max_retained_entries - admission_entries_;
    if (limits_.kernel.max_storage_entries > kernel_allowance_entries)
        limits_.kernel.max_storage_entries = kernel_allowance_entries;
    const auto kernel_retained_setup = 20ULL * h + 8ULL * b + 256ULL +
        (rank_cache_boards_ + 1ULL) * h;
    const auto constructor_scratch = 12ULL * h + 512ULL;
    const auto support_scratch = 10ULL * h + 600ULL;
    const auto kernel_storage_required = kernel_retained_setup +
        std::max(constructor_scratch, support_scratch);
    if (limits_.kernel.max_storage_entries < kernel_storage_required)
        detail::fail(ErrorCode::storage_limit, "owned exact kernel setup/support storage forecast exceeds allowance");
}

inline void Plan::instantiate_owned_kernel() {
    kernel_ = std::make_unique<exact_selected_kernel::ExactSelectedKernel>(
        ranges_[0], ranges_[1], boards_, rank_cache_boards_, limits_.kernel);
    for (const auto& mapping : group_) {
        std::array<std::vector<std::size_t>, 2> hand_map;
        for (std::size_t side = 0; side < 2; ++side) {
            std::map<std::uint16_t, std::size_t> indices;
            for (std::size_t i = 0; i < ranges_[side].size(); ++i)
                indices.emplace(detail::holding_key(ranges_[side][i].hand), i);
            hand_map[side].resize(ranges_[side].size());
            for (std::size_t i = 0; i < ranges_[side].size(); ++i) {
                const auto h = detail::mapped_hand(ranges_[side][i].hand, mapping);
                const auto it = indices.find(detail::holding_key(Hand{h[0], h[1]}));
                if (it == indices.end()) detail::fail(ErrorCode::group_invalid, "missing transformed weighted holding");
                hand_map[side][i] = it->second;
            }
        }
        hand_maps_[0].push_back(std::move(hand_map[0])); hand_maps_[1].push_back(std::move(hand_map[1]));
    }
}

inline std::vector<std::size_t> Plan::indexes_for_prefix(const std::vector<Card>& prefix) const {
    std::vector<std::size_t> indexes; indexes.reserve(boards_.size());
    for (std::size_t i = 0; i < boards_.size(); ++i) {
        bool match = prefix.size() <= 5;
        for (std::size_t j = 0; match && j < prefix.size(); ++j) match = prefix[j] == boards_[i].cards[j];
        if (match) indexes.push_back(i);
    }
    return indexes;
}

inline void Plan::validate_chance_coverage() {
    positive_selected_boards_.assign(boards_.size(), false);
    for (std::size_t board_index = 0; board_index < boards_.size(); ++board_index) {
        const std::array<std::size_t, 1> index{board_index};
        const auto supported = kernel_->support(index);
        positive_selected_boards_[board_index] =
            std::any_of(supported[0].begin(), supported[0].end(), [](bool value) { return value; }) ||
            std::any_of(supported[1].begin(), supported[1].end(), [](bool value) { return value; });
    }
    for_each_occurrence([&](std::size_t id, const History& history) {
        const auto& vertex = graph_.vertices[id];
        if (vertex.kind != VertexKind::chance) return;
        const auto prefix = detail::revealed_cards(history);
        std::set<std::string> expected;
        for (std::size_t i = 0; i < boards_.size(); ++i) {
            if (!positive_selected_boards_[i]) continue;
            bool matches = prefix.size() <= 5;
            for (std::size_t j = 0; matches && j < prefix.size(); ++j)
                matches = prefix[j] == boards_[i].cards[j];
            if (!matches) continue;
            if (vertex.street == Street::flop) {
                expected.insert(detail::card_text(boards_[i].cards[0]) +
                    detail::card_text(boards_[i].cards[1]) + detail::card_text(boards_[i].cards[2]));
            } else if (vertex.street == Street::turn) expected.insert(detail::card_text(boards_[i].cards[3]));
            else expected.insert(detail::card_text(boards_[i].cards[4]));
        }
        std::set<std::string> actual;
        for (const auto& branch : vertex.branches) actual.insert(branch.label);
        if (expected.empty() || actual != expected)
            detail::fail(ErrorCode::invalid_graph, "chance branches do not exactly cover positive compatible selected outcomes");
    });
}

inline void Plan::build_support_cache() {
    for (const auto& prefix : prefixes_) {
        auto indexes = indexes_for_prefix(prefix);
        if (indexes.empty()) detail::fail(ErrorCode::invalid_graph, "graph prefix has no selected-board outcomes");
        const auto supported = kernel_->support(indexes);
        std::array<std::vector<std::size_t>, 2> hands;
        for (std::size_t p = 0; p < 2; ++p)
            for (std::size_t i = 0; i < supported[p].size(); ++i) if (supported[p][i]) hands[p].push_back(i);
        support_.emplace(prefix, PrefixSupport{std::move(indexes), std::move(hands)});
    }
}

inline void Plan::build_q_rows() {
    std::map<RowKey, QBuild> builds;
    for_each_occurrence([&](std::size_t id, const History& history) {
        const auto& v = graph_.vertices[id]; if (v.kind != VertexKind::decision) return;
        const auto prefix = detail::revealed_cards(history);
        const auto found = support_.find(prefix);
        if (found == support_.end()) detail::fail(ErrorCode::unsupported_row, "missing admitted prefix support");
        for (const auto hand : found->second.hands[v.actor]) {
            RowKey key{v.actor, hand, history}; auto images = row_images(key);
            for (const auto& image : images) {
                const auto image_support = support_.find(detail::revealed_cards(image.history));
                if (image_support == support_.end() ||
                    !std::binary_search(image_support->second.hands[image.actor].begin(),
                                        image_support->second.hands[image.actor].end(), image.hand_index))
                    detail::fail(ErrorCode::group_not_closed, "suit image row is absent from positive physical support");
            }
            const auto& representative = images.front();
            const auto it = builds.find(representative);
            if (it == builds.end()) builds.emplace(representative, QBuild{v.actions, images.size(), 0});
            else if (it->second.menu != v.actions || it->second.orbit_size != images.size())
                detail::fail(ErrorCode::unsupported_row, "repeated Q representative has inconsistent orbit/menu");
        }
    });
    rows_.reserve(builds.size()); locations_.clear(); locations_.insert({});
    for (const auto& [key, data] : builds) {
        const auto index = rows_.size(); QRow row; row.key = key; row.menu = data.menu;
        row.count = row.menu.size(); row.orbit_size = data.orbit_size;
        row.size = data.orbit_size;
        row.expected_mask = row.orbit_size == 32 ? 0xffffffffU : ((1U << row.orbit_size) - 1U);
        rows_.push_back(std::move(row)); locations_.emplace(key, index);
    }
    std::size_t offset = 0;
    for (auto& row : rows_) { row.offset = offset; offset = detail::checked_entries(offset, row.count); }
}

inline void Plan::finalize_receipt() {
    if (admission_profile_ == AdmissionProfile::indexed_v1) receipt_.admission_contract = "indexed-v1";
    receipt_.legacy_training_lookup_work_removed = legacy_training_lookup_work_removed_;
    receipt_.legacy_training_action_work_removed = legacy_training_action_work_removed_;
    receipt_.graph_vertices = graph_census_.vertices; receipt_.graph_edges = graph_census_.edges;
    receipt_.logical_visits = graph_census_.logical_visits;
    receipt_.decision_occurrences = graph_census_.decision_occurrences;
    receipt_.chance_occurrences = graph_census_.chance_occurrences;
    receipt_.terminal_occurrences = graph_census_.terminal_occurrences;
    receipt_.maximum_depth = graph_census_.maximum_depth;
    receipt_.history_token_work = graph_census_.history_token_work;
    receipt_.history_bytes = graph_census_.history_bytes;
    receipt_.history_token_entries_upper = graph_census_.history_token_entries_upper;
    receipt_.row_history_bytes_upper = graph_census_.row_history_bytes_upper;
    receipt_.group_size = group_.size(); receipt_.support_prefixes = support_.size();
    receipt_.quotient_rows = rows_.size();
    for (const auto& row : rows_) receipt_.quotient_action_slots += row.count;
    receipt_.modeled_work_upper = admission_work_;
    receipt_.retained_entries_upper = admission_entries_ + kernel_->receipt().retained_entries;
    receipt_.peak_scratch_entries_upper = kernel_->receipt().peak_scratch_entries;
}

template<class Function>
inline void Plan::for_each_occurrence(Function&& function) const {
    History history = graph_.initial_history;
    struct Frame { std::size_t vertex, child_index, history_size; bool entered; };
    std::vector<Frame> stack; stack.reserve(limits_.max_depth + 2);
    stack.push_back({graph_.root_id, 0, history.size(), false});
    while (!stack.empty()) {
        auto& frame = stack.back();
        const auto& v = graph_.vertices[frame.vertex];
        if (!frame.entered) { frame.entered = true; function(frame.vertex, history); }
        const auto kids = detail::children(v);
        if (frame.child_index >= kids.size()) {
            history.resize(frame.history_size); stack.pop_back(); continue;
        }
        const auto index = frame.child_index++;
        if (v.kind == VertexKind::decision) history.push_back(v.actions[index].token);
        else if (v.kind == VertexKind::chance) {
            const char* prefix = v.street == Street::flop ? "flop@" : v.street == Street::turn ? "turn@" : "river@";
            history.push_back(std::string(prefix) + v.branches[index].label);
        }
        stack.push_back({kids[index], 0, history.size() - (v.kind == VertexKind::terminal ? 0 : 1), false});
    }
}

inline const Vertex& Plan::decision_at_history(std::span<const std::string> history) const {
    if (history.size() < graph_.initial_history.size() ||
        !std::equal(graph_.initial_history.begin(), graph_.initial_history.end(), history.begin()))
        detail::fail(ErrorCode::invalid_query, "history does not begin with graph initial history");
    std::size_t id = graph_.root_id; std::size_t pos = graph_.initial_history.size();
    while (true) {
        const auto& v = graph_.vertices[id];
        if (v.kind == VertexKind::decision) {
            if (pos == history.size()) return v;
            const auto it = std::find_if(v.actions.begin(), v.actions.end(), [&](const Action& a) { return a.token == history[pos]; });
            if (it == v.actions.end()) detail::fail(ErrorCode::invalid_query, "history action token absent from ordered menu");
            id = v.children[static_cast<std::size_t>(it - v.actions.begin())]; ++pos;
        } else if (v.kind == VertexKind::chance) {
            if (pos == history.size()) detail::fail(ErrorCode::invalid_query, "history ends at chance vertex");
            const auto& token = history[pos]; const auto at = token.find('@');
            const auto expected = v.street == Street::flop ? "flop" : v.street == Street::turn ? "turn" : "river";
            if (at == std::string::npos || token.substr(0, at) != expected)
                detail::fail(ErrorCode::invalid_query, "history reveal street differs from graph");
            const auto label = token.substr(at + 1);
            const auto it = std::find_if(v.branches.begin(), v.branches.end(), [&](const Branch& b) { return b.label == label; });
            if (it == v.branches.end()) detail::fail(ErrorCode::invalid_query, "history reveal label absent from graph");
            id = it->child; ++pos;
        } else detail::fail(ErrorCode::invalid_query, "history continues past terminal");
    }
}

inline const std::vector<Action>& Plan::menu_at_history(std::uint8_t actor,
                                                        std::span<const std::string> history) const {
    const auto& v = decision_at_history(history);
    if (v.kind != VertexKind::decision || v.actor != actor) detail::fail(ErrorCode::invalid_query, "history is not the requested actor decision");
    return v.actions;
}

inline void Plan::validate_row_key(const RowKey& key) const {
    if (key.actor > 1 || key.hand_index >= hand_counts_[key.actor]) detail::fail(ErrorCode::invalid_query, "row actor/hand index invalid");
    const auto& menu = menu_at_history(key.actor, key.history);
    (void)menu;
    const auto prefix = detail::revealed_cards(key.history);
    const auto it = support_.find(prefix);
    if (it == support_.end() || !std::binary_search(it->second.hands[key.actor].begin(), it->second.hands[key.actor].end(), key.hand_index))
        detail::fail(ErrorCode::unsupported_row, "row hand has no positive physical support at this prefix");
}

inline void Plan::validate_query_history(std::span<const std::string> history) const {
    if (history.size() > graph_.initial_history.size() + limits_.max_depth)
        detail::fail(ErrorCode::invalid_query, "history token count exceeds graph depth envelope");
    std::size_t bytes = 0;
    for (const auto& token : history) {
        const auto token_size = detail::token_bytes(token, limits_.max_token_bytes);
        bytes = detail::checked_entries(bytes, token_size);
        if (bytes > limits_.max_history_bytes)
            detail::fail(ErrorCode::invalid_query, "history text exceeds graph-plan envelope");
    }
    (void)detail::revealed_cards(history);
}

inline std::vector<RowKey> Plan::row_images(const RowKey& key, const std::vector<History>* transformed) const {
    std::vector<RowKey> images; images.reserve(group_.size());
    for (std::size_t g = 0; g < group_.size(); ++g) {
        const auto history = transformed ? (*transformed)[g] : transform_history(key.history, group_[g]);
        images.push_back({key.actor, hand_maps_[key.actor][g][key.hand_index], history});
    }
    std::sort(images.begin(), images.end()); images.erase(std::unique(images.begin(), images.end()), images.end());
    return images;
}

} // namespace openpoker::exact_public_graph

