#pragma once

// Bounded graph-only lexicographic public-history ordinals. This index keeps
// one canonical continuation class per exact graph signature and prebuilt
// suit-image edge transitions; it never stores unfolded occurrence histories.

#include "exact_public_graph.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <map>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace openpoker::exact_public_history_index {

using namespace exact_public_graph;

inline constexpr std::size_t kMaximumSuitMaps = 24;
inline constexpr std::size_t kFixedBookkeepingEntriesUpper = 512;
inline constexpr std::size_t kVertexClassScalarEntries = 1;
inline constexpr std::size_t kClassRecordScalarEntries = 4;
inline constexpr std::size_t kRawVertexRecordScalarEntries = 2;
inline constexpr std::size_t kClassEdgeScalarEntries = 2;
inline constexpr std::size_t kRawEdgeScalarEntries = 2;
inline constexpr std::size_t kMappedTransitionScalarEntries = 6;
inline constexpr std::size_t kClassEdgeUpperSlackEntries = 1;
inline constexpr std::size_t kMappedTransitionUpperSlackEntries = 2;

struct QuerySchedule {
    std::uint64_t history_route_calls = 0;
    std::uint64_t history_route_tokens_upper = 0;
    std::uint64_t root_cursor_calls = 0; // excludes route-internal roots
    std::uint64_t edge_advance_calls = 0;
};

struct ExternalReservation {
    std::uint64_t work_upper = 0;
    std::size_t entries_upper = 0;
};

struct QueryCounts {
    std::uint64_t history_routes = 0;
    std::uint64_t history_route_tokens = 0;
    std::uint64_t root_cursors = 0;
    std::uint64_t edge_advances = 0;
};

struct Limits {
    // These are whole-owner ceilings. The constructor adds the existing Plan
    // receipt to the new index's retained/scratch and work reservations.
    std::uint64_t max_combined_modeled_work = kMaximumModeledWork;
    std::size_t max_combined_entries = kMaximumRetainedEntries;
    std::optional<QuerySchedule> query_schedule = std::nullopt;
    ExternalReservation external{};
};

struct Receipt {
    std::string version = "native-exact-public-history-index-v1";
    std::size_t graph_vertices = 0;
    std::size_t graph_edges = 0;
    std::size_t continuation_classes = 0;
    std::size_t suit_maps = 0;
    std::size_t logical_occurrences = 0;
    std::size_t class_edge_entries = 0;
    std::size_t raw_edge_entries = 0;
    std::size_t suit_class_entries = 0;
    std::size_t transformed_transition_entries = 0;
    std::size_t ordinal_entries = 0;
    std::size_t expanded_history_table_entries = 0;
    std::size_t physical_row_lookup_table_entries = 0;
    std::size_t retained_token_bytes = 0;
    std::size_t retained_token_bytes_upper = 0;
    std::size_t index_fixed_bookkeeping_entries_upper = 0;
    std::size_t index_vertex_record_entries_upper = 0;
    std::size_t index_class_edge_entries_upper = 0;
    std::size_t index_raw_edge_entries_upper = 0;
    std::size_t index_suit_class_entries_upper = 0;
    std::size_t index_transformed_transition_entries_upper = 0;
    std::size_t index_token_bytes_entries_upper = 0;
    std::size_t index_fixed_bookkeeping_entries_actual = 0;
    std::size_t vertex_class_entries_actual = 0;
    std::size_t class_record_entries_actual = 0;
    std::size_t raw_vertex_record_entries_actual = 0;
    std::size_t class_edge_entries_actual = 0;
    std::size_t class_edge_string_headers_actual = 0;
    std::size_t class_lex_order_entries_actual = 0;
    std::size_t raw_edge_entries_actual = 0;
    std::size_t raw_edge_string_headers_actual = 0;
    std::size_t raw_lex_order_entries_actual = 0;
    std::size_t suit_class_entries_actual = 0;
    std::size_t transformed_transition_entries_actual = 0;
    std::size_t retained_token_bytes_actual = 0;
    std::size_t index_retained_entries_actual = 0;
    std::size_t signature_scratch_bytes_upper = 0;
    std::uint64_t plan_modeled_work_upper = 0;
    std::uint64_t index_modeled_work_upper = 0;
    std::uint64_t combined_modeled_work_upper = 0;
    std::uint64_t combined_base_modeled_work_upper = 0;
    std::uint64_t external_work_upper = 0;
    std::size_t external_entries_upper = 0;
    bool query_schedule_declared = false;
    std::uint64_t query_work_upper = 0;
    std::size_t query_cumulative_entries_upper = 0;
    std::size_t combined_base_peak_entries_upper = 0;
    std::uint64_t modeled_work_limit = 0;
    std::size_t plan_retained_entries_upper = 0;
    std::size_t index_retained_entries_upper = 0;
    std::size_t index_scratch_entries_upper = 0;
    std::size_t combined_peak_entries_upper = 0;
    std::size_t retained_entry_limit = 0;
    std::size_t max_query_depth = 0;
    std::string scope =
        "Logical scalar/string-header/token-character entry bounds plus modeled comparisons; fixed 512-entry reserve covers index/receipt bookkeeping, vector control blocks and fixed receipt strings. Not allocator bytes, vector capacity, CPU or RSS. Plan must outlive index.";
};

// Exact value encoding of a visible card prefix. This fixed-size typed ID
// contains only cards already revealed along the current public path.
struct VisiblePrefixId {
    std::array<Card, 5> cards{};
    std::uint8_t size = 0;
    friend bool operator==(const VisiblePrefixId&, const VisiblePrefixId&) = default;
};

struct CursorImage {
    std::size_t continuation_class = 0;
    std::uint64_t ordinal = 0;
    VisiblePrefixId visible_prefix{};
};

class TraversalWorkspace;
class FrameView;

class HistoryIndex final {
    friend class TraversalWorkspace;
    friend class FrameView;
public:
    class Cursor final {
    public:
        Cursor(const Cursor&) = default;
        Cursor(Cursor&&) noexcept = default;
        Cursor& operator=(const Cursor&) = default;
        Cursor& operator=(Cursor&&) noexcept = default;

        [[nodiscard]] std::uint64_t ordinal() const noexcept { return images_[0].ordinal; }
        [[nodiscard]] std::size_t image_count() const noexcept { return image_count_; }
        [[nodiscard]] std::uint64_t image_ordinal(std::size_t map_index) const {
            if (map_index >= image_count_) detail::fail(ErrorCode::invalid_query, "history cursor suit-map index is invalid");
            return images_[map_index].ordinal;
        }
        [[nodiscard]] VisiblePrefixId visible_prefix(std::size_t map_index = 0) const {
            if (map_index >= image_count_) detail::fail(ErrorCode::invalid_query, "history cursor prefix map index is invalid");
            return images_[map_index].visible_prefix;
        }

    private:
        friend class HistoryIndex;
        Cursor() = default;
        const HistoryIndex* owner_ = nullptr;
        std::uint64_t generation_ = 0;
        std::size_t raw_vertex_ = 0;
        std::size_t image_count_ = 0;
        std::array<CursorImage, kMaximumSuitMaps> images_{};
    };

    explicit HistoryIndex(const Plan& plan, Limits limits = {})
        : plan_(&plan), graph_(&plan.graph()), limits_(limits),
          generation_(next_generation()) {
        validate_limits();
        preflight();
        build_topology_and_signatures();
        build_class_edges_and_offsets();
        build_suit_transitions();
        finalize_receipt();
    }

