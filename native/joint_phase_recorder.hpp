#pragma once
// Diagnostic targets only. No row timers or standard-target clock calls.
#include <array>
#include <chrono>
#include <cstdint>
#include <ostream>
#include <stdexcept>

namespace openpoker::joint_phase_profile {
#if defined(_MSC_VER)
#define OPENPOKER_JOINT_DIAGNOSTIC_NOINLINE __declspec(noinline)
#elif defined(__GNUC__) || defined(__clang__)
#define OPENPOKER_JOINT_DIAGNOSTIC_NOINLINE __attribute__((noinline))
#else
#define OPENPOKER_JOINT_DIAGNOSTIC_NOINLINE
#endif
inline constexpr std::uint64_t extra_work=8192+16*4096;
inline constexpr std::size_t entries=256,payload_bits=2048*8,stderr_limit=4096;
class Recorder final {
    struct Event {const char* phase=nullptr;std::uint64_t epoch=0,ns=0;};
    std::array<Event,32> events_{};
    std::size_t size_=0;
    std::chrono::steady_clock::time_point origin_=std::chrono::steady_clock::now(),last_=origin_;
public:
    OPENPOKER_JOINT_DIAGNOSTIC_NOINLINE void mark(const char* phase,std::uint64_t epoch) {
        if (size_==events_.size() || epoch>2) throw std::runtime_error("joint diagnostic capacity");
        const auto current=std::chrono::steady_clock::now();
        if (current<last_) throw std::runtime_error("joint diagnostic nonmonotonic clock");
        last_=current;
        events_[size_++]={phase,epoch,static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(current-origin_).count())};
    }
    OPENPOKER_JOINT_DIAGNOSTIC_NOINLINE void write(std::ostream& out) const {
        out<<"JOINT_PHASE_PROFILE {\"version\":1,\"extra_work\":"<<extra_work
            <<",\"metadata_entries\":"<<entries<<",\"metadata_payload_bits\":"<<payload_bits
            <<",\"clock_reads\":"<<size_+1<<",\"events\":[";
        for (std::size_t i=0;i<size_;++i) {
            if (i) out<<',';
            out<<"[\""<<events_[i].phase<<"\","<<events_[i].epoch<<','<<events_[i].ns<<']';
        }
        out<<"]}\n";
        if (!out) throw std::runtime_error("joint diagnostic output failure");
    }
};
static_assert(sizeof(Recorder)<=2048);
#undef OPENPOKER_JOINT_DIAGNOSTIC_NOINLINE
}
