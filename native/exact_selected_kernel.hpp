#pragma once

// Bounded exact-product selected-board arithmetic.  All counters below are
// logical admission units/value widths, not cpp_int allocator or CPU bounds.
#include "exact_binary64.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iterator>
#include <limits>
#include <list>
#include <map>
#include <set>
#include <span>
#include <type_traits>
#include <stdexcept>
#include <tuple>
#include <unordered_set>
#include <utility>
#include <vector>

namespace openpoker::exact_selected_kernel {

using Integer = exact_binary64::Integer;
inline constexpr std::size_t kMaximumHandsPerSide = 1326;
inline constexpr std::size_t kMaximumBoards = 64;
inline constexpr std::uint64_t kMaximumModeledWork = 500'000'000;
inline constexpr std::size_t kMaximumStorageEntries = 2'000'000;
inline constexpr std::size_t kMaximumIntegerBits = exact_binary64::kMaximumInputBits;
inline constexpr std::size_t kMaximumIntegerPayloadBits = 1U << 30;

enum class ErrorCode {
    invalid_limits, invalid_input, duplicate_hand, duplicate_board,
    no_compatible_deals, integer_bit_limit, modeled_work_limit,
    integer_payload_limit, storage_limit, invalid_query, invalid_dyadic, conversion_failure
};

class KernelError final : public std::runtime_error {
public:
    KernelError(ErrorCode code, const char* message)
        : std::runtime_error(message), code_(code) {}
    [[nodiscard]] ErrorCode code() const noexcept { return code_; }
private:
    ErrorCode code_;
};

struct Hand {
    std::uint8_t first = 0;
    std::uint8_t second = 0;
};

struct WeightedHand {
    Hand hand{};
    std::uint64_t binary64_weight_bits = 0;
};

// The first three ids are the canonical DECK-ordered flop; turn and river
// remain ordered.  Card ids are rank-major, c/d/h/s within each rank.
struct SelectedBoard {
    std::array<std::uint8_t, 5> cards{};
};

struct Limits {
    std::size_t max_hands_per_side = kMaximumHandsPerSide;
    std::size_t max_boards = kMaximumBoards;
    std::size_t max_integer_bits = kMaximumIntegerBits;
    std::uint64_t max_modeled_work = kMaximumModeledWork;
    std::size_t max_storage_entries = kMaximumStorageEntries;
    std::size_t max_integer_payload_bits = kMaximumIntegerPayloadBits;
};

struct Receipt {
    std::uint64_t modeled_work = 0;
    std::size_t retained_entries = 0;
    std::size_t peak_scratch_entries = 0;
    std::size_t peak_integer_bits = 0;
    std::size_t peak_conversion_scratch_bits = 0;
    std::size_t setup_integer_payload_bits = 0;
    std::size_t peak_integer_payload_bits = 0;
    std::size_t rank_calls = 0;
    std::size_t rank_cache_hits = 0;
    std::size_t rank_cache_misses = 0;
    std::size_t rank_cache_evictions = 0;
    std::size_t boards_processed = 0;
    std::size_t marginal_queries = 0;
    std::size_t terminal_queries = 0;
    std::size_t integer_additions = 0;
    std::size_t integer_multiplications = 0;
    std::size_t integer_shifts = 0;
    std::size_t conversion_calls = 0;
    std::uint64_t fold_class_setup_work = 0;
    std::size_t fold_class_setup_entries = 0;
    std::size_t fold_class_queries = 0;
    std::size_t fold_reference_queries = 0;
    std::size_t fold_class_buckets = 0;
    std::size_t fold_class_own_checks = 0;
    std::size_t fold_mask_entries = 0;
    std::size_t fold_membership_entries = 0;
    std::array<std::size_t, 2> fold_classes_per_side{};
    std::array<std::size_t, 2> fold_class_calls_by_player{};
    std::array<std::size_t, 2> fold_literal_calls_by_player{};
    std::array<std::size_t, 2> fold_buckets_by_player{};
};

enum class TerminalKind { fold, showdown };
enum class FoldTraversal { literal_boards, mask_classes_v1 };

inline std::uint64_t fold_class_setup_work(std::size_t hands, std::size_t boards) {
    return 2048ULL * hands + 8ULL * boards * hands + 65536ULL;
}
inline std::size_t fold_class_setup_entries(std::size_t hands) { return 10 * hands + 128; }
inline std::size_t fold_class_constructor_scratch(std::size_t hands) {
    return std::max<std::size_t>(12 * hands + 512, 4224);
}
inline std::uint64_t fold_class_query_work(std::size_t classes, std::size_t own,
                                         std::size_t opponent, std::size_t boards) {
    return classes * (64ULL * own + 256ULL) + 64ULL * opponent + 8ULL * boards + 128ULL;
}

namespace detail {

struct Dyadic {
    Integer significand = 0;
    int exponent = 0; // value = significand * 2^exponent
};

struct Binary64Parts {
    std::uint64_t significand = 0;
    int exponent = 0;
};

inline Binary64Parts decode_parts(std::uint64_t bits, bool allow_negative,
                                  bool allow_zero, const char* label) {
    const bool negative = (bits >> 63) != 0;
    const std::uint64_t exp = (bits >> 52) & 0x7ffU;
    const std::uint64_t fraction = bits & ((std::uint64_t{1} << 52) - 1);
    if (exp == 0x7ffU) throw KernelError(ErrorCode::invalid_dyadic, label);
    if (exp == 0 && fraction == 0) {
        if (!allow_zero) throw KernelError(ErrorCode::invalid_dyadic, label);
        return {};
    }
    if (negative && !allow_negative) throw KernelError(ErrorCode::invalid_dyadic, label);
    const auto sig = exp == 0 ? fraction : ((std::uint64_t{1} << 52) | fraction);
    const int power = exp == 0 ? -1074 : static_cast<int>(exp) - 1023 - 52;
    return {sig, power};
}

inline Dyadic decode_double(std::uint64_t bits, bool allow_negative,
                            bool allow_zero, const char* label) {
    const auto parts = decode_parts(bits, allow_negative, allow_zero, label);
    Integer value = parts.significand;
    if ((bits >> 63) != 0 && value != 0) value = -value;
    return {std::move(value), parts.exponent};
}

inline std::size_t magnitude_bits(const Integer& value) {
    const auto& backend = value.backend();
    const std::size_t used = backend.size();
    using LimbReference = decltype(backend.limbs()[0]);
    using Limb = std::remove_cv_t<std::remove_reference_t<LimbReference>>;
    constexpr std::size_t limb_bits = std::numeric_limits<Limb>::digits;
    if (used == 0) return 0;
    const Limb top = backend.limbs()[used - 1];
    std::size_t top_bits = 0;
    for (Limb x = top; x != 0; x >>= 1) ++top_bits;
    return (used - 1) * limb_bits + top_bits;
}

inline std::uint64_t checked_add_count(std::uint64_t a, std::uint64_t b) {
    if (b > std::numeric_limits<std::uint64_t>::max() - a)
        throw KernelError(ErrorCode::modeled_work_limit, "work count overflow");
    return a + b;
}

inline std::uint64_t checked_mul_count(std::uint64_t a, std::uint64_t b) {
    if (a && b > std::numeric_limits<std::uint64_t>::max() / a)
        throw KernelError(ErrorCode::modeled_work_limit, "work count overflow");
    return a * b;
}

inline std::uint64_t saturating_add_count(std::uint64_t a, std::uint64_t b) {
    return b > std::numeric_limits<std::uint64_t>::max() - a
        ? std::numeric_limits<std::uint64_t>::max() : a + b;
}

struct Rank {
    std::array<std::uint8_t, 6> value{};
    friend bool operator==(const Rank&, const Rank&) = default;
    friend bool operator<(const Rank& a, const Rank& b) { return a.value < b.value; }
};

inline int straight_high(std::uint16_t mask) {
    for (int high = 14; high >= 6; --high) {
        const auto required = static_cast<std::uint16_t>(0x1fU << (high - 4));
        if ((mask & required) == required) return high;
    }
    constexpr std::uint16_t wheel = static_cast<std::uint16_t>(
        (1U << 14) | (1U << 5) | (1U << 4) | (1U << 3) | (1U << 2));
    return (mask & wheel) == wheel ? 5 : 0;
}

inline Rank rank_seven(const std::array<std::uint8_t, 7>& cards) {
    std::array<std::uint8_t, 15> counts{};
    std::array<std::uint8_t, 4> suit_counts{};
    std::array<std::uint16_t, 4> suit_masks{};
    std::uint16_t ranks = 0;
    for (auto card : cards) {
        const unsigned rank = 2U + card / 4U;
        const unsigned suit = card % 4U;
        ++counts[rank];
        ++suit_counts[suit];
        suit_masks[suit] = static_cast<std::uint16_t>(suit_masks[suit] | (1U << rank));
        ranks = static_cast<std::uint16_t>(ranks | (1U << rank));
    }
    for (unsigned s = 0; s < 4; ++s) if (suit_counts[s] >= 5) {
        const int high = straight_high(suit_masks[s]);
        if (high) return Rank{{8, static_cast<std::uint8_t>(high), 0, 0, 0, 0}};
    }
    for (int r = 14; r >= 2; --r) if (counts[static_cast<unsigned>(r)] == 4) {
        for (int k = 14; k >= 2; --k) if (k != r && counts[static_cast<unsigned>(k)])
            return Rank{{7, static_cast<std::uint8_t>(r), static_cast<std::uint8_t>(k), 0, 0, 0}};
    }
    int trip = 0;
    for (int r = 14; r >= 2; --r) if (counts[static_cast<unsigned>(r)] >= 3) { trip = r; break; }
    if (trip) for (int r = 14; r >= 2; --r)
        if (r != trip && counts[static_cast<unsigned>(r)] >= 2)
            return Rank{{6, static_cast<std::uint8_t>(trip), static_cast<std::uint8_t>(r), 0, 0, 0}};
    for (unsigned s = 0; s < 4; ++s) if (suit_counts[s] >= 5) {
        Rank out{}; out.value[0] = 5; unsigned n = 1;
        for (int r = 14; r >= 2 && n < 6; --r)
            if (suit_masks[s] & (1U << r)) out.value[n++] = static_cast<std::uint8_t>(r);
        return out;
    }
    if (const int high = straight_high(ranks); high)
        return Rank{{4, static_cast<std::uint8_t>(high), 0, 0, 0, 0}};
    if (trip) {
        Rank out{}; out.value[0] = 3; out.value[1] = static_cast<std::uint8_t>(trip); unsigned n = 2;
        for (int r = 14; r >= 2 && n < 4; --r)
            if (r != trip && counts[static_cast<unsigned>(r)]) out.value[n++] = static_cast<std::uint8_t>(r);
        return out;
    }
    int first_pair = 0, second_pair = 0;
    for (int r = 14; r >= 2; --r) if (counts[static_cast<unsigned>(r)] == 2) {
        if (!first_pair) first_pair = r; else { second_pair = r; break; }
    }
    if (second_pair) {
        Rank out{{2, static_cast<std::uint8_t>(first_pair), static_cast<std::uint8_t>(second_pair), 0, 0, 0}};
        for (int r = 14; r >= 2; --r) if (r != first_pair && r != second_pair && counts[static_cast<unsigned>(r)]) {
            out.value[3] = static_cast<std::uint8_t>(r); break;
        }
        return out;
    }
    if (first_pair) {
        Rank out{}; out.value[0] = 1; out.value[1] = static_cast<std::uint8_t>(first_pair); unsigned n = 2;
        for (int r = 14; r >= 2 && n < 5; --r)
            if (r != first_pair && counts[static_cast<unsigned>(r)]) out.value[n++] = static_cast<std::uint8_t>(r);
        return out;
    }
    Rank out{}; unsigned n = 1;
    for (int r = 14; r >= 2 && n < 6; --r)
        if (counts[static_cast<unsigned>(r)]) out.value[n++] = static_cast<std::uint8_t>(r);
    return out;
}

inline std::uint16_t hand_key(Hand hand) {
    const auto a = std::min(hand.first, hand.second);
    const auto b = std::max(hand.first, hand.second);
    return static_cast<std::uint16_t>((static_cast<unsigned>(a) << 6) | b);
}

} // namespace detail

class ExactSelectedKernel final {
public:
    using MarginalVectors = std::array<std::vector<double>, 2>;

