#include "../../native/dyadic_policy.hpp"
#include <bit>
#include <iostream>
#include <sstream>
#include <string>
#include <type_traits>
#include <vector>
namespace grid = openpoker::dyadic_policy;
using grid::Integer;
static_assert(!std::is_copy_constructible_v<grid::Quantizer>);
static_assert(!std::is_copy_assignable_v<grid::Quantizer>);
static_assert(!std::is_move_constructible_v<grid::Quantizer>);
static_assert(!std::is_move_assignable_v<grid::Quantizer>);

namespace {
std::vector<Integer> fixture(std::size_t count, int profile) {
    std::vector<Integer> result(count);
    for (std::size_t i=0; i<count; ++i) {
        if (profile==0) result[i]=0;
        else if (profile==1) result[i]=-Integer(i+1);
        else if (profile==2) result[i]=i%3==0 ? -Integer(i+3) : i%3==1 ? Integer(0) : Integer(i+1);
        else if (profile==3) result[i]=1;
        else if (profile==4) result[i]=i+1;
        else if (profile==5) result[i]=count-i;
        else if (profile==6) result[i]=(Integer(1) << (64+5*i))+(37*i+1);
        else if (profile==7) result[i]=Integer(i+1)<<1800;
        else if (profile==8) result[i]=(Integer(1)<<(1000+(37*i)%700))+(2*i+3)*11;
        else if (profile==9) result[i]=i==0 ? Integer(1) : i==1 ? (Integer(1)<<2000)-1 : Integer(0);
        else throw std::runtime_error("unknown policy fixture");
    }
    return result;
}
std::string hex(const Integer& value) {
    if (value<0) {
        const Integer magnitude=-value;
        return "-"+magnitude.str(0,std::ios_base::hex);
    }
    return value.str(0,std::ios_base::hex);
}
template<class Function>
bool rejects(const char* label, grid::ErrorCode expected, Function function) {
    try { function(); }
    catch (const grid::Error& error) {
        const bool ok=error.code()==expected;
        std::cout<<"GUARD "<<label<<' '<<(ok ? "PASS" : "FAIL")<<'\n';
        return ok;
    }
    std::cout<<"GUARD "<<label<<" FAIL no_error\n";
    return false;
}
bool failed_row(const char* label,grid::Limits limits,std::vector<Integer> input,
                grid::ErrorCode expected,bool average=false) {
    grid::Quantizer owner(limits);
    const auto before=input;
    const bool rejected=rejects(label,expected,[&] {
        if (average) (void)owner.average_export(input);
        else (void)owner.regret_policy(input);
    });
    const bool closed=rejects("failed_owner",grid::ErrorCode::failed_owner,[&] {
        (void)owner.regret_policy(std::array<Integer,2>{1,2});
    });
    return rejected && closed && owner.failed() && owner.receipt().rows==0 && input==before;
}
bool guards() {
    bool ok=true;
    ok=failed_row("empty",{}, {},grid::ErrorCode::invalid_row)&&ok;
    ok=failed_row("wide_menu",{},std::vector<Integer>(21,1),grid::ErrorCode::invalid_row)&&ok;
    ok=failed_row("negative_average",{}, {-1,2},grid::ErrorCode::invalid_row,true)&&ok;
    ok=failed_row("oversized_input",{}, {Integer(1)<<65536,1},grid::ErrorCode::integer_width)&&ok;
    auto limits=grid::Limits{}; limits.integer_bits=128;
    ok=failed_row("input_width",limits, {Integer(1)<<200,1},grid::ErrorCode::integer_width)&&ok;
    ok=failed_row("arithmetic_width",limits, {(Integer(1)<<100)+1,1},grid::ErrorCode::integer_width)&&ok;
    limits=grid::Limits{}; limits.entries=100;
    ok=failed_row("entries",limits,{1,2,3,4},grid::ErrorCode::storage_limit)&&ok;
    limits=grid::Limits{}; limits.integer_payload_bits=2048;
    ok=failed_row("payload",limits,{1,1,1},grid::ErrorCode::payload_limit)&&ok;
    limits=grid::Limits{}; limits.work=128;
    ok=failed_row("work",limits,{1,2},grid::ErrorCode::work_limit)&&ok;
    limits=grid::Limits{}; limits.work=500000001;
    ok=rejects("raised_work",grid::ErrorCode::invalid_limits,[&] { grid::Quantizer owner(limits); })&&ok;
    limits=grid::Limits{}; limits.integer_bits=65537;
    ok=rejects("raised_width",grid::ErrorCode::invalid_limits,[&] { grid::Quantizer owner(limits); })&&ok;
    limits=grid::Limits{}; limits.entries=2000001;
    ok=rejects("raised_entries",grid::ErrorCode::invalid_limits,[&] { grid::Quantizer owner(limits); })&&ok;
    limits=grid::Limits{}; limits.integer_payload_bits=(std::size_t{1}<<30)+1;
    ok=rejects("raised_payload",grid::ErrorCode::invalid_limits,[&] { grid::Quantizer owner(limits); })&&ok;
    limits=grid::Limits{}; limits.work=1000;
    grid::Quantizer owner(limits);
    const std::array<Integer,2> input{1,1};
    const auto first=owner.regret_policy(input);
    const auto first_work=owner.receipt().work;
    ok=rejects("cumulative_work",grid::ErrorCode::work_limit,[&] { (void)owner.regret_policy(input); })&&ok;
    ok=rejects("cumulative_failed_owner",grid::ErrorCode::failed_owner,[&] { (void)owner.average_export(input); })&&ok;
    ok=ok && owner.failed() && owner.receipt().rows==1 && owner.receipt().work>=first_work &&
       first.units()[0]==grid::grid_units/2 && first.units()[1]==grid::grid_units/2;
    std::cout<<"GUARDS_END "<<(ok ? "PASS" : "FAIL")<<'\n';
    return ok;
}
} // namespace

