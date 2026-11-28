#pragma once
// Exact row arithmetic only: no History ownership, role-lease or draw authority.
#include "dyadic_policy.hpp"
#include <bit>
#include <vector>

namespace openpoker::opponent_role_row {
namespace q=dyadic_policy;
using Integer=q::Integer;
inline constexpr std::size_t maximum_rows=204,maximum_steps=2,maximum_actions=4;
inline constexpr unsigned regret_power=365,average_power=52;
inline constexpr std::uint64_t work_cap=5'000'000;
inline constexpr std::size_t entries_cap=32768,payload_cap=1<<24;

inline void require(bool value,const char* message) {
    if (!value) throw std::runtime_error(message);
}
inline std::size_t bits(const Integer& value) {
    const auto& b=value.backend();
    return b.size()?std::numeric_limits<boost::multiprecision::limb_type>::digits*(b.size()-1)+
        std::bit_width(b.limbs()[b.size()-1]):0;
}
struct Limits {
    std::size_t rows=maximum_rows,steps=maximum_steps;
    std::uint64_t work=work_cap;
    std::size_t entries=entries_cap,payload_bits=payload_cap;
};
struct Forecast {
    std::uint64_t work=0,quantizer_work=0;
    std::size_t entries=0,payload_bits=0;
};
inline Forecast forecast(Limits l) {
    require(l.rows && l.rows<=maximum_rows && l.steps && l.steps<=maximum_steps &&
        l.work && l.work<=work_cap && l.entries && l.entries<=entries_cap &&
        l.payload_bits && l.payload_bits<=payload_cap,"role row reduce-only limits");
    // Four signed cumulative R coordinates <=371 bits; sum of positive R
    // <=373, Q52-scaled weights <=425. The legacy separate division kernel
    // is reused unchanged with a tighter explicit integer allowance.
    Forecast f;
    f.quantizer_work=l.rows*l.steps*8'000;
    f.work=1024+l.rows*l.steps*2'048+f.quantizer_work;
    f.entries=256+64*l.rows;
    f.payload_bits=65536+l.rows*(2048+4*(371+54+64));
    require(f.work<=l.work && f.entries<=l.entries && f.payload_bits<=l.payload_bits,
        "role row complete scalar admission");
    return f;
}
struct Image {
    std::vector<Integer> regrets,averages;
    std::vector<std::uint64_t> units;
};
class Owner final {
    Limits limits_;
    Forecast forecast_;
    q::Quantizer quantizer_;
    std::size_t rows_=0,steps_=0;
    std::uint64_t own_work_=1024;
    bool failed_=false;
    static q::Limits quantizer_limits(Limits l) {
        const auto f=forecast(l);q::Limits result;
        result.work=f.quantizer_work;result.integer_bits=426;
        result.entries=l.entries;result.integer_payload_bits=l.payload_bits;
        return result;
    }
public:
    explicit Owner(Limits limits={}):limits_(limits),forecast_(forecast(limits)),
        quantizer_(quantizer_limits(limits)) {}
    Owner(const Owner&)=delete;Owner& operator=(const Owner&)=delete;
    [[nodiscard]] bool failed() const {return failed_ || quantizer_.failed();}
    [[nodiscard]] const Forecast& admitted() const {return forecast_;}
    [[nodiscard]] const q::Receipt& quantizer_receipt() const {return quantizer_.receipt();}
    [[nodiscard]] std::uint64_t work() const {return own_work_+quantizer_.receipt().work;}
    [[nodiscard]] std::size_t rows() const {return rows_;}
    [[nodiscard]] std::size_t steps() const {return steps_;}
    // Caller supplies complete immutable step arrays for one synthetic or
    // authenticated raw row. This API cannot authorize a poker role/history.
    std::vector<Image> row(std::span<const std::uint64_t> initial,
        std::span<const std::vector<Integer>> regrets,std::span<const std::vector<Integer>> averages) {
        try {
            require(!failed(),"role row owner failed closed");
            const auto k=initial.size(),count=regrets.size();
            require(k>=2 && k<=maximum_actions && count && count<=limits_.steps && count==averages.size() &&
                rows_<limits_.rows && count<=limits_.rows*limits_.steps-steps_,"role row shape/lifetime");
            std::uint64_t sum=0;
            for (const auto u:initial) {require(u<=q::grid_units && u<=q::grid_units-sum,"role row Q52 units");sum+=u;}
            require(sum==q::grid_units,"role row Q52 partition");
            // All input widths checked before arithmetic/allocation proportional
            // to the row. The owner stays poisoned after any rejected input.
            for (std::size_t s=0;s<count;++s) {
                require(regrets[s].size()==k && averages[s].size()==k,"role row step menu");
                for (std::size_t a=0;a<k;++a)
                    require(bits(regrets[s][a])<=370 && averages[s][a]>=0 && bits(averages[s][a])<=53,
                        "role row raw coordinate width/sign");
            }
            std::vector<Integer> cumulative_r(k),cumulative_a(k);
            std::vector<std::uint64_t> units(initial.begin(),initial.end());
            std::vector<Image> result;result.reserve(count);
            const Integer denominator=Integer(1)<<regret_power;
            for (std::size_t s=0;s<count;++s) {
                own_work_+=2048;require(own_work_<=forecast_.work-forecast_.quantizer_work,"role row own work");
                Integer dot=0;bool changed=false,average_zero=true;
                for (std::size_t a=0;a<k;++a) {
                    require(regrets[s][a]>=-16*denominator && regrets[s][a]<=16*denominator &&
                        averages[s][a]<=q::grid_units,"role row raw magnitude");
                    dot+=regrets[s][a]*units[a];
                    require(bits(dot)<=424,"role row centered product/sum width");
                    changed=changed || regrets[s][a]!=0;average_zero=average_zero && averages[s][a]==0;
                }
                require(dot==0 && bits(dot)<=424,"role row regret not centered on frozen policy");
                for (std::size_t a=0;a<k;++a) {
                    require(average_zero || averages[s][a]==units[a],"role row average must equal frozen Q52 units or zero");
                    cumulative_r[a]+=regrets[s][a];cumulative_a[a]+=averages[s][a];
                    require(bits(cumulative_r[a])<=371 && bits(cumulative_a[a])<=54,"role row cumulative widths");
                }
                if (changed) {
                    const auto prior=quantizer_.receipt().work;
                    const auto policy=quantizer_.regret_policy(cumulative_r);
                    require(quantizer_.receipt().work-prior<=8000,"role row quantizer per-step forecast");
                    units.assign(policy.units().begin(),policy.units().end());
                }
                result.push_back({cumulative_r,cumulative_a,units});++steps_;
            }
            ++rows_;require(work()<=forecast_.work,"role row total work");return result;
        } catch (...) {failed_=true;throw;}
    }
};
}
