#pragma once
// Two-board fixed-policy session envelope. Forecast only; no producer calls.
#include "virtual_frozen_grid_update_forecast.hpp"

namespace openpoker::virtual_frozen_policy_session {
namespace t=virtual_dyadic_training;
namespace p=virtual_frozen_grid_update_forecast;
namespace s=virtual_dyadic_state;
namespace proposal=virtual_frozen_update;

inline constexpr std::size_t session_boards=2;
inline constexpr std::uint64_t geometry_work=1'040'000;
inline constexpr std::uint64_t old_forecast_geometry_work=149'420;
inline constexpr std::uint64_t session_metadata_work=1'024;
inline constexpr std::uint64_t session_metadata_entries=512;
inline constexpr std::uint64_t session_metadata_payload_bits=4'096;
inline constexpr std::uint64_t session_output_header_bytes=136;
inline constexpr std::uint64_t policy_body_bytes=1'442'112;
inline constexpr std::uint64_t session_footer_bytes=208;
inline constexpr std::uint64_t board_record_fixed_bytes=728;
static_assert(geometry_work+old_forecast_geometry_work<=3'000'000,
              "shared selector census exceeds the original geometry family");
inline constexpr std::uint64_t domain_work=316'294'067;
inline constexpr std::uint64_t domain_history=39'784'400;
inline constexpr std::uint64_t domain_state=55'075'516;
inline constexpr std::uint64_t domain_chance=2'579'498;
inline constexpr std::uint64_t domain_parent=8'209'324;
inline constexpr std::uint64_t domain_entries=1'184'881;
inline constexpr std::uint64_t domain_payload=263'169'724;
inline constexpr std::uint64_t domain_output=1'936'776;
inline constexpr std::uint64_t domain_stage_payload=6'281'940;
static_assert(domain_work<=t::work_cap && domain_history<=t::history_cap &&
              domain_state<=t::state_cap && domain_chance<=t::chance_cap &&
              domain_parent<=t::parent_cap && domain_entries<=t::entries_cap &&
              domain_payload<=t::payload_cap && domain_output<=p::output_cap,
              "two-board source-derived domain exceeds a retained ceiling");

struct Selector {
    std::array<std::uint8_t,5> board{};
    proposal::ProposalKind law=proposal::ProposalKind::uniform_public;
};

struct Forecast {
    std::array<p::Forecast,session_boards> boards{};
    std::uint64_t reads=0,state=0,history=0,chance=0,parent=0;
    std::uint64_t work=0,entries=0,payload=0,output=0,stage_payload=0;
    bool feasible=false;
};

inline constexpr std::uint64_t plus(std::uint64_t a,std::uint64_t b) {
    return a+b;
}
inline constexpr std::uint64_t times(std::uint64_t a,std::uint64_t b) {
    return a*b;
}

inline Forecast forecast(const p::Geometry& geometry,const std::array<Selector,session_boards>& selectors) {
    Forecast result;
    for (std::size_t i=0;i<session_boards;++i)
        result.boards[i]=p::forecast(geometry,selectors[i].board,selectors[i].law);

    constexpr std::uint64_t rows=24420,slots=58164,history_tokens=249662;
    const auto& dense=t::proof9.shape;
    const auto catalog=3000000+8*dense.visits+64*dense.candidates+16*rows+4*slots;
    const s::Forecast state_shape{24420,58164,1,15,648,1,1};
    const auto read_shape=s::State::frozen_policy_forecast(state_shape,1);
    result.reads=rows+2*(result.boards[0].rows+result.boards[1].rows);

    const auto state_prefix=1024+8*rows+16*slots+4*11+rows*(128+16*t::logceil(rows+1))+
        256*slots+read_shape.import_work;
    result.state=state_prefix+read_shape.read_work*result.reads;

    const auto history_prefix=4096*t::literal_count+1280+40*dense.actions+72*dense.reveals+
        48*dense.visits+40*rows+8*rows+72*history_tokens+
        (56*rows+16*slots)+288*rows;
    const auto raw_history=2*(48*geometry.actions+80*geometry.reveals+8);
    result.history=history_prefix+40*result.reads+2*raw_history;

    result.chance=t::chance_setup_bound;
    for (const auto& board:result.boards) {
        t::require(board.chance>=t::chance_setup_bound,"session board chance below shared setup");
        result.chance+=board.chance-t::chance_setup_bound;
    }

    result.parent=catalog+session_metadata_work;
    for (const auto& board:result.boards) {
        const auto raw_parent=board.reach+board.scale+board.mix+board.average+board.stage+board.walk;
        result.parent+=raw_parent;
        result.stage_payload+=board.stage_payload;
    }

    const auto storage=s::State::storage_forecast(state_shape,{388,410,false});
    const auto entries_base=storage.entries+131072+(32*t::literal_count+1)+t::chance_entries+t::parent_entries;
    result.entries=entries_base+session_metadata_entries;
    const auto payload_base=storage.payload_bits+t::chance_payload+8*t::history_bytes+t::parent_payload+
        32*181+8*16384;
    result.payload=payload_base+session_metadata_payload_bits;
    result.output=session_output_header_bytes+policy_body_bytes+session_footer_bytes;
    for (const auto& board:result.boards) {
        result.entries+=8*board.rows+2*board.slots+64*19+64;
        result.payload+=board.stage_payload;
        result.output+=board_record_fixed_bytes+136*(board.rows+board.slots);
    }
    result.work=t::template_cap+result.chance+result.history+result.state+1+result.parent+
        16*p::input_cap+16*p::output_cap;
    result.feasible=result.work<=t::work_cap && result.history<=t::history_cap &&
        result.state+1<=t::state_cap && result.chance<=t::chance_cap &&
        result.parent<=t::parent_cap && result.entries<=t::entries_cap &&
        result.payload<=t::payload_cap && result.output<=p::output_cap &&
        result.boards[0].feasible && result.boards[1].feasible;
    return result;
}
} // namespace openpoker::virtual_frozen_policy_session
