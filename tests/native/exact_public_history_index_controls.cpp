#include "../../native/exact_public_history_index.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace history_index = openpoker::exact_public_history_index;
namespace public_graph = openpoker::exact_public_graph;

using public_graph::Action;
using public_graph::Graph;
using public_graph::History;
using public_graph::Plan;
using public_graph::SelectedBoard;
using public_graph::Street;
using public_graph::TerminalKind;
using public_graph::Vertex;
using public_graph::WeightedHand;

constexpr std::uint64_t kOneBits = 0x3ff0000000000000ULL;
constexpr std::array<WeightedHand, 1> kSb{{{{48, 49}, kOneBits}}};
constexpr std::array<WeightedHand, 1> kBb{{{{44, 45}, kOneBits}}};
constexpr std::array<SelectedBoard, 1> kBoard{{{{0, 4, 8, 12, 16}}}};

void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}

template<class Function>
void expect_error(public_graph::ErrorCode code, Function&& function, const char* message) {
    try {
        function();
    } catch (const public_graph::PlanError& error) {
        require(error.code() == code, message);
        return;
    }
    throw std::runtime_error(message);
}

Graph reconvergent_duplicate_graph() {
    const Action z{"z", 0, 0, false, "z"};
    const Action a{"a", 0, 0, false, "a"};
    const Action w{"w", 0, 0, false, "w"};
    const Action x{"x", 0, 0, false, "x"};
    const Action y{"y", 0, 0, false, "y"};
    Graph graph;
    graph.vertices.push_back(Vertex::decision(0, {z, a, w}, {1, 2, 1}));
    graph.vertices.push_back(Vertex::decision(1, {x, y}, {3, 4}));
    graph.vertices.push_back(Vertex::decision(1, {x, y}, {3, 4}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOneBits, kOneBits}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOneBits, kOneBits}));
    return graph;
}

Graph paired_reveal_graph() {
    const Action bet{"bet", 0, 0, false, "bet"};
    const Action check{"check", 0, 0, false, "check"};
    Graph graph;
    graph.initial_history = {"flop@2c2d3h"};
    graph.vertices.push_back(Vertex::chance(Street::turn, 5, {{"4d", 1}, {"4c", 2}}));
    graph.vertices.push_back(Vertex::decision(0, {bet, check}, {3, 4}));
    graph.vertices.push_back(Vertex::decision(0, {bet, check}, {3, 4}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOneBits, kOneBits}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOneBits, kOneBits}));
    return graph;
}

Graph duplicate_chance_signature_graph() {
    const Action right{"right", 0, 0, false, "right"};
    const Action left{"left", 0, 0, false, "left"};
    Graph graph;
    graph.initial_history = {"flop@2c3c4h", "turn@5c"};
    graph.vertices.push_back(Vertex::decision(0, {right, left}, {2, 1}));
    graph.vertices.push_back(Vertex::chance(Street::river, 6, {{"6c", 3}, {"6d", 4}}));
    graph.vertices.push_back(Vertex::chance(Street::river, 6, {{"6d", 4}, {"6c", 3}}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOneBits, kOneBits}));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {0x4000000000000000ULL, kOneBits}));
    return graph;
}

void enumerate(const Graph& graph, std::size_t vertex_id, History& history,
               std::vector<History>& histories) {
    histories.push_back(history);
    const auto& vertex = graph.vertices[vertex_id];
    if (vertex.kind == public_graph::VertexKind::decision) {
        for (std::size_t i = 0; i < vertex.actions.size(); ++i) {
            history.push_back(vertex.actions[i].token);
            enumerate(graph, vertex.children[i], history, histories);
            history.pop_back();
        }
    } else if (vertex.kind == public_graph::VertexKind::chance) {
        const char* prefix = vertex.street == Street::flop ? "flop@" :
                             vertex.street == Street::turn ? "turn@" : "river@";
        for (const auto& branch : vertex.branches) {
            history.push_back(std::string(prefix) + branch.label);
            enumerate(graph, branch.child, history, histories);
            history.pop_back();
        }
    }
}

