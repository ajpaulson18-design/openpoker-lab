#pragma once

// Bounded numeric Q routing over the existing public-history continuation
// index. Q indices, offsets, menus and masks remain owned by the immutable Plan.

#include "exact_public_history_index.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <span>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace openpoker::exact_indexed_routing {

namespace graph = exact_public_graph;
namespace history_index = exact_public_history_index;

inline constexpr std::size_t kMaximumSuitMaps = history_index::kMaximumSuitMaps;
inline constexpr std::size_t kRouterFixedEntriesUpper = 512;
inline constexpr std::size_t kNumericKeyScalarEntries = 3;
inline constexpr std::size_t kNumericQEntryScalarEntries = 4;
inline constexpr std::size_t kCursorImageLogicalEntries = 8;
inline constexpr std::size_t kCursorFixedLogicalEntries = 4;
inline constexpr std::size_t kPrefixSupportViewLogicalEntries = 7;
inline constexpr std::size_t kMaximumImageViewAndKeyEntries =
    kMaximumSuitMaps * (kPrefixSupportViewLogicalEntries + kNumericKeyScalarEntries);
inline constexpr std::size_t kMaximumCursorLogicalEntries =
    kCursorFixedLogicalEntries + kMaximumSuitMaps * kCursorImageLogicalEntries;

struct NumericRowKey {
    std::uint8_t actor = 0;
    std::size_t original_hand_index = 0;
    std::uint64_t public_path_ordinal = 0;
    friend bool operator==(const NumericRowKey&, const NumericRowKey&) = default;
    friend bool operator<(const NumericRowKey& left, const NumericRowKey& right) noexcept {
        return std::tie(left.actor, left.original_hand_index, left.public_path_ordinal) <
               std::tie(right.actor, right.original_hand_index, right.public_path_ordinal);
    }
};

struct RoutingSchedule {
    std::uint64_t complete_training_runs = 1;
    std::uint64_t additional_full_shadow_walks = 0;
};

struct WholeLimits {
    std::uint64_t modeled_work = graph::kMaximumModeledWork;
    std::size_t logical_entries = graph::kMaximumRetainedEntries;
};

struct NumericQEntry {
    NumericRowKey key{};
    std::size_t original_q = 0;
};

struct Receipt {
    std::string version = "native-exact-indexed-routing-v1";
    std::size_t original_q_rows = 0;
    std::size_t numeric_map_entries_upper = 0;
    std::size_t numeric_map_entries_actual = 0;
    std::size_t numeric_map_entry_fields = kNumericQEntryScalarEntries;
    std::size_t r_lookup_entries = 0;
    bool original_q_histories_retained = true;
    std::size_t router_fixed_entries_upper = kRouterFixedEntriesUpper;
    std::size_t router_retained_entries_upper = 0;
    std::size_t router_retained_entries_actual = 0;
    std::size_t router_setup_scratch_entries_upper = 0;
    std::size_t router_query_scratch_entries_upper = 0;
    std::size_t router_prefix_view_logical_entries = kPrefixSupportViewLogicalEntries;
    std::size_t router_scratch_entries_upper = 0;
    std::size_t caller_reservation_entries_upper = 0;
    std::size_t cursor_logical_entries_upper = kMaximumCursorLogicalEntries;
    std::uint64_t history_route_calls = 0;
    std::uint64_t history_route_tokens_upper = 0;
    std::uint64_t history_route_calls_actual = 0;
    std::uint64_t history_route_tokens_actual = 0;
    std::uint64_t root_cursor_calls = 0;
    std::uint64_t root_cursor_calls_actual = 0;
    std::uint64_t edge_advance_calls = 0;
    std::uint64_t edge_advance_calls_actual = 0;
    std::uint64_t decision_lookup_calls_upper = 0;
    std::uint64_t prefix_lookup_calls_upper = 0;
    std::uint64_t decision_lookup_calls_actual = 0;
    std::uint64_t prefix_lookup_calls_actual = 0;
    std::uint64_t router_setup_work_upper = 0;
    std::uint64_t router_setup_work_actual = 0;
    std::uint64_t router_query_work_upper = 0;
    std::uint64_t router_query_work_actual = 0;
    std::uint64_t index_query_work_upper = 0;
    std::uint64_t index_query_work_actual = 0;
    std::size_t index_query_entries_upper = 0;
    std::size_t index_query_entries_actual = 0;
    std::uint64_t router_work_upper = 0;
    std::uint64_t caller_reservation_work_upper = 0;
    std::uint64_t combined_modeled_work_upper = 0;
    std::size_t combined_logical_entries_upper = 0;
    std::uint64_t work_limit = 0;
    std::size_t logical_entry_limit = 0;
    std::string scope =
        "Sorted numeric Q route over the existing Plan; logical fields/comparisons, not allocator bytes, vector capacity, CPU or RSS. Plan outlives router; traversal owner reserves live frames and caller state.";
};

