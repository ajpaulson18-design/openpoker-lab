// Project-owned bounded vector conformance driver. Not a poker solver backend.
#include "exact_selected_kernel.hpp"
#include <charconv>
#include <iomanip>
#include <iostream>
#include <string>
#include <string_view>

namespace {
namespace kernel = openpoker::exact_selected_kernel;
constexpr std::size_t maximum_input = 8U << 20;
constexpr std::size_t maximum_queries = 256;
constexpr std::size_t maximum_values = 2'000'000;

void need(bool condition, const char* message) {
    if (!condition) throw std::invalid_argument(message);
}

class Parser {
public:
    explicit Parser(std::string text) : text_(std::move(text)) {}
    std::string_view token() {
        while (position_ < text_.size() && (text_[position_] == ' ' || text_[position_] == '\n' || text_[position_] == '\r' || text_[position_] == '\t')) ++position_;
        const auto start = position_;
        while (position_ < text_.size() && text_[position_] != ' ' && text_[position_] != '\n' && text_[position_] != '\r' && text_[position_] != '\t') ++position_;
        need(position_ > start && position_ - start <= 64, "missing/oversized token");
        return std::string_view(text_).substr(start, position_ - start);
    }
    std::uint64_t number(std::uint64_t maximum, int base = 10) {
        const auto value = token();
        need(base != 16 || value.size() == 16, "binary64 bits require sixteen hex digits");
        std::uint64_t result = 0;
        const auto parsed = std::from_chars(value.data(), value.data() + value.size(), result, base);
        need(parsed.ec == std::errc{} && parsed.ptr == value.data() + value.size() && result <= maximum, "invalid/capped unsigned integer");
        return result;
    }
    std::size_t size(std::size_t maximum) { return static_cast<std::size_t>(number(maximum)); }
    double binary64() { return std::bit_cast<double>(number(UINT64_MAX, 16)); }
    void finish() {
        while (position_ < text_.size()) {
            const auto c = text_[position_++];
            need(c == ' ' || c == '\n' || c == '\r' || c == '\t', "trailing request bytes");
        }
    }
private:
    std::string text_;
    std::size_t position_ = 0;
};

struct Query {
    char kind = 'M';
    std::size_t player = 0;
    std::vector<std::size_t> indexes;
    double payoff = 0;
    std::vector<double> reach;
};

void values(const std::vector<double>& row) {
    for (double value : row) std::cout << '\t' << std::hex << std::setw(16) << std::setfill('0')
        << std::bit_cast<std::uint64_t>(value) << std::dec;
    std::cout << '\n';
}

int run() {
    std::string input;
    input.reserve(4096);
    for (int c; (c = std::cin.get()) != std::char_traits<char>::eof();) {
        need(input.size() < maximum_input && c > 0 && c <= 127, "input byte/encoding cap");
        input.push_back(static_cast<char>(c));
    }
    Parser parser(std::move(input));
    need(parser.token() == "OPENPOKER_EXACT_SELECTED_VECTORS_V1", "unsupported vector protocol");
    const std::array<std::size_t, 2> count{parser.size(1326), parser.size(1326)};
    const auto board_count = parser.size(64), cache = parser.size(64), query_count = parser.size(maximum_queries);
    need(count[0] && count[1] && board_count && cache && query_count, "zero request dimension");
    need(query_count * (count[0] + count[1]) <= maximum_values, "query/output entry cap");
    kernel::Limits limits;
    limits.max_hands_per_side = parser.size(1326);
    limits.max_boards = parser.size(64);
    limits.max_integer_bits = parser.size(65536);
    limits.max_modeled_work = parser.number(500'000'000);
    limits.max_storage_entries = parser.size(2'000'000);
    limits.max_integer_payload_bits = parser.size(1U << 30);
    std::array<std::vector<kernel::WeightedHand>, 2> hands;
    for (std::size_t side = 0; side < 2; ++side) {
        hands[side].reserve(count[side]);
        for (std::size_t i = 0; i < count[side]; ++i) {
            kernel::WeightedHand hand;
            hand.hand.first = static_cast<std::uint8_t>(parser.size(51));
            hand.hand.second = static_cast<std::uint8_t>(parser.size(51));
            hand.binary64_weight_bits = parser.number(UINT64_MAX, 16);
            hands[side].push_back(hand);
        }
    }
    std::vector<kernel::SelectedBoard> boards(board_count);
    for (auto& board : boards) for (auto& card : board.cards) card = static_cast<std::uint8_t>(parser.size(51));
    std::vector<Query> queries;
    queries.reserve(query_count);
    for (std::size_t i = 0; i < query_count; ++i) {
        Query query;
        const auto kind = parser.token();
        need(kind.size() == 1 && (kind == "M" || kind == "S" || kind == "F" || kind == "D"), "invalid query kind");
        query.kind = kind[0];
        query.player = parser.size(1);
        const auto length = parser.size(board_count);
        query.indexes.reserve(length);
        std::array<bool, 64> seen{};
        for (std::size_t j = 0; j < length; ++j) {
            const auto index = parser.size(board_count - 1);
            need(!seen[index], "duplicate query board index");
            seen[index] = true;
            query.indexes.push_back(index);
        }
        if (query.kind == 'F' || query.kind == 'D') {
            query.payoff = parser.binary64();
            query.reach.reserve(count[1 - query.player]);
            for (std::size_t j = 0; j < count[1 - query.player]; ++j) query.reach.push_back(parser.binary64());
        }
        queries.push_back(std::move(query));
    }
    parser.finish();
    kernel::ExactSelectedKernel engine(std::move(hands[0]), std::move(hands[1]), std::move(boards), cache, limits);
    const auto exponents = engine.seat_weight_exponents();
    std::cout << "READY\tOPENPOKER_EXACT_SELECTED_VECTORS_V1\nZ\t" << engine.normalizer_hex()
        << '\t' << exponents[0] << '\t' << exponents[1] << '\n';
    for (std::size_t i = 0; i < queries.size(); ++i) {
        const auto& query = queries[i];
        if (query.kind == 'M') {
            const auto result = engine.marginals(query.indexes);
            for (std::size_t p = 0; p < 2; ++p) { std::cout << "M\t" << i << '\t' << p; values(result[p]); }
        } else if (query.kind == 'S') {
            const auto result = engine.support(query.indexes);
            for (std::size_t p = 0; p < 2; ++p) {
                std::cout << "S\t" << i << '\t' << p;
                for (bool value : result[p]) std::cout << '\t' << (value ? 1 : 0);
                std::cout << '\n';
            }
        } else {
            const auto result = engine.terminal(query.player, query.indexes,
                query.kind == 'F' ? kernel::TerminalKind::fold : kernel::TerminalKind::showdown,
                query.payoff, query.reach);
            std::cout << query.kind << '\t' << i << '\t' << query.player; values(result);
        }
    }
    const auto& r = engine.receipt();
    std::cout << "COUNTS\t" << r.modeled_work << '\t' << r.retained_entries << '\t' << r.peak_scratch_entries
        << '\t' << r.peak_integer_bits << '\t' << r.rank_calls << '\t' << r.rank_cache_hits
        << '\t' << r.rank_cache_misses << '\t' << r.rank_cache_evictions << '\t' << r.conversion_calls
        << '\t' << r.peak_integer_payload_bits << '\t' << r.peak_conversion_scratch_bits << '\n';
    return 0;
}
} // namespace

int main() {
    try { return run(); }
    catch (const kernel::KernelError& error) { std::cout << "ERR\tkernel\t" << static_cast<int>(error.code()) << '\t' << error.what() << '\n'; }
    catch (const std::exception& error) { std::cout << "ERR\tinput\t" << error.what() << '\n'; }
    return 2;
}
