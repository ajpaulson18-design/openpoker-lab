#pragma once

#include "exact_binary64.hpp"
#include <array>
#include <bit>
#include <cstdint>
#include <stdexcept>
#include <utility>

namespace openpoker::dyadic_policy_division {
using Integer = exact_binary64::Integer;

struct Trace {
    unsigned corrections = 0;
    unsigned addbacks = 0;
    unsigned max_digit_corrections = 0;
    unsigned normalization = 0;
};
struct Result {
    std::uint64_t quotient;
    Integer remainder;
};

// Exact divmod(weight * 2^52, sum) using normalized base-2^32 division.
inline Result divide_grid(const Integer& weight, const Integer& sum, Trace* trace = nullptr) {
    constexpr unsigned limit = 704;
    constexpr unsigned grid = 52;
    constexpr std::uint64_t base = std::uint64_t{1} << 32;
    constexpr std::uint64_t mask = base - 1;
    if (sum <= 0 || weight < 0 || weight > sum ||
        boost::multiprecision::msb(sum) >= limit ||
        (weight != 0 && boost::multiprecision::msb(weight) >= limit))
        throw std::invalid_argument("dyadic division input outside bounds");
    if (trace) *trace = {};
    if (weight == 0) return {0, Integer(0)};
    if (weight == sum) return {std::uint64_t{1} << grid, Integer(0)};

    // At most 22 source digits, 24 shifted numerator digits, and a sentinel.
    std::array<std::uint32_t, 26> divisor{}, numerator_digits{};
    const Integer numerator = weight << grid;
    const std::size_t n = (boost::multiprecision::msb(sum) + 32) / 32;
    const std::size_t un = (boost::multiprecision::msb(numerator) + 32) / 32;
    boost::multiprecision::export_bits(sum, divisor.begin(), 32, false);
    boost::multiprecision::export_bits(numerator, numerator_digits.begin(), 32, false);
    if (un < n) return {0, numerator};
    if (un - n > 2)
        throw std::logic_error("dyadic division position overflow");

    const unsigned shift = std::countl_zero(divisor[n - 1]);
    if (trace) trace->normalization = shift;
    if (shift) {
        std::uint64_t carry = 0;
        for (std::size_t i = 0; i < n; ++i) {
            const auto value = (std::uint64_t(divisor[i]) << shift) | carry;
            divisor[i] = std::uint32_t(value);
            carry = value >> 32;
        }
        carry = 0;
        for (std::size_t i = 0; i < un; ++i) {
            const auto value = (std::uint64_t(numerator_digits[i]) << shift) | carry;
            numerator_digits[i] = std::uint32_t(value);
            carry = value >> 32;
        }
        // Keep un at its original size. This word is the loop's sentinel.
        numerator_digits[un] = std::uint32_t(carry);
    }

    std::uint64_t quotient = 0;
    // Three positions at most. The leading position may have a zero digit.
    for (std::size_t j = un - n + 1; j-- > 0;) {
        const std::uint64_t top =
            (std::uint64_t(numerator_digits[j + n]) << 32) | numerator_digits[j + n - 1];
        std::uint64_t qhat, rhat;
        if (numerator_digits[j + n] == divisor[n - 1]) {
            qhat = mask;
            rhat = std::uint64_t(numerator_digits[j + n - 1]) + divisor[n - 1];
        } else {
            qhat = top / divisor[n - 1];
            rhat = top % divisor[n - 1];
        }
        if (qhat > mask)
            throw std::logic_error("dyadic division estimate outside digit");

        unsigned corrections = 0;
        if (n > 1) {
            while (rhat < base &&
                   qhat * std::uint64_t(divisor[n - 2]) >
                       (rhat << 32) + numerator_digits[j + n - 2]) {
                if (++corrections > 2)
                    throw std::logic_error("dyadic division correction overflow");
                --qhat;
                rhat += divisor[n - 1];
                if (trace) {
                    ++trace->corrections;
                    if (trace->max_digit_corrections < corrections)
                        trace->max_digit_corrections = corrections;
                }
            }
        }

        std::uint64_t borrow = 0;
        for (std::size_t i = 0; i < n; ++i) {
            const std::uint64_t product = qhat * std::uint64_t(divisor[i]) + borrow;
            const auto low = std::uint32_t(product);
            const auto old = numerator_digits[j + i];
            numerator_digits[j + i] = old - low;
            borrow = (product >> 32) + (old < low);
        }
        const auto old = numerator_digits[j + n];
        numerator_digits[j + n] = std::uint32_t(std::uint64_t(old) - borrow);
        if (std::uint64_t(old) < borrow) {
            if (trace) ++trace->addbacks;
            --qhat;
            std::uint64_t carry = 0;
            for (std::size_t i = 0; i < n; ++i) {
                const auto value = std::uint64_t(numerator_digits[j + i]) + divisor[i] + carry;
                numerator_digits[j + i] = std::uint32_t(value);
                carry = value >> 32;
            }
            numerator_digits[j + n] = std::uint32_t(std::uint64_t(numerator_digits[j + n]) + carry);
        }
        if (numerator_digits[j + n] != 0)
            throw std::logic_error("dyadic division residual outside divisor width");
        if (j >= 2) {
            if (qhat) throw std::logic_error("dyadic division quotient overflow");
        } else {
            quotient |= qhat << (32 * j);
        }
    }

    Integer remainder = 0;
    boost::multiprecision::import_bits(remainder, numerator_digits.begin(),
                                      numerator_digits.begin() + n, 32, false);
    remainder >>= shift;
    if (quotient > (std::uint64_t{1} << grid) || remainder >= sum)
        throw std::logic_error("dyadic division result outside bounds");
    return {quotient, std::move(remainder)};
}
} // namespace openpoker::dyadic_policy_division

