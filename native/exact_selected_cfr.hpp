#pragma once

// Whole-root alternating CFR+ over the exact native kernel and procedural Q plan.
// This implementation is pending integration/conformance; no backend is registered.
#include "exact_public_graph.hpp"
#include "exact_indexed_routing.hpp"
#include <cfenv>
#include <cmath>
#include <map>

namespace openpoker::exact_selected_cfr {
namespace graph = exact_public_graph;
namespace kernel = exact_selected_kernel;
namespace routing = exact_indexed_routing;
using Vector = std::vector<double>;

inline double finite(double value) {
    if (!std::isfinite(value)) throw std::runtime_error("nonfinite native CFR intermediate");
    return value == 0.0 ? 0.0 : value;
}
inline double add(double a, double b) { return finite(finite(a) + finite(b)); }
inline double sub(double a, double b) { return finite(finite(a) - finite(b)); }
inline double mul(double a, double b) { return finite(finite(a) * finite(b)); }
inline double div(double a, double b) {
    if (finite(b) == 0.0) throw std::runtime_error("zero native CFR divisor");
    return finite(finite(a) / b);
}

struct Limits {
    std::uint64_t max_modeled_work = 500'000'000;
    std::size_t max_entries = 25'000'000;
    std::size_t max_action_slots = 1'000'000;
    std::size_t max_output_values = 2'000'000;
};
struct IndexedShadowReceipt {
    std::string version = "native-exact-cfr-indexed-shadow-v1";
    std::string mode = "shadow";
    routing::Receipt routing;
    std::uint64_t caller_work_upper = 0;
    std::uint64_t comparison_and_cursor_work_upper = 0;
    std::uint64_t plan_kernel_forecast_retained_overlap = 0;
    std::size_t caller_entries_upper = 0;
    std::size_t cursor_frame_entries_upper = 0;
    std::size_t report_and_bookkeeping_entries_upper = 4096;
    std::uint64_t decision_comparisons = 0;
    std::uint64_t prefix_comparisons = 0;
    std::uint64_t legacy_training_history_extensions = 0;
    std::uint64_t legacy_training_row_lookups = 0;
    std::uint64_t legacy_training_prefix_lookups = 0;
    std::uint64_t legacy_full_history_work_forecast_retained = 0;
    std::size_t final_router_entries = 0;
};
struct Receipt {
    std::string version = "native-exact-sorted-q-cfrplus-v1";
    std::uint64_t modeled_work_upper = 0;
    std::uint64_t kernel_work_upper = 0;
    std::uint64_t plan_kernel_forecast_removed = 0;
    std::uint64_t plan_non_kernel_work_upper = 0;
    std::uint64_t training_work_upper = 0;
    std::uint64_t full_history_lookup_work_upper = 0;
    std::uint64_t marginal_work_upper = 0;
    std::size_t marginal_entries_upper = 0;
    std::size_t kernel_query_scratch_upper = 0;
    std::size_t kernel_payload_upper = 0;
    std::size_t retained_entries_upper = 0;
    std::size_t member_checks = 0;
    std::size_t expected_member_checks = 0;
    std::size_t action_slots = 0;
    std::size_t expanded_output_values = 0;
    std::size_t maximum_numeric_workspace_slots = 0;
    std::size_t final_numeric_workspace_slots = 0;
    // Counts only learning; preflight, marginal setup and Q-map construction
    // intentionally retain their old history preparation outside this scope.
    std::uint64_t legacy_training_history_extensions = 0;
    std::uint64_t legacy_training_row_lookups = 0;
    std::uint64_t legacy_training_prefix_lookups = 0;
    std::optional<IndexedShadowReceipt> indexed_shadow;
};
struct Result { Vector quotient_policy; Receipt receipt; };

class Trainer final {
public:
    Trainer(graph::Plan& plan, Limits limits = {}) : plan_(plan), limits_(limits) {
        if (!limits.max_modeled_work || limits.max_modeled_work > 500'000'000 ||
            !limits.max_entries || limits.max_entries > 25'000'000 ||
            !limits.max_action_slots || limits.max_action_slots > 1'000'000 ||
            !limits.max_output_values || limits.max_output_values > 2'000'000)
            throw std::invalid_argument("native CFR limits must be positive reduce-only values");
        validate_floating_environment();
        preflight();
        construction_kernel_work_ = plan_.kernel().receipt().modeled_work;
    }

    Result run() { return run_impl(RunMode::legacy); }

    // Explicit C++ control entry only. Production wire/default still use run().
    Result run_indexed_shadow() { return run_impl(RunMode::shadow); }

