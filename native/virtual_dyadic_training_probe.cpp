#include "virtual_dyadic_training.hpp"
#include <array>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string_view>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

namespace training=openpoker::virtual_dyadic_training;
namespace {
enum class Mode { admit, train, admit_paired, train_paired, admit_packed, train_packed, admit_compact, train_compact,
                  admit_scaled, train_scaled, admit_sealed, train_sealed, admit_paged, train_paged,
                  admit_directory, train_directory, admit_rank_sets, train_rank_sets, admit_split, train_split,
                  admit_ten, train_ten, admit_ten_buffered, train_ten_buffered,
                  admit_ten_virtual_zero, train_ten_virtual_zero, admit_ten_ordered_state, train_ten_ordered_state,
                  admit_ten_row_coverage, train_ten_row_coverage, admit_ten_shared_policy, train_ten_shared_policy,
                  admit_ten_paged_directory, train_ten_paged_directory,
                  admit_ten_sweep_stream, train_ten_sweep_stream,
                  admit_ten_sparse_chance, train_ten_sparse_chance,
                  admit_ten_single_division, train_ten_single_division,
                  admit_ten_phase_payload, train_ten_phase_payload,
                  admit_ten_row_batched, train_ten_row_batched,
                  admit_ten_indexed_cache, train_ten_indexed_cache,
                  admit_proof9_t3, train_proof9_t3, admit_proof9_t4, train_proof9_t4, admit_proof9_q32, train_proof9_q32 };

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
    if (line=="DYADIC_T2_V1 ADMIT_COMPACT") return Mode::admit_compact;
    if (line=="DYADIC_T2_V1 TRAIN_COMPACT") return Mode::train_compact;
    if (line=="DYADIC_T2_V1 ADMIT_SCALED") return Mode::admit_scaled;
    if (line=="DYADIC_T2_V1 TRAIN_SCALED") return Mode::train_scaled;
    if (line=="DYADIC_T2_V1 ADMIT_SEALED") return Mode::admit_sealed;
    if (line=="DYADIC_T2_V1 TRAIN_SEALED") return Mode::train_sealed;
    if (line=="DYADIC_T2_V1 ADMIT_PAGED") return Mode::admit_paged;
    if (line=="DYADIC_T2_V1 TRAIN_PAGED") return Mode::train_paged;
    if (line=="DYADIC_T2_V1 ADMIT_DIRECTORY") return Mode::admit_directory;
    if (line=="DYADIC_T2_V1 TRAIN_DIRECTORY") return Mode::train_directory;
    if (line=="DYADIC_T2_V1 ADMIT_RANK_SETS") return Mode::admit_rank_sets;
    if (line=="DYADIC_T2_V1 TRAIN_RANK_SETS") return Mode::train_rank_sets;
    if (line=="DYADIC_T2_V1 ADMIT_SPLIT") return Mode::admit_split;
    if (line=="DYADIC_T2_V1 TRAIN_SPLIT") return Mode::train_split;
    if (line=="DYADIC_T2_V1 ADMIT_TEN") return Mode::admit_ten;
    if (line=="DYADIC_T2_V1 TRAIN_TEN") return Mode::train_ten;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_BUFFERED") return Mode::admit_ten_buffered;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_BUFFERED") return Mode::train_ten_buffered;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_VIRTUAL_ZERO") return Mode::admit_ten_virtual_zero;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_VIRTUAL_ZERO") return Mode::train_ten_virtual_zero;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_ORDERED_STATE") return Mode::admit_ten_ordered_state;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_ORDERED_STATE") return Mode::train_ten_ordered_state;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_ROW_COVERAGE") return Mode::admit_ten_row_coverage;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_ROW_COVERAGE") return Mode::train_ten_row_coverage;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_SHARED_POLICY") return Mode::admit_ten_shared_policy;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_SHARED_POLICY") return Mode::train_ten_shared_policy;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_PAGED_DIRECTORY") return Mode::admit_ten_paged_directory;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_PAGED_DIRECTORY") return Mode::train_ten_paged_directory;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_SWEEP_STREAM") return Mode::admit_ten_sweep_stream;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_SWEEP_STREAM") return Mode::train_ten_sweep_stream;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_SPARSE_CHANCE") return Mode::admit_ten_sparse_chance;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_SPARSE_CHANCE") return Mode::train_ten_sparse_chance;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_SINGLE_DIVISION") return Mode::admit_ten_single_division;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_SINGLE_DIVISION") return Mode::train_ten_single_division;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_PHASE_PAYLOAD") return Mode::admit_ten_phase_payload;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_PHASE_PAYLOAD") return Mode::train_ten_phase_payload;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_ROW_BATCHED") return Mode::admit_ten_row_batched;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_ROW_BATCHED") return Mode::train_ten_row_batched;
    if (line=="DYADIC_T2_V1 ADMIT_TEN_INDEXED_CACHE") return Mode::admit_ten_indexed_cache;
    if (line=="DYADIC_T2_V1 TRAIN_TEN_INDEXED_CACHE") return Mode::train_ten_indexed_cache;
    if (line=="DYADIC_T3_V1 ADMIT_PROOF9_T3") return Mode::admit_proof9_t3;
    if (line=="DYADIC_T3_V1 TRAIN_PROOF9_T3") return Mode::train_proof9_t3;
    if (line=="DYADIC_T4_V1 ADMIT_PROOF9_T4") return Mode::admit_proof9_t4;
    if (line=="DYADIC_T4_V1 TRAIN_PROOF9_T4") return Mode::train_proof9_t4;
    if (line=="DYADIC_T32_V1 ADMIT_PROOF9_Q32") return Mode::admit_proof9_q32;
    if (line=="DYADIC_T32_V1 TRAIN_PROOF9_Q32") return Mode::train_proof9_q32;
    throw training::Error("unsupported fixed dyadic request");
}

