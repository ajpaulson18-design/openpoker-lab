#pragma once
// Reusable fixed PROOF9 frozen-grid preflight geometry and resource forecast.
// This header admits an architecture envelope only; it performs no policy
// import, prepared contraction, ranking, update, or training.
#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include "virtual_dyadic_training.hpp"
#include "virtual_frozen_proposal.hpp"

namespace openpoker::virtual_frozen_grid_update_forecast {
namespace t=openpoker::virtual_dyadic_training;
namespace b=t::betting;
namespace s=t::state;
namespace f=openpoker::virtual_frozen_update;

inline constexpr std::uint64_t input_cap=8ULL<<20,output_cap=2100000;

struct Geometry {
    std::uint64_t visits=0,actions=0,reveals=0,folds=0,showdowns=0,decisions=0;
    std::array<std::array<std::uint64_t,2>,4> rows{},slots{};
    std::array<std::size_t,2> depth{};
    std::size_t route=0,mix_route=0;
};

inline std::size_t suffix(const b::Template& source,std::size_t id) {
    const auto& node=source.nodes().at(id);std::size_t result=0;
    for (const auto& edge:node.edges) {
        const auto child=suffix(source,edge.child);
        result=std::max(result,child);
    }
    if (node.state.phase==b::Phase::decision) ++result;
    return result;
}

inline void census(const b::Template& source,std::size_t id,std::array<std::size_t,2> past,Geometry& g) {
    t::require(++g.visits<=t::literal_count,"literal occurrence cap");
    const auto& node=source.nodes().at(id);const auto phase=node.state.phase;
    if (phase==b::Phase::decision) {
        const auto actor=node.state.actor;
        const auto k=t::street_index(node.state.street);
        t::require(actor<2 && node.edges.size()>=2 && node.edges.size()<=4,"fixed legal menu");
        ++g.decisions;++g.rows[k][actor];g.slots[k][actor]+=node.edges.size();g.actions+=node.edges.size();
        // Opponent reach includes its future decisions as well as its past.
        for (const auto& edge:node.edges) g.mix_route=std::max(g.mix_route,past[1-actor]+suffix(source,edge.child));
        ++past[actor];g.depth[actor]=std::max(g.depth[actor],past[actor]);g.route=std::max(g.route,past[0]+past[1]);
    } else if (phase==b::Phase::reveal) ++g.reveals;
    else if (phase==b::Phase::fold) ++g.folds;
    else {t::require(phase==b::Phase::showdown,"fixed phase");++g.showdowns;}
    for (const auto& edge:node.edges) census(source,edge.child,past,g);
}

inline std::uint64_t contraction_cost(bool showdown,std::size_t own,std::size_t opposite) {
    // Same existing logical word ledger and Prepared blocker-bucket algorithm.
    // Both stored ranges contain two rows, even if board-blocked.
    constexpr std::size_t reach=365;
    const auto bucket=own && opposite?4+reach+t::logceil(opposite)+4:1;
    const auto out=own && opposite?4+bucket:1;
    auto cost=12+(6+5)+2*(4+2*t::words(reach))+4+12;
    if (own && opposite) {
        cost+=opposite*t::mul_cost(4,reach)+53*(showdown?2+own:1);
        cost+=(showdown?9:3)*opposite*t::add_cost(bucket);
        cost+=own*((showdown?12:3)*t::add_cost(bucket)+t::mul_cost(4,bucket)+t::copy_cost(out)+2*t::words(bucket));
        cost+=128;
    }
    return cost+(showdown?6*64:0); // full old 64-plane lookup bound
}

struct Forecast {
    std::uint64_t rows=0,slots=0,reads=0,state=0,history=0,chance=0,reach=0,scale=0,mix=0,average=0,stage=0,walk=0;
    std::uint64_t work=0,entries=0,payload=0,output=0,stage_payload=0;
    bool physical=false,feasible=false;
};

inline Forecast forecast(const Geometry& g,const std::array<std::uint8_t,5>& board,f::ProposalKind proposal) {
    Forecast result;const auto law=f::proposal_for(t::chance::DeckDefinition::reduced(t::deck_cards),board,proposal);
    t::require(law.board.numerator && law.board.denominator<=12600,"fixed proposal bounds");
    std::uint64_t mask=0;std::array<unsigned,2> unblocked{};
    for (std::size_t k=0;k<4;++k) {
        const auto length=k?k+2:0;
        mask=0;for (std::size_t i=0;i<length;++i) mask|=std::uint64_t{1}<<board[i];
        const auto support=t::physical_support(mask);
        for (std::size_t p=0;p<2;++p) {
            const auto count=std::popcount(support[p]);result.rows+=g.rows[k][p]*count;result.slots+=g.slots[k][p]*count;
        }
        if (k==3) result.physical=bool(support[0]);
    }
    for (std::size_t p=0;p<2;++p) for (const auto hand:t::hand_masks[p]) unblocked[p]+=!(hand&mask);
    result.reads=24420+2*result.rows; // retained full readback + both value passes
    s::Forecast sf{24420,58164,1,15,648,1,1};
    const auto component=s::State::frozen_policy_forecast(sf,result.reads);
    result.state=1024+8*24420+16*58164+4*11+24420*(128+16*t::logceil(24421))+256*58164+
        component.import_work+component.read_work;
    sf.own_work=result.state;
    const auto& dense=t::proof9.shape;
    result.history=4096*t::literal_count+1280+40*dense.actions+72*dense.reveals+48*dense.visits+40*dense.rows+
        8*24420+72*249662+component.history_work+288*24420+2*(48*g.actions+80*g.reveals+8);
    result.chance=t::chance_setup_bound;
    for (std::size_t p=0;p<2;++p) result.chance+=g.folds*contraction_cost(false,unblocked[p],unblocked[1-p])+
        g.showdowns*contraction_cost(true,unblocked[p],unblocked[1-p]);
    // One complete-board plane is sufficient. Reserve all four rank calls,
    // both range sorts, fill and all input/cache inspections regardless of mass.
    result.chance+=4*4096+512+64+4*64;
    // Four visible prefixes, both actors: unit-reach fold contractions own
    // the raw marginal masses/divisors needed by averages. Reuse the full
    // two-by-two 365-bit query bound, conservatively also covering e=0.
    result.chance+=8*contraction_cost(false,2,2);
    result.reach=2*g.actions*(24+2*(t::mul_cost(365,53)+t::copy_cost(365)));
    result.scale=4*(g.folds+g.showdowns)*(32+t::mul_cost(378,4)+t::mul_cost(382,14)+t::copy_cost(647)+2*t::words(699));
    result.mix=4*g.actions*(8+t::mul_cost(647,53)+t::add_cost(699)+t::copy_cost(699))+
        result.slots*(8+t::add_cost(648)+t::copy_cost(648))+4*g.decisions*(t::copy_cost(699)+t::copy_cost(648));
    result.average=result.rows*(64+t::mul_cost(5,14)+t::mul_cost(313,19)+t::copy_cost(381)+t::copy_cost(383))+
        result.slots*(16+t::mul_cost(332,53)+t::copy_cost(383));
    result.stage=1024+64*result.rows+16*result.slots; // includes marginal copy/identity validation
    result.walk=512+256*g.visits;
    const auto catalog=3000000+8*dense.visits+64*dense.candidates+16*dense.rows+4*dense.slots;
    const auto parent=catalog+result.reach+result.scale+result.mix+result.average+result.stage+result.walk;
    result.work=t::template_cap+result.chance+result.history+result.state+1+parent+16*input_cap+16*output_cap;
    const auto storage=s::State::storage_forecast(sf,{388,410,false});
    result.entries=storage.entries+131072+(32*t::literal_count+1)+t::chance_entries+t::parent_entries+
        8*result.rows+2*result.slots+64*19+64;
    result.stage_payload=result.rows*(2*(383+58)+512)+result.slots*((648+58)+(383+58))+64*19*(704+58)+16*(5+58)+4096;
    result.payload=storage.payload_bits+t::chance_payload+8*t::history_bytes+t::parent_payload+32*181+8*16384+result.stage_payload;
    // Candidate fixed-width row image: 5 words, mass/denominator 48 bytes
    // each, signed two's-complement regret 88 and average numerator 48 per
    // slot. The 648-bit regret magnitude plus sign fits 704 bits. This wire is a
    // reservation design, not an implemented raw-update protocol.
    result.output=1442320+256+88+2*88+136*result.rows+136*result.slots;
    result.feasible=result.work<=t::work_cap && result.history<=t::history_cap && result.state+1<=t::state_cap &&
        result.chance<=t::chance_cap && parent<=t::parent_cap && result.entries<=t::entries_cap && result.payload<=t::payload_cap && result.output<=output_cap;
    return result;
}
} // namespace openpoker::virtual_frozen_grid_update_forecast
