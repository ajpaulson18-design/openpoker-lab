// Fixed, bounded component fixtures; not a sampler or a training protocol.
#include "../../native/prepared_public_chance.hpp"
#include <array>
#include <bit>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>

namespace chance = openpoker::full_deck_public_chance;
namespace prepared = openpoker::prepared_public_chance;
using chance::Integer;
namespace {
const std::array<std::uint8_t, 9> deck{16,17,24,32,33,35,37,43,48};
const std::array<chance::WeightedHand,2> sb{{
    {{43,48},std::bit_cast<std::uint64_t>(0.125)},
    {{32,43},std::bit_cast<std::uint64_t>(0.75)}}};
const std::array<chance::WeightedHand,2> bb{{
    {{24,37},std::bit_cast<std::uint64_t>(0.375)},
    {{16,32},std::bit_cast<std::uint64_t>(1.0)}}};

static_assert(!std::is_copy_constructible_v<prepared::PreparedPublicChance>);
static_assert(!std::is_move_constructible_v<prepared::PreparedPublicChance>);
static_assert(!std::is_copy_assignable_v<prepared::PreparedPublicChance>);
static_assert(!std::is_move_assignable_v<prepared::PreparedPublicChance>);
struct Reach { std::array<Integer,2> n{}; std::size_t exponent=0; };
Reach fixture(int id) {
    Reach r;
    if (id==0) { r.exponent=2; r.n={1,3}; }
    else if (id==1) {
        const Integer a=(Integer(1)<<53)-1,b=(Integer(1)<<52)+1;
        r.exponent=159; r.n={(a*a)<<53,b*b*b};
    } else if (id==2) { r.exponent=300; }
    else if (id==3) { r.exponent=2200; r.n={1,3}; }
    else if (id==4) { r.n={1,1}; }
    else if (id==5) { r.exponent=2200; r.n={Integer(1)<<2200,0}; }
    else throw std::runtime_error("fixed prepared reach selector required");
    return r;
}
std::string hex(const Integer& value) {
    if (value<0) { const Integer n=-value; return "-"+n.str(0,std::ios_base::hex); }
    return value.str(0,std::ios_base::hex);
}
int digit(const char* text,int max) {
    if (!text[0] || text[1] || text[0]<'0' || text[0]>'0'+max)
        throw std::runtime_error("bounded prepared fixture selector required");
    return text[0]-'0';
}
bool ledger(const prepared::Receipt& r) {
    return r.modeled_work==r.prior_work+r.setup_work+r.input_work+r.cache_lookup_work+
        r.rank_work+r.sort_work+r.contraction_work && r.modeled_work<=500'000'000 &&
        r.peak_live_entries<=2'000'000 && r.peak_integer_bits<=65536 &&
        r.peak_integer_payload_bits<=(std::size_t{1}<<30);
}
const std::array<std::uint8_t,5> board_a{17,24,33,35,37},board_b{17,24,33,37,35},
    board_c{17,24,33,35,48};
const std::array<std::uint8_t,0> empty{};
bool rejected(const char* name,Reach r,chance::Limits limits,chance::ErrorCode expected,
              std::span<const std::uint8_t> board=board_a,std::size_t player=0,
              chance::TerminalKind kind=chance::TerminalKind::showdown,std::size_t count=2) {
    prepared::PreparedPublicChance owner(sb,bb,chance::DeckDefinition::reduced(deck),limits);
    try { (void)owner.contraction(player,board,kind,std::span<const Integer>(r.n.data(),count),r.exponent); }
    catch (const chance::KernelError& error) {
        const auto& receipt=owner.receipt();
        const auto before=receipt.modeled_work;
        bool poisoned=false;
        try { (void)owner.contraction(0,empty,chance::TerminalKind::fold,fixture(4).n,0); }
        catch (const chance::KernelError&) { poisoned=owner.receipt().modeled_work==before; }
        const bool ok=error.code()==expected && owner.failed() && poisoned && ledger(receipt) &&
            receipt.rank_calls==0 && receipt.completed_contractions==0 && receipt.query_array_admissions==0;
        std::cout<<"GUARD "<<name<<' '<<(ok ? "PASS" : "FAIL")<<' '
            <<receipt.modeled_work<<' '<<receipt.rank_calls<<' '<<receipt.query_array_admissions<<'\n';
        return ok;
    }
    std::cout<<"GUARD "<<name<<" FAIL no_error\n"; return false;
}
int guards() {
    bool ok=true;
    const auto ordinary=fixture(0);
    auto r=ordinary; r.n[0]=-1; // BB[0] blocked by the board
    ok=rejected("negative_blocked",r,{},chance::ErrorCode::invalid_query)&&ok;
    r=ordinary; r.n[0]=5;
    ok=rejected("above_one_blocked",r,{},chance::ErrorCode::invalid_query)&&ok;
    r=ordinary; r.n[0]=8;
    ok=rejected("wide_above_one_blocked",r,{},chance::ErrorCode::invalid_query)&&ok;
    r=ordinary; r.n[1]=-1;
    ok=rejected("late_negative",r,{},chance::ErrorCode::invalid_query)&&ok;
    ok=rejected("reach_length",ordinary,{},chance::ErrorCode::invalid_query,board_a,0,
        chance::TerminalKind::showdown,1)&&ok;
    ok=rejected("player",ordinary,{},chance::ErrorCode::invalid_query,board_a,2)&&ok;
    ok=rejected("kind",ordinary,{},chance::ErrorCode::invalid_query,board_a,0,
        static_cast<chance::TerminalKind>(99))&&ok;
    r=ordinary; r.exponent=65536;
    ok=rejected("reach_exponent",r,{},chance::ErrorCode::integer_bit_limit)&&ok;
    r=ordinary; r.exponent=std::numeric_limits<std::size_t>::max();
    ok=rejected("overflow_exponent",r,{},chance::ErrorCode::integer_bit_limit)&&ok;
    const std::array<std::uint8_t,3> flop{17,24,33},unsorted{24,17,33},foreign{17,18,24},outside{17,24,52};
    const std::array<std::uint8_t,2> short_board{17,24};
    const std::array<std::uint8_t,5> duplicate{17,24,33,35,35};
    ok=rejected("short_showdown",ordinary,{},chance::ErrorCode::invalid_query,flop)&&ok;
    ok=rejected("short_fold",ordinary,{},chance::ErrorCode::invalid_query,short_board,0,
        chance::TerminalKind::fold)&&ok;
    ok=rejected("unsorted_flop",ordinary,{},chance::ErrorCode::invalid_query,unsorted,0,
        chance::TerminalKind::fold)&&ok;
    ok=rejected("foreign_board",ordinary,{},chance::ErrorCode::invalid_query,foreign,0,
        chance::TerminalKind::fold)&&ok;
    ok=rejected("outside_board",ordinary,{},chance::ErrorCode::invalid_query,outside,0,
        chance::TerminalKind::fold)&&ok;
    ok=rejected("duplicate_board",ordinary,{},chance::ErrorCode::invalid_query,duplicate)&&ok;
    auto limits=chance::Limits{}; limits.max_integer_bits=128;
    r=ordinary; r.n[0]=Integer(1)<<130;
    ok=rejected("blocked_input_width",r,limits,chance::ErrorCode::integer_bit_limit)&&ok;
    r=ordinary; r.exponent=120; r.n={Integer(1)<<120,Integer(1)<<120};
    ok=rejected("intermediate_width",r,limits,chance::ErrorCode::integer_bit_limit)&&ok;
    limits=chance::Limits{}; limits.max_integer_payload_bits=70000;
    ok=rejected("query_payload",fixture(5),limits,chance::ErrorCode::integer_payload_limit,empty,0,
        chance::TerminalKind::fold)&&ok;
    prepared::PreparedPublicChance calibrate(sb,bb,chance::DeckDefinition::reduced(deck));
    limits=chance::Limits{}; limits.max_modeled_work=calibrate.receipt().modeled_work+100;
    ok=rejected("query_work",ordinary,limits,chance::ErrorCode::modeled_work_limit)&&ok;
    return ok ? 0 : 1;
}
int cache_control() {
    prepared::PreparedPublicChance owner(sb,bb,chance::DeckDefinition::reduced(deck),{},2);
    const auto zero=fixture(2),one=fixture(4);
    (void)owner.contraction(0,board_a,chance::TerminalKind::showdown,zero.n,zero.exponent);
    const auto first=owner.receipt().rank_calls;
    bool ok=first==3 && owner.receipt().cache_misses==1;
    (void)owner.contraction(1,board_a,chance::TerminalKind::showdown,one.n,one.exponent);
    ok=ok && owner.receipt().rank_calls==first && owner.receipt().cache_hits==1;
    (void)owner.contraction(0,board_b,chance::TerminalKind::showdown,one.n,one.exponent);
    ok=ok && owner.receipt().rank_calls==6 && owner.receipt().cache_misses==2;
    (void)owner.contraction(0,board_a,chance::TerminalKind::showdown,one.n,one.exponent);
    (void)owner.contraction(0,board_c,chance::TerminalKind::showdown,one.n,one.exponent);
    const auto before=owner.receipt().rank_calls;
    (void)owner.contraction(0,board_a,chance::TerminalKind::showdown,one.n,one.exponent);
    ok=ok && owner.receipt().rank_calls==before;
    (void)owner.contraction(0,board_b,chance::TerminalKind::showdown,one.n,one.exponent);
    ok=ok && owner.receipt().rank_calls==before+3 && owner.receipt().cache_misses==4 &&
        owner.receipt().cache_evictions==2 && owner.receipt().cache_hits==3 && ledger(owner.receipt());
    const auto ranks=owner.receipt().rank_calls;
    (void)owner.contraction(0,empty,chance::TerminalKind::fold,one.n,one.exponent);
    ok=ok && owner.receipt().rank_calls==ranks && owner.receipt().cache_misses==4;
    std::cout<<"CACHE_ORDERED_LRU_ZERO_REACH "<<(ok ? "PASS" : "FAIL")<<'\n';
    return ok ? 0 : 1;
}
int cumulative() {
    prepared::PreparedPublicChance reference(sb,bb,chance::DeckDefinition::reduced(deck));
    const auto initial=reference.receipt().modeled_work;
    const auto one=fixture(4);
    (void)reference.contraction(0,empty,chance::TerminalKind::fold,one.n,0);
    const auto per=reference.receipt().modeled_work-initial;
    auto limits=chance::Limits{}; limits.max_modeled_work=initial+3*per+per/2;
    prepared::PreparedPublicChance owner(sb,bb,chance::DeckDefinition::reduced(deck),limits);
    for (int i=0;i<3;++i) (void)owner.contraction(0,empty,chance::TerminalKind::fold,one.n,0);
    bool ok=owner.receipt().modeled_work==initial+3*per;
    try { (void)owner.contraction(0,empty,chance::TerminalKind::fold,one.n,0); ok=false; }
    catch (const chance::KernelError& e) {
        ok=ok && e.code()==chance::ErrorCode::modeled_work_limit && owner.failed() &&
            owner.receipt().completed_contractions==3 && owner.receipt().query_array_admissions==3;
    }
    ok=ok && ledger(owner.receipt()) && owner.receipt().prior_work==owner.prior_receipt().modeled_work &&
        owner.receipt().retained_entries>owner.prior_receipt().retained_entries &&
        owner.receipt().retained_integer_payload_bits>owner.prior_receipt().setup_integer_payload_bits;
    std::cout<<"CUMULATIVE_POISON "<<(ok ? "PASS" : "FAIL")<<' '<<initial<<' '<<per<<'\n';
    return ok ? 0 : 1;
}
int setup_guards() {
    bool ok=true;
    for (int id=0;id<5;++id) {
        auto limits=chance::Limits{}; std::size_t cap=64;
        auto expected=chance::ErrorCode::invalid_limits;
        if (id==0) cap=65;
        if (id==1) { limits.max_storage_entries=1; expected=chance::ErrorCode::storage_limit; }
        if (id==2) { limits.max_modeled_work=21520; expected=chance::ErrorCode::modeled_work_limit; }
        if (id==3) limits.max_integer_bits=65537;
        if (id==4) cap=0;
        bool rejected=false;
        try { prepared::PreparedPublicChance owner(sb,bb,chance::DeckDefinition::reduced(deck),limits,cap); }
        catch (const chance::KernelError& e) { rejected=e.code()==expected; }
        std::cout<<"SETUP "<<id<<' '<<(rejected ? "PASS" : "FAIL")<<'\n'; ok=ok&&rejected;
    }
    return ok ? 0 : 1;
}
int same_fixture() {
    const std::array<chance::WeightedHand,3> side0{{
        {{43,48},std::bit_cast<std::uint64_t>(0.5)},
        {{16,32},std::bit_cast<std::uint64_t>(0.25)},
        {{24,37},std::bit_cast<std::uint64_t>(1.0)}}};
    const std::array<chance::WeightedHand,2> side1{{
        {{43,48},std::bit_cast<std::uint64_t>(0.75)},
        {{24,37},std::bit_cast<std::uint64_t>(0.125)}}};
    prepared::PreparedPublicChance owner(side0,side1,chance::DeckDefinition::reduced(deck));
    const std::array<Integer,3> reach0{3,0,4}; const std::array<Integer,2> reach1{3,1};
    const std::array<std::uint8_t,3> flop{16,17,33};
    const std::array<std::uint8_t,5> full{16,17,32,33,35};
    for (std::size_t p=0;p<2;++p) for (int k=0;k<4;++k) {
        const auto board=k==0 ? std::span<const std::uint8_t>(empty) :
            k==1 ? std::span<const std::uint8_t>(flop) : std::span<const std::uint8_t>(full);
        const auto kind=k==3 ? chance::TerminalKind::showdown : chance::TerminalKind::fold;
        const auto reach=p==0 ? std::span<const Integer>(reach1) : std::span<const Integer>(reach0);
        const auto value=owner.contraction(p,board,kind,reach,2);
        std::cout<<"SAME "<<p<<' '<<k<<' '<<hex(owner.normalizer_integer())<<' '<<value.prefix_divisor;
        for (const auto& n:value.numerators) std::cout<<' '<<hex(n);
        std::cout<<'\n';
    }
    return ledger(owner.receipt()) ? 0 : 1;
}
int snapshot() {
    auto own=sb,opposite=bb;
    prepared::PreparedPublicChance owner(own,opposite,chance::DeckDefinition::reduced(deck));
    for (auto& row:own) { row.hand={0,0}; row.binary64_weight_bits=0; }
    for (auto& row:opposite) { row.hand={51,51}; row.binary64_weight_bits=~std::uint64_t{0}; }
    const auto one=fixture(4);
    const auto out=owner.contraction(0,empty,chance::TerminalKind::fold,one.n,0);
    std::cout<<"SNAPSHOT "<<hex(owner.normalizer_integer());
    for (const auto& n:out.numerators) std::cout<<' '<<hex(n);
    std::cout<<'\n'; return 0;
}
} // namespace
int main(int argc,char** argv) {
    try {
        if (argc==2) {
            const std::string mode=argv[1];
            if (mode=="guards") return guards();
            if (mode=="cache") return cache_control();
            if (mode=="cumulative") return cumulative();
            if (mode=="setup") return setup_guards();
            if (mode=="same") return same_fixture();
            if (mode=="snapshot") return snapshot();
        }
        if (argc!=4) throw std::runtime_error("three fixed prepared fixture selectors required");
        const int profile=digit(argv[1],5),player=digit(argv[2],1),mode=digit(argv[3],1);
        const auto reach=fixture(profile);
        prepared::PreparedPublicChance owner(sb,bb,chance::DeckDefinition::reduced(deck));
        std::cout<<"PREPARED_CASES_V1 "<<profile<<' '<<player<<' '<<mode<<' '<<hex(owner.normalizer_integer())<<'\n';
        std::size_t index=0,bytes=0;
        auto emit=[&](std::span<const std::uint8_t> board) {
            if (mode==1 && board.size()!=5) return;
            const auto out=owner.contraction(static_cast<std::size_t>(player),board,
                mode ? chance::TerminalKind::showdown : chance::TerminalKind::fold,reach.n,reach.exponent);
            const auto& r=owner.receipt();
            if (!ledger(r)) throw std::runtime_error("prepared cumulative ledger mismatch");
            std::ostringstream line;
            line<<index<<' '<<out.prefix_divisor<<' '<<out.reach_exponent;
            for (const auto& n:out.numerators) line<<' '<<hex(n);
            line<<' '<<r.modeled_work<<' '<<r.rank_calls<<' '<<r.cache_hits<<' '<<r.cache_misses<<' '
                <<r.cache_evictions<<' '<<r.retained_entries<<' '<<r.peak_integer_bits<<' '
                <<r.peak_integer_payload_bits<<'\n';
            const auto raw=line.str();
            if (raw.size()>2048 || bytes+raw.size()>2'100'000)
                throw std::runtime_error("prepared fixture output bound");
            std::cout<<raw; bytes+=raw.size(); ++index;
        };
        emit(empty);
        for (std::size_t a=0;a<deck.size();++a) for (std::size_t b=a+1;b<deck.size();++b)
        for (std::size_t c=b+1;c<deck.size();++c) {
            const std::array<std::uint8_t,3> flop{deck[a],deck[b],deck[c]}; emit(flop);
            for (const auto turn:deck) {
                if (turn==deck[a] || turn==deck[b] || turn==deck[c]) continue;
                const std::array<std::uint8_t,4> turn_board{deck[a],deck[b],deck[c],turn}; emit(turn_board);
                for (const auto river:deck) {
                    if (river==deck[a] || river==deck[b] || river==deck[c] || river==turn) continue;
                    const std::array<std::uint8_t,5> full{deck[a],deck[b],deck[c],turn,river}; emit(full);
                }
            }
        }
        const auto expected=mode ? 2520 : 3109;
        if (index!=static_cast<std::size_t>(expected)) throw std::runtime_error("incomplete declared fixture");
        std::cout<<"END "<<index<<' '<<owner.receipt().modeled_work<<'\n'; return 0;
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
