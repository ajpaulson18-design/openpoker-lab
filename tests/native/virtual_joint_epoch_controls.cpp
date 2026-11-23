// Synthetic constructor-bound arithmetic controls, not whole-game learning.
#include "../../native/virtual_sparse_strategy_epoch.hpp"
#include "../../native/virtual_dyadic_training.hpp"
#include <array>
#include <iostream>

namespace t=openpoker::virtual_dyadic_training;
namespace h=openpoker::virtual_dyadic_history;
namespace c=openpoker::virtual_strategy_catalog;
namespace e=openpoker::virtual_sparse_strategy_epoch;
using Row=std::array<e::Integer,4>;
namespace {
void require(bool value,const char* message) {if(!value)throw std::runtime_error(message);}
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
    e::Store store;
    explicit Fixture(e::ArithmeticContract arithmetic=e::ArithmeticContract::true_joint_proof9)
        :store(catalog,history,{2,2},epoch_limits(),arithmetic) {}
};
template<class F> void rejected(const char* label,e::ErrorKind expected,F&& operation) {
    try {operation();}
    catch(const e::Error& error) {
        require(error.kind()==expected,"joint epoch rejection has wrong typed error");
        std::cout<<"GUARD "<<label<<" PASS\n";return;
    }
    throw std::runtime_error("joint epoch accepted invalid operation");
}
auto read_twice(Fixture& fixture,e::Store::EpochLease& lease) {
    const auto first=lease.frozen_policy(fixture.history.root(),0,0);
    const auto second=lease.frozen_policy(fixture.history.root(),0,0);
    require(first.id==second.id && first.units.size()==4,"joint two-read identity");
    return first;
}
void export_row(const char* label,Fixture& fixture) {
    fixture.store.visit_committed([&](c::RowId id,std::span<const e::Integer> r,
                                    std::span<const e::Integer> a,std::span<const std::uint64_t> u) {
        const auto view=fixture.catalog.view(id);
        require(view.actor==0 && view.holding_index==0 && view.public_ordinal==0 && u.size()==4,
                "joint export own holding/visible identity");
        std::cout<<"ROW "<<label;
        for(std::size_t i=0;i<4;++i)std::cout<<' '<<r[i]<<' '<<a[i]<<' '<<u[i];
        std::cout<<'\n';
    });
}
void step(Fixture& fixture,const Row& r,const Row& a,bool explicit_denominator,
          const std::array<std::uint64_t,4>& expected) {
    {
        auto lease=fixture.store.begin_epoch(e::ProposalLaw::true_joint);
        require(lease.arithmetic_contract()==e::ArithmeticContract::true_joint_proof9,
            "joint lease constructor-bound arithmetic tag");
        const auto view=read_twice(fixture,lease);
        require(std::equal(view.units.begin(),view.units.end(),expected.begin()),"joint frozen policy image");
        lease.seal_raw_walk(1,4,2);
        if(explicit_denominator)lease.stage(view.id,r,a,fixture.store.average_denominator_value(),
                                         fixture.store.regret_denominator_value());
        else lease.stage(view.id,r,a,fixture.store.average_denominator_value());
        require(std::equal(view.units.begin(),view.units.end(),expected.begin()),"joint staging changed leased units");
    }
    fixture.store.commit();
}
template<class Operation> void bad_stage(const char* label,Operation&& operation,
                                        e::ArithmeticContract contract=e::ArithmeticContract::true_joint_proof9) {
    Fixture fixture(contract);
    {
        auto lease=fixture.store.begin_epoch(contract==e::ArithmeticContract::true_joint_proof9?
            e::ProposalLaw::true_joint:e::ProposalLaw::uniform_public);
        const auto view=read_twice(fixture,lease);lease.seal_raw_walk(1,4,2);
        rejected(label,e::ErrorKind::arithmetic,[&]{operation(fixture,lease,view.id);});
    }
    require(fixture.store.failed() && fixture.store.receipt().commits==0,"joint stage failure did not poison owner");
}
void controls() {
    std::cout<<"VIRTUAL_JOINT_EPOCH_COMPONENT_V1\n";
    const e::Integer dr=e::Integer(1)<<625,da=e::Integer(1)<<364;
    const std::array<std::uint64_t,4> uniform{e::grid/4,e::grid/4,e::grid/4,e::grid/4};
    Fixture main;
    require(main.store.arithmetic_contract()==e::ArithmeticContract::true_joint_proof9 &&
        main.store.regret_denominator_value()==dr && main.store.average_denominator_value()==da,
        "joint constructor-bound denominators");
    std::cout<<"DENOM joint "<<main.store.regret_denominator_value()<<' '
             <<main.store.average_denominator_value()<<'\n';
    step(main,{5*dr,-3*dr,0,-2*dr},{da/4,da/4,da/4,da/4},false,uniform);
    export_row("E1",main);
    step(main,{0,4*dr,2*dr,-dr},{da,0,0,0},true,{e::grid,0,0,0});
    export_row("E2",main);
    const auto& receipt=main.store.receipt();
    require(receipt.reads==4 && receipt.staged_rows==2 && receipt.staged_slots==8 && receipt.commits==2 &&
        receipt.current_rows==1 && receipt.current_slots==4 && receipt.quantized_rows==2,
        "joint cumulative two-read lifecycle");
    std::cout<<"RECEIPT "<<receipt.work<<' '<<receipt.quantizer_work<<' '<<receipt.reads<<' '
        <<receipt.staged_rows<<' '<<receipt.staged_slots<<' '<<receipt.commits<<' '
        <<receipt.quantized_rows<<' '<<receipt.current_rows<<' '<<receipt.current_slots<<'\n';
    rejected("joint-third-epoch",e::ErrorKind::epoch_limit,[&]{(void)main.store.begin_epoch(e::ProposalLaw::true_joint);});

    // Construct with the original signature to verify the unchanged default.
    Fixture source_owner;
    e::Store legacy(source_owner.catalog,source_owner.history,{2,2},epoch_limits());
    require(legacy.arithmetic_contract()==e::ArithmeticContract::uniform_public_proof9 &&
        legacy.regret_denominator_value()==e::regret_denominator &&
        legacy.average_denominator_value()==e::average_denominator,"legacy arithmetic default changed");
    std::cout<<"DENOM legacy "<<legacy.regret_denominator_value()<<' '<<legacy.average_denominator_value()<<'\n';
    rejected("legacy-rejects-joint-law",e::ErrorKind::invalid_limits,[&]{(void)legacy.begin_epoch(e::ProposalLaw::true_joint);});
    require(legacy.failed(),"legacy proposal mismatch did not poison");
    Fixture public_law;
    rejected("joint-rejects-public-law",e::ErrorKind::invalid_limits,[&]{(void)public_law.store.begin_epoch(e::ProposalLaw::uniform_public);});
    require(public_law.store.failed(),"joint public mismatch did not poison");
    Fixture weighted;
    rejected("joint-rejects-weighted-law",e::ErrorKind::invalid_limits,[&]{(void)weighted.store.begin_epoch(e::ProposalLaw::weighted_river);});
    Fixture invalid_law;
    rejected("joint-rejects-unknown-law",e::ErrorKind::invalid_limits,[&]{(void)invalid_law.store.begin_epoch(static_cast<e::ProposalLaw>(255));});
    rejected("unknown-arithmetic",e::ErrorKind::invalid_limits,[&]{
        e::Store invalid(source_owner.catalog,source_owner.history,{2,2},epoch_limits(),static_cast<e::ArithmeticContract>(255));
        (void)invalid;
    });

    const Row centered{5*dr,-3*dr,0,-2*dr},averages{da/4,da/4,da/4,da/4};
    bad_stage("joint-rejects-public-R",[&](auto&,auto& lease,auto id){lease.stage(id,centered,averages,da,e::regret_denominator);});
    bad_stage("joint-rejects-public-A",[&](auto&,auto& lease,auto id){lease.stage(id,centered,averages,e::average_denominator,dr);});
    bad_stage("joint-rejects-divisor-A",[&](auto&,auto& lease,auto id){lease.stage(id,centered,averages,da/2,dr);});
    bad_stage("legacy-rejects-joint-R",[&](auto&,auto& lease,auto id){lease.stage(id,centered,averages,da,dr);},
        e::ArithmeticContract::uniform_public_proof9);
    bad_stage("joint-uncentered-regret",[&](auto&,auto& lease,auto id){lease.stage(id,Row{dr,0,0,0},averages,da);});
    bad_stage("joint-average-proportions",[&](auto&,auto& lease,auto id){lease.stage(id,centered,Row{da,0,0,0},da);});
    bad_stage("joint-negative-average",[&](auto&,auto& lease,auto id){lease.stage(id,centered,Row{-1,-1,-1,-1},da);});
    Fixture incomplete;
    {
        auto lease=incomplete.store.begin_epoch(e::ProposalLaw::true_joint);
        (void)lease.frozen_policy(incomplete.history.root(),0,0);
        rejected("joint-needs-two-reads",e::ErrorKind::incomplete_walk,[&]{lease.seal_raw_walk(1,4,2);});
    }
    require(incomplete.store.failed(),"joint incomplete read did not poison");
    Fixture missing;
    {
        auto lease=missing.store.begin_epoch(e::ProposalLaw::true_joint);
        (void)read_twice(missing,lease);lease.seal_raw_walk(1,4,2);
    }
    require(missing.store.failed() && missing.store.receipt().commits==0,"joint abandoned stage image");
    rejected("joint-missing-stage",e::ErrorKind::failed_owner,[&]{missing.store.commit();});
    Fixture duplicate;
    {
        auto lease=duplicate.store.begin_epoch(e::ProposalLaw::true_joint);
        const auto view=read_twice(duplicate,lease);lease.seal_raw_walk(1,4,2);
        lease.stage(view.id,centered,averages,da);
        rejected("joint-duplicate-stage",e::ErrorKind::duplicate_stage,[&]{lease.stage(view.id,centered,averages,da);});
    }
    require(duplicate.store.failed() && duplicate.store.receipt().commits==0,"joint duplicate published partial image");
    std::cout<<"END\n";
}
} // namespace
int main() {
    try {controls();return 0;}
    catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