class IndexedRouting final {
public:
    using Cursor = history_index::HistoryIndex::Cursor;

    explicit IndexedRouting(const graph::Plan& plan, RoutingSchedule schedule = {},
                            WholeLimits whole = {}, history_index::ExternalReservation caller = {})
        : IndexedRouting(plan, prepare(plan, schedule, whole, caller)) {}

    IndexedRouting(const IndexedRouting&) = delete;
    IndexedRouting& operator=(const IndexedRouting&) = delete;
    IndexedRouting(IndexedRouting&&) = delete;
    IndexedRouting& operator=(IndexedRouting&&) = delete;

    [[nodiscard]] Cursor root_cursor() const {
        reserve_call(root_calls_used_, 1, receipt_.root_cursor_calls,
                     "indexed root cursor exceeds the declared whole-call schedule");
        return index_.root_cursor();
    }

    [[nodiscard]] Cursor advance_action(const Cursor& cursor, std::size_t original_menu_index) const {
        reserve_call(edge_calls_used_, 1, receipt_.edge_advance_calls,
                     "indexed action edge exceeds the declared whole-call schedule");
        return index_.advance_action(cursor, original_menu_index);
    }

    [[nodiscard]] Cursor advance_reveal(const Cursor& cursor, std::size_t original_branch_index) const {
        reserve_call(edge_calls_used_, 1, receipt_.edge_advance_calls,
                     "indexed reveal edge exceeds the declared whole-call schedule");
        return index_.advance_reveal(cursor, original_branch_index);
    }

    [[nodiscard]] std::vector<std::optional<graph::RowLocation>> locate_decision_rows(
        const Cursor& cursor, std::uint8_t actor, std::span<const graph::Action> complete_menu) const {
        reserve_call(decision_calls_used_, 1, receipt_.decision_lookup_calls_upper,
                     "indexed decision lookup exceeds the declared whole-call schedule");
        charge_query_work(decision_query_work_upper_);

        const auto& vertex = index_.vertex_at(cursor);
        if (vertex.kind != graph::VertexKind::decision || actor > 1 || vertex.actor != actor ||
            vertex.actions.size() != complete_menu.size() ||
            !std::equal(vertex.actions.begin(), vertex.actions.end(), complete_menu.begin(), complete_menu.end()))
            graph::detail::fail(graph::ErrorCode::invalid_query,
                                "indexed decision actor, vertex kind or complete ordered menu mismatch");

        const auto group_size = plan_->group().size();
        const auto hand_count = plan_->hand_counts()[actor];
        if (group_size == 0 || group_size > kMaximumSuitMaps)
            graph::detail::fail(graph::ErrorCode::group_invalid, "indexed router suit-map count is outside its fixed bound");

        std::array<graph::PrefixSupportView, kMaximumSuitMaps> views{};
        for (std::size_t g = 0; g < group_size; ++g) {
            const auto prefix = cursor.visible_prefix(g);
            views[g] = plan_->prefix_support(std::span<const graph::Card>(prefix.cards.data(), prefix.size));
        }

        std::vector<std::optional<graph::RowLocation>> result(hand_count);
        std::array<NumericRowKey, kMaximumSuitMaps> image_keys{};
        for (const auto hand : views[0].hands[actor]) {
            if (hand >= hand_count)
                graph::detail::fail(graph::ErrorCode::invalid_query, "typed support returned an out-of-range hand index");
            const NumericRowKey original{actor, hand, cursor.ordinal()};
            for (std::size_t g = 0; g < group_size; ++g) {
                const auto mapped = plan_->mapped_hand_index(actor, g, hand);
                const auto support = views[g].hands[actor];
                if (!std::binary_search(support.begin(), support.end(), mapped))
                    graph::detail::fail(graph::ErrorCode::group_not_closed,
                                        "typed suit-image prefix lacks support for the mapped hand");
                image_keys[g] = {actor, mapped, cursor.image_ordinal(g)};
            }
            const auto image_count = sort_unique_keys(image_keys, group_size);
            auto first = image_keys.begin();
            const auto unique_end = first + static_cast<std::ptrdiff_t>(image_count);
            if (image_count == 0)
                graph::detail::fail(graph::ErrorCode::group_not_closed,
                                    "numeric suit-image orbit is empty");

            const auto found = std::lower_bound(numeric_q_.begin(), numeric_q_.end(), *first,
                [](const NumericQEntry& entry, const NumericRowKey& key) { return entry.key < key; });
            if (found == numeric_q_.end() || !(found->key == *first))
                graph::detail::fail(graph::ErrorCode::unsupported_row,
                                    "canonical numeric Q key is absent from the admitted map");
            if (found->original_q >= plan_->rows().size())
                graph::detail::fail(graph::ErrorCode::invalid_graph, "numeric Q map points outside original Q rows");
            const auto& row = plan_->rows()[found->original_q];
            const auto expected_mask = image_count == 32 ? 0xffffffffU : ((1U << image_count) - 1U);
            if (row.orbit_size != image_count || row.size != image_count ||
                row.expected_mask != expected_mask || row.menu.size() != complete_menu.size() ||
                !std::equal(row.menu.begin(), row.menu.end(), complete_menu.begin(), complete_menu.end()))
                graph::detail::fail(graph::ErrorCode::unsupported_row,
                                    "numeric Q orbit, mask or complete ordered menu differs from the original row");
            const auto member = std::lower_bound(first, unique_end, original);
            if (member == unique_end || !(*member == original))
                graph::detail::fail(graph::ErrorCode::group_not_closed,
                                    "original numeric Q member is absent from its sorted image orbit");
            const auto member_index = static_cast<std::size_t>(member - first);
            result[hand] = graph::RowLocation{found->original_q, row.offset,
                                               static_cast<std::uint32_t>(1U << member_index)};
        }
        return result;
    }

