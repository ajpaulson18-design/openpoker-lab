#pragma once
// Two literal target walks with supplied Q52 tickets. No RNG or reach product.
#include "virtual_opponent_role_walk_forecast.hpp"
#include <boost/multiprecision/cpp_int/import_export.hpp>

namespace openpoker::virtual_opponent_role_walk {
namespace f=virtual_opponent_role_walk_forecast;
namespace t=f::t;
namespace r=f::r;
namespace b=t::betting;
using Integer=t::Integer;
using Packed=std::array<std::uint64_t,7>;
inline Packed pack(const Integer& value) {
    t::require(r::e::magnitude_bits(value)<=370,"role raw packed magnitude");Packed result{};
    const bool negative=value<0;const Integer magnitude=negative?-value:value;
    boost::multiprecision::export_bits(magnitude,result.begin(),64,false);
    if(negative){std::uint64_t carry=1;for(auto& word:result){word=~word;const auto old=word;word+=carry;carry=static_cast<std::uint64_t>(carry && word<old);}}
    return result;
}
inline Integer unpack(Packed value) {
    const bool negative=(value.back()>>63)!=0;
    if(negative){std::uint64_t carry=1;for(auto& word:value){word=~word;const auto old=word;word+=carry;carry=static_cast<std::uint64_t>(carry && word<old);}}
    Integer result;boost::multiprecision::import_bits(result,value.begin(),value.end(),64,false);
    t::require(r::e::magnitude_bits(result)<=370,"role raw unpacked magnitude");return negative?-result:result;
}
inline std::size_t select(std::span<const std::uint64_t> units,std::uint64_t ticket) {
    t::require(units.size()>=2 && units.size()<=4 && ticket<t::grid,"role action ticket/menu domain");
    std::uint64_t cumulative=0;std::size_t chosen=units.size();
    for(std::size_t a=0;a<units.size();++a) {
        t::require(units[a]<=t::grid-cumulative,"role action CDF partition overflow");cumulative+=units[a];
        if(chosen==units.size() && ticket<cumulative)chosen=a;
    }
    t::require(cumulative==t::grid && chosen<units.size() && units[chosen]>0,"role action ticket outside positive support");return chosen;
}
struct Row {
    std::uint64_t actor=0,holding=0,ordinal=0,source=0,actions=0,roles=0;
    std::array<std::uint64_t,4> units{},averages{};
    std::array<Packed,4> regrets{};
    r::Store::Token token{};
};
static_assert(sizeof(Row)<=56*sizeof(std::uint64_t),"role raw row fixed reservation");
struct Choice {std::uint64_t target=0,actor=0,holding=0,ordinal=0,source=0,action=0,ticket=0,units=0;};
static_assert(sizeof(Choice)==8*sizeof(std::uint64_t));
struct Counts {
    std::array<std::uint64_t,2> visits{},actions{},reveals{},terminals{},decisions{},own_rows{},tickets{};
};
enum class Family:std::size_t{scale,mix,regret,average,stage,walk};
class Walk final {
    const b::Template& source_;
    r::h::History& history_;
    r::Store::Epoch& epoch_;
    const r::Certificate& world_;
    const std::array<std::span<const std::uint64_t>,2> tapes_;
    const std::array<std::uint64_t,6> limits_;
    std::array<std::uint64_t,6> actual_{};
    std::array<std::int16_t,1105> directory_{};
    std::vector<Row> rows_;
    std::vector<Choice> choices_;
    std::array<Integer,2> roots_{};
    Counts counts_{};
    std::size_t slots_=0,peak_bits_=0;
    bool entered_=false,complete_=false;
    void charge(Family family,std::uint64_t amount) {
        const auto i=static_cast<std::size_t>(family);t::require(amount<=limits_[i]-actual_[i],"role raw family work exhausted");actual_[i]+=amount;
    }
    void check(const Integer& value,std::size_t bits) {
        const auto width=r::e::magnitude_bits(value);t::require(width<=bits && width<=423,"role raw exact integer width");peak_bits_=std::max(peak_bits_,width);
    }
    static std::uint64_t total(const std::array<std::uint64_t,2>& x){return x[0]+x[1];}
    Integer visit(std::size_t source,r::h::History::Cursor cursor,std::size_t visible,std::size_t target) {
        charge(Family::walk,256);t::require(history_.identity_matches(cursor,source,visible) && source<source_.nodes().size(),"role raw source/History identity");
        ++counts_.visits[target];t::require(total(counts_.visits)<=f::visits,"role raw visit bound");
        const auto& node=source_.nodes()[source];t::require(node.state.street==visible,"role raw visible street");
        if(node.state.phase==b::Phase::reveal) {
            ++counts_.reveals[target];t::require(node.edges.size()==1 && total(counts_.reveals)<=f::reveals,"role raw reveal bound");
            return visit(node.edges[0].child,history_.append_reveal(cursor,std::span(world_.board()).first(node.state.next_street)),node.state.next_street,target);
        }
        if(node.state.phase==b::Phase::fold || node.state.phase==b::Phase::showdown) {
            ++counts_.terminals[target];t::require(total(counts_.terminals)<=f::terminals,"role raw terminal bound");charge(Family::scale,32+t::copy_cost(369));
            const auto money=t::stake(node.state);t::require(money.power>=-1 && money.power<=3 && money.significand<=15 &&
                (money.significand<<static_cast<unsigned>(money.power+1))<=16,"role raw whole-hand payoff bound");
            auto sign=node.state.phase==b::Phase::fold?(node.state.winner==0?1:-1):world_.showdown_sign();if(target)sign=-sign;
            Integer value=money.significand;value<<=static_cast<unsigned>(365+money.power);
            if(sign<0)value=-value;else if(!sign)value=0;check(value,369);return value;
        }
        const auto actor=node.state.actor;const auto k=node.edges.size();
        t::require(node.state.phase==b::Phase::decision && actor<2 && k>=2 && k<=4,"role raw decision/menu");
        ++counts_.decisions[target];t::require(total(counts_.decisions)<=f::decisions,"role raw decision bound");
        const auto view=epoch_.observe(cursor,actor,world_.holding_indices()[actor]);
        t::require(view.units.size()==k && view.descriptor.actions.size()==k,"role raw frozen legal menu");
        for(std::size_t a=0;a<k;++a)t::require(node.edges[a].action.token.size()<=16 && node.edges[a].action.token==view.descriptor.actions[a],"role raw exact action token");
        const auto path=history_.literal_ordinal(cursor);t::require(path<directory_.size(),"role raw literal directory domain");auto index=directory_[path];
        if(index<0) {
            t::require(rows_.size()<204 && k<=816-slots_,"role raw row/slot bound");charge(Family::walk,256+16*k);
            index=static_cast<std::int16_t>(rows_.size());directory_[path]=index;rows_.emplace_back();auto& row=rows_.back();
            row.actor=actor;row.holding=view.descriptor.holding_index;row.ordinal=view.descriptor.history_ordinal;row.source=source;row.actions=k;row.token=view.token;
            std::copy(view.units.begin(),view.units.end(),row.units.begin());slots_+=k;
        }
        auto& row=rows_[static_cast<std::size_t>(index)];
        t::require(row.actor==actor && row.holding==view.descriptor.holding_index && row.ordinal==view.descriptor.history_ordinal && row.source==source && row.actions==k &&
            std::equal(view.units.begin(),view.units.end(),row.units.begin()),"role raw bound-world directory identity");
        row.roles|=std::uint64_t{1}<<target;t::require(row.roles==view.roles,"role raw/facade target role agreement");
        if(actor!=target) {
            charge(Family::average,64+16*k);const auto at=counts_.tickets[target];
            t::require(at<tapes_[target].size() && choices_.size()<204,"role raw action tape exhausted");const auto ticket=tapes_[target][at];
            const auto action=select(view.units,ticket);++counts_.tickets[target];
            std::copy(view.units.begin(),view.units.end(),row.averages.begin());
            choices_.push_back({target,actor,row.holding,row.ordinal,source,action,ticket,view.units[action]});
            ++counts_.actions[target];t::require(total(counts_.actions)<=f::actions,"role raw action bound");
            return visit(node.edges[action].child,history_.append_action(cursor,action),visible,target);
        }
        ++counts_.own_rows[target];t::require(total(counts_.own_rows)<=f::own_rows,"role raw own-row bound");std::array<Integer,4> children{};
        for(std::size_t a=0;a<k;++a) {
            ++counts_.actions[target];t::require(total(counts_.actions)<=f::actions,"role raw own action bound");
            children[a]=visit(node.edges[a].child,history_.append_action(cursor,a),visible,target);
        }
        Integer mixed=0;
        for(std::size_t a=0;a<k;++a) {
            charge(Family::mix,8+t::mul_cost(369,53)+t::add_cost(423)+t::copy_cost(423));
            Integer product=children[a]*row.units[a];check(product,423);mixed+=product;check(mixed,423);
        }
        charge(Family::mix,64+t::copy_cost(423)+t::copy_cost(369)+2*t::words(423));
        const bool negative=mixed<0;if(negative)mixed=-mixed;
        if(mixed!=0)t::require(boost::multiprecision::lsb(mixed)>=52,"role raw mixture not exactly divisible on compact carrier");
        mixed>>=52;if(negative)mixed=-mixed;check(mixed,369);
        for(std::size_t a=0;a<k;++a) {
            charge(Family::regret,64+t::add_cost(370)+t::copy_cost(370)+512);Integer delta=children[a]-mixed;check(delta,370);row.regrets[a]=pack(delta);
        }
        return mixed;
    }
public:
    Walk(const b::Template& source,r::h::History& history,r::Store::Epoch& epoch,const r::Certificate& world,
         std::array<std::span<const std::uint64_t>,2> tapes,const f::Raw& budget)
        :source_(source),history_(history),epoch_(epoch),world_(world),tapes_(tapes),
         limits_{budget.scale,budget.mix,budget.regret,budget.average,budget.stage,budget.walk} {
        epoch.require_world(world);t::require(world.purpose()==t::prepared::Purpose::joint_tickets_v1 && history.supports_deck(world.deck()) &&
            tapes[0].size()+tapes[1].size()<=204,"role raw certificate/tape admission");
        for(const auto tape:tapes)for(const auto ticket:tape)t::require(ticket<t::grid,"role raw ticket width");
        charge(Family::walk,512+8*1105);charge(Family::stage,1024);directory_.fill(-1);rows_.reserve(204);choices_.reserve(204);
    }
    void run() {
        t::require(!entered_,"role raw owner reused");entered_=true;
        for(std::size_t target=0;target<2;++target) {
            t::require(epoch_.current_target()==target,"role raw target phase");roots_[target]=visit(source_.root(),history_.root(),0,target);
            t::require(counts_.tickets[target]==tapes_[target].size() && counts_.visits[target]==counts_.actions[target]+counts_.reveals[target]+1 &&
                counts_.visits[target]==counts_.decisions[target]+counts_.reveals[target]+counts_.terminals[target],"role raw complete target/tape census");
            epoch_.finish_target(target);
        }
        t::require(total(counts_.decisions)==total(counts_.own_rows)+total(counts_.tickets) && choices_.size()==total(counts_.tickets),"role raw complete roles");
        epoch_.seal();
        for(auto& row:rows_) {
            charge(Family::stage,256+512*row.actions);std::array<Integer,4> rr{};
            for(std::size_t a=0;a<row.actions;++a)rr[a]=unpack(row.regrets[a]);
            epoch_.stage(row.token,std::span(rr).first(row.actions),std::span(row.averages).first(row.actions));row.token={};
        }
        world_.require_active();complete_=true;
    }
    [[nodiscard]] const auto& rows() const {t::require(complete_,"role raw rows before completion");return rows_;}
    [[nodiscard]] const auto& choices() const {t::require(complete_,"role raw choices before completion");return choices_;}
    [[nodiscard]] const auto& roots() const {t::require(complete_,"role raw roots before completion");return roots_;}
    [[nodiscard]] const auto& counts() const {return counts_;}
    [[nodiscard]] const auto& actual_work() const {return actual_;}
    [[nodiscard]] std::size_t slots() const {return slots_;}
    [[nodiscard]] std::size_t peak_bits() const {return peak_bits_;}
};
}
