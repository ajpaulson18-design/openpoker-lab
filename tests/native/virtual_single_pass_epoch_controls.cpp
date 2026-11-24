// Read-contract guards for the new mode, independent of any poker sampling.
#include "../../native/virtual_sparse_strategy_epoch.hpp"
#include "../../native/virtual_dyadic_training.hpp"
#include <iostream>
namespace t=openpoker::virtual_dyadic_training;
namespace h=openpoker::virtual_dyadic_history;
namespace c=openpoker::virtual_strategy_catalog;
namespace e=openpoker::virtual_sparse_strategy_epoch;
namespace {
void require(bool value,const char* message) {if(!value)throw std::runtime_error(message);}
e::Limits limits(std::size_t reads=1) {
    e::Limits l;l.max_rows_touched=2;l.max_slots_touched=8;l.max_stage_rows=1;l.max_stage_slots=4;
    l.max_reads=2*reads;l.policy_reads_per_row=reads;l.catalog_max_public_blocks=32;l.max_work=1'000'000;return l;
}
c::Limits catalog_limits() {
    c::Limits l{32,32,128,32,2,512,5'000'000,0,0};
    l.max_metadata_entries=c::Catalog::metadata_word_forecast(l);
    l.max_metadata_payload_bits=64*l.max_metadata_entries;return l;
}
template<class F> void rejected(const char* label,e::ErrorKind expected,F&& operation) {
    try {operation();} catch(const e::Error& error) {
        require(error.kind()==expected,"single-pass guard wrong error kind");
        std::cout<<"GUARD "<<label<<" PASS\n";return;
    }
    throw std::runtime_error("single-pass guard accepted invalid operation");
}
}
int main() {
    try {
        t::betting::Template source(t::configuration(),t::template_limits());
        h::History history(source,t::chance::DeckDefinition::reduced(t::deck_cards));
        c::Catalog catalog(history,{2,2},catalog_limits());
        const auto mode=e::ArithmeticContract::weighted_joint_single_pass;
        for(const auto contract:{e::ArithmeticContract::true_joint_proof9,e::ArithmeticContract::weighted_joint_fixed_tree})
            rejected(contract==e::ArithmeticContract::true_joint_proof9?"legacy-one-read":"weighted-v1-one-read",
                e::ErrorKind::invalid_limits,[&]{e::Store invalid(catalog,history,{2,2},limits(1),contract);});
        rejected("single-mode-two-reads",e::ErrorKind::invalid_limits,[&]{e::Store invalid(catalog,history,{2,2},limits(2),mode);});
        rejected("zero-read-contract",e::ErrorKind::invalid_limits,[&]{e::Store invalid(catalog,history,{2,2},limits(0),mode);});
        const e::Integer dr=e::Integer(1)<<625,da=e::Integer(1)<<364;
        const std::array<e::Integer,4> r{5*dr,-3*dr,0,-2*dr},a{da/4,da/4,da/4,da/4};
        e::Store good(catalog,history,{2,2},limits(),mode);
        {
            auto lease=good.begin_epoch(e::ProposalLaw::true_joint);
            const auto view=lease.frozen_policy(history.root(),0,0);
            lease.seal_raw_walk(1,4,1);lease.stage(view.id,r,a,da,dr);
            require(view.units[0]==e::grid/4,"single-pass staging mutated frozen input");
        }
        good.commit();std::size_t exported=0;
        good.visit_committed([&](auto,std::span<const e::Integer> regrets,std::span<const e::Integer> averages,
                               std::span<const std::uint64_t> units) {
            require(regrets.size()==4 && averages.size()==4 && units.size()==4 && units[0]==e::grid &&
                units[1]==0 && units[2]==0 && units[3]==0,"single-pass exact committed policy");
            for(std::size_t i=0;i<4;++i) require(regrets[i]==r[i] && averages[i]==a[i],"single-pass exact numeric image");
            ++exported;
        });
        require(exported==1 && good.receipt().reads==1 && good.receipt().commits==1,"single-pass read/commit lifecycle");
        {
            e::Store owner(catalog,history,{2,2},limits(),mode);
            auto lease=owner.begin_epoch(e::ProposalLaw::true_joint);
            (void)lease.frozen_policy(history.root(),0,0);
            rejected("duplicate-read",e::ErrorKind::incomplete_walk,[&]{(void)lease.frozen_policy(history.root(),0,0);});
            require(owner.failed(),"single-pass duplicate read did not poison");
        }
        {
            e::Store owner(catalog,history,{2,2},limits(),mode);
            auto lease=owner.begin_epoch(e::ProposalLaw::true_joint);(void)lease.frozen_policy(history.root(),0,0);
            rejected("wrong-seal-read-count",e::ErrorKind::incomplete_walk,[&]{lease.seal_raw_walk(1,4,2);});
        }
        {
            e::Store owner(catalog,history,{2,2},limits(),mode);
            {auto lease=owner.begin_epoch(e::ProposalLaw::true_joint);(void)lease.frozen_policy(history.root(),0,0);lease.seal_raw_walk(1,4,1);}
            rejected("abandoned-stage",e::ErrorKind::failed_owner,[&]{owner.commit();});
        }
        {
            e::Store owner(catalog,history,{2,2},limits(2),e::ArithmeticContract::true_joint_proof9);
            auto lease=owner.begin_epoch(e::ProposalLaw::true_joint);(void)lease.frozen_policy(history.root(),0,0);
            rejected("old-mode-still-needs-two",e::ErrorKind::incomplete_walk,[&]{lease.seal_raw_walk(1,4,1);});
        }
        {
            e::Store owner(catalog,history,{2,2},limits(),mode);
            auto lease=owner.begin_epoch(e::ProposalLaw::true_joint);(void)lease.frozen_policy(history.root(),0,0);
            lease.seal_raw_walk(1,4,1);
            const auto cursor=history.root();const auto info=history.decision_key(cursor);
            std::array<std::string_view,4> actions{};history.decision_actions(cursor,actions);
            const auto unseen=catalog.resolve(history,cursor,0,1,2,info.source,actions);
            rejected("unobserved-stage-row",e::ErrorKind::row_or_menu,[&]{lease.stage(unseen,r,a,da,dr);});
        }
        {
            e::Store owner(catalog,history,{2,2},limits(),mode);
            rejected("public-proposal",e::ErrorKind::invalid_limits,[&]{(void)owner.begin_epoch(e::ProposalLaw::uniform_public);});
        }
        std::cout<<"SINGLE_PASS_EPOCH_GUARDS_V1 PASS 10 1\n";return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}
