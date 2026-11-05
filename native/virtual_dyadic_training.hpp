#pragma once
// Fixed PROOF9, q=1, two simultaneous CFR+ sweeps. No board, world, reach,
// or payoff table is retained. This front door has no general solver dispatch.
#include "prepared_public_chance.hpp"
#include "virtual_dyadic_state.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <limits>
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
using chance::Integer;
using Values=std::array<Integer,2>;
using Cursor=history::History::Cursor;
inline constexpr std::size_t sweeps=2, targets=2, seat_passes=sweeps*targets;
enum class Traversal { by_seat, paired };
inline constexpr std::uint64_t visit_cost(Traversal mode) {
    // Paired frames carry one additional two-holding lane and lane routing.
    return mode==Traversal::paired?12:8;
}
inline constexpr std::size_t literal_count=1105, template_count=388;
inline constexpr std::size_t integer_words=11, value_bits=642;
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
static_assert(template_cap+chance_cap+history_cap+state_cap+quantizer_cap+parent_cap<=work_cap);
// At most 16 visible frames plus three hidden reveal levels. Even 64
// simultaneous 700-bit integer objects per level fit the parent reservation.
static_assert(19*64*(value_bits+58)<parent_payload);

class Error final : public std::runtime_error {
public:
    explicit Error(const char* message):std::runtime_error(message) {}
};
inline void require(bool condition,const char* message) { if (!condition) throw Error(message); }

