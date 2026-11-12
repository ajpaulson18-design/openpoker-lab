#pragma once
// Fixed PROOF9 and PROOF10, q=1, bounded simultaneous CFR+ sweeps. No board, world, reach,
// or payoff table is retained. This front door has no general solver dispatch.
#include "prepared_public_chance.hpp"
#include "virtual_dyadic_state.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <filesystem>
#include <limits>
#include <memory>
#include <optional>
#include <ostream>
#include <span>
#include <stdexcept>
#include <string_view>
#include <type_traits>
#include <utility>

namespace openpoker::virtual_dyadic_training {
namespace betting=virtual_betting_template;
namespace chance=full_deck_public_chance;
namespace prepared=prepared_public_chance;
namespace history=virtual_dyadic_history;
namespace state=virtual_dyadic_state;
namespace paging=virtual_dyadic_paged_image;
using chance::Integer;
using Values=std::array<Integer,2>;
using Cursor=history::History::Cursor;
inline constexpr std::size_t sweeps=2, targets=2, seat_passes=sweeps*targets;
enum class Traversal { by_seat, paired };
enum class StrategyProfile {
    dense, packed_averages, compact, scaled, sealed, paged, directory, rank_sets, split_checkpoint, ten_card,
    ten_card_buffered, ten_card_virtual_zero, ten_card_ordered_state, ten_card_row_coverage, ten_card_shared_policy,
    ten_card_paged_directory, proof9_three_sweep, proof9_four_sweep, ten_card_sparse_chance, ten_card_single_division,
    ten_card_phase_payload,
    ten_card_row_batched,
    ten_card_indexed_cache, proof9_quality32, proof9_linear32, ten_card_complement, ten_card_compact_wire
};
inline constexpr std::uint64_t visit_cost(Traversal mode) {
    // Paired frames carry one additional two-holding lane and lane routing.
    return mode==Traversal::paired?12:8;
}
inline constexpr std::size_t literal_count=1105, template_count=388;
inline constexpr std::size_t integer_words=11;
inline constexpr std::uint64_t grid=dyadic_policy::grid_units;
inline constexpr auto grid_bits=dyadic_policy::grid_bits;
inline constexpr std::size_t reach_operand_bits=7*grid_bits+1;
inline constexpr std::uint64_t work_cap=500000000, template_cap=43000000,
    chance_cap=110000000, history_cap=42000000, state_cap=75000000,
    quantizer_cap=106000000, parent_cap=115000000;
inline constexpr std::size_t entries_cap=2000000, payload_cap=std::size_t{1}<<30,
    chance_entries=12000, chance_payload=std::size_t{1}<<20,
    history_bytes=std::size_t{1}<<20, parent_entries=16384, parent_payload=std::size_t{1}<<22;
inline constexpr std::uint64_t chance_setup_bound=65536;
inline constexpr std::uint64_t proof9_t3_parent_cap=298417808;
inline constexpr std::size_t proof9_t3_directory_page_limit=2122;
inline constexpr std::uint64_t proof9_t3_general_quantizer_expected=78506392;
inline constexpr std::uint64_t proof9_t3_sweep_stream_copy_work=3669084;
inline constexpr std::uint64_t proof9_t3_sweep_stream_image_bytes=4853840;
inline constexpr std::uint64_t proof9_t3_sweep_stream_retained_bytes=2579724;
inline constexpr std::uint64_t proof9_t3_sweep_stream_read_bytes=14561520;
inline constexpr std::uint64_t proof9_t3_sweep_stream_wire_bytes=17141340;
inline constexpr std::uint64_t proof9_t3_sweep_stream_frames=3;
inline constexpr std::uint64_t proof9_t4_parent_cap=340111558;
inline constexpr std::uint64_t proof9_t4_general_quantizer_expected=2*proof9_t3_general_quantizer_expected;
inline constexpr std::uint64_t proof9_t4_sweep_stream_copy_work=4892112;
inline constexpr std::uint64_t proof9_t4_sweep_stream_image_bytes=4853840;
inline constexpr std::uint64_t proof9_t4_sweep_stream_retained_bytes=3045420;
inline constexpr std::uint64_t proof9_t4_sweep_stream_read_bytes=4*proof9_t4_sweep_stream_image_bytes;
inline constexpr std::uint64_t proof9_t4_sweep_stream_wire_bytes=22460908;
inline constexpr std::uint64_t proof9_t4_sweep_stream_frames=4;
inline constexpr std::uint64_t proof9_q32_parent_cap=2500000000ULL;
inline constexpr std::uint64_t proof9_q32_sweep_stream_copy_work=39136896;
inline constexpr std::uint64_t proof9_q32_sweep_stream_image_bytes=4853840;
inline constexpr std::uint64_t proof9_q32_sweep_stream_retained_bytes=16084908;
inline constexpr std::uint64_t proof9_q32_sweep_stream_read_bytes=155322880;
inline constexpr std::uint64_t proof9_q32_sweep_stream_wire_bytes=171408812;
inline constexpr std::uint64_t proof9_q32_sweep_stream_frames=32;
inline constexpr std::uint64_t sweep_stream_header_bytes=32;
inline constexpr std::uint64_t sweep_stream_scratch_bytes=paging::maximum_checkpoint_stream_scratch_bytes;
inline constexpr std::uint64_t sweep_stream_entries=(sweep_stream_scratch_bytes+sweep_stream_header_bytes+7)/8;
inline constexpr std::uint64_t sweep_stream_payload_bits=8*(sweep_stream_scratch_bytes+sweep_stream_header_bytes);
static_assert(template_cap+chance_cap+history_cap+state_cap+quantizer_cap+parent_cap<=work_cap);
// At most 16 visible frames plus three hidden reveal levels. Even 64
// simultaneous 702-bit integer objects per level fit the parent reservation.
static_assert(19*64*(644+58)<parent_payload);

class Error final : public std::runtime_error {
public:
    explicit Error(const char* message):std::runtime_error(message) {}
};
inline void require(bool condition,const char* message) { if (!condition) throw Error(message); }

inline constexpr std::array<std::uint8_t,9> deck_cards{16,17,24,32,33,35,37,43,48};
inline constexpr std::array<std::uint8_t,10> ten_cards{0,16,17,24,32,33,35,37,43,48};
inline constexpr std::array<std::array<chance::WeightedHand,2>,2> ranges{
    std::array{chance::WeightedHand{{43,48},std::bit_cast<std::uint64_t>(.125)},
               chance::WeightedHand{{32,43},std::bit_cast<std::uint64_t>(.75)}},
    std::array{chance::WeightedHand{{24,37},std::bit_cast<std::uint64_t>(.375)},
               chance::WeightedHand{{16,32},std::bit_cast<std::uint64_t>(1.)}}
};
inline constexpr std::uint64_t hand_mask(chance::Hand hand) {
    return (std::uint64_t{1}<<hand.first)|(std::uint64_t{1}<<hand.second);
}
inline constexpr std::array<std::array<std::uint64_t,2>,2> hand_masks{{
    {hand_mask(ranges[0][0].hand),hand_mask(ranges[0][1].hand)},
    {hand_mask(ranges[1][0].hand),hand_mask(ranges[1][1].hand)}
}};
inline betting::Config configuration() {
    betting::Config config;
    config.stacks={8.,8.};
    config.sb=.5;
    config.bb=1.;
    config.stages[0]={{.5},{1.},1,true};
    for (std::size_t i=1;i<4;++i) config.stages[i]={{.5,1.},{.25},1,true};
    return config;
}
inline betting::Limits template_limits() {
    betting::Limits limits;
    limits.work=template_cap;
    limits.nodes=template_count;
    limits.edges=410;
    limits.occurrences=literal_count;
    limits.depth=15;
    limits.entries=131072;
    return limits;
}

enum class Work : std::size_t { geometry,visit,support,reach,value_add,terminal_scale,average,route,output,count };
using WorkList=std::array<std::uint64_t,static_cast<std::size_t>(Work::count)>;
inline constexpr std::array<std::string_view,9> work_names{
    "geometry","visit","support","reach","value_add","terminal_scale","average","route","output"
};
inline constexpr std::size_t work_index(Work family) { return static_cast<std::size_t>(family); }
inline std::uint64_t sum_work(const WorkList& list) {
    std::uint64_t total=0;
    for (const auto item:list) total+=item;
    return total;
}
class Meter final {
    WorkList actual_{},limits_{};
    std::uint64_t total_=0,ceiling_=parent_cap;
public:
    Meter() { limits_[work_index(Work::geometry)]=3000000; }
    void bootstrap_ceiling(std::uint64_t ceiling) {
        require(total_<=ceiling,"dyadic bootstrap work exceeds profile ceiling");
        ceiling_=ceiling;
    }
    void charge(Work family,std::uint64_t cost) {
        const auto at=work_index(family);
        require(cost<=limits_[at]-actual_[at] && cost<=ceiling_-total_,"dyadic parent work admission exceeded");
        actual_[at]+=cost;
        total_+=cost;
    }
    void seal(const WorkList& limits,std::uint64_t allowance) {
        for (std::size_t i=0;i<limits.size();++i) require(actual_[i]<=limits[i],"dyadic parent forecast underrun");
        require(sum_work(limits)<=allowance,"dyadic parent forecast exceeds partition");
        limits_=limits;
        ceiling_=allowance;
    }
    [[nodiscard]] const WorkList& actual() const noexcept { return actual_; }
    [[nodiscard]] std::uint64_t total() const noexcept { return total_; }
};
inline std::uint64_t words(std::size_t bits) { return std::max<std::uint64_t>(1,(bits+63)/64); }
inline std::size_t width(std::uint64_t value) { return static_cast<std::size_t>(std::bit_width(value)); }
inline std::size_t logceil(std::size_t count) { return count<=1?0:width(count-1); }
inline std::uint64_t copy_cost(std::size_t bits) { return 1+2*words(bits); }
inline std::uint64_t add_cost(std::size_t bits) { return 2+3*words(bits); }
inline std::uint64_t mul_cost(std::size_t left,std::size_t right) {
    const auto x=words(left),y=words(right);
    return 2+2*(x+y)+x*y;
}
inline std::uint64_t scaled_average_cost(std::size_t past_bits,std::size_t base_bits,std::size_t actions) {
    const auto row_bits=past_bits+base_bits;
    return 32+mul_cost(past_bits+1,base_bits)+copy_cost(row_bits)+actions*(8+mul_cost(row_bits,53));
}
inline std::uint64_t checked_weighted_marginal(std::uint64_t marginal,std::size_t sweep) {
    require(marginal>=1 && marginal<=580 && sweep>=1 && sweep<=32,
        "linear average marginal or sweep outside PROOF9 bounds");
    require(marginal<=std::numeric_limits<std::uint64_t>::max()/sweep,
        "linear average weighted marginal overflows uint64");
    return marginal*static_cast<std::uint64_t>(sweep);
}
static_assert(580ULL*528ULL<(1ULL<<19) && 580ULL*528ULL>=(1ULL<<18));

struct Prefix {
    std::array<std::uint8_t,5> cards{};
    std::size_t size=0;
    std::uint64_t mask=0;
    [[nodiscard]] std::span<const std::uint8_t> view() const { return {cards.data(),size}; }
};
using Support=std::array<unsigned,2>;
inline unsigned count_supported(unsigned mask) { return static_cast<unsigned>(std::popcount(mask)); }
inline Support physical_support(std::uint64_t blocked) {
    Support result{};
    // Stream compatibility checks for the fixed range; retain only support bits.
    for (std::size_t sb=0;sb<2;++sb) for (std::size_t bb=0;bb<2;++bb) {
        const auto a=hand_masks[0][sb],b=hand_masks[1][bb];
        if (!(a&b) && !((a|b)&blocked)) {
            result[0]|=1U<<sb;
            result[1]|=1U<<bb;
        }
    }
    return result;
}
inline std::size_t candidate_count(std::size_t deck_size,std::size_t size) {
    if (size==0) return deck_size*(deck_size-1)*(deck_size-2)/6;
    require(size==3 || size==4,"invalid physical reveal predecessor");
    return deck_size-size;
}
template<class F> void reveal(std::span<const std::uint8_t> deck,const Prefix& prefix,F&& visit) {
    if (!prefix.size) {
        for (std::size_t a=0;a<deck.size();++a)
            for (std::size_t b=a+1;b<deck.size();++b)
                for (std::size_t c=b+1;c<deck.size();++c) {
                    const auto x=deck[a],y=deck[b],z=deck[c];
                    visit(Prefix{{x,y,z,0,0},3,(std::uint64_t{1}<<x)|(std::uint64_t{1}<<y)|(std::uint64_t{1}<<z)});
                }
        return;
    }
    require(prefix.size==3 || prefix.size==4,"invalid ordered physical reveal");
    for (const auto card:deck) {
        const auto bit=std::uint64_t{1}<<card;
        if (prefix.mask&bit) continue;
        auto next=prefix;
        next.cards[next.size++]=card;
        next.mask|=bit;
        visit(next);
    }
}
inline std::size_t street_index(std::size_t size) {
    require(size==0 || size==3 || size==4 || size==5,"invalid pinned street");
    return size?size-2:0;
}
struct Money { std::uint64_t significand=0; int power=0; };
inline Money stake(const betting::State& node) {
    const auto matched=std::min(node.committed[0],node.committed[1]);
    const auto parts=chance::prior::decode_parts(std::bit_cast<std::uint64_t>(matched),false,true,"invalid pinned terminal stake");
    if (!parts.significand) return {};
    const auto trailing=std::countr_zero(parts.significand);
    return {parts.significand>>trailing,parts.exponent+trailing};
}
inline std::uint64_t uniform_unit(std::size_t menu,std::size_t action) {
    return grid/menu+(action<grid%menu?1U:0U);
}
inline std::size_t uniform_exponent(std::size_t menu) {
    unsigned trailing=grid_bits;
    for (std::size_t a=0;a<menu;++a) trailing=std::min(trailing,static_cast<unsigned>(std::countr_zero(uniform_unit(menu,a))));
    return grid_bits-trailing;
}

struct Counts {
    std::uint64_t visits=0,actions=0,reveals=0,candidates=0,folds=0,showdowns=0,rows=0,slots=0;
    friend bool operator==(const Counts&,const Counts&)=default;
};
struct Fixture {
    std::span<const std::uint8_t> deck;
    std::array<std::uint64_t,4> divisors, prefix_counts;
    Counts shape;
    std::size_t value_bits, denominator_bits, rank_planes, rank_calls;
    std::uint64_t showdown_completions, hidden_candidates;
    std::uint64_t work_limit, chance_limit, history_limit, state_limit, quantizer_limit;
    std::uint64_t payload_limit, output_limit;
    std::size_t requested_sweeps=sweeps;
};
inline constexpr Fixture proof9{
    deck_cards,{1,10,20,20},{1,25,56,60},{61099,57363,3735,15662,16631,17356,24420,58164},
    642,635,3,7,18180,22168,work_cap,chance_cap,history_cap,state_cap,quantizer_cap,payload_cap,22662720
};
inline constexpr Fixture proof10{
    ten_cards,{1,20,60,120},{1,46,156,340},{288946,270487,18458,49182,77857,88290,119196,281066},
    644,637,17,42,103020,70912,2150000000,450000000,100000000,300000000,520000000,1200000000,9833076
};
inline constexpr Fixture proof9_t3{
    deck_cards,{1,10,20,20},{1,25,56,60},{61099,57363,3735,15662,16631,17356,24420,58164},
    642,635,3,7,18180,22168,750000000,125000000,32000000,77000000,184000000,
    payload_cap,2579724,3
};
inline constexpr Fixture proof9_t4{
    deck_cards,{1,10,20,20},{1,25,56,60},{61099,57363,3735,15662,16631,17356,24420,58164},
    642,635,3,7,18180,22168,950000000,171000000,38000000,99000000,262000000,
    payload_cap,3045420,4
};
// The named Q32 lifetime retains the N9 game and equal-sweep average.
// Every owner remains alive across all 32 updates.
inline constexpr Fixture proof9_q32{
    deck_cards,{1,10,20,20},{1,25,56,60},{61099,57363,3735,15662,16631,17356,24420,58164},
    644,635,3,7,18180,22168,5800000000ULL,400000000,220000000,725000000,1870000000,
    payload_cap,proof9_q32_sweep_stream_retained_bytes,32
};
struct PrefixStats {
    std::uint64_t count=0;
    std::array<std::uint64_t,2> supported{};
    std::array<std::array<std::uint64_t,3>,3> unblocked{};
};
struct Plan {
    const Fixture* fixture=&proof9;
    [[nodiscard]] const Fixture& game() const noexcept { return *fixture; }
    [[nodiscard]] bool ten_card() const noexcept { return fixture==&proof10; }
    [[nodiscard]] bool proof9_three_sweep() const noexcept { return fixture==&proof9_t3; }
    [[nodiscard]] bool proof9_four_sweep() const noexcept { return fixture==&proof9_t4; }
    [[nodiscard]] bool proof9_q32_base() const noexcept { return fixture==&proof9_q32; }
    [[nodiscard]] bool proof9_quality32() const noexcept { return proof9_q32_base() && !linear_average; }
    bool linear_average=false;
    [[nodiscard]] bool proof9_linear32() const noexcept { return proof9_q32_base() && linear_average; }
    [[nodiscard]] bool bounded_proof9() const noexcept { return proof9_three_sweep() || proof9_four_sweep() || proof9_q32_base(); }
    Counts shape;
    std::array<PrefixStats,4> prefixes{};
    std::array<std::uint64_t,3> quantizer_terms{};
    std::uint64_t general_quantizer_work=0;
    WorkList parent{};
    Traversal traversal=Traversal::by_seat;
    bool packed_averages=false;
    bool packed_regrets=false;
    bool scaled_averages=false;
    bool sealed_menus=false;
    bool paged_strategy=false;
    bool compact_directory=false;
    bool rank_board_sets=false;
    bool sparse_chance=false;
    bool single_division=false;
    bool phase_payload=false;
    bool row_batched=false;
    bool indexed_cache=false;
    bool complement_division=false;
    bool compact_wire=false;
    bool split_checkpoint=false;
    std::size_t requested_sweeps=sweeps,seat_passes=targets*sweeps,public_walks=targets*sweeps;
    std::size_t H=0,M=0,shift=0,denominator_bits=0,pay_bits=0,max_first_exponent=0;
    std::array<std::size_t,2> max_actor_depth{};
    std::array<std::uint8_t,template_count> suffix_decisions{};
    std::uint64_t normalizer=0,denominator_base=0,expected_rank_calls=0;
    std::size_t rank_planes=0;
    std::uint64_t showdown_contractions=0,hidden_candidates=0;
    std::uint64_t template_work=0,chance_work=0,history_work=0,state_work=0,quantizer_work=0,total_work=0;
    std::uint64_t state_entries=0,state_payload=0,entries=0,payload_bits=0,output_bytes=0;
    std::uint64_t packed_average_limbs=0,packed_average_work=0;
    std::uint64_t packed_regret_limbs=0,packed_regret_work=0;
    std::uint64_t scaled_average_build_work=0;
    std::uint64_t sealed_menu_count=0,sealed_token_count=0;
    paging::Limits page_limits{};
    std::uint64_t paging_work=0;
    std::uint64_t directory_work=0;
    std::uint64_t registration_path_work=0;
    bool ordered_state=false;
    bool row_coverage=false;
    bool shared_policy=false;
    bool paged_directory=false;
    std::uint64_t policy_spill_work=0;
    static constexpr std::size_t policy_frame_entries=136;
    static constexpr std::size_t directory_frame_entries=192;
    static constexpr std::size_t directory_page_limit=7656,directory_read_rows=directory_page_limit*128;
    std::size_t admitted_directory_page_limit=directory_page_limit;
    std::size_t admitted_directory_read_rows=directory_read_rows;
    std::uint64_t parent_allowance=parent_cap;
};
inline std::size_t average_shift(std::size_t denominator_shift,std::size_t past_actions) {
    require(past_actions<reach_operand_bits/grid_bits && grid_bits*(past_actions+1)<=denominator_shift,
        "fixed average row shift exceeds admitted actor depth");
    return denominator_shift-grid_bits*(past_actions+1);
}
inline std::size_t regret_shift(std::size_t horizon,std::size_t opponent_past,std::size_t suffix) {
    require(suffix>0 && suffix<=horizon && opponent_past<=horizon-suffix,
        "fixed regret row shift exceeds admitted decision horizon");
    return grid_bits*(horizon-opponent_past-suffix);
}
inline constexpr std::size_t header_words=16, literal_bytes=96, row_bytes=24;
inline constexpr std::size_t footer_words=64;
inline std::uint64_t artifact_bytes(const Counts& c,bool split,std::size_t requested_sweeps=sweeps) {
    const auto checkpoint_words=split?0:2*integer_words;
    return 8+8*header_words+8*integer_words+literal_count*literal_bytes+c.rows*row_bytes+
        requested_sweeps*(8*c.slots*(1+checkpoint_words)+4*8*(integer_words+1))+
        8*c.slots+c.rows+8+8*footer_words;
}

inline std::uint64_t compact_artifact_bytes(const Counts& c) {
    require(c.slots>=c.rows,"compact row geometry");
    return 8+8*header_words+8*integer_words+literal_count*literal_bytes+
        6*c.rows+2*4*8*(integer_words+1)+14*(c.slots-c.rows)+(c.rows+7)/8+8+8*footer_words;
}

inline std::uint64_t compact_encoding_work(const Counts& c) {
    constexpr auto limit=std::numeric_limits<std::uint64_t>::max();
    require(c.rows<=limit/224 && c.slots<=limit/128,"compact encoding dimensions overflow");
    const auto rows=208*c.rows+16*((c.rows+7)/8);
    const auto slots=64*c.slots;
    require(slots<=limit-rows,"compact encoding work overflow");
    return rows+slots;
}

class Forecast final {
    struct Suffix { std::size_t decisions=0,uniform=0; unsigned mark=0; };
    const betting::Template& source_;
    Meter& meter_;
    Plan plan_{};
    std::array<Suffix,template_count> suffix_{};
    std::size_t literals_=0;
    std::uint64_t payoff_ceiling_=0;
    std::uint64_t contractions_=0;
    std::array<std::uint64_t,64> rank_sets_{};

