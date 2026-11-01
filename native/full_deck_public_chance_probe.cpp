#include "full_deck_public_chance.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <iomanip>
#include <limits>
#include <span>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {
using namespace openpoker::full_deck_public_chance;
constexpr std::string_view kProtocol = "OPENPOKER_FULL_DECK_PUBLIC_CHANCE_V1";
constexpr std::size_t kMaximumLineBytes = 1U << 20;
constexpr std::size_t kMaximumResponseBytes = 64U << 20;
constexpr std::size_t kMaximumRecords = 4096;
constexpr std::size_t kMaximumTokensPerRecord = 20000;

enum class Failure { invalid_request, invalid_limit, invalid_range, invalid_query,
                     request_too_large, modeled_work_limit, storage_limit,
                     integer_payload_limit };
class ParseError final : public std::runtime_error {
public:
    ParseError(Failure code, const char* what) : std::runtime_error(what), code_(code) {}
    Failure code() const noexcept { return code_; }
private:
    Failure code_;
};

std::uint64_t checked_add(std::uint64_t a, std::uint64_t b) {
    if (b > std::numeric_limits<std::uint64_t>::max() - a)
        throw ParseError(Failure::invalid_limit, "probe work arithmetic overflow");
    return a + b;
}
std::uint64_t checked_mul(std::uint64_t a, std::uint64_t b) {
    if (a && b > std::numeric_limits<std::uint64_t>::max() / a)
        throw ParseError(Failure::invalid_limit, "probe work arithmetic overflow");
    return a * b;
}

enum class ReadStatus { line, end, too_large };
ReadStatus read_line(std::istream& in, std::string& line) {
    line.clear();
    bool any = false;
    for (;;) {
        const int next = in.get();
        if (next == std::char_traits<char>::eof()) return any ? ReadStatus::line : ReadStatus::end;
        any = true;
        if (next == '\n') break;
        if (line.size() == kMaximumLineBytes) return ReadStatus::too_large;
        line.push_back(static_cast<char>(next));
    }
    if (!line.empty() && line.back() == '\r') line.pop_back();
    return ReadStatus::line;
}