void check_all_ordinals(const Plan& plan, const history_index::HistoryIndex& index) {
    std::vector<History> histories;
    auto initial = plan.graph().initial_history;
    enumerate(plan.graph(), plan.graph().root_id, initial, histories);
    std::sort(histories.begin(), histories.end());
    require(histories.size() == plan.graph_census().logical_visits,
            "literal history count differs from the admitted logical census");
    for (std::size_t i = 0; i < histories.size(); ++i) {
        const auto cursor = index.cursor_from_history(histories[i]);
        require(cursor.ordinal() == i, "cursor ordinal differs from sorted literal full history");
        require(index.history_at_ordinal(i) == histories[i], "ordinal inverse differs from sorted literal full history");
    }
}

void check_retained_ledger(const Plan& plan, const history_index::HistoryIndex& index) {
    const auto& receipt = index.receipt();
    static_assert(history_index::kVertexClassScalarEntries == 1);
    static_assert(history_index::kClassRecordScalarEntries == 4);
    static_assert(history_index::kRawVertexRecordScalarEntries == 2);
    static_assert(history_index::kClassEdgeScalarEntries == 2);
    static_assert(history_index::kRawEdgeScalarEntries == 2);
    static_assert(history_index::kMappedTransitionScalarEntries == 6);
    static_assert(history_index::kClassEdgeUpperSlackEntries == 1);
    static_assert(history_index::kMappedTransitionUpperSlackEntries == 2);
    const auto fixed = receipt.index_fixed_bookkeeping_entries_actual;
    const auto actual = fixed + receipt.vertex_class_entries_actual +
        receipt.class_record_entries_actual + receipt.raw_vertex_record_entries_actual +
        receipt.class_edge_entries_actual + receipt.class_edge_string_headers_actual +
        receipt.class_lex_order_entries_actual + receipt.raw_edge_entries_actual +
        receipt.raw_edge_string_headers_actual + receipt.raw_lex_order_entries_actual +
        receipt.suit_class_entries_actual + receipt.transformed_transition_entries_actual +
        receipt.retained_token_bytes_actual;
    require(fixed == history_index::kFixedBookkeepingEntriesUpper,
            "fixed object/receipt bookkeeping reserve is not reported explicitly");
    require(receipt.vertex_class_entries_actual ==
                history_index::kVertexClassScalarEntries * receipt.graph_vertices,
            "vertex-class array length is absent from the retained ledger");
    require(receipt.class_record_entries_actual ==
                history_index::kClassRecordScalarEntries * receipt.continuation_classes,
            "ClassRecord scalar fields are absent from the retained ledger");
    require(receipt.raw_vertex_record_entries_actual ==
                history_index::kRawVertexRecordScalarEntries * receipt.graph_vertices,
            "raw-vertex record fields are absent from the retained ledger");
    require(receipt.class_edge_entries_actual ==
                history_index::kClassEdgeScalarEntries * receipt.class_edge_entries &&
                receipt.class_edge_string_headers_actual == receipt.class_edge_entries &&
                receipt.class_lex_order_entries_actual == receipt.class_edge_entries,
            "canonical edge payload, string-header or lex-index array is miscounted");
    require(receipt.raw_edge_entries_actual ==
                history_index::kRawEdgeScalarEntries * receipt.raw_edge_entries &&
                receipt.raw_edge_string_headers_actual == receipt.raw_edge_entries &&
                receipt.raw_lex_order_entries_actual == receipt.raw_edge_entries,
            "raw edge payload, string-header or lex-index array is miscounted");
    require(receipt.suit_class_entries_actual == receipt.suit_class_entries &&
                receipt.transformed_transition_entries_actual ==
                    history_index::kMappedTransitionScalarEntries * receipt.transformed_transition_entries,
            "suit-map or transition arrays are miscounted");
    require(receipt.retained_token_bytes_actual == receipt.retained_token_bytes,
            "retained token character count is inconsistent");
    require(receipt.index_retained_entries_actual == actual &&
                receipt.index_retained_entries_actual <= receipt.index_retained_entries_upper,
            "actual logical retained-entry ledger exceeds or differs from its reservation");

    const auto expected_fixed = history_index::kFixedBookkeepingEntriesUpper;
    const auto expected_vertices = (history_index::kVertexClassScalarEntries +
        history_index::kClassRecordScalarEntries + history_index::kRawVertexRecordScalarEntries) *
        receipt.graph_vertices;
    const auto expected_classes = (history_index::kClassEdgeScalarEntries + 1 + 1 +
        history_index::kClassEdgeUpperSlackEntries) * plan.graph_census().edges;
    const auto expected_raw_edges = (history_index::kRawEdgeScalarEntries + 1 + 1) *
        plan.graph_census().edges;
    const auto expected_suit_classes = receipt.suit_maps * receipt.graph_vertices;
    const auto expected_transitions = (history_index::kMappedTransitionScalarEntries +
        history_index::kMappedTransitionUpperSlackEntries) * receipt.suit_maps * plan.graph_census().edges;
    const auto upper = expected_fixed + expected_vertices + expected_classes + expected_raw_edges +
        expected_suit_classes + expected_transitions + receipt.index_token_bytes_entries_upper;
    require(receipt.index_fixed_bookkeeping_entries_upper == expected_fixed &&
                receipt.index_vertex_record_entries_upper == expected_vertices &&
                receipt.index_class_edge_entries_upper == expected_classes &&
                receipt.index_raw_edge_entries_upper == expected_raw_edges &&
                receipt.index_suit_class_entries_upper == expected_suit_classes &&
                receipt.index_transformed_transition_entries_upper == expected_transitions &&
                receipt.index_retained_entries_upper == upper,
            "named preflight retained-entry components do not sum to the admitted upper bound");
}

