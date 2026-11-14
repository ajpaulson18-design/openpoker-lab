#pragma once
// Finite-grid policy images, independent of poker row/history routing.
#include "exact_binary64.hpp"
#include "dyadic_policy_division.hpp"
#include <boost/multiprecision/integer.hpp>
#include <algorithm>
#include <array>
#include <bit>
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
enum class Profile { legacy, proof10, proof9_q32 };
enum class DivisionKernel { separate, combined, complement, equal_complement, pair_complement, bounded_complement };
inline constexpr std::uint64_t proof10_work_cap = 520000000;
inline constexpr std::uint64_t proof9_q32_work_cap = 1870000000;
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
struct PackedReceipt {
    std::uint64_t rows = 0, zero_rows = 0, pure_rows = 0, equal_rows = 0, mixed_rows = 0;
    std::uint64_t words_scanned = 0, imported_slots = 0, scan_work = 0;
};
struct Receipt {
    std::uint64_t work = 0, rows = 0;
    std::size_t max_input_bits = 0, peak_forecast_bits = 0;
    std::size_t retained_entries = 32, peak_scratch_entries = 0;
    std::size_t peak_integer_payload_bits = 0;
    std::uint64_t combined_divisions = 0;
    std::uint64_t equal_rows = 0, equal_divisions_avoided = 0;
    PackedReceipt packed{};
};
static_assert(sizeof(Receipt)<=32*sizeof(std::uint64_t));
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
        const bool proof9_q32=limits.profile==Profile::proof9_q32;
        if ((limits.profile!=Profile::legacy && !proof10 && !proof9_q32) ||
                (limits.division_kernel!=DivisionKernel::separate &&
                 limits.division_kernel!=DivisionKernel::combined &&
                 limits.division_kernel!=DivisionKernel::complement &&
                 limits.division_kernel!=DivisionKernel::equal_complement &&
                 limits.division_kernel!=DivisionKernel::pair_complement &&
                 limits.division_kernel!=DivisionKernel::bounded_complement) ||
                ((limits.division_kernel==DivisionKernel::combined && !proof10 && !proof9_q32) ||
                 ((limits.division_kernel==DivisionKernel::complement ||
                  limits.division_kernel==DivisionKernel::equal_complement ||
                  limits.division_kernel==DivisionKernel::pair_complement ||
                  limits.division_kernel==DivisionKernel::bounded_complement) && !proof10)) ||
                !limits.work || limits.work > (proof10?proof10_work_cap:proof9_q32?proof9_q32_work_cap:500000000) || !limits.integer_bits ||
                limits.integer_bits > ((proof10||proof9_q32)?proof10_integer_bits:65536) ||
                limits.entries < receipt_.retained_entries ||
                limits.entries > ((proof10||proof9_q32)?336u:2000000u) || !limits.integer_payload_bits ||
                limits.integer_payload_bits > (std::size_t{1} << 30))
            fail(ErrorCode::invalid_limits, "invalid reduce-only dyadic policy limits");
    }
    Quantizer(const Quantizer&) = delete;
    Quantizer& operator=(const Quantizer&) = delete;
    Quantizer(Quantizer&&) = delete;
    Quantizer& operator=(Quantizer&&) = delete;
    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }
    [[nodiscard]] bool failed() const noexcept { return failed_; }
    // Little-endian unsigned fixed-stride words. The caller supplies clipped
    // weights with a common positive scale; no wide integers are built for shortcuts.
    [[nodiscard]] Policy packed_policy(std::span<const std::uint64_t> input,
            std::size_t count, std::size_t value_bits, ImageKind kind, bool first_sweep=false,
            bool defer_width=false) {
        if (failed_) fail(ErrorCode::failed_owner, "dyadic policy owner already failed");
        try {
            if (limits_.profile!=Profile::proof10 || limits_.division_kernel!=DivisionKernel::bounded_complement ||
                count<2 || count>4 || !value_bits || value_bits>limits_.integer_bits || value_bits>704 ||
                (kind!=ImageKind::current_regret && kind!=ImageKind::exported_average) ||
                (first_sweep && kind!=ImageKind::current_regret))
                fail(ErrorCode::invalid_row, "invalid packed policy contract");
            const auto stride=(value_bits+63)/64;
            if (input.size()!=count*stride)
                fail(ErrorCode::invalid_row, "invalid packed policy size");
            const auto scan=add(16,mul(4*count,add(stride,1)));
            // Padding, support, both equality operands and one representative
            // width pass touch at most count+(3*count-1)*stride words. The
            // retained allowance covers that bound before any word access.
            charge(scan);
            std::array<bool,4> positive{};
            std::size_t positives=0, first=0, max_bits=0;
            bool equal=true;
            if (defer_width) {
                // Validate padding even when nonzero detection can stop early.
                // Mixed rows let allocate inspect widths once. Pure/equal rows
                // need the width of only their first positive representative.
                for (std::size_t i=0;i<count;++i) {
                    const auto row=input.subspan(i*stride,stride);
                    if (value_bits%64 && (row.back()>>(value_bits%64)))
                        fail(ErrorCode::invalid_row, "nonzero packed policy padding");
                    if (std::any_of(row.begin(),row.end(),[](auto word) {return word!=0;})) {
                        positive[i]=true;
                        if (!positives) first=i;
                        else if (!std::equal(row.begin(),row.end(),input.begin()+first*stride))
                            equal=false;
                        ++positives;
                    }
                }
                if (positives && (positives==1 || equal)) {
                    const auto row=input.subspan(first*stride,stride);
                    for (std::size_t j=stride;j-- > 0;) if (row[j]) {
                        max_bits=64*j+std::bit_width(row[j]);
                        break;
                    }
                }
            } else {
                for (std::size_t i=0;i<count;++i) {
                    std::size_t bits=0;
                    for (std::size_t j=0;j<stride;++j) {
                        const auto w=input[i*stride+j];
                        if (j==stride-1 && value_bits%64 && (w>>(value_bits%64)))
                            fail(ErrorCode::invalid_row, "nonzero packed policy padding");
                        if (w) bits=64*j+std::bit_width(w);
                    }
                    max_bits=std::max(max_bits,bits);
                    if (bits) {
                        positive[i]=true;
                        if (!positives) first=i;
                        else for (std::size_t j=0;j<stride;++j)
                            if (input[i*stride+j]!=input[first*stride+j]) equal=false;
                        ++positives;
                    }
                }
            }
            if (first_sweep && positives==count)
                fail(ErrorCode::invalid_row, "first-sweep clipped regret row must contain a zero");
            Policy result;
            if (positives>=2 && !equal) {
                std::array<Integer,4> values{};
                for (std::size_t i=0;i<count;++i) {
                    const auto first_word=input.begin()+i*stride;
                    boost::multiprecision::import_bits(values[i],first_word,first_word+stride,64,false);
                }
                result=allocate(std::span<const Integer>(values.data(),count),kind,first_sweep);
            } else {
                // Mirror allocate's logical reservations and extrema exactly.
                charge(64+16*count);
                receipt_.max_input_bits=std::max(receipt_.max_input_bits,max_bits);
                if (positives>=2)
                    charge(add(16,mul(4*count,add(words(max_bits),1))));
                admit(count,53,256+32*count);
                result.count_=count; result.kind_=kind; result.uniform_fallback_=positives==0;
                const auto divisor=positives ? positives : count;
                const auto base=grid_units/divisor, left=grid_units%divisor;
                std::size_t rank=0;
                for (std::size_t i=0;i<count;++i) if (!positives || positive[i]) {
                    result.units_[i]=base+(rank<left ? 1U : 0U); ++rank;
                }
                if (positives>=2) {
                    ++receipt_.equal_rows;
                    receipt_.equal_divisions_avoided=add(receipt_.equal_divisions_avoided,positives-1);
                }
                partition(result); ++receipt_.rows;
            }
            auto& packed=receipt_.packed;
            ++packed.rows;
            if (!positives) ++packed.zero_rows;
            else if (positives==1) ++packed.pure_rows;
            else if (equal) ++packed.equal_rows;
            else { ++packed.mixed_rows; packed.imported_slots=add(packed.imported_slots,count); }
            // Retained input extent, not a count of scalar memory loads.
            packed.words_scanned=add(packed.words_scanned,count*stride);
            packed.scan_work=add(packed.scan_work,scan);
            return result;
        } catch (...) { failed_=true; throw; }
    }
    [[nodiscard]] Policy regret_policy(std::span<const Integer> regrets) {
        return allocate(regrets,ImageKind::current_regret);
    }
    [[nodiscard]] Policy first_sweep_regret_policy(std::span<const Integer> regrets) {
        return allocate(regrets,ImageKind::current_regret,true);
    }
    [[nodiscard]] Policy average_export(std::span<const Integer> masses) {
        return allocate(masses,ImageKind::exported_average);
    }
