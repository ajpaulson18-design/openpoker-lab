// Exact bounded public-tree CFR+ helper. All poker rules and worlds arrive from
// the authenticated Python adapter; this code does not read files or use network.
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr const char* PROTOCOL = "OPENPOKER_PUBLIC_CFR_V1";
constexpr int MAX_DEPTH = 64;
constexpr int MAX_HANDS = 128;
constexpr int MAX_NODES = 250000;
constexpr int MAX_PREFIXES = 4096;
constexpr int MAX_EDGES = 250000;
constexpr int MAX_SLOTS = 1000000;
constexpr unsigned long long MAX_WORK = 500000000ULL;
constexpr unsigned long long MAX_HEAP = 256ULL * 1024ULL * 1024ULL;

struct Node {
    int kind, player, prefix, first, count, map, terminal;
    double payoff;
};
struct Pair { int oop, ip; double mass, signed_mass; };
struct Span { int first, count; };
struct Row { int count, slot; };

int checked_int(long long value, int lo, int hi, const char* label) {
    if (value < lo || value > hi) throw std::runtime_error(label);
    return static_cast<int>(value);
}
double checked_double(double x, double lo, double hi, const char* label) {
    if (!std::isfinite(x) || x < lo || x > hi) throw std::runtime_error(label);
    return x;
}
double read_real(std::istream& input, const char* label) {
    std::string token;
    if (!(input >> token) || token.empty() || token.size() > 64)
        throw std::runtime_error(label);
    char* end = nullptr;
    errno = 0;
    double value = std::strtod(token.c_str(), &end);
    if (end != token.c_str() + token.size() || !std::isfinite(value) ||
            (errno == ERANGE && value == 0.0 &&
             token != "0x0.0p+0" && token != "-0x0.0p+0"))
        throw std::runtime_error(label);
    return value;
}
unsigned long long add(unsigned long long x, unsigned long long y) {
    if (x > std::numeric_limits<unsigned long long>::max() - y)
        throw std::runtime_error("resource arithmetic overflow");
    return x + y;
}
unsigned long long mul(unsigned long long x, unsigned long long y) {
    if (y && x > std::numeric_limits<unsigned long long>::max() / y)
        throw std::runtime_error("resource arithmetic overflow");
    return x * y;
}
struct AccurateSum {
    double hi = 0.0, lo = 0.0;
    void append(double x) {
        double next = hi + x;
        if (std::abs(hi) >= std::abs(x)) lo += (hi - next) + x;
        else lo += (x - next) + hi;
        hi = next;
    }
    double result(bool compensated) const { return compensated ? hi + lo : hi; }
};

struct Game {
    int n, m, p, e, r, q, s, h[2], t, sum_mode;
    unsigned long long terminal_visits;
    unsigned long long decision_action_hands, opponent_action_hands;
    unsigned long long chance_children, decision_children;
    std::vector<Node> nodes;
    std::vector<int> children, maps;
    std::vector<Span> spans;
    std::vector<Pair> pairs;
    std::vector<Row> rows;
    std::vector<double> marg[2], regrets, delta, sigma, sums;
    std::vector<double> values, reaches;
    int width;

