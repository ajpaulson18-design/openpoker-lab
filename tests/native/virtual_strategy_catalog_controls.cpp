#include "../../native/virtual_strategy_catalog.hpp"
#include "../../native/virtual_dyadic_training.hpp"
#include <algorithm>
#include <array>
#include <iostream>
#include <stdexcept>
#include <string_view>

namespace t=openpoker::virtual_dyadic_training;
namespace h=openpoker::virtual_dyadic_history;
namespace c=openpoker::virtual_strategy_catalog;
namespace b=openpoker::virtual_betting_template;
namespace chance=openpoker::full_deck_public_chance;

namespace {
void require(bool ok,const char* why) { if (!ok) throw std::runtime_error(why); }
c::Limits limits(std::size_t blocks=8,std::size_t rows=16,std::size_t slots=128,
                 std::size_t menus=8,std::size_t holdings=1326,
                 std::uint64_t lookups=32,std::uint64_t work=1000000) {
    c::Limits result{blocks,rows,slots,menus,holdings,lookups,work,0,0};
    result.max_metadata_entries=c::Catalog::metadata_word_forecast(result);
    result.max_metadata_payload_bits=result.max_metadata_entries*64;
    return result;
}

struct Fixture {
    b::Template source{t::configuration(),t::template_limits()};
    h::History history{source,chance::DeckDefinition::reduced(t::deck_cards)};
    h::History::Cursor root=history.root();
    std::size_t root_source=history.decision_key(root).source;
    std::array<std::string_view,c::maximum_actions> root_actions{};
    std::size_t root_count=history.decision_key(root).actions;
    Fixture() { history.decision_actions(root,std::span(root_actions).first(root_count)); }
};

bool first_reveal(Fixture& f,h::History::Cursor cursor,h::History::Cursor& result,
                 std::size_t& visits) {
    if (++visits>250000) return false;
    const auto source=f.history.source_node(cursor);
    const auto phase=f.source.nodes().at(source).state.phase;
    if (phase==b::Phase::reveal) { result=cursor; return true; }
    if (phase!=b::Phase::decision) return false;
    try {
        const auto info=f.history.decision_key(cursor);
        std::array<std::string_view,c::maximum_actions> actions{};
        f.history.decision_actions(cursor,std::span(actions).first(info.actions));
        for (std::size_t i=0;i<info.actions;++i)
            if (first_reveal(f,f.history.append_action(cursor,i),result,visits)) return true;
        return false;
    } catch (const h::Error&) { return false; }
}

void row(const char* label,c::Catalog& catalog,c::RowId id) {
    // This control prints only identity and menu text, never a strategy value.
    const auto view=catalog.view(id);
    std::cout<<"ROW "<<label<<' '<<view.public_ordinal<<' '<<view.actor<<' '
             <<view.holding_index<<' '<<view.source_menu_ref<<' '<<view.actions.size();
    for (const auto& action:view.actions) std::cout<<' '<<action;
    std::cout<<'\n';
}

template<class F> void rejected(F&& fn,const char* label) {
    try { fn(); } catch (const c::Error&) { std::cout<<"GUARD "<<label<<" PASS\n"; return; }
    throw std::runtime_error(std::string("catalog accepted ")+label);
}

void controls() {
    Fixture f;
    std::cout<<"VIRTUAL_STRATEGY_CATALOG_V1\n";
    c::Catalog catalog(f.history,{1326,1326},limits());
    const auto menu=std::span(f.root_actions).first(f.root_count);
    const auto first=catalog.resolve(f.history,f.root,0,0,1326,f.root_source,menu);
    const auto first_again=catalog.resolve(f.history,f.root,0,0,1326,f.root_source,menu);
    const auto last=catalog.resolve(f.history,f.root,0,1325,1326,f.root_source,menu);
    require(catalog.view(first).holding_index==0 && catalog.view(first_again).holding_index==0,
            "duplicate RowId was unstable");
    require(catalog.view(last).holding_index==1325,"last generic holding index missing");
    require(catalog.receipt().public_blocks==1 && catalog.receipt().information_rows_seen==2,
            "catalog materialized undeclared holding rows");
    require(catalog.receipt().menus==1 && catalog.receipt().action_slots_seen==2*f.root_count,
            "menu or action-slot reuse accounting");
    row("root-first",catalog,first);
    row("root-last",catalog,last);
    std::cout<<"CONTROL sparse-endpoints PASS\n";

    h::History::Cursor child{};
    h::History::DecisionKey child_info{};
    bool found_decision=false;
    for (std::size_t edge=0;edge<f.root_count && !found_decision;++edge) {
        auto candidate=f.history.append_action(f.root,edge);
        try { child_info=f.history.decision_key(candidate); child=candidate; found_decision=true; }
        catch (const h::Error&) { }
    }
    require(found_decision,"fixture has no decision after an action");
    std::array<std::string_view,c::maximum_actions> child_actions{};
    f.history.decision_actions(child,std::span(child_actions).first(child_info.actions));
    auto other=catalog.resolve(f.history,child,child_info.actor,0,1326,child_info.source,
                               std::span(child_actions).first(child_info.actions));
    require(catalog.view(other).public_ordinal!=catalog.view(first).public_ordinal,
            "action histories collapsed to a single infoset");
    row("after-action",catalog,other);
    std::cout<<"CONTROL action-perfect-recall PASS\n";

    h::History::Cursor reveal{}; std::size_t visits=0;
    require(first_reveal(f,f.root,reveal,visits),"fixture has no public reveal");
    require(f.history.visible_size(reveal)==0,"expected first reveal to be the flop");
    const auto cards=t::deck_cards;
    std::array<std::uint8_t,3> board_a{cards[0],cards[1],cards[2]};
    std::array<std::uint8_t,3> board_b{cards[0],cards[1],cards[3]};
    std::sort(board_a.begin(),board_a.end()); std::sort(board_b.begin(),board_b.end());
    auto flop_a=f.history.append_reveal(reveal,board_a);
    auto flop_b=f.history.append_reveal(reveal,board_b);
    const auto ainfo=f.history.decision_key(flop_a),binfo=f.history.decision_key(flop_b);
    require(ainfo.source==binfo.source && ainfo.ordinal!=binfo.ordinal,
            "ordered visible prefixes did not retain distinct full-history identities");
    std::array<std::string_view,c::maximum_actions> aa{},ba{};
    f.history.decision_actions(flop_a,std::span(aa).first(ainfo.actions));
    f.history.decision_actions(flop_b,std::span(ba).first(binfo.actions));
    const auto flop_row_a=catalog.resolve(f.history,flop_a,ainfo.actor,1,1326,ainfo.source,std::span(aa).first(ainfo.actions));
    const auto flop_row_b=catalog.resolve(f.history,flop_b,binfo.actor,1,1326,binfo.source,std::span(ba).first(binfo.actions));
    row("flop-a",catalog,flop_row_a); row("flop-b",catalog,flop_row_b);
    require(catalog.receipt().public_blocks>=4,"ordered visible prefixes merged as a public block");
    std::cout<<"CONTROL ordered-prefix-perfect-recall PASS\n";

    c::Catalog bad_default(f.history,{1326,1326},limits());
    rejected([&]{(void)bad_default.view(c::RowId{});},"default-row-id-poisons");
    require(bad_default.failed(),"default RowId did not poison catalog");
    c::Catalog owner_a(f.history,{1326,1326},limits()),owner_b(f.history,{1326,1326},limits());
    const auto foreign_id=owner_b.resolve(f.history,f.root,0,0,1326,f.root_source,
                                           std::span(f.root_actions).first(f.root_count));
    rejected([&]{(void)owner_a.view(foreign_id);},"foreign-row-id-poisons");
    require(owner_a.failed(),"foreign RowId did not poison catalog");
    c::Catalog foreign_cursor_catalog(f.history,{1326,1326},limits());
    Fixture foreign;
    rejected([&]{(void)foreign_cursor_catalog.resolve(foreign.history,foreign.root,0,0,1326,foreign.root_source,
                                       std::span(foreign.root_actions).first(foreign.root_count));},
             "foreign-history-poisons");
    require(foreign_cursor_catalog.failed(),"foreign history did not poison catalog");
    c::Catalog unknown_holding(f.history,{1326,1326},limits());
    rejected([&]{(void)unknown_holding.resolve(f.history,f.root,0,1326,1326,f.root_source,
                                       std::span(f.root_actions).first(f.root_count));},"unknown-holding-poisons");
    c::Catalog wrong_actor(f.history,{1326,1326},limits());
    rejected([&]{(void)wrong_actor.resolve(f.history,f.root,1,0,1326,f.root_source,
                                       std::span(f.root_actions).first(f.root_count));},"wrong-actor-poisons");
    c::Catalog wrong_menu(f.history,{1326,1326},limits());
    auto changed=f.root_actions; changed[0]="changed-menu";
    rejected([&]{(void)wrong_menu.resolve(f.history,f.root,0,0,1326,f.root_source,
                                       std::span(changed).first(f.root_count));},"changed-menu-poisons");
    c::Catalog low_rows(f.history,{1326,1326},limits(8,1));
    (void)low_rows.resolve(f.history,f.root,0,0,1326,f.root_source,menu);
    rejected([&]{(void)low_rows.resolve(f.history,f.root,0,1,1326,f.root_source,menu);},"row-cap-poisons");
    auto short_metadata=limits(); --short_metadata.max_metadata_entries;
    rejected([&]{(void)c::Catalog(f.history,{1326,1326},short_metadata);},"metadata-one-short");
    auto short_work=limits(); short_work.max_work=c::Catalog::work_forecast(short_work)-1;
    rejected([&]{(void)c::Catalog(f.history,{1326,1326},short_work);},"work-one-short");
    auto one_access=limits(8,16,128,8,1326,1);
    c::Catalog readcap(f.history,{1326,1326},one_access);
    auto read_id=readcap.resolve(f.history,f.root,0,0,1326,f.root_source,menu);
    rejected([&]{(void)readcap.view(read_id);},"view-read-cap-poisons");

    rejected([&]{(void)c::Catalog(f.history,{1326,1326},limits(0));},"zero-block-limit");
    rejected([&]{(void)c::Catalog(f.history,{1326,1326},limits(8,16,128,8,1327));},"holding-limit");
    rejected([&]{(void)c::Catalog(f.history,{1326,1326},limits(8,16,128,8,1326,1,1));},"work-limit");
    auto receipt=catalog.receipt();
    std::cout<<"RECEIPT "<<receipt.work<<' '<<receipt.lookups<<' '<<receipt.public_blocks<<' '
             <<receipt.information_rows_seen<<' '<<receipt.action_slots_seen<<' '<<receipt.menus<<' '
             <<receipt.metadata_entries<<' '<<receipt.metadata_payload_bits<<'\n';
    std::cout<<"END\n";
}
}

int main() {
    try { controls(); return 0; }
    catch (const std::exception& e) { std::cerr<<"virtual strategy catalog controls: "<<e.what()<<'\n'; return 2; }
}
