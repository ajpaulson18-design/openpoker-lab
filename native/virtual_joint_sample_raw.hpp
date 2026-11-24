#pragma once
// One certified private-pair/board observation, two frozen scalar target passes.
// No sampling/RNG, prior multiplication, clipping, or policy publication here.
#include "virtual_frozen_grid_raw.hpp"
#include "virtual_sparse_strategy_epoch.hpp"

namespace openpoker::virtual_joint_sample_raw {
namespace t=virtual_dyadic_training;
namespace h=virtual_dyadic_history;
namespace b=virtual_betting_template;
namespace p=virtual_frozen_grid_update_forecast;
namespace e=virtual_sparse_strategy_epoch;
namespace raw=virtual_frozen_grid_raw;
using Integer=t::Integer;
using Certificate=t::prepared::PreparedPublicChance::JointTicketCertificate;

struct Reach {
    Integer numerator=1;
    unsigned exponent=0;
};

class Walk final {
    const b::Template& source_;
    h::History& history_;
    e::Store::EpochLease& policy_;
    const Certificate& sample_;
    const p::Geometry& geometry_;
    const p::Forecast& forecast_;
    std::array<std::size_t,2> holdings_;
    std::array<std::uint8_t,5> board_;
    int showdown_sign_;
    const bool weighted_;
    raw::Ledger ledger_;
    raw::Result result_;
    bool entered_=false,complete_=false;

