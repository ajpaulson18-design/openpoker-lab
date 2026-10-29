#include "../../native/exact_public_history_index.hpp"

#include <iostream>
#include <limits>
#include <stdexcept>

namespace graph = openpoker::exact_public_graph;
namespace history_index = openpoker::exact_public_history_index;

void check(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
template<class Function>
void rejected(graph::ErrorCode expected, Function&& function) {
    try { function(); }
    catch (const graph::PlanError& error) { check(error.code() == expected, "wrong rejection code"); return; }
    throw std::runtime_error("expected rejection was absent");
}

int main() {
    try {
        constexpr std::uint64_t unit = 0x3ff0000000000000ULL;
        graph::Graph game;
        game.initial_history = {"flop@2c3c4c", "turn@5c", "river@6c"};
        game.vertices.push_back(graph::Vertex::decision(0,
            {{"z", 0, 0, false, "z"}, {"a", 0, 0, false, "a"}}, {1, 1}));
        game.vertices.push_back(graph::Vertex::terminal(graph::TerminalKind::showdown, 2, {unit, unit}));
        graph::Plan plan(std::move(game), {{{48, 49}, unit}}, {{{44, 45}, unit}}, {{{0, 4, 8, 12, 16}}}, 10);
        const std::array<graph::Card, 5> cards{0, 4, 8, 12, 16};
        const auto support = plan.prefix_support(cards);
        const auto& old = plan.prefix_board_indexes(plan.graph().initial_history);
        check(support.board_indexes.data() == old.data() && support.board_index_key == &old,
            "typed lookup copied or changed the stable board-index key");
        check(support.hands[0].size() == 1 && support.hands[1].size() == 1, "typed support lost original hands");
        for (std::size_t g = 0; g < plan.group().size(); ++g)
            check(plan.mapped_hand_index(0, g, 0) == 0, "mapped original hand changed");
        rejected(graph::ErrorCode::invalid_query, [&] { (void)plan.mapped_hand_index(2, 0, 0); });
        rejected(graph::ErrorCode::invalid_query, [&] { (void)plan.mapped_hand_index(0, plan.group().size(), 0); });
        rejected(graph::ErrorCode::invalid_query, [&] { (void)plan.mapped_hand_index(0, 0, 1); });
        const std::array<graph::Card, 3> duplicate{0, 4, 4}, unordered{4, 0, 8}, invalid{0, 4, 52};
        const std::array<graph::Card, 2> partial{0, 4};
        rejected(graph::ErrorCode::invalid_query, [&] { (void)plan.prefix_support(duplicate); });
        rejected(graph::ErrorCode::invalid_query, [&] { (void)plan.prefix_support(unordered); });
        rejected(graph::ErrorCode::invalid_query, [&] { (void)plan.prefix_support(invalid); });
        rejected(graph::ErrorCode::invalid_query, [&] { (void)plan.prefix_support(partial); });

        history_index::Limits limits;
        limits.external = {1234, 77};
        limits.query_schedule = history_index::QuerySchedule{1, 4, 1, 1};
        history_index::HistoryIndex route(plan, limits);
        const auto& receipt = route.receipt();
        const auto g = plan.group().size();
        const auto root_work = g * (3 * graph::kMaximumTokenBytes + 8);
        const auto edge_work = 8 + 8 * g;
        // Maximum degree two gives ceil_log2=1; this independent fixture
        // calculation must agree with actual charges at exact exhaustion.
        const auto route_work = 4 * (graph::kMaximumTokenBytes * 3 + 8 * g + 8);
        check(receipt.query_work_upper == 2 * root_work + edge_work + route_work,
            "future query work omitted or double-counted a route-internal root");
        check(receipt.query_cumulative_entries_upper == 2 * g * graph::kMaximumTokenBytes,
            "future query entry count differs from all root calls");
        check(receipt.combined_modeled_work_upper == plan.receipt().modeled_work_upper +
            receipt.index_modeled_work_upper + 1234 + receipt.query_work_upper, "combined work ledger differs");
        check(receipt.combined_peak_entries_upper == plan.receipt().retained_entries_upper +
            receipt.index_retained_entries_upper + receipt.index_scratch_entries_upper + 77 +
            receipt.query_cumulative_entries_upper, "combined entry ledger differs");
        const auto root = route.root_cursor();
        check(&route.vertex_at(root) == &plan.graph().vertices[plan.graph().root_id], "cursor vertex binding differs");
        check(route.advance_edge(root, 0).ordinal() == 2, "numeric advance reordered actual action position");
        auto history = plan.graph().initial_history; history.push_back("a");
        check(route.cursor_from_history(history).ordinal() == 1, "scheduled old history route differs");
        const auto counts = route.query_counts();
        check(counts.history_routes == 1 && counts.history_route_tokens == 4 &&
            counts.root_cursors == 1 && counts.edge_advances == 1, "operation counters differ from schedule");
        check(route.query_work_reserved() == receipt.query_work_upper &&
            route.inverse_query_entries_reserved() == receipt.query_cumulative_entries_upper,
            "actual charges differ at exact declared exhaustion");
        rejected(graph::ErrorCode::work_limit, [&] { (void)route.root_cursor(); });
        rejected(graph::ErrorCode::work_limit, [&] { (void)route.advance_edge(root, 1); });
        rejected(graph::ErrorCode::work_limit, [&] { (void)route.cursor_from_history(history); });
        rejected(graph::ErrorCode::invalid_query, [&] { (void)route.advance_token(root, "a"); });
        rejected(graph::ErrorCode::invalid_query, [&] { (void)route.history_at_ordinal(0); });
        history_index::Limits short_work = limits;
        short_work.max_combined_modeled_work = receipt.combined_modeled_work_upper - 1;
        rejected(graph::ErrorCode::work_limit, [&] { history_index::HistoryIndex denied(plan, short_work); });
        history_index::Limits short_entries = limits;
        short_entries.max_combined_entries = receipt.combined_peak_entries_upper - 1;
        rejected(graph::ErrorCode::storage_limit, [&] { history_index::HistoryIndex denied(plan, short_entries); });
        history_index::Limits overflow;
        overflow.query_schedule = history_index::QuerySchedule{std::numeric_limits<std::uint64_t>::max(), 0, 1, 0};
        rejected(graph::ErrorCode::work_limit, [&] { history_index::HistoryIndex denied(plan, overflow); });
        history_index::Limits zero;
        zero.query_schedule = history_index::QuerySchedule{};
        history_index::HistoryIndex no_queries(plan, zero);
        rejected(graph::ErrorCode::work_limit, [&] { (void)no_queries.root_cursor(); });
        history_index::HistoryIndex legacy(plan);
        check(!legacy.declared_query_schedule() && legacy.root_cursor().ordinal() == 0, "legacy dynamic behavior changed");
        rejected(graph::ErrorCode::invalid_query, [&] { (void)legacy.vertex_at(root); });
        std::cout << "ALL INDEX SCHEDULE AND TYPED SUPPORT CONTROLS PASSED\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "INDEX SCHEDULE CONTROL FAILURE: " << error.what() << '\n'; return 1;
    }
}
