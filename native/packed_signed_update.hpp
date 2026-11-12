#pragma once

#include "exact_binary64.hpp"
#include <array>
#include <bit>
#include <cstdint>
#include <limits>
#include <span>
#include <stdexcept>
#include <type_traits>

namespace openpoker::packed_signed_update {
// Word counts cover the target storage extent, not all arithmetic operations.
struct Counts { std::uint64_t additions=0, subtractions=0, clipped=0, words_read=0, words_written=0; };

// Counts describe successful calls only; target and counts remain unchanged on failure.
inline void apply(std::span<std::uint64_t> target, const exact_binary64::Integer& coefficient,
                  std::size_t left_shift, bool clip_zero, std::size_t retained_bits, Counts& counts) {
    using Limb = std::remove_cvref_t<decltype(coefficient.backend().limbs()[0])>;
    constexpr auto limb_bits=std::numeric_limits<Limb>::digits;
    if constexpr ((limb_bits != 64 && limb_bits != 32) || sizeof(Limb)*8 != limb_bits ||
                  std::endian::native != std::endian::little)
        throw std::invalid_argument("unsupported packed limb platform");
    if (target.empty() || target.size()>11 || !retained_bits || retained_bits>704 ||
        retained_bits>64*target.size() || left_shift>704)
        throw std::invalid_argument("invalid packed update dimensions");
    const auto& raw=coefficient.backend();
    const auto limbs=raw.size();
    if (limbs>(704+limb_bits-1)/limb_bits)
        throw std::invalid_argument("coefficient too wide");
    const auto n=(limbs*limb_bits+63)/64;
    const auto used=(retained_bits+63)/64;
    const auto rem=retained_bits%64;
    if ((rem && (target[used-1] >> rem)) ) throw std::invalid_argument("noncanonical target");
    for (std::size_t i=used;i<target.size();++i)
        if (target[i]) throw std::invalid_argument("noncanonical target");
    const auto word_shift=left_shift/64, bits=left_shift%64;
    const auto source_word=[&](std::size_t i) -> std::uint64_t {
        if (i>=n) return 0;
        std::uint64_t limb;
        if constexpr (limb_bits==32) {
            limb=static_cast<std::uint64_t>(raw.limbs()[2*i]);
            if (2*i+1<limbs) limb|=static_cast<std::uint64_t>(raw.limbs()[2*i+1])<<32;
        } else limb=static_cast<std::uint64_t>(raw.limbs()[i]);
        return limb;
    };
    const auto shifted_word=[&](std::size_t i) -> std::uint64_t {
        if (i<word_shift) return 0;
        const auto index=i-word_shift;
        auto value=source_word(index)<<bits;
        if (bits && index) value|=source_word(index-1)>>(64-bits);
        return value;
    };
    const auto top=source_word(n-1);
    const bool zero=top==0;
    const auto magnitude_bits=zero?0:64*(n-1)+std::bit_width(top)+left_shift;
    std::array<std::uint64_t,11> result;
    for (std::size_t i=0;i<target.size();++i) result[i]=target[i];
    Counts delta{}; delta.words_read=target.size(); delta.words_written=target.size();
    if (!zero && raw.sign()) {
        bool greater=magnitude_bits>retained_bits, equal=!greater;
        for (std::size_t i=target.size();!greater && i-- > 0;) {
            const auto a=target[i], m=shifted_word(i);
            if (m!=a) { greater=m>a; equal=false; break; }
        }
        if (greater || equal) {
            if (greater && !clip_zero) throw std::overflow_error("negative packed result");
            for (std::size_t i=0;i<target.size();++i) result[i]=0;
            if (clip_zero) ++delta.clipped;
        } else {
            std::uint64_t borrow=0;
            for (std::size_t i=0;i<target.size();++i) {
                const auto x=result[i], y=shifted_word(i);
                const auto t=x-y, b1=static_cast<std::uint64_t>(x<y);
                result[i]=t-borrow; borrow=b1 | static_cast<std::uint64_t>(t<borrow);
            }
        }
        ++delta.subtractions;
    } else if (!zero) {
        if (magnitude_bits>retained_bits) throw std::overflow_error("packed update overflow");
        std::uint64_t carry=0;
        for (std::size_t i=0;i<target.size();++i) {
            const auto x=result[i], y=shifted_word(i);
            const auto t=x+y, c1=static_cast<std::uint64_t>(t<x);
            result[i]=t+carry; carry=c1 | static_cast<std::uint64_t>(result[i]<t);
        }
        if (carry || (rem && (result[used-1] >> rem))) throw std::overflow_error("packed update overflow");
        for (std::size_t i=used;i<target.size();++i) if (result[i]) throw std::overflow_error("packed update overflow");
        ++delta.additions;
    }
    const auto max=std::numeric_limits<std::uint64_t>::max();
    if (delta.additions>max-counts.additions || delta.subtractions>max-counts.subtractions ||
        delta.clipped>max-counts.clipped || delta.words_read>max-counts.words_read ||
        delta.words_written>max-counts.words_written)
        throw std::overflow_error("packed update counter overflow");
    for (std::size_t i=0;i<target.size();++i) target[i]=result[i];
    counts.additions+=delta.additions; counts.subtractions+=delta.subtractions; counts.clipped+=delta.clipped;
    counts.words_read+=delta.words_read; counts.words_written+=delta.words_written;
}
}