void check_reconvergence_and_duplicate_signatures() {
    Plan plan(reconvergent_duplicate_graph(), std::vector<WeightedHand>(kSb.begin(), kSb.end()),
              std::vector<WeightedHand>(kBb.begin(), kBb.end()),
              std::vector<SelectedBoard>(kBoard.begin(), kBoard.end()), 10);
    history_index::HistoryIndex index(plan);
    const auto& receipt = index.receipt();
    require(receipt.logical_occurrences == 10, "unfolded census is incorrect");
    require(receipt.continuation_classes == 3, "exact duplicate signatures did not share continuation classes");
    require(receipt.expanded_history_table_entries == 0 && receipt.physical_row_lookup_table_entries == 0,
            "index unexpectedly retained an occurrence history or physical-row table");
    require(receipt.class_edge_entries == 5 && receipt.raw_edge_entries == 7,
            "index edge arrays differ from the compact graph shape");
    check_retained_ledger(plan, index);
    const auto root = index.root_cursor();
    const auto z = index.advance_action(root, 0);
    const auto a = index.advance_action(root, 1);
    const auto w = index.advance_action(root, 2);
    require(z.ordinal() == 7 && a.ordinal() == 1 && w.ordinal() == 4,
            "lexical sibling offsets ignored history order or reconvergence");
    require(z.image_ordinal(0) == 7 && a.image_ordinal(0) == 1,
            "identity image ordinal differs from actual ordinal");
    check_all_ordinals(plan, index);
}