    Result run_indexed() { return run_impl(RunMode::indexed); }

private:
    enum class RunMode { legacy, shadow, indexed };
    Result run_impl(RunMode mode) {
        if (started_) throw std::runtime_error("native CFR trainer is single use");
        started_ = true;
        mode_ = mode;
        // The caller must exclusively own the plan/kernel for this complete
        // single-use run. Re-admit fresh cumulative kernel work because a
        // caller may have consumed it after construction; no concurrent use.
        try {
            validate_floating_environment();
            if (mode != RunMode::legacy && plan_.kernel().receipt().modeled_work != construction_kernel_work_)
                throw std::runtime_error("indexed shadow requires the constructor-admitted exclusive kernel state");
            preflight();
            if (mode != RunMode::legacy) prepare_indexed_shadow();
            populate_marginal_keys();
            for (auto& [indexes, value] : marginals_) value = plan_.kernel().marginals(indexes);
            regrets_.assign(receipt_.action_slots, 0.0);
            sums_.assign(receipt_.action_slots, 0.0);
            current_.assign(receipt_.action_slots, 0.0);
            deltas_.assign(receipt_.action_slots, 0.0);
            seen_.assign(plan_.rows().size(), 0);
            receipt_.maximum_numeric_workspace_slots = 4 * receipt_.action_slots;
            for (unsigned iteration = 1; iteration <= plan_.iterations(); ++iteration) {
                rematch(); responder(0); rematch(); responder(1); rematch();
                average_pass(static_cast<double>(iteration));
            }
            if (receipt_.member_checks != receipt_.expected_member_checks ||
                plan_.kernel().receipt().modeled_work > receipt_.kernel_work_upper)
                throw std::runtime_error("native CFR completed receipt differs from admission");
            if (shadow_router_) finish_indexed_shadow();
            // Normalize the existing average array in place, then transfer its
            // ownership after dropping the other three arrays and member masks.
            // No fifth Q-sized double buffer overlaps training workspaces.
            for (const auto& row : plan_.rows()) {
                double total = 0.0;
                for (std::size_t action = 0; action < row.count; ++action) total = add(total, sums_[row.offset + action]);
                for (std::size_t action = 0; action < row.count; ++action)
                    sums_[row.offset + action] = total
                        ? div(sums_[row.offset + action], total) : div(1.0, static_cast<double>(row.count));
            }
            Vector().swap(regrets_); Vector().swap(current_); Vector().swap(deltas_);
            std::vector<std::uint32_t>().swap(seen_);
            Result result;
            result.quotient_policy.swap(sums_);
            marginals_.clear();
            shadow_router_.reset();
            receipt_.final_numeric_workspace_slots = 0;
            result.receipt = receipt_;
            return result;
        } catch (...) { release_workspace(); marginals_.clear(); shadow_router_.reset(); throw; }
    }

