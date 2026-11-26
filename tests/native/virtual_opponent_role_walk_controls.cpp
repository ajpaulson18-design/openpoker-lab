// Exact ticket intervals, signed raw words, and foreign active certificate.
#include "../../native/virtual_opponent_role_walk.hpp"
#include <iostream>
#include <sstream>
namespace w=openpoker::virtual_opponent_role_walk;
namespace t=w::t;
namespace r=w::r;
using Integer=w::Integer;
namespace {
std::ostringstream output;
template<class F> void refuses(const char* label,F&& operation) {
    bool rejected=false;try{operation();}catch(const std::exception&){rejected=true;}
    t::require(rejected,"role walk scalar guard accepted");output<<"GUARD "<<label<<" PASS\n";
}
}
int main(int argc,char**) {
    try {
        t::require(argc==1,"role walk controls accept no arguments");(void)w::f::domain();
        r::Limits tiny;tiny.rows=1;tiny.slots=4;tiny.encounters=2;tiny.catalog_blocks=8;tiny.holding_count=2;
        const auto role=r::forecast(tiny);r::c::Limits cl{8,16,64,8,2,64,0,0,0};
        cl.max_work=r::c::Catalog::work_forecast(cl);cl.max_metadata_entries=r::c::Catalog::metadata_word_forecast(cl);
        cl.max_metadata_payload_bits=64*cl.max_metadata_entries;
        const auto control_work=t::template_cap+t::history_cap+cl.max_work+2*1'000'000+role.work+1'000'000+16*65536;
        const auto control_entries=131072+(32*1105+1)+cl.max_metadata_entries+2*12000+role.entries+16384+2*65536;
        const auto control_payload=131072*64ULL+(8ULL<<20)+64*cl.max_metadata_entries+2*(1ULL<<20)+role.payload_bits+(1ULL<<22)+16*65536;
        t::require(control_work<=t::work_cap && control_entries<=t::entries_cap && control_payload<=t::payload_cap,
            "role scalar/world controls complete envelope");
        output<<"CONTROL_BUDGET "<<control_work<<' '<<control_entries<<' '<<control_payload<<'\n';
        constexpr auto q=t::grid;
        const std::array<std::vector<std::uint64_t>,8> profiles{
            std::vector<std::uint64_t>{q/2,q/2},{q,0},{0,q},{1,q-1},
            {q/3+1,q/3,q/3},{0,q/2,q/2},{1,q-3,1,1},{0,0,q,0}};
        std::size_t queries=0;
        for(std::size_t profile=0;profile<profiles.size();++profile) {
            const auto& units=profiles[profile];std::uint64_t left=0;
            for(std::size_t a=0;a<units.size();++a) {
                if(units[a])for(const auto ticket:std::array<std::uint64_t,3>{left,left+units[a]-1,left+(units[a]-1)/2}) {
                    const auto selected=w::select(units,ticket);t::require(selected==a,"role CDF interval boundary");
                    output<<"SELECT "<<profile<<' '<<units.size()<<' '<<ticket<<' '<<selected;
                    for(const auto u:units)output<<' '<<u;
                    output<<'\n';++queries;
                }
                left+=units[a];
            }
        }
        refuses("ticket-Q",[&]{(void)w::select(profiles[0],q);});
        refuses("empty-menu",[]{(void)w::select({},0);});
        refuses("single-action",[&]{(void)w::select(std::array<std::uint64_t,1>{q},0);});
        refuses("short-partition",[&]{(void)w::select(std::array<std::uint64_t,2>{q-1,0},0);});
        refuses("overflow-partition",[&]{(void)w::select(std::array<std::uint64_t,2>{q,1},0);});
        const Integer d=Integer(1)<<365;
        const std::array<Integer,7> numbers{0,1,-1,16*d,-16*d,d-1,-(d-1)};
        for(std::size_t i=0;i<numbers.size();++i) {
            const auto packed=w::pack(numbers[i]);t::require(w::unpack(packed)==numbers[i],"role signed raw codec round trip");
            output<<"PACK "<<i<<' '<<numbers[i];for(const auto word:packed)output<<' '<<word;output<<'\n';
        }
        refuses("wide-pack",[]{(void)w::pack(Integer(1)<<447);});
        refuses("wide-unpack",[]{w::Packed raw{};raw[6]=1;(void)w::unpack(raw);});
        t::betting::Template source(t::configuration(),t::template_limits());r::h::Limits hl;
        hl.work=t::history_cap;hl.nodes=1105;hl.entries=32*1105+1;hl.owned_bytes=t::history_bytes;hl.depth=15;
        const auto deck=t::prepared::DeckDefinition::reduced(t::deck_cards);r::h::History history(source,deck,hl);
        r::c::Catalog catalog(history,{2,2},cl);t::prepared::Limits pl;
        pl.max_hands_per_side=2;pl.max_integer_bits=181;pl.max_modeled_work=1'000'000;pl.max_storage_entries=12000;pl.max_integer_payload_bits=1<<20;
        t::prepared::PreparedPublicChance first(t::ranges[0],t::ranges[1],t::prepared::Purpose::joint_tickets_v1,deck,pl);
        t::prepared::PreparedPublicChance second(t::ranges[0],t::ranges[1],t::prepared::Purpose::joint_tickets_v1,deck,pl);
        r::Store owner(catalog,history,first,{2,2},tiny);
        refuses("foreign-active-world",[&]{
            owner.apply_world(0,0,[&](r::Store::Epoch& epoch,const r::Certificate& actual) {
                second.with_joint_ticket(0,0,[&](const r::Certificate& foreign) {
                    t::require(actual.board()==foreign.board() && actual.holding_indices()==foreign.holding_indices(),"foreign identity witness values differ");
                    epoch.require_world(foreign);
                });
            });
        });
        t::require(owner.failed() && owner.receipt().commits==0,"foreign active world published state");
        output<<"ROLE_WALK_CONTROLS_PASS "<<queries<<" 7 8\n";
        const auto raw=output.str();t::require(raw.size()<=65536,"role walk controls output bound");std::cout<<raw;return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
