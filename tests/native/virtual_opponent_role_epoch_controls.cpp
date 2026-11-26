// Synthetic ownership/role transitions, not complete poker traversals.
#include "../../native/virtual_opponent_role_epoch.hpp"
#include "../../native/virtual_dyadic_training.hpp"
#include <optional>
#include <sstream>
#include <iostream>

namespace r=openpoker::virtual_opponent_role_epoch;
namespace t=openpoker::virtual_dyadic_training;
using Epoch=r::Store::Epoch;
using Function=std::function<void(Epoch&,const r::Certificate&)>;
using Cursor=r::h::History::Cursor;
using Integer=r::Integer;
namespace {
std::ostringstream output;
r::Limits small() {
    r::Limits l;l.rows=3;l.slots=12;l.encounters=6;l.catalog_blocks=8;l.holding_count=2;return l;
}
r::h::Limits history_limits() {
    r::h::Limits l;l.work=t::history_cap;l.nodes=1105;l.entries=32*1105+1;l.owned_bytes=t::history_bytes;l.depth=15;return l;
}
r::c::Limits catalog_limits() {
    r::c::Limits l{8,16,64,8,2,2048,0,0,0};
    l.max_work=r::c::Catalog::work_forecast(l);l.max_metadata_entries=r::c::Catalog::metadata_word_forecast(l);
    l.max_metadata_payload_bits=64*l.max_metadata_entries;return l;
}
r::p::Limits chance_limits() {
    r::p::Limits l;l.max_hands_per_side=2;l.max_integer_bits=181;l.max_modeled_work=1'000'000;
    l.max_storage_entries=12000;l.max_integer_payload_bits=1<<20;return l;
}
struct Shared {
    t::betting::Template source{t::configuration(),t::template_limits()};
    r::h::History history{source,r::p::DeckDefinition::reduced(t::deck_cards),history_limits()};
    r::h::History foreign{source,r::p::DeckDefinition::reduced(t::deck_cards),history_limits()};
    r::c::Catalog catalog{history,{2,2},catalog_limits()};
    Cursor bb;
    Shared() {
        const auto root=history.root();bool found=false;
        for(std::size_t a=0;a<source.nodes()[source.root()].edges.size();++a) {
            const auto child=history.append_action(root,a);const auto& state=source.nodes()[history.source_node(child)].state;
            if(state.phase==t::betting::Phase::decision && state.actor==1){bb=child;found=true;break;}
        }
        r::require(found,"role controls BB decision unavailable");
    }
};
auto make_chance(bool full=false) {
    return r::p::PreparedPublicChance(t::ranges[0],t::ranges[1],r::p::Purpose::joint_tickets_v1,
        full?r::p::DeckDefinition::full52():r::p::DeckDefinition::reduced(t::deck_cards),chance_limits());
}
void apply(r::Store& owner,const Function& function){owner.apply_world(0,0,function);}
void phases(Epoch& epoch,Shared& shared,const r::Certificate& sample,unsigned mask=3) {
    for(std::size_t target=0;target<2;++target) {
        (void)epoch.observe(shared.history.root(),0,sample.holding_indices()[0]);
        if(mask&(1U<<target))(void)epoch.observe(shared.bb,1,sample.holding_indices()[1]);
        epoch.finish_target(target);
    }
    epoch.seal();
}
void stage(Epoch& epoch,const r::Store::Row& row,unsigned root_step=0,bool bb_regret=false) {
    const auto k=row.units.size(),actor=row.descriptor.actor;
    std::array<Integer,4> rr{};std::array<std::uint64_t,4> aa{};
    if(actor==0 && root_step) {
        const std::array<int,4> values=root_step==1?std::array<int,4>{5,-3,0,-2}:std::array<int,4>{0,4,2,-1};
        for(std::size_t a=0;a<k;++a)rr[a]=Integer(values[a])*(Integer(1)<<365);
    }
    if(actor==1 && bb_regret){rr[0]=row.units[1];rr[1]=-Integer(row.units[0]);}
    if(row.roles&(1U<<(1-actor)))std::copy(row.units.begin(),row.units.end(),aa.begin());
    epoch.stage(row.token,std::span(rr).first(k),std::span(aa).first(k));
}
void complete(Epoch& epoch,Shared& shared,const r::Certificate& sample,unsigned mask=3,
              unsigned root_step=0,bool bb_regret=false,r::Store::Token* saved=nullptr) {
    phases(epoch,shared,sample,mask);
    epoch.consume_rows([&](const auto& row){if(saved && row.descriptor.actor==0)*saved=row.token;stage(epoch,row,root_step,bb_regret);});
}
void snapshot(const char* label,unsigned step,r::Store& owner,Shared& shared) {
    owner.visit_committed([&](auto id,std::span<const Integer> rr,std::span<const Integer> aa,std::span<const std::uint64_t> uu) {
        const auto row=shared.catalog.view(id);output<<"ROW "<<label<<' '<<step<<' '<<row.actor<<' '<<row.holding_index<<' '<<row.public_ordinal<<' '<<uu.size();
        for(std::size_t a=0;a<uu.size();++a)output<<' '<<rr[a]<<' '<<aa[a]<<' '<<uu[a];
        output<<'\n';
    });
}
void receipt(const char* label,r::Store& owner) {
    const auto& a=owner.receipt();const auto& b=owner.storage_receipt();const auto& f=owner.admitted_forecast();
    r::require(a.own_work<=f.own_work && b.work+b.quantizer_work<=f.storage.component_work,"role component actual work guard");
    output<<"RECEIPT "<<label<<' '<<a.own_work<<' '<<a.encounters<<' '<<a.frozen_reads<<' '<<a.cache_hits<<' '
        <<a.staged_rows<<' '<<a.staged_slots<<' '<<a.commits<<' '<<a.peak_cache_rows<<' '<<a.peak_cache_slots<<' '
        <<b.reads<<' '<<b.commits<<' '<<b.current_rows<<' '<<b.current_slots<<'\n';
}
void good(Shared& shared,const char* label,unsigned mask,unsigned epochs) {
    auto chance=make_chance();r::Store owner(shared.catalog,shared.history,chance,{2,2},small());
    for(unsigned i=0;i<epochs;++i) {
        apply(owner,[&](Epoch& epoch,const r::Certificate& sample){complete(epoch,shared,sample,epochs==2 && i==1?1U:mask,epochs==2?i+1:0,mask==2);});
        snapshot(label,i+1,owner,shared);
    }
    r::require(!owner.failed(),"role good owner failed");receipt(label,owner);
}
Cursor wrong_public_prefix(Shared& shared,const r::Certificate& sample) {
    std::vector<Cursor> pending{shared.history.root()};
    for(std::size_t i=0;i<pending.size();++i) {
        r::require(pending.size()<=1105,"role reveal search bound");const auto cursor=pending[i];const auto& node=shared.source.nodes()[shared.history.source_node(cursor)];
        if(node.state.phase==t::betting::Phase::reveal && node.state.next_street==3 &&
           shared.source.nodes()[node.edges[0].child].state.phase==t::betting::Phase::decision) {
            auto board=sample.board();
            for(const auto card:t::deck_cards)if(std::find(board.begin(),board.begin()+3,card)==board.begin()+3){board[0]=card;break;}
            std::sort(board.begin(),board.begin()+3);
            return shared.history.append_reveal(cursor,std::span(board).first(3));
        }
        if(node.state.phase==t::betting::Phase::decision)
            for(std::size_t a=0;a<node.edges.size();++a)pending.push_back(shared.history.append_action(cursor,a));
    }
    throw std::runtime_error("role wrong-prefix source unavailable");
}
const std::array<const char*,35> names{
    "duplicate-role","target-order","premature-seal","abandoned-callback","one-target-only","missing-first-root",
    "wrong-holding","wrong-actor","foreign-history-cursor","stage-before-seal","duplicate-stage","default-token",
    "foreign-token","stale-token","wrong-average","uncentered-regret","regret-magnitude","stage-menu",
    "unvisited-regret-role","unvisited-average-role","repeat-enumeration","read-after-seal","finish-after-seal",
    "late-callback-error","swallowed-error","export-while-active","reentrant-world","invalidated-certificate",
    "third-epoch","wrong-public-prefix","wrong-history-deck","missing-second-root",
    "cache-row-bound","cache-slot-bound","role-encounter-bound"};
void bad(Shared& shared,unsigned kind) {
    auto chance=make_chance(kind==30);auto limits=small();
    if(kind==32)limits.rows=1;
    if(kind==33)limits.slots=4;
    if(kind==34)limits.encounters=2;
    r::Store owner(shared.catalog,shared.history,chance,{2,2},limits);
    r::Store::Token saved;
    std::optional<r::p::PreparedPublicChance> other_chance;
    std::unique_ptr<r::Store> other;
    if(kind==12) {
        other_chance.emplace(t::ranges[0],t::ranges[1],r::p::Purpose::joint_tickets_v1,
            r::p::DeckDefinition::reduced(t::deck_cards),chance_limits());
        other=std::make_unique<r::Store>(shared.catalog,shared.history,*other_chance,std::array<std::size_t,2>{2,2},small());
        apply(*other,[&](Epoch& ep,const r::Certificate& sample){complete(ep,shared,sample,3,0,false,&saved);});
    }
    if(kind==13 || kind==28)apply(owner,[&](Epoch& ep,const r::Certificate& sample){complete(ep,shared,sample,3,0,false,&saved);});
    if(kind==28)apply(owner,[&](Epoch& ep,const r::Certificate& sample){complete(ep,shared,sample);});
    const auto before=owner.receipt().commits;bool refused=false;
    try {
        apply(owner,[&](Epoch& ep,const r::Certificate& sample) {
            const auto root=shared.history.root();const auto holds=sample.holding_indices();
            std::array<Integer,4> zero{};std::array<std::uint64_t,4> averages{};
            if(kind==0){(void)ep.observe(root,0,holds[0]);(void)ep.observe(root,0,holds[0]);}
            if(kind==1)ep.finish_target(1);
            if(kind==2)ep.seal();
            if(kind==3)return;
            if(kind==4){(void)ep.observe(root,0,holds[0]);ep.finish_target(0);return;}
            if(kind==5){(void)ep.observe(shared.bb,1,holds[1]);ep.finish_target(0);}
            if(kind==6)(void)ep.observe(root,0,1-holds[0]);
            if(kind==7)(void)ep.observe(root,1,holds[1]);
            if(kind==8)(void)ep.observe(shared.foreign.root(),0,holds[0]);
            if(kind==9){const auto row=ep.observe(root,0,holds[0]);ep.stage(row.token,zero,averages);}
            if(kind==25)owner.visit_committed([](auto,auto,auto,auto){});
            if(kind==26)apply(owner,[](Epoch&,const r::Certificate&){});
            if(kind==27){try{chance.with_joint_ticket(0,0,[](const auto&){});}catch(const std::exception&){}return;}
            if(kind==29){const auto cursor=wrong_public_prefix(shared,sample);const auto info=shared.history.decision_key(cursor);(void)ep.observe(cursor,info.actor,holds[info.actor]);}
            if(kind==31){(void)ep.observe(root,0,holds[0]);ep.finish_target(0);(void)ep.observe(shared.bb,1,holds[1]);ep.finish_target(1);}
            phases(ep,shared,sample,kind==18?1U:kind==19?2U:3U);
            if(kind==21)(void)ep.observe(root,0,holds[0]);
            if(kind==22)ep.finish_target(1);
            ep.consume_rows([&](const auto& row) {
                const auto k=row.units.size();const auto actor=row.descriptor.actor;
                if(actor==0 && (kind==11 || kind==12 || kind==13))ep.stage(kind==11?r::Store::Token{}:saved,zero,std::span(averages).first(k));
                if(actor==0 && kind==14)ep.stage(row.token,zero,std::span(averages).first(k));
                if(actor==0 && (kind==15 || kind==16 || kind==17)) {
                    auto rr=zero;rr[0]=kind==16?(Integer(17)<<365):Integer(1);
                    if(kind==16)rr[1]=-rr[0];
                    std::copy(row.units.begin(),row.units.end(),averages.begin());
                    ep.stage(row.token,std::span(rr).first(kind==17?k-1:k),std::span(averages).first(k));
                }
                if(actor==1 && kind==18){auto rr=zero;rr[0]=1;std::copy(row.units.begin(),row.units.end(),averages.begin());ep.stage(row.token,std::span(rr).first(k),std::span(averages).first(k));}
                if(actor==1 && kind==19){std::copy(row.units.begin(),row.units.end(),averages.begin());ep.stage(row.token,std::span(zero).first(k),std::span(averages).first(k));}
                stage(ep,row);
                if(actor==0 && kind==10)stage(ep,row);
                if(actor==0 && kind==24){try{stage(ep,row);}catch(const std::exception&){} }
            });
            if(kind==20)ep.consume_rows([](const auto&){});
            if(kind==23)throw std::runtime_error("late producer failure");
        });
    }catch(const std::exception&){refused=true;}
    r::require(refused && owner.failed() && owner.receipt().commits==before,"role guard accepted or published invalid epoch");
    bool closed=false;try{apply(owner,[](Epoch&,const r::Certificate&){});}catch(const std::exception&){closed=true;}
    r::require(closed && owner.receipt().commits==before,"role guard failed owner reused");
    output<<"GUARD "<<names[kind]<<" PASS "<<before<<'\n';
}
template<class F> void constructor_guard(const char* name,F&& function) {
    bool refused=false;try{function();}catch(const std::exception&){refused=true;}
    r::require(refused,"role constructor guard accepted");output<<"GUARD "<<name<<" PASS 0\n";
}
void forecasts(const char* name,r::Limits limits) {
    const auto f=r::forecast(limits);const auto& s=f.storage;
    output<<"FORECAST "<<name<<' '<<f.own_work<<' '<<f.extra_history_work<<' '<<f.work<<' '<<f.cache_entries<<' '
        <<f.cache_payload_bits<<' '<<f.entries<<' '<<f.payload_bits<<' '<<s.own_work<<' '<<s.quantizer_work<<' '
        <<s.catalog_read_work<<' '<<s.history_read_work<<' '<<s.work<<' '<<s.entries<<' '<<s.payload_bits<<'\n';
}
void address_reuse(Shared& shared) {
    alignas(r::Store) std::array<std::byte,sizeof(r::Store)> memory{};
    const auto destroy=[](r::Store* owner){std::destroy_at(owner);};
    auto first_chance=make_chance();auto second_chance=make_chance();r::Store::Token saved;
    std::unique_ptr<r::Store,decltype(destroy)> owner(std::construct_at(reinterpret_cast<r::Store*>(memory.data()),
        shared.catalog,shared.history,first_chance,std::array<std::size_t,2>{2,2},small()),destroy);
    apply(*owner,[&](Epoch& ep,const r::Certificate& sample){complete(ep,shared,sample,3,0,false,&saved);});
    const auto address=owner.get();owner.reset();
    owner.reset(std::construct_at(reinterpret_cast<r::Store*>(memory.data()),shared.catalog,shared.history,
        second_chance,std::array<std::size_t,2>{2,2},small()));
    r::require(owner.get()==address,"role address reuse control did not reuse address");
    bool refused=false;
    try {
        apply(*owner,[&](Epoch& ep,const r::Certificate& sample) {
            phases(ep,shared,sample);
            ep.consume_rows([&](const auto& row) {
                if(row.descriptor.actor==0){std::array<Integer,4> rr{};ep.stage(saved,rr,row.units);}
                else stage(ep,row);
            });
        });
    }catch(const std::exception&){refused=true;}
    r::require(refused && owner->failed() && owner->receipt().commits==0,"role token accepted recycled owner address");
    output<<"GUARD recycled-store-address PASS 0\n";
}
void aliases(Shared& shared) {
    auto chance=make_chance();r::Store owner(shared.catalog,shared.history,chance,{2,2},small());
    apply(owner,[&](Epoch& ep,const r::Certificate& sample) {
        std::map<std::size_t,std::pair<std::size_t,Cursor>> sources;std::vector<Cursor> pending{shared.history.root()};
        std::optional<std::array<Cursor,2>> match;std::size_t matched_source=0;
        for(std::size_t i=0;i<pending.size() && !match;++i) {
            r::require(pending.size()<=1105,"role alias search bound");const auto cursor=pending[i];
            const auto& node=shared.source.nodes()[shared.history.source_node(cursor)];
            if(node.state.phase==t::betting::Phase::decision) {
                const auto key=shared.history.decision_key(cursor);const auto found=sources.find(key.source);
                if(found!=sources.end() && found->second.first!=key.ordinal){match=std::array{found->second.second,cursor};matched_source=key.source;break;}
                sources.emplace(key.source,std::pair{key.ordinal,cursor});
                for(std::size_t a=0;a<node.edges.size();++a)pending.push_back(shared.history.append_action(cursor,a));
            } else if(node.state.phase==t::betting::Phase::reveal)
                pending.push_back(shared.history.append_reveal(cursor,std::span(sample.board()).first(node.state.next_street)));
        }
        r::require(bool(match),"role shared-source decision witness unavailable");
        (void)ep.observe(shared.history.root(),0,sample.holding_indices()[0]);std::array<std::size_t,2> ordinals{};
        for(std::size_t i=0;i<2;++i) {
            const auto key=shared.history.decision_key((*match)[i]);ordinals[i]=key.ordinal;
            (void)ep.observe((*match)[i],key.actor,sample.holding_indices()[key.actor]);
        }
        ep.finish_target(0);(void)ep.observe(shared.history.root(),0,sample.holding_indices()[0]);ep.finish_target(1);ep.seal();
        ep.consume_rows([&](const auto& row){stage(ep,row);});
        r::require(ordinals[0]!=ordinals[1],"role alias witness collapsed full histories");
        output<<"ALIAS "<<matched_source<<' '<<ordinals[0]<<' '<<ordinals[1]<<' '
            <<unsigned(shared.source.nodes()[matched_source].state.actor)<<' '<<shared.source.nodes()[matched_source].edges.size()<<'\n';
    });
    r::require(owner.receipt().frozen_reads==3 && owner.receipt().cache_hits==1 && owner.receipt().staged_rows==3,
        "role shared numeric source collapsed policy rows");
    snapshot("shared-source",1,owner,shared);receipt("shared-source",owner);
}
}
int main() {
    try {
        static_assert(!std::is_copy_constructible_v<Epoch> && !std::is_move_constructible_v<Epoch>);
        static_assert(!std::is_constructible_v<Epoch,r::Store&,const r::Certificate&>);
        const auto f=r::forecast(small());const auto cat=catalog_limits();
        const auto chance_bound=64*(r::p::PreparedPublicChance::weighted_joint_setup_work_bound(2,2)+
            2*r::p::PreparedPublicChance::weighted_joint_ticket_work_bound(2,2));
        const auto work=t::template_cap+2*t::history_cap+cat.max_work+64*f.work+chance_bound+1'000'000+16*65536;
        const auto entries=131072+2*(32*1105+1)+cat.max_metadata_entries+2*f.entries+12000+16384+2*65536+2048;
        const auto payload=131072*64ULL+2*(8ULL<<20)+64*cat.max_metadata_entries+2*f.payload_bits+(1<<20)+(1<<22)+16*65536;
        r::require(work<=t::work_cap && chance_bound<=t::chance_cap && entries<=t::entries_cap && payload<=t::payload_cap,
            "complete role component controls envelope");
        output<<"ROLE_EPOCH_COMPONENT_V1\n";forecasts("full",{});forecasts("small",small());
        output<<"PROBE_FORECAST "<<work<<' '<<entries<<' '<<payload<<' '<<chance_bound<<'\n';
        Shared shared;
        good(shared,"both",3,2);good(shared,"average-only",1,1);good(shared,"regret-only",2,1);
        for(unsigned kind=0;kind<names.size();++kind)bad(shared,kind);
        auto chance=make_chance();
        constructor_guard("foreign-catalog-history",[&]{r::Store owner(shared.catalog,shared.foreign,chance,{2,2},small());});
        constructor_guard("range-binding",[&]{r::Store owner(shared.catalog,shared.history,chance,{1,2},small());});
        for(unsigned kind=0;kind<6;++kind) {
            auto limits=small();const auto base=r::forecast(limits);
            if(kind==0)limits.work=base.work-1;
            if(kind==1)limits.entries=base.entries-1;
            if(kind==2)limits.payload_bits=base.payload_bits-1;
            if(kind==3)limits.rows=205;
            if(kind==4)limits.encounters=205;
            if(kind==5)limits.slots=817;
            const std::array<const char*,6> labels{"reduce-work","reduce-entries","reduce-payload","row-ceiling","encounter-ceiling","slot-ceiling"};
            constructor_guard(labels[kind],[&]{r::Store owner(shared.catalog,shared.history,chance,{2,2},limits);});
        }
        address_reuse(shared);aliases(shared);
        output<<"STATIC_EPOCH_SCOPE PASS 3\n";
        output<<"ROLE_EPOCH_COMPONENT_PASS 44 5\n";
        const auto text=output.str();r::require(text.size()<=65536,"role controls output bound");std::cout<<text;return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
