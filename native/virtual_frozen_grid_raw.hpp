#pragma once
// Fixed-policy raw values/regrets/averages only. No clipping or State update.
#include "virtual_frozen_policy_snapshot.hpp"
#include "virtual_frozen_grid_update_forecast.hpp"

namespace openpoker::virtual_frozen_grid_raw {
namespace t=virtual_dyadic_training;
namespace h=virtual_dyadic_history;
namespace s=virtual_dyadic_state;
namespace b=virtual_betting_template;
namespace p=virtual_frozen_grid_update_forecast;
namespace proposal=virtual_frozen_update;
using Integer=t::Integer;
using Values=t::Values;
using Reach=t::Reach;

enum class Family : std::size_t { reach,scale,mix,average,stage,walk,count };
class Ledger final {
    std::array<std::uint64_t,6> limits_,actual_{};
public:
    explicit Ledger(const p::Forecast& f):limits_{f.reach,f.scale,f.mix,f.average,f.stage,f.walk} {}
    void charge(Family family,std::uint64_t work) {
        const auto i=static_cast<std::size_t>(family);
        t::require(work<=limits_[i]-actual_[i],"raw-update parent family exceeded");actual_[i]+=work;
    }
    [[nodiscard]] std::uint64_t total() const {
        std::uint64_t value=0;for (const auto n:actual_) value+=n;return value;
    }
    [[nodiscard]] const auto& actual() const noexcept {return actual_;}
};
inline std::size_t magnitude_bits(const Integer& value) {
    // cpp_int is signed magnitude. Inspect the normalized top limb without
    // constructing an absolute-value copy at each intermediate check.
    const auto& backend=value.backend();const auto n=backend.size();
    constexpr auto limb_bits=std::numeric_limits<boost::multiprecision::limb_type>::digits;
    static_assert(limb_bits==32 || limb_bits==64);
    return n?limb_bits*(static_cast<std::size_t>(n)-1)+std::bit_width(backend.limbs()[n-1]):0;
}
struct Row {
    std::uint64_t actor=0,holding=0,ordinal=0,offset=0,actions=0;
    Integer average_denominator=1,average_mass=0;
    std::vector<Integer> regret,average;
};
struct Result {
    std::vector<Row> rows;
    Integer denominator;
    Values roots{};
    std::uint64_t slots=0,visits=0,actions=0,reveals=0,terminals=0,reads=0;
    std::size_t peak_bits=0;
};

class Walk final {
    const b::Template& source_;
    h::History& history_;
    s::State& state_;
    t::prepared::PreparedPublicChance& chance_;
    const p::Geometry& geometry_;
    const p::Forecast& forecast_;
    std::array<std::uint8_t,5> board_;
    proposal::ProposalSnapshot law_;
    Ledger ledger_;
    std::array<std::array<Values,2>,4> masses_{};
    std::array<std::array<unsigned,2>,4> support_{};
    Result result_;
    bool entered_=false,complete_=false;
    void check(const Integer& value,std::size_t bound) {
        const auto bits=magnitude_bits(value);t::require(bits<=bound && bits<=704,"raw-update integer bound exceeded");
        result_.peak_bits=std::max(result_.peak_bits,bits);
    }
    void prepare_marginals() {
        ledger_.charge(Family::stage,512);
        constexpr std::array<std::size_t,4> lengths{0,3,4,5};
        constexpr std::array<std::uint64_t,4> divisors{1,10,20,20};
        const Values unit{1,1};
        for (std::size_t k=0;k<4;++k) for (std::size_t actor=0;actor<2;++actor) {
            auto value=chance_.contraction(actor,std::span(board_).first(lengths[k]),t::chance::TerminalKind::fold,unit,0);
            t::require(value.numerators.size()==2 && value.reach_exponent==0 && value.prefix_divisor==divisors[k],"raw prefix marginal identity");
            for (std::size_t holding=0;holding<2;++holding) {
                check(value.numerators[holding],5);
                t::require(value.numerators[holding]>=0 && value.numerators[holding]<=29,"raw prefix marginal mass");
                support_[k][actor]|=static_cast<unsigned>(value.numerators[holding]>0)<<holding;
                masses_[k][actor][holding]=std::move(value.numerators[holding]);
            }
        }
    }
    Values terminal(const b::State& node,std::size_t target,const Reach& opposite) {
        t::require(++result_.terminals<=2*(geometry_.folds+geometry_.showdowns),"raw terminal census exceeded");
        const bool fold=node.phase==b::Phase::fold;
        const auto kind=fold?t::chance::TerminalKind::fold:t::chance::TerminalKind::showdown;
        auto values=chance_.contraction(target,board_,kind,opposite.numerators,opposite.exponent);
        t::require(values.numerators.size()==2 && values.reach_exponent==opposite.exponent && values.prefix_divisor==20,"raw terminal contraction identity");
        const auto stake=t::stake(node);
        t::require(stake.power>=-1 && stake.power<=3 && stake.significand<=15 &&
            (stake.significand<<static_cast<unsigned>(stake.power+1))<=16,"raw terminal money bound");
        const auto shift=625-static_cast<int>(opposite.exponent)+stake.power;
        t::require(shift>=0 && opposite.exponent<=364,"raw terminal reach exponent");
        Values output{};
        for (std::size_t i=0;i<2;++i) {
            ledger_.charge(Family::scale,32+t::mul_cost(378,4)+t::mul_cost(382,14)+t::copy_cost(647)+2*t::words(699));
            auto value=std::move(values.numerators[i]);check(value,378);
            value*=stake.significand;check(value,382);
            value*=law_.board.denominator;check(value,396);
            value<<=static_cast<unsigned>(shift);check(value,647);
            if (fold && node.winner!=target) value=-value;
            output[i]=std::move(value);
        }
        return output;
    }
    Row average_row(const s::FrozenPolicyView& view,std::size_t holding,std::size_t street,const Reach& own) {
        const auto count=view.row.actions.size();const auto k=t::street_index(street);const auto q=law_.prefix[k];
        t::require(own.exponent<=312 && own.numerators[holding]>=0,"raw average own reach");
        ledger_.charge(Family::average,64+t::mul_cost(5,14)+t::mul_cost(313,19)+t::copy_cost(381)+t::copy_cost(383));
        ledger_.charge(Family::stage,64+16*count);
        Row row;row.actor=view.row.actor;row.holding=holding;row.ordinal=view.row.history_ordinal;
        row.offset=view.row.offset;row.actions=count;
        row.regret.resize(count);row.average.resize(count);
        Integer base=masses_[k][view.row.actor][holding]*q.denominator;
        base*=own.numerators[holding];check(base,331);
        constexpr std::array<std::uint64_t,4> divisors{1,10,20,20};
        row.average_denominator=Integer(29)*divisors[k]*q.numerator;
        row.average_denominator<<=own.exponent+52;check(row.average_denominator,381);
        row.average_mass=base<<52;check(row.average_mass,383);
        for (std::size_t a=0;a<count;++a) {
            ledger_.charge(Family::average,16+t::mul_cost(332,53)+t::copy_cost(383));
            row.average[a]=base*view.units[a];check(row.average[a],383);
        }
        return row;
    }
    Values visit(std::size_t id,h::History::Cursor cursor,std::size_t visible,std::size_t target,const Reach& sb,const Reach& bb) {
        ledger_.charge(Family::walk,128);
        t::require(++result_.visits<=2*geometry_.visits && id<source_.nodes().size(),"raw visit census exceeded");
        const auto& node=source_.nodes()[id];t::require(node.state.street==visible,"raw visible street identity");
        if (node.state.phase==b::Phase::reveal) {
            t::require(node.edges.size()==1 && ++result_.reveals<=2*geometry_.reveals,"raw reveal census exceeded");
            const auto next=node.state.next_street;
            return visit(node.edges[0].child,history_.append_reveal(cursor,std::span(board_).first(next)),next,target,sb,bb);
        }
        if (node.state.phase==b::Phase::fold || node.state.phase==b::Phase::showdown)
            return terminal(node.state,target,target?sb:bb);
        t::require(node.state.phase==b::Phase::decision && node.state.actor<2 && node.edges.size()>=2 && node.edges.size()<=4,"raw decision shape");
        const auto actor=node.state.actor;const auto menu=node.edges.size();const auto k=t::street_index(visible);
        const auto support=support_[k][actor];
        std::array<std::span<const std::uint64_t>,2> units{};
        std::array<std::size_t,2> staged{};
        for (std::size_t holding=0;holding<2;++holding) if (support&(1U<<holding)) {
            const auto view=state_.frozen_policy(cursor,actor,holding);++result_.reads;
            t::require(view.row.actions.size()==menu,"raw State ordered menu extent");units[holding]=view.units;
            if (actor==target) {
                t::require(result_.rows.size()<forecast_.rows && menu<=forecast_.slots-result_.slots,"raw staged row/slot capacity");
                staged[holding]=result_.rows.size();
                result_.rows.push_back(average_row(view,holding,visible,actor?bb:sb));result_.slots+=menu;
            }
        }
        std::array<Values,4> children{};
        for (std::size_t a=0;a<menu;++a) {
            t::require(++result_.actions<=2*geometry_.actions,"raw action census exceeded");
            ledger_.charge(Family::reach,24+2*(t::mul_cost(365,53)+t::copy_cost(365)));
            const auto next=t::advanced_exact_reach(actor?bb:sb,units,a,support);
            children[a]=visit(node.edges[a].child,history_.append_action(cursor,a),visible,target,actor?sb:next,actor?next:bb);
        }
        Values mixed{};
        for (std::size_t holding=0;holding<2;++holding) {
            for (std::size_t a=0;a<menu;++a) {
                ledger_.charge(Family::mix,8+t::mul_cost(647,53)+t::add_cost(699)+t::copy_cost(699));
                if (actor==target) {
                    if (support&(1U<<holding)) mixed[holding]+=children[a][holding]*units[holding][a];
                    else t::require(children[a][holding]==0,"unsupported raw target has nonzero child");
                } else mixed[holding]+=children[a][holding];
                check(mixed[holding],actor==target?699:647);
            }
            if (actor==target) {
                ledger_.charge(Family::mix,t::copy_cost(699)+t::copy_cost(648));
                // Canonical multiply-first kernel; divide-first is a separate
                // potential optimization, not silently assumed in this ledger.
                t::require(mixed[holding]%t::grid==0,"raw target mixture is not exactly divisible by Q52");
                const bool negative=mixed[holding]<0;
                if (negative) mixed[holding]=-mixed[holding];
                mixed[holding]>>=52;
                if (negative) mixed[holding]=-mixed[holding];
                check(mixed[holding],647);
                if (support&(1U<<holding)) for (std::size_t a=0;a<menu;++a) {
                    ledger_.charge(Family::mix,8+t::add_cost(648)+t::copy_cost(648));
                    auto& value=result_.rows[staged[holding]].regret[a];value=children[a][holding]-mixed[holding];check(value,648);
                }
            }
        }
        return mixed;
    }
public:
    Walk(const b::Template& source,h::History& history,s::State& state,t::prepared::PreparedPublicChance& chance,
         const p::Geometry& geometry,const p::Forecast& forecast,std::array<std::uint8_t,5> board,proposal::ProposalKind law)
      :source_(source),history_(history),state_(state),chance_(chance),geometry_(geometry),forecast_(forecast),board_(board),
       law_(proposal::proposal_for(t::chance::DeckDefinition::reduced(t::deck_cards),board,law)),ledger_(forecast) {
        t::require(forecast.feasible && geometry.mix_route==11 && geometry.route==12 && geometry.depth==std::array<std::size_t,2>{6,7},"raw fixed route admission");
        t::require(state.frozen_policy_receipt().ready && state.regrets().empty() && state.averages().empty(),"raw update needs immutable policy-only State");
        result_.rows.reserve(static_cast<std::size_t>(forecast.rows));
        ledger_.charge(Family::stage,512);
        result_.denominator=Integer(580)*law_.board.numerator;result_.denominator<<=625;check(result_.denominator,638);
    }
    const Result& run() {
        t::require(!entered_,"raw update owner already entered");entered_=true;
        prepare_marginals();ledger_.charge(Family::walk,512);
        for (std::size_t target=0;target<2;++target) {
            const auto value=visit(source_.root(),history_.root(),0,target,Reach{},Reach{});
            result_.roots[target]=value[0]+value[1];check(result_.roots[target],647);
        }
        t::require(result_.roots[0]+result_.roots[1]==0,"raw root is not globally zero-sum");
        t::require(result_.rows.size()==forecast_.rows && result_.slots==forecast_.slots && result_.reads==2*forecast_.rows &&
            result_.visits==2*geometry_.visits && result_.actions==2*geometry_.actions && result_.reveals==2*geometry_.reveals &&
            result_.terminals==2*(geometry_.folds+geometry_.showdowns),"raw complete-walk census mismatch");
        complete_=true;return result_;
    }
    [[nodiscard]] const Ledger& ledger() const noexcept {return ledger_;}
    [[nodiscard]] bool complete() const noexcept {return complete_;}
};
} // namespace openpoker::virtual_frozen_grid_raw
