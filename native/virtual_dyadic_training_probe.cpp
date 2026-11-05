#include "virtual_dyadic_training.hpp"
#include <array>
#include <cstdio>
#include <iostream>
#include <string_view>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

namespace training=openpoker::virtual_dyadic_training;
namespace {
enum class Mode { admit, train, admit_paired, train_paired, admit_packed, train_packed };

Mode request() {
    std::array<char,64> buffer{};
    std::size_t length=0;
    for (;;) {
        const auto next=std::cin.get();
        if (next=='\n') break;
        training::require(next!=std::char_traits<char>::eof() && length<buffer.size(),
            "expected one bounded LF-terminated dyadic request");
        buffer[length++]=static_cast<char>(next);
    }
    training::require(std::cin.peek()==std::char_traits<char>::eof() && !std::cin.bad(),
        "trailing dyadic request bytes");
    const std::string_view line(buffer.data(),length);
    if (line=="DYADIC_T2_V1 ADMIT") return Mode::admit;
    if (line=="DYADIC_T2_V1 TRAIN") return Mode::train;
    if (line=="DYADIC_T2_V1 ADMIT_PAIRED") return Mode::admit_paired;
    if (line=="DYADIC_T2_V1 TRAIN_PAIRED") return Mode::train_paired;
    if (line=="DYADIC_T2_V1 ADMIT_PACKED") return Mode::admit_packed;
    if (line=="DYADIC_T2_V1 TRAIN_PACKED") return Mode::train_packed;
    throw training::Error("unsupported fixed dyadic request");
}

void admit(const training::Driver& driver) {
    const auto& plan=driver.plan();
    const auto& counts=plan.shape;
    std::cout<<"{\"protocol\":\"DYADIC_T2_V1\",\"status\":\"ADMITTED\",\"training_invocations\":0,"
        "\"target_passes\":0,\"completed_sweeps\":0,\"rank_calls\":0,\"rows\":"<<counts.rows
        <<",\"slots\":"<<counts.slots<<",\"visits\":"<<counts.visits<<",\"actions\":"<<counts.actions
        <<",\"reveals\":"<<counts.reveals<<",\"candidates\":"<<counts.candidates
        <<",\"folds\":"<<counts.folds<<",\"showdowns\":"<<counts.showdowns
        <<",\"showdown_contractions_per_pass\":"<<plan.showdown_contractions
        <<",\"hidden_completion_candidates_per_pass\":"<<plan.hidden_candidates
        <<",\"literal_nodes\":"<<training::literal_count<<",\"requested_sweeps\":"<<training::sweeps;
    if (plan.traversal==training::Traversal::paired) std::cout<<",\"public_walks_per_sweep\":1";
    if (plan.packed_averages) std::cout<<",\"packed_average_limbs\":"<<plan.packed_average_limbs
        <<",\"packed_average_work\":"<<plan.packed_average_work;
    std::cout<<",\"H\":"<<plan.H<<",\"M\":"<<plan.M<<",\"D_bits\":"<<plan.denominator_bits
        <<",\"value_bits\":"<<training::value_bits<<",\"normalizer\":"<<plan.normalizer
        <<",\"d5\":"<<training::chance_divisors[3]<<",\"entries\":"<<plan.entries
        <<",\"payload_bits\":"<<plan.payload_bits<<",\"output_bytes\":"<<plan.output_bytes
        <<",\"expected_rank_calls\":"<<plan.expected_rank_calls
        <<",\"first_uniform_exponent\":"<<plan.max_first_exponent
        <<",\"max_actor_depth\":["<<plan.max_actor_depth[0]<<','<<plan.max_actor_depth[1]<<']'
        <<",\"prefix_counts\":[";
    for (std::size_t i=0;i<plan.prefixes.size();++i) {
        if (i) std::cout<<',';
        std::cout<<plan.prefixes[i].count;
    }
    std::cout<<"],\"prefix_supported_rows\":[";
    for (std::size_t i=0;i<plan.prefixes.size();++i) {
        if (i) std::cout<<',';
        std::cout<<'['<<plan.prefixes[i].supported[0]<<','<<plan.prefixes[i].supported[1]<<']';
    }
    std::cout<<"],\"planned_total_work\":"<<plan.total_work
        <<",\"component_work\":{\"template\":"<<plan.template_work<<",\"chance\":"<<plan.chance_work
        <<",\"history\":"<<plan.history_work<<",\"state\":"<<plan.state_work
        <<",\"quantizer\":"<<plan.quantizer_work<<",\"parent\":"<<training::sum_work(plan.parent)
        <<"},\"quantizer_terms\":["<<plan.quantizer_terms[0]<<','<<plan.quantizer_terms[1]<<','<<plan.quantizer_terms[2]
        <<"],\"parent_work\":{";
    for (std::size_t i=0;i<plan.parent.size();++i) {
        if (i) std::cout<<',';
        std::cout<<'"'<<training::work_names[i]<<"\":"<<plan.parent[i];
    }
    std::cout<<"},\"actual_admission_work\":"<<plan.template_work+driver.admission_work()<<"}\n";
    std::cout.flush();
    training::require(bool(std::cout),"dyadic admission output failed");
}
} // namespace

int main() {
    try {
#ifdef _WIN32
        training::require(_setmode(_fileno(stdin),_O_BINARY)!=-1 && _setmode(_fileno(stdout),_O_BINARY)!=-1,
            "could not establish exact binary transport");
#endif
        std::ios::sync_with_stdio(false);
        const auto mode=request();
        const bool packed=mode==Mode::admit_packed || mode==Mode::train_packed;
        const bool paired=packed || mode==Mode::admit_paired || mode==Mode::train_paired;
        training::Driver driver(paired?training::Traversal::paired:training::Traversal::by_seat,packed);
        if (mode==Mode::admit || mode==Mode::admit_paired || mode==Mode::admit_packed) admit(driver);
        else driver.train(std::cout);
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<"DYADIC_T2_V1 ERROR "<<error.what()<<'\n';
        return 2;
    }
}
