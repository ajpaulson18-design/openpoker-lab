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
int main() {
    try {
        rank_anchors();
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
