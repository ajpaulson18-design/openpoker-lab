// Synthetic component transitions, not a whole-game learner.
#include "../../native/virtual_sparse_strategy_epoch.hpp"
#include "../../native/virtual_frozen_grid_raw.hpp"
#include <array>
#include <iostream>

namespace t=openpoker::virtual_dyadic_training;
namespace h=openpoker::virtual_dyadic_history;
namespace c=openpoker::virtual_strategy_catalog;
namespace e=openpoker::virtual_sparse_strategy_epoch;

// Compile the reused numerical traversal against the leased provider. Runtime
// whole-game admission and numerical replay remain separate integration gates.
using SparseRawWalk=openpoker::virtual_frozen_grid_raw::BasicWalk<e::Store::EpochLease>;
[[maybe_unused]] const auto sparse_raw_entry=&SparseRawWalk::run;

namespace {
void require(bool value,const char* text) {if(!value)throw std::runtime_error(text);}
c::Limits catalog_limits() {
    c::Limits limits{8,8,32,8,2,64,1000000,0,0};
    limits.max_metadata_entries=c::Catalog::metadata_word_forecast(limits);
    limits.max_metadata_payload_bits=64*limits.max_metadata_entries;return limits;
}
e::Limits epoch_limits() {
    e::Limits limits;limits.max_rows_touched=2;limits.max_slots_touched=8;
    limits.max_stage_rows=1;limits.max_stage_slots=4;limits.max_reads=4;
    limits.catalog_max_public_blocks=8;limits.max_work=1000000;return limits;
}
struct Fixture {
    t::betting::Template source{t::configuration(),t::template_limits()};
    h::History history{source,t::chance::DeckDefinition::reduced(t::deck_cards)};
    c::Catalog catalog{history,{2,2},catalog_limits()};
    e::Store store{catalog,history,{2,2},epoch_limits()};
    explicit Fixture(e::Limits limits=epoch_limits()) : store(catalog,history,{2,2},limits) {}
};
template<class F> void rejected(const char* label,F&& call) {
    try {call();} catch(const e::Error&) {std::cout<<"GUARD "<<label<<" PASS\n";return;}
    throw std::runtime_error("sparse epoch accepted invalid component operation");
}
void observe(const char* label,Fixture& fixture) {
    fixture.store.visit_committed([&](c::RowId id,std::span<const e::Integer> regrets,
                                  std::span<const e::Integer> averages,std::span<const std::uint64_t> units) {
        const auto row=fixture.catalog.view(id);
        std::cout<<"ROW "<<label<<' '<<row.public_ordinal<<' '<<row.actor<<' '
                 <<row.holding_index<<' '<<units.size();
        for(std::size_t i=0;i<units.size();++i)std::cout<<' '<<regrets[i]<<' '<<averages[i]<<' '<<units[i];
        std::cout<<'\n';
    });
}
void step(Fixture& fixture,const std::array<e::Integer,4>& regret,
          const std::array<e::Integer,4>& average,const e::Integer& denominator,
          const std::array<std::uint64_t,4>& expected_units) {
    {
        auto lease=fixture.store.begin_epoch(e::ProposalLaw::uniform_public);
        const auto first=lease.frozen_policy(fixture.history.root(),0,0);
        const auto second=lease.frozen_policy(fixture.history.root(),0,0);
        require(first.id==second.id && first.units.size()==4,"sparse repeated catalog identity");
        require(std::equal(first.units.begin(),first.units.end(),expected_units.begin()),"sparse frozen units differ");
        lease.seal_raw_walk(1,4,2);
        lease.stage(first.id,regret,average,denominator,e::regret_denominator);
        // Staging next values must leave this epoch's borrowed units unchanged.
        require(std::equal(first.units.begin(),first.units.end(),expected_units.begin()),"sparse staging mutated leased policy");
    }
    fixture.store.commit();
}
void controls() {
    std::cout<<"VIRTUAL_SPARSE_EPOCH_COMPONENT_V1\n";
    const std::array<std::uint64_t,4> uniform{e::grid/4,e::grid/4,e::grid/4,e::grid/4};
    Fixture fixture;
    step(fixture,{5,-3,0,-2},{1,2,3,4},e::Integer(29)<<52,uniform);
    observe("signed-E1",fixture);
    step(fixture,{-7,4,2,-1},{7,0,9,0},e::average_denominator,{e::grid,0,0,0});
    observe("signed-E2",fixture);
    const auto receipt=fixture.store.receipt();
    require(receipt.commits==2 && receipt.quantized_rows==2 && receipt.current_rows==1 && receipt.current_slots==4,
            "sparse cumulative row/quantization census");
    std::cout<<"RECEIPT signed "<<receipt.work<<' '<<receipt.quantizer_work<<' '<<receipt.reads<<' '
             <<receipt.staged_rows<<' '<<receipt.staged_slots<<' '<<receipt.commits<<' '
             <<receipt.quantized_rows<<' '<<receipt.current_rows<<' '<<receipt.current_slots<<' '
             <<receipt.peak_payload_bits<<'\n';
    rejected("third-epoch",[&]{(void)fixture.store.begin_epoch(e::ProposalLaw::uniform_public);});

    Fixture averages;
    step(averages,{0,0,0,0},{1,2,3,4},e::Integer(29)<<52,uniform);
    observe("averages-E1",averages);
    step(averages,{0,0,0,0},{7,0,9,0},e::average_denominator,uniform);
    observe("averages-E2",averages);
    require(averages.store.receipt().quantized_rows==0 && averages.store.receipt().quantizer_work==0,
            "average-only stage quantized an unchanged regret row");
    std::cout<<"CONTROL average-only-no-quantization PASS\n";

    Fixture optional_export;
    step(optional_export,{5,-3,0,-2},{1,2,3,4},e::Integer(29)<<52,uniform);
    step(optional_export,{-7,4,2,-1},{7,0,9,0},e::average_denominator,{e::grid,0,0,0});
    require(optional_export.store.receipt().export_calls==0,"sparse transition required an image export");
    observe("no-intermediate-export-E2",optional_export);
    require(optional_export.store.receipt().export_calls==1,"optional final export count");
    std::cout<<"CONTROL no-intermediate-export PASS\n";

    Fixture active;
    {
        auto lease=active.store.begin_epoch(e::ProposalLaw::uniform_public);
        rejected("commit-during-lease",[&]{active.store.commit();});
        require(active.store.failed(),"active-lease guard did not fail closed");
    }
    Fixture weighted;
    rejected("weighted-law",[&]{(void)weighted.store.begin_epoch(e::ProposalLaw::weighted_river);});
    Fixture incomplete;
    {
        auto lease=incomplete.store.begin_epoch(e::ProposalLaw::uniform_public);
        (void)lease.frozen_policy(incomplete.history.root(),0,0);
        rejected("incomplete-two-seat-read",[&]{lease.seal_raw_walk(1,4,2);});
    }
    Fixture duplicate;
    {
        auto lease=duplicate.store.begin_epoch(e::ProposalLaw::uniform_public);
        const auto view=lease.frozen_policy(duplicate.history.root(),0,0);
        (void)lease.frozen_policy(duplicate.history.root(),0,0);lease.seal_raw_walk(1,4,2);
        const std::array<e::Integer,4> r{5,-3,0,-2},a{1,2,3,4};
        lease.stage(view.id,r,a,e::Integer(29)<<52);
        rejected("duplicate-stage",[&]{lease.stage(view.id,r,a,e::Integer(29)<<52);});
    }
    Fixture invalid;
    {
        auto lease=invalid.store.begin_epoch(e::ProposalLaw::uniform_public);
        const auto view=lease.frozen_policy(invalid.history.root(),0,0);
        (void)lease.frozen_policy(invalid.history.root(),0,0);lease.seal_raw_walk(1,4,2);
        const std::array<e::Integer,4> r{5,-3,0,-2},a{1,2,3,4};
        rejected("nonmember-denominator",[&]{lease.stage(view.id,r,a,3);});
    }
    auto two_rows=epoch_limits();two_rows.max_rows_touched=4;two_rows.max_slots_touched=16;
    two_rows.max_stage_rows=2;two_rows.max_stage_slots=8;two_rows.max_reads=8;
    Fixture omitted(two_rows);
    {
        auto lease=omitted.store.begin_epoch(e::ProposalLaw::uniform_public);
        const auto row0=lease.frozen_policy(omitted.history.root(),0,0);
        (void)lease.frozen_policy(omitted.history.root(),0,1);
        (void)lease.frozen_policy(omitted.history.root(),0,0);
        (void)lease.frozen_policy(omitted.history.root(),0,1);
        lease.seal_raw_walk(2,8,4);
        const std::array<e::Integer,4> r{5,-3,0,-2},a{1,2,3,4};
        lease.stage(row0.id,r,a,e::Integer(29)<<52);
    }
    require(omitted.store.failed() && omitted.store.receipt().commits==0,
            "incomplete stage set changed the committed image");
    rejected("incomplete-stage-set",[&]{omitted.store.commit();});
    std::cout<<"END\n";
}
}
int main() {
    try {controls();return 0;}
    catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
