#include "../../native/exact_indexed_routing.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace graph = openpoker::exact_public_graph;
namespace routing = openpoker::exact_indexed_routing;
namespace history_index = openpoker::exact_public_history_index;

using graph::Action;
using graph::Graph;
using graph::History;
using graph::Plan;
using graph::QRow;
using graph::SelectedBoard;
using graph::Street;
using graph::TerminalKind;
using graph::Vertex;
using graph::WeightedHand;

constexpr std::uint64_t kOne = 0x3ff0000000000000ULL;
constexpr SelectedBoard kBoard{{0, 4, 8, 12, 16}};

void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}

template<class Function>
void expect_error(graph::ErrorCode code, Function&& function, const char* message) {
    try {
        function();
    } catch (const graph::PlanError& error) {
        if (error.code() != code)
            throw std::runtime_error(std::string(message) + " (unexpected error code " +
                                     std::to_string(static_cast<int>(error.code())) + ")");
        return;
    }
    throw std::runtime_error(message);
}

Graph shared_reconvergent_graph() {
    const Action z{"z", 0, 0, false, "z"};
    const Action a{"a", 0, 0, false, "a"};
    const Action w{"w", 0, 0, false, "w"};
    const Action x{"x", 0, 0, false, "x"};
    const Action y{"y", 0, 0, false, "y"};
    Graph graph;
    graph.vertices.push_back(Vertex::decision(0, {z, a, w}, {1, 2, 1}));
    graph.vertices.push_back(Vertex::decision(1, {x, y}, {3, 4}));
    graph.vertices.push_back(Vertex::decision(1, {x, y}, {3, 4}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOne, kOne}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOne, kOne}));
    return graph;
}

Graph g2_turn_graph() {
    const Action bet{"bet", 0, 0, false, "bet"};
    const Action check{"check", 0, 0, false, "check"};
    Graph graph;
    graph.initial_history = {"flop@2c2d3h"};
    graph.vertices.push_back(Vertex::decision(0, {bet, check}, {1, 1}));
    graph.vertices.push_back(Vertex::chance(Street::turn, 5, {{"4d", 2}, {"4c", 3}}));
    graph.vertices.push_back(Vertex::decision(0, {bet, check}, {4, 5}));
    graph.vertices.push_back(Vertex::decision(0, {bet, check}, {4, 5}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOne, kOne}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOne, kOne}));
    return graph;
}

Graph all_streets_with_early_terminal() {
    const Action fold{"fold", 0, 0, false, "fold"};
    const Action play{"play", 0, 0, false, "play"};
    const Action call{"call", 0, 0, false, "call"};
    Graph graph;
    graph.vertices.push_back(Vertex::decision(0, {fold, play}, {1, 2}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::fold, 1, {kOne, kOne}));
    graph.vertices.push_back(Vertex::chance(Street::flop, 4, {{"2c3c4c", 3}}));
    graph.vertices.push_back(Vertex::chance(Street::turn, 5, {{"5c", 4}}));
    graph.vertices.push_back(Vertex::chance(Street::river, 6, {{"6c", 5}}));
    graph.vertices.push_back(Vertex::decision(1, {call}, {6}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOne, kOne}));
    return graph;
}

struct WalkCounts {
    std::size_t occurrences = 0;
    std::size_t decisions = 0;
};

void compare_location_vectors(const std::vector<std::optional<graph::RowLocation>>& indexed,
                              const std::vector<std::optional<graph::RowLocation>>& original) {
    require(indexed.size() == original.size(), "indexed output changed the original hand-vector length");
    for (std::size_t h = 0; h < indexed.size(); ++h) {
        require(indexed[h].has_value() == original[h].has_value(),
                "indexed router compacted or invented a support hole");
        if (indexed[h])
            require(*indexed[h] == *original[h],
                    "indexed q, action offset or distinct-member bit differs from the original route");
    }
}