    HistoryIndex(const HistoryIndex&) = delete;
    HistoryIndex& operator=(const HistoryIndex&) = delete;
    HistoryIndex(HistoryIndex&&) = delete;
    HistoryIndex& operator=(HistoryIndex&&) = delete;

    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }
    [[nodiscard]] const Graph& graph() const noexcept { return *graph_; }
    [[nodiscard]] const Vertex& vertex_at(const Cursor& cursor) const {
        validate_cursor(cursor);
        return graph_->vertices[cursor.raw_vertex_];
    }
    [[nodiscard]] const Vertex& vertex_at(const FrameView& view) const;
    [[nodiscard]] std::size_t suit_map_count() const noexcept { return plan_->group().size(); }
    [[nodiscard]] std::uint64_t query_work_reserved() const noexcept {
        return query_work_used_.load(std::memory_order_relaxed);
    }
    [[nodiscard]] std::size_t inverse_query_entries_reserved() const noexcept {
        return query_entries_used_.load(std::memory_order_relaxed);
    }
    [[nodiscard]] std::optional<QuerySchedule> declared_query_schedule() const noexcept {
        return limits_.query_schedule;
    }
    [[nodiscard]] QueryCounts query_counts() const noexcept {
        return {route_calls_used_.load(std::memory_order_relaxed), route_tokens_used_.load(std::memory_order_relaxed),
            root_calls_used_.load(std::memory_order_relaxed), edge_calls_used_.load(std::memory_order_relaxed)};
    }

    [[nodiscard]] Cursor root_cursor() const {
        reserve_scheduled(root_calls_used_, 1, limits_.query_schedule ? limits_.query_schedule->root_cursor_calls : 0);
        return make_root_cursor();
    }

    // Advance by the physical vertex's original child index. This preserves
    // production traversal order even when equivalent chance vertices list
    // their branches in different orders.
    [[nodiscard]] Cursor advance_edge(const Cursor& cursor, std::size_t child_index) const {
        validate_cursor(cursor);
        const auto& vertex = graph_->vertices[cursor.raw_vertex_];
        const auto raw_count = vertex.kind == VertexKind::decision ? vertex.actions.size() :
                               vertex.kind == VertexKind::chance ? vertex.branches.size() : 0U;
        if (child_index >= raw_count)
            detail::fail(ErrorCode::invalid_query, "history index edge position is outside the active menu");
        const auto raw_edge_id = raw_vertex_edges_[cursor.raw_vertex_].edge_begin + child_index;
        reserve_scheduled(edge_calls_used_, 1, limits_.query_schedule ? limits_.query_schedule->edge_advance_calls : 0);
        reserve_query_work(edge_work_per_call());
        return advance_canonical_edge(cursor, raw_edges_[raw_edge_id].canonical_edge,
                                      raw_edges_[raw_edge_id].child_vertex);
    }

    [[nodiscard]] Cursor advance_action(const Cursor& cursor, std::size_t action_index) const {
        validate_cursor(cursor);
        if (graph_->vertices[cursor.raw_vertex_].kind != VertexKind::decision)
            detail::fail(ErrorCode::invalid_query, "action advance requires a decision vertex");
        return advance_edge(cursor, action_index);
    }

    [[nodiscard]] Cursor advance_reveal(const Cursor& cursor, std::size_t branch_index) const {
        validate_cursor(cursor);
        if (graph_->vertices[cursor.raw_vertex_].kind != VertexKind::chance)
            detail::fail(ErrorCode::invalid_query, "reveal advance requires a chance vertex");
        return advance_edge(cursor, branch_index);
    }

    // Validated history route used by the old literal full-history path and
    // by conformance tests. Initial history is a fixed common prefix.
    [[nodiscard]] Cursor cursor_from_history(std::span<const std::string> history) const {
        const auto depth = history.size();
        const auto maximum_tokens = graph_->initial_history.size() + plan_->graph_census().maximum_depth;
        if (depth < graph_->initial_history.size() || depth > maximum_tokens)
            detail::fail(ErrorCode::invalid_query, "history exceeds admitted token depth");
        reserve_scheduled(route_calls_used_, 1, limits_.query_schedule ? limits_.query_schedule->history_route_calls : 0);
        reserve_scheduled(route_tokens_used_, depth,
            limits_.query_schedule ? limits_.query_schedule->history_route_tokens_upper : 0);
        const auto route_work = detail::checked_mul(depth, route_work_per_token());
        reserve_query_work(route_work);
        std::size_t bytes = 0;
        for (const auto& token : history) {
            detail::token_bytes(token, kMaximumTokenBytes);
            bytes = detail::checked_entries(bytes, token.size());
            if (bytes > kMaximumHistoryBytes)
                detail::fail(ErrorCode::invalid_query, "history exceeds admitted byte cap");
        }
        for (std::size_t i = 0; i < graph_->initial_history.size(); ++i)
            if (history[i] != graph_->initial_history[i])
                detail::fail(ErrorCode::invalid_query, "history does not begin with the fixed admitted initial prefix");
        auto cursor = make_root_cursor();
        for (std::size_t i = graph_->initial_history.size(); i < history.size(); ++i)
            cursor = advance_token_unreserved(cursor, history[i]);
        return cursor;
    }

    [[nodiscard]] Cursor advance_token(const Cursor& cursor, std::string_view token) const {
        if (limits_.query_schedule)
            detail::fail(ErrorCode::invalid_query, "token advances are absent from the declared index schedule");
        validate_cursor(cursor);
        if (token.empty() || token.size() > kMaximumTokenBytes)
            detail::fail(ErrorCode::invalid_query, "history edge token is empty or oversized");
        reserve_query_work(static_cast<std::uint64_t>(token.size()) *
            (ceil_log2(std::max<std::size_t>(2, raw_vertex_edges_[cursor.raw_vertex_].edge_count)) + 2ULL) +
            8ULL * cursor.image_count_);
        return advance_token_unreserved(cursor, token);
    }

    [[nodiscard]] History history_at_ordinal(std::uint64_t ordinal) const {
        if (limits_.query_schedule)
            detail::fail(ErrorCode::invalid_query, "inverse queries are absent from the declared index schedule");
        const auto root_class = vertex_class_[graph_->root_id];
        if (ordinal >= classes_[root_class].subtree_count)
            detail::fail(ErrorCode::invalid_query, "history ordinal is outside the admitted logical path range");
        const auto max_depth = graph_->initial_history.size() + plan_->graph_census().maximum_depth;
        const auto scratch_work = static_cast<std::uint64_t>(max_depth) *
            (kMaximumTokenBytes + maximum_degree_ + 2ULL);
        reserve_query_work(scratch_work);
        reserve_query_entries(max_depth * (kMaximumTokenBytes + 1ULL));

        History result;
        result.reserve(max_depth);
        for (const auto& token : graph_->initial_history) result.push_back(token);
        auto continuation = root_class;
        auto relative = ordinal;
        std::size_t depth = 0;
        while (relative != 0) {
            if (++depth > plan_->graph_census().maximum_depth)
                detail::fail(ErrorCode::invalid_query, "history ordinal exceeded the graph depth bound");
            const auto& record = classes_[continuation];
            bool selected = false;
            for (std::size_t position = 0; position < record.edge_count; ++position) {
                const auto edge_id = class_lex_order_[record.edge_begin + position];
                const auto& edge = class_edges_[edge_id];
                if (relative == edge.offset) {
                    result.push_back(edge.token);
                    continuation = edge.child_class;
                    relative = 0;
                    selected = true;
                    break;
                }
                if (relative > edge.offset && relative - edge.offset < classes_[edge.child_class].subtree_count) {
                    result.push_back(edge.token);
                    relative -= edge.offset;
                    continuation = edge.child_class;
                    selected = true;
                    break;
                }
            }
            if (!selected) detail::fail(ErrorCode::invalid_query, "history ordinal does not map to an admitted child interval");
        }
        return result;
    }