    ExactSelectedKernel(std::vector<WeightedHand> sb,
                        std::vector<WeightedHand> bb,
                        std::vector<SelectedBoard> boards,
                        std::size_t rank_cache_boards = 1,
                        Limits limits = {}, FoldTraversal fold_traversal = FoldTraversal::literal_boards)
        : limits_(limits), rank_cache_boards_(rank_cache_boards),
          source_hands_{std::move(sb), std::move(bb)}, boards_(std::move(boards)), fold_traversal_(fold_traversal) {
        if (fold_traversal_ != FoldTraversal::literal_boards && fold_traversal_ != FoldTraversal::mask_classes_v1)
            fail(ErrorCode::invalid_input, "unsupported fold traversal profile");
        validate_limits();
        if (source_hands_[0].empty() || source_hands_[1].empty() ||
            source_hands_[0].size() > limits_.max_hands_per_side ||
            source_hands_[1].size() > limits_.max_hands_per_side ||
            boards_.empty() || boards_.size() > limits_.max_boards ||
            rank_cache_boards_ == 0 || rank_cache_boards_ > kMaximumBoards)
            fail(ErrorCode::invalid_input, "input dimensions exceed admitted bounds");
        const auto h0 = source_hands_[0].size(), h1 = source_hands_[1].size();
        const bool fold_classes = fold_traversal_ == FoldTraversal::mask_classes_v1;
        receipt_.fold_class_setup_entries = fold_classes ? fold_class_setup_entries(h0 + h1) : 0;
        receipt_.fold_class_setup_work = fold_classes ? fold_class_setup_work(h0 + h1, boards_.size()) : 0;
        const auto retained_setup = 20 * (h0 + h1) + 8 * boards_.size() + 256 +
            (rank_cache_boards_ + 1) * (h0 + h1) + receipt_.fold_class_setup_entries;
        preflight_storage(retained_setup, fold_classes ? fold_class_constructor_scratch(h0 + h1) : 12 * (h0 + h1) + 512,
                          "constructor setup");
        reserve_work(32 * (h0 + h1) + 16 * boards_.size() + 512 + receipt_.fold_class_setup_work);
        validate_inputs();
        prepare_weights();
        if (fold_classes) prepare_fold_classes();
        reserve_work(detail::checked_mul_count(boards_.size(),
            detail::checked_add_count(detail::checked_mul_count(40, h0 + h1), 512)));
        compute_normalizer();
    }

