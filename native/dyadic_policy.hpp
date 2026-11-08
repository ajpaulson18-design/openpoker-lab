#pragma once
// Finite-grid policy images, independent of poker row/history routing.
#include "exact_binary64.hpp"
#include <boost/multiprecision/integer.hpp>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <stdexcept>

namespace openpoker::dyadic_policy {
using Integer = exact_binary64::Integer;
inline constexpr unsigned grid_bits = 52;
inline constexpr std::uint64_t grid_units = std::uint64_t{1} << grid_bits;
inline constexpr std::size_t maximum_actions = 20;
enum class ImageKind { current_regret, exported_average };
enum class Profile { legacy, proof10 };
enum class DivisionKernel { separate, combined };
inline constexpr std::uint64_t proof10_work_cap = 520000000;
inline constexpr std::size_t proof10_integer_bits = 702;

enum class ErrorCode { invalid_limits, invalid_row, integer_width, work_limit,
                       storage_limit, payload_limit, failed_owner, arithmetic };
class Error final : public std::runtime_error {
    ErrorCode code_;
public:
    Error(ErrorCode code, const char* text) : std::runtime_error(text), code_(code) {}
    [[nodiscard]] ErrorCode code() const noexcept { return code_; }
};
struct Limits {
    std::uint64_t work = 500000000;
    std::size_t integer_bits = 65536;
    std::size_t entries = 2000000;
    std::size_t integer_payload_bits = std::size_t{1} << 30;
    Profile profile = Profile::legacy;
    DivisionKernel division_kernel = DivisionKernel::separate;
};
struct Receipt {
    std::uint64_t work = 0, rows = 0;
    std::size_t max_input_bits = 0, peak_forecast_bits = 0;
    std::size_t retained_entries = 32, peak_scratch_entries = 0;
    std::size_t peak_integer_payload_bits = 0;
    std::uint64_t combined_divisions = 0;
};
class Quantizer;
class Policy final {
    std::array<std::uint64_t, maximum_actions> units_{};
    std::size_t count_ = 0;
    ImageKind kind_ = ImageKind::current_regret;
    bool uniform_fallback_ = false;
    Policy() = default;
    friend class Quantizer;
public:
    Policy(const Policy&) = default;
    Policy(Policy&&) noexcept = default;
    Policy& operator=(const Policy&) = default;
    Policy& operator=(Policy&&) noexcept = default;
    [[nodiscard]] std::size_t size() const noexcept { return count_; }
    [[nodiscard]] ImageKind kind() const noexcept { return kind_; }
    [[nodiscard]] bool uniform_fallback() const noexcept { return uniform_fallback_; }
    [[nodiscard]] std::span<const std::uint64_t> units() const noexcept {
        return {units_.data(), count_};
    }
    [[nodiscard]] double binary64(std::size_t index) const {
        if (index >= count_) throw Error(ErrorCode::invalid_row, "dyadic policy action index");
        // Integer conversion is exact through 2^52; all positive probabilities
        // are normal binary64 values. No approximate row renormalization.
        return std::ldexp(static_cast<double>(units_[index]), -static_cast<int>(grid_bits));
    }
};

class Quantizer final {
    Limits limits_;
    Receipt receipt_{};
    bool failed_ = false;
    [[noreturn]] static void fail(ErrorCode code, const char* message) {
        throw Error(code, message);
    }
    static std::uint64_t add(std::uint64_t a, std::uint64_t b) {
        if (b > std::numeric_limits<std::uint64_t>::max() - a)
            fail(ErrorCode::arithmetic, "dyadic policy count overflow");
        return a+b;
    }
    static std::uint64_t mul(std::uint64_t a, std::uint64_t b) {
        if (a && b > std::numeric_limits<std::uint64_t>::max()/a)
            fail(ErrorCode::arithmetic, "dyadic policy count overflow");
        return a*b;
    }
    static std::size_t width(const Integer& value) {
        try {
            return exact_binary64::detail::magnitude_bits(value,65536,
                exact_binary64::ErrorCode::input_bit_limit);
        } catch (const exact_binary64::ConversionError&) {
            fail(ErrorCode::integer_width, "dyadic policy input integer width");
        }
    }
    static std::size_t ceil_log2(std::size_t n) {
        std::size_t result = 0;
        for (std::size_t value = n-1; value; value >>= 1) ++result;
        return result;
    }
    static std::uint64_t words(std::size_t bits) {
        return static_cast<std::uint64_t>((bits+63)/64);
    }
    void charge(std::uint64_t amount) {
        if (amount > limits_.work-receipt_.work)
            fail(ErrorCode::work_limit, "dyadic policy cumulative work exceeded");
        receipt_.work += amount;
    }
    void admit(std::size_t count, std::size_t bits, std::uint64_t work) {
        if (bits > limits_.integer_bits)
            fail(ErrorCode::integer_width, "dyadic policy arithmetic width admission");
        const auto entries = 12*count+64;
        if (entries > limits_.entries-receipt_.retained_entries)
            fail(ErrorCode::storage_limit, "dyadic policy scratch entry admission");
        const auto payload = (6*count+32)*std::max<std::size_t>(bits,64);
        if (payload > limits_.integer_payload_bits)
            fail(ErrorCode::payload_limit, "dyadic policy integer payload admission");
        charge(work);
        receipt_.peak_forecast_bits = std::max(receipt_.peak_forecast_bits,bits);
        receipt_.peak_scratch_entries = std::max(receipt_.peak_scratch_entries,entries);
        receipt_.peak_integer_payload_bits = std::max(receipt_.peak_integer_payload_bits,payload);
    }
    static void partition(const Policy& policy) {
        std::uint64_t total = 0;
        for (const auto unit : policy.units()) {
            if (unit > grid_units-total)
                fail(ErrorCode::arithmetic, "dyadic policy partition exceeded one");
            total += unit;
        }
        if (total != grid_units)
            fail(ErrorCode::arithmetic, "dyadic policy partition incomplete");
    }
public:
    explicit Quantizer(Limits limits = {}) : limits_(limits) {
        const bool proof10=limits.profile==Profile::proof10;
        if ((limits.profile!=Profile::legacy && !proof10) ||
                (limits.division_kernel!=DivisionKernel::separate &&
                 limits.division_kernel!=DivisionKernel::combined) ||
                (limits.division_kernel==DivisionKernel::combined && !proof10) ||
                !limits.work || limits.work > (proof10?proof10_work_cap:500000000) || !limits.integer_bits ||
                limits.integer_bits > (proof10?proof10_integer_bits:65536) ||
                limits.entries < receipt_.retained_entries ||
                limits.entries > (proof10?336u:2000000u) || !limits.integer_payload_bits ||
                limits.integer_payload_bits > (std::size_t{1} << 30))
            fail(ErrorCode::invalid_limits, "invalid reduce-only dyadic policy limits");
    }
    Quantizer(const Quantizer&) = delete;
    Quantizer& operator=(const Quantizer&) = delete;
    Quantizer(Quantizer&&) = delete;
    Quantizer& operator=(Quantizer&&) = delete;
    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }
    [[nodiscard]] bool failed() const noexcept { return failed_; }
    [[nodiscard]] Policy regret_policy(std::span<const Integer> regrets) {
        return allocate(regrets,ImageKind::current_regret);
    }
    [[nodiscard]] Policy average_export(std::span<const Integer> masses) {
        return allocate(masses,ImageKind::exported_average);
    }
private:
    // Each row's inputs share one positive scale/denominator and exact legal
    // action order. Caller owns immutable input and retained returned policies.
    // Scratch is per call; work is cumulative. No reset or owner fork API.
    [[nodiscard]] Policy allocate(std::span<const Integer> regrets, ImageKind kind) {
        if (failed_) fail(ErrorCode::failed_owner, "dyadic policy owner already failed");
        try {
            const auto count = regrets.size();
            if (!count || count > maximum_actions)
                fail(ErrorCode::invalid_row, "dyadic policy menu width");
            charge(64+16*count);
            std::size_t positives = 0, positive_index = 0, max_positive_bits = 0;
            for (std::size_t i=0; i<count; ++i) {
                const auto bits = width(regrets[i]);
                if (bits > limits_.integer_bits)
                    fail(ErrorCode::integer_width, "dyadic policy input integer width");
                if (kind==ImageKind::exported_average && regrets[i]<0)
                    fail(ErrorCode::invalid_row, "dyadic average mass must be nonnegative");
                receipt_.max_input_bits = std::max(receipt_.max_input_bits,bits);
                if (regrets[i] > 0) {
                    ++positives; positive_index = i;
                    max_positive_bits = std::max(max_positive_bits,bits);
                }
            }
            if (positives < 2) {
                admit(count,53,256+32*count);
                Policy policy; policy.count_ = count; policy.kind_ = kind;
                policy.uniform_fallback_ = positives==0;
                if (positives == 1) policy.units_[positive_index] = grid_units;
                else {
                    const auto base = grid_units/static_cast<std::uint64_t>(count);
                    const auto left = grid_units%static_cast<std::uint64_t>(count);
                    for (std::size_t i=0; i<count; ++i)
                        policy.units_[i] = base + (i<left ? 1U : 0U);
                }
                partition(policy); ++receipt_.rows; return policy;
            }
            // Cancel only an exact common power of two; no weight is rounded.
            // Charge bounded limb scans before asking lsb to inspect them.
            std::size_t common = 65536;
            for (const auto& value : regrets) if (value > 0) {
                charge(mul(4,add(words(width(value)),1)));
                common = std::min(common,static_cast<std::size_t>(boost::multiprecision::lsb(value)));
            }
            const auto effective = max_positive_bits-common;
            const auto sum_bits = effective+ceil_log2(positives)+1;
            const auto scaled_bits = effective+grid_bits;
            const auto bits = std::max({sum_bits,scaled_bits,std::size_t{53}});
            const auto division = mul(words(scaled_bits),words(sum_bits));
            // The combined ledger counts one eval_qr invocation per positive
            // action. It does not bound backend CPU or its internal iterations.
            const auto division_factor=limits_.division_kernel==DivisionKernel::combined?1U:2U;
            const auto work = add(256,add(mul(16*count,add(words(bits),1)),
                add(mul(8*positives,add(mul(division_factor,division),add(mul(4,words(bits)),8))),
                    mul(4*count*count,add(words(sum_bits),1)))));
            admit(count,bits,work);
            Integer sum = 0;
            for (const auto& value : regrets) if (value > 0) sum += value >> common;
            std::array<Integer,maximum_actions> remainders{};
            std::array<std::size_t,maximum_actions> order{};
            Policy policy; policy.count_ = count; policy.kind_ = kind;
            std::uint64_t allocated = 0;
            for (std::size_t i=0; i<count; ++i) {
                order[i] = i;
                if (regrets[i] <= 0) continue;
                const Integer scaled = (regrets[i] >> common) << grid_bits;
                Integer quotient=0;
                if (limits_.division_kernel==DivisionKernel::combined) {
                    boost::multiprecision::divide_qr(scaled,sum,quotient,remainders[i]);
                    ++receipt_.combined_divisions;
                } else {
                    quotient=scaled/sum;
                    remainders[i]=scaled%sum;
                }
                if (quotient < 0 || quotient > grid_units)
                    fail(ErrorCode::arithmetic, "dyadic policy quotient outside unit grid");
                policy.units_[i] = quotient.convert_to<std::uint64_t>();
                if (policy.units_[i] > grid_units-allocated)
                    fail(ErrorCode::arithmetic, "dyadic policy allocation overflow");
                allocated += policy.units_[i];
            }
            // Stable insertion order gives equal remainders to earlier legal
            // actions. At most count*(count-1)/2 bounded comparisons/swaps.
            for (std::size_t i=1; i<count; ++i) {
                std::size_t j = i;
                while (j && remainders[order[j]] > remainders[order[j-1]]) {
                    std::swap(order[j],order[j-1]); --j;
                }
            }
            const auto left = grid_units-allocated;
            if (left >= positives)
                fail(ErrorCode::arithmetic, "dyadic policy remainder count");
            for (std::uint64_t i=0; i<left; ++i) {
                const auto selected = order[static_cast<std::size_t>(i)];
                if (regrets[selected] <= 0 || remainders[selected] <= 0)
                    fail(ErrorCode::arithmetic, "dyadic policy remainder assigned to zero weight");
                ++policy.units_[selected];
            }
            partition(policy); ++receipt_.rows; return policy;
        } catch (...) {
            failed_ = true;
            throw;
        }
    }
};
} // namespace openpoker::dyadic_policy