void check_suit_transition_and_visible_prefix() {
    constexpr std::uint64_t money = kOneBits;
    const std::vector<WeightedHand> sb{{{48, 50}, money}, {{49, 50}, money}};
    const std::vector<WeightedHand> bb{{{44, 46}, money}, {{45, 46}, money}};
    const std::vector<SelectedBoard> boards{{{0, 1, 6, 8, 14}}, {{0, 1, 6, 9, 14}}};
    Plan plan(paired_reveal_graph(), sb, bb, boards, 10);
    require(plan.group().size() == 2, "paired c/d fixture did not derive the expected G2 group");
    history_index::HistoryIndex index(plan);
    check_retained_ledger(plan, index);
    const auto root = index.root_cursor();
    const auto prefix = root.visible_prefix();
    require(prefix.size == 3 && prefix.cards[0] == 0 && prefix.cards[1] == 1 && prefix.cards[2] == 6,
            "fixed initial flop prefix ID is not canonical");
    const auto first_branch = index.advance_reveal(root, 0); // input order is 4d then 4c
    const auto second_branch = index.advance_reveal(root, 1);
    require(first_branch.ordinal() == 4 && first_branch.image_ordinal(1) == 1,
            "transformed branch offset did not follow lexical suit-image edge");
    require(second_branch.ordinal() == 1 && second_branch.image_ordinal(1) == 4,
            "second transformed branch offset is incorrect");
    require(first_branch.visible_prefix().size == 4 && first_branch.visible_prefix().cards[3] == 9,
            "actual visible turn prefix was not advanced");
    require(first_branch.visible_prefix(1).size == 4 && first_branch.visible_prefix(1).cards[3] == 8,
            "suit-image visible turn prefix was not advanced");
    const auto completed = index.advance_action(first_branch, 1);
    History transformed;
    for (const auto& token : plan.graph().initial_history)
        transformed.push_back(public_graph::detail::transform_reveal(token, plan.group()[1]));
    transformed.push_back(public_graph::detail::transform_reveal("turn@4d", plan.group()[1]));
    transformed.push_back("check");
    const auto literal_image = index.cursor_from_history(transformed);
    require(completed.image_ordinal(1) == literal_image.ordinal(),
            "incremental transformed transitions differ from literal history transformation");
    check_all_ordinals(plan, index);
}

Graph linear_graph(std::size_t decision_count) {
    Graph graph;
    graph.vertices.reserve(decision_count + 1);
    for (std::size_t i = 0; i < decision_count; ++i) {
        const Action action{"continue", 0, 0, false, "step-" + std::to_string(i)};
        graph.vertices.push_back(Vertex::decision(static_cast<std::uint8_t>(i % 2), {action}, {i + 1}));
    }
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOneBits, kOneBits}));
    return graph;
}

void check_tall_graph_retained_ledger() {
    Plan plan(linear_graph(48), std::vector<WeightedHand>(kSb.begin(), kSb.end()),
              std::vector<WeightedHand>(kBb.begin(), kBb.end()),
              std::vector<SelectedBoard>(kBoard.begin(), kBoard.end()), 10);
    history_index::HistoryIndex index(plan);
    check_retained_ledger(plan, index);
    require(index.receipt().graph_vertices == 49 && index.receipt().graph_edges == 48,
            "tall linear control did not retain the intended low-edge, many-vertex shape");
}

void check_duplicate_chance_input_order() {
    const std::vector<WeightedHand> sb{{{48, 49}, kOneBits}};
    const std::vector<WeightedHand> bb{{{44, 45}, kOneBits}};
    const std::vector<SelectedBoard> boards{{{0, 4, 10, 12, 16}}, {{0, 4, 10, 12, 17}}};
    Plan plan(duplicate_chance_signature_graph(), sb, bb, boards, 10);
    history_index::HistoryIndex index(plan);
    require(index.receipt().continuation_classes == 4,
            "exactly matching chance signatures with reversed input order were not interned");
    const auto root = index.root_cursor();
    const auto left = index.advance_action(root, 1);
    const auto right = index.advance_action(root, 0);
    require(left.ordinal() == 1 && right.ordinal() == 4,
            "root action offsets do not follow exact lexical history order");
    const auto left_first_input = index.advance_reveal(left, 0); // 6c
    const auto right_first_input = index.advance_reveal(right, 0); // 6d
    require(left_first_input.ordinal() == 2 && right_first_input.ordinal() == 6,
            "duplicate chance vertex input order was not preserved independently of lexical offsets");
    check_all_ordinals(plan, index);
}

