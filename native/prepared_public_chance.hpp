#pragma once
// Prepared q=1 integer contractions only. The parent owns money, fixed-game
// scaling, output lifetime and complete training admission. No pair/world table.
#include "full_deck_public_chance.hpp"
#include <bit>
#include <memory>

namespace openpoker::prepared_public_chance {
namespace chance = full_deck_public_chance;
namespace detail = exact_selected_kernel::detail;
using chance::Integer;
using chance::Hand;
using chance::WeightedHand;
using chance::TerminalKind;
using chance::KernelError;
using chance::ErrorCode;
using chance::Limits;
using chance::DeckDefinition;

enum class RankCacheKey { ordered_prefix, board_set };
enum class RankCacheIndex { linear, sorted_board_set };
enum class ContractionKernel { blocker_buckets, sparse_pairs };

struct Contraction {
    std::vector<Integer> numerators;
    std::uint64_t prefix_divisor = 1;
    std::size_t reach_exponent = 0;
};
struct Receipt {
    std::uint64_t modeled_work = 0, prior_work = 0, setup_work = 0,
        input_work = 0, cache_lookup_work = 0, rank_work = 0,
        sort_work = 0, contraction_work = 0;
    std::size_t retained_entries = 0, peak_scratch_entries = 0,
        peak_live_entries = 0, retained_integer_payload_bits = 0,
        peak_integer_payload_bits = 0, peak_integer_bits = 0,
        rank_calls = 0, cache_hits = 0, cache_misses = 0, cache_evictions = 0,
        completed_contractions = 0, query_array_admissions = 0, sparse_pair_visits = 0;
};

struct RankIndexReceipt {
    std::size_t capacity=0, entries=0, size=0;
    std::uint64_t searches=0, updates=0, lookup_work=0, update_work=0, setup_work=0;
};

class PreparedPublicChance final {
    struct Bucket { Integer total = 0; std::array<Integer,52> cards{}; };
    struct WeightedReach { std::size_t row=0; Integer mass=0; };
    struct SparsePairCost {
        std::size_t scratch_entries=0;
        std::uint64_t scratch_payload_bits=0;
    };
    struct Plane {
        std::array<std::uint8_t,sizeof(std::uint64_t)> board_key{};
        std::array<std::vector<detail::Rank>,2> ranks;
        std::array<std::vector<std::size_t>,2> order;
        std::array<std::vector<unsigned char>,2> unblocked;
        std::uint64_t stamp = 0;
        bool valid = false;
    };
    struct IndexEntry { std::uint64_t key=0; std::size_t slot=0; };
    struct RankIndex {
        std::unique_ptr<IndexEntry[]> entries;
        std::size_t size=0;
        std::uint64_t searches=0, updates=0, lookup_work=0, update_work=0, setup_work=0;
    };
    // Owner metadata, returned diagnostics and bounded search/update scalars.
    static constexpr std::size_t index_fixed_entries=32;
    static constexpr std::size_t index_entry_words=(sizeof(IndexEntry)+7)/8;
    static constexpr std::size_t missing = std::numeric_limits<std::size_t>::max();
    [[noreturn]] static void fail(ErrorCode code,const char* text) { throw KernelError(code,text); }
    static std::uint64_t add(std::uint64_t a,std::uint64_t b) { return detail::checked_add_count(a,b); }
    static std::uint64_t mul(std::uint64_t a,std::uint64_t b) { return detail::checked_mul_count(a,b); }
    static std::size_t width(const Integer& n) { return detail::magnitude_bits(n); }
    static std::size_t lg(std::size_t n) { return n<=1 ? 0 : std::bit_width(n-1); }
    static std::uint64_t words(std::size_t bits) { return std::max<std::uint64_t>(1,(bits+63)/64); }
    // Logical 64-bit operand ledger, not a Boost allocation/CPU/RSS promise.
    // A copy scans/writes one operand; an add/subtract scans two and writes one.
    // A multiply admits schoolbook word products plus operand/result passes.
    static std::uint64_t copy_cost(std::size_t b) { return 1+2*words(b); }
    static std::uint64_t add_cost(std::size_t b) { return 2+3*words(b); }
    static std::uint64_t multiply_cost(std::size_t a,std::size_t b) {
        const auto x=words(a),y=words(b);
        return add(2+2*(x+y),mul(x,y));
    }
    void charge(std::uint64_t work,std::uint64_t& category) {
        if (work>limits_.max_modeled_work-receipt_.modeled_work)
            fail(ErrorCode::modeled_work_limit,"prepared cumulative work exceeded");
        receipt_.modeled_work+=work; category+=work;
    }
    void admit(std::size_t retained_add,std::size_t payload_add,std::size_t scratch,
               std::size_t scratch_payload,std::size_t bits) {
        if (bits>limits_.max_integer_bits)
            fail(ErrorCode::integer_bit_limit,"prepared integer width exceeded");
        const auto retained=add(receipt_.retained_entries,retained_add);
        const auto live=add(retained,scratch);
        if (live>limits_.max_storage_entries)
            fail(ErrorCode::storage_limit,"prepared live entries exceeded");
        const auto payload=add(receipt_.retained_integer_payload_bits,payload_add);
        if (add(payload,scratch_payload)>limits_.max_integer_payload_bits)
            fail(ErrorCode::integer_payload_limit,"prepared live integer payload exceeded");
        receipt_.retained_entries=static_cast<std::size_t>(retained);
        receipt_.retained_integer_payload_bits=static_cast<std::size_t>(payload);
        receipt_.peak_scratch_entries=std::max(receipt_.peak_scratch_entries,scratch);
        receipt_.peak_live_entries=std::max(receipt_.peak_live_entries,static_cast<std::size_t>(live));
        receipt_.peak_integer_payload_bits=std::max(receipt_.peak_integer_payload_bits,
            static_cast<std::size_t>(payload+scratch_payload));
        receipt_.peak_integer_bits=std::max(receipt_.peak_integer_bits,bits);
    }
    static std::uint64_t hand_mask(Hand hand) {
        return (std::uint64_t{1}<<hand.first)|(std::uint64_t{1}<<hand.second);
    }
    std::uint64_t board_mask(std::span<const std::uint8_t> board,TerminalKind kind) const {
        const auto n=board.size();
        if ((n!=0 && n!=3 && n!=4 && n!=5) || (kind==TerminalKind::showdown && n!=5))
            fail(ErrorCode::invalid_query,"invalid prepared visible prefix length");
        if (n>=3 && !(board[0]<board[1] && board[1]<board[2]))
            fail(ErrorCode::invalid_query,"prepared flop must be canonical");
        std::uint64_t result=0;
        for (const auto c:board) {
            if (c>=52 || !(deck_mask_&(std::uint64_t{1}<<c)) || (result&(std::uint64_t{1}<<c)))
                fail(ErrorCode::invalid_query,"duplicate or foreign prepared board card");
            result|=std::uint64_t{1}<<c;
        }
        return result;
    }
    std::uint64_t divisor(std::size_t n) const {
        if (n==0) return 1;
        const auto a=deck_.count-4;
        const auto flop=static_cast<std::uint64_t>(a*(a-1)*(a-2)/6);
        if (n==3) return flop;
        if (n==4) return flop*(deck_.count-7);
        return flop*(deck_.count-7)*(deck_.count-8);
    }
    static void bucket_add(Bucket& b,Hand hand,const Integer& value) {
        b.total+=value; b.cards[hand.first]+=value; b.cards[hand.second]+=value;
    }
    static Integer compatible(const Bucket& b,Hand hand,const Integer& same) {
        return b.total-b.cards[hand.first]-b.cards[hand.second]+same;
    }
    // Heap sort has explicit O(n log n) comparison/move bounds; indices retain
    // original row identity, including all unblocked zero-reach holdings.
    static void sort_order(Plane& plane,std::size_t p) {
        auto& order=plane.order[p]; const auto& ranks=plane.ranks[p];
        const auto less=[&](std::size_t a,std::size_t b) {
            return ranks[a]==ranks[b] ? a<b : ranks[a]<ranks[b];
        };
        std::make_heap(order.begin(),order.end(),less);
        std::sort_heap(order.begin(),order.end(),less);
    }
    static void validate_index_capacity(std::size_t capacity) {
        if (!capacity || capacity>64)
            fail(ErrorCode::invalid_limits,"invalid sorted rank index capacity");
    }
    [[nodiscard]] std::size_t index_position(std::uint64_t key) const noexcept {
        std::size_t lower=0,upper=index_->size;
        while (lower<upper) {
            const auto middle=lower+(upper-lower)/2;
            if (index_->entries[middle].key<key) lower=middle+1;
            else upper=middle;
        }
        return lower;
    }
    void publish_index(std::size_t slot,bool replacing,std::uint64_t previous,std::uint64_t key) {
        auto& index=*index_;
        if (replacing) {
            const auto old=index_position(previous);
            if (old>=index.size || index.entries[old].key!=previous || index.entries[old].slot!=slot)
                fail(ErrorCode::invalid_query,"sorted rank index lost its evicted plane");
            for (auto at=old+1;at<index.size;++at) index.entries[at-1]=index.entries[at];
            --index.size;
        }
        const auto position=index_position(key);
        if (index.size>=cache_.size() || (position<index.size && index.entries[position].key==key))
            fail(ErrorCode::invalid_query,"sorted rank index has a duplicate or excess plane");
        for (auto at=index.size;at>position;--at) index.entries[at]=index.entries[at-1];
        index.entries[position]={key,slot};
        ++index.size;
        ++index.updates;
    }
    std::size_t find_plane(std::span<const std::uint8_t> board,std::uint64_t blocked) {
        const auto matches=[&](std::size_t i) {
            if (rank_cache_key_==RankCacheKey::board_set) {
                charge(board_set_probe_work,receipt_.cache_lookup_work);
                return cache_[i].valid && std::bit_cast<std::uint64_t>(cache_[i].board_key)==blocked;
            }
            // One valid flag plus all five ordered public-card comparisons.
            charge(6,receipt_.cache_lookup_work);
            return cache_[i].valid && std::equal(board.begin(),board.end(),cache_[i].board_key.begin());
        };
        if (recent_!=missing && matches(recent_)) return recent_;
        if (index_) {
            // Reserve every possible binary-search probe and final slot check
            // before reading the index. A recent hit bypasses this reservation.
            const auto work=sorted_lookup_work(cache_.size())-board_set_probe_work;
            charge(work,receipt_.cache_lookup_work);
            index_->lookup_work+=work;
            ++index_->searches;
            const auto position=index_position(blocked);
            if (position==index_->size || index_->entries[position].key!=blocked) return missing;
            const auto slot=index_->entries[position].slot;
            if (slot>=cache_.size() || !cache_[slot].valid ||
                std::bit_cast<std::uint64_t>(cache_[slot].board_key)!=blocked)
                fail(ErrorCode::invalid_query,"sorted rank index returned a foreign plane");
            return slot;
        }
        for (std::size_t i=0;i<cache_.size();++i)
            if (i!=recent_ && matches(i)) return i;
        return missing;
    }
    std::size_t replacement() const {
        std::size_t oldest=0;
        for (std::size_t i=0;i<cache_.size();++i) {
            if (!cache_[i].valid) return i;
            if (cache_[i].stamp<cache_[oldest].stamp) oldest=i;
        }
        return oldest;
    }
    void fill_plane(std::size_t slot,std::span<const std::uint8_t> board,std::uint64_t blocked) {
        auto& plane=cache_[slot];
        const bool replacing=plane.valid;
        const auto previous=std::bit_cast<std::uint64_t>(plane.board_key);
        if (replacing && !index_) ++receipt_.cache_evictions;
        if (rank_cache_key_==RankCacheKey::board_set)
            plane.board_key=std::bit_cast<decltype(plane.board_key)>(blocked);
        else std::copy(board.begin(),board.end(),plane.board_key.begin());
        for (std::size_t p=0;p<2;++p) {
            const auto n=source_[p].size();
            plane.ranks[p].resize(n); plane.unblocked[p].resize(n);
            plane.order[p].clear(); plane.order[p].reserve(n);
            for (std::size_t i=0;i<n;++i) {
                const bool live=(masks_[p][i]&blocked)==0;
                plane.unblocked[p][i]=static_cast<unsigned char>(live);
                if (!live) continue;
                const auto hand=source_[p][i].hand;
                const std::array<std::uint8_t,7> cards{hand.first,hand.second,
                    board[0],board[1],board[2],board[3],board[4]};
                plane.ranks[p][i]=detail::rank_seven(cards);
                ++receipt_.rank_calls; plane.order[p].push_back(i);
            }
            sort_order(plane,p);
        }
        plane.valid=true;
        if (index_) {
            // All allocations and ranking have succeeded. Publication consists
            // only of the precharged bounded searches and POD shifts.
            publish_index(slot,replacing,previous,blocked);
            if (replacing) ++receipt_.cache_evictions;
        }
        ++receipt_.cache_misses;
    }
    Contraction contract(std::size_t player,std::span<const std::uint8_t> prefix,TerminalKind kind,
                         std::span<const Integer> reach,std::size_t exponent) {
        charge(12,receipt_.input_work);
        if (player>1 || (kind!=TerminalKind::fold && kind!=TerminalKind::showdown))
            fail(ErrorCode::invalid_query,"invalid prepared player or terminal kind");
        const auto opp=1-player;
        if (reach.size()!=source_[opp].size()) fail(ErrorCode::invalid_query,"prepared reach length mismatch");
        // 2^e is never constructed. Its potential e+1 width is admitted first.
        if (exponent>=limits_.max_integer_bits)
            fail(ErrorCode::integer_bit_limit,"prepared reach exponent exceeded");
        charge(6+prefix.size(),receipt_.input_work);
        const auto blocked=board_mask(prefix,kind);
        std::size_t active=0,own_live=0,max_weighted_bits=0;
        std::uint64_t products=0;
        for (std::size_t j=0;j<reach.size();++j) {
            charge(4,receipt_.input_work); // sign/top-limb width inspection
            const auto bits=width(reach[j]);
            if (bits>limits_.max_integer_bits)
                fail(ErrorCode::integer_bit_limit,"prepared reach numerator width exceeded");
            charge(2*words(bits),receipt_.input_work); // scans incl. exact power-of-two check
            if (reach[j]<0 || bits>exponent+1 ||
                (bits==exponent+1 && reach[j]!=0 &&
                 static_cast<std::size_t>(boost::multiprecision::lsb(reach[j]))!=exponent))
                fail(ErrorCode::invalid_query,"prepared reach must be in [0,2^e]");
            if (bits && !(masks_[opp][j]&blocked)) {
                ++active;
                max_weighted_bits=std::max(max_weighted_bits,weight_bits_[opp][j]+bits);
                products=add(products,multiply_cost(weight_bits_[opp][j],bits));
            }
        }
        for (const auto mask:masks_[player]) if (!(mask&blocked)) ++own_live;
        charge(2*source_[player].size(),receipt_.input_work);
        const bool zero=active==0 || own_live==0;
        const auto bucket_bits=zero ? std::size_t{1} : max_weighted_bits+lg(active)+4;
        const auto output_bits=zero ? std::size_t{1} : max_weight_bits_[player]+bucket_bits;
        const auto peak_bits=std::max({output_bits,bucket_bits,exponent+1});
        if (peak_bits>limits_.max_integer_bits)
            fail(ErrorCode::integer_bit_limit,"prepared contraction intermediate width exceeded");
        std::size_t slot=missing,cache_add=0;
        std::uint64_t rank_work=0,sort_work=0,cache_work=0,index_work=0;
        if (kind==TerminalKind::showdown) {
            slot=find_plane(prefix,blocked);
            if (slot==missing) {
                // LRU search, plane metadata/copies/zero initialization are
                // separate from rank evaluation and sort comparisons/moves.
                charge(4*cache_.size(),receipt_.cache_lookup_work);
                slot=replacement();
                if (!cache_[slot].valid) cache_add=8*total_hands();
                std::size_t all_live=0;
                for (const auto& side:masks_) for (const auto mask:side) if (!(mask&blocked)) ++all_live;
                // rank_seven: fixed 7-card, 15-rank, 4-suit loops. 4096
                // scalar units/rank conservatively cover every nested branch.
                rank_work=mul(4096,all_live);
                for (std::size_t p=0;p<2;++p)
                    sort_work=add(sort_work,mul(64*source_[p].size(),1+lg(source_[p].size())));
                cache_work=16+12*total_hands();
                if (index_) {
                    index_work=index_update_work(cache_.size());
                    cache_work=add(cache_work,index_work);
                }
            }
        }
        // Each live opposite row is inserted into all once, lower at most
        // once and equal at most once. Each own showdown row computes three
        // compatible masses (9 adds), high (2), signed delta (1), then one
        // own-weight product. Fold uses one compatible mass (3 adds).
        auto dynamic=static_cast<std::uint64_t>(source_[opp].size()+source_[player].size()+8);
        std::size_t scratch=source_[player].size()+16;
        std::uint64_t scratch_payload=mul(source_[player].size()+8,output_bits);
        const bool sparse=contraction_kernel_==ContractionKernel::sparse_pairs;
        if (!zero && sparse) {
            dynamic=sparse_pairs_dynamic_cost(source_[player].size(),source_[opp].size(),own_live,active,
                products,bucket_bits,output_bits,max_weight_bits_[player],kind);
            const auto temporary=sparse_pairs_scratch(source_[player].size(),active,
                max_weighted_bits,bucket_bits,output_bits);
            scratch=temporary.scratch_entries;
            scratch_payload=temporary.scratch_payload_bits;
        } else if (!zero) {
            const auto buckets=kind==TerminalKind::fold ? std::size_t{1} : 2+own_live;
            dynamic=add(dynamic,products);
            dynamic=add(dynamic,mul(53,buckets)); // cpp_int zero construction/reset
            dynamic=add(dynamic,mul((kind==TerminalKind::fold ? 3 : 9)*active,add_cost(bucket_bits)));
            for (std::size_t i=0;i<source_[player].size();++i) if (!(masks_[player][i]&blocked)) {
                dynamic=add(dynamic,mul(kind==TerminalKind::fold ? 3 : 12,add_cost(bucket_bits)));
                dynamic=add(dynamic,multiply_cost(weight_bits_[player][i],bucket_bits));
                dynamic=add(dynamic,copy_cost(output_bits)+2*words(bucket_bits));
            }
            dynamic=add(dynamic,32*total_hands()); // bounded rank-byte/index/zero comparisons
            scratch+=source_[opp].size()+159; // at most three simultaneous buckets
            scratch_payload=add(scratch_payload,mul(source_[opp].size(),max_weighted_bits));
            scratch_payload=add(scratch_payload,mul(159+8,bucket_bits));
        }
        // Stage all allocation and the complete query ledger before entering
        // arrays/ranking. No per-call payoff/proposal/general denominator or
        // generic maximum-width square is charged or computed here.
        if (cache_work) scratch+=128+2*lg(total_hands()); // ranker/heap scalar frames
        const auto work=add(dynamic,add(cache_work,add(rank_work,sort_work)));
        if (work>limits_.max_modeled_work-receipt_.modeled_work)
            fail(ErrorCode::modeled_work_limit,"prepared query work admission exceeded");
        admit(cache_add,0,scratch,static_cast<std::size_t>(scratch_payload),peak_bits);
        charge(dynamic,receipt_.contraction_work);
        charge(cache_work,receipt_.cache_lookup_work);
        if (index_) index_->update_work+=index_work;
        charge(rank_work,receipt_.rank_work); charge(sort_work,receipt_.sort_work);
        ++receipt_.query_array_admissions;
        if (kind==TerminalKind::showdown) {
            if (!rank_work && !sort_work && !cache_work) ++receipt_.cache_hits;
            else fill_plane(slot,prefix,blocked);
            cache_[slot].stamp=++clock_; recent_=slot;
        }
        Contraction out;
        out.prefix_divisor=divisor(prefix.size()); out.reach_exponent=exponent;
        out.numerators.resize(source_[player].size());
        if (zero) { ++receipt_.completed_contractions; return out; }
        if (sparse) {
            std::array<WeightedReach,2> weighted{};
            std::size_t used=0;
            for (std::size_t j=0;j<reach.size();++j) if (!(masks_[opp][j]&blocked) && reach[j]!=0) {
                weighted[used].row=j;
                weighted[used].mass=weights_[opp][j]*reach[j];
                ++used;
            }
            const auto live=std::span(weighted).first(used);
            if (kind==TerminalKind::fold) {
                for (std::size_t i=0;i<source_[player].size();++i) if (!(masks_[player][i]&blocked)) {
                    Integer mass=0;
                    for (const auto& row:live)
                        if (!(masks_[player][i]&masks_[opp][row.row])) mass+=row.mass;
                    out.numerators[i]=weights_[player][i]*mass;
                }
            } else {
                const auto& plane=cache_[slot];
                for (std::size_t i=0;i<source_[player].size();++i) if (!(masks_[player][i]&blocked)) {
                    Integer signed_mass=0;
                    const auto own_rank=plane.ranks[player][i];
                    for (const auto& row:live) {
                        if (masks_[player][i]&masks_[opp][row.row]) continue;
                        const auto other_rank=plane.ranks[opp][row.row];
                        if (other_rank<own_rank) signed_mass+=row.mass;
                        else if (own_rank<other_rank) signed_mass-=row.mass;
                    }
                    out.numerators[i]=weights_[player][i]*signed_mass;
                }
            }
            receipt_.sparse_pair_visits=add(receipt_.sparse_pair_visits,mul(own_live,active));
            ++receipt_.completed_contractions;
            return out;
        }
        std::vector<Integer> weighted(source_[opp].size());
        Bucket all;
        for (std::size_t j=0;j<reach.size();++j) if (!(masks_[opp][j]&blocked) && reach[j]!=0) {
            weighted[j]=weights_[opp][j]*reach[j];
            bucket_add(all,source_[opp][j].hand,weighted[j]);
        }
        const Integer empty=0;
        const auto same_at=[&](std::size_t i)->const Integer& {
            const auto j=same_[player][i]; return j==missing ? empty : weighted[j];
        };
        if (kind==TerminalKind::fold) {
            for (std::size_t i=0;i<source_[player].size();++i) if (!(masks_[player][i]&blocked))
                out.numerators[i]=weights_[player][i]*compatible(all,source_[player][i].hand,same_at(i));
        } else {
            const auto& plane=cache_[slot]; const auto& own=plane.order[player];
            const auto& opposite=plane.order[opp];
            Bucket lower; std::size_t pos=0,i=0;
            while (i<own.size()) {
                const auto rank=plane.ranks[player][own[i]];
                while (pos<opposite.size() && plane.ranks[opp][opposite[pos]]<rank) {
                    const auto j=opposite[pos++]; if (weighted[j]!=0) bucket_add(lower,source_[opp][j].hand,weighted[j]);
                }
                Bucket equal; auto end=pos;
                while (end<opposite.size() && plane.ranks[opp][opposite[end]]==rank) {
                    const auto j=opposite[end++]; if (weighted[j]!=0) bucket_add(equal,source_[opp][j].hand,weighted[j]);
                }
                while (i<own.size() && plane.ranks[player][own[i]]==rank) {
                    const auto row=own[i++]; const auto hand=source_[player][row].hand;
                    const auto j=same_[player][row];
                    const auto& same=same_at(row);
                    const auto& lo_same=j!=missing && plane.ranks[opp][j]<rank ? same : empty;
                    const auto& eq_same=j!=missing && plane.ranks[opp][j]==rank ? same : empty;
                    const Integer lo=compatible(lower,hand,lo_same);
                    const Integer hi=compatible(all,hand,same)-lo-compatible(equal,hand,eq_same);
                    if (hi<0) fail(ErrorCode::invalid_query,"negative prepared compatible mass");
                    out.numerators[row]=weights_[player][row]*(lo-hi);
                }
                while (pos<end) {
                    const auto j=opposite[pos++]; if (weighted[j]!=0) bucket_add(lower,source_[opp][j].hand,weighted[j]);
                }
            }
        }
        ++receipt_.completed_contractions; return out;
    }
public:
    static constexpr std::uint64_t board_set_probe_work=2;
    [[nodiscard]] static std::uint64_t sorted_lookup_work(std::size_t capacity) {
        validate_index_capacity(capacity);
        return add(6,mul(8,std::bit_width(capacity)));
    }
    [[nodiscard]] static std::uint64_t index_update_work(std::size_t capacity) {
        validate_index_capacity(capacity);
        return add(add(mul(8,capacity),mul(16,std::bit_width(capacity))),32);
    }
    [[nodiscard]] static std::uint64_t index_setup_work(std::size_t capacity) {
        validate_index_capacity(capacity);
        return add(mul(4,capacity),16);
    }
    [[nodiscard]] static std::size_t index_storage_entries(std::size_t capacity) {
        validate_index_capacity(capacity);
        return static_cast<std::size_t>(add(index_fixed_entries,mul(index_entry_words,capacity)));
    }
    // Charges every live pair for blocker/rank checks and a possible signed
    // accumulation, plus the caller's summed weighted-product bound, one
    // own-weight multiply per live own row, and output initialization.
    [[nodiscard]] static std::uint64_t sparse_pairs_dynamic_cost(
            std::size_t own_rows,std::size_t opponent_rows,std::size_t own_live,std::size_t active,
            std::uint64_t weighted_product_work,std::size_t signed_mass_bits,
            std::size_t output_bits,std::size_t max_own_weight_bits,TerminalKind kind) {
        if (kind!=TerminalKind::fold && kind!=TerminalKind::showdown)
            fail(ErrorCode::invalid_query,"invalid sparse terminal kind");
        if (own_rows>2 || opponent_rows>2 || own_live>own_rows || active>opponent_rows ||
            !signed_mass_bits || !output_bits || signed_mass_bits>65536 || output_bits>65536 ||
            max_own_weight_bits>65536)
            fail(ErrorCode::invalid_query,"invalid sparse cost dimensions");
        auto work=add(add(own_rows,opponent_rows),8);
        work=add(work,weighted_product_work);
        const auto pairs=mul(own_live,active);
        work=add(work,mul(pairs,kind==TerminalKind::showdown?16:8));
        work=add(work,mul(pairs,add_cost(signed_mass_bits)));
        work=add(work,mul(own_live,multiply_cost(max_own_weight_bits,signed_mass_bits)));
        work=add(work,mul(own_rows,copy_cost(output_bits)+2));
        return work;
    }
private:
    // Bound the output, fixed two-row scratch, live operands and temporaries.
    [[nodiscard]] static SparsePairCost sparse_pairs_scratch(
            std::size_t own_rows,std::size_t active,std::size_t max_weighted_bits,
            std::size_t signed_mass_bits,std::size_t output_bits) {
        const auto bits=add(add(mul(add(own_rows,4),output_bits),mul(active,max_weighted_bits)),
            mul(4,signed_mass_bits));
        return {own_rows+18,bits};
    }
public:
    PreparedPublicChance(std::span<const WeightedHand> sb,std::span<const WeightedHand> bb,
                         DeckDefinition deck=DeckDefinition::full52(),Limits limits={},
                         std::size_t cache_capacity=64,RankCacheKey rank_cache_key=RankCacheKey::ordered_prefix,
                         ContractionKernel contraction_kernel=ContractionKernel::blocker_buckets,
                         RankCacheIndex cache_index=RankCacheIndex::linear)
        :limits_(limits),deck_(deck),rank_cache_key_(rank_cache_key),contraction_kernel_(contraction_kernel) {
        if (!limits.max_hands_per_side || limits.max_hands_per_side>1326 ||
            !limits.max_integer_bits || limits.max_integer_bits>65536 ||
            !limits.max_modeled_work || limits.max_modeled_work>500'000'000 ||
            !limits.max_storage_entries || limits.max_storage_entries>2'000'000 ||
            !limits.max_integer_payload_bits || limits.max_integer_payload_bits>(std::size_t{1}<<30) ||
            !cache_capacity || cache_capacity>64 ||
            (contraction_kernel_!=ContractionKernel::blocker_buckets &&
             contraction_kernel_!=ContractionKernel::sparse_pairs) ||
            (contraction_kernel_==ContractionKernel::sparse_pairs && limits.max_hands_per_side>2) ||
            (rank_cache_key_!=RankCacheKey::ordered_prefix && rank_cache_key_!=RankCacheKey::board_set) ||
            (cache_index!=RankCacheIndex::linear && cache_index!=RankCacheIndex::sorted_board_set) ||
            (cache_index==RankCacheIndex::sorted_board_set && rank_cache_key_!=RankCacheKey::board_set))
            fail(ErrorCode::invalid_limits,"invalid prepared reduce-only limits");
        charge(16,receipt_.setup_work);
        if (sb.empty() || bb.empty() || sb.size()>limits.max_hands_per_side || bb.size()>limits.max_hands_per_side)
            fail(ErrorCode::invalid_input,"invalid prepared range dimensions");
        const auto h=sb.size()+bb.size();
        charge(6*h,receipt_.setup_work); // bounded immutable input snapshot
        admit(3*h+64,0,0,0,1);
        source_[0].assign(sb.begin(),sb.end()); source_[1].assign(bb.begin(),bb.end());
        auto remaining=limits;
        if (receipt_.modeled_work>=limits.max_modeled_work || receipt_.retained_entries>=limits.max_storage_entries)
            fail(ErrorCode::modeled_work_limit,"prepared prior allowance exhausted");
        remaining.max_modeled_work-=receipt_.modeled_work;
        remaining.max_storage_entries-=receipt_.retained_entries;
        prior_=std::make_unique<const chance::PublicChanceKernel>(source_[0],source_[1],deck_,remaining);
        const auto& previous=prior_->receipt();
        charge(previous.modeled_work,receipt_.prior_work);
        admit(previous.retained_entries,previous.setup_integer_payload_bits,
            previous.peak_scratch_entries,0,previous.peak_integer_bits);
        receipt_.peak_integer_payload_bits=std::max(receipt_.peak_integer_payload_bits,previous.peak_integer_payload_bits);
        for (std::size_t i=0;i<deck_.count;++i) deck_mask_|=std::uint64_t{1}<<deck_.cards[i];
        const auto exponents=prior_->weight_denominator_exponents();
        std::array<std::size_t,2> cancel{missing,missing};
        std::size_t raw_weight_bits=1;
        charge(24*h+16,receipt_.setup_work); // two decode/width passes, deck scan
        for (std::size_t p=0;p<2;++p) for (const auto& row:source_[p]) {
            const auto d=detail::decode_parts(row.binary64_weight_bits,false,false,"validated prepared weight");
            const auto shift=d.exponent+exponents[p];
            cancel[p]=std::min(cancel[p],static_cast<std::size_t>(std::countr_zero(d.significand)+shift));
            raw_weight_bits=std::max(raw_weight_bits,static_cast<std::size_t>(std::bit_width(d.significand)+shift));
        }
        const auto original_bits=width(prior_->normalizer_integer());
        const auto removal=cancel[0]+cancel[1];
        if (removal>=original_bits) fail(ErrorCode::invalid_query,"invalid normalized prior width");
        const auto normalizer_bits=original_bits-removal;
        std::uint64_t weight_payload=normalizer_bits;
        for (std::size_t p=0;p<2;++p) for (const auto& row:source_[p]) {
            const auto d=detail::decode_parts(row.binary64_weight_bits,false,false,"validated prepared weight");
            const auto bits=static_cast<std::size_t>(std::bit_width(d.significand)+d.exponent+exponents[p])-cancel[p];
            max_weight_bits_[p]=std::max(max_weight_bits_[p],bits);
            weight_payload=add(weight_payload,bits);
        }
        const auto setup_work=add(6*sb.size()*bb.size(),
            add(mul(6*h,copy_cost(raw_weight_bits)),4*words(original_bits)+copy_cost(original_bits)));
        charge(setup_work,receipt_.setup_work);
        const bool indexed=cache_index==RankCacheIndex::sorted_board_set;
        if (indexed) charge(index_setup_work(cache_capacity),receipt_.setup_work);
        const auto index_entries=indexed?index_storage_entries(cache_capacity):0;
        admit(4*h+16*cache_capacity+32+index_entries,static_cast<std::size_t>(weight_payload),16,
            static_cast<std::size_t>(mul(4,std::max(original_bits,raw_weight_bits))),
            std::max(original_bits,raw_weight_bits));
        if (static_cast<std::size_t>(boost::multiprecision::lsb(prior_->normalizer_integer()))<removal)
            fail(ErrorCode::invalid_query,"prior normalizer is not exactly divisible");
        normalizer_=prior_->normalizer_integer()>>removal;
        for (std::size_t p=0;p<2;++p) {
            const auto n=source_[p].size();
            weights_[p].reserve(n); weight_bits_[p].reserve(n); masks_[p].reserve(n);
            same_[p].assign(n,missing);
            for (const auto& row:source_[p]) {
                const auto d=detail::decode_parts(row.binary64_weight_bits,false,false,"validated prepared weight");
                const auto shift=d.exponent+exponents[p]-static_cast<int>(cancel[p]);
                Integer value=d.significand;
                if (shift<0) value>>=static_cast<unsigned>(-shift); else value<<=static_cast<unsigned>(shift);
                weight_bits_[p].push_back(width(value)); weights_[p].push_back(std::move(value));
                masks_[p].push_back(hand_mask(row.hand));
            }
        }
        for (std::size_t i=0;i<source_[0].size();++i) for (std::size_t j=0;j<source_[1].size();++j)
            if (masks_[0][i]==masks_[1][j]) { same_[0][i]=j; same_[1][j]=i; }
        cache_.resize(cache_capacity);
        if (indexed) {
            index_=std::make_unique<RankIndex>();
            index_->entries=std::make_unique<IndexEntry[]>(cache_capacity);
            index_->setup_work=index_setup_work(cache_capacity);
        }
    }
    PreparedPublicChance(const PreparedPublicChance&)=delete;
    PreparedPublicChance& operator=(const PreparedPublicChance&)=delete;
    PreparedPublicChance(PreparedPublicChance&&)=delete;
    PreparedPublicChance& operator=(PreparedPublicChance&&)=delete;
    [[nodiscard]] Contraction contraction(std::size_t player,std::span<const std::uint8_t> prefix,
            TerminalKind kind,std::span<const Integer> opposite_numerators,std::size_t reach_exponent) {
        if (failed_) fail(ErrorCode::invalid_query,"prepared owner is poisoned");
        try { return contract(player,prefix,kind,opposite_numerators,reach_exponent); }
        catch (...) { failed_=true; throw; }
    }
    [[nodiscard]] const Integer& normalizer_integer() const noexcept { return normalizer_; }
    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }
    [[nodiscard]] const chance::Receipt& prior_receipt() const noexcept { return prior_->receipt(); }
    [[nodiscard]] RankIndexReceipt rank_index_receipt() const noexcept {
        if (!index_) return {};
        return {cache_.size(),index_fixed_entries+index_entry_words*cache_.size(),index_->size,
            index_->searches,index_->updates,index_->lookup_work,index_->update_work,index_->setup_work};
    }
    [[nodiscard]] bool failed() const noexcept { return failed_; }
private:
    Limits limits_{}; DeckDefinition deck_{};
    const RankCacheKey rank_cache_key_;
    const ContractionKernel contraction_kernel_;
    Receipt receipt_{}; bool failed_=false;
    std::uint64_t deck_mask_=0,clock_=0;
    std::array<std::vector<WeightedHand>,2> source_;
    std::unique_ptr<const chance::PublicChanceKernel> prior_;
    std::array<std::vector<Integer>,2> weights_;
    std::array<std::vector<std::size_t>,2> weight_bits_,same_;
    std::array<std::vector<std::uint64_t>,2> masks_;
    std::array<std::size_t,2> max_weight_bits_{};
    Integer normalizer_=0;
    std::vector<Plane> cache_;
    std::unique_ptr<RankIndex> index_;
    std::size_t recent_=missing;
    [[nodiscard]] std::size_t total_hands() const noexcept { return source_[0].size()+source_[1].size(); }
};
} // namespace openpoker::prepared_public_chance
