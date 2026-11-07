#pragma once
// Persistent simultaneous CFR+ state. The enclosing trainer authenticates menus,
// physical support and the common fixed game denominator before calling this owner.
#include "dyadic_policy.hpp"
#include "virtual_dyadic_history.hpp"
#include "virtual_dyadic_paged_image.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <optional>
#include <span>
#include <stdexcept>
#include <string_view>
#include <tuple>
#include <utility>

namespace openpoker::virtual_dyadic_state {
using Integer = exact_binary64::Integer;
using History = virtual_dyadic_history::History;
enum class ErrorCode { invalid_limits, invalid_forecast, invalid_scale,
    invalid_row, changed_menu, capacity, phase, integer_width, work_limit,
    failed_owner, arithmetic };
class Error final : public std::runtime_error {
    ErrorCode code_;
public:
    Error(ErrorCode code, const char* message) : std::runtime_error(message), code_(code) {}
    [[nodiscard]] ErrorCode code() const noexcept { return code_; }
};
struct Limits {
    std::uint64_t work = 500000000;
    std::size_t integer_bits = 65536, entries = 2000000;
    std::size_t integer_payload_bits = std::size_t{1} << 30;
};
inline constexpr std::uint64_t proof10_work_cap = 810000000;
inline constexpr std::size_t proof10_payload_cap = 1200000000;
struct Forecast {
    std::size_t rows = 0, slots = 0, sweeps = 0, max_history_depth = 0;
    std::size_t value_bits = 0;
    // Two disjoint cumulative allowances. A whole-game preflight must justify
    // these for the requested workload; constructor admission alone cannot.
    std::uint64_t own_work = 0, quantizer_work = 0;
};
struct ActionCatalogCapacity {
    std::size_t keys = 0, token_slots = 0;
    bool sealed = false;
};
struct PackedAverageCapacity {
    // Exact word census per image. regret_limbs is zero in the legacy
    // average-only mode; nonzero enables the dual packed representation.
    std::size_t limb_count = 0;
    std::size_t regret_limbs = 0;
};
enum class Lifecycle { fixed_two_sweep, bounded_v1 };
struct PagedStrategy {
    std::filesystem::path scratch;
    virtual_dyadic_paged_image::Limits limits;
    bool compact_rows=false;
    bool ordered_rows=false;
    bool row_coverage=false;
    bool shared_policy=false;
    bool paged_directory=false;
    std::size_t directory_page_limit=0;
    Lifecycle lifecycle=Lifecycle::fixed_two_sweep;
};
struct StorageForecast { std::size_t entries = 0, payload_bits = 0; };
struct ActionStorage {
    std::size_t token_slots, catalog_keys, stored_tokens, stored_menus;
    std::size_t token_slot_bytes, catalog_key_bytes;
    [[nodiscard]] std::size_t array_bytes() const noexcept {
        return token_slots*token_slot_bytes+catalog_keys*catalog_key_bytes;
    }
};
struct Receipt {
    std::uint64_t work = 0, state_work = 0, quantizer_work = 0;
    std::size_t rows = 0, slots = 0, completed_sweeps = 0, staged_rows = 0;
    std::size_t reserved_entries = 0, reserved_integer_and_text_payload_bits = 0;
    std::size_t peak_input_bits = 0, peak_arithmetic_bits = 0;
};
struct Row {
    std::size_t history_ordinal = 0, actor = 0, holding_index = 0;
    std::size_t offset = 0;
    std::span<const std::string_view> actions;
};
struct RowDescriptor {
    Row row;
    std::size_t average_offset=0,average_shift=0,regret_offset=0,regret_shift=0;
};
struct PolicySnapshot {
    RowDescriptor descriptor;
    std::span<const std::uint64_t> units;
};
struct RowDirectoryReceipt {
    std::size_t appended_rows=0,build_snapshots=0,read_calls=0,cache_hits=0,page_reads=0,
                read_rows=0,write_calls=0,written_rows=0;
};
struct AverageExport {
    dyadic_policy::ImageKind kind = dyadic_policy::ImageKind::exported_average;
    std::size_t rows = 0, slots = 0;
    std::unique_ptr<std::uint64_t[]> units;
    std::unique_ptr<unsigned char[]> uniform_fallback;
    std::unique_ptr<Integer[]> raw_masses;
};
struct ScaledAverageIncrements {
    std::span<const Integer> values;
    std::size_t shift = 0;
};
struct PolicySpillSweep {
    std::size_t uniform_rows=0,pure_rows=0,mixed_rows=0,extent_words=0;
    std::size_t write_words=0,read_calls=0,mixed_read_calls=0,read_words=0;
};
using PolicySpillReceipt = std::array<PolicySpillSweep,2>;
struct CheckpointEpoch {
    std::size_t sweep=0,current_slot=0,previous_sweep=0,previous_slot=0,image_words=0;
    bool previous_is_virtual=false;
};

class State final {
    using Key = std::tuple<std::size_t,std::size_t,std::size_t>;
    using RegistrationOrder = std::pair<History::DecisionPath,std::size_t>;
    using ActionText = std::array<char,64>;
    using Menu = std::span<const std::string_view>;
    struct PackedRow { std::size_t limb_offset = 0, shift = 0; };
    struct PackedRegretRow { std::size_t limb_offset = 0, shift = 0; };
    struct CompactRow {
        std::uint64_t history;
        std::uint32_t offset, average_offset, regret_offset;
        std::uint16_t source, average_shift, regret_shift;
        std::uint8_t actor, holding, policy_tag=0;
    };
    static_assert(sizeof(CompactRow)==32);
    class RowDirectory {
        using Wire = std::array<std::uint64_t,4>;
        static constexpr std::size_t page_rows=128,cache_pages=8;
        const std::size_t rows_,page_limit_,read_limit_;
        std::fstream file_;
        std::array<Wire,page_rows*cache_pages> cache_{};
        std::array<std::size_t,cache_pages> tags_{};
        std::array<bool,cache_pages> valid_{};
        Wire last_{};
        RowDirectoryReceipt receipt_{};
        bool ready_=false,failed_=false;

        void flush_build(std::size_t count) {
            file_.write(reinterpret_cast<const char*>(cache_.data()),static_cast<std::streamsize>(count*sizeof(Wire)));
            if (!file_) throw std::runtime_error("cannot append row directory");
            ++receipt_.write_calls;
            receipt_.written_rows+=count;
        }
        static CompactRow decode(const Wire& words) {
            if (words[3]>>32) throw std::runtime_error("row directory reserved bits differ");
            return {words[0],static_cast<std::uint32_t>(words[1]),static_cast<std::uint32_t>(words[1]>>32),
                static_cast<std::uint32_t>(words[2]),static_cast<std::uint16_t>(words[2]>>32),
                static_cast<std::uint16_t>(words[2]>>48),static_cast<std::uint16_t>(words[3]),
                static_cast<std::uint8_t>(words[3]>>16),static_cast<std::uint8_t>(words[3]>>24)};
        }
    public:
        RowDirectory(std::filesystem::path scratch,std::size_t rows,std::size_t page_limit,std::size_t read_limit)
            :rows_(rows),page_limit_(page_limit),read_limit_(read_limit) {
            if (!rows || !page_limit || !read_limit || page_limit>read_limit)
                throw std::invalid_argument("invalid row directory bounds");
            scratch+="-rows";
            std::error_code error;
            if (!std::filesystem::create_directory(scratch,error) || error)
                throw std::runtime_error("fresh row directory could not be reserved");
            file_.open(scratch/"rows.bin",std::ios::binary|std::ios::in|std::ios::out|std::ios::trunc);
            if (!file_) throw std::runtime_error("cannot open row directory");
        }
        void append(const CompactRow& row) {
            try {
                if (failed_ || ready_ || receipt_.appended_rows>=rows_ || row.policy_tag)
                    throw std::logic_error("invalid ordered directory append");
                last_={row.history,static_cast<std::uint64_t>(row.offset)|(static_cast<std::uint64_t>(row.average_offset)<<32),
                    row.regret_offset|(static_cast<std::uint64_t>(row.source)<<32)|(static_cast<std::uint64_t>(row.average_shift)<<48),
                    row.regret_shift|(static_cast<std::uint64_t>(row.actor)<<16)|(static_cast<std::uint64_t>(row.holding)<<24)};
                cache_[receipt_.appended_rows%page_rows]=last_;
                ++receipt_.appended_rows;
                if (receipt_.appended_rows%page_rows==0) flush_build(page_rows);
            } catch (...) {failed_=true;throw;}
        }
        void freeze() {
            try {
                if (failed_ || ready_ || receipt_.appended_rows!=rows_)
                    throw std::logic_error("row directory build is incomplete");
                const auto remaining=rows_%page_rows;
                if (remaining) flush_build(remaining);
                file_.flush();
                if (!file_ || receipt_.written_rows!=rows_ || file_.tellp()!=static_cast<std::streamoff>(32*rows_))
                    throw std::runtime_error("row directory extent differs");
                ready_=true;
            } catch (...) {failed_=true;throw;}
        }
        CompactRow get(std::size_t row) {
            try {
                if (failed_ || row>=receipt_.appended_rows) throw std::out_of_range("row directory index");
                if (!ready_) {
                    if (row+1!=receipt_.appended_rows || receipt_.build_snapshots>=rows_)
                        throw std::logic_error("building directory exposes only its last append");
                    ++receipt_.build_snapshots;
                    return decode(last_);
                }
                if (receipt_.read_calls>=read_limit_) throw std::length_error("row directory lookup cap");
                const auto page=row/page_rows,slot=page%cache_pages;
                if (!valid_[slot] || tags_[slot]!=page) {
                    if (receipt_.page_reads>=page_limit_) throw std::length_error("row directory page-read cap");
                    const auto count=std::min(page_rows,rows_-page*page_rows);
                    valid_[slot]=false;
                    file_.seekg(static_cast<std::streamoff>(32*page*page_rows));
                    file_.read(reinterpret_cast<char*>(cache_.data()+slot*page_rows),
                        static_cast<std::streamsize>(count*sizeof(Wire)));
                    if (!file_) throw std::runtime_error("short row directory page");
                    tags_[slot]=page;valid_[slot]=true;
                    ++receipt_.page_reads;receipt_.read_rows+=count;
                } else ++receipt_.cache_hits;
                ++receipt_.read_calls;
                return decode(cache_[slot*page_rows+row%page_rows]);
            } catch (...) {failed_=true;throw;}
        }
        bool failed() const noexcept {return failed_;}
        const RowDirectoryReceipt& receipt() const noexcept {return receipt_;}
    };
    static constexpr std::size_t row_directory_entries=4608;
    static_assert(sizeof(RowDirectory)<=8*row_directory_entries);
    class PolicySpill {
        static constexpr std::uint8_t uniform_tag=1,mixed_tag=22;
        const std::size_t rows_,words_;
        const std::size_t generations_;
        std::fstream file_;
        PolicySpillReceipt receipt_{};
        std::unique_ptr<PolicySpillSweep[]> bounded_receipt_;
        std::size_t sweeps_=0,next_word_=0;
        bool ready_=false;

