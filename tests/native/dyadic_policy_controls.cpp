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
bool combined_controls() {
    grid::Limits limits{};
    limits.profile=grid::Profile::proof10;
    limits.integer_bits=702;
    limits.entries=336;
    limits.division_kernel=grid::DivisionKernel::combined;
    auto separate_limits=limits;separate_limits.division_kernel=grid::DivisionKernel::separate;
    grid::Quantizer combined(limits),separate(separate_limits);
    std::size_t rows=0,divisions=0;
    for (std::size_t actions=1;actions<=4;++actions)
    for (int profile=0;profile<11;++profile)
    for (int kind=0;kind<2;++kind) {
        if (kind==1 && (profile==1 || profile==2)) continue;
        auto input=fixture(actions,profile==10?0:profile);
        if (profile==7) for (std::size_t i=0;i<actions;++i) input[i]=Integer(i+1)<<590;
        if (profile==8) for (std::size_t i=0;i<actions;++i) input[i]=(Integer(1)<<(600+7*i))+(2*i+3)*11;
        if (profile==9) {input.assign(actions,0);input[0]=1;if (actions>1) input[1]=(Integer(1)<<640)-1;}
        if (profile==10) {
            input.assign(actions,0);
            input[0]=Integer("1393796574908165155322327656701986271657982");
            if (actions>1) input[1]=Integer("696898287454081973172991196020261454725646");
        }
        const auto positives=std::count_if(input.begin(),input.end(),[](const Integer& x){return x>0;});
        if (positives>1) divisions+=static_cast<std::size_t>(positives);
        const auto original=input;
        const auto a=kind?separate.average_export(input):separate.regret_policy(input);
        const auto b=kind?combined.average_export(input):combined.regret_policy(input);
        if (input!=original || a.kind()!=b.kind() || a.uniform_fallback()!=b.uniform_fallback() ||
            !std::equal(a.units().begin(),a.units().end(),b.units().begin(),b.units().end()))
            throw std::runtime_error("combined division policy differs");
        std::cout<<"COMBINED "<<kind<<' '<<profile<<' '<<actions<<' '<<b.uniform_fallback();
        for (std::size_t i=0;i<actions;++i) std::cout<<' '<<hex(input[i])<<' '<<b.units()[i];
        std::cout<<'\n';++rows;
    }
    auto bad=limits;bad.integer_bits=128;
    bool width=failed_row("combined_width",bad,{(Integer(1)<<100)+1,1},grid::ErrorCode::integer_width);
    bad=limits;
    bool intermediate=failed_row("combined_intermediate_width",bad,{(Integer(1)<<650)+1,1},grid::ErrorCode::integer_width);
    bad=limits;bad.work=128;
    bool work=failed_row("combined_work",bad,{1,2},grid::ErrorCode::work_limit);
    const bool counts=combined.receipt().combined_divisions==divisions && separate.receipt().combined_divisions==0;
    std::cout<<"COMBINED_END "<<rows<<' '<<combined.receipt().combined_divisions<<' '
        <<(width && intermediate && work && counts ? "PASS":"FAIL")<<'\n';
    auto q32_limits=limits;
    q32_limits.profile=grid::Profile::proof9_q32;
    q32_limits.work=grid::proof9_q32_work_cap;
    grid::Quantizer q32(q32_limits);
    const auto q32_policy=q32.regret_policy(std::array<Integer,2>{3,7});
    const bool q32_ok=q32_policy.units().size()==2 && q32.receipt().combined_divisions==2;
    std::cout<<"Q32_PROFILE "<<(q32_ok?"PASS":"FAIL")<<'\n';
    return rows==80 && width && intermediate && work && counts && q32_ok;
}
bool complement_controls() {
    grid::Limits limits{};
    limits.profile=grid::Profile::proof10;
    limits.integer_bits=702; limits.entries=336;
    limits.division_kernel=grid::DivisionKernel::complement;
    auto separate_limits=limits; separate_limits.division_kernel=grid::DivisionKernel::separate;
    grid::Quantizer complement(limits),separate(separate_limits);
    std::size_t rows=0,divisions=0;
    for (std::size_t actions=2;actions<=4;++actions)
    for (int profile=0;profile<10;++profile)
    for (int kind=0;kind<2;++kind) {
        if (kind==1 && (profile==1 || profile==2)) continue;
        auto input=fixture(actions,profile);
        if (profile==7) for (std::size_t i=0;i<actions;++i) input[i]=Integer(i+1)<<590;
        if (profile==8) for (std::size_t i=0;i<actions;++i) input[i]=(Integer(1)<<(600+7*i))+(2*i+3)*11;
        if (profile==9) {input.assign(actions,0);input[0]=1;if(actions>1) input[1]=(Integer(1)<<640)-1;}
        const auto n=std::count_if(input.begin(),input.end(),[](const Integer& x){return x>0;});
        if (n>1) divisions+=static_cast<std::size_t>(n-1);
        const auto a=kind?separate.average_export(input):separate.regret_policy(input);
        const auto b=kind?complement.average_export(input):complement.regret_policy(input);
        if (!std::equal(a.units().begin(),a.units().end(),b.units().begin(),b.units().end()))
            throw std::runtime_error("complement policy differs from exact separate divisions");
        std::cout<<"COMPLEMENT "<<kind<<' '<<profile<<' '<<actions;
        for(std::size_t i=0;i<actions;++i) std::cout<<' '<<hex(input[i])<<' '<<b.units()[i];
        std::cout<<'\n'; ++rows;
    }
    const bool count_ok=complement.receipt().combined_divisions==divisions;
    auto bad=limits; bad.profile=grid::Profile::proof9_q32;
    const bool profile_ok=rejects("complement_profile",grid::ErrorCode::invalid_limits,[&]{grid::Quantizer q(bad);});
    auto too_wide=fixture(5,3);
    const bool width_ok=failed_row("complement_menu",limits,too_wide,grid::ErrorCode::invalid_row);
    std::cout<<"COMPLEMENT_END "<<rows<<' '<<complement.receipt().combined_divisions<<' '
        <<(count_ok&&profile_ok&&width_ok?"PASS":"FAIL")<<'\n';
    return rows==54 && count_ok && profile_ok && width_ok;
}
bool equal_complement_controls() {
    grid::Limits limits{};
    limits.profile=grid::Profile::proof10;
    limits.integer_bits=702; limits.entries=336;
    limits.division_kernel=grid::DivisionKernel::equal_complement;
    auto baseline_limits=limits; baseline_limits.division_kernel=grid::DivisionKernel::separate;
    grid::Quantizer equal(limits), baseline(baseline_limits);
    const std::array<std::vector<Integer>,4> cases{{
        {Integer(1)<<600,Integer(1)<<600,Integer(1)<<600,Integer(1)<<600},
        {0,Integer(1)<<640,Integer(1)<<640,0},
        {7,0,7,7},
        {(Integer(1)<<640)+3, (Integer(1)<<640)+3, (Integer(1)<<640)+3, (Integer(1)<<640)+3}
    }};
    for (const auto& input : cases) {
        const auto a=baseline.regret_policy(input), b=equal.regret_policy(input);
        if (!std::equal(a.units().begin(),a.units().end(),b.units().begin(),b.units().end()))
            throw std::runtime_error("equal-complement policy differs from baseline");
    }
    const std::array<Integer,4> unequal{(Integer(1)<<640)+1,(Integer(1)<<639)+7,0,3};
    const auto a=baseline.regret_policy(unequal), b=equal.regret_policy(unequal);
    if (!std::equal(a.units().begin(),a.units().end(),b.units().begin(),b.units().end()))
        throw std::runtime_error("unequal equal-complement fallback differs from baseline");
    const std::array<Integer,4> tied{3,3,3,0};
    const auto tied_policy=equal.regret_policy(tied);
    if (tied_policy.units()[0]!=((grid::grid_units+2)/3) ||
        tied_policy.units()[1]!=(grid::grid_units/3) ||
        tied_policy.units()[2]!=(grid::grid_units-(grid::grid_units+2)/3-grid::grid_units/3))
        throw std::runtime_error("equal-complement tie or remainder order changed");
    const std::vector<Integer> negative{5,-1,5};
    if (!failed_row("equal_negative_average",limits,negative,grid::ErrorCode::invalid_row,true))
        return false;
    const bool receipt_ok=equal.receipt().equal_rows==5 &&
        equal.receipt().equal_divisions_avoided==3+1+2+3+2;
    const bool restricted=rejects("equal_q32_profile",grid::ErrorCode::invalid_limits,[&]{
        auto bad=limits; bad.profile=grid::Profile::proof9_q32; grid::Quantizer q(bad);
    });
    std::cout<<"EQUAL_COMPLEMENT_END "<<equal.receipt().equal_rows<<' '
        <<equal.receipt().equal_divisions_avoided<<' '
        <<(receipt_ok&&restricted?"PASS":"FAIL")<<'\n';
    return receipt_ok&&restricted;
}

