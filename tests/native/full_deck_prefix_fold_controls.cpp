// Fixed, bounded component fixtures; not a sampler or a training protocol.
#include "../../native/full_deck_public_chance.hpp"
#include <array>
#include <bit>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>

namespace chance = openpoker::full_deck_public_chance;
using chance::Integer;
namespace {
const std::array<std::uint8_t, 9> deck{16,17,24,32,33,35,37,43,48};
const std::array<chance::WeightedHand,2> sb{{
    {{43,48},std::bit_cast<std::uint64_t>(0.125)},
    {{32,43},std::bit_cast<std::uint64_t>(0.75)}}};
const std::array<chance::WeightedHand,2> bb{{
    {{24,37},std::bit_cast<std::uint64_t>(0.375)},
    {{16,32},std::bit_cast<std::uint64_t>(1.0)}}};
struct Reach { std::array<Integer,2> numerator{}; Integer denominator=1; };
Reach reach_case(int id) {
    Reach r;
    if (id==0) { r.denominator=4; r.numerator={1,3}; }
    else if (id==1) {
        const Integer a=(Integer(1)<<53)-1, b=(Integer(1)<<52)+1;
        r.denominator=Integer(1)<<159;
        r.numerator[0]=(a*a)<<53; r.numerator[1]=b*b*b;
    } else if (id==2) {
        r.denominator=((Integer(1)<<89)-1)*((Integer(1)<<83)-1);
        r.numerator[0]=r.denominator/3+1; r.numerator[1]=r.denominator-7;
    } else if (id==3) { r.denominator=(Integer(1)<<300)+7; }
    else if (id==4) { r.denominator=Integer(1)<<2200; r.numerator={1,3}; }
    else if (id==5) { r.numerator={1,1}; }
    else throw std::runtime_error("unknown fixed reach case");
    return r;
}
std::string hex(const Integer& value) {
    if (value<0) {
        const Integer magnitude=-value;
        return "-"+magnitude.str(0,std::ios_base::hex);
    }
    return value.str(0,std::ios_base::hex);
}
int digit(const char* value,int maximum) {
    if (!value[0] || value[1] || value[0]<'0' || value[0]>'0'+maximum)
        throw std::runtime_error("bounded fixed fixture selector required");
    return value[0]-'0';
}
bool guard(const char* name,Reach r,chance::Limits limits,chance::ErrorCode expected,
           std::span<const std::uint8_t> board, std::size_t player=0,
           double payoff=-1.25,std::size_t count=2,bool full_api=false) {
    chance::PublicChanceKernel kernel(sb,bb,chance::DeckDefinition::reduced(deck),limits);
    try {
        const auto reach=std::span<const Integer>(r.numerator.data(),count);
        if (full_api) (void)kernel.terminal_exact_reach(player,board,chance::TerminalKind::fold,
            payoff,reach,r.denominator,Integer(1),Integer(1));
        else (void)kernel.fold_prefix_exact_reach(player,board,payoff,reach,r.denominator);
    } catch (const chance::KernelError& error) {
        const auto& receipt=kernel.receipt();
        const bool ok=error.code()==expected && receipt.rank_calls==0 &&
            receipt.terminal_queries==0 && receipt.prefix_queries==0;
        std::cout<<"GUARD "<<name<<' '<<(ok ? "PASS" : "FAIL")<<' '
                 <<receipt.modeled_work<<' '<<receipt.rank_calls<<' '<<receipt.terminal_queries<<'\n';
        return ok;
    }
    std::cout<<"GUARD "<<name<<" FAIL no_error\n";
    return false;
}
int guards() {
    bool ok=true;
    const auto ordinary=reach_case(0);
    const std::array<std::uint8_t,5> full{16,17,24,32,33};
    const std::array<std::uint8_t,3> flop{16,17,24}, unsorted{17,16,24},
        duplicate{16,16,24}, foreign{16,17,18}, outside{16,17,52};
    const std::array<std::uint8_t,2> short_board{16,17};
    const std::array<std::uint8_t,4> repeat_turn{16,17,24,16};
    const std::array<std::uint8_t,5> repeat_river{16,17,24,32,32};
    const std::array<std::uint8_t,6> long_board{16,17,24,32,33,35};
    auto r=ordinary; r.numerator[0]=-1;
    ok=guard("negative_blocked_reach",r,{},chance::ErrorCode::invalid_query,flop)&&ok;
    r=ordinary; r.numerator[0]=5;
    ok=guard("above_one_blocked_reach",r,{},chance::ErrorCode::invalid_query,flop)&&ok;
    r=ordinary; r.numerator[1]=-1;
    ok=guard("late_negative_blocked_reach",r,{},chance::ErrorCode::invalid_query,full)&&ok;
    r=ordinary; r.denominator=0;
    ok=guard("zero_reach_denominator",r,{},chance::ErrorCode::invalid_query,flop)&&ok;
    r.denominator=-4;
    ok=guard("negative_reach_denominator",r,{},chance::ErrorCode::invalid_query,flop)&&ok;
    ok=guard("foreign_player",ordinary,{},chance::ErrorCode::invalid_query,flop,2)&&ok;
    ok=guard("wrong_reach_count",ordinary,{},chance::ErrorCode::invalid_query,flop,0,-1.25,1)&&ok;
    ok=guard("short_prefix",ordinary,{},chance::ErrorCode::invalid_query,short_board)&&ok;
    ok=guard("long_prefix",ordinary,{},chance::ErrorCode::invalid_query,long_board)&&ok;
    ok=guard("unsorted_flop",ordinary,{},chance::ErrorCode::invalid_query,unsorted)&&ok;
    ok=guard("duplicate_flop",ordinary,{},chance::ErrorCode::invalid_query,duplicate)&&ok;
    ok=guard("foreign_card",ordinary,{},chance::ErrorCode::invalid_query,foreign)&&ok;
    ok=guard("outside_card",ordinary,{},chance::ErrorCode::invalid_query,outside)&&ok;
    ok=guard("repeated_turn",ordinary,{},chance::ErrorCode::invalid_query,repeat_turn)&&ok;
    ok=guard("repeated_river",ordinary,{},chance::ErrorCode::invalid_query,repeat_river)&&ok;
    ok=guard("full_api_still_requires_five",ordinary,{},chance::ErrorCode::invalid_query,flop,0,-1.25,2,true)&&ok;
    ok=guard("nonfinite_payoff",ordinary,{},chance::ErrorCode::invalid_dyadic,flop,0,
        std::numeric_limits<double>::infinity())&&ok;
    auto limits=chance::Limits{}; limits.max_integer_bits=128;
    ok=guard("output_width",ordinary,limits,chance::ErrorCode::integer_bit_limit,flop)&&ok;
    r=ordinary; r.denominator=Integer(1)<<130;
    ok=guard("input_width",r,limits,chance::ErrorCode::integer_bit_limit,flop)&&ok;
    r=ordinary; r.numerator[0]=Integer(1)<<130;
    ok=guard("blocked_input_width",r,limits,chance::ErrorCode::integer_bit_limit,flop)&&ok;
    limits=chance::Limits{}; limits.max_integer_payload_bits=70000;
    ok=guard("query_payload",ordinary,limits,chance::ErrorCode::integer_payload_limit,flop)&&ok;
    limits=chance::Limits{}; limits.max_modeled_work=30000;
    ok=guard("query_work",ordinary,limits,chance::ErrorCode::modeled_work_limit,flop)&&ok;
    return ok ? 0 : 1;
}
int support() {
    chance::PublicChanceKernel kernel(sb,bb,chance::DeckDefinition::reduced(deck));
    const std::array<std::uint8_t,0> empty{};
    const auto physical=kernel.prefix(empty);
    const auto zero=reach_case(3);
    const auto value=kernel.fold_prefix_exact_reach(0,empty,-1.25,zero.numerator,zero.denominator);
    bool ok=physical.total_numerator>0 && physical.physical_support[0][0] &&
        physical.physical_support[0][1] && value.numerators[0]==0 && value.numerators[1]==0 &&
        kernel.receipt().rank_calls==0 && kernel.receipt().prefix_queries==1 &&
        kernel.receipt().terminal_queries==1;
    std::cout<<"PHYSICAL_SUPPORT_WITH_ZERO_REACH "<<(ok ? "PASS" : "FAIL")<<'\n';
    return ok ? 0 : 1;
}
} // namespace

