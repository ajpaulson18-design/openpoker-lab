// Explicit fixed-policy per-board study. No training, clipping or solver API.
#include "../../native/virtual_frozen_grid_raw.hpp"
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

namespace {
std::string_view bounded_argument(const char* input,std::size_t bound) {
    std::size_t n=0;while (n<=bound && input[n]) ++n;
    t::require(n<=bound,"raw study argument byte boundary");return {input,n};
}
void integer(snap::Output& output,const t::Integer& value,std::size_t words,bool signed_value) {
    const auto bits=raw::magnitude_bits(value);
    t::require((signed_value || value>=0) && bits<=(signed_value?words*64-1:words*64),"raw wire integer width");
    const auto& backend=value.backend();const bool negative=value<0;
    constexpr auto limb_bits=std::numeric_limits<boost::multiprecision::limb_type>::digits;
    static_assert(limb_bits==32 || limb_bits==64);
    constexpr auto parts=64/limb_bits;
    std::uint64_t carry=negative?1:0;
    for (std::size_t i=0;i<words;++i) {
        std::uint64_t limb=0;
        for (std::size_t part=0;part<parts;++part) {
            const auto index=i*parts+part;
            if (index<backend.size()) limb|=static_cast<std::uint64_t>(backend.limbs()[index])<<(part*limb_bits);
        }
        if (negative) {const auto sum=(~limb)+carry;carry=static_cast<std::uint64_t>(carry && sum==0);limb=sum;}
        output.word(limb);
    }
}
int run(const std::filesystem::path& input_path,proposal::ProposalKind law,const std::array<std::uint8_t,5>& board) {
    static_assert(std::endian::native==std::endian::little);
    // The committed V2 all-board envelope bounds every supported selector.
    // Reserve that domain before template/catalog or private policy preparation.
    constexpr std::uint64_t domain_work=312947940,domain_entries=1176285,domain_payload=260024658;
    static_assert(domain_work<=t::work_cap && domain_entries<=t::entries_cap && domain_payload<=t::payload_cap);
    (void)proposal::proposal_for(t::chance::DeckDefinition::reduced(t::deck_cards),board,law);
    snap::Input input(input_path);const auto header=snap::read_header(input);
    const t::betting::Template source(t::configuration(),t::template_limits());
    p::Geometry geometry;p::census(source,source.root(),{},geometry);
    const auto f=p::forecast(geometry,board,law);
    t::require(f.feasible && f.work<=domain_work && f.entries<=domain_entries && f.payload<=domain_payload,"raw whole-request admission rejected");
    t::require(geometry.visits==1105 && geometry.depth==std::array<std::size_t,2>{6,7} && geometry.route==12 && geometry.mix_route==11,
               "raw source route census");
    t::Meter meter;
    // Each literal occurs <=12 times in all decision-child suffix scans:
    // 128*1105 +64*12*1105 =990080. A further16384 bounds selector/ledger
    // metadata. The combined source scanner and existing Forecast remain
    // cumulatively guarded by the unchanged3M geometry family.
    meter.charge(t::Work::geometry,1020000);
    const auto plan=t::Forecast(source,meter,t::Traversal::by_seat,t::StrategyProfile::dense).make();
    const auto& dense=t::proof9.shape;t::require(plan.shape==dense,"raw catalog geometry");
    const auto catalog_work=3000000+8*dense.visits+64*dense.candidates+16*dense.rows+4*dense.slots;
    t::WorkList limits{};limits[t::work_index(t::Work::geometry)]=3000000;
    limits[t::work_index(t::Work::visit)]=8*dense.visits;limits[t::work_index(t::Work::support)]=64*dense.candidates;
    limits[t::work_index(t::Work::route)]=16*dense.rows+4*dense.slots;meter.seal(limits,catalog_work);
    t::chance::Limits chance_limits;chance_limits.max_hands_per_side=2;chance_limits.max_integer_bits=384;
    chance_limits.max_modeled_work=f.chance;chance_limits.max_storage_entries=t::chance_entries;
    chance_limits.max_integer_payload_bits=t::chance_payload;
    t::prepared::PreparedPublicChance chance(t::ranges[0],t::ranges[1],t::chance::DeckDefinition::reduced(t::deck_cards),chance_limits,64);
    t::require(chance.normalizer_integer()==29,"raw prior normalizer");
    h::Limits history_limits;history_limits.work=f.history;history_limits.nodes=t::literal_count;
    history_limits.entries=32*t::literal_count+1;history_limits.owned_bytes=t::history_bytes;history_limits.depth=15;
    h::History history(source,t::chance::DeckDefinition::reduced(t::deck_cards),history_limits);
    s::Forecast state_forecast{24420,58164,1,15,648,f.state,1};
    const s::Integer denominator=s::Integer(580)<<625;
    s::State state(history,{2,2},denominator,state_forecast,{t::state_cap,65536,t::entries_cap,t::payload_cap},{388,410,false});
    (void)t::Walk<false>(source,plan,meter,history,chance,state,2).run(history.root());
    // The catalog's single root charge is part of its original bound. Only
    // the two additional raw-walk roots use V2's extra history reservation.
    state.begin_frozen_policy_import(static_cast<std::size_t>(f.reads));
    snap::import_rows(input,header,history,source,state);
    raw::Walk walk(source,history,state,chance,geometry,f,board,law);
    const auto& result=walk.run();
    t::require(walk.complete() && chance.receipt().completed_contractions==2*(geometry.folds+geometry.showdowns)+8 &&
        chance.receipt().rank_calls<=4 && state.receipt().completed_sweeps==0 && state.receipt().staged_rows==0 &&
        state.receipt().quantizer_work==0,"raw study scope counters");
#ifdef _WIN32
    t::require(_setmode(_fileno(stdout),_O_BINARY)!=-1,"raw binary stdout mode");
#endif
    snap::Output output;output.bytes("OPLGRW01",8);
    const std::array<std::uint64_t,31> fields{
        1,24420,58164,f.rows,f.slots,static_cast<std::uint64_t>(law==proposal::ProposalKind::weighted_river_proof9),
        board[0],board[1],board[2],board[3],board[4],t::grid,f.work,f.entries,f.payload,f.state,f.history,f.chance,
        f.reach,f.scale,f.mix,f.average,f.stage,f.walk,f.output,f.stage_payload,f.reads,704,11,12,static_cast<std::uint64_t>(f.physical)};
    for (const auto value:fields) output.word(value);
    for (std::size_t row=0;row<24420;++row) {
        const auto record=state.row_at(row);const auto cursor=history.decision_cursor(record.history_ordinal);
        const auto view=state.frozen_policy(cursor,record.actor,record.holding_index);
        for (const auto value:std::array<std::uint64_t,5>{record.actor,record.holding_index,record.history_ordinal,record.offset,view.units.size()}) output.word(value);
        for (const auto value:view.units) output.word(value);
    }
    integer(output,result.denominator,11,false);
    for (const auto& root:result.roots) integer(output,root,11,true);
    for (const auto& row:result.rows) {
        for (const auto value:std::array<std::uint64_t,5>{row.actor,row.holding,row.ordinal,row.offset,row.actions}) output.word(value);
        integer(output,row.average_denominator,6,false);integer(output,row.average_mass,6,false);
        for (std::size_t a=0;a<row.actions;++a) {integer(output,row.regret[a],11,true);integer(output,row.average[a],6,false);}
    }
    const auto state_receipt=state.receipt();const auto policy_receipt=state.frozen_policy_receipt();
    const auto actual=source.receipt().work+meter.total()+state_receipt.state_work+history.receipt().work+
        chance.receipt().modeled_work+walk.ledger().total()+16*input.used()+16*f.output;
    t::require(actual<=f.work && state_receipt.state_work<=f.state && history.receipt().work<=f.history &&
        policy_receipt.imported_rows==24420 && policy_receipt.read_calls==f.reads && policy_receipt.ready &&
        output.written()+26*8==f.output,"raw final resource or output census");
    const std::array<std::uint64_t,26> footer{
        1,24420,58164,result.rows.size(),result.slots,actual,source.receipt().work,meter.total(),state_receipt.state_work,
        history.receipt().work,chance.receipt().modeled_work,walk.ledger().total(),input.used(),f.output,result.peak_bits,
        chance.receipt().rank_calls,chance.receipt().completed_contractions,0,0,0,policy_receipt.imported_rows,policy_receipt.read_calls,
        result.visits,result.actions,result.reveals,2};
    for (const auto value:footer) output.word(value);
    t::require(output.written()==f.output,"raw final wire byte count");return 0;
}
}
int main(int argc,char** argv) {
    try {
        t::require(argc==8,"raw study requires snapshot path, proposal and five original card IDs");
        const auto path=bounded_argument(argv[1],1024),name=bounded_argument(argv[2],14);
        t::require(name=="uniform" || name=="river_weighted","unsupported raw proposal");
        std::array<std::uint8_t,5> board{};
        for (std::size_t i=0;i<5;++i) {
            const auto text=bounded_argument(argv[3+i],2);unsigned card=0;
            const auto parsed=std::from_chars(text.data(),text.data()+text.size(),card);
            t::require(parsed.ec==std::errc{} && parsed.ptr==text.data()+text.size() && card<52,"invalid raw original card ID");
            board[i]=static_cast<std::uint8_t>(card);
        }
        return run(std::filesystem::path(path),name=="uniform"?proposal::ProposalKind::uniform_public:proposal::ProposalKind::weighted_river_proof9,board);
    } catch (const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}
