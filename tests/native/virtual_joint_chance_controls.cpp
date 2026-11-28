// Source-level controls for the fixed PROOF9 joint ticket/board certificate.
// No weighted contractions, training, RNG, or owner changes are performed.
#include "../../native/virtual_dyadic_training.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <tuple>
#include <type_traits>

namespace t=openpoker::virtual_dyadic_training;
namespace chance=t::chance;
namespace prepared=t::prepared;
using Integer=chance::Integer;
using IndexPair=std::array<std::size_t,2>;
using Board=std::array<std::uint8_t,5>;

static_assert(!std::is_copy_constructible_v<prepared::PreparedPublicChance>);
static_assert(!std::is_move_constructible_v<prepared::PreparedPublicChance>);
static_assert(!std::is_copy_constructible_v<prepared::PreparedPublicChance::JointTicketCertificate>);
static_assert(!std::is_move_constructible_v<prepared::PreparedPublicChance::JointTicketCertificate>);
static_assert(prepared::PreparedPublicChance::joint_ticket_work_bound()==16'384);
static_assert(prepared::PreparedPublicChance::joint_ticket_entries_bound()==128);
static_assert(prepared::PreparedPublicChance::joint_ticket_payload_bound()==1'024);

namespace {
void require(bool value,const char* message) {
    if (!value) throw std::runtime_error(message);
}

prepared::PreparedPublicChance owner_for(
        const std::array<std::array<chance::WeightedHand,2>,2>& ranges=t::ranges) {
    return prepared::PreparedPublicChance(ranges[0],ranges[1],
        chance::DeckDefinition::reduced(t::deck_cards),chance::Limits{},64);
}

bool exact_inventory() {
    auto owner=owner_for();
    require(owner.normalizer_integer()==29,"fixed normalizer is not Z=29");
    const auto before=owner.receipt();
    std::map<IndexPair,std::size_t> ticket_counts;
    std::map<IndexPair,std::set<Board>> pair_boards;
    std::set<std::tuple<IndexPair,Board>> worlds;
    std::set<int> signs;
    for (std::uint64_t ticket=0;ticket<29;++ticket) {
        for (std::uint64_t rank=0;rank<20;++rank) {
            bool called=false;
            owner.with_joint_ticket(ticket,rank,[&](const prepared::PreparedPublicChance::JointTicketCertificate& view) {
                called=true;
                view.require_active();
                require(view.private_ticket()==ticket && view.board_rank()==rank,
                        "borrowed certificate ticket identity");
                const auto indices=view.holding_indices();
                const auto holdings=view.holdings();
                const auto board=view.board();
                require(indices[0]<2 && indices[1]<2,"original holding indices out of range");
                require(holdings[0].first==t::ranges[0][indices[0]].hand.first &&
                        holdings[0].second==t::ranges[0][indices[0]].hand.second &&
                        holdings[1].first==t::ranges[1][indices[1]].hand.first &&
                        holdings[1].second==t::ranges[1][indices[1]].hand.second,
                        "certificate did not preserve original row identity");
                require(board[0]<board[1] && board[1]<board[2],"joint board flop is not canonical");
                std::set<std::uint8_t> unique;
                for (const auto card:board) {
                    require(std::find(t::deck_cards.begin(),t::deck_cards.end(),card)!=t::deck_cards.end(),
                            "joint board card is outside PROOF9");
                    unique.insert(card);
                }
                require(unique.size()==5,"joint board contains duplicate cards");
                for (std::size_t seat=0;seat<2;++seat)
                    require(!unique.contains(holdings[seat].first) && !unique.contains(holdings[seat].second),
                            "joint board overlaps a selected private holding");
                const auto sign=view.showdown_sign();
                require(sign>=-1 && sign<=1,"invalid showdown sign");
                signs.insert(sign);
                ++ticket_counts[indices];
                pair_boards[indices].insert(board);
                worlds.emplace(indices,board);
                std::cout<<"TICKET "<<ticket<<' '<<rank<<' '<<indices[0]<<' '<<indices[1]<<' '
                    <<static_cast<unsigned>(board[0])<<' '<<static_cast<unsigned>(board[1])<<' '
                    <<static_cast<unsigned>(board[2])<<' '<<static_cast<unsigned>(board[3])<<' '
                    <<static_cast<unsigned>(board[4])<<' '<<sign<<'\n';
            });
            require(called,"joint ticket callback was not entered");
        }
    }
    require(ticket_counts==std::map<IndexPair,std::size_t>{{{0,0},60},{{0,1},160},{{1,0},360}},
            "ticket multiplicities do not encode pair weights 3/8/18");
    require(pair_boards.size()==3 && worlds.size()==60,"joint ticket world census");
    for (const auto& [indices,boards]:pair_boards) {
        (void)indices;
        require(boards.size()==20,"each compatible pair must have twenty board ranks");
    }
    require(signs.size()==3,"PROOF9 joint inventory did not expose win/tie/loss signs");
    const auto& receipt=owner.receipt();
    require(receipt.joint_ticket_queries==580 && receipt.joint_ticket_decodes==580 &&
            receipt.joint_ticket_board_unranks==580,"joint query/decode counters");
    require(receipt.rank_calls==before.rank_calls+1'160 && receipt.joint_ticket_rank_work==580*8'192,
            "only selected two holdings should be ranked per joint query");
    require(receipt.joint_ticket_work==580*prepared::PreparedPublicChance::joint_ticket_work_bound() &&
            receipt.joint_ticket_setup_work+receipt.joint_ticket_decode_work+
                receipt.joint_ticket_board_work+receipt.joint_ticket_rank_work+
                receipt.joint_ticket_margin_work==receipt.joint_ticket_work,
            "joint ticket fixed work receipt");
    require(receipt.modeled_work==receipt.prior_work+receipt.setup_work+receipt.input_work+
            receipt.cache_lookup_work+receipt.rank_work+receipt.sort_work+receipt.contraction_work+
            receipt.joint_ticket_work && receipt.modeled_work<=500'000'000,
            "joint ticket modeled-work ledger");
    require(receipt.completed_contractions==0 && receipt.weighted_families==0 &&
            receipt.weighted_showdowns==0,"joint ticket path entered a contraction family");
    require(receipt.peak_scratch_entries>=prepared::PreparedPublicChance::joint_ticket_entries_bound() &&
            receipt.peak_integer_payload_bits>=prepared::PreparedPublicChance::joint_ticket_payload_bound() &&
            receipt.peak_live_entries<=2'000'000 && receipt.peak_integer_payload_bits<=(std::size_t{1}<<30),
            "joint ticket scratch admission receipt");
    std::cout<<"RECEIPT "<<receipt.modeled_work<<' '<<receipt.joint_ticket_work<<' '
        <<receipt.joint_ticket_queries<<' '<<receipt.joint_ticket_decodes<<' '
        <<receipt.joint_ticket_board_unranks<<' '<<receipt.rank_calls<<' '
        <<receipt.completed_contractions<<'\n';
    return true;
}

bool rejects_before_reservation(std::uint64_t ticket,std::uint64_t rank) {
    auto owner=owner_for();
    const auto before=owner.receipt();
    try {
        owner.with_joint_ticket(ticket,rank,[](const auto&) {});
    } catch (const chance::KernelError& error) {
        const auto& after=owner.receipt();
        return error.code()==chance::ErrorCode::invalid_query && owner.failed() &&
            after.modeled_work==before.modeled_work && after.joint_ticket_work==0 &&
            after.joint_ticket_queries==0 && after.rank_calls==before.rank_calls;
    }
    return false;
}

bool rejects_unsupported_owner_before_reservation() {
    auto ranges=t::ranges;
    ranges[0][0].binary64_weight_bits=std::bit_cast<std::uint64_t>(0.25);
    auto owner=owner_for(ranges);
    const auto before=owner.receipt();
    try {
        owner.with_joint_ticket(0,0,[](const auto&) {});
    } catch (const chance::KernelError& error) {
        const auto& after=owner.receipt();
        return error.code()==chance::ErrorCode::invalid_query && owner.failed() &&
            after.modeled_work==before.modeled_work && after.joint_ticket_work==0 &&
            after.joint_ticket_queries==0 && after.rank_calls==before.rank_calls;
    }
    return false;
}

bool rejects_nested_scope() {
    auto owner=owner_for();
    try {
        owner.with_joint_ticket(0,0,[&](const auto& outer) {
            outer.require_active();
            owner.with_joint_ticket(1,0,[](const auto&) {});
        });
    } catch (const chance::KernelError& error) {
        const auto& receipt=owner.receipt();
        return error.code()==chance::ErrorCode::invalid_query && owner.failed() &&
            receipt.joint_ticket_queries==1 &&
            receipt.joint_ticket_work==prepared::PreparedPublicChance::joint_ticket_work_bound();
    }
    return false;
}

bool rejects_contraction_inside_scope() {
    auto owner=owner_for();
    std::array<Integer,2> reaches{1,1};
    const std::array<std::uint8_t,0> empty{};
    try {
        owner.with_joint_ticket(0,0,[&](const auto& view) {
            view.require_active();
            (void)owner.contraction(0,empty,chance::TerminalKind::fold,reaches,1);
        });
    } catch (const chance::KernelError& error) {
        return error.code()==chance::ErrorCode::invalid_query && owner.failed() &&
            owner.receipt().joint_ticket_queries==1 && owner.receipt().completed_contractions==0;
    }
    return false;
}

bool rejects_callback_exception() {
    auto owner=owner_for();
    try {
        owner.with_joint_ticket(0,0,[](const auto& view) {
            view.require_active();
            throw std::runtime_error("synthetic borrowed callback exception");
        });
    } catch (const std::runtime_error&) {
        return owner.failed() && owner.receipt().joint_ticket_queries==1;
    }
    return false;
}
} // namespace

int main() {
    try {
        require(exact_inventory(),"joint inventory control");
        require(rejects_before_reservation(29,0),"reject ticket 29 before resource reservation");
        require(rejects_before_reservation(0,20),"reject board rank 20 before resource reservation");
        require(rejects_before_reservation(std::numeric_limits<std::uint64_t>::max(),0),
                "reject oversized ticket before resource reservation");
        require(rejects_unsupported_owner_before_reservation(),"reject unsupported range before joint setup");
        require(rejects_nested_scope(),"reject nested joint ticket scope");
        require(rejects_contraction_inside_scope(),"reject conflicting contraction in ticket callback");
        require(rejects_callback_exception(),"poison owner after callback exception");
        std::cout<<"JOINT_CHANCE_CONTROL_V1 PASS 580 60 3 8 18 0\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<"JOINT_CHANCE_CONTROL_V1 FAIL "<<error.what()<<'\n';
        return 1;
    }
}