void shadow_walk(const Plan& plan, const routing::IndexedRouting& indexed,
                 std::size_t vertex_id, History& history,
                 const routing::IndexedRouting::Cursor& cursor, WalkCounts& counts) {
    ++counts.occurrences;
    const auto& vertex = plan.graph().vertices[vertex_id];
    const auto indexed_prefix = indexed.prefix_board_indexes(cursor);
    const auto& old_prefix = plan.prefix_board_indexes(history);
    require(std::equal(indexed_prefix.begin(), indexed_prefix.end(), old_prefix.begin(), old_prefix.end()),
            "typed indexed prefix board vector differs from old history route");

    if (vertex.kind == graph::VertexKind::decision) {
        ++counts.decisions;
        const auto found = indexed.locate_decision_rows(cursor, vertex.actor, vertex.actions);
        const auto original = plan.locate_decision_rows(vertex.actor, history, vertex.actions);
        compare_location_vectors(found, original);
        for (std::size_t i = 0; i < vertex.actions.size(); ++i) {
            history.push_back(vertex.actions[i].token);
            const auto child = indexed.advance_action(cursor, i);
            shadow_walk(plan, indexed, vertex.children[i], history, child, counts);
            history.pop_back();
        }
    } else if (vertex.kind == graph::VertexKind::chance) {
        const auto prefix = vertex.street == Street::flop ? std::string("flop@") :
                            vertex.street == Street::turn ? std::string("turn@") : std::string("river@");
        for (std::size_t i = 0; i < vertex.branches.size(); ++i) {
            history.push_back(prefix + vertex.branches[i].label);
            const auto child = indexed.advance_reveal(cursor, i);
            shadow_walk(plan, indexed, vertex.branches[i].child, history, child, counts);
            history.pop_back();
        }
    }
}

history_index::ExternalReservation caller_reservation(const Plan& plan) {
    const auto depth = plan.graph_census().maximum_depth + plan.graph().initial_history.size();
    const auto max_hands = std::max(plan.hand_counts()[0], plan.hand_counts()[1]);
    const auto frames = depth + 3;
    const auto cursor_entries = frames * routing::kMaximumCursorLogicalEntries;
    const auto history_entries = depth * (graph::kMaximumTokenBytes + 1);
    const auto row_entries = (depth + 1) * 4 * max_hands;
    return {static_cast<std::uint64_t>(plan.graph_census().logical_visits) * 2'000 + 1'024,
            cursor_entries + history_entries + row_entries + 1'024};
}

void check_route_parity(Plan& plan, routing::RoutingSchedule schedule = {1, 1}) {
    routing::IndexedRouting indexed(plan, schedule, {}, caller_reservation(plan));
    auto cursor = indexed.root_cursor();
    auto history = plan.graph().initial_history;
    WalkCounts counts;
    shadow_walk(plan, indexed, plan.graph().root_id, history, cursor, counts);
    require(counts.occurrences == plan.graph_census().logical_visits,
            "bounded path walk did not visit the exact logical-occurrence census");
    const auto receipt = indexed.receipt_snapshot();
    require(receipt.numeric_map_entries_actual == plan.rows().size() &&
                receipt.original_q_histories_retained && receipt.r_lookup_entries == 0,
            "router did not retain exactly the numeric Q map and original Q histories");
    require(receipt.decision_lookup_calls_actual == counts.decisions &&
                receipt.prefix_lookup_calls_actual == counts.occurrences,
            "router actual query-call counters differ from the shadow walk");
    std::uint64_t history_tokens = 0;
    for (const auto& row : plan.rows()) history_tokens += row.key.history.size();
    require(receipt.history_route_calls_actual == plan.rows().size() &&
                receipt.history_route_tokens_actual == history_tokens,
            "numeric Q map construction route counters differ from the original rows");
    require(receipt.root_cursor_calls_actual == 1 &&
                receipt.edge_advance_calls_actual + 1 == plan.graph_census().logical_visits,
            "bounded shadow traversal root/edge counters differ from the logical graph walk");
    require(receipt.router_query_work_actual <= receipt.router_query_work_upper &&
                receipt.index_query_work_actual <= receipt.index_query_work_upper &&
                receipt.index_query_entries_actual <= receipt.index_query_entries_upper,
            "actual router/index query counters exceeded their preflight reservations");
    const auto minimum_setup_scratch = routing::kRouterFixedEntriesUpper +
        2 * routing::kMaximumCursorLogicalEntries + routing::kMaximumImageViewAndKeyEntries;
    const auto minimum_decision_scratch = routing::kRouterFixedEntriesUpper +
        4 * std::max(plan.hand_counts()[0], plan.hand_counts()[1]) +
        routing::kMaximumImageViewAndKeyEntries;
    require(receipt.router_setup_scratch_entries_upper >= minimum_setup_scratch &&
                receipt.router_query_scratch_entries_upper >= minimum_decision_scratch,
            "router scratch ledger did not include all fixed 24-map arrays");
    require(receipt.combined_modeled_work_upper <= receipt.work_limit &&
                receipt.combined_logical_entries_upper <= receipt.logical_entry_limit,
            "router receipt exceeds the original Plan/index combined ceilings");
}

void check_g1_shared_q_and_lexical_order() {
    std::vector<WeightedHand> sb{{{48, 49}, kOne}};
    std::vector<WeightedHand> bb{{{44, 45}, kOne}};
    std::vector<SelectedBoard> boards{kBoard};
    Plan plan(shared_reconvergent_graph(), std::move(sb), std::move(bb), std::move(boards), 10);
    check_route_parity(plan);
}

void check_private_swap_g2_initial_history_and_turn_prefix() {
    const std::vector<WeightedHand> sb{{{48, 49}, kOne}, {{48, 50}, kOne}, {{49, 50}, kOne}};
    const std::vector<WeightedHand> bb{{{44, 45}, kOne}, {{44, 46}, kOne}, {{45, 46}, kOne}};
    const std::vector<SelectedBoard> boards{{{0, 1, 6, 8, 14}}, {{0, 1, 6, 9, 14}}};
    Plan plan(g2_turn_graph(), sb, bb, boards, 10);
    require(plan.group().size() == 2, "private-swap fixture did not derive G2");
    bool has_fixed_row = false;
    bool has_two_member_row = false;
    for (const auto& row : plan.rows()) {
        has_fixed_row |= row.orbit_size == 1;
        has_two_member_row |= row.orbit_size == 2;
    }
    require(has_fixed_row && has_two_member_row,
            "G2 fixture did not cover both fixed-member and two-member Q row stabilizers");
    check_route_parity(plan);
}

void check_flop_turn_river_terminal_and_early_prefixes() {
    const std::vector<WeightedHand> sb{{{48, 49}, kOne}};
    const std::vector<WeightedHand> bb{{{44, 45}, kOne}};
    const std::vector<SelectedBoard> boards{kBoard};
    Plan plan(all_streets_with_early_terminal(), sb, bb, boards, 10);
    check_route_parity(plan);
}

void check_supported_hand_holes_and_failures() {
    const std::vector<WeightedHand> sb{{{0, 2}, kOne}, {{18, 20}, kOne}};
    const std::vector<WeightedHand> bb{{{24, 26}, kOne}, {{28, 30}, kOne}};
    const std::vector<SelectedBoard> boards{kBoard};
    Graph graph;
    const Action left{"left", 0, 0, false, "left"};
    const Action right{"right", 0, 0, false, "right"};
    graph.vertices.push_back(Vertex::decision(0, {left, right}, {1, 2}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::fold, 1, {kOne, kOne}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOne, kOne}));
    Plan plan(std::move(graph), sb, bb, boards, 10);
    routing::IndexedRouting indexed(plan, {1, 2}, {}, caller_reservation(plan));
    auto cursor = indexed.root_cursor();
    const auto& root = plan.graph().vertices[plan.graph().root_id];
    const auto locations = indexed.locate_decision_rows(cursor, 0, root.actions);
    require(locations.size() == sb.size() && !locations[0] && locations[1],
            "unsupported original hand was not preserved as an internal null hole");
    const auto old = plan.locate_decision_rows(0, plan.graph().initial_history, root.actions);
    compare_location_vectors(locations, old);

    expect_error(graph::ErrorCode::invalid_query,
        [&] { (void)indexed.locate_decision_rows(cursor, 1, root.actions); },
        "indexed router accepted an actor/menu mismatch");
    expect_error(graph::ErrorCode::invalid_query,
        [&] { (void)indexed.locate_decision_rows(cursor, 0, std::span<const Action>(root.actions.data(), 1)); },
        "indexed router accepted an incomplete ordered menu");

    routing::WholeLimits too_small;
    too_small.modeled_work = 1;
    expect_error(graph::ErrorCode::work_limit,
        [&] { routing::IndexedRouting rejected(plan, {1, 0}, too_small, {}); },
        "router/index combined admission accepted a work ceiling below its bounded scan floor");
}