int main() {
    try {
        grid::Quantizer owner;
        std::size_t count=0,bytes=0;
        std::cout<<"DYADIC_POLICY_V1 "<<grid::grid_bits<<' '<<grid::maximum_actions<<'\n';
        for (std::size_t actions=1; actions<=20; ++actions)
        for (int profile=0; profile<10; ++profile)
        for (int kind=0; kind<2; ++kind) {
            if (kind==1 && (profile==1 || profile==2)) continue;
            const auto weights=fixture(actions,profile), original=weights;
            const auto policy=kind==0 ? owner.regret_policy(weights) : owner.average_export(weights);
            if (weights!=original || policy.size()!=actions ||
                    static_cast<int>(policy.kind())!=kind)
                throw std::runtime_error("policy input ownership or image kind changed");
            const auto& receipt=owner.receipt();
            std::ostringstream line;
            line<<"ROW "<<count<<' '<<kind<<' '<<profile<<' '<<actions<<' '
                <<(policy.uniform_fallback() ? 1 : 0);
            for (std::size_t i=0; i<actions; ++i)
                line<<' '<<hex(weights[i])<<' '<<policy.units()[i]<<' '
                    <<std::hex<<std::bit_cast<std::uint64_t>(policy.binary64(i))<<std::dec;
            line<<" META "<<receipt.work<<' '<<receipt.rows<<' '<<receipt.max_input_bits<<' '
                <<receipt.peak_forecast_bits<<' '<<receipt.retained_entries+receipt.peak_scratch_entries<<' '
                <<receipt.peak_integer_payload_bits<<'\n';
            const auto raw=line.str();
            if (raw.size()>20000 || bytes+raw.size()>2100000)
                throw std::runtime_error("policy control output admission exceeded");
            bytes+=raw.size(); std::cout<<raw; ++count;
        }
        if (count!=360 || owner.receipt().rows!=360)
            throw std::runtime_error("policy fixed coverage incomplete");
        std::cout<<"END "<<count<<' '<<owner.receipt().work<<'\n';
        return guards() ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n'; return 1;
    }
}