    [[nodiscard]] const std::vector<std::size_t>& prefix_board_indexes(const Cursor& cursor) const {
        reserve_call(prefix_calls_used_, 1, receipt_.prefix_lookup_calls_upper,
                     "indexed prefix lookup exceeds the declared whole-call schedule");
        charge_query_work(prefix_query_work_upper_);
        (void)index_.vertex_at(cursor);
        const auto prefix = cursor.visible_prefix();
        const auto view = plan_->prefix_support(std::span<const graph::Card>(prefix.cards.data(), prefix.size));
        if (!view.board_index_key)
            graph::detail::fail(graph::ErrorCode::invalid_graph, "typed prefix view lacks its stable board-index key");
        return *view.board_index_key;
    }

    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }
    [[nodiscard]] Receipt receipt_snapshot() const noexcept {
        auto result = receipt_;
        const auto counts = index_.query_counts();
        result.history_route_calls_actual = counts.history_routes;
        result.history_route_tokens_actual = counts.history_route_tokens;
        result.root_cursor_calls_actual = counts.root_cursors;
        result.edge_advance_calls_actual = counts.edge_advances;
        result.decision_lookup_calls_actual = decision_calls_used_.load(std::memory_order_relaxed);
        result.prefix_lookup_calls_actual = prefix_calls_used_.load(std::memory_order_relaxed);
        result.router_query_work_actual = query_work_used_.load(std::memory_order_relaxed);
        result.index_query_work_actual = index_.query_work_reserved();
        result.index_query_entries_actual = index_.inverse_query_entries_reserved();
        return result;
    }
    [[nodiscard]] const history_index::Receipt& index_receipt() const noexcept { return index_.receipt(); }
    [[nodiscard]] std::uint64_t index_query_work_actual() const noexcept { return index_.query_work_reserved(); }
    [[nodiscard]] std::size_t index_query_entries_actual() const noexcept { return index_.inverse_query_entries_reserved(); }
    [[nodiscard]] std::uint64_t decision_lookup_calls_actual() const noexcept {
        return decision_calls_used_.load(std::memory_order_relaxed);
    }
    [[nodiscard]] std::uint64_t prefix_lookup_calls_actual() const noexcept {
        return prefix_calls_used_.load(std::memory_order_relaxed);
    }
    [[nodiscard]] std::uint64_t router_query_work_actual() const noexcept {
        return query_work_used_.load(std::memory_order_relaxed);
    }
    [[nodiscard]] std::uint64_t root_cursor_calls_actual() const noexcept {
        return root_calls_used_.load(std::memory_order_relaxed);
    }
    [[nodiscard]] std::uint64_t edge_advance_calls_actual() const noexcept {
        return edge_calls_used_.load(std::memory_order_relaxed);
    }

