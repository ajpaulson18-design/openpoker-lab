// Retain the complete original Catalog controls, then add the opt-in contract.
#define main original_catalog_controls_main
#include "virtual_strategy_catalog_controls.cpp"
#undef main

namespace {
template<class F> void lazy_rejected(F&& fn,const char* label,c::ErrorKind expected) {
    try { fn(); }
    catch (const c::Error& e) {
        require(e.kind()==expected,"lazy guard returned a different typed failure");
        std::cout<<"GUARD "<<label<<" PASS\n"; return;
    }
    throw std::runtime_error(std::string("lazy catalog accepted ")+label);
}
c::Limits lazy_limits(std::size_t blocks=8,std::size_t rows=16,std::size_t menus=8,
                      std::uint64_t lookups=64) {
    auto result=limits(blocks,rows,rows*c::maximum_actions,menus,1326,lookups,75000000);
    result.seen_storage=c::Limits::SeenStorage::first_holding_inline;
    result.max_metadata_entries=c::Catalog::metadata_word_forecast(result);
    result.max_metadata_payload_bits=64*result.max_metadata_entries;
    result.max_work=c::Catalog::work_forecast(result);
    return result;
}

void lazy_controls() {
    Fixture f; const auto menu=std::span(f.root_actions).first(f.root_count);
    std::cout<<"VIRTUAL_LAZY_CATALOG_V1\n";
    const auto wide_limits=lazy_limits(1,1326,1,4000);
    c::Catalog wide(f.history,{1326,1326},wide_limits);
    const auto first=wide.resolve(f.history,f.root,0,1325,1326,f.root_source,menu);
    const auto duplicate=wide.resolve(f.history,f.root,0,1325,1326,f.root_source,menu);
    require(first==duplicate && wide.view(first).holding_index==1325 &&
            wide.receipt().allocated_bitmap_words==0 && wide.receipt().information_rows_seen==1,
            "inline first/duplicate holding semantics");
    std::cout<<"SNAP first "<<wide.receipt().public_blocks<<' '<<wide.receipt().information_rows_seen<<' '
             <<wide.receipt().allocated_bitmap_words<<' '<<wide.receipt().peak_occupied_metadata_entries<<'\n';
    row("lazy-first",wide,first);
    const auto second=wide.resolve(f.history,f.root,0,0,1326,f.root_source,menu);
    require(wide.view(first).holding_index==1325 && wide.view(second).holding_index==0 &&
            wide.receipt().allocated_bitmap_words==21,"promotion lost first/second original holding");
    row("lazy-promoted",wide,second);
    std::cout<<"IDS 1326 1325";
    for (std::size_t holding=0;holding<1325;++holding) {
        const auto id=wide.resolve(f.history,f.root,0,holding,1326,f.root_source,menu);
        const auto view=wide.view(id);
        require(view.public_ordinal==wide.view(first).public_ordinal && view.actor==0 &&
                view.holding_index==holding && view.source_menu_ref==f.root_source,"dense promoted row identity");
        std::cout<<' '<<view.holding_index;
    }
    std::cout<<'\n';
    require(wide.receipt().information_rows_seen==1326 && wide.receipt().allocated_bitmap_words==21,
            "all holding endpoints did not reuse one bitmap");
    std::cout<<"SNAP all "<<wide.receipt().public_blocks<<' '<<wide.receipt().information_rows_seen<<' '
             <<wide.receipt().allocated_bitmap_words<<' '<<wide.receipt().peak_occupied_metadata_entries<<'\n';

    h::History::Cursor reveal{}; std::size_t visits=0;
    require(first_reveal(f,f.root,reveal,visits),"missing public reveal");
    const auto cards=t::deck_cards;
    c::Catalog sparse(f.history,{1326,1326},lazy_limits(32,32,1,64));
    auto eager_limits=limits(32,32,640,1,1326,64,75000000);
    eager_limits.max_work=c::Catalog::work_forecast(eager_limits);
    c::Catalog eager(f.history,{1326,1326},eager_limits);
    std::size_t blocks=0;
    h::History::Cursor last_flop{};
    for (std::size_t a=0;a<cards.size() && blocks<32;++a)
    for (std::size_t b=a+1;b<cards.size() && blocks<32;++b)
    for (std::size_t d=b+1;d<cards.size() && blocks<32;++d) {
        std::array<std::uint8_t,3> board{cards[a],cards[b],cards[d]}; std::sort(board.begin(),board.end());
        const auto flop=f.history.append_reveal(reveal,board); last_flop=flop;
        const auto info=f.history.decision_key(flop);
        std::array<std::string_view,c::maximum_actions> aa{};
        f.history.decision_actions(flop,std::span(aa).first(info.actions));
        const auto holding=(97*blocks)%1326;
        const auto lazy_id=sparse.resolve(f.history,flop,info.actor,holding,1326,info.source,std::span(aa).first(info.actions));
        const auto old_id=eager.resolve(f.history,flop,info.actor,holding,1326,info.source,std::span(aa).first(info.actions));
        const auto lhs=sparse.view(lazy_id),rhs=eager.view(old_id);
        require(lhs.public_ordinal==rhs.public_ordinal && lhs.holding_index==rhs.holding_index &&
                lhs.actor==rhs.actor && lhs.source_menu_ref==rhs.source_menu_ref &&
                std::equal(lhs.actions.begin(),lhs.actions.end(),rhs.actions.begin(),rhs.actions.end()),
                "eager/lazy sparse public identity/menu parity");
        ++blocks;
    }
    require(blocks==32 && sparse.receipt().allocated_bitmap_words==0 && eager.receipt().allocated_bitmap_words==672,
            "new public blocks allocated eager bitmaps in lazy mode");
    std::cout<<"SPARSE "<<sparse.receipt().public_blocks<<' '<<sparse.receipt().information_rows_seen<<' '
             <<sparse.receipt().allocated_bitmap_words<<' '<<eager.receipt().allocated_bitmap_words<<' '
             <<sparse.receipt().metadata_entries<<' '<<eager.receipt().metadata_entries<<'\n';

    const auto coupled_limits=lazy_limits(2,2,2,8);
    c::Catalog coupled(f.history,{1326,1326},coupled_limits);
    (void)coupled.resolve(f.history,f.root,0,0,1326,f.root_source,menu);
    (void)coupled.resolve(f.history,f.root,0,1325,1326,f.root_source,menu);
    require(coupled.receipt().allocated_bitmap_words==21 &&
            coupled.receipt().peak_occupied_metadata_entries<=coupled.receipt().metadata_entries,
            "descriptor slack did not cover a feasible promoted block");
    std::cout<<"COUPLED "<<coupled.receipt().public_blocks<<' '<<coupled.receipt().information_rows_seen<<' '
             <<coupled.receipt().allocated_bitmap_words<<' '<<coupled.receipt().metadata_entries<<' '
             <<coupled.receipt().peak_occupied_metadata_entries<<'\n';

    auto one=lazy_limits(1,1,1,8); c::Catalog capped(f.history,{1326,1326},one);
    (void)capped.resolve(f.history,f.root,0,0,1326,f.root_source,menu);
    lazy_rejected([&]{(void)capped.resolve(f.history,f.root,0,1,1326,f.root_source,menu);},"lazy-row-cap-before-bitmap",c::ErrorKind::capacity);
    require(capped.failed() && capped.receipt().allocated_bitmap_words==0,"row cap allocated a forbidden bitmap");
    c::Catalog foreign(f.history,{1326,1326},lazy_limits());
    lazy_rejected([&]{(void)foreign.view(first);},"lazy-foreign-row",c::ErrorKind::foreign_row);
    c::Catalog bad_default(f.history,{1326,1326},lazy_limits());
    lazy_rejected([&]{(void)bad_default.view(c::RowId{});},"lazy-default-row",c::ErrorKind::foreign_row);
    c::Catalog changed(f.history,{1326,1326},lazy_limits());
    (void)changed.resolve(f.history,f.root,0,0,1326,f.root_source,menu);
    auto wrong=f.root_actions; wrong[0]="changed-menu";
    lazy_rejected([&]{(void)changed.resolve(f.history,f.root,0,1,1326,f.root_source,std::span(wrong).first(f.root_count));},"lazy-changed-menu",c::ErrorKind::changed_menu);
    require(changed.failed() && changed.receipt().allocated_bitmap_words==0,"changed menu allocated before rejection");
    auto short_metadata=one; --short_metadata.max_metadata_entries;
    lazy_rejected([&]{(void)c::Catalog(f.history,{1326,1326},short_metadata);},"lazy-metadata-one-short",c::ErrorKind::invalid_limits);
    auto short_work=one; --short_work.max_work;
    lazy_rejected([&]{(void)c::Catalog(f.history,{1326,1326},short_work);},"lazy-work-one-short",c::ErrorKind::invalid_limits);
    auto invalid=one; invalid.seen_storage=static_cast<c::Limits::SeenStorage>(2);
    lazy_rejected([&]{(void)c::Catalog(f.history,{1326,1326},invalid);},"lazy-invalid-mode",c::ErrorKind::invalid_limits);
    invalid=one; invalid.max_public_blocks=2;
    lazy_rejected([&]{(void)c::Catalog(f.history,{1326,1326},invalid);},"lazy-rows-below-blocks",c::ErrorKind::invalid_limits);
    const auto last_info=f.history.decision_key(last_flop);
    require(last_info.actor<=1,"ordered public fixture actor");
    std::cout<<"FORECAST wide "<<wide_limits.max_public_blocks<<' '<<wide_limits.max_information_rows_seen<<' '
             <<wide_limits.max_menus<<' '<<wide_limits.max_holding_count<<' '<<wide_limits.max_lookups<<' '
             <<wide_limits.max_work<<' '<<wide_limits.max_metadata_entries<<' '<<wide_limits.max_metadata_payload_bits<<'\n';
    std::cout<<"LAZY_END\n";
}
}

int main() {
    const int old=original_catalog_controls_main(); if (old) return old;
    try { lazy_controls(); return 0; }
    catch (const std::exception& e) { std::cerr<<"lazy catalog controls: "<<e.what()<<'\n'; return 2; }
}