private:
    [[nodiscard]] std::uint64_t root_work_per_call() const {
        return detail::checked_mul(plan_->group().size(),
            detail::checked_add(detail::checked_mul(graph_->initial_history.size(), kMaximumTokenBytes), 8));
    }
    [[nodiscard]] std::size_t root_entries_per_call() const {
        return static_cast<std::size_t>(detail::checked_mul(plan_->group().size(), kMaximumTokenBytes));
    }
    [[nodiscard]] std::uint64_t edge_work_per_call() const {
        return 8ULL + 8ULL * plan_->group().size();
    }
    [[nodiscard]] std::uint64_t route_work_per_token() const {
        return kMaximumTokenBytes * (ceil_log2(std::max<std::size_t>(2, maximum_degree_)) + 2ULL) +
            8ULL * plan_->group().size() + 8ULL;
    }
    void reserve_scheduled(std::atomic<std::uint64_t>& counter, std::uint64_t amount,
                           std::uint64_t upper) const {
        if (!limits_.query_schedule) return;
        auto previous = counter.load(std::memory_order_relaxed);
        while (true) {
            const auto next = detail::checked_add(previous, amount);
            if (next > upper)
                detail::fail(ErrorCode::work_limit, "index operation exceeds its declared complete-call schedule");
            if (counter.compare_exchange_weak(previous, next,
                    std::memory_order_relaxed, std::memory_order_relaxed)) return;
        }
    }
    [[nodiscard]] Cursor make_root_cursor() const {
        reserve_query_work(root_work_per_call());
        reserve_query_entries(root_entries_per_call());
        Cursor result;
        result.owner_ = this;
        result.generation_ = generation_;
        result.raw_vertex_ = graph_->root_id;
        result.image_count_ = plan_->group().size();
        const auto root_class = vertex_class_[graph_->root_id];
        for (std::size_t g = 0; g < result.image_count_; ++g) {
            const auto image_class = class_map_[g * classes_.size() + root_class];
            if (image_class != root_class)
                detail::fail(ErrorCode::graph_not_invariant, "history index suit image moved the public root");
            result.images_[g].continuation_class = image_class;
            result.images_[g].visible_prefix = initial_prefix(plan_->group()[g]);
        }
        return result;
    }
    struct ClassRecord {
        std::size_t representative_vertex = 0;
        std::size_t edge_begin = 0;
        std::size_t edge_count = 0;
        std::uint64_t subtree_count = 0;
    };
    struct ClassEdge {
        std::string token;
        std::size_t child_class = 0;
        std::uint64_t offset = 0;
    };
    struct RawEdge {
        std::string token;
        std::size_t child_vertex = 0;
        std::size_t canonical_edge = 0;
    };
    struct PrefixDelta {
        std::array<Card, 3> cards{};
        std::uint8_t count = 0;
    };
    struct MappedTransition {
        std::size_t child_class = 0;
        std::uint64_t offset = 0;
        PrefixDelta prefix{};
    };
    struct RawVertexRecord { std::size_t edge_begin = 0; std::size_t edge_count = 0; };

    static std::uint64_t next_generation() {
        auto value = generation_counter_.load(std::memory_order_relaxed);
        while (true) {
            if (value == 0 || value == std::numeric_limits<std::uint64_t>::max())
                detail::fail(ErrorCode::invalid_limits, "history-index generation space exhausted");
            if (generation_counter_.compare_exchange_weak(value, value + 1,
                    std::memory_order_relaxed, std::memory_order_relaxed)) return value;
        }
    }
    static std::size_t ceil_log2(std::size_t value) noexcept {
        if (value <= 1) return 0;
        return static_cast<std::size_t>(std::bit_width(value - 1));
    }
    static std::uint64_t checked_uadd(std::uint64_t a, std::uint64_t b) {
        return detail::checked_add(a, b);
    }
    static std::size_t checked_sadd(std::size_t a, std::size_t b) {
        return detail::checked_entries(a, b);
    }

    void validate_limits() const {
        if (limits_.max_combined_modeled_work == 0 ||
            limits_.max_combined_modeled_work > kMaximumModeledWork ||
            limits_.max_combined_entries == 0 ||
            limits_.max_combined_entries > kMaximumRetainedEntries)
            detail::fail(ErrorCode::invalid_limits, "history-index combined limits must be positive and reduce-only");
        if (limits_.external.work_upper > limits_.max_combined_modeled_work ||
            limits_.external.entries_upper > limits_.max_combined_entries)
            detail::fail(ErrorCode::invalid_limits, "external reservation exceeds the shared ceiling");
        if (plan_->group().empty() || plan_->group().size() > kMaximumSuitMaps)
            detail::fail(ErrorCode::group_invalid, "history-index suit-group size is outside the S4 ceiling");
        if (plan_->group().front().image != std::array<std::uint8_t, 4>{0, 1, 2, 3})
            detail::fail(ErrorCode::group_invalid, "history cursor requires identity suit map at group index zero");
    }

    void preflight() {
        const auto& census = plan_->graph_census();
        const auto v = census.vertices;
        const auto e = census.edges;
        const auto g = plan_->group().size();
        const auto pre_scan_work = detail::checked_add(8ULL * v + 8ULL * e,
            detail::checked_add(detail::checked_mul(2ULL * kMaximumTokenBytes, e),
                detail::checked_mul(kMaximumTokenBytes, graph_->initial_history.size())));
        if (detail::checked_add(detail::checked_add(plan_->receipt().modeled_work_upper,
                limits_.external.work_upper), pre_scan_work) >
            limits_.max_combined_modeled_work)
            detail::fail(ErrorCode::work_limit, "history-index bounded input scan exceeds remaining combined work before token scan");
        std::size_t text_bytes = 0;
        std::size_t copied_edge_token_bytes = 0;
        std::size_t max_degree = 0;
        std::size_t signature_bytes = 0;
        std::size_t initial_history_bytes = 0;
        for (const auto& vertex : graph_->vertices) {
            const auto degree = vertex.kind == VertexKind::decision ? vertex.actions.size() :
                                vertex.kind == VertexKind::chance ? vertex.branches.size() : 0U;
            max_degree = std::max(max_degree, degree);
            if (vertex.kind == VertexKind::decision) {
                for (const auto& action : vertex.actions) {
                    text_bytes = checked_sadd(text_bytes, action.token.size());
                    text_bytes = checked_sadd(text_bytes, action.name.size());
                    copied_edge_token_bytes = checked_sadd(copied_edge_token_bytes, action.token.size());
                }
            } else if (vertex.kind == VertexKind::chance) {
                const auto prefix_bytes = vertex.street == Street::river ? 6U : 5U;
                for (const auto& branch : vertex.branches) {
                    text_bytes = checked_sadd(text_bytes, branch.label.size() + prefix_bytes);
                    copied_edge_token_bytes = checked_sadd(copied_edge_token_bytes, branch.label.size() + prefix_bytes);
                }
            }
            signature_bytes = checked_sadd(signature_bytes, 64U);
            signature_bytes = checked_sadd(signature_bytes,
                degree * (2U * kMaximumTokenBytes + 64U));
        }
        for (const auto& token : graph_->initial_history) {
            text_bytes = checked_sadd(text_bytes, token.size());
            initial_history_bytes = checked_sadd(initial_history_bytes, token.size());
        }
        if (text_bytes > kMaximumHistoryBytes)
            detail::fail(ErrorCode::history_limit, "history-index copied token text exceeds the existing history cap");
        maximum_degree_ = max_degree;
        if (limits_.query_schedule) {
            const auto& schedule = *limits_.query_schedule;
            if ((!schedule.history_route_calls && schedule.history_route_tokens_upper) ||
                schedule.history_route_tokens_upper < detail::checked_mul(
                    schedule.history_route_calls, graph_->initial_history.size()))
                detail::fail(ErrorCode::invalid_limits, "history route token schedule cannot cover its fixed prefixes");
            const auto roots = detail::checked_add(schedule.history_route_calls, schedule.root_cursor_calls);
            query_work_upper_ = detail::checked_add(detail::checked_mul(roots, root_work_per_call()),
                detail::checked_add(detail::checked_mul(schedule.history_route_tokens_upper, route_work_per_token()),
                    detail::checked_mul(schedule.edge_advance_calls, edge_work_per_call())));
            const auto entries = detail::checked_mul(roots, root_entries_per_call());
            if (entries > limits_.max_combined_entries)
                detail::fail(ErrorCode::storage_limit, "index cumulative query entries exceed the shared ceiling");
            query_entries_upper_ = static_cast<std::size_t>(entries);
        }
        const auto log_v = ceil_log2(std::max<std::size_t>(2, v));
        const auto log_d = ceil_log2(std::max<std::size_t>(2, max_degree));
        const auto sort_comparisons = detail::checked_mul(2ULL * e, log_d + 1U);
        const auto signature_work = detail::checked_mul(
            static_cast<std::uint64_t>(g) * (log_v + 2U), signature_bytes);
        const auto transformed_match_work = detail::checked_mul(
            static_cast<std::uint64_t>(g) * e,
            static_cast<std::uint64_t>(log_d + 1U) * kMaximumTokenBytes);
        const auto raw_edge_match_work = detail::checked_mul(e,
            static_cast<std::uint64_t>(log_d + 1U) * kMaximumTokenBytes);
        const auto transformed_initial_work = detail::checked_mul(g, initial_history_bytes);
        const auto base_work = detail::checked_add(pre_scan_work,
            detail::checked_add(24ULL * v + 16ULL * e, 4ULL * text_bytes));
        index_work_upper_ = detail::checked_add(base_work,
            detail::checked_add(signature_work,
                detail::checked_add(detail::checked_mul(sort_comparisons, kMaximumTokenBytes),
                    detail::checked_add(raw_edge_match_work,
                        detail::checked_add(transformed_match_work, transformed_initial_work)))));

        // Every array has a named logical slot count. The fixed 512 reserve
        // covers this object's and Receipt's fixed bookkeeping, all vector
        // control blocks, and the version/scope string headers and characters;
        // it is not an allocator-byte or vector-capacity estimate.
        const auto vertex_records = detail::checked_mul(
            kVertexClassScalarEntries + kClassRecordScalarEntries + kRawVertexRecordScalarEntries, v);
        // ClassEdge has two scalar fields, one string header, and one lex-index
        // entry (4 total); reserve one explicit slack entry per edge.
        const auto canonical_edges = detail::checked_mul(
            kClassEdgeScalarEntries + 1U + 1U + kClassEdgeUpperSlackEntries, e);
        // RawEdge has two scalar fields, one string header and one lex index.
        const auto raw_edges = detail::checked_mul(kRawEdgeScalarEntries + 1U + 1U, e);
        const auto suit_classes = detail::checked_mul(g, v);
        // MappedTransition has child, offset, three prefix cards and count (6);
        // reserve two explicit slack entries per transition.
        const auto mapped_transitions = detail::checked_mul(detail::checked_mul(g, e),
            kMappedTransitionScalarEntries + kMappedTransitionUpperSlackEntries);
        const auto retained_tokens = detail::checked_mul(2ULL, copied_edge_token_bytes);
        index_retained_upper_ = detail::checked_add(kFixedBookkeepingEntriesUpper,
            detail::checked_add(vertex_records,
                detail::checked_add(canonical_edges,
                    detail::checked_add(raw_edges,
                        detail::checked_add(suit_classes,
                            detail::checked_add(mapped_transitions, retained_tokens))))));
        retained_vertex_records_upper_ = vertex_records;
        retained_class_edges_upper_ = canonical_edges;
        retained_raw_edges_upper_ = raw_edges;
        retained_suit_classes_upper_ = suit_classes;
        retained_transitions_upper_ = mapped_transitions;
        retained_fixed_upper_ = kFixedBookkeepingEntriesUpper;
        const auto graph_scratch = detail::checked_add(10ULL * v, 5ULL * e);
        const auto suit_scratch = detail::checked_mul(2ULL * g, v);
        index_scratch_upper_ = detail::checked_add(256ULL,
            detail::checked_add(graph_scratch,
                detail::checked_add(suit_scratch, detail::checked_mul(2ULL, signature_bytes))));
        const auto combined_base_work = detail::checked_add(plan_->receipt().modeled_work_upper,
            detail::checked_add(index_work_upper_, limits_.external.work_upper));
        const auto base_entries = detail::checked_add(plan_->receipt().retained_entries_upper,
            detail::checked_add(index_retained_upper_, detail::checked_add(index_scratch_upper_, limits_.external.entries_upper)));
        const auto combined_work = detail::checked_add(combined_base_work, query_work_upper_);
        const auto combined_entries = detail::checked_entries(base_entries, query_entries_upper_);
        if (combined_work > limits_.max_combined_modeled_work)
            detail::fail(ErrorCode::work_limit, "combined Plan/history-index work reservation exceeds supplied ceiling");
        if (combined_entries > limits_.max_combined_entries)
            detail::fail(ErrorCode::storage_limit, "combined Plan/history-index retained-plus-scratch reservation exceeds supplied ceiling");
        reserved_combined_work_ = combined_base_work;
        reserved_combined_entries_ = base_entries;
        retained_token_bytes_upper_ = retained_tokens;
        signature_scratch_bytes_upper_ = signature_bytes;
    }

    [[nodiscard]] std::string edge_token(const Vertex& vertex, std::size_t index) const {
        if (vertex.kind == VertexKind::decision) return vertex.actions.at(index).token;
        if (vertex.kind == VertexKind::chance) {
            const auto& branch = vertex.branches.at(index);
            const char* prefix = vertex.street == Street::flop ? "flop@" :
                                 vertex.street == Street::turn ? "turn@" : "river@";
            return std::string(prefix) + branch.label;
        }
        detail::fail(ErrorCode::invalid_query, "terminal vertex has no history edge");
    }

    void build_topology_and_signatures() {
        const auto n = graph_->vertices.size();
        const auto root = graph_->root_id;
        std::vector<std::size_t> indegree(n, 0);
        std::vector<std::size_t> queue; queue.reserve(n);
        std::vector<std::size_t> topo; topo.reserve(n);
        for (std::size_t id = 0; id < n; ++id) {
            const auto& vertex = graph_->vertices[id];
            const auto degree = vertex.kind == VertexKind::decision ? vertex.children.size() :
                                vertex.kind == VertexKind::chance ? vertex.branches.size() : 0U;
            for (std::size_t i = 0; i < degree; ++i) {
                const auto child = vertex.kind == VertexKind::decision ? vertex.children[i] : vertex.branches[i].child;
                if (child >= n || indegree[child] == std::numeric_limits<std::size_t>::max())
                    detail::fail(ErrorCode::invalid_graph, "history-index graph edge or indegree is invalid");
                ++indegree[child];
            }
        }
        for (std::size_t id = 0; id < n; ++id) if (indegree[id] == 0) queue.push_back(id);
        for (std::size_t cursor = 0; cursor < queue.size(); ++cursor) {
            const auto id = queue[cursor]; topo.push_back(id);
            const auto& vertex = graph_->vertices[id];
            const auto degree = vertex.kind == VertexKind::decision ? vertex.children.size() :
                                vertex.kind == VertexKind::chance ? vertex.branches.size() : 0U;
            for (std::size_t i = 0; i < degree; ++i) {
                const auto child = vertex.kind == VertexKind::decision ? vertex.children[i] : vertex.branches[i].child;
                if (--indegree[child] == 0) queue.push_back(child);
            }
        }
        if (topo.size() != n) detail::fail(ErrorCode::graph_cycle, "history-index source graph is not acyclic");

        std::map<std::string, std::size_t> interned;
        vertex_class_.assign(n, 0);
        std::vector<std::size_t> representatives;
        representatives.reserve(n);
        for (auto topo_it = topo.rbegin(); topo_it != topo.rend(); ++topo_it) {
            const auto id = *topo_it;
            const auto& vertex = graph_->vertices[id];
            const auto degree = vertex.kind == VertexKind::decision ? vertex.children.size() :
                                vertex.kind == VertexKind::chance ? vertex.branches.size() : 0U;
            std::vector<std::size_t> child_classes; child_classes.reserve(degree);
            for (std::size_t i = 0; i < degree; ++i) {
                const auto child = vertex.kind == VertexKind::decision ? vertex.children[i] : vertex.branches[i].child;
                child_classes.push_back(vertex_class_[child]);
            }
            auto key = detail::vertex_signature(vertex, child_classes);
            const auto found = interned.find(key);
            if (found != interned.end()) vertex_class_[id] = found->second;
            else {
                const auto class_id = representatives.size();
                interned.emplace(std::move(key), class_id);
                representatives.push_back(id);
                vertex_class_[id] = class_id;
            }
        }
        classes_.resize(representatives.size());
        for (std::size_t c = 0; c < representatives.size(); ++c)
            classes_[c].representative_vertex = representatives[c];

        // Suit maps preserve exact signature classes, including duplicate raw
        // vertices. Every transformed source vertex must map to one identical
        // canonical continuation class.
        const auto group_count = plan_->group().size();
        class_map_.assign(group_count * classes_.size(), std::numeric_limits<std::size_t>::max());
        for (std::size_t g = 0; g < group_count; ++g) {
            const auto& mapping = plan_->group()[g];
            for (auto topo_it = topo.rbegin(); topo_it != topo.rend(); ++topo_it) {
                const auto id = *topo_it;
                const auto& vertex = graph_->vertices[id];
                const auto degree = vertex.kind == VertexKind::decision ? vertex.children.size() :
                                    vertex.kind == VertexKind::chance ? vertex.branches.size() : 0U;
                std::vector<std::size_t> transformed_children; transformed_children.reserve(degree);
                for (std::size_t i = 0; i < degree; ++i) {
                    const auto child = vertex.kind == VertexKind::decision ? vertex.children[i] : vertex.branches[i].child;
                    transformed_children.push_back(class_map_[g * classes_.size() + vertex_class_[child]]);
                    if (transformed_children.back() == std::numeric_limits<std::size_t>::max())
                        detail::fail(ErrorCode::invalid_graph, "transformed child class was not available bottom-up");
                }
                Vertex transformed = vertex;
                if (vertex.kind == VertexKind::chance) {
                    for (auto& branch : transformed.branches) {
                        const auto token = edge_token(vertex, static_cast<std::size_t>(&branch - transformed.branches.data()));
                        const auto mapped = detail::transform_reveal(token, mapping);
                        const auto at = mapped.find('@');
                        branch.label = mapped.substr(at + 1);
                    }
                }
                const auto key = detail::vertex_signature(transformed, transformed_children);
                const auto found = interned.find(key);
                if (found == interned.end())
                    detail::fail(ErrorCode::graph_not_invariant, "suit image lacks an exact canonical continuation class");
                const auto source_class = vertex_class_[id];
                auto& mapped_class = class_map_[g * classes_.size() + source_class];
                if (mapped_class == std::numeric_limits<std::size_t>::max()) mapped_class = found->second;
                else if (mapped_class != found->second)
                    detail::fail(ErrorCode::graph_not_invariant, "duplicate signature class has inconsistent suit image");
            }
            if (class_map_[g * classes_.size() + vertex_class_[root]] != vertex_class_[root])
                detail::fail(ErrorCode::graph_not_invariant, "suit map moved the fixed public root continuation");
        }

        // Counts over canonical continuation classes. Because exact signature
        // identity includes child classes and labels, duplicates share counts.
        std::vector<bool> seen_class(classes_.size(), false);
        for (auto it = topo.rbegin(); it != topo.rend(); ++it) {
            const auto c = vertex_class_[*it];
            if (seen_class[c]) continue;
            seen_class[c] = true;
            const auto& vertex = graph_->vertices[classes_[c].representative_vertex];
            const auto degree = vertex.kind == VertexKind::decision ? vertex.children.size() :
                                vertex.kind == VertexKind::chance ? vertex.branches.size() : 0U;
            std::uint64_t count = 1;
            for (std::size_t i = 0; i < degree; ++i) {
                const auto child = vertex.kind == VertexKind::decision ? vertex.children[i] : vertex.branches[i].child;
                count = checked_uadd(count, classes_[vertex_class_[child]].subtree_count);
            }
            classes_[c].subtree_count = count;
        }
        if (classes_[vertex_class_[root]].subtree_count != plan_->graph_census().logical_visits)
            detail::fail(ErrorCode::invalid_graph, "canonical subtree count differs from validated logical occurrence census");
    }

    void build_class_edges_and_offsets() {
        std::size_t total = 0;
        for (const auto& record : classes_) {
            const auto& vertex = graph_->vertices[record.representative_vertex];
            total = checked_sadd(total, vertex.kind == VertexKind::decision ? vertex.actions.size() :
                                 vertex.kind == VertexKind::chance ? vertex.branches.size() : 0U);
        }
        class_edges_.reserve(total);
        class_lex_order_.resize(total);
        for (std::size_t c = 0; c < classes_.size(); ++c) {
            auto& record = classes_[c];
            record.edge_begin = class_edges_.size();
            const auto& vertex = graph_->vertices[record.representative_vertex];
            record.edge_count = vertex.kind == VertexKind::decision ? vertex.actions.size() :
                                vertex.kind == VertexKind::chance ? vertex.branches.size() : 0U;
            for (std::size_t i = 0; i < record.edge_count; ++i) {
                const auto child = vertex.kind == VertexKind::decision ? vertex.children[i] : vertex.branches[i].child;
                auto token = edge_token(vertex, i);
                actual_token_bytes_ = checked_sadd(actual_token_bytes_, token.size());
                class_edges_.push_back({std::move(token), vertex_class_[child], 0});
                class_lex_order_[record.edge_begin + i] = record.edge_begin + i;
            }
            std::sort(class_lex_order_.begin() + static_cast<std::ptrdiff_t>(record.edge_begin),
                      class_lex_order_.begin() + static_cast<std::ptrdiff_t>(record.edge_begin + record.edge_count),
                      [this](std::size_t a, std::size_t b) { return class_edges_[a].token < class_edges_[b].token; });
            std::uint64_t offset = 1;
            for (std::size_t position = 0; position < record.edge_count; ++position) {
                const auto edge_id = class_lex_order_[record.edge_begin + position];
                class_edges_[edge_id].offset = offset;
                offset = checked_uadd(offset, classes_[class_edges_[edge_id].child_class].subtree_count);
            }
            if (offset != record.subtree_count)
                detail::fail(ErrorCode::invalid_graph, "lexical edge offsets do not tile the canonical subtree interval");
        }

        raw_vertex_edges_.resize(graph_->vertices.size());
        std::size_t raw_total = 0;
        for (const auto& vertex : graph_->vertices)
            raw_total = checked_sadd(raw_total, vertex.kind == VertexKind::decision ? vertex.actions.size() :
                                     vertex.kind == VertexKind::chance ? vertex.branches.size() : 0U);
        raw_edges_.reserve(raw_total);
        raw_lex_order_.resize(raw_total);
        for (std::size_t id = 0; id < graph_->vertices.size(); ++id) {
            auto& raw_record = raw_vertex_edges_[id];
            raw_record.edge_begin = raw_edges_.size();
            const auto& vertex = graph_->vertices[id];
            raw_record.edge_count = vertex.kind == VertexKind::decision ? vertex.actions.size() :
                                   vertex.kind == VertexKind::chance ? vertex.branches.size() : 0U;
            const auto class_id = vertex_class_[id];
            const auto& class_record = classes_[class_id];
            for (std::size_t i = 0; i < raw_record.edge_count; ++i) {
                const auto child = vertex.kind == VertexKind::decision ? vertex.children[i] : vertex.branches[i].child;
                auto token = edge_token(vertex, i);
                actual_token_bytes_ = checked_sadd(actual_token_bytes_, token.size());
                const auto canonical = find_class_edge(class_id, token);
                if (class_edges_[canonical].child_class != vertex_class_[child])
                    detail::fail(ErrorCode::invalid_graph, "raw duplicate continuation disagrees with canonical edge class");
                raw_edges_.push_back({std::move(token), child, canonical});
                raw_lex_order_[raw_record.edge_begin + i] = raw_record.edge_begin + i;
            }
            std::sort(raw_lex_order_.begin() + static_cast<std::ptrdiff_t>(raw_record.edge_begin),
                      raw_lex_order_.begin() + static_cast<std::ptrdiff_t>(raw_record.edge_begin + raw_record.edge_count),
                      [this](std::size_t a, std::size_t b) { return raw_edges_[a].token < raw_edges_[b].token; });
            (void)class_record;
        }
    }

    [[nodiscard]] std::size_t find_class_edge(std::size_t class_id, std::string_view token) const {
        const auto& record = classes_[class_id];
        const auto first = class_lex_order_.begin() + static_cast<std::ptrdiff_t>(record.edge_begin);
        const auto last = first + static_cast<std::ptrdiff_t>(record.edge_count);
        const auto found = std::lower_bound(first, last, token, [this](std::size_t edge_id, std::string_view value) {
            return class_edges_[edge_id].token < value;
        });
        if (found == last || class_edges_[*found].token != token)
            detail::fail(ErrorCode::invalid_query, "history token is absent from the canonical continuation");
        return *found;
    }

    void build_suit_transitions() {
        const auto group_count = plan_->group().size();
        mapped_transitions_.resize(group_count * class_edges_.size());
        for (std::size_t g = 0; g < group_count; ++g) {
            const auto& mapping = plan_->group()[g];
            for (std::size_t c = 0; c < classes_.size(); ++c) {
                const auto mapped_source = class_map_[g * classes_.size() + c];
                const auto& record = classes_[c];
                for (std::size_t local = 0; local < record.edge_count; ++local) {
                    const auto source_id = record.edge_begin + local;
                    const auto& source_edge = class_edges_[source_id];
                    const auto image_token = detail::transform_reveal(source_edge.token, mapping);
                    const auto target_id = find_class_edge(mapped_source, image_token);
                    const auto mapped_child = class_map_[g * classes_.size() + source_edge.child_class];
                    const auto& target_edge = class_edges_[target_id];
                    if (target_edge.child_class != mapped_child)
                        detail::fail(ErrorCode::graph_not_invariant, "transformed edge target differs from exact child signature image");
                    auto& transition = mapped_transitions_[g * class_edges_.size() + source_id];
                    transition.child_class = target_edge.child_class;
                    transition.offset = target_edge.offset;
                    transition.prefix = prefix_delta(image_token);
                }
            }
        }
    }

    [[nodiscard]] PrefixDelta prefix_delta(std::string_view token) const {
        PrefixDelta out;
        const auto at = token.find('@');
        if (at == std::string_view::npos) return out;
        const auto street = token.substr(0, at);
        const auto payload = token.substr(at + 1);
        if (street == "flop") {
            if (payload.size() != 6) detail::fail(ErrorCode::invalid_graph, "malformed indexed flop reveal");
            out.count = 3;
            for (std::size_t i = 0; i < 3; ++i) out.cards[i] = detail::parse_card(payload.substr(2 * i, 2));
            if (!(out.cards[0] < out.cards[1] && out.cards[1] < out.cards[2]))
                detail::fail(ErrorCode::invalid_graph, "indexed flop reveal is not canonical");
        } else if (street == "turn" || street == "river") {
            if (payload.size() != 2) detail::fail(ErrorCode::invalid_graph, "malformed indexed turn/river reveal");
            out.count = 1; out.cards[0] = detail::parse_card(payload);
        }
        return out;
    }

    [[nodiscard]] VisiblePrefixId initial_prefix(const SuitMap& mapping) const {
        VisiblePrefixId result;
        for (const auto& token : graph_->initial_history) {
            const auto mapped = detail::transform_reveal(token, mapping);
            const auto delta = prefix_delta(mapped);
            append_prefix(result, delta);
        }
        return result;
    }
    static void append_prefix(VisiblePrefixId& prefix, const PrefixDelta& delta) {
        if (delta.count == 0) return;
        if (delta.count == 3) {
            if (prefix.size != 0) detail::fail(ErrorCode::invalid_query, "flop prefix does not start an empty board");
            for (std::size_t i = 0; i < 3; ++i) prefix.cards[i] = delta.cards[i];
            prefix.size = 3; return;
        }
        if (delta.count != 1 || (prefix.size != 3 && prefix.size != 4) || prefix.size >= 5)
            detail::fail(ErrorCode::invalid_query, "turn/river prefix reveal is out of order");
        for (std::size_t i = 0; i < prefix.size; ++i)
            if (prefix.cards[i] == delta.cards[0]) detail::fail(ErrorCode::invalid_query, "duplicate card in visible prefix");
        prefix.cards[prefix.size++] = delta.cards[0];
    }

    [[nodiscard]] Cursor advance_token_unreserved(const Cursor& cursor, std::string_view token) const {
        validate_cursor(cursor);
        const auto raw_id = cursor.raw_vertex_;
        const auto& raw_record = raw_vertex_edges_[raw_id];
        const auto first = raw_lex_order_.begin() + static_cast<std::ptrdiff_t>(raw_record.edge_begin);
        const auto last = first + static_cast<std::ptrdiff_t>(raw_record.edge_count);
        const auto found = std::lower_bound(first, last, token, [this](std::size_t edge_id, std::string_view value) {
            return raw_edges_[edge_id].token < value;
        });
        if (found == last || raw_edges_[*found].token != token)
            detail::fail(ErrorCode::invalid_query, "history token does not identify an edge at the current continuation");
        const auto raw_edge_id = *found;
        return advance_canonical_edge(cursor, raw_edges_[raw_edge_id].canonical_edge,
                                      raw_edges_[raw_edge_id].child_vertex);
    }

    [[nodiscard]] Cursor advance_canonical_edge(const Cursor& cursor, std::size_t canonical_edge,
                                                std::size_t raw_child) const {
        validate_cursor(cursor);
        const auto source_class = cursor.images_[0].continuation_class;
        const auto& record = classes_[source_class];
        if (canonical_edge < record.edge_begin || canonical_edge >= record.edge_begin + record.edge_count)
            detail::fail(ErrorCode::invalid_query, "history edge does not belong to current continuation class");
        Cursor result = cursor;
        result.raw_vertex_ = raw_child;
        write_next_images(std::span<const CursorImage>(cursor.images_.data(), cursor.image_count_),
                          std::span<CursorImage>(result.images_.data(), cursor.image_count_), canonical_edge);
        return result;
    }

    void write_next_images(std::span<const CursorImage> previous, std::span<CursorImage> next,
                           std::size_t canonical_edge) const {
        if (previous.size() != plan_->group().size() || next.size() != previous.size() || previous.empty())
            detail::fail(ErrorCode::invalid_query, "history image span mismatch");
        const auto source_class = previous[0].continuation_class;
        const auto& record = classes_[source_class];
        if (canonical_edge < record.edge_begin || canonical_edge >= record.edge_begin + record.edge_count)
            detail::fail(ErrorCode::invalid_query, "history edge does not belong to continuation");
        const auto& actual = class_edges_[canonical_edge];
        next[0] = previous[0];
        next[0].continuation_class = actual.child_class;
        next[0].ordinal = checked_uadd(previous[0].ordinal, actual.offset);
        append_prefix(next[0].visible_prefix, prefix_delta(actual.token));
        for (std::size_t g = 1; g < previous.size(); ++g) {
            if (previous[g].continuation_class != class_map_[g * classes_.size() + source_class])
                detail::fail(ErrorCode::invalid_query, "cursor transformed continuation is inconsistent with its owner");
            const auto& transition = mapped_transitions_[g * class_edges_.size() + canonical_edge];
            next[g] = previous[g];
            next[g].continuation_class = transition.child_class;
            next[g].ordinal = checked_uadd(previous[g].ordinal, transition.offset);
            append_prefix(next[g].visible_prefix, transition.prefix);
        }
    }

    void validate_cursor(const Cursor& cursor) const {
        if (cursor.owner_ != this || cursor.generation_ != generation_ ||
            cursor.image_count_ != plan_->group().size() || cursor.raw_vertex_ >= graph_->vertices.size())
            detail::fail(ErrorCode::invalid_query, "history cursor is forged, stale, or owned by another index");
        const auto actual_class = vertex_class_[cursor.raw_vertex_];
        if (cursor.images_[0].continuation_class != actual_class)
            detail::fail(ErrorCode::invalid_query, "history cursor raw vertex/class binding is invalid");
    }

    void reserve_query_work(std::uint64_t amount) const {
        auto previous = query_work_used_.load(std::memory_order_relaxed);
        while (true) {
            const auto next = detail::checked_add(previous, amount);
            if (limits_.query_schedule && next > query_work_upper_)
                detail::fail(ErrorCode::work_limit, "index query work exceeds its preflight schedule forecast");
            if (detail::checked_add(reserved_combined_work_, next) > limits_.max_combined_modeled_work)
                detail::fail(ErrorCode::work_limit, "history-index query work exceeds combined admitted ceiling");
            if (query_work_used_.compare_exchange_weak(previous, next,
                    std::memory_order_relaxed, std::memory_order_relaxed)) return;
        }
    }
    void reserve_query_entries(std::size_t amount) const {
        auto previous = query_entries_used_.load(std::memory_order_relaxed);
        while (true) {
            const auto next = detail::checked_entries(previous, amount);
            if (limits_.query_schedule && next > query_entries_upper_)
                detail::fail(ErrorCode::storage_limit, "index query entries exceed their preflight schedule forecast");
            if (detail::checked_entries(reserved_combined_entries_, next) > limits_.max_combined_entries)
                detail::fail(ErrorCode::storage_limit, "history-index inverse-query scratch exceeds combined admitted ceiling");
            if (query_entries_used_.compare_exchange_weak(previous, next,
                    std::memory_order_relaxed, std::memory_order_relaxed)) return;
        }
    }

    void finalize_receipt() {
        receipt_.graph_vertices = graph_->vertices.size();
        receipt_.graph_edges = plan_->graph_census().edges;
        receipt_.continuation_classes = classes_.size();
        receipt_.suit_maps = plan_->group().size();
        receipt_.logical_occurrences = plan_->graph_census().logical_visits;
        receipt_.class_edge_entries = class_edges_.size();
        receipt_.raw_edge_entries = raw_edges_.size();
        receipt_.suit_class_entries = class_map_.size();
        receipt_.transformed_transition_entries = mapped_transitions_.size();
        receipt_.ordinal_entries = classes_.size();
        receipt_.retained_token_bytes = actual_token_bytes_;
        receipt_.retained_token_bytes_upper = retained_token_bytes_upper_;
        receipt_.index_fixed_bookkeeping_entries_upper = retained_fixed_upper_;
        receipt_.index_vertex_record_entries_upper = retained_vertex_records_upper_;
        receipt_.index_class_edge_entries_upper = retained_class_edges_upper_;
        receipt_.index_raw_edge_entries_upper = retained_raw_edges_upper_;
        receipt_.index_suit_class_entries_upper = retained_suit_classes_upper_;
        receipt_.index_transformed_transition_entries_upper = retained_transitions_upper_;
        receipt_.index_token_bytes_entries_upper = retained_token_bytes_upper_;
        receipt_.index_fixed_bookkeeping_entries_actual = kFixedBookkeepingEntriesUpper;
        receipt_.vertex_class_entries_actual = vertex_class_.size();
        receipt_.class_record_entries_actual = detail::checked_mul(kClassRecordScalarEntries, classes_.size());
        receipt_.raw_vertex_record_entries_actual = detail::checked_mul(
            kRawVertexRecordScalarEntries, raw_vertex_edges_.size());
        receipt_.class_edge_entries_actual = detail::checked_mul(kClassEdgeScalarEntries, class_edges_.size());
        receipt_.class_edge_string_headers_actual = class_edges_.size();
        receipt_.class_lex_order_entries_actual = class_lex_order_.size();
        receipt_.raw_edge_entries_actual = detail::checked_mul(kRawEdgeScalarEntries, raw_edges_.size());
        receipt_.raw_edge_string_headers_actual = raw_edges_.size();
        receipt_.raw_lex_order_entries_actual = raw_lex_order_.size();
        receipt_.suit_class_entries_actual = class_map_.size();
        receipt_.transformed_transition_entries_actual = detail::checked_mul(
            kMappedTransitionScalarEntries, mapped_transitions_.size());
        receipt_.retained_token_bytes_actual = actual_token_bytes_;
        auto actual_entries = kFixedBookkeepingEntriesUpper;
        actual_entries = detail::checked_add(actual_entries, receipt_.vertex_class_entries_actual);
        actual_entries = detail::checked_add(actual_entries, receipt_.class_record_entries_actual);
        actual_entries = detail::checked_add(actual_entries, receipt_.raw_vertex_record_entries_actual);
        actual_entries = detail::checked_add(actual_entries, receipt_.class_edge_entries_actual);
        actual_entries = detail::checked_add(actual_entries, receipt_.class_edge_string_headers_actual);
        actual_entries = detail::checked_add(actual_entries, receipt_.class_lex_order_entries_actual);
        actual_entries = detail::checked_add(actual_entries, receipt_.raw_edge_entries_actual);
        actual_entries = detail::checked_add(actual_entries, receipt_.raw_edge_string_headers_actual);
        actual_entries = detail::checked_add(actual_entries, receipt_.raw_lex_order_entries_actual);
        actual_entries = detail::checked_add(actual_entries, receipt_.suit_class_entries_actual);
        actual_entries = detail::checked_add(actual_entries, receipt_.transformed_transition_entries_actual);
        actual_entries = detail::checked_add(actual_entries, receipt_.retained_token_bytes_actual);
        if (actual_entries > index_retained_upper_)
            detail::fail(ErrorCode::invalid_graph, "actual history-index retained ledger exceeds its preflight reservation");
        receipt_.index_retained_entries_actual = actual_entries;
        receipt_.signature_scratch_bytes_upper = signature_scratch_bytes_upper_;
        receipt_.plan_modeled_work_upper = plan_->receipt().modeled_work_upper;
        receipt_.index_modeled_work_upper = index_work_upper_;
        receipt_.combined_base_modeled_work_upper = reserved_combined_work_;
        receipt_.combined_modeled_work_upper = detail::checked_add(reserved_combined_work_, query_work_upper_);
        receipt_.external_work_upper = limits_.external.work_upper;
        receipt_.external_entries_upper = limits_.external.entries_upper;
        receipt_.query_schedule_declared = limits_.query_schedule.has_value();
        receipt_.query_work_upper = query_work_upper_;
        receipt_.query_cumulative_entries_upper = query_entries_upper_;
        receipt_.modeled_work_limit = limits_.max_combined_modeled_work;
        receipt_.plan_retained_entries_upper = plan_->receipt().retained_entries_upper;
        receipt_.index_retained_entries_upper = index_retained_upper_;
        receipt_.index_scratch_entries_upper = index_scratch_upper_;
        receipt_.combined_base_peak_entries_upper = reserved_combined_entries_;
        receipt_.combined_peak_entries_upper = detail::checked_entries(reserved_combined_entries_, query_entries_upper_);
        receipt_.retained_entry_limit = limits_.max_combined_entries;
        receipt_.max_query_depth = plan_->graph_census().maximum_depth;
        if (limits_.query_schedule || limits_.external.work_upper || limits_.external.entries_upper)
            receipt_.version = "native-exact-public-history-index-scheduled-v2";
    }

    const Plan* plan_ = nullptr; // Plan is required to outlive this index.
    const Graph* graph_ = nullptr;
    Limits limits_{};
    std::uint64_t generation_ = 0;
    std::size_t maximum_degree_ = 0;
    std::vector<std::size_t> vertex_class_;
    std::vector<ClassRecord> classes_;
    std::vector<std::size_t> class_map_;
    std::vector<ClassEdge> class_edges_;
    std::vector<std::size_t> class_lex_order_;
    std::vector<RawVertexRecord> raw_vertex_edges_;
    std::vector<RawEdge> raw_edges_;
    std::vector<std::size_t> raw_lex_order_;
    std::vector<MappedTransition> mapped_transitions_;
    std::size_t retained_token_bytes_upper_ = 0;
    std::size_t actual_token_bytes_ = 0;
    std::size_t signature_scratch_bytes_upper_ = 0;
    std::uint64_t index_work_upper_ = 0;
    std::size_t index_retained_upper_ = 0;
    std::size_t retained_fixed_upper_ = 0;
    std::size_t retained_vertex_records_upper_ = 0;
    std::size_t retained_class_edges_upper_ = 0;
    std::size_t retained_raw_edges_upper_ = 0;
    std::size_t retained_suit_classes_upper_ = 0;
    std::size_t retained_transitions_upper_ = 0;
    std::size_t index_scratch_upper_ = 0;
    std::uint64_t reserved_combined_work_ = 0;
    std::size_t reserved_combined_entries_ = 0;
    std::uint64_t query_work_upper_ = 0;
    std::size_t query_entries_upper_ = 0;
    mutable std::atomic<std::uint64_t> query_work_used_{0};
    mutable std::atomic<std::size_t> query_entries_used_{0};
    mutable std::atomic<std::uint64_t> root_calls_used_{0};
    mutable std::atomic<std::uint64_t> edge_calls_used_{0};
    mutable std::atomic<std::uint64_t> route_calls_used_{0};
    mutable std::atomic<std::uint64_t> route_tokens_used_{0};
    Receipt receipt_{};
    inline static std::atomic<std::uint64_t> generation_counter_{1};
};