    void prefixes(const Prefix& prefix,Support support) {
        meter_.charge(Work::geometry,64);
        auto& row=plan_.prefixes[street_index(prefix.size)];
        ++row.count;
        std::array<unsigned,2> unblocked{};
        for (std::size_t p=0;p<2;++p) {
            row.supported[p]+=count_supported(support[p]);
            for (const auto hand:hand_masks[p]) if (!(hand&prefix.mask)) ++unblocked[p];
        }
        ++row.unblocked[unblocked[0]][unblocked[1]];
        if (prefix.size==5) {
            if (plan_.rank_board_sets) {
                const auto end=rank_sets_.begin()+plan_.rank_planes;
                meter_.charge(Work::geometry,2*(plan_.rank_planes+1));
                if (std::find(rank_sets_.begin(),end,prefix.mask)!=end) return;
                require(plan_.rank_planes<rank_sets_.size(),"rank board-set census exceeds cache capacity");
                rank_sets_[plan_.rank_planes]=prefix.mask;
            }
            ++plan_.rank_planes;
            plan_.expected_rank_calls+=unblocked[0]+unblocked[1];
            return;
        }
        const auto deck=plan_.game().deck;
        meter_.charge(Work::geometry,64*candidate_count(deck.size(),prefix.size));
        reveal(deck,prefix,[&](const Prefix& next) {
            const auto live=physical_support(next.mask);
            if (live[0]) prefixes(next,live);
        });
    }
    const Suffix& suffix(std::size_t id) {
        meter_.charge(Work::geometry,48);
        require(id<source_.nodes().size(),"pinned suffix source edge");
        auto& result=suffix_[id];
        if (result.mark==2) return result;
        require(!result.mark,"pinned suffix cycle");
        result.mark=1;
        const auto& node=source_.nodes()[id];
        const auto menu=node.edges.size();
        if (node.state.phase==betting::Phase::decision) require(menu>=2 && menu<=4 && node.state.actor<2,"pinned decision menu");
        else require(menu==(node.state.phase==betting::Phase::reveal?1U:0U),"pinned source phase");
        for (const auto& edge:node.edges) {
            const auto& tail=suffix(edge.child);
            result.decisions=std::max(result.decisions,tail.decisions);
            result.uniform=std::max(result.uniform,tail.uniform);
        }
        if (node.state.phase==betting::Phase::decision) {
            ++result.decisions;
            result.uniform+=uniform_exponent(menu);
        }
        result.mark=2;
        return result;
    }
    std::uint64_t chance_cost(bool showdown,std::size_t size,std::size_t target,std::size_t exp) {
        const auto& population=plan_.prefixes[street_index(size)].unblocked;
        const auto lookup=plan_.indexed_cache?prepared::PreparedPublicChance::sorted_lookup_work(plan_.rank_planes):
            plan_.rank_board_sets?prepared::PreparedPublicChance::board_set_probe_work*plan_.rank_planes:6*64;
        std::uint64_t sum=0;
        for (std::size_t sb=0;sb<3;++sb) for (std::size_t bb=0;bb<3;++bb) {
            meter_.charge(Work::geometry,8);
            if (!population[sb][bb]) continue;
            meter_.charge(Work::geometry,96);
            const auto own=target?bb:sb, opp=target?sb:bb, reach=exp+1;
            // All unblocked opponent rows may have a full-width positive reach.
            // Both normalized ranges have weights of at most four bits.
            const auto bucket=4+reach+logceil(opp)+4, out=4+bucket;
            const auto input=12+(6+size)+2*(4+2*words(reach))+4;
            const auto bucket_count=showdown?2+own:1;
            const auto dynamic=plan_.sparse_chance?
                prepared::PreparedPublicChance::sparse_pairs_dynamic_cost(2,2,own,opp,
                    opp*mul_cost(4,reach),bucket,out,4,
                    showdown?chance::TerminalKind::showdown:chance::TerminalKind::fold):
                12+opp*mul_cost(4,reach)+53*bucket_count+
                (showdown?9:3)*opp*add_cost(bucket)+
                own*((showdown?12:3)*add_cost(bucket)+mul_cost(4,bucket)+copy_cost(out)+2*words(bucket))+128;
            // This is the full lookup bound. Miss construction is admitted separately.
            sum+=population[sb][bb]*(input+dynamic+(showdown?lookup:0));
        }
        return sum;
    }
    std::uint64_t quantizer_cost(std::size_t n,std::size_t effective,std::size_t value_bits) const {
        const auto sum=effective+logceil(n)+1,scaled=effective+grid_bits;
        const auto bits=std::max({std::size_t{53},sum,scaled});
        return 64+16*n+4*n*(words(value_bits)+1)+256+16*n*(words(bits)+1)+
            8*n*((plan_.single_division?1:2)*words(scaled)*words(sum)+4*words(bits)+8)+4*n*n*(words(sum)+1);
    }
    void literal(std::size_t id,std::array<std::size_t,2> past,std::array<std::size_t,2> first) {
        meter_.charge(Work::geometry,256);
        require(++literals_<=literal_count && id<source_.nodes().size(),"pinned literal census changed");
        const auto& node=source_.nodes()[id];
        const auto value_bits=plan_.game().value_bits,deck_size=plan_.game().deck.size();
        const auto k=static_cast<std::size_t>(node.state.street);
        const auto population=plan_.prefixes[street_index(k)];
        const auto m=node.edges.size(),np=population.count;
        auto& shape=plan_.shape;
        auto& work=plan_.parent;
        shape.visits+=np;
        if (node.state.phase==betting::Phase::decision) {
            const auto actor=node.state.actor;
            require(actor<2 && m>=2 && m<=4,"pinned decision census");
            const auto rows=population.supported[actor],slots=rows*m;
            shape.rows+=rows;
            shape.slots+=slots;
            shape.actions+=np*m;
        const auto E=first[1-actor]+suffix_[id].uniform;
            const auto EA=grid_bits*(past[actor]+1);
            const auto base_bits=width(plan_.denominator_base);
            // First regrets have the common 2^(shift-M-E) divisor. Average
            // masses have the common 2^(shift-EA) divisor for both sweeps.
            require(E+plan_.M<=plan_.shift && EA<=plan_.shift,"pinned fixed-scale divisibility forecast");
            if (plan_.packed_averages)
                plan_.packed_average_limbs+=slots*words(value_bits-(plan_.shift-EA));
            if (plan_.packed_regrets) {
                const auto shift=regret_shift(plan_.H,past[1-actor],suffix_[id].decisions);
                plan_.packed_regret_limbs+=slots*words(value_bits-shift);
            }
            plan_.quantizer_terms[0]+=rows*(320+48*m);
            plan_.quantizer_terms[1]+=rows*quantizer_cost(m,base_bits+2+width(payoff_ceiling_)+plan_.M+E,value_bits);
            plan_.quantizer_terms[2]+=rows*quantizer_cost(m,
                base_bits+(plan_.proof9_q32_base()?(plan_.proof9_linear32()?9:5):2)+EA,value_bits);
            for (std::size_t sweep=2;sweep<plan_.requested_sweeps;++sweep) {
                const auto shift=regret_shift(plan_.H,past[1-actor],suffix_[id].decisions);
                plan_.general_quantizer_work+=rows*quantizer_cost(m,value_bits-shift,value_bits);
            }
            plan_.max_actor_depth[actor]=std::max(plan_.max_actor_depth[actor],past[actor]+1);
            work[work_index(Work::reach)]+=plan_.public_walks*np*m*(24+2*(mul_cost(reach_operand_bits,53)+copy_cost(reach_operand_bits)));
            work[work_index(Work::value_add)]+=plan_.requested_sweeps*np*m*2*add_cost(value_bits);
            if (plan_.scaled_averages) {
                const auto build=plan_.requested_sweeps*rows*(scaled_average_cost(grid_bits*past[actor],
                    plan_.proof9_linear32()?15:base_bits,m)+(plan_.proof9_linear32()?8:0));
                plan_.scaled_average_build_work+=build;
                work[work_index(Work::average)]+=build;
            } else {
                work[work_index(Work::average)]+=plan_.requested_sweeps*slots*(16+3*mul_cost(value_bits,53)+copy_cost(value_bits));
            }
            ++past[actor];
            first[actor]+=uniform_exponent(m);
        } else if (node.state.phase==betting::Phase::reveal) {
            const auto next=node.state.next_street;
            require(m==1 && next==(k?k+1:3),"pinned reveal census");
            const auto child=plan_.prefixes[street_index(next)].count;
            shape.reveals+=child;
            shape.candidates+=np*candidate_count(deck_size,k);
            work[work_index(Work::value_add)]+=plan_.seat_passes*child*2*add_cost(value_bits);
            for (std::size_t target=0;target<2;++target) contractions_+=plan_.requested_sweeps*chance_cost(false,next,target,0);
        } else {
            const auto showdown=node.state.phase==betting::Phase::showdown;
            require(!m && (showdown?node.state.winner==2:node.state.phase==betting::Phase::fold && node.state.winner<2),"pinned terminal census");
            (showdown?shape.showdowns:shape.folds)+=np;
            if (showdown) {
                const auto full=plan_.prefixes[3].count;
                plan_.showdown_contractions+=full;
                if (k<5) {
                    constexpr std::array<std::size_t,3> visible{0,3,4};
                    for (auto street=street_index(k);street<visible.size();++street)
                        plan_.hidden_candidates+=plan_.prefixes[street].count*candidate_count(deck_size,visible[street]);
                    work[work_index(Work::value_add)]+=plan_.seat_passes*full*2*add_cost(value_bits);
                }
            }
            for (std::size_t target=0;target<2;++target) {
                contractions_+=chance_cost(showdown,showdown?5:k,target,first[1-target]);
                contractions_+=chance_cost(showdown,showdown?5:k,target,grid_bits*past[1-target]);
                if (plan_.proof9_q32_base()) {
                    // All later grid-policy operands share the same full-width
                    // bound. Census that bound once and multiply its lifetime.
                    contractions_+=(plan_.requested_sweeps-2)*
                        chance_cost(showdown,showdown?5:k,target,grid_bits*past[1-target]);
                } else for (std::size_t sweep=2;sweep<plan_.requested_sweeps;++sweep)
                    contractions_+=chance_cost(showdown,showdown?5:k,target,grid_bits*past[1-target]);
            }
            work[work_index(Work::terminal_scale)]+=plan_.seat_passes*np*2*(16+mul_cost(value_bits,plan_.pay_bits)+mul_cost(value_bits,6)+copy_cost(value_bits));
        }
        for (const auto& edge:node.edges) literal(edge.child,past,first);
    }
    void prior_geometry() {
        // Reconstruct normalized integer weights from the exact binary64
        // source images and check the fixed fixture's single scalar prior Z.
        meter_.charge(Work::geometry,4096);
        std::array<std::array<std::uint64_t,2>,2> weights{};
        for (std::size_t p=0;p<2;++p) {
            std::array<Money,2> exact{};
            for (std::size_t i=0;i<2;++i) {
                const auto parts=chance::prior::decode_parts(ranges[p][i].binary64_weight_bits,false,false,"invalid pinned range weight");
                const auto trailing=std::countr_zero(parts.significand);
                exact[i]={parts.significand>>trailing,parts.exponent+trailing};
            }
            const auto common=std::min(exact[0].power,exact[1].power);
            for (std::size_t i=0;i<2;++i) {
                const auto shift=exact[i].power-common;
                require(shift>=0 && shift<4 && width(exact[i].significand)+static_cast<unsigned>(shift)<=4,"pinned normalized weight width");
                weights[p][i]=exact[i].significand<<static_cast<unsigned>(shift);
            }
        }
        for (std::size_t sb=0;sb<2;++sb) for (std::size_t bb=0;bb<2;++bb)
            if (!(hand_masks[0][sb]&hand_masks[1][bb])) plan_.normalizer+=weights[0][sb]*weights[1][bb];
        const auto& game=plan_.game();
        const auto remaining=game.deck.size()-4;
        const auto flop=remaining*(remaining-1)*(remaining-2)/6;
        require(game.divisors==std::array<std::uint64_t,4>{1,flop,flop*(remaining-3),flop*(remaining-3)*(remaining-4)},"pinned chance divisor drift");
        plan_.denominator_base=plan_.normalizer*game.divisors[3];
        require(plan_.normalizer==29 && plan_.denominator_base==(plan_.ten_card()?3480u:580u),"pinned root prior changed");
    }
public:
    Forecast(const betting::Template& source,Meter& meter,Traversal mode,StrategyProfile profile)
        :source_(source),meter_(meter) {
        require(profile==StrategyProfile::dense || mode==Traversal::paired,
            "invalid packed training profile");
        plan_.traversal=mode;
        const bool t3=profile==StrategyProfile::proof9_three_sweep;
        const bool t4=profile==StrategyProfile::proof9_four_sweep;
        const bool linear32=profile==StrategyProfile::proof9_linear32;
        const bool q32=profile==StrategyProfile::proof9_quality32 || linear32;
        const bool bounded=t3||t4||q32;
        if (bounded) {
            plan_.fixture=q32?&proof9_q32:t3?&proof9_t3:&proof9_t4;
            plan_.linear_average=linear32;
            plan_.requested_sweeps=plan_.fixture->requested_sweeps;
            plan_.seat_passes=targets*plan_.requested_sweeps;
            meter_.bootstrap_ceiling(q32?proof9_q32_parent_cap:t3?proof9_t3_parent_cap:proof9_t4_parent_cap);
        }
        plan_.compact_wire=profile==StrategyProfile::ten_card_compact_wire;
        plan_.complement_division=profile==StrategyProfile::ten_card_complement || plan_.compact_wire;
        plan_.indexed_cache=profile==StrategyProfile::ten_card_indexed_cache || plan_.complement_division;
        plan_.row_batched=profile==StrategyProfile::ten_card_row_batched || plan_.indexed_cache || q32;
        plan_.phase_payload=profile==StrategyProfile::ten_card_phase_payload || (plan_.row_batched && !q32);
        plan_.single_division=profile==StrategyProfile::ten_card_single_division || plan_.phase_payload || q32;
        plan_.sparse_chance=profile==StrategyProfile::ten_card_sparse_chance || plan_.single_division;
        plan_.paged_directory=profile==StrategyProfile::ten_card_paged_directory || bounded || plan_.sparse_chance;
        plan_.shared_policy=profile==StrategyProfile::ten_card_shared_policy || plan_.paged_directory;
        plan_.row_coverage=profile==StrategyProfile::ten_card_row_coverage || plan_.shared_policy;
        plan_.ordered_state=profile==StrategyProfile::ten_card_ordered_state || plan_.row_coverage;
        const bool virtual_zero=profile==StrategyProfile::ten_card_virtual_zero || plan_.ordered_state || bounded;
        const bool buffered=profile==StrategyProfile::ten_card_buffered || virtual_zero;
        if (profile==StrategyProfile::ten_card || (buffered && !bounded)) plan_.fixture=&proof10;
        if (buffered) plan_.page_limits.write_requests=q32?paging::n9_q32_write_requests:t3?5931:t4?paging::n9_t4_write_requests:virtual_zero?18836:19560;
        plan_.page_limits.virtual_initial_zero=virtual_zero;
        plan_.packed_averages=profile!=StrategyProfile::dense;
        plan_.split_checkpoint=profile==StrategyProfile::split_checkpoint || plan_.ten_card() || bounded;
        require(!plan_.split_checkpoint || (q32 || plan_.requested_sweeps<=4),"split checkpoint sweep count exceeds fixed receipt");
        plan_.rank_board_sets=profile==StrategyProfile::rank_sets || plan_.split_checkpoint;
        plan_.compact_directory=profile==StrategyProfile::directory || plan_.rank_board_sets;
        plan_.paged_strategy=profile==StrategyProfile::paged || plan_.compact_directory;
        plan_.sealed_menus=profile==StrategyProfile::sealed || plan_.paged_strategy;
        plan_.scaled_averages=profile==StrategyProfile::scaled || plan_.sealed_menus;
        plan_.packed_regrets=profile==StrategyProfile::compact || plan_.scaled_averages;
        plan_.public_walks=mode==Traversal::paired?plan_.requested_sweeps:plan_.seat_passes;
    }
    Plan make() {
        const bool t3=plan_.proof9_three_sweep();
        const bool t4=plan_.proof9_four_sweep();
        const bool q32=plan_.proof9_q32_base();
        const bool bounded=t3||t4||q32;
        const auto& game=plan_.game();
        const auto value_bits=game.value_bits;
        const auto& template_receipt=source_.receipt();
        require(template_receipt.nodes==template_count && template_receipt.edges==410 &&
            template_receipt.logical_occurrences==literal_count && template_receipt.max_depth==15 &&
            !template_receipt.history_suffix_only,"pinned betting source shape changed");
        meter_.charge(Work::geometry,256*template_count);
        prior_geometry();
        // Terminal scaling combines a stake significand (at most 16) with
        // one exact street-divisor ratio before multiplying the wide value.
        const auto full_divisor=game.divisors.back();
        require(full_divisor<=std::numeric_limits<std::uint64_t>::max()/16,
            "pinned terminal scale exceeds uint64");
        for (const auto divisor:game.divisors)
            require(divisor && full_divisor%divisor==0,"pinned terminal divisor must divide the full divisor");
        prefixes(Prefix{},physical_support(0));
        const auto& p=plan_.prefixes;
        for (std::size_t i=0;i<p.size();++i)
            require(p[i].count==game.prefix_counts[i],"pinned physical prefix census changed");
        require(plan_.rank_board_sets?(plan_.rank_planes==game.rank_planes && plan_.expected_rank_calls==game.rank_calls):
            (plan_.rank_planes==60 && plan_.expected_rank_calls==140),"pinned rank-plane census changed");
        for (const auto& node:source_.nodes()) if (node.state.phase==betting::Phase::fold || node.state.phase==betting::Phase::showdown) {
            const auto money=stake(node.state);
            require(money.power>=-1 && money.power<=3 && money.significand<=16,"pinned terminal money range changed");
            plan_.M=std::max(plan_.M,static_cast<std::size_t>(std::max(0,-money.power)));
            plan_.pay_bits=std::max(plan_.pay_bits,width(money.significand));
            const auto ceiling=money.power<0?(money.significand+1)/2:money.significand<<static_cast<unsigned>(money.power);
            payoff_ceiling_=std::max(payoff_ceiling_,ceiling);
        }
        const auto& tail=suffix(source_.root());
        plan_.H=tail.decisions;
        plan_.max_first_exponent=tail.uniform;
        plan_.shift=grid_bits*plan_.H+plan_.M;
        plan_.denominator_bits=width(plan_.denominator_base)+plan_.shift;
        require(plan_.H==12 && plan_.M==1 && payoff_ceiling_==8 && plan_.max_first_exponent==420 &&
            plan_.denominator_bits==game.denominator_bits && (q32?plan_.denominator_bits+9:plan_.denominator_bits+width(payoff_ceiling_)+3)==value_bits,
            "pinned fixed denominator bounds changed");
        if (plan_.packed_regrets) {
            for (std::size_t id=0;id<source_.nodes().size();++id) {
                meter_.charge(Work::geometry,8);
                require(suffix_[id].mark==2 && suffix_[id].decisions<=plan_.H,"packed regret suffix census changed");
                plan_.suffix_decisions[id]=static_cast<std::uint8_t>(suffix_[id].decisions);
                if (plan_.sealed_menus) {
                    meter_.charge(Work::geometry,8);
                    const auto& node=source_.nodes()[id];
                    if (node.state.phase==betting::Phase::decision) {
                        ++plan_.sealed_menu_count;
                        plan_.sealed_token_count+=node.edges.size();
                    }
                }
            }
        }
        literal(source_.root(),{},{});
        require(literals_==literal_count && plan_.shape==game.shape && plan_.max_actor_depth==std::array<std::size_t,2>{6,7} &&
            plan_.showdown_contractions==game.showdown_completions && plan_.hidden_candidates==game.hidden_candidates,
            "pinned complete geometry changed");
        for (std::size_t target=0;target<2;++target) contractions_+=plan_.requested_sweeps*chance_cost(false,0,target,0);

        const auto& g=plan_.shape;
        const auto R=g.rows,S=g.slots;
        plan_.template_work=template_receipt.work;
        // Setup bound covers the existing 21,504-unit prior constructor and
        // fixed four-holding copies/normalization. At most 60 misses retain
        // every physically supported ordered board in the 64-plane owner.
        plan_.chance_work=chance_setup_bound+contractions_+
            (plan_.rank_board_sets?4096*plan_.expected_rank_calls+plan_.rank_planes*(512+64+4*plan_.rank_planes):
                p[3].count*(4*4096+512+64+4*64));
        if (plan_.indexed_cache)
            plan_.chance_work+=prepared::PreparedPublicChance::index_setup_work(plan_.rank_planes)+
                plan_.rank_planes*prepared::PreparedPublicChance::index_update_work(plan_.rank_planes);
        const auto public_walks=plan_.public_walks;
        plan_.history_work=4096*literal_count+1280+(public_walks+1)*(40*g.actions+72*g.reveals+48*g.visits+40*R);
        const auto lookup=plan_.paged_directory?32:16*logceil(static_cast<std::size_t>(R+1));
        auto registration_work=256*S;
        if (plan_.sealed_menus) {
            const auto M=plan_.sealed_menu_count,T=plan_.sealed_token_count;
            require(M>0 && M<=template_count && T>=2*M && T<=template_receipt.edges,
                "sealed action catalog census changed");
            plan_.history_work=plan_.history_work-8*R+24*M+16*T;
            registration_work=64*M+16*T+16*R;
            const auto catalog_objects=template_receipt.nodes+template_receipt.edges;
            if (catalog_objects>S) registration_work+=16*(catalog_objects-S);
        }
        if (plan_.ordered_state) {
            plan_.registration_path_work=history::History::decision_path_work*R;
            plan_.history_work+=plan_.registration_path_work;
        }
        plan_.state_work=1024+8*R+16*S+4*words(plan_.denominator_bits)+(128+lookup)*R+registration_work+8*S+2*R+
            plan_.requested_sweeps*(4*R+16*R+4*S+64*R+128*S+(16*S+8*R)*words(value_bits+58)+4*R)+
            (4*words(value_bits)+4)*S+20*R+4*S;
        for (const auto work:plan_.quantizer_terms) plan_.quantizer_work+=work;
        plan_.quantizer_work+=plan_.general_quantizer_work;
        auto& w=plan_.parent;
        w[work_index(Work::geometry)]=3000000;
        w[work_index(Work::visit)]=(8+public_walks*visit_cost(plan_.traversal))*g.visits;
        w[work_index(Work::support)]=64*((public_walks+1)*g.candidates+public_walks*plan_.hidden_candidates);
        w[work_index(Work::route)]=public_walks*16*R+16*R+4*S;
        w[work_index(Work::average)]+=plan_.seat_passes*(g.reveals+1)*24;
        if (plan_.packed_averages) {
            require(plan_.packed_average_limbs>=S && plan_.packed_average_limbs<=words(value_bits)*S,
                "packed average word census outside fixed bounds");
            // Precharge fixed storage codec operations in addition to the
            // original conservative state charge. No training occurs here.
            // A scaled stage only loads, adds and stores compact limbs. The
            // checkpoint still expands twice and the export decodes once.
            const auto wide_word_factor=plan_.scaled_averages?6:14;
            plan_.packed_average_work=32*R+36*plan_.packed_average_limbs+(wide_word_factor*words(value_bits)+70)*S;
            if (bounded) plan_.packed_average_work=(plan_.requested_sweeps*plan_.packed_average_work+1)/2;
            w[work_index(Work::average)]+=plan_.packed_average_work;
        }
        if (plan_.packed_regrets) {
            require(plan_.packed_regret_limbs>=S && plan_.packed_regret_limbs<=words(value_bits)*S,
                "packed regret word census outside fixed bounds");
            // Covers two signed-delta staging passes, two full checkpoint
            // reads, two compact policy decodes, layout and routing. The
            // original state charge still covers mix and update arithmetic.
            plan_.packed_regret_work=32*R+44*plan_.packed_regret_limbs+(16*words(value_bits)+88)*S;
            if (bounded) plan_.packed_regret_work=(plan_.requested_sweeps*plan_.packed_regret_work+1)/2;
            w[work_index(Work::route)]+=plan_.packed_regret_work;
        }
        if (plan_.paged_strategy) {
            const auto A=plan_.packed_average_limbs,G=plan_.packed_regret_limbs,L=A+G;
            // The two page files retain sweep 1 and sweep 2. The split
            // stream skips both fields of both checkpoint scans.
            const auto request_units=plan_.row_batched?R:S;
            const auto requests=(plan_.split_checkpoint?11:15)*request_units;
            const bool virtual_zero=plan_.page_limits.virtual_initial_zero;
            const auto read_words=q32?paging::n9_q32_read_words:t4?paging::n9_t4_read_words:t3?2223164u:virtual_zero?6130244u:
                plan_.ten_card()?paging::n10_read_words:plan_.split_checkpoint?2250000u:3500000u;
            const auto write_requests=q32?paging::n9_q32_write_requests:t4?paging::n9_t4_write_requests:plan_.page_limits.write_requests;
            plan_.page_limits={static_cast<std::size_t>(L),4096,16,read_words,
                q32?paging::n9_q32_write_words:t4?paging::n9_t4_write_words:t3?1820190u:(virtual_zero?2:3)*L,
                q32?paging::n9_q32_logical_requests:t4?paging::n9_t4_logical_requests:t3?930624u:requests,2,
                q32?paging::Profile::proof9_q32:t4?paging::Profile::proof9_t4:plan_.ten_card()?paging::Profile::proof10:paging::Profile::legacy,
                q32?paging::n9_q32_stage_split_words:t4?paging::n9_t4_stage_split_words:write_requests?static_cast<std::size_t>(A):0,write_requests,virtual_zero};
            // Arithmetic bookkeeping for bounded requests, scratch copies,
            // write-once bits, initialization chunks and bitmap resets.
            // Physical file traffic has its own independent word ceilings.
            const auto initialization_chunks=virtual_zero?0:(L+4095)/4096;
            const auto coverage_reset_work=plan_.row_coverage?0:8*((L+63)/64);
            if (t3) {
                plan_.page_limits.stage_split_words=static_cast<std::size_t>(A);
                plan_.page_limits.write_requests=5931;
            }
            plan_.paging_work=bounded?16*plan_.page_limits.requests+plan_.requested_sweeps*(5*A+6*G)+
                    8*plan_.requested_sweeps*L:
                16*requests+2*(5*A+6*G)+16*L+16*initialization_chunks+coverage_reset_work;
            if (write_requests) {
                // Up to two page fragments per staged extent, one copy and
                // mark per staged word, and at most 64 bitmap words to scan
                // and clear per nonempty flush, plus bookkeeping per run.
                plan_.paging_work+=8*(2*plan_.requested_sweeps*request_units)+2*plan_.requested_sweeps*L+160*write_requests+2*(4096+64+1);
            }
            w[work_index(Work::route)]+=plan_.paging_work;
        }
        if (plan_.shared_policy) {
            // One build and three read passes. Every row can require spill.
            plan_.policy_spill_work=plan_.requested_sweeps*(32*R+16*(S-R)+4*S)+64;
            w[work_index(Work::route)]+=plan_.policy_spill_work;
        }
        if (plan_.compact_directory) {
            // Table initialization plus compact row encode/decode across both
            // sweeps and checkpoint export. Probes use the existing lookup budget.
            if (bounded) {
                plan_.admitted_directory_page_limit=proof9_t3_directory_page_limit;
                if (t4) plan_.admitted_directory_page_limit=state::proof9_t4_directory_page_limit;
                if (q32) plan_.admitted_directory_page_limit=state::State::proof9_q32_directory_page_limit;
                plan_.admitted_directory_read_rows=plan_.admitted_directory_page_limit*128;
            }
            plan_.directory_work=plan_.paged_directory?
                4*state::State::row_directory_resident_entries+16*R+
                    16*(bounded?(2+4*plan_.requested_sweeps):10)*R+4*plan_.admitted_directory_read_rows:96*R;
            w[work_index(Work::route)]+=plan_.directory_work;
        }
        // Fixed-width limb emission, two policy-image checks, literal BFS
        // records, and the bounded header/footer. No per-row history rendering.
        const auto wide_output=plan_.split_checkpoint?0:4*S*(4+2*integer_words);
        w[work_index(Work::output)]=wide_output+3*S*2+24*R+
            plan_.requested_sweeps*(6*S+32*R)+160*literal_count+65536;
        if (q32) w[work_index(Work::output)]+=plan_.requested_sweeps*sizeof(state::PolicySpillSweep);
        const auto other_work=plan_.template_work+plan_.chance_work+plan_.history_work+
            plan_.state_work+plan_.quantizer_work;
        require(other_work<=game.work_limit,"fixed non-parent work exceeds aggregate cap");
        if (plan_.packed_regrets) plan_.parent_allowance=game.work_limit-other_work;
        plan_.total_work=other_work+sum_work(w);
        plan_.state_entries=1024+16*R+10*S;
        plan_.state_payload=(5*S+256)*(value_bits+58)+640*S+16*R;
        if (plan_.packed_averages) {
            const auto storage=state::State::storage_forecast(
                {static_cast<std::size_t>(R),static_cast<std::size_t>(S),plan_.requested_sweeps,15,value_bits,
            plan_.state_work,plan_.quantizer_work},
                {template_receipt.nodes,template_receipt.edges,plan_.sealed_menus},{static_cast<std::size_t>(plan_.packed_average_limbs),
                 static_cast<std::size_t>(plan_.packed_regret_limbs)},
                plan_.paged_strategy?std::optional<paging::Limits>{plan_.page_limits}:std::nullopt,
                plan_.compact_directory,plan_.ordered_state,plan_.row_coverage,plan_.shared_policy,plan_.paged_directory,
                q32?state::Lifecycle::quality32:bounded?state::Lifecycle::bounded_v1:state::Lifecycle::fixed_two_sweep,
                plan_.phase_payload?state::PayloadModel::paged_phases:state::PayloadModel::legacy,plan_.row_batched);
            plan_.state_entries=storage.entries;
            plan_.state_payload=storage.payload_bits;
        }
        plan_.entries=plan_.state_entries+template_receipt.entries+template_receipt.peak_scratch_entries+
            chance_entries+32*literal_count+1+parent_entries+(plan_.shared_policy?Plan::policy_frame_entries:0)+
            (plan_.paged_directory?Plan::directory_frame_entries:0);
        plan_.payload_bits=plan_.state_payload+chance_payload+8*history_bytes+parent_payload+32*181;
        plan_.output_bytes=plan_.compact_wire?compact_artifact_bytes(g):artifact_bytes(g,plan_.split_checkpoint,plan_.requested_sweeps);
        if (bounded) {
            plan_.entries+=sweep_stream_entries;
            plan_.payload_bits+=sweep_stream_payload_bits;
            if (q32) {
                plan_.entries+=plan_.requested_sweeps*sizeof(state::PolicySpillSweep)/8;
                plan_.payload_bits+=8*plan_.requested_sweeps*sizeof(state::PolicySpillSweep);
            }
            if (t4) {
                // Driver returns a bounded copy of the per-sweep sidecar in
                // addition to State's own generation receipts.
                plan_.entries+=8;
                plan_.payload_bits+=512;
            }
            require(q32 || plan_.general_quantizer_work==(t4?proof9_t4_general_quantizer_expected:
                proof9_t3_general_quantizer_expected),"bounded PROOF9 general quantizer forecast changed");
            // R_t <= 16tD. The Q32 multiplier 512 is exactly 2^9.
            require(q32?(2*payoff_ceiling_*plan_.requested_sweeps==512 &&
                plan_.denominator_bits+9<=value_bits):
                plan_.denominator_bits+width(2*payoff_ceiling_*plan_.requested_sweeps)<=value_bits,
                "bounded PROOF9 retained value width exceeds fixed integer");
            require(plan_.parent_allowance==game.work_limit-other_work,
                "bounded PROOF9 parent allowance setup changed");
        }
        require(plan_.template_work<=template_cap,"pinned template forecast exceeds fixture cap");
        require(plan_.chance_work<=game.chance_limit,"pinned chance forecast exceeds fixture cap");
        require(plan_.history_work<=game.history_limit,"pinned history forecast exceeds fixture cap");
        require(plan_.state_work<=game.state_limit,"pinned state forecast exceeds fixture cap");
        require(plan_.quantizer_work<=game.quantizer_limit,"pinned quantizer forecast exceeds fixture cap");
        require(sum_work(w)<=plan_.parent_allowance,"pinned parent forecast exceeds parent allowance");
        require(plan_.total_work<=game.work_limit,"pinned total forecast exceeds fixture cap");
        require(plan_.entries<=entries_cap,"pinned entry forecast exceeds fixture cap");
        require(plan_.payload_bits<=game.payload_limit,"pinned payload forecast exceeds fixture cap");
        require(value_bits+58<=65536 && plan_.output_bytes<=game.output_limit,
            "pinned value width or output forecast exceeds fixture cap");
        meter_.seal(w,plan_.parent_allowance);
        return plan_;
    }
};

struct Reach { Values numerators{1,1}; std::size_t exponent=0; };
struct Marginal { Values numerators{}; std::uint64_t scale=0; };

template<bool Paired> class Walk final {
    static constexpr std::size_t lanes=Paired?targets:1;
    using LaneValues=std::array<Values,lanes>;
    using Marginals=std::array<Marginal,lanes>;
    const betting::Template& source_;
    const Plan& plan_;
    Meter& meter_;
    history::History& history_;
    prepared::PreparedPublicChance& chance_;
    state::State& state_;
    std::size_t target_;
    const std::size_t averaging_sweep_;
    Counts shape_{};
    std::uint64_t showdown_contractions_=0,hidden_candidates_=0;
    static constexpr std::size_t catalog=targets;

    [[nodiscard]] std::size_t seat(std::size_t lane) const { return Paired?lane:target_; }
    static const Reach& opposite(std::size_t player,const Reach& sb,const Reach& bb) { return player?sb:bb; }

    void add_values(Values& total,const Values& child) {
        meter_.charge(Work::value_add,2*add_cost(plan_.game().value_bits));
        for (std::size_t holding=0;holding<2;++holding) total[holding]+=child[holding];
    }
    void add_lanes(LaneValues& total,const LaneValues& child) {
        for (std::size_t lane=0;lane<lanes;++lane) add_values(total[lane],child[lane]);
    }
    prepared::Contraction contraction(std::size_t target,const Prefix& prefix,chance::TerminalKind kind,const Reach& reach) {
        auto result=chance_.contraction(target,prefix.view(),kind,reach.numerators,reach.exponent);
        require(result.numerators.size()==2 && result.reach_exponent==reach.exponent &&
            result.prefix_divisor==plan_.game().divisors[street_index(prefix.size)],"prepared contraction identity changed");
        return result;
    }
    Marginals marginal(const Prefix& prefix,Support support) {
        Marginals masses{};
        for (std::size_t lane=0;lane<lanes;++lane) {
            meter_.charge(Work::average,24);
            const auto target=seat(lane);
            auto result=contraction(target,prefix,chance::TerminalKind::fold,Reach{});
            auto& mass=masses[lane];
            mass.scale=plan_.game().divisors[3]/result.prefix_divisor;
            for (std::size_t holding=0;holding<2;++holding) {
                const auto& value=result.numerators[holding];
                require(value>=0 && (value>0)==bool(support[target]&(1U<<holding)),"prior own marginal support changed");
                mass.numerators[holding]=std::move(result.numerators[holding]);
            }
        }
        return masses;
    }
    LaneValues ranked(const Prefix& board,const Reach& sb,const Reach& bb) {
        require(board.size==5 && ++showdown_contractions_<=plan_.showdown_contractions,"ranked completion census changed");
        LaneValues values{};
        for (std::size_t lane=0;lane<lanes;++lane) {
            const auto target=seat(lane);
            auto result=contraction(target,board,chance::TerminalKind::showdown,opposite(target,sb,bb));
            values[lane]={std::move(result.numerators[0]),std::move(result.numerators[1])};
        }
        return values;
    }
    void hidden_completions(const Prefix& prefix,const Reach& sb,const Reach& bb,LaneValues& sum) {
        if (prefix.size==5) {
            add_lanes(sum,ranked(prefix,sb,bb));
            return;
        }
        const auto deck=plan_.game().deck;
        const auto candidates=candidate_count(deck.size(),prefix.size);
        meter_.charge(Work::support,64*candidates);
        hidden_candidates_+=candidates;
        require(hidden_candidates_<=plan_.hidden_candidates,"hidden runout candidate census changed");
        reveal(deck,prefix,[&](const Prefix& next) {
            if (physical_support(next.mask)[0]) hidden_completions(next,sb,bb,sum);
        });
    }
    LaneValues terminal(const betting::State& node,const Prefix& prefix,const Reach& sb,const Reach& bb) {
        const auto& game=plan_.game();
        const auto value_bits=game.value_bits;
        meter_.charge(Work::terminal_scale,lanes*2*(16+mul_cost(value_bits,plan_.pay_bits)+mul_cost(value_bits,6)+copy_cost(value_bits)));
        const bool showdown=node.phase==betting::Phase::showdown;
        const auto money=stake(node);
        require(width(money.significand)<=plan_.pay_bits && money.power>=-static_cast<int>(plan_.M),"pinned terminal money exceeds forecast");
        std::array<unsigned,lanes> shifts{};
        for (std::size_t lane=0;lane<lanes;++lane) {
            const auto exponent=opposite(seat(lane),sb,bb).exponent;
            const auto shift=static_cast<int>(plan_.shift)-static_cast<int>(exponent)+money.power;
            require(shift>=0,"terminal outside fixed game scale");
            shifts[lane]=static_cast<unsigned>(shift);
        }
        LaneValues result{};
        if (showdown) {
            if (prefix.size==5) result=ranked(prefix,sb,bb);
            // An all-in has no later information sets. Integrate completions
            // as raw full-board numerators on one scale, with no History reveal.
            else hidden_completions(prefix,sb,bb,result);
        } else {
            for (std::size_t lane=0;lane<lanes;++lane) {
                const auto target=seat(lane);
                auto raw=contraction(target,prefix,chance::TerminalKind::fold,opposite(target,sb,bb));
                result[lane]={std::move(raw.numerators[0]),std::move(raw.numerators[1])};
            }
        }
        const auto divisor=showdown?game.divisors.back():game.divisors[street_index(prefix.size)];
        const auto factor=money.significand*(game.divisors.back()/divisor);
        for (std::size_t lane=0;lane<lanes;++lane)
            for (auto& value:result[lane]) {
                value*=factor;
                value<<=shifts[lane];
                if (!showdown && node.winner!=seat(lane)) value=-value;
            }
        return result;
    }
    Reach advance(const Reach& previous,const std::array<std::span<const std::uint64_t>,2>& policy,
                  std::size_t action,unsigned support) {
        // The pinned source has at most seven actions by any one actor.
        // Each reduced numerator is at most 2^exponent, independently of D.
        meter_.charge(Work::reach,24+2*(mul_cost(reach_operand_bits,53)+copy_cost(reach_operand_bits)));
        unsigned common=grid_bits;
        bool nonzero=false;
        std::array<std::uint64_t,2> units{};
        for (std::size_t holding=0;holding<2;++holding) if (support&(1U<<holding)) {
            units[holding]=policy[holding][action];
            if (units[holding]) {
                common=std::min(common,static_cast<unsigned>(std::countr_zero(units[holding])));
                nonzero=true;
            }
        }
        Reach next{{0,0},0};
        if (nonzero) {
            next.exponent=previous.exponent+grid_bits-common;
            require(next.exponent<reach_operand_bits,"sequence reach depth exceeds forecast");
            for (std::size_t holding=0;holding<2;++holding)
                next.numerators[holding]=previous.numerators[holding]*(units[holding]>>common);
        }
        return next;
    }
    void stage_average(std::span<Integer> out,std::span<const std::uint64_t> policy,
                       const Marginal& prior,const Reach& own,std::size_t holding) {
        require(own.exponent<=plan_.shift,"average reach exceeds fixed game exponent");
        const auto scale=plan_.shift-own.exponent;
        require(scale>=grid_bits && prior.scale,"average outside fixed game scale");
        for (std::size_t action=0;action<out.size();++action) {
            const auto value_bits=plan_.game().value_bits;
            meter_.charge(Work::average,16+3*mul_cost(value_bits,53)+copy_cost(value_bits));
            // Equal sweep weights. Keep the raw sum of own reach times the
            // frozen policy, including zeros, on the fixed game denominator.
            out[action]=prior.numerators[holding]*own.numerators[holding];
            out[action]*=policy[action];
            out[action]*=prior.scale;
            out[action]<<=scale-grid_bits;
        }
    }
    void stage_scaled_average(std::span<Integer> out,std::span<const std::uint64_t> policy,
                              const Marginal& prior,const Reach& own,std::size_t holding,
                              std::size_t row_shift) {
        require(row_shift<=plan_.shift-grid_bits,"scaled average row shift outside fixed game scale");
        const auto past_bits=plan_.shift-grid_bits-row_shift;
        meter_.charge(Work::average,scaled_average_cost(past_bits,
            plan_.proof9_linear32()?15:width(plan_.denominator_base),out.size())+(plan_.proof9_linear32()?8:0));
        require(own.exponent<=past_bits && prior.scale && prior.numerators[holding]>0 &&
            prior.numerators[holding]<=plan_.denominator_base/prior.scale,
            "scaled average reach exponent or marginal outside fixed bounds");
        const auto raw_marginal=prior.numerators[holding].convert_to<std::uint64_t>()*prior.scale;
        const auto marginal=plan_.linear_average?checked_weighted_marginal(raw_marginal,averaging_sweep_):raw_marginal;
        // The reduced own reach is at most one. Factor the row scale out
        // before multiplying by the frozen action units, including zeros.
        Integer row_base=own.numerators[holding]*marginal;
        row_base<<=past_bits-own.exponent;
        for (std::size_t action=0;action<out.size();++action) out[action]=row_base*policy[action];
    }
    LaneValues visit(std::size_t id,Cursor cursor,const Prefix& prefix,Support support,
                     const Reach& sb,const Reach& bb,const Marginals& prior,std::array<std::size_t,2> past={}) {
        meter_.charge(Work::visit,visit_cost(Paired?Traversal::paired:Traversal::by_seat));
        require(++shape_.visits<=plan_.shape.visits && support[0] && support[1] &&
            id<source_.nodes().size() && history_.source_node(cursor)==id && history_.visible_size(cursor)==prefix.size,
            "dense public visit identity changed");
        const auto& node=source_.nodes()[id];
        require(node.state.street==prefix.size,"dense visible street changed");
        if (node.state.phase==betting::Phase::reveal) {
            LaneValues result{};
            const auto deck=plan_.game().deck;
            const auto candidates=candidate_count(deck.size(),prefix.size);
            meter_.charge(Work::support,64*candidates);
            shape_.candidates+=candidates;
            require(shape_.candidates<=plan_.shape.candidates && node.edges.size()==1,"dense reveal candidate census changed");
            reveal(deck,prefix,[&](const Prefix& next) {
                const auto live=physical_support(next.mask);
                if (!live[0]) return; // prior physical support only
                require(++shape_.reveals<=plan_.shape.reveals,"dense positive reveal count changed");
                const auto child=history_.append_reveal(cursor,next.view());
                if (target_==catalog) (void)visit(node.edges[0].child,child,next,live,sb,bb,prior,past);
                else {
                    const auto child_prior=marginal(next,live);
                    add_lanes(result,visit(node.edges[0].child,child,next,live,sb,bb,child_prior,past));
                }
            });
            return result;
        }
        if (node.state.phase!=betting::Phase::decision) {
            const auto showdown=node.state.phase==betting::Phase::showdown;
            auto& total=showdown?shape_.showdowns:shape_.folds;
            require(++total<=(showdown?plan_.shape.showdowns:plan_.shape.folds),"dense terminal count changed");
            if (target_==catalog) return {};
            return terminal(node.state,prefix,sb,bb);
        }
        const auto actor=node.state.actor;
        const auto menu=node.edges.size();
        require(actor<2 && menu>=2 && menu<=4,"dense decision menu changed");
        const auto row_regret_shift=plan_.packed_regrets?regret_shift(plan_.H,past[1-actor],plan_.suffix_decisions[id]):0;
        const auto row_shift=plan_.packed_averages?average_shift(plan_.shift,past[actor]++):0;
        if (target_==catalog) {
            meter_.charge(Work::route,16+4*menu);
            std::array<std::string_view,4> tokens{};
            if (!plan_.sealed_menus)
                for (std::size_t action=0;action<menu;++action) tokens[action]=node.edges[action].action.token;
            for (std::size_t holding=0;holding<2;++holding) if (support[actor]&(1U<<holding)) {
                const std::span<const std::string_view> actions{tokens.data(),menu};
                std::size_t row;
                if (plan_.sealed_menus)
                    row=state_.register_sealed_row(cursor,holding,row_shift,row_regret_shift);
                else if (plan_.packed_regrets)
                    row=state_.register_catalog_row(cursor,actor,holding,id,actions,row_shift,row_regret_shift);
                else if (plan_.packed_averages)
                    row=state_.register_catalog_row(cursor,actor,holding,id,actions,row_shift);
                else row=state_.register_catalog_row(cursor,actor,holding,id,actions);
                require(row==shape_.rows && state_.row_at(row).offset==shape_.slots,"catalog row order changed");
                ++shape_.rows;
                shape_.slots+=menu;
            }
            for (std::size_t action=0;action<menu;++action) {
                ++shape_.actions;
                const auto child=history_.append_action(cursor,action);
                (void)visit(node.edges[action].child,child,prefix,support,sb,bb,prior,past);
            }
            return {};
        }
        const auto key=history_.ordinal(cursor);
        std::array<std::size_t,2> row_ids{};
        std::array<std::array<std::uint64_t,4>,2> policy_copies{};
        std::array<std::span<const std::uint64_t>,2> policy{};
        for (std::size_t holding=0;holding<2;++holding) if (support[actor]&(1U<<holding)) {
            meter_.charge(Work::route,16);
            require(shape_.rows<state_.row_count(),"dense policy row overflow");
            const auto row=static_cast<std::size_t>(shape_.rows++);
            state::PolicySnapshot snapshot{};
            if (plan_.paged_directory) snapshot=state_.copy_policy_snapshot(row,policy_copies[holding]);
            const auto record=plan_.paged_directory?snapshot.descriptor.row:state_.row_at(row);
            // Menus come from the same immutable source used at registration.
            // Check the complete identity and packed extent before policy access.
            require(record.history_ordinal==key && record.actor==actor && record.holding_index==holding &&
                record.offset==shape_.slots && record.actions.size()==menu,"dense policy route changed");
            if (plan_.packed_averages)
                require((plan_.paged_directory?snapshot.descriptor.average_shift:state_.average_row_shift(row))==row_shift,
                    "packed average row depth changed");
            if (plan_.packed_regrets)
                require((plan_.paged_directory?snapshot.descriptor.regret_shift:state_.regret_row_shift(row))==row_regret_shift,
                    "packed regret row depth changed");
            shape_.slots+=menu;
            row_ids[holding]=row;
            if (plan_.paged_directory) policy[holding]=snapshot.units;
            else if (plan_.shared_policy) {
                const auto units=std::span(policy_copies[holding]).first(menu);
                state_.copy_policy_units(row,units);
                policy[holding]=units;
            } else policy[holding]=state_.policy_units(row);
        }
        LaneValues result{};
        std::array<std::array<Integer,4>,2> action_values{};
        const auto& actor_reach=actor?bb:sb;
        const std::size_t acting_lane=Paired?actor:(actor==target_?0:lanes);
        for (std::size_t action=0;action<menu;++action) {
            require(++shape_.actions<=plan_.shape.actions,"dense action count changed");
            const auto child=history_.append_action(cursor,action);
            const auto next=advance(actor_reach,policy,action,support[actor]);
            auto values=actor?visit(node.edges[action].child,child,prefix,support,sb,next,prior,past):
                visit(node.edges[action].child,child,prefix,support,next,bb,prior,past);
            for (std::size_t lane=0;lane<lanes;++lane) {
                if (lane!=acting_lane) add_values(result[lane],values[lane]);
                else for (std::size_t holding=0;holding<2;++holding)
                    action_values[holding][action]=std::move(values[lane][holding]);
            }
        }
        if (acting_lane<lanes) {
            for (std::size_t holding=0;holding<2;++holding) if (support[actor]&(1U<<holding)) {
                std::array<Integer,4> increments{};
                const std::span<Integer> average{increments.data(),menu};
                const std::span<const Integer> values{action_values[holding].data(),menu};
                if (plan_.scaled_averages) {
                    stage_scaled_average(average,policy[holding],prior[acting_lane],actor_reach,holding,row_shift);
                    result[acting_lane][holding]=state_.stage_scaled_row(row_ids[holding],values,{average,row_shift});
                } else {
                    stage_average(average,policy[holding],prior[acting_lane],actor_reach,holding);
                    result[acting_lane][holding]=state_.stage_row(row_ids[holding],values,average);
                }
            }
        }
        return result;
    }
public:
    Walk(const betting::Template& source,const Plan& plan,Meter& meter,history::History& history,
         prepared::PreparedPublicChance& chance,state::State& state,std::size_t target,std::size_t averaging_sweep=1)
        :source_(source),plan_(plan),meter_(meter),history_(history),chance_(chance),state_(state),target_(target),
         averaging_sweep_(averaging_sweep) {}
    LaneValues run(Cursor root) {
        require(Paired?(target_==0 && plan_.traversal==Traversal::paired):
            (target_==catalog || (target_<catalog && plan_.traversal==Traversal::by_seat)),"invalid fixed sweep target");
        require(!plan_.linear_average || (averaging_sweep_>=1 && averaging_sweep_<=32),
            "linear average sweep is outside its admitted one-based horizon");
        const auto support=physical_support(0);
        const auto prior=target_==catalog?Marginals{}:marginal(Prefix{},support);
        auto value=visit(source_.root(),root,Prefix{},support,Reach{},Reach{},prior);
        require(shape_==plan_.shape &&
            showdown_contractions_==(target_==catalog?0:plan_.showdown_contractions) &&
            hidden_candidates_==(target_==catalog?0:plan_.hidden_candidates),"actual dense pass differs from rank-free census");
        return value;
    }
};

class Binary final {
    std::ostream& out_;
    std::uint64_t capacity_,written_=0;
    std::size_t value_bits_;
    std::uint64_t compact_limit_=0,compact_work_=0;
public:
    Binary(std::ostream& out,std::uint64_t capacity,std::size_t value_bits,std::uint64_t compact_limit=0)
        :out_(out),capacity_(capacity),value_bits_(value_bits),compact_limit_(compact_limit) {
        static_assert(std::endian::native==std::endian::little,"fixed binary producer requires little endian");
        require(value_bits_==proof9.value_bits || value_bits_==proof10.value_bits || value_bits_==proof9_t3.value_bits ||
            value_bits_==proof9_t4.value_bits,"unsupported fixed output width");
    }
    void bytes(const void* data,std::size_t size) {
        require(size<=capacity_-written_,"fixed training output exceeds byte admission");
        if (size) out_.write(static_cast<const char*>(data),static_cast<std::streamsize>(size));
        require(bool(out_),"fixed training output write failed");
        written_+=size;
    }
    void text(std::string_view value) { bytes(value.data(),value.size()); }
    void u64(std::uint64_t value) { bytes(&value,sizeof(value)); }
    void charge_compact(std::uint64_t work) {
        require(work<=compact_limit_-compact_work_,"compact encoding work cap exceeded");
        compact_work_+=work;
    }
    [[nodiscard]] std::uint64_t compact_work() const noexcept { return compact_work_; }
    void bounded_word(std::uint64_t value,std::size_t count) {
        require((count==6 || count==7) && value<(1ULL<<(8*count)),"compact output word exceeds width");
        bytes(&value,count);
    }
    void policy(std::span<const std::uint64_t> units,bool compact) {
        // Source-level scalar packing/check operations. The existing output
        // ledger retains common stream emission and policy access charges.
        if (!compact) {
            for (const auto unit:units) u64(unit);
            return;
        }
        require(units.size()<=4,"compact policy menu exceeds packing model");
        charge_compact(64+32*units.size());
        std::uint64_t total=0;
        for (std::size_t i=0;i<units.size();++i) {
            require(units[i]<=grid-total,"policy output exceeds fixed grid");
            total+=units[i];
            if (i+1<units.size()) bounded_word(units[i],7);
        }
        require(!units.empty() && units.size()<=4 && total==grid,"policy output partition differs");
    }
    void fallback_bits(std::span<const unsigned char> flags) {
        charge_compact(16*flags.size()+16*((flags.size()+7)/8));
        for (std::size_t start=0;start<flags.size();start+=8) {
            unsigned char byte=0;
            for (std::size_t bit=0;bit<8 && start+bit<flags.size();++bit) {
                require(flags[start+bit]<=1,"compact fallback flag outside boolean range");
                byte|=static_cast<unsigned char>(flags[start+bit]<<bit);
            }
            bytes(&byte,1);
        }
    }
    void wide(const Integer& value,bool signed_field=false) {
        const auto& raw=value.backend();
        using Limb=std::remove_cvref_t<decltype(raw.limbs()[0])>;
        constexpr auto limb_bits=std::numeric_limits<Limb>::digits;
        static_assert((limb_bits==32 || limb_bits==64) && limb_bits==8*sizeof(Limb),"unsupported fixed proof limb layout");
        constexpr auto wire_bytes=integer_words*sizeof(std::uint64_t);
        const auto value_limbs=(value_bits_+limb_bits-1)/limb_bits;
        const auto top_mask=1ULL<<(value_bits_%limb_bits);
        const auto used=static_cast<std::size_t>(raw.size());
        require(used && used<=value_limbs && (used<value_limbs || raw.limbs()[value_limbs-1]<top_mask),
            "fixed output integer width exceeded");
        if (signed_field) u64(raw.sign()?1:0);
        else require(!raw.sign(),"negative unsigned training output field");
        constexpr std::array<std::uint64_t,integer_words> zeros{};
        bytes(raw.limbs(),used*sizeof(Limb));
        bytes(zeros.data(),wire_bytes-used*sizeof(Limb));
    }
    void finish() {
        require(written_==capacity_,"fixed training output length changed");
        require(compact_work_==compact_limit_,"compact encoding work differs from reservation");
        out_.flush();
        require(bool(out_),"fixed training output flush failed");
    }
};

static_assert(proof9_q32_sweep_stream_read_bytes==proof9_q32_sweep_stream_frames*
    proof9_q32_sweep_stream_image_bytes);
static_assert(proof9_q32_sweep_stream_wire_bytes==proof9_q32_sweep_stream_retained_bytes+
    proof9_q32_sweep_stream_read_bytes+proof9_q32_sweep_stream_frames*sweep_stream_header_bytes);
static_assert(proof9_q32_sweep_stream_copy_work==proof9_q32_sweep_stream_frames*
    (2ULL*paging::n9_image_words+64*((proof9_q32_sweep_stream_image_bytes+sweep_stream_scratch_bytes-1)/
        sweep_stream_scratch_bytes)+sweep_stream_header_bytes));

struct TrainingIO {
    std::optional<paging::Receipt> paging;
    std::optional<state::PolicySpillReceipt> policy;
    std::optional<state::RowDirectoryReceipt> directory;
    std::unique_ptr<state::PolicySpillSweep[]> bounded_policy;
    std::size_t bounded_policy_count=0;
    std::uint64_t combined_divisions=0,compact_encoding_work=0;
    std::optional<prepared::RankIndexReceipt> rank_index;
};

inline constexpr std::uint64_t sweep_stream_frames=sweeps;
inline constexpr std::uint64_t sweep_stream_image_bytes=8ULL*paging::n10_image_words;
inline constexpr std::uint64_t sweep_stream_retained_bytes=9833076;
inline constexpr std::uint64_t sweep_stream_read_bytes=sweep_stream_frames*sweep_stream_image_bytes;
inline constexpr std::uint64_t sweep_stream_wire_bytes=sweep_stream_retained_bytes+sweep_stream_read_bytes+
    sweep_stream_frames*sweep_stream_header_bytes;
inline constexpr std::uint64_t sweep_stream_blocks=(sweep_stream_image_bytes+sweep_stream_scratch_bytes-1)/
    sweep_stream_scratch_bytes;
// One read and one write per word, plus bounded block and header bookkeeping.
inline constexpr std::uint64_t sweep_stream_copy_work=sweep_stream_frames*
    (2*paging::n10_image_words+64*sweep_stream_blocks+sweep_stream_header_bytes);
static_assert(proof9_t3_sweep_stream_image_bytes==8ULL*paging::n9_image_words);
static_assert(proof9_t3_sweep_stream_read_bytes==proof9_t3_sweep_stream_frames*proof9_t3_sweep_stream_image_bytes);
static_assert(proof9_t3_sweep_stream_wire_bytes==proof9_t3_sweep_stream_frames*(sweep_stream_header_bytes+proof9_t3_sweep_stream_image_bytes)+
    proof9_t3_sweep_stream_retained_bytes);
inline constexpr std::uint64_t proof9_t3_sweep_stream_blocks=(proof9_t3_sweep_stream_image_bytes+sweep_stream_scratch_bytes-1)/
    sweep_stream_scratch_bytes;
static_assert(proof9_t3_sweep_stream_copy_work==proof9_t3_sweep_stream_frames*
    (2ULL*paging::n9_image_words+64*proof9_t3_sweep_stream_blocks+sweep_stream_header_bytes));
inline constexpr std::uint64_t proof9_t4_sweep_stream_blocks=(proof9_t4_sweep_stream_image_bytes+sweep_stream_scratch_bytes-1)/
    sweep_stream_scratch_bytes;
static_assert(proof9_t4_sweep_stream_read_bytes==proof9_t4_sweep_stream_frames*proof9_t4_sweep_stream_image_bytes);
static_assert(proof9_t4_sweep_stream_wire_bytes==proof9_t4_sweep_stream_retained_bytes+
    proof9_t4_sweep_stream_read_bytes+proof9_t4_sweep_stream_frames*sweep_stream_header_bytes);
static_assert(proof9_t4_sweep_stream_copy_work==proof9_t4_sweep_stream_frames*
    (2ULL*paging::n9_image_words+64*proof9_t4_sweep_stream_blocks+sweep_stream_header_bytes));

class Driver final {
    betting::Template source_{configuration(),template_limits()};
    Meter meter_;
    const Plan plan_;
    bool entered_=false;