    ExactSelectedKernel(const ExactSelectedKernel&) = delete;
    ExactSelectedKernel& operator=(const ExactSelectedKernel&) = delete;

    [[nodiscard]] MarginalVectors marginals(std::span<const std::size_t> indexes) {
        validate_indexes(indexes);
        const auto bits = std::max(detail::magnitude_bits(normalizer_),
            max_weight_bits_[0] + max_weight_bits_[1] +
            ceil_log2(hands_[0].size()) + ceil_log2(hands_[1].size()) +
            ceil_log2(std::max<std::size_t>(1, indexes.size())) + 6);
        preflight_query(indexes.size(), 40 * total_hands() + 512,
                        12 * total_hands() + 600, "marginal query", bits,
                        4 * total_hands() + 32);
        ++receipt_.marginal_queries;
        MarginalVectors out{std::vector<double>(hands_[0].size(), 0.0),
                            std::vector<double>(hands_[1].size(), 0.0)};
        std::array<std::vector<Integer>, 2> sums{
            std::vector<Integer>(hands_[0].size()), std::vector<Integer>(hands_[1].size())};
        for (auto k : indexes) {
            ++receipt_.boards_processed;
            const auto rows0 = visible(0, k), rows1 = visible(1, k);
            const auto bucket0 = make_bucket(0, rows0, nullptr);
            const auto bucket1 = make_bucket(1, rows1, nullptr);
            for (auto i : rows0) {
                const Integer compatible = compatible_mass(hands_[0][i], bucket1);
                sums[0][i] = add(sums[0][i], multiply(weights_[0][i], compatible));
            }
            for (auto i : rows1) {
                const Integer compatible = compatible_mass(hands_[1][i], bucket0);
                sums[1][i] = add(sums[1][i], multiply(weights_[1][i], compatible));
            }
        }
        for (std::size_t p = 0; p < 2; ++p) for (std::size_t i = 0; i < sums[p].size(); ++i)
            out[p][i] = convert(sums[p][i], normalizer_);
        return out;
    }

    [[nodiscard]] std::array<std::vector<bool>, 2>
    support(std::span<const std::size_t> indexes) {
        validate_indexes(indexes);
        preflight_query(indexes.size(), 36 * total_hands() + 512,
                        10 * total_hands() + 600, "support query",
                        ceil_log2(std::max(hands_[0].size(), hands_[1].size())) + 2,
                        2 * total_hands() + 32);
        std::array<std::vector<bool>, 2> out{
            std::vector<bool>(hands_[0].size(), false), std::vector<bool>(hands_[1].size(), false)};
        for (auto k : indexes) {
            const auto rows0 = visible(0, k), rows1 = visible(1, k);
            const auto bucket0 = make_unit_bucket(0, rows0);
            const auto bucket1 = make_unit_bucket(1, rows1);
            for (auto i : rows0) if (compatible_mass(hands_[0][i], bucket1) != 0) out[0][i] = true;
            for (auto i : rows1) if (compatible_mass(hands_[1][i], bucket0) != 0) out[1][i] = true;
        }
        return out;
    }