void admit(const training::Driver& driver,bool sweep_stream=false,bool proof9_t3=false,bool proof9_t4=false) {
    if (sweep_stream) driver.validate_sweep_stream();
    const auto& plan=driver.plan();
    const auto& counts=plan.shape;
    const bool q32=plan.proof9_quality32();
    std::cout<<"{\"protocol\":\""<<(q32?"DYADIC_T32_V1":proof9_t4?"DYADIC_T4_V1":proof9_t3?"DYADIC_T3_V1":"DYADIC_T2_V1")<<"\",\"status\":\"ADMITTED\",\"training_invocations\":0,"
        "\"target_passes\":0,\"completed_sweeps\":0,\"rank_calls\":0,\"rows\":"<<counts.rows
        <<",\"slots\":"<<counts.slots<<",\"visits\":"<<counts.visits<<",\"actions\":"<<counts.actions
        <<",\"reveals\":"<<counts.reveals<<",\"candidates\":"<<counts.candidates
        <<",\"folds\":"<<counts.folds<<",\"showdowns\":"<<counts.showdowns
        <<",\"showdown_contractions_per_pass\":"<<plan.showdown_contractions
        <<",\"hidden_completion_candidates_per_pass\":"<<plan.hidden_candidates
        <<",\"literal_nodes\":"<<training::literal_count<<",\"requested_sweeps\":"<<plan.requested_sweeps;
    if (plan.traversal==training::Traversal::paired) std::cout<<",\"public_walks_per_sweep\":1";
    if (plan.packed_averages) std::cout<<",\"packed_average_limbs\":"<<plan.packed_average_limbs
        <<",\"packed_average_work\":"<<plan.packed_average_work;
    if (plan.packed_regrets) std::cout<<",\"packed_regret_limbs\":"<<plan.packed_regret_limbs
        <<",\"packed_regret_work\":"<<plan.packed_regret_work<<",\"parent_allowance\":"<<plan.parent_allowance;
    if (plan.scaled_averages) std::cout<<",\"scaled_average_build_work\":"<<plan.scaled_average_build_work;
    if (plan.sealed_menus) std::cout<<",\"sealed_menu_count\":"<<plan.sealed_menu_count
        <<",\"sealed_token_count\":"<<plan.sealed_token_count;
    if (plan.paged_strategy) {
        const auto& pages=plan.page_limits;
        std::cout<<",\"paging_work\":"<<plan.paging_work<<",\"page_image_words\":"<<pages.image_words
            <<",\"page_words\":"<<pages.page_words<<",\"page_cache_pages\":"<<pages.cache_pages
            <<",\"page_cache_banks\":"<<pages.cache_banks<<",\"page_read_word_limit\":"<<pages.read_words
            <<",\"page_write_word_limit\":"<<pages.write_words<<",\"page_request_limit\":"<<pages.requests
            <<",\"page_resident_bytes\":"<<training::state::State::pager_resident_bytes(pages,plan.row_coverage);
        if (pages.stage_split_words)
            std::cout<<",\"page_stage_split_words\":"<<pages.stage_split_words
                <<",\"page_write_request_limit\":"<<pages.write_requests;
        if (pages.virtual_initial_zero) std::cout<<",\"page_virtual_initial_zero\":true";
        if (plan.row_coverage) std::cout<<",\"page_state_row_coverage\":true";
    }
    if (plan.compact_directory)
        std::cout<<",\"directory_work\":"<<plan.directory_work
            <<",\"directory_record_bytes\":"<<training::state::State::compact_record_bytes
            <<",\"directory_index_slots\":"<<(plan.ordered_state?0:training::state::State::compact_index_slots(plan.shape.rows));
    if (plan.ordered_state)
        std::cout<<",\"ordered_registration\":true,\"export_workspace_reused\":"
            <<(plan.shared_policy?"false":"true")<<",\"registration_path_work\":"
            <<plan.registration_path_work;
    if (plan.shared_policy)
        std::cout<<",\"shared_policy\":true,\"streamed_average\":true,\"policy_spill_work\":"<<plan.policy_spill_work
            <<",\"policy_spill_word_limit\":"<<counts.slots-counts.rows
            <<",\"policy_spill_read_call_limit\":"<<3*counts.rows;
    if (plan.paged_directory)
        std::cout<<",\"paged_row_directory\":true,\"row_directory_entries\":"
            <<training::state::State::row_directory_resident_entries
            <<",\"row_directory_page_limit\":"<<plan.admitted_directory_page_limit
            <<",\"row_directory_read_call_limit\":"<<(plan.bounded_proof9()?2+4*plan.requested_sweeps:10)*counts.rows;
    if (plan.rank_board_sets)
        std::cout<<",\"rank_cache_planes\":"<<plan.rank_planes
            <<",\"rank_lookup_work_per_query\":"
            <<(plan.indexed_cache?training::prepared::PreparedPublicChance::sorted_lookup_work(plan.rank_planes):
                training::prepared::PreparedPublicChance::board_set_probe_work*plan.rank_planes);
    if (plan.split_checkpoint)
        std::cout<<",\"split_checkpoint\":true,\"checkpoint_image_bytes\":"<<8*plan.page_limits.image_words;
    if (plan.ten_card()) std::cout<<",\"ten_card\":true";
    if (plan.sparse_chance) std::cout<<",\"sparse_chance\":true";
    if (plan.single_division) std::cout<<",\"single_division\":true";
    if (plan.phase_payload) std::cout<<",\"phase_payload\":true,\"state_payload_bits\":"<<plan.state_payload;
    if (plan.row_batched) std::cout<<",\"row_batched\":true";
    if (plan.indexed_cache)
        std::cout<<",\"sorted_rank_index\":true,\"rank_index_entries\":"
            <<training::prepared::PreparedPublicChance::index_storage_entries(plan.rank_planes)
            <<",\"rank_index_update_work\":"<<training::prepared::PreparedPublicChance::index_update_work(plan.rank_planes)
            <<",\"rank_index_setup_work\":"<<training::prepared::PreparedPublicChance::index_setup_work(plan.rank_planes);
    std::cout<<",\"H\":"<<plan.H<<",\"M\":"<<plan.M<<",\"D_bits\":"<<plan.denominator_bits
        <<",\"value_bits\":"<<plan.game().value_bits<<",\"normalizer\":"<<plan.normalizer
        <<",\"d5\":"<<plan.game().divisors[3]<<",\"entries\":"<<plan.entries
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
    std::cout<<"},\"actual_admission_work\":"<<plan.template_work+driver.admission_work();
    if (q32) std::cout<<",\"proof9_quality32\":true,\"general_quantizer_work\":"<<plan.general_quantizer_work;
    if (proof9_t3) std::cout<<",\"proof9_t3\":true,\"general_quantizer_work\":"<<plan.general_quantizer_work;
    if (proof9_t4) std::cout<<",\"proof9_t4\":true,\"general_quantizer_work\":"<<plan.general_quantizer_work;
    if (sweep_stream || proof9_t3 || proof9_t4 || q32) std::cout<<",\"sweep_stream\":{\"version\":1,\"frames\":"
        <<(q32?training::proof9_q32_sweep_stream_frames:proof9_t4?training::proof9_t4_sweep_stream_frames:proof9_t3?training::proof9_t3_sweep_stream_frames:training::sweep_stream_frames)
        <<",\"frame_header_bytes\":"<<training::sweep_stream_header_bytes
        <<",\"image_bytes\":"<<(q32?training::proof9_q32_sweep_stream_image_bytes:proof9_t4?training::proof9_t4_sweep_stream_image_bytes:proof9_t3?training::proof9_t3_sweep_stream_image_bytes:training::sweep_stream_image_bytes)
        <<",\"wire_bytes\":"<<(q32?training::proof9_q32_sweep_stream_wire_bytes:proof9_t4?training::proof9_t4_sweep_stream_wire_bytes:proof9_t3?training::proof9_t3_sweep_stream_wire_bytes:training::sweep_stream_wire_bytes)
        <<",\"retained_bytes\":"<<(q32?training::proof9_q32_sweep_stream_retained_bytes:proof9_t4?training::proof9_t4_sweep_stream_retained_bytes:proof9_t3?training::proof9_t3_sweep_stream_retained_bytes:training::sweep_stream_retained_bytes)
        <<",\"read_bytes\":"<<(q32?training::proof9_q32_sweep_stream_read_bytes:proof9_t4?training::proof9_t4_sweep_stream_read_bytes:proof9_t3?training::proof9_t3_sweep_stream_read_bytes:training::sweep_stream_read_bytes)
        <<",\"scratch_bytes\":"<<training::sweep_stream_scratch_bytes
        <<",\"copy_work\":"<<(q32?training::proof9_q32_sweep_stream_copy_work:proof9_t4?training::proof9_t4_sweep_stream_copy_work:proof9_t3?training::proof9_t3_sweep_stream_copy_work:training::sweep_stream_copy_work)<<'}';
    std::cout<<"}\n";
    std::cout.flush();
    training::require(bool(std::cout),"dyadic admission output failed");
}