void check_larger_suit_group() {
    const std::vector<WeightedHand> sb{{{48, 49}, kOneBits}, {{48, 50}, kOneBits}, {{48, 51}, kOneBits}};
    const std::vector<WeightedHand> bb{{{44, 45}, kOneBits}, {{44, 46}, kOneBits}, {{44, 47}, kOneBits}};
    // Three permuted suits stay together on the flop; club remains fixed on
    // turn and river, yielding the exact six-element S3 public stabilizer.
    const std::vector<SelectedBoard> boards{{{1, 2, 3, 0, 4}}};
    Plan plan(reconvergent_duplicate_graph(), sb, bb, boards, 10);
    require(plan.group().size() == 6, "symmetric fixture did not derive its six-map S3 stabilizer");
    history_index::HistoryIndex index(plan);
    const auto root = index.root_cursor();
    const auto action = index.advance_action(root, 1);
    for (std::size_t g = 0; g < plan.group().size(); ++g)
        require(action.image_ordinal(g) == action.ordinal(), "nontrivial suit image changed an action-only path ordinal");
    check_all_ordinals(plan, index);
}

std::string flop_label(const SelectedBoard& board) {
    return public_graph::detail::card_text(board.cards[0]) +
           public_graph::detail::card_text(board.cards[1]) +
           public_graph::detail::card_text(board.cards[2]);
}

public_graph::SuitMap compose_maps(const public_graph::SuitMap& after,
                                   const public_graph::SuitMap& before) {
    public_graph::SuitMap result;
    for (std::size_t suit = 0; suit < result.image.size(); ++suit)
        result.image[suit] = after.image[before.image[suit]];
    return result;
}

History transform_history(const History& source, const public_graph::SuitMap& mapping) {
    History result;
    result.reserve(source.size());
    for (const auto& token : source)
        result.push_back(public_graph::detail::transform_reveal(token, mapping));
    return result;
}

void check_s3_reveal_composition() {
    const std::uint64_t money = kOneBits;
    const std::vector<WeightedHand> sb{{{48, 49}, money}, {{48, 50}, money}, {{48, 51}, money}};
    const std::vector<WeightedHand> bb{{{44, 45}, money}, {{44, 46}, money}, {{44, 47}, money}};

    // The six boards are the S3 suit orbit of 2d3h4s; clubs stay fixed on
    // the turn and river. Every transformed flop is a distinct chance edge.
    std::vector<SelectedBoard> boards;
    std::array<std::uint8_t, 3> suits{1, 2, 3};
    do {
        SelectedBoard board{{suits[0], static_cast<public_graph::Card>(4 + suits[1]),
                             static_cast<public_graph::Card>(8 + suits[2]), 12, 16}};
        std::sort(board.cards.begin(), board.cards.begin() + 3);
        boards.push_back(board);
    } while (std::next_permutation(suits.begin(), suits.end()));

    std::vector<std::string> labels;
    labels.reserve(boards.size());
    for (const auto& board : boards) labels.push_back(flop_label(board));
    std::sort(labels.begin(), labels.end());
    std::vector<public_graph::Branch> branches;
    branches.reserve(labels.size());
    for (std::size_t i = 0; i < labels.size(); ++i) branches.emplace_back(labels[i], 1);
    Graph graph;
    graph.vertices.push_back(Vertex::chance(Street::flop, 4, std::move(branches)));
    graph.vertices.push_back(Vertex::terminal(TerminalKind::showdown, 2, {kOneBits, kOneBits}));

    Plan plan(std::move(graph), sb, bb, boards, 10);
    require(plan.group().size() == 6, "reveal-composition fixture did not derive its full S3 group");
    history_index::HistoryIndex index(plan);
    const auto root = index.root_cursor();
    for (std::size_t branch = 0; branch < labels.size(); ++branch) {
        const History observed{"flop@" + labels[branch]};
        const auto cursor = index.advance_reveal(root, branch);
        require(cursor.ordinal() == index.cursor_from_history(observed).ordinal(),
                "observed S3 flop edge disagrees with its literal path ordinal");

        for (std::size_t g = 0; g < plan.group().size(); ++g) {
            const auto history_g = transform_history(observed, plan.group()[g]);
            const auto cursor_g = index.cursor_from_history(history_g);
            require(cursor.image_ordinal(g) == cursor_g.ordinal(),
                    "incremental S3 image differs from the literal transformed reveal");
            require(cursor.visible_prefix(g) == cursor_g.visible_prefix(),
                    "S3 image visible prefix differs from its literal transformed reveal");

            for (std::size_t h = 0; h < plan.group().size(); ++h) {
                const auto composed = compose_maps(plan.group()[h], plan.group()[g]);
                const auto composed_it = std::find_if(plan.group().begin(), plan.group().end(),
                    [&](const auto& item) { return item.image == composed.image; });
                require(composed_it != plan.group().end(), "S3 group is not closed under image composition");
                const auto composed_index = static_cast<std::size_t>(composed_it - plan.group().begin());
                const auto literal_composed = transform_history(observed, composed);
                const auto cursor_composed = index.cursor_from_history(literal_composed);
                require(cursor_g.image_ordinal(h) == cursor.image_ordinal(composed_index) &&
                            cursor_g.image_ordinal(h) == cursor_composed.ordinal(),
                        "incremental noncommuting S3 reveal composition differs from the literal route");
                require(cursor_g.visible_prefix(h) == cursor.visible_prefix(composed_index) &&
                            cursor_g.visible_prefix(h) == cursor_composed.visible_prefix(),
                        "composed S3 visible prefix differs from the literal route");
            }
        }
    }
}

