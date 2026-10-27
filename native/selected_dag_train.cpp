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
#include <map>
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
constexpr const char* PROTOCOL = "OPENPOKER_SELECTED_DAG_V1";
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

struct Prefix { int size; std::array<U,3> token; };
struct Board { std::array<U,3> token; U mask; };
struct Hand { U mask; double weight; };
struct Node { int kind, player, first, count, stage, terminal; double payoff; };
struct Edge { int child; U reveal; };
struct Row { int count, slot; };
// N,R,S,Q,terminal,marginal,action hands,opponent hands,chance,decision.
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

using Census = std::array<U,10>;
struct Context { int node, prefix, first=0, count=0, height=0; Census totals{}; };
struct ContextEdge { int child; U row, slot; };
struct Game {
    int v,e,c,ce,r,s,h[2],b,p,t,sum_mode,root,n,q,width,root_context=0;
    double normalizer;
    Census declared{};
    std::vector<Node> nodes;
    std::vector<Edge> edges;
    std::vector<Context> contexts;
    std::vector<ContextEdge> context_edges;
    std::map<std::pair<int,int>,int> context_ids;
    std::vector<int> ordinals, active_counts, row_player;
    std::vector<unsigned char> supported_boards, board_activity, seen_nodes;
    std::vector<Row> rows;
    std::vector<Prefix> prefixes;
    std::map<std::array<U,4>,int> prefix_ids;
    std::vector<Board> boards;
    std::vector<Hand> hands[2];
    std::vector<unsigned int> ranks;
    std::vector<double> regrets,delta,sigma,sums,values,reaches,marginal[2];
    int marginal_prefix=-1;
    U terminal_checks=0,marginal_checks=0,normalization_checks=0;
    int ordinal(int prefix,int player,int hand) const {
        return ordinals[static_cast<std::size_t>(prefix)*(h[0]+h[1])+(player?h[0]:0)+hand];
    }
    int active(int prefix,int player) const { return active_counts[2*prefix+player]; }
    void within(const Census& value) const {
        for (std::size_t i=0;i<value.size();++i)
            if (value[i]>declared[i]) throw std::runtime_error("logical census exceeds declaration");
    }
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
    void terminal(const Node& node, int prefix, int player, const double* opp, double* out) {
        int count;
        auto selected = matching(prefix, count);
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

    double probability(int id,U row_base,int hand,int action) const {
        const Context& context=contexts[id]; const Node& x=nodes[context.node];
        int at=ordinal(context.prefix,x.player,hand);
        return at<0 ? 1.0/x.count : sigma[rows[static_cast<std::size_t>(row_base)+at].slot+action];
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
    void target(int id, U row_base, U slot_base, int player, const double* opp, double* out, int depth) {
        const Context& context=contexts[id];
        const Node& x=nodes[context.node];
        if (add(row_base,context.totals[1])>static_cast<U>(r) || add(slot_base,context.totals[2])>static_cast<U>(s) || depth>DEPTH)
            throw std::runtime_error("traversal span/depth");
        std::fill(out, out + h[player], 0.0);
        if (x.kind == 0) { terminal(x, context.prefix, player, opp, out); return; }
        double* scratch = values.data() + static_cast<std::size_t>(depth) * FANOUT * width;
        if (x.kind == 2) {
            for (int a = 0; a < x.count; ++a) {
                double* value = scratch + a * width;
                target(context_edges[context.first+a].child, add(row_base,context_edges[context.first+a].row), add(slot_base,context_edges[context.first+a].slot), player, opp, value, depth + 1);
                for (int hand = 0; hand < h[player]; ++hand) out[hand] += value[hand];
            }
        } else if (x.player == player) {
            for (int a = 0; a < x.count; ++a)
                target(context_edges[context.first+a].child, add(row_base,context_edges[context.first+a].row), add(slot_base,context_edges[context.first+a].slot), player, opp, scratch + a * width, depth + 1);
            for (int hand = 0; hand < h[player]; ++hand) {
                Sum expected;
                for (int a = 0; a < x.count; ++a)
                    expected.append(probability(id, row_base, hand, a) * scratch[a * width + hand]);
                out[hand] = expected.result(sum_mode);
                int ordinal_index=ordinal(context.prefix,x.player,hand);
                int row=ordinal_index<0 ? -1 : static_cast<int>(row_base)+ordinal_index;
                if (row >= 0) for (int a = 0; a < x.count; ++a)
                    delta[rows[row].slot + a] += scratch[a * width + hand] - out[hand];
            }
        } else {
            double* next = reaches.data() + static_cast<std::size_t>(depth) * 2 * width;
            for (int a = 0; a < x.count; ++a) {
                for (int hand = 0; hand < h[1-player]; ++hand)
                    next[hand] = opp[hand] * probability(id, row_base, hand, a);
                double* value = scratch + a * width;
                target(context_edges[context.first+a].child, add(row_base,context_edges[context.first+a].row), add(slot_base,context_edges[context.first+a].slot), player, next, value, depth + 1);
                for (int hand = 0; hand < h[player]; ++hand) out[hand] += value[hand];
            }
        }
    }
    void average(int id, U row_base, U slot_base, const double* reach0, const double* reach1, int depth, double factor) {
        const Context& context=contexts[id];
        const Node& x=nodes[context.node];
        if (add(row_base,context.totals[1])>static_cast<U>(r) || add(slot_base,context.totals[2])>static_cast<U>(s) || depth>DEPTH)
            throw std::runtime_error("traversal span/depth");
        if (x.kind == 0) return;
        if (x.kind == 2) {
            for (int a = 0; a < x.count; ++a) average(context_edges[context.first+a].child, add(row_base,context_edges[context.first+a].row), add(slot_base,context_edges[context.first+a].slot), reach0, reach1, depth + 1, factor);
            return;
        }
        marginals(context.prefix);
        const double* own = x.player == 0 ? reach0 : reach1;
        for (int hand = 0; hand < h[x.player]; ++hand) {
            int ordinal_index=ordinal(context.prefix,x.player,hand);
                int row=ordinal_index<0 ? -1 : static_cast<int>(row_base)+ordinal_index;
            if (row >= 0) for (int a = 0; a < x.count; ++a)
                sums[rows[row].slot + a] += marginal[x.player][hand] * own[hand] * probability(id, row_base, hand, a) * factor;
        }
        double* next = reaches.data() + static_cast<std::size_t>(depth) * 2 * width + width;
        for (int a = 0; a < x.count; ++a) {
            for (int hand = 0; hand < h[x.player]; ++hand) next[hand] = own[hand] * probability(id, row_base, hand, a);
            average(context_edges[context.first+a].child, add(row_base,context_edges[context.first+a].row), add(slot_base,context_edges[context.first+a].slot), x.player == 0 ? next : reach0, x.player == 1 ? next : reach1, depth + 1, factor);
        }
    }
    void train() {
        match();
        std::vector<double> ones0(h[0], 1.0), ones1(h[1], 1.0), result(width);
        for (int iteration = 1; iteration <= t; ++iteration) {
            for (int player = 0; player < 2; ++player) {
                std::fill(delta.begin(), delta.end(), 0.0);
                target(root_context, 0, 0, player, player == 0 ? ones1.data() : ones0.data(), result.data(), 0);
                for (int row = 0; row < r; ++row) if (row_player[row] == player)
                    for (int a = 0; a < rows[row].count; ++a) {
                        int slot = rows[row].slot + a;
                        regrets[slot] = std::max(0.0, regrets[slot] + delta[slot]);
                    }
                match();
            }
            average(root_context, 0, 0, ones0.data(), ones1.data(), 0, static_cast<double>(iteration));
        }
    }
    int ensure(int node_id,int prefix_id,int depth) {
        if (depth>DEPTH) throw std::runtime_error("context depth");
        auto key=std::make_pair(node_id,prefix_id);
        auto known=context_ids.find(key);
        if (known!=context_ids.end()) {
            if (contexts[known->second].height+depth>DEPTH) throw std::runtime_error("cached context depth");
            return known->second;
        }
        if (contexts.size()>=static_cast<std::size_t>(c)) throw std::runtime_error("context capacity");
        int id=static_cast<int>(contexts.size());
        contexts.push_back(Context{node_id,prefix_id}); context_ids.emplace(key,id); seen_nodes[node_id]=1;
        const Node& x=nodes[node_id]; const Prefix& prefix=prefixes[prefix_id];
        int matches=0; matching(prefix_id,matches);
        if (!matches) throw std::runtime_error("unsupported context prefix");
        Census total{}; total[0]=1;
        if (x.kind==0) total[4]=mul(matches,mul(h[0],h[1]));
        if (x.kind==1) {
            total[1]=static_cast<U>(active(prefix_id,x.player)); total[2]=mul(total[1],x.count);
            total[3]=static_cast<U>(h[x.player]); total[5]=mul(matches,mul(h[0],h[1]));
            total[6]=mul(x.count,h[x.player]); total[7]=mul(x.count,h[1-x.player]); total[9]=static_cast<U>(x.count);
        }
        std::set<U> expected,actual;
        std::array<U,BOARDS> expected_order{}; int reveal_count=0;
        if (x.kind==2) {
            if (prefix.size>=3 || x.stage!=prefix.size+1) throw std::runtime_error("chance stage");
            total[8]=static_cast<U>(x.count);
            for (int k=0;k<b;++k) if (supported_boards[k]) {
                bool same=true;
                for (int z=0;z<prefix.size;++z) same=same && boards[k].token[z]==prefix.token[z];
                if (same && expected.insert(boards[k].token[prefix.size]).second) expected_order[reveal_count++]=boards[k].token[prefix.size];
            }
        }
        if (x.kind==2 && prefix.size>0) {
            // Python sorts two-character public card tokens lexically, not by deck index.
            auto lexical=[](U token) {
                unsigned int index=static_cast<unsigned int>(std::countr_zero(token));
                return std::pair<char,char>{"23456789TJQKA"[index/4],"cdhs"[index%4]};
            };
            std::sort(expected_order.begin(),expected_order.begin()+reveal_count,[&](U a,U b){return lexical(a)<lexical(b);});
        }
        within(total);
        std::array<ContextEdge,FANOUT> temporary{}; int height=0;
        for (int a=0;a<x.count;++a) {
            const Edge& edge=edges[x.first+a]; int next_prefix=prefix_id;
            if (x.kind==2) {
                if (a>=reveal_count || edge.reveal!=expected_order[a] || !expected.contains(edge.reveal) || !actual.insert(edge.reveal).second)
                    throw std::runtime_error("invalid/duplicate chance reveal");
                auto token=prefix.token; token[prefix.size]=edge.reveal;
                std::array<U,4> pk{static_cast<U>(prefix.size+1),token[0],token[1],token[2]};
                auto found=prefix_ids.find(pk);
                if (found==prefix_ids.end()) throw std::runtime_error("unsupported reveal prefix");
                next_prefix=found->second;
            }
            int child=ensure(edge.child,next_prefix,depth+1);
            const Context& next=contexts[child];
            temporary[a]={child,total[1],total[2]};
            for (std::size_t z=0;z<total.size();++z) total[z]=add(total[z],next.totals[z]);
            within(total); height=std::max(height,next.height+1);
        }
        if (x.kind==2 && actual!=expected) throw std::runtime_error("incomplete chance partition");
        if (height+depth>DEPTH || add(context_edges.size(),x.count)>static_cast<U>(ce))
            throw std::runtime_error("context edge/depth capacity");
        contexts[id].first=static_cast<int>(context_edges.size()); contexts[id].count=x.count;
        contexts[id].height=height; contexts[id].totals=total;
        context_edges.insert(context_edges.end(),temporary.begin(),temporary.begin()+x.count);
        return id;
    }
    void initialize_rows(int id,U row_base,U slot_base,int depth,U& visits,U& row_visits,U& slot_visits) {
        const Context& context=contexts[id]; const Node& x=nodes[context.node];
        if (depth>DEPTH || add(row_base,context.totals[1])>static_cast<U>(r) || add(slot_base,context.totals[2])>static_cast<U>(s))
            throw std::runtime_error("row span/depth");
        visits=add(visits,1);
        if (visits>static_cast<U>(n)) throw std::runtime_error("row traversal capacity");
        if (x.kind==1) {
            int count=active(context.prefix,x.player);
            for (int hand=0;hand<count;++hand) {
                U index=add(row_base,hand), slot=add(slot_base,mul(hand,x.count));
                if (index!=row_visits || slot!=slot_visits || index>=static_cast<U>(r) || add(slot,x.count)>static_cast<U>(s) || row_player[index]!=-1)
                    throw std::runtime_error("duplicate/out-of-order row span");
                rows[index]={x.count,static_cast<int>(slot)}; row_player[index]=x.player;
                row_visits=add(row_visits,1); slot_visits=add(slot_visits,x.count);
            }
        }
        for (int a=0;a<context.count;++a) {
            const ContextEdge& edge=context_edges[context.first+a];
            initialize_rows(edge.child,add(row_base,edge.row),add(slot_base,edge.slot),depth+1,visits,row_visits,slot_visits);
        }
    }
};

std::pair<U,U> envelope(const Game& g,const Census& counts) {
    U hs=static_cast<U>(g.h[0]+g.h[1]);
    U setup=add(mul(128,add(add(g.n,g.q),g.s)),add(mul(counts[5],10),add(mul(mul(g.n,g.b),32),add(mul(mul(g.b,mul(g.h[0],g.h[1])),128),mul(g.p,64)))));
    U sweep=add(mul(counts[4],20),add(mul(counts[5],10),add(mul(mul(g.n,hs),10),add(mul(g.s,12),add(mul(mul(g.b,g.n),6),add(mul(counts[6],8),add(counts[7],add(mul(counts[8],hs),mul(counts[9],4)))))))));
    U extra=mul(256,add(add(add(g.v,g.e),add(g.c,g.ce)),add(g.r,mul(g.p,hs))));
    extra=add(extra,add(mul(mul(mul(128,g.p),g.b),hs),mul(mul(32,g.c),g.b)));
    U per=add(mul(mul(16,g.n),hs),mul(8,g.q));
    U work=add(add(setup,add(mul(g.t,sweep),add(g.r,mul(g.s,2)))),add(extra,mul(g.t,per)));
    U heap=128ULL*1024*1024+1;
    for (auto item:std::array<U,12>{mul(96,g.v),mul(16,g.e),mul(160,g.c),mul(32,g.ce),mul(24,g.r),mul(40,g.s),mul(64,g.p),mul(mul(add(mul(2,g.p),g.b),hs),8),mul(g.b,add(32,mul(8,hs))),mul(32,hs),mul((DEPTH+1ULL)*(FANOUT+2ULL)*g.width,16),0}) heap=add(heap,item);
    if (work>MAX_WORK || heap>MAX_HEAP) throw std::runtime_error("native DAG work/heap admission rejected");
    return {work,heap};
}

Game read_game(std::istream& in) {
    std::string magic; if (!(in>>magic) || magic!=PROTOCOL) throw std::runtime_error("unsupported protocol");
    Game g{};
    g.v=integer(in,1,NODES); g.e=integer(in,0,NODES-1); g.c=integer(in,1,NODES); g.ce=integer(in,0,NODES-1);
    g.r=integer(in,0,SLOTS); g.s=integer(in,0,SLOTS); g.h[0]=integer(in,1,HANDS); g.h[1]=integer(in,1,HANDS);
    g.b=integer(in,1,BOARDS); g.p=integer(in,1,PREFIXES); g.t=integer(in,10,10000); g.sum_mode=integer(in,0,1);
    g.root=integer(in,0,g.v-1); g.n=integer(in,1,NODES); g.q=integer(in,0,2000000); g.width=std::max(g.h[0],g.h[1]);
    g.declared={static_cast<U>(g.n),static_cast<U>(g.r),static_cast<U>(g.s),static_cast<U>(g.q),0,0,0,0,0,0};
    for (int z=4;z<10;++z) g.declared[z]=natural(in,1000000000000ULL);
    if (g.v>g.c || g.c>g.n || g.e>g.ce || g.ce>g.n-1 || g.b*(g.h[0]+g.h[1])>8192)
        throw std::runtime_error("DAG dimension capacity");
    envelope(g,g.declared); g.normalizer=normal(real(in));
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
    g.board_activity.assign(static_cast<std::size_t>(g.b)*(g.h[0]+g.h[1]),0);
    std::vector<unsigned char> supported_boards(g.b,0);
    for (int i=0;i<g.h[0];++i) for (int j=0;j<g.h[1];++j) {
        if (g.hands[0][i].mask&g.hands[1][j].mask) continue;
        for (int k=0;k<g.b;++k) {
            const Board& board=g.boards[k];
            ++g.normalization_checks;
            if (board.mask&(g.hands[0][i].mask|g.hands[1][j].mask)) continue;
            supported_boards[k]=1;
            auto activity=static_cast<std::size_t>(k)*(g.h[0]+g.h[1]);
            g.board_activity[activity+i]=1; g.board_activity[activity+g.h[0]+j]=1;
            double raw=normal((g.hands[0][i].weight*g.hands[1][j].weight)/DENOMINATOR);
            normalization.append(raw);
            normal(raw/g.normalizer);
        }
    }
    double observed=normalization.result();
    if (observed!=g.normalizer)
        throw std::runtime_error("global chance normalizer mismatch");

    g.supported_boards=std::move(supported_boards);
    g.prefixes.reserve(g.p);
    auto insert_prefix=[&](int size,const std::array<U,3>& tokens) {
        std::array<U,3> padded{}; for (int z=0;z<size;++z) padded[z]=tokens[z];
        std::array<U,4> key{static_cast<U>(size),padded[0],padded[1],padded[2]};
        if (g.prefix_ids.contains(key)) return;
        if (g.prefixes.size()>=static_cast<std::size_t>(g.p)) throw std::runtime_error("prefix capacity");
        g.prefix_ids.emplace(key,static_cast<int>(g.prefixes.size())); g.prefixes.push_back({size,padded});
    };
    insert_prefix(0,{});
    for (int k=0;k<g.b;++k) if (g.supported_boards[k])
        for (int size=1;size<=3;++size) insert_prefix(size,g.boards[k].token);
    if (g.prefixes.size()!=static_cast<std::size_t>(g.p)) throw std::runtime_error("prefix census mismatch");
    int hs=g.h[0]+g.h[1]; g.ordinals.assign(static_cast<std::size_t>(g.p)*hs,-1); g.active_counts.assign(2*g.p,0);
    for (int prefix=0;prefix<g.p;++prefix) {
        int count=0; auto selected=g.matching(prefix,count);
        for (int player=0;player<2;++player) for (int hand=0;hand<g.h[player];++hand) {
            bool active=false; int offset=(player?g.h[0]:0)+hand;
            for (int at=0;at<count;++at) active=active || g.board_activity[static_cast<std::size_t>(selected[at])*hs+offset]!=0;
            if (active) g.ordinals[static_cast<std::size_t>(prefix)*hs+offset]=g.active_counts[2*prefix+player]++;
        }
    }
    g.nodes.resize(g.v); g.edges.resize(g.e); int expected_edge=0;
    for (Node& x:g.nodes) {
        x.kind=integer(in,0,2); x.player=integer(in,-1,1); x.first=integer(in,0,g.e); x.count=integer(in,0,FANOUT);
        x.stage=integer(in,0,3); x.terminal=integer(in,-1,1); x.payoff=real(in);
        if (x.first!=expected_edge || x.count>g.e-x.first) throw std::runtime_error("vertex edge span");
        expected_edge+=x.count;
        if (x.kind==0) {
            if (x.count || x.player!=-1 || x.stage || x.terminal<0 || std::abs(x.payoff)>1e12 || (x.terminal==1 && x.payoff<0))
                throw std::runtime_error("terminal shape");
        } else if (x.kind==1) {
            if (x.player<0 || x.count<1 || x.count>12 || x.stage || x.terminal!=-1 || x.payoff!=0)
                throw std::runtime_error("decision shape");
        } else if (x.player!=-1 || x.count<1 || x.stage<1 || x.terminal!=-1 || x.payoff!=0) throw std::runtime_error("chance shape");
    }
    if (expected_edge!=g.e) throw std::runtime_error("edge census");
    for (int node=0;node<g.v;++node) {
        const Node& x=g.nodes[node];
        for (int a=0;a<x.count;++a) {
            Edge& edge=g.edges[x.first+a]; edge.child=integer(in,0,g.v-1); edge.reveal=natural(in,CARD_BITS);
            if (edge.child>=node || (x.kind==1 && edge.reveal!=0) ||
                (x.kind==2 && std::popcount(edge.reveal)!=(x.stage==1?3:1))) throw std::runtime_error("postorder child/reveal");
        }
    }
    in>>std::ws; if (in.peek()!=std::char_traits<char>::eof()) throw std::runtime_error("trailing data");
    g.contexts.reserve(g.c); g.context_edges.reserve(g.ce); g.seen_nodes.assign(g.v,0);
    g.root_context=g.ensure(g.root,0,0);
    for (auto seen:g.seen_nodes) if (!seen) throw std::runtime_error("unreachable vertex");
    if (g.contexts.size()!=static_cast<std::size_t>(g.c) || g.context_edges.size()!=static_cast<std::size_t>(g.ce) || g.contexts[g.root_context].totals!=g.declared)
        throw std::runtime_error("native DAG census mismatch");
    envelope(g,g.contexts[g.root_context].totals);
    g.rows.resize(g.r); g.row_player.assign(g.r,-1);
    U visits=0,row_visits=0,slot_visits=0; g.initialize_rows(g.root_context,0,0,0,visits,row_visits,slot_visits);
    if (visits!=static_cast<U>(g.n) || row_visits!=static_cast<U>(g.r) || slot_visits!=static_cast<U>(g.s)) throw std::runtime_error("row coverage");
    for (int player:g.row_player) if (player<0) throw std::runtime_error("orphan row");
    // Setup-only tables/maps are released before allocating numerical training buffers.
    g.context_ids.clear(); g.prefix_ids.clear(); g.seen_nodes.clear(); g.board_activity.clear();
    g.marginal[0].assign(g.h[0],0); g.marginal[1].assign(g.h[1],0);
    g.regrets.assign(g.s,0); g.delta.assign(g.s,0); g.sigma.assign(g.s,0); g.sums.assign(g.s,0);
    g.values.assign((DEPTH+1ULL)*FANOUT*g.width,0); g.reaches.assign((DEPTH+1ULL)*2*g.width,0);
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
    } catch (const std::exception& error) { std::fprintf(stderr,"native selected DAG: %s\n",error.what()); return 2; }
}