void save_paging(const std::filesystem::path& scratch,const training::paging::Receipt& receipt,bool virtual_zero) {
    std::ofstream stream(scratch/"paging.json",std::ios::binary);
    training::require(bool(stream),"paged receipt open failed");
    stream<<"{\"read_words\":"<<receipt.read_words<<",\"logical_read_words\":"<<receipt.logical_read_words
        <<",\"write_words\":"<<receipt.write_words<<",\"read_calls\":"<<receipt.read_calls
        <<",\"stage_calls\":"<<receipt.stage_calls<<",\"physical_read_requests\":"<<receipt.physical_read_requests
        <<",\"physical_write_requests\":"<<receipt.physical_write_requests<<",\"cache_hits\":"<<receipt.cache_hits
        <<",\"cache_misses\":"<<receipt.cache_misses<<",\"completed_sweeps\":"<<receipt.completed_sweeps;
    if (virtual_zero) stream<<",\"synthetic_read_calls\":"<<receipt.synthetic_read_calls
        <<",\"synthetic_read_words\":"<<receipt.synthetic_read_words;
    stream<<"}\n";
    stream.close();
    training::require(bool(stream),"paged receipt write failed");
}
void save_policy(const std::filesystem::path& scratch,std::span<const training::state::PolicySpillSweep> receipt) {
    std::ofstream stream(scratch/"policy.json",std::ios::binary);
    training::require(bool(stream),"policy receipt open failed");
    stream<<'[';
    for (std::size_t sweep=0;sweep<receipt.size();++sweep) {
        if (sweep) stream<<',';
        const auto& counts=receipt[sweep];
        stream<<"{\"uniform_rows\":"<<counts.uniform_rows<<",\"pure_rows\":"<<counts.pure_rows
            <<",\"mixed_rows\":"<<counts.mixed_rows<<",\"extent_words\":"<<counts.extent_words
            <<",\"write_words\":"<<counts.write_words<<",\"read_calls\":"<<counts.read_calls
            <<",\"mixed_read_calls\":"<<counts.mixed_read_calls<<",\"read_words\":"<<counts.read_words<<'}';
    }
    stream<<"]\n";
    stream.close();
    training::require(bool(stream),"policy receipt write failed");
}
void save_directory(std::filesystem::path scratch,const training::state::RowDirectoryReceipt& receipt) {
    scratch+="-rows";
    std::ofstream stream(scratch/"rows.json",std::ios::binary);
    training::require(bool(stream),"row receipt open failed");
    stream<<"{\"appended_rows\":"<<receipt.appended_rows<<",\"build_snapshots\":"<<receipt.build_snapshots
        <<",\"read_calls\":"<<receipt.read_calls<<",\"cache_hits\":"<<receipt.cache_hits
        <<",\"page_reads\":"<<receipt.page_reads<<",\"read_rows\":"<<receipt.read_rows
        <<",\"write_calls\":"<<receipt.write_calls<<",\"written_rows\":"<<receipt.written_rows<<"}\n";
    stream.close();
    training::require(bool(stream),"row receipt write failed");
}
void save_rank_index(const std::filesystem::path& scratch,const training::prepared::RankIndexReceipt& receipt) {
    std::ofstream stream(scratch/"rank-index.json",std::ios::binary);
    training::require(bool(stream),"rank index receipt open failed");
    stream<<"{\"capacity\":"<<receipt.capacity<<",\"entries\":"<<receipt.entries<<",\"size\":"<<receipt.size
        <<",\"searches\":"<<receipt.searches<<",\"updates\":"<<receipt.updates
        <<",\"lookup_work\":"<<receipt.lookup_work<<",\"update_work\":"<<receipt.update_work
        <<",\"setup_work\":"<<receipt.setup_work<<"}\n";
    stream.close();
    training::require(bool(stream),"rank index receipt write failed");
}
void save_divisions(const std::filesystem::path& scratch,std::uint64_t count) {
    std::ofstream stream(scratch/"quantizer.json",std::ios::binary);
    training::require(bool(stream),"quantizer receipt open failed");
    stream<<"{\"combined_divisions\":"<<count<<"}\n";
    stream.close();
    training::require(bool(stream),"quantizer receipt write failed");
}
} // namespace

