#pragma once
// Complete fixed full52/T2 request envelope, before physical or tree preparation.
#include "virtual_opponent_role_epoch.hpp"
#include "virtual_frozen_grid_update_forecast.hpp"

namespace openpoker::virtual_opponent_role_walk_forecast {
namespace t=virtual_dyadic_training;
namespace r=virtual_opponent_role_epoch;
namespace c=virtual_strategy_catalog;
namespace g=virtual_frozen_grid_update_forecast;
inline constexpr std::uint64_t visits=367,actions=327,reveals=41,terminals=127,decisions=204,own_rows=76;
inline constexpr std::uint64_t input_cap=4096,summary_cap=16384;
inline constexpr std::uint64_t output_upper=512+2*(768+64*204+72*816+64*204)+40*612+144*2448+512;
inline constexpr std::uint64_t raw_entries=56*204+8*204+1105+64*19+64;
inline constexpr std::uint64_t raw_payload=3'140'970;
// Exact maximum for the unchanged canonical snapshot layout plus explicit
// representation header, two storage observations and extended parent footer.
inline constexpr std::uint64_t storage_wire_upper=280+48+2*(432+48*204+72*816+64*204+32+32+296+64)+
    40*612+144*2448+40;
static_assert(storage_wire_upper<=output_upper,"storage observation must fit the original output cap");
struct Raw {
    std::uint64_t scale=0,mix=0,regret=0,average=0,stage=0,walk=0;
    [[nodiscard]] std::uint64_t work() const{return scale+mix+regret+average+stage+walk;}
};
struct Forecast {
    r::Limits role_limits{};
    r::Forecast role{};
    c::Limits catalog{};
    Raw raw{};
    std::uint64_t history=0,chance=0,component=0,parent=0,work=0,entries=0,payload=0,output=output_upper;
};
inline constexpr std::uint64_t expansion_slot_work=64+t::copy_cost(631)+t::copy_cost(366);
inline Forecast domain(r::PersistentCarrier persistent=r::PersistentCarrier::canonical,bool observe_storage=false) {
    t::require((persistent==r::PersistentCarrier::canonical || persistent==r::PersistentCarrier::compact) &&
        (persistent==r::PersistentCarrier::canonical || observe_storage),"compact role requires explicit storage observation contract");
    Forecast f;f.role_limits.persistent=persistent;f.role=r::forecast(f.role_limits);
    auto& cat=f.catalog;cat.max_public_blocks=408;cat.max_information_rows_seen=408;
    cat.max_action_slots_seen=1632;cat.max_menus=408;cat.max_holding_count=1326;
    // Two Catalog calls per unique read, one validating stage, and at most
    // 204+408 exported rows. RowId reuse removes a separate staging join.
    cat.max_lookups=3*408+612;cat.max_work=c::Catalog::work_forecast(cat);
    cat.max_metadata_entries=c::Catalog::metadata_word_forecast(cat);cat.max_metadata_payload_bits=64*cat.max_metadata_entries;
    auto& x=f.raw;
    x.scale=terminals*(32+t::copy_cost(369));
    x.mix=actions*(8+t::mul_cost(369,53)+t::add_cost(423)+t::copy_cost(423))+
        own_rows*(64+t::copy_cost(423)+t::copy_cost(369)+2*t::words(423));
    x.regret=actions*(64+t::add_cost(370)+t::copy_cost(370)+512);
    x.average=decisions*(64+16*4);
    x.stage=1024+204*256+816*512;
    x.walk=512+256*visits+decisions*(256+16*4)+8*1105;
    // Existing complete History construction + both literal target routes,
    // source identity checks, raw-directory checks, and the role/Store reads.
    f.history=4096*1105+1280+2*(48*actions+80*reveals+16+8*visits+8*decisions)+
        f.role.extra_history_work+f.role.storage.history_read_work;
    using Prepared=t::prepared::PreparedPublicChance;
    f.chance=Prepared::weighted_joint_setup_work_bound(1326,1326)+2*Prepared::weighted_joint_ticket_work_bound(1326,1326);
    f.component=f.role.storage.component_work+f.role.own_work;
    f.parent=1'040'000+4096+2*x.work();
    if(observe_storage)f.parent+=2*512+3*816*64;
    if(persistent==r::PersistentCarrier::compact)f.parent+=2*512+3*816*expansion_slot_work;
    f.work=t::template_cap+cat.max_work+f.history+f.chance+f.component+f.parent+16*(f.output+input_cap);
    f.entries=131072+cat.max_metadata_entries+f.role.entries+12000+Prepared::weighted_joint_ticket_entries_bound()+
        (32*1105+1)+16384+raw_entries+f.output+4096;
    f.payload=131072*64+64*cat.max_metadata_entries+f.role.payload_bits+(1ULL<<20)+
        Prepared::weighted_joint_ticket_payload_bound()+8*(1ULL<<20)+(1ULL<<22)+raw_payload+8*f.output+4096*64+32*181;
    constexpr auto modeled_raw=64*(56*204+8*204+1105+64)+19*64*(423+256);
    t::require(modeled_raw<=raw_payload && raw_entries<=t::parent_entries && output_upper<=g::output_cap &&
        cat.max_work<=c::work_cap && f.history<=t::history_cap && f.chance<=t::chance_cap &&
        f.component<=t::state_cap && f.parent<=t::parent_cap && f.work<=t::work_cap &&
        f.entries<=t::entries_cap && f.payload<=t::payload_cap,"role walk whole request exceeds unchanged caps");
    return f;
}
inline void validate_source(const t::betting::Template& source,const g::Geometry& v) {
    const auto& q=source.receipt();
    t::require(q.nodes==388 && q.edges==410 && q.logical_occurrences==1105 && q.max_depth==15 && !q.history_suffix_only &&
        q.work<=t::template_cap && q.entries+q.peak_scratch_entries<=131072 &&
        v.visits==1105 && v.actions==1039 && v.decisions==434 && v.reveals==65 && v.folds==303 && v.showdowns==303 &&
        v.route==12 && v.mix_route==11 && v.depth==std::array<std::size_t,2>{6,7},"role walk fixed four-street source changed");
}
}