// A workspace and its Index/Plan must outlive every Lease and FrameView. This
// internal interface is single-traversal and intentionally nonmovable.
inline constexpr std::size_t kFrameViewLogicalEntries = 3;
inline constexpr std::size_t kFrameLeaseLogicalEntries = 3;
inline constexpr std::size_t kFrameHeaderLogicalEntries = 3;
inline constexpr std::size_t kWorkspaceFixedLogicalEntries = 64;
struct WorkspaceCounts { std::uint64_t activations = 0, released_frames = 0, release_calls = 0; };
struct WorkspaceReservation {
    std::size_t frame_count = 0, image_slots = 0, header_entries = 0, retained_entries_upper = 0;
    std::uint64_t setup_work_upper = 0;
};

class FrameView final {
public:
    [[nodiscard]] bool belongs_to(const TraversalWorkspace& workspace) const noexcept { return owner_ == &workspace; }
    [[nodiscard]] std::uint64_t ordinal() const;
    [[nodiscard]] std::size_t image_count() const;
    [[nodiscard]] std::uint64_t image_ordinal(std::size_t map_index) const;
    [[nodiscard]] VisiblePrefixId visible_prefix(std::size_t map_index = 0) const;
private:
    friend class TraversalWorkspace;
    friend class HistoryIndex;
    FrameView(const TraversalWorkspace* owner, std::size_t slot, std::uint64_t epoch)
        : owner_(owner), slot_(slot), epoch_(epoch) {}
    const TraversalWorkspace* owner_;
    std::size_t slot_;
    std::uint64_t epoch_;
};

