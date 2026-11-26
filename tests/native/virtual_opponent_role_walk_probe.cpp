// Full52 fixed-template T2 research updates from supplied deterministic tapes.
#include "../../native/virtual_opponent_role_walk.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
namespace w=openpoker::virtual_opponent_role_walk;
namespace f=w::f;
namespace t=w::t;
namespace r=w::r;
namespace p=t::prepared;
using Integer=t::Integer;
namespace {
class Input final {
    std::vector<unsigned char> raw_;
    std::size_t at_=0;
public:
    explicit Input(const std::filesystem::path& path) {
        t::require(std::filesystem::is_regular_file(path) && !std::filesystem::is_symlink(path) &&
            std::filesystem::file_size(path)<=f::input_cap,"role input bounded regular file");
        std::ifstream stream(path,std::ios::binary);t::require(bool(stream),"role input unreadable");char c;
        while(stream.get(c)){t::require(raw_.size()<f::input_cap,"role input file grew beyond cap");raw_.push_back(static_cast<unsigned char>(c));}
    }
    void magic() {
        t::require(raw_.size()>=8,"role input truncated magic");constexpr char expected[]="OPLRIN01";
        for(std::size_t i=0;i<8;++i)t::require(raw_[at_++]==static_cast<unsigned char>(expected[i]),"role input version magic");
    }
    std::uint64_t word() {
        t::require(raw_.size()-at_>=8,"role input truncated word");std::uint64_t n=0;
        for(unsigned i=0;i<8;++i)n|=static_cast<std::uint64_t>(raw_[at_++])<<(8*i);
        return n;
    }
    void end() const{t::require(at_==raw_.size(),"role input trailing bytes");}
};
class Output final {
    std::vector<unsigned char> data_;
public:
    Output(){data_.reserve(f::output_upper);}
    void word(std::uint64_t value) {
        t::require(data_.size()+8<=f::output_upper,"role private output bound");
        for(unsigned i=0;i<8;++i)data_.push_back(static_cast<unsigned char>(value>>(8*i)));
    }
    void magic(const char* text){for(unsigned i=0;i<8;++i){t::require(data_.size()<f::output_upper,"role output magic bound");data_.push_back(static_cast<unsigned char>(text[i]));}}
    void integer(const Integer& value,std::size_t words,bool signed_value) {
        t::require((signed_value || value>=0) && r::e::magnitude_bits(value)<=64*words-static_cast<unsigned>(signed_value),"role output integer extent");
        const bool negative=value<0;const Integer magnitude=negative?-value:value;std::array<std::uint64_t,11> raw{};
        t::require(words<=raw.size(),"role output integer word domain");boost::multiprecision::export_bits(magnitude,raw.begin(),64,false);
        if(negative){std::uint64_t carry=1;for(std::size_t i=0;i<words;++i){raw[i]=~raw[i];const auto before=raw[i];raw[i]+=carry;carry=static_cast<std::uint64_t>(carry && raw[i]<before);}}
        for(std::size_t i=0;i<words;++i)word(raw[i]);
    }
    [[nodiscard]] std::size_t size() const{return data_.size();}
    void publish() const {
        std::cout.write(reinterpret_cast<const char*>(data_.data()),static_cast<std::streamsize>(data_.size()));
        t::require(bool(std::cout),"role final output write");
    }
};
template<class Values> void words(Output& out,const Values& values){for(const auto n:values)out.word(n);}
void raw_world(Output& out,unsigned epoch,const r::Certificate& sample,const w::Walk& walk) {
    out.magic("OPLRWO01");out.word(epoch);out.word(sample.private_ticket());out.word(sample.board_rank());
    words(out,sample.holding_indices());
    for(const auto hand:sample.holdings()){out.word(hand.first);out.word(hand.second);}
    words(out,sample.board());out.word(static_cast<std::uint64_t>(sample.showdown_sign()+1));
    out.word(walk.rows().size());out.word(walk.slots());out.word(walk.choices().size());
    for(const auto& root:walk.roots())out.integer(root,7,true);
    const auto& n=walk.counts();
    words(out,n.visits);words(out,n.actions);words(out,n.reveals);words(out,n.terminals);words(out,n.decisions);words(out,n.own_rows);words(out,n.tickets);
    words(out,walk.actual_work());out.word(walk.peak_bits());
    for(const auto& row:walk.rows()) {
        words(out,std::array<std::uint64_t,6>{row.actor,row.holding,row.ordinal,row.source,row.actions,row.roles});
        for(std::size_t a=0;a<row.actions;++a){out.word(row.units[a]);words(out,row.regrets[a]);out.word(row.averages[a]);}
    }
    for(const auto& q:walk.choices())words(out,std::array<std::uint64_t,8>{q.target,q.actor,q.holding,q.ordinal,q.source,q.action,q.ticket,q.units});
    out.magic("OPLREN01");std::uint64_t work=0;for(const auto cost:walk.actual_work())work+=cost;
    out.word(work);out.word(walk.rows().size());out.word(walk.slots());
}
void snapshot(Output& out,unsigned epoch,r::Store& owner,r::c::Catalog& catalog,r::h::History& history,
              p::PreparedPublicChance& chance) {
    out.magic("OPLRSN01");out.word(epoch);out.word(owner.storage_receipt().current_rows);out.word(owner.storage_receipt().current_slots);
    std::size_t rows=0,slots=0;
    owner.visit_committed([&](auto id,std::span<const Integer> rr,std::span<const Integer> aa,std::span<const std::uint64_t> units) {
        const auto info=catalog.view(id);++rows;slots+=units.size();
        words(out,std::array<std::uint64_t,5>{info.actor,info.holding_index,info.public_ordinal,info.source_menu_ref,units.size()});
        for(std::size_t a=0;a<units.size();++a){out.integer(rr[a],11,true);out.integer(aa[a],6,false);out.word(units[a]);}
    });
    t::require(rows==owner.storage_receipt().current_rows && slots==owner.storage_receipt().current_slots,"role complete committed snapshot");
    out.magic("OPLRRC01");const auto& x=owner.receipt();const auto& s=owner.storage_receipt();const auto& c=catalog.receipt();
    words(out,std::array<std::uint64_t,9>{x.own_work,x.encounters,x.frozen_reads,x.cache_hits,x.staged_rows,x.staged_slots,x.commits,x.peak_cache_rows,x.peak_cache_slots});
    words(out,std::array<std::uint64_t,15>{s.work,s.reads,s.staged_rows,s.staged_slots,s.commits,s.quantizer_work,s.quantized_rows,s.export_calls,s.export_rows,s.export_slots,
        s.current_rows,s.pending_rows,s.current_slots,s.pending_slots,s.peak_payload_bits});
    words(out,std::array<std::uint64_t,8>{c.work,c.lookups,c.public_blocks,c.information_rows_seen,c.action_slots_seen,c.menus,c.metadata_entries,c.metadata_payload_bits});
    out.word(history.receipt().work);const auto& q=chance.receipt();words(out,std::array<std::uint64_t,3>{q.modeled_work,q.rank_calls,q.joint_ticket_queries});
}
}
int main(int argc,char** argv) {
    try {
        t::require(argc==2,"one explicit bounded role ticket file required");const auto model=f::domain();
        Input input{std::filesystem::path(argv[1])};input.magic();const auto version=input.word(),profile=input.word(),epochs=input.word();
        t::require(version==1 && profile<2 && epochs==2,"unsupported role profile/version/lifetime");
        std::array<std::array<std::uint64_t,2>,2> selectors{};
        const std::array<std::uint64_t,2> normalizers{1624350,25908876};
        for(auto& pair:selectors){pair={input.word(),input.word()};t::require(pair[0]<normalizers[profile] && pair[1]<34246080,"role chance selector domain");}
        std::array<std::array<std::uint64_t,2>,2> sizes{};
        for(auto& row:sizes){row={input.word(),input.word()};t::require(row[0]<=204 && row[1]<=204 && row[0]+row[1]<=204,"role per-world complete ticket extent");}
        std::array<std::array<std::vector<std::uint64_t>,2>,2> tapes;
        for(std::size_t i=0;i<2;++i)for(std::size_t target=0;target<2;++target) {
            tapes[i][target].reserve(static_cast<std::size_t>(sizes[i][target]));
            for(std::uint64_t n=0;n<sizes[i][target];++n){const auto value=input.word();t::require(value<t::grid,"role action ticket exceeds Q52");tapes[i][target].push_back(value);}
        }
        input.end(); // Every input domain is checked before any range/tree preparation.
        t::betting::Template source(t::configuration(),t::template_limits());f::g::Geometry geometry;
        f::g::census(source,source.root(),{},geometry);f::validate_source(source,geometry);
        std::array<std::vector<t::chance::WeightedHand>,2> ranges;
        for(auto& side:ranges) {
            side.reserve(1326);
            for(unsigned first=0;first<52;++first)for(unsigned second=first+1;second<52;++second) {
                const double weight=profile?static_cast<double>(side.size()%7+1):1.;
                side.push_back({{static_cast<std::uint8_t>(first),static_cast<std::uint8_t>(second)},std::bit_cast<std::uint64_t>(weight)});
            }
        }
        const auto deck=p::DeckDefinition::full52();t::chance::Limits chance_limits;
        chance_limits.max_hands_per_side=1326;chance_limits.max_integer_bits=181;chance_limits.max_modeled_work=model.chance;
        chance_limits.max_storage_entries=t::chance_entries;chance_limits.max_integer_payload_bits=t::chance_payload;
        p::PreparedPublicChance chance(ranges[0],ranges[1],p::Purpose::joint_tickets_v1,deck,chance_limits);
        t::require(chance.normalizer_integer()==normalizers[profile],"role independent named normalizer mismatch");
        r::h::Limits history_limits;history_limits.work=model.history;history_limits.nodes=1105;history_limits.entries=32*1105+1;
        history_limits.owned_bytes=t::history_bytes;history_limits.depth=15;
        r::h::History history(source,deck,history_limits);r::c::Catalog catalog(history,{1326,1326},model.catalog);
        r::Store owner(catalog,history,chance,{1326,1326},model.role_limits);Output out;
        out.magic("OPLROW01");words(out,std::array<std::uint64_t,28>{1,profile,52,1326,1326,2,t::grid,365,52,625,364,704,181,
            model.work,model.entries,model.payload,model.output,f::input_cap,model.catalog.max_work,model.history,model.chance,model.component,model.parent,
            model.catalog.max_lookups,model.catalog.max_metadata_entries,model.role.own_work,model.role.storage.component_work,model.role.work});
        words(out,std::array<std::uint64_t,6>{model.raw.scale,model.raw.mix,model.raw.regret,model.raw.average,model.raw.stage,model.raw.walk});
        std::uint64_t parent=1044096;
        for(unsigned i=0;i<2;++i) {
            owner.apply_world(selectors[i][0],selectors[i][1],[&](r::Store::Epoch& epoch,const r::Certificate& sample) {
                w::Walk walk(source,history,epoch,sample,{tapes[i][0],tapes[i][1]},model.raw);walk.run();raw_world(out,i+1,sample,walk);
                for(const auto value:walk.actual_work())parent+=value;
            });
            snapshot(out,i+1,owner,catalog,history,chance);
        }
        t::require(!owner.failed() && parent<=model.parent && history.receipt().work<=model.history &&
            catalog.receipt().work<=model.catalog.max_work && chance.receipt().modeled_work==model.chance &&
            owner.storage_receipt().work+owner.storage_receipt().quantizer_work+owner.receipt().own_work<=model.component,
            "role complete native actual owner ledgers");
        out.magic("OPLRFN01");out.word(parent);out.word(out.size()+8); // length includes this final size word
#ifdef _WIN32
        t::require(_setmode(_fileno(stdout),_O_BINARY)!=-1,"role binary stdout mode");
#endif
        out.publish();return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
