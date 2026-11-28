#pragma once
// Diagnostic targets only. Standard targets do not include this header.
#include <array>
#include <charconv>
#include <cstddef>
#include <cstdint>
#include <ostream>
#include <stdexcept>
#include <string_view>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0600
#endif
#include <windows.h>
#endif

namespace openpoker::joint_thread_cycles {
inline constexpr std::uint64_t extra_work=524288;
inline constexpr std::size_t entries=2048,payload_bits=131072,stderr_limit=8192;
inline constexpr std::size_t maximum_queries=512,maximum_reads=868,stride=4;
struct Phase {std::string_view name;std::uint64_t epoch;};
inline constexpr std::array<Phase,22> phases{{
    {"begin",0},{"range_input",0},{"template",0},{"chance",0},{"owners",0},{"header",0},
    {"epoch_begin",1},{"ticket",1},{"walk",1},{"stage",1},{"release",1},{"commit",1},{"snapshot",1},
    {"epoch_begin",2},{"ticket",2},{"walk",2},{"stage",2},{"release",2},{"commit",2},{"snapshot",2},
    {"footer",0},{"publish",0}}};
struct SystemClock {
    static constexpr std::string_view units="cpu_clock_cycles";
    static std::uint64_t thread_id() {
#ifdef _WIN32
        return GetCurrentThreadId();
#else
        throw std::runtime_error("own-thread cycle diagnostics require Windows; no fallback");
#endif
    }
    static std::uint64_t read() {
#ifdef _WIN32
        ULONG64 value=0;
        if(!QueryThreadCycleTime(GetCurrentThread(),&value))
            throw std::runtime_error("own-thread cycle query failed");
        return static_cast<std::uint64_t>(value);
#else
        throw std::runtime_error("own-thread cycle diagnostics require Windows; no fallback");
#endif
    }
};
class Observer {
public:
    virtual void check_thread() const=0;
    virtual void begin_read()=0;
    virtual void end_read()=0;
    virtual void abandon_read() noexcept=0;
    virtual ~Observer()=default;
};
inline thread_local Observer* active=nullptr;
class Install final {
    Observer* owner_;
public:
    explicit Install(Observer& owner):owner_(&owner) {
        owner.check_thread();
        if(active)throw std::runtime_error("nested thread-cycle observer");
        active=owner_;
    }
    ~Install() {if(active==owner_)active=nullptr;}
    Install(const Install&)=delete;Install& operator=(const Install&)=delete;
};
class ReadScope final {
    Observer* owner_=nullptr;
public:
    ReadScope() {
        if(!active)throw std::runtime_error("missing thread-cycle observer");
        active->begin_read();owner_=active;
    }
    void close() {
        if(!owner_)throw std::runtime_error("duplicate thread-cycle read close");
        owner_->end_read();owner_=nullptr;
    }
    ~ReadScope() {if(owner_)owner_->abandon_read();}
    ReadScope(const ReadScope&)=delete;ReadScope& operator=(const ReadScope&)=delete;
};

template<class Clock=SystemClock> class Recorder final:public Observer {
    std::array<std::uint64_t,22> events_{};
    std::array<std::uint64_t,16> calibration_{};
    std::array<std::uint64_t,2> reads_{},samples_{},read_cycles_{};
    std::uint64_t owner_=0,origin_=0,last_=0,read_start_=0;
    std::size_t size_=0,queries_=0,read_total_=0,read_epoch_=0;
    unsigned offset_=0;
    bool lazy_=false,open_=false,sampled_=false,failed_=false;
    void healthy() const {if(failed_)throw std::runtime_error("failed thread-cycle observer");}
    std::uint64_t counter() {
        healthy();check_thread();
        if(queries_==maximum_queries)throw std::runtime_error("thread-cycle query cap");
        ++queries_;const auto value=Clock::read();
        if(value<last_)throw std::runtime_error("nonmonotone thread cycles");
        last_=value;return value;
    }
public:
    Recorder(unsigned offset,bool lazy):offset_(offset),lazy_(lazy) {
        if(offset>=stride)throw std::runtime_error("thread-cycle sampling offset");
        owner_=Clock::thread_id();if(!owner_)throw std::runtime_error("invalid thread-cycle owner");
        origin_=counter();
        for(auto& value:calibration_){const auto a=counter(),b=counter();value=b-a;}
    }
    void check_thread() const override {
        if(Clock::thread_id()!=owner_)throw std::runtime_error("foreign thread-cycle owner");
    }
    void mark(std::string_view name,std::uint64_t epoch) {
        healthy();check_thread();
        if(open_ || size_==phases.size() || name!=phases[size_].name || epoch!=phases[size_].epoch)
            throw std::runtime_error("thread-cycle phase schedule");
        const auto value=counter()-origin_;
        if(name=="walk") {
            const auto which=static_cast<std::size_t>(epoch-1);
            if(reads_[which]!=434 || read_cycles_[which]>value-events_[size_-1])
                throw std::runtime_error("thread-cycle complete disjoint read census");
        }
        events_[size_++]=value;
    }
    void begin_read() override {
        healthy();check_thread();
        if(open_ || !size_ || phases[size_-1].name!="ticket" || read_total_==maximum_reads)
            throw std::runtime_error("thread-cycle read scope/context");
        read_epoch_=static_cast<std::size_t>(phases[size_-1].epoch-1);
        if(read_epoch_>=2 || reads_[read_epoch_]==434)throw std::runtime_error("thread-cycle epoch read cap");
        sampled_=read_total_%stride==offset_;++read_total_;++reads_[read_epoch_];
        if(sampled_)read_start_=counter();
        open_=true;
    }
    void end_read() override {
        healthy();check_thread();if(!open_)throw std::runtime_error("thread-cycle unopened read");
        if(sampled_) {
            const auto delta=counter()-read_start_;
            if(delta>UINT64_MAX-read_cycles_[read_epoch_])throw std::runtime_error("thread-cycle sum overflow");
            read_cycles_[read_epoch_]+=delta;++samples_[read_epoch_];
        }
        open_=false;
    }
    void abandon_read() noexcept override {failed_=true;open_=false;}
    void write(std::ostream& out) const {
        healthy();check_thread();
        if(open_ || size_!=phases.size() || reads_!=std::array<std::uint64_t,2>{434,434} ||
            samples_[0]+samples_[1]!=217 || queries_!=489)
            throw std::runtime_error("incomplete thread-cycle diagnostic");
        std::array<char,stderr_limit> buffer{};std::size_t used=0;
        const auto text=[&](std::string_view value) {
            if(value.size()>buffer.size()-used)throw std::runtime_error("thread-cycle format capacity");
            for(char ch:value)buffer[used++]=ch;
        };
        const auto number=[&](std::uint64_t value) {
            const auto converted=std::to_chars(buffer.data()+used,buffer.data()+buffer.size(),value);
            if(converted.ec!=std::errc{})throw std::runtime_error("thread-cycle number capacity");
            used=static_cast<std::size_t>(converted.ptr-buffer.data());
        };
        text("JOINT_THREAD_CYCLES {\"version\":1,\"units\":\"");text(Clock::units);
        text("\",\"variant\":\"");text(lazy_?"lazy":"eager");text("\",\"offset\":");number(offset_);
        text(",\"stride\":4,\"cycle_queries\":");number(queries_);text(",\"maximum_queries\":512,\"thread_id\":");number(owner_);
        text(",\"extra_work\":");number(extra_work);text(",\"metadata_entries\":");number(entries);
        text(",\"metadata_payload_bits\":");number(payload_bits);
        const auto array=[&](std::string_view label,const auto& values) {
            text(label);text("[");bool first=true;
            for(const auto value:values){if(!first)text(",");number(value);first=false;}text("]");
        };
        array(",\"empty_pair_cycles\":",calibration_);array(",\"epoch_read_calls\":",reads_);
        array(",\"epoch_sampled_calls\":",samples_);array(",\"epoch_sampled_read_cycles\":",read_cycles_);
        text(",\"events\":[");
        for(std::size_t i=0;i<size_;++i) {
            if(i)text(",");
            text("[\"");text(phases[i].name);text("\",");number(phases[i].epoch);
            text(",");number(events_[i]);text("]");
        }
        text("]");
        // Charge the maximum output allowance so the receipt never depends
        // on its own decimal length; all diagnostic work is separate from stdout.
        const auto actual=32768+256*queries_+256*read_total_+256*size_+16*stderr_limit;
        if(actual>extra_work)throw std::runtime_error("thread-cycle work reservation");
        text(",\"diagnostic_actual_work\":");number(actual);text("}\n");
        out.write(buffer.data(),static_cast<std::streamsize>(used));
        if(!out)throw std::runtime_error("thread-cycle output write");
    }
};
static_assert(sizeof(Recorder<>)+stderr_limit+512<=payload_bits/8);
static_assert(entries*8==payload_bits/8);
static_assert(32768+256*maximum_queries+256*maximum_reads+256*phases.size()+16*stderr_limit<=extra_work);
}