void check_limits_and_owner_binding() {
    Plan first(reconvergent_duplicate_graph(), std::vector<WeightedHand>(kSb.begin(), kSb.end()),
               std::vector<WeightedHand>(kBb.begin(), kBb.end()),
               std::vector<SelectedBoard>(kBoard.begin(), kBoard.end()), 10);
    Plan second(reconvergent_duplicate_graph(), std::vector<WeightedHand>(kSb.begin(), kSb.end()),
                std::vector<WeightedHand>(kBb.begin(), kBb.end()),
                std::vector<SelectedBoard>(kBoard.begin(), kBoard.end()), 10);
    history_index::HistoryIndex first_index(first);
    history_index::HistoryIndex second_index(second);
    const auto cursor = first_index.root_cursor();
    expect_error(public_graph::ErrorCode::invalid_query,
        [&] { (void)second_index.advance_edge(cursor, 0); }, "cross-index cursor was accepted");
    expect_error(public_graph::ErrorCode::invalid_query,
        [&] { (void)first_index.advance_token(cursor, "absent"); }, "unknown history token was accepted");
    expect_error(public_graph::ErrorCode::invalid_query,
        [&] { (void)first_index.history_at_ordinal(std::numeric_limits<std::uint64_t>::max()); },
        "overflow-sized ordinal was accepted");

    history_index::Limits low_work;
    low_work.max_combined_modeled_work = first.receipt().modeled_work_upper;
    expect_error(public_graph::ErrorCode::work_limit,
        [&] { history_index::HistoryIndex rejected(first, low_work); },
        "index input scan was not rejected against the Plan's remaining work");
    history_index::Limits low_storage;
    low_storage.max_combined_entries = first.receipt().retained_entries_upper;
    expect_error(public_graph::ErrorCode::storage_limit,
        [&] { history_index::HistoryIndex rejected(first, low_storage); },
        "index storage was not rejected against the Plan's remaining entries");
    history_index::Limits widened;
    widened.max_combined_modeled_work = public_graph::kMaximumModeledWork + 1ULL;
    expect_error(public_graph::ErrorCode::invalid_limits,
        [&] { history_index::HistoryIndex rejected(first, widened); },
        "history-index work ceiling was increased above the existing cap");
}

int main() {
    try {
        check_reconvergence_and_duplicate_signatures();
        check_tall_graph_retained_ledger();
        check_suit_transition_and_visible_prefix();
        check_duplicate_chance_input_order();
        check_larger_suit_group();
        check_s3_reveal_composition();
        check_limits_and_owner_binding();
        std::cout << "ALL HISTORY INDEX CONTROLS PASSED\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "HISTORY INDEX CONTROL FAILURE: " << error.what() << '\n';
        return 1;
    }
}
