// Bounded selected-game CFR+ over on-demand private-pair/board queries.
// No complete-world rows or prefix/private-pair edge tables are stored.
// Public rules and per-hand ranks arrive from the source-authenticated adapter.
#include <algorithm>
#include <array>
#include <bit>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#ifdef _WIN32
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#else
#include <sys/resource.h>
#endif

namespace {
using U = unsigned long long;
constexpr const char* PROTOCOL = "OPENPOKER_SELECTED_OPERATOR_V1";
constexpr int DEPTH = 64, FANOUT = 64, HANDS = 128, BOARDS = 64;
constexpr int NODES = 250000, SLOTS = 1000000, PREFIXES = 193;
constexpr U MAX_WORK = 500000000ULL, MAX_HEAP = 256ULL * 1024 * 1024;
constexpr U CARD_BITS = (1ULL << 52) - 1;
constexpr double DENOMINATOR = 34246080.0;
static_assert(sizeof(U)==8 && sizeof(double)==8 && std::numeric_limits<double>::is_iec559 &&
              std::numeric_limits<double>::digits==53, "binary64/uint64 required");

U add(U x, U y) {
    if (x > std::numeric_limits<U>::max() - y) throw std::runtime_error("resource overflow");
    return x + y;
}
U mul(U x, U y) {
    if (y && x > std::numeric_limits<U>::max() / y) throw std::runtime_error("resource overflow");
    return x * y;
}
U peak_working_set() {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS counters{};
    if (!K32GetProcessMemoryInfo(GetCurrentProcess(),&counters,static_cast<DWORD>(sizeof(counters))))
        throw std::runtime_error("native process memory measurement failed");
    return static_cast<U>(counters.PeakWorkingSetSize);
#else
    struct rusage usage{};
    if (getrusage(RUSAGE_SELF,&usage)!=0 || usage.ru_maxrss<0)
        throw std::runtime_error("native process memory measurement failed");
#ifdef __APPLE__
    return static_cast<U>(usage.ru_maxrss);
#else
    return mul(static_cast<U>(usage.ru_maxrss),1024);
#endif
#endif
}
int integer(std::istream& in, int lo, int hi) {
    long long x;
    if (!(in >> x) || x < lo || x > hi) throw std::runtime_error("integer envelope");
    return static_cast<int>(x);
}
U natural(std::istream& in, U maximum) {
    std::string token;
    if (!(in >> token) || token.empty() || token.size() > 20 ||
        token.find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error("unsigned token");
    std::size_t end = 0;
    U x = std::stoull(token, &end);
    if (end != token.size() || x > maximum) throw std::runtime_error("unsigned envelope");
    return x;
}
double real(std::istream& in) {
    std::string token;
    if (!(in >> token) || token.empty() || token.size() > 64) throw std::runtime_error("real token");
    char* end = nullptr;
    errno = 0;
    double x = std::strtod(token.c_str(), &end);
    if (end != token.c_str() + token.size() || !std::isfinite(x) ||
        (errno == ERANGE && x == 0.0 && token != "0x0.0p+0" && token != "-0x0.0p+0"))
        throw std::runtime_error("invalid finite real");
    return x;
}
double normal(double x) {
    if (!std::isnormal(x) || x <= 0) throw std::runtime_error("unsupported probability mass");
    return x;
}
// Same binary64 reduction contract as the retained public-tree backend.
struct Sum {
    double hi = 0, lo = 0;
    void append(double x) {
        double next = hi + x;
        lo += std::abs(hi) >= std::abs(x) ? (hi - next) + x : (x - next) + hi;
        hi = next;
    }
    double result(int mode) const { return mode ? hi + lo : hi; }
};
// Exact nonnegative binary64 sum in units of 2^-1074. Normal raw inputs have
// mantissa*(2^(exponent_bits-1)) integer units. Thirty-six 64-bit limbs cover
// every finite raw input and the bounded candidate count with headroom.
struct PositiveExactSum {
    std::array<U,36> words{};
    void word_add(std::size_t at, U value) {
        while (value) {
            if (at>=words.size()) throw std::runtime_error("exact mass accumulator overflow");
            U before=words[at]; words[at]+=value;
            value=words[at]<before ? 1ULL : 0ULL;
            ++at;
        }
    }
    void append(double value) {
        U bits=std::bit_cast<U>(normal(value));
        U mantissa=(bits&((1ULL<<52)-1))|(1ULL<<52);
        unsigned int shift=static_cast<unsigned int>(((bits>>52)&2047)-1);
        std::size_t at=shift/64; unsigned int offset=shift%64;
        word_add(at,mantissa<<offset);
        if (offset) word_add(at+1,mantissa>>(64-offset));
    }
    bool bit(int position) const { return ((words[static_cast<std::size_t>(position/64)]>>(position%64))&1)!=0; }
    bool below(int limit) const {
        for (int at=0;at<limit/64;++at) if (words[at]) return true;
        unsigned int rest=static_cast<unsigned int>(limit%64);
        return rest && (words[static_cast<std::size_t>(limit/64)]&((1ULL<<rest)-1));
    }
    double result() const {
        int last=static_cast<int>(words.size())-1;
        while (last>=0 && words[last]==0) --last;
        if (last<0) return 0.0;
        int highest=last*64+63-std::countl_zero(words[last]);
        if (highest<52) throw std::runtime_error("raw normal mass invariant");
        int shift=highest-52;
        std::size_t at=static_cast<std::size_t>(shift/64); unsigned int offset=static_cast<unsigned int>(shift%64);
        U mantissa=words[at]>>offset;
        if (offset && at+1<words.size()) mantissa|=words[at+1]<<(64-offset);
        mantissa&=(1ULL<<53)-1;
        if (shift && bit(shift-1) && (below(shift-1) || (mantissa&1))) ++mantissa;
        int exponent=highest-1074;
        if (mantissa==(1ULL<<53)) { mantissa>>=1; ++exponent; }
        if (exponent>1023) throw std::runtime_error("exact mass sum overflow");
        U encoded=(static_cast<U>(exponent+1023)<<52)|(mantissa&((1ULL<<52)-1));
        return std::bit_cast<double>(encoded);
    }
};
struct Prefix { int size; std::array<U, 3> token; };
struct Board { std::array<U, 3> token; U mask; };
struct Hand { U mask; double weight; };
struct Node { int kind, player, prefix, first, count, map, terminal; double payoff; };
struct Row { int count, slot; };
bool valid_rank(unsigned int code) {
    constexpr int lengths[9]={6,5,4,4,2,6,3,3,2};
    unsigned int category=code>>20;
    if (category>8) return false;
    for (int i=1;i<6;++i) {
        unsigned int digit=(code>>(4*(5-i)))&15;
        if (i<lengths[category]) { if (digit<2 || digit>14) return false; }
        else if (digit) return false;
    }
    return true;
}

struct Game {
    int n, m, r, q, s, h[2], b, p, t, sum_mode, width;
    double normalizer;
    std::vector<Node> nodes;
    std::vector<int> children, maps, row_player;
    std::vector<Row> rows;
    std::vector<Prefix> prefixes;
    std::vector<Board> boards;
    std::vector<Hand> hands[2];
    std::vector<unsigned int> ranks;
    std::vector<double> regrets, delta, sigma, sums, values, reaches, marginal[2];
    int marginal_prefix = -1;
    U terminal_checks = 0, marginal_checks = 0, normalization_checks = 0;
    U terminal_candidates = 0, marginal_candidates = 0, action_hands = 0;
    U opponent_hands = 0, chance_children = 0, decision_children = 0;

    std::array<int, BOARDS> matching(int prefix, int& count) const {
        std::array<int, BOARDS> result{};
        count = 0;
        for (int k = 0; k < b; ++k) {
            bool match = true;
            for (int i = 0; i < prefixes[prefix].size; ++i)
                match = match && prefixes[prefix].token[i] == boards[k].token[i];
            if (match) result[count++] = k;
        }
        return result;
    }
    double mass(int i, int j) const {
        // Keep the Python reference's multiplication/division boundaries.
        return normal(normal((hands[0][i].weight * hands[1][j].weight) / DENOMINATOR) / normalizer);
    }
    int sign(int i, int j, int board) const {
        std::size_t at = static_cast<std::size_t>(board) * (h[0] + h[1]);
        unsigned int x = ranks[at + i], y = ranks[at + h[0] + j];
        return (x > y) - (x < y);
    }
    void marginals(int prefix) {
        if (marginal_prefix == prefix) return;
        std::fill(marginal[0].begin(), marginal[0].end(), 0.0);
        std::fill(marginal[1].begin(), marginal[1].end(), 0.0);
        int count;
        auto selected = matching(prefix, count);
        for (int i = 0; i < h[0]; ++i) for (int j = 0; j < h[1]; ++j) {
            U mask = hands[0][i].mask | hands[1][j].mask;
            if (hands[0][i].mask & hands[1][j].mask) continue;
            double total = 0, unit = 0;
            for (int at = 0; at < count; ++at) {
                ++marginal_checks;
                int k = selected[at];
                if (mask & boards[k].mask) continue;
                if (unit == 0) unit = mass(i, j);
                total += unit;
            }
            if (total) { marginal[0][i] += total; marginal[1][j] += total; }
        }
        marginal_prefix = prefix;
    }
    void terminal(const Node& node, int player, const double* opp, double* out) {
        int count;
        auto selected = matching(node.prefix, count);
        for (int i = 0; i < h[0]; ++i) for (int j = 0; j < h[1]; ++j) {
            if (hands[0][i].mask & hands[1][j].mask) continue;
            U mask = hands[0][i].mask | hands[1][j].mask;
            double total = 0, unit = 0;
            for (int at = 0; at < count; ++at) {
                ++terminal_checks;
                int k = selected[at];
                if (mask & boards[k].mask) continue;
                if (unit == 0) unit = mass(i, j);
                total += node.terminal ? unit * sign(i, j, k) : unit;
            }
            if (player == 0) out[i] += (total * opp[j]) * node.payoff;
            else out[j] -= (total * opp[i]) * node.payoff;
        }
    }
    double probability(int id, int hand, int action) const {
        const Node& x = nodes[id];
        int row = maps[x.map + hand];
        return row < 0 ? 1.0 / x.count : sigma[rows[row].slot + action];
    }
    void match() {
        for (const Row& row : rows) {
            Sum total;
            for (int a = 0; a < row.count; ++a) total.append(std::max(0.0, regrets[row.slot + a]));
            double mass_total = total.result(sum_mode);
            if (!std::isfinite(mass_total)) throw std::runtime_error("nonfinite regrets");
            for (int a = 0; a < row.count; ++a)
                sigma[row.slot + a] = mass_total ? std::max(0.0, regrets[row.slot + a]) / mass_total : 1.0 / row.count;
        }
    }
    void target(int id, int player, const double* opp, double* out, int depth) {
        const Node& x = nodes[id];
        std::fill(out, out + h[player], 0.0);
        if (x.kind == 0) { terminal(x, player, opp, out); return; }
        double* scratch = values.data() + static_cast<std::size_t>(depth) * FANOUT * width;
        if (x.kind == 2) {
            for (int a = 0; a < x.count; ++a) {
                double* value = scratch + a * width;
                target(children[x.first + a], player, opp, value, depth + 1);
                for (int hand = 0; hand < h[player]; ++hand) out[hand] += value[hand];
            }
        } else if (x.player == player) {
            for (int a = 0; a < x.count; ++a)
                target(children[x.first + a], player, opp, scratch + a * width, depth + 1);
            for (int hand = 0; hand < h[player]; ++hand) {
                Sum expected;
                for (int a = 0; a < x.count; ++a)
                    expected.append(probability(id, hand, a) * scratch[a * width + hand]);
                out[hand] = expected.result(sum_mode);
                int row = maps[x.map + hand];
                if (row >= 0) for (int a = 0; a < x.count; ++a)
                    delta[rows[row].slot + a] += scratch[a * width + hand] - out[hand];
            }
        } else {
            double* next = reaches.data() + static_cast<std::size_t>(depth) * 2 * width;
            for (int a = 0; a < x.count; ++a) {
                for (int hand = 0; hand < h[1-player]; ++hand)
                    next[hand] = opp[hand] * probability(id, hand, a);
                double* value = scratch + a * width;
                target(children[x.first + a], player, next, value, depth + 1);
                for (int hand = 0; hand < h[player]; ++hand) out[hand] += value[hand];
            }
        }
    }
    void average(int id, const double* reach0, const double* reach1, int depth, double factor) {
        const Node& x = nodes[id];
        if (x.kind == 0) return;
        if (x.kind == 2) {
            for (int a = 0; a < x.count; ++a) average(children[x.first + a], reach0, reach1, depth + 1, factor);
            return;
        }
        marginals(x.prefix);
        const double* own = x.player == 0 ? reach0 : reach1;
        for (int hand = 0; hand < h[x.player]; ++hand) {
            int row = maps[x.map + hand];
            if (row >= 0) for (int a = 0; a < x.count; ++a)
                sums[rows[row].slot + a] += marginal[x.player][hand] * own[hand] * probability(id, hand, a) * factor;
        }
        double* next = reaches.data() + static_cast<std::size_t>(depth) * 2 * width + width;
        for (int a = 0; a < x.count; ++a) {
            for (int hand = 0; hand < h[x.player]; ++hand) next[hand] = own[hand] * probability(id, hand, a);
            average(children[x.first + a], x.player == 0 ? next : reach0, x.player == 1 ? next : reach1, depth + 1, factor);
        }
    }
    void train() {
        match();
        std::vector<double> ones0(h[0], 1.0), ones1(h[1], 1.0), result(width);
        for (int iteration = 1; iteration <= t; ++iteration) {
            for (int player = 0; player < 2; ++player) {
                std::fill(delta.begin(), delta.end(), 0.0);
                target(0, player, player == 0 ? ones1.data() : ones0.data(), result.data(), 0);
                for (int row = 0; row < r; ++row) if (row_player[row] == player)
                    for (int a = 0; a < rows[row].count; ++a) {
                        int slot = rows[row].slot + a;
                        regrets[slot] = std::max(0.0, regrets[slot] + delta[slot]);
                    }
                match();
            }
            average(0, ones0.data(), ones1.data(), 0, static_cast<double>(iteration));
        }
    }
};

std::pair<U,U> envelope(const Game& g, U terminal, U marginal, U actions, U opponents, U chances, U decisions) {
    U hand_sum = static_cast<U>(g.h[0] + g.h[1]);
    U setup = add(mul(128, add(add(g.n,g.q),g.s)),
        add(mul(marginal,10), add(mul(mul(g.n,g.b),32),
        add(mul(mul(g.b,mul(g.h[0],g.h[1])),128),mul(g.p,64)))));
    U sweep = add(mul(terminal, 20), add(mul(marginal, 10),
        add(mul(mul(g.n, hand_sum), 10), add(mul(g.s, 12),
        add(mul(mul(g.b, g.n), 6), add(mul(actions, 8), add(opponents, add(mul(chances, hand_sum), mul(decisions, 4)))))))));
    U work = add(setup, add(mul(g.t, sweep), add(g.r, mul(g.s, 2))));
    U heap = add(128ULL*1024*1024+1, add(mul(g.n, 96), add(mul(g.m, 8), add(mul(g.q, 8),
        add(mul(g.r, 24), add(mul(g.s, 40), add(mul(g.p, 48),
        add(mul(g.b, 32+8*hand_sum), add(mul(hand_sum, 32),
        mul((DEPTH+1ULL)*(FANOUT+2ULL)*g.width, 16))))))))));
    if (work > MAX_WORK || heap > MAX_HEAP) throw std::runtime_error("native operator work/heap admission rejected");
    return {work,heap};
}

Game read_game(std::istream& in) {
    std::string magic;
    if (!(in >> magic) || magic != PROTOCOL) throw std::runtime_error("unsupported protocol");
    Game g{};
    g.n=integer(in,1,NODES); g.m=integer(in,0,NODES); g.r=integer(in,0,SLOTS);
    g.q=integer(in,0,2000000); g.s=integer(in,0,SLOTS);
    g.h[0]=integer(in,1,HANDS); g.h[1]=integer(in,1,HANDS);
    g.b=integer(in,1,BOARDS); g.p=integer(in,1,PREFIXES);
    g.t=integer(in,10,10000); g.sum_mode=integer(in,0,1);
    g.width=std::max(g.h[0],g.h[1]);
    if (g.b*(g.h[0]+g.h[1])>8192) throw std::runtime_error("rank-vector capacity");
    U declared[6]; for (auto& x:declared) x=natural(in,1000000000000ULL);
    g.normalizer=normal(real(in));
    envelope(g,declared[0],declared[1],declared[2],declared[3],declared[4],declared[5]);
    for (int player=0;player<2;++player) {
        g.hands[player].resize(g.h[player]);
        std::set<U> seen;
        for (Hand& h:g.hands[player]) {
            h.mask=natural(in,CARD_BITS); h.weight=real(in);
            if (std::popcount(h.mask)!=2 || h.weight<=0 || h.weight>1 || !seen.insert(h.mask).second)
                throw std::runtime_error("private hand input");
        }
    }
    g.boards.resize(g.b);
    g.ranks.resize(static_cast<std::size_t>(g.b)*(g.h[0]+g.h[1]));
    std::set<std::array<U,3>> seen_boards;
    for (int k=0;k<g.b;++k) {
        Board& board=g.boards[k];
        for (U& token:board.token) token=natural(in,CARD_BITS);
        board.mask=board.token[0]|board.token[1]|board.token[2];
        if (std::popcount(board.token[0])!=3 || std::popcount(board.token[1])!=1 ||
            std::popcount(board.token[2])!=1 || std::popcount(board.mask)!=5 || !seen_boards.insert(board.token).second)
            throw std::runtime_error("selected board input");
        std::size_t at=static_cast<std::size_t>(k)*(g.h[0]+g.h[1]);
        for (int player=0;player<2;++player) for (int i=0;i<g.h[player];++i) {
            unsigned int rank=static_cast<unsigned int>(natural(in,0xffffff));
            bool blocked=(board.mask&g.hands[player][i].mask)!=0;
            if ((rank==0)!=blocked || (!blocked && !valid_rank(rank))) throw std::runtime_error("blocked/rank encoding");
            g.ranks[at++]=rank;
        }
    }
    PositiveExactSum normalization;
    std::vector<unsigned char> supported_boards(g.b,0);
    for (int i=0;i<g.h[0];++i) for (int j=0;j<g.h[1];++j) {
        if (g.hands[0][i].mask&g.hands[1][j].mask) continue;
        for (int k=0;k<g.b;++k) {
            const Board& board=g.boards[k];
            ++g.normalization_checks;
            if (board.mask&(g.hands[0][i].mask|g.hands[1][j].mask)) continue;
            supported_boards[k]=1;
            double raw=normal((g.hands[0][i].weight*g.hands[1][j].weight)/DENOMINATOR);
            normalization.append(raw);
            normal(raw/g.normalizer);
        }
    }
    double observed=normalization.result();
    if (observed!=g.normalizer)
        throw std::runtime_error("global chance normalizer mismatch");
    g.prefixes.resize(g.p);
    std::set<std::array<U,4>> seen_prefixes;
    for (Prefix& prefix:g.prefixes) {
        prefix.size=integer(in,0,3);
        for (U& token:prefix.token) token=natural(in,CARD_BITS);
        for (int i=prefix.size;i<3;++i) if (prefix.token[i]) throw std::runtime_error("prefix padding");
        std::array<U,4> key{static_cast<U>(prefix.size),prefix.token[0],prefix.token[1],prefix.token[2]};
        if (!seen_prefixes.insert(key).second) throw std::runtime_error("duplicate prefix");
    }
    if (g.prefixes[0].size) throw std::runtime_error("root must hide future boards");
    g.nodes.resize(g.n); g.children.resize(g.m); g.maps.resize(g.q); g.rows.resize(g.r);
    g.row_player.assign(g.r,-1);
    int expected_child=0, expected_map=0;
    for (Node& x:g.nodes) {
        x.kind=integer(in,0,2); x.player=integer(in,-1,1); x.prefix=integer(in,0,g.p-1);
        x.first=integer(in,0,g.m); x.count=integer(in,0,FANOUT); x.map=integer(in,0,g.q);
        x.terminal=integer(in,-1,1); x.payoff=real(in);
        if (x.first!=expected_child || x.count>g.m-x.first || x.map!=expected_map)
            throw std::runtime_error("node span mismatch");
        expected_child+=x.count;
        int matches; g.matching(x.prefix,matches);
        if (matches==0) throw std::runtime_error("unsupported public prefix");
        if (x.kind==0) {
            if (x.count || x.player!=-1 || x.terminal<0 || std::abs(x.payoff)>1e12 ||
                (x.terminal==1 && x.payoff<0)) throw std::runtime_error("terminal shape");
            g.terminal_candidates=add(g.terminal_candidates,mul(matches,mul(g.h[0],g.h[1])));
        } else if (x.kind==1) {
            if (x.player<0 || x.count<1 || x.count>12 || x.map>g.q-g.h[x.player] || x.terminal!=-1 || x.payoff!=0)
                throw std::runtime_error("decision shape");
            expected_map+=g.h[x.player];
            g.marginal_candidates=add(g.marginal_candidates,mul(matches,mul(g.h[0],g.h[1])));
            g.action_hands=add(g.action_hands,mul(x.count,g.h[x.player]));
            g.opponent_hands=add(g.opponent_hands,mul(x.count,g.h[1-x.player]));
            g.decision_children=add(g.decision_children,x.count);
        } else {
            if (x.player!=-1 || x.count<1 || x.terminal!=-1 || x.payoff!=0) throw std::runtime_error("chance shape");
            g.chance_children=add(g.chance_children,x.count);
        }
    }
    U actual[6]={g.terminal_candidates,g.marginal_candidates,g.action_hands,g.opponent_hands,g.chance_children,g.decision_children};
    for (int i=0;i<6;++i) if (actual[i]!=declared[i]) throw std::runtime_error("native census mismatch");
    if (expected_child!=g.m || expected_map!=g.q || g.m!=g.n-1 || g.nodes[0].prefix!=0)
        throw std::runtime_error("tree totals");
    std::vector<int> indegree(g.n,0);
    for (int& child:g.children) { child=integer(in,1,g.n-1); ++indegree[child]; }
    if (indegree[0]) throw std::runtime_error("root incoming edge");
    for (int i=1;i<g.n;++i) if (indegree[i]!=1) throw std::runtime_error("shared tree");
    int expected_slot=0;
    for (Row& row:g.rows) {
        row.count=integer(in,1,12); row.slot=integer(in,0,g.s);
        if (row.slot!=expected_slot || row.count>g.s-row.slot) throw std::runtime_error("row span");
        expected_slot+=row.count;
    }
    if (expected_slot!=g.s) throw std::runtime_error("action slots");
    for (int& row:g.maps) row=integer(in,-1,g.r-1);
    in>>std::ws; if (in.peek()!=std::char_traits<char>::eof()) throw std::runtime_error("trailing data");
    std::vector<unsigned char> visited(g.n,0);
    std::vector<std::pair<int,int>> todo{{0,0}};
    while (!todo.empty()) {
        auto [id,depth]=todo.back(); todo.pop_back();
        if (depth>DEPTH || visited[id]++) throw std::runtime_error("tree depth/cycle");
        const Node& x=g.nodes[id];
        std::set<U> expected_reveals, actual_reveals;
        const Prefix& parent=g.prefixes[x.prefix];
        if (x.kind==2) {
            if (parent.size>=3) throw std::runtime_error("chance after complete board");
            for (int k=0;k<g.b;++k) if (supported_boards[k]) {
                bool match=true;
                for (int i=0;i<parent.size;++i) match=match && g.boards[k].token[i]==parent.token[i];
                if (match) expected_reveals.insert(g.boards[k].token[parent.size]);
            }
        }
        for (int a=0;a<x.count;++a) {
            int child_id=g.children[x.first+a]; const Node& child=g.nodes[child_id];
            const Prefix& next=g.prefixes[child.prefix];
            if (x.kind==1 && child.prefix!=x.prefix) throw std::runtime_error("private/public decision mismatch");
            if (x.kind==2) {
                if (next.size!=parent.size+1) throw std::runtime_error("reveal length");
                for (int i=0;i<parent.size;++i) if (next.token[i]!=parent.token[i]) throw std::runtime_error("reveal prefix");
                if (!actual_reveals.insert(next.token[parent.size]).second)
                    throw std::runtime_error("duplicate chance partition reveal");
            }
            todo.emplace_back(child_id,depth+1);
        }
        if (x.kind==2 && actual_reveals!=expected_reveals)
            throw std::runtime_error("incomplete selected chance partition");
    }
    for (auto value:visited) if (!value) throw std::runtime_error("unreachable node");
    g.marginal[0].assign(g.h[0],0); g.marginal[1].assign(g.h[1],0);
    for (const Node& x:g.nodes) if (x.kind==1) {
        g.marginals(x.prefix);
        for (int i=0;i<g.h[x.player];++i) {
            int row=g.maps[x.map+i];
            if ((row>=0)!=(g.marginal[x.player][i]>0)) throw std::runtime_error("visible private support map");
            if (row>=0) {
                if (g.rows[row].count!=x.count || g.row_player[row]!=-1) throw std::runtime_error("information row identity/menu");
                g.row_player[row]=x.player;
            }
        }
    }
    for (int player:g.row_player) if (player<0) throw std::runtime_error("orphan policy row");
    g.regrets.assign(g.s,0); g.delta.assign(g.s,0); g.sigma.assign(g.s,0); g.sums.assign(g.s,0);
    g.values.assign((DEPTH+1ULL)*FANOUT*g.width,0); g.reaches.assign((DEPTH+1ULL)*2*g.width,0);
    g.terminal_checks=0; g.marginal_checks=0; g.marginal_prefix=-1;
    return g;
}
} // namespace

int main() {
    try {
        std::ios::sync_with_stdio(false); std::cin.tie(nullptr);
        std::string payload; char chunk[65536];
        while (std::cin) {
            std::cin.read(chunk,sizeof(chunk)); auto got=std::cin.gcount();
            if (got>0) {
                if (payload.size()>64ULL*1024*1024-static_cast<std::size_t>(got)) throw std::runtime_error("input exceeds 64 MiB");
                payload.append(chunk,static_cast<std::size_t>(got));
            }
        }
        std::istringstream input(std::move(payload)); Game game=read_game(input); game.train();
        std::printf("%s %d %llu %llu %llu\n",PROTOCOL,game.s,game.terminal_checks,game.marginal_checks,game.normalization_checks);
        for (const Row& row:game.rows) {
            Sum total; for (int a=0;a<row.count;++a) total.append(game.sums[row.slot+a]);
            double value=total.result(game.sum_mode);
            if (!std::isfinite(value) || value<0) throw std::runtime_error("policy total");
            for (int a=0;a<row.count;++a) {
                double probability=value ? game.sums[row.slot+a]/value : 1.0/row.count;
                if (!std::isfinite(probability) || probability<0 || probability>1) throw std::runtime_error("policy probability");
                std::printf("%a\n",probability);
            }
        }
        std::fflush(stdout);
        std::printf("RSS %llu\n",peak_working_set());
        return 0;
    } catch (const std::exception& error) { std::fprintf(stderr,"native selected operator: %s\n",error.what()); return 2; }
}