class TraversalWorkspace final {
    friend class FrameView;
    friend class HistoryIndex;
    struct Header { std::size_t raw_vertex = 0; std::uint64_t epoch = 0; bool active = false; };
public:
    class Lease final {
        friend class TraversalWorkspace;
    public:
        Lease(const Lease&) = delete;
        Lease& operator=(const Lease&) = delete;
        Lease(Lease&& other) noexcept : owner_(other.owner_), slot_(other.slot_), epoch_(other.epoch_) { other.owner_ = nullptr; }
        Lease& operator=(Lease&&) = delete;
        ~Lease() noexcept { if (owner_) owner_->release(slot_, epoch_); }
        [[nodiscard]] FrameView view() const {
            if (!owner_) detail::fail(ErrorCode::invalid_query, "moved-from frame lease");
            FrameView v(owner_, slot_, epoch_); owner_->validate(v); return v;
        }
    private:
        Lease(TraversalWorkspace* owner, std::size_t slot, std::uint64_t epoch)
            : owner_(owner), slot_(slot), epoch_(epoch) {}
        TraversalWorkspace* owner_;
        std::size_t slot_;
        std::uint64_t epoch_;
    };

    [[nodiscard]] static WorkspaceReservation reservation(std::size_t max_depth, std::size_t group_size) {
        if (group_size == 0 || group_size > kMaximumSuitMaps)
            detail::fail(ErrorCode::invalid_limits, "workspace suit-map count invalid");
        // The fixed global entry ceiling also keeps all products representable
        // on 32-bit size_t before any vector allocation.
        if (max_depth >= kMaximumRetainedEntries)
            detail::fail(ErrorCode::storage_limit, "workspace depth exceeds entry ceiling");
        WorkspaceReservation r;
        r.frame_count = detail::checked_entries(max_depth, 1);
        r.image_slots = detail::checked_mul(r.frame_count, group_size);
        r.header_entries = detail::checked_mul(r.frame_count, kFrameHeaderLogicalEntries);
        r.retained_entries_upper = detail::checked_entries(kWorkspaceFixedLogicalEntries, detail::checked_entries(r.header_entries, detail::checked_mul(r.image_slots, 8)));
        r.setup_work_upper = detail::checked_add(kWorkspaceFixedLogicalEntries, detail::checked_add(r.header_entries, detail::checked_mul(r.image_slots, 8)));
        return r;
    }
    explicit TraversalWorkspace(const HistoryIndex& index, std::size_t max_depth,
                                std::uint64_t max_work = kMaximumModeledWork,
                                std::size_t max_entries = kMaximumRetainedEntries)
        : index_(&index), group_size_(index.suit_map_count()), reservation_(reservation(max_depth, group_size_)) {
        if (max_work == 0 || max_work > kMaximumModeledWork || max_entries == 0 || max_entries > kMaximumRetainedEntries)
            detail::fail(ErrorCode::invalid_limits, "workspace limits invalid");
        if (max_depth < index.plan_->graph_census().maximum_depth)
            detail::fail(ErrorCode::invalid_limits, "workspace depth below admitted graph depth");
        if (reservation_.setup_work_upper > max_work) detail::fail(ErrorCode::work_limit, "workspace setup work exceeds limit");
        if (reservation_.retained_entries_upper > max_entries) detail::fail(ErrorCode::storage_limit, "workspace entries exceed limit");
        headers_.resize(reservation_.frame_count);
        images_.resize(reservation_.image_slots);
    }
    TraversalWorkspace(const TraversalWorkspace&) = delete;
    TraversalWorkspace& operator=(const TraversalWorkspace&) = delete;
    TraversalWorkspace(TraversalWorkspace&&) = delete;
    TraversalWorkspace& operator=(TraversalWorkspace&&) = delete;
    [[nodiscard]] const WorkspaceReservation& receipt() const noexcept { return reservation_; }
    [[nodiscard]] const HistoryIndex& index() const noexcept { return *index_; }
    [[nodiscard]] WorkspaceCounts counts() const noexcept { return counts_; }
    [[nodiscard]] std::size_t active_frames() const noexcept { return active_count_; }
    [[nodiscard]] Lease root() {
        if (headers_[0].active) detail::fail(ErrorCode::invalid_query, "workspace root already active");
        ensure_epoch(0);
        index_->reserve_scheduled(index_->root_calls_used_, 1, index_->limits_.query_schedule ? index_->limits_.query_schedule->root_cursor_calls : 0);
        index_->reserve_query_work(index_->root_work_per_call());
        index_->reserve_query_entries(index_->root_entries_per_call());
        const auto root_class = index_->vertex_class_[index_->graph_->root_id];
        auto target = image_span(0);
        for (std::size_t g = 0; g < group_size_; ++g) {
            const auto cls = index_->class_map_[g * index_->classes_.size() + root_class];
            if (cls != root_class) detail::fail(ErrorCode::graph_not_invariant, "workspace suit image moved root");
            target[g] = CursorImage{}; target[g].continuation_class = cls;
            target[g].visible_prefix = index_->initial_prefix(index_->plan_->group()[g]);
        }
        return activate(0, index_->graph_->root_id);
    }
    [[nodiscard]] Lease advance_action(const FrameView& parent, std::size_t edge) { return advance(parent, edge, VertexKind::decision); }
    [[nodiscard]] Lease advance_reveal(const FrameView& parent, std::size_t edge) { return advance(parent, edge, VertexKind::chance); }
private:
    [[nodiscard]] std::span<CursorImage> image_span(std::size_t slot) { return {images_.data() + slot * group_size_, group_size_}; }
    [[nodiscard]] std::span<const CursorImage> image_span(std::size_t slot) const { return {images_.data() + slot * group_size_, group_size_}; }
    void validate(const FrameView& v) const {
        if (v.owner_ != this || v.slot_ >= headers_.size() || !headers_[v.slot_].active ||
            headers_[v.slot_].epoch != v.epoch_ || headers_[v.slot_].raw_vertex >= index_->graph_->vertices.size() ||
            image_span(v.slot_)[0].continuation_class != index_->vertex_class_[headers_[v.slot_].raw_vertex])
            detail::fail(ErrorCode::invalid_query, "workspace frame is stale or foreign");
    }
    void ensure_epoch(std::size_t slot) const {
        if (headers_[slot].epoch == std::numeric_limits<std::uint64_t>::max())
            detail::fail(ErrorCode::invalid_query, "workspace epoch exhausted");
    }
    [[nodiscard]] Lease activate(std::size_t slot, std::size_t raw_vertex) {
        auto& h = headers_[slot]; ++h.epoch; h.raw_vertex = raw_vertex; h.active = true;
        active_count_ = slot + 1; ++counts_.activations;
        return Lease(this, slot, h.epoch);
    }
    void release(std::size_t slot, std::uint64_t epoch) noexcept {
        ++counts_.release_calls;
        if (slot >= headers_.size() || !headers_[slot].active || headers_[slot].epoch != epoch) return;
        while (active_count_ > slot) { headers_[--active_count_].active = false; ++counts_.released_frames; }
    }
    [[nodiscard]] Lease advance(const FrameView& parent, std::size_t edge, VertexKind expected) {
        validate(parent);
        const auto slot = parent.slot_ + 1;
        if (slot >= headers_.size() || headers_[slot].active) detail::fail(ErrorCode::invalid_query, "workspace child slot unavailable");
        const auto raw = headers_[parent.slot_].raw_vertex;
        const auto& vertex = index_->graph_->vertices[raw];
        if (vertex.kind != expected) detail::fail(ErrorCode::invalid_query, "workspace edge vertex kind invalid");
        const auto count = expected == VertexKind::decision ? vertex.actions.size() : vertex.branches.size();
        if (edge >= count) detail::fail(ErrorCode::invalid_query, "workspace edge outside menu");
        ensure_epoch(slot);
        const auto raw_edge = index_->raw_vertex_edges_[raw].edge_begin + edge;
        index_->reserve_scheduled(index_->edge_calls_used_, 1, index_->limits_.query_schedule ? index_->limits_.query_schedule->edge_advance_calls : 0);
        index_->reserve_query_work(index_->edge_work_per_call());
        const auto& item = index_->raw_edges_[raw_edge];
        index_->write_next_images(image_span(parent.slot_), image_span(slot), item.canonical_edge);
        return activate(slot, item.child_vertex);
    }
    const HistoryIndex* index_;
    std::size_t group_size_;
    WorkspaceReservation reservation_;
    std::size_t active_count_ = 0;
    WorkspaceCounts counts_{};
    std::vector<Header> headers_;
    std::vector<CursorImage> images_;
};

inline std::size_t FrameView::image_count() const { owner_->validate(*this); return owner_->group_size_; }
inline std::uint64_t FrameView::ordinal() const { return image_ordinal(0); }
inline std::uint64_t FrameView::image_ordinal(std::size_t g) const {
    owner_->validate(*this); if (g >= owner_->group_size_) detail::fail(ErrorCode::invalid_query, "frame suit-map index invalid");
    return owner_->image_span(slot_)[g].ordinal;
}
inline VisiblePrefixId FrameView::visible_prefix(std::size_t g) const {
    owner_->validate(*this); if (g >= owner_->group_size_) detail::fail(ErrorCode::invalid_query, "frame prefix index invalid");
    return owner_->image_span(slot_)[g].visible_prefix;
}
inline const Vertex& HistoryIndex::vertex_at(const FrameView& view) const {
    if (!view.owner_ || view.owner_->index_ != this) detail::fail(ErrorCode::invalid_query, "foreign frame index");
    view.owner_->validate(view); return graph_->vertices[view.owner_->headers_[view.slot_].raw_vertex];
}

} // namespace openpoker::exact_public_history_index