bool space(char c) {
    return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == '\f' || c == '\v';
}
class Tokens final {
public:
    explicit Tokens(std::string_view text) : text_(text) {}
    std::string_view next() {
        while (position_ < text_.size() && space(text_[position_])) ++position_;
        const auto first = position_;
        while (position_ < text_.size() && !space(text_[position_])) ++position_;
        if (first == position_) throw ParseError(Failure::invalid_request, "missing token");
        if (++count_ > kMaximumTokensPerRecord)
            throw ParseError(Failure::request_too_large, "request token cap");
        return text_.substr(first, position_ - first);
    }
    bool done() {
        while (position_ < text_.size() && space(text_[position_])) ++position_;
        return position_ == text_.size();
    }
    void expect(std::string_view expected) {
        if (next() != expected) throw ParseError(Failure::invalid_request, "unexpected token");
    }
    std::size_t count() const noexcept { return count_; }
    std::uint64_t decimal(std::uint64_t maximum, Failure failure) {
        const auto token = next();
        if (token.empty() || token.size() > 20) throw ParseError(failure, "decimal width");
        std::uint64_t value = 0;
        for (const char c : token) {
            if (c < '0' || c > '9') throw ParseError(failure, "invalid decimal");
            const auto digit = static_cast<std::uint64_t>(c - '0');
            if (value > (std::numeric_limits<std::uint64_t>::max() - digit) / 10)
                throw ParseError(failure, "decimal limit");
            value = value * 10 + digit;
            if (value > maximum) throw ParseError(failure, "decimal limit");
        }
        return value;
    }
    std::uint64_t card(std::uint8_t deck_count, const std::array<bool, 52>& in_deck,
                       Failure failure) {
        const auto value = decimal(51, failure);
        if (!in_deck[value] || value >= 52 || deck_count < 9)
            throw ParseError(failure, "card outside declared deck");
        return value;
    }
    std::uint64_t bits64(bool allow_negative, bool allow_zero, Failure failure,
                         bool at_most_one = false) {
        const auto token = next();
        if (token.size() != 16) throw ParseError(failure, "binary64 token width");
        std::uint64_t value = 0;
        for (const char c : token) {
            const int digit = hex_digit(c);
            if (digit < 0) throw ParseError(failure, "invalid binary64 token");
            value = (value << 4) | static_cast<std::uint64_t>(digit);
        }
        const auto exponent = (value >> 52) & 0x7ffU;
        const auto fraction = value & ((std::uint64_t{1} << 52) - 1);
        const bool negative = (value >> 63) != 0;
        const bool zero = exponent == 0 && fraction == 0;
        if (exponent == 0x7ffU || (!allow_negative && negative && !zero) ||
            (!allow_zero && zero) ||
            (at_most_one && (value & ~(std::uint64_t{1} << 63)) > 0x3ff0000000000000ULL))
            throw ParseError(failure, "invalid binary64 value");
        return value;
    }
    std::string_view bounded_hex(std::size_t max_bits, Failure failure, bool positive) {
        const auto token = next();
        const auto max_digits = (max_bits + 3) / 4;
        if (token.empty() || token.size() > max_digits)
            throw ParseError(failure, "integer token width");
        bool nonzero = false;
        std::size_t bits = 0;
        bool top_seen = false;
        for (const char c : token) {
            const int digit = hex_digit(c);
            if (digit < 0) throw ParseError(failure, "invalid integer token");
            if (!top_seen && digit != 0) {
                top_seen = true;
                int top_bits = 0;
                for (int v = digit; v; v >>= 1) ++top_bits;
                bits = top_bits;
            } else if (top_seen) {
                bits += 4;
            }
            nonzero = nonzero || digit != 0;
        }
        if (bits > max_bits || (positive && !nonzero))
            throw ParseError(failure, "integer value width or sign");
        return token;
    }
    static int hex_digit(char c) {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    }
private:
    std::string_view text_;
    std::size_t position_ = 0;
    std::size_t count_ = 0;
};

int compare_hex_values(std::string_view left, std::string_view right) {
    while (left.size() > 1 && left.front() == '0') left.remove_prefix(1);
    while (right.size() > 1 && right.front() == '0') right.remove_prefix(1);
    if (left.size() != right.size()) return left.size() < right.size() ? -1 : 1;
    for (std::size_t i=0;i<left.size();++i) {
        const int a=Tokens::hex_digit(left[i]), b=Tokens::hex_digit(right[i]);
        if (a!=b) return a<b ? -1 : 1;
    }
    return 0;
}

struct Request {
    DeckDefinition deck{};
    Limits limits{};
    std::size_t sb_count = 0, bb_count = 0;
    bool terminal = false, convert = false;
    std::size_t prefix_length = 0, player = 0, reach_count = 0;
    std::size_t input_tokens = 0, output_bytes_upper = 0;
    std::size_t ownership_entries_upper = 0, ownership_payload_bits_upper = 0;
    std::uint64_t parse_work_upper = 0;
    std::uint64_t caller_work_limit = 0;
    TerminalKind kind = TerminalKind::fold;
    std::array<std::uint8_t, 5> cards{};
    std::uint64_t payoff_bits = 0;
    std::string_view q_num, q_den;
};

struct MaterializationReceipt {
    std::size_t range_vector_allocation_sites = 0;
    std::size_t reach_vector_allocation_sites = 0;
    std::size_t proposal_integer_parse_calls = 0;
    std::size_t kernel_constructor_calls = 0;
};

Integer parse_hex_integer(std::string_view token) {
    Integer result = 0;
    for (const char c : token) {
        result <<= 4;
        result += Tokens::hex_digit(c);
    }
    return result;
}

