#pragma once

#include "exact_binary64.hpp"

#include <algorithm>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <stdexcept>
#include <type_traits>
#include <utility>

namespace openpoker::factored_dyadic {

using Integer = exact_binary64::Integer;

inline constexpr unsigned kMaximumExpandedBits = 704;
inline constexpr unsigned kMixGridBits = 52;
inline constexpr std::uint64_t kMixGrid = std::uint64_t{1} << kMixGridBits;
inline constexpr unsigned kMaximumMixIntermediateBits = 704;

namespace detail {
inline unsigned magnitude_bits(const Integer& value) {
    const auto& backend = value.backend();
    const std::size_t used = backend.size();
    if (used == 0) return 0;
    using LimbRef = decltype(backend.limbs()[0]);
    using Limb = std::remove_cv_t<std::remove_reference_t<LimbRef>>;
    constexpr unsigned limb_bits = std::numeric_limits<Limb>::digits;
    static_assert(limb_bits == 32 || limb_bits == 64,
                  "factored dyadic requires 32-bit or 64-bit cpp_int limbs");
    const auto& raw = backend.limbs();
    constexpr std::size_t max_limbs =
        (kMaximumMixIntermediateBits + limb_bits - 1) / limb_bits;
    if (used > max_limbs || used != backend.size())
        throw std::overflow_error("factored dyadic integer exceeds limb bound");
    const std::size_t lower = (used - 1) * limb_bits;
    if (lower >= kMaximumMixIntermediateBits)
        throw std::overflow_error("factored dyadic integer exceeds intermediate bound");
    const Limb top = raw[used - 1];
    const std::size_t bits = lower + std::bit_width(top);
    if (bits > kMaximumMixIntermediateBits)
        throw std::overflow_error("factored dyadic integer exceeds intermediate bound");
    return static_cast<unsigned>(bits);
}

inline unsigned checked_expanded_bits(unsigned bits, unsigned shift) {
    if (shift > kMaximumExpandedBits)
        throw std::overflow_error("factored dyadic shift exceeds bound");
    if (bits != 0 && (shift > kMaximumExpandedBits - bits))
        throw std::overflow_error("factored dyadic expansion exceeds bound");
    return bits == 0 ? 0 : bits + shift;
}

inline void preflight_sum(unsigned lhs_bits, unsigned rhs_bits, bool same_sign) {
    const unsigned maximum = lhs_bits > rhs_bits ? lhs_bits : rhs_bits;
    // For equal-sign operands, a max-width term can grow by one bit. Opposite
    // signs cannot grow, so cancellation at the exact bound remains supported.
    if (same_sign && maximum >= kMaximumMixIntermediateBits)
        throw std::overflow_error("factored dyadic sum exceeds intermediate bound");
}
}  // namespace detail

class Value {
public:
    Value() = default;

    static Value from_scaled(Integer coefficient, unsigned shift) {
        if (coefficient == 0) return {};
        const unsigned bits = detail::magnitude_bits(coefficient);
        detail::checked_expanded_bits(bits, shift);
        return Value(std::move(coefficient), shift, bits);
    }

    static Value from_integer(Integer value) { return from_scaled(std::move(value), 0); }

    [[nodiscard]] const Integer& coefficient() const noexcept { return coefficient_; }
    [[nodiscard]] unsigned shift() const noexcept { return shift_; }
    [[nodiscard]] unsigned coefficient_bits() const noexcept { return coefficient_bits_; }
    [[nodiscard]] unsigned expanded_bits() const noexcept {
        return is_zero() ? 0 : coefficient_bits_ + shift_;
    }
    [[nodiscard]] bool is_zero() const noexcept { return coefficient_ == 0; }

    [[nodiscard]] Value added(const Value& rhs) const {
        if (is_zero()) return rhs;
        if (rhs.is_zero()) return *this;
        if (shift_ == rhs.shift_) {
            detail::preflight_sum(coefficient_bits_, rhs.coefficient_bits_,
                                  coefficient_.backend().sign() == rhs.coefficient_.backend().sign());
            Integer result = coefficient_ + rhs.coefficient_;
            return result == 0 ? Value{} : from_scaled(std::move(result), shift_);
        }
        const bool left_has_lower_shift = shift_ < rhs.shift_;
        const unsigned common = left_has_lower_shift ? shift_ : rhs.shift_;
        const unsigned aligned_bits = left_has_lower_shift
            ? rhs.coefficient_bits_ + rhs.shift_ - common
            : coefficient_bits_ + shift_ - common;
        const unsigned other_bits = left_has_lower_shift ? coefficient_bits_ : rhs.coefficient_bits_;
        detail::preflight_sum(aligned_bits, other_bits,
                              coefficient_.backend().sign() == rhs.coefficient_.backend().sign());
        Integer result = left_has_lower_shift ? rhs.coefficient_ : coefficient_;
        result <<= (left_has_lower_shift ? rhs.shift_ - shift_ : shift_ - rhs.shift_);
        result += left_has_lower_shift ? coefficient_ : rhs.coefficient_;
        if (result == 0) return {};
        return from_scaled(std::move(result), common);
    }