    void skeleton(Binary& output) const {
        struct Literal { std::size_t id=0,parent=0,edge=0; std::string_view token; };
        constexpr auto sentinel=std::numeric_limits<std::size_t>::max();
        constexpr std::array<char,64> pad{};
        std::array<Literal,literal_count> breadth{};
        breadth[0]={source_.root(),sentinel,sentinel,{}};
        std::size_t count=1;
        for (std::size_t at=0;at<count;++at) {
            const auto& record=breadth[at];
            const auto& node=source_.nodes()[record.id];
            const auto phase=node.state.phase;
            const std::uint64_t actor=phase==betting::Phase::decision?node.state.actor:255U;
            const std::uint64_t next=phase==betting::Phase::reveal?node.state.next_street:0U;
            const std::uint64_t winner=phase==betting::Phase::fold?node.state.winner:255U;
            const auto shape=static_cast<std::uint64_t>(phase)|(static_cast<std::uint64_t>(node.state.street)<<8)|
                (actor<<16)|(next<<24)|(winner<<32)|(static_cast<std::uint64_t>(node.edges.size())<<40);
            require(record.token.size()<=pad.size(),"literal skeleton token bound");
            output.u64(record.parent);output.u64(record.edge);output.u64(shape);output.u64(record.token.size());
            output.text(record.token);output.bytes(pad.data(),pad.size()-record.token.size());
            for (std::size_t edge=0;edge<node.edges.size();++edge) {
                require(count<literal_count,"literal skeleton breadth exceeded");
                breadth[count++]={node.edges[edge].child,at,edge,phase==betting::Phase::decision?
                    std::string_view(node.edges[edge].action.token):std::string_view{}};
            }
        }
        require(count==literal_count,"literal skeleton breadth incomplete");
    }
    void prelude(Binary& out,const state::State& state,const Integer& denominator) const {
        const auto& p=plan_;
        out.text(p.compact_wire?"OPLDTC01":p.proof9_linear32()?"OPLDSL31":p.proof9_quality32()?"OPLDSQ31":p.proof9_four_sweep()?"OPLDST41":p.proof9_three_sweep()?"OPLDST31":p.ten_card()?"OPLDTP01":p.split_checkpoint?"OPLDSP01":"OPLDYA01");
        for (const auto word:std::array<std::uint64_t,header_words>{p.bounded_proof9()?p.requested_sweeps:1ULL,grid_bits,integer_words,p.shape.rows,
            p.shape.slots,literal_count,p.requested_sweeps,p.H,p.M,p.denominator_bits,p.game().value_bits,p.output_bytes,2,2,
            p.normalizer,p.game().divisors[3]}) out.u64(word);
        out.wide(denominator);
        skeleton(out);
        for (std::size_t i=0;i<state.row_count();++i) {
            const auto row=state.row_at(i);
            if (p.compact_wire) {
                out.charge_compact(64);
                require(row.history_ordinal<(1ULL<<44) && row.actor<2 && row.holding_index<2 &&
                    !row.actions.empty() && row.actions.size()<=4,"compact row identity exceeds width");
                out.bounded_word((static_cast<std::uint64_t>(row.history_ordinal)<<4)|
                    (row.actor<<3)|(row.holding_index<<2)|(row.actions.size()-1),6);
            } else {
                out.u64(row.history_ordinal);
                out.u64(row.actor|(row.holding_index<<8)|(row.actions.size()<<16));
                out.u64(row.offset);
            }
        }
    }
    static std::uint64_t profile(Binary& out,state::State& state,std::size_t sweep,bool shared_policy,bool paged_directory,bool compact_wire) {
        std::uint64_t changed=0;
        for (std::size_t row=0;row<state.row_count();++row) {
            std::array<std::uint64_t,4> copied{};
            std::span<const std::uint64_t> units;
            if (paged_directory) units=state.copy_policy_snapshot(row,copied).units;
            else if (shared_policy) {
                const auto menu=state.row_at(row).actions.size();
                require(menu<=copied.size(),"shared policy menu exceeds stream scratch");
                const auto target=std::span(copied).first(menu);
                state.copy_policy_units(row,target);
                units=target;
            } else units=state.policy_units(row);
            bool distinct=false;
            for (std::size_t action=0;action<units.size();++action) {
                distinct=distinct || units[action]!=uniform_unit(units.size(),action);
            }
            require(sweep || !distinct,"first policy differs from the admitted uniform grid");
            if (!compact_wire || sweep) out.policy(units,compact_wire);
            if (distinct) ++changed;
        }
        return changed;
    }
    void wide_checkpoint(Binary& out,const state::State& state) const {
        if (plan_.packed_regrets) {
            for (std::size_t row=0;row<state.row_count();++row)
                for (std::size_t action=0,count=state.row_at(row).actions.size();action<count;++action)
                    out.wide(state.regret_numerator(row,action));
        } else {
            for (const auto& value:state.regrets()) out.wide(value);
        }
        if (plan_.packed_averages) {
            for (std::size_t row=0;row<state.row_count();++row)
                for (std::size_t action=0,count=state.row_at(row).actions.size();action<count;++action)
                    out.wide(state.average_numerator(row,action));
        } else {
            for (const auto& value:state.averages()) out.wide(value);
        }
    }
    void footer(Binary& out,const prepared::Receipt& chance,const history::Receipt& history,
                const state::Receipt& state,std::uint64_t feedback) const {
        const auto& p=plan_;
        const std::array<std::uint64_t,6> forecast{p.template_work,p.chance_work,p.history_work,
            p.state_work,p.quantizer_work,sum_work(p.parent)};
        const std::array<std::uint64_t,6> actual{source_.receipt().work,chance.modeled_work,history.work,
            state.state_work,state.quantizer_work,meter_.total()};
        for (std::size_t i=0;i<actual.size();++i) require(actual[i]<=forecast[i],"child component exceeded composed forecast");
        require(chance.completed_contractions==p.seat_passes*(p.shape.folds+p.showdown_contractions+p.shape.reveals+1) &&
            chance.rank_calls==p.expected_rank_calls && chance.cache_misses==p.rank_planes &&
            chance.cache_hits+chance.cache_misses==p.seat_passes*p.showdown_contractions && !chance.cache_evictions &&
            chance.peak_live_entries<=chance_entries && chance.peak_integer_payload_bits<=chance_payload &&
            state.completed_sweeps==p.requested_sweeps && state.rows==p.shape.rows && state.slots==p.shape.slots &&
            state.reserved_entries==p.state_entries && state.reserved_integer_and_text_payload_bits==p.state_payload &&
            feedback && history.owned_bytes<=history_bytes,"completed training receipt differs from admission");
        require((chance.sparse_pair_visits>0)==p.sparse_chance,"sparse chance execution receipt differs");
        out.text(p.proof9_linear32()?"OPLDSL32":p.proof9_quality32()?"OPLDSQ32":p.proof9_four_sweep()?"OPLDST42":p.proof9_three_sweep()?"OPLDST32":p.ten_card()?"OPLDTP02":p.split_checkpoint?"OPLDSP02":
            p.traversal==Traversal::paired?"OPLDEND2":"OPLDEND1");
        for (const auto word:forecast) out.u64(word);
        for (const auto word:actual) out.u64(word);
        for (const auto word:p.parent) out.u64(word);
        for (const auto word:meter_.actual()) out.u64(word);
        const auto& g=p.shape;
        for (const auto word:std::array<std::uint64_t,34>{g.visits,g.actions,g.reveals,g.candidates,g.folds,g.showdowns,g.rows,g.slots,
            p.entries,p.payload_bits,p.expected_rank_calls,
            chance.prior_work,chance.setup_work,chance.input_work,chance.cache_lookup_work,chance.rank_work,chance.sort_work,
            chance.contraction_work,chance.completed_contractions,chance.rank_calls,chance.cache_hits,chance.cache_misses,
            chance.cache_evictions,chance.peak_live_entries,chance.peak_integer_payload_bits,chance.peak_integer_bits,feedback,
            state.completed_sweeps,p.public_walks,1,history.entries,history.owned_bytes,state.reserved_entries,
            state.reserved_integer_and_text_payload_bits}) out.u64(word);
    }
    static void emit_sweep_checkpoint(std::ostream& stream,state::State& state,
                                      std::span<char> scratch,std::size_t sweep,std::uint64_t image_bytes) {
        constexpr std::array<char,8> magic{'O','P','L','C','P','G','0','1'};
        std::array<char,sweep_stream_header_bytes> header{};
        std::copy(magic.begin(),magic.end(),header.begin());
        const auto put_u64=[&](std::size_t offset,std::uint64_t value) {
            for (unsigned byte=0;byte<8;++byte)
                header[offset+byte]=static_cast<char>((value>>(8*byte))&0xff);
        };
        const auto slot=sweep%2;
        put_u64(8,sweep);
        put_u64(16,slot);
        put_u64(24,image_bytes);
        stream.write(header.data(),static_cast<std::streamsize>(header.size()));
        require(bool(stream),"sweep checkpoint frame header write failed");
        const auto copied=state.stream_committed_checkpoint(stream,scratch,sweep,slot);
        require(copied==image_bytes,"sweep checkpoint image byte count differs");
        stream.flush();
        require(bool(stream),"sweep checkpoint frame flush failed");
    }
public:
    explicit Driver(Traversal mode=Traversal::by_seat,StrategyProfile profile=StrategyProfile::dense)
        :plan_(Forecast(source_,meter_,mode,profile).make()) {}
    Driver(const Driver&)=delete;
    Driver& operator=(const Driver&)=delete;
    Driver(Driver&&)=delete;
    Driver& operator=(Driver&&)=delete;
    [[nodiscard]] const Plan& plan() const noexcept { return plan_; }
    [[nodiscard]] std::uint64_t admission_work() const noexcept { return meter_.total(); }

