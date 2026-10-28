#pragma once

#include <bit>
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>

#include <boost/multiprecision/cpp_int.hpp>

namespace openpoker::exact_binary64 {

using Integer = boost::multiprecision::cpp_int;

static_assert(sizeof(double) == sizeof(std::uint64_t));
static_assert(std::numeric_limits<double>::is_iec559);
static_assert(std::numeric_limits<double>::radix == 2);
static_assert(std::numeric_limits<double>::digits == 53);
static_assert(std::numeric_limits<double>::min_exponent == -1021);
static_assert(std::numeric_limits<double>::max_exponent == 1024);
static_assert(std::numeric_limits<std::uint64_t>::digits == 64);

inline constexpr std::size_t kMaximumInputBits = 65536;
inline constexpr std::size_t kMaximumScratchBits = kMaximumInputBits + 53;

enum class ErrorCode {
    invalid_limits,
    nonpositive_denominator,
    input_bit_limit,
    scratch_bit_limit,
    rounded_below_normal,
    rounded_overflow,
};

class ConversionError final : public std::runtime_error {
public:
    ConversionError(ErrorCode code, const char* message)
        : std::runtime_error(message), code_(code) {}

    [[nodiscard]] ErrorCode code() const noexcept { return code_; }

private:
    ErrorCode code_;
};

struct Limits {
    // Callers may narrow these source limits, but cannot raise the project caps.
    std::size_t max_input_bits = kMaximumInputBits;
    std::size_t max_scratch_bits = kMaximumScratchBits;
};

struct Receipt {
    // Integer-value widths only. These are not cpp_int allocation/limb or CPU bounds.
    std::size_t peak_input_bits = 0;
    std::size_t peak_scratch_bits = 0;
    // Logical model: operand-width products for quotient/remainder plus widths
    // visited/shifted. It is not a runtime estimate or a library-work bound.
    std::uint64_t modeled_work = 0;
};

struct Result {
    std::uint64_t bits = 0;
    double value = 0.0;
    Receipt receipt{};
};

namespace detail {

inline void validate_limits(const Limits& limits) {
    if (limits.max_input_bits == 0 ||
        limits.max_input_bits > kMaximumInputBits ||
        limits.max_scratch_bits == 0 ||
        limits.max_scratch_bits > kMaximumScratchBits) {
        throw ConversionError(ErrorCode::invalid_limits, "invalid conversion limits");
    }
}

// cpp_int stores signed_magnitude limbs. Inspecting these read-only fields avoids
// constructing a second, potentially oversized absolute-value integer just to
// learn whether the caller's source operand exceeds the admission cap.
inline std::size_t magnitude_bits(const Integer& value, std::size_t cap,
                                  ErrorCode cap_code) {
    const auto& backend = value.backend();
    const std::size_t used = backend.size();
    using LimbReference = decltype(backend.limbs()[0]);
    using Limb = std::remove_cv_t<std::remove_reference_t<LimbReference>>;
    constexpr std::size_t limb_bits = std::numeric_limits<Limb>::digits;

    if (used == 0) return 0;
    if (used - 1 > cap / limb_bits) {
        throw ConversionError(cap_code, "integer bit limit exceeded");
    }
    const Limb top = backend.limbs()[used - 1];
    if (top == 0) return 0;
    std::size_t top_bits = 0;
    for (Limb value_bits = top; value_bits != 0; value_bits >>= 1) ++top_bits;
    const std::size_t lower = (used - 1) * limb_bits;
    if (top_bits > std::numeric_limits<std::size_t>::max() - lower) {
        throw ConversionError(cap_code, "integer bit limit exceeded");
    }
    const std::size_t result = lower + top_bits;
    if (result > cap) {
        throw ConversionError(cap_code, "integer bit limit exceeded");
    }
    return result;
}

inline std::size_t shifted_width(std::size_t width, std::size_t shift) {
    if (width == 0) return 0;
    if (shift > std::numeric_limits<std::size_t>::max() - width) {
        throw ConversionError(ErrorCode::scratch_bit_limit, "shift width overflow");
    }
    return width + shift;
}

inline void preflight_scratch(std::size_t width, const Limits& limits) {
    if (width > limits.max_scratch_bits) {
        throw ConversionError(ErrorCode::scratch_bit_limit, "conversion scratch bit limit exceeded");
    }
}

inline std::uint64_t saturating_multiply(std::uint64_t lhs, std::uint64_t rhs) {
    if (lhs != 0 && rhs > std::numeric_limits<std::uint64_t>::max() / lhs) {
        return std::numeric_limits<std::uint64_t>::max();
    }
    return lhs * rhs;
}

inline std::uint64_t saturating_add(std::uint64_t lhs, std::uint64_t rhs) {
    if (rhs > std::numeric_limits<std::uint64_t>::max() - lhs) {
        return std::numeric_limits<std::uint64_t>::max();
    }
    return lhs + rhs;
}

inline std::uint64_t division_work(std::size_t numerator_bits,
                                   std::size_t denominator_bits) {
    // Model each quotient/remainder request as the product of operand widths.
    // This is a conservative logical-unit receipt, not an algorithm/CPU claim.
    const auto n = static_cast<std::uint64_t>(numerator_bits);
    const auto d = static_cast<std::uint64_t>(denominator_bits);
    return saturating_multiply(saturating_multiply(n, d), 2);
}

inline std::uint64_t work_add_width(std::uint64_t work, std::size_t width) {
    return saturating_add(work, static_cast<std::uint64_t>(width));
}

inline void note_scratch(Receipt& receipt, const Integer& value,
                         const Limits& limits) {
    const auto width = magnitude_bits(value, limits.max_scratch_bits,
                                      ErrorCode::scratch_bit_limit);
    if (width > receipt.peak_scratch_bits) receipt.peak_scratch_bits = width;
}

inline Integer shift_left_admitted(const Integer& value, std::size_t value_bits,
                                   std::size_t shift, const Limits& limits,
                                   Receipt& receipt) {
    const auto forecast = shifted_width(value_bits, shift);
    preflight_scratch(forecast, limits);
    Integer result = value << shift;
    note_scratch(receipt, result, limits);
    receipt.modeled_work = work_add_width(receipt.modeled_work, forecast);
    return result;
}

inline int compare_scaled(const Integer& numerator, std::size_t numerator_bits,
                          const Integer& denominator, std::size_t denominator_bits,
                          int exponent, const Limits& limits, Receipt& receipt) {
    if (exponent >= 0) {
        Integer shifted = shift_left_admitted(
            denominator, denominator_bits, static_cast<std::size_t>(exponent),
            limits, receipt);
        receipt.modeled_work = work_add_width(
            receipt.modeled_work, std::max(numerator_bits, magnitude_bits(
                shifted, limits.max_scratch_bits, ErrorCode::scratch_bit_limit)));
        return numerator.compare(shifted);
    }
    Integer shifted = shift_left_admitted(
        numerator, numerator_bits, static_cast<std::size_t>(-exponent),
        limits, receipt);
    receipt.modeled_work = work_add_width(
        receipt.modeled_work, std::max(denominator_bits, magnitude_bits(
            shifted, limits.max_scratch_bits, ErrorCode::scratch_bit_limit)));
    return shifted.compare(denominator);
}

}  // namespace detail

// Convert an exact signed rational to its IEEE-754 binary64 encoding without
// intermediate floating arithmetic. Nonzero results must round to a finite,
// normal binary64 value. Exact zero always returns canonical positive zero.
inline Result convert(const Integer& signed_numerator,
                      const Integer& positive_denominator,
                      const Limits& limits = {}) {
    detail::validate_limits(limits);
    Receipt receipt{};
    if (positive_denominator <= 0) {
        throw ConversionError(ErrorCode::nonpositive_denominator,
                              "denominator must be positive");
    }

    const auto numerator_source_bits = detail::magnitude_bits(
        signed_numerator, limits.max_input_bits, ErrorCode::input_bit_limit);
    const auto denominator_bits = detail::magnitude_bits(
        positive_denominator, limits.max_input_bits, ErrorCode::input_bit_limit);
    receipt.peak_input_bits = std::max(numerator_source_bits, denominator_bits);
    receipt.modeled_work = detail::work_add_width(
        receipt.modeled_work, numerator_source_bits + denominator_bits + 1);

    if (numerator_source_bits == 0) {
        return Result{0, std::bit_cast<double>(std::uint64_t{0}), receipt};
    }

    const bool negative = signed_numerator.backend().sign();
    detail::preflight_scratch(numerator_source_bits, limits);
    Integer numerator = negative ? -signed_numerator : signed_numerator;
    detail::note_scratch(receipt, numerator, limits);
    const auto numerator_bits = numerator_source_bits;

    // The difference in operand bit lengths is an upper candidate for floor(log2(x)).
    // Values certainly outside this window cannot round to a normal finite number.
    const auto difference = static_cast<std::int64_t>(numerator_bits) -
                            static_cast<std::int64_t>(denominator_bits);
    if (difference > 1024) {
        throw ConversionError(ErrorCode::rounded_overflow,
                              "nonzero rational rounds outside finite binary64 range");
    }
    if (difference < -1023) {
        throw ConversionError(ErrorCode::rounded_below_normal,
                              "nonzero rational rounds below normal binary64 range");
    }

    int exponent = static_cast<int>(difference);
    if (detail::compare_scaled(numerator, numerator_bits,
                               positive_denominator, denominator_bits,
                               exponent, limits, receipt) < 0) {
        --exponent;
    }
    if (exponent > 1023) {
        throw ConversionError(ErrorCode::rounded_overflow,
                              "nonzero rational rounds outside finite binary64 range");
    }
    if (exponent < -1023) {
        throw ConversionError(ErrorCode::rounded_below_normal,
                              "nonzero rational rounds below normal binary64 range");
    }

    const bool subnormal_boundary = exponent == -1023;
    const int scale = subnormal_boundary ? 1074 : 52 - exponent;
    Integer scaled_numerator;
    Integer scaled_denominator;
    std::size_t scaled_numerator_bits = numerator_bits;
    std::size_t scaled_denominator_bits = denominator_bits;
    if (scale >= 0) {
        scaled_numerator = detail::shift_left_admitted(
            numerator, numerator_bits, static_cast<std::size_t>(scale),
            limits, receipt);
        scaled_numerator_bits = detail::shifted_width(
            numerator_bits, static_cast<std::size_t>(scale));
        detail::preflight_scratch(denominator_bits, limits);
        scaled_denominator = positive_denominator;
        detail::note_scratch(receipt, scaled_denominator, limits);
    } else {
        const auto denominator_shift = static_cast<std::size_t>(-scale);
        scaled_numerator = numerator;
        detail::note_scratch(receipt, scaled_numerator, limits);
        scaled_denominator = detail::shift_left_admitted(
            positive_denominator, denominator_bits, denominator_shift,
            limits, receipt);
        scaled_denominator_bits = detail::shifted_width(
            denominator_bits, denominator_shift);
    }

    // Both operations are separately charged. The source widths are admitted
    // before either arbitrary-precision operation is called.
    detail::preflight_scratch(scaled_numerator_bits, limits);
    detail::preflight_scratch(scaled_denominator_bits, limits);
    detail::preflight_scratch(53, limits);
    receipt.modeled_work = detail::saturating_add(
        receipt.modeled_work,
        detail::division_work(scaled_numerator_bits, scaled_denominator_bits));
    Integer quotient = scaled_numerator / scaled_denominator;
    Integer remainder = scaled_numerator % scaled_denominator;
    detail::note_scratch(receipt, quotient, limits);
    detail::note_scratch(receipt, remainder, limits);
    const auto quotient_bits = detail::magnitude_bits(
        quotient, limits.max_scratch_bits, ErrorCode::scratch_bit_limit);
    if (quotient_bits > 53) {
        throw ConversionError(ErrorCode::rounded_overflow,
                              "scaled quotient exceeds the binary64 significand bound");
    }

    // Compare r with d-r instead of constructing 2r, so midpoint detection
    // never needs a denominator-plus-one-bit temporary.
    Integer complement = scaled_denominator - remainder;
    detail::note_scratch(receipt, complement, limits);
    const int midpoint_cmp = remainder.compare(complement);
    receipt.modeled_work = detail::work_add_width(
        receipt.modeled_work, scaled_denominator_bits);
    bool round_up = midpoint_cmp > 0;
    if (midpoint_cmp == 0) {
        round_up = static_cast<bool>((quotient & 1) != 0);
    }
    if (round_up) {
        const auto quotient_value = quotient.convert_to<std::uint64_t>();
        const bool increment_grows = quotient_bits < 64 &&
            quotient_value == ((std::uint64_t{1} << quotient_bits) - 1);
        const auto increment_width = quotient_bits + (increment_grows ? 1U : 0U);
        detail::preflight_scratch(increment_width, limits);
        quotient += 1;
        detail::note_scratch(receipt, quotient, limits);
        receipt.modeled_work = detail::work_add_width(
            receipt.modeled_work, 53);
    }

    if (quotient < (std::uint64_t{1} << 51) ||
        quotient > (std::uint64_t{1} << 53)) {
        throw ConversionError(ErrorCode::rounded_overflow,
                              "rounded significand outside supported binary64 range");
    }
    const std::uint64_t significand = quotient.convert_to<std::uint64_t>();
    std::uint64_t encoded = 0;
    if (subnormal_boundary) {
        if (significand != (std::uint64_t{1} << 52)) {
            throw ConversionError(ErrorCode::rounded_below_normal,
                                  "nonzero rational rounds to zero or subnormal binary64");
        }
        encoded = std::uint64_t{1} << 52;  // minimum normal: exponent field 1, fraction 0
    } else {
        std::uint64_t normalized = significand;
        if (normalized == (std::uint64_t{1} << 53)) {
            normalized >>= 1;
            ++exponent;
        }
        if (exponent > 1023) {
            throw ConversionError(ErrorCode::rounded_overflow,
                                  "nonzero rational rounds outside finite binary64 range");
        }
        if (normalized < (std::uint64_t{1} << 52) ||
            normalized >= (std::uint64_t{1} << 53)) {
            throw ConversionError(ErrorCode::rounded_overflow,
                                  "internal normalized significand outside binary64 range");
        }
        const auto exponent_field = static_cast<std::uint64_t>(exponent + 1023);
        const auto fraction_field = normalized - (std::uint64_t{1} << 52);
        encoded = (exponent_field << 52) | fraction_field;
    }
    if (negative) encoded |= (std::uint64_t{1} << 63);
    return Result{encoded, std::bit_cast<double>(encoded), receipt};
}

inline const char* error_name(ErrorCode code) noexcept {
    switch (code) {
        case ErrorCode::invalid_limits: return "invalid_limits";
        case ErrorCode::nonpositive_denominator: return "nonpositive_denominator";
        case ErrorCode::input_bit_limit: return "input_bit_limit";
        case ErrorCode::scratch_bit_limit: return "scratch_bit_limit";
        case ErrorCode::rounded_below_normal: return "rounded_below_normal";
        case ErrorCode::rounded_overflow: return "rounded_overflow";
    }
    return "conversion_error";
}

}  // namespace openpoker::exact_binary64
