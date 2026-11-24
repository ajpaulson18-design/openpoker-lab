#define main original_single_pass_epoch_main
#include "virtual_single_pass_epoch_controls.cpp"
#undef main

int main() {
    const int original=original_single_pass_epoch_main(); if(original)return original;
    try {
        t::betting::Template source(t::configuration(),t::template_limits());
        h::History history(source,t::chance::DeckDefinition::reduced(t::deck_cards));
        c::Catalog eager(history,{2,2},catalog_limits());
        auto catalog_plan=catalog_limits();
        catalog_plan.seen_storage=c::Limits::SeenStorage::first_holding_inline;
        catalog_plan.max_metadata_entries=c::Catalog::metadata_word_forecast(catalog_plan);
        catalog_plan.max_metadata_payload_bits=64*catalog_plan.max_metadata_entries;
        catalog_plan.max_work=c::Catalog::work_forecast(catalog_plan);
        c::Catalog lazy(history,{2,2},catalog_plan);
        const auto mode=e::ArithmeticContract::weighted_joint_single_pass;
        auto lazy_plan=limits();lazy_plan.catalog_seen_storage=catalog_plan.seen_storage;
        rejected("eager-store-lazy-catalog",e::ErrorKind::invalid_limits,[&]{e::Store invalid(lazy,history,{2,2},limits(),mode);});
        rejected("lazy-store-eager-catalog",e::ErrorKind::invalid_limits,[&]{e::Store invalid(eager,history,{2,2},lazy_plan,mode);});
        auto invalid=lazy_plan;invalid.catalog_seen_storage=static_cast<c::Limits::SeenStorage>(2);
        rejected("invalid-storage-contract",e::ErrorKind::invalid_limits,[&]{e::Store bad(lazy,history,{2,2},invalid,mode);});
        e::Store good(lazy,history,{2,2},lazy_plan,mode);
        const e::Integer dr=e::Integer(1)<<625,da=e::Integer(1)<<364;
        const std::array<e::Integer,4> r{5*dr,-3*dr,0,-2*dr},a{da/4,da/4,da/4,da/4};
        {
            auto lease=good.begin_epoch(e::ProposalLaw::true_joint);
            const auto view=lease.frozen_policy(history.root(),0,0);
            lease.seal_raw_walk(1,4,1);lease.stage(view.id,r,a,da,dr);
            require(view.units[0]==e::grid/4,"lazy stage mutated frozen policy");
        }
        good.commit();std::size_t exported=0;
        good.visit_committed([&](auto,std::span<const e::Integer> regrets,std::span<const e::Integer> averages,
                               std::span<const std::uint64_t> units) {
            require(units.size()==4 && units[0]==e::grid && units[1]==0 && units[2]==0 && units[3]==0,
                    "lazy exact committed policy");
            for(std::size_t i=0;i<4;++i)require(regrets[i]==r[i] && averages[i]==a[i],"lazy exact cumulative numerics");
            ++exported;
        });
        require(exported==1 && lazy.receipt().allocated_bitmap_words==0,"lazy epoch allocated first-holding bitmap");
        std::cout<<"LAZY_EPOCH_GUARDS_V1 PASS 3 1\n";return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}