    using Locations = std::vector<std::optional<graph::RowLocation>>;
    using Cursor = routing::IndexedRouting::Cursor;
    using Marginals = kernel::ExactSelectedKernel::MarginalVectors;
    static std::uint64_t checked_add(std::uint64_t a, std::uint64_t b) {
        return graph::detail::checked_add(a, b);
    }
    static std::uint64_t checked_mul(std::uint64_t a, std::uint64_t b) {
        return graph::detail::checked_mul(a, b);
    }
    static std::size_t log_upper(std::size_t value) {
        std::size_t result = 0;
        for (std::size_t x = value > 0 ? value - 1 : 0; x; x >>= 1) ++result;
        return result;
    }
    static void validate_floating_environment() {
        if (std::fegetround() != FE_TONEAREST) throw std::runtime_error("native CFR requires nearest rounding mode");
        volatile double tiny = std::numeric_limits<double>::denorm_min();
        volatile double unit = 1.0;
        const double product = tiny * unit;
        if (std::bit_cast<std::uint64_t>(product) != 1)
            throw std::runtime_error("native CFR requires preserved binary64 subnormals");
    }
    void prepare_indexed_shadow() {
        if (shadow_router_ || !regrets_.empty() || !sums_.empty() || !marginals_.empty())
            throw std::runtime_error("indexed shadow router/workspace is not fresh");
        const auto& census = plan_.graph_census();
        const auto t = static_cast<std::uint64_t>(plan_.iterations());
        const auto visits = checked_mul(3 * t, census.logical_visits);
        const auto decisions = checked_mul(3 * t, census.decision_occurrences);
        const auto prefixes = checked_add(checked_mul(2 * t, census.terminal_occurrences),
                                         checked_mul(t, census.decision_occurrences));
        const auto max_h = std::max(plan_.hand_counts()[0], plan_.hand_counts()[1]);
        // Cursor has a fixed 24-image array even for G1. Reserve four complete
        // cursor copies per live depth, including edge-return/root temporaries.
        const auto cursor_entries = checked_mul(checked_mul(4, census.maximum_depth + 4),
                                                 routing::kMaximumCursorLogicalEntries);
        const auto cursor_work = checked_mul(visits,
            checked_add(64, checked_mul(4, routing::kMaximumCursorLogicalEntries)));
        const auto comparison_work = checked_add(
            checked_mul(decisions, checked_add(32, checked_mul(8, max_h))),
            checked_mul(prefixes, checked_add(16, checked_mul(2, plan_.selected_board_count()))));
        const auto extra_work = checked_add(cursor_work, comparison_work);
        // Plan's named setup-kernel forecast remains conservatively charged:
        // Index adds full Plan once; caller adds fresh full callbacks and old
        // history training. No capacity credit or duplicate Plan subtraction.
        const auto caller_work = checked_add(receipt_.kernel_work_upper,
            checked_add(receipt_.training_work_upper, extra_work));
        if (receipt_.retained_entries_upper < plan_.receipt().retained_entries_upper)
            throw std::runtime_error("indexed shadow Plan storage overlap changed");
        const auto caller_entries = checked_add(
            receipt_.retained_entries_upper - plan_.receipt().retained_entries_upper,
            checked_add(cursor_entries, 4096));
        if (caller_entries > graph::kMaximumRetainedEntries)
            throw std::runtime_error("indexed shadow caller entries exceed whole ceiling before router");
        routing::WholeLimits whole{limits_.max_modeled_work,
            std::min(limits_.max_entries, graph::kMaximumRetainedEntries)};
        auto router = std::make_unique<routing::IndexedRouting>(plan_, routing::RoutingSchedule{}, whole,
            exact_public_history_index::ExternalReservation{caller_work, static_cast<std::size_t>(caller_entries)});
        IndexedShadowReceipt shadow;
        if (mode_ == RunMode::indexed) {
            shadow.mode = "indexed";
            shadow.version = "native-exact-cfr-indexed-v1";
        }
        shadow.caller_work_upper = caller_work;
        shadow.comparison_and_cursor_work_upper = extra_work;
        shadow.plan_kernel_forecast_retained_overlap = receipt_.plan_kernel_forecast_removed;
        shadow.caller_entries_upper = static_cast<std::size_t>(caller_entries);
        shadow.cursor_frame_entries_upper = static_cast<std::size_t>(cursor_entries);
        shadow.legacy_full_history_work_forecast_retained = receipt_.full_history_lookup_work_upper;
        receipt_.indexed_shadow = std::move(shadow);
        shadow_router_ = std::move(router);
    }
    void finish_indexed_shadow() {
        auto& shadow = *receipt_.indexed_shadow;
        shadow.routing = shadow_router_->receipt_snapshot();
        const auto& r = shadow.routing;
        const bool indexed_only = mode_ == RunMode::indexed;
        shadow.legacy_training_history_extensions = receipt_.legacy_training_history_extensions;
        shadow.legacy_training_row_lookups = receipt_.legacy_training_row_lookups;
        shadow.legacy_training_prefix_lookups = receipt_.legacy_training_prefix_lookups;
        if (r.history_route_calls_actual != r.history_route_calls ||
            r.history_route_tokens_actual != r.history_route_tokens_upper ||
            r.root_cursor_calls_actual != r.root_cursor_calls ||
            r.edge_advance_calls_actual != r.edge_advance_calls ||
            r.decision_lookup_calls_actual != r.decision_lookup_calls_upper ||
            r.prefix_lookup_calls_actual != r.prefix_lookup_calls_upper ||
            shadow.decision_comparisons != (indexed_only ? 0 : r.decision_lookup_calls_actual) ||
            shadow.prefix_comparisons != (indexed_only ? 0 : r.prefix_lookup_calls_actual) ||
            shadow.legacy_training_history_extensions != (indexed_only ? 0 : r.edge_advance_calls_actual) ||
            shadow.legacy_training_row_lookups != (indexed_only ? 0 : r.decision_lookup_calls_actual) ||
            shadow.legacy_training_prefix_lookups != (indexed_only ? 0 : r.prefix_lookup_calls_actual) ||
            r.r_lookup_entries || !r.original_q_histories_retained)
            throw std::runtime_error("indexed shadow complete-call routing coverage differs from admission");
        shadow.final_router_entries = 0; // ownership is dropped before returning Result
    }
    Locations decision_locations(std::uint8_t actor, const graph::History& history,
                                 std::span<const graph::Action> menu, const Cursor* cursor) {
        if (mode_ == RunMode::indexed) {
            if (!shadow_router_ || !cursor) throw std::runtime_error("indexed decision lacks its exclusive cursor/router");
            return shadow_router_->locate_decision_rows(*cursor, actor, menu);
        }
        ++receipt_.legacy_training_row_lookups;
        auto old = plan_.locate_decision_rows(actor, history, menu);
        if (shadow_router_) {
            if (!cursor) throw std::runtime_error("indexed shadow decision lacks its cursor");
            const auto indexed = shadow_router_->locate_decision_rows(*cursor, actor, menu);
            if (old != indexed) throw std::runtime_error("indexed shadow q/offset/member/null-hole comparison differs");
            ++receipt_.indexed_shadow->decision_comparisons;
        }
        return old;
    }
    const std::vector<std::size_t>& callback_indexes(const graph::History& history, const Cursor* cursor) {
        if (mode_ == RunMode::indexed) {
            if (!shadow_router_ || !cursor) throw std::runtime_error("indexed callback lacks its exclusive cursor/router");
            return shadow_router_->prefix_board_indexes(*cursor);
        }
        ++receipt_.legacy_training_prefix_lookups;
        const auto& old = plan_.prefix_board_indexes(history);
        if (shadow_router_) {
            if (!cursor) throw std::runtime_error("indexed shadow callback lacks its cursor");
            const auto& indexed = shadow_router_->prefix_board_indexes(*cursor);
            if (old != indexed) throw std::runtime_error("indexed shadow ordered board-index comparison differs");
            ++receipt_.indexed_shadow->prefix_comparisons;
        }
        return old;
    }
    const graph::History& training_root_history() const noexcept {
        return mode_ == RunMode::indexed ? empty_training_history_ : plan_.graph().initial_history;
    }
    void preflight() {
        receipt_ = Receipt{};
        const auto counts = plan_.hand_counts();
        const auto h = counts[0] + counts[1];
        const auto& census = plan_.graph_census();
        std::size_t maximum_degree = 1;
        for (const auto& vertex : plan_.graph().vertices)
            maximum_degree = std::max(maximum_degree, std::max(vertex.children.size(), vertex.branches.size()));
        if (census.maximum_depth > 64 || census.logical_visits > 250'000 ||
            census.decision_hand_slots_upper > 2'000'000 || census.action_slots_upper > limits_.max_action_slots)
            throw std::runtime_error("native CFR old expanded geometry limit exceeded");
        const auto lookup = checked_mul(plan_.iterations(), checked_add(
            checked_mul(census.logical_visits, checked_mul(h, 32 + 8 * log_upper(maximum_degree))),
            checked_mul(census.action_slots_upper, 40)));
        // Plan::preflight_q_plan already reserves (3T+8) group lookups and
        // (6T+8) action checks. Add an explicit full-history/key-byte envelope
        // for trainer scans/parsing/map comparisons; do not infer free work
        // from that existing lookup count. Units are logical, not CPU bounds.
        const auto history_keys = checked_add(
            checked_mul(16, census.history_token_entries_upper),
            checked_add(checked_mul(4, census.row_history_bytes_upper),
                checked_add(checked_mul(8 * (census.maximum_depth + 1), census.decision_hand_slots_upper),
                            checked_mul(16 * (census.maximum_depth + 1), census.logical_visits))));
        receipt_.full_history_lookup_work_upper = checked_mul(3ULL * plan_.iterations() + 4ULL,
            checked_mul(plan_.group().size(), history_keys));
        receipt_.training_work_upper = checked_add(lookup, receipt_.full_history_lookup_work_upper);
        receipt_.expanded_output_values = census.action_slots_upper;
        if (receipt_.expanded_output_values > limits_.max_output_values)
            throw std::runtime_error("native CFR expanded output admission exceeded");
        for (const auto& row : plan_.rows()) {
            if (row.offset != receipt_.action_slots || row.count != row.menu.size() || !row.count)
                throw std::runtime_error("native CFR Q layout changed");
            receipt_.action_slots += row.count;
            receipt_.expected_member_checks += 2 * static_cast<std::size_t>(plan_.iterations()) * row.orbit_size;
        }
        if (receipt_.action_slots > limits_.max_action_slots)
            throw std::runtime_error("native CFR Q action admission exceeded");
        const auto nested = checked_mul(census.maximum_depth + 2, checked_mul(maximum_degree + 8, 8 * h + 64));
        const auto entries = checked_add(plan_.receipt().retained_entries_upper,
            checked_add(4 * receipt_.action_slots + plan_.rows().size(), nested));
        if (entries > limits_.max_entries) throw std::runtime_error("native CFR combined scratch admission exceeded");
        receipt_.retained_entries_upper = static_cast<std::size_t>(entries);
        // Pre-admit full map/key/value storage before any map insertion.
        // A prefix key has at most B board indexes. Prefix caching is owned
        // by Plan, and no more distinct index keys can occur than its prefixes.
        const auto board_count = plan_.selected_board_count();
        receipt_.marginal_entries_upper = static_cast<std::size_t>(checked_mul(
            plan_.receipt().support_prefixes, checked_add(h + 64, board_count)));
        if (receipt_.marginal_entries_upper > limits_.max_entries - receipt_.retained_entries_upper)
            throw std::runtime_error("native CFR retained marginal admission exceeded");
        receipt_.retained_entries_upper += receipt_.marginal_entries_upper;
        // No public cache-capacity accessor exists: reserve the admitted
        // maximum cache64 plus active vector overlap, not inferred cache state.
        const auto terminal_scratch = checked_add(140 * h + 1000, 65 * h);
        const auto marginal_scratch = 12 * h + 600;
        receipt_.kernel_query_scratch_upper = static_cast<std::size_t>(std::max(terminal_scratch, marginal_scratch));
        const auto kernel_retained = plan_.kernel().receipt().retained_entries;
        if (receipt_.kernel_query_scratch_upper > plan_.kernel().limits().max_storage_entries ||
            kernel_retained > plan_.kernel().limits().max_storage_entries - receipt_.kernel_query_scratch_upper)
            throw std::runtime_error("native CFR kernel retained/query-scratch admission exceeded");
        if (receipt_.kernel_query_scratch_upper > limits_.max_entries - receipt_.retained_entries_upper)
            throw std::runtime_error("native CFR combined kernel scratch admission exceeded");
        receipt_.retained_entries_upper += receipt_.kernel_query_scratch_upper;
        // Walk occurrence histories without retaining an expanded row/node table
        // or performing a kernel query/counter mutation during admission.
        std::uint64_t terminal_per_iteration = 0;
        std::function<void(std::size_t, const graph::History&)> scan;
        scan = [&](std::size_t id, const graph::History& history) {
            const auto& vertex = plan_.graph().vertices[id];
            const auto& indexes = plan_.prefix_board_indexes(history);
            if (vertex.kind == graph::VertexKind::decision) {
                for (std::size_t a = 0; a < vertex.children.size(); ++a)
                    scan(vertex.children[a], graph::Plan::extend_history(history, vertex.actions[a]));
            } else if (vertex.kind == graph::VertexKind::chance) {
                for (const auto& branch : vertex.branches)
                    scan(branch.child, graph::Plan::extend_history(history, vertex.street, branch.label));
            } else {
                for (const auto bits : vertex.contribution_bits) {
                    const auto amount = std::bit_cast<double>(bits);
                    if (!std::isfinite(amount) || amount < 0.0 || amount > 1e12)
                        throw std::runtime_error("native CFR original terminal money exceeds payoff proof envelope");
                }
                const auto per_board = vertex.terminal_kind == graph::TerminalKind::showdown
                    ? 200 * h + 520 + h * (16 * log_upper(std::max<std::size_t>(2, h)) + 8)
                    : 48 * h + 512;
                terminal_per_iteration = checked_add(terminal_per_iteration,
                    checked_add(checked_mul(2 * indexes.size(), per_board), 12 * h + 128));
            }
        };
        scan(plan_.graph().root_id, plan_.graph().initial_history);
        scan = nullptr;
        const auto marginal_work = checked_mul(plan_.receipt().support_prefixes,
            checked_add(checked_mul(board_count, 40 * h + 512), 4 * h + 32));
        receipt_.marginal_work_upper = marginal_work;
        receipt_.kernel_work_upper = checked_add(plan_.kernel().receipt().modeled_work,
            checked_add(marginal_work, checked_mul(plan_.iterations(), terminal_per_iteration)));
        if (receipt_.kernel_work_upper > plan_.kernel().limits().max_modeled_work)
            throw std::runtime_error("native CFR complete callback-work admission exceeded");
        // The plan receipt includes a conservative kernel constructor/support
        // forecast, not just non-kernel graph/Q work. Remove its named forecast
        // before adding the fresh actual kernel
        // counter and all future callbacks; otherwise it is charged twice.
        receipt_.plan_kernel_forecast_removed = plan_.kernel_setup_support_work_upper();
        if (plan_.receipt().modeled_work_upper < receipt_.plan_kernel_forecast_removed)
            throw std::runtime_error("native CFR plan work-accounting contract changed");
        receipt_.plan_non_kernel_work_upper = plan_.receipt().modeled_work_upper - receipt_.plan_kernel_forecast_removed;
        receipt_.modeled_work_upper = checked_add(receipt_.plan_non_kernel_work_upper,
            checked_add(receipt_.kernel_work_upper, receipt_.training_work_upper));
        if (receipt_.modeled_work_upper > limits_.max_modeled_work)
            throw std::runtime_error("native CFR whole-request modeled-work admission exceeded");
        std::size_t w0 = 0, w1 = 0;
        for (const auto& value : plan_.kernel().integer_weights()[0]) w0 = std::max(w0, kernel::detail::magnitude_bits(value));
        for (const auto& value : plan_.kernel().integer_weights()[1]) w1 = std::max(w1, kernel::detail::magnitude_bits(value));
        const auto query_width = std::max(w0 + w1 + 1127 + 53 + log_upper(h) + 80,
            kernel::detail::magnitude_bits(plan_.kernel().normalizer_integer()) + 2148);
        const auto payload = checked_add(plan_.kernel().receipt().setup_integer_payload_bits,
            checked_add(checked_mul(140 * h + 800, query_width), query_width + 53));
        if (query_width > plan_.kernel().limits().max_integer_bits ||
            payload > plan_.kernel().limits().max_integer_payload_bits)
            throw std::runtime_error("native CFR full callback integer-payload admission exceeded");
        receipt_.kernel_payload_upper = static_cast<std::size_t>(payload);
    }