    double probability(int node, int hand, int action) const {
        const Node& x = nodes[node];
        int row = maps[x.map + hand];
        return row < 0 ? 1.0 / x.count : sigma[rows[row].slot + action];
    }
    void match() {
        for (const Row& row : rows) {
            AccurateSum positive;
            for (int a = 0; a < row.count; ++a)
                positive.append(std::max(0.0, regrets[row.slot + a]));
            double mass = positive.result(sum_mode != 0);
            if (!std::isfinite(mass)) throw std::runtime_error("nonfinite regret mass");
            for (int a = 0; a < row.count; ++a)
                sigma[row.slot + a] = mass == 0 ? 1.0 / row.count :
                    std::max(0.0, regrets[row.slot + a]) / mass;
        }
    }
    // Child values use a depth arena. No iteration allocates heap memory.
    void target(int id, int player, const double* opp, double* out, int depth) {
        const Node& x = nodes[id];
        const int own_h = h[player];
        std::fill(out, out + own_h, 0.0);
        if (x.kind == 0) {
            const Span& span = spans[x.prefix];
            for (int k = span.first; k < span.first + span.count; ++k) {
                const Pair& pair = pairs[k];
                double weighted = x.terminal == 0 ? pair.mass : pair.signed_mass;
                if (player == 0) out[pair.oop] += (weighted * opp[pair.ip]) * x.payoff;
                else out[pair.ip] -= (weighted * opp[pair.oop]) * x.payoff;
            }
            return;
        }
        double* scratch = values.data() + static_cast<std::size_t>(depth) * 52 * width;
        if (x.kind == 2) {
            for (int a = 0; a < x.count; ++a) {
                double* child_value = scratch + a * width;
                target(children[x.first + a], player, opp, child_value, depth + 1);
                for (int hand = 0; hand < own_h; ++hand)
                    out[hand] += child_value[hand];
            }
            return;
        }
        if (x.player == player) {
            for (int a = 0; a < x.count; ++a)
                target(children[x.first + a], player, opp,
                       scratch + a * width, depth + 1);
            for (int hand = 0; hand < own_h; ++hand) {
                AccurateSum expected;
                for (int a = 0; a < x.count; ++a)
                    expected.append(probability(id, hand, a) * scratch[a * width + hand]);
                out[hand] = expected.result(sum_mode != 0);
                const int row = maps[x.map + hand];
                if (row >= 0)
                    for (int a = 0; a < x.count; ++a)
                        delta[rows[row].slot + a] += scratch[a * width + hand] - out[hand];
            }
        } else {
            const int opp_h = h[1 - player];
            double* next = reaches.data() + static_cast<std::size_t>(depth) * 2 * width;
            for (int a = 0; a < x.count; ++a) {
                for (int hand = 0; hand < opp_h; ++hand)
                    next[hand] = opp[hand] * probability(id, hand, a);
                double* child_value = scratch + a * width;
                target(children[x.first + a], player, next, child_value, depth + 1);
                for (int hand = 0; hand < own_h; ++hand)
                    out[hand] += child_value[hand];
            }
        }
    }
    void average(int id, const double* reach0, const double* reach1,
                 int depth, double factor) {
        const Node& x = nodes[id];
        if (x.kind == 0) return;
        if (x.kind == 2) {
            for (int a = 0; a < x.count; ++a)
                average(children[x.first + a], reach0, reach1, depth + 1, factor);
            return;
        }
        const int player = x.player;
        const double* own = player == 0 ? reach0 : reach1;
        const double* marginal = marg[player].data() +
            static_cast<std::size_t>(x.prefix) * h[player];
        for (int hand = 0; hand < h[player]; ++hand) {
            const int row = maps[x.map + hand];
            if (row >= 0)
                for (int a = 0; a < x.count; ++a)
                    sums[rows[row].slot + a] += marginal[hand] * own[hand] *
                                                 probability(id, hand, a) * factor;
        }
        double* next = reaches.data() +
            static_cast<std::size_t>(depth) * 2 * width + width;
        for (int a = 0; a < x.count; ++a) {
            for (int hand = 0; hand < h[player]; ++hand)
                next[hand] = own[hand] * probability(id, hand, a);
            if (player == 0) average(children[x.first + a], next, reach1, depth + 1, factor);
            else average(children[x.first + a], reach0, next, depth + 1, factor);
        }
    }
    void train() {
        match();
        std::vector<double> ones0(h[0], 1.0), ones1(h[1], 1.0), result(width);
        for (int iteration = 1; iteration <= t; ++iteration) {
            for (int player = 0; player < 2; ++player) {
                std::fill(delta.begin(), delta.end(), 0.0);
                target(0, player, player == 0 ? ones1.data() : ones0.data(),
                       result.data(), 0);
                for (int row = 0; row < r; ++row) {
                    // Only the target player's rows have deltas in this pass.
                    // Player identity is stored in row_player below.
                    if (row_player[row] != player) continue;
                    for (int a = 0; a < rows[row].count; ++a) {
                        int slot = rows[row].slot + a;
                        regrets[slot] = std::max(0.0, regrets[slot] + delta[slot]);
                    }
                }
                match();
            }
            average(0, ones0.data(), ones1.data(), 0, static_cast<double>(iteration));
        }
    }
    std::vector<int> row_player;
};