bool pair_complement_controls() {
    grid::Limits limits{};
    limits.profile=grid::Profile::proof10;
    limits.integer_bits=702; limits.entries=336;
    limits.division_kernel=grid::DivisionKernel::pair_complement;
    auto complement_limits=limits; complement_limits.division_kernel=grid::DivisionKernel::complement;
    auto equal_limits=limits; equal_limits.division_kernel=grid::DivisionKernel::equal_complement;
    auto separate_limits=limits; separate_limits.division_kernel=grid::DivisionKernel::separate;
    grid::Quantizer pair(limits),complement(complement_limits),equal_complement(equal_limits),separate(separate_limits);
    const Integer units=grid::grid_units;
    const std::array<std::vector<Integer>,6> cases{{
        {0,1,-9,2*units-1},               // exact half-unit tie: earlier positive action wins
        {0,1,-9,2*units},                 // remainder below its complement: later action wins
        {0,Integer(3)<<600,-7,Integer(7)<<600},
        {(Integer(1)<<640)+1,0,-11,Integer(1)<<602},
        {0,3,0,7},                        // unequal pair with interspersed zero
        {0,3,5,7}                         // non-pair fallback retains complement behavior
    }};
    std::uint64_t expected_divisions=0;
    for (const auto& input : cases) {
        const auto a=separate.regret_policy(input);
        const auto b=complement.regret_policy(input);
        const auto c=pair.regret_policy(input);
        const auto equal_units=[](const auto& lhs,const auto& rhs) {
            return lhs.size()==rhs.size() &&
                std::equal(lhs.units().begin(),lhs.units().end(),rhs.units().begin(),rhs.units().end());
        };
        if (!equal_units(a,b) || !equal_units(a,c))
            throw std::runtime_error("pair-complement policy differs from generic division");
        std::size_t positive_count=0,first=0,second=0;
        for (std::size_t i=0;i<input.size();++i) if (input[i]>0) {
            if (positive_count==0) first=i;
            else if (positive_count==1) second=i;
            ++positive_count;
        }
        if (positive_count==2 && input[first]!=input[second]) {
            ++expected_divisions;
            if (input[0]==0 && input[1]==1 && input[3]==2*units-1 &&
                (c.units()[1]!=1 || c.units()[3]!=units-1))
                throw std::runtime_error("pair-complement exact tie did not favor earlier positive action");
            if (input[0]==0 && input[1]==1 && input[3]==2*units &&
                (c.units()[1]!=0 || c.units()[3]!=units))
                throw std::runtime_error("pair-complement non-tie remainder allocation changed");
        } else if (positive_count>1) {
            expected_divisions+=positive_count-1;
        }
    }
    const std::array<Integer,4> equal{0,Integer(1)<<640,0,Integer(1)<<640};
    const auto eq_pair=pair.regret_policy(equal);
    const auto eq_baseline=equal_complement.regret_policy(equal);
    if (!std::equal(eq_pair.units().begin(),eq_pair.units().end(),eq_baseline.units().begin(),eq_baseline.units().end()))
        throw std::runtime_error("pair-complement equal row changed");
    const std::array<Integer,4> avg{0,1,0,2*units-1};
    const auto avg_separate=separate.average_export(avg);
    const auto avg_pair=pair.average_export(avg);
    const auto avg_equal=equal_complement.average_export(avg);
    if (!std::equal(avg_separate.units().begin(),avg_separate.units().end(),avg_pair.units().begin(),avg_pair.units().end()) ||
        !std::equal(avg_equal.units().begin(),avg_equal.units().end(),avg_pair.units().begin(),avg_pair.units().end()) ||
        avg_pair.units()[1]!=1 || avg_pair.units()[3]!=units-1)
        throw std::runtime_error("pair-complement average tie or generic parity changed");
    expected_divisions+=1;
    const bool receipts=pair.receipt().combined_divisions==expected_divisions &&
        pair.receipt().equal_rows==equal_complement.receipt().equal_rows &&
        pair.receipt().equal_divisions_avoided==equal_complement.receipt().equal_divisions_avoided &&
        pair.receipt().work==equal_complement.receipt().work;
    const bool profile_rejects=rejects("pair_q32_profile",grid::ErrorCode::invalid_limits,[&]{
        auto bad=limits; bad.profile=grid::Profile::proof9_q32; grid::Quantizer q(bad);
    });
    const bool menu_rejects=failed_row("pair_menu",limits,fixture(5,3),grid::ErrorCode::invalid_row);
    std::cout<<"PAIR_COMPLEMENT_END "<<pair.receipt().combined_divisions<<' '
        <<pair.receipt().equal_rows<<' '<<pair.receipt().work<<' '
        <<(receipts&&profile_rejects&&menu_rejects?"PASS":"FAIL")<<'\n';
    return receipts&&profile_rejects&&menu_rejects;
}
} // namespace

bool first_sweep_regret_controls() {
    grid::Limits limits;
    limits.profile=grid::Profile::proof10;
    limits.integer_bits=grid::proof10_integer_bits;
    limits.entries=336;
    limits.division_kernel=grid::DivisionKernel::equal_complement;
    grid::Quantizer checked(limits), generic(limits);
    const std::array<Integer,4> values{(Integer(1)<<640)+1,0,(Integer(1)<<639)+7,3};
    const auto a=checked.first_sweep_regret_policy(values), b=generic.regret_policy(values);
    if (!std::equal(a.units().begin(),a.units().end(),b.units().begin(),b.units().end()) ||
        checked.receipt().work!=generic.receipt().work)
        throw std::runtime_error("bounded first regret policy differs from generic allocation");
    const std::array<Integer,2> full{1,2};
    try {
        (void)checked.first_sweep_regret_policy(full);
    } catch (const grid::Error& error) {
        return error.code()==grid::ErrorCode::invalid_row && checked.failed() &&
            checked.receipt().rows==1;
    }
    return false;
}

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
        const bool legacy=guards();
        return combined_controls() && complement_controls() && equal_complement_controls() &&
            pair_complement_controls() && first_sweep_regret_controls() && legacy ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n'; return 1;
    }
}
