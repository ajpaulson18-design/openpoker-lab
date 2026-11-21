// Two raw walks share one immutable epoch. No training or policy transition.
#include "../../native/virtual_frozen_grid_raw.hpp"
#include "../../native/virtual_frozen_policy_session_forecast.hpp"
#include <charconv>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

namespace t=openpoker::virtual_dyadic_training;
namespace s=t::state;
namespace h=t::history;
namespace p=openpoker::virtual_frozen_grid_update_forecast;
namespace snap=openpoker::virtual_frozen_policy_snapshot;
namespace raw=openpoker::virtual_frozen_grid_raw;
namespace proposal=openpoker::virtual_frozen_update;
namespace session=openpoker::virtual_frozen_policy_session;

namespace {
std::string_view argument(const char* text,std::size_t bound) {
    std::size_t n=0;while(n<=bound && text[n])++n;
    t::require(n<=bound,"session argument byte boundary");return {text,n};
}
void integer(snap::Output& output,const t::Integer& value,std::size_t words,bool signed_value) {
    const auto bits=raw::magnitude_bits(value);
    t::require((signed_value || value>=0) && bits<=(signed_value?words*64-1:words*64),"session wire integer width");
    const auto& backend=value.backend();const bool negative=value<0;
    constexpr auto limb_bits=std::numeric_limits<boost::multiprecision::limb_type>::digits;
    static_assert(limb_bits==32 || limb_bits==64);
    constexpr auto parts=64/limb_bits;std::uint64_t carry=negative?1:0;
    for(std::size_t i=0;i<words;++i) {
        std::uint64_t limb=0;
        for(std::size_t part=0;part<parts;++part) {
            const auto index=i*parts+part;
            if(index<backend.size())limb|=static_cast<std::uint64_t>(backend.limbs()[index])<<(part*limb_bits);
        }
        if(negative){const auto sum=(~limb)+carry;carry=static_cast<std::uint64_t>(carry && sum==0);limb=sum;}
        output.word(limb);
    }
}
int run(const std::filesystem::path& path,const std::array<session::Selector,2>& selectors) {
    static_assert(std::endian::native==std::endian::little);
    static_assert(session::domain_work<=t::work_cap && session::domain_entries<=t::entries_cap &&
                  session::domain_payload<=t::payload_cap && session::domain_output<=snap::output_cap);
    // Both complete selectors are admitted before any shared owner is built.
    for(const auto& request:selectors)
        (void)proposal::proposal_for(t::chance::DeckDefinition::reduced(t::deck_cards),request.board,request.law);
    snap::Input input(path);const auto header=snap::read_header(input);
    const t::betting::Template source(t::configuration(),t::template_limits());
    p::Geometry geometry;p::census(source,source.root(),{},geometry);
    const auto f=session::forecast(geometry,selectors);
    t::require(f.feasible && f.work<=session::domain_work && f.entries<=session::domain_entries &&
               f.payload<=session::domain_payload && f.output<=session::domain_output,"session whole-request admission rejected");
    t::require(geometry.visits==1105 && geometry.depth==std::array<std::size_t,2>{6,7} &&
               geometry.route==12 && geometry.mix_route==11,"session source route census");
    t::Meter meter;meter.charge(t::Work::geometry,session::geometry_work);
    const auto plan=t::Forecast(source,meter,t::Traversal::by_seat,t::StrategyProfile::dense).make();
    const auto& dense=t::proof9.shape;t::require(plan.shape==dense,"session catalog geometry");
    const auto catalog=3000000+8*dense.visits+64*dense.candidates+16*dense.rows+4*dense.slots;
    t::WorkList limits{};limits[t::work_index(t::Work::geometry)]=3000000;
    limits[t::work_index(t::Work::visit)]=8*dense.visits;limits[t::work_index(t::Work::support)]=64*dense.candidates;
    limits[t::work_index(t::Work::route)]=16*dense.rows+4*dense.slots;meter.seal(limits,catalog);
    t::chance::Limits chance_limits;chance_limits.max_hands_per_side=2;chance_limits.max_integer_bits=384;
    chance_limits.max_modeled_work=f.chance;chance_limits.max_storage_entries=t::chance_entries;
    chance_limits.max_integer_payload_bits=t::chance_payload;
    t::prepared::PreparedPublicChance chance(t::ranges[0],t::ranges[1],
        t::chance::DeckDefinition::reduced(t::deck_cards),chance_limits,64);
    t::require(chance.normalizer_integer()==29,"session prior normalizer");
    h::Limits history_limits;history_limits.work=f.history;history_limits.nodes=t::literal_count;
    history_limits.entries=32*t::literal_count+1;history_limits.owned_bytes=t::history_bytes;history_limits.depth=15;
    h::History history(source,t::chance::DeckDefinition::reduced(t::deck_cards),history_limits);
    s::Forecast sf{24420,58164,1,15,648,f.state,1};
    const s::Integer denominator=s::Integer(580)<<625;
    s::State state(history,{2,2},denominator,sf,{t::state_cap,65536,t::entries_cap,t::payload_cap},{388,410,false});
    (void)t::Walk<false>(source,plan,meter,history,chance,state,2).run(history.root());
    state.begin_frozen_policy_import(static_cast<std::size_t>(f.reads));
    snap::import_rows(input,header,history,source,state);
    const auto counters=[&]{return std::array<std::uint64_t,5>{state.receipt().state_work,history.receipt().work,
        chance.receipt().modeled_work,chance.receipt().rank_calls,chance.receipt().completed_contractions};};
    std::array<std::unique_ptr<raw::Walk>,2> walks;
    std::array<const raw::Result*,2> results{};
    std::array<std::array<std::uint64_t,5>,2> deltas{};
    std::uint64_t parent=session::session_metadata_work;std::size_t peak=0;
    for(std::size_t i=0;i<2;++i) {
        const auto before=counters();
        walks[i]=std::make_unique<raw::Walk>(source,history,state,chance,geometry,f.boards[i],selectors[i].board,selectors[i].law);
        const auto& result=walks[i]->run();t::require(walks[i]->complete(),"session raw result incomplete");
        results[i]=&result;
        const auto after=counters();for(std::size_t j=0;j<5;++j)deltas[i][j]=after[j]-before[j];
        parent+=walks[i]->ledger().total();peak=std::max(peak,result.peak_bits);
    }
    t::require(parent+catalog<=f.parent && chance.receipt().completed_contractions==2440 &&
        chance.receipt().rank_calls<=8 && state.receipt().completed_sweeps==0 && state.receipt().staged_rows==0 &&
        state.receipt().quantizer_work==0,"session cumulative raw scope");
    // Both complete results remain owned until validation above finishes.
    // There is no first-board stdout publication or partial success response.
#ifdef _WIN32
    t::require(_setmode(_fileno(stdout),_O_BINARY)!=-1,"session binary stdout mode");
#endif
    snap::Output output;output.bytes("OPLGEP01",8);
    const std::array<std::uint64_t,16> global{1,2,24420,58164,t::grid,f.work,f.entries,f.payload,
        f.state,f.history,f.chance,f.parent,f.output,f.stage_payload,f.reads,session::geometry_work};
    for(const auto value:global)output.word(value);
    for(std::size_t row=0;row<24420;++row) {
        const auto record=state.row_at(row);const auto cursor=history.decision_cursor(record.history_ordinal);
        const auto view=state.frozen_policy(cursor,record.actor,record.holding_index);
        for(const auto value:std::array<std::uint64_t,5>{record.actor,record.holding_index,record.history_ordinal,record.offset,view.units.size()})output.word(value);
        for(const auto value:view.units)output.word(value);
    }
    for(std::size_t i=0;i<2;++i) {
        const auto& request=selectors[i];const auto& b=f.boards[i];const auto& result=*results[i];
        output.bytes("OPLGBD01",8);
        const std::array<std::uint64_t,31> fields{1,24420,58164,b.rows,b.slots,
            static_cast<std::uint64_t>(request.law==proposal::ProposalKind::weighted_river_proof9),
            request.board[0],request.board[1],request.board[2],request.board[3],request.board[4],t::grid,
            b.work,b.entries,b.payload,b.state,b.history,b.chance,b.reach,b.scale,b.mix,b.average,b.stage,b.walk,
            b.output-1442112,b.stage_payload,b.reads,704,11,12,static_cast<std::uint64_t>(b.physical)};
        for(const auto value:fields)output.word(value);
        integer(output,result.denominator,11,false);for(const auto& root:result.roots)integer(output,root,11,true);
        for(const auto& row:result.rows) {
            for(const auto value:std::array<std::uint64_t,5>{row.actor,row.holding,row.ordinal,row.offset,row.actions})output.word(value);
            integer(output,row.average_denominator,6,false);integer(output,row.average_mass,6,false);
            for(std::size_t a=0;a<row.actions;++a){integer(output,row.regret[a],11,true);integer(output,row.average[a],6,false);}
        }
        std::array<std::uint64_t,26> footer{1,result.rows.size(),result.slots,walks[i]->ledger().total(),result.peak_bits,
            result.reads,result.visits,result.actions,result.reveals,result.terminals,
            deltas[i][0],deltas[i][1],deltas[i][2],deltas[i][3],deltas[i][4],0,0,0};
        const auto& families=walks[i]->ledger().actual();for(std::size_t j=0;j<6;++j)footer[18+j]=families[j];
        footer[24]=i;footer[25]=f.reads;for(const auto value:footer)output.word(value);
    }
    const auto st=state.receipt();const auto policy=state.frozen_policy_receipt();
    const auto actual=source.receipt().work+meter.total()+st.state_work+history.receipt().work+
        chance.receipt().modeled_work+parent+16*input.used()+16*f.output;
    t::require(actual<=f.work && st.state_work<=f.state && history.receipt().work<=f.history &&
        chance.receipt().modeled_work<=f.chance && policy.imported_rows==24420 && policy.read_calls==f.reads &&
        policy.ready && output.written()+208==f.output,"session final cumulative resource census");
    const std::array<std::uint64_t,26> footer{1,24420,58164,2,actual,source.receipt().work,meter.total(),st.state_work,
        history.receipt().work,chance.receipt().modeled_work,parent,input.used(),f.output,peak,
        chance.receipt().rank_calls,chance.receipt().completed_contractions,0,0,0,policy.imported_rows,policy.read_calls,
        4420,4156,260,4,1};
    for(const auto value:footer)output.word(value);t::require(output.written()==f.output,"session wire byte census");return 0;
}
}
int main(int argc,char** argv) {
    try {
        t::require(argc==14,"session requires snapshot and exactly two proposal/board selectors");
        const auto path=argument(argv[1],1024);std::array<session::Selector,2> selectors{};
        for(std::size_t i=0;i<2;++i) {
            const auto law=argument(argv[2+6*i],14);
            t::require(law=="uniform" || law=="river_weighted","unsupported session proposal");
            selectors[i].law=law=="uniform"?proposal::ProposalKind::uniform_public:proposal::ProposalKind::weighted_river_proof9;
            for(std::size_t j=0;j<5;++j) {
                const auto text=argument(argv[3+6*i+j],2);unsigned card=0;
                const auto parsed=std::from_chars(text.data(),text.data()+text.size(),card);
                t::require(parsed.ec==std::errc{} && parsed.ptr==text.data()+text.size() && card<52,"session original card ID");
                selectors[i].board[j]=static_cast<std::uint8_t>(card);
            }
        }
        return run(std::filesystem::path(path),selectors);
    } catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