        static std::uint64_t uniform(std::size_t count,std::size_t action) noexcept {
            const auto q=dyadic_policy::grid_units;
            return q/count+static_cast<std::uint64_t>(action<q%count);
        }
    public:
        PolicySpill(std::size_t rows,std::size_t words,std::size_t generations=2,bool bounded_lifecycle=false)
            :rows_(rows),words_(words),generations_(generations) {
            if (!generations_ || generations_>8) throw std::invalid_argument("invalid policy spill generation bound");
            if (bounded_lifecycle) bounded_receipt_=std::make_unique<PolicySpillSweep[]>(generations_);
        }

        PolicySpillSweep& current_receipt() noexcept {
            return bounded_receipt_?bounded_receipt_[sweeps_-1]:receipt_[sweeps_-1];
        }
        const PolicySpillSweep& current_receipt() const noexcept {
            return bounded_receipt_?bounded_receipt_[sweeps_-1]:receipt_[sweeps_-1];
        }

        void begin(const std::filesystem::path& path) {
            if (sweeps_==generations_ || (sweeps_ && !ready_))
                throw std::logic_error("invalid policy spill generation");
            if (file_.is_open()) {
                file_.close();
                if (!file_) throw std::runtime_error("cannot close policy spill");
            }
            file_.open(path,std::ios::binary|std::ios::in|std::ios::out|std::ios::trunc);
            if (!file_) throw std::runtime_error("cannot open policy spill");
            ++sweeps_;
            if (bounded_receipt_) bounded_receipt_[sweeps_-1]=PolicySpillSweep{};
            next_word_=0;
            ready_=false;
        }

        [[nodiscard]] std::uint8_t append(std::size_t offset,std::span<const std::uint64_t> units) {
            if (!sweeps_ || ready_ || units.size()<2 || units.size()>20 || offset!=next_word_ ||
                units.size()-1>words_-next_word_)
                throw std::logic_error("invalid policy spill row extent");
            auto& census=current_receipt();
            if (census.uniform_rows+census.pure_rows+census.mixed_rows>=rows_)
                throw std::length_error("policy spill row cap");
            next_word_+=units.size()-1;
            bool is_uniform=true;
            std::uint8_t pure=0;
            std::uint64_t sum=0;
            const auto q=dyadic_policy::grid_units;
            for (std::size_t action=0;action<units.size();++action) {
                const auto unit=units[action];
                if (unit>q-sum) throw std::logic_error("policy spill grid sum overflow");
                sum+=unit;
                if (unit==q) pure=static_cast<std::uint8_t>(2+action);
                is_uniform=is_uniform && unit==uniform(units.size(),action);
            }
            if (sum!=q) throw std::logic_error("policy spill grid sum differs");
            if (is_uniform) {++census.uniform_rows;return uniform_tag;}
            if (pure) {++census.pure_rows;return pure;}
            const auto words=units.first(units.size()-1);
            file_.seekp(static_cast<std::streamoff>(8*offset));
            file_.write(reinterpret_cast<const char*>(words.data()),static_cast<std::streamsize>(words.size_bytes()));
            if (!file_) throw std::runtime_error("cannot write policy spill row");
            ++census.mixed_rows;
            census.write_words+=words.size();
            census.extent_words=next_word_;
            return mixed_tag;
        }

        void finish() {
            if (!sweeps_ || ready_) throw std::logic_error("policy spill finish requires active build");
            const auto& counts=current_receipt();
            if (next_word_!=words_ || counts.uniform_rows+counts.pure_rows+counts.mixed_rows!=rows_)
                throw std::logic_error("incomplete policy spill build");
            file_.flush();
            if (!file_) throw std::runtime_error("cannot flush policy spill");
            ready_=true;
        }

        void load(std::uint8_t tag,std::size_t offset,std::span<std::uint64_t> output) {
            if (!ready_ || output.size()<2 || output.size()>20 || offset>words_ || output.size()-1>words_-offset)
                throw std::logic_error("invalid frozen policy spill extent");
            auto& counts=current_receipt();
            if (counts.read_calls>=3*rows_) throw std::length_error("policy spill read request cap");
            if (tag==uniform_tag) {
                for (std::size_t action=0;action<output.size();++action) output[action]=uniform(output.size(),action);
            } else if (tag>=2 && tag<2+output.size()) {
                std::fill(output.begin(),output.end(),std::uint64_t{0});
                output[tag-2]=dyadic_policy::grid_units;
            } else if (tag==mixed_tag) {
                const auto words=output.first(output.size()-1);
                if (offset+words.size()>counts.extent_words || words.size()>3*words_-counts.read_words)
                    throw std::length_error("policy spill physical read bound");
                file_.seekg(static_cast<std::streamoff>(8*offset));
                file_.read(reinterpret_cast<char*>(words.data()),static_cast<std::streamsize>(words.size_bytes()));
                if (!file_) throw std::runtime_error("short frozen policy spill read");
                auto left=dyadic_policy::grid_units;
                for (const auto unit:words) {
                    if (unit>left) throw std::runtime_error("invalid frozen policy spill grid");
                    left-=unit;
                }
                output.back()=left;
                ++counts.mixed_read_calls;
                counts.read_words+=words.size();
            } else throw std::logic_error("unknown frozen policy tag");
            ++counts.read_calls;
        }

        [[nodiscard]] const PolicySpillReceipt& receipt() const noexcept {return receipt_;}
        [[nodiscard]] std::span<const PolicySpillSweep> receipts() const noexcept {
            return bounded_receipt_?std::span<const PolicySpillSweep>(bounded_receipt_.get(),sweeps_):
                std::span<const PolicySpillSweep>(receipt_.data(),sweeps_);
        }
        [[nodiscard]] bool bounded() const noexcept {return bounded_receipt_!=nullptr;}
    };
    static constexpr std::size_t policy_spill_entries=128;
    static_assert(sizeof(PolicySpill)+20*sizeof(std::uint64_t)<=8*policy_spill_entries);
    enum class Phase { building, closed, sweeping };
    enum class PackedField { average, regret };
    static constexpr std::size_t page_codec_words=11;
    const History* history_;
    std::array<std::size_t,2> hand_counts_;
    Forecast forecast_;
    Limits limits_;
    const ActionCatalogCapacity catalog_;
    const PackedAverageCapacity packed_;
    const std::optional<PagedStrategy> paged_;
    const StorageForecast storage_;
    dyadic_policy::Quantizer quantizer_;
    Receipt receipt_{};
    Integer denominator_;
    std::unique_ptr<Row[]> rows_;
    std::unique_ptr<CompactRow[]> compact_rows_;
    std::unique_ptr<RowDirectory> row_directory_;
    std::unique_ptr<std::uint32_t[]> compact_index_;
    std::size_t compact_index_slots_=0;
    std::size_t compact_probe_limit_=0;
    std::optional<RegistrationOrder> last_registration_;
    std::unique_ptr<ActionText[]> action_text_;
    std::unique_ptr<std::string_view[]> action_views_;
    std::unique_ptr<Menu[]> action_catalog_;
    std::size_t stored_tokens_ = 0, stored_menus_ = 0;
    std::map<Key,std::size_t> index_;
    std::unique_ptr<Integer[]> regrets_, averages_, staged_regrets_, staged_averages_;
    std::unique_ptr<PackedRow[]> packed_rows_;
    std::unique_ptr<PackedRegretRow[]> packed_regret_rows_;
    std::unique_ptr<std::uint64_t[]> packed_averages_, staged_packed_averages_;
    std::unique_ptr<std::uint64_t[]> packed_regrets_, staged_packed_regrets_;
    std::unique_ptr<virtual_dyadic_paged_image::Image> paged_image_;
    std::size_t packed_words_registered_ = 0, packed_regret_words_registered_ = 0;
    std::unique_ptr<std::uint64_t[]> units_;
    std::unique_ptr<unsigned char[]> seen_;
    std::unique_ptr<PolicySpill> policy_spill_;
    Phase phase_ = Phase::building;
    mutable bool failed_ = false;
    bool exported_ = false;

