// Synthetic same-owner compact arithmetic only; no full poker-walk claim.
#include "../../native/virtual_opponent_role_walk_forecast.hpp"
#include <iostream>
#include <sstream>
namespace f=openpoker::virtual_opponent_role_walk_forecast;
namespace r=f::r;
namespace e=r::e;
namespace t=f::t;
using Integer=e::Integer;
namespace {
std::ostringstream output;
template<class Function> void refuses(const char* label,Function&& operation) {
    bool rejected=false;try{operation();}catch(const std::exception&){rejected=true;}
    r::require(rejected,"compact Store guard accepted");output<<"GUARD "<<label<<" PASS\n";
}
r::Limits tiny() {
    r::Limits l;l.rows=1;l.slots=4;l.encounters=2;l.catalog_blocks=8;l.holding_count=2;
    l.persistent=r::PersistentCarrier::compact;return l;
}
r::c::Limits catalog_limits() {
    r::c::Limits l{8,16,64,8,2,64,0,0,0};l.max_work=r::c::Catalog::work_forecast(l);
    l.max_metadata_entries=r::c::Catalog::metadata_word_forecast(l);l.max_metadata_payload_bits=64*l.max_metadata_entries;return l;
}
t::prepared::Limits chance_limits() {
    t::prepared::Limits l;l.max_hands_per_side=2;l.max_integer_bits=181;l.max_modeled_work=1'000'000;
    l.max_storage_entries=12000;l.max_integer_payload_bits=1<<20;return l;
}
struct Fixture {
    r::c::Catalog catalog;
    t::prepared::PreparedPublicChance chance;
    r::Store owner;
    explicit Fixture(r::h::History& history)
        :catalog(history,{2,2},catalog_limits()),
         chance(t::ranges[0],t::ranges[1],t::prepared::Purpose::joint_tickets_v1,
            t::prepared::DeckDefinition::reduced(t::deck_cards),chance_limits()),
         owner(catalog,history,chance,{2,2},tiny()) {}
};
}
int main(int argc,char**) {
    try {
        r::require(argc==1,"compact Store controls accept no arguments");
        const auto rf=r::forecast(tiny());const auto cl=catalog_limits();(void)f::domain(r::PersistentCarrier::compact,true);
        const auto work=t::template_cap+t::history_cap+9*(1'000'000+cl.max_work+2*rf.work)+1'000'000+16*65536;
        const auto entries=131072+35361+9*(12000+cl.max_metadata_entries+2*rf.entries)+65536+16384;
        const auto payload=131072*64ULL+(8ULL<<20)+9*((1ULL<<20)+64*cl.max_metadata_entries+2*rf.payload_bits)+(1ULL<<22)+8*65536;
        r::require(work<=t::work_cap && entries<=t::entries_cap && payload<=t::payload_cap,
            "compact Store complete control batch admission");
        output<<"COMPACT_STORE_BUDGET "<<work<<' '<<entries<<' '<<payload<<'\n';
        refuses("unknown-persistent",[]{auto l=tiny();l.persistent=static_cast<r::PersistentCarrier>(255);(void)r::forecast(l);});
        refuses("compact-without-observation",[]{(void)f::domain(r::PersistentCarrier::compact,false);});
        t::betting::Template source(t::configuration(),t::template_limits());r::h::Limits hl;
        hl.work=t::history_cap;hl.nodes=1105;hl.entries=35361;hl.owned_bytes=t::history_bytes;hl.depth=15;
        r::h::History history(source,t::prepared::DeckDefinition::reduced(t::deck_cards),hl);
        const Integer dr=Integer(1)<<365;const Integer da=Integer(1)<<52;
        {
            Fixture fixture(history);
            for(unsigned step=0;step<2;++step) {
                fixture.owner.apply_world(0,0,[&](r::Store::Epoch& epoch,const r::Certificate& sample) {
                    r::Store::Token token;std::array<std::uint64_t,4> averages{};
                    for(unsigned target=0;target<2;++target) {
                        const auto row=epoch.observe(history.root(),0,sample.holding_indices()[0]);
                        r::require(row.units.size()==4,"compact Store root menu");token=row.token;
                        std::copy(row.units.begin(),row.units.end(),averages.begin());epoch.finish_target(target);
                    }
                    epoch.seal();const std::array<Integer,4> regrets=step?std::array<Integer,4>{0,2*dr,0,0}:std::array<Integer,4>{dr,-dr,0,0};
                    epoch.stage(token,regrets,averages);
                });
                std::size_t rows=0;
                fixture.owner.visit_committed([&](auto,std::span<const Integer> rr,std::span<const Integer> aa,std::span<const std::uint64_t> units) {
                    ++rows;r::require(rr.size()==4 && aa.size()==4 && units.size()==4,"compact Store complete exported row");
                    const std::array<Integer,4> expected_r=step?std::array<Integer,4>{dr,dr,0,0}:std::array<Integer,4>{dr,-dr,0,0};
                    const std::array<Integer,4> expected_a=step?std::array<Integer,4>{5*da/4,da/4,da/4,da/4}:std::array<Integer,4>{da/4,da/4,da/4,da/4};
                    const std::array<std::uint64_t,4> expected_units=step?std::array<std::uint64_t,4>{t::grid/2,t::grid/2,0,0}:std::array<std::uint64_t,4>{t::grid,0,0,0};
                    for(std::size_t a=0;a<4;++a)r::require(rr[a]==expected_r[a] && aa[a]==expected_a[a] && units[a]==expected_units[a],
                        "compact Store exact evolving state/policy");
                    output<<"ROW "<<step+1;for(std::size_t a=0;a<4;++a)output<<' '<<rr[a]<<' '<<aa[a]<<' '<<units[a];output<<'\n';
                });
                r::require(rows==1 && fixture.owner.receipt().commits==step+1,"compact Store complete exact commit/export");
            }
        }
        const auto sl=rf.storage_limits;
        refuses("two-policy-reads",[&]{Fixture fixture(history);auto limits=sl;limits.policy_reads_per_row=2;limits.max_reads=4;
            e::Store invalid(fixture.catalog,history,{2,2},limits,e::ArithmeticContract::weighted_joint_role_compact);});
        refuses("unknown-arithmetic",[&]{Fixture fixture(history);
            e::Store invalid(fixture.catalog,history,{2,2},sl,static_cast<e::ArithmeticContract>(255));});
        const std::array<const char*,6> labels{"canonical-regret-scale","canonical-average-scale","wide-regret","wide-average","negative-average","uncentered-regret"};
        for(std::size_t guard=0;guard<labels.size();++guard)refuses(labels[guard],[&] {
            Fixture fixture(history);e::Store owner(fixture.catalog,history,{2,2},sl,e::ArithmeticContract::weighted_joint_role_compact);
            auto lease=owner.begin_epoch(e::ProposalLaw::true_joint);const auto view=lease.frozen_policy(history.root(),0,0);
            r::require(view.units.size()==4 && owner.regret_denominator_value()==dr && owner.average_denominator_value()==da,
                "compact Store private denominator/read contract");
            lease.seal_raw_walk(1,4,1);std::array<Integer,4> rr{0,0,0,0},aa{da/4,da/4,da/4,da/4};Integer ar=da,rg=dr;
            if(guard==0)rg=Integer(1)<<625;
            if(guard==1)ar=Integer(1)<<364;
            if(guard==2){rr[0]=Integer(1)<<370;rr[1]=-rr[0];}
            if(guard==3){aa[0]=Integer(1)<<53;aa[1]=0;}
            if(guard==4){aa[0]=-1;aa[1]=0;}
            if(guard==5)rr[0]=1;
            try{lease.stage(view.id,rr,aa,ar,rg);}
            catch(...){r::require(owner.failed() && owner.receipt().commits==0,"compact Store rejection published state");throw;}
        });
        r::require(history.receipt().work<=t::history_cap,"compact Store cumulative shared History work");
        output<<"COMPACT_STORE_PASS 2 24 10\n";const auto raw=output.str();r::require(raw.size()<=65536,"compact Store output cap");
        std::cout<<raw;return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
