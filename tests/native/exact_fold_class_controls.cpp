// Exact fold classes are exercised through the same coupled indexed trainer.
#include "../../native/exact_selected_cfr.hpp"
#include <iostream>

namespace k = openpoker::exact_selected_kernel;
namespace g = openpoker::exact_public_graph;
namespace c = openpoker::exact_selected_cfr;
using V = std::vector<double>;
std::uint64_t bits(double value) { return std::bit_cast<std::uint64_t>(value); }
void need(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
std::vector<k::SelectedBoard> boards() {
    std::vector<k::SelectedBoard> out;
    for (std::uint8_t turn = 12; turn < 20; ++turn)
        for (std::uint8_t river = 24; river < 32; ++river) out.push_back({{0,4,8,turn,river}});
    return out;
}
std::vector<k::WeightedHand> hands(unsigned player, bool symmetry = false) {
    if (symmetry) return player ? std::vector<k::WeightedHand>{{{45,46},bits(1.)},{{45,47},bits(1.)},{{46,47},bits(1.)}}
        : std::vector<k::WeightedHand>{{{49,50},bits(1.)},{{49,51},bits(1.)},{{50,51},bits(1.)}};
    return player ? std::vector<k::WeightedHand>{{{49,48},bits(.75)},{{40,41},bits(.25)},{{4,46},bits(.1)},{{24,46},bits(.375)}}
        : std::vector<k::WeightedHand>{{{48,49},bits(.5)},{{44,45},bits(.25)},{{0,48},bits(.1)},{{12,48},bits(.125)}};
}
void same(const V& a, const V& b) {
    need(a.size()==b.size(),"vector size differs");
    for (std::size_t i=0;i<a.size();++i) need(bits(a[i])==bits(b[i]),"exact callback/policy bit differs");
}
void vectors() {
    k::ExactSelectedKernel old(hands(0),hands(1),boards(),64);
    k::ExactSelectedKernel candidate(hands(0),hands(1),boards(),64,{},k::FoldTraversal::mask_classes_v1);
    need(old.normalizer_integer()==candidate.normalizer_integer(),"global exact normalizer changed");
    std::vector<std::vector<std::size_t>> subsets(4);
    for(std::size_t i=0;i<64;++i) {subsets[0].push_back(i);if(i%3==0)subsets[1].push_back(i);}
    subsets[2]={63}; // Selective crossover retains the literal path for small subsets.
    std::size_t comparisons=0;
    for (const auto& subset:subsets) for (std::size_t player=0;player<2;++player)
        for (const double payoff: {0.,.5,-.5,.1,-.1,std::numeric_limits<double>::denorm_min()}) for (unsigned r=0;r<4;++r) {
            V reach{0.,.1,1.,.5}; if(r==1)reach={1.,1.,1.,1.};if(r==2)reach={0.,0.,0.,0.};
            if(r==3)reach={0x1p-1000,0x1p-900,0x1p-1000,0x1p-1000};
            V a,b; int ea=-1,eb=-1;
            try {a=old.terminal(player,subset,k::TerminalKind::fold,payoff,reach);}
            catch(const k::KernelError& error){ea=static_cast<int>(error.code());}
            try {b=candidate.terminal(player,subset,k::TerminalKind::fold,payoff,reach);}
            catch(const k::KernelError& error){eb=static_cast<int>(error.code());}
            need(ea==eb,"conversion/rejection outcome differs"); if(ea==-1)same(a,b);
            ++comparisons;
        }
    need(candidate.receipt().fold_class_queries>0 && candidate.receipt().fold_reference_queries>0,
         "class/literal crossover not exercised");
    need(candidate.receipt().fold_class_buckets>0 && candidate.receipt().fold_class_own_checks>0,
         "class execution counters absent");
    need(candidate.receipt().fold_mask_entries==8 && candidate.receipt().fold_membership_entries==8 &&
         candidate.receipt().fold_class_calls_by_player[0]+candidate.receipt().fold_class_calls_by_player[1]==candidate.receipt().fold_class_queries &&
         candidate.receipt().fold_literal_calls_by_player[0]+candidate.receipt().fold_literal_calls_by_player[1]==candidate.receipt().fold_reference_queries &&
         candidate.receipt().fold_class_own_checks==4*(candidate.receipt().fold_buckets_by_player[0]+candidate.receipt().fold_buckets_by_player[1]),
         "class entered-call/membership ownership counters differ");
    for(std::size_t player=0;player<2;++player)
        same(old.terminal(player,subsets[0],k::TerminalKind::showdown,.5,V{1.,.1,0.,.5}),
             candidate.terminal(player,subsets[0],k::TerminalKind::showdown,.5,V{1.,.1,0.,.5}));
    need(candidate.receipt().modeled_work==old.receipt().modeled_work+candidate.receipt().fold_class_setup_work,
         "candidate took unverified per-query admission credit");
    std::cout<<"callback pairs="<<comparisons<<" classes="<<candidate.receipt().fold_class_queries
             <<" fallback="<<candidate.receipt().fold_reference_queries<<'\n';
}
void guards() {
    bool invalid=false;
    try {k::ExactSelectedKernel kernel(hands(0),hands(1),boards(),64,{},static_cast<k::FoldTraversal>(99));}
    catch(const k::KernelError& error){invalid=error.code()==k::ErrorCode::invalid_input;}
    need(invalid,"unknown fold mode accepted");
    k::Limits storage; storage.max_storage_entries=5879;
    bool refused=false;
    try {k::ExactSelectedKernel kernel(hands(0),hands(1),boards(),64,storage,k::FoldTraversal::mask_classes_v1);}
    catch(const k::KernelError& error){refused=error.code()==k::ErrorCode::storage_limit;}
    need(refused,"constructor omitted mask/class retained entries");
    storage.max_storage_entries=5880;
    k::ExactSelectedKernel narrow(hands(0),hands(1),boards(),64,storage,k::FoldTraversal::mask_classes_v1);
    std::vector<std::size_t> indexes;for(std::size_t i=0;i<64;++i)indexes.push_back(i);
    // The new constructor scratch exceeds this fixture's query scratch. A
    // larger callback fixture independently exercises query-only rejection.
    (void)narrow.terminal(0,indexes,k::TerminalKind::fold,.5,V{1.,1.,1.,1.});
    need(narrow.receipt().terminal_queries==1,"constructor boundary rejects an admitted query");
    std::vector<k::WeightedHand> many_a,many_b;
    for(std::uint8_t a=32;a<52 && many_b.size()<16;++a)
        for(std::uint8_t b=static_cast<std::uint8_t>(a+1);b<52 && many_b.size()<16;++b)
            if(many_a.size()<16) many_a.push_back({{a,b},bits(1.)});
            else many_b.push_back({{a,b},bits(1.)});
    storage.max_storage_entries=8160;
    k::ExactSelectedKernel query_limited(many_a,many_b,boards(),64,storage,k::FoldTraversal::mask_classes_v1);
    const auto query_start=query_limited.receipt();refused=false;
    try {(void)query_limited.terminal(0,indexes,k::TerminalKind::fold,.5,V(16,1.));}
    catch(const k::KernelError& error){refused=error.code()==k::ErrorCode::storage_limit;}
    need(refused && query_limited.receipt().modeled_work==query_start.modeled_work && query_limited.receipt().terminal_queries==0,
         "query-only storage failure changed kernel before admission");
    k::ExactSelectedKernel base(hands(0),hands(1),boards(),64,{},k::FoldTraversal::mask_classes_v1);
    k::Limits budget;budget.max_modeled_work=base.receipt().modeled_work+64*(48*8+512)+112-1;
    k::ExactSelectedKernel limited(hands(0),hands(1),boards(),64,budget,k::FoldTraversal::mask_classes_v1);
    const auto start=limited.receipt();refused=false;
    try {(void)limited.terminal(0,indexes,k::TerminalKind::fold,.5,V{1.,1.,1.,1.});}
    catch(const k::KernelError& error){refused=error.code()==k::ErrorCode::modeled_work_limit;}
    need(refused && limited.receipt().modeled_work==start.modeled_work && limited.receipt().terminal_queries==0,
         "query work failure changed kernel before admission");
}
g::Action act(const char* token) {return {token,0,0,false,token};}
g::Graph graph() {
    g::Graph out;
    std::vector<g::Branch> turns,rivers;
    const char* suits="cdhs";
    for(std::uint8_t i=12;i<20;++i) turns.push_back({std::string(1,i<16?'5':'6')+suits[i%4],6});
    for(std::uint8_t i=24;i<32;++i) rivers.push_back({std::string(1,i<28?'8':'9')+suits[i%4],8});
    out.vertices={g::Vertex::decision(0,{act("fold"),act("call")},{1,2}),
        g::Vertex::terminal(g::TerminalKind::fold,1,{bits(.5),bits(.5)}),
        g::Vertex::chance(g::Street::flop,4,{{"2c3c4c",3}}),
        g::Vertex::decision(1,{act("fold"),act("call")},{4,5}),
        g::Vertex::terminal(g::TerminalKind::fold,0,{bits(.5),bits(.5)}),
        g::Vertex::chance(g::Street::turn,5,std::move(turns)),
        g::Vertex::decision(0,{act("fold"),act("call")},{1,7}),
        g::Vertex::chance(g::Street::river,6,std::move(rivers)),
        g::Vertex::decision(1,{act("fold"),act("call")},{4,9}),
        g::Vertex::terminal(g::TerminalKind::showdown,2,{bits(.5),bits(.5)})};
    return out;
}
void coupled(bool symmetry) {
    g::Plan old(graph(),hands(0,symmetry),hands(1,symmetry),boards(),10,64,{},g::AdmissionProfile::indexed_v1);
    g::Plan candidate(graph(),hands(0,symmetry),hands(1,symmetry),boards(),10,64,{},g::AdmissionProfile::indexed_v1,
                      k::FoldTraversal::mask_classes_v1);
    const auto a=c::Trainer(old).run_active_frames(),b=c::Trainer(candidate).run_active_frames();
    same(a.quotient_policy,b.quotient_policy);
    need(a.receipt.member_checks==b.receipt.member_checks &&
         a.receipt.expected_member_checks==b.receipt.expected_member_checks,"whole-game member contract changed");
    need(candidate.kernel().receipt().fold_class_queries>0,"coupled trainer never used fold classes");
    need(b.receipt.active_frames->final_active_frames==0 && b.receipt.active_frames->value_cursor_learning_calls==0,
         "coupled active lifetime contract changed");
    if(symmetry) need(candidate.group().size()==6,"G6 coupled fixture lost suit group");
    std::cout<<"coupled G="<<candidate.group().size()<<" Q="<<candidate.rows().size()
             <<" fold class queries="<<candidate.kernel().receipt().fold_class_queries<<'\n';
}
int main() {
    try {vectors();guards();coupled(false);coupled(true);std::cout<<"ALL FOLD CLASS CONTROLS PASSED\n";return 0;}
    catch(const std::exception& error){std::cerr<<"FOLD CLASS FAILURE: "<<error.what()<<'\n';return 1;}
}
