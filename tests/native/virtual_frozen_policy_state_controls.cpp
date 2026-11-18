// Read-only Q52 import boundary. No training or raw-update producer is entered.
#include "../../native/virtual_dyadic_training.hpp"
#include <array>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

namespace t=openpoker::virtual_dyadic_training;
namespace s=openpoker::virtual_dyadic_state;
namespace h=openpoker::virtual_dyadic_history;
namespace b=openpoker::virtual_betting_template;
namespace c=openpoker::full_deck_public_chance;
using s::ErrorCode;
constexpr auto Q=openpoker::dyadic_policy::grid_units;

namespace {
void require(bool value,const char* message) {if (!value) throw std::runtime_error(message);}
struct Small {
    b::Template source{t::configuration()};
    h::History history{source,c::DeckDefinition::reduced(t::deck_cards)};
    std::array<h::History::Cursor,4> cursors{history.root(),history.root(),
        history.append_action(history.root(),1),history.append_action(history.root(),2)};
    std::array<std::size_t,4> holdings{0,1,0,0};
    std::size_t slots=0;
    s::Forecast forecast{};
    std::unique_ptr<s::State> state;
    explicit Small(std::uint64_t own_work=10000000) {
        for (const auto cursor:cursors) slots+=history.decision_key(cursor).actions;
        forecast={4,slots,1,15,648,own_work,1};
        state=std::make_unique<s::State>(history,std::array<std::size_t,2>{2,2},1,forecast);
        for (std::size_t row=0;row<cursors.size();++row) {
            const auto info=history.decision_key(cursors[row]);
            std::array<std::string_view,20> tokens{};
            history.decision_actions(cursors[row],std::span(tokens).first(info.actions));
            require(state->register_row(cursors[row],info.actor,holdings[row],std::span(tokens).first(info.actions))==row,
                "small catalog row order");
        }
    }
    std::array<std::uint64_t,20> units(std::size_t row) const {
        std::array<std::uint64_t,20> result{};
        const auto count=state->row_at(row).actions.size();
        if (row==0) {std::fill_n(result.begin(),count,1);result[0]=Q-count+1;}
        else if (row==1) result[1]=Q;
        else for (std::size_t a=0;a<count;++a) result[a]=Q/count+static_cast<std::uint64_t>(a<Q%count);
        return result;
    }
    void import(std::size_t row) {
        const auto record=state->row_at(row);auto values=units(row);
        state->import_frozen_policy_row(row,cursors[row],record.actor,holdings[row],record.actions,
            std::span(values).first(record.actions.size()));
        values.fill(0); // Caller mutation must not alias the sealed image.
    }
    void seal(std::size_t reads=4) {
        state->begin_frozen_policy_import(reads);
        for (std::size_t row=0;row<4;++row) import(row);
        state->seal_frozen_policy();
    }
};
template<class Operation> void rejected(const char* label,Operation operation,bool poison=true) {
    Small fixture;
    try {operation(fixture);}
    catch (const s::Error&) {
        require(!poison || fixture.state->failed(),"failed input did not poison its owner");
        std::cout<<"GUARD "<<label<<" PASS\n";return;
    }
    throw std::runtime_error(std::string("accepted invalid frozen policy: ")+label);
}
int controls() {
    Small good;
    const auto before=good.state->receipt().state_work;
    const auto history_before=good.history.receipt().work;
    const auto bound=s::State::frozen_policy_forecast(good.forecast,4);
    good.seal();
    require(good.state->regrets().empty() && good.state->averages().empty(),"read-only state exposed numeric arrays");
    for (std::size_t row=0;row<4;++row) {
        const auto record=good.state->row_at(row);
        const auto view=good.state->frozen_policy(good.cursors[row],record.actor,good.holdings[row]);
        const auto expected=good.units(row);
        require(view.row.offset==record.offset && std::equal(view.units.begin(),view.units.end(),expected.begin()),
            "copied policy or zero action changed");
        std::cout<<"ROW "<<row<<' '<<view.row.actor<<' '<<view.row.holding_index<<' '
            <<view.row.history_ordinal<<' '<<view.row.offset<<' '<<view.units.size();
        for (const auto unit:view.units) std::cout<<' '<<unit;
        std::cout<<'\n';
    }
    require(good.state->receipt().quantizer_work==0 && good.state->receipt().completed_sweeps==0 &&
        good.state->receipt().staged_rows==0,"read-only import entered training");
    require(good.state->receipt().state_work-before<=bound.import_work+bound.read_work &&
        good.history.receipt().work-history_before<=bound.history_work,"component reservation underrun");
    std::cout<<"READONLY 4 "<<good.slots<<' '<<bound.import_work<<' '<<bound.read_work<<' '
        <<bound.history_work<<' '<<good.state->receipt().state_work-before<<' '
        <<good.history.receipt().work-history_before<<"\n";
    rejected("unsealed_read",[](Small& f){f.state->begin_frozen_policy_import(4);(void)f.state->frozen_policy(f.cursors[0],0,0);});
    rejected("incomplete",[](Small& f){f.state->begin_frozen_policy_import(4);f.import(0);f.state->seal_frozen_policy();});
    rejected("duplicate",[](Small& f){f.state->begin_frozen_policy_import(4);f.import(0);f.import(0);});
    rejected("out_of_order",[](Small& f){f.state->begin_frozen_policy_import(4);f.import(1);});
    rejected("wrong_history",[](Small& f){f.state->begin_frozen_policy_import(4);auto r=f.state->row_at(0);auto u=f.units(0);
        f.state->import_frozen_policy_row(0,f.cursors[2],0,0,r.actions,std::span(u).first(r.actions.size()));});
    rejected("foreign_history",[](Small& f){f.state->begin_frozen_policy_import(4);auto r=f.state->row_at(0);auto u=f.units(0);
        f.state->import_frozen_policy_row(0,h::History::Cursor{},0,0,r.actions,std::span(u).first(r.actions.size()));});
    rejected("wrong_holding",[](Small& f){f.state->begin_frozen_policy_import(4);auto r=f.state->row_at(0);auto u=f.units(0);
        f.state->import_frozen_policy_row(0,f.cursors[0],0,1,r.actions,std::span(u).first(r.actions.size()));});
    rejected("wrong_menu",[](Small& f){f.state->begin_frozen_policy_import(4);auto r=f.state->row_at(0);auto u=f.units(0);
        std::array<std::string_view,20> changed{};std::copy(r.actions.begin(),r.actions.end(),changed.begin());
        std::swap(changed[0],changed[1]);f.state->import_frozen_policy_row(0,f.cursors[0],0,0,
            std::span(changed).first(r.actions.size()),std::span(u).first(r.actions.size()));});
    rejected("zero_partition",[](Small& f){f.state->begin_frozen_policy_import(4);auto r=f.state->row_at(0);
        std::array<std::uint64_t,20> u{};f.state->import_frozen_policy_row(0,f.cursors[0],0,0,r.actions,std::span(u).first(r.actions.size()));});
    rejected("overflow_partition",[](Small& f){f.state->begin_frozen_policy_import(4);auto r=f.state->row_at(0);auto u=f.units(0);u[0]=UINT64_MAX;
        f.state->import_frozen_policy_row(0,f.cursors[0],0,0,r.actions,std::span(u).first(r.actions.size()));});
    rejected("read_cap",[](Small& f){f.seal(1);(void)f.state->frozen_policy(f.cursors[0],0,0);(void)f.state->frozen_policy(f.cursors[0],0,0);});
    rejected("training",[](Small& f){f.seal();f.state->begin_sweep();});
    rejected("freeze",[](Small& f){f.seal();f.state->freeze();});
    rejected("commit",[](Small& f){f.seal();f.state->commit_sweep();});
    rejected("export",[](Small& f){f.seal();(void)f.state->export_average();});
    rejected("reimport",[](Small& f){f.seal();f.state->begin_frozen_policy_import(4);});
    rejected("zero_reads",[](Small& f){f.state->begin_frozen_policy_import(0);});
    rejected("overflow_reads",[](Small& f){f.state->begin_frozen_policy_import(SIZE_MAX);});
    const auto exact=before+bound.import_work+bound.read_work;
    Small short_work(exact-1);
    try {short_work.state->begin_frozen_policy_import(4);throw std::runtime_error("short work admitted");}
    catch (const s::Error& e) {require(e.code()==ErrorCode::work_limit && short_work.state->failed(),"short work rejection");}
    std::cout<<"GUARD lifetime_one_short PASS\n";
    const auto bad_key=[](const char* label,auto make_key) {
        Small fixture;
        try {(void)fixture.history.decision_cursor(make_key(fixture));}
        catch (const h::Error&) {
            require(fixture.history.failed(),"directory codec did not fail closed");
            std::cout<<"HISTORY_GUARD "<<label<<" PASS\n";return;
        }
        throw std::runtime_error("invalid directory key accepted");
    };
    bad_key("unused_root",[](Small&){return UINT64_C(1);});
    bad_key("foreign_path",[](Small&){return UINT64_C(1105)<<33;});
    bad_key("bad_length",[](Small&){return UINT64_C(1)<<30;});
    bad_key("terminal_path",[](Small& f){return f.history.ordinal(f.history.append_action(f.cursors[0],0));});
    const auto flop_key=[](Small& f) {
        auto cursor=f.history.append_action(f.cursors[2],0);
        const std::array<std::uint8_t,3> flop{16,17,24};
        return f.history.ordinal(f.history.append_reveal(cursor,flop));
    };
    bad_key("duplicate_card",[&](Small& f){return (flop_key(f)&~(UINT64_C(63)<<6))|(UINT64_C(16)<<6);});
    bad_key("foreign_card",[&](Small& f){return flop_key(f)&~UINT64_C(63);});
    bad_key("unsorted_flop",[&](Small& f){return (flop_key(f)&~UINT64_C(4095))|UINT64_C(17)|(UINT64_C(16)<<6);});
    bad_key("unused_flop",[&](Small& f){return flop_key(f)|(UINT64_C(1)<<18);});
    std::cout<<"END\n";
    return 0;
}
struct Header {std::uint64_t rows=0,slots=0,tokens=0,history_bytes=0,action_bytes=0,q=0;};
constexpr std::uint64_t input_cap=8*1024*1024,output_cap=2100000;
class Input {
    std::ifstream file_;
    std::uint64_t size_,used_=0;
public:
    explicit Input(const std::filesystem::path& path):size_(std::filesystem::file_size(path)) {
        require(path.native().size()<=1024 && std::filesystem::is_regular_file(path) && size_<=input_cap,"snapshot input boundary");
        file_.open(path,std::ios::binary);require(bool(file_),"snapshot input open");
    }
    void bytes(void* out,std::size_t n) {
        require(n<=size_-used_,"truncated snapshot input");
        file_.read(static_cast<char*>(out),static_cast<std::streamsize>(n));
        require(bool(file_),"snapshot input read");used_+=n;
    }
    std::uint64_t word() {std::uint64_t v;bytes(&v,8);return v;}
    std::string token() {
        std::uint8_t n;bytes(&n,1);require(n && n<=64,"snapshot token bound");
        std::string result(n,'\0');bytes(result.data(),n);return result;
    }
    std::uint64_t size() const {return size_;}
    std::uint64_t used() const {return used_;}
};
class Output {
    std::uint64_t written_=0;
public:
    void bytes(const void* data,std::size_t n) {
        require(n<=output_cap-written_,"snapshot output boundary");
        std::cout.write(static_cast<const char*>(data),static_cast<std::streamsize>(n));
        require(bool(std::cout),"snapshot output write");written_+=n;
    }
    void word(std::uint64_t value) {bytes(&value,8);}
    std::uint64_t written() const {return written_;}
};
std::uint8_t card(std::string_view text) {
    constexpr std::string_view ranks="23456789TJQKA",suits="cdhs";
    require(text.size()==2,"snapshot card token");
    const auto rank=ranks.find(text[0]),suit=suits.find(text[1]);
    require(rank<13 && suit<4,"snapshot card grammar");
    return static_cast<std::uint8_t>(4*rank+suit);
}
h::History::Cursor reconstruct(h::History& history,const b::Template& source,
                              std::span<const std::string> tokens) {
    auto cursor=history.root();auto node_id=source.root();std::array<std::uint8_t,5> board{};std::size_t visible=0;
    for (const auto& token:tokens) {
        const auto& node=source.nodes().at(node_id);
        if (node.state.phase==b::Phase::decision) {
            std::size_t edge=0;
            while (edge<node.edges.size() && node.edges[edge].action.token!=token) ++edge;
            require(edge<node.edges.size(),"snapshot history action");
            cursor=history.append_action(cursor,edge);node_id=node.edges[edge].child;
        } else {
            require(node.state.phase==b::Phase::reveal && node.edges.size()==1,"snapshot history phase");
            const auto next=node.state.next_street;
            if (next==3) {
                require(!visible && token.size()==11 && token.starts_with("flop@"),"snapshot flop token");
                for (std::size_t i=0;i<3;++i) board[i]=card(std::string_view(token).substr(5+2*i,2));
            } else {
                require(visible+1==next && (next==4 || next==5),"snapshot ordered reveal");
                const std::string_view label=next==4?"turn@":"river@";
                require(token.size()==label.size()+2 && token.starts_with(label),"snapshot reveal token");
                board[visible]=card(std::string_view(token).substr(label.size(),2));
            }
            visible=next;cursor=history.append_reveal(cursor,std::span(board).first(visible));node_id=node.edges[0].child;
        }
    }
    require(source.nodes().at(node_id).state.phase==b::Phase::decision,"snapshot row must be a decision");
    return cursor;
}
int complete_snapshot(const std::filesystem::path& path) {
    static_assert(std::endian::native==std::endian::little);
    Input input(path);std::array<char,8> magic{};input.bytes(magic.data(),magic.size());
    require(std::string_view(magic.data(),magic.size())=="OPLFGS01","snapshot input version");
    const Header header{input.word(),input.word(),input.word(),input.word(),input.word(),input.word()};
    require(header.rows==24420 && header.slots==58164 && header.tokens==249662 &&
        header.history_bytes==1500675 && header.action_bytes==294353 && header.q==Q,"snapshot fixed complete census");
    const auto expected=56+40*header.rows+header.tokens+header.history_bytes+header.slots+header.action_bytes+8*header.slots;
    require(input.size()==expected,"snapshot complete byte count");
    const auto& g=t::proof9.shape;
    s::Forecast sf{24420,58164,1,15,648,1,1};
    const auto component=s::State::frozen_policy_forecast(sf,sf.rows);
    const auto construction=1024+8*header.rows+16*header.slots+4*11;
    const auto registration=header.rows*(128+16*t::logceil(header.rows+1))+256*header.slots;
    sf.own_work=construction+registration+component.import_work+component.read_work;
    const auto history_work=4096*t::literal_count+1280+40*g.actions+72*g.reveals+48*g.visits+40*g.rows+
        8*header.rows+72*header.tokens+component.history_work+288*header.rows;
    const auto catalog_work=3'000'000+8*g.visits+64*g.candidates+16*g.rows+4*g.slots;
    const auto total_work=t::template_cap+t::chance_setup_bound+history_work+sf.own_work+sf.quantizer_work+
        catalog_work+16*input_cap+16*output_cap;
    const s::ActionCatalogCapacity menus{388,410,false};
    const auto storage=s::State::storage_forecast(sf,menus);
    const auto entries=storage.entries+131072+(32*t::literal_count+1)+t::chance_entries+t::parent_entries;
    const auto payload=storage.payload_bits+t::chance_payload+8*t::history_bytes+t::parent_payload+32*181+8*16384;
    require(total_work<=t::work_cap && sf.own_work+1<=t::state_cap && history_work<=t::history_cap &&
        entries<=t::entries_cap && payload<=t::payload_cap,"whole snapshot request admission rejected");
    const b::Template source(t::configuration(),t::template_limits());
    t::Meter meter;const auto plan=t::Forecast(source,meter,t::Traversal::by_seat,t::StrategyProfile::dense).make();
    require(plan.shape==g,"snapshot source catalog census");
    t::WorkList catalog_limits{};
    catalog_limits[t::work_index(t::Work::geometry)]=3'000'000;
    catalog_limits[t::work_index(t::Work::visit)]=8*g.visits;
    catalog_limits[t::work_index(t::Work::support)]=64*g.candidates;
    catalog_limits[t::work_index(t::Work::route)]=16*g.rows+4*g.slots;
    meter.seal(catalog_limits,catalog_work);
    const auto deck=c::DeckDefinition::reduced(t::deck_cards);
    c::Limits chance_limits;chance_limits.max_hands_per_side=2;chance_limits.max_modeled_work=t::chance_setup_bound;
    chance_limits.max_storage_entries=t::chance_entries;chance_limits.max_integer_payload_bits=t::chance_payload;
    t::prepared::PreparedPublicChance chance(t::ranges[0],t::ranges[1],deck,chance_limits,64);
    h::Limits history_limits;history_limits.work=history_work;history_limits.nodes=t::literal_count;
    history_limits.entries=32*t::literal_count+1;history_limits.owned_bytes=t::history_bytes;history_limits.depth=15;
    h::History history(source,deck,history_limits);
    const s::Integer denominator=s::Integer(580)<<625;
    s::State state(history,{2,2},denominator,sf,{t::state_cap,65536,t::entries_cap,t::payload_cap},menus);
    (void)t::Walk<false>(source,plan,meter,history,chance,state,2).run(history.root());
    state.begin_frozen_policy_import(sf.rows);
    std::uint64_t tokens=0,history_bytes=0,actions=0,action_bytes=0;
    for (std::size_t row=0;row<sf.rows;++row) {
        const auto actor=input.word(),first=input.word(),second=input.word(),n=input.word(),m=input.word();
        require(actor<2 && first<second && second<52 && n<=15 && m>=2 && m<=20 &&
            n<=header.tokens-tokens && m<=header.slots-actions,"snapshot row header");
        std::size_t holding=0;
        while (holding<2 && (t::ranges[actor][holding].hand.first!=first || t::ranges[actor][holding].hand.second!=second)) ++holding;
        require(holding<2,"snapshot original holding identity");
        std::array<std::string,15> history_tokens{};
        std::array<std::string,20> action_tokens{};std::array<std::string_view,20> action_views{};
        std::array<std::uint64_t,20> units{};
        for (std::size_t i=0;i<n;++i) {
            history_tokens[i]=input.token();require(history_tokens[i].size()<=header.history_bytes-history_bytes,"snapshot history text count");
            history_bytes+=history_tokens[i].size();
        }
        for (std::size_t i=0;i<m;++i) {
            action_tokens[i]=input.token();require(action_tokens[i].size()<=header.action_bytes-action_bytes,"snapshot action text count");
            action_bytes+=action_tokens[i].size();action_views[i]=action_tokens[i];
        }
        for (std::size_t i=0;i<m;++i) units[i]=input.word();
        const auto cursor=reconstruct(history,source,std::span(history_tokens).first(static_cast<std::size_t>(n)));
        state.import_frozen_policy_row(row,cursor,actor,holding,std::span(action_views).first(static_cast<std::size_t>(m)),
            std::span(units).first(static_cast<std::size_t>(m)));
        tokens+=n;actions+=m;
    }
    require(tokens==header.tokens && actions==header.slots && history_bytes==header.history_bytes &&
        action_bytes==header.action_bytes && input.used()==input.size(),"snapshot final input census");
    state.seal_frozen_policy();
#ifdef _WIN32
    require(_setmode(_fileno(stdout),_O_BINARY)!=-1,"snapshot binary stdout mode");
#endif
    Output output;
    output.bytes("OPLFGV01",8);
    for (const auto value:std::array<std::uint64_t,7>{header.rows,header.slots,total_work,entries,payload,history_work,sf.own_work}) output.word(value);
    for (std::size_t row=0;row<sf.rows;++row) {
        const auto record=state.row_at(row);
        const auto cursor=history.decision_cursor(record.history_ordinal);
        const auto view=state.frozen_policy(cursor,record.actor,record.holding_index);
        for (const auto value:std::array<std::uint64_t,5>{view.row.actor,view.row.holding_index,view.row.history_ordinal,
            view.row.offset,view.units.size()}) output.word(value);
        for (const auto unit:view.units) output.word(unit);
    }
    constexpr std::size_t footer_bytes=18*8;
    require(output.written()<=output_cap-footer_bytes,"snapshot footer output reservation");
    const auto final_bytes=output.written()+footer_bytes;
    const auto actual=source.receipt().work+meter.total()+chance.receipt().modeled_work+history.receipt().work+
        state.receipt().state_work+state.receipt().quantizer_work+16*input.used()+16*final_bytes;
    require(actual<=total_work && chance.receipt().rank_calls==0 && chance.receipt().completed_contractions==0 &&
        state.receipt().completed_sweeps==0 && state.receipt().staged_rows==0 && state.receipt().quantizer_work==0,
        "snapshot actual owner scope or reservation");
    const auto frozen=state.frozen_policy_receipt();
    for (const auto value:std::array<std::uint64_t,18>{header.rows,header.slots,actual,history.receipt().work,
        state.receipt().state_work,source.receipt().work,meter.total(),chance.receipt().modeled_work,input.used(),final_bytes,
        chance.receipt().rank_calls,chance.receipt().completed_contractions,state.receipt().quantizer_work,
        state.receipt().completed_sweeps,state.receipt().staged_rows,frozen.imported_rows,frozen.read_calls,frozen.ready?1u:0u}) output.word(value);
    return 0;
}
} // namespace

int main(int argc,char** argv) {
    try {
        if (argc==2) return complete_snapshot(argv[1]);
        require(argc==1,"frozen policy controls argument count");
        std::cout<<"FROZEN_POLICY_STATE_V1\n";return controls();
    }
    catch (const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}
