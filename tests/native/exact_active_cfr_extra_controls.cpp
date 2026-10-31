#define main reference_cfr_controls_main
#include "exact_selected_cfr_controls.cpp"
#undef main

std::unique_ptr<g::Plan> extra_plan(unsigned kind) {
    g::Graph graph;
    std::vector<g::WeightedHand> sb,bb;
    std::vector<g::SelectedBoard> boards;
    if (kind==0) {
        sb={{{48,49},bits(1.)},{{48,50},bits(1.)},{{48,51},bits(1.)}};
        bb={{{44,45},bits(1.)},{{44,46},bits(1.)},{{44,47},bits(1.)}};
        std::array<std::uint8_t,3> suits{1,2,3};
        do { g::SelectedBoard board{{suits[0],static_cast<g::Card>(4+suits[1]),static_cast<g::Card>(8+suits[2]),12,16}};
             std::sort(board.cards.begin(),board.cards.begin()+3);boards.push_back(board); }
        while(std::next_permutation(suits.begin(),suits.end()));
        std::vector<std::string> labels;
        for(const auto& board:boards) labels.push_back(g::detail::card_text(board.cards[0])+g::detail::card_text(board.cards[1])+g::detail::card_text(board.cards[2]));
        std::sort(labels.begin(),labels.end());std::vector<g::Branch> branches;
        for(const auto& label:labels) branches.emplace_back(label,1);
        graph.vertices={g::Vertex::chance(g::Street::flop,4,std::move(branches)),
            g::Vertex::decision(0,{act("fold"),act("call")},{2,3}),
            g::Vertex::terminal(g::TerminalKind::fold,1,{bits(1.),bits(1.)}),
            g::Vertex::terminal(g::TerminalKind::showdown,2,{bits(1.),bits(1.)})};
    } else if(kind==1) {
        sb={{{48,50},bits(1.)},{{49,50},bits(1.)}};bb={{{44,46},bits(1.)},{{45,46},bits(1.)}};
        boards={{{0,1,6,8,14}},{{0,1,6,9,14}}}; graph.initial_history={"flop@2c2d3h"};
        graph.vertices={g::Vertex::chance(g::Street::turn,5,{{"4c",1},{"4d",1}}),
            g::Vertex::decision(0,{act("fold"),act("call")},{2,3}),
            g::Vertex::terminal(g::TerminalKind::fold,1,{bits(1.),bits(1.)}),
            g::Vertex::terminal(g::TerminalKind::showdown,2,{bits(1.),bits(1.)})};
    } else {
        sb={{{48,49},bits(1.)}};bb={{{44,46},bits(1.)}};boards={{{0,4,8,12,16}}};
        graph.vertices={g::Vertex::terminal(g::TerminalKind::showdown,2,{bits(1.),bits(1.)})};
    }
    return std::make_unique<g::Plan>(std::move(graph),std::move(sb),std::move(bb),std::move(boards),10,1,g::Limits{},g::AdmissionProfile::indexed_v1);
}
void compare_extra(unsigned kind) {
    auto old_plan=extra_plan(kind),new_plan=extra_plan(kind);
    if(kind==0) need(new_plan->group().size()==6,"G6 fixture symmetry");
    if(kind==1) need(new_plan->group().size()==2 && !new_plan->graph().initial_history.empty(),"initial G2 fixture");
    if(kind==2) need(new_plan->graph_census().maximum_depth==0 && new_plan->rows().empty(),"terminal-only fixture");
    c::Trainer old(*old_plan),active(*new_plan); const auto reference=old.run_indexed();const auto result=active.run_active_frames();
    need(reference.quotient_policy.size()==result.quotient_policy.size(),"extra Q width");
    for(std::size_t i=0;i<reference.quotient_policy.size();++i) need(bits(reference.quotient_policy[i])==bits(result.quotient_policy[i]),"extra policy bit mismatch");
    if(kind!=2) {
        need(!result.quotient_policy.empty(),"nonterminal policy missing");
        bool varied=false; for(double p:result.quotient_policy) varied |= p!=0.5;
        need(varied,"nontrivial payoff did not affect policy");
    }
    need(result.receipt.active_frames.has_value() && result.receipt.indexed_shadow.has_value(),"extra frame receipt missing");
    const auto& f=*result.receipt.active_frames; const auto& route=result.receipt.indexed_shadow->routing;
    const auto& census=new_plan->graph_census();const auto visits=3ULL*new_plan->iterations()*census.logical_visits;
    need(f.actual.activations==visits && f.actual.released_frames==visits && f.actual.release_calls==visits && !f.final_active_frames && !f.final_workspace_entries && !f.value_cursor_learning_calls,"extra frame lifecycle");
    need(result.receipt.member_checks==result.receipt.expected_member_checks && result.receipt.member_checks==reference.receipt.member_checks,"extra member coverage");
    need(route.root_cursor_calls_actual==3ULL*new_plan->iterations() && route.edge_advance_calls_actual==3ULL*new_plan->iterations()*(census.logical_visits-1),"extra route counts");
    need(route.decision_lookup_calls_actual==3ULL*new_plan->iterations()*census.decision_occurrences && route.prefix_lookup_calls_actual==new_plan->iterations()*(2*census.terminal_occurrences+census.decision_occurrences),"extra decision/prefix counts");
    need(!result.receipt.legacy_training_history_extensions && !result.receipt.legacy_training_row_lookups && !result.receipt.legacy_training_prefix_lookups && !result.receipt.value_cursor_learning_calls,"extra legacy fallback");
    need(new_plan->kernel().receipt().rank_calls==old_plan->kernel().receipt().rank_calls && new_plan->kernel().receipt().modeled_work==old_plan->kernel().receipt().modeled_work,"extra callback accounting");
    rejection("extra trainer single use",[&]{active.run_active_frames();});
    std::cout<<"extra kind="<<kind<<" G="<<new_plan->group().size()<<" policy="<<result.quotient_policy.size()<<" visits="<<visits<<"\n";
}
void check_rounding_failure() {
    auto plan=extra_plan(0); c::Trainer trainer(*plan); const auto old=std::fegetround();
    need(old!=-1 && std::fesetround(FE_DOWNWARD)==0,"cannot set FP rounding");
    const auto before=plan->kernel().receipt(); bool rejected=false;
    try { (void)trainer.run_active_frames(); } catch(const std::exception&) { rejected=true; }
    const bool restored=std::fesetround(old)==0;
    need(restored && rejected,"wrong rounding accepted");
    need(plan->kernel().receipt().modeled_work==before.modeled_work && plan->kernel().receipt().rank_calls==before.rank_calls,"wrong rounding touched kernel");
    rejection("failed trainer single use",[&]{(void)trainer.run_active_frames();});
}
void check_terminal_conversion_failure() {
    g::Graph graph; const auto tiny=std::numeric_limits<double>::denorm_min();
    graph.vertices={g::Vertex::terminal(g::TerminalKind::fold,1,{bits(tiny),bits(tiny)})};
    g::Plan plan(std::move(graph),{{{48,49},bits(1.)}},{{{44,46},bits(1.)}},{{{0,4,8,12,16}}},10,1,g::Limits{},g::AdmissionProfile::indexed_v1);
    c::Trainer trainer(plan); const auto before=plan.kernel().receipt(); bool failed=false;
    try { (void)trainer.run_active_frames(); } catch(const k::KernelError& e) {
        failed = e.code()==k::ErrorCode::conversion_failure;
    }
    need(failed,"terminal callback did not reject subnormal payoff");
    need(plan.kernel().receipt().terminal_queries==before.terminal_queries+1,"terminal callback was not entered exactly once");
    rejection("callback-failed trainer single use",[&]{(void)trainer.run_active_frames();});
}
int main() {
    try { for(unsigned kind=0;kind<3;++kind) compare_extra(kind); check_rounding_failure(); check_terminal_conversion_failure();
        std::cout<<"ALL EXTRA ACTIVE CFR CONTROLS PASSED\n";return 0;
    } catch(const std::exception& e) {std::cerr<<"EXTRA ACTIVE CFR FAILURE: "<<e.what()<<'\n';return 1;}
}