    void validate_sweep_stream() const {
        const auto& p=plan_;
        const auto& game=p.game();
        if (p.proof9_q32_base()) {
            require(p.paged_directory && p.split_checkpoint && p.requested_sweeps==32 &&
                p.shape.rows==24420 && p.shape.slots==58164 && p.game().value_bits==644 &&
                p.row_batched && !p.phase_payload && p.single_division && p.sparse_chance && !p.indexed_cache &&
                p.page_limits.profile==paging::Profile::proof9_q32 &&
                p.page_limits.image_words==paging::n9_image_words &&
                p.page_limits.read_words==paging::n9_q32_read_words &&
                p.page_limits.write_words==paging::n9_q32_write_words &&
                p.page_limits.write_requests==paging::n9_q32_write_requests &&
                p.page_limits.requests==paging::n9_q32_logical_requests &&
                p.page_limits.stage_split_words==paging::n9_q32_stage_split_words &&
                p.admitted_directory_page_limit==state::State::proof9_q32_directory_page_limit &&
                p.output_bytes==proof9_q32_sweep_stream_retained_bytes &&
                proof9_q32_sweep_stream_image_bytes==8ULL*p.page_limits.image_words,
                "sweep streaming is restricted to the fixed PROOF9 Q32 profile");
            require(p.entries<=entries_cap && p.payload_bits<=game.payload_limit,
                "Q32 sweep streaming scratch exceeds scoped storage admission");
            require(p.total_work<=game.work_limit && proof9_q32_sweep_stream_copy_work<=game.work_limit-p.total_work,
                "Q32 sweep streaming copy work exceeds transport work cap");
            return;
        }
        if (p.proof9_four_sweep()) {
            require(p.paged_directory && p.split_checkpoint && p.requested_sweeps==4 &&
                p.shape.rows==24420 && p.shape.slots==58164 &&
                p.page_limits.profile==paging::Profile::proof9_t4 &&
                p.page_limits.image_words==paging::n9_image_words &&
                p.page_limits.read_words==paging::n9_t4_read_words &&
                p.page_limits.write_words==paging::n9_t4_write_words &&
                p.page_limits.write_requests==paging::n9_t4_write_requests &&
                p.page_limits.requests==paging::n9_t4_logical_requests &&
                p.page_limits.stage_split_words==paging::n9_t4_stage_split_words &&
                p.admitted_directory_page_limit==state::proof9_t4_directory_page_limit &&
                p.output_bytes==proof9_t4_sweep_stream_retained_bytes &&
                proof9_t4_sweep_stream_image_bytes==8ULL*p.page_limits.image_words,
                "sweep streaming is restricted to the fixed PROOF9 T4 profile");
            require(p.entries<=entries_cap && p.payload_bits<=game.payload_limit,
                "T4 sweep streaming scratch exceeds existing storage admission");
            require(p.total_work<=game.work_limit && proof9_t4_sweep_stream_copy_work<=game.work_limit-p.total_work,
                "T4 sweep streaming copy work exceeds transport work cap");
            return;
        }
        if (p.proof9_three_sweep()) {
            require(p.paged_directory && p.split_checkpoint && p.requested_sweeps==3 &&
                p.shape.rows==24420 && p.shape.slots==58164 &&
                p.page_limits.profile==paging::Profile::legacy &&
                p.page_limits.image_words==paging::n9_image_words &&
                p.page_limits.read_words==2223164 && p.page_limits.write_words==1820190 &&
                p.page_limits.write_requests==5931 && p.page_limits.requests==930624 &&
                p.admitted_directory_page_limit==2122 && p.output_bytes==proof9_t3_sweep_stream_retained_bytes &&
                proof9_t3_sweep_stream_image_bytes==8ULL*p.page_limits.image_words,
                "sweep streaming is restricted to the fixed PROOF9 T3 profile");
            require(p.entries<=entries_cap && p.payload_bits<=game.payload_limit,
                "T3 sweep streaming scratch exceeds existing storage admission");
            require(p.total_work<=game.work_limit && proof9_t3_sweep_stream_copy_work<=game.work_limit-p.total_work,
                "T3 sweep streaming copy work exceeds transport work cap");
            return;
        }
        require(p.ten_card() && p.paged_directory && p.split_checkpoint && sweeps==2 &&
            p.shape.rows==119196 && p.shape.slots==281066 &&
            p.page_limits.profile==paging::Profile::proof10 &&
            p.page_limits.image_words==paging::n10_image_words &&
            p.output_bytes==(p.compact_wire?compact_artifact_bytes(p.shape):sweep_stream_retained_bytes) &&
            p.page_limits.image_words<=std::numeric_limits<std::uint64_t>::max()/8 &&
            8*static_cast<std::uint64_t>(p.page_limits.image_words)==sweep_stream_image_bytes,
            "sweep streaming is restricted to the fixed ten-card paged-directory profile");
        require(p.entries<=entries_cap && sweep_stream_entries<=entries_cap-p.entries &&
            p.payload_bits<=game.payload_limit && sweep_stream_payload_bits<=game.payload_limit-p.payload_bits,
            "sweep streaming scratch exceeds existing storage admission");
        require(p.total_work<=game.work_limit && sweep_stream_copy_work<=game.work_limit-p.total_work,
            "sweep streaming copy work exceeds transport work cap");
        require(!p.compact_wire || compact_encoding_work(p.shape)<=
            game.work_limit-p.total_work-sweep_stream_copy_work,
            "compact encoding exceeds composed transport work cap");
        // Bounded scalar encoder counters, temporary packed row and flag byte.
        require(!p.compact_wire || (32<=entries_cap-p.entries-sweep_stream_entries &&
            2048<=game.payload_limit-p.payload_bits-sweep_stream_payload_bits),
            "compact encoder scratch exceeds composed storage cap");
    }