    void populate_marginal_keys() {
        if (!marginals_.empty()) throw std::runtime_error("native CFR marginal map is not fresh");
        std::size_t entries = 0;
        std::function<void(std::size_t, const graph::History&)> scan;
        scan = [&](std::size_t id, const graph::History& history) {
            const auto& vertex = plan_.graph().vertices[id];
            if (vertex.kind == graph::VertexKind::decision) {
                const auto& indexes = plan_.prefix_board_indexes(history);
                if (marginals_.find(indexes) == marginals_.end()) {
                    const auto amount = checked_add(plan_.hand_counts()[0] + plan_.hand_counts()[1] + 64, indexes.size());
                    if (marginals_.size() >= plan_.receipt().support_prefixes ||
                        amount > receipt_.marginal_entries_upper - entries)
                        throw std::runtime_error("native CFR marginal map/key capacity exceeded before insertion");
                    entries += static_cast<std::size_t>(amount);
                    marginals_.try_emplace(indexes);
                }
                for (std::size_t a = 0; a < vertex.children.size(); ++a)
                    scan(vertex.children[a], graph::Plan::extend_history(history, vertex.actions[a]));
            } else if (vertex.kind == graph::VertexKind::chance) {
                for (const auto& branch : vertex.branches)
                    scan(branch.child, graph::Plan::extend_history(history, vertex.street, branch.label));
            }
        };
        scan(plan_.graph().root_id, plan_.graph().initial_history);
    }

