#pragma once

// Exact public-prefix/full-board chance seam for a finite declared deck.
// This is not a sampler, trainer, policy router, CPU bound, or RSS model.
#include "exact_selected_kernel.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <utility>
#include <vector>

namespace openpoker::full_deck_public_chance {
using Integer = exact_selected_kernel::Integer;
using Hand = exact_selected_kernel::Hand;
using WeightedHand = exact_selected_kernel::WeightedHand;
using TerminalKind = exact_selected_kernel::TerminalKind;
using ErrorCode = exact_selected_kernel::ErrorCode;
using KernelError = exact_selected_kernel::KernelError;
namespace prior = exact_selected_kernel::detail;

enum class DeckMode { full52, reduced_proof };
struct DeckDefinition {
    DeckMode mode = DeckMode::full52;
    std::array<std::uint8_t, 52> cards{};
    std::size_t count = 0;
    static DeckDefinition full52() {
        DeckDefinition d; d.count = 52;
        for (std::size_t i = 0; i < 52; ++i) d.cards[i] = static_cast<std::uint8_t>(i);
        return d;
    }
    static DeckDefinition reduced(std::span<const std::uint8_t> cards_in) {
        if (cards_in.size() < 9 || cards_in.size() > 52)
            throw KernelError(ErrorCode::invalid_input, "deck size must be between nine and 52");
        DeckDefinition d; d.mode = DeckMode::reduced_proof; d.count = cards_in.size();
        for (std::size_t i = 0; i < cards_in.size(); ++i) {
            if (cards_in[i] >= 52 || (i && cards_in[i - 1] >= cards_in[i]))
                throw KernelError(ErrorCode::invalid_input, "deck ids must be strictly sorted physical cards");
            d.cards[i] = cards_in[i];
        }
        return d;
    }
};
struct Limits {
    std::size_t max_hands_per_side = 1326;
    std::size_t max_integer_bits = 65536;
    std::uint64_t max_modeled_work = 500'000'000;
    std::size_t max_storage_entries = 2'000'000;
    std::size_t max_integer_payload_bits = std::size_t{1} << 30;
};
struct ExactVector { std::vector<Integer> numerators; Integer denominator = 1; };
struct PrefixResult {
    std::array<ExactVector, 2> hand_masses;
    Integer total_numerator = 0;
    Integer denominator = 1;
    std::array<std::vector<bool>, 2> physical_support;
};
struct Receipt {
    std::uint64_t modeled_work = 0;
    std::size_t retained_entries = 0;
    std::size_t peak_scratch_entries = 0;
    std::size_t peak_integer_bits = 0;
    std::size_t setup_integer_payload_bits = 0;
    std::size_t peak_integer_payload_bits = 0;
    std::size_t prefix_queries = 0;
    std::size_t terminal_queries = 0;
    std::size_t rank_calls = 0;
    std::size_t conversion_calls = 0;
};

class PublicChanceKernel final {
    struct Bucket { Integer total = 0; std::array<Integer, 52> cards{}; };
    struct Row { prior::Rank rank; std::size_t index; };
    static constexpr std::size_t missing = std::numeric_limits<std::size_t>::max();
    [[noreturn]] static void fail(ErrorCode c, const char* message) { throw KernelError(c, message); }
    static std::size_t width(const Integer& v) { return prior::magnitude_bits(v); }
    static std::size_t log2ceil(std::size_t n) {
        return n <= 1 ? 0 : static_cast<std::size_t>(std::bit_width(n - 1));
    }
    static std::uint64_t mask(Hand h) { return (std::uint64_t{1} << h.first) | (std::uint64_t{1} << h.second); }
    static std::size_t key(Hand h) { return static_cast<std::size_t>(h.first) * 52 + h.second; }
    static void add_bucket(Bucket& b, Hand h, const Integer& v) {
        b.total += v; b.cards[h.first] += v; b.cards[h.second] += v;
    }
    static Integer compatible(const Bucket& b, Hand h, const Integer& same) {
        return b.total - b.cards[h.first] - b.cards[h.second] + same;
    }
    void charge(std::uint64_t cost) {
        if (cost > limits_.max_modeled_work - receipt_.modeled_work)
            fail(ErrorCode::modeled_work_limit, "full-deck modeled work admission exceeded");
        receipt_.modeled_work += cost;
    }
    void reserve_query(std::uint64_t work, std::size_t entries, std::size_t bits) {
        if (bits > limits_.max_integer_bits)
            fail(ErrorCode::integer_bit_limit, "full-deck integer width admission exceeded");
        if (entries > limits_.max_storage_entries - receipt_.retained_entries)
            fail(ErrorCode::storage_limit, "full-deck query entries admission exceeded");
        const auto payload = prior::checked_mul_count(entries, std::max<std::size_t>(bits, 1));
        if (payload > limits_.max_integer_payload_bits - receipt_.setup_integer_payload_bits)
            fail(ErrorCode::integer_payload_limit, "full-deck query integer payload admission exceeded");
        charge(work);
        receipt_.peak_scratch_entries = std::max(receipt_.peak_scratch_entries, entries);
        receipt_.peak_integer_bits = std::max(receipt_.peak_integer_bits, bits);
        receipt_.peak_integer_payload_bits = std::max(receipt_.peak_integer_payload_bits,
            receipt_.setup_integer_payload_bits + static_cast<std::size_t>(payload));
    }
    std::uint64_t board_mask(std::span<const std::uint8_t> board, bool full) const {
        const auto n = board.size();
        if ((full && n != 5) || (!full && n != 0 && n != 3 && n != 4 && n != 5))
            fail(ErrorCode::invalid_query, "invalid visible board length");
        if (n >= 3 && !(board[0] < board[1] && board[1] < board[2]))
            fail(ErrorCode::invalid_query, "flop must be canonical card order");
        std::uint64_t result = 0;
        for (const auto c : board) {
            if (c >= 52 || !(deck_mask_ & (std::uint64_t{1} << c)) || (result & (std::uint64_t{1} << c)))
                fail(ErrorCode::invalid_query, "duplicate or foreign board card");
            result |= std::uint64_t{1} << c;
        }
        return result;
    }
    std::uint64_t divisor(std::size_t n) const {
        if (n == 0) return 1;
        const std::uint64_t a = deck_.count - 4;
        const std::uint64_t flop = a * (a - 1) * (a - 2) / 6;
        if (n == 3) return flop;
        if (n == 4) return flop * (deck_.count - 7);
        return flop * (deck_.count - 7) * (deck_.count - 8);
    }
    Integer same_value(std::size_t own, std::size_t i, const std::vector<Integer>& values,
                       const std::vector<unsigned char>& active) const {
        const auto j = same_[own][i];
        return j != missing && active[j] ? values[j] : Integer(0);
    }
    // All reach front doors enter the same admitted blocker/rank evaluator.
    // `factor` already includes the old dyadic reach exponent on the double path.
    template<class ReachAt>
    [[nodiscard]] ExactVector terminal_integer_values(std::size_t player,
            std::span<const std::uint8_t> board, TerminalKind kind,
            std::uint64_t blocked, bool any, const Integer& pay_sig, int factor,
            const Integer& reach_denominator, const Integer& proposal_num,
            const Integer& proposal_den, std::uint64_t chance_divisor, ReachAt&& reach_at) {
        const auto opp = 1-player;
        std::vector<Integer> weighted(hands_[opp].size());
        std::vector<unsigned char> active(hands_[opp].size());
        for (std::size_t j=0;j<hands_[opp].size();++j) {
            if (mask(hands_[opp][j]) & blocked) continue;
            const auto& reach = reach_at(j);
            if (reach == 0) continue;
            weighted[j]=weights_[opp][j]*reach;
            active[j]=1;
        }
        ExactVector out;
        out.denominator=normalizer_*chance_divisor*proposal_num;
        if (reach_denominator != 1) out.denominator *= reach_denominator;
        if (factor<0) out.denominator <<= static_cast<unsigned>(-factor);
        out.numerators.resize(hands_[player].size());
        Bucket all;
        for (std::size_t j=0;j<hands_[opp].size();++j)
            if (active[j]) add_bucket(all,hands_[opp][j],weighted[j]);
        if (kind==TerminalKind::fold) {
            for (std::size_t i=0;i<hands_[player].size();++i) {
                const auto hand=hands_[player][i];
                if (mask(hand)&blocked) continue;
                Integer value=weights_[player][i]*compatible(all,hand,same_value(player,i,weighted,active));
                value*=pay_sig; value*=proposal_den;
                if (factor>0) value <<= static_cast<unsigned>(factor);
                out.numerators[i]=std::move(value);
            }
        } else if (pay_sig != 0 && any) {
            std::array<std::uint8_t,5> public_cards{};
            std::copy(board.begin(),board.end(),public_cards.begin());
            std::vector<Row> opponents,own;
            std::vector<prior::Rank> ranks(hands_[opp].size());
            opponents.reserve(hands_[opp].size()); own.reserve(hands_[player].size());
            auto hand_rank=[&](Hand hand) {
                std::array<std::uint8_t,7> all_cards{hand.first,hand.second,
                    public_cards[0],public_cards[1],public_cards[2],public_cards[3],public_cards[4]};
                ++receipt_.rank_calls; return prior::rank_seven(all_cards);
            };
            for (std::size_t j=0;j<hands_[opp].size();++j) if (active[j]) {
                ranks[j]=hand_rank(hands_[opp][j]); opponents.push_back(Row{ranks[j],j});
            }
            for (std::size_t i=0;i<hands_[player].size();++i)
                if (!(mask(hands_[player][i]) & blocked)) own.push_back(Row{hand_rank(hands_[player][i]),i});
            const auto less=[](const Row& a,const Row& b) {
                return a.rank==b.rank ? a.index<b.index : a.rank<b.rank;
            };
            std::sort(opponents.begin(),opponents.end(),less);std::sort(own.begin(),own.end(),less);
            Bucket lower; std::size_t pos=0, i=0;
            while (i<own.size()) {
                const auto rank=own[i].rank;
                while (pos<opponents.size() && opponents[pos].rank<rank) {
                    const auto j=opponents[pos++].index; add_bucket(lower,hands_[opp][j],weighted[j]);
                }
                Bucket equal; auto end=pos;
                while (end<opponents.size() && opponents[end].rank==rank) {
                    const auto j=opponents[end++].index;add_bucket(equal,hands_[opp][j],weighted[j]);
                }
                while (i<own.size() && own[i].rank==rank) {
                    const auto row=own[i++].index;const auto hand=hands_[player][row];const auto j=same_[player][row];
                    Integer allsame=0, lowsame=0, equalsame=0;
                    if (j!=missing && active[j]) {
                        allsame=weighted[j];
                        if (ranks[j]<rank) lowsame=weighted[j];
                        else if (ranks[j]==rank) equalsame=weighted[j];
                    }
                    const Integer lo=compatible(lower,hand,lowsame);
                    const Integer hi=compatible(all,hand,allsame)-lo-compatible(equal,hand,equalsame);
                    if (hi<0) fail(ErrorCode::invalid_query,"negative blocker-compatible rank mass");
                    Integer value=weights_[player][row]*(lo-hi);
                    value*=pay_sig;value*=proposal_den;
                    if (factor>0) value <<= static_cast<unsigned>(factor);
                    out.numerators[row]=std::move(value);
                }
                while (pos<end) {
                    const auto j=opponents[pos++].index;add_bucket(lower,hands_[opp][j],weighted[j]);
                }
            }
        }
        ++receipt_.terminal_queries; return out;
    }
    // Shared exact input validation/admission precedes query arrays and ranking.
    [[nodiscard]] ExactVector exact_reach_values(std::size_t player,
            std::span<const std::uint8_t> board, TerminalKind kind, double payoff,
            std::span<const Integer> reach_numerators, const Integer& reach_denominator,
            const Integer& proposal_num, const Integer& proposal_den, bool full_board) {
        if (player > 1 || (kind != TerminalKind::fold && kind != TerminalKind::showdown))
            fail(ErrorCode::invalid_query,"invalid exact-reach terminal player or kind");
        const auto opp=1-player;
        if (reach_numerators.size()!=hands_[opp].size())
            fail(ErrorCode::invalid_query,"exact opponent reach length mismatch");
        charge(128 + 32 * hands_[opp].size());
        const auto blocked=board_mask(board,full_board);
        const auto qn=width(proposal_num), qd=width(proposal_den);
        const auto rd=width(reach_denominator);
        if (std::max({qn,qd,rd}) > limits_.max_integer_bits)
            fail(ErrorCode::integer_bit_limit,"exact reach/proposal width exceeded");
        // Charge width-dependent comparisons before entering them, including
        // invalid/rejected input. These charges remain on the same owner.
        charge(prior::checked_mul_count(16,std::max({qn,qd,rd,std::size_t{1}})));
        if (proposal_num<=0 || proposal_den<=0 || proposal_num>proposal_den || reach_denominator<=0)
            fail(ErrorCode::invalid_query,"invalid exact reach/proposal denominator or probability");
        bool any=false;
        std::size_t max_reach_bits=0;
        for (const auto& value:reach_numerators) {
            const auto n=width(value);
            if (n>limits_.max_integer_bits)
                fail(ErrorCode::integer_bit_limit,"exact reach numerator width exceeded");
            charge(prior::checked_mul_count(16,prior::checked_add_count(n,rd)));
            if (value<0 || value>reach_denominator)
                fail(ErrorCode::invalid_query,"exact reach must lie between zero and one");
            any=any || value!=0;
            max_reach_bits=std::max(max_reach_bits,n);
        }
        const auto paybits=std::bit_cast<std::uint64_t>(payoff);
        const auto pay=prior::decode_parts(paybits,true,true,"invalid exact-reach terminal payoff");
        if (kind==TerminalKind::showdown && (paybits>>63) && pay.significand)
            fail(ErrorCode::invalid_dyadic,"showdown stake must be nonnegative");
        const auto h=hands_[0].size()+hands_[1].size();
        const auto pay_width=pay.significand ? static_cast<std::size_t>(64-std::countl_zero(pay.significand)) : 1U;
        const auto opp_sum=weight_bits_[opp]+max_reach_bits+log2ceil(hands_[opp].size())+6;
        const auto num_bits=weight_bits_[player]+opp_sum+pay_width+qd+
            static_cast<std::size_t>(std::max(0,pay.exponent))+12;
        const auto den_bits=normalizer_bits_+log2ceil(divisor(board.size())+1)+qn+rd+
            static_cast<std::size_t>(std::max(0,-pay.exponent))+8;
        const auto bits=std::max({num_bits,den_bits,qn,qd,rd,std::size_t{53}});
        const auto sorting=prior::checked_mul_count(64*h,1+log2ceil(h));
        // Logical 64-bit word-width-product accounting, not Boost allocation,
        // machine instruction count or elapsed time. Retain all old charges;
        // exact input scans and quadratic-width arithmetic are additional.
        const auto words=prior::checked_add_count(bits,63)/64;
        const auto word_work=prior::checked_mul_count(4096+64*h,
            prior::checked_mul_count(words,words));
        const auto work=prior::checked_add_count(4096+512*h,
            prior::checked_add_count(sorting,word_work));
        reserve_query(work,24*h+2048,bits);
        Integer pay_sig=pay.significand;
        if ((paybits>>63) && pay_sig!=0) pay_sig=-pay_sig;
        return terminal_integer_values(player,board,kind,blocked,any,pay_sig,pay.exponent,
            reach_denominator,proposal_num,proposal_den,divisor(board.size()),[&](std::size_t j) -> const Integer& {
                return reach_numerators[j];
            });
    }

public:
    PublicChanceKernel(std::span<const WeightedHand> sb, std::span<const WeightedHand> bb,
                       DeckDefinition deck = DeckDefinition::full52(), Limits limits = {})
        : deck_(deck), limits_(limits) {
        if (!limits_.max_hands_per_side || limits_.max_hands_per_side > 1326 ||
            !limits_.max_integer_bits || limits_.max_integer_bits > 65536 ||
            !limits_.max_modeled_work || limits_.max_modeled_work > 500'000'000 ||
            !limits_.max_storage_entries || limits_.max_storage_entries > 2'000'000 ||
            !limits_.max_integer_payload_bits || limits_.max_integer_payload_bits > (std::size_t{1} << 30))
            fail(ErrorCode::invalid_limits, "invalid reduce-only full-deck limits");
        if (deck_.count < 9 || deck_.count > 52 || sb.empty() || bb.empty() ||
            sb.size() > limits_.max_hands_per_side || bb.size() > limits_.max_hands_per_side)
            fail(ErrorCode::invalid_input, "invalid deck or range dimensions");
        charge(1024); // bounded deck validation before scanning its cards
        if ((deck_.mode != DeckMode::full52 && deck_.mode != DeckMode::reduced_proof) ||
            (deck_.mode == DeckMode::full52 && deck_.count != 52))
            fail(ErrorCode::invalid_input, "invalid declared deck mode");
        for (std::size_t i = 0; i < deck_.count; ++i) {
            const auto c = deck_.cards[i];
            if (c >= 52 || (i && deck_.cards[i - 1] >= c))
                fail(ErrorCode::invalid_input, "invalid canonical deck");
            deck_mask_ |= std::uint64_t{1} << c;
        }
        const std::array<std::span<const WeightedHand>,2> input{sb,bb};
        const auto h = sb.size() + bb.size();
        const auto retained = 8 * h + 256;
        const auto scratch = 8 * h + 6000;
        if (retained > limits_.max_storage_entries || scratch > limits_.max_storage_entries - retained)
            fail(ErrorCode::storage_limit, "full-deck constructor entry admission exceeded");
        charge(1024 * h + 16384);
        std::array<std::array<std::size_t, 2704>, 2> lookup{};
        for (auto& side : lookup) side.fill(missing);
        std::array<int,2> common{};
        std::array<std::size_t,2> weight_bits{};
        for (std::size_t p = 0; p < 2; ++p) {
            common[p] = std::numeric_limits<int>::max();
            for (std::size_t i = 0; i < input[p].size(); ++i) {
                const auto& row = input[p][i]; const auto hand = row.hand;
                if (hand.first >= hand.second || hand.second >= 52 ||
                    !(deck_mask_ & (std::uint64_t{1} << hand.first)) ||
                    !(deck_mask_ & (std::uint64_t{1} << hand.second)))
                    fail(ErrorCode::invalid_input, "holding must contain canonical declared-deck cards");
                if (lookup[p][key(hand)] != missing)
                    fail(ErrorCode::duplicate_hand, "duplicate physical holding");
                lookup[p][key(hand)] = i;
                const auto d = prior::decode_parts(row.binary64_weight_bits, false, false, "invalid positive weight");
                common[p] = std::min(common[p], d.exponent);
            }
            for (const auto& row : input[p]) {
                const auto d = prior::decode_parts(row.binary64_weight_bits, false, false, "invalid positive weight");
                weight_bits[p] = std::max(weight_bits[p], static_cast<std::size_t>(64 - std::countl_zero(d.significand)) +
                    static_cast<std::size_t>(d.exponent - common[p]));
            }
        }
        const auto setup_bits = weight_bits[0] + weight_bits[1] + log2ceil(sb.size()) + log2ceil(bb.size()) + 8;
        if (setup_bits > limits_.max_integer_bits)
            fail(ErrorCode::integer_bit_limit, "full-deck constructor integer width exceeded");
        const auto setup_payload = prior::checked_mul_count(8 * h + 512, std::max<std::size_t>(setup_bits, 53));
        if (setup_payload > limits_.max_integer_payload_bits)
            fail(ErrorCode::integer_payload_limit, "full-deck constructor integer payload exceeded");
        receipt_.retained_entries = retained; receipt_.peak_scratch_entries = scratch;
        receipt_.setup_integer_payload_bits = static_cast<std::size_t>(setup_payload);
        receipt_.peak_integer_payload_bits = receipt_.setup_integer_payload_bits;
        receipt_.peak_integer_bits = setup_bits;
        for (std::size_t p = 0; p < 2; ++p) {
            hands_[p].reserve(input[p].size()); weights_[p].reserve(input[p].size()); same_[p].reserve(input[p].size());
            for (const auto& row : input[p]) {
                const auto d = prior::decode_parts(row.binary64_weight_bits, false, false, "invalid positive weight");
                hands_[p].push_back(row.hand);
                weights_[p].push_back(Integer(d.significand) << static_cast<unsigned>(d.exponent - common[p]));
                same_[p].push_back(lookup[1-p][key(row.hand)]);
            }
        }
        weight_bits_ = weight_bits; denominator_exponents_ = {-common[0],-common[1]};
        Bucket bucket;
        for (std::size_t j = 0; j < hands_[1].size(); ++j) add_bucket(bucket, hands_[1][j], weights_[1][j]);
        for (std::size_t i = 0; i < hands_[0].size(); ++i) {
            const auto j = same_[0][i];
            const Integer addback = j == missing ? Integer(0) : weights_[1][j];
            normalizer_ += weights_[0][i] * compatible(bucket, hands_[0][i], addback);
        }
        if (normalizer_ <= 0) fail(ErrorCode::no_compatible_deals, "ranges have no compatible deals");
        normalizer_bits_ = width(normalizer_);
    }
    [[nodiscard]] PrefixResult prefix(std::span<const std::uint8_t> board) {
        charge(64); // fixed prefix grammar scan precedes all query allocations
        const auto blocked = board_mask(board, false); const auto h = hands_[0].size()+hands_[1].size();
        const auto bits = std::max(normalizer_bits_ + log2ceil(divisor(board.size()) + 1) + 2,
            weight_bits_[0] + weight_bits_[1] + log2ceil(hands_[0].size()) + log2ceil(hands_[1].size()) + 8);
        reserve_query(512 + 128 * h, 12 * h + 1024, bits);
        PrefixResult out; out.denominator = normalizer_ * divisor(board.size());
        for (std::size_t p = 0; p < 2; ++p) {
            const auto opp=1-p; Bucket bucket;
            for (std::size_t j=0;j<hands_[opp].size();++j)
                if (!(mask(hands_[opp][j]) & blocked)) add_bucket(bucket,hands_[opp][j],weights_[opp][j]);
            out.hand_masses[p].denominator=out.denominator;
            out.hand_masses[p].numerators.resize(hands_[p].size());
            out.physical_support[p].resize(hands_[p].size());
            for (std::size_t i=0;i<hands_[p].size();++i) {
                if (mask(hands_[p][i]) & blocked) continue;
                const auto j=same_[p][i];
                const Integer addback=j==missing ? Integer(0) : weights_[opp][j];
                Integer mass=weights_[p][i]*compatible(bucket,hands_[p][i],addback);
                out.physical_support[p][i]=mass>0;
                out.hand_masses[p].numerators[i]=std::move(mass);
            }
        }
        for (const auto& x : out.hand_masses[0].numerators) out.total_numerator+=x;
        ++receipt_.prefix_queries; return out;
    }
    [[nodiscard]] ExactVector terminal(std::size_t player, std::span<const std::uint8_t> board,
            TerminalKind kind, double payoff, std::span<const double> opponent_reach,
            const Integer& proposal_num, const Integer& proposal_den) {
        if (player > 1 || (kind != TerminalKind::fold && kind != TerminalKind::showdown))
            fail(ErrorCode::invalid_query, "invalid terminal player or kind");
        const auto opp=1-player;
        if (opponent_reach.size()!=hands_[opp].size())
            fail(ErrorCode::invalid_query, "opponent reach length mismatch");
        charge(128 + 32 * hands_[opp].size()); // validate board, proposal and reach before scanning
        const auto blocked=board_mask(board,true);
        const auto qn=width(proposal_num), qd=width(proposal_den);
        if (!qn || !qd || proposal_num <= 0 || proposal_den <= 0 || proposal_num > proposal_den)
            fail(ErrorCode::invalid_query, "proposal must be an exact positive probability at most one");
        if (qn > limits_.max_integer_bits || qd > limits_.max_integer_bits)
            fail(ErrorCode::integer_bit_limit, "proposal integer width exceeded");
        const auto paybits=std::bit_cast<std::uint64_t>(payoff);
        const auto pay=prior::decode_parts(paybits,true,true,"invalid terminal payoff");
        if (kind==TerminalKind::showdown && (paybits>>63) && pay.significand)
            fail(ErrorCode::invalid_dyadic,"showdown stake must be nonnegative");
        bool any=false; int common=0; std::size_t max_reach_bits=0;
        for (const auto value:opponent_reach) {
            const auto parts=prior::decode_parts(std::bit_cast<std::uint64_t>(value),false,true,"invalid opponent reach");
            if (value>1.0) fail(ErrorCode::invalid_dyadic,"opponent reach must be at most one");
            if (parts.significand && (!any || parts.exponent<common)) { common=parts.exponent; any=true; }
        }
        if (any) for (const auto value:opponent_reach) {
            const auto parts=prior::decode_parts(std::bit_cast<std::uint64_t>(value),false,true,"invalid opponent reach");
            if (parts.significand) max_reach_bits=std::max(max_reach_bits,
                static_cast<std::size_t>(64-std::countl_zero(parts.significand))+
                static_cast<std::size_t>(parts.exponent-common));
        }
        const auto h=hands_[0].size()+hands_[1].size();
        const int factor=common+pay.exponent;
        const auto pay_width=pay.significand ? static_cast<std::size_t>(64-std::countl_zero(pay.significand)) : 1U;
        const auto opp_sum=weight_bits_[opp]+max_reach_bits+log2ceil(hands_[opp].size())+6;
        const auto num_bits=weight_bits_[player]+opp_sum+pay_width+qd+
            static_cast<std::size_t>(std::max(0,factor))+12;
        const auto den_bits=normalizer_bits_+log2ceil(divisor(5)+1)+qn+
            static_cast<std::size_t>(std::max(0,-factor))+8;
        const auto bits=std::max({num_bits,den_bits,qn,qd,std::size_t{53}});
        const auto sorting=static_cast<std::uint64_t>(64*h*(1+log2ceil(h)));
        reserve_query(4096+512*h+sorting, 24*h+2048, bits);
        Integer pay_sig=pay.significand;
        if ((paybits>>63) && pay_sig != 0) pay_sig=-pay_sig;
        return terminal_integer_values(player,board,kind,blocked,any,pay_sig,factor,
            Integer(1),proposal_num,proposal_den,divisor(5),[&](std::size_t j) -> Integer {
                const auto parts=prior::decode_parts(std::bit_cast<std::uint64_t>(opponent_reach[j]),false,true,"invalid opponent reach");
                return Integer(parts.significand) << static_cast<unsigned>(parts.exponent-common);
            });
    }
    // Exact input-order opponent sequence reaches n_j/D, including off-path
    // zeros. The caller owns/admit its immutable input storage and common-D
    // construction. No rational is rounded through binary64 here.
    [[nodiscard]] ExactVector terminal_exact_reach(std::size_t player,
            std::span<const std::uint8_t> board, TerminalKind kind, double payoff,
            std::span<const Integer> reach_numerators, const Integer& reach_denominator,
            const Integer& proposal_num, const Integer& proposal_den) {
        return exact_reach_values(player,board,kind,payoff,reach_numerators,
            reach_denominator,proposal_num,proposal_den,true);
    }
    // Exhaustive-reveal (q=1) fold contribution at the visible prefix only.
    // The caller supplies signed whole-hand payoff. Own prior appears once;
    // own preceding action reach is absent. No future cards are enumerated.
    [[nodiscard]] ExactVector fold_prefix_exact_reach(std::size_t player,
            std::span<const std::uint8_t> visible_prefix, double signed_payoff,
            std::span<const Integer> opponent_numerators, const Integer& common_D) {
        return exact_reach_values(player,visible_prefix,TerminalKind::fold,signed_payoff,
            opponent_numerators,common_D,Integer(1),Integer(1),false);
    }
    [[nodiscard]] std::vector<double> binary64(const ExactVector& value) {
        if (value.denominator<=0 || value.numerators.size()>limits_.max_hands_per_side)
            fail(ErrorCode::invalid_query,"invalid exact vector for binary64 conversion");
        charge(128 + 32 * value.numerators.size()); // precharge operand-width scan
        std::size_t bits=width(value.denominator);
        for (const auto& n:value.numerators) bits=std::max(bits,width(n));
        if (bits>limits_.max_integer_bits)
            fail(ErrorCode::integer_bit_limit,"conversion input integer width exceeded");
        const auto entries=8*value.numerators.size()+128;
        const auto payload=prior::checked_mul_count(entries,bits+53);
        if (payload>limits_.max_integer_payload_bits-receipt_.setup_integer_payload_bits)
            fail(ErrorCode::integer_payload_limit,"conversion scratch integer payload exceeded");
        // Compose the converter's existing width-product work ledger before
        // entering it. Its two quotient/remainder operations cost at most
        // 2*S*S, S=largest input width+53; scans/shifts/comparisons/rounding
        // fit the additional 16*S term. This remains a logical model.
        const auto scratch_width=prior::checked_add_count(bits,53);
        const auto conversion_upper=prior::checked_add_count(
            prior::checked_mul_count(2,prior::checked_mul_count(scratch_width,scratch_width)),
            prior::checked_mul_count(16,scratch_width));
        const auto conversion_work=prior::checked_mul_count(value.numerators.size(),conversion_upper);
        reserve_query(prior::checked_add_count(1024+256*value.numerators.size(),conversion_work),entries,bits);
        receipt_.peak_integer_payload_bits=std::max(receipt_.peak_integer_payload_bits,
            receipt_.setup_integer_payload_bits+static_cast<std::size_t>(payload));
        std::vector<double> result;result.reserve(value.numerators.size());
        for (const auto& n:value.numerators) {
            try {
                const auto converted=exact_binary64::convert(n,value.denominator,
                    exact_binary64::Limits{limits_.max_integer_bits,
                        std::min(exact_binary64::kMaximumScratchBits,limits_.max_integer_bits+53)});
                if (converted.receipt.modeled_work>conversion_upper)
                    fail(ErrorCode::invalid_query,"converter exceeded its admitted logical work forecast");
                result.push_back(converted.value);++receipt_.conversion_calls;
            } catch (const exact_binary64::ConversionError&) {
                fail(ErrorCode::conversion_failure,"exact vector cannot round to normal finite binary64");
            }
        }
        return result;
    }
    [[nodiscard]] const Integer& normalizer_integer() const noexcept { return normalizer_; }
    [[nodiscard]] std::array<int,2> weight_denominator_exponents() const noexcept { return denominator_exponents_; }
    [[nodiscard]] std::size_t deck_size() const noexcept { return deck_.count; }
    [[nodiscard]] DeckMode deck_mode() const noexcept { return deck_.mode; }
    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }
private:
    DeckDefinition deck_{}; Limits limits_{}; Receipt receipt_{};
    std::uint64_t deck_mask_=0;
    std::array<std::vector<Hand>,2> hands_;
    std::array<std::vector<Integer>,2> weights_;
    std::array<std::vector<std::size_t>,2> same_;
    std::array<int,2> denominator_exponents_{};
    std::array<std::size_t,2> weight_bits_{};
    Integer normalizer_=0; std::size_t normalizer_bits_=0;
};
} // namespace openpoker::full_deck_public_chance

