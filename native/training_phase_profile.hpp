#pragma once
#include "training_phase_trace.hpp"
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <span>

namespace openpoker::training_phase_profile {
using training_phase_trace::Phase;
using training_phase_trace::Edge;
using training_phase_trace::Sink;
inline constexpr std::size_t capacity=64;
inline constexpr std::size_t clock_limit=80;
inline constexpr std::size_t metadata_bytes_reserved=2048;
inline constexpr std::size_t metadata_entries_reserved=256;
inline constexpr std::uint64_t work_allowance=8192;
struct Event { Phase phase; Edge edge; std::uint32_t sweep; std::uint64_t ns; };

template<class Clock=std::chrono::steady_clock> class BasicRecorder final {
    std::array<Event,capacity> events_{};
    std::size_t size_=0, reads_=0;
    typename Clock::time_point origin_{}, last_{};
    bool healthy_=true;
    static void callback(void* context,Phase phase,Edge edge,std::uint32_t sweep) noexcept {
        if (context) static_cast<BasicRecorder*>(context)->record(phase,edge,sweep);
    }
    void record(Phase phase,Edge edge,std::uint32_t sweep) noexcept {
        if (!healthy_) return;
        if (static_cast<unsigned>(phase)>static_cast<unsigned>(Phase::footer) ||
            (edge!=Edge::begin && edge!=Edge::end) || size_==capacity) {
            healthy_=false; return;
        }
        const auto ns=now_ns();
        if (healthy_) events_[size_++]={phase,edge,sweep,ns};
    }
public:
    BasicRecorder() noexcept {
        try { origin_=last_=Clock::now(); reads_=1; }
        catch (...) { healthy_=false; }
    }
    BasicRecorder(const BasicRecorder&)=delete;
    BasicRecorder& operator=(const BasicRecorder&)=delete;
    BasicRecorder(BasicRecorder&&)=delete;
    BasicRecorder& operator=(BasicRecorder&&)=delete;
    [[nodiscard]] std::uint64_t now_ns() noexcept {
        if (!healthy_) return 0;
        if (reads_>=clock_limit) { healthy_=false; return 0; }
        try {
            const auto current=Clock::now(); ++reads_;
            if (current<last_ || current<origin_) { healthy_=false; return 0; }
            last_=current;
            const auto duration=std::chrono::duration_cast<std::chrono::nanoseconds>(current-origin_).count();
            if (duration<0) { healthy_=false; return 0; }
            return static_cast<std::uint64_t>(duration);
        } catch (...) { healthy_=false; return 0; }
    }
    [[nodiscard]] Sink sink() noexcept { return {this,&callback}; }
    [[nodiscard]] std::span<const Event> events() const noexcept { return {events_.data(),size_}; }
    [[nodiscard]] bool healthy() const noexcept { return healthy_; }
    [[nodiscard]] std::size_t clock_reads() const noexcept { return reads_; }
};
using Recorder=BasicRecorder<>;
static_assert(sizeof(Recorder)<=metadata_bytes_reserved);
}
