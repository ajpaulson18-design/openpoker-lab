#pragma once
// Internal, exact common-denominator operations for a single admitted board.
// The caller must include the returned integers in its already-reserved staging payload.
#include "exact_binary64.hpp"
#include <algorithm>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <utility>

namespace openpoker::virtual_frozen_update {
using CommonInteger = exact_binary64::Integer;
class CommonDenominatorError final : public std::runtime_error {
public:
    explicit CommonDenominatorError(const char* s) : std::runtime_error(s) {}
};
struct CommonDenominatorLimits {
    std::uint64_t work = 500000000;
    std::size_t integer_bits = 65536;
    std::size_t temporary_payload_bits = std::size_t{1} << 30;
};
struct CommonDenominatorReceipt {
    std::uint64_t work = 0;
    std::size_t peak_bits = 0, peak_temporary_payload_bits = 0, operations = 0;
};
class CommonDenominator final {
    CommonDenominatorLimits limits_;
    CommonDenominatorReceipt receipt_{};
    CommonInteger base_, denominator_;
    std::size_t shift_ = 0;
    static std::size_t bits(const CommonInteger& value) {
        return exact_binary64::detail::magnitude_bits(value, 65536, exact_binary64::ErrorCode::input_bit_limit);
    }
    static std::size_t plus(std::size_t a, std::size_t b) {
        if (b > std::numeric_limits<std::size_t>::max() - a) throw CommonDenominatorError("integer width overflow");
        return a + b;
    }
    void reserve(std::size_t width, std::size_t temporaries, std::uint64_t per_bit) {
        width = std::max<std::size_t>(width, 1);
        if (width > limits_.integer_bits) throw CommonDenominatorError("common denominator integer width exceeded");
        if (temporaries && width > limits_.temporary_payload_bits / temporaries)
            throw CommonDenominatorError("common denominator temporary payload exceeded");
        const auto payload = width * temporaries;
        // This is an explicitly bounded logical bit-operation model, not a CPU or RSS bound.
        const auto w = static_cast<std::uint64_t>(width);
        const auto cost = per_bit * w + 1024ULL;
        if (cost > limits_.work - receipt_.work) throw CommonDenominatorError("common denominator work exceeded");
        receipt_.work += cost;
        ++receipt_.operations;
        receipt_.peak_bits = std::max(receipt_.peak_bits, width);
        receipt_.peak_temporary_payload_bits = std::max(receipt_.peak_temporary_payload_bits, payload);
    }
public:
    // Parent admits both these permanently retained integers and all returned values.
    CommonDenominator(const CommonInteger& normalizer, std::uint64_t divisor,
                      std::uint64_t proposal_numerator, std::size_t shift,
                      CommonDenominatorLimits limits = {}) : limits_(limits), shift_(shift) {
        if (!limits.work || limits.work > 500000000 || !limits.integer_bits || limits.integer_bits > 65536 ||
            !limits.temporary_payload_bits || limits.temporary_payload_bits > (std::size_t{1} << 30))
            throw CommonDenominatorError("invalid reduce-only common denominator limits");
        if (normalizer <= 0 || !divisor || !proposal_numerator)
            throw CommonDenominatorError("invalid common denominator factor");
        const auto factor_bits = plus(plus(bits(normalizer), std::bit_width(divisor)), std::bit_width(proposal_numerator));
        // Two at-most-64-bit factor multiplies, copies and width scans.
        reserve(plus(factor_bits, shift), 5, 512);
        base_ = normalizer * divisor;
        base_ *= proposal_numerator;
        denominator_ = base_ << shift_;
    }
    [[nodiscard]] const CommonInteger& denominator() const noexcept { return denominator_; }
    [[nodiscard]] const CommonInteger& base() const noexcept { return base_; }
    [[nodiscard]] std::size_t shift() const noexcept { return shift_; }
    [[nodiscard]] const CommonDenominatorReceipt& receipt() const noexcept { return receipt_; }
    // Candidate terminal denominators are unreduced. Verify exact membership before shifting.
    [[nodiscard]] CommonInteger scale_terminal(const CommonInteger& numerator,
                                               const CommonInteger& terminal_denominator) {
        if (terminal_denominator <= 0) throw CommonDenominatorError("nonpositive terminal denominator");
        const auto base_bits = bits(base_), den_bits = bits(terminal_denominator);
        if (den_bits < base_bits) throw CommonDenominatorError("terminal denominator below base");
        const auto k = den_bits - base_bits;
        if (k > shift_) throw CommonDenominatorError("terminal denominator shift exceeds admission");
        // One base shift, equality scan and signed numerator shift, with copies.
        reserve(std::max({plus(base_bits, k), den_bits, plus(bits(numerator), shift_ - k)}), 5, 64);
        if ((base_ << k) != terminal_denominator)
            throw CommonDenominatorError("terminal denominator differs from admitted base");
        return numerator << (shift_ - k);
    }
    [[nodiscard]] CommonInteger divide_power_two(const CommonInteger& value, std::size_t exponent) {
        // Sign normalization, two shifts and equality scan, plus copies.
        reserve(plus(bits(value), 1), 5, 64);
        if (!exponent || value == 0) return value;
        if (exponent >= bits(value)) throw CommonDenominatorError("policy shift would lose exactness");
        CommonInteger magnitude = value < 0 ? -value : value;
        CommonInteger quotient = magnitude >> exponent;
        if ((quotient << exponent) != magnitude)
            throw CommonDenominatorError("policy shift would lose exactness");
        return value < 0 ? -quotient : quotient;
    }
    [[nodiscard]] CommonInteger add(const CommonInteger& a, const CommonInteger& b) {
        // Operand width scans, one signed addition/subtraction and output copy.
        reserve(plus(std::max(bits(a), bits(b)), 1), 3, 32);
        return a + b;
    }
    [[nodiscard]] CommonInteger subtract(const CommonInteger& a, const CommonInteger& b) {
        // Operand width scans, one signed addition/subtraction and output copy.
        reserve(plus(std::max(bits(a), bits(b)), 1), 3, 32);
        return a - b;
    }
};
} // namespace openpoker::virtual_frozen_update
