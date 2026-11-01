#include "virtual_betting_template.hpp"
#include <array>
#include <bit>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <string_view>

namespace {
namespace v = openpoker::virtual_betting_template;
constexpr std::size_t kMaxLine = 16384, kMaxOutput = 64 * 1024 * 1024;
struct Failure : std::runtime_error {
    using std::runtime_error::runtime_error;
};
class Tokens {
    std::string_view text_;
    std::size_t pos_ = 0, count_ = 0;

  public:
    explicit Tokens(std::string_view text) : text_(text) {}
    std::string_view next() {
        while (pos_ < text_.size() &&
               (text_[pos_] == ' ' || text_[pos_] == '\t' || text_[pos_] == '\r'))
            ++pos_;
        auto begin = pos_;
        while (pos_ < text_.size() && text_[pos_] != ' ' && text_[pos_] != '\t' &&
               text_[pos_] != '\r')
            ++pos_;
        if (begin == pos_ || ++count_ > 512)
            throw Failure("invalid token");
        return text_.substr(begin, pos_ - begin);
    }
    void expect(std::string_view s) {
        if (next() != s)
            throw Failure("unexpected token");
    }
    std::uint64_t decimal(std::uint64_t max) {
        const auto x = next();
        if (x.empty() || x.size() > 20)
            throw Failure("integer width");
        std::uint64_t n = 0;
        for (char c : x) {
            if (c < '0' || c > '9' || n > (UINT64_MAX - static_cast<unsigned>(c - '0')) / 10)
                throw Failure("integer value");
            n = n * 10 + static_cast<unsigned>(c - '0');
            if (n > max)
                throw Failure("integer cap");
        }
        return n;
    }
    double number() {
        const auto x = next();
        if (x.size() != 16)
            throw Failure("number width");
        std::uint64_t n = 0;
        for (char c : x) {
            const int d = c >= '0' && c <= '9'
                              ? c - '0'
                              : (c >= 'a' && c <= 'f' ? c - 'a' + 10
                                                      : (c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1));
            if (d < 0)
                throw Failure("number hex");
            n = (n << 4) | static_cast<unsigned>(d);
        }
        return std::bit_cast<double>(n);
    }
    bool done() {
        while (pos_ < text_.size() &&
               (text_[pos_] == ' ' || text_[pos_] == '\t' || text_[pos_] == '\r'))
            ++pos_;
        return pos_ == text_.size();
    }
    std::size_t count() const { return count_; }
};
struct RawStage {
    std::array<double, 8> bets{}, raises{};
    std::size_t nb = 0, nr = 0;
    unsigned max = 0;
    bool allin = false;
};
void bits(std::ostream &out, double x) {
    out << std::hex << std::setw(16) << std::setfill('0') << std::bit_cast<std::uint64_t>(x)
        << std::dec << std::setfill(' ');
}
std::string process(const std::string &line) {
    try {
        Tokens t(line);
        t.expect("VIRTUAL_BETTING_V1");
        auto mode = t.next();
        if (mode != "BUILD" && mode != "STATE")
            throw Failure("mode");
        t.expect("limits");
        v::Limits limits;
        limits.nodes = static_cast<std::size_t>(t.decimal(250000));
        limits.edges = static_cast<std::size_t>(t.decimal(1000000));
        limits.work = t.decimal(500000000);
        limits.entries = static_cast<std::size_t>(t.decimal(2000000));
        limits.occurrences = t.decimal(1000000000000ULL);
        limits.depth = static_cast<std::size_t>(t.decimal(64));
        if (!limits.nodes || !limits.edges || !limits.work || !limits.entries ||
            !limits.occurrences || !limits.depth)
            throw Failure("zero limit");
        t.expect("config");
        const std::array<double, 2> stacks{t.number(), t.number()};
        const double sb = t.number(), bb = t.number();
        const bool initial_empty = t.decimal(1) != 0;
        std::array<RawStage, 4> raw{};
        const std::array<unsigned, 4> streets{0, 3, 4, 5};
        for (std::size_t i = 0; i < 4; ++i) {
            t.expect("stage");
            if (t.decimal(5) != streets[i])
                throw Failure("stage order");
            raw[i].nb = static_cast<std::size_t>(t.decimal(8));
            for (std::size_t j = 0; j < raw[i].nb; ++j)
                raw[i].bets[j] = t.number();
            raw[i].nr = static_cast<std::size_t>(t.decimal(8));
            for (std::size_t j = 0; j < raw[i].nr; ++j)
                raw[i].raises[j] = t.number();
            raw[i].max = static_cast<unsigned>(t.decimal(8));
            raw[i].allin = t.decimal(1) != 0;
        }
        v::State state;
        if (mode == "STATE") {
            t.expect("state");
            state.phase = static_cast<v::Phase>(t.decimal(3));
            state.street = static_cast<std::uint8_t>(t.decimal(5));
            state.actor = static_cast<std::uint8_t>(t.decimal(1));
            state.committed = {t.number(), t.number()};
            state.increment = t.number();
            state.raises = static_cast<unsigned>(t.decimal(8));
            state.reopened = t.decimal(1) != 0;
            state.checks = static_cast<unsigned>(t.decimal(1));
            state.origin_present = t.decimal(1) != 0;
            state.origin = t.number();
            state.boundary_pot = t.number();
            state.local_present = t.decimal(1) != 0;
            state.local = {t.number(), t.number()};
            state.history_empty = t.decimal(1) != 0;
            // STATE represents a decision; explicit reveal/terminal inspection is via BUILD nodes.
            if (state.phase != v::Phase::decision)
                throw Failure("state must be decision");
        }
        if (!t.done())
            throw Failure("trailing tokens");
        const std::uint64_t out_upper = 4096ULL + 768ULL * limits.nodes + 192ULL * limits.edges;
        if (out_upper > kMaxOutput)
            throw Failure("response capacity");
        const std::uint64_t transport = 8ULL * line.size() + 32ULL * t.count() + 8ULL * out_upper;
        if (transport >= limits.work)
            throw Failure("transport work limit");
        constexpr std::size_t owned = 256;
        if (owned >= limits.entries)
            throw Failure("transport entries limit");
        limits.work -= transport;
        limits.entries -= owned;
        v::Config config;
        config.stacks = stacks;
        config.sb = sb;
        config.bb = bb;
        config.initial_history_empty = initial_empty;
        for (std::size_t i = 0; i < 4; ++i) {
            config.stages[i].bets.assign(raw[i].bets.begin(), raw[i].bets.begin() + raw[i].nb);
            config.stages[i].raises.assign(raw[i].raises.begin(),
                                           raw[i].raises.begin() + raw[i].nr);
            config.stages[i].max_raises = raw[i].max;
            config.stages[i].all_in = raw[i].allin;
        }
        const v::Template result(config, limits, mode == "STATE" ? &state : nullptr);
        const auto &rec = result.receipt();
        std::ostringstream out;
        out << "VIRTUAL_BETTING_RESULT_V1\nroot " << result.root() << "\nreceipt " << rec.nodes
            << ' ' << rec.edges << ' ' << rec.work << ' ' << rec.entries << ' '
            << rec.peak_scratch_entries << ' ' << rec.logical_occurrences << ' ' << rec.max_depth
            << "\ntransport " << line.size() << ' ' << out_upper << ' ' << transport << ' ' << owned
            << '\n';
        out << "history_scope " << (rec.history_suffix_only ? "suffix-only" : "empty-root") << '\n';
        for (std::size_t k = 0; k < 4; ++k)
            out << "street " << streets[k] << ' ' << rec.decisions[k][0] << ' '
                << rec.decisions[k][1] << ' ' << rec.reveals[k] << ' ' << rec.folds[k] << ' '
                << rec.showdowns[k] << ' ' << rec.action_slots[k] << '\n';
        for (std::size_t i = 0; i < result.nodes().size(); ++i) {
            const auto &n = result.nodes()[i];
            const auto &s = n.state;
            const auto &h = result.histories()[i];
            out << "node " << i << ' ' << static_cast<unsigned>(s.phase) << ' '
                << static_cast<unsigned>(s.street) << ' ' << static_cast<unsigned>(s.actor) << ' '
                << static_cast<unsigned>(s.next_street) << ' ' << static_cast<unsigned>(s.winner)
                << ' ';
            bits(out, s.committed[0]);
            out << ' ';
            bits(out, s.committed[1]);
            out << ' ';
            bits(out, s.increment);
            out << ' ' << s.raises << ' ' << s.reopened << ' ' << s.checks << ' '
                << s.origin_present << ' ';
            bits(out, s.origin);
            out << ' ';
            bits(out, s.boundary_pot);
            out << ' ' << s.local_present << ' ';
            bits(out, s.local[0]);
            out << ' ';
            bits(out, s.local[1]);
            out << ' ' << s.history_empty << ' ';
            bits(out, std::min(s.committed[0], s.committed[1]));
            out << ' ' << n.edges.size();
            for (auto x : h)
                out << ' ' << x;
            out << '\n';
            for (std::size_t j = 0; j < n.edges.size(); ++j) {
                const auto &e = n.edges[j];
                out << "edge " << i << ' ' << j << ' '
                    << (s.phase == v::Phase::reveal ? "reveal" : v::name(e.action.kind)) << ' ';
                bits(out, e.action.amount);
                out << ' ';
                bits(out, e.action.target);
                out << ' ';
                bits(out, e.action.local_target);
                out << ' ' << e.action.has_local_target << ' ' << e.action.full_raise << ' '
                    << (e.action.token.empty() ? "-" : e.action.token) << ' ' << e.child << '\n';
            }
        }
        auto text = out.str();
        if (text.size() > out_upper)
            throw Failure("response forecast invariant");
        return text;
    } catch (const std::exception &e) {
        return std::string("ERR ") + e.what() + "\n";
    }
}
}
int main() {
    std::string line;
    std::size_t records = 0;
    for (;;) {
        line.clear();
        int c;
        while ((c = std::cin.get()) != EOF && c != '\n') {
            if (line.size() == kMaxLine) {
                std::cout << "ERR request capacity\n";
                return 2;
            }
            line.push_back(static_cast<char>(c));
        }
        if (c == EOF && line.empty())
            return 0;
        if (++records > 256) {
            std::cout << "ERR record capacity\n";
            return 3;
        }
        std::cout << process(line);
        if (!std::cout)
            return 4;
    }
}