private:
    struct Prepared {
        graph::Plan const* plan = nullptr;
        RoutingSchedule schedule{};
        WholeLimits whole{};
        history_index::Limits index_limits{};
        Receipt receipt{};
        std::uint64_t decision_work_upper = 0;
        std::uint64_t prefix_work_upper = 0;
    };

    static std::uint64_t checked_add(std::uint64_t a, std::uint64_t b) {
        return graph::detail::checked_add(a, b);
    }
    static std::uint64_t checked_mul(std::uint64_t a, std::uint64_t b) {
        return graph::detail::checked_mul(a, b);
    }
    static std::size_t checked_entries(std::size_t a, std::size_t b) {
        return graph::detail::checked_entries(a, b);
    }
    static std::uint64_t ceil_log2(std::uint64_t value) noexcept {
        if (value <= 1) return 0;
        return static_cast<std::uint64_t>(std::bit_width(value - 1));
    }
    static std::uint64_t checked_sum(std::uint64_t a, std::uint64_t b, std::uint64_t c) {
        return checked_add(checked_add(a, b), c);
    }
    static std::size_t cursor_frame_entries_upper(std::uint64_t count) {
        return static_cast<std::size_t>(checked_mul(count, kMaximumCursorLogicalEntries));
    }
    static std::size_t sort_unique_keys(std::array<NumericRowKey, kMaximumSuitMaps>& keys,
                                        std::size_t size) {
        // G<=24 makes insertion sort's G*(G-1)/2 comparison ceiling exact and
        // independent of standard-library sorting implementation details.
        for (std::size_t i = 1; i < size; ++i) {
            const auto value = keys[i];
            auto j = i;
            while (j > 0 && value < keys[j - 1]) {
                keys[j] = keys[j - 1];
                --j;
            }
            keys[j] = value;
        }
        std::size_t unique_count = 0;
        for (std::size_t i = 0; i < size; ++i)
            if (unique_count == 0 || !(keys[i] == keys[unique_count - 1]))
                keys[unique_count++] = keys[i];
        return unique_count;
    }

    static Prepared prepare(const graph::Plan& plan, RoutingSchedule schedule,
                            WholeLimits whole, history_index::ExternalReservation caller) {
        if (!whole.modeled_work || whole.modeled_work > graph::kMaximumModeledWork ||
            !whole.logical_entries || whole.logical_entries > graph::kMaximumRetainedEntries)
            graph::detail::fail(graph::ErrorCode::invalid_limits, "indexed router whole limits must be positive and reduce-only");
        if (schedule.complete_training_runs != 1)
            graph::detail::fail(graph::ErrorCode::invalid_limits,
                                "indexed router schedule requires exactly one complete training run");

        Prepared prepared;
        prepared.plan = &plan;
        prepared.schedule = schedule;
        prepared.whole = whole;
        const auto& census = plan.graph_census();
        const auto q_count = plan.rows().size();
        const auto group_size = plan.group().size();
        if (group_size == 0 || group_size > kMaximumSuitMaps)
            graph::detail::fail(graph::ErrorCode::group_invalid, "indexed router suit-map count is outside its fixed bound");

        // Establish a conservative scan-work floor before walking Q histories
        // or graph vertices to derive the detailed route/query schedule.
        const auto max_history_tokens = checked_add(census.maximum_depth,
                                                     plan.graph().initial_history.size());
        const auto q_history_scan = checked_mul(q_count, max_history_tokens);
        const auto pre_scan_work = checked_sum(q_count, q_history_scan,
                                               checked_add(census.vertices, census.edges));
        const auto required_before_scan = checked_add(plan.receipt().modeled_work_upper,
            checked_add(pre_scan_work, caller.work_upper));
        if (required_before_scan > whole.modeled_work)
            graph::detail::fail(graph::ErrorCode::work_limit,
                                "indexed router whole-work limit is below its bounded schedule scan floor");

        std::uint64_t route_tokens = 0;
        std::size_t max_actions = 0;
        for (const auto& row : plan.rows())
            route_tokens = checked_add(route_tokens, row.key.history.size());
        std::uint64_t graph_scan_work = plan.graph().vertices.size();
        for (const auto& vertex : plan.graph().vertices) {
            max_actions = std::max(max_actions, vertex.actions.size());
            graph_scan_work = checked_add(graph_scan_work, vertex.actions.size());
        }

        const auto iterations = static_cast<std::uint64_t>(plan.iterations());
        const auto runtime_roots = checked_add(checked_mul(3, iterations),
            schedule.additional_full_shadow_walks);
        const auto total_walks = runtime_roots;
        const auto edge_calls = checked_mul(total_walks, census.logical_visits ? census.logical_visits - 1 : 0);
        const auto decision_calls = checked_add(
            checked_mul(checked_mul(3, iterations), census.decision_occurrences),
            checked_mul(schedule.additional_full_shadow_walks, census.decision_occurrences));
        const auto prefix_calls = checked_sum(
            checked_mul(checked_mul(2, iterations), census.terminal_occurrences),
                        checked_mul(iterations, census.decision_occurrences),
                        checked_mul(schedule.additional_full_shadow_walks, census.logical_visits));

        history_index::QuerySchedule index_schedule;
        index_schedule.history_route_calls = q_count;
        index_schedule.history_route_tokens_upper = route_tokens;
        index_schedule.root_cursor_calls = runtime_roots;
        index_schedule.edge_advance_calls = edge_calls;

        const auto prefix_count = std::max<std::size_t>(1, plan.receipt().support_prefixes);
        const auto hands = std::max(plan.hand_counts()[0], plan.hand_counts()[1]);
        const auto qlog = ceil_log2(static_cast<std::uint64_t>(q_count) + 1);
        const auto glog = ceil_log2(group_size + 1);
        const auto plog = ceil_log2(static_cast<std::uint64_t>(prefix_count) + 1);
        const auto hlog = ceil_log2(static_cast<std::uint64_t>(hands) + 1);
        // Plan::prefix_support validates at most five cards and performs at
        // most ten pairwise duplicate checks. PrefixLess compares at most five
        // cards per tree level. This is named modeled work, not CPU time.
        const auto prefix_lookup_work = checked_add(64, checked_mul(10, plog));
        const auto menu_action_work = checked_add(8, 2 * graph::kMaximumTokenBytes);
        const auto menu_work = checked_mul(max_actions, menu_action_work);
        const auto image_construction_work = checked_mul(group_size, 6);
        const auto image_sort_work = checked_mul(3, checked_mul(group_size, group_size - 1) / 2);
        const auto image_dedup_work = checked_mul(3, group_size);
        const auto member_search_work = checked_mul(3, glog);
        const auto image_key_work = checked_sum(image_construction_work, image_sort_work,
                                                image_dedup_work);
        const auto support_work = checked_mul(group_size, checked_add(3, hlog));
        const auto q_search_work = checked_mul(3, qlog);
        const auto per_row_work = checked_sum(64 + menu_work,
            checked_mul(group_size, prefix_lookup_work), checked_add(image_key_work, support_work));
        const auto setup_work = checked_sum(graph_scan_work, q_history_scan,
            checked_mul(q_count, checked_add(per_row_work, checked_add(q_search_work, 32))));

        const auto per_decision_work = checked_add(64 + menu_work,
            checked_add(checked_mul(group_size, prefix_lookup_work),
                checked_mul(hands, checked_sum(checked_add(image_key_work,
                    checked_add(support_work, member_search_work)),
                    checked_add(q_search_work, menu_work), 32))));
        const auto decision_work = checked_mul(decision_calls, per_decision_work);
        const auto prefix_work = checked_mul(prefix_calls, checked_add(16, prefix_lookup_work));
        const auto router_query_work = checked_add(decision_work, prefix_work);
        const auto router_work = checked_add(setup_work, router_query_work);

        const auto map_entries = checked_mul(q_count, kNumericQEntryScalarEntries);
        if (map_entries > std::numeric_limits<std::size_t>::max())
            graph::detail::fail(graph::ErrorCode::invalid_limits,
                                "numeric Q map entry forecast exceeds the platform entry counter");
        const auto router_retained = checked_entries(kRouterFixedEntriesUpper,
                                                     static_cast<std::size_t>(map_entries));
        // Both implementation sites use fixed std::array<..., Gmax> scratch,
        // even when the derived symmetry group is smaller than Gmax.
        const auto views_and_keys = kMaximumImageViewAndKeyEntries;
        const auto setup_scratch = checked_entries(kRouterFixedEntriesUpper,
            checked_entries(cursor_frame_entries_upper(2), static_cast<std::size_t>(views_and_keys)));
        const auto decision_scratch = checked_entries(kRouterFixedEntriesUpper,
            checked_entries(checked_mul(4, hands),
                static_cast<std::size_t>(views_and_keys)));
        const auto router_scratch = std::max(setup_scratch, decision_scratch);
        const auto external_work = checked_add(router_work, caller.work_upper);
        const auto external_entries = checked_entries(checked_entries(router_retained, router_scratch),
                                                       caller.entries_upper);

        auto& index_limits = prepared.index_limits;
        index_limits.max_combined_modeled_work = whole.modeled_work;
        index_limits.max_combined_entries = whole.logical_entries;
        index_limits.query_schedule = index_schedule;
        index_limits.external = {external_work, external_entries};

        auto& receipt = prepared.receipt;
        receipt.original_q_rows = q_count;
        receipt.numeric_map_entries_upper = q_count;
        receipt.router_retained_entries_upper = router_retained;
        receipt.router_setup_scratch_entries_upper = setup_scratch;
        receipt.router_query_scratch_entries_upper = decision_scratch;
        receipt.router_scratch_entries_upper = router_scratch;
        receipt.caller_reservation_entries_upper = caller.entries_upper;
        receipt.history_route_calls = index_schedule.history_route_calls;
        receipt.history_route_tokens_upper = index_schedule.history_route_tokens_upper;
        receipt.root_cursor_calls = index_schedule.root_cursor_calls;
        receipt.edge_advance_calls = index_schedule.edge_advance_calls;
        receipt.decision_lookup_calls_upper = decision_calls;
        receipt.prefix_lookup_calls_upper = prefix_calls;
        receipt.router_setup_work_upper = setup_work;
        receipt.router_query_work_upper = router_query_work;
        receipt.router_work_upper = router_work;
        receipt.caller_reservation_work_upper = caller.work_upper;
        receipt.work_limit = whole.modeled_work;
        receipt.logical_entry_limit = whole.logical_entries;
        receipt.index_query_work_upper = 0; // filled from the constructed index receipt
        receipt.index_query_entries_upper = 0;
        prepared.decision_work_upper = per_decision_work;
        prepared.prefix_work_upper = checked_add(16, prefix_lookup_work);
        return prepared;
    }

    IndexedRouting(const graph::Plan& plan, Prepared prepared)
        : plan_(&plan),
          decision_query_work_upper_(prepared.decision_work_upper),
          prefix_query_work_upper_(prepared.prefix_work_upper),
          index_(plan, prepared.index_limits), receipt_(std::move(prepared.receipt)) {
        if (prepared.plan != &plan)
            graph::detail::fail(graph::ErrorCode::invalid_query, "router preparation belongs to another Plan");
        numeric_q_.reserve(plan.rows().size());
        for (std::size_t q = 0; q < plan.rows().size(); ++q) {
            const auto& row = plan.rows()[q];
            const auto cursor = index_.cursor_from_history(row.key.history);
            const auto& vertex = index_.vertex_at(cursor);
            if (vertex.kind != graph::VertexKind::decision || vertex.actor != row.key.actor ||
                vertex.actions != row.menu || row.key.actor > 1 ||
                row.key.hand_index >= plan.hand_counts()[row.key.actor])
                graph::detail::fail(graph::ErrorCode::invalid_graph,
                                    "original Q key does not identify its admitted decision vertex/menu");

            std::array<graph::PrefixSupportView, kMaximumSuitMaps> views{};
            std::array<NumericRowKey, kMaximumSuitMaps> images{};
            const auto group_size = plan.group().size();
            for (std::size_t g = 0; g < group_size; ++g) {
                const auto prefix = cursor.visible_prefix(g);
                views[g] = plan.prefix_support(std::span<const graph::Card>(prefix.cards.data(), prefix.size));
                const auto mapped = plan.mapped_hand_index(row.key.actor, g, row.key.hand_index);
                if (!std::binary_search(views[g].hands[row.key.actor].begin(),
                                        views[g].hands[row.key.actor].end(), mapped))
                    graph::detail::fail(graph::ErrorCode::group_not_closed,
                                        "original Q row has an unsupported suit-image hand/prefix");
                images[g] = {row.key.actor, mapped, cursor.image_ordinal(g)};
            }
            const auto image_count = sort_unique_keys(images, group_size);
            auto first = images.begin();
            const auto unique_end = first + static_cast<std::ptrdiff_t>(image_count);
            const NumericRowKey original{row.key.actor, row.key.hand_index, cursor.ordinal()};
            const auto expected_mask = image_count == 32 ? 0xffffffffU : ((1U << image_count) - 1U);
            if (image_count == 0 || !(*first == original) || row.orbit_size != image_count ||
                row.size != image_count || row.expected_mask != expected_mask)
                graph::detail::fail(graph::ErrorCode::invalid_graph,
                                    "numeric Q image orbit does not preserve original representative, size or mask");
            if (!numeric_q_.empty() && !(numeric_q_.back().key < original))
                graph::detail::fail(graph::ErrorCode::invalid_graph,
                                    "numeric Q keys are not strictly increasing in original Q order");
            numeric_q_.push_back({original, q});
        }
        if (numeric_q_.size() != plan.rows().size())
            graph::detail::fail(graph::ErrorCode::invalid_graph, "numeric Q map omitted an original Q row");
        receipt_.numeric_map_entries_actual = numeric_q_.size();
        const auto actual_map_fields = checked_mul(numeric_q_.size(), kNumericQEntryScalarEntries);
        if (actual_map_fields > std::numeric_limits<std::size_t>::max())
            graph::detail::fail(graph::ErrorCode::invalid_limits,
                                "actual numeric Q map exceeds the platform entry counter");
        receipt_.router_retained_entries_actual = checked_entries(
            kRouterFixedEntriesUpper, static_cast<std::size_t>(actual_map_fields));
        if (receipt_.router_retained_entries_actual > receipt_.router_retained_entries_upper)
            graph::detail::fail(graph::ErrorCode::invalid_graph,
                                "actual numeric Q entries exceed their admitted retained ledger");
        receipt_.combined_modeled_work_upper = index_.receipt().combined_modeled_work_upper;
        receipt_.combined_logical_entries_upper = index_.receipt().combined_peak_entries_upper;
        receipt_.router_setup_work_actual = receipt_.router_setup_work_upper;
        receipt_.index_query_work_upper = index_.receipt().query_work_upper;
        receipt_.index_query_entries_upper = index_.receipt().query_cumulative_entries_upper;
        receipt_.index_query_work_actual = index_.query_work_reserved();
        receipt_.index_query_entries_actual = index_.inverse_query_entries_reserved();
    }

    static void reserve_call(std::atomic<std::uint64_t>& counter, std::uint64_t amount,
                             std::uint64_t upper, const char* message) {
        auto previous = counter.load(std::memory_order_relaxed);
        while (true) {
            const auto next = checked_add(previous, amount);
            if (next > upper) graph::detail::fail(graph::ErrorCode::work_limit, message);
            if (counter.compare_exchange_weak(previous, next,
                    std::memory_order_relaxed, std::memory_order_relaxed)) return;
        }
    }
    void charge_query_work(std::uint64_t amount) const {
        auto previous = query_work_used_.load(std::memory_order_relaxed);
        while (true) {
            const auto next = checked_add(previous, amount);
            if (next > receipt_.router_query_work_upper)
                graph::detail::fail(graph::ErrorCode::work_limit,
                                    "indexed router work exceeds its whole-call query forecast");
            if (query_work_used_.compare_exchange_weak(previous, next,
                    std::memory_order_relaxed, std::memory_order_relaxed)) return;
        }
    }

    const graph::Plan* plan_ = nullptr;
    std::uint64_t decision_query_work_upper_ = 0;
    std::uint64_t prefix_query_work_upper_ = 0;
    history_index::HistoryIndex index_;
    std::vector<NumericQEntry> numeric_q_;
    mutable std::atomic<std::uint64_t> decision_calls_used_{0};
    mutable std::atomic<std::uint64_t> prefix_calls_used_{0};
    mutable std::atomic<std::uint64_t> query_work_used_{0};
    mutable std::atomic<std::uint64_t> root_calls_used_{0};
    mutable std::atomic<std::uint64_t> edge_calls_used_{0};
    mutable Receipt receipt_{};
};

} // namespace openpoker::exact_indexed_routing
