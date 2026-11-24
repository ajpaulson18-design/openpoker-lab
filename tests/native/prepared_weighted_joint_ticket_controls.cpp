// Bounded component wire for the compact purpose on the existing owner.
// Exact input binary64 bits, original row order, no RNG or training.
#include "../../native/prepared_public_chance.hpp"
#include <charconv>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

namespace p=openpoker::prepared_public_chance;
using Owner=p::PreparedPublicChance;
namespace {
std::istream* input_stream=&std::cin;
std::uint64_t word() {
    std::string token;
    if (!(*input_stream>>token) || token.empty() || token.size()>20 ||
        token.find_first_not_of("0123456789")!=std::string::npos)
        throw std::runtime_error("invalid bounded unsigned token");
    std::uint64_t value=0;
    const auto parsed=std::from_chars(token.data(),token.data()+token.size(),value);
    if (parsed.ec!=std::errc{} || parsed.ptr!=token.data()+token.size())
        throw std::runtime_error("invalid bounded unsigned value");
    return value;
}
void require(bool condition,const char* message) {if (!condition) throw std::runtime_error(message);}
}
int main(int argc,char** argv) {
    try {
        // New range-bearing wire has a separate fixed file envelope. Keep the
        // established short-stdin observer cap unchanged. At most2652 rows
        // consume27 bytes each and512 selectors consume42 bytes each; header
        // and whitespace fit the remaining space below98304 bytes.
        require(argc==2,"one bounded input artifact path required");
        const std::filesystem::path path(argv[1]);
        require(std::filesystem::is_regular_file(path) && !std::filesystem::is_symlink(path) &&
                std::filesystem::file_size(path)<=98'304,"probe input artifact byte bound");
        std::ifstream input(path);require(input.good(),"probe input artifact unreadable");input_stream=&input;
        const auto n=word(),h0=word(),h1=word(),queries=word();
        require((n==9 || n==52) && h0>0 && h0<=1326 && h1>0 && h1<=1326 && queries>0 && queries<=512,
                "probe request geometry");
        // Complete probe scalar envelope before source arrays: candidate chance
        // lifetime plus bounded input/output/loop overhead; no limit increases.
        const auto chance_work=Owner::weighted_joint_setup_work_bound(h0,h1)+
            queries*Owner::weighted_joint_ticket_work_bound(h0,h1);
        require(chance_work<=110'000'000 && chance_work+3'000'000<=500'000'000 &&
                3*(h0+h1)+Owner::weighted_joint_owner_entries_bound(h0,h1)+256+131072<=2'000'000,
                "complete probe envelope");
        std::array<std::vector<p::WeightedHand>,2> input;
        for (std::size_t seat=0;seat<2;++seat) {
            const auto count=seat ? h1 : h0;
            input[seat].reserve(static_cast<std::size_t>(count));
            for (std::size_t i=0;i<count;++i) {
                const auto a=word(),b=word(),bits=word();
                require(a<52 && b<52,"physical input card bound");
                input[seat].push_back({{static_cast<std::uint8_t>(a),static_cast<std::uint8_t>(b)},bits});
            }
        }
        constexpr std::array<std::uint8_t,9> proof{16,17,24,32,33,35,37,43,48};
        const auto deck=n==52 ? p::DeckDefinition::full52() : p::DeckDefinition::reduced(proof);
        p::Limits limits;
        limits.max_hands_per_side=1326;limits.max_integer_bits=181;
        limits.max_modeled_work=110'000'000;limits.max_storage_entries=12'000;
        limits.max_integer_payload_bits=std::size_t{1}<<20;
        Owner owner(input[0],input[1],p::Purpose::joint_tickets_v1,deck,limits);
        std::ostringstream output;
        output<<"WEIGHTED_JOINT_V1 "<<owner.normalizer_integer()<<' '<<h0<<' '<<h1<<' '<<queries<<'\n';
        for (std::size_t seat=0;seat<2;++seat) {
            const auto scale=owner.ticket_normalization(seat);
            output<<"SCALE "<<seat<<' '<<scale.power<<' '<<scale.gcd<<'\n';
        }
        for (std::size_t query=0;query<queries;++query) {
            const auto ticket=word(),rank=word();
            owner.with_joint_ticket(ticket,rank,[&](const Owner::JointTicketCertificate& sample) {
                require(sample.purpose()==p::Purpose::joint_tickets_v1 &&
                    sample.declared_hand_counts()==std::array<std::size_t,2>{h0,h1} && sample.deck().count==n,
                    "borrowed purpose/range/deck contract");
                const auto indices=sample.holding_indices();const auto hands=sample.holdings();
                output<<"WORLD "<<ticket<<' '<<rank<<' '<<indices[0]<<' '<<indices[1];
                for (const auto hand:hands) output<<' '<<unsigned(hand.first)<<' '<<unsigned(hand.second);
                for (const auto card:sample.board()) output<<' '<<unsigned(card);
                output<<' '<<sample.showdown_sign()<<'\n';
            });
        }
        std::string extra;require(!(*input_stream>>extra),"extra input token");
        const auto& receipt=owner.receipt();
        require(!owner.failed() && receipt.completed_contractions==0 && receipt.prior_work==0 &&
                receipt.joint_ticket_queries==queries && receipt.rank_calls==2*queries &&
                receipt.modeled_work==chance_work,"complete compact owner receipt");
        output<<"RECEIPT "<<receipt.modeled_work<<' '<<receipt.retained_entries<<' '
            <<receipt.peak_scratch_entries<<' '<<receipt.peak_live_entries<<' '
            <<receipt.retained_integer_payload_bits<<' '<<receipt.peak_integer_payload_bits<<' '
            <<receipt.peak_integer_bits<<' '<<receipt.rank_calls<<' '
            <<receipt.completed_contractions<<' '<<receipt.prior_work<<'\n';
        const auto result=output.str();require(result.size()<=131072,"probe bounded output");
        std::cout<<result;return 0;
    } catch (const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}