    [[nodiscard]] std::vector<double> terminal(
        std::size_t player, std::span<const std::size_t> indexes,
        TerminalKind kind, double payoff, std::span<const double> opponent_reach) {
        if (player > 1 || (kind != TerminalKind::fold && kind != TerminalKind::showdown))
            fail(ErrorCode::invalid_query, "invalid terminal kind or player");
        validate_indexes(indexes);
        const std::size_t own = player, opp = 1 - player;
        if (opponent_reach.size() != hands_[opp].size())
            fail(ErrorCode::invalid_query, "opponent reach dimension mismatch");
        const auto pay = detail::decode_double(std::bit_cast<std::uint64_t>(payoff),
                                               kind == TerminalKind::fold, true,
                                               "invalid terminal payoff bits");
        if (kind == TerminalKind::showdown && pay.significand < 0)
            fail(ErrorCode::invalid_dyadic, "showdown payoff must be nonnegative");
        const auto rank_sweep_work = total_hands() *
            (16 * ceil_log2(std::max<std::size_t>(2, total_hands())) + 8);
        // A showdown board charges 200 units per hand for ranking and bucket
        // maintenance, a separate comparison envelope for two H log H sorts
        // plus three ordered-map lookups per own row, and fixed setup. Fold
        // buckets charge 48 units per hand plus fixed setup. These are logical
        // work units, not CPU estimates.
        const std::uint64_t per_board_work = kind == TerminalKind::showdown
            ? 200 * total_hands() + 520 + rank_sweep_work
            : 48 * total_hands() + 512;
        preflight_query(indexes.size(), per_board_work,
                        140 * total_hands() + 1000 + (rank_cache_boards_ + 1) * total_hands(),
                        "terminal query", 0,
                        8 * hands_[opp].size() + 4 * hands_[own].size() + 64);
        std::vector<detail::Dyadic> reaches;
        int reach_min_power = 0;
        bool any_reach = false;
        std::size_t max_reach_significand_bits = 0;
        for (double value : opponent_reach) {
            auto decoded = detail::decode_double(std::bit_cast<std::uint64_t>(value), false, true,
                                                 "invalid opponent reach bits");
            if (value > 1.0)
                fail(ErrorCode::invalid_dyadic, "opponent reach must be in [0,1]");
            if (decoded.significand != 0 && (!any_reach || decoded.exponent < reach_min_power)) {
                reach_min_power = decoded.exponent; any_reach = true;
            }
            max_reach_significand_bits = std::max(max_reach_significand_bits,
                detail::magnitude_bits(decoded.significand));
        }
        if (!any_reach) reach_min_power = 0;
        const int factor_power = reach_min_power + pay.exponent;
        const std::size_t maxreachbits = any_reach ? max_reach_significand_bits +
            static_cast<std::size_t>(std::max(0, -reach_min_power)) : 0U;
        const std::size_t max_weight_bits = max_weight_bits_[opp];
        const std::size_t opp_sum_bits = max_weight_bits + maxreachbits + ceil_log2(hands_[opp].size()) + 4;
        const std::size_t signed_bits = opp_sum_bits + 4;
        const std::size_t numerator_forecast = max_weight_bits_[own] + signed_bits +
            detail::magnitude_bits(pay.significand) + ceil_log2(std::max<std::size_t>(1, indexes.size())) + 4;
        const std::size_t scaled_numerator_forecast = numerator_forecast +
            static_cast<std::size_t>(std::max(0, factor_power));
        const std::size_t denominator_forecast = detail::magnitude_bits(normalizer_) +
            static_cast<std::size_t>(std::max(0, -factor_power));
        const std::size_t query_bits = std::max(scaled_numerator_forecast, denominator_forecast);
        check_query_bits(query_bits, "terminal query");
        ++receipt_.terminal_queries;

        reaches.reserve(opponent_reach.size());
        for (double value : opponent_reach)
            reaches.push_back(detail::decode_double(std::bit_cast<std::uint64_t>(value), false, true,
                                                     "invalid opponent reach bits"));

        int common_denominator_power = factor_power;
        Integer output_denominator = normalizer_;
        if (common_denominator_power < 0) {
            output_denominator = shift_left(normalizer_, static_cast<std::size_t>(-common_denominator_power));
            common_denominator_power = 0;
        }
        std::vector<Integer> answer(hands_[own].size());
        std::vector<Integer> aligned_reach(reaches.size());
        for (std::size_t j = 0; j < reaches.size(); ++j) {
            if (reaches[j].significand == 0) continue;
            const auto shift = static_cast<std::size_t>(reaches[j].exponent - reach_min_power);
            aligned_reach[j] = shift_left(reaches[j].significand, shift);
        }
        const Integer payoff_sig = pay.significand;
        const auto class_work = fold_class_query_work(fold_classes_[opp].size(),
            hands_[own].size(), hands_[opp].size(), indexes.size());
        const bool use_fold_classes = kind == TerminalKind::fold &&
            fold_traversal_ == FoldTraversal::mask_classes_v1 &&
            class_work <= static_cast<std::uint64_t>(indexes.size()) * per_board_work;
        if (use_fold_classes) {
            ++receipt_.fold_class_queries;
            ++receipt_.fold_class_calls_by_player[player];
            std::uint64_t query_mask = 0;
            for (auto k : indexes) query_mask |= std::uint64_t{1} << k;
            std::vector<Integer> weighted(reaches.size());
            for (std::size_t j = 0; j < reaches.size(); ++j)
                if (aligned_reach[j] != 0) weighted[j] = multiply(weights_[opp][j], aligned_reach[j]);
            for (const auto& group : fold_classes_[opp]) {
                if ((group.board_mask & query_mask) == 0 || payoff_sig == 0) continue;
                bool any = false;
                const auto bucket = make_fold_bucket(opp, group, weighted, any);
                if (!any) continue;
                ++receipt_.fold_class_buckets;
                ++receipt_.fold_buckets_by_player[player];
                for (std::size_t i = 0; i < hands_[own].size(); ++i) {
                    ++receipt_.fold_class_own_checks;
                    const auto count = static_cast<unsigned>(std::popcount(
                        query_mask & fold_board_masks_[own][i] & group.board_mask));
                    if (!count) continue;
                    Integer value = multiply(weights_[own][i], fold_compatible_mass(own, i, group.board_mask, bucket, weighted));
                    value = multiply(value, Integer{count});
                    value = multiply(value, payoff_sig);
                    if (player == 1) value = -value;
                    answer[i] = add(answer[i], std::move(value));
                }
            }
        } else {
        if (kind == TerminalKind::fold) {
            ++receipt_.fold_reference_queries;
            ++receipt_.fold_literal_calls_by_player[player];
        }
        for (auto k : indexes) {
            ++receipt_.boards_processed;
            const auto opp_rows = visible(opp, k);
            const auto own_rows = visible(own, k);
            std::vector<Integer> weighted(reaches.size());
            std::vector<std::size_t> weighted_rows;
            weighted_rows.reserve(opp_rows.size());
            for (auto j : opp_rows) if (aligned_reach[j] != 0) {
                weighted[j] = multiply(weights_[opp][j], aligned_reach[j]);
                weighted_rows.push_back(j);
            }
            if (weighted_rows.empty() || payoff_sig == 0) continue;
            if (kind == TerminalKind::fold) {
                const auto bucket = make_bucket(opp, weighted_rows, &weighted);
                for (auto i : own_rows) {
                    Integer value = multiply(weights_[own][i], compatible_mass(hands_[own][i], bucket));
                    value = multiply(value, payoff_sig);
                    if (player == 1) value = -value;
                    answer[i] = add(answer[i], std::move(value));
                }
            } else {
                const auto& ranks = rank_vectors(k);
                struct Row { detail::Rank rank; std::size_t index; };
                std::vector<Row> sorted_opp, sorted_own;
                sorted_opp.reserve(weighted_rows.size()); sorted_own.reserve(own_rows.size());
                for (auto j : weighted_rows) sorted_opp.push_back({ranks.sides[opp][j], j});
                for (auto i : own_rows) sorted_own.push_back({ranks.sides[own][i], i});
                std::sort(sorted_opp.begin(), sorted_opp.end(), [](const Row& a, const Row& b) {
                    return a.rank == b.rank ? a.index < b.index : a.rank < b.rank;
                });
                std::sort(sorted_own.begin(), sorted_own.end(), [](const Row& a, const Row& b) {
                    return a.rank == b.rank ? a.index < b.index : a.rank < b.rank;
                });
                auto all = make_bucket(opp, weighted_rows, &weighted);
                Bucket lower = zero_bucket();
                std::size_t opos = 0, p = 0;
                while (p < sorted_own.size()) {
                    const auto rank = sorted_own[p].rank;
                    while (opos < sorted_opp.size() && sorted_opp[opos].rank < rank) {
                        const auto j = sorted_opp[opos++].index;
                        add_to_bucket(lower, opp, j, weighted[j]);
                    }
                    Bucket equal = zero_bucket();
                    std::size_t end = opos;
                    while (end < sorted_opp.size() && sorted_opp[end].rank == rank) {
                        const auto j = sorted_opp[end++].index;
                        add_to_bucket(equal, opp, j, weighted[j]);
                    }
                    std::size_t own_end = p;
                    while (own_end < sorted_own.size() && sorted_own[own_end].rank == rank) {
                        const auto i = sorted_own[own_end++].index;
                        const auto holding = hands_[own][i];
                        const Integer all_compatible = compatible_mass(holding, all);
                        const Integer low = compatible_mass(holding, lower);
                        const Integer equal_mass = compatible_mass(holding, equal);
                        Integer high = add(all_compatible, -low);
                        high = add(high, -equal_mass);
                        if (high < 0)
                            fail(ErrorCode::invalid_input, "negative higher-rank compatible mass");
                        Integer signed_mass = add(low, -high);
                        Integer value = multiply(weights_[own][i], signed_mass);
                        value = multiply(value, payoff_sig);
                        answer[i] = add(answer[i], std::move(value));
                    }
                    while (opos < end) {
                        const auto j = sorted_opp[opos++].index;
                        add_to_bucket(lower, opp, j, weighted[j]);
                    }
                    p = own_end;
                }
            }
        }
        }
        if (common_denominator_power > 0) {
            for (auto& value : answer) if (value != 0)
                value = shift_left(value, static_cast<std::size_t>(common_denominator_power));
        }
        std::vector<double> out(answer.size());
        for (std::size_t i = 0; i < answer.size(); ++i)
            out[i] = convert(answer[i], output_denominator);
        return out;
    }