void validate_record(std::string_view line, Request& r) {
    Tokens t(line);
    t.expect(kProtocol);
    t.expect("deck");
    std::array<bool, 52> in_deck{};
    const auto deck_mode = t.next();
    if (deck_mode == "FULL52") {
        r.deck = DeckDefinition::full52();
        in_deck.fill(true);
    } else if (deck_mode == "REDUCED") {
        const auto count = t.decimal(52, Failure::invalid_request);
        if (count < 9) throw ParseError(Failure::invalid_request, "reduced deck size");
        r.deck.mode = DeckMode::reduced_proof;
        r.deck.count = static_cast<std::size_t>(count);
        int previous = -1;
        for (std::size_t i = 0; i < r.deck.count; ++i) {
            const auto card = t.decimal(51, Failure::invalid_request);
            if (static_cast<int>(card) <= previous) throw ParseError(Failure::invalid_request, "deck order");
            previous = static_cast<int>(card);
            r.deck.cards[i] = static_cast<std::uint8_t>(card);
            in_deck[card] = true;
        }
    } else throw ParseError(Failure::invalid_request, "deck mode");

    t.expect("limits");
    r.limits.max_hands_per_side = static_cast<std::size_t>(t.decimal(1326, Failure::invalid_limit));
    r.limits.max_integer_bits = static_cast<std::size_t>(t.decimal(65536, Failure::invalid_limit));
    r.limits.max_modeled_work = t.decimal(500'000'000, Failure::invalid_limit);
    r.caller_work_limit = r.limits.max_modeled_work;
    r.limits.max_storage_entries = static_cast<std::size_t>(t.decimal(2'000'000, Failure::invalid_limit));
    r.limits.max_integer_payload_bits = static_cast<std::size_t>(t.decimal(1U << 30, Failure::invalid_limit));
    if (!r.limits.max_hands_per_side || !r.limits.max_integer_bits || !r.limits.max_modeled_work ||
        !r.limits.max_storage_entries || !r.limits.max_integer_payload_bits)
        throw ParseError(Failure::invalid_limit, "zero limit");

    t.expect("ranges");
    r.sb_count = static_cast<std::size_t>(t.decimal(r.limits.max_hands_per_side, Failure::invalid_range));
    r.bb_count = static_cast<std::size_t>(t.decimal(r.limits.max_hands_per_side, Failure::invalid_range));
    if (!r.sb_count || !r.bb_count) throw ParseError(Failure::invalid_range, "empty range");
    std::array<std::array<std::uint64_t, 43>, 2> seen_hands{};
    std::size_t side_index = 0;
    for (const auto side : {std::string_view("sb"), std::string_view("bb")}) {
        t.expect(side);
        const auto count = side == "sb" ? r.sb_count : r.bb_count;
        for (std::size_t i = 0; i < count; ++i) {
            const auto a = t.card(static_cast<std::uint8_t>(r.deck.count), in_deck, Failure::invalid_range);
            const auto b = t.card(static_cast<std::uint8_t>(r.deck.count), in_deck, Failure::invalid_range);
            if (a >= b) throw ParseError(Failure::invalid_range, "hand card order");
            const auto key = a * 52 + b;
            const auto word = key >> 6;
            const auto bit = std::uint64_t{1} << (key & 63U);
            if (seen_hands[side_index][word] & bit)
                throw ParseError(Failure::invalid_range, "duplicate holding within seat");
            seen_hands[side_index][word] |= bit;
            const auto weight = t.bits64(false, false, Failure::invalid_range);
            (void)weight;
        }
        ++side_index;
    }

    t.expect("query");
    const auto query = t.next();
    if (query == "PREFIX") {
        t.expect("prefix");
        const auto mode = t.next();
        if (mode != "exact" && mode != "binary64") throw ParseError(Failure::invalid_query, "prefix mode");
        r.convert = mode == "binary64";
        r.prefix_length = static_cast<std::size_t>(t.decimal(5, Failure::invalid_query));
        if (r.prefix_length != 0 && r.prefix_length != 3 && r.prefix_length != 4 && r.prefix_length != 5)
            throw ParseError(Failure::invalid_query, "prefix length");
        std::array<bool, 52> seen{};
        for (std::size_t i = 0; i < r.prefix_length; ++i) {
            const auto card = t.card(static_cast<std::uint8_t>(r.deck.count), in_deck, Failure::invalid_query);
            if (seen[card]) throw ParseError(Failure::invalid_query, "duplicate prefix card");
            seen[card] = true;
            r.cards[i] = static_cast<std::uint8_t>(card);
        }
        if (r.prefix_length >= 3 && !(r.cards[0] < r.cards[1] && r.cards[1] < r.cards[2]))
            throw ParseError(Failure::invalid_query, "noncanonical flop");
    } else if (query == "TERMINAL") {
        t.expect("terminal");
        const auto mode = t.next();
        if (mode != "exact" && mode != "binary64") throw ParseError(Failure::invalid_query, "terminal mode");
        r.convert = mode == "binary64"; r.terminal = true;
        r.player = static_cast<std::size_t>(t.decimal(1, Failure::invalid_query));
        const auto kind = t.next();
        if (kind == "FOLD") r.kind = TerminalKind::fold;
        else if (kind == "SHOWDOWN") r.kind = TerminalKind::showdown;
        else throw ParseError(Failure::invalid_query, "terminal kind");
        r.payoff_bits = t.bits64(r.kind == TerminalKind::fold, true, Failure::invalid_query);
        r.q_num = t.bounded_hex(r.limits.max_integer_bits, Failure::invalid_query, true);
        r.q_den = t.bounded_hex(r.limits.max_integer_bits, Failure::invalid_query, true);
        if (compare_hex_values(r.q_num,r.q_den)>0)
            throw ParseError(Failure::invalid_query, "proposal exceeds one");
        r.reach_count = static_cast<std::size_t>(t.decimal(1326, Failure::invalid_query));
        const auto expected_reaches = r.player == 0 ? r.bb_count : r.sb_count;
        if (r.reach_count != expected_reaches) throw ParseError(Failure::invalid_query, "reach count mismatch");
        for (std::size_t i = 0; i < r.reach_count; ++i)
            (void)t.bits64(false, true, Failure::invalid_query, true);
        std::array<bool, 52> seen{};
        for (auto& card : r.cards) {
            const auto value = t.card(static_cast<std::uint8_t>(r.deck.count), in_deck, Failure::invalid_query);
            if (seen[value]) throw ParseError(Failure::invalid_query, "duplicate board card");
            seen[value] = true; card = static_cast<std::uint8_t>(value);
        }
        if (!(r.cards[0] < r.cards[1] && r.cards[1] < r.cards[2]))
            throw ParseError(Failure::invalid_query, "noncanonical flop");
    } else throw ParseError(Failure::invalid_request, "query kind");
    if (!t.done()) throw ParseError(Failure::invalid_request, "trailing request tokens");
    r.input_tokens = t.count();
    const std::size_t output_rows = r.terminal ? (r.player == 0 ? r.sb_count : r.bb_count) : r.sb_count + r.bb_count;
    const std::size_t row_digits = (r.limits.max_integer_bits + 3) / 4;
    const auto row_model = checked_mul(static_cast<std::uint64_t>(output_rows),
        static_cast<std::uint64_t>(row_digits + 64 + (r.convert ? 17 : 0)));
    const auto scalar_model = checked_mul(3, static_cast<std::uint64_t>(row_digits));
    const auto response_model = checked_add(checked_add(4096, row_model), scalar_model);
    if (response_model > kMaximumResponseBytes)
        throw ParseError(Failure::request_too_large, "response forecast exceeds transport cap");
    r.output_bytes_upper = static_cast<std::size_t>(response_model);
    r.parse_work_upper = checked_add(checked_mul(6, static_cast<std::uint64_t>(line.size())),
        checked_add(checked_mul(16, static_cast<std::uint64_t>(r.input_tokens)), 16384));
    const auto transport_reserve = checked_add(r.parse_work_upper, checked_mul(8, response_model));
    if (transport_reserve >= r.caller_work_limit)
        throw ParseError(Failure::modeled_work_limit, "probe transport plus kernel work exceeds caller limit");
    const auto hand_total = checked_add(static_cast<std::uint64_t>(r.sb_count),
                                        static_cast<std::uint64_t>(r.bb_count));
    const auto ownership_entries = checked_add(checked_mul(4, hand_total), 128);
    const auto proposal_chars = r.terminal
        ? checked_add(static_cast<std::uint64_t>(r.q_num.size()), static_cast<std::uint64_t>(r.q_den.size()))
        : 0;
    const auto ownership_payload = checked_add(
        checked_add(checked_mul(16, proposal_chars),
                    checked_mul(4, static_cast<std::uint64_t>(r.limits.max_integer_bits))), 256);
    if (ownership_entries >= r.limits.max_storage_entries)
        throw ParseError(Failure::storage_limit, "probe ownership entry reserve exceeds caller limit");
    if (ownership_payload >= r.limits.max_integer_payload_bits)
        throw ParseError(Failure::integer_payload_limit, "probe ownership payload reserve exceeds caller limit");
    r.ownership_entries_upper = static_cast<std::size_t>(ownership_entries);
    r.ownership_payload_bits_upper = static_cast<std::size_t>(ownership_payload);
    r.limits.max_storage_entries -= r.ownership_entries_upper;
    r.limits.max_integer_payload_bits -= r.ownership_payload_bits_upper;
    r.limits.max_modeled_work = r.caller_work_limit - transport_reserve;
}

