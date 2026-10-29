// External conditional-graph controls. Independent literal R learning loop
// shares the separately conformance-tested native exact callback kernel only.
#include "exact_selected_cfr.hpp"
#include <iostream>
#include <map>
#include <tuple>
#include <cfenv>
#if defined(__SSE__) || defined(_M_X64) || defined(_M_IX86)
#include <xmmintrin.h>
#endif
namespace g = openpoker::exact_public_graph;
namespace c = openpoker::exact_selected_cfr;
namespace k = openpoker::exact_selected_kernel;
using V = std::vector<double>;
std::uint64_t bits(double x) { return std::bit_cast<std::uint64_t>(x); }
void need(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
g::Action act(const char* name) { return {name, 0, 0, false, name}; }
g::Graph fixture(bool symmetry) {
    g::Graph graph;
    const auto first = symmetry ? "2c3c7c" : "2c3d4h";
    const auto second = "2d3d7d";
    graph.vertices = {
        g::Vertex::decision(0, {act("fold"), act("call")}, {1,2}),
        g::Vertex::terminal(g::TerminalKind::fold, 1, {bits(1.),bits(1.)}),
        g::Vertex::chance(g::Street::flop,4, symmetry ? std::vector<g::Branch>{{first,3},{second,3}} : std::vector<g::Branch>{{first,3}}),
        g::Vertex::decision(1,{act("fold"),act("call")},{4,5}),
        g::Vertex::terminal(g::TerminalKind::fold,0,{bits(1.),bits(1.)}),
        g::Vertex::chance(g::Street::turn,5,{{symmetry ? "9h" : "7s",6}}),
        g::Vertex::decision(0,{act("fold"),act("call")},{1,7}),
        g::Vertex::chance(g::Street::river,6,{{symmetry ? "Ts" : "8c",8}}),
        g::Vertex::decision(1,{act("fold"),act("call")},{4,9}),
        g::Vertex::terminal(g::TerminalKind::showdown,2,{bits(1.),bits(1.)})};
    return graph;
}
std::unique_ptr<g::Plan> make_plan(bool symmetry, g::Limits limits = {}, bool excessive_money = false) {
    auto graph = fixture(symmetry);
    if (excessive_money) graph.vertices[9].contribution_bits = {bits(1e13),bits(1e13)};
    std::vector<g::WeightedHand> a = symmetry ? std::vector<g::WeightedHand>{{{48,40},bits(1.)},{{49,41},bits(1.)}} : std::vector<g::WeightedHand>{{{51,50},bits(1.)}};
    std::vector<g::WeightedHand> b = symmetry ? std::vector<g::WeightedHand>{{{44,36},bits(1.)},{{45,37},bits(1.)}} : std::vector<g::WeightedHand>{{{47,46},bits(1.)}};
    std::vector<g::SelectedBoard> boards = symmetry ? std::vector<g::SelectedBoard>{{{0,4,20,30,35}},{{1,5,21,30,35}}} : std::vector<g::SelectedBoard>{{{0,5,10,23,24}}};
    return std::make_unique<g::Plan>(std::move(graph),std::move(a),std::move(b),std::move(boards),10,1,limits);
}

std::unique_ptr<g::Plan> shadow_fixture(unsigned kind) {
    if (kind < 2) return make_plan(kind == 1);
    const bool symmetry = kind != 4;
    auto graph = fixture(symmetry);
    std::vector<g::WeightedHand> a{{{48,40},bits(1.)},{{49,41},bits(1.)}};
    std::vector<g::WeightedHand> b{{{44,36},bits(1.)},{{45,37},bits(1.)}};
    std::vector<g::SelectedBoard> boards{{{0,4,20,30,35}},{{1,5,21,30,35}}};
    if (kind == 2) a.push_back({{50,42},bits(1.)}); // c/d-fixed member plus a swapped pair
    if (kind == 3) a = {{{48,40},bits(1.)},{{0,48},bits(1.)},{{1,49},bits(1.)},{{49,41},bits(1.)}};
    if (kind == 4) {
        // River prefix is terminal-only: no decision at its five-card prefix.
        graph.vertices[8] = g::Vertex::terminal(g::TerminalKind::showdown,2,{bits(1.),bits(1.)});
        graph.vertices.pop_back();
        a = {{{51,50},bits(1.)}}; b = {{{47,46},bits(1.)}};
        boards = {{{0,5,10,23,24}}};
    }
    return std::make_unique<g::Plan>(std::move(graph),std::move(a),std::move(b),std::move(boards),10,1);
}

// Separate expanded-row implementation: plain R map, no procedural Q lookup,
// masks or staging functions from the candidate are reused.
using Key = std::tuple<unsigned,std::size_t,g::History>;
struct State { V regret, mass, policy, delta; };
class Literal {
    g::Plan& p;
    std::map<Key,State> rows;
    std::map<std::vector<std::size_t>,k::ExactSelectedKernel::MarginalVectors> masses;
    double sum(double a,double b) { double out=a+b;need(std::isfinite(out),"literal nonfinite");return out==0?0.:out; }
    void match() {
        for(auto& [key,s]:rows) {
            (void)key;double total=0;
            for(double v:s.regret) total=sum(total,v>0?v:0.);
            for(std::size_t a=0;a<s.policy.size();++a)s.policy[a]=total?(s.regret[a]>0?s.regret[a]:0.)/total:1./static_cast<double>(s.policy.size());
        }
    }
    V values(std::size_t id,const g::History& history,const V& reach,unsigned target) {
        const auto& v=p.graph().vertices[id];auto hands=p.hand_counts();
        if(v.kind==g::VertexKind::terminal) {
            double pay=std::min(std::bit_cast<double>(v.contribution_bits[0]),std::bit_cast<double>(v.contribution_bits[1]));
            const bool fold=v.terminal_kind==g::TerminalKind::fold;
            if(fold&&v.winner==1)pay=-pay;
            return p.kernel().terminal(target,p.prefix_board_indexes(history),fold?k::TerminalKind::fold:k::TerminalKind::showdown,pay,reach);
        }
        if(v.kind==g::VertexKind::chance) {
            std::vector<V> parts(hands[target]);
            for(const auto& b:v.branches) {
                auto child=values(b.child,g::Plan::extend_history(history,v.street,b.label),reach,target);
                for(std::size_t h=0;h<child.size();++h)parts[h].push_back(child[h]==0?0.:child[h]);
            }
            V out(hands[target],0.);
            for(std::size_t h=0;h<out.size();++h) {std::sort(parts[h].begin(),parts[h].end());for(double x:parts[h])out[h]=sum(out[h],x);}
            return out;
        }
        const auto n=v.children.size();V out(hands[target],0.);
        auto probability=[&](std::size_t h,std::size_t a) {auto found=rows.find({v.actor,h,history});return found==rows.end()?1./static_cast<double>(n):found->second.policy[a];};
        if(v.actor==target) {
            std::vector<V> children;
            for(std::size_t a=0;a<n;++a)children.push_back(values(v.children[a],g::Plan::extend_history(history,v.actions[a]),reach,target));
            for(std::size_t h=0;h<out.size();++h) {
                for(std::size_t a=0;a<n;++a)out[h]=sum(out[h],probability(h,a)*children[a][h]);
                auto found=rows.find({v.actor,h,history});
                if(found!=rows.end())for(std::size_t a=0;a<n;++a)found->second.delta[a]=sum(found->second.delta[a],children[a][h]-out[h]);
            }
        } else for(std::size_t a=0;a<n;++a) {
            V changed(reach.size());for(std::size_t h=0;h<reach.size();++h)changed[h]=reach[h]*probability(h,a);
            auto child=values(v.children[a],g::Plan::extend_history(history,v.actions[a]),changed,target);
            for(std::size_t h=0;h<out.size();++h)out[h]=sum(out[h],child[h]);
        }
        return out;
    }
    void average(std::size_t id,const g::History& history,const std::array<V,2>& reach,double t) {
        const auto& v=p.graph().vertices[id];if(v.kind==g::VertexKind::terminal)return;
        if(v.kind==g::VertexKind::chance) {for(const auto& b:v.branches)average(b.child,g::Plan::extend_history(history,v.street,b.label),reach,t);return;}
        const auto& mass=masses.at(p.prefix_board_indexes(history));
        for(std::size_t h=0;h<reach[v.actor].size();++h) {
            auto found=rows.find({v.actor,h,history});if(found==rows.end())continue;
            auto& s=found->second;
            for(std::size_t a=0;a<v.children.size();++a) {double x=mass[v.actor][h]*reach[v.actor][h];x=x*s.policy[a];x=x*t;s.mass[a]=sum(s.mass[a],x);}
        }
        for(std::size_t a=0;a<v.children.size();++a) {
            auto changed=reach;
            for(std::size_t h=0;h<changed[v.actor].size();++h) {auto found=rows.find({v.actor,h,history});double prob=found==rows.end()?1./static_cast<double>(v.children.size()):found->second.policy[a];changed[v.actor][h]=reach[v.actor][h]*prob;}
            average(v.children[a],g::Plan::extend_history(history,v.actions[a]),changed,t);
        }
    }
public:
    explicit Literal(g::Plan& plan):p(plan) {
        p.for_each_supported_row([&](const g::RowKey& key,const std::vector<g::Action>& menu){
            rows.emplace(Key{key.actor,key.hand_index,key.history},State{V(menu.size(),0),V(menu.size(),0),V(menu.size(),0),V(menu.size(),0)});
            const auto& indexes=p.prefix_board_indexes(key.history);
            if(!masses.contains(indexes))masses.emplace(indexes,p.kernel().marginals(indexes));
        });
    }
    void run() {
        auto h=p.hand_counts();
        for(unsigned t=1;t<=p.iterations();++t) {
            match();
            for(unsigned player=0;player<2;++player) {
                for(auto& [key,s]:rows)if(std::get<0>(key)==player)std::fill(s.delta.begin(),s.delta.end(),0.);
                values(p.graph().root_id,p.graph().initial_history,V(h[1-player],1.),player);
                for(auto& [key,s]:rows)if(std::get<0>(key)==player)for(std::size_t a=0;a<s.regret.size();++a)s.regret[a]=std::max(sum(s.regret[a],s.delta[a]),0.);
                match();
            }
            average(p.graph().root_id,p.graph().initial_history,{V(h[0],1.),V(h[1],1.)},static_cast<double>(t));
        }
        for(auto& [key,s]:rows) {(void)key;double total=0;for(double x:s.mass)total=sum(total,x);for(std::size_t a=0;a<s.policy.size();++a)s.policy[a]=total?s.mass[a]/total:1./static_cast<double>(s.policy.size());}
    }
    const V& policy(const g::RowKey& key)const {return rows.at(Key{key.actor,key.hand_index,key.history}).policy;}
};

template<class F>void rejection(const char* label,F body) {
    bool rejected=false;try {body();}catch(const std::exception& e) {rejected=true;std::cout<<label<<" rejected: "<<e.what()<<"\n";}
    need(rejected,label);
}
void rank_anchors() {
    // Root hardcoded best-five anchors complement physical pair-game replay.
    const auto check=[](const char* text,std::array<std::uint8_t,6> expected) {
        constexpr std::string_view ranks="23456789TJQKA", suits="cdhs";
        std::array<std::uint8_t,7> cards{};
        for(std::size_t i=0;i<7;++i) cards[i]=static_cast<std::uint8_t>(
            4*ranks.find(text[2*i])+suits.find(text[2*i+1]));
        need(k::detail::rank_seven(cards).value==expected,"native hardcoded best-five rank anchor differs");
    };
    check("AcKcQcJc2dTc3d",{8,14,0,0,0,0});
    check("AcAdAhKs2dAs3d",{7,14,13,0,0,0});
    check("AcAdKhKd2cAs3d",{6,14,13,0,0,0});
    check("2c4c6c8dTdAcQc",{5,14,12,6,4,2});
    check("Ac2d3h4sKd5c6d",{4,6,0,0,0,0});
    check("Ac7d7h2sKd7cQd",{3,7,14,13,0,0});
    check("AcAdKhKd2sQcQd",{2,14,13,12,0,0});
    check("AcKd9h7s2cAsQd",{1,14,13,12,9,0});
    check("2c5d7h9sJcAdKh",{0,14,13,11,9,7});
    check("Ac2c3c4cKd5c6d",{8,5,0,0,0,0});
    check("2c3c7c9cKdAcQc",{5,14,12,9,7,3});
    check("7c7d7h7s2cAcKd",{7,7,14,0,0,0});
    check("AcAdKhKd2sAsKs",{6,14,13,0,0,0});
    check("2c3c4c5c6c7c8c",{8,8,0,0,0,0});
    std::cout<<"14 hardcoded seven-card best-five rank anchors passed\n";
}
void indexed_shadow_controls() {
    for (unsigned kind = 0; kind < 5; ++kind) {
        auto reference_plan = shadow_fixture(kind);
        c::Trainer reference(*reference_plan); const auto old = reference.run();
        need(!old.receipt.indexed_shadow,"default path gained a shadow receipt");
        auto plan = shadow_fixture(kind);
        if (kind == 2) {
            need(plan->group().size()==2,"mixed stabilizer lost G2");
            bool one=false,two=false;for(const auto& row:plan->rows()){one|=row.orbit_size==1;two|=row.orbit_size==2;}
            need(one&&two,"mixed fixture lacks distinct orbit sizes");
        }
        if (kind == 3) {
            const auto history = g::History{"call","flop@2c3c7c"};
            const auto rows = plan->locate_decision_rows(1,history,plan->graph().vertices[3].actions);
            (void)rows;
            const auto support=plan->prefix_support(std::array<g::Card,3>{0,4,20});
            need(!std::binary_search(support.hands[0].begin(),support.hands[0].end(),1U) &&
                 std::binary_search(support.hands[0].begin(),support.hands[0].end(),2U),"hole fixture lacks internal support hole");
        }
        c::Trainer candidate(*plan);const auto result = candidate.run_indexed_shadow();
        need(result.quotient_policy.size()==old.quotient_policy.size(),"shadow changed full Q policy width");
        for(std::size_t i=0;i<old.quotient_policy.size();++i)
            need(bits(result.quotient_policy[i])==bits(old.quotient_policy[i]),"shadow changed Q probability bits");
        need(result.receipt.member_checks==old.receipt.member_checks &&
             result.receipt.expected_member_checks==old.receipt.expected_member_checks,"shadow changed phase/member coverage");
        need(result.receipt.indexed_shadow.has_value(),"explicit shadow missing receipt");
        const auto& s=*result.receipt.indexed_shadow;const auto& r=s.routing;
        need(s.mode=="shadow" && s.version=="native-exact-cfr-indexed-shadow-v1","shadow mode identity changed");
        need(s.legacy_training_history_extensions==r.edge_advance_calls_actual &&
             s.legacy_training_row_lookups==r.decision_lookup_calls_actual &&
             s.legacy_training_prefix_lookups==r.prefix_lookup_calls_actual,"shadow legacy-call coverage differs");
        need(old.receipt.legacy_training_history_extensions==r.edge_advance_calls_actual &&
             old.receipt.legacy_training_row_lookups==r.decision_lookup_calls_actual &&
             old.receipt.legacy_training_prefix_lookups==r.prefix_lookup_calls_actual,"default legacy-call coverage differs");
        need(s.final_router_entries==0 && r.r_lookup_entries==0 && r.original_q_histories_retained,"shadow retained forbidden/final state");
        need(r.combined_modeled_work_upper<=500'000'000 && r.combined_logical_entries_upper<=2'000'000,"shadow lacks shared limits");
        need(r.root_cursor_calls_actual==30 && r.edge_advance_calls_actual==30*(plan->graph_census().logical_visits-1),"shadow root/edge counts differ");
        need(s.decision_comparisons==30*plan->graph_census().decision_occurrences &&
             s.prefix_comparisons==20*plan->graph_census().terminal_occurrences+10*plan->graph_census().decision_occurrences,"shadow did not compare every scheduled query");
        need(s.cursor_frame_entries_upper==4*(plan->graph_census().maximum_depth+4)*openpoker::exact_indexed_routing::kMaximumCursorLogicalEntries,"shadow did not reserve full24-image cursor copies");
        need(s.plan_kernel_forecast_retained_overlap==plan->kernel_setup_support_work_upper(),"shadow omitted named conservative kernel overlap");
        std::cout<<"indexed-shadow kind="<<kind<<" policybits="<<result.quotient_policy.size()
                 <<" decisions="<<s.decision_comparisons<<" prefixes="<<s.prefix_comparisons
                 <<" wholework="<<r.combined_modeled_work_upper<<" entries="<<r.combined_logical_entries_upper<<"\n";
        rejection("shadow single-use",[&]{candidate.run_indexed_shadow();});
        rejection("shadow then default single-use",[&]{candidate.run();});
        rejection("shadow then indexed single-use",[&]{candidate.run_indexed();});
        rejection("default then indexed single-use",[&]{reference.run_indexed();});
        auto indexed_plan=shadow_fixture(kind);c::Trainer indexed_trainer(*indexed_plan);
        const auto indexed=indexed_trainer.run_indexed();
        need(indexed.quotient_policy.size()==old.quotient_policy.size(),"indexed changed full Q policy width");
        for(std::size_t i=0;i<old.quotient_policy.size();++i) {
            need(bits(indexed.quotient_policy[i])==bits(old.quotient_policy[i]),"indexed/default policy bits differ");
            need(bits(indexed.quotient_policy[i])==bits(result.quotient_policy[i]),"indexed/shadow policy bits differ");
        }
        need(indexed.receipt.indexed_shadow.has_value(),"indexed-only missing namespaced receipt");
        const auto& ns=*indexed.receipt.indexed_shadow;const auto& nr=ns.routing;
        need(ns.mode=="indexed" && ns.version=="native-exact-cfr-indexed-v1","indexed mode is not explicit");
        need(!ns.legacy_training_history_extensions && !ns.legacy_training_row_lookups &&
             !ns.legacy_training_prefix_lookups && !indexed.receipt.legacy_training_history_extensions &&
             !indexed.receipt.legacy_training_row_lookups && !indexed.receipt.legacy_training_prefix_lookups,
             "indexed learning retained a legacy history operation");
        need(!ns.decision_comparisons && !ns.prefix_comparisons,"indexed-only still runs shadow comparisons");
        need(nr.root_cursor_calls_actual==r.root_cursor_calls_actual && nr.edge_advance_calls_actual==r.edge_advance_calls_actual &&
             nr.decision_lookup_calls_actual==r.decision_lookup_calls_actual && nr.prefix_lookup_calls_actual==r.prefix_lookup_calls_actual,
             "indexed-only changed complete routing coverage");
        need(nr.combined_modeled_work_upper==r.combined_modeled_work_upper &&
             nr.combined_logical_entries_upper==r.combined_logical_entries_upper &&
             indexed.receipt.full_history_lookup_work_upper==old.receipt.full_history_lookup_work_upper &&
             ns.legacy_full_history_work_forecast_retained==old.receipt.full_history_lookup_work_upper,
             "indexed-only took capacity credit from old forecast");
        need(!ns.final_router_entries && !indexed.receipt.final_numeric_workspace_slots &&
             indexed.receipt.maximum_numeric_workspace_slots==4*indexed.receipt.action_slots &&
             indexed.receipt.member_checks==old.receipt.member_checks,"indexed-only changed workspace or phase/member coverage");
        std::cout<<"indexed-only kind="<<kind<<" policybits="<<indexed.quotient_policy.size()
                 <<" indexeddecisions="<<nr.decision_lookup_calls_actual<<" indexedprefixes="<<nr.prefix_lookup_calls_actual
                 <<" legacytraining=0/0/0\n";
        rejection("indexed single-use",[&]{indexed_trainer.run_indexed();});
        rejection("indexed then shadow single-use",[&]{indexed_trainer.run_indexed_shadow();});
        rejection("indexed then default single-use",[&]{indexed_trainer.run();});
        // Budget exactly below the complete shadow envelope: reject before
        // marginal/terminal callbacks, while the ordinary run still fits.
        auto constrained = shadow_fixture(kind); c::Limits limits;
        limits.max_modeled_work=r.combined_modeled_work_upper-1;
        c::Trainer low(*constrained,limits);const auto kernel_before=constrained->kernel().receipt();
        rejection("shadow shared work prelearning",[&]{low.run_indexed_shadow();});
        need(constrained->kernel().receipt().modeled_work==kernel_before.modeled_work &&
             constrained->kernel().receipt().rank_calls==kernel_before.rank_calls,"shadow admission mutated kernel before rejection");
        auto entry_plan=shadow_fixture(kind);limits={};limits.max_entries=r.combined_logical_entries_upper-1;
        c::Trainer entry_low(*entry_plan,limits);const auto work_before=entry_plan->kernel().receipt().modeled_work;
        rejection("shadow shared entries prelearning",[&]{entry_low.run_indexed_shadow();});
        need(entry_plan->kernel().receipt().modeled_work==work_before,"shadow entry rejection mutated kernel");
        auto indexed_work_plan=shadow_fixture(kind);limits={};limits.max_modeled_work=nr.combined_modeled_work_upper-1;
        c::Trainer indexed_low(*indexed_work_plan,limits);const auto indexed_before=indexed_work_plan->kernel().receipt();
        rejection("indexed shared work prelearning",[&]{indexed_low.run_indexed();});
        need(indexed_work_plan->kernel().receipt().modeled_work==indexed_before.modeled_work &&
             indexed_work_plan->kernel().receipt().rank_calls==indexed_before.rank_calls,"indexed work rejection queried kernel");
        auto indexed_entry_plan=shadow_fixture(kind);limits={};limits.max_entries=nr.combined_logical_entries_upper-1;
        c::Trainer indexed_entry_low(*indexed_entry_plan,limits);const auto indexed_entry_before=indexed_entry_plan->kernel().receipt();
        rejection("indexed shared entries prelearning",[&]{indexed_entry_low.run_indexed();});
        need(indexed_entry_plan->kernel().receipt().modeled_work==indexed_entry_before.modeled_work &&
             indexed_entry_plan->kernel().receipt().rank_calls==indexed_entry_before.rank_calls,"indexed entry rejection queried kernel");
    }
    {auto plan=make_plan(false);c::Trainer trainer(*plan);
     (void)plan->kernel().support(plan->prefix_board_indexes(plan->graph().initial_history));
     const auto before=plan->kernel().receipt();rejection("shadow externally consumed kernel",[&]{trainer.run_indexed_shadow();});
     need(plan->kernel().receipt().modeled_work==before.modeled_work,"shadow freshness guard queried kernel");}
    {auto plan=make_plan(false);c::Trainer trainer(*plan);std::fesetround(FE_DOWNWARD);
     try{rejection("shadow nearest rounding",[&]{trainer.run_indexed_shadow();});}catch(...){std::fesetround(FE_TONEAREST);throw;}
     std::fesetround(FE_TONEAREST);}
    {auto plan=make_plan(false);c::Trainer trainer(*plan);
     (void)plan->kernel().support(plan->prefix_board_indexes(plan->graph().initial_history));
     const auto before=plan->kernel().receipt();rejection("indexed externally consumed kernel",[&]{trainer.run_indexed();});
     need(plan->kernel().receipt().modeled_work==before.modeled_work,"indexed freshness guard queried kernel");}
    {auto plan=make_plan(false);c::Trainer trainer(*plan);std::fesetround(FE_DOWNWARD);
     try{rejection("indexed nearest rounding",[&]{trainer.run_indexed();});}catch(...){std::fesetround(FE_TONEAREST);throw;}
     std::fesetround(FE_TONEAREST);}
#if defined(__SSE__) || defined(_M_X64) || defined(_M_IX86)
    {auto plan=make_plan(false);c::Trainer trainer(*plan);const auto original=_mm_getcsr();_mm_setcsr(original|0x8040U);
     try{rejection("shadow FTZ/DAZ",[&]{trainer.run_indexed_shadow();});}catch(...){_mm_setcsr(original);throw;}_mm_setcsr(original);}
    {auto plan=make_plan(false);c::Trainer trainer(*plan);const auto original=_mm_getcsr();_mm_setcsr(original|0x8040U);
     try{rejection("indexed FTZ/DAZ",[&]{trainer.run_indexed();});}catch(...){_mm_setcsr(original);throw;}_mm_setcsr(original);}
#endif
}
int main() {
    try {
        rank_anchors();
        indexed_shadow_controls();
        for(bool symmetry:{false,true}) {
            auto p=make_plan(symmetry);need(p->group().size()==(symmetry?2U:1U),"fixture group size");
            c::Trainer trainer(*p);auto result=trainer.run();
            need(result.receipt.maximum_numeric_workspace_slots==4*result.receipt.action_slots,"numeric peak not4Q");
            need(result.receipt.final_numeric_workspace_slots==0,"workspace retained");
            need(result.receipt.modeled_work_upper==result.receipt.plan_non_kernel_work_upper+result.receipt.kernel_work_upper+result.receipt.training_work_upper,"whole work not combined");
            auto other=make_plan(symmetry);Literal literal(*other);literal.run();std::size_t rows=0;
            p->for_each_supported_row([&](const g::RowKey& key,const std::vector<g::Action>& menu){auto location=p->locate(key);const auto& expected=literal.policy(key);for(std::size_t a=0;a<menu.size();++a)need(bits(expected[a])==bits(result.quotient_policy[location.offset+a]),"literalR/Q policy bits differ");++rows;});
            std::cout<<(symmetry?"G2":"identity")<<" complete four-street literalR/Q bitwise matched rows="<<rows<<" Qslots="<<result.receipt.action_slots<<" wholework="<<result.receipt.modeled_work_upper<<"\n";
            rejection("single-use",[&]{trainer.run();});
            const auto baseline=result.receipt.modeled_work_upper;
            auto changed=make_plan(symmetry);c::Limits budget;budget.max_modeled_work=baseline+100;
            c::Trainer before(*changed,budget);
            const auto indexes=changed->prefix_board_indexes(changed->graph().initial_history);
            for(unsigned n=0;n<4;++n)(void)changed->kernel().support(indexes);
            const auto count=changed->kernel().receipt().modeled_work;
            rejection("run-entry external kernel work",[&]{before.run();});
            need(changed->kernel().receipt().modeled_work==count,"late kernel mutation before rejection");
        }
        {auto p=make_plan(false);c::Trainer trainer(*p);std::fesetround(FE_DOWNWARD);rejection("run-entry floating mode",[&]{trainer.run();});std::fesetround(FE_TONEAREST);}
#if defined(__SSE__) || defined(_M_X64) || defined(_M_IX86)
        {auto p=make_plan(false);c::Trainer trainer(*p);const auto original=_mm_getcsr();_mm_setcsr(original|0x8040U);try {rejection("run-entry FTZ/DAZ",[&]{trainer.run();});}catch(...){_mm_setcsr(original);throw;}_mm_setcsr(original);}
#endif
        {g::Limits low;low.kernel.max_storage_entries=1300;auto p=make_plan(true,low);auto before=p->kernel().receipt();rejection("kernel storage before queries",[&]{c::Trainer trainer(*p);});need(p->kernel().receipt().modeled_work==before.modeled_work,"storage rejection mutated kernel");}
        rejection("original payoff envelope (Plan or Trainer)",[&]{auto p=make_plan(true,{},true);c::Trainer trainer(*p);});
        std::cout<<"ALL CONTROLS PASSED; conditional graph arithmetic only, no independent legal-game proof\n";return 0;
    }catch(const std::exception& e){std::cerr<<"FAILED "<<e.what()<<"\n";return 1;}
}