    [[nodiscard]] Value subtracted(const Value& rhs) const {
        if (rhs.is_zero()) return *this;
        if (is_zero()) return from_scaled(-rhs.coefficient_, rhs.shift_);
        if (shift_ == rhs.shift_) {
            detail::preflight_sum(coefficient_bits_, rhs.coefficient_bits_,
                                  coefficient_.backend().sign() != rhs.coefficient_.backend().sign());
            Integer result = coefficient_ - rhs.coefficient_;
            return result == 0 ? Value{} : from_scaled(std::move(result), shift_);
        }
        const bool right_has_lower_shift = rhs.shift_ < shift_;
        const unsigned common = right_has_lower_shift ? rhs.shift_ : shift_;
        const unsigned aligned_bits = right_has_lower_shift
            ? coefficient_bits_ + shift_ - common
            : rhs.coefficient_bits_ + rhs.shift_ - common;
        const unsigned other_bits = right_has_lower_shift ? rhs.coefficient_bits_ : coefficient_bits_;
        detail::preflight_sum(aligned_bits, other_bits,
                              coefficient_.backend().sign() != rhs.coefficient_.backend().sign());
        Integer result = right_has_lower_shift ? coefficient_ : rhs.coefficient_;
        result <<= (right_has_lower_shift ? shift_ - rhs.shift_ : rhs.shift_ - shift_);
        result -= right_has_lower_shift ? rhs.coefficient_ : coefficient_;
        if (!right_has_lower_shift) result = -result;
        if (result == 0) return {};
        return from_scaled(std::move(result), common);
    }

    [[nodiscard]] Value scaled(std::uint64_t factor, unsigned additional_shift,
                               bool negate = false) const {
        if (is_zero() || factor == 0) return {};
        if (additional_shift > kMaximumExpandedBits - shift_)
            throw std::overflow_error("factored dyadic shift exceeds bound");
        const unsigned factor_bits = std::bit_width(factor);
        const unsigned product_upper_bits = coefficient_bits_ + factor_bits -
            (std::has_single_bit(factor) ? 1U : 0U);
        if (product_upper_bits > kMaximumMixIntermediateBits)
            throw std::overflow_error("factored dyadic product exceeds intermediate bound");
        Integer result = coefficient_ * factor;
        if (negate) result = -result;
        return from_scaled(std::move(result), shift_ + additional_shift);
    }

    [[nodiscard]] Integer expanded() const {
        if (is_zero()) return 0;
        detail::checked_expanded_bits(coefficient_bits_, shift_);
        return coefficient_ << shift_;
    }

    [[nodiscard]] static Value mix(std::span<const Value> values,
                                   std::span<const std::uint64_t> units) {
        if (values.size() != units.size() || values.empty() || values.size() > 4)
            throw std::invalid_argument("mix requires one to four matching values and units");
        std::uint64_t total = 0;
        unsigned common = std::numeric_limits<unsigned>::max();
        unsigned common_unit_shift = kMixGridBits;
        for (std::size_t i = 0; i < values.size(); ++i) {
            if (units[i] > kMixGrid - total)
                throw std::invalid_argument("mix units exceed the exact grid");
            total += units[i];
            if (units[i] != 0)
                common_unit_shift = std::min(common_unit_shift,
                                             static_cast<unsigned>(std::countr_zero(units[i])));
            if (units[i] != 0 && !values[i].is_zero() && values[i].shift_ < common)
                common = values[i].shift_;
        }
        if (total != kMixGrid)
            throw std::invalid_argument("mix units must partition the exact grid");
        if (common == std::numeric_limits<unsigned>::max()) return {};
        for (std::size_t i = 0; i < values.size(); ++i) {
            if (units[i] == kMixGrid) return values[i];
        }

        Integer sum = 0;
        unsigned sum_bits = 0;
        const unsigned divisor_shift = kMixGridBits - common_unit_shift;
        for (std::size_t i = 0; i < values.size(); ++i) {
            if (units[i] == 0 || values[i].is_zero()) continue;
            const std::uint64_t reduced_unit = units[i] >> common_unit_shift;
            const unsigned unit_bits = std::bit_width(reduced_unit);
            const unsigned product_upper_bits = values[i].coefficient_bits_ + unit_bits -
                (std::has_single_bit(reduced_unit) ? 1U : 0U);
            const unsigned alignment = values[i].shift_ - common;
            if (product_upper_bits > kMaximumMixIntermediateBits ||
                alignment > kMaximumMixIntermediateBits - product_upper_bits)
                throw std::overflow_error("factored mix product exceeds intermediate bound");
            Integer term = values[i].coefficient_ * reduced_unit;
            const unsigned term_bits = detail::magnitude_bits(term);
            const unsigned aligned_bits = term_bits + alignment;
            if (sum_bits != 0) {
                const bool same_sign = sum.backend().sign() == term.backend().sign();
                detail::preflight_sum(sum_bits, aligned_bits, same_sign);
            }
            term <<= alignment;
            sum += term;
            sum_bits = detail::magnitude_bits(sum);
        }
        if (sum == 0) return {};
        if (common >= divisor_shift)
            return from_scaled(std::move(sum), common - divisor_shift);
        const unsigned remaining_divisor_shift = divisor_shift - common;
        const Integer mask = (Integer(1) << remaining_divisor_shift) - 1;
        if ((sum & mask) != 0)
            throw std::invalid_argument("mix result is not integral in the dyadic grid");
        return from_integer(sum >> remaining_divisor_shift);
    }

private:
    Value(Integer coefficient, unsigned shift, unsigned coefficient_bits)
        : coefficient_(std::move(coefficient)), shift_(shift), coefficient_bits_(coefficient_bits) {}
    Integer coefficient_ = 0;
    unsigned shift_ = 0;
    unsigned coefficient_bits_ = 0;
};

}  // namespace openpoker::factored_dyadic
