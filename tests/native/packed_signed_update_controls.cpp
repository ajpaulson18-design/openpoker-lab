#include "../../native/packed_signed_update.hpp"
#include <random>
#include <vector>
#include <iostream>
using openpoker::exact_binary64::Integer;
using namespace openpoker::packed_signed_update;
static void require(bool condition) { if (!condition) throw std::runtime_error("packed update control failed"); }

static void check(const std::vector<std::uint64_t>& original, const Integer& c,
                  std::size_t shift, bool clip, std::size_t bits) {
    Integer value=0;
    for (std::size_t i=original.size();i-- > 0;) { value<<=64; value+=original[i]; }
    Integer expected=value+(c<<shift);
    bool error=expected<0 && !clip;
    if (expected<0 && clip) expected=0;
    error |= expected >= (Integer(1)<<bits);
    auto target=original;
    Counts counts{};
    bool failed=false;
    try { apply(target,c,shift,clip,bits,counts); } catch (const std::exception&) { failed=true; }
    require(failed==error);
    if (failed) { require(target==original); require(!counts.words_written); return; }
    Integer actual=0;
    for (std::size_t i=target.size();i-- > 0;) { actual<<=64; actual+=target[i]; }
    require(actual==expected);
    require(counts.words_read==target.size() && counts.words_written==target.size());
}
int main() {
    std::mt19937_64 rng(0x12abcdef);
    for (int k=0;k<20000;++k) {
        const std::size_t n=1+rng()%11, bits=1+rng()%(64*n);
        std::vector<std::uint64_t> v(n);
        for (auto& x:v) x=rng();
        const auto used=(bits+63)/64;
        for (auto i=used;i<n;++i) v[i]=0;
        if (bits%64) v[used-1]&=(std::uint64_t(1)<<(bits%64))-1;
        Integer c=0;
        const auto words=1+rng()%11;
        for (std::size_t i=0;i<words;++i) { c<<=64; c+=rng(); }
        if (rng()&1) c=-c;
        check(v,c,rng()%705,rng()&1,bits);
    }
    check({~std::uint64_t(0),0},1,0,false,128);
    check({0,1},-1,0,false,128);
    check({1},-1,0,true,64);
    check({1},-1,704,true,64);
    check({~std::uint64_t(0)},1,0,false,64);
    check({0},0,704,false,1);
    std::vector<std::uint64_t> bad{2}; Counts counts{};
    bool failed=false;
    try { apply(bad,0,0,false,1,counts); } catch (const std::invalid_argument&) { failed=true; }
    require(failed && bad[0]==2 && !counts.words_written);
    auto reject=[&](std::span<std::uint64_t> span,const Integer& coefficient,std::size_t shift,std::size_t width) {
        const auto before=bad; const auto old=counts; bool rejected=false;
        try { apply(span,coefficient,shift,false,width,counts); } catch (const std::exception&) { rejected=true; }
        require(rejected && bad==before && counts.additions==old.additions && counts.words_written==old.words_written);
    };
    bad[0]=0;
    reject(bad,0,705,64);
    reject(bad,Integer(1)<<704,0,64);
    reject(bad,0,0,0);
    reject(bad,0,0,65);
    reject(std::span<std::uint64_t>{},0,0,1);
    counts.words_written=std::numeric_limits<std::uint64_t>::max();
    const auto before=bad;
    failed=false;
    try { apply(bad,1,0,false,64,counts); } catch (const std::overflow_error&) { failed=true; }
    require(failed && bad==before && counts.additions==0 && counts.words_read==0 &&
            counts.words_written==std::numeric_limits<std::uint64_t>::max());
    std::cout << "packed signed update controls passed\n";
}
