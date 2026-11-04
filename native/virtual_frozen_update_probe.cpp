// Explicit PROOF9/v1 conformance transport. No RNG, training or solver fallback.
#include "virtual_frozen_update.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

namespace {
namespace v = openpoker::virtual_frozen_update;
namespace c = openpoker::full_deck_public_chance;
namespace b = openpoker::virtual_betting_template;
constexpr std::size_t kLineBytes = 1024, kRecords = 8192, kIntegerBits = 384;
constexpr std::uint64_t kRows = 868, kSlots = 2078, kDepth = 15;
constexpr std::uint64_t kIntegerFields = 2 * kSlots + 2 * kRows + 1;
// Framing/strings and every signed hex integer are reserved before game setup.
constexpr std::uint64_t kOutputBytes = 16384 + 256 * kRows +
    kRows * kDepth * (64 + 16) + 128 * kSlots + kIntegerFields * (kIntegerBits / 4 + 4);
constexpr std::size_t kInputEntries = 512;
static_assert(kOutputBytes < 64ULL * 1024 * 1024);

class Failure final : public std::runtime_error {
public:
    explicit Failure(const char* text) : std::runtime_error(text) {}
};

class Tokens final {
    std::string_view source_;
    std::size_t position_ = 0, count_ = 0;
public:
    explicit Tokens(std::string_view source) : source_(source) {}
    std::string_view next() {
        while (position_ < source_.size() && (source_[position_] == ' ' || source_[position_] == '\t' || source_[position_] == '\r')) ++position_;
        const auto begin = position_;
        while (position_ < source_.size() && source_[position_] != ' ' && source_[position_] != '\t' && source_[position_] != '\r') ++position_;
        if (begin == position_ || ++count_ > 16) throw Failure("invalid probe token count");
        return source_.substr(begin, position_ - begin);
    }
    std::uint64_t number(std::uint64_t ceiling) {
        const auto text = next();
        std::uint64_t value = 0;
        const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
        if (text.empty() || text.size() > 20 || result.ec != std::errc{} || result.ptr != text.data() + text.size() || value > ceiling)
            throw Failure("probe integer outside declared bounds");
        return value;
    }
    bool done() {
        while (position_ < source_.size() && (source_[position_] == ' ' || source_[position_] == '\t' || source_[position_] == '\r')) ++position_;
        return position_ == source_.size();
    }
};

class Output final {
    std::string data_;
public:
    Output() { data_.reserve(static_cast<std::size_t>(kOutputBytes)); }
    void text(std::string_view text) {
        if (text.size() > kOutputBytes - data_.size()) throw Failure("probe response byte forecast exceeded");
        data_.append(text);
    }
    void number(std::uint64_t value) {
        std::array<char, 32> buffer{};
        const auto result = std::to_chars(buffer.data(), buffer.data() + buffer.size(), value);
        if (result.ec != std::errc{}) throw Failure("probe integer framing failure");
        text(std::string_view(buffer.data(), static_cast<std::size_t>(result.ptr - buffer.data())));
    }
    void field(std::uint64_t value) { text(" "); number(value); }
    void integer(const v::CommonInteger& value) {
        // Read signed-magnitude limbs directly: no arbitrary-width temporary or
        // opaque decimal conversion is hidden in the boundary's numeric model.
        const auto width = openpoker::exact_binary64::detail::magnitude_bits(
            value, kIntegerBits, openpoker::exact_binary64::ErrorCode::input_bit_limit);
        if (!width) { text("0"); return; }
        const auto& backend = value.backend();
        using Limb = std::remove_cv_t<std::remove_reference_t<decltype(backend.limbs()[0])>>;
        constexpr std::size_t limb_bits = std::numeric_limits<Limb>::digits;
        static_assert(limb_bits % 4 == 0);
        if (backend.sign()) text("-");
        constexpr std::string_view alphabet = "0123456789abcdef";
        for (std::size_t i = (width + 3) / 4; i > 0; --i) {
            const auto offset = 4 * (i - 1);
            const auto digit = static_cast<std::size_t>((backend.limbs()[offset / limb_bits] >> (offset % limb_bits)) & Limb{15});
            text(alphabet.substr(digit, 1));
        }
    }
    std::string finish() { return std::move(data_); }
};

b::Config config() {
    b::Config result;
    result.stacks = {8., 8.}; result.sb = .5; result.bb = 1.;
    result.stages[0].bets = {.5}; result.stages[0].raises = {1.};
    result.stages[0].max_raises = 1; result.stages[0].all_in = true;
    for (std::size_t stage = 1; stage < 4; ++stage) {
        result.stages[stage].bets = {.5, 1.}; result.stages[stage].raises = {.25};
        result.stages[stage].max_raises = 1; result.stages[stage].all_in = true;
    }
    return result;
}

void forecast(Output& out, const v::FrozenUpdateForecast& f) {
    out.text("forecast");
    for (auto value : std::array<std::uint64_t, 17>{f.admitted ? 1ULL : 0ULL,
         f.work_upper, f.chance_work_upper, f.history_work_upper, f.arithmetic_work_upper,
         f.average_work_upper, f.rows_upper, f.slots_upper, f.edge_occurrences,
         f.token_bytes, f.terminal_occurrences, f.integer_bits_upper,
         f.integer_payload_bits_upper, f.entries_upper, f.reach_exponent_upper,
         f.row_history_tokens_upper, f.retained_text_bytes_upper}) out.field(value);
    out.text("\n");
}

std::string process(std::string_view line) {
    try {
        Tokens input(line);
        if (input.next() != "FROZEN_UPDATE_V1") throw Failure("unsupported proof protocol");
        const auto mode = input.next();
        if (mode != "ADMIT" && mode != "EVAL") throw Failure("unsupported proof mode");
        const auto proposal = input.next();
        if (proposal != "UNIFORM" && proposal != "RIVER_WEIGHTED") throw Failure("unsupported proof proposal");
        const auto kind = proposal == "UNIFORM" ? v::ProposalKind::uniform_public : v::ProposalKind::weighted_river_proof9;
        std::array<std::uint8_t, 5> board{};
        for (auto& card : board) card = static_cast<std::uint8_t>(input.number(51));
        v::FrozenGameLimits requested;
        requested.work = input.number(500000000);
        requested.entries = static_cast<std::size_t>(input.number(2000000));
        requested.integer_bits = static_cast<std::size_t>(input.number(65536));
        requested.integer_payload_bits = static_cast<std::size_t>(input.number(std::uint64_t{1} << 30));
        if (!input.done()) throw Failure("trailing proof tokens");
        if (!requested.work || !requested.entries || !requested.integer_bits || !requested.integer_payload_bits)
            throw Failure("zero probe limit");
        const std::uint64_t transport_work = 16384 + 16 * line.size() + 16 * kOutputBytes;
        if (transport_work >= requested.work || kInputEntries >= requested.entries)
            throw Failure("probe transport admission exceeded");
        auto limits = requested;
        limits.work -= transport_work; limits.entries -= kInputEntries;
        limits.integer_bits = std::min(limits.integer_bits, kIntegerBits);
        limits.max_hands_per_side = 2;
        constexpr std::array<std::uint8_t, 9> cards{16,17,24,32,33,35,37,43,48};
        const auto deck = c::DeckDefinition::reduced(cards);
        // Reject invalid boards before owned setup; the owned proposal repeats
        // validation as part of the mathematical request.
        (void)v::proposal_for(deck, board, kind);
        const std::array<c::WeightedHand, 2> sb{{{{43,48}, std::bit_cast<std::uint64_t>(.125)},
                                               {{32,43}, std::bit_cast<std::uint64_t>(.75)}}};
        const std::array<c::WeightedHand, 2> bb{{{{24,37}, std::bit_cast<std::uint64_t>(.375)},
                                               {{16,32}, std::bit_cast<std::uint64_t>(1.)}}};
        v::FrozenGame game(config(), deck, sb, bb, limits);
        const auto& shape = game.template_receipt();
        if (shape.nodes != 388 || shape.edges != 410 || shape.logical_occurrences != 1105 || shape.max_depth != 15)
            throw Failure("pinned v1 betting geometry changed");
        v::FrozenUpdateForecast f;
        v::FrozenUpdateStage stage;
        if (mode == "EVAL") { stage = v::FrozenUpdate::run(game, board, kind); f = stage.forecast; }
        else f = v::FrozenUpdate::forecast(game, board, kind);
        if (f.rows_upper > kRows || f.slots_upper > kSlots || f.integer_bits_upper > kIntegerBits)
            throw Failure("pinned proof response geometry changed");
        Output out;
        out.text("FROZEN_UPDATE_RESULT_V1\nmode "); out.text(mode);
        out.text("\nstatus "); out.text(mode == "EVAL" ? "COMPLETE" : (f.admitted ? "ADMITTED" : "REJECTED"));
        out.text("\nscope PROOF9_FULL_V1\nproposal "); out.text(proposal);
        out.text("\nboard"); for (auto card : board) out.field(card);
        out.text("\nprobe"); out.field(line.size()); out.field(kOutputBytes);
        out.field(transport_work); out.field(kInputEntries); out.field(limits.integer_bits); out.text("\n");
        forecast(out, f);
        const auto& setup = game.setup_receipt();
        out.text("setup"); out.field(setup.work); out.field(setup.retained_entries_upper);
        out.field(setup.peak_setup_entries_upper); out.field(setup.peak_setup_integer_bits_upper);
        out.field(setup.peak_setup_integer_payload_bits_upper); out.text("\n");
        const auto& calls = game.chance_receipt();
        out.text("calls"); out.field(calls.prefix_queries); out.field(calls.terminal_queries);
        out.field(calls.rank_calls); out.field(calls.conversion_calls); out.text("\n");
        if (mode == "EVAL") {
            out.text("actual"); out.field(stage.chance_work); out.field(stage.history_work);
            out.field(stage.common_regret_work); out.field(stage.average_work); out.text("\nregret_denominator ");
            out.integer(stage.regret_denominator); out.text("\nrows"); out.field(stage.rows.size()); out.text("\n");
            for (std::size_t index = 0; index < stage.rows.size(); ++index) {
                const auto& row = stage.rows[index];
                const auto count = row.actions.size();
                if (row.history.size() > kDepth || !count || count > 4 || row.policy_exponents.size() != count ||
                    row.regret_numerators.size() != count || row.average_numerators.size() != count)
                    throw Failure("invalid staged proof row shape");
                out.text("row"); out.field(index); out.field(row.actor); out.field(row.first); out.field(row.second);
                out.field(row.history.size()); out.field(count); out.text("\n");
                for (const auto& token : row.history) {
                    if (token.empty() || token.size() > 64) throw Failure("invalid staged history token");
                    out.text("token "); out.text(token); out.text("\n");
                }
                out.text("average "); out.integer(row.average_denominator); out.text(" ");
                out.integer(row.average_mass_numerator); out.text("\n");
                for (std::size_t action = 0; action < count; ++action) {
                    if (row.actions[action].empty() || row.actions[action].size() > 64 ||
                        row.policy_exponents[action] < -1 || row.policy_exponents[action] > 19)
                        throw Failure("invalid staged action");
                    out.text("action"); out.field(action); out.text(" ");
                    if (row.policy_exponents[action] < 0) out.text("-1");
                    else out.number(static_cast<std::uint64_t>(row.policy_exponents[action]));
                    out.text(" "); out.text(row.actions[action]); out.text(" ");
                    out.integer(row.regret_numerators[action]); out.text(" "); out.integer(row.average_numerators[action]); out.text("\n");
                }
                out.text("endrow\n");
            }
        } else out.text("rows 0\n");
        out.text("end\n");
        return out.finish();
    } catch (const std::exception& error) {
        std::string reason;
        for (const unsigned char byte : std::string_view(error.what()).substr(0, 256))
            reason.push_back(byte >= 32 && byte <= 126 ? static_cast<char>(byte) : '?');
        return "FROZEN_UPDATE_ERROR_V1\nreason " + reason + "\nend\n";
    }
}
} // namespace

int main() {
#ifdef _WIN32
    // Preserve the exact framing-byte bound instead of CRT newline expansion.
    if (_setmode(_fileno(stdin), _O_BINARY) == -1 ||
        _setmode(_fileno(stdout), _O_BINARY) == -1) return 5;
#endif
    std::string line;
    std::size_t records = 0;
    for (;;) {
        line.clear(); int value;
        while ((value = std::cin.get()) != EOF && value != '\n') {
            if (line.size() == kLineBytes) { std::cout << "FROZEN_UPDATE_ERROR_V1\nreason request frame exceeded\nend\n"; return 2; }
            line.push_back(static_cast<char>(value));
        }
        if (value == EOF && line.empty()) return 0;
        if (++records > kRecords) { std::cout << "FROZEN_UPDATE_ERROR_V1\nreason record frame exceeded\nend\n"; return 3; }
        const auto response = process(line);
        std::cout.write(response.data(), static_cast<std::streamsize>(response.size()));
        if (!std::cout) return 4;
    }
}
