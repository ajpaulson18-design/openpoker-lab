#pragma once
#include <cstdint>

namespace openpoker::training_phase_trace {
enum class Phase : std::uint8_t {
    plan_preflight, chance_setup, owners_setup, row_registration, freeze, prelude,
    policy_build, policy_emit, walk, commit, checkpoint, average_export, footer
};
enum class Edge : std::uint8_t { begin, end };
struct Sink {
    void* context = nullptr;
    void (*emit)(void*, Phase, Edge, std::uint32_t) noexcept = nullptr;
};
inline void mark(const Sink* sink, Phase phase, Edge edge, std::uint32_t sweep=0) noexcept {
    if (sink && sink->emit) sink->emit(sink->context,phase,edge,sweep);
}
inline constexpr const char* name(Phase phase) noexcept {
    switch (phase) {
    case Phase::plan_preflight: return "plan_preflight";
    case Phase::chance_setup: return "chance_setup";
    case Phase::owners_setup: return "owners_setup";
    case Phase::row_registration: return "row_registration";
    case Phase::freeze: return "freeze";
    case Phase::prelude: return "prelude";
    case Phase::policy_build: return "policy_build";
    case Phase::policy_emit: return "policy_emit";
    case Phase::walk: return "walk";
    case Phase::commit: return "commit";
    case Phase::checkpoint: return "checkpoint";
    case Phase::average_export: return "average_export";
    case Phase::footer: return "footer";
    }
    return "unknown";
}
}
