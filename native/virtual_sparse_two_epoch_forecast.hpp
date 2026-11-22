#pragma once
// Whole-request logical reservation for exactly two uniform PROOF9 epochs.
// The source allocation allowance is a logical model, not an allocator/RSS census.
#include "virtual_frozen_grid_update_forecast.hpp"
#include "virtual_sparse_strategy_epoch.hpp"

namespace openpoker::virtual_sparse_two_epoch {
namespace t=virtual_dyadic_training;
namespace p=virtual_frozen_grid_update_forecast;
namespace e=virtual_sparse_strategy_epoch;
namespace c=virtual_strategy_catalog;
namespace proposal=virtual_frozen_update;
using Board=std::array<std::uint8_t,5>;
inline constexpr std::uint64_t max_rows=530,max_slots=1282;
inline constexpr std::uint64_t output_upper=619152,setup_work=1040000;
inline constexpr std::uint64_t raw_stage_payload=3140970;

struct Forecast {
    std::array<p::Forecast,2> boards{};
    c::Limits catalog{};
    e::Limits epoch{};
    e::Forecast epoch_cost{};
    std::uint64_t history=0,chance=0,parent=0,work=0,entries=0,payload=0,output=0,setup=0;
};

inline e::Limits epoch_limits() {
    e::Limits l;
    l.max_rows_touched=1060;l.max_slots_touched=2564;
    l.max_stage_rows=530;l.max_stage_slots=1282;l.max_reads=2120;
    l.catalog_max_public_blocks=1060;l.max_work=e::work_cap;
    l.max_entries=t::entries_cap;l.max_payload_bits=t::payload_cap;l.max_epochs=2;
    return l;
}
inline c::Limits catalog_limits() {
    c::Limits l;
    l.max_public_blocks=1060;l.max_information_rows_seen=1060;l.max_action_slots_seen=2564;
    l.max_menus=434;l.max_holding_count=2;l.max_lookups=7950;
    l.max_work=c::work_forecast(l);
    l.max_metadata_entries=c::metadata_word_forecast(l);
    l.max_metadata_payload_bits=64*l.max_metadata_entries;
    return l;
}
inline std::uint64_t raw_work(const p::Forecast& f) {
    return f.reach+f.scale+f.mix+f.average+f.stage+f.walk;
}
inline void check_geometry(const p::Geometry& g) {
    t::require(g.visits==1105 && g.actions==1039 && g.reveals==65 &&
        g.folds==303 && g.showdowns==303 && g.decisions==434 &&
        g.depth==std::array<std::size_t,2>{6,7} && g.route==12 && g.mix_route==11,
        "sparse epoch fixed source census changed");
}
inline void check(const Forecast& f) {
    t::require(f.work<=t::work_cap && f.history<=t::history_cap && f.chance<=t::chance_cap &&
        f.parent<=t::parent_cap && f.catalog.max_work<=c::work_cap &&
        f.epoch_cost.work<=e::work_cap && f.epoch_cost.component_work<=e::work_cap &&
        f.entries<=t::entries_cap && f.payload<=t::payload_cap && f.output<=p::output_cap,
        "sparse epoch whole-request reservation exceeds unchanged caps");
}
inline Forecast compose(std::array<p::Forecast,2> boards) {
    Forecast f;f.boards=std::move(boards);f.epoch=epoch_limits();f.epoch_cost=e::forecast(f.epoch);
    f.catalog=catalog_limits();f.setup=setup_work;f.output=output_upper;
    f.history=4096*1105+1280+2*(2*(48*1039+80*65+8))+2120*288+1060*640;
    f.chance=t::chance_setup_bound;f.parent=f.setup+4096+512*1060;
    for (const auto& board:f.boards) {
        t::require(board.rows<=max_rows && board.slots<=max_slots &&
            board.chance>=t::chance_setup_bound && board.stage_payload<=raw_stage_payload,
            "sparse epoch board exceeds fixed domain");
        f.chance+=board.chance-t::chance_setup_bound;f.parent+=raw_work(board);
    }
    f.work=t::template_cap+f.catalog.max_work+f.history+f.chance+
        f.epoch_cost.component_work+f.parent+16*f.output;
    const auto cat_words=f.catalog.max_metadata_entries;
    f.entries=131072+cat_words+f.epoch_cost.entries+12000+(32*1105+1)+16384+
        (8*530+2*1282+64*19+64)+output_upper+4096;
    f.payload=131072*64+64*cat_words+f.epoch_cost.payload_bits+(1ULL<<20)+
        8*(1ULL<<20)+(1ULL<<22)+raw_stage_payload+8*output_upper+4096*64+32*181;
    check(f);return f;
}

// Before source construction, bound every legal pair of selectors. At a
// five-card board only four of the nine deck cards remain. All four original
// holdings together use six cards, so (two unblocked,two unblocked) is
// impossible. Maximizing the two target costs over a+b<=3 bounds terminals;
// the earlier prefix marginals retain the full two-by-two bound.
inline Forecast domain_forecast() {
    constexpr auto all_hands=t::hand_masks[0][0]|t::hand_masks[0][1]|t::hand_masks[1][0]|t::hand_masks[1][1];
    static_assert(std::popcount(all_hands)==6);
    std::uint64_t terminal=0;
    for (std::size_t a=0;a<=2;++a) for (std::size_t b=0;b<=2;++b) if (a+b<=3) {
        const auto cost=303*(p::contraction_cost(false,a,b)+p::contraction_cost(false,b,a)+
            p::contraction_cost(true,a,b)+p::contraction_cost(true,b,a));
        terminal=std::max(terminal,cost);
    }
    p::Forecast board;board.rows=max_rows;board.slots=max_slots;board.stage_payload=raw_stage_payload;
    board.chance=t::chance_setup_bound+terminal+4*4096+512+64+4*64+8*p::contraction_cost(false,2,2);
    board.reach=2*1039*(24+2*(t::mul_cost(365,53)+t::copy_cost(365)));
    board.scale=4*606*(32+t::mul_cost(378,4)+t::mul_cost(382,14)+t::copy_cost(647)+2*t::words(699));
    board.mix=4*1039*(8+t::mul_cost(647,53)+t::add_cost(699)+t::copy_cost(699))+
        max_slots*(8+t::add_cost(648)+t::copy_cost(648))+4*434*(t::copy_cost(699)+t::copy_cost(648));
    board.average=max_rows*(64+t::mul_cost(5,14)+t::mul_cost(313,19)+t::copy_cost(381)+t::copy_cost(383))+
        max_slots*(16+t::mul_cost(332,53)+t::copy_cost(383));
    board.stage=1024+64*max_rows+16*max_slots;board.walk=512+256*1105;
    return compose({board,board});
}
inline Forecast forecast(const p::Geometry& g,const std::array<Board,2>& boards) {
    check_geometry(g);
    const auto f=compose({p::forecast(g,boards[0],proposal::ProposalKind::uniform_public),
                          p::forecast(g,boards[1],proposal::ProposalKind::uniform_public)});
    auto domain=domain_forecast();
    t::require(f.work<=domain.work && f.chance<=domain.chance && f.parent<=domain.parent &&
        f.entries==domain.entries && f.payload==domain.payload,"sparse epoch pair exceeds pre-source domain");
    for (const auto& board:f.boards) t::require(board.feasible,"sparse epoch raw board admission rejected");
    // Publish the independently bounded complete selector domain, while the
    // reused raw kernel still receives the concrete selector's six families.
    domain.boards=f.boards;return domain;
}
} // namespace openpoker::virtual_sparse_two_epoch
