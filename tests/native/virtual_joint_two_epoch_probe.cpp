// Two exact true-joint observations under frozen sparse policy epochs.
// Both genuine target passes finish before staging and private publication.
#include "../../native/virtual_joint_two_epoch_forecast.hpp"
#include "../../native/virtual_joint_sample_raw.hpp"
#include <charconv>
#include <cstring>
#include <iostream>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

namespace whole=openpoker::virtual_joint_two_epoch;
namespace t=whole::t;
namespace p=whole::p;
namespace e=whole::e;
namespace c=whole::c;
namespace h=openpoker::virtual_dyadic_history;
namespace raw=openpoker::virtual_frozen_grid_raw;
namespace joint=openpoker::virtual_joint_sample_raw;


namespace {
class Buffer final {
    std::vector<unsigned char> data_;
    std::size_t limit_;
public:
    explicit Buffer(std::size_t limit):limit_(limit) {data_.reserve(limit);}
    void bytes(const char* input,std::size_t count) {
        t::require(count<=limit_-data_.size(),"sparse epoch private output boundary");
        const auto* first=reinterpret_cast<const unsigned char*>(input);
        data_.insert(data_.end(),first,first+count);
    }
    void word(std::uint64_t value) {
        t::require(8<=limit_-data_.size(),"sparse epoch private word boundary");
        for (unsigned i=0;i<8;++i) data_.push_back(static_cast<unsigned char>(value>>(8*i)));
    }
    template<std::size_t N> void words(const std::array<std::uint64_t,N>& values) {
        for (const auto value:values) word(value);
    }
    [[nodiscard]] std::uint64_t written() const noexcept {return data_.size();}
    void publish() const {
#ifdef _WIN32
        t::require(_setmode(_fileno(stdout),_O_BINARY)!=-1,"sparse epoch binary stdout mode");
#endif
        std::cout.write(reinterpret_cast<const char*>(data_.data()),static_cast<std::streamsize>(data_.size()));
        t::require(bool(std::cout),"sparse epoch final output write");
    }
};
void integer(Buffer& output,const t::Integer& value,std::size_t words,bool signed_value) {
    const auto bits=raw::magnitude_bits(value);
    t::require((signed_value || value>=0) && bits<=(signed_value?words*64-1:words*64),
               "sparse epoch wire integer width");
    const auto& backend=value.backend();const bool negative=value<0;
    constexpr auto limb_bits=std::numeric_limits<boost::multiprecision::limb_type>::digits;
    static_assert(limb_bits==32 || limb_bits==64);
    constexpr auto parts=64/limb_bits;std::uint64_t carry=negative?1:0;
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
std::string_view argument(const char* text,std::size_t bound) {
    std::size_t n=0;while (n<=bound && text[n]) ++n;
    t::require(n<=bound,"sparse epoch argument byte boundary");return {text,n};
}
struct Observation {
    t::Values roots{};
    std::uint64_t rows=0,slots=0,reads=0,visits=0,actions=0,reveals=0,terminals=0,ledger=0;
    std::size_t peak_bits=0;
};
void check_components(const whole::Forecast& f,const t::betting::Template& source,
                      const h::History& history,const t::prepared::PreparedPublicChance& chance,
                      const c::Catalog& catalog,const e::Store& store,std::uint64_t parent) {
    const auto& sr=source.receipt();const auto& hr=history.receipt();
    const auto& pr=chance.receipt();const auto& cr=catalog.receipt();const auto& er=store.receipt();
    t::require(!store.failed() && !catalog.failed() && sr.work<=t::template_cap &&
        sr.entries+sr.peak_scratch_entries<=131072 &&
        hr.work<=f.history && hr.entries<=32*1105+1 && hr.owned_bytes<=t::history_bytes &&
        pr.modeled_work<=f.chance && pr.peak_live_entries<=t::chance_entries &&
        pr.peak_integer_payload_bits<=t::chance_payload && pr.peak_integer_bits<=384 &&
        pr.completed_contractions==0 && pr.joint_ticket_queries<=2 &&
        cr.work<=f.catalog.max_work && cr.metadata_entries<=f.catalog.max_metadata_entries &&
        cr.metadata_payload_bits<=f.catalog.max_metadata_payload_bits &&
        cr.public_blocks<=868 && cr.information_rows_seen<=868 && cr.action_slots_seen<=2078 &&
        cr.menus<=434 && cr.lookups<=6510 &&
        er.work<=f.epoch_cost.own_work && er.quantizer_work<=f.epoch_cost.quantizer_work &&
        er.work+er.quantizer_work<=f.epoch_cost.component_work &&
        er.peak_payload_bits<=f.epoch_cost.payload_bits && parent<=f.parent,
        "sparse epoch actual component exceeds whole admission");
}
void snapshot(Buffer& output,std::size_t epoch,std::uint64_t ticket,std::uint64_t rank,
              const std::array<std::size_t,2>& holdings,const whole::Board& board,const Observation& observation,
              e::Store& store,c::Catalog& catalog,const h::History& history,
              const t::prepared::PreparedPublicChance& chance) {
    const auto begin=output.written();const auto before=store.receipt();
    const auto record_bytes=600+40*before.current_rows+144*before.current_slots;
    output.bytes("OPLJEB01",8);
    output.words(std::array<std::uint64_t,20>{1,epoch,ticket,rank,holdings[0],holdings[1],
        board[0],board[1],board[2],board[3],board[4],
        before.current_rows,before.current_slots,observation.rows,observation.slots,observation.reads,
        before.quantized_rows,before.staged_rows,before.reads,record_bytes});
    for (const auto& root:observation.roots) integer(output,root,11,true);
    std::uint64_t rows=0,slots=0;
    store.visit_committed([&](e::RowId id,std::span<const t::Integer> regrets,
                             std::span<const t::Integer> averages,std::span<const std::uint64_t> units) {
        const auto view=catalog.view(id);
        t::require(view.actor<2 && view.holding_index<2 && !units.empty() && units.size()<=4 &&
            units.size()==view.actions.size() && regrets.size()==units.size() && averages.size()==units.size(),
            "sparse epoch committed export shape");
        t::require(rows<before.current_rows && units.size()<=before.current_slots-slots,
            "sparse epoch committed export census exceeded");
        ++rows;slots+=units.size();
        output.words(std::array<std::uint64_t,5>{view.actor,view.holding_index,view.public_ordinal,
            view.source_menu_ref,units.size()});
        for (std::size_t a=0;a<units.size();++a) {
            integer(output,regrets[a],11,true);integer(output,averages[a],6,false);output.word(units[a]);
        }
    });
    const auto& er=store.receipt();const auto& cr=catalog.receipt();const auto& pr=chance.receipt();
    t::require(rows==before.current_rows && slots==before.current_slots &&
        er.export_calls==epoch && er.commits==epoch,"sparse epoch export incomplete");
    output.words(std::array<std::uint64_t,32>{1,epoch,er.work,er.quantizer_work,cr.work,history.receipt().work,
        pr.modeled_work,observation.ledger,er.current_rows,er.current_slots,er.staged_rows,er.staged_slots,
        er.reads,er.quantized_rows,er.peak_payload_bits,cr.public_blocks,cr.information_rows_seen,
        cr.action_slots_seen,cr.menus,cr.lookups,pr.rank_calls,pr.completed_contractions,
        observation.visits,observation.actions,observation.reveals,observation.terminals,
        observation.peak_bits,er.export_calls,er.export_rows,er.export_slots,1,pr.joint_ticket_queries});
    t::require(output.written()-begin==record_bytes,"sparse epoch snapshot byte census");
}
int run(const std::array<std::array<std::uint64_t,2>,2>& selectors) {
    // Strong fixed-domain admission precedes Template and private preparation.
    // This evaluates only scalar resource equations, without a policy image.
    const auto domain=whole::domain_forecast();
    const auto deck=t::chance::DeckDefinition::reduced(t::deck_cards);
    for(const auto& selector:selectors) t::require(selector[0]<29 && selector[1]<20,"joint selector domain");
    const t::betting::Template source(t::configuration(),t::template_limits());
    p::Geometry geometry;p::census(source,source.root(),{},geometry);
    const auto f=whole::forecast(source,geometry);
    t::require(f.work<=domain.work && f.entries<=domain.entries && f.payload<=domain.payload &&
        source.receipt().nodes==388 && source.receipt().edges==410 && !source.receipt().history_suffix_only,
        "sparse epoch source or pair admission changed");
    t::chance::Limits chance_limits;chance_limits.max_hands_per_side=2;chance_limits.max_integer_bits=384;
    chance_limits.max_modeled_work=f.chance;chance_limits.max_storage_entries=t::chance_entries;
    chance_limits.max_integer_payload_bits=t::chance_payload;
    t::prepared::PreparedPublicChance chance(t::ranges[0],t::ranges[1],deck,chance_limits,64);
    t::require(chance.normalizer_integer()==29 && chance.receipt().modeled_work<=t::chance_setup_bound,
        "sparse epoch physical prior normalizer or setup bound");
    h::Limits history_limits;history_limits.work=f.history;history_limits.nodes=1105;
    history_limits.entries=32*1105+1;history_limits.owned_bytes=t::history_bytes;history_limits.depth=15;
    h::History history(source,deck,history_limits);
    c::Catalog catalog(history,{2,2},f.catalog);
    e::Store store(catalog,history,{2,2},f.epoch,e::ArithmeticContract::true_joint_proof9);
    Buffer output(static_cast<std::size_t>(f.output));
    output.bytes("OPLJEP01",8);
    output.words(std::array<std::uint64_t,24>{1,2,24420,58164,t::grid,f.work,f.entries,f.payload,f.output,
        f.catalog.max_work,f.history,f.chance,f.epoch_cost.component_work,f.parent,f.catalog.max_lookups,
        1105,388,410,12,11,704,384,0,1});
    integer(output,store.regret_denominator_value(),11,false);integer(output,store.average_denominator_value(),6,false);
    t::require(output.written()==336,"sparse epoch global header size");
    std::uint64_t parent=f.setup+4096,staged_rows=0,staged_slots=0,raw_visits=0,raw_actions=0,raw_reveals=0;
    for (std::size_t i=0;i<2;++i) {
        Observation observation;whole::Board board{};std::array<std::size_t,2> holdings{};
        {
            auto lease=store.begin_epoch(e::ProposalLaw::true_joint);
            chance.with_joint_ticket(selectors[i][0],selectors[i][1],[&](const auto& sample) {
                board=sample.board();holdings=sample.holding_indices();
                joint::Walk walk(source,history,lease,sample,geometry,f.raw);
                const auto& result=walk.run();
                t::require(walk.complete() && result.rows.size()==f.raw.rows && result.slots==f.raw.slots &&
                    result.denominator==store.regret_denominator_value(),"sparse epoch raw walk census or denominator");
                observation.roots=result.roots;observation.rows=result.rows.size();observation.slots=result.slots;
                observation.reads=result.reads;observation.visits=result.visits;observation.actions=result.actions;
                observation.reveals=result.reveals;observation.terminals=result.terminals;
                observation.peak_bits=result.peak_bits;observation.ledger=walk.ledger().total();
                t::require(observation.ledger<=whole::raw_work(f.raw),"sparse epoch raw parent ledger");
                t::require(observation.ledger<=f.parent-parent,"sparse epoch raw cumulative parent reservation");
                parent+=observation.ledger;
                lease.seal_raw_walk(result.rows.size(),static_cast<std::size_t>(result.slots),result.reads);
                for (const auto& row:result.rows) {
                    t::require(512<=f.parent-parent,"sparse epoch row join parent reservation");parent+=512;
                    const auto cursor=history.decision_cursor(row.ordinal);const auto info=history.decision_key(cursor);
                    t::require(info.ordinal==row.ordinal && info.actor==row.actor && row.actor<2 && row.holding<2 &&
                        info.actions==row.actions && row.actions>=2 && row.actions<=4 &&
                        row.regret.size()==row.actions && row.average.size()==row.actions,
                        "sparse epoch raw row identity mismatch");
                    std::array<std::string_view,4> actions{};
                    history.decision_actions(cursor,std::span(actions).first(info.actions));
                    const auto id=catalog.resolve(history,cursor,static_cast<std::size_t>(row.actor),
                        static_cast<std::size_t>(row.holding),2,info.source,std::span(actions).first(info.actions));
                    lease.stage(id,row.regret,row.average,row.average_denominator,result.denominator);
                }
            }); // Scalar walk, staged image and borrowed sample expire before commit.
        } // Completed lease releases all immutable borrowed policy views.
        store.commit();
        staged_rows+=observation.rows;staged_slots+=observation.slots;
        raw_visits+=observation.visits;raw_actions+=observation.actions;raw_reveals+=observation.reveals;
        const auto& er=store.receipt();
        t::require(er.commits==i+1 && er.staged_rows==staged_rows && er.staged_slots==staged_slots &&
            er.reads==2*staged_rows && er.quantized_rows<=staged_rows && er.pending_rows==0 &&
            er.current_rows<=staged_rows && er.current_slots<=staged_slots &&
            // Catalog retains all supported observations. Store omits rows
            // whose cumulative numeric regret and average are both all zero.
            er.current_rows<=catalog.receipt().information_rows_seen &&
            er.current_slots<=catalog.receipt().action_slots_seen &&
            chance.receipt().completed_contractions==0 && chance.receipt().rank_calls==(i+1)*2 &&
            chance.receipt().joint_ticket_queries==i+1,
            "sparse epoch cumulative transition counters");
        snapshot(output,i+1,selectors[i][0],selectors[i][1],holdings,board,observation,store,catalog,history,chance);
        check_components(f,source,history,chance,catalog,store,parent);
    }
    const auto& er=store.receipt();const auto& cr=catalog.receipt();const auto& pr=chance.receipt();
    const auto final_bytes=output.written()+256;
    t::require(final_bytes<=f.output && er.commits==2 && store.committed_epochs()==2 && er.export_calls==2 &&
        er.export_rows<=1302 && er.export_slots<=3117 && er.reads==4*f.raw.rows &&
        staged_rows==2*f.raw.rows && staged_slots==2*f.raw.slots &&
        raw_visits==4*geometry.visits && raw_actions==4*geometry.actions && raw_reveals==4*geometry.reveals &&
        pr.completed_contractions==0 && pr.rank_calls==4 && pr.joint_ticket_queries==2,"sparse epoch final exact counters");
    const auto actual=source.receipt().work+parent+cr.work+history.receipt().work+pr.modeled_work+
        er.work+er.quantizer_work+16*final_bytes;
    t::require(actual<=f.work,"sparse epoch final actual work exceeds reservation");
    check_components(f,source,history,chance,catalog,store,parent);
    // Global footer: version,epochs,total,source,parent,Store,Q,Catalog,
    // History,Chance,bytes,stageR/S,reads,quantR,currentR/S,exports,exportR/S,
    // blocks,seenR/S,menus,lookups,ranks,contractions,raw visits/actions/reveals,
    // complete,reserved. All counters are cumulative for this single owner set.
    output.words(std::array<std::uint64_t,32>{1,2,actual,source.receipt().work,parent,er.work,er.quantizer_work,
        cr.work,history.receipt().work,pr.modeled_work,final_bytes,er.staged_rows,er.staged_slots,er.reads,
        er.quantized_rows,er.current_rows,er.current_slots,er.export_calls,er.export_rows,er.export_slots,
        cr.public_blocks,cr.information_rows_seen,cr.action_slots_seen,cr.menus,cr.lookups,pr.rank_calls,
        pr.completed_contractions,raw_visits,raw_actions,raw_reveals,1,pr.joint_ticket_queries});
    t::require(output.written()==final_bytes,"sparse epoch final wire byte count");
    output.publish();return 0;
}
} // namespace

int main(int argc,char** argv) {
    try {
        t::require(argc==5,"joint epoch requires two private tickets and board ranks");
        std::array<std::array<std::uint64_t,2>,2> selectors{};
        for(std::size_t epoch=0;epoch<2;++epoch) for(std::size_t field=0;field<2;++field) {
            const auto text=argument(argv[1+2*epoch+field],2);unsigned value=0;
            const auto parsed=std::from_chars(text.data(),text.data()+text.size(),value);
            t::require(!text.empty() && parsed.ec==std::errc{} && parsed.ptr==text.data()+text.size() &&
                value<(field?20:29),"joint selector outside exact fixed ticket domain");
            selectors[epoch][field]=value;
        }
        return run(selectors);
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}