    void check(const Integer& value,std::size_t bits) {
        const auto actual=raw::magnitude_bits(value);
        t::require(actual<=bits && actual<=683,"joint scalar integer width exceeded");
        result_.peak_bits=std::max(result_.peak_bits,actual);
    }
    // Signed right shifts never supply rounding semantics. Validate exact
    // divisibility on the magnitude, then restore the original sign.
    static void reduce_exact(Integer& value,unsigned exponent) {
        const bool negative=value<0;
        if (negative) value=-value;
        if (value!=0) t::require(boost::multiprecision::lsb(value)>=exponent,
            "joint scalar value is not exactly divisible by the required power of two");
        value>>=exponent;
        if (negative) value=-value;
    }
    Reach advance(const Reach& previous,std::uint64_t units) {
        ledger_.charge(raw::Family::reach,24+t::mul_cost(365,53)+t::copy_cost(365));
        t::require(previous.exponent<=312 && previous.numerator>=0 && units<=t::grid,
            "joint scalar reach outside fixed route");
        Reach next;
        next.exponent=previous.exponent+52;
        next.numerator=previous.numerator*units;
        check(next.numerator,365);
        // Zero reach retains the full literal action count and exponent.
        return next;
    }
    Integer terminal(const b::State& state) {
        t::require(++result_.terminals<=1212,"joint scalar terminal census exceeded");
        ledger_.charge(raw::Family::scale,32+t::copy_cost(629));
        const bool fold=state.phase==b::Phase::fold;
        t::require(fold || state.phase==b::Phase::showdown,"joint scalar terminal phase");
        const auto money=t::stake(state);
        t::require(money.power>=-1 && money.power<=3 && money.significand<=15 &&
            (money.significand<<static_cast<unsigned>(money.power+1))<=16,"joint scalar stake bound");
        const auto sign=fold?(state.winner==0?1:-1):showdown_sign_;
        Integer value=money.significand;
        value<<=static_cast<unsigned>(625+money.power);
        if (sign<0) value=-value;
        else if (!sign) value=0;
        check(value,629);return value;
    }
    raw::Row average_row(const e::FrozenPolicyView& view,const Reach& own) {
        const auto count=view.units.size();
        ledger_.charge(raw::Family::average,64+t::copy_cost(365));
        ledger_.charge(raw::Family::stage,64+16*count);
        t::require(own.exponent<=312 && own.numerator>=0,"joint scalar average own reach");
        raw::Row row;
        row.actor=view.row.actor;row.holding=view.row.holding_index;
        row.ordinal=view.row.history_ordinal;row.offset=view.row.offset;row.actions=count;
        row.regret.resize(count);row.average.resize(count);
        row.average_denominator=Integer(1)<<364;
        row.average_mass=own.numerator<<(364-own.exponent);check(row.average_mass,365);
        for (std::size_t action=0;action<count;++action) {
            ledger_.charge(raw::Family::average,32+t::mul_cost(313,53)+t::copy_cost(365)+2*t::words(365));
            Integer value=own.numerator*view.units[action];check(value,365);
            value<<=312-own.exponent;check(value,365);
            row.average[action]=std::move(value);
        }
        return row;
    }
    Integer visit(std::size_t id,h::History::Cursor cursor,std::size_t visible,std::size_t target,
                  const Reach& sb,const Reach& bb) {
        ledger_.charge(raw::Family::walk,128);
        if (weighted_) {
            // Explicit extra allowance for History/source identity and up to
            // four fixed <=16-byte action-token comparisons at a decision.
            ledger_.charge(raw::Family::walk,128);
            t::require(history_.identity_matches(cursor,id,visible),"weighted joint source/history identity");
        }
        t::require(++result_.visits<=2210 && id<source_.nodes().size(),"joint scalar visit census exceeded");
        const auto& node=source_.nodes()[id];
        t::require(node.state.street==visible,"joint scalar visible street identity");
        if (node.state.phase==b::Phase::reveal) {
            t::require(node.edges.size()==1 && ++result_.reveals<=130,"joint scalar reveal census exceeded");
            const auto next=node.state.next_street;
            return visit(node.edges[0].child,history_.append_reveal(cursor,std::span(board_).first(next)),
                         next,target,sb,bb);
        }
        if (node.state.phase==b::Phase::fold || node.state.phase==b::Phase::showdown)
            return terminal(node.state);
        const auto actor=node.state.actor;const auto count=node.edges.size();
        t::require(node.state.phase==b::Phase::decision && actor<2 && count>=2 && count<=4,
            "joint scalar decision/menu shape");
        const auto view=policy_.frozen_policy(cursor,actor,holdings_[actor]);
        t::require(++result_.reads<=868 && view.row.actor==actor &&
            view.row.holding_index==holdings_[actor] && view.units.size()==count && view.row.actions.size()==count,
            "joint scalar selected original holding/menu mismatch");
        if (weighted_) for (std::size_t action=0;action<count;++action)
            t::require(node.edges[action].action.token.size()<=16 &&
                node.edges[action].action.token==view.row.actions[action],"weighted joint numeric/action menu identity");
        std::size_t row_index=0;
        if (actor==target) {
            t::require(result_.rows.size()<434 && count<=1039-result_.slots,"joint scalar staged capacity");
            row_index=result_.rows.size();
            result_.rows.push_back(average_row(view,actor?bb:sb));result_.slots+=count;
        }
        std::array<Integer,4> children{};
        for (std::size_t action=0;action<count;++action) {
            t::require(++result_.actions<=2078,"joint scalar action census exceeded");
            const auto next=advance(actor?bb:sb,view.units[action]);
            children[action]=visit(node.edges[action].child,history_.append_action(cursor,action),visible,target,
                actor?sb:next,actor?next:bb);
        }
        Integer mixed=0;
        for (std::size_t action=0;action<count;++action) {
            ledger_.charge(raw::Family::mix,8+t::mul_cost(629,53)+t::add_cost(683)+t::copy_cost(683));
            Integer product=children[action]*view.units[action];check(product,683);
            mixed+=product;check(mixed,683);
        }
        ledger_.charge(raw::Family::mix,32+t::copy_cost(683)+t::copy_cost(629));
        reduce_exact(mixed,52);check(mixed,629);
        if (actor==target) {
            const auto& opposite=actor?sb:bb;
            t::require(opposite.exponent<=364 && opposite.numerator>=0,"joint scalar opposite reach");
            for (std::size_t action=0;action<count;++action) {
                ledger_.charge(raw::Family::mix,64+t::add_cost(630)+t::copy_cost(630)+
                    t::mul_cost(630,365)+t::copy_cost(630));
                Integer difference=children[action]-mixed;check(difference,630);
                // At this row, earlier opponent actions consume route factors
                // but are absent from this future-value denominator. Cancel
                // their power before multiplying, avoiding a ~995-bit product.
                reduce_exact(difference,opposite.exponent);
                check(difference,630-opposite.exponent);
                difference*=opposite.numerator;check(difference,630);
                if (actor) difference=-difference;
                result_.rows[row_index].regret[action]=std::move(difference);
            }
        }
        return mixed;
    }
public:
    Walk(const b::Template& source,h::History& history,e::Store::EpochLease& policy,
         const Certificate& sample,const p::Geometry& geometry,const p::Forecast& forecast)
        :source_(source),history_(history),policy_(policy),sample_(sample),geometry_(geometry),forecast_(forecast),
         holdings_(sample.holding_indices()),board_(sample.board()),showdown_sign_(sample.showdown_sign()),
         weighted_(policy.arithmetic_contract()==e::ArithmeticContract::weighted_joint_fixed_tree),ledger_(forecast) {
        sample_.require_active();
        const auto counts=policy.declared_hand_counts();
        const bool binding=weighted_ ?
            (sample.purpose()==t::prepared::Purpose::joint_tickets_v1 &&
             sample.declared_hand_counts()==counts && counts[0]<=1326 && counts[1]<=1326 &&
             holdings_[0]<counts[0] && holdings_[1]<counts[1] && history.supports_deck(sample.deck())) :
            (policy.arithmetic_contract()==e::ArithmeticContract::true_joint_proof9 &&
             sample.purpose()==t::prepared::Purpose::legacy_contractions && holdings_[0]<2 && holdings_[1]<2);
        t::require(policy.raw_policy_ready() && binding &&
            showdown_sign_>=-1 && showdown_sign_<=1 && forecast.rows==434 && forecast.slots==1039 &&
            geometry.visits==1105 && geometry.actions==1039 && geometry.decisions==434 &&
            geometry.reveals==65 && geometry.folds==303 && geometry.showdowns==303 &&
            geometry.route==12 && geometry.mix_route==11 && geometry.depth==std::array<std::size_t,2>{6,7},
            "joint scalar fixed request admission");
        ledger_.charge(raw::Family::stage,1024);
        result_.rows.reserve(434);result_.denominator=Integer(1)<<625;check(result_.denominator,626);
    }
    const raw::Result& run() {
        t::require(!entered_,"joint scalar owner already entered");entered_=true;
        sample_.require_active();
        ledger_.charge(raw::Family::walk,512);
        for (std::size_t target=0;target<2;++target) {
            auto value=visit(source_.root(),history_.root(),0,target,Reach{},Reach{});
            if (target) value=-value;
            result_.roots[target]=std::move(value);check(result_.roots[target],629);
        }
        sample_.require_active();
        t::require(result_.roots[0]+result_.roots[1]==0 && result_.rows.size()==forecast_.rows &&
            result_.slots==forecast_.slots && result_.reads==868 && result_.visits==2*geometry_.visits &&
            result_.actions==2*geometry_.actions && result_.reveals==2*geometry_.reveals &&
            result_.terminals==2*(geometry_.folds+geometry_.showdowns),"joint scalar complete two-seat census mismatch");
        complete_=true;return result_;
    }
    [[nodiscard]] const raw::Ledger& ledger() const noexcept {return ledger_;}
    [[nodiscard]] bool complete() const noexcept {return complete_;}
};
} // namespace openpoker::virtual_joint_sample_raw