int main(int argc,char** argv) {
    try {
        if (argc==2 && std::string(argv[1])=="guards") return guards();
        if (argc==2 && std::string(argv[1])=="support") return support();
        if (argc!=4) throw std::runtime_error("three fixed fixture selectors required");
        const int profile=digit(argv[1],5), player=digit(argv[2],1), mode=digit(argv[3],3);
        const auto reach=reach_case(profile);
        const double payoff=mode==0 ? -0.75 : mode==1 ? 2.5 : mode==2 ? 0.0 : 0x1p200;
        std::size_t index=0,bytes=0;
        std::uint64_t total_work=0;
        std::cout<<"PREFIX_FOLD_CASES_V1 "<<profile<<' '<<player<<' '<<mode<<'\n';
        auto emit=[&](std::span<const std::uint8_t> board) {
            // Each record has an independent bounded component owner. This is
            // neither a reset cumulative learning owner nor training admission.
            chance::PublicChanceKernel kernel(sb,bb,chance::DeckDefinition::reduced(deck));
            const auto value=kernel.fold_prefix_exact_reach(static_cast<std::size_t>(player),board,
                payoff,reach.numerator,reach.denominator);
            const auto& receipt=kernel.receipt();
            if (receipt.rank_calls!=0 || receipt.terminal_queries!=1 || receipt.prefix_queries!=0)
                throw std::runtime_error("prefix fold unexpectedly ranked or queried physical support");
            std::ostringstream line;
            line<<index<<' '<<hex(value.denominator);
            for (const auto& n:value.numerators) line<<' '<<hex(n);
            line<<' '<<receipt.modeled_work<<' '<<receipt.peak_integer_bits<<' '
                <<receipt.peak_integer_payload_bits<<' '<<receipt.rank_calls<<'\n';
            const auto raw=line.str();
            if (raw.size()>1024 || bytes+raw.size()>2'100'000)
                throw std::runtime_error("fixed component output admission exceeded");
            bytes+=raw.size(); total_work+=receipt.modeled_work;
            std::cout<<raw; ++index;
        };
        const std::array<std::uint8_t,0> empty{};
        emit(empty);
        for (std::size_t a=0;a<deck.size();++a)
        for (std::size_t b=a+1;b<deck.size();++b)
        for (std::size_t c=b+1;c<deck.size();++c) {
            const std::array<std::uint8_t,3> flop{deck[a],deck[b],deck[c]};
            emit(flop);
            for (const auto turn:deck) {
                if (turn==deck[a] || turn==deck[b] || turn==deck[c]) continue;
                const std::array<std::uint8_t,4> turn_board{deck[a],deck[b],deck[c],turn};
                emit(turn_board);
                for (const auto river:deck) {
                    if (river==deck[a] || river==deck[b] || river==deck[c] || river==turn) continue;
                    const std::array<std::uint8_t,5> board{deck[a],deck[b],deck[c],turn,river};
                    emit(board);
                }
            }
        }
        if (index!=3109) throw std::runtime_error("complete fixed prefix enumeration required");
        std::cout<<"END "<<index<<' '<<total_work<<'\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n'; return 1;
    }
}