    [[nodiscard]] const Integer& normalizer_integer() const noexcept { return normalizer_; }
    [[nodiscard]] std::string normalizer_hex() const {
        std::vector<unsigned char> bytes;
        boost::multiprecision::export_bits(normalizer_, std::back_inserter(bytes), 8, true);
        if (bytes.empty()) return "0";
        constexpr char digits[] = "0123456789abcdef";
        std::string out;
        out.reserve(bytes.size() * 2);
        bool started = false;
        for (const auto byte : bytes) {
            const unsigned high = static_cast<unsigned>(byte >> 4);
            const unsigned low = static_cast<unsigned>(byte & 0x0fU);
            if (started) {
                out.push_back(digits[high]); out.push_back(digits[low]);
            } else if (high != 0) {
                out.push_back(digits[high]); out.push_back(digits[low]); started = true;
            } else if (low != 0) {
                out.push_back(digits[low]); started = true;
            }
        }
        return out;
    }
    [[nodiscard]] std::array<int, 2> seat_weight_exponents() const noexcept { return weight_exponents_; }
    [[nodiscard]] const std::array<std::vector<Integer>, 2>& integer_weights() const noexcept { return weights_; }
    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }
    [[nodiscard]] const Limits& limits() const noexcept { return limits_; }
    [[nodiscard]] std::array<std::size_t, 2> hand_counts() const noexcept {
        return {hands_[0].size(), hands_[1].size()};
    }
    void clear_rank_cache() noexcept {
        rank_cache_.clear();
        lru_.clear();
    }
    [[nodiscard]] std::size_t rank_cache_size() const noexcept { return rank_cache_.size(); }

private:
    struct Bucket { Integer total{}; std::array<Integer, 52> cards{}; std::map<std::uint16_t, Integer> exact{}; };
    struct CachedRanks { std::array<std::vector<detail::Rank>, 2> sides; };
    struct FoldClass { std::uint64_t board_mask = 0; std::vector<std::size_t> members; };
    struct FoldBucket { Integer total{}; std::array<Integer, 52> cards{}; };
    static constexpr auto no_identical_hand = std::numeric_limits<std::size_t>::max();

