// Architecture envelope only: no policy import, contraction, ranking or update.
#include "../../native/virtual_frozen_grid_update_forecast.hpp"
#include <iostream>
#include <sstream>

namespace t=openpoker::virtual_dyadic_training;
namespace f=openpoker::virtual_frozen_update;
namespace p=openpoker::virtual_frozen_grid_update_forecast;

int main() {
    try {
        constexpr auto own_bound=43000000ULL+3000000+5040*16384ULL+16*p::output_cap;
        constexpr auto own_entries=131072+(p::output_cap+7)/8+16384;
        constexpr auto own_payload=8*p::output_cap+(1ULL<<22)+64*19*(704+58);
        static_assert(own_bound<=t::work_cap && own_entries<=t::entries_cap && own_payload<=t::payload_cap);
        const p::b::Template source(t::configuration(),t::template_limits());p::Geometry geometry;p::census(source,source.root(),{},geometry);
        t::require(geometry.visits==1105 && geometry.depth==std::array<std::size_t,2>{6,7} && geometry.route==12 && geometry.mix_route==11,
                   "fixed route/integrality census");
        std::string output;output.reserve(p::output_cap);
        auto append=[&](const std::string& line) {
            t::require(line.size()<=2048 && line.size()<=p::output_cap-output.size(),"bounded preflight output");output+=line;
        };
        append("FROZEN_GRID_ENVELOPE_V2\n");
        std::ostringstream header;
        header<<"GEOMETRY "<<geometry.visits<<' '<<geometry.actions<<' '<<geometry.reveals<<' '<<geometry.folds<<' '<<geometry.showdowns<<' '
            <<geometry.decisions<<" 6 7 12 11\n";
        append(header.str());
        const auto& deck=t::deck_cards;std::uint64_t count=0;
        for (std::size_t a=0;a<9;++a) for (std::size_t c=a+1;c<9;++c) for (std::size_t d=c+1;d<9;++d)
            for (const auto turn:deck) for (const auto river:deck) {
                if (turn==river || turn==deck[a] || turn==deck[c] || turn==deck[d] || river==deck[a] || river==deck[c] || river==deck[d]) continue;
                const std::array<std::uint8_t,5> board{deck[a],deck[c],deck[d],turn,river};
                for (const auto law:{f::ProposalKind::uniform_public,f::ProposalKind::weighted_river_proof9}) {
                    const auto value=p::forecast(geometry,board,law);++count;
                    std::ostringstream line;line<<"F "<<(law==f::ProposalKind::uniform_public?0:1);
                    for (const auto card:board) line<<' '<<unsigned(card);
                    for (const auto x:std::array<std::uint64_t,21>{value.rows,value.slots,value.reads,value.state,value.history,value.chance,
                        value.reach,value.scale,value.mix,value.average,value.stage,value.walk,value.work,value.entries,value.payload,
                        value.output,value.stage_payload,static_cast<std::uint64_t>(value.physical),static_cast<std::uint64_t>(value.feasible),0,704}) line<<' '<<x;
                    line<<'\n';append(line.str());
                }
            }
        t::require(count==5040,"proposal forecast census");
        append("END 5040 0 0 0 0 0\n"); // policy import, rank, contraction, update, training calls
        std::cout.write(output.data(),static_cast<std::streamsize>(output.size()));return 0;
    } catch (const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}