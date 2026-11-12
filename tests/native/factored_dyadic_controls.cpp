#include "../../native/factored_execution.hpp"
#include "../../native/factored_dyadic.hpp"

#include <array>
#include <iostream>
#include <stdexcept>

using openpoker::factored_dyadic::Integer;
using openpoker::factored_dyadic::Value;

namespace {
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
}

int main() {
    using namespace openpoker::factored_dyadic;
    const Value zero;
    require(zero.is_zero() && zero.shift() == 0 && zero.expanded() == 0,
            "canonical zero");

    const Value a = Value::from_scaled(Integer(7), 3);
    const Value b = Value::from_scaled(Integer(-1), 1);
    require(a.added(b).expanded() == 54, "addition across shifts");
    require(a.subtracted(a).is_zero(), "signed cancellation");
    require(a.subtracted(Value::from_integer(Integer(10))).expanded() == 46,
            "negative subtraction");
    require(a.scaled(9, 2, true).expanded() == -2016, "scaled negation");
    const Value lower_shift = Value::from_scaled(Integer(3), 1);
    const Value higher_shift = Value::from_scaled(Integer(2), 3);
    require(lower_shift.added(higher_shift).expanded() == 22,
            "addition with left operand at lower shift");
    require(lower_shift.subtracted(higher_shift).expanded() == -10,
            "subtraction with right operand at higher shift");

    const std::array<Value, 2> integral_values{
        Value::from_scaled(Integer(1), 1), Value::from_integer(Integer(0))};
    constexpr std::array<std::uint64_t, 2> integral_units{ kMixGrid / 2, kMixGrid / 2 };
    require(Value::mix(integral_values, integral_units).expanded() == 1,
            "exactly divisible mix");

    const std::array<Value, 4> quarter_values{
        Value::from_integer(Integer(1)), Value::from_integer(Integer(1)),
        Value::from_integer(Integer(3)), Value::from_integer(Integer(3))};
    const std::array<std::uint64_t, 4> quarter_units{
        kMixGrid / 4, kMixGrid / 4, kMixGrid / 4, kMixGrid / 4};
    require(Value::mix(quarter_values, quarter_units).expanded() == 2,
            "four-way shared unit factors preserve exact average");

    const std::array<Value, 2> fractional_values{
        Value::from_integer(Integer(1)), Value::from_integer(Integer(0))};
    bool fractional_rejected = false;
    try {
        (void)Value::mix(fractional_values, integral_units);
    } catch (const std::invalid_argument&) { fractional_rejected = true; }
    require(fractional_rejected, "fractional mix rejected");

    const std::array<Value, 3> weighted_values{
        Value::from_scaled(Integer(3), 52), Value::from_scaled(Integer(-2), 53),
        Value::from_integer(Integer(98))};
    const std::array<std::uint64_t, 3> weighted_units{
        kMixGrid / 4, kMixGrid / 4, kMixGrid / 2};
    const auto weighted = Value::mix(weighted_values, weighted_units);
    std::cout << "weighted\t" << weighted.coefficient() << '\t' << weighted.shift() << '\n';

    bool invalid_partition_rejected = false;
    try {
        const std::array<std::uint64_t, 2> bad_units{1, 1};
        (void)Value::mix(fractional_values, bad_units);
    } catch (const std::invalid_argument&) { invalid_partition_rejected = true; }
    require(invalid_partition_rejected, "bad partition rejected");

    bool bound_rejected = false;
    try { (void)Value::from_scaled(Integer(1), kMaximumExpandedBits + 1); }
    catch (const std::overflow_error&) { bound_rejected = true; }
    require(bound_rejected, "shift bound rejected");

    const auto edge = Value::from_scaled(Integer(1), kMaximumExpandedBits - 1);
    require(edge.coefficient_bits() == 1 && edge.expanded_bits() == kMaximumExpandedBits,
            "cached width accessors");
    require(edge.expanded() == (Integer(1) << (kMaximumExpandedBits - 1)),
            "maximum supported expansion");

    const std::array<Value, 2> pure_values{edge, Value::from_integer(Integer(5))};
    const std::array<std::uint64_t, 2> pure_units{kMixGrid, 0};
    const Value pure = Value::mix(pure_values, pure_units);
    require(pure.coefficient() == edge.coefficient() && pure.shift() == edge.shift(),
            "pure policy preserves maximum value without scaling");

    const Integer maximum_coefficient = Integer(1) << (kMaximumExpandedBits - 1);
    const Value positive = Value::from_scaled(maximum_coefficient, 0);
    const Value negative = Value::from_scaled(-maximum_coefficient, 0);
    require(positive.added(negative).is_zero(), "maximum-width opposite-sign cancellation");
    require(positive.subtracted(positive).is_zero(), "maximum-width same-sign cancellation");

    const Value product_at_limit = Value::from_scaled(
        Integer(1) << (kMaximumExpandedBits - 2), 0).scaled(2, 0);
    require(product_at_limit.coefficient_bits() == kMaximumExpandedBits,
            "704-bit product admitted");
    bool product_over_limit_rejected = false;
    try { (void)positive.scaled(2, 0); }
    catch (const std::overflow_error&) { product_over_limit_rejected = true; }
    require(product_over_limit_rejected, "705-bit product rejected before materialization");

    const std::array<Value, 2> mix_at_limit_values{
        Value::from_scaled(Integer(1) << 652, 0), Value{}};
    const std::array<std::uint64_t, 2> half_units{kMixGrid / 2, kMixGrid / 2};
    require(Value::mix(mix_at_limit_values, half_units).coefficient_bits() == 652,
            "704-bit weighted product admitted");
    const std::array<Value, 2> mix_over_limit_values{positive, Value{}};
    const std::array<std::uint64_t, 2> mix_over_limit_units{kMixGrid - 1, 1};
    bool mix_over_limit_rejected = false;
    try { (void)Value::mix(mix_over_limit_values, mix_over_limit_units); }
    catch (const std::overflow_error&) { mix_over_limit_rejected = true; }
    require(mix_over_limit_rejected, "705-bit weighted product rejected");
    Execution execution(128);
    const auto unit=execution.from_integer(1);
    require(execution.expanded(unit)==1 && execution.receipt().work==128,
            "shared metadata allowance realization");
    bool quota_rejected=false;
    try { (void)execution.from_integer(2); }
    catch (const std::runtime_error&) { quota_rejected=true; }
    require(quota_rejected && execution.receipt().from_values==1,
            "metadata rejection does not increment event counter");
    bool poisoned=false;
    try { (void)execution.expanded(unit); }
    catch (const std::runtime_error&) { poisoned=true; }
    require(poisoned && execution.receipt().expansions==1,
            "failed metadata owner stays poisoned");
    Execution invalid_operation(1024);
    bool arithmetic_rejected=false;
    try { (void)invalid_operation.scaled(positive,2,0,false); }
    catch (const std::overflow_error&) { arithmetic_rejected=true; }
    require(arithmetic_rejected && invalid_operation.receipt().scales==0,
            "failed arithmetic preserves event counter");
    poisoned=false;
    try { (void)invalid_operation.from_integer(1); }
    catch (const std::runtime_error&) { poisoned=true; }
    require(poisoned,"arithmetic failure poisons shared owner");
    std::cout << "controls=pass\n";
}