    void prepare_fold_classes() {
        // These radix buffers die before the separate 4096-slot lookup below.
        for (std::size_t p = 0; p < 2; ++p) {
            fold_board_masks_[p].resize(hands_[p].size());
            fold_classes_[p].reserve(hands_[p].size());
            std::vector<std::size_t> order(hands_[p].size()), scratch(hands_[p].size());
            for (std::size_t i = 0; i < hands_[p].size(); ++i) {
                std::uint64_t mask = 0;
                for (std::size_t k = 0; k < boards_.size(); ++k)
                    if ((hand_masks_[p][i] & board_masks_[k]) == 0) mask |= std::uint64_t{1} << k;
                fold_board_masks_[p][i] = mask;
                order[i] = i;
            }
            for (unsigned bit = 0; bit < 64; ++bit) {
                std::size_t zeros = 0;
                for (auto i : order) if (((fold_board_masks_[p][i] >> bit) & 1U) == 0) ++zeros;
                std::size_t low = 0, high = zeros;
                for (auto i : order)
                    scratch[((fold_board_masks_[p][i] >> bit) & 1U) ? high++ : low++] = i;
                order.swap(scratch);
            }
            for (std::size_t first = 0; first < order.size();) {
                const auto mask = fold_board_masks_[p][order[first]];
                auto last = first + 1;
                while (last < order.size() && fold_board_masks_[p][order[last]] == mask) ++last;
                FoldClass group{mask, {}};
                group.members.reserve(last - first);
                for (auto position = first; position < last; ++position) {
                    group.members.push_back(order[position]);
                    ++receipt_.fold_membership_entries;
                }
                fold_classes_[p].push_back(std::move(group));
                first = last;
            }
            receipt_.fold_mask_entries += fold_board_masks_[p].size();
            receipt_.fold_classes_per_side[p] = fold_classes_[p].size();
        }
        std::array<std::size_t, 4096> lookup;
        for (std::size_t own = 0; own < 2; ++own) {
            lookup.fill(no_identical_hand);
            const auto opp = 1 - own;
            for (std::size_t j = 0; j < hands_[opp].size(); ++j)
                lookup[detail::hand_key(hands_[opp][j])] = j;
            fold_identical_opponent_[own].resize(hands_[own].size());
            for (std::size_t i = 0; i < hands_[own].size(); ++i)
                fold_identical_opponent_[own][i] = lookup[detail::hand_key(hands_[own][i])];
        }
        const auto logical_entries = 3 * total_hands() +
            4 * (fold_classes_[0].size() + fold_classes_[1].size()) + 64;
        if (logical_entries > receipt_.fold_class_setup_entries ||
            receipt_.fold_mask_entries != total_hands() || receipt_.fold_membership_entries != total_hands())
            fail(ErrorCode::storage_limit, "fold class logical layout exceeds constructor reservation");
    }
    FoldBucket make_fold_bucket(std::size_t opp, const FoldClass& group,
                                const std::vector<Integer>& weighted, bool& any) {
        FoldBucket bucket;
        for (auto j : group.members) {
            if (weighted[j] == 0) continue;
            any = true;
            const auto hand = hands_[opp][j];
            bucket.total = add(bucket.total, weighted[j]);
            bucket.cards[hand.first] = add(bucket.cards[hand.first], weighted[j]);
            bucket.cards[hand.second] = add(bucket.cards[hand.second], weighted[j]);
        }
        return bucket;
    }
    Integer fold_compatible_mass(std::size_t own, std::size_t i, std::uint64_t mask,
                                 const FoldBucket& bucket, const std::vector<Integer>& weighted) {
        const auto hand = hands_[own][i];
        Integer result = add(bucket.total, -bucket.cards[hand.first]);
        result = add(result, -bucket.cards[hand.second]);
        const auto j = fold_identical_opponent_[own][i];
        if (j != no_identical_hand && fold_board_masks_[1 - own][j] == mask)
            result = add(result, weighted[j]);
        if (result < 0) fail(ErrorCode::invalid_input, "negative fold-class blocker mass");
        return result;
    }

