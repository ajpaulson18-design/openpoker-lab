#include "../../native/packed_signed_update.hpp"
#include <algorithm>
#include <random>
#include <span>
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

static void check_initialize(const std::vector<std::uint64_t>& sentinel, const Integer& c,
                             std::size_t shift, bool clip, std::size_t bits) {
    auto initialized=sentinel;
    auto baseline=std::vector<std::uint64_t>(sentinel.size(),0);
    Counts initialized_counts{}, baseline_counts{};
    bool initialize_failed=false, baseline_failed=false;
    try { initialize_from_zero(initialized,c,shift,clip,bits,initialized_counts); }
    catch (const std::exception&) { initialize_failed=true; }
    try { apply(baseline,c,shift,clip,bits,baseline_counts); }
    catch (const std::exception&) { baseline_failed=true; }
    require(initialize_failed==baseline_failed);
    if (initialize_failed) {
        require(initialized==sentinel);
        require(initialized_counts.additions==0 && initialized_counts.subtractions==0 &&
                initialized_counts.clipped==0 && initialized_counts.words_read==0 &&
                initialized_counts.words_written==0);
        return;
    }
    require(initialized==baseline);
    require(initialized_counts.additions==baseline_counts.additions &&
            initialized_counts.subtractions==baseline_counts.subtractions &&
            initialized_counts.clipped==baseline_counts.clipped &&
            initialized_counts.words_read==0 &&
            initialized_counts.words_written==initialized.size());
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

    // Initialization has apply-equivalent arithmetic from certified zero, but
    // ignores every target word and accounts for no target reads.
    for (int k=0;k<20000;++k) {
        const std::size_t n=1+rng()%11, bits=1+rng()%(64*n);
        std::vector<std::uint64_t> sentinel(n);
        for (auto& x:sentinel) x=rng();
        Integer c=0;
        const auto words=1+rng()%11;
        for (std::size_t i=0;i<words;++i) { c<<=64; c+=rng(); }
        if (rng()&1) c=-c;
        check_initialize(sentinel,c,rng()%705,rng()&1,bits);
    }
    check_initialize({~std::uint64_t(0),~std::uint64_t(0)},1,0,false,128);
    check_initialize({~std::uint64_t(0)},1,63,false,64);
    check_initialize({1},-1,0,true,64);
    check_initialize({1},-1,0,false,64);
    check_initialize({1,2},0,704,false,128);

    auto unchanged=std::vector<std::uint64_t>{0xfeedfacecafebeefULL};
    Counts init_counts{};
    init_counts.words_written=std::numeric_limits<std::uint64_t>::max();
    const auto init_counts_before=init_counts;
    failed=false;
    try { initialize_from_zero(unchanged,1,0,false,64,init_counts); }
    catch (const std::overflow_error&) { failed=true; }
    require(failed && unchanged[0]==0xfeedfacecafebeefULL &&
            init_counts.additions==init_counts_before.additions &&
            init_counts.subtractions==init_counts_before.subtractions &&
            init_counts.clipped==init_counts_before.clipped &&
            init_counts.words_read==init_counts_before.words_read &&
            init_counts.words_written==init_counts_before.words_written);

    auto reject_initialize=[&](std::span<std::uint64_t> span,const Integer& coefficient,
                               std::size_t shift,std::size_t width) {
        std::vector<std::uint64_t> before_words(span.begin(),span.end());
        const auto before_counts=init_counts;
        bool rejected=false;
        try { initialize_from_zero(span,coefficient,shift,false,width,init_counts); }
        catch (const std::exception&) { rejected=true; }
        require(rejected && std::equal(span.begin(),span.end(),before_words.begin()) &&
                init_counts.additions==before_counts.additions &&
                init_counts.subtractions==before_counts.subtractions &&
                init_counts.clipped==before_counts.clipped &&
                init_counts.words_read==before_counts.words_read &&
                init_counts.words_written==before_counts.words_written);
    };
    init_counts={};
    unchanged[0]=0xfeedfacecafebeefULL;
    reject_initialize(unchanged,0,0,0);   // positive-width validation is atomic
    reject_initialize(unchanged,0,0,65);
    reject_initialize(std::span<std::uint64_t>{},0,0,1);
    reject_initialize(unchanged,0,705,64);
    reject_initialize(unchanged,Integer(1)<<704,0,64);
    init_counts.additions=std::numeric_limits<std::uint64_t>::max();
    const auto additions_before=init_counts;
    unchanged[0]=0xfeedfacecafebeefULL;
    failed=false;
    try { initialize_from_zero(unchanged,1,0,false,64,init_counts); }
    catch (const std::overflow_error&) { failed=true; }
    require(failed && unchanged[0]==0xfeedfacecafebeefULL &&
            init_counts.additions==additions_before.additions &&
            init_counts.words_written==additions_before.words_written);

    auto clipped_target=std::vector<std::uint64_t>{0x123456789abcdef0ULL};
    Counts clipped_counts{};
    clipped_counts.clipped=std::numeric_limits<std::uint64_t>::max();
    failed=false;
    try { initialize_from_zero(clipped_target,-1,0,true,64,clipped_counts); }
    catch (const std::overflow_error&) { failed=true; }
    require(failed && clipped_target[0]==0x123456789abcdef0ULL &&
            clipped_counts.subtractions==0 && clipped_counts.words_written==0);
    Counts subtraction_counts{};
    subtraction_counts.subtractions=std::numeric_limits<std::uint64_t>::max();
    failed=false;
    try { initialize_from_zero(clipped_target,-1,0,true,64,subtraction_counts); }
    catch (const std::overflow_error&) { failed=true; }
    require(failed && clipped_target[0]==0x123456789abcdef0ULL &&
            subtraction_counts.subtractions==std::numeric_limits<std::uint64_t>::max() &&
            subtraction_counts.clipped==0 && subtraction_counts.words_written==0);
    std::cout << "packed signed update controls passed\n";
}
