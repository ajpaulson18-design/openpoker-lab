// Bounded exact compact/canonical row images. Not a poker traversal or sampler.
#include "../../native/opponent_role_row.hpp"
#include <array>
#include <cstring>
#include <iostream>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
namespace r=openpoker::opponent_role_row;
namespace q=r::q;
using Integer=r::Integer;
namespace {
constexpr std::size_t input_cap=116000,output_cap=131072;
class Bytes {
    std::vector<unsigned char> data_;
    std::size_t offset_=0;
public:
    explicit Bytes(bool input=false) {
        if(input) {
            char c;
            while(std::cin.get(c)) {
                r::require(data_.size()<input_cap,"role row input cap");
                data_.push_back(static_cast<unsigned char>(c));
            }
        }
    }
    void word(std::uint64_t n) {
        r::require(data_.size()+8<=output_cap,"role row output cap");
        for(unsigned i=0;i<8;++i)data_.push_back(static_cast<unsigned char>(n>>(8*i)));
    }
    std::uint64_t word() {
        r::require(data_.size()-offset_>=8,"role row truncated request");std::uint64_t n=0;
        for(unsigned i=0;i<8;++i)n|=static_cast<std::uint64_t>(data_[offset_++])<<(8*i);
        return n;
    }
    void magic(const char* text) {for(std::size_t i=0;i<8;++i)data_.push_back(static_cast<unsigned char>(text[i]));}
    void expect(const char* text) {
        r::require(data_.size()-offset_>=8,"role row truncated magic");
        for(std::size_t i=0;i<8;++i)r::require(data_[offset_++]==static_cast<unsigned char>(text[i]),"role row request magic");
    }
    Integer integer() {
        Integer n=0;
        for(unsigned i=0;i<7;++i)n+=Integer(word())<<(64*i);
        if(boost::multiprecision::bit_test(n,447))n-=Integer(1)<<448;
        r::require(r::bits(n)<=370,"role row input integer width");return n;
    }
    void integer(const Integer& n) {
        r::require(r::bits(n)<=371,"role row output integer width");
        Integer encoded=n;if(encoded<0)encoded+=Integer(1)<<448;
        const Integer mask=(Integer(1)<<64)-1;
        for(unsigned i=0;i<7;++i)word(static_cast<std::uint64_t>((encoded>>(64*i))&mask));
    }
    void end() const {r::require(offset_==data_.size(),"role row trailing request bytes");}
    void publish() const {
        std::cout.write(reinterpret_cast<const char*>(data_.data()),static_cast<std::streamsize>(data_.size()));
        r::require(bool(std::cout),"role row stdout failure");
    }
};
template<class F> void refusal(const char* label,F&& f) {
    bool refused=false;try{f();}catch(const std::exception&){refused=true;}
    r::require(refused,"role row guard accepted invalid operation");std::cout<<"GUARD "<<label<<" PASS\n";
}
void guards() {
    const auto budget=r::forecast({});
    refusal("rows-limit",[]{r::Limits l;l.rows=205;(void)r::Owner(l);});
    refusal("steps-limit",[]{r::Limits l;l.steps=3;(void)r::Owner(l);});
    refusal("work-limit",[&]{r::Limits l;l.work=budget.work-1;(void)r::Owner(l);});
    refusal("entries-limit",[&]{r::Limits l;l.entries=budget.entries-1;(void)r::Owner(l);});
    refusal("payload-limit",[&]{r::Limits l;l.payload_bits=budget.payload_bits-1;(void)r::Owner(l);});
    const std::array<std::uint64_t,2> units{q::grid_units/2,q::grid_units/2};
    for(unsigned kind=0;kind<7;++kind) {
        r::Owner owner;std::vector<std::vector<Integer>> rr(1,std::vector<Integer>(2));
        std::vector<std::vector<Integer>> aa(1,std::vector<Integer>(2));auto input=units;
        if(kind==0)++input[0];
        if(kind==1)rr[0][0]=1;
        if(kind==2)rr[0]={Integer(17)<<365,-(Integer(17)<<365)};
        if(kind==3)aa[0][0]=-1;
        if(kind==4)aa[0][0]=1;
        if(kind==5)rr[0]={Integer(1)<<448,0};
        if(kind==6)aa[0]={Integer(1)<<53,0};
        const std::array<const char*,7> names{"grid","centering","raw-magnitude","negative-average","average-role-units","wide-regret","wide-average"};
        refusal(names[kind],[&]{(void)owner.row(input,rr,aa);});
        r::require(owner.failed(),"role row refusal did not poison");
        refusal("failed-owner",[&]{(void)owner.row(units,std::vector<std::vector<Integer>>(1,std::vector<Integer>(2)),
            std::vector<std::vector<Integer>>(1,std::vector<Integer>(2)));});
    }
    r::Limits one;one.rows=1;one.steps=1;r::Owner owner(one);
    const std::vector<std::vector<Integer>> zero(1,std::vector<Integer>(2));
    (void)owner.row(units,zero,zero);
    refusal("cumulative-row-limit",[&]{(void)owner.row(units,zero,zero);});
    std::cout<<"OPPONENT_ROLE_ROW_GUARDS_V1 PASS 20\n";
}
}
int main(int argc,char** argv) {
    try {
        r::require(argc==1 || (argc==2 && std::strcmp(argv[1],"--guards")==0),"role row explicit arguments");
        if(argc==2){guards();return 0;}
        const auto plan=r::forecast({}); // before request arrays or Quantizer
#ifdef _WIN32
        r::require(_setmode(_fileno(stdin),_O_BINARY)!=-1 && _setmode(_fileno(stdout),_O_BINARY)!=-1,"role row binary streams");
#endif
        Bytes input(true),output;input.expect("OPLRQ001");const auto count=input.word();
        r::require(count && count<=r::maximum_rows,"role row request count");
        r::Owner compact;q::Limits canonical_limits;canonical_limits.work=5'000'000;
        canonical_limits.integer_bits=704;canonical_limits.entries=r::entries_cap;canonical_limits.integer_payload_bits=r::payload_cap;
        q::Quantizer canonical(canonical_limits);
        output.magic("OPLRP001");output.word(count);
        for(std::size_t index=0;index<count;++index) {
            const auto id=input.word(),k=input.word(),steps=input.word();
            r::require(id==index && k>=2 && k<=4 && steps && steps<=2,"role row request descriptor");
            std::vector<std::uint64_t> units(k);for(auto& u:units)u=input.word();
            std::vector<std::vector<Integer>> rr(steps,std::vector<Integer>(k)),aa(steps,std::vector<Integer>(k));
            for(std::size_t s=0;s<steps;++s)for(std::size_t a=0;a<k;++a){rr[s][a]=input.integer();aa[s][a]=input.word();}
            const auto images=compact.row(units,rr,aa);output.word(id);output.word(k);output.word(steps);
            std::vector<Integer> cr(k),ca(k);auto current=units;
            for(std::size_t s=0;s<steps;++s) {
                bool changed=false;
                for(std::size_t a=0;a<k;++a){cr[a]+=rr[s][a]<<260;ca[a]+=aa[s][a]<<312;changed=changed || rr[s][a]!=0;}
                if(changed){const auto image=canonical.regret_policy(cr);current.assign(image.units().begin(),image.units().end());}
                for(std::size_t a=0;a<k;++a) {
                    r::require(cr[a]==(images[s].regrets[a]<<260) && ca[a]==(images[s].averages[a]<<312) &&
                        current[a]==images[s].units[a],"role row compact/canonical coupled image");
                    output.integer(images[s].regrets[a]);output.word(static_cast<std::uint64_t>(images[s].averages[a]));
                    output.word(images[s].units[a]);
                }
            }
        }
        input.end();output.magic("OPLRF001");
        for(const auto value:{compact.work(),compact.quantizer_receipt().work,canonical.receipt().work,
            static_cast<std::uint64_t>(compact.quantizer_receipt().max_input_bits),static_cast<std::uint64_t>(canonical.receipt().max_input_bits),
            static_cast<std::uint64_t>(compact.quantizer_receipt().peak_forecast_bits),static_cast<std::uint64_t>(canonical.receipt().peak_forecast_bits),
            static_cast<std::uint64_t>(compact.rows()),static_cast<std::uint64_t>(compact.steps()),plan.work})output.word(value);
        output.publish();return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
