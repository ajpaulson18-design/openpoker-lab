#define main indexed_reference_controls_main
#include "exact_indexed_routing_controls.cpp"
#undef main

using FrameWorkspace = history_index::TraversalWorkspace;
using FrameView = history_index::FrameView;

void frame_walk(const Plan& plan, const routing::IndexedRouting& indexed, FrameWorkspace& workspace,
                const routing::IndexedRouting& reference, std::size_t vertex_id, History& history,
                const FrameView& frame, const routing::IndexedRouting::Cursor& cursor, bool average, std::vector<std::uint32_t>& masks) {
    const auto& vertex = plan.graph().vertices[vertex_id];
    if ((average && vertex.kind == graph::VertexKind::decision) || (!average && vertex.kind == graph::VertexKind::terminal)) {
        const auto& a=indexed.prefix_board_indexes(frame); const auto& b=reference.prefix_board_indexes(cursor);
        require(a==b && a==plan.prefix_board_indexes(history),"frame prefix differs from literal route");
    }
    if (vertex.kind == graph::VertexKind::decision) {
        const auto a=indexed.locate_decision_rows(frame,vertex.actor,vertex.actions);
        const auto b=reference.locate_decision_rows(cursor,vertex.actor,vertex.actions);
        compare_location_vectors(a,b); compare_location_vectors(a,plan.locate_decision_rows(vertex.actor,history,vertex.actions));
        for (const auto& row : a) if (row) { require(row->q < masks.size() && !(masks[row->q] & row->member_bit),"duplicate Q member"); masks[row->q] |= row->member_bit; }
        for (std::size_t i=0;i<vertex.actions.size();++i) {
            history.push_back(vertex.actions[i].token); auto next=indexed.advance_action(workspace,frame,i);
            const auto old=reference.advance_action(cursor,i); frame_walk(plan,indexed,workspace,reference,vertex.children[i],history,next.view(),old,average,masks); history.pop_back();
        }
    } else if (vertex.kind == graph::VertexKind::chance) {
        const auto tag=vertex.street==Street::flop?"flop@":vertex.street==Street::turn?"turn@":"river@";
        for (std::size_t i=0;i<vertex.branches.size();++i) {
            history.push_back(std::string(tag)+vertex.branches[i].label); auto next=indexed.advance_reveal(workspace,frame,i);
            const auto old=reference.advance_reveal(cursor,i); frame_walk(plan,indexed,workspace,reference,vertex.branches[i].child,history,next.view(),old,average,masks); history.pop_back();
        }
    }
}
void check_frame_parity(Plan& plan) {
    const auto reservation=FrameWorkspace::reservation(plan.graph_census().maximum_depth,plan.group().size());
    auto caller=caller_reservation(plan); caller.work_upper+=reservation.setup_work_upper; caller.entries_upper+=reservation.retained_entries_upper;
    routing::IndexedRouting frames(plan,{1,0},{},caller,true), old(plan,{1,0},{},caller,false);
    auto& workspace=frames.make_workspace();
    expect_error(graph::ErrorCode::invalid_query,[&]{(void)frames.make_workspace();},"duplicate workspace factory accepted");
    expect_error(graph::ErrorCode::invalid_query,[&]{(void)frames.root_cursor();},"value cursor accepted in frame mode");
    expect_error(graph::ErrorCode::invalid_query,[&]{(void)old.make_workspace();},"workspace accepted in value mode");
    const auto T=plan.iterations();
    for (std::size_t t=0;t<T;++t) for (unsigned phase=0;phase<3;++phase) {
        auto root=frames.root_frame(workspace); auto value=old.root_cursor(); auto history=plan.graph().initial_history;
        expect_error(graph::ErrorCode::invalid_query,[&]{(void)old.prefix_board_indexes(root.view());},"frame accepted in value mode");
        expect_error(graph::ErrorCode::invalid_query,[&]{(void)frames.prefix_board_indexes(value);},"value accepted in frame mode");
        std::vector<std::uint32_t> masks(plan.rows().size());
        frame_walk(plan,frames,workspace,old,plan.graph().root_id,history,root.view(),value,phase==2,masks);
        for (std::size_t q=0;q<masks.size();++q) require(masks[q]==plan.rows()[q].expected_mask,"incomplete Q mask");
    }
    const auto receipt=frames.receipt_snapshot(), ref=old.receipt_snapshot(); const auto& c=plan.graph_census();
    require(workspace.active_frames()==0,"live frame leaked after traversal");
    require(frames.root_cursor_calls_actual()==3*T && frames.edge_advance_calls_actual()==3*T*(c.logical_visits-1),"frame root/edge schedule mismatch");
    require(receipt.root_cursor_calls_actual==ref.root_cursor_calls_actual && receipt.edge_advance_calls_actual==ref.edge_advance_calls_actual && receipt.decision_lookup_calls_actual==ref.decision_lookup_calls_actual && receipt.prefix_lookup_calls_actual==ref.prefix_lookup_calls_actual,"frame/value counters differ");
    require(receipt.decision_lookup_calls_actual==3*T*c.decision_occurrences && receipt.prefix_lookup_calls_actual==T*(2*c.terminal_occurrences+c.decision_occurrences),"3T decision/prefix schedule mismatch");
    const auto counts=workspace.counts(); require(counts.activations==3*T*c.logical_visits && counts.released_frames==counts.activations,"workspace activation/release mismatch");
}
void check_preflight(Plan& plan) {
    const auto res=FrameWorkspace::reservation(plan.graph_census().maximum_depth,plan.group().size());
    history_index::ExternalReservation short_caller{res.setup_work_upper,res.retained_entries_upper-1};
    routing::IndexedRouting short_router(plan,{1,0},{},short_caller,true);
    expect_error(graph::ErrorCode::invalid_limits,[&]{(void)short_router.make_workspace();},"undersized workspace reservation accepted");
    auto caller=caller_reservation(plan); caller.work_upper+=res.setup_work_upper; caller.entries_upper+=res.retained_entries_upper;
    routing::IndexedRouting admitted(plan,{1,0},{},caller,true); const auto r=admitted.receipt_snapshot();
    routing::WholeLimits work{r.combined_modeled_work_upper-1,graph::kMaximumRetainedEntries};
    expect_error(graph::ErrorCode::work_limit,[&]{routing::IndexedRouting rejected(plan,{1,0},work,caller,true);},"combined work cap-minus-one accepted");
    routing::WholeLimits entries{graph::kMaximumModeledWork,r.combined_logical_entries_upper-1};
    expect_error(graph::ErrorCode::storage_limit,[&]{routing::IndexedRouting rejected(plan,{1,0},entries,caller,true);},"combined entries cap-minus-one accepted");
}
void check_same_index_foreign(Plan& plan) {
    const auto res=FrameWorkspace::reservation(plan.graph_census().maximum_depth,plan.group().size()); auto caller=caller_reservation(plan); caller.work_upper+=res.setup_work_upper; caller.entries_upper+=res.retained_entries_upper;
    routing::IndexedRouting router(plan,{1,0},{},caller,true); auto& owner=router.make_workspace();
    FrameWorkspace foreign(owner.index(),plan.graph_census().maximum_depth); auto bad=foreign.root(); auto good=router.root_frame(owner);
    const auto before=router.receipt_snapshot(); const auto root_before=router.root_cursor_calls_actual(),edge_before=router.edge_advance_calls_actual();
    const auto& vertex=plan.graph().vertices[plan.graph().root_id];
    expect_error(graph::ErrorCode::invalid_query,[&]{(void)router.prefix_board_indexes(bad.view());},"same-index foreign prefix accepted");
    expect_error(graph::ErrorCode::invalid_query,[&]{(void)router.locate_decision_rows(bad.view(),vertex.actor,vertex.actions);},"same-index foreign rows accepted");
    expect_error(graph::ErrorCode::invalid_query,[&]{auto x=router.advance_action(owner,bad.view(),0);},"same-index foreign parent accepted");
    const auto after=router.receipt_snapshot(); require(before.decision_lookup_calls_actual==after.decision_lookup_calls_actual && before.prefix_lookup_calls_actual==after.prefix_lookup_calls_actual && before.index_query_work_actual==after.index_query_work_actual && before.router_query_work_actual==after.router_query_work_actual && root_before==router.root_cursor_calls_actual() && edge_before==router.edge_advance_calls_actual(),"foreign frame consumed query budget");
    expect_error(graph::ErrorCode::invalid_query,[&]{(void)router.locate_decision_rows(good.view(),static_cast<std::uint8_t>(1-vertex.actor),vertex.actions);},"frame wrong actor accepted");
    expect_error(graph::ErrorCode::invalid_query,[&]{(void)router.locate_decision_rows(good.view(),vertex.actor,std::span<const Action>(vertex.actions.data(),1));},"frame incomplete menu accepted");
    auto reversed=vertex.actions; std::reverse(reversed.begin(),reversed.end());
    expect_error(graph::ErrorCode::invalid_query,[&]{(void)router.locate_decision_rows(good.view(),vertex.actor,reversed);},"frame reordered menu accepted");
    std::optional<FrameView> stale;
    { auto child=router.advance_action(owner,good.view(),0); stale.emplace(child.view()); }
    const auto stale_before=router.receipt_snapshot(); const auto stale_edge=router.edge_advance_calls_actual();
    expect_error(graph::ErrorCode::invalid_query,[&]{(void)router.prefix_board_indexes(*stale);},"stale frame prefix accepted");
    expect_error(graph::ErrorCode::invalid_query,[&]{(void)router.locate_decision_rows(*stale,vertex.actor,vertex.actions);},"stale frame rows accepted");
    expect_error(graph::ErrorCode::invalid_query,[&]{auto x=router.advance_action(owner,*stale,0);},"stale frame advance accepted");
    const auto stale_after=router.receipt_snapshot();
    require(stale_before.decision_lookup_calls_actual==stale_after.decision_lookup_calls_actual && stale_before.prefix_lookup_calls_actual==stale_after.prefix_lookup_calls_actual && stale_before.index_query_work_actual==stale_after.index_query_work_actual && stale_before.router_query_work_actual==stale_after.router_query_work_actual && stale_edge==router.edge_advance_calls_actual(),"stale frame consumed query budget");
}
int main() {
    try {
        Plan g1(shared_reconvergent_graph(),{{{48,49},kOne}},{{{44,46},kOne}},{kBoard},10); require(g1.group().size()==1,"G1 fixture"); check_frame_parity(g1); check_same_index_foreign(g1); check_preflight(g1);
        const std::vector<WeightedHand> sb{{{48,49},kOne},{{48,50},kOne},{{49,50},kOne}}, bb{{{44,45},kOne},{{44,46},kOne},{{45,46},kOne}};
        const std::vector<SelectedBoard> boards{{{0,1,6,8,14}},{{0,1,6,9,14}}}; Plan g2(g2_turn_graph(),sb,bb,boards,10); require(g2.group().size()==2,"G2 fixture"); check_frame_parity(g2);
        {
            Graph holes; const Action left{"left",0,0,false,"left"},right{"right",0,0,false,"right"};
            holes.vertices.push_back(Vertex::decision(0,{left,right},{1,2}));
            holes.vertices.push_back(Vertex::terminal(TerminalKind::fold,1,{kOne,kOne}));
            holes.vertices.push_back(Vertex::terminal(TerminalKind::showdown,2,{kOne,kOne}));
            Plan p(std::move(holes),{{{0,2},kOne},{{18,20},kOne}},{{{24,26},kOne},{{28,30},kOne}},{kBoard},10);
            const auto rows=p.locate_decision_rows(0,p.graph().initial_history,p.graph().vertices[p.graph().root_id].actions);
            require(rows.size()==2 && !rows[0] && rows[1],"support-hole fixture"); check_frame_parity(p);
        }
        const std::vector<WeightedHand> sb6{{{48,49},kOne},{{48,50},kOne},{{48,51},kOne}},bb6{{{44,45},kOne},{{44,46},kOne},{{44,47},kOne}};
        Plan g6(shared_reconvergent_graph(),sb6,bb6,std::vector<SelectedBoard>{{{1,2,3,0,4}}},10); require(g6.group().size()==6,"G6 fixture"); check_frame_parity(g6);
        {
            std::vector<SelectedBoard> chance_boards; std::array<std::uint8_t,3> suits{1,2,3};
            do { SelectedBoard b{{suits[0],static_cast<graph::Card>(4+suits[1]),static_cast<graph::Card>(8+suits[2]),12,16}}; std::sort(b.cards.begin(),b.cards.begin()+3); chance_boards.push_back(b); } while(std::next_permutation(suits.begin(),suits.end()));
            std::vector<std::string> labels;
            for(const auto& board:chance_boards) labels.push_back(graph::detail::card_text(board.cards[0])+graph::detail::card_text(board.cards[1])+graph::detail::card_text(board.cards[2]));
            std::sort(labels.begin(),labels.end()); std::vector<graph::Branch> branches; for(const auto& label:labels) branches.emplace_back(label,1);
            Graph game; game.vertices.push_back(Vertex::chance(Street::flop,4,std::move(branches)));
            const Action check{"check",0,0,false,"check"}; game.vertices.push_back(Vertex::decision(0,{check},{2})); game.vertices.push_back(Vertex::terminal(TerminalKind::showdown,2,{kOne,kOne}));
            Plan p(std::move(game),sb6,bb6,chance_boards,10); require(p.group().size()==6,"G6 reveal fixture"); check_frame_parity(p);
        }
        std::cout << "ALL ACTIVE ROUTING CONTROLS PASSED\n"; return 0;
    } catch(const std::exception& e) { std::cerr << "ACTIVE ROUTING FAILURE: " << e.what() << '\n'; return 1; }
}