std::uint64_t read_hex64(std::string_view token) {
    std::uint64_t value = 0;
    for (const char c : token) value = (value << 4) | static_cast<std::uint64_t>(Tokens::hex_digit(c));
    return value;
}
std::string hex_integer(const Integer& value) {
    const Integer magnitude = value < 0 ? -value : value;
    return magnitude.str(0, std::ios_base::hex);
}
void append_value(std::ostringstream& out, const Integer& value) {
    out << "value " << (value < 0 ? '-' : value == 0 ? '0' : '+') << ' ' << hex_integer(value);
}
void append_receipt(std::ostringstream& out, const PublicChanceKernel& kernel) {
    const auto& r = kernel.receipt();
    out << "receipt " << r.modeled_work << ' ' << r.retained_entries << ' ' << r.peak_scratch_entries
        << ' ' << r.peak_integer_bits << ' ' << r.setup_integer_payload_bits << ' '
        << r.peak_integer_payload_bits << ' ' << r.prefix_queries << ' ' << r.terminal_queries << ' '
        << r.rank_calls << ' ' << r.conversion_calls << '\n';
}
std::string error_name(ErrorCode code) {
    switch (code) {
    case ErrorCode::invalid_limits: return "invalid_limit";
    case ErrorCode::invalid_input: case ErrorCode::duplicate_hand: return "invalid_range";
    case ErrorCode::duplicate_board: case ErrorCode::invalid_query: case ErrorCode::invalid_dyadic: return "invalid_query";
    case ErrorCode::no_compatible_deals: return "no_compatible_deals";
    case ErrorCode::integer_bit_limit: return "integer_bit_limit";
    case ErrorCode::integer_payload_limit: return "integer_payload_limit";
    case ErrorCode::modeled_work_limit: return "modeled_work_limit";
    case ErrorCode::storage_limit: return "storage_limit";
    case ErrorCode::conversion_failure: return "conversion_failure";
    }
    return "invalid_request";
}
const char* parse_error_name(Failure code) {
    switch (code) {
    case Failure::invalid_limit: return "invalid_limit";
    case Failure::invalid_range: return "invalid_range";
    case Failure::invalid_query: return "invalid_query";
    case Failure::request_too_large: return "request_too_large";
    case Failure::modeled_work_limit: return "modeled_work_limit";
    case Failure::storage_limit: return "storage_limit";
    case Failure::integer_payload_limit: return "integer_payload_limit";
    case Failure::invalid_request: return "invalid_request";
    }
    return "invalid_request";
}

