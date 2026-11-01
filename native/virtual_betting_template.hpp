#pragma once
// Card-free immutable betting continuation DAG. Node identity is NOT infoset identity.
#include "exact_selected_kernel.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <map>
#include <numeric>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace openpoker::virtual_betting_template {
using Integer = exact_binary64::Integer;
namespace dyadic = exact_selected_kernel::detail;
constexpr double EPS = 1e-9;
enum class Phase : std::uint8_t { decision = 0, reveal = 1, fold = 2, showdown = 3 };
enum class ActionKind : std::uint8_t {
    fold = 0,
    call = 1,
    check = 2,
    bet = 3,
    raise = 4,
    all_in = 5
};
struct Stage {
    std::vector<double> bets, raises;
    unsigned max_raises = 0;
    bool all_in = false;
};
struct Config {
    std::array<double, 2> stacks{100, 100};
    double sb = .5, bb = 1.;
    std::array<Stage, 4> stages;
    bool initial_history_empty = true;
};
struct Limits {
    std::size_t nodes = 250000, edges = 1000000, entries = 2000000, depth = 64;
    std::uint64_t work = 500000000, occurrences = 1000000000000ULL;
};
struct State {
    Phase phase = Phase::decision;
    std::uint8_t street = 0, actor = 0, next_street = 0, winner = 2;
    std::array<double, 2> committed{};
    double increment = 0;
    unsigned raises = 0;
    bool reopened = true;
    unsigned checks = 0;
    bool origin_present = false;
    double origin = 0, boundary_pot = 0;
    bool local_present = false;
    std::array<double, 2> local{};
    bool history_empty = true;
    auto key() const {
        return std::tuple{phase,
                          street,
                          actor,
                          next_street,
                          winner,
                          std::bit_cast<std::uint64_t>(committed[0]),
                          std::bit_cast<std::uint64_t>(committed[1]),
                          std::bit_cast<std::uint64_t>(increment),
                          raises,
                          reopened,
                          checks,
                          origin_present,
                          std::bit_cast<std::uint64_t>(origin),
                          std::bit_cast<std::uint64_t>(boundary_pot),
                          local_present,
                          std::bit_cast<std::uint64_t>(local[0]),
                          std::bit_cast<std::uint64_t>(local[1]),
                          history_empty};
    }
    friend bool operator<(const State &a, const State &b) { return a.key() < b.key(); }
};
struct Action {
    ActionKind kind = ActionKind::check;
    double amount = 0, target = 0, local_target = 0;
    bool has_local_target = false, full_raise = false;
    std::string token;
};
struct Edge {
    Action action;
    std::size_t child = 0;
};
struct Node {
    State state;
    std::vector<Edge> edges;
};
struct Receipt {
    std::uint64_t work = 0, logical_occurrences = 0;
    std::size_t nodes = 0, edges = 0, entries = 0, peak_scratch_entries = 0, max_depth = 0;
    bool history_suffix_only = false;
    std::array<std::array<std::uint64_t, 2>, 4> decisions{};
    std::array<std::uint64_t, 4> reveals{}, folds{}, showdowns{}, action_slots{};
};
class Error : public std::runtime_error {
  public:
    explicit Error(const char *s) : std::runtime_error(s) {}
};
struct Meter {
    Limits limits;
    Receipt receipt;
    void work(std::uint64_t n) {
        if (n > limits.work - receipt.work)
            throw Error("template work limit exceeded");
        receipt.work += n;
    }
    void entries(std::size_t n) {
        if (n > limits.entries - receipt.entries ||
            receipt.peak_scratch_entries > limits.entries - receipt.entries - n)
            throw Error("template entries limit exceeded");
        receipt.entries += n;
    }
    void scratch(std::size_t n) {
        if (n > limits.entries - receipt.entries)
            throw Error("template scratch entries limit exceeded");
        receipt.peak_scratch_entries = std::max(receipt.peak_scratch_entries, n);
    }
};
inline std::size_t street_index(unsigned s) {
    switch (s) {
    case 0:
        return 0;
    case 3:
        return 1;
    case 4:
        return 2;
    case 5:
        return 3;
    default:
        throw Error("invalid street");
    }
}
inline std::uint64_t checked_add(std::uint64_t a, std::uint64_t b, std::uint64_t cap) {
    if (b > cap - a)
        throw Error("template occurrence limit exceeded");
    return a + b;
}