    [[noreturn]] static void fail(ErrorCode code, const char* message) { throw Error(code,message); }
    static std::uint64_t plus(std::uint64_t a,std::uint64_t b) {
        if (b>std::numeric_limits<std::uint64_t>::max()-a) fail(ErrorCode::invalid_forecast,"state count overflow");
        return a+b;
    }
    static std::uint64_t times(std::uint64_t a,std::uint64_t b) {
        if (a && b>std::numeric_limits<std::uint64_t>::max()/a) fail(ErrorCode::invalid_forecast,"state count overflow");
        return a*b;
    }
    static std::size_t logceil(std::size_t n) {
        std::size_t answer=0;
        for (std::size_t v=n ? n-1 : 0;v;v>>=1) ++answer;
        return answer;
    }
    static std::uint64_t words(std::size_t bits) { return (static_cast<std::uint64_t>(bits)+63)/64; }
    static std::size_t width(const Integer& value) {
        try { return exact_binary64::detail::magnitude_bits(value,65536,
                exact_binary64::ErrorCode::input_bit_limit); }
        catch (const exact_binary64::ConversionError&) { fail(ErrorCode::integer_width,"state source integer width"); }
    }
    static bool proof10(const std::optional<PagedStrategy>& paged) {
        return paged && paged->limits.profile==virtual_dyadic_paged_image::Profile::proof10;
    }
    static Forecast admit(Forecast f, Limits limits, std::array<std::size_t,2> hands,
                          const std::optional<PagedStrategy>& paged) {
        const bool expanded=proof10(paged);
        if (!limits.work || limits.work>(expanded?proof10_work_cap:500000000) || !limits.integer_bits ||
            limits.integer_bits>(expanded?dyadic_policy::proof10_integer_bits:65536) ||
            !limits.entries || limits.entries>2000000 || !limits.integer_payload_bits ||
            limits.integer_payload_bits>(expanded?proof10_payload_cap:(std::size_t{1}<<30)))
            fail(ErrorCode::invalid_limits,"invalid reduce-only state limits");
        if (!hands[0] || !hands[1] || hands[0]>1326 || hands[1]>1326 || !f.rows || !f.slots ||
            f.slots<f.rows || f.slots>times(20,f.rows) || !f.sweeps || !f.max_history_depth ||
            f.max_history_depth>64 || !f.value_bits || f.value_bits>limits.integer_bits ||
            plus(f.value_bits,58)>limits.integer_bits || !f.own_work || !f.quantizer_work ||
            plus(f.own_work,f.quantizer_work)>limits.work ||
            (expanded && (hands!=std::array<std::size_t,2>{2,2} ||
                          f.quantizer_work>dyadic_policy::proof10_work_cap)))
            fail(ErrorCode::invalid_forecast,"invalid state dimensions or work partition");
        return f;
    }
    static dyadic_policy::Limits policy_limits(const Forecast& f, const Limits& limits,
                                              const std::optional<PagedStrategy>& paged) {
        // Maximum menu20: 32 retained + (12*20+64) scratch logical entries.
        return {f.quantizer_work,limits.integer_bits,336,
            std::min(limits.integer_payload_bits,std::size_t{1}<<30),
            proof10(paged)?dyadic_policy::Profile::proof10:dyadic_policy::Profile::legacy};
    }
    static ActionCatalogCapacity admit_catalog(const Forecast& f, ActionCatalogCapacity capacity) {
        if (!capacity.keys && !capacity.token_slots) {
            if (capacity.sealed) fail(ErrorCode::invalid_forecast,"sealed state requires an action catalog");
            return capacity;
        }
        if (!capacity.keys || !capacity.token_slots ||
            (capacity.sealed ? capacity.keys>250000 : capacity.keys>f.rows) || capacity.token_slots>f.slots)
            fail(ErrorCode::invalid_forecast,"invalid state action catalog dimensions");
        // The original reservation covers three logical entries and 64 text
        // bytes per slot. Account for the catalog spans inside those same
        // bounds. Their array initialization also fits the original slot work.
        if (!capacity.sealed && (plus(times(3,capacity.token_slots),times(2,capacity.keys))>times(3,f.slots) ||
            plus(times(sizeof(ActionText),capacity.token_slots),times(sizeof(Menu),capacity.keys))>
                times(sizeof(ActionText),f.slots)))
            fail(ErrorCode::capacity,"state action catalog exceeds original footprint");
        return capacity;
    }
    [[nodiscard]] std::size_t token_capacity() const noexcept {
        return catalog_.keys?catalog_.token_slots:forecast_.slots;
    }
    [[nodiscard]] bool packed() const noexcept { return packed_.limb_count!=0; }
    [[nodiscard]] bool packed_regrets() const noexcept { return packed_.regret_limbs!=0; }
    [[nodiscard]] bool compact() const noexcept {return paged_ && paged_->compact_rows;}
    [[nodiscard]] bool disk_rows() const noexcept {return paged_ && paged_->paged_directory;}
    CompactRow compact_record(std::size_t row) const {
        const auto record=row_directory_?row_directory_->get(row):compact_rows_[row];
        if (row_directory_) {
            try {
                if (record.source>=catalog_.keys || record.actor>1 || record.holding>=hand_counts_[record.actor] ||
                    record.average_shift>=forecast_.value_bits || record.regret_shift>=forecast_.value_bits)
                    fail(ErrorCode::invalid_row,"invalid directory row identity");
                const auto menu=action_catalog_[record.source].size();
                if (!menu || record.offset>forecast_.slots || menu>forecast_.slots-record.offset ||
                    record.average_offset>packed_.limb_count ||
                    menu*packed_stride(record.average_shift)>packed_.limb_count-record.average_offset ||
                    record.regret_offset>packed_.regret_limbs ||
                    menu*packed_stride(record.regret_shift)>packed_.regret_limbs-record.regret_offset)
                    fail(ErrorCode::invalid_row,"invalid directory row extent");
            } catch (...) {failed_=true;throw;}
        }
        return record;
    }
    RowDescriptor describe_row(std::size_t row) const {
        index_bound(row);
        if (compact()) {
            const auto info=compact_record(row);
            return {{info.history,info.actor,info.holding,info.offset,action_catalog_[info.source]},
                info.average_offset,info.average_shift,info.regret_offset,info.regret_shift};
        }
        const auto average=packed()?packed_rows_[row]:PackedRow{};
        const auto regret=packed_regrets()?packed_regret_rows_[row]:PackedRegretRow{};
        return {rows_[row],average.limb_offset,average.shift,regret.limb_offset,regret.shift};
    }
    std::uint8_t policy_tag(std::size_t row) const noexcept {
        return disk_rows()?static_cast<std::uint8_t>(seen_[row]&31):compact_rows_[row].policy_tag;
    }
    bool row_seen(std::size_t row) const noexcept {return disk_rows()?(seen_[row]&128)!=0:seen_[row]!=0;}
    static StorageForecast admit_storage(const Forecast& f,const Limits& limits,
                                         ActionCatalogCapacity catalog,PackedAverageCapacity packed,
                                         const std::optional<PagedStrategy>& paged) {
        if (paged && paged->scratch.empty())
            fail(ErrorCode::invalid_forecast,"paged state requires a scratch path");
        const auto lifecycle=paged?paged->lifecycle:Lifecycle::fixed_two_sweep;
        const auto directory_read_limit=paged_directory_read_limit(f,lifecycle);
        if (paged && paged->paged_directory &&
            (!paged->directory_page_limit || paged->directory_page_limit>directory_read_limit))
            fail(ErrorCode::invalid_forecast,"invalid paged row directory read bound");
        const auto footprint=storage_forecast(f,catalog,packed,paged?std::optional(paged->limits):std::nullopt,
                                              paged && paged->compact_rows,paged && paged->ordered_rows,
                                              paged && paged->row_coverage,paged && paged->shared_policy,
                                              paged && paged->paged_directory,lifecycle);
        if (footprint.entries>limits.entries || footprint.payload_bits>limits.integer_payload_bits)
            fail(ErrorCode::capacity,"persistent state/export footprint admission exceeded");
        return footprint;
    }
    static std::size_t paged_directory_read_limit(const Forecast& f,Lifecycle lifecycle) {
        if (lifecycle==Lifecycle::fixed_two_sweep) return times(10,f.rows);
        if (lifecycle==Lifecycle::bounded_v1) return times(plus(2,times(4,f.sweeps)),f.rows);
        fail(ErrorCode::invalid_forecast,"unknown state lifecycle");
    }
    [[nodiscard]] std::size_t packed_stride(std::size_t shift) const noexcept {
        return static_cast<std::size_t>(words(forecast_.value_bits-shift));
    }
    [[nodiscard]] std::size_t page_base(PackedField field) const noexcept {
        return field==PackedField::regret?packed_.limb_count:0;
    }
    [[nodiscard]] Integer load_compact(PackedField field,std::size_t offset,
                                       std::size_t shift,std::size_t action) const {
        const auto stride=packed_stride(shift);
        const auto index=offset+action*stride;
        std::array<std::uint64_t,page_codec_words> scratch;
        const std::uint64_t* first=scratch.data();
        if (paged_image_) {
            const auto bank=field==PackedField::regret && paged_->limits.cache_banks>1?1u:0u;
            paged_image_->read(page_base(field)+index,std::span(scratch).first(stride),bank);
        } else {
            const auto* image=field==PackedField::regret?packed_regrets_.get():packed_averages_.get();
            first=image+index;
        }
        // A native little-endian uint64_t pointer selects Boost's bounded copy
        // and normalize path. Packed mode admits this layout before allocation.
        Integer result;
        boost::multiprecision::import_bits(result,first,first+stride,64,false);
        return result;
    }
    [[nodiscard]] Integer load_average(const PackedRow& row,std::size_t action) const {
        Integer result=load_compact(PackedField::average,row.limb_offset,row.shift,action);
        result<<=row.shift;
        return result;
    }
    void stage_compact(const PackedRow& row,std::size_t action,const Integer& increment) {
        if (increment!=0 && boost::multiprecision::lsb(increment)<row.shift)
            fail(ErrorCode::arithmetic,"state average increment is outside certified packed scale");
        Integer value=load_compact(PackedField::average,row.limb_offset,row.shift,action);
        value+=increment>>row.shift;
        if (width(value)>forecast_.value_bits-row.shift)
            fail(ErrorCode::integer_width,"state retained average exceeds packed admission");
        store_compact(PackedField::average,row.limb_offset,row.shift,action,value,
                      "state packed average encoding width changed");
    }
    void stage_compact_scaled(const PackedRow& row,std::size_t action,const Integer& increment) {
        Integer value=load_compact(PackedField::average,row.limb_offset,row.shift,action);
        value+=increment;
        if (width(value)>forecast_.value_bits-row.shift)
            fail(ErrorCode::integer_width,"state retained average exceeds packed admission");
        store_compact(PackedField::average,row.limb_offset,row.shift,action,value,
                      "state packed average encoding width changed");
    }
    void stage_compact_image(PackedField field,std::size_t offset,
                             std::size_t shift,std::size_t action,const Integer& increment,const char* label) {
        std::optional<Integer> negative_magnitude;
        const Integer* magnitude=&increment;
        if (increment<0) { negative_magnitude.emplace(-increment);magnitude=&*negative_magnitude; }
        if (*magnitude!=0 && boost::multiprecision::lsb(*magnitude)<shift)
            fail(ErrorCode::arithmetic,"state packed delta is outside certified scale");
        Integer value=load_compact(field,offset,shift,action);
        const Integer quotient=*magnitude>>shift;
        if (increment<0) value-=quotient; else value+=quotient;
        if (value<0) value=0;
        if (width(value)>forecast_.value_bits-shift)
            fail(ErrorCode::integer_width,label);
        store_compact(field,offset,shift,action,value,label);
    }
    void store_compact(PackedField field,std::size_t offset,std::size_t shift,
                       std::size_t action,const Integer& value,const char* label) {
        const auto stride=packed_stride(shift);
        const auto index=offset+action*stride;
        std::array<std::uint64_t,page_codec_words> scratch;
        auto* first=scratch.data();
        if (!paged_image_) {
            auto* staged=field==PackedField::regret?staged_packed_regrets_.get():staged_packed_averages_.get();
            first=staged+index;
        }
        const auto& raw=value.backend();
        const auto used=raw.size()*sizeof(*raw.limbs());
        const auto bytes=stride*sizeof(*first);
        if (raw.sign() || used>bytes) fail(ErrorCode::arithmetic,label);
        std::memcpy(first,raw.limbs(),used);
        std::memset(reinterpret_cast<unsigned char*>(first)+used,0,bytes-used);
        if (paged_image_) {
            const auto extent=std::span(scratch).first(stride);
            if (paged_->row_coverage) paged_image_->stage_row_extent(page_base(field)+index,extent);
            else paged_image_->stage(page_base(field)+index,extent);
        }
    }
    void healthy() const {
        if (failed_ || (row_directory_ && row_directory_->failed()))
            fail(ErrorCode::failed_owner,"state owner already failed");
    }
    void charge(std::uint64_t work) {
        if (work>forecast_.own_work-receipt_.state_work) fail(ErrorCode::work_limit,"state cumulative work allowance exceeded");
        receipt_.state_work+=work;
    }
    void input_width(const Integer& value) {
        const auto bits=width(value);
        if (bits>forecast_.value_bits) fail(ErrorCode::integer_width,"state input exceeds fixed value width");
        receipt_.peak_input_bits=std::max(receipt_.peak_input_bits,bits);
    }
    void retained_width(const Integer& value) {
        const auto bits=width(value);
        if (bits>forecast_.value_bits) fail(ErrorCode::integer_width,"state retained value exceeds admission");
        receipt_.peak_arithmetic_bits=std::max(receipt_.peak_arithmetic_bits,bits);
    }
    Key key(History::Cursor cursor,std::size_t actor,std::size_t holding) {
        if (actor>1 || holding>=hand_counts_[actor]) fail(ErrorCode::invalid_row,"state actor or original holding index");
        // These validate the exact live history owner and its generation.
        const auto ordinal=history_->ordinal(cursor);
        if (history_->depth(cursor)>forecast_.max_history_depth) fail(ErrorCode::invalid_row,"state history depth exceeds forecast");
        return {ordinal,actor,holding};
    }
    void index_bound(std::size_t row) const {
        if (row>=receipt_.rows) fail(ErrorCode::invalid_row,"state row index");
    }
    [[nodiscard]] PackedRow average_record(std::size_t row) const {
        if (!compact()) return packed_rows_[row];
        const auto info=compact_record(row);
        return {info.average_offset,info.average_shift};
    }
    [[nodiscard]] PackedRegretRow regret_record(std::size_t row) const {
        if (!compact()) return packed_regret_rows_[row];
        const auto info=compact_record(row);
        return {info.regret_offset,info.regret_shift};
    }
    [[nodiscard]] std::size_t compact_slot(std::uint64_t history,std::size_t holding) const {
        // History authenticates the actor. Compare the complete key even when hashes collide.
        auto hash=(history<<1)|holding;
        hash=(hash^(hash>>30))*UINT64_C(0xbf58476d1ce4e5b9);
        hash=(hash^(hash>>27))*UINT64_C(0x94d049bb133111eb);
        const auto mask=compact_index_slots_-1;
        auto slot=static_cast<std::size_t>(hash^(hash>>31))&mask;
        for (std::size_t probe=0;probe<compact_probe_limit_;++probe,slot=(slot+1)&mask) {
            const auto reference=compact_index_[slot];
            if (!reference) return slot;
            const auto& row=compact_rows_[reference-1];
            if (row.history==history && row.holding==holding) return slot;
        }
        fail(ErrorCode::capacity,"compact row index probe limit exceeded");
    }
public:
    static constexpr std::size_t compact_record_bytes=sizeof(CompactRow);
    static constexpr std::size_t row_directory_resident_entries=row_directory_entries;
    [[nodiscard]] static std::size_t compact_index_slots(std::size_t rows) {
        if (!rows || rows>2'000'000) fail(ErrorCode::invalid_forecast,"invalid compact row count");
        return std::bit_ceil(4*rows);
    }
    [[nodiscard]] static std::size_t pager_resident_bytes(const virtual_dyadic_paged_image::Limits& limits,
                                                         bool row_coverage=false) {
        using Image = virtual_dyadic_paged_image::Image;
        return Image::resident_bytes(limits,row_coverage?Image::Coverage::state_rows:Image::Coverage::words);
    }
    static StorageForecast storage_forecast(const Forecast& f,ActionCatalogCapacity catalog={},
                                             PackedAverageCapacity packed={},
                                             std::optional<virtual_dyadic_paged_image::Limits> paged={},
                                             bool compact_rows=false,bool ordered_rows=false,bool row_coverage=false,
                                             bool shared_policy=false,bool paged_directory=false,
                                             Lifecycle lifecycle=Lifecycle::fixed_two_sweep) {
        (void)admit_catalog(f,catalog);
        if (ordered_rows && !compact_rows)
            fail(ErrorCode::invalid_forecast,"ordered registration requires compact rows");
        if (catalog.sealed && (!packed.limb_count || !packed.regret_limbs))
            fail(ErrorCode::invalid_forecast,"sealed action catalog requires packed strategy fields");
        const bool expanded=paged && paged->profile==virtual_dyadic_paged_image::Profile::proof10;
        if (expanded && (!compact_rows || f.rows!=119196 || f.slots!=281066 || f.sweeps!=2 ||
            f.max_history_depth!=15 || f.value_bits!=644 ||
            packed.limb_count!=1295812 || packed.regret_limbs!=1666910))
            fail(ErrorCode::invalid_forecast,"invalid ten-card strategy census");
        if (paged && (!catalog.sealed || (!expanded && f.value_bits>642) || paged->page_words<words(f.value_bits) ||
            paged->image_words!=plus(packed.limb_count,packed.regret_limbs)))
            fail(ErrorCode::invalid_forecast,"invalid paged state profile, width or image word census");
        if (compact_rows && (!paged || catalog.keys>std::size_t{UINT16_MAX}+1 || f.slots>UINT32_MAX ||
            packed.limb_count>UINT32_MAX || packed.regret_limbs>UINT32_MAX))
            fail(ErrorCode::invalid_forecast,"invalid compact row layout dimensions");
        if (row_coverage && (!ordered_rows || !packed.limb_count || !packed.regret_limbs ||
            paged->stage_split_words!=packed.limb_count))
            fail(ErrorCode::invalid_forecast,"row coverage requires ordered disjoint packed fields");
        if (shared_policy && (!row_coverage || f.slots<2*f.rows ||
            (lifecycle==Lifecycle::fixed_two_sweep && f.sweeps!=2) ||
            (lifecycle==Lifecycle::bounded_v1 && (f.sweeps<1 || f.sweeps>8))))
            fail(ErrorCode::invalid_forecast,"shared policy sweep geometry does not match lifecycle");
        if (paged_directory && !shared_policy)
            fail(ErrorCode::invalid_forecast,"paged directory requires shared ordered policy");
        if (lifecycle==Lifecycle::bounded_v1 &&
            (!paged || paged->profile!=virtual_dyadic_paged_image::Profile::legacy || !compact_rows ||
             !ordered_rows || !row_coverage || !shared_policy || !paged_directory ||
             f.sweeps<1 || f.sweeps>8))
            fail(ErrorCode::invalid_forecast,"bounded lifecycle requires legacy pager and all shared ordered row features");
        if (lifecycle!=Lifecycle::fixed_two_sweep && lifecycle!=Lifecycle::bounded_v1)
            fail(ErrorCode::invalid_forecast,"unknown state lifecycle");
        auto entries=plus(1024,plus(times(16,f.rows),times(10,f.slots)));
        const auto width_with_scratch=plus(f.value_bits,58);
        // Preserve the original integer/text reservation across all modes.
        auto payload=plus(times(plus(times(5,f.slots),256),width_with_scratch),
            plus(times(128,f.slots),plus(times(512,f.slots),times(16,f.rows))));
        if (lifecycle==Lifecycle::bounded_v1)
            payload=plus(payload,times(8,times(sizeof(PolicySpillSweep),f.sweeps)));
        if (catalog.sealed) {
            const auto menu_bits=plus(times(8*sizeof(std::string_view),catalog.token_slots),
                times(8*sizeof(Menu),catalog.keys));
            const auto reserved_menu_bits=times(640,f.slots);
            if (menu_bits>reserved_menu_bits) payload=plus(payload,menu_bits-reserved_menu_bits);
        }
        if (packed.limb_count) {
            if (std::endian::native!=std::endian::little || !f.slots || !f.rows || !f.value_bits || f.value_bits>65536 ||
                packed.limb_count<f.slots || packed.limb_count>times(f.slots,words(f.value_bits)))
                fail(ErrorCode::invalid_forecast,"invalid packed average dimensions or platform");
            // Replace the dense committed/staged/export average arrays and,
            // when used, the original per-row menu reservation. Keep metadata
            // and one decoder regardless of the backing used for packed words.
            entries-=times(3,f.slots);
            if (catalog.keys) {
                entries-=times(3,f.slots);
                entries=plus(entries,plus(times(3,catalog.token_slots),times(2,catalog.keys)));
            }
            entries=plus(entries,plus(times(2,f.rows),32));
            auto packed_bits=plus(times(8*sizeof(PackedRow),f.rows),
                times(std::min<std::size_t>(20,f.slots)+4,width_with_scratch));
            if (packed.regret_limbs) {
                if (packed.regret_limbs<f.slots || packed.regret_limbs>times(f.slots,words(f.value_bits)))
                    fail(ErrorCode::invalid_forecast,"invalid packed regret dimensions");
                entries-=times(2,f.slots);
                entries=plus(entries,times(2,f.rows));
                packed_bits=plus(packed_bits,times(8*sizeof(PackedRegretRow),f.rows));
            }
            const auto packed_credit=times(packed.regret_limbs?5:3,times(f.slots,width_with_scratch));
            if (paged) {
                const auto resident_bytes=plus(pager_resident_bytes(*paged,row_coverage),
                                               times(sizeof(std::uint64_t),page_codec_words));
                entries=plus(entries,plus(resident_bytes,7)/8);
                packed_bits=plus(packed_bits,times(8,resident_bytes));
                if (compact_rows) {
                    const auto order_entries=ordered_rows?(sizeof(last_registration_)+7)/8:0;
                    const auto records=paged_directory?row_directory_entries:4*f.rows;
                    const auto common=plus(1056+order_entries,plus(records,plus(3*catalog.token_slots,2*catalog.keys)));
                    const auto build=ordered_rows?common:plus(common,compact_index_slots(f.rows));
                    auto policies=shared_policy?plus(f.rows,policy_spill_entries):
                        times(ordered_rows?1:2,plus(f.rows,f.slots));
                    if (shared_policy && lifecycle==Lifecycle::bounded_v1)
                        policies=plus(policies,plus(times(sizeof(PolicySpillSweep),f.sweeps),7)/8);
                    const auto frozen=plus(common,plus(policies,plus(resident_bytes,7)/8));
                    entries=std::max(build,frozen);
                }
                if (packed_bits>packed_credit) payload=plus(payload,packed_bits-packed_credit);
            } else {
                const auto image_words=plus(packed.limb_count,packed.regret_limbs);
                entries=plus(entries,times(2,image_words));
                packed_bits=plus(packed_bits,times(128,image_words));
                if (packed_bits>packed_credit)
                    fail(ErrorCode::capacity,"packed average exceeds original integer payload reservation");
            }
        } else if (packed.regret_limbs) fail(ErrorCode::invalid_forecast,"packed regrets require packed averages");
        if (entries>std::numeric_limits<std::size_t>::max() || payload>std::numeric_limits<std::size_t>::max())
            fail(ErrorCode::capacity,"state storage forecast exceeds platform size");
        return {static_cast<std::size_t>(entries),static_cast<std::size_t>(payload)};
    }
    // History must remain alive for this owner's entire lifetime. Menus and
    // prior physical support are authenticated by the enclosing trainer.
    State(const History& history,std::array<std::size_t,2> hands,const Integer& denominator,
          Forecast forecast,Limits limits={})
        : State(history,hands,denominator,forecast,limits,{}) {}
    State(const History& history,std::array<std::size_t,2> hands,const Integer& denominator,
          Forecast forecast,Limits limits,ActionCatalogCapacity catalog)
        : State(history,hands,denominator,forecast,limits,catalog,{}) {}
    State(const History& history,std::array<std::size_t,2> hands,const Integer& denominator,
          Forecast forecast,Limits limits,ActionCatalogCapacity catalog,PackedAverageCapacity packed,
          std::optional<PagedStrategy> paged={})
        : history_(&history),hand_counts_(hands),forecast_(admit(forecast,limits,hands,paged)),
          limits_(limits),catalog_(catalog),packed_(packed),paged_(std::move(paged)),
          storage_(admit_storage(forecast_,limits_,catalog_,packed_,paged_)),
          quantizer_(policy_limits(forecast_,limits_,paged_)) {
        if (denominator<=0) fail(ErrorCode::invalid_scale,"state fixed game denominator must be positive");
        input_width(denominator);
        receipt_.reserved_entries=storage_.entries;
        receipt_.reserved_integer_and_text_payload_bits=storage_.payload_bits;
        charge(plus(1024,plus(times(8,forecast_.rows),plus(times(16,forecast_.slots),times(4,words(width(denominator)))))));
        if (catalog_.sealed) {
            const auto catalog_objects=plus(catalog_.keys,catalog_.token_slots);
            if (catalog_objects>forecast_.slots) charge(times(16,catalog_objects-forecast_.slots));
        }
        denominator_=denominator;
        if (paged_ && paged_->compact_rows) {
            if (hands[0]>2 || hands[1]>2)
                fail(ErrorCode::invalid_forecast,"compact rows support at most two holdings per seat");
            if (paged_->paged_directory)
                row_directory_=std::make_unique<RowDirectory>(paged_->scratch,forecast_.rows,
                    paged_->directory_page_limit,paged_directory_read_limit(forecast_,paged_->lifecycle));
            else compact_rows_=std::make_unique<CompactRow[]>(forecast_.rows);
            if (!paged_->ordered_rows) {
                compact_index_slots_=compact_index_slots(forecast_.rows);
                compact_probe_limit_=2*logceil(forecast_.rows+1);
                compact_index_=std::make_unique<std::uint32_t[]>(compact_index_slots_);
            }
        } else rows_=std::make_unique<Row[]>(forecast_.rows);
        if (!catalog_.sealed) action_text_=std::make_unique<ActionText[]>(token_capacity());
        action_views_=std::make_unique<std::string_view[]>(token_capacity());
        if (catalog_.keys) action_catalog_=std::make_unique<Menu[]>(catalog_.keys);
        if (!compact() && this->packed()) packed_rows_=std::make_unique<PackedRow[]>(forecast_.rows);
        if (!compact() && packed_regrets()) packed_regret_rows_=std::make_unique<PackedRegretRow[]>(forecast_.rows);
    }
    State(const State&)=delete;
    State& operator=(const State&)=delete;
    State(State&&)=delete;
    State& operator=(State&&)=delete;
    [[nodiscard]] bool failed() const noexcept { return failed_ || (row_directory_ && row_directory_->failed()); }
    [[nodiscard]] const Integer& denominator() const noexcept { return denominator_; }
    [[nodiscard]] Receipt receipt() const noexcept {
        auto answer=receipt_;
        answer.quantizer_work=quantizer_.receipt().work;
        answer.work=answer.state_work+answer.quantizer_work;
        return answer;
    }
    [[nodiscard]] std::optional<virtual_dyadic_paged_image::Receipt> paged_receipt() const {
        if (!paged_image_) return std::nullopt;
        return paged_image_->receipt();
    }
    [[nodiscard]] std::optional<PolicySpillReceipt> policy_spill_receipt() const {
        if (!policy_spill_) return std::nullopt;
        if (paged_ && paged_->lifecycle==Lifecycle::bounded_v1)
            fail(ErrorCode::phase,"bounded lifecycle uses policy_sweep_receipts");
        return policy_spill_->receipt();
    }
    [[nodiscard]] std::span<const PolicySpillSweep> policy_sweep_receipts() const noexcept {
        if (!policy_spill_) return {};
        return policy_spill_->receipts();
    }
    // Metadata only; this does not claim immutability or persist an external checkpoint.
    [[nodiscard]] CheckpointEpoch checkpoint_epoch() const {
        healthy();
        if (!paged_ || paged_->lifecycle!=Lifecycle::bounded_v1 || !paged_image_ ||
            phase_!=Phase::closed || !receipt_.completed_sweeps)
            fail(ErrorCode::phase,"checkpoint epoch requires a committed bounded lifecycle");
        const auto sweep=receipt_.completed_sweeps;
        const auto slot=sweep%2;
        return {sweep,slot,sweep-1,slot^1,paged_->limits.image_words,
            sweep==1 && paged_->limits.virtual_initial_zero};
    }
    [[nodiscard]] std::optional<RowDirectoryReceipt> row_directory_receipt() const {
        if (!row_directory_) return std::nullopt;
        return row_directory_->receipt();
    }
    [[nodiscard]] std::span<const Row> rows() const {
        if (compact()) fail(ErrorCode::phase,"compact row directory has no contiguous Row view");
        return {rows_.get(),receipt_.rows};
    }
    [[nodiscard]] std::size_t row_count() const noexcept { return receipt_.rows; }
    [[nodiscard]] Row row_at(std::size_t row) const {
        return describe_row(row).row;
    }
    [[nodiscard]] ActionStorage action_storage() const noexcept {
        return {token_capacity(),catalog_.keys,catalog_.keys?stored_tokens_:receipt_.slots,
            catalog_.keys?stored_menus_:receipt_.rows,
            catalog_.sealed?sizeof(std::string_view):sizeof(ActionText)+sizeof(std::string_view),sizeof(Menu)};
    }
    [[nodiscard]] std::span<const Integer> regrets() const noexcept {
        return phase_==Phase::building || packed_regrets() ? std::span<const Integer>() : std::span<const Integer>(regrets_.get(),forecast_.slots);
    }
    [[nodiscard]] std::span<const Integer> averages() const noexcept {
        return phase_==Phase::building || packed()?std::span<const Integer>():
            std::span<const Integer>(averages_.get(),forecast_.slots);
    }
    [[nodiscard]] std::size_t average_row_shift(std::size_t row) const {
        index_bound(row);
        if (!packed()) fail(ErrorCode::invalid_row,"state has no packed average row shift");
        return average_record(row).shift;
    }
    [[nodiscard]] std::size_t regret_row_shift(std::size_t row) const {
        index_bound(row);
        if (!packed_regrets()) fail(ErrorCode::invalid_row,"state has no packed regret row shift");
        return regret_record(row).shift;
    }
    [[nodiscard]] Integer regret_numerator(std::size_t row,std::size_t action) const {
        if (phase_==Phase::building) fail(ErrorCode::phase,"state regret read before freeze");
        index_bound(row);
        const auto info=row_at(row);
        if (action>=info.actions.size()) fail(ErrorCode::invalid_row,"state regret action index");
        if (!packed_regrets()) return regrets_[info.offset+action];
        const auto record=regret_record(row);
        Integer result=load_compact(PackedField::regret,record.limb_offset,record.shift,action);
        result<<=record.shift;
        return result;
    }
    // This reads the committed image, including after a failed staging call.
    // A packed caller admits the copy/shift codec work for each requested value.
    [[nodiscard]] Integer average_numerator(std::size_t row,std::size_t action) const {
        if (phase_==Phase::building) fail(ErrorCode::phase,"state average read before freeze");
        index_bound(row);
        const auto info=row_at(row);
        if (action>=info.actions.size()) fail(ErrorCode::invalid_row,"state average action index");
        return packed()?load_average(average_record(row),action):averages_[info.offset+action];
    }
    [[nodiscard]] std::size_t register_row(History::Cursor cursor,std::size_t actor,std::size_t holding,
                                          std::span<const std::string_view> actions) {
        return register_owned_row(cursor,actor,holding,0,false,actions,std::nullopt,std::nullopt);
    }
    [[nodiscard]] std::size_t register_row(History::Cursor cursor,std::size_t actor,std::size_t holding,
                                          std::span<const std::string_view> actions,std::size_t average_shift) {
        return register_owned_row(cursor,actor,holding,0,false,actions,average_shift,std::nullopt);
    }
    [[nodiscard]] std::size_t register_row(History::Cursor cursor,std::size_t actor,std::size_t holding,
                                          std::span<const std::string_view> actions,std::size_t average_shift,
                                          std::size_t regret_shift) {
        return register_owned_row(cursor,actor,holding,0,false,actions,average_shift,regret_shift);
    }
    // The trainer supplies an already verified source node ID. Menus are
    // always copied into this owner's arrays, and an occupied ID must match
    // every ordered token. No source view survives registration.
    [[nodiscard]] std::size_t register_catalog_row(History::Cursor cursor,std::size_t actor,std::size_t holding,
                                                  std::size_t menu_key,std::span<const std::string_view> actions) {
        return register_owned_row(cursor,actor,holding,menu_key,true,actions,std::nullopt,std::nullopt);
    }
    [[nodiscard]] std::size_t register_catalog_row(History::Cursor cursor,std::size_t actor,std::size_t holding,
                                                  std::size_t menu_key,std::span<const std::string_view> actions,
                                                  std::size_t average_shift) {
        return register_owned_row(cursor,actor,holding,menu_key,true,actions,average_shift,std::nullopt);
    }
    [[nodiscard]] std::size_t register_catalog_row(History::Cursor cursor,std::size_t actor,std::size_t holding,
                                                  std::size_t menu_key,std::span<const std::string_view> actions,
                                                  std::size_t average_shift,std::size_t regret_shift) {
        return register_owned_row(cursor,actor,holding,menu_key,true,actions,average_shift,regret_shift);
    }
    // Sealed registration obtains every public row key and the legal menu from
    // the live History owner. Source IDs are the only menu-sharing identity.
    [[nodiscard]] std::size_t register_sealed_row(History::Cursor cursor,std::size_t holding,
                                                   std::size_t average_shift,std::size_t regret_shift) {
        healthy();
        try {
            if (!catalog_.sealed) fail(ErrorCode::invalid_row,"sealed registration requires sealed catalog mode");
            if (phase_!=Phase::building) fail(ErrorCode::phase,"state row registration is closed");
            const bool ordered=paged_ && paged_->ordered_rows;
            History::DecisionPath path{};
            const auto info=history_->decision_key(cursor,ordered?&path:nullptr);
            if (info.actor>1 || holding>=hand_counts_[info.actor] || info.actions==0 || info.actions>20 ||
                info.source>=catalog_.keys || info.depth>forecast_.max_history_depth)
                fail(ErrorCode::invalid_row,"sealed history decision key outside admitted range");
            if (paged_ && paged_->shared_policy && info.actions<2)
                fail(ErrorCode::invalid_row,"shared policy requires at least two actions");
            if (average_shift>=forecast_.value_bits || regret_shift>=forecast_.value_bits ||
                !packed() || !packed_regrets())
                fail(ErrorCode::invalid_row,"sealed packed row shifts or mode");
            charge(plus(128,disk_rows()?32:times(16,logceil(forecast_.rows+1))));
            const Key identity{info.ordinal,info.actor,holding};
            std::size_t slot=0,existing=receipt_.rows;
            if (ordered) {
                if (last_registration_ && RegistrationOrder{path,holding}<=*last_registration_)
                    fail(ErrorCode::invalid_row,"sealed row is not in strict traversal order");
            } else if (compact_rows_) {
                slot=compact_slot(info.ordinal,holding);
                if (compact_index_[slot]) existing=compact_index_[slot]-1;
            } else {
                const auto found=index_.find(identity);
                if (found!=index_.end()) existing=found->second;
            }
            if (existing!=receipt_.rows) {
                const auto old=row_at(existing);
                if (old.actions.size()!=info.actions || old.actions.data()!=action_catalog_[info.source].data())
                    fail(ErrorCode::changed_menu,"sealed repeated row menu changed");
                if (average_record(existing).shift!=average_shift ||
                    regret_record(existing).shift!=regret_shift)
                    fail(ErrorCode::invalid_row,"sealed repeated row packed shift changed");
                return existing;
            }
            if (receipt_.rows>=forecast_.rows || info.actions>forecast_.slots-receipt_.slots)
                fail(ErrorCode::capacity,"state row or slot forecast exceeded");
            const auto pw=info.actions*packed_stride(average_shift);
            const auto rw=info.actions*packed_stride(regret_shift);
            if (pw>packed_.limb_count-packed_words_registered_ || rw>packed_.regret_limbs-packed_regret_words_registered_)
                fail(ErrorCode::capacity,"state packed limb census exceeded");
            auto owned=action_catalog_[info.source];
            if (owned.empty()) {
                if (info.actions>catalog_.token_slots-stored_tokens_)
                    fail(ErrorCode::capacity,"state action catalog token capacity exceeded");
                charge(64+16*info.actions);
                auto destination=std::span<std::string_view>(action_views_.get()+stored_tokens_,info.actions);
                history_->decision_actions(cursor,destination);
                for (const auto token:destination)
                    if (token.empty() || token.size()>64) fail(ErrorCode::invalid_row,"sealed action token length");
                owned=destination;
                action_catalog_[info.source]=owned;stored_tokens_+=info.actions;++stored_menus_;
            } else if (owned.size()!=info.actions) fail(ErrorCode::changed_menu,"sealed source menu changed");
            const auto number=receipt_.rows,offset=receipt_.slots;
            if (compact()) {
                const CompactRow record{info.ordinal,static_cast<std::uint32_t>(offset),
                    static_cast<std::uint32_t>(packed_words_registered_),static_cast<std::uint32_t>(packed_regret_words_registered_),
                    static_cast<std::uint16_t>(info.source),static_cast<std::uint16_t>(average_shift),
                    static_cast<std::uint16_t>(regret_shift),static_cast<std::uint8_t>(info.actor),
                    static_cast<std::uint8_t>(holding)};
                if (row_directory_) row_directory_->append(record);
                else compact_rows_[number]=record;
                if (ordered) last_registration_.emplace(path,holding);
                else compact_index_[slot]=static_cast<std::uint32_t>(number+1);
            } else {
                rows_[number]={info.ordinal,info.actor,holding,offset,owned};
                packed_rows_[number]={packed_words_registered_,average_shift};
                packed_regret_rows_[number]={packed_regret_words_registered_,regret_shift};
                index_.emplace(identity,number);
            }
            packed_words_registered_+=pw;packed_regret_words_registered_+=rw;
            ++receipt_.rows;receipt_.slots+=info.actions;
            return number;
        } catch (...) { failed_=true;throw; }
    }
private:
    static bool same_menu(Menu left,Menu right) {
        return left.size()==right.size() && std::equal(left.begin(),left.end(),right.begin());
    }
    [[nodiscard]] std::size_t register_owned_row(History::Cursor cursor,std::size_t actor,std::size_t holding,
                                                std::size_t menu_key,bool catalogued,Menu actions,
                                                std::optional<std::size_t> average_shift,
                                                std::optional<std::size_t> regret_shift) {
        healthy();
        try {
            if (phase_!=Phase::building) fail(ErrorCode::phase,"state row registration is closed");
            if (catalog_.sealed) fail(ErrorCode::invalid_row,"generic registration disabled in sealed catalog mode");
            if (actions.empty() || actions.size()>20) fail(ErrorCode::invalid_row,"state legal menu width");
            if (catalogued?menu_key>=catalog_.keys:catalog_.keys!=0)
                fail(ErrorCode::invalid_row,"state action catalog key or mode");
            if (average_shift.has_value()!=packed() || (average_shift && *average_shift>=forecast_.value_bits))
                fail(ErrorCode::invalid_row,"state packed average shift or mode");
            if (regret_shift.has_value()!=packed_regrets() || (regret_shift && *regret_shift>=forecast_.value_bits))
                fail(ErrorCode::invalid_row,"state packed regret shift or mode");
            charge(plus(128,plus(times(16,logceil(forecast_.rows+1)),times(256,actions.size()))));
            for (const auto action:actions) {
                if (action.empty() || action.size()>64) fail(ErrorCode::invalid_row,"state action token length");
                for (const unsigned char c:action) if (c<0x20 || c>0x7e) fail(ErrorCode::invalid_row,"state action token encoding");
            }
            const auto identity=key(cursor,actor,holding);
            Menu owned=catalogued?action_catalog_[menu_key]:Menu{};
            if (!owned.empty() && !same_menu(owned,actions))
                fail(ErrorCode::changed_menu,"state action catalog menu changed");
            const auto found=index_.find(identity);
            if (found!=index_.end()) {
                if (!same_menu(rows_[found->second].actions,actions))
                    fail(ErrorCode::changed_menu,"state repeated row legal menu changed");
                if (average_shift && packed_rows_[found->second].shift!=*average_shift)
                    fail(ErrorCode::invalid_row,"state repeated row packed average shift changed");
                if (regret_shift && packed_regret_rows_[found->second].shift!=*regret_shift)
                    fail(ErrorCode::invalid_row,"state repeated row packed regret shift changed");
                return found->second;
            }
            if (receipt_.rows>=forecast_.rows || actions.size()>forecast_.slots-receipt_.slots)
                fail(ErrorCode::capacity,"state row or slot forecast exceeded");
            const auto packed_words=average_shift?actions.size()*packed_stride(*average_shift):0;
            if (packed_words>packed_.limb_count-packed_words_registered_)
                fail(ErrorCode::capacity,"state packed average limb census exceeded");
            const auto packed_regret_words=regret_shift?actions.size()*packed_stride(*regret_shift):0;
            if (packed_regret_words>packed_.regret_limbs-packed_regret_words_registered_)
                fail(ErrorCode::capacity,"state packed regret limb census exceeded");
            const auto number=receipt_.rows, offset=receipt_.slots;
            if (owned.empty()) {
                const auto token_offset=catalogued?stored_tokens_:offset;
                if (catalogued && actions.size()>token_capacity()-token_offset)
                    fail(ErrorCode::capacity,"state action catalog token capacity exceeded");
                for (std::size_t a=0;a<actions.size();++a) {
                    auto& token=action_text_[token_offset+a];
                    std::copy(actions[a].begin(),actions[a].end(),token.begin());
                    action_views_[token_offset+a]={token.data(),actions[a].size()};
                }
                owned={action_views_.get()+token_offset,actions.size()};
                if (catalogued) {
                    action_catalog_[menu_key]=owned;
                    stored_tokens_+=actions.size();
                    ++stored_menus_;
                }
            }
            rows_[number]={std::get<0>(identity),actor,holding,offset,owned};
            index_.emplace(identity,number);
            if (average_shift) {
                packed_rows_[number]={packed_words_registered_,*average_shift};
            }
            if (regret_shift) {
                packed_regret_rows_[number]={packed_regret_words_registered_,*regret_shift};
            }
            packed_words_registered_+=packed_words;
            packed_regret_words_registered_+=packed_regret_words;
            ++receipt_.rows;
            receipt_.slots+=actions.size();
            return number;
        } catch (...) { failed_=true;throw; }
    }
public:
    [[nodiscard]] std::size_t find_row(History::Cursor cursor,std::size_t actor,std::size_t holding) {
        healthy();
        try {
            if (catalog_.sealed && phase_!=Phase::building) fail(ErrorCode::phase,"state row index lookup is closed after freeze");
            if (catalog_.sealed) fail(ErrorCode::invalid_row,"sealed lookup requires history-authenticated overload");
            charge(64+16*logceil(forecast_.rows+1));
            const auto found=index_.find(key(cursor,actor,holding));
            if (found==index_.end()) fail(ErrorCode::invalid_row,"state full-history row is absent");
            return found->second;
        } catch (...) { failed_=true;throw; }
    }
    [[nodiscard]] std::size_t find_row(History::Cursor cursor,std::size_t holding) {
        healthy();
        try {
            if (phase_!=Phase::building) fail(ErrorCode::phase,"state row index lookup is closed after freeze");
            if (!catalog_.sealed) fail(ErrorCode::invalid_row,"history-authenticated lookup requires sealed mode");
            if (paged_ && paged_->ordered_rows) fail(ErrorCode::phase,"ordered registration has no row index");
            const auto info=history_->decision_key(cursor);
            if (info.actor>1 || holding>=hand_counts_[info.actor]) fail(ErrorCode::invalid_row,"sealed lookup holding");
            charge(64+16*logceil(forecast_.rows+1));
            if (compact_rows_) {
                const auto reference=compact_index_[compact_slot(info.ordinal,holding)];
                if (!reference) fail(ErrorCode::invalid_row,"sealed full-history row is absent");
                return reference-1;
            }
            const auto found=index_.find(Key{info.ordinal,info.actor,holding});
            if (found==index_.end()) fail(ErrorCode::invalid_row,"state full-history row is absent");
            return found->second;
        } catch (...) {failed_=true;throw;}
    }
    void freeze() {
        healthy();
        try {
            if (phase_!=Phase::building || receipt_.rows!=forecast_.rows || receipt_.slots!=forecast_.slots)
                fail(ErrorCode::phase,"state complete row/slot census required before freeze");
            if (packed_words_registered_!=packed_.limb_count || packed_regret_words_registered_!=packed_.regret_limbs)
                fail(ErrorCode::capacity,"state complete packed average limb census required before freeze");
            charge(plus(times(8,forecast_.slots),times(2,forecast_.rows)));
            if (catalog_.sealed) {
                charge(times(16,forecast_.rows));
                if (compact()) compact_index_.reset();
                else index_.clear();
            }
            if (!packed_regrets()) {
                regrets_=std::make_unique<Integer[]>(forecast_.slots);
                staged_regrets_=std::make_unique<Integer[]>(forecast_.slots);
            }
            if (packed() && !paged_) {
                packed_averages_=std::make_unique<std::uint64_t[]>(packed_.limb_count);
                staged_packed_averages_=std::make_unique<std::uint64_t[]>(packed_.limb_count);
                if (packed_regrets()) {
                    packed_regrets_=std::make_unique<std::uint64_t[]>(packed_.regret_limbs);
                    staged_packed_regrets_=std::make_unique<std::uint64_t[]>(packed_.regret_limbs);
                }
            } else if (!packed()) {
                averages_=std::make_unique<Integer[]>(forecast_.slots);
                staged_averages_=std::make_unique<Integer[]>(forecast_.slots);
            }
            if (paged_ && paged_->shared_policy)
                policy_spill_=std::make_unique<PolicySpill>(forecast_.rows,forecast_.slots-forecast_.rows,
                    paged_->lifecycle==Lifecycle::bounded_v1?forecast_.sweeps:2,
                    paged_->lifecycle==Lifecycle::bounded_v1);
            else units_=std::make_unique<std::uint64_t[]>(forecast_.slots);
            seen_=std::make_unique<unsigned char[]>(forecast_.rows);
            if (row_directory_) row_directory_->freeze();
            if (paged_) {
                using Image = virtual_dyadic_paged_image::Image;
                if (paged_->row_coverage)
                    paged_image_.reset(new Image(paged_->scratch,paged_->limits,Image::Coverage::state_rows));
                else paged_image_=std::make_unique<Image>(paged_->scratch,paged_->limits);
            }
            phase_=Phase::closed;
        } catch (...) { failed_=true;throw; }
    }
    void begin_sweep() {
        healthy();
        try {
            if (phase_!=Phase::closed || receipt_.completed_sweeps>=forecast_.sweeps || exported_)
                fail(ErrorCode::phase,"state sweep phase or requested iteration limit");
            charge(times(4,forecast_.rows));
            std::fill_n(seen_.get(),forecast_.rows,static_cast<unsigned char>(0));
            receipt_.staged_rows=0;
            if (policy_spill_) policy_spill_->begin(paged_->scratch/"policy.bin");
            if (paged_image_) paged_image_->begin_sweep();
            std::optional<std::array<Integer,20>> decoded;
            if (packed_regrets()) decoded.emplace();
            for (std::size_t row_index=0;row_index<row_count();++row_index) {
                const auto descriptor=describe_row(row_index);
                const auto row=descriptor.row;
                charge(16+4*row.actions.size());
                std::span<const Integer> values;
                if (packed_regrets()) {
                    const PackedRegretRow packed_row{descriptor.regret_offset,descriptor.regret_shift};
                    for (std::size_t a=0;a<row.actions.size();++a)
                        (*decoded)[a]=load_compact(PackedField::regret,packed_row.limb_offset,packed_row.shift,a);
                    values={decoded->data(),row.actions.size()};
                } else values={regrets_.get()+row.offset,row.actions.size()};
                const auto policy=quantizer_.regret_policy(values);
                if (policy_spill_) {
                    const auto tag=policy_spill_->append(row.offset-row_index,policy.units());
                    if (row_directory_) seen_[row_index]=tag;
                    else compact_rows_[row_index].policy_tag=tag;
                }
                else std::copy(policy.units().begin(),policy.units().end(),units_.get()+row.offset);
            }
            if (policy_spill_) policy_spill_->finish();
            phase_=Phase::sweeping;
        } catch (...) { failed_=true;throw; }
    }
    // Borrowed view for this sweep. A later begin_sweep replaces these units.
    [[nodiscard]] std::span<const std::uint64_t> policy_units(std::size_t row) const {
        healthy();index_bound(row);
        if (phase_!=Phase::sweeping) fail(ErrorCode::phase,"state policy requires an active frozen sweep");
        if (policy_spill_) fail(ErrorCode::phase,"shared policy requires caller-owned row storage");
        const auto r=row_at(row);return {units_.get()+r.offset,r.actions.size()};
    }
    void copy_policy_units(std::size_t row,std::span<std::uint64_t> output) {
        healthy();
        try {
            if (phase_!=Phase::sweeping || !policy_spill_)
                fail(ErrorCode::phase,"policy copy requires an active shared sweep");
            const auto record=row_at(row);
            if (output.size()!=record.actions.size()) fail(ErrorCode::invalid_row,"policy copy extent differs");
            policy_spill_->load(policy_tag(row),record.offset-row,output);
        } catch (...) {failed_=true;throw;}
    }
    [[nodiscard]] PolicySnapshot copy_policy_snapshot(std::size_t row,std::span<std::uint64_t> storage) {
        healthy();
        try {
            if (phase_!=Phase::sweeping || !row_directory_ || !policy_spill_)
                fail(ErrorCode::phase,"policy snapshot requires frozen paged rows");
            const auto descriptor=describe_row(row);
            const auto count=descriptor.row.actions.size();
            if (count>storage.size()) fail(ErrorCode::invalid_row,"policy snapshot storage is too short");
            const auto units=storage.first(count);
            policy_spill_->load(policy_tag(row),descriptor.row.offset-row,units);
            return {descriptor,units};
        } catch (...) {failed_=true;throw;}
    }
private:
    // The returned exact mixed numerator belongs to the enclosing traversal.
    Integer stage_row_impl(std::size_t row,std::span<const Integer> action_values,
                           std::span<const Integer> average_action_increments,
                           std::optional<std::size_t> scaled_shift) {
        healthy();
        try {
            if (phase_!=Phase::sweeping) fail(ErrorCode::phase,"state staging requires active sweep");
            const auto descriptor=describe_row(row);
            const auto r=descriptor.row;const auto count=r.actions.size();
            if (row_seen(row) || action_values.size()!=count || average_action_increments.size()!=count)
                fail(ErrorCode::invalid_row,"state duplicate or incomplete staged row");
            const PackedRow average_row{descriptor.average_offset,descriptor.average_shift};
            const PackedRegretRow regret_row{descriptor.regret_offset,descriptor.regret_shift};
            if (scaled_shift && (!packed() || *scaled_shift!=average_row.shift))
                fail(ErrorCode::invalid_row,"state scaled average requires matching packed row shift");
            // Constant bounded backend width inspection/sign checks precede
            // arithmetic. Inputs are caller-owned and never mutated.
            charge(64+128*count);
            for (std::size_t a=0;a<count;++a) {
                input_width(action_values[a]);
                if (scaled_shift) {
                    const auto bits=width(average_action_increments[a]);
                    receipt_.peak_input_bits=std::max(receipt_.peak_input_bits,bits);
                    if (bits>forecast_.value_bits-*scaled_shift)
                        fail(ErrorCode::integer_width,"state scaled average increment exceeds packed admission");
                } else input_width(average_action_increments[a]);
                if (average_action_increments[a]<0) fail(ErrorCode::invalid_row,"state average increment must be nonnegative");
            }
            const auto temp_bits=forecast_.value_bits+58;
            charge(times(16*count+8,words(temp_bits)));
            receipt_.peak_arithmetic_bits=std::max(receipt_.peak_arithmetic_bits,temp_bits);
            Integer mixed=0;
            std::array<std::uint64_t,20> copied{};
            if (policy_spill_) policy_spill_->load(policy_tag(row),r.offset-row,
                std::span(copied).first(count));
            const auto* policy=policy_spill_?copied.data():units_.get()+r.offset;
            for (std::size_t a=0;a<count;++a) mixed+=action_values[a]*policy[a];
            if (mixed%dyadic_policy::grid_units!=0)
                fail(ErrorCode::arithmetic,"state mixed value is outside fixed denominator grid");
            mixed>>=dyadic_policy::grid_bits;
            for (std::size_t a=0;a<count;++a) {
                const auto at=r.offset+a;
                const Integer delta=action_values[a]-mixed;
                if (packed_regrets()) {
                    stage_compact_image(PackedField::regret,
                        regret_row.limb_offset,regret_row.shift,a,delta,
                        "state retained regret exceeds packed admission");
                } else {
                    Integer regret=regrets_[at]+delta;
                    if (regret<0) regret=0;
                    retained_width(regret);
                    staged_regrets_[at]=std::move(regret);
                }
                if (scaled_shift) stage_compact_scaled(average_row,a,average_action_increments[a]);
                else if (packed()) stage_compact(average_row,a,average_action_increments[a]);
                else {
                    Integer average=averages_[at]+average_action_increments[a];
                    retained_width(average);
                    staged_averages_[at]=std::move(average);
                }
            }
            if (row_directory_) seen_[row]|=128;
            else seen_[row]=1;
            ++receipt_.staged_rows;
            return mixed;
        } catch (...) { failed_=true;throw; }
    }
public:
    Integer stage_row(std::size_t row,std::span<const Integer> action_values,
                      std::span<const Integer> average_action_increments) {
        return stage_row_impl(row,action_values,average_action_increments,std::nullopt);
    }
    Integer stage_scaled_row(std::size_t row,std::span<const Integer> action_values,
                             ScaledAverageIncrements average_increments) {
        return stage_row_impl(row,action_values,average_increments.values,average_increments.shift);
    }
    void commit_sweep() {
        healthy();
        try {
            if (phase_!=Phase::sweeping || receipt_.staged_rows!=receipt_.rows)
                fail(ErrorCode::phase,"state cannot commit incomplete sweep");
            charge(times(4,receipt_.rows));
            for (std::size_t row=0;row<receipt_.rows;++row)
                if (!row_seen(row)) fail(ErrorCode::phase,"state missing staged row");
            if (paged_image_) {
                // Successful State rows cover the two disjoint, fully
                // registered fields exactly once. The pager checks word count.
                if (paged_->row_coverage) paged_image_->commit_covered_rows();
                else paged_image_->commit_sweep();
            } else {
                if (packed_regrets()) packed_regrets_.swap(staged_packed_regrets_);
                else regrets_.swap(staged_regrets_);
                if (packed()) packed_averages_.swap(staged_packed_averages_);
                else averages_.swap(staged_averages_);
            }
            ++receipt_.completed_sweeps;phase_=Phase::closed;
        } catch (...) { failed_=true;throw; }
    }
private:
    void admit_export() {
        if (phase_!=Phase::closed || receipt_.completed_sweeps!=forecast_.sweeps || exported_)
            fail(ErrorCode::phase,"state average export requires all requested sweeps once");
        charge(plus(times(4*words(forecast_.value_bits)+4,forecast_.slots),times(4,forecast_.rows)));
        exported_=true;
    }
    template<class Emit>
    void average_rows(Emit&& emit) {
        std::optional<std::array<Integer,20>> decoded;
        if (packed()) decoded.emplace();
        for (std::size_t i=0;i<forecast_.rows;++i) {
            const auto descriptor=describe_row(i);
            const auto row=descriptor.row;charge(16+4*row.actions.size());
            const Integer* masses;
            if (decoded) {
                const PackedRow average_row{descriptor.average_offset,descriptor.average_shift};
                for (std::size_t a=0;a<row.actions.size();++a)
                    (*decoded)[a]=packed_regrets()
                        ?load_compact(PackedField::average,average_row.limb_offset,average_row.shift,a)
                        :load_average(average_row,a);
                masses=decoded->data();
            } else masses=averages_.get()+row.offset;
            const auto policy=quantizer_.average_export({masses,row.actions.size()});
            emit(i,row.offset,policy.units(),static_cast<unsigned char>(policy.uniform_fallback()));
            healthy();
        }
    }
public:
    template<class Emit>
    [[nodiscard]] std::span<const unsigned char> stream_average(Emit&& emit) {
        healthy();
        try {
            if (!policy_spill_) fail(ErrorCode::phase,"streamed average requires shared policy mode");
            admit_export();
            average_rows([&](std::size_t row,std::size_t,std::span<const std::uint64_t> units,unsigned char fallback) {
                emit(units);
                seen_[row]=fallback;
            });
            return {seen_.get(),forecast_.rows};
        } catch (...) {failed_=true;throw;}
    }
    [[nodiscard]] AverageExport export_average(bool include_raw=true) {
        healthy();
        try {
            if (policy_spill_) fail(ErrorCode::phase,"shared policy requires streamed average export");
            if (packed() && include_raw) fail(ErrorCode::phase,"state packed export requires policy-only mode");
            admit_export();
            AverageExport image;
            image.rows=forecast_.rows;
            image.slots=forecast_.slots;
            if (paged_ && paged_->ordered_rows) {
                // The final commit ended all policy borrows and staging marks.
                image.units=std::move(units_);
                image.uniform_fallback=std::move(seen_);
            } else {
                image.units=std::make_unique<std::uint64_t[]>(image.slots);
                image.uniform_fallback=std::make_unique<unsigned char[]>(image.rows);
            }
            if (include_raw) {
                image.raw_masses=std::make_unique<Integer[]>(image.slots);
                std::copy_n(averages_.get(),image.slots,image.raw_masses.get());
            }
            average_rows([&](std::size_t row,std::size_t offset,std::span<const std::uint64_t> units,unsigned char fallback) {
                image.uniform_fallback[row]=fallback;
                std::copy(units.begin(),units.end(),image.units.get()+offset);
            });
            return image;
        } catch (...) { failed_=true;throw; }
    }
};
} // namespace openpoker::virtual_dyadic_state