    void release_workspace() noexcept {
        Vector().swap(regrets_); Vector().swap(sums_); Vector().swap(current_); Vector().swap(deltas_);
        std::vector<std::uint32_t>().swap(seen_);
    }
    void rematch() {
        for (const auto& row : plan_.rows()) {
            double mass = 0.0;
            for (std::size_t a = 0; a < row.count; ++a) mass = add(mass, std::max(finite(regrets_[row.offset + a]), 0.0));
            for (std::size_t a = 0; a < row.count; ++a)
                current_[row.offset + a] = mass ? div(std::max(finite(regrets_[row.offset + a]), 0.0), mass)
                    : div(1.0, static_cast<double>(row.count));
        }
    }
    void stage(const graph::RowLocation& location, std::size_t count, const Vector& increment) {
        const auto prior = seen_[location.q];
        if (prior & location.member_bit) throw std::runtime_error("duplicate native Q member");
        for (std::size_t a = 0; a < count; ++a) {
            const double value = add(0.0, increment[a]);
            if (!prior) deltas_[location.offset + a] = value;
            else if (std::bit_cast<std::uint64_t>(deltas_[location.offset + a]) != std::bit_cast<std::uint64_t>(value))
                throw std::runtime_error("native Q orbit increment differs by member");
        }
        seen_[location.q] |= location.member_bit;
    }
    Vector target_child(const graph::Vertex& vertex, const graph::History& history, const Vector& reach,
                        std::size_t player, const Cursor* parent, std::size_t edge) {
        const bool reveal = vertex.kind == graph::VertexKind::chance;
        const auto id = reveal ? vertex.branches[edge].child : vertex.children[edge];
        // Branch before any full-history extension: indexed learning carries
        // only the cursor; setup/preflight retain the unchanged old histories.
        if (mode_ == RunMode::indexed) {
            if (!parent) throw std::runtime_error("indexed target child lacks its cursor");
            const auto next = reveal ? shadow_router_->advance_reveal(*parent, edge)
                                     : shadow_router_->advance_action(*parent, edge);
            return target(id, empty_training_history_, reach, player, &next);
        }
        ++receipt_.legacy_training_history_extensions;
        const auto extended = reveal
            ? graph::Plan::extend_history(history, vertex.street, vertex.branches[edge].label)
            : graph::Plan::extend_history(history, vertex.actions[edge]);
        if (!parent) return target(id, extended, reach, player);
        const auto next = reveal ? shadow_router_->advance_reveal(*parent, edge)
                                 : shadow_router_->advance_action(*parent, edge);
        return target(id, extended, reach, player, &next);
    }
    Vector target(std::size_t id, const graph::History& history, const Vector& reach,
                  std::size_t player, const Cursor* cursor = nullptr) {
        const auto& vertex = plan_.graph().vertices[id];
        if (vertex.kind == graph::VertexKind::terminal) {
            const auto amount = std::min(std::bit_cast<double>(vertex.contribution_bits[0]),
                                         std::bit_cast<double>(vertex.contribution_bits[1]));
            const bool fold = vertex.terminal_kind == graph::TerminalKind::fold;
            const double payoff = fold && vertex.winner == 1 ? -amount : amount;
            return plan_.kernel().terminal(player, callback_indexes(history, cursor),
                fold ? kernel::TerminalKind::fold : kernel::TerminalKind::showdown, payoff, reach);
        }
        const auto h = plan_.hand_counts()[player];
        if (vertex.kind == graph::VertexKind::chance) {
            std::vector<Vector> components(h);
            for (std::size_t edge = 0; edge < vertex.branches.size(); ++edge) {
                const auto child = target_child(vertex, history, reach, player, cursor, edge);
                for (std::size_t i = 0; i < h; ++i) components[i].push_back(finite(child[i]));
            }
            Vector result(h, 0.0);
            for (std::size_t i = 0; i < h; ++i) {
                std::sort(components[i].begin(), components[i].end());
                for (double value : components[i]) result[i] = add(result[i], value);
            }
            return result;
        }
        const auto slots = decision_locations(vertex.actor, history, vertex.actions, cursor);
        const auto count = vertex.children.size();
        auto probability = [&](std::size_t hand, std::size_t action) {
            return slots[hand] ? finite(current_[slots[hand]->offset + action]) : div(1.0, static_cast<double>(count));
        };
        Vector result(h, 0.0);
        if (vertex.actor == player) {
            std::vector<Vector> values;
            values.reserve(count);
            for (std::size_t a = 0; a < count; ++a)
                values.push_back(target_child(vertex, history, reach, player, cursor, a));
            for (std::size_t i = 0; i < h; ++i) {
                for (std::size_t a = 0; a < count; ++a) result[i] = add(result[i], mul(probability(i, a), values[a][i]));
                if (slots[i]) {
                    Vector increment(count);
                    for (std::size_t a = 0; a < count; ++a) increment[a] = sub(values[a][i], result[i]);
                    stage(*slots[i], count, increment);
                }
            }
        } else {
            for (std::size_t a = 0; a < count; ++a) {
                Vector changed(reach.size());
                for (std::size_t i = 0; i < reach.size(); ++i) changed[i] = mul(reach[i], probability(i, a));
                const auto child = target_child(vertex, history, changed, player, cursor, a);
                for (std::size_t i = 0; i < h; ++i) result[i] = add(result[i], child[i]);
            }
        }
        return result;
    }
    void responder(std::size_t player) {
        for (std::size_t q = 0; q < plan_.rows().size(); ++q) if (plan_.rows()[q].key.actor == player) seen_[q] = 0;
        if (shadow_router_) {
            const auto cursor = shadow_router_->root_cursor();
            target(plan_.graph().root_id, training_root_history(), Vector(plan_.hand_counts()[1 - player], 1.0), player, &cursor);
        } else target(plan_.graph().root_id, plan_.graph().initial_history, Vector(plan_.hand_counts()[1 - player], 1.0), player);
        for (std::size_t q = 0; q < plan_.rows().size(); ++q) if (plan_.rows()[q].key.actor == player) {
            const auto& row = plan_.rows()[q];
            if (seen_[q] != row.expected_mask) throw std::runtime_error("incomplete native Q responder coverage");
            receipt_.member_checks += row.orbit_size;
            for (std::size_t a = 0; a < row.count; ++a) add(regrets_[row.offset + a], deltas_[row.offset + a]);
        }
        for (const auto& row : plan_.rows()) if (row.key.actor == player)
            for (std::size_t a = 0; a < row.count; ++a)
                regrets_[row.offset + a] = std::max(add(regrets_[row.offset + a], deltas_[row.offset + a]), 0.0);
    }
    void average_child(const graph::Vertex& vertex, const graph::History& history,
                       const std::array<Vector, 2>& reaches, double factor, const Cursor* parent, std::size_t edge) {
        const bool reveal = vertex.kind == graph::VertexKind::chance;
        const auto id = reveal ? vertex.branches[edge].child : vertex.children[edge];
        if (mode_ == RunMode::indexed) {
            if (!parent) throw std::runtime_error("indexed average child lacks its cursor");
            const auto next = reveal ? shadow_router_->advance_reveal(*parent, edge)
                                     : shadow_router_->advance_action(*parent, edge);
            average(id, empty_training_history_, reaches, factor, &next);
            return;
        }
        ++receipt_.legacy_training_history_extensions;
        const auto extended = reveal
            ? graph::Plan::extend_history(history, vertex.street, vertex.branches[edge].label)
            : graph::Plan::extend_history(history, vertex.actions[edge]);
        if (!parent) { average(id, extended, reaches, factor); return; }
        const auto next = reveal ? shadow_router_->advance_reveal(*parent, edge)
                                 : shadow_router_->advance_action(*parent, edge);
        average(id, extended, reaches, factor, &next);
    }
    void average(std::size_t id, const graph::History& history, const std::array<Vector, 2>& reaches,
                 double factor, const Cursor* cursor = nullptr) {
        const auto& vertex = plan_.graph().vertices[id];
        if (vertex.kind == graph::VertexKind::terminal) return;
        if (vertex.kind == graph::VertexKind::chance) {
            for (std::size_t edge = 0; edge < vertex.branches.size(); ++edge) {
                average_child(vertex, history, reaches, factor, cursor, edge);
            }
            return;
        }
        const auto slots = decision_locations(vertex.actor, history, vertex.actions, cursor);
        const auto count = vertex.children.size();
        const auto& mass = marginals_.at(callback_indexes(history, cursor))[vertex.actor];
        for (std::size_t i = 0; i < slots.size(); ++i) if (slots[i]) {
            Vector increment(count);
            for (std::size_t a = 0; a < count; ++a)
                increment[a] = mul(mul(mul(mass[i], reaches[vertex.actor][i]), current_[slots[i]->offset + a]), factor);
            stage(*slots[i], count, increment);
        }
        for (std::size_t a = 0; a < count; ++a) {
            auto changed = reaches;
            for (std::size_t i = 0; i < slots.size(); ++i)
                changed[vertex.actor][i] = mul(reaches[vertex.actor][i], slots[i]
                    ? current_[slots[i]->offset + a] : div(1.0, static_cast<double>(count)));
            average_child(vertex, history, changed, factor, cursor, a);
        }
    }
    void average_pass(double factor) {
        std::fill(seen_.begin(), seen_.end(), 0);
        if (shadow_router_) {
            const auto cursor = shadow_router_->root_cursor();
            average(plan_.graph().root_id, training_root_history(),
                {Vector(plan_.hand_counts()[0], 1.0), Vector(plan_.hand_counts()[1], 1.0)}, factor, &cursor);
        } else average(plan_.graph().root_id, plan_.graph().initial_history,
            {Vector(plan_.hand_counts()[0], 1.0), Vector(plan_.hand_counts()[1], 1.0)}, factor);
        for (std::size_t q = 0; q < plan_.rows().size(); ++q) {
            const auto& row = plan_.rows()[q];
            if (seen_[q] != row.expected_mask) throw std::runtime_error("incomplete native Q average coverage");
            receipt_.member_checks += row.orbit_size;
            for (std::size_t a = 0; a < row.count; ++a) add(sums_[row.offset + a], deltas_[row.offset + a]);
        }
        for (const auto& row : plan_.rows()) for (std::size_t a = 0; a < row.count; ++a)
            sums_[row.offset + a] = add(sums_[row.offset + a], deltas_[row.offset + a]);
    }

    graph::Plan& plan_;
    Limits limits_;
    Receipt receipt_;
    bool started_ = false;
    RunMode mode_ = RunMode::legacy;
    const graph::History empty_training_history_{};
    std::uint64_t construction_kernel_work_ = 0;
    std::unique_ptr<routing::IndexedRouting> shadow_router_;
    std::map<std::vector<std::size_t>, Marginals> marginals_;
    Vector regrets_, sums_, current_, deltas_;
    std::vector<std::uint32_t> seen_;
};
} // namespace openpoker::exact_selected_cfr