// Correctly rounded binary64 -> decimal 1e-9 grid -> binary64, ties-even.
// No intermediate floating multiply by 1e9. The largest scratch value is
// bounded by 1,200 bits for any finite binary64, before its construction.
inline std::pair<double, std::int64_t> money_with_units(double value, Meter &meter) {
    if (!std::isfinite(value) || std::abs(value) > 1'000'000.)
        throw Error("money outside supported bound");
    // Values below 2^-31 are strictly below half of a 1e-9 grid step.
    // This also prevents constructing a 1,075-bit denominator for subnormals.
    if (std::abs(value) < 0x1p-31) {
        meter.work(64);
        return {0., 0};
    }
    // Remaining inputs have exponent >= -83 and scaled significand <=83 bits:
    // 2*83*84 quotient/remainder width products + converter <=7028 + scans
    // fit 30,000 logical units. No CPU/allocator claim follows.
    meter.work(30000);
    meter.scratch(32);
    auto bits = std::bit_cast<std::uint64_t>(value);
    const bool neg = (bits >> 63) != 0;
    const auto parts = dyadic::decode_parts(bits, true, true, "invalid money bits");
    Integer scaled = Integer(parts.significand) * 1'000'000'000;
    Integer rounded;
    if (parts.exponent >= 0)
        rounded = scaled << static_cast<unsigned>(parts.exponent);
    else {
        const unsigned shift = static_cast<unsigned>(-parts.exponent);
        const Integer denom = Integer(1) << shift;
        rounded = scaled / denom;
        const Integer remainder = scaled % denom;
        const Integer other = denom - remainder;
        if (remainder > other || (remainder == other && static_cast<bool>(rounded & 1)))
            ++rounded;
    }
    if (neg)
        rounded = -rounded;
    const auto units = rounded.convert_to<std::int64_t>();
    try {
        const auto result = exact_binary64::convert(rounded, Integer(1'000'000'000),
                                                    exact_binary64::Limits{128, 181});
        if (result.receipt.modeled_work > 7028)
            throw Error("money conversion work forecast exceeded");
        return {result.value, units};
    } catch (const exact_binary64::ConversionError &) {
        throw Error("money conversion failed");
    }
}
inline double money(double x, Meter &m) { return money_with_units(x, m).first; }
inline const char *name(ActionKind k) {
    switch (k) {
    case ActionKind::fold:
        return "fold";
    case ActionKind::call:
        return "call";
    case ActionKind::check:
        return "check";
    case ActionKind::bet:
        return "bet";
    case ActionKind::raise:
        return "raise";
    case ActionKind::all_in:
        return "all_in";
    }
    throw Error("invalid action");
}
inline std::string token(ActionKind k, double target, Meter &m) {
    m.work(256);
    m.scratch(48);
    std::string s = name(k);
    if (k != ActionKind::bet && k != ActionKind::raise && k != ActionKind::all_in)
        return s;
    const auto u = money_with_units(target, m).second;
    if (u < 0)
        throw Error("negative action target");
    auto whole = std::to_string(u / 1000000000);
    auto fraction = std::to_string(u % 1000000000);
    fraction.insert(fraction.begin(), 9 - fraction.size(), '0');
    while (!fraction.empty() && fraction.back() == '0')
        fraction.pop_back();
    s += '@';
    s += whole;
    if (!fraction.empty()) {
        s += '.';
        s += fraction;
    }
    return s;
}
inline void validate_config(Config &c, const Limits &l, Meter &m) {
    if (!l.nodes || l.nodes > 250000 || !l.edges || l.edges > 1000000 || !l.entries ||
        l.entries > 2000000 || !l.depth || l.depth > 64 || !l.work || l.work > 500000000 ||
        !l.occurrences || l.occurrences > 1000000000000ULL)
        throw Error("invalid reduce-only limits");
    if (std::fegetround() != FE_TONEAREST)
        throw Error("nearest rounding required");
    m.work(4096);
    m.scratch(128);
    auto pos = [&](double x) { return std::isfinite(x) && x >= 1e-9 && x <= 1e6; };
    if (!pos(c.stacks[0]) || !pos(c.stacks[1]) || !pos(c.sb) || !pos(c.bb))
        throw Error("invalid stack or blinds");
    for (auto &x : c.stacks)
        x = money(x, m);
    c.sb = money(c.sb, m);
    c.bb = money(c.bb, m);
    // Binary64 1e-9 is the least representable value strictly above exact 1/1e9.
    if (c.stacks[0] <= 0 || c.stacks[1] <= 0 || c.sb >= c.bb || c.sb < EPS || c.bb - c.sb < EPS)
        throw Error("invalid rounded stack or blinds");
    for (std::size_t k = 0; k < 4; ++k) {
        auto &st = c.stages[k];
        if (st.bets.size() > 8 || st.raises.size() > 8 || st.max_raises > 8 ||
            (k && st.bets.empty()))
            throw Error("invalid stage sizes");
        for (auto x : st.bets)
            if (!pos(x))
                throw Error("invalid bet size");
        for (auto x : st.raises)
            if (!pos(x))
                throw Error("invalid raise size");
        std::sort(st.bets.begin(), st.bets.end());
        st.bets.erase(std::unique(st.bets.begin(), st.bets.end()), st.bets.end());
        std::sort(st.raises.begin(), st.raises.end());
        st.raises.erase(std::unique(st.raises.begin(), st.raises.end()), st.raises.end());
    }
}
inline void validate_state(const State &s) {
    (void)street_index(s.street);
    if (s.actor > 1 || s.raises > 8 || s.checks > 1 || s.winner > 2 ||
        (s.phase != Phase::decision && s.phase != Phase::reveal && s.phase != Phase::fold &&
         s.phase != Phase::showdown))
        throw Error("invalid betting state");
    if (s.phase == Phase::reveal) {
        const auto next = s.street == 0 ? 3 : (s.street == 3 ? 4 : (s.street == 4 ? 5 : 0));
        if (!next || s.next_street != next || s.winner != 2)
            throw Error("invalid reveal state");
    } else if (s.next_street != 0)
        throw Error("invalid next street");
    if (s.phase == Phase::fold) {
        if (s.winner != 1 - s.actor)
            throw Error("invalid fold winner");
    } else if (s.winner != 2)
        throw Error("invalid terminal winner");
    for (auto x : {s.committed[0], s.committed[1], s.increment, s.origin, s.boundary_pot,
                   s.local[0], s.local[1]})
        if (!std::isfinite(x) || x < 0 || x > 1000000 || std::signbit(x))
            throw Error("invalid state money");
    if (s.history_empty && s.street != 0)
        throw Error("empty history after preflop");
    if (!s.origin_present && (s.origin != 0 || s.boundary_pot != 0 || s.local_present))
        throw Error("invalid origin state");
    if (!s.local_present && (s.local[0] != 0 || s.local[1] != 0))
        throw Error("invalid local state");
    if (s.phase == Phase::decision && s.next_street != 0)
        throw Error("invalid decision state");
}
inline State initial(const Config &c, Meter &m) {
    State s;
    s.committed = {money(std::min(c.sb, c.stacks[0]), m), money(std::min(c.bb, c.stacks[1]), m)};
    s.increment = money(c.bb, m);
    s.history_empty = c.initial_history_empty;
    for (std::size_t p = 0; p < 2; ++p)
        if (s.committed[p] >= c.stacks[p] - EPS && s.committed[1 - p] >= s.committed[p] - EPS) {
            s.phase = Phase::showdown;
            s.winner = 2;
            break;
        }
    return s;
}
inline State settle(State s, const Config &c, Meter &m) {
    const double matched = std::min(s.committed[0], s.committed[1]);
    s.committed = {matched, matched};
    if (s.street == 5 || matched >= c.stacks[0] - EPS || matched >= c.stacks[1] - EPS) {
        s.phase = Phase::showdown;
        s.winner = 2;
        return s;
    }
    if (s.street == 0) {
        const auto origin = money(matched, m), pot = money(origin + origin, m);
        const auto a = money(c.stacks[0] - origin, m), b = money(c.stacks[1] - origin, m);
        if (pot < .01 || pot > 1e6 || a < .01 || a > 1e6 || b < .01 || b > 1e6)
            throw Error("invalid live continuation");
    }
    s.phase = Phase::reveal;
    s.next_street = s.street == 0 ? 3 : (s.street == 3 ? 4 : 5);
    return s;
}
inline State reveal(State s, Meter &m) {
    if (!s.origin_present) {
        s.origin = money(std::min(s.committed[0], s.committed[1]), m);
        s.origin_present = true;
        s.boundary_pot = money(2 * s.origin, m);
        s.local = {0, 0};
        s.local_present = true;
        s.committed = {s.origin, s.origin};
    } else if (s.local_present) {
        const auto x = std::min(s.local[0], s.local[1]);
        s.local = {x, x};
        const auto all = money(s.origin + x, m);
        s.committed = {all, all};
    }
    s.phase = Phase::decision;
    s.street = s.next_street;
    s.next_street = 0;
    s.actor = 1;
    s.increment = 0;
    s.raises = 0;
    s.reopened = true;
    s.checks = 0;
    s.history_empty = false;
    return s;
}
struct Branch {
    Action action;
    State next;
};
inline std::vector<Branch> expand(const State &s, const Config &c, Meter &m) {
    m.work(2048);
    m.scratch(1024);
    if (s.phase == Phase::fold || s.phase == Phase::showdown)
        return {};
    if (s.phase == Phase::reveal)
        return {{Action{}, reveal(s, m)}};
    if (s.committed[s.actor] >= c.stacks[s.actor] - EPS)
        return {{Action{}, settle(s, c, m)}};
    const auto p = static_cast<std::size_t>(s.actor), other = 1 - p;
    const double origin = s.origin_present ? s.origin : 0;
    const double own = s.local_present ? s.local[p] : s.committed[p],
                 theirs = s.local_present ? s.local[other] : s.committed[other];
    const double stack = money(c.stacks[p] - origin, m),
                 other_stack = money(c.stacks[other] - origin, m);
    const double owed_raw = theirs - own,
                 owed = std::abs(owed_raw) <= EPS ? 0 : std::max(0., owed_raw);
    std::vector<Action> actions, sized;
    actions.reserve(20);
    sized.reserve(20);
    if (owed) {
        const auto call_amount = money(std::min(owed, stack - own), m),
                   local_call = money(std::min(theirs, stack), m);
        actions.push_back({ActionKind::fold, 0, 0, 0, false, false, "fold"});
        actions.push_back({ActionKind::call, call_amount, money(origin + local_call, m), local_call,
                           true, false, "call"});
    } else
        actions.push_back({ActionKind::check, 0, 0, 0, false, false, "check"});
    const auto &opts = c.stages[street_index(s.street)];
    const double base = s.origin_present ? s.boundary_pot : 0;
    auto add = [&](ActionKind kind, double target, double committed, double maximum, bool full) {
        target = money(std::min(maximum, std::max(committed, target)), m);
        if (target <= committed + EPS)
            return;
        if (target >= maximum - EPS)
            kind = ActionKind::all_in;
        for (const auto &a : sized)
            if (std::abs(a.local_target - target) <= EPS)
                return;
        const auto global = money(origin + target, m);
        Action a{kind, money(target - committed, m), global, target, true,
                 full, token(kind, global, m)};
        sized.push_back(std::move(a));
    };
    if (s.street && !owed) {
        for (double frac : opts.bets) {
            const double pot = base + (own + theirs);
            add(ActionKind::bet, own + frac * pot, own, stack, false);
        }
        if (opts.all_in && stack > own + EPS)
            add(ActionKind::all_in, stack, own, stack, false);
    } else if ((owed || s.street == 0) && s.reopened && s.raises < opts.max_raises &&
               stack > theirs + EPS && theirs < other_stack - EPS) {
        const double pot = (base + (own + theirs)) + owed_raw;
        for (double frac : opts.raises) {
            const double requested = theirs + frac * pot, minimum = theirs + s.increment;
            const auto target = money(std::min(stack, std::max(minimum, requested)), m);
            const bool full = target - theirs + EPS >= s.increment;
            if (full)
                add(ActionKind::raise, target, own, stack, true);
            else if (requested + EPS >= stack || minimum > stack)
                add(ActionKind::all_in, stack, own, stack, false);
        }
        if (opts.all_in && stack > theirs + EPS)
            add(ActionKind::all_in, stack, own, stack, stack - theirs + EPS >= s.increment);
    }
    std::sort(sized.begin(), sized.end(),
              [](const Action &a, const Action &b) { return a.target < b.target; });
    actions.insert(actions.end(), sized.begin(), sized.end());
    if (actions.empty() || actions.size() > 20)
        throw Error("invalid menu width");
    std::vector<Branch> result;
    result.reserve(actions.size());
    for (const auto &a : actions) {
        State n = s;
        n.history_empty = false;
        if (a.kind == ActionKind::fold) {
            n.phase = Phase::fold;
            n.winner = static_cast<std::uint8_t>(other);
            n.history_empty = s.history_empty;
        } else if (a.kind == ActionKind::call) {
            n.committed[p] = a.target;
            if (s.street && s.local_present)
                n.local[p] = money(a.local_target, m);
            else {
                n.local_present = false;
                n.local = {0, 0};
            }
            const bool same = std::abs(n.committed[0] - n.committed[1]) <= EPS,
                       chips =
                           n.committed[0] < c.stacks[0] - EPS && n.committed[1] < c.stacks[1] - EPS;
            if (s.street == 0 && s.history_empty && same && chips)
                n.actor = 1;
            else
                n = settle(n, c, m);
        } else if (a.kind == ActionKind::check) {
            if (s.street == 0 || s.checks == 1)
                n = settle(n, c, m);
            else {
                n.actor = static_cast<std::uint8_t>(other);
                n.checks = 1;
            }
        } else {
            n.committed[p] = a.target;
            bool opening = false;
            double increment = 0;
            if (s.street && s.local_present) {
                opening = std::abs(s.local[0] - s.local[1]) <= EPS;
                n.local[p] = a.local_target;
                increment = opening
                                ? a.amount
                                : (a.full_raise ? a.local_target - s.local[other] : s.increment);
            } else {
                opening = s.street && s.committed[0] == s.committed[1];
                increment = opening ? a.amount
                                    : (a.full_raise ? a.target - s.committed[other] : s.increment);
                n.local_present = false;
                n.local = {0, 0};
            }
            n.actor = static_cast<std::uint8_t>(other);
            n.increment = increment;
            n.raises = opening ? 0 : s.raises + 1;
            n.reopened = opening ? true : a.full_raise;
            n.checks = 0;
        }
        result.push_back({a, n});
    }
    return result;
}
class Template final {
    Config config_;
    Meter meter_;
    std::vector<Node> nodes_;
    std::map<State, std::size_t> index_;
    std::size_t root_ = 0;
    std::size_t intern(State state) {
        if (state.phase == Phase::decision &&
            state.committed[state.actor] >= config_.stacks[state.actor] - EPS)
            state = settle(state, config_, meter_);
        meter_.work(512 * (1 + std::bit_width(index_.size() + 1)));
        auto found = index_.find(state);
        if (found != index_.end())
            return found->second;
        if (nodes_.size() >= meter_.limits.nodes)
            throw Error("template node limit exceeded");
        meter_.entries(192);
        const auto id = nodes_.size();
        index_.emplace(state, id);
        nodes_.push_back(Node{state, {}});
        return id;
    }
    void build(State start) {
        root_ = intern(start);
        for (std::size_t at = 0; at < nodes_.size(); ++at) {
            const auto state = nodes_[at].state;
            const auto branches = expand(state, config_, meter_);
            if (branches.size() > meter_.limits.edges - meter_.receipt.edges)
                throw Error("template edge limit exceeded");
            meter_.entries(32 * branches.size());
            std::vector<Edge> edges;
            edges.reserve(branches.size());
            for (const auto &branch : branches) {
                const auto id = intern(branch.next);
                edges.push_back(Edge{branch.action, id});
            }
            meter_.receipt.edges += edges.size();
            nodes_[at].edges = std::move(edges);
        }
        census();
    }
    static std::uint64_t multiply(std::uint64_t a, std::uint64_t b) {
        if (a && b > std::numeric_limits<std::uint64_t>::max() / a)
            throw Error("template history count overflow");
        return a * b;
    }
    void census() {
        const auto n = nodes_.size();
        meter_.work(1024 + 64 * n + 64 * meter_.receipt.edges);
        meter_.entries(5 * n);
        meter_.scratch(12 * n + 1024);
        std::vector<std::size_t> indegree(n), depth(n);
        std::vector<std::uint64_t> count(n), sem_tokens(n), sem_bytes(n), old_tokens(n),
            old_bytes(n);
        for (const auto &node : nodes_)
            for (const auto &e : node.edges) {
                if (e.child >= n)
                    throw Error("invalid template edge");
                ++indegree[e.child];
            }
        std::vector<std::size_t> ready;
        ready.reserve(n);
        for (std::size_t i = 0; i < n; ++i)
            if (!indegree[i])
                ready.push_back(i);
        count[root_] = 1;
        std::size_t processed = 0;
        for (std::size_t at = 0; at < ready.size(); ++at) {
            const auto id = ready[at];
            ++processed;
            const auto &node = nodes_[id];
            const auto paths = count[id];
            if (!paths)
                throw Error("unreachable template node");
            auto &rec = meter_.receipt;
            rec.logical_occurrences =
                checked_add(rec.logical_occurrences, paths, meter_.limits.occurrences);
            rec.max_depth = std::max(rec.max_depth, depth[id]);
            if (depth[id] > meter_.limits.depth)
                throw Error("template depth exceeded");
            const auto k = street_index(node.state.phase == Phase::reveal ? node.state.next_street
                                                                          : node.state.street);
            if (node.state.phase == Phase::decision) {
                rec.decisions[k][node.state.actor] = checked_add(rec.decisions[k][node.state.actor],
                                                                 paths, meter_.limits.occurrences);
                rec.action_slots[k] =
                    checked_add(rec.action_slots[k], multiply(paths, node.edges.size()),
                                meter_.limits.occurrences);
            } else if (node.state.phase == Phase::reveal)
                rec.reveals[k] = checked_add(rec.reveals[k], paths, meter_.limits.occurrences);
            else if (node.state.phase == Phase::fold)
                rec.folds[k] = checked_add(rec.folds[k], paths, meter_.limits.occurrences);
            else
                rec.showdowns[k] = checked_add(rec.showdowns[k], paths, meter_.limits.occurrences);
            for (const auto &e : node.edges) {
                const auto target = e.child;
                const bool reveal_edge = node.state.phase == Phase::reveal;
                const bool action_edge = node.state.phase == Phase::decision;
                const std::size_t bytes =
                    reveal_edge
                        ? (node.state.next_street == 3 ? 11 : (node.state.next_street == 4 ? 7 : 8))
                        : (action_edge ? e.action.token.size() : 0);
                const bool token_edge = action_edge || reveal_edge,
                           old_edge =
                               token_edge && !(action_edge && e.action.kind == ActionKind::fold);
                count[target] = checked_add(count[target], paths, meter_.limits.occurrences);
                sem_tokens[target] =
                    checked_add(sem_tokens[target],
                                checked_add(sem_tokens[id], token_edge ? paths : 0,
                                            std::numeric_limits<std::uint64_t>::max()),
                                std::numeric_limits<std::uint64_t>::max());
                sem_bytes[target] =
                    checked_add(sem_bytes[target],
                                checked_add(sem_bytes[id], multiply(paths, bytes),
                                            std::numeric_limits<std::uint64_t>::max()),
                                std::numeric_limits<std::uint64_t>::max());
                old_tokens[target] =
                    checked_add(old_tokens[target],
                                checked_add(old_tokens[id], old_edge ? paths : 0,
                                            std::numeric_limits<std::uint64_t>::max()),
                                std::numeric_limits<std::uint64_t>::max());
                old_bytes[target] =
                    checked_add(old_bytes[target],
                                checked_add(old_bytes[id], old_edge ? multiply(paths, bytes) : 0,
                                            std::numeric_limits<std::uint64_t>::max()),
                                std::numeric_limits<std::uint64_t>::max());
                depth[target] = std::max(depth[target], depth[id] + 1);
                if (!--indegree[target])
                    ready.push_back(target);
            }
        }
        if (processed != n)
            throw Error("template continuation cycle");
        histories_.reserve(n);
        for (std::size_t i = 0; i < n; ++i)
            histories_.push_back(
                {count[i], sem_tokens[i], sem_bytes[i], old_tokens[i], old_bytes[i]});
        meter_.receipt.nodes = n;
    }
    std::vector<std::array<std::uint64_t, 5>> histories_;

  public:
    Template(const Config &config, Limits limits = {}, const State *supplied = nullptr)
        : meter_{limits, {}} {
        if (!limits.nodes || limits.nodes > 250000 || !limits.edges || limits.edges > 1000000 ||
            !limits.entries || limits.entries > 2000000 || !limits.depth || limits.depth > 64 ||
            !limits.work || limits.work > 500000000 || !limits.occurrences ||
            limits.occurrences > 1000000000000ULL)
            throw Error("invalid reduce-only limits");
        meter_.work(4608); // bounded configuration and supplied-state validation scan
        if (std::fegetround() != FE_TONEAREST)
            throw Error("nearest rounding required");
        auto positive = [](double x) { return std::isfinite(x) && x >= 1e-9 && x <= 1e6; };
        if (!positive(config.stacks[0]) || !positive(config.stacks[1]) || !positive(config.sb) ||
            !positive(config.bb))
            throw Error("invalid stack or blinds");
        std::size_t sizes = 0;
        for (std::size_t i = 0; i < config.stages.size(); ++i) {
            const auto &stage = config.stages[i];
            if (stage.bets.size() > 8 || stage.raises.size() > 8 || stage.max_raises > 8 ||
                (i && stage.bets.empty()))
                throw Error("invalid stage sizes");
            for (double x : stage.bets)
                if (!positive(x))
                    throw Error("invalid bet size");
            for (double x : stage.raises)
                if (!positive(x))
                    throw Error("invalid raise size");
            sizes += stage.bets.size() + stage.raises.size();
        }
        if (supplied)
            validate_state(*supplied);
        meter_.entries(64 + 4 * sizes);
        config_ = config;
        validate_config(config_, limits, meter_);
        State start = supplied ? *supplied : initial(config_, meter_);
        validate_state(start);
        for (std::size_t i = 0; i < 2; ++i)
            if (start.committed[i] > config_.stacks[i] + EPS)
                throw Error("state commitment exceeds stack");
        if (supplied) {
            if (start.phase != Phase::decision)
                throw Error("supplied state must be a decision");
            auto clean = [&](double x) {
                return std::bit_cast<std::uint64_t>(money(x, meter_)) ==
                       std::bit_cast<std::uint64_t>(x);
            };
            if (!clean(start.committed[0]) || !clean(start.committed[1]))
                throw Error("state commitments are not cleaned money");
            if (start.street == 0) {
                if (start.origin_present || start.local_present)
                    throw Error("preflop state cannot have a local ledger");
            } else {
                if (!start.origin_present || !start.local_present)
                    throw Error("postflop state requires a local ledger");
                if (start.origin > std::min(config_.stacks[0], config_.stacks[1]) + EPS ||
                    !clean(start.origin) || !clean(start.boundary_pot) || !clean(start.local[0]) ||
                    !clean(start.local[1]))
                    throw Error("invalid local ledger values");
                if (money(2 * start.origin, meter_) != start.boundary_pot)
                    throw Error("boundary pot does not match origin");
                for (std::size_t i = 0; i < 2; ++i) {
                    const double local_stack = money(config_.stacks[i] - start.origin, meter_);
                    if (start.local[i] > local_stack + EPS ||
                        money(start.origin + start.local[i], meter_) != start.committed[i])
                        throw Error("local/global commitment mismatch");
                }
            }
            if (start.history_empty) {
                const auto actual = initial(config_, meter_);
                if (start.key() != actual.key() || actual.phase != Phase::decision)
                    throw Error("empty-history state is not the initial decision");
            }
        }
        meter_.receipt.history_suffix_only = !start.history_empty;
        build(start);
    }
    [[nodiscard]] const std::vector<Node> &nodes() const noexcept { return nodes_; }
    [[nodiscard]] const std::vector<std::array<std::uint64_t, 5>> &histories() const noexcept {
        return histories_;
    }
    [[nodiscard]] const Receipt &receipt() const noexcept { return meter_.receipt; }
    [[nodiscard]] std::size_t root() const noexcept { return root_; }
};
} // namespace openpoker::virtual_betting_template
