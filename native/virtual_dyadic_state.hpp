#pragma once
// Persistent simultaneous CFR+ state. The enclosing trainer authenticates menus,
// physical support and the common fixed game denominator before calling this owner.
#include "dyadic_policy.hpp"
#include "virtual_dyadic_history.hpp"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <map>
#include <memory>
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
struct Forecast {
    std::size_t rows = 0, slots = 0, sweeps = 0, max_history_depth = 0;
    std::size_t value_bits = 0;
    // Two disjoint cumulative allowances. A whole-game preflight must justify
    // these for the requested workload; constructor admission alone cannot.
    std::uint64_t own_work = 0, quantizer_work = 0;
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
struct AverageExport {
    dyadic_policy::ImageKind kind = dyadic_policy::ImageKind::exported_average;
    std::size_t rows = 0, slots = 0;
    std::unique_ptr<std::uint64_t[]> units;
    std::unique_ptr<unsigned char[]> uniform_fallback;
    std::unique_ptr<Integer[]> raw_masses;
};

class State final {
    using Key = std::tuple<std::size_t,std::size_t,std::size_t>;
    enum class Phase { building, closed, sweeping };
    const History* history_;
    std::array<std::size_t,2> hand_counts_;
    Forecast forecast_;
    Limits limits_;
    dyadic_policy::Quantizer quantizer_;
    Receipt receipt_{};
    Integer denominator_;
    std::unique_ptr<Row[]> rows_;
    std::unique_ptr<std::array<char,64>[]> action_text_;
    std::unique_ptr<std::string_view[]> action_views_;
    std::map<Key,std::size_t> index_;
    std::unique_ptr<Integer[]> regrets_, averages_, staged_regrets_, staged_averages_;
    std::unique_ptr<std::uint64_t[]> units_;
    std::unique_ptr<unsigned char[]> seen_;
    Phase phase_ = Phase::building;
    bool failed_ = false, exported_ = false;

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
    static Forecast admit(Forecast f, Limits limits, std::array<std::size_t,2> hands) {
        if (!limits.work || limits.work>500000000 || !limits.integer_bits || limits.integer_bits>65536 ||
            !limits.entries || limits.entries>2000000 || !limits.integer_payload_bits ||
            limits.integer_payload_bits>(std::size_t{1}<<30))
            fail(ErrorCode::invalid_limits,"invalid reduce-only state limits");
        if (!hands[0] || !hands[1] || hands[0]>1326 || hands[1]>1326 || !f.rows || !f.slots ||
            f.slots<f.rows || f.slots>times(20,f.rows) || !f.sweeps || !f.max_history_depth ||
            f.max_history_depth>64 || !f.value_bits || f.value_bits>limits.integer_bits ||
            plus(f.value_bits,58)>limits.integer_bits || !f.own_work || !f.quantizer_work ||
            plus(f.own_work,f.quantizer_work)>limits.work)
            fail(ErrorCode::invalid_forecast,"invalid state dimensions or work partition");
        // Four retained integer arrays, frozen policy units, ordered token
        // metadata and map/row headers; additionally reserve one returned export
        // (raw masses, units and fallback flags) and quantizer/mix scratch.
        const auto entries=plus(1024,plus(times(16,f.rows),times(10,f.slots)));
        const auto payload=plus(times(plus(times(5,f.slots),256),plus(f.value_bits,58)),
            plus(times(128,f.slots),plus(times(512,f.slots),times(16,f.rows))));
        if (entries>limits.entries || payload>limits.integer_payload_bits)
            fail(ErrorCode::capacity,"persistent state/export footprint admission exceeded");
        return f;
    }
    static dyadic_policy::Limits policy_limits(const Forecast& f, const Limits& limits) {
        // Maximum menu20: 32 retained + (12*20+64) scratch logical entries.
        return {f.quantizer_work,limits.integer_bits,336,limits.integer_payload_bits};
    }
    void healthy() const { if (failed_) fail(ErrorCode::failed_owner,"state owner already failed"); }
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
public:
    // History must remain alive for this owner's entire lifetime. Menus and
    // prior physical support are authenticated by the enclosing trainer.
    State(const History& history,std::array<std::size_t,2> hands,const Integer& denominator,
          Forecast forecast,Limits limits={})
        : history_(&history),hand_counts_(hands),forecast_(admit(forecast,limits,hands)),
          limits_(limits),quantizer_(policy_limits(forecast_,limits_)) {
        if (denominator<=0) fail(ErrorCode::invalid_scale,"state fixed game denominator must be positive");
        input_width(denominator);
        receipt_.reserved_entries=static_cast<std::size_t>(plus(1024,plus(times(16,forecast_.rows),times(10,forecast_.slots))));
        receipt_.reserved_integer_and_text_payload_bits=static_cast<std::size_t>(
            plus(times(plus(times(5,forecast_.slots),256),plus(forecast_.value_bits,58)),
                 plus(times(128,forecast_.slots),plus(times(512,forecast_.slots),times(16,forecast_.rows)))));
        charge(plus(1024,plus(times(8,forecast_.rows),plus(times(16,forecast_.slots),times(4,words(width(denominator)))))));
        denominator_=denominator;
        rows_=std::make_unique<Row[]>(forecast_.rows);
        action_text_=std::make_unique<std::array<char,64>[]>(forecast_.slots);
        action_views_=std::make_unique<std::string_view[]>(forecast_.slots);
    }
    State(const State&)=delete;
    State& operator=(const State&)=delete;
    State(State&&)=delete;
    State& operator=(State&&)=delete;
    [[nodiscard]] bool failed() const noexcept { return failed_; }
    [[nodiscard]] const Integer& denominator() const noexcept { return denominator_; }
    [[nodiscard]] Receipt receipt() const noexcept {
        auto answer=receipt_;
        answer.quantizer_work=quantizer_.receipt().work;
        answer.work=answer.state_work+answer.quantizer_work;
        return answer;
    }
    [[nodiscard]] std::span<const Row> rows() const noexcept { return {rows_.get(),receipt_.rows}; }
    [[nodiscard]] std::span<const Integer> regrets() const noexcept {
        return phase_==Phase::building ? std::span<const Integer>() : std::span<const Integer>(regrets_.get(),forecast_.slots);
    }
    [[nodiscard]] std::span<const Integer> averages() const noexcept {
        return phase_==Phase::building ? std::span<const Integer>() : std::span<const Integer>(averages_.get(),forecast_.slots);
    }
    [[nodiscard]] std::size_t register_row(History::Cursor cursor,std::size_t actor,std::size_t holding,
                                          std::span<const std::string_view> actions) {
        healthy();
        try {
            if (phase_!=Phase::building) fail(ErrorCode::phase,"state row registration is closed");
            if (actions.empty() || actions.size()>20) fail(ErrorCode::invalid_row,"state legal menu width");
            charge(plus(128,plus(times(16,logceil(forecast_.rows+1)),times(256,actions.size()))));
            for (const auto action:actions) {
                if (action.empty() || action.size()>64) fail(ErrorCode::invalid_row,"state action token length");
                for (const unsigned char c:action) if (c<0x20 || c>0x7e) fail(ErrorCode::invalid_row,"state action token encoding");
            }
            const auto identity=key(cursor,actor,holding);
            const auto found=index_.find(identity);
            if (found!=index_.end()) {
                const auto& old=rows_[found->second].actions;
                if (old.size()!=actions.size() || !std::equal(old.begin(),old.end(),actions.begin()))
                    fail(ErrorCode::changed_menu,"state repeated row legal menu changed");
                return found->second;
            }
            if (receipt_.rows>=forecast_.rows || actions.size()>forecast_.slots-receipt_.slots)
                fail(ErrorCode::capacity,"state row or slot forecast exceeded");
            const auto number=receipt_.rows, offset=receipt_.slots;
            for (std::size_t a=0;a<actions.size();++a) {
                auto& token=action_text_[offset+a];
                std::copy(actions[a].begin(),actions[a].end(),token.begin());
                action_views_[offset+a]={token.data(),actions[a].size()};
            }
            rows_[number]={std::get<0>(identity),actor,holding,offset,{action_views_.get()+offset,actions.size()}};
            index_.emplace(identity,number);
            ++receipt_.rows;
            receipt_.slots+=actions.size();
            return number;
        } catch (...) { failed_=true;throw; }
    }
    [[nodiscard]] std::size_t find_row(History::Cursor cursor,std::size_t actor,std::size_t holding) {
        healthy();
        try {
            charge(64+16*logceil(forecast_.rows+1));
            const auto found=index_.find(key(cursor,actor,holding));
            if (found==index_.end()) fail(ErrorCode::invalid_row,"state full-history row is absent");
            return found->second;
        } catch (...) { failed_=true;throw; }
    }
    void freeze() {
        healthy();
        try {
            if (phase_!=Phase::building || receipt_.rows!=forecast_.rows || receipt_.slots!=forecast_.slots)
                fail(ErrorCode::phase,"state complete row/slot census required before freeze");
            charge(plus(times(8,forecast_.slots),times(2,forecast_.rows)));
            regrets_=std::make_unique<Integer[]>(forecast_.slots);
            averages_=std::make_unique<Integer[]>(forecast_.slots);
            staged_regrets_=std::make_unique<Integer[]>(forecast_.slots);
            staged_averages_=std::make_unique<Integer[]>(forecast_.slots);
            units_=std::make_unique<std::uint64_t[]>(forecast_.slots);
            seen_=std::make_unique<unsigned char[]>(forecast_.rows);
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
            for (const auto& row:rows()) {
                charge(16+4*row.actions.size());
                const auto policy=quantizer_.regret_policy({regrets_.get()+row.offset,row.actions.size()});
                std::copy(policy.units().begin(),policy.units().end(),units_.get()+row.offset);
            }
            phase_=Phase::sweeping;
        } catch (...) { failed_=true;throw; }
    }
    // Borrowed view for this sweep. A later begin_sweep replaces these units.
    [[nodiscard]] std::span<const std::uint64_t> policy_units(std::size_t row) const {
        healthy();index_bound(row);
        if (phase_!=Phase::sweeping) fail(ErrorCode::phase,"state policy requires an active frozen sweep");
        const auto& r=rows_[row];return {units_.get()+r.offset,r.actions.size()};
    }
    // The returned exact mixed numerator belongs to the enclosing traversal.
    Integer stage_row(std::size_t row,std::span<const Integer> action_values,
                      std::span<const Integer> average_action_increments) {
        healthy();
        try {
            if (phase_!=Phase::sweeping) fail(ErrorCode::phase,"state staging requires active sweep");
            index_bound(row);const auto& r=rows_[row];const auto count=r.actions.size();
            if (seen_[row] || action_values.size()!=count || average_action_increments.size()!=count)
                fail(ErrorCode::invalid_row,"state duplicate or incomplete staged row");
            // Constant bounded backend width inspection/sign checks precede
            // arithmetic. Inputs are caller-owned and never mutated.
            charge(64+128*count);
            for (std::size_t a=0;a<count;++a) {
                input_width(action_values[a]);input_width(average_action_increments[a]);
                if (average_action_increments[a]<0) fail(ErrorCode::invalid_row,"state average increment must be nonnegative");
            }
            const auto temp_bits=forecast_.value_bits+58;
            charge(times(16*count+8,words(temp_bits)));
            receipt_.peak_arithmetic_bits=std::max(receipt_.peak_arithmetic_bits,temp_bits);
            Integer mixed=0;
            for (std::size_t a=0;a<count;++a) mixed+=action_values[a]*units_[r.offset+a];
            if (mixed%dyadic_policy::grid_units!=0)
                fail(ErrorCode::arithmetic,"state mixed value is outside fixed denominator grid");
            mixed>>=dyadic_policy::grid_bits;
            for (std::size_t a=0;a<count;++a) {
                const auto at=r.offset+a;
                Integer regret=regrets_[at]+action_values[a]-mixed;
                if (regret<0) regret=0;
                Integer average=averages_[at]+average_action_increments[a];
                retained_width(regret);retained_width(average);
                staged_regrets_[at]=std::move(regret);staged_averages_[at]=std::move(average);
            }
            seen_[row]=1;++receipt_.staged_rows;
            return mixed;
        } catch (...) { failed_=true;throw; }
    }
    void commit_sweep() {
        healthy();
        try {
            if (phase_!=Phase::sweeping || receipt_.staged_rows!=receipt_.rows)
                fail(ErrorCode::phase,"state cannot commit incomplete sweep");
            charge(times(4,receipt_.rows));
            for (std::size_t row=0;row<receipt_.rows;++row)
                if (!seen_[row]) fail(ErrorCode::phase,"state missing staged row");
            regrets_.swap(staged_regrets_);averages_.swap(staged_averages_);
            ++receipt_.completed_sweeps;phase_=Phase::closed;
        } catch (...) { failed_=true;throw; }
    }
    [[nodiscard]] AverageExport export_average() {
        healthy();
        try {
            if (phase_!=Phase::closed || receipt_.completed_sweeps!=forecast_.sweeps || exported_)
                fail(ErrorCode::phase,"state average export requires all requested sweeps once");
            charge(plus(times(4*words(forecast_.value_bits)+4,forecast_.slots),times(4,forecast_.rows)));
            AverageExport image;
            image.rows=forecast_.rows;
            image.slots=forecast_.slots;
            image.units=std::make_unique<std::uint64_t[]>(image.slots);
            image.uniform_fallback=std::make_unique<unsigned char[]>(image.rows);
            image.raw_masses=std::make_unique<Integer[]>(image.slots);
            std::copy_n(averages_.get(),image.slots,image.raw_masses.get());
            for (std::size_t i=0;i<image.rows;++i) {
                const auto& row=rows_[i];charge(16+4*row.actions.size());
                const auto policy=quantizer_.average_export({averages_.get()+row.offset,row.actions.size()});
                image.uniform_fallback[i]=static_cast<unsigned char>(policy.uniform_fallback());
                std::copy(policy.units().begin(),policy.units().end(),image.units.get()+row.offset);
            }
            exported_=true;return image;
        } catch (...) { failed_=true;throw; }
    }
};
} // namespace openpoker::virtual_dyadic_state