Game read_game(std::istream& input) {
    std::string magic;
    if (!(input >> magic) || magic != PROTOCOL)
        throw std::runtime_error("unsupported protocol");
    long long raw[16];
    for (auto& value : raw) if (!(input >> value)) throw std::runtime_error("truncated header");
    double pot = read_real(input, "invalid pot token");
    Game g{};
    g.n = checked_int(raw[0], 1, MAX_NODES, "node cap");
    g.m = checked_int(raw[1], 0, MAX_NODES, "child cap");
    g.p = checked_int(raw[2], 1, MAX_PREFIXES, "prefix cap");
    g.e = checked_int(raw[3], 1, MAX_EDGES, "pair-edge cap");
    g.r = checked_int(raw[4], 0, MAX_SLOTS, "row cap");
    g.q = checked_int(raw[5], 0, MAX_SLOTS, "map cap");
    g.s = checked_int(raw[6], 0, MAX_SLOTS, "slot cap");
    g.h[0] = checked_int(raw[7], 1, MAX_HANDS, "oop hand cap");
    g.h[1] = checked_int(raw[8], 1, MAX_HANDS, "ip hand cap");
    g.t = checked_int(raw[9], 1, 100000, "iteration cap");
    g.sum_mode = checked_int(raw[10], 0, 1, "sum mode");
    if (raw[11] < 0 || raw[11] > 62500000000LL)
        throw std::runtime_error("terminal-edge visit cap");
    g.terminal_visits = static_cast<unsigned long long>(raw[11]);
    for (int index = 12; index < 16; ++index)
        if (raw[index] < 0 || raw[index] > 100000000LL)
            throw std::runtime_error("traversal census cap");
    g.decision_action_hands = static_cast<unsigned long long>(raw[12]);
    g.opponent_action_hands = static_cast<unsigned long long>(raw[13]);
    g.chance_children = static_cast<unsigned long long>(raw[14]);
    g.decision_children = static_cast<unsigned long long>(raw[15]);
    checked_double(pot, std::numeric_limits<double>::denorm_min(), 1e12, "invalid pot");
    g.width = std::max(g.h[0], g.h[1]);
    const auto width = static_cast<unsigned long long>(g.width);
    unsigned long long heap = 128ULL * 1024 * 1024 + 1;
    heap = add(heap, mul(g.n, 80)); heap = add(heap, mul(g.m, 4));
    heap = add(heap, mul(g.p, 16 + 8ULL * (g.h[0] + g.h[1])));
    heap = add(heap, mul(g.e, 32)); heap = add(heap, mul(g.r, 20));
    heap = add(heap, mul(g.q, 4)); heap = add(heap, mul(g.s, 40));
    heap = add(heap, mul((MAX_DEPTH + 1ULL) * 52 * width, 8 * 2));
    heap = add(heap, 262144);
    const unsigned long long hand_sum = g.h[0] + g.h[1];
    unsigned long long traversal = add(mul(g.n, 3 + hand_sum),
        add(mul(g.terminal_visits, 2),
        add(mul(g.chance_children, hand_sum + 3),
        add(mul(g.decision_action_hands, 5),
        add(g.opponent_action_hands,
        add(mul(g.q, 2),
        add(mul(g.decision_children, 3),
        add(mul(g.s, 7), mul(g.r, 4)))))))));
    unsigned long long setup = add(mul(128, static_cast<unsigned long long>(g.n) +
        g.e + g.q + g.s + mul(g.p, hand_sum)),
        g.r + 2ULL * g.s + (MAX_DEPTH + 1ULL) * 54 * g.width +
        hand_sum + g.width);
    unsigned long long work = add(mul(g.t, traversal),
                                  add(setup, g.r + 2ULL * g.s));
    if (heap > MAX_HEAP || work > MAX_WORK)
        throw std::runtime_error("native heap/work admission rejected");
    g.nodes.resize(g.n); g.children.resize(g.m); g.spans.resize(g.p);
    g.pairs.resize(g.e); g.rows.resize(g.r); g.maps.resize(g.q);
    g.row_player.assign(g.r, -1);
    g.marg[0].assign(static_cast<std::size_t>(g.p) * g.h[0], 0.0);
    g.marg[1].assign(static_cast<std::size_t>(g.p) * g.h[1], 0.0);
    g.regrets.assign(g.s, 0.0); g.delta.assign(g.s, 0.0);
    g.sigma.assign(g.s, 0.0); g.sums.assign(g.s, 0.0);
    g.values.assign((MAX_DEPTH + 1ULL) * 52 * g.width, 0.0);
    g.reaches.assign((MAX_DEPTH + 1ULL) * 2 * g.width, 0.0);
    std::vector<int> indegree(g.n, 0);
    int expected_child = 0, expected_map = 0;
    unsigned long long actual_d = 0, actual_o = 0, actual_c = 0, actual_a = 0;
    for (int i = 0; i < g.n; ++i) {
        Node& x = g.nodes[i];
        if (!(input >> x.kind >> x.player >> x.prefix >> x.first >> x.count
                >> x.map >> x.terminal))
            throw std::runtime_error("truncated node");
        x.payoff = read_real(input, "invalid node payoff token");
        if (x.kind < 0 || x.kind > 2 || x.prefix < 0 || x.prefix >= g.p ||
                x.first != expected_child || x.count < 0 ||
                x.first > g.m - x.count || x.map != expected_map ||
                !std::isfinite(x.payoff))
            throw std::runtime_error("invalid node");
        expected_child += x.count;
        if (x.kind == 0) {
            if (x.count || (x.terminal != 0 && x.terminal != 1) ||
                    std::abs(x.payoff) > 1e12)
                throw std::runtime_error("invalid terminal");
        } else if (x.kind == 1) {
            if ((x.player != 0 && x.player != 1) || x.count < 1 || x.count > 12 ||
                    x.map > g.q - g.h[x.player])
                throw std::runtime_error("invalid decision");
            expected_map += g.h[x.player];
            actual_d = add(actual_d, mul(x.count, g.h[x.player]));
            actual_o = add(actual_o, mul(x.count, g.h[1 - x.player]));
            actual_a = add(actual_a, x.count);
        } else if (x.count < 1 || x.count > 52) {
            throw std::runtime_error("invalid chance");
        } else {
            actual_c = add(actual_c, x.count);
        }
    }
    if (expected_child != g.m || expected_map != g.q)
        throw std::runtime_error("tree/map total mismatch");
    if (actual_d != g.decision_action_hands ||
            actual_o != g.opponent_action_hands ||
            actual_c != g.chance_children ||
            actual_a != g.decision_children)
        throw std::runtime_error("traversal census reservation mismatch");
    for (int i = 0; i < g.m; ++i) {
        if (!(input >> g.children[i]) || g.children[i] <= 0 ||
                g.children[i] >= g.n) throw std::runtime_error("invalid child");
        ++indegree[g.children[i]];
    }
    if (indegree[0] || g.m != g.n - 1)
        throw std::runtime_error("tree is not an arborescence");
    for (int i = 1; i < g.n; ++i)
        if (indegree[i] != 1) throw std::runtime_error("tree is not an arborescence");
    int expected_edge = 0;
    for (int i = 0; i < g.p; ++i) {
        if (!(input >> g.spans[i].first >> g.spans[i].count) ||
                g.spans[i].first < 0 || g.spans[i].count < 0 ||
                g.spans[i].first != expected_edge ||
                g.spans[i].first > g.e - g.spans[i].count)
            throw std::runtime_error("invalid prefix edge span");
        expected_edge += g.spans[i].count;
    }
    if (expected_edge != g.e) throw std::runtime_error("prefix edge total mismatch");
    unsigned long long actual_terminal_visits = 0;
    for (const Node& x : g.nodes)
        if (x.kind == 0)
            actual_terminal_visits = add(actual_terminal_visits,
                                         g.spans[x.prefix].count);
    if (actual_terminal_visits != g.terminal_visits)
        throw std::runtime_error("terminal-edge visit reservation mismatch");
    for (int i = 0; i < g.e; ++i) {
        Pair& pair = g.pairs[i];
        if (!(input >> pair.oop >> pair.ip))
            throw std::runtime_error("truncated pair edge");
        pair.mass = read_real(input, "invalid pair mass token");
        pair.signed_mass = read_real(input, "invalid signed mass token");
        if (
                pair.oop < 0 || pair.oop >= g.h[0] || pair.ip < 0 ||
                pair.ip >= g.h[1] || !std::isfinite(pair.mass) ||
                !std::isfinite(pair.signed_mass) || pair.mass < 0 ||
                std::abs(pair.signed_mass) > pair.mass + 1e-12)
            throw std::runtime_error("invalid pair edge");
    }
    for (int i = 0; i < g.p; ++i) {
        for (int k = g.spans[i].first; k < g.spans[i].first + g.spans[i].count; ++k) {
            const Pair& pair = g.pairs[k];
            g.marg[0][static_cast<std::size_t>(i) * g.h[0] + pair.oop] += pair.mass;
            g.marg[1][static_cast<std::size_t>(i) * g.h[1] + pair.ip] += pair.mass;
        }
    }
    int expected_slot = 0;
    for (int i = 0; i < g.r; ++i) {
        Row& row = g.rows[i];
        if (!(input >> row.count >> row.slot) || row.count < 1 ||
                row.count > 12 || row.slot != expected_slot ||
                row.slot > g.s - row.count)
            throw std::runtime_error("invalid policy row");
        expected_slot += row.count;
    }
    if (expected_slot != g.s) throw std::runtime_error("slot total mismatch");
    for (int i = 0; i < g.q; ++i)
        if (!(input >> g.maps[i]) || g.maps[i] < -1 || g.maps[i] >= g.r)
            throw std::runtime_error("invalid decision row map");
    input >> std::ws;
    if (input.peek() != std::char_traits<char>::eof())
        throw std::runtime_error("trailing protocol data");
    for (const Node& x : g.nodes) if (x.kind == 1)
        for (int hand = 0; hand < g.h[x.player]; ++hand) {
            int row = g.maps[x.map + hand];
            if (row >= 0) {
                if (g.rows[row].count != x.count ||
                        (g.row_player[row] != -1 && g.row_player[row] != x.player))
                    throw std::runtime_error("inconsistent information row");
                g.row_player[row] = x.player;
            }
        }
    // Iterative DFS verifies reachability, acyclicity, and depth before traversal.
    std::vector<std::pair<int,int>> todo{{0, 0}};
    std::vector<unsigned char> visited(g.n, 0);
    while (!todo.empty()) {
        auto [id, depth] = todo.back(); todo.pop_back();
        if (depth > MAX_DEPTH || visited[id]++) throw std::runtime_error("invalid tree depth/cycle");
        const Node& x = g.nodes[id];
        for (int a = 0; a < x.count; ++a)
            todo.emplace_back(g.children[x.first + a], depth + 1);
    }
    for (auto value : visited) if (!value) throw std::runtime_error("unreachable tree node");
    for (const Node& x : g.nodes) if (x.kind != 0)
        for (int a = 0; a < x.count; ++a) {
            const Node& child = g.nodes[g.children[x.first + a]];
            if ((x.kind == 1 && child.prefix != x.prefix) ||
                    (x.kind == 2 && child.prefix == x.prefix))
                throw std::runtime_error("invalid public prefix transition");
        }
    return g;
}
} // namespace

