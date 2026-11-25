#pragma once
// Separate diagnostic: disjoint numeric helper bodies, sampled at 1/32.
// Includes guards, ledgers and local allocation; not pure integer-op latency.
#include "joint_thread_cycle_recorder.hpp"
namespace openpoker::joint_arithmetic_cycles {
namespace base=joint_thread_cycles;
using base::SystemClock;using base::Install;
inline constexpr std::uint64_t extra_work=655360;
inline constexpr std::size_t entries=2048,payload_bits=131072,stderr_limit=8192;
inline constexpr std::size_t stride=32,maximum_queries=512,maximum_calls=5026;
enum class Family:unsigned {reach,terminal,average,mix};
inline constexpr std::array<std::string_view,4> family_names{"reach","terminal","average","mix"};
inline constexpr std::array<std::uint64_t,4> epoch_calls{1039,606,434,434};
inline thread_local Family current_family=Family::reach;
class Scope final {
    struct Tag {explicit Tag(Family family){current_family=family;}} tag_;
    base::ReadScope scope_;
public:
    explicit Scope(Family family):tag_(family){}
    void close(){scope_.close();}
};
template<class Clock=SystemClock> class Recorder final:public base::Observer {
    using Counts=std::array<std::array<std::uint64_t,4>,2>;
    std::array<std::uint64_t,22> events_{};
    std::array<std::uint64_t,16> calibration_{};
    Counts calls_{},samples_{},cycles_{};
    std::uint64_t owner_=0,origin_=0,last_=0,start_=0;
    std::size_t size_=0,queries_=0,total_=0,epoch_=0,family_=0;
    unsigned offset_=0;
    bool open_=false,sampled_=false,failed_=false;
    void healthy()const{if(failed_)throw std::runtime_error("failed arithmetic-cycle observer");}
    std::uint64_t counter(){
        healthy();check_thread();
        if(queries_==maximum_queries)throw std::runtime_error("arithmetic-cycle query cap");
        ++queries_;const auto value=Clock::read();
        if(value<last_)throw std::runtime_error("nonmonotone arithmetic cycles");
        last_=value;return value;
    }
public:
    Recorder(unsigned offset,bool lazy):offset_(offset){
        if(offset>=stride || lazy)throw std::runtime_error("arithmetic-cycle explicit eager/offset domain");
        owner_=Clock::thread_id();if(!owner_)throw std::runtime_error("arithmetic-cycle owner");
        origin_=counter();for(auto& value:calibration_){const auto a=counter(),b=counter();value=b-a;}
    }
    void check_thread()const override{
        if(Clock::thread_id()!=owner_)throw std::runtime_error("foreign arithmetic-cycle owner");
    }
    void mark(std::string_view name,std::uint64_t epoch){
        healthy();check_thread();
        if(open_ || size_==base::phases.size() || name!=base::phases[size_].name || epoch!=base::phases[size_].epoch)
            throw std::runtime_error("arithmetic-cycle phase schedule");
        const auto value=counter()-origin_;
        if(name=="walk"){
            const auto which=static_cast<std::size_t>(epoch-1);
            std::uint64_t sum=0;for(auto cycles:cycles_[which])sum+=cycles;
            if(calls_[which]!=epoch_calls || sum>value-events_[size_-1])
                throw std::runtime_error("arithmetic-cycle complete disjoint helper census");
        }
        events_[size_++]=value;
    }
    void begin_read()override{
        healthy();check_thread();
        if(open_ || !size_ || base::phases[size_-1].name!="ticket" || total_==maximum_calls)
            throw std::runtime_error("arithmetic-cycle scope/context");
        epoch_=static_cast<std::size_t>(base::phases[size_-1].epoch-1);
        family_=static_cast<std::size_t>(current_family);
        if(epoch_>=2 || family_>=4 || calls_[epoch_][family_]==epoch_calls[family_])
            throw std::runtime_error("arithmetic-cycle family cap");
        sampled_=total_%stride==offset_;++total_;++calls_[epoch_][family_];
        if(sampled_)start_=counter();
        open_=true;
    }
    void end_read()override{
        healthy();check_thread();if(!open_)throw std::runtime_error("arithmetic-cycle unopened scope");
        if(sampled_){
            const auto delta=counter()-start_;
            if(delta>UINT64_MAX-cycles_[epoch_][family_])throw std::runtime_error("arithmetic-cycle overflow");
            cycles_[epoch_][family_]+=delta;++samples_[epoch_][family_];
        }
        open_=false;
    }
    void abandon_read()noexcept override{failed_=true;open_=false;}
    void write(std::ostream& out)const{
        healthy();check_thread();const auto expected_samples=(maximum_calls+stride-1-offset_)/stride;
        std::uint64_t samples=0;for(const auto& epoch:samples_)for(const auto count:epoch)samples+=count;
        if(open_ || size_!=22 || calls_[0]!=epoch_calls || calls_[1]!=epoch_calls || total_!=maximum_calls ||
            samples!=expected_samples || queries_!=55+2*expected_samples)
            throw std::runtime_error("incomplete arithmetic-cycle diagnostic");
        std::array<char,stderr_limit> buffer{};std::size_t used=0;
        const auto text=[&](std::string_view value){
            if(value.size()>buffer.size()-used)throw std::runtime_error("arithmetic-cycle format cap");
            for(char ch:value)buffer[used++]=ch;
        };
        const auto number=[&](std::uint64_t value){
            const auto r=std::to_chars(buffer.data()+used,buffer.data()+buffer.size(),value);
            if(r.ec!=std::errc{})throw std::runtime_error("arithmetic-cycle number cap");
            used=static_cast<std::size_t>(r.ptr-buffer.data());
        };
        const auto array=[&](const auto& values){
            text("[");bool first=true;for(auto value:values){if(!first)text(",");number(value);first=false;}text("]");
        };
        const auto matrix=[&](std::string_view label,const Counts& values){
            text(label);text("[");array(values[0]);text(",");array(values[1]);text("]");
        };
        text("JOINT_ARITHMETIC_CYCLES {\"version\":1,\"units\":\"");text(Clock::units);
        text("\",\"variant\":\"eager\",\"offset\":");number(offset_);text(",\"stride\":32,\"cycle_queries\":");number(queries_);
        text(",\"maximum_queries\":512,\"thread_id\":");number(owner_);
        text(",\"extra_work\":655360,\"metadata_entries\":2048,\"metadata_payload_bits\":131072,\"families\":[\"reach\",\"terminal\",\"average\",\"mix\"],\"empty_pair_cycles\":");array(calibration_);
        matrix(",\"epoch_helper_calls\":",calls_);matrix(",\"epoch_sampled_calls\":",samples_);matrix(",\"epoch_sampled_helper_cycles\":",cycles_);
        text(",\"events\":[");
        for(std::size_t i=0;i<size_;++i){
            if(i)text(",");
            text("[\"");text(base::phases[i].name);text("\",");number(base::phases[i].epoch);text(",");number(events_[i]);text("]");
        }
        const auto actual=32768+256*queries_+64*total_+256*size_+16*stderr_limit;
        if(actual>extra_work)throw std::runtime_error("arithmetic-cycle work reservation");
        text("],\"diagnostic_actual_work\":");number(actual);text("}\n");
        out.write(buffer.data(),static_cast<std::streamsize>(used));if(!out)throw std::runtime_error("arithmetic-cycle output");
    }
};
static_assert(sizeof(Recorder<>)+stderr_limit+512<=payload_bits/8);
static_assert(32768+256*maximum_queries+64*maximum_calls+256*22+16*stderr_limit<=extra_work);
}