    TrainingIO train(std::ostream& stream,const std::filesystem::path& page_scratch={},
                     bool streamed_checkpoints=false) {
        require(!entered_,"fixed training owner already entered");
        entered_=true;
        const auto& p=plan_;
        const auto& game=p.game();
        const auto value_bits=game.value_bits;
        require(!p.bounded_proof9() || streamed_checkpoints,
            "bounded PROOF9 requires explicit sweep checkpoint streaming");
        require(!p.sparse_chance || streamed_checkpoints,
            "sparse chance profile requires explicit sweep checkpoint streaming");
        if (streamed_checkpoints) validate_sweep_stream();
        require(p.paged_strategy==!page_scratch.empty(),"paged strategy requires explicit private scratch");
        const auto deck=chance::DeckDefinition::reduced(game.deck);
        chance::Limits chance_limits;
        chance_limits.max_hands_per_side=2;
        chance_limits.max_integer_bits=value_bits+58;
        chance_limits.max_modeled_work=p.chance_work;
        chance_limits.max_storage_entries=chance_entries;
        chance_limits.max_integer_payload_bits=chance_payload;
        prepared::PreparedPublicChance chance(ranges[0],ranges[1],deck,chance_limits,
            p.rank_board_sets?p.rank_planes:64,
            p.rank_board_sets?prepared::RankCacheKey::board_set:prepared::RankCacheKey::ordered_prefix,
            p.sparse_chance?prepared::ContractionKernel::sparse_pairs:prepared::ContractionKernel::blocker_buckets,
            p.indexed_cache?prepared::RankCacheIndex::sorted_board_set:prepared::RankCacheIndex::linear);
        require(chance.normalizer_integer()==p.normalizer && chance.receipt().modeled_work<=
            chance_setup_bound+(p.indexed_cache?prepared::PreparedPublicChance::index_setup_work(p.rank_planes):0),
            "prepared prior differs from admitted source prior");
        history::Limits history_limits;
        history_limits.work=p.history_work;
        history_limits.nodes=literal_count;
        history_limits.entries=32*literal_count+1;
        history_limits.owned_bytes=history_bytes;
        history_limits.depth=15;
        history::History history(source_,deck,history_limits);
        const Integer denominator=Integer(p.denominator_base)<<p.shift;
        if (p.packed_averages) meter_.charge(Work::average,p.packed_average_work);
        if (p.packed_regrets) meter_.charge(Work::route,p.packed_regret_work);
        if (p.paged_strategy) meter_.charge(Work::route,p.paging_work);
        if (p.shared_policy) meter_.charge(Work::route,p.policy_spill_work);
        if (p.compact_directory) meter_.charge(Work::route,p.directory_work);
        auto division_kernel=dyadic_policy::DivisionKernel::separate;
        if (p.complement_division) division_kernel=dyadic_policy::DivisionKernel::complement;
        else if (p.single_division) division_kernel=dyadic_policy::DivisionKernel::combined;
        state::State state(history,{2,2},denominator,
            {static_cast<std::size_t>(p.shape.rows),static_cast<std::size_t>(p.shape.slots),p.requested_sweeps,15,value_bits,
             p.state_work,p.quantizer_work},
            {p.state_work+p.quantizer_work,value_bits+58,static_cast<std::size_t>(p.state_entries),
             static_cast<std::size_t>(p.state_payload)},
            {source_.nodes().size(),source_.receipt().edges,p.sealed_menus},{static_cast<std::size_t>(p.packed_average_limbs),
             static_cast<std::size_t>(p.packed_regret_limbs)},
            p.paged_strategy?std::optional<state::PagedStrategy>{
                state::PagedStrategy{page_scratch,p.page_limits,p.compact_directory,p.ordered_state,p.row_coverage,
                    p.shared_policy,p.paged_directory,p.paged_directory?p.admitted_directory_page_limit:0,
                    p.proof9_q32_base()?state::Lifecycle::quality32:p.bounded_proof9()?state::Lifecycle::bounded_v1:state::Lifecycle::fixed_two_sweep,
                    division_kernel,
                    p.phase_payload?state::PayloadModel::paged_phases:state::PayloadModel::legacy,p.row_batched}}:std::nullopt);
        const auto root=history.root();
        (void)Walk<false>(source_,p,meter_,history,chance,state,targets).run(root);
        state.freeze();
        if (p.sealed_menus) {
            const auto actions=state.action_storage();
            require(actions.stored_menus==p.sealed_menu_count && actions.stored_tokens==p.sealed_token_count,
                "sealed action catalog realization differs from admission");
        }

        meter_.charge(Work::output,p.parent[work_index(Work::output)]);
        Binary out(stream,p.output_bytes,value_bits,p.compact_wire?compact_encoding_work(p.shape):0);
        prelude(out,state,denominator);
        std::uint64_t feedback=0;
        for (std::size_t sweep=0;sweep<p.requested_sweeps;++sweep) {
            state.begin_sweep();
            feedback=profile(out,state,sweep,p.shared_policy,p.paged_directory,p.compact_wire);
            std::array<Values,targets> roots{};
            if (p.traversal==Traversal::paired) roots=Walk<true>(source_,p,meter_,history,chance,state,0,sweep+1).run(root);
            else {
                auto sb=Walk<false>(source_,p,meter_,history,chance,state,0,sweep+1).run(root);
                auto bb=Walk<false>(source_,p,meter_,history,chance,state,1,sweep+1).run(root);
                roots={std::move(sb[0]),std::move(bb[0])};
            }
            require(roots[0][0]+roots[0][1]+roots[1][0]+roots[1][1]==0,"simultaneous fixed profile is not zero-sum");
            state.commit_sweep();
            if (!p.split_checkpoint) wide_checkpoint(out,state);
            for (const auto& root_value:roots) for (const auto& value:root_value) out.wide(value,true);
            if (streamed_checkpoints) {
                const auto receipt=state.paged_receipt();
                require(receipt && receipt->completed_sweeps==sweep+1,
                    "pager generation did not advance exactly once before frame stream");
                std::array<char,sweep_stream_scratch_bytes> scratch;
            emit_sweep_checkpoint(stream,state,scratch,sweep+1,
                p.bounded_proof9()?proof9_t3_sweep_stream_image_bytes:sweep_stream_image_bytes);
            }
        }
        if (p.shared_policy) {
            const auto flags=state.stream_average([&](std::span<const std::uint64_t> units) {
                out.policy(units,p.compact_wire);
            });
            require(flags.size()==p.shape.rows,"streamed export row count changed");
            if (p.compact_wire) out.fallback_bits(flags);
            else out.bytes(flags.data(),flags.size());
        } else {
            const auto image=state.export_average(!p.packed_averages);
            require(image.kind==dyadic_policy::ImageKind::exported_average && image.rows==p.shape.rows && image.slots==p.shape.slots,
                "fixed export policy image changed");
            for (std::size_t i=0;i<image.slots;++i) out.u64(image.units[i]);
            out.bytes(image.uniform_fallback.get(),image.rows);
        }
        const auto& state_receipt=state.receipt();
        require((state_receipt.combined_divisions>0)==p.single_division,"combined division execution receipt differs");
        footer(out,chance.receipt(),history.receipt(),state_receipt,feedback);
        out.finish();
        TrainingIO result;
        result.compact_encoding_work=out.compact_work();
        result.paging=state.paged_receipt();
        if (p.bounded_proof9()) {
            const auto receipts=state.policy_sweep_receipts();
            require(receipts.size()==p.requested_sweeps,"bounded policy sweep receipt length changed");
            result.bounded_policy=std::make_unique<state::PolicySpillSweep[]>(receipts.size());
            result.bounded_policy_count=receipts.size();
            std::copy(receipts.begin(),receipts.end(),result.bounded_policy.get());
        } else result.policy=state.policy_spill_receipt();
        result.directory=state.row_directory_receipt();
        result.combined_divisions=state_receipt.combined_divisions;
        if (p.indexed_cache) result.rank_index=chance.rank_index_receipt();
        return result;
    }
};
} // namespace openpoker::virtual_dyadic_training