int main() {
    try {
        std::ios::sync_with_stdio(false);
        std::cin.tie(nullptr);
        std::string payload;
        char chunk[65536];
        while (std::cin) {
            std::cin.read(chunk, sizeof(chunk));
            std::streamsize got = std::cin.gcount();
            if (got > 0) {
                if (payload.size() > 64ULL * 1024 * 1024 - static_cast<std::size_t>(got))
                    throw std::runtime_error("input exceeds 64 MiB");
                payload.append(chunk, static_cast<std::size_t>(got));
            }
        }
        std::istringstream input(std::move(payload));
        Game game = read_game(input);
        game.train();
        std::vector<double> output;
        output.reserve(game.s);
        for (const Row& row : game.rows) {
            AccurateSum accumulator;
            for (int a = 0; a < row.count; ++a)
                accumulator.append(game.sums[row.slot + a]);
            double total = accumulator.result(game.sum_mode != 0);
            if (!std::isfinite(total) || total < 0)
                throw std::runtime_error("nonfinite policy sum");
            for (int a = 0; a < row.count; ++a) {
                double value = total ? game.sums[row.slot + a] / total : 1.0 / row.count;
                if (!std::isfinite(value)) throw std::runtime_error("nonfinite policy");
                output.push_back(value);
            }
        }
        std::printf("%s %d\n", PROTOCOL, game.s);
        for (double value : output) std::printf("%a\n", value);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "native public CFR: %s\n", error.what());
        return 2;
    }
}