inline constexpr std::array<std::uint8_t,9> deck_cards{16,17,24,32,33,35,37,43,48};
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
inline std::size_t candidate_count(std::size_t size) {
    if (size==0) return deck_cards.size()*(deck_cards.size()-1)*(deck_cards.size()-2)/6;
    require(size==3 || size==4,"invalid physical reveal predecessor");
    return deck_cards.size()-size;
}
template<class F> void reveal(const Prefix& prefix,F&& visit) {
    if (!prefix.size) {
        for (std::size_t a=0;a<deck_cards.size();++a)
            for (std::size_t b=a+1;b<deck_cards.size();++b)
                for (std::size_t c=b+1;c<deck_cards.size();++c) {
                    const auto x=deck_cards[a],y=deck_cards[b],z=deck_cards[c];
                    visit(Prefix{{x,y,z,0,0},3,(std::uint64_t{1}<<x)|(std::uint64_t{1}<<y)|(std::uint64_t{1}<<z)});
                }
        return;
    }
    require(prefix.size==3 || prefix.size==4,"invalid ordered physical reveal");
    for (const auto card:deck_cards) {
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
inline constexpr std::array<std::uint64_t,4> chance_divisors{1,10,20,20};
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
inline constexpr Counts expected_counts{61099,57363,3735,15662,16631,17356,24420,58164};
struct PrefixStats {
    std::uint64_t count=0;
    std::array<std::uint64_t,2> supported{};
    std::array<std::array<std::uint64_t,3>,3> unblocked{};
};
struct Plan {
    Counts shape;
    std::array<PrefixStats,4> prefixes{};
    std::array<std::uint64_t,3> quantizer_terms{};
    WorkList parent{};
    Traversal traversal=Traversal::by_seat;
    bool packed_averages=false;
    bool packed_regrets=false;
    std::size_t public_walks=seat_passes;
    std::size_t H=0,M=0,shift=0,denominator_bits=0,pay_bits=0,max_first_exponent=0;
    std::array<std::size_t,2> max_actor_depth{};
    std::array<std::uint8_t,template_count> suffix_decisions{};
    std::uint64_t normalizer=0,denominator_base=0,expected_rank_calls=0;
    std::uint64_t showdown_contractions=0,hidden_candidates=0;
    std::uint64_t template_work=0,chance_work=0,history_work=0,state_work=0,quantizer_work=0,total_work=0;
    std::uint64_t state_entries=0,state_payload=0,entries=0,payload_bits=0,output_bytes=0;
    std::uint64_t packed_average_limbs=0,packed_average_work=0;
    std::uint64_t packed_regret_limbs=0,packed_regret_work=0;
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
inline std::uint64_t artifact_bytes(const Counts& c) {
    return 8+8*header_words+8*integer_words+literal_count*literal_bytes+c.rows*row_bytes+
        sweeps*(8*c.slots*(1+2*integer_words)+4*8*(integer_words+1))+
        8*c.slots+c.rows+8+8*footer_words;
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
            plan_.expected_rank_calls+=unblocked[0]+unblocked[1];
            return;
        }
        meter_.charge(Work::geometry,64*candidate_count(prefix.size));
        reveal(prefix,[&](const Prefix& next) {
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
            const auto dynamic=12+opp*mul_cost(4,reach)+53*bucket_count+
                (showdown?9:3)*opp*add_cost(bucket)+
                own*((showdown?12:3)*add_cost(bucket)+mul_cost(4,bucket)+copy_cost(out)+2*words(bucket))+128;
            // A full lookup checks at most 64 ordered boards. Miss construction
            // has its own upper bound below and no board is evicted in PROOF9.
            sum+=population[sb][bb]*(input+dynamic+(showdown?6*64:0));
        }
        return sum;
    }
    static std::uint64_t quantizer_cost(std::size_t n,std::size_t effective) {
        const auto sum=effective+logceil(n)+1,scaled=effective+grid_bits;
        const auto bits=std::max({std::size_t{53},sum,scaled});
        return 64+16*n+4*n*(words(value_bits)+1)+256+16*n*(words(bits)+1)+
            8*n*(2*words(scaled)*words(sum)+4*words(bits)+8)+4*n*n*(words(sum)+1);
    }
    void literal(std::size_t id,std::array<std::size_t,2> past,std::array<std::size_t,2> first) {
        meter_.charge(Work::geometry,256);
        require(++literals_<=literal_count && id<source_.nodes().size(),"pinned literal census changed");
        const auto& node=source_.nodes()[id];
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
            plan_.quantizer_terms[1]+=rows*quantizer_cost(m,base_bits+2+width(payoff_ceiling_)+plan_.M+E);
            plan_.quantizer_terms[2]+=rows*quantizer_cost(m,base_bits+2+EA);
            plan_.max_actor_depth[actor]=std::max(plan_.max_actor_depth[actor],past[actor]+1);
            work[work_index(Work::reach)]+=plan_.public_walks*np*m*(24+2*(mul_cost(reach_operand_bits,53)+copy_cost(reach_operand_bits)));
            work[work_index(Work::value_add)]+=sweeps*np*m*2*add_cost(value_bits);
            work[work_index(Work::average)]+=sweeps*slots*(16+3*mul_cost(value_bits,53)+copy_cost(value_bits));
            ++past[actor];
            first[actor]+=uniform_exponent(m);
        } else if (node.state.phase==betting::Phase::reveal) {
            const auto next=node.state.next_street;
            require(m==1 && next==(k?k+1:3),"pinned reveal census");
            const auto child=plan_.prefixes[street_index(next)].count;
            shape.reveals+=child;
            shape.candidates+=np*candidate_count(k);
            work[work_index(Work::value_add)]+=seat_passes*child*2*add_cost(value_bits);
            for (std::size_t target=0;target<2;++target) contractions_+=sweeps*chance_cost(false,next,target,0);
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
                        plan_.hidden_candidates+=plan_.prefixes[street].count*candidate_count(visible[street]);
                    work[work_index(Work::value_add)]+=seat_passes*full*2*add_cost(value_bits);
                }
            }
            for (std::size_t target=0;target<2;++target) {
                contractions_+=chance_cost(showdown,showdown?5:k,target,first[1-target]);
                contractions_+=chance_cost(showdown,showdown?5:k,target,grid_bits*past[1-target]);
            }
            work[work_index(Work::terminal_scale)]+=seat_passes*np*2*(16+mul_cost(value_bits,plan_.pay_bits)+mul_cost(value_bits,6)+copy_cost(value_bits));
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
        const auto remaining=deck_cards.size()-4;
        const auto flop=remaining*(remaining-1)*(remaining-2)/6;
        require(chance_divisors==std::array<std::uint64_t,4>{1,flop,flop*(remaining-3),flop*(remaining-3)*(remaining-4)},"pinned chance divisor drift");
        plan_.denominator_base=plan_.normalizer*chance_divisors[3];
        require(plan_.normalizer==29 && plan_.denominator_base==580,"pinned root prior changed");
    }
public:
    Forecast(const betting::Template& source,Meter& meter,Traversal mode,bool packed_averages,bool packed_regrets)
        :source_(source),meter_(meter) {
        require((!packed_averages || mode==Traversal::paired) && (!packed_regrets || packed_averages),
            "invalid packed training profile");
        plan_.traversal=mode;
        plan_.packed_averages=packed_averages;
        plan_.packed_regrets=packed_regrets;
        plan_.public_walks=mode==Traversal::paired?sweeps:seat_passes;
    }
    Plan make() {
        const auto& template_receipt=source_.receipt();
        require(template_receipt.nodes==template_count && template_receipt.edges==410 &&
            template_receipt.logical_occurrences==literal_count && template_receipt.max_depth==15 &&
            !template_receipt.history_suffix_only,"pinned betting source shape changed");
        meter_.charge(Work::geometry,256*template_count);
        prior_geometry();
        prefixes(Prefix{},physical_support(0));
        const auto& p=plan_.prefixes;
        require(p[0].count==1 && p[1].count==25 && p[2].count==56 && p[3].count==60,"pinned physical prefix census changed");
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
            plan_.denominator_bits==635 && plan_.denominator_bits+width(payoff_ceiling_)+3==value_bits,"pinned fixed denominator bounds changed");
        if (plan_.packed_regrets) {
            for (std::size_t id=0;id<source_.nodes().size();++id) {
                meter_.charge(Work::geometry,8);
                require(suffix_[id].mark==2 && suffix_[id].decisions<=plan_.H,"packed regret suffix census changed");
                plan_.suffix_decisions[id]=static_cast<std::uint8_t>(suffix_[id].decisions);
            }
        }
        literal(source_.root(),{},{});
        require(literals_==literal_count && plan_.shape==expected_counts && plan_.max_actor_depth==std::array<std::size_t,2>{6,7} &&
            plan_.showdown_contractions==18180 && plan_.hidden_candidates==22168,
            "pinned complete geometry changed");
        for (std::size_t target=0;target<2;++target) contractions_+=sweeps*chance_cost(false,0,target,0);

        const auto& g=plan_.shape;
        const auto R=g.rows,S=g.slots;
        plan_.template_work=template_receipt.work;
        // Setup bound covers the existing 21,504-unit prior constructor and
        // fixed four-holding copies/normalization. At most 60 misses retain
        // every physically supported ordered board in the 64-plane owner.
        plan_.chance_work=chance_setup_bound+contractions_+p[3].count*(4*4096+512+64+4*64);
        const auto public_walks=plan_.public_walks;
        plan_.history_work=4096*literal_count+1280+(public_walks+1)*(40*g.actions+72*g.reveals+48*g.visits+40*R);
        const auto lookup=16*logceil(static_cast<std::size_t>(R+1));
        plan_.state_work=1024+8*R+16*S+4*words(plan_.denominator_bits)+(128+lookup)*R+256*S+8*S+2*R+
            sweeps*(4*R+16*R+4*S+64*R+128*S+(16*S+8*R)*words(value_bits+58)+4*R)+
            (4*words(value_bits)+4)*S+20*R+4*S;
        for (const auto work:plan_.quantizer_terms) plan_.quantizer_work+=work;
        auto& w=plan_.parent;
        w[work_index(Work::geometry)]=3000000;
        w[work_index(Work::visit)]=(8+public_walks*visit_cost(plan_.traversal))*g.visits;
        w[work_index(Work::support)]=64*((public_walks+1)*g.candidates+public_walks*plan_.hidden_candidates);
        w[work_index(Work::route)]=public_walks*16*R+16*R+4*S;
        w[work_index(Work::average)]+=seat_passes*(g.reveals+1)*24;
        if (plan_.packed_averages) {
            require(plan_.packed_average_limbs>=S && plan_.packed_average_limbs<=words(value_bits)*S,
                "packed average word census outside fixed bounds");
            // Precharge fixed storage codec operations in addition to the
            // original conservative state charge. No training occurs here.
            plan_.packed_average_work=32*R+36*plan_.packed_average_limbs+(14*words(value_bits)+70)*S;
            w[work_index(Work::average)]+=plan_.packed_average_work;
        }
        if (plan_.packed_regrets) {
            require(plan_.packed_regret_limbs>=S && plan_.packed_regret_limbs<=words(value_bits)*S,
                "packed regret word census outside fixed bounds");
            // Covers two signed-delta staging passes, two full checkpoint
            // reads, two compact policy decodes, layout and routing. The
            // original state charge still covers mix and update arithmetic.
            plan_.packed_regret_work=32*R+44*plan_.packed_regret_limbs+(16*words(value_bits)+88)*S;
            w[work_index(Work::route)]+=plan_.packed_regret_work;
        }
        // Fixed-width limb emission, two policy-image checks, literal BFS
        // records, and the bounded header/footer. No per-row history rendering.
        w[work_index(Work::output)]=4*S*(4+2*integer_words)+3*S*2+24*R+
            sweeps*(6*S+32*R)+160*literal_count+65536;
        const auto other_work=plan_.template_work+plan_.chance_work+plan_.history_work+
            plan_.state_work+plan_.quantizer_work;
        require(other_work<=work_cap,"fixed non-parent work exceeds aggregate cap");
        if (plan_.packed_regrets) plan_.parent_allowance=work_cap-other_work;
        plan_.total_work=other_work+sum_work(w);
        plan_.state_entries=1024+16*R+10*S;
        plan_.state_payload=(5*S+256)*(value_bits+58)+640*S+16*R;
        if (plan_.packed_averages) {
            const auto storage=state::State::storage_forecast(
                {static_cast<std::size_t>(R),static_cast<std::size_t>(S),sweeps,15,value_bits,
                 plan_.state_work,plan_.quantizer_work},
                {template_receipt.nodes,template_receipt.edges},{static_cast<std::size_t>(plan_.packed_average_limbs),
                 static_cast<std::size_t>(plan_.packed_regret_limbs)});
            plan_.state_entries=storage.entries;
            plan_.state_payload=storage.payload_bits;
        }
        plan_.entries=plan_.state_entries+template_receipt.entries+template_receipt.peak_scratch_entries+
            chance_entries+32*literal_count+1+parent_entries;
        plan_.payload_bits=plan_.state_payload+chance_payload+8*history_bytes+parent_payload+32*181;
        plan_.output_bytes=artifact_bytes(g);
        require(plan_.template_work<=template_cap && plan_.chance_work<=chance_cap && plan_.history_work<=history_cap &&
            plan_.state_work<=state_cap && plan_.quantizer_work<=quantizer_cap && sum_work(w)<=plan_.parent_allowance &&
            plan_.total_work<=work_cap && plan_.entries<=entries_cap && plan_.payload_bits<=payload_cap &&
            value_bits+58<=65536 && plan_.output_bytes<=22662720,"pinned complete training forecast exceeds original caps");
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
    Counts shape_{};
    std::uint64_t showdown_contractions_=0,hidden_candidates_=0;
    static constexpr std::size_t catalog=targets;

    [[nodiscard]] std::size_t seat(std::size_t lane) const { return Paired?lane:target_; }
    static const Reach& opposite(std::size_t player,const Reach& sb,const Reach& bb) { return player?sb:bb; }

    void add_values(Values& total,const Values& child) {
        meter_.charge(Work::value_add,2*add_cost(value_bits));
        for (std::size_t holding=0;holding<2;++holding) total[holding]+=child[holding];
    }
    void add_lanes(LaneValues& total,const LaneValues& child) {
        for (std::size_t lane=0;lane<lanes;++lane) add_values(total[lane],child[lane]);
    }
    prepared::Contraction contraction(std::size_t target,const Prefix& prefix,chance::TerminalKind kind,const Reach& reach) {
        auto result=chance_.contraction(target,prefix.view(),kind,reach.numerators,reach.exponent);
        require(result.numerators.size()==2 && result.reach_exponent==reach.exponent &&
            result.prefix_divisor==chance_divisors[street_index(prefix.size)],"prepared contraction identity changed");
        return result;
    }
    Marginals marginal(const Prefix& prefix,Support support) {
        Marginals masses{};
        for (std::size_t lane=0;lane<lanes;++lane) {
            meter_.charge(Work::average,24);
            const auto target=seat(lane);
            auto result=contraction(target,prefix,chance::TerminalKind::fold,Reach{});
            auto& mass=masses[lane];
            mass.scale=chance_divisors[3]/result.prefix_divisor;
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
        const auto candidates=candidate_count(prefix.size);
        meter_.charge(Work::support,64*candidates);
        hidden_candidates_+=candidates;
        require(hidden_candidates_<=plan_.hidden_candidates,"hidden runout candidate census changed");
        reveal(prefix,[&](const Prefix& next) {
            if (physical_support(next.mask)[0]) hidden_completions(next,sb,bb,sum);
        });
    }
    LaneValues terminal(const betting::State& node,const Prefix& prefix,const Reach& sb,const Reach& bb) {
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
        std::uint64_t divisor=chance_divisors[3];
        if (showdown) {
            if (prefix.size==5) result=ranked(prefix,sb,bb);
            // An all-in has no later information sets. Integrate completions
            // as raw full-board numerators on one scale, with no History reveal.
            else hidden_completions(prefix,sb,bb,result);
        } else {
            divisor=chance_divisors[street_index(prefix.size)];
            for (std::size_t lane=0;lane<lanes;++lane) {
                const auto target=seat(lane);
                auto raw=contraction(target,prefix,chance::TerminalKind::fold,opposite(target,sb,bb));
                result[lane]={std::move(raw.numerators[0]),std::move(raw.numerators[1])};
            }
        }
        for (std::size_t lane=0;lane<lanes;++lane)
            for (auto& value:result[lane]) {
                value*=money.significand;
                value*=chance_divisors[3]/divisor;
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
            meter_.charge(Work::average,16+3*mul_cost(value_bits,53)+copy_cost(value_bits));
            // Equal sweep weights. Keep the raw sum of own reach times the
            // frozen policy, including zeros, on the fixed game denominator.
            out[action]=prior.numerators[holding]*own.numerators[holding];
            out[action]*=policy[action];
            out[action]*=prior.scale;
            out[action]<<=scale-grid_bits;
        }
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
            const auto candidates=candidate_count(prefix.size);
            meter_.charge(Work::support,64*candidates);
            shape_.candidates+=candidates;
            require(shape_.candidates<=plan_.shape.candidates && node.edges.size()==1,"dense reveal candidate census changed");
            reveal(prefix,[&](const Prefix& next) {
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
            for (std::size_t action=0;action<menu;++action) tokens[action]=node.edges[action].action.token;
            for (std::size_t holding=0;holding<2;++holding) if (support[actor]&(1U<<holding)) {
                const std::span<const std::string_view> actions{tokens.data(),menu};
                std::size_t row;
                if (plan_.packed_regrets)
                    row=state_.register_catalog_row(cursor,actor,holding,id,actions,row_shift,row_regret_shift);
                else if (plan_.packed_averages)
                    row=state_.register_catalog_row(cursor,actor,holding,id,actions,row_shift);
                else row=state_.register_catalog_row(cursor,actor,holding,id,actions);
                require(row==shape_.rows && state_.rows()[row].offset==shape_.slots,"catalog row order changed");
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
        std::array<std::span<const std::uint64_t>,2> policy{};
        for (std::size_t holding=0;holding<2;++holding) if (support[actor]&(1U<<holding)) {
            meter_.charge(Work::route,16);
            require(shape_.rows<state_.rows().size(),"dense policy row overflow");
            const auto row=static_cast<std::size_t>(shape_.rows++);
            const auto& record=state_.rows()[row];
            // Menus come from the same immutable source used at registration.
            // Check the complete identity and packed extent before policy access.
            require(record.history_ordinal==key && record.actor==actor && record.holding_index==holding &&
                record.offset==shape_.slots && record.actions.size()==menu,"dense policy route changed");
            if (plan_.packed_averages)
                require(state_.average_row_shift(row)==row_shift,"packed average row depth changed");
            if (plan_.packed_regrets)
                require(state_.regret_row_shift(row)==row_regret_shift,"packed regret row depth changed");
            shape_.slots+=menu;
            row_ids[holding]=row;
            policy[holding]=state_.policy_units(row);
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
                stage_average({increments.data(),menu},policy[holding],prior[acting_lane],actor_reach,holding);
                result[acting_lane][holding]=state_.stage_row(row_ids[holding],{action_values[holding].data(),menu},{increments.data(),menu});
            }
        }
        return result;
    }
public:
    Walk(const betting::Template& source,const Plan& plan,Meter& meter,history::History& history,
         prepared::PreparedPublicChance& chance,state::State& state,std::size_t target)
        :source_(source),plan_(plan),meter_(meter),history_(history),chance_(chance),state_(state),target_(target) {}
    LaneValues run(Cursor root) {
        require(Paired?(target_==0 && plan_.traversal==Traversal::paired):
            (target_==catalog || (target_<catalog && plan_.traversal==Traversal::by_seat)),"invalid fixed sweep target");
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
public:
    Binary(std::ostream& out,std::uint64_t capacity):out_(out),capacity_(capacity) {
        static_assert(std::endian::native==std::endian::little,"fixed PROOF9 binary producer requires little endian");
    }
    void bytes(const void* data,std::size_t size) {
        require(size<=capacity_-written_,"fixed training output exceeds byte admission");
        if (size) out_.write(static_cast<const char*>(data),static_cast<std::streamsize>(size));
        require(bool(out_),"fixed training output write failed");
        written_+=size;
    }
    void text(std::string_view value) { bytes(value.data(),value.size()); }
    void u64(std::uint64_t value) { bytes(&value,sizeof(value)); }
    void wide(const Integer& value,bool signed_field=false) {
        const auto& raw=value.backend();
        using Limb=std::remove_cvref_t<decltype(raw.limbs()[0])>;
        constexpr auto limb_bits=std::numeric_limits<Limb>::digits;
        static_assert((limb_bits==32 || limb_bits==64) && limb_bits==8*sizeof(Limb),"unsupported fixed proof limb layout");
        constexpr auto wire_bytes=integer_words*sizeof(std::uint64_t);
        constexpr auto value_limbs=(value_bits+limb_bits-1)/limb_bits;
        constexpr auto top_mask=1ULL<<(value_bits%limb_bits);
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
        out_.flush();
        require(bool(out_),"fixed training output flush failed");
    }
};

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
        out.text("OPLDYA01");
        for (const auto word:std::array<std::uint64_t,header_words>{1,grid_bits,integer_words,p.shape.rows,
            p.shape.slots,literal_count,sweeps,p.H,p.M,p.denominator_bits,value_bits,p.output_bytes,2,2,
            p.normalizer,chance_divisors[3]}) out.u64(word);
        out.wide(denominator);
        skeleton(out);
        for (const auto& row:state.rows()) {
            out.u64(row.history_ordinal);
            out.u64(row.actor|(row.holding_index<<8)|(row.actions.size()<<16));
            out.u64(row.offset);
        }
    }
    static std::uint64_t profile(Binary& out,const state::State& state,std::size_t sweep) {
        std::uint64_t changed=0;
        for (std::size_t row=0;row<state.rows().size();++row) {
            const auto units=state.policy_units(row);
            bool distinct=false;
            for (std::size_t action=0;action<units.size();++action) {
                distinct=distinct || units[action]!=uniform_unit(units.size(),action);
                out.u64(units[action]);
            }
            require(sweep || !distinct,"first policy differs from the admitted uniform grid");
            if (distinct) ++changed;
        }
        return changed;
    }
    void footer(Binary& out,const prepared::Receipt& chance,const history::Receipt& history,
                const state::Receipt& state,std::uint64_t feedback) const {
        const auto& p=plan_;
        const std::array<std::uint64_t,6> forecast{p.template_work,p.chance_work,p.history_work,
            p.state_work,p.quantizer_work,sum_work(p.parent)};
        const std::array<std::uint64_t,6> actual{source_.receipt().work,chance.modeled_work,history.work,
            state.state_work,state.quantizer_work,meter_.total()};
        for (std::size_t i=0;i<actual.size();++i) require(actual[i]<=forecast[i],"child component exceeded composed forecast");
        require(chance.completed_contractions==seat_passes*(p.shape.folds+p.showdown_contractions+p.shape.reveals+1) &&
            chance.rank_calls==p.expected_rank_calls && chance.cache_misses==p.prefixes[3].count &&
            chance.cache_hits+chance.cache_misses==seat_passes*p.showdown_contractions && !chance.cache_evictions &&
            chance.peak_live_entries<=chance_entries && chance.peak_integer_payload_bits<=chance_payload &&
            state.completed_sweeps==sweeps && state.rows==p.shape.rows && state.slots==p.shape.slots &&
            state.reserved_entries==p.state_entries && state.reserved_integer_and_text_payload_bits==p.state_payload &&
            feedback && history.owned_bytes<=history_bytes,"completed training receipt differs from admission");
        out.text(p.traversal==Traversal::paired?"OPLDEND2":"OPLDEND1");
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
public:
    explicit Driver(Traversal mode=Traversal::by_seat,bool packed_averages=false,bool packed_regrets=false)
        :plan_(Forecast(source_,meter_,mode,packed_averages,packed_regrets).make()) {}
    Driver(const Driver&)=delete;
    Driver& operator=(const Driver&)=delete;
    Driver(Driver&&)=delete;
    Driver& operator=(Driver&&)=delete;
    [[nodiscard]] const Plan& plan() const noexcept { return plan_; }
    [[nodiscard]] std::uint64_t admission_work() const noexcept { return meter_.total(); }

    void train(std::ostream& stream) {
        require(!entered_,"fixed training owner already entered");
        entered_=true;
        const auto& p=plan_;
        const auto deck=chance::DeckDefinition::reduced(deck_cards);
        chance::Limits chance_limits;
        chance_limits.max_hands_per_side=2;
        chance_limits.max_integer_bits=value_bits+58;
        chance_limits.max_modeled_work=p.chance_work;
        chance_limits.max_storage_entries=chance_entries;
        chance_limits.max_integer_payload_bits=chance_payload;
        prepared::PreparedPublicChance chance(ranges[0],ranges[1],deck,chance_limits,64);
        require(chance.normalizer_integer()==p.normalizer && chance.receipt().modeled_work<=chance_setup_bound,
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
        state::State state(history,{2,2},denominator,
            {static_cast<std::size_t>(p.shape.rows),static_cast<std::size_t>(p.shape.slots),sweeps,15,value_bits,
             p.state_work,p.quantizer_work},
            {p.state_work+p.quantizer_work,value_bits+58,static_cast<std::size_t>(p.state_entries),
             static_cast<std::size_t>(p.state_payload)},
            {source_.nodes().size(),source_.receipt().edges},{static_cast<std::size_t>(p.packed_average_limbs),
             static_cast<std::size_t>(p.packed_regret_limbs)});
        const auto root=history.root();
        (void)Walk<false>(source_,p,meter_,history,chance,state,targets).run(root);
        state.freeze();

        meter_.charge(Work::output,p.parent[work_index(Work::output)]);
        Binary out(stream,p.output_bytes);
        prelude(out,state,denominator);
        std::uint64_t feedback=0;
        for (std::size_t sweep=0;sweep<sweeps;++sweep) {
            state.begin_sweep();
            feedback=profile(out,state,sweep);
            std::array<Values,targets> roots{};
            if (p.traversal==Traversal::paired) roots=Walk<true>(source_,p,meter_,history,chance,state,0).run(root);
            else {
                auto sb=Walk<false>(source_,p,meter_,history,chance,state,0).run(root);
                auto bb=Walk<false>(source_,p,meter_,history,chance,state,1).run(root);
                roots={std::move(sb[0]),std::move(bb[0])};
            }
            require(roots[0][0]+roots[0][1]+roots[1][0]+roots[1][1]==0,"simultaneous fixed profile is not zero-sum");
            state.commit_sweep();
            if (p.packed_regrets) {
                for (std::size_t row=0;row<state.rows().size();++row)
                    for (std::size_t action=0;action<state.rows()[row].actions.size();++action)
                        out.wide(state.regret_numerator(row,action));
            } else {
                for (const auto& value:state.regrets()) out.wide(value);
            }
            if (p.packed_averages) {
                for (std::size_t row=0;row<state.rows().size();++row)
                    for (std::size_t action=0;action<state.rows()[row].actions.size();++action)
                        out.wide(state.average_numerator(row,action));
            } else {
                for (const auto& value:state.averages()) out.wide(value);
            }
            for (const auto& root_value:roots) for (const auto& value:root_value) out.wide(value,true);
        }
        const auto image=state.export_average(!p.packed_averages);
        require(image.kind==dyadic_policy::ImageKind::exported_average && image.rows==p.shape.rows && image.slots==p.shape.slots,
            "fixed export policy image changed");
        for (std::size_t i=0;i<image.slots;++i) out.u64(image.units[i]);
        out.bytes(image.uniform_fallback.get(),image.rows);
        footer(out,chance.receipt(),history.receipt(),state.receipt(),feedback);
        out.finish();
    }
};
} // namespace openpoker::virtual_dyadic_training
