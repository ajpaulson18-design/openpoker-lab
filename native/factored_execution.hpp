#pragma once
#include "factored_dyadic.hpp"
#include <algorithm>
#include <cstdint>
#include <stdexcept>

namespace openpoker::factored_dyadic {
struct Receipt {
    std::uint64_t work=0,from_values=0,additions=0,subtractions=0,scales=0,mixes=0,expansions=0;
    std::uint64_t implicit_zero_bits=0;
    unsigned maximum_coefficient_bits=0,maximum_shift=0;
};

// One shared cumulative metadata allowance for a training invocation. Existing
// learning ledgers continue to reserve the bounded wide arithmetic and codecs.
class Execution final {
    std::uint64_t limit_;
    Receipt receipt_{};
    bool failed_=false;

    void charge(std::uint64_t work) {
        if (failed_ || work>limit_-receipt_.work) {
            failed_=true;
            throw std::runtime_error("factored execution metadata allowance exceeded");
        }
        receipt_.work+=work;
    }
    Value record(Value value) {
        receipt_.maximum_coefficient_bits=std::max(receipt_.maximum_coefficient_bits,value.coefficient_bits());
        receipt_.maximum_shift=std::max(receipt_.maximum_shift,value.shift());
        if (!value.is_zero()) receipt_.implicit_zero_bits+=value.shift();
        return value;
    }
    template<class Operation>
    Value evaluate(std::uint64_t work,std::uint64_t& count,Operation operation) {
        charge(work);
        try {
            auto result=record(operation());
            ++count;
            return result;
        } catch (...) { failed_=true;throw; }
    }
public:
    explicit Execution(std::uint64_t limit):limit_(limit) {
        if (!limit) throw std::invalid_argument("factored execution needs a positive allowance");
    }
    Execution(const Execution&)=delete;
    Execution& operator=(const Execution&)=delete;
    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }

    Value from_integer(Integer value) {
        return evaluate(64,receipt_.from_values,[&] {return Value::from_integer(std::move(value));});
    }
    Value added(const Value& a,const Value& b) {
        return evaluate(64,receipt_.additions,[&] {return a.added(b);});
    }
    Value subtracted(const Value& a,const Value& b) {
        return evaluate(64,receipt_.subtractions,[&] {return a.subtracted(b);});
    }
    Value scaled(const Value& value,std::uint64_t factor,unsigned shift,bool negate) {
        return evaluate(64,receipt_.scales,[&] {return value.scaled(factor,shift,negate);});
    }
    Value mix(std::span<const Value> values,std::span<const std::uint64_t> units) {
        return evaluate(320,receipt_.mixes,[&] {return Value::mix(values,units);});
    }
    Integer expanded(const Value& value) {
        charge(64);
        try {
            auto result=value.expanded();
            ++receipt_.expansions;
            return result;
        } catch (...) {failed_=true;throw;}
    }
};
}