int main(int argc,char* argv[]) {
    try {
#ifdef _WIN32
        training::require(_setmode(_fileno(stdin),_O_BINARY)!=-1 && _setmode(_fileno(stdout),_O_BINARY)!=-1,
            "could not establish exact binary transport");
#endif
        std::ios::sync_with_stdio(false);
        const auto mode=request();
        const bool paged_train=mode==Mode::train_paged || mode==Mode::train_directory ||
            mode==Mode::train_rank_sets || mode==Mode::train_split || mode==Mode::train_ten ||
            mode==Mode::train_ten_buffered || mode==Mode::train_ten_virtual_zero || mode==Mode::train_ten_ordered_state ||
            mode==Mode::train_ten_row_coverage || mode==Mode::train_ten_shared_policy ||
            mode==Mode::train_ten_paged_directory || mode==Mode::train_ten_sweep_stream ||
            mode==Mode::train_proof9_t3 || mode==Mode::train_proof9_t4 || mode==Mode::train_ten_sparse_chance ||
            mode==Mode::train_ten_single_division || mode==Mode::train_ten_phase_payload ||
            mode==Mode::train_ten_row_batched || mode==Mode::train_ten_indexed_cache || mode==Mode::train_proof9_q32;
        training::require(argc==(paged_train?2:1),"fixed request scratch argument count");
        const std::filesystem::path scratch=paged_train?std::filesystem::path(argv[1]):std::filesystem::path{};
        if (paged_train) training::require(scratch.is_absolute() && scratch.filename()=="page-images",
            "paged request needs an absolute private page-images directory");
        auto profile=training::StrategyProfile::dense;
        if (mode==Mode::admit_proof9_q32 || mode==Mode::train_proof9_q32)
            profile=training::StrategyProfile::proof9_quality32;
        else if (mode==Mode::admit_proof9_t4 || mode==Mode::train_proof9_t4)
            profile=training::StrategyProfile::proof9_four_sweep;
        else if (mode==Mode::admit_proof9_t3 || mode==Mode::train_proof9_t3)
            profile=training::StrategyProfile::proof9_three_sweep;
        else if (mode==Mode::admit_ten_sparse_chance || mode==Mode::train_ten_sparse_chance)
            profile=training::StrategyProfile::ten_card_sparse_chance;
        else if (mode==Mode::admit_ten_single_division || mode==Mode::train_ten_single_division)
            profile=training::StrategyProfile::ten_card_single_division;
        else if (mode==Mode::admit_ten_indexed_cache || mode==Mode::train_ten_indexed_cache)
            profile=training::StrategyProfile::ten_card_indexed_cache;
        else if (mode==Mode::admit_ten_row_batched || mode==Mode::train_ten_row_batched)
            profile=training::StrategyProfile::ten_card_row_batched;
        else if (mode==Mode::admit_ten_phase_payload || mode==Mode::train_ten_phase_payload)
            profile=training::StrategyProfile::ten_card_phase_payload;
        else if (mode==Mode::admit_ten_paged_directory || mode==Mode::train_ten_paged_directory ||
            mode==Mode::admit_ten_sweep_stream || mode==Mode::train_ten_sweep_stream)
            profile=training::StrategyProfile::ten_card_paged_directory;
        else if (mode==Mode::admit_ten_shared_policy || mode==Mode::train_ten_shared_policy)
            profile=training::StrategyProfile::ten_card_shared_policy;
        else if (mode==Mode::admit_ten_row_coverage || mode==Mode::train_ten_row_coverage)
            profile=training::StrategyProfile::ten_card_row_coverage;
        else if (mode==Mode::admit_ten_ordered_state || mode==Mode::train_ten_ordered_state)
            profile=training::StrategyProfile::ten_card_ordered_state;
        else if (mode==Mode::admit_ten_virtual_zero || mode==Mode::train_ten_virtual_zero)
            profile=training::StrategyProfile::ten_card_virtual_zero;
        else if (mode==Mode::admit_ten_buffered || mode==Mode::train_ten_buffered)
            profile=training::StrategyProfile::ten_card_buffered;
        else if (mode==Mode::admit_ten || mode==Mode::train_ten) profile=training::StrategyProfile::ten_card;
        else if (mode==Mode::admit_split || mode==Mode::train_split) profile=training::StrategyProfile::split_checkpoint;
        else if (mode==Mode::admit_rank_sets || mode==Mode::train_rank_sets) profile=training::StrategyProfile::rank_sets;
        else if (mode==Mode::admit_directory || mode==Mode::train_directory) profile=training::StrategyProfile::directory;
        else if (mode==Mode::admit_paged || paged_train) profile=training::StrategyProfile::paged;
        else if (mode==Mode::admit_sealed || mode==Mode::train_sealed) profile=training::StrategyProfile::sealed;
        else if (mode==Mode::admit_scaled || mode==Mode::train_scaled) profile=training::StrategyProfile::scaled;
        else if (mode==Mode::admit_compact || mode==Mode::train_compact) profile=training::StrategyProfile::compact;
        else if (mode==Mode::admit_packed || mode==Mode::train_packed) profile=training::StrategyProfile::packed_averages;
        const bool paired=profile!=training::StrategyProfile::dense || mode==Mode::admit_paired || mode==Mode::train_paired;
        training::Driver driver(paired?training::Traversal::paired:training::Traversal::by_seat,profile);
        if (mode==Mode::admit || mode==Mode::admit_paired || mode==Mode::admit_packed ||
            mode==Mode::admit_compact || mode==Mode::admit_scaled || mode==Mode::admit_sealed ||
            mode==Mode::admit_paged || mode==Mode::admit_directory || mode==Mode::admit_rank_sets ||
            mode==Mode::admit_split || mode==Mode::admit_ten || mode==Mode::admit_ten_buffered ||
            mode==Mode::admit_ten_virtual_zero || mode==Mode::admit_ten_ordered_state ||
            mode==Mode::admit_ten_row_coverage || mode==Mode::admit_ten_shared_policy ||
            mode==Mode::admit_ten_paged_directory || mode==Mode::admit_ten_sweep_stream ||
            mode==Mode::admit_proof9_t3 || mode==Mode::admit_proof9_t4 || mode==Mode::admit_ten_sparse_chance ||
            mode==Mode::admit_ten_single_division || mode==Mode::admit_ten_phase_payload ||
            mode==Mode::admit_ten_row_batched || mode==Mode::admit_ten_indexed_cache || mode==Mode::admit_proof9_q32)
            admit(driver,mode==Mode::admit_ten_sweep_stream || mode==Mode::admit_proof9_t3 ||
                  mode==Mode::admit_proof9_t4 || mode==Mode::admit_ten_sparse_chance || mode==Mode::admit_ten_single_division ||
                  mode==Mode::admit_ten_phase_payload || mode==Mode::admit_ten_row_batched ||
                  mode==Mode::admit_ten_indexed_cache || mode==Mode::admit_proof9_q32,
                mode==Mode::admit_proof9_t3,mode==Mode::admit_proof9_t4);
        else {
            const auto io=driver.train(std::cout,scratch,mode==Mode::train_ten_sweep_stream ||
                mode==Mode::train_proof9_t3 || mode==Mode::train_proof9_t4 || mode==Mode::train_ten_sparse_chance ||
                mode==Mode::train_ten_single_division || mode==Mode::train_ten_phase_payload ||
                mode==Mode::train_ten_row_batched || mode==Mode::train_ten_indexed_cache || mode==Mode::train_proof9_q32);
            if (io.paging) save_paging(scratch,*io.paging,driver.plan().page_limits.virtual_initial_zero);
            if (io.policy) save_policy(scratch,*io.policy);
            if (io.bounded_policy) save_policy(scratch,{io.bounded_policy.get(),io.bounded_policy_count});
            if (io.directory) save_directory(scratch,*io.directory);
            if (io.combined_divisions) save_divisions(scratch,io.combined_divisions);
            if (io.rank_index) save_rank_index(scratch,*io.rank_index);
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<"DYADIC_T2_V1 ERROR "<<error.what()<<'\n';
        return 2;
    }
}
