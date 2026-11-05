#pragma once
// Persistent simultaneous CFR+ state. The enclosing trainer authenticates menus,
// physical support and the common fixed game denominator before calling this owner.
#include "dyadic_policy.hpp"
#include "virtual_dyadic_history.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstring>
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
struct Forecast {
    std::size_t rows = 0, slots = 0, sweeps = 0, max_history_depth = 0;
    std::size_t value_bits = 0;
    // Two disjoint cumulative allowances. A whole-game preflight must justify
    // these for the requested workload; constructor admission alone cannot.
    std::uint64_t own_work = 0, quantizer_work = 0;
};
struct ActionCatalogCapacity {
    std::size_t keys = 0, token_slots = 0;
};
struct PackedAverageCapacity {
    // Exact word census per image. regret_limbs is zero in the legacy
    // average-only mode; nonzero enables the dual packed representation.
    std::size_t limb_count = 0;
    std::size_t regret_limbs = 0;
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

class State final {
    using Key = std::tuple<std::size_t,std::size_t,std::size_t>;
    using ActionText = std::array<char,64>;
    using Menu = std::span<const std::string_view>;
    struct PackedRow { std::size_t limb_offset = 0, shift = 0; };
    struct PackedRegretRow { std::size_t limb_offset = 0, shift = 0; };
    enum class Phase { building, closed, sweeping };
    const History* history_;
    std::array<std::size_t,2> hand_counts_;
    Forecast forecast_;
    Limits limits_;
    const ActionCatalogCapacity catalog_;
    const PackedAverageCapacity packed_;
    const StorageForecast storage_;
    dyadic_policy::Quantizer quantizer_;
    Receipt receipt_{};
    Integer denominator_;
    std::unique_ptr<Row[]> rows_;
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
    std::size_t packed_words_registered_ = 0, packed_regret_words_registered_ = 0;
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
        return f;
    }
    static dyadic_policy::Limits policy_limits(const Forecast& f, const Limits& limits) {
        // Maximum menu20: 32 retained + (12*20+64) scratch logical entries.
        return {f.quantizer_work,limits.integer_bits,336,limits.integer_payload_bits};
    }
    static ActionCatalogCapacity admit_catalog(const Forecast& f, ActionCatalogCapacity capacity) {
        if (!capacity.keys && !capacity.token_slots) return capacity;
        if (!capacity.keys || !capacity.token_slots || capacity.keys>f.rows || capacity.token_slots>f.slots)
            fail(ErrorCode::invalid_forecast,"invalid state action catalog dimensions");
        // The original reservation covers three logical entries and 64 text
        // bytes per slot. Account for the catalog spans inside those same
        // bounds. Their array initialization also fits the original slot work.
        if (plus(times(3,capacity.token_slots),times(2,capacity.keys))>times(3,f.slots) ||
            plus(times(sizeof(ActionText),capacity.token_slots),times(sizeof(Menu),capacity.keys))>
                times(sizeof(ActionText),f.slots))
            fail(ErrorCode::capacity,"state action catalog exceeds original footprint");
        return capacity;
    }
    [[nodiscard]] std::size_t token_capacity() const noexcept {
        return catalog_.keys?catalog_.token_slots:forecast_.slots;
    }
    [[nodiscard]] bool packed() const noexcept { return packed_.limb_count!=0; }
    [[nodiscard]] bool packed_regrets() const noexcept { return packed_.regret_limbs!=0; }
    static StorageForecast admit_storage(const Forecast& f,const Limits& limits,
                                         ActionCatalogCapacity catalog,PackedAverageCapacity packed) {
        const auto footprint=storage_forecast(f,catalog,packed);
        if (footprint.entries>limits.entries || footprint.payload_bits>limits.integer_payload_bits)
            fail(ErrorCode::capacity,"persistent state/export footprint admission exceeded");
        return footprint;
    }
    [[nodiscard]] std::size_t packed_stride(std::size_t shift) const noexcept {
        return static_cast<std::size_t>(words(forecast_.value_bits-shift));
    }
    [[nodiscard]] Integer load_compact(const std::uint64_t* image,std::size_t offset,
                                       std::size_t shift,std::size_t action) const {
        const auto stride=packed_stride(shift);
        const auto* first=image+offset+action*stride;
        Integer result;
        // A native little-endian uint64_t pointer selects Boost's bounded copy
        // and normalize path. Packed mode admits this layout before allocation.
        boost::multiprecision::import_bits(result,first,first+stride,64,false);
        return result;
    }
    [[nodiscard]] Integer load_average(const PackedRow& row,std::size_t action) const {
        Integer result=load_compact(packed_averages_.get(),row.limb_offset,row.shift,action);
        result<<=row.shift;
        return result;
    }
    void stage_compact(const PackedRow& row,std::size_t action,const Integer& increment) {
        if (increment!=0 && boost::multiprecision::lsb(increment)<row.shift)
            fail(ErrorCode::arithmetic,"state average increment is outside certified packed scale");
        Integer value=load_compact(packed_averages_.get(),row.limb_offset,row.shift,action);
        value+=increment>>row.shift;
        if (width(value)>forecast_.value_bits-row.shift)
            fail(ErrorCode::integer_width,"state retained average exceeds packed admission");
        store_compact(staged_packed_averages_.get(),row.limb_offset,row.shift,action,value,
                      "state packed average encoding width changed");
    }
    void stage_compact_scaled(const PackedRow& row,std::size_t action,const Integer& increment) {
        Integer value=load_compact(packed_averages_.get(),row.limb_offset,row.shift,action);
        value+=increment;
        if (width(value)>forecast_.value_bits-row.shift)
            fail(ErrorCode::integer_width,"state retained average exceeds packed admission");
        store_compact(staged_packed_averages_.get(),row.limb_offset,row.shift,action,value,
                      "state packed average encoding width changed");
    }
    void stage_compact_image(const std::uint64_t* committed,std::uint64_t* staged,std::size_t offset,
                             std::size_t shift,std::size_t action,const Integer& increment,const char* label) {
        std::optional<Integer> negative_magnitude;
        const Integer* magnitude=&increment;
        if (increment<0) { negative_magnitude.emplace(-increment);magnitude=&*negative_magnitude; }
        if (*magnitude!=0 && boost::multiprecision::lsb(*magnitude)<shift)
            fail(ErrorCode::arithmetic,"state packed delta is outside certified scale");
        Integer value=load_compact(committed,offset,shift,action);
        const Integer quotient=*magnitude>>shift;
        if (increment<0) value-=quotient; else value+=quotient;
        if (value<0) value=0;
        if (width(value)>forecast_.value_bits-shift)
            fail(ErrorCode::integer_width,label);
        store_compact(staged,offset,shift,action,value,label);
    }
    void store_compact(std::uint64_t* staged,std::size_t offset,std::size_t shift,
                       std::size_t action,const Integer& value,const char* label) {
        const auto stride=packed_stride(shift);
        auto* first=staged+offset+action*stride;
        const auto& raw=value.backend();
        const auto used=raw.size()*sizeof(*raw.limbs());
        const auto bytes=stride*sizeof(*first);
        if (raw.sign() || used>bytes) fail(ErrorCode::arithmetic,label);
        std::memcpy(first,raw.limbs(),used);
        std::memset(reinterpret_cast<unsigned char*>(first)+used,0,bytes-used);
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
    static StorageForecast storage_forecast(const Forecast& f,ActionCatalogCapacity catalog={},
                                             PackedAverageCapacity packed={}) {
        (void)admit_catalog(f,catalog);
        auto entries=plus(1024,plus(times(16,f.rows),times(10,f.slots)));
        const auto width_with_scratch=plus(f.value_bits,58);
        // Preserve the original integer/text reservation in both modes.
        const auto payload=plus(times(plus(times(5,f.slots),256),width_with_scratch),
            plus(times(128,f.slots),plus(times(512,f.slots),times(16,f.rows))));
        if (packed.limb_count) {
            if (std::endian::native!=std::endian::little || !f.slots || !f.rows || !f.value_bits || f.value_bits>65536 ||
                packed.limb_count<f.slots || packed.limb_count>times(f.slots,words(f.value_bits)))
                fail(ErrorCode::invalid_forecast,"invalid packed average dimensions or platform");
            // Replace the dense committed/staged/export average arrays and,
            // when used, the original per-row menu reservation. Count each
            // retained packed word as an entry, plus metadata and one decoder.
            entries-=times(3,f.slots);
            if (catalog.keys) {
                entries-=times(3,f.slots);
                entries=plus(entries,plus(times(3,catalog.token_slots),times(2,catalog.keys)));
            }
            entries=plus(entries,plus(times(2,packed.limb_count),plus(times(2,f.rows),32)));
            auto packed_bits=plus(times(128,packed.limb_count),plus(times(8*sizeof(PackedRow),f.rows),
                times(std::min<std::size_t>(20,f.slots)+4,width_with_scratch)));
            if (packed.regret_limbs) {
                if (packed.regret_limbs<f.slots || packed.regret_limbs>times(f.slots,words(f.value_bits)))
                    fail(ErrorCode::invalid_forecast,"invalid packed regret dimensions");
                entries-=times(2,f.slots);
                entries=plus(entries,plus(times(2,packed.regret_limbs),times(2,f.rows)));
                packed_bits=plus(packed_bits,plus(times(128,packed.regret_limbs),
                    times(8*sizeof(PackedRegretRow),f.rows)));
            }
            if (packed_bits>times(packed.regret_limbs?5:3,times(f.slots,width_with_scratch)))
                fail(ErrorCode::capacity,"packed average exceeds original integer payload reservation");
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
          Forecast forecast,Limits limits,ActionCatalogCapacity catalog,PackedAverageCapacity packed)
        : history_(&history),hand_counts_(hands),forecast_(admit(forecast,limits,hands)),
          limits_(limits),catalog_(catalog),packed_(packed),storage_(admit_storage(forecast_,limits_,catalog_,packed_)),
          quantizer_(policy_limits(forecast_,limits_)) {
        if (denominator<=0) fail(ErrorCode::invalid_scale,"state fixed game denominator must be positive");
        input_width(denominator);
        receipt_.reserved_entries=storage_.entries;
        receipt_.reserved_integer_and_text_payload_bits=storage_.payload_bits;
        charge(plus(1024,plus(times(8,forecast_.rows),plus(times(16,forecast_.slots),times(4,words(width(denominator)))))));
        denominator_=denominator;
        rows_=std::make_unique<Row[]>(forecast_.rows);
        action_text_=std::make_unique<ActionText[]>(token_capacity());
        action_views_=std::make_unique<std::string_view[]>(token_capacity());
        if (catalog_.keys) action_catalog_=std::make_unique<Menu[]>(catalog_.keys);
        if (this->packed()) packed_rows_=std::make_unique<PackedRow[]>(forecast_.rows);
        if (packed_regrets()) packed_regret_rows_=std::make_unique<PackedRegretRow[]>(forecast_.rows);
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
    [[nodiscard]] ActionStorage action_storage() const noexcept {
        return {token_capacity(),catalog_.keys,catalog_.keys?stored_tokens_:receipt_.slots,
            catalog_.keys?stored_menus_:receipt_.rows,
            sizeof(ActionText)+sizeof(std::string_view),sizeof(Menu)};
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
        return packed_rows_[row].shift;
    }
    [[nodiscard]] std::size_t regret_row_shift(std::size_t row) const {
        index_bound(row);
        if (!packed_regrets()) fail(ErrorCode::invalid_row,"state has no packed regret row shift");
        return packed_regret_rows_[row].shift;
    }
    [[nodiscard]] Integer regret_numerator(std::size_t row,std::size_t action) const {
        if (phase_==Phase::building) fail(ErrorCode::phase,"state regret read before freeze");
        index_bound(row);
        if (action>=rows_[row].actions.size()) fail(ErrorCode::invalid_row,"state regret action index");
        if (!packed_regrets()) return regrets_[rows_[row].offset+action];
        Integer result=load_compact(packed_regrets_.get(),packed_regret_rows_[row].limb_offset,
                                    packed_regret_rows_[row].shift,action);
        result<<=packed_regret_rows_[row].shift;
        return result;
    }
    // This reads the committed image, including after a failed staging call.
    // A packed caller admits the copy/shift codec work for each requested value.
    [[nodiscard]] Integer average_numerator(std::size_t row,std::size_t action) const {
        if (phase_==Phase::building) fail(ErrorCode::phase,"state average read before freeze");
        index_bound(row);
        if (action>=rows_[row].actions.size()) fail(ErrorCode::invalid_row,"state average action index");
        return packed()?load_average(packed_rows_[row],action):averages_[rows_[row].offset+action];
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
            if (packed_words_registered_!=packed_.limb_count || packed_regret_words_registered_!=packed_.regret_limbs)
                fail(ErrorCode::capacity,"state complete packed average limb census required before freeze");
            charge(plus(times(8,forecast_.slots),times(2,forecast_.rows)));
            if (!packed_regrets()) {
                regrets_=std::make_unique<Integer[]>(forecast_.slots);
                staged_regrets_=std::make_unique<Integer[]>(forecast_.slots);
            }
            if (packed()) {
                packed_averages_=std::make_unique<std::uint64_t[]>(packed_.limb_count);
                staged_packed_averages_=std::make_unique<std::uint64_t[]>(packed_.limb_count);
                if (packed_regrets()) {
                    packed_regrets_=std::make_unique<std::uint64_t[]>(packed_.regret_limbs);
                    staged_packed_regrets_=std::make_unique<std::uint64_t[]>(packed_.regret_limbs);
                }
            } else {
                averages_=std::make_unique<Integer[]>(forecast_.slots);
                staged_averages_=std::make_unique<Integer[]>(forecast_.slots);
            }
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
            std::optional<std::array<Integer,20>> decoded;
            if (packed_regrets()) decoded.emplace();
            for (const auto& row:rows()) {
                charge(16+4*row.actions.size());
                std::span<const Integer> values;
                if (packed_regrets()) {
                    const auto row_index=static_cast<std::size_t>(&row-rows_.get());
                    const auto& packed_row=packed_regret_rows_[row_index];
                    for (std::size_t a=0;a<row.actions.size();++a)
                        (*decoded)[a]=load_compact(packed_regrets_.get(),packed_row.limb_offset,packed_row.shift,a);
                    values={decoded->data(),row.actions.size()};
                } else values={regrets_.get()+row.offset,row.actions.size()};
                const auto policy=quantizer_.regret_policy(values);
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
private:
    // The returned exact mixed numerator belongs to the enclosing traversal.
    Integer stage_row_impl(std::size_t row,std::span<const Integer> action_values,
                           std::span<const Integer> average_action_increments,
                           std::optional<std::size_t> scaled_shift) {
        healthy();
        try {
            if (phase_!=Phase::sweeping) fail(ErrorCode::phase,"state staging requires active sweep");
            index_bound(row);const auto& r=rows_[row];const auto count=r.actions.size();
            if (seen_[row] || action_values.size()!=count || average_action_increments.size()!=count)
                fail(ErrorCode::invalid_row,"state duplicate or incomplete staged row");
            if (scaled_shift && (!packed() || *scaled_shift!=packed_rows_[row].shift))
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
            for (std::size_t a=0;a<count;++a) mixed+=action_values[a]*units_[r.offset+a];
            if (mixed%dyadic_policy::grid_units!=0)
                fail(ErrorCode::arithmetic,"state mixed value is outside fixed denominator grid");
            mixed>>=dyadic_policy::grid_bits;
            for (std::size_t a=0;a<count;++a) {
                const auto at=r.offset+a;
                const Integer delta=action_values[a]-mixed;
                if (packed_regrets()) {
                    const auto& packed_row=packed_regret_rows_[row];
                    stage_compact_image(packed_regrets_.get(),staged_packed_regrets_.get(),
                        packed_row.limb_offset,packed_row.shift,a,delta,
                        "state retained regret exceeds packed admission");
                } else {
                    Integer regret=regrets_[at]+delta;
                    if (regret<0) regret=0;
                    retained_width(regret);
                    staged_regrets_[at]=std::move(regret);
                }
                if (scaled_shift) stage_compact_scaled(packed_rows_[row],a,average_action_increments[a]);
                else if (packed()) stage_compact(packed_rows_[row],a,average_action_increments[a]);
                else {
                    Integer average=averages_[at]+average_action_increments[a];
                    retained_width(average);
                    staged_averages_[at]=std::move(average);
                }
            }
            seen_[row]=1;++receipt_.staged_rows;
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
                if (!seen_[row]) fail(ErrorCode::phase,"state missing staged row");
            if (packed_regrets()) packed_regrets_.swap(staged_packed_regrets_);
            else regrets_.swap(staged_regrets_);
            if (packed()) packed_averages_.swap(staged_packed_averages_);
            else averages_.swap(staged_averages_);
            ++receipt_.completed_sweeps;phase_=Phase::closed;
        } catch (...) { failed_=true;throw; }
    }
    [[nodiscard]] AverageExport export_average(bool include_raw=true) {
        healthy();
        try {
            if (phase_!=Phase::closed || receipt_.completed_sweeps!=forecast_.sweeps || exported_)
                fail(ErrorCode::phase,"state average export requires all requested sweeps once");
            if (packed() && include_raw) fail(ErrorCode::phase,"state packed export requires policy-only mode");
            charge(plus(times(4*words(forecast_.value_bits)+4,forecast_.slots),times(4,forecast_.rows)));
            AverageExport image;
            image.rows=forecast_.rows;
            image.slots=forecast_.slots;
            image.units=std::make_unique<std::uint64_t[]>(image.slots);
            image.uniform_fallback=std::make_unique<unsigned char[]>(image.rows);
            if (include_raw) {
                image.raw_masses=std::make_unique<Integer[]>(image.slots);
                std::copy_n(averages_.get(),image.slots,image.raw_masses.get());
            }
            std::optional<std::array<Integer,20>> decoded;
            if (packed()) decoded.emplace();
            for (std::size_t i=0;i<image.rows;++i) {
                const auto& row=rows_[i];charge(16+4*row.actions.size());
                const Integer* masses;
                if (decoded) {
                    for (std::size_t a=0;a<row.actions.size();++a)
                        (*decoded)[a]=packed_regrets()
                            ?load_compact(packed_averages_.get(),packed_rows_[i].limb_offset,packed_rows_[i].shift,a)
                            :load_average(packed_rows_[i],a);
                    masses=decoded->data();
                } else masses=averages_.get()+row.offset;
                const auto policy=quantizer_.average_export({masses,row.actions.size()});
                image.uniform_fallback[i]=static_cast<unsigned char>(policy.uniform_fallback());
                std::copy(policy.units().begin(),policy.units().end(),image.units.get()+row.offset);
            }
            exported_=true;return image;
        } catch (...) { failed_=true;throw; }
    }
};
} // namespace openpoker::virtual_dyadic_state
