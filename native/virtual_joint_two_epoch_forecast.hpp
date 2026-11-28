#pragma once
// Fixed N9 true-joint ticket domain: two deterministic observations, no RNG.
// Scalar resource equations run before Template/range/rank preparation.
#include "virtual_frozen_grid_update_forecast.hpp"
#include "virtual_sparse_strategy_epoch.hpp"

namespace openpoker::virtual_joint_two_epoch {
namespace t=virtual_dyadic_training;
namespace p=virtual_frozen_grid_update_forecast;
namespace e=virtual_sparse_strategy_epoch;
namespace c=virtual_strategy_catalog;
using Board=std::array<std::uint8_t,5>;
inline constexpr std::uint64_t ticket_count=580,ordered_ticket_pairs=ticket_count*ticket_count;
inline constexpr std::uint64_t output_upper=502720,setup_work=1040000,raw_stage_payload=3140970;

struct Forecast {
    p::Forecast raw{};
    c::Limits catalog{};
    e::Limits epoch{};
    e::Forecast epoch_cost{};
    std::uint64_t history=0,chance=0,parent=0,work=0,entries=0,payload=0,output=0,setup=0;
};
inline std::uint64_t raw_work(const p::Forecast& f) {
    return f.reach+f.scale+f.mix+f.average+f.stage+f.walk;
}
inline e::Limits epoch_limits() {
    e::Limits l;
    l.max_rows_touched=868;l.max_slots_touched=2078;l.max_stage_rows=434;l.max_stage_slots=1039;
    l.max_reads=1736;l.catalog_max_public_blocks=868;l.max_work=e::work_cap;
    l.max_entries=t::entries_cap;l.max_payload_bits=t::payload_cap;l.max_epochs=2;return l;
}
inline c::Limits catalog_limits() {
    c::Limits l;
    l.max_public_blocks=868;l.max_information_rows_seen=868;l.max_action_slots_seen=2078;
    l.max_menus=434;l.max_holding_count=2;l.max_lookups=6510;
    l.max_work=c::Catalog::work_forecast(l);
    l.max_metadata_entries=c::Catalog::metadata_word_forecast(l);
    l.max_metadata_payload_bits=64*l.max_metadata_entries;return l;
}
inline void check_geometry(const p::Geometry& g) {
    t::require(g.visits==1105 && g.actions==1039 && g.decisions==434 && g.reveals==65 &&
        g.folds==303 && g.showdowns==303 && g.route==12 && g.mix_route==11 &&
        g.depth==std::array<std::size_t,2>{6,7},"joint two-epoch fixed source geometry changed");
}
inline Forecast domain_forecast() {
    Forecast f;f.epoch=epoch_limits();f.epoch_cost=e::forecast(f.epoch);f.catalog=catalog_limits();
    f.setup=setup_work;f.output=output_upper;
    auto& r=f.raw;r.rows=434;r.slots=1039;r.reads=868;r.stage_payload=raw_stage_payload;
    r.reach=2*1039*(24+t::mul_cost(365,53)+t::copy_cost(365));
    r.scale=2*606*(32+t::copy_cost(629));
    r.mix=2*1039*(8+t::mul_cost(629,53)+t::add_cost(683)+t::copy_cost(683))+
        2*434*(32+t::copy_cost(683)+t::copy_cost(629))+
        1039*(64+t::add_cost(630)+t::copy_cost(630)+t::mul_cost(630,365)+t::copy_cost(630));
    r.average=434*(64+t::copy_cost(365))+
        1039*(32+t::mul_cost(313,53)+t::copy_cost(365)+2*t::words(365));
    r.stage=1024+64*434+16*1039;r.walk=512+256*1105;
    r.work=raw_work(r);r.feasible=true;
    f.history=4096*1105+1280+4*(48*1039+80*65+8)+1736*288+868*640;
    f.chance=t::chance_setup_bound+2*t::prepared::PreparedPublicChance::joint_ticket_work_bound();
    f.parent=f.setup+4096+512*868+2*r.work;
    f.work=t::template_cap+f.catalog.max_work+f.history+f.chance+f.epoch_cost.component_work+f.parent+16*f.output;
    const auto cat_words=f.catalog.max_metadata_entries;
    const auto joint_entries=t::prepared::PreparedPublicChance::joint_ticket_entries_bound();
    const auto joint_payload=t::prepared::PreparedPublicChance::joint_ticket_payload_bound();
    // One raw result at a time and a private byte buffer covering both committed
    // snapshots. Existing 12k/1,048,576-bit chance owner reservation excludes the scoped
    // certificate's explicitly added 128 entries/1024 bits. Source allowance is
    // a logical reservation, not a complete allocator or RSS measurement.
    f.entries=131072+cat_words+f.epoch_cost.entries+12000+joint_entries+(32*1105+1)+16384+
        (8*434+2*1039+64*19+64)+output_upper+4096;
    f.payload=131072*64+64*cat_words+f.epoch_cost.payload_bits+(1ULL<<20)+joint_payload+
        8*(1ULL<<20)+(1ULL<<22)+raw_stage_payload+8*output_upper+4096*64+32*181;
    t::require(f.catalog.max_work<=c::work_cap && f.epoch_cost.work<=e::work_cap &&
        f.epoch_cost.component_work<=e::work_cap && f.history<=t::history_cap && f.chance<=t::chance_cap &&
        f.parent<=t::parent_cap && f.work<=t::work_cap && f.entries<=t::entries_cap &&
        f.payload<=t::payload_cap && f.output<=p::output_cap,"joint two-epoch whole request exceeds unchanged caps");
    return f;
}
inline Forecast forecast(const t::betting::Template& source,const p::Geometry& geometry) {
    check_geometry(geometry);const auto& receipt=source.receipt();
    t::require(receipt.nodes==388 && receipt.edges==410 && receipt.logical_occurrences==1105 &&
        receipt.max_depth==15 && !receipt.history_suffix_only && receipt.work<=t::template_cap &&
        receipt.entries+receipt.peak_scratch_entries<=131072,"joint two-epoch source receipt changed");
    return domain_forecast();
}
// Same fixed betting tree and sparse update lifetime, with an explicitly
// weighted compact owner. This is a scalar envelope, not admission by itself.
inline Forecast weighted_domain_forecast(std::array<std::size_t,2> counts) {
    t::require(counts[0] && counts[1] && counts[0]<=1326 && counts[1]<=1326,
        "weighted joint declared range geometry");
    auto f=domain_forecast();
    const auto old_words=f.catalog.max_metadata_entries;
    f.catalog.max_holding_count=std::max(counts[0],counts[1]);
    f.catalog.max_work=c::Catalog::work_forecast(f.catalog);
    f.catalog.max_metadata_entries=c::Catalog::metadata_word_forecast(f.catalog);
    f.catalog.max_metadata_payload_bits=64*f.catalog.max_metadata_entries;
    f.epoch.catalog_max_holding_count=f.catalog.max_holding_count;
    f.epoch_cost=e::forecast(f.epoch);
    f.raw.walk+=128*2*1105;f.raw.work=raw_work(f.raw);
    using Prepared=t::prepared::PreparedPublicChance;
    f.chance=Prepared::weighted_joint_setup_work_bound(counts[0],counts[1])+
        2*Prepared::weighted_joint_ticket_work_bound(counts[0],counts[1]);
    const auto chance_entries=Prepared::weighted_joint_owner_entries_bound(counts[0],counts[1])+
        Prepared::weighted_joint_ticket_entries_bound();
    const auto chance_payload=Prepared::weighted_joint_owner_payload_bound(counts[0],counts[1])+
        Prepared::weighted_joint_ticket_payload_bound();
    t::require(chance_entries<=t::chance_entries && chance_payload<=t::chance_payload,
        "weighted joint chance does not fit unchanged owner caps");
    // Four extra header words name deck/profile/original holding counts.
    f.output+=32;
    f.parent=f.setup+4096+512*868+2*f.raw.work;
    f.work=t::template_cap+f.catalog.max_work+f.history+f.chance+f.epoch_cost.component_work+f.parent+16*f.output;
    f.entries+=f.catalog.max_metadata_entries-old_words+
        Prepared::weighted_joint_ticket_entries_bound()-Prepared::joint_ticket_entries_bound()+32;
    f.payload+=64*(f.catalog.max_metadata_entries-old_words)+
        Prepared::weighted_joint_ticket_payload_bound()-Prepared::joint_ticket_payload_bound()+8*32;
    // The existing16,384-entry/2^22-bit caller-source allowance also covers
    // both full explicit input ranges (3*2652 entries and80*2652 bits), plus
    // bounded construction temporaries. No second full range copy in Prepared.
    t::require(3*(counts[0]+counts[1])+256<=16384 &&
        80*(counts[0]+counts[1])+8192<=(1ULL<<22) &&
        f.catalog.max_work<=c::work_cap && f.epoch_cost.work<=e::work_cap &&
        f.history<=t::history_cap && f.chance<=t::chance_cap && f.parent<=t::parent_cap &&
        f.work<=t::work_cap && f.entries<=t::entries_cap && f.payload<=t::payload_cap && f.output<=p::output_cap,
        "weighted joint complete request exceeds unchanged caps");
    return f;
}
inline Forecast single_pass_domain_forecast(std::array<std::size_t,2> counts) {
    auto f=weighted_domain_forecast(counts);
    f.epoch.policy_reads_per_row=1;f.epoch.max_reads=868;
    f.epoch_cost=e::forecast(f.epoch);
    // Two Catalog operations per frozen read, join+stage per complete row,
    // and cumulative exports of at most434+868 rows.
    f.catalog.max_lookups=2*f.epoch.max_reads+2*868+1302;
    f.catalog.max_work=c::Catalog::work_forecast(f.catalog);
    auto& r=f.raw;r.reads=434;r.reach/=2;r.scale/=2;
    r.mix=1039*(8+t::mul_cost(629,53)+t::add_cost(683)+t::copy_cost(683))+
        434*(32+t::copy_cost(683)+t::copy_cost(629))+
        1039*(64+t::add_cost(630)+t::copy_cost(630)+t::mul_cost(630,365)+t::copy_cost(630));
    r.walk=512+256*1105;r.work=raw_work(r);
    f.history=4096*1105+1280+2*(48*1039+80*65+8)+868*288+868*640;
    f.parent=f.setup+4096+512*868+2*r.work;
    f.work=t::template_cap+f.catalog.max_work+f.history+f.chance+f.epoch_cost.component_work+f.parent+16*f.output;
    t::require(f.catalog.max_work<=c::work_cap && f.epoch_cost.work<=e::work_cap && f.history<=t::history_cap &&
        f.chance<=t::chance_cap && f.parent<=t::parent_cap && f.work<=t::work_cap && f.entries<=t::entries_cap &&
        f.payload<=t::payload_cap && f.output<=p::output_cap,"single-pass joint request exceeds unchanged caps");
    return f;
}
inline Forecast single_pass_lazy_domain_forecast(std::array<std::size_t,2> counts) {
    auto f=single_pass_domain_forecast(counts);
    const auto old_words=f.catalog.max_metadata_entries;
    f.catalog.seen_storage=c::Limits::SeenStorage::first_holding_inline;
    f.catalog.max_work=c::Catalog::work_forecast(f.catalog);
    f.catalog.max_metadata_entries=c::Catalog::metadata_word_forecast(f.catalog);
    f.catalog.max_metadata_payload_bits=64*f.catalog.max_metadata_entries;
    f.epoch.catalog_seen_storage=f.catalog.seen_storage;
    f.epoch_cost=e::forecast(f.epoch);
    t::require(f.catalog.max_metadata_entries<=old_words,"lazy Catalog metadata reservation increased");
    const auto removed_words=old_words-f.catalog.max_metadata_entries;
    // Two trailing words preserve observed bitmap and occupied-ledger peaks.
    f.output+=16;f.entries=f.entries-removed_words+16;f.payload=f.payload-64*removed_words+128;
    f.work=t::template_cap+f.catalog.max_work+f.history+f.chance+f.epoch_cost.component_work+f.parent+16*f.output;
    t::require(f.catalog.max_work<=c::work_cap && f.epoch_cost.work<=e::work_cap &&
        f.history<=t::history_cap && f.chance<=t::chance_cap && f.parent<=t::parent_cap &&
        f.work<=t::work_cap && f.entries<=t::entries_cap && f.payload<=t::payload_cap && f.output<=p::output_cap,
        "lazy Catalog single-pass request exceeds unchanged caps");
    return f;
}
} // namespace openpoker::virtual_joint_two_epoch
