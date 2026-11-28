#pragma once
// Separate typed-TLS diagnostic: sample selection/census inline at 1/32.
// Includes guards, ledgers and local allocation; not pure integer-op latency.
#include "joint_thread_cycle_recorder.hpp"
#include <exception>
namespace openpoker::joint_arithmetic_light_cycles {
namespace base=joint_thread_cycles;
using base::SystemClock;
inline constexpr std::uint64_t extra_work=655360;
inline constexpr std::size_t entries=2048,payload_bits=131072,stderr_limit=8192;
inline constexpr std::size_t stride=32,maximum_queries=512,maximum_calls=5026;
enum class Family:unsigned {reach,terminal,average,mix};
inline constexpr std::array<std::string_view,4> family_names{"reach","terminal","average","mix"};
inline constexpr std::array<std::uint64_t,4> epoch_calls{1039,606,434,434};
template<class Clock> class Recorder;
template<class Clock> inline thread_local Recorder<Clock>* active=nullptr;
inline thread_local const void* installed=nullptr;
template<class Clock=SystemClock> class Recorder final {
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
    Recorder(const Recorder&)=delete;Recorder& operator=(const Recorder&)=delete;
    void check_thread()const{
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
    void begin_read(Family family){
        healthy();
        if(active<Clock> !=this)throw std::runtime_error("foreign/missing light cycle context");
        if(open_ || !size_ || base::phases[size_-1].name!="ticket" || total_==maximum_calls)
            throw std::runtime_error("arithmetic-cycle scope/context");
        epoch_=static_cast<std::size_t>(base::phases[size_-1].epoch-1);
        family_=static_cast<std::size_t>(family);
        if(epoch_>=2 || family_>=4 || calls_[epoch_][family_]==epoch_calls[family_])
            throw std::runtime_error("arithmetic-cycle family cap");
        sampled_=total_%stride==offset_;++total_;++calls_[epoch_][family_];
        if(sampled_)start_=counter();
        open_=true;
    }
    void end_read(){
        healthy();
        if(active<Clock> !=this)throw std::runtime_error("foreign light cycle close");
        if(!open_)throw std::runtime_error("arithmetic-cycle unopened scope");
        if(sampled_){
            const auto delta=counter()-start_;
            if(delta>UINT64_MAX-cycles_[epoch_][family_])throw std::runtime_error("arithmetic-cycle overflow");
            cycles_[epoch_][family_]+=delta;++samples_[epoch_][family_];
        }
        open_=false;
    }
    void abandon_read()noexcept{failed_=true;open_=false;}
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
        text("JOINT_ARITHMETIC_LIGHT_CYCLES {\"version\":2,\"observer_mode\":\"typed-tls-inline-v1\",\"units\":\"");text(Clock::units);
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
// Only sampled calls enter counter(), which checks the actual thread ID.
// Every scope still validates its typed thread-local installation and census.
template<class Clock> class Install final {
    Recorder<Clock>* owner_;
public:
    explicit Install(Recorder<Clock>& owner):owner_(&owner){
        owner.check_thread();
        if(installed || base::active)throw std::runtime_error("nested light cycle observer");
        active<Clock> =owner_;installed=owner_;
    }
    ~Install(){if(installed==owner_){active<Clock> =nullptr;installed=nullptr;}}
    Install(const Install&)=delete;Install& operator=(const Install&)=delete;
};
template<class Clock=SystemClock> class Scope final {
    Recorder<Clock>* owner_=nullptr;
public:
    explicit Scope(Family family){
        auto* candidate=active<Clock>;
        if(!candidate)throw std::runtime_error("missing light cycle observer");
        candidate->begin_read(family);owner_=candidate;
    }
    void close(){
        if(!owner_ || active<Clock> !=owner_)throw std::runtime_error("duplicate/foreign light cycle close");
        owner_->end_read();owner_=nullptr;
    }
    ~Scope(){
        if(owner_){
            if(active<Clock> !=owner_)std::terminate();
            owner_->abandon_read();
        }
    }
    Scope(const Scope&)=delete;Scope& operator=(const Scope&)=delete;
};
static_assert(sizeof(Recorder<>)+stderr_limit+512<=payload_bits/8);
static_assert(32768+256*maximum_queries+64*maximum_calls+256*22+16*stderr_limit<=extra_work);
}