    [[noreturn]] static void fail(ErrorCode code, const char* message) { throw KernelError(code, message); }
    void validate_limits() const {
        if (!limits_.max_hands_per_side || limits_.max_hands_per_side > kMaximumHandsPerSide ||
            !limits_.max_boards || limits_.max_boards > kMaximumBoards ||
            !limits_.max_integer_bits || limits_.max_integer_bits > kMaximumIntegerBits ||
            !limits_.max_integer_payload_bits ||
            limits_.max_integer_payload_bits > kMaximumIntegerPayloadBits ||
            !limits_.max_modeled_work || limits_.max_modeled_work > kMaximumModeledWork ||
            !limits_.max_storage_entries || limits_.max_storage_entries > kMaximumStorageEntries)
            fail(ErrorCode::invalid_limits, "limits must be positive reduce-only values");
    }
    void reserve_work(std::uint64_t amount) {
        if (amount > limits_.max_modeled_work - receipt_.modeled_work)
            fail(ErrorCode::modeled_work_limit, "exact selected kernel modeled-work limit exceeded");
        receipt_.modeled_work += amount;
    }
    void reserve_entries(std::size_t amount) {
        if (amount > limits_.max_storage_entries)
            fail(ErrorCode::storage_limit, "exact selected kernel storage-entry limit exceeded");
        receipt_.retained_entries = std::max(receipt_.retained_entries, amount);
    }
    void preflight_storage(std::size_t retained, std::size_t scratch, const char* label) {
        if (retained > limits_.max_storage_entries ||
            scratch > limits_.max_storage_entries - retained)
            fail(ErrorCode::storage_limit, label);
        receipt_.retained_entries = std::max(receipt_.retained_entries, retained);
        receipt_.peak_scratch_entries = std::max(receipt_.peak_scratch_entries, scratch);
    }
    void preflight_query(std::size_t board_count, std::uint64_t per_board,
                         std::size_t entries, const char* label, std::size_t bits = 0,
                         std::uint64_t fixed_work = 0) {
        const auto work = detail::checked_add_count(
            detail::checked_mul_count(board_count, per_board), fixed_work);
        if (work > limits_.max_modeled_work - receipt_.modeled_work)
            fail(ErrorCode::modeled_work_limit, label);
        if (entries > limits_.max_storage_entries ||
            receipt_.retained_entries > limits_.max_storage_entries - entries)
            fail(ErrorCode::storage_limit, label);
        if (bits > limits_.max_integer_bits)
            fail(ErrorCode::integer_bit_limit, label);
        check_payload_forecast(bits, label);
        receipt_.modeled_work += work;
        receipt_.peak_scratch_entries = std::max(receipt_.peak_scratch_entries, entries);
        receipt_.peak_integer_bits = std::max(receipt_.peak_integer_bits, bits);
    }
    void check_query_bits(std::size_t bits, const char* label) {
        if (bits > limits_.max_integer_bits)
            fail(ErrorCode::integer_bit_limit, label);
        check_payload_forecast(bits, label);
        receipt_.peak_integer_bits = std::max(receipt_.peak_integer_bits, bits);
    }
    void check_payload_forecast(std::size_t query_bits, const char* label) {
        const auto h = static_cast<std::uint64_t>(total_hands());
        const auto query_entries = detail::checked_add_count(
            detail::checked_mul_count(140, h), 800);
        const auto query_payload = detail::checked_mul_count(
            query_entries, std::max<std::size_t>(1, query_bits));
        const auto conversion_payload = static_cast<std::uint64_t>(std::max<std::size_t>(1, query_bits) + 53);
        const auto forecast = detail::checked_add_count(
            detail::checked_add_count(receipt_.setup_integer_payload_bits, query_payload),
            conversion_payload);
        receipt_.peak_integer_payload_bits = std::max(receipt_.peak_integer_payload_bits, forecast);
        if (forecast > limits_.max_integer_payload_bits)
            fail(ErrorCode::integer_payload_limit, label);
    }
    static std::size_t ceil_log2(std::size_t n) {
        if (n <= 1) return 0;
        std::size_t bits = 0, x = n - 1;
        while (x) { ++bits; x >>= 1; }
        return bits;
    }
    std::size_t total_hands() const { return hands_[0].size() + hands_[1].size(); }
    void check_bits(std::size_t bits) {
        if (bits > limits_.max_integer_bits)
            fail(ErrorCode::integer_bit_limit, "exact selected kernel integer-bit limit exceeded");
        receipt_.peak_integer_bits = std::max(receipt_.peak_integer_bits, bits);
    }
    std::size_t forecast_add(const Integer& a, const Integer& b) const {
        return std::max(detail::magnitude_bits(a), detail::magnitude_bits(b)) + 1;
    }
    Integer add(const Integer& a, const Integer& b) {
        check_bits(forecast_add(a, b)); ++receipt_.integer_additions;
        return a + b;
    }
    Integer multiply(const Integer& a, const Integer& b) {
        const auto bits = detail::magnitude_bits(a) + detail::magnitude_bits(b);
        check_bits(bits); ++receipt_.integer_multiplications;
        return a * b;
    }
    Integer shift_left(const Integer& value, std::size_t shift) {
        const auto width = detail::magnitude_bits(value);
        if (shift > limits_.max_integer_bits || width > limits_.max_integer_bits - shift)
            fail(ErrorCode::integer_bit_limit, "exact selected kernel shift forecast exceeded");
        check_bits(width + shift); ++receipt_.integer_shifts;
        return value << shift;
    }
    double convert(const Integer& numerator, const Integer& denominator) {
        try {
            auto converted = exact_binary64::convert(numerator, denominator,
                exact_binary64::Limits{limits_.max_integer_bits,
                    std::min(exact_binary64::kMaximumScratchBits, limits_.max_integer_bits + 53)});
            ++receipt_.conversion_calls;
            receipt_.peak_integer_bits = std::max(receipt_.peak_integer_bits,
                converted.receipt.peak_input_bits);
            receipt_.peak_conversion_scratch_bits = std::max(
                receipt_.peak_conversion_scratch_bits, converted.receipt.peak_scratch_bits);
            return converted.value;
        } catch (const exact_binary64::ConversionError&) {
            fail(ErrorCode::conversion_failure, "completed exact callback cannot round to a normal finite double");
        }
    }
    void validate_inputs() {
        for (std::size_t p = 0; p < 2; ++p) {
            std::unordered_set<std::uint16_t> seen;
            seen.reserve(source_hands_[p].size());
            for (const auto& row : source_hands_[p]) {
                const auto a = row.hand.first, b = row.hand.second;
                if (a >= 52 || b >= 52 || a == b)
                    fail(ErrorCode::invalid_input, "invalid physical hand card ids");
                if (!seen.insert(detail::hand_key(row.hand)).second)
                    fail(ErrorCode::duplicate_hand, "duplicate physical holding after canonicalization");
                (void)detail::decode_parts(row.binary64_weight_bits, false, false,
                                           "range weights must be finite and positive");
            }
        }
        std::set<std::array<std::uint8_t, 5>> seen_boards;
        std::array<std::uint8_t, 5> previous_board{};
        bool have_previous = false;
        for (const auto& board : boards_) {
            std::array<std::uint8_t, 5> sorted = board.cards;
            for (auto card : sorted) if (card >= 52) fail(ErrorCode::invalid_input, "invalid board card id");
            std::sort(sorted.begin(), sorted.end());
            if (std::adjacent_find(sorted.begin(), sorted.end()) != sorted.end())
                fail(ErrorCode::invalid_input, "selected board repeats a card");
            if (!(board.cards[0] < board.cards[1] && board.cards[1] < board.cards[2]))
                fail(ErrorCode::invalid_input, "selected flop must be canonical DECK order");
            if (!seen_boards.insert(board.cards).second)
                fail(ErrorCode::duplicate_board, "duplicate ordered selected board");
            if (have_previous && !(previous_board < board.cards))
                fail(ErrorCode::invalid_input, "selected boards must be in canonical full-outcome order");
            previous_board = board.cards; have_previous = true;
            board_masks_.push_back(mask_of(board.cards));
        }
        for (const auto& side : source_hands_) {
            std::vector<Hand> copy; copy.reserve(side.size());
            for (const auto& row : side) copy.push_back(row.hand);
            hands_.push_back(std::move(copy));
        }
        hand_masks_[0].reserve(hands_[0].size()); hand_masks_[1].reserve(hands_[1].size());
        for (std::size_t p = 0; p < 2; ++p) for (const auto& hand : hands_[p])
            hand_masks_[p].push_back((std::uint64_t{1} << hand.first) | (std::uint64_t{1} << hand.second));
    }
    static std::uint64_t mask_of(const std::array<std::uint8_t, 5>& cards) {
        std::uint64_t mask = 0; for (auto c : cards) mask |= std::uint64_t{1} << c; return mask;
    }
    void prepare_weights() {
        int exponents[2]{};
        std::array<std::size_t, 2> forecast_weight_bits{};
        for (std::size_t p = 0; p < 2; ++p) {
            int common = std::numeric_limits<int>::max();
            for (const auto& row : source_hands_[p]) {
                const auto d = detail::decode_parts(row.binary64_weight_bits, false, false,
                                                    "range weights must be finite and positive");
                common = std::min(common, d.exponent);
            }
            exponents[p] = common;
            for (const auto& row : source_hands_[p]) {
                const auto d = detail::decode_parts(row.binary64_weight_bits, false, false,
                                                    "range weights must be finite and positive");
                const auto sig_bits = static_cast<std::size_t>(64 - std::countl_zero(d.significand));
                forecast_weight_bits[p] = std::max(forecast_weight_bits[p],
                    sig_bits + static_cast<std::size_t>(d.exponent - common));
            }
            check_bits(forecast_weight_bits[p]);
        }
        const auto z_forecast = forecast_weight_bits[0] + forecast_weight_bits[1] +
            ceil_log2(source_hands_[0].size()) + ceil_log2(source_hands_[1].size()) +
            ceil_log2(boards_.size()) + 4;
        check_bits(z_forecast);
        const auto setup_width = std::max<std::size_t>(53, z_forecast);
        const auto setup_entries = detail::checked_add_count(
            detail::checked_mul_count(8, total_hands()), 128);
        const auto setup_payload = detail::checked_mul_count(setup_entries, setup_width);
        receipt_.setup_integer_payload_bits = static_cast<std::size_t>(setup_payload);
        receipt_.peak_integer_payload_bits = std::max(receipt_.peak_integer_payload_bits,
                                                       receipt_.setup_integer_payload_bits);
        if (setup_payload > limits_.max_integer_payload_bits)
            fail(ErrorCode::integer_payload_limit, "constructor integer-payload admission exceeded");

        std::array<std::vector<Integer>, 2> prepared;
        for (std::size_t p = 0; p < 2; ++p) {
            prepared[p].reserve(source_hands_[p].size());
            for (const auto& row : source_hands_[p]) {
                const auto d = detail::decode_parts(row.binary64_weight_bits, false, false,
                                                    "range weights must be finite and positive");
                prepared[p].push_back(shift_left(Integer(d.significand),
                    static_cast<std::size_t>(d.exponent - exponents[p])));
            }
        }
        weights_ = std::move(prepared);
        weight_exponents_ = {exponents[0], exponents[1]};
        max_weight_bits_ = {0, 0};
        for (std::size_t p = 0; p < 2; ++p) for (const auto& w : weights_[p])
            max_weight_bits_[p] = std::max(max_weight_bits_[p], detail::magnitude_bits(w));
    }
    void validate_indexes(std::span<const std::size_t> indexes) const {
        if (indexes.size() > boards_.size()) fail(ErrorCode::invalid_query, "too many board indexes");
        std::array<bool, kMaximumBoards> seen{};
        for (auto k : indexes) {
            if (k >= boards_.size() || seen[k]) fail(ErrorCode::invalid_query, "invalid or duplicate board index");
            seen[k] = true;
        }
    }
    std::vector<std::size_t> visible(std::size_t side, std::size_t board) const {
        std::vector<std::size_t> out; out.reserve(hands_[side].size());
        for (std::size_t i = 0; i < hands_[side].size(); ++i)
            if ((board_masks_[board] & hand_masks_[side][i]) == 0) out.push_back(i);
        return out;
    }
    Bucket zero_bucket() const { return {}; }
    Bucket make_bucket(std::size_t side, const std::vector<std::size_t>& rows,
                       const std::vector<Integer>* override_weights) {
        Bucket out;
        for (auto i : rows) {
            const Integer& value = override_weights ? (*override_weights)[i] : weights_[side][i];
            out.total = add(out.total, value);
            const auto hand = hands_[side][i];
            out.cards[hand.first] = add(out.cards[hand.first], value);
            out.cards[hand.second] = add(out.cards[hand.second], value);
            out.exact.emplace(detail::hand_key(hand), value);
        }
        return out;
    }
    Bucket make_unit_bucket(std::size_t side, const std::vector<std::size_t>& rows) {
        Bucket out;
        for (auto i : rows) {
            out.total = add(out.total, Integer(1));
            const auto hand = hands_[side][i];
            out.cards[hand.first] = add(out.cards[hand.first], Integer(1));
            out.cards[hand.second] = add(out.cards[hand.second], Integer(1));
            out.exact.emplace(detail::hand_key(hand), Integer(1));
        }
        return out;
    }
    Integer compatible_mass(Hand hand, const Bucket& bucket) {
        Integer result = add(bucket.total, -bucket.cards[hand.first]);
        result = add(result, -bucket.cards[hand.second]);
        const auto found = bucket.exact.find(detail::hand_key(hand));
        if (found != bucket.exact.end()) result = add(result, found->second);
        if (result < 0) fail(ErrorCode::invalid_input, "negative blocker inclusion-exclusion mass");
        return result;
    }
    void add_to_bucket(Bucket& bucket, std::size_t side, std::size_t i, const Integer& value) {
        bucket.total = add(bucket.total, value);
        const auto hand = hands_[side][i];
        bucket.cards[hand.first] = add(bucket.cards[hand.first], value);
        bucket.cards[hand.second] = add(bucket.cards[hand.second], value);
        bucket.exact.emplace(detail::hand_key(hand), value);
    }
    void compute_normalizer() {
        normalizer_ = 0;
        for (std::size_t k = 0; k < boards_.size(); ++k) {
            auto rows0 = visible(0, k), rows1 = visible(1, k);
            auto bucket1 = make_bucket(1, rows1, nullptr);
            for (auto i : rows0) {
                Integer term = multiply(weights_[0][i], compatible_mass(hands_[0][i], bucket1));
                normalizer_ = add(normalizer_, term);
            }
        }
        if (normalizer_ <= 0) fail(ErrorCode::no_compatible_deals, "selected boards contain no compatible deal");
        const auto z_bits = detail::magnitude_bits(normalizer_);
        check_bits(z_bits);
        receipt_.retained_entries = std::max(receipt_.retained_entries,
            20 * total_hands() + 8 * boards_.size() + 256 +
            (rank_cache_boards_ + 1) * total_hands());
    }
    const CachedRanks& rank_vectors(std::size_t board) {
        auto found = rank_cache_.find(board);
        if (found != rank_cache_.end()) {
            ++receipt_.rank_cache_hits;
            lru_.remove(board);
            lru_.push_back(board);
            return found->second;
        }
        ++receipt_.rank_cache_misses;
        CachedRanks ranks;
        const auto& b = boards_[board].cards;
        for (std::size_t p = 0; p < 2; ++p) {
            ranks.sides[p].resize(hands_[p].size());
            for (std::size_t i = 0; i < hands_[p].size(); ++i) {
                if (board_masks_[board] & hand_masks_[p][i]) continue;
                std::array<std::uint8_t, 7> cards{
                    hands_[p][i].first, hands_[p][i].second,
                    b[0], b[1], b[2], b[3], b[4]};
                ranks.sides[p][i] = detail::rank_seven(cards);
                ++receipt_.rank_calls;
            }
        }
        if (rank_cache_.size() == rank_cache_boards_) {
            const auto evicted = lru_.front(); lru_.pop_front();
            rank_cache_.erase(evicted); ++receipt_.rank_cache_evictions;
        }
        lru_.push_back(board);
        return rank_cache_.emplace(board, std::move(ranks)).first->second;
    }

    Limits limits_{};
    std::size_t rank_cache_boards_ = 1;
    std::array<std::vector<WeightedHand>, 2> source_hands_{};
    std::vector<SelectedBoard> boards_;
    std::vector<std::vector<Hand>> hands_;
    std::array<std::vector<std::uint64_t>, 2> hand_masks_{};
    std::vector<std::uint64_t> board_masks_;
    FoldTraversal fold_traversal_ = FoldTraversal::literal_boards;
    std::array<std::vector<std::uint64_t>, 2> fold_board_masks_{};
    std::array<std::vector<FoldClass>, 2> fold_classes_{};
    std::array<std::vector<std::size_t>, 2> fold_identical_opponent_{};
    std::array<std::vector<Integer>, 2> weights_{};
    std::array<int, 2> weight_exponents_{};
    std::array<std::size_t, 2> max_weight_bits_{};
    Integer normalizer_{};
    std::map<std::size_t, CachedRanks> rank_cache_;
    std::list<std::size_t> lru_;
    Receipt receipt_{};
};

} // namespace openpoker::exact_selected_kernel

