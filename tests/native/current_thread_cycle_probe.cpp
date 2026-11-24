// Own-thread counter capability/cost probe only. No solver is constructed.
#include <array>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
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

#ifdef _WIN32
namespace {
inline constexpr std::size_t pairs=1024,warmups=32,max_queries=4096,output_cap=32768;
class Output final {
    std::array<char,output_cap> buffer_{};std::size_t size_=0;
public:
    void text(std::string_view value) {
        if(value.size()>buffer_.size()-size_)throw std::runtime_error("cycle probe output cap");
        for(const char ch:value)buffer_[size_++]=ch;
    }
    void number(std::uint64_t value) {
        const auto converted=std::to_chars(buffer_.data()+size_,buffer_.data()+buffer_.size(),value);
        if(converted.ec!=std::errc{})throw std::runtime_error("cycle probe integer formatting cap");
        size_=static_cast<std::size_t>(converted.ptr-buffer_.data());
    }
    void publish() const {std::cout.write(buffer_.data(),static_cast<std::streamsize>(size_));
        if(!std::cout)throw std::runtime_error("cycle probe output write");}
};
}
#endif

int main(int argc,char**) {
    if(argc!=1){std::cerr<<"cycle probe takes no arguments\n";return 2;}
#ifndef _WIN32
    std::cerr<<"current-thread CPU cycle probe requires Windows; no fallback\n";return 2;
#else
    try {
        const auto handle=GetCurrentThread();const auto thread=GetCurrentThreadId();
        std::size_t queries=0;
        const auto query=[&]() -> std::uint64_t {
            if(queries>=max_queries)throw std::runtime_error("cycle probe query cap");
            ++queries;ULONG64 value=0;
            if(!QueryThreadCycleTime(handle,&value))throw std::runtime_error("QueryThreadCycleTime failed:"+std::to_string(GetLastError()));
            return static_cast<std::uint64_t>(value);
        };
        for(std::size_t i=0;i<warmups;++i)(void)query();
        std::array<std::uint64_t,pairs> deltas{};
        const auto first=query();const auto wall_begin=std::chrono::steady_clock::now();
        auto previous=first;
        for(std::size_t i=0;i<pairs;++i) {
            const auto a=query(),b=query();
            if(a<previous || b<a)throw std::runtime_error("nonmonotone current-thread cycles");
            deltas[i]=b-a;previous=b;
        }
        const auto last=query();const auto wall_end=std::chrono::steady_clock::now();
        const auto wall=std::chrono::duration_cast<std::chrono::nanoseconds>(wall_end-wall_begin).count();
        if(last<previous || wall<=0 || GetCurrentThreadId()!=thread || queries!=warmups+2*pairs+2)
            throw std::runtime_error("cycle probe final thread/query/clock invariant");
        Output out;
        out.text("{\"schema\":\"current-thread-cycle-probe-v1\",\"units\":\"cpu_clock_cycles\",\"thread_id\":");out.number(thread);
        out.text(",\"queries\":");out.number(queries);out.text(",\"maximum_queries\":");out.number(max_queries);
        out.text(",\"pair_count\":");out.number(pairs);out.text(",\"warmup_queries\":");out.number(warmups);
        out.text(",\"first\":");out.number(first);out.text(",\"last\":");out.number(last);
        out.text(",\"wall_nanoseconds\":");out.number(static_cast<std::uint64_t>(wall));
        out.text(",\"measured_queries\":");out.number(2*pairs+1);
        out.text(",\"limits\":{\"entries\":65536,\"payload_bits\":1048576,\"stdout_bytes\":32768},\"pair_deltas\":[");
        for(std::size_t i=0;i<pairs;++i){if(i)out.text(",");out.number(deltas[i]);}
        out.text("],\"solver_constructed\":false,\"system_profiler_started\":false}\n");out.publish();return 0;
    }catch(const std::exception& error){std::cerr<<"current-thread-cycle probe: "<<error.what()<<'\n';return 2;}
#endif
}
