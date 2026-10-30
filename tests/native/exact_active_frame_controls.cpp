#define main history_reference_controls_main
#include "exact_public_history_index_controls.cpp"
#undef main
#include <optional>

using history_index::TraversalWorkspace;
using history_index::FrameView;

void compare_images(const history_index::HistoryIndex::Cursor& old, const FrameView& view) {
    require(old.image_count() == view.image_count(), "image count differs");
    for (std::size_t g = 0; g < old.image_count(); ++g) {
        require(old.image_ordinal(g) == view.image_ordinal(g), "image ordinal differs");
        require(old.visible_prefix(g) == view.visible_prefix(g), "visible prefix differs");
    }
}
void walk(const history_index::HistoryIndex& index, TraversalWorkspace& workspace,
          const history_index::HistoryIndex::Cursor& old, const FrameView& view) {
    compare_images(old, view);
    const auto& vertex = index.vertex_at(view);
    require(&vertex == &index.vertex_at(old), "raw vertex differs");
    const auto n = vertex.kind == public_graph::VertexKind::decision ? vertex.actions.size() :
                   vertex.kind == public_graph::VertexKind::chance ? vertex.branches.size() : 0;
    for (std::size_t i = 0; i < n; ++i) {
        auto next = vertex.kind == public_graph::VertexKind::decision ? workspace.advance_action(view, i) : workspace.advance_reveal(view, i);
        const auto reference = vertex.kind == public_graph::VertexKind::decision ? index.advance_action(old, i) : index.advance_reveal(old, i);
        walk(index, workspace, reference, next.view());
    }
}
void exercise(Plan& plan) {
    history_index::HistoryIndex index(plan);
    const auto depth = plan.graph_census().maximum_depth;
    const auto r = TraversalWorkspace::reservation(depth, plan.group().size());
    require(r.frame_count == depth + 1 && r.image_slots == r.frame_count * plan.group().size(), "active group reservation wrong");
    expect_error(public_graph::ErrorCode::storage_limit, [&] { TraversalWorkspace x(index, depth, public_graph::kMaximumModeledWork, r.retained_entries_upper - 1); }, "workspace storage cap");
    TraversalWorkspace workspace(index, depth);
    auto root = workspace.root();
    const auto root_view = root.view();
    expect_error(public_graph::ErrorCode::invalid_query, [&] { auto x = workspace.root(); }, "duplicate root");
    const auto before = index.query_counts();
    expect_error(public_graph::ErrorCode::invalid_query, [&] { auto x = workspace.advance_action(root_view, 9999); }, "bad edge");
    require(index.query_counts().edge_advances == before.edge_advances, "bad edge consumed schedule");
    walk(index, workspace, index.root_cursor(), root_view);
    if (depth > 0 && index.vertex_at(root_view).kind == public_graph::VertexKind::decision) {
        std::optional<FrameView> stale;
        {
            auto child = workspace.advance_action(root_view, 0); stale.emplace(child.view());
            expect_error(public_graph::ErrorCode::invalid_query, [&] { auto other = workspace.advance_action(root_view, 0); }, "active sibling accepted");
        }
        expect_error(public_graph::ErrorCode::invalid_query, [&] { (void)stale->ordinal(); }, "stale frame accepted");
        auto child = workspace.advance_action(root_view, 0);
        expect_error(public_graph::ErrorCode::invalid_query, [&] { (void)stale->ordinal(); }, "reused slot revived stale frame");
    }
    history_index::HistoryIndex other(plan);
    expect_error(public_graph::ErrorCode::invalid_query, [&] { (void)other.vertex_at(root_view); }, "foreign index accepted");
    TraversalWorkspace foreign(other, depth);
    expect_error(public_graph::ErrorCode::invalid_query, [&] { auto x = foreign.advance_action(root_view, 0); }, "foreign workspace accepted");
}
int main() {
    try {
        Plan first(reconvergent_duplicate_graph(), std::vector<WeightedHand>(kSb.begin(), kSb.end()), std::vector<WeightedHand>{{{44, 46}, kOneBits}}, std::vector<SelectedBoard>(kBoard.begin(), kBoard.end()), 10);
        require(first.group().size() == 1, "G1 fixture"); exercise(first);
        const std::vector<WeightedHand> sb{{{48, 50}, kOneBits}, {{49, 50}, kOneBits}};
        const std::vector<WeightedHand> bb{{{44, 46}, kOneBits}, {{45, 46}, kOneBits}};
        const std::vector<SelectedBoard> boards{{{0, 1, 6, 8, 14}}, {{0, 1, 6, 9, 14}}};
        Plan second(paired_reveal_graph(), sb, bb, boards, 10); require(second.group().size() == 2, "G2 fixture"); exercise(second);
        {
            const std::vector<WeightedHand> six_sb{{{48,49},kOneBits},{{48,50},kOneBits},{{48,51},kOneBits}};
            const std::vector<WeightedHand> six_bb{{{44,45},kOneBits},{{44,46},kOneBits},{{44,47},kOneBits}};
            std::vector<SelectedBoard> six_boards;
            std::array<std::uint8_t,3> suits{1,2,3};
            do {
                SelectedBoard b{{suits[0],static_cast<public_graph::Card>(4+suits[1]),static_cast<public_graph::Card>(8+suits[2]),12,16}};
                std::sort(b.cards.begin(),b.cards.begin()+3); six_boards.push_back(b);
            } while (std::next_permutation(suits.begin(),suits.end()));
            std::vector<std::string> labels;
            for (const auto& b : six_boards) labels.push_back(flop_label(b));
            std::sort(labels.begin(),labels.end());
            std::vector<public_graph::Branch> branches;
            for (const auto& label : labels) branches.emplace_back(label,1);
            Graph g; g.vertices.push_back(Vertex::chance(Street::flop,4,std::move(branches)));
            g.vertices.push_back(Vertex::terminal(TerminalKind::showdown,2,{kOneBits,kOneBits}));
            Plan six(std::move(g),six_sb,six_bb,six_boards,10);
            require(six.group().size()==6,"G6 fixture"); exercise(six);
        }
        {
            history_index::HistoryIndex index(first); TraversalWorkspace workspace(index,first.graph_census().maximum_depth);
            std::optional<TraversalWorkspace::Lease> parent; parent.emplace(workspace.root());
            auto child=workspace.advance_action(parent->view(),0); auto old=child.view(); parent.reset();
            expect_error(public_graph::ErrorCode::invalid_query,[&]{(void)old.ordinal();},"cascade did not invalidate child");
            auto new_root=workspace.root();
            require(workspace.counts().released_frames==2,"cascade release count");
        }
        {
            Graph g; g.vertices.push_back(Vertex::terminal(TerminalKind::showdown,2,{kOneBits,kOneBits}));
            Plan terminal(std::move(g),std::vector<WeightedHand>(kSb.begin(),kSb.end()),std::vector<WeightedHand>(kBb.begin(),kBb.end()),std::vector<SelectedBoard>(kBoard.begin(),kBoard.end()),10);
            require(terminal.graph_census().maximum_depth==0,"terminal fixture depth"); exercise(terminal);
        }
        {
            history_index::HistoryIndex index(first); TraversalWorkspace workspace(index,first.graph_census().maximum_depth);
            auto root=workspace.root(); std::optional<FrameView> stale;
            try { auto child=workspace.advance_action(root.view(),0); stale.emplace(child.view()); throw std::runtime_error("injected"); }
            catch (const std::runtime_error&) {}
            expect_error(public_graph::ErrorCode::invalid_query,[&]{(void)stale->ordinal();},"exception did not release child");
            auto next=workspace.advance_action(root.view(),0); (void)next.view();
        }
        {
            const auto r=TraversalWorkspace::reservation(first.graph_census().maximum_depth,first.group().size());
            history_index::HistoryIndex index(first);
            expect_error(public_graph::ErrorCode::work_limit,[&]{TraversalWorkspace w(index,first.graph_census().maximum_depth,r.setup_work_upper-1,public_graph::kMaximumRetainedEntries);},"workspace work cap");
            expect_error(public_graph::ErrorCode::invalid_limits,[&]{TraversalWorkspace w(index,first.graph_census().maximum_depth,public_graph::kMaximumModeledWork+1,public_graph::kMaximumRetainedEntries);},"workspace widened work cap");
            expect_error(public_graph::ErrorCode::invalid_limits,[&]{TraversalWorkspace w(index,0);},"workspace depth below graph");
        }
        std::cout << "ALL ACTIVE FRAME CONTROLS PASSED\n"; return 0;
    } catch (const std::exception& e) { std::cerr << "ACTIVE FRAME FAILURE: " << e.what() << '\n'; return 1; }
}
