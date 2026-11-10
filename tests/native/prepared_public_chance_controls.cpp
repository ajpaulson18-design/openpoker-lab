// Fixed, bounded component fixtures; not a sampler or a training protocol.
#include "../../native/prepared_public_chance.hpp"
#include <array>
#include <bit>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

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
chance::Limits kernel_limits(prepared::ContractionKernel kernel,chance::Limits limits={}) {
    if (kernel==prepared::ContractionKernel::sparse_pairs) limits.max_hands_per_side=2;
    return limits;
}
bool rejected(const char* name,Reach r,chance::Limits limits,chance::ErrorCode expected,
              std::span<const std::uint8_t> board=board_a,std::size_t player=0,
              chance::TerminalKind kind=chance::TerminalKind::showdown,std::size_t count=2,
              prepared::ContractionKernel kernel=prepared::ContractionKernel::blocker_buckets) {
    prepared::PreparedPublicChance owner(sb,bb,chance::DeckDefinition::reduced(deck),kernel_limits(kernel,limits),64,
                                         prepared::RankCacheKey::ordered_prefix,kernel);
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
int cumulative(prepared::ContractionKernel kernel=prepared::ContractionKernel::blocker_buckets) {
    prepared::PreparedPublicChance reference(sb,bb,chance::DeckDefinition::reduced(deck),kernel_limits(kernel),64,
                                             prepared::RankCacheKey::ordered_prefix,kernel);
    const auto initial=reference.receipt().modeled_work;
    const auto one=fixture(4);
    (void)reference.contraction(0,empty,chance::TerminalKind::fold,one.n,0);
    const auto per=reference.receipt().modeled_work-initial;
    auto limits=chance::Limits{}; limits.max_modeled_work=initial+3*per+per/2;
    prepared::PreparedPublicChance owner(sb,bb,chance::DeckDefinition::reduced(deck),kernel_limits(kernel,limits),64,
                                         prepared::RankCacheKey::ordered_prefix,kernel);
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

int sparse_guards() {
    using Kernel=prepared::ContractionKernel;
    auto reach=fixture(0);
    reach.n[0]=-1; // Even blocked rows must be validated before cache access.
    bool ok=rejected("sparse_blocked_negative",reach,{},chance::ErrorCode::invalid_query,
        board_a,0,chance::TerminalKind::showdown,2,Kernel::sparse_pairs);
    const auto reduced=chance::DeckDefinition::reduced(deck);
    prepared::PreparedPublicChance calibration(sb,bb,reduced,kernel_limits(Kernel::sparse_pairs),64,
        prepared::RankCacheKey::ordered_prefix,Kernel::sparse_pairs);
    auto limits=chance::Limits{};
    limits.max_modeled_work=calibration.receipt().modeled_work+100;
    ok=rejected("sparse_work",fixture(0),limits,chance::ErrorCode::modeled_work_limit,
        board_a,0,chance::TerminalKind::showdown,2,Kernel::sparse_pairs)&&ok;
    const std::array<chance::WeightedHand,3> wide{sb[0],sb[1],{{17,33},std::bit_cast<std::uint64_t>(0.5)}};
    bool wide_rejected=false;
    try { prepared::PreparedPublicChance foreign(wide,bb,reduced,kernel_limits(Kernel::sparse_pairs),64,
        prepared::RankCacheKey::ordered_prefix,Kernel::sparse_pairs); }
    catch (const chance::KernelError& error) { wide_rejected=error.code()==chance::ErrorCode::invalid_input; }
    std::cout<<"SPARSE_WIDE "<<(wide_rejected?"PASS":"FAIL")<<'\n';
    return ok && wide_rejected ? 0 : 1;
}

int board_set_controls(prepared::ContractionKernel kernel=prepared::ContractionKernel::blocker_buckets) {
    const std::array<std::uint8_t,10> nested{0,16,17,24,32,33,35,37,43,48};
    const auto kind=chance::TerminalKind::showdown;
    for (const auto size:{std::size_t{9},std::size_t{10}}) {
        const auto cards=std::span(nested).last(size);
        const auto capacity=size==9?3u:17u;
        const auto limits=kernel_limits(kernel);
        prepared::PreparedPublicChance owner(sb,bb,chance::DeckDefinition::reduced(cards),limits,capacity,
                                             prepared::RankCacheKey::board_set,kernel);
        std::optional<prepared::PreparedPublicChance> reference;
        if (kernel==prepared::ContractionKernel::sparse_pairs)
            reference.emplace(sb,bb,chance::DeckDefinition::reduced(cards),limits,capacity,
                              prepared::RankCacheKey::board_set);
        const auto mask=[](chance::Hand h) { return (UINT64_C(1)<<h.first)|(UINT64_C(1)<<h.second); };
        std::size_t count=0;
        std::array<std::uint8_t,5> last{};
        for (std::size_t a=0;a<size;++a) for (std::size_t b=a+1;b<size;++b)
        for (std::size_t c=b+1;c<size;++c) for (std::size_t t=0;t<size;++t)
        for (std::size_t r=0;r<size;++r) {
            if (t==a || t==b || t==c || r==a || r==b || r==c || r==t) continue;
            const std::array<std::uint8_t,5> board{cards[a],cards[b],cards[c],cards[t],cards[r]};
            std::uint64_t blocked=0;
            for (const auto card:board) blocked|=UINT64_C(1)<<card;
            bool supported=false;
            for (const auto& x:sb) for (const auto& y:bb) {
                const auto first=mask(x.hand),second=mask(y.hand);
                supported=supported || (!(first&second) && !((first|second)&blocked));
            }
            if (!supported) continue;
            last=board;
            for (std::size_t player=0;player<2;++player) {
                // Warm the first plane with zero reach and vary later hits.
                const auto selector=count==0 && player==0?2:static_cast<int>((count+player)%2);
                const auto reach=fixture(selector);
                const auto value=owner.contraction(player,board,kind,reach.n,reach.exponent);
                if (reference) {
                    const auto original=reference->contraction(player,board,kind,reach.n,reach.exponent);
                    if (original.numerators!=value.numerators || original.prefix_divisor!=value.prefix_divisor ||
                        original.reach_exponent!=value.reach_exponent)
                        throw std::runtime_error("sparse board-set contraction differs from buckets");
                }
                std::cout<<"BOARD_SET "<<size<<' '<<player<<' '<<selector;
                for (const auto card:board) std::cout<<' '<<static_cast<unsigned>(card);
                std::cout<<' '<<value.prefix_divisor<<' '<<value.reach_exponent;
                for (const auto& n:value.numerators) std::cout<<' '<<hex(n);
                std::cout<<'\n';
            }
            ++count;
        }
        const auto before=owner.receipt();
        const auto wanted=size==9?60u:340u;
        const auto ranks=size==9?7u:42u;
        if (count!=wanted || before.rank_calls!=ranks || before.cache_misses!=capacity ||
            before.cache_hits!=2*count-capacity || before.cache_evictions || !ledger(before))
            throw std::runtime_error("rank board-set census differs");
        std::swap(last[0],last[1]);
        bool rejected=false;
        try { (void)owner.contraction(0,last,kind,fixture(4).n,0); }
        catch (const chance::KernelError& error) { rejected=error.code()==chance::ErrorCode::invalid_query; }
        const auto& after=owner.receipt();
        if (!rejected || !owner.failed() || after.cache_lookup_work!=before.cache_lookup_work ||
            after.rank_calls!=before.rank_calls || after.query_array_admissions!=before.query_array_admissions)
            throw std::runtime_error("invalid ordered flop reached a warm board-set cache");
        std::cout<<"BOARD_SET_END "<<size<<' '<<count<<' '<<before.rank_calls<<' '<<before.cache_misses
            <<' '<<before.cache_hits<<' '<<before.cache_evictions<<'\n';
        if (reference) {
            const auto& original=reference->receipt();
            if (!ledger(original) || original.rank_calls!=before.rank_calls ||
                original.cache_hits!=before.cache_hits || original.cache_misses!=before.cache_misses ||
                original.cache_lookup_work!=before.cache_lookup_work || original.input_work!=before.input_work)
                throw std::runtime_error("sparse board-set contraction changed shared receipt categories");
            std::cout<<"SPARSE_WORK "<<size<<' '<<original.contraction_work<<' '<<before.contraction_work
                <<' '<<original.modeled_work<<' '<<before.modeled_work<<' '
                <<original.peak_live_entries<<' '<<before.peak_live_entries<<' '
                <<original.peak_integer_payload_bits<<' '<<before.peak_integer_payload_bits<<'\n';
        }
    }
    prepared::PreparedPublicChance evict(sb,bb,chance::DeckDefinition::reduced(deck),kernel_limits(kernel),1,
                                         prepared::RankCacheKey::board_set,kernel);
    const auto reach=fixture(0);
    const auto first=evict.contraction(0,board_a,kind,reach.n,reach.exponent);
    (void)evict.contraction(0,board_c,kind,reach.n,reach.exponent);
    const auto reloaded=evict.contraction(0,board_b,kind,reach.n,reach.exponent);
    if (first.numerators!=reloaded.numerators || evict.receipt().cache_misses!=3 || evict.receipt().cache_evictions!=2)
        throw std::runtime_error("rank board-set eviction changed the reloaded contraction");
    return 0;
}
int indexed_controls() {
    using K=prepared::ContractionKernel;
    using R=prepared::RankCacheKey;
    using I=prepared::RankCacheIndex;
    auto limits=kernel_limits(K::sparse_pairs);
    prepared::PreparedPublicChance sorted(sb,bb,chance::DeckDefinition::reduced(deck),limits,2,R::board_set,K::sparse_pairs,I::sorted_board_set);
    prepared::PreparedPublicChance linear(sb,bb,chance::DeckDefinition::reduced(deck),limits,2,R::board_set,K::sparse_pairs);
    if (sorted.receipt().setup_work-linear.receipt().setup_work!=
        prepared::PreparedPublicChance::index_setup_work(2))
        throw std::runtime_error("indexed setup charge differs");
    const std::array<std::uint8_t,5> board_d{17,24,33,37,48};
    const std::array<std::array<std::uint8_t,5>,6> trace{board_a,board_b,board_c,board_d,board_a,board_c};
    for (std::size_t i=0;i<trace.size();++i) {
        const auto reach=fixture(i==0?2:0);
        const auto actual=sorted.contraction(i%2,trace[i],chance::TerminalKind::showdown,reach.n,reach.exponent);
        const auto expected=linear.contraction(i%2,trace[i],chance::TerminalKind::showdown,reach.n,reach.exponent);
        if (actual.numerators!=expected.numerators || actual.prefix_divisor!=expected.prefix_divisor ||
            actual.reach_exponent!=expected.reach_exponent) throw std::runtime_error("indexed result differs");
        const auto index=sorted.rank_index_receipt();const auto receipt=sorted.receipt();
        if (!ledger(receipt)) throw std::runtime_error("indexed parent ledger differs");
        std::cout<<"INDEXED_ROW "<<i<<' '<<(i%2)<<' '<<(i==0?2:0);
        for (auto card:trace[i]) std::cout<<' '<<static_cast<unsigned>(card);
        std::cout<<' '<<actual.prefix_divisor<<' '<<actual.reach_exponent;
        for (const auto& n:actual.numerators) std::cout<<' '<<hex(n);
        std::cout<<' '<<index.capacity<<' '<<index.entries<<' '<<index.size<<' '<<index.searches
            <<' '<<index.updates<<' '<<index.lookup_work<<' '<<index.update_work<<' '<<index.setup_work
            <<' '<<receipt.cache_hits<<' '<<receipt.cache_misses<<' '<<receipt.cache_evictions
            <<' '<<receipt.cache_lookup_work<<'\n';
    }
    for (std::size_t cap:{std::size_t{1},std::size_t{2},std::size_t{17},std::size_t{56},std::size_t{64}})
        std::cout<<"INDEXED_BOUND "<<cap<<' '<<prepared::PreparedPublicChance::sorted_lookup_work(cap)<<' '
            <<prepared::PreparedPublicChance::index_update_work(cap)<<' '
            <<prepared::PreparedPublicChance::index_setup_work(cap)<<' '
            <<prepared::PreparedPublicChance::index_storage_entries(cap)<<'\n';
    bool wrong_key=false;
    try {prepared::PreparedPublicChance bad(sb,bb,chance::DeckDefinition::reduced(deck),limits,2,R::ordered_prefix,K::sparse_pairs,I::sorted_board_set);}
    catch (const chance::KernelError&) {wrong_key=true;}
    if (!wrong_key) throw std::runtime_error("indexed ordered-prefix mode accepted");
    auto bad_reach=fixture(0);bad_reach.n[0]=-1;
    const auto before=sorted.rank_index_receipt();
    bool rejected=false;
    try {(void)sorted.contraction(0,board_a,chance::TerminalKind::showdown,bad_reach.n,bad_reach.exponent);}
    catch (const chance::KernelError&) {rejected=true;}
    const auto after=sorted.rank_index_receipt();
    if (!rejected || !sorted.failed() || before.searches!=after.searches || before.updates!=after.updates)
        throw std::runtime_error("invalid blocked reach mutated index");
    // Fill every sorted slot using a deliberately nonmonotone permutation,
    // then evict/revisit the true LRU. All boards have canonical sorted flops.
    {
        std::vector<std::array<std::uint8_t,5>> all;
        for (std::size_t a=0;a<deck.size();++a) for (std::size_t b=a+1;b<deck.size();++b)
        for (std::size_t c=b+1;c<deck.size();++c) for (std::size_t d=c+1;d<deck.size();++d)
        for (std::size_t e=d+1;e<deck.size();++e)
            all.push_back({deck[a],deck[b],deck[c],deck[d],deck[e]});
        if (all.size()!=126) throw std::runtime_error("indexed full-cache board geometry");
        prepared::PreparedPublicChance indexed(sb,bb,chance::DeckDefinition::reduced(deck),limits,64,
            R::board_set,K::sparse_pairs,I::sorted_board_set);
        prepared::PreparedPublicChance baseline(sb,bb,chance::DeckDefinition::reduced(deck),limits,64,
            R::board_set,K::sparse_pairs);
        const auto perform=[&](std::size_t position,bool nonzero) {
            const auto reach=fixture(nonzero?0:2);
            const auto a=indexed.contraction(position%2,all[position],chance::TerminalKind::showdown,reach.n,reach.exponent);
            const auto b=baseline.contraction(position%2,all[position],chance::TerminalKind::showdown,reach.n,reach.exponent);
            if (a.numerators!=b.numerators || a.prefix_divisor!=b.prefix_divisor || a.reach_exponent!=b.reach_exponent)
                throw std::runtime_error("full indexed cache differs from linear");
            const auto x=indexed.receipt(),y=baseline.receipt();
            if (x.cache_hits!=y.cache_hits || x.cache_misses!=y.cache_misses || x.cache_evictions!=y.cache_evictions ||
                x.rank_calls!=y.rank_calls) throw std::runtime_error("full indexed cache receipt differs");
        };
        // gcd(37,126)=1, giving distinct first/middle/last insertion positions.
        for (std::size_t i=0;i<64;++i) perform((37*i)%126,i%17==0);
        const auto recent=(37*63)%126;
        perform(recent,true);
        if (indexed.receipt().cache_hits!=1 || indexed.receipt().cache_misses!=64 ||
            indexed.rank_index_receipt().size!=64) throw std::runtime_error("full index warm or recent hit");
        perform((37*64)%126,true);
        if (indexed.receipt().cache_evictions!=1 || indexed.receipt().cache_misses!=65)
            throw std::runtime_error("full index did not evict oldest slot");
        perform(0,true);
        const auto index=indexed.rank_index_receipt();
        if (indexed.receipt().cache_evictions!=2 || indexed.receipt().cache_misses!=66 ||
            index.capacity!=64 || index.size!=64 || index.updates!=66)
            throw std::runtime_error("full index did not reload true LRU");
        std::cout<<"INDEXED_FULL64 PASS\n";
    }
    // Independent exact one-short calibration: construction and one complete
    // miss must fail before granting any rank or index publication.
    auto make=[&](chance::Limits bounds) {
        return std::make_unique<prepared::PreparedPublicChance>(sb,bb,chance::DeckDefinition::reduced(deck),
            kernel_limits(K::sparse_pairs,bounds),2,R::board_set,K::sparse_pairs,I::sorted_board_set);
    };
    auto calibrated=make({});
    const auto construction=calibrated->receipt();
    auto short_entries=chance::Limits{};
    short_entries.max_storage_entries=construction.peak_live_entries-1;
    bool entries_rejected=false;
    try {(void)make(short_entries);} catch (const chance::KernelError&) {entries_rejected=true;}
    if (!entries_rejected) throw std::runtime_error("indexed constructor admitted one-short entries");
    const auto one=fixture(0);
    (void)calibrated->contraction(0,board_a,chance::TerminalKind::showdown,one.n,one.exponent);
    auto short_work=chance::Limits{};
    short_work.max_modeled_work=calibrated->receipt().modeled_work-1;
    auto capped=make(short_work);
    bool work_rejected=false;
    try {(void)capped->contraction(0,board_a,chance::TerminalKind::showdown,one.n,one.exponent);}
    catch (const chance::KernelError& error) {work_rejected=error.code()==chance::ErrorCode::modeled_work_limit;}
    const auto failed=capped->receipt();const auto index_failed=capped->rank_index_receipt();
    if (!work_rejected || !capped->failed() || failed.rank_calls || failed.completed_contractions ||
        failed.query_array_admissions || index_failed.updates || index_failed.size)
        throw std::runtime_error("indexed one-short work reached rank publication");
    std::cout<<"INDEXED_GUARDS PASS\n";
    return 0;
}
} // namespace
int main(int argc,char** argv) {
    try {
        if (argc==2) {
            const std::string mode=argv[1];
            if (mode=="indexed") return indexed_controls();
            if (mode=="guards") return guards();
            if (mode=="cache") return cache_control();
            if (mode=="cumulative") return cumulative();
            if (mode=="setup") return setup_guards();
            if (mode=="same") return same_fixture();
            if (mode=="snapshot") return snapshot();
            if (mode=="board-sets") return board_set_controls();
            if (mode=="sparse-board-sets") return board_set_controls(prepared::ContractionKernel::sparse_pairs);
            if (mode=="sparse-guards") return sparse_guards();
            if (mode=="sparse-cumulative") return cumulative(prepared::ContractionKernel::sparse_pairs);
        }
        const bool sparse=argc==5 && std::string_view(argv[4])=="sparse";
        if (argc!=4 && !sparse) throw std::runtime_error("three fixed prepared fixture selectors required");
        const int profile=digit(argv[1],5),player=digit(argv[2],1),mode=digit(argv[3],1);
        const auto reach=fixture(profile);
        const auto kernel=sparse?prepared::ContractionKernel::sparse_pairs:prepared::ContractionKernel::blocker_buckets;
        prepared::PreparedPublicChance owner(sb,bb,chance::DeckDefinition::reduced(deck),kernel_limits(kernel),64,
            prepared::RankCacheKey::ordered_prefix,kernel);
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