std::string process(std::string_view line, MaterializationReceipt* observer = nullptr) {
    Request request;
    try { validate_record(line, request); }
    catch (const ParseError& error) { return std::string("ERR ") + parse_error_name(error.code()) + '\n'; }
    try {
        Tokens t(line);
        t.expect(kProtocol); t.expect("deck");
        if (t.next() == "REDUCED") {
            const auto n = t.decimal(52, Failure::invalid_request);
            for (std::size_t i = 0; i < n; ++i) (void)t.decimal(51, Failure::invalid_request);
        }
        t.expect("limits");
        for (int i = 0; i < 5; ++i) (void)t.decimal(std::numeric_limits<std::uint64_t>::max(), Failure::invalid_request);
        t.expect("ranges"); (void)t.decimal(1326, Failure::invalid_request); (void)t.decimal(1326, Failure::invalid_request);
        t.expect("sb");
        std::vector<WeightedHand> sb;
        if (observer) ++observer->range_vector_allocation_sites;
        sb.reserve(request.sb_count);
        for (std::size_t i = 0; i < request.sb_count; ++i) {
            const auto a = static_cast<std::uint8_t>(t.decimal(51, Failure::invalid_range));
            const auto b = static_cast<std::uint8_t>(t.decimal(51, Failure::invalid_range));
            sb.push_back(WeightedHand{Hand{a,b}, read_hex64(t.next())});
        }
        t.expect("bb");
        std::vector<WeightedHand> bb;
        if (observer) ++observer->range_vector_allocation_sites;
        bb.reserve(request.bb_count);
        for (std::size_t i = 0; i < request.bb_count; ++i) {
            const auto a = static_cast<std::uint8_t>(t.decimal(51, Failure::invalid_range));
            const auto b = static_cast<std::uint8_t>(t.decimal(51, Failure::invalid_range));
            bb.push_back(WeightedHand{Hand{a,b}, read_hex64(t.next())});
        }
        std::vector<double> reach;
        Integer qn = 1, qd = 1;
        t.expect("query"); const auto query = t.next();
        if (query == "PREFIX") {
            t.expect("prefix"); (void)t.next(); (void)t.decimal(5, Failure::invalid_query);
            for (std::size_t i=0;i<request.prefix_length;++i) (void)t.decimal(51, Failure::invalid_query);
        } else {
            t.expect("terminal"); (void)t.next(); (void)t.decimal(1, Failure::invalid_query); (void)t.next();
            (void)t.next();
            if (observer) observer->proposal_integer_parse_calls += 2;
            qn=parse_hex_integer(t.next()); qd=parse_hex_integer(t.next());
            (void)t.decimal(1326,Failure::invalid_query);
            if (observer) ++observer->reach_vector_allocation_sites;
            reach.reserve(request.reach_count);
            for (std::size_t i=0;i<request.reach_count;++i)
                reach.push_back(std::bit_cast<double>(read_hex64(t.next())));
            for (int i=0;i<5;++i) (void)t.decimal(51, Failure::invalid_query);
        }
        if (!t.done()) throw ParseError(Failure::invalid_request,"trailing request tokens");
        if (observer) ++observer->kernel_constructor_calls;
        PublicChanceKernel kernel(std::span<const WeightedHand>(sb), std::span<const WeightedHand>(bb),
                                  request.deck, request.limits);
        std::ostringstream out;
        out << "OPENPOKER_FULL_DECK_PUBLIC_CHANCE_RESULT_V1\n" << "deck_size " << kernel.deck_size()
            << "\ndeck_mode " << (kernel.deck_mode()==DeckMode::full52 ? "FULL52" : "REDUCED")
            << "\nnormalizer_hex " << hex_integer(kernel.normalizer_integer()) << "\nweight_denominator_exponents "
            << kernel.weight_denominator_exponents()[0] << ' ' << kernel.weight_denominator_exponents()[1] << '\n'
            << "probe_receipt " << line.size() << ' ' << request.input_tokens << ' '
            << request.parse_work_upper << ' ' << request.output_bytes_upper << '\n'
            << "probe_ownership " << request.ownership_entries_upper << ' '
            << request.ownership_payload_bits_upper << '\n';
        if (!request.terminal) {
            const auto result = kernel.prefix(std::span<const std::uint8_t>(request.cards.data(),request.prefix_length));
            out << "prefix " << request.prefix_length << "\ndenominator_hex " << hex_integer(result.denominator)
                << "\ntotal_numerator_hex " << hex_integer(result.total_numerator) << '\n';
            for (std::size_t side=0; side<2; ++side) {
                out << "side " << side << ' ' << result.hand_masses[side].numerators.size() << '\n';
                for (std::size_t i=0;i<result.hand_masses[side].numerators.size();++i) {
                    append_value(out,result.hand_masses[side].numerators[i]);
                    out << ' ' << (result.physical_support[side][i] ? 1 : 0) << '\n';
                }
            }
            if (request.convert) {
                const auto sb_values=kernel.binary64(result.hand_masses[0]);
                const auto bb_values=kernel.binary64(result.hand_masses[1]);
                out << "binary64_bits " << sb_values.size()+bb_values.size() << '\n';
                for (const auto value:sb_values) out << std::hex << std::setw(16) << std::setfill('0')
                    << std::bit_cast<std::uint64_t>(value) << std::dec << '\n';
                for (const auto value:bb_values) out << std::hex << std::setw(16) << std::setfill('0')
                    << std::bit_cast<std::uint64_t>(value) << std::dec << '\n';
            }
        } else {
            const auto payoff=std::bit_cast<double>(request.payoff_bits);
            const auto result=kernel.terminal(request.player,request.cards,request.kind,payoff,reach,qn,qd);
            out << "terminal " << request.player << ' ' << result.numerators.size() << "\ndenominator_hex "
                << hex_integer(result.denominator) << '\n';
            for (const auto& value:result.numerators) { append_value(out,value); out << '\n'; }
            if (request.convert) {
                const auto values=kernel.binary64(result);
                out << "binary64_bits " << values.size() << '\n';
                for (const auto value:values) out << std::hex << std::setw(16) << std::setfill('0')
                    << std::bit_cast<std::uint64_t>(value) << std::dec << '\n';
            }
        }
        append_receipt(out,kernel);
        auto response=out.str();
        if (response.size()>kMaximumResponseBytes) return "ERR response_too_large\n";
        return response;
    } catch (const KernelError& error) { return std::string("ERR ")+error_name(error.code())+'\n'; }
      catch (const ParseError& error) { return std::string("ERR ")+parse_error_name(error.code())+'\n'; }
      catch (const std::exception&) { return "ERR invalid_request\n"; }
}
} // namespace

int main() {
    std::string line;
    std::size_t records = 0;
    for (;;) {
        const auto status = read_line(std::cin,line);
        if (status==ReadStatus::end) return 0;
        if (status==ReadStatus::too_large) { std::cout << "ERR request_too_large\n"; return 2; }
        if (++records>kMaximumRecords) { std::cout << "ERR record_limit\n"; return 3; }
        std::cout << process(line);
        if (!std::cout) return 4;
    }
}
