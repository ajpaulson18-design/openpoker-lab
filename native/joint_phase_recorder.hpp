#pragma once
// Diagnostic targets only. No row timers or standard-target clock calls.
#include <array>
#include <chrono>
#include <charconv>
#include <cstddef>
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
    std::array<Event,24> events_{};
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
        // cerr is unit-buffered: a chain of insertions would flush hundreds
        // of fragments. Build one bounded record and issue one stream write.
        std::array<char,1280> buffer{};std::size_t used=0;
        const auto text=[&](const char* value) {
            while (*value) {
                if (used==buffer.size()) throw std::runtime_error("joint diagnostic text bound");
                buffer[used++]=*value++;
            }
        };
        const auto number=[&](std::uint64_t value) {
            const auto encoded=std::to_chars(buffer.data()+used,buffer.data()+buffer.size(),value);
            if (encoded.ec!=std::errc{}) throw std::runtime_error("joint diagnostic number bound");
            used=static_cast<std::size_t>(encoded.ptr-buffer.data());
        };
        text("JOINT_PHASE_PROFILE {\"version\":1,\"extra_work\":");number(extra_work);
        text(",\"metadata_entries\":");number(entries);text(",\"metadata_payload_bits\":");number(payload_bits);
        text(",\"clock_reads\":");number(size_+1);text(",\"events\":[");
        for (std::size_t i=0;i<size_;++i) {
            if (i) text(",");
            text("[\"");text(events_[i].phase);text("\",");number(events_[i].epoch);
            text(",");number(events_[i].ns);text("]");
        }
        text("]}\n");out.write(buffer.data(),static_cast<std::streamsize>(used));
        if (!out) throw std::runtime_error("joint diagnostic output failure");
    }
};
// Fixed metadata uses <=256 64-bit words, including overlapping JSON scratch.
static_assert(sizeof(Recorder)+1280<=2048);
#undef OPENPOKER_JOINT_DIAGNOSTIC_NOINLINE
}