void check_foreign_cursor_rejection() {
    const std::vector<WeightedHand> sb{{{48, 49}, kOne}};
    const std::vector<WeightedHand> bb{{{44, 45}, kOne}};
    const std::vector<SelectedBoard> boards{kBoard};
    Plan first_plan(shared_reconvergent_graph(), sb, bb, boards, 10);
    Plan second_plan(shared_reconvergent_graph(), sb, bb, boards, 10);
    routing::IndexedRouting first(first_plan, {1, 0}, {}, caller_reservation(first_plan));
    routing::IndexedRouting second(second_plan, {1, 0}, {}, caller_reservation(second_plan));
    const auto foreign = first.root_cursor();
    expect_error(graph::ErrorCode::invalid_query,
        [&] { (void)second.prefix_board_indexes(foreign); },
        "foreign router cursor was accepted for typed prefix lookup");
}

int main() {
    try {
        check_g1_shared_q_and_lexical_order();
        check_private_swap_g2_initial_history_and_turn_prefix();
        check_flop_turn_river_terminal_and_early_prefixes();
        check_supported_hand_holes_and_failures();
        check_foreign_cursor_rejection();
        std::cout << "ALL INDEXED ROUTING CONTROLS PASSED\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "INDEXED ROUTING CONTROL FAILURE: " << error.what() << '\n';
        return 1;
    }
}