private:
    // Each row's inputs share one positive scale/denominator and exact legal
    // action order. Caller owns immutable input and retained returned policies.
    // Scratch is per call; work is cumulative. No reset or owner fork API.
    [[nodiscard]] Policy allocate(std::span<const Integer> regrets, ImageKind kind, bool first_sweep=false) {
        if (failed_) fail(ErrorCode::failed_owner, "dyadic policy owner already failed");
        try {
            const auto count = regrets.size();
            if (!count || count > maximum_actions)
                fail(ErrorCode::invalid_row, "dyadic policy menu width");
            if ((limits_.division_kernel==DivisionKernel::complement ||
                 limits_.division_kernel==DivisionKernel::equal_complement ||
                 limits_.division_kernel==DivisionKernel::pair_complement ||
                 limits_.division_kernel==DivisionKernel::bounded_complement) && count>4)
                fail(ErrorCode::invalid_row, "complement kernel menu width");
            charge(64+16*count);
            std::size_t positives = 0, first_positive_index = 0, positive_index = 0, max_positive_bits = 0;
            for (std::size_t i=0; i<count; ++i) {
                const auto bits = width(regrets[i]);
                if (bits > limits_.integer_bits)
                    fail(ErrorCode::integer_width, "dyadic policy input integer width");
                if (kind==ImageKind::exported_average && regrets[i]<0)
                    fail(ErrorCode::invalid_row, "dyadic average mass must be nonnegative");
                receipt_.max_input_bits = std::max(receipt_.max_input_bits,bits);
                if (regrets[i] > 0) {
                    if (positives==0) first_positive_index=i;
                    ++positives; positive_index = i;
                    max_positive_bits = std::max(max_positive_bits,bits);
                }
            }
            if (first_sweep && positives==count)
                fail(ErrorCode::invalid_row, "first-sweep clipped regret row must contain a zero");
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
            // Equal-weight rows can be emitted without any wide arithmetic.
            // Charge the bounded equality scan before comparing input integers.
            if (limits_.division_kernel==DivisionKernel::equal_complement ||
                limits_.division_kernel==DivisionKernel::pair_complement ||
                limits_.division_kernel==DivisionKernel::bounded_complement) {
                charge(add(16,mul(4*count,add(words(max_positive_bits),1))));
                const Integer* first_positive=nullptr;
                bool equal_positive_weights=true;
                for (const auto& value : regrets) if (value>0) {
                    if (!first_positive) first_positive=&value;
                    else if (value!=*first_positive) equal_positive_weights=false;
                }
                if (equal_positive_weights) {
                    admit(count,53,256+32*count);
                    Policy policy; policy.count_=count; policy.kind_=kind;
                    const auto base=grid_units/static_cast<std::uint64_t>(positives);
                    const auto left=grid_units%static_cast<std::uint64_t>(positives);
                    std::uint64_t rank=0;
                    for (std::size_t i=0;i<count;++i) if (regrets[i]>0) {
                        policy.units_[i]=base+(rank<left ? 1U : 0U);
                        ++rank;
                    }
                    ++receipt_.equal_rows;
                    receipt_.equal_divisions_avoided=add(receipt_.equal_divisions_avoided,static_cast<std::uint64_t>(positives-1));
                    partition(policy); ++receipt_.rows; return policy;
                }
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
            const bool bounded_complement=limits_.division_kernel==DivisionKernel::bounded_complement;
            const bool pair_complement=(limits_.division_kernel==DivisionKernel::pair_complement || bounded_complement) && positives==2;
            const bool combined=limits_.division_kernel!=DivisionKernel::separate;
            const bool complement=limits_.division_kernel==DivisionKernel::complement ||
                limits_.division_kernel==DivisionKernel::equal_complement ||
                limits_.division_kernel==DivisionKernel::pair_complement || bounded_complement;
            // Keep the conservative combined reservation for the complement.
            // The receipt counts completed quotient/remainder operations.
            const auto division_factor=combined?1U:2U;
            const auto work = add(256,add(mul(16*count,add(words(bits),1)),
                add(mul(8*positives,add(mul(division_factor,division),add(mul(4,words(bits)),8))),
                    mul(4*count*count,add(words(sum_bits),1)))));
            admit(count,bits,work);
            Integer sum = 0;
            for (const auto& value : regrets) if (value > 0) sum += value >> common;
            Policy policy; policy.count_ = count; policy.kind_ = kind;
            if (pair_complement) {
                const auto first=first_positive_index;
                const auto second=positive_index;
                const Integer normalized=regrets[first] >> common;
                std::uint64_t quotient_value=0;
                Integer remainder=0;
                if (bounded_complement) {
                    const auto divided=dyadic_policy_division::divide_grid(normalized,sum);
                    quotient_value=divided.quotient;
                    remainder=divided.remainder;
                } else {
                    const Integer scaled=normalized << grid_bits;
                    Integer quotient=0;
                    boost::multiprecision::divide_qr(scaled,sum,quotient,remainder);
                    if (quotient<0 || quotient>grid_units)
                        fail(ErrorCode::arithmetic,"dyadic policy quotient outside unit grid");
                    quotient_value=quotient.convert_to<std::uint64_t>();
                }
                ++receipt_.combined_divisions;
                policy.units_[first]=quotient_value;
                if (remainder==0) {
                    policy.units_[second]=grid_units-policy.units_[first];
                } else {
                    const Integer complementary_remainder=sum-remainder;
                    if (complementary_remainder<=0)
                        fail(ErrorCode::arithmetic,"dyadic policy complementary remainder");
                    policy.units_[second]=grid_units-policy.units_[first]-1;
                    // Exact ties go to the earlier positive action in legal order.
                    if (remainder>=complementary_remainder) ++policy.units_[first];
                    else ++policy.units_[second];
                }
                partition(policy); ++receipt_.rows; return policy;
            }
            std::array<Integer,maximum_actions> remainders{};
            std::array<std::size_t,maximum_actions> order{};
            std::uint64_t allocated = 0;
            Integer residue = 0;
            std::uint64_t carry = 0;
            for (std::size_t i=0; i<count; ++i) {
                order[i] = i;
                if (regrets[i]<=0 || (complement && i==positive_index)) continue;
                Integer quotient=0;
                if (combined) {
                    if (bounded_complement) {
                        const auto divided=dyadic_policy_division::divide_grid(regrets[i] >> common,sum);
                        quotient=divided.quotient;
                        remainders[i]=divided.remainder;
                    } else {
                        const Integer scaled = (regrets[i] >> common) << grid_bits;
                        boost::multiprecision::divide_qr(scaled,sum,quotient,remainders[i]);
                    }
                    ++receipt_.combined_divisions;
                    if (complement) {
                        // Both summands are below sum, so one subtraction suffices.
                        residue+=remainders[i];
                        if (residue>=sum) { residue-=sum; ++carry; }
                    }
                } else {
                    const Integer scaled = (regrets[i] >> common) << grid_bits;
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
            if (complement) {
                // The exact scaled quotients sum to grid_units. The previous
                // residues contribute carry plus residue/sum to that total.
                const auto credit=carry+static_cast<std::uint64_t>(residue!=0);
                if (credit>grid_units-allocated)
                    fail(ErrorCode::arithmetic, "dyadic policy complement underflow");
                policy.units_[positive_index]=grid_units-allocated-credit;
                if (residue!=0) remainders[positive_index]=sum-residue;
                allocated=grid_units-credit;
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
