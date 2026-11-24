#pragma once
// Sparse fixed-Q52 vanilla strategy rows for two sequential PROOF9 epochs.
// This is a component contract, not a trainer or admission for other games.
#include "dyadic_policy.hpp"
#include "virtual_dyadic_history.hpp"
#include "virtual_strategy_catalog.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <map>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

namespace openpoker::virtual_sparse_strategy_epoch {
namespace policy = dyadic_policy;
namespace history = virtual_dyadic_history;
namespace catalog = virtual_strategy_catalog;
using Integer = policy::Integer;
using RowId = catalog::RowId;
using History = history::History;
using Catalog = catalog::Catalog;
using Cursor = History::Cursor;
inline constexpr std::uint64_t grid = policy::grid_units;
inline constexpr std::size_t action_limit = 4;
inline constexpr std::size_t epoch_limit = 2;
inline const Integer regret_denominator = Integer(580) << 625;
inline const Integer average_denominator = Integer(580) << 364;
inline constexpr std::uint64_t work_cap = 75'000'000;
inline constexpr std::size_t entries_cap = 2'000'000;
inline constexpr std::size_t payload_bits_cap = std::size_t{1} << 30;

enum class ErrorKind { invalid_limits, owner_mismatch, failed_owner, active_lease,
                       lease_generation, incomplete_walk, row_or_menu, duplicate_stage,
                       epoch_limit, arithmetic, resource_limit, quantizer };
enum class ArithmeticContract { uniform_public_proof9, true_joint_proof9, weighted_joint_fixed_tree,
                                weighted_joint_single_pass };
enum class ProposalLaw { uniform_public, weighted_river, true_joint };
class Error final : public std::runtime_error {
    ErrorKind kind_;
public:
    Error(ErrorKind kind, const char* message) : std::runtime_error(message), kind_(kind) {}
    [[nodiscard]] ErrorKind kind() const noexcept { return kind_; }
};

struct Limits {
    std::size_t max_rows_touched = 1'060;       // cumulative across two transitions
    std::size_t max_slots_touched = 2'564;
    std::size_t max_stage_rows = 530;           // per transition
    std::size_t max_stage_slots = 1'282;
    std::uint64_t max_reads = 2'136;            // two policy reads per row plus controls
    std::size_t catalog_max_public_blocks = 24'420;
    std::uint64_t max_work = work_cap;
    std::size_t max_entries = entries_cap;
    std::size_t max_payload_bits = payload_bits_cap;
    std::size_t max_epochs = epoch_limit;
    // Borrowed Catalog bitmap cost, not a numerical row allocation.
    std::size_t catalog_max_holding_count = 2;
    std::size_t policy_reads_per_row = 2;
    catalog::Limits::SeenStorage catalog_seen_storage = catalog::Limits::SeenStorage::eager_bitmap;
};

struct Forecast {
    std::uint64_t constructor_work = 0;
    std::uint64_t lease_work = 0;
    std::uint64_t read_work = 0;
    std::uint64_t stage_work = 0;
    std::uint64_t commit_work = 0;
    std::uint64_t enumeration_work = 0;
    std::uint64_t export_work = 0;
    std::uint64_t quantizer_work = 0;
    std::uint64_t catalog_read_work = 0; // billed by Catalog
    std::uint64_t history_read_work = 0; // billed by History
    std::uint64_t own_work = 0;
    std::uint64_t component_work = 0; // Store + Quantizer; do not double-count borrowed owners
    std::uint64_t work = 0;
    std::size_t entries = 0;
    std::size_t payload_bits = 0;
    std::uint64_t max_quantized_rows = 0;
};

struct Receipt {
    std::uint64_t work = 0;
    std::uint64_t reads = 0;
    std::uint64_t staged_rows = 0;
    std::uint64_t staged_slots = 0;
    std::uint64_t commits = 0;
    std::uint64_t quantizer_work = 0;
    std::uint64_t quantized_rows = 0;
    std::uint64_t export_calls = 0;
    std::uint64_t export_rows = 0;
    std::uint64_t export_slots = 0;
    std::size_t current_rows = 0;
    std::size_t pending_rows = 0;
    std::size_t current_slots = 0;
    std::size_t pending_slots = 0;
    std::size_t peak_payload_bits = 0;
};

inline std::size_t magnitude_bits(const Integer& value) {
    const auto& backend = value.backend();
    const auto count = backend.size();
    using Limb = std::remove_cvref_t<decltype(backend.limbs()[0])>;
    constexpr auto limb_bits = std::numeric_limits<Limb>::digits;
    return count ? limb_bits * (count - 1) + std::bit_width(backend.limbs()[count - 1]) : 0;
}
inline constexpr std::uint64_t words(std::size_t bits) { return (bits + 63) / 64; }
inline constexpr std::uint64_t copy_cost(std::size_t bits) { return 1 + 2 * words(bits); }
inline constexpr std::uint64_t add_cost(std::size_t bits) { return 2 + 3 * words(bits); }
inline constexpr std::uint64_t multiply_cost(std::size_t a, std::size_t b) {
    return 2 + 2 * (words(a) + words(b)) + words(a) * words(b);
}
inline constexpr std::uint64_t stage_slot_work() {
    return 48 + copy_cost(649) + add_cost(649) + multiply_cost(383, 317) + add_cost(382) + 64 +
        multiply_cost(648,53) + add_cost(703) + 2*multiply_cost(383,53) +
        add_cost(383) + 2*copy_cost(436) + 32;
}
inline constexpr std::uint64_t row_map_work(std::size_t rows) {
    return 128 + 32 * std::bit_width(rows + 1);
}

inline std::vector<std::uint64_t> uniform_units(std::size_t count) {
    if (!count || count > action_limit) throw Error(ErrorKind::row_or_menu, "sparse row action count");
    std::vector<std::uint64_t> result(count);
    const auto base = grid / count;
    const auto remainder = grid % count;
    for (std::size_t i = 0; i < count; ++i) result[i] = base + (i < remainder ? 1 : 0);
    return result;
}

inline Forecast forecast(const Limits& limits) {
    if (limits.max_epochs != epoch_limit || !limits.max_rows_touched ||
        limits.max_rows_touched > 1'060 || !limits.max_slots_touched || limits.max_slots_touched > 2'564 ||
        !limits.max_stage_rows || limits.max_stage_rows > 530 ||
        !limits.max_stage_slots || limits.max_stage_slots > 1'282 ||
        2 * limits.max_stage_rows > limits.max_rows_touched ||
        2 * limits.max_stage_slots > limits.max_slots_touched ||
        (limits.policy_reads_per_row!=1 && limits.policy_reads_per_row!=2) ||
        (limits.catalog_seen_storage!=catalog::Limits::SeenStorage::eager_bitmap &&
         limits.catalog_seen_storage!=catalog::Limits::SeenStorage::first_holding_inline) ||
        limits.max_reads < limits.policy_reads_per_row * limits.max_rows_touched || limits.max_reads > 2'136 ||
        !limits.catalog_max_public_blocks || limits.catalog_max_public_blocks > 24'420 ||
        !limits.max_work || limits.max_work > work_cap || !limits.max_entries || limits.max_entries > entries_cap ||
        !limits.max_payload_bits || limits.max_payload_bits > payload_bits_cap ||
        !limits.catalog_max_holding_count || limits.catalog_max_holding_count > catalog::maximum_holding_count)
        throw Error(ErrorKind::invalid_limits, "invalid sparse strategy epoch limits");
    Forecast f;
    f.constructor_work = 2'048;
    f.lease_work = limits.max_epochs * 128;
    const auto map_work = row_map_work(limits.max_rows_touched);
    f.read_work = limits.max_reads * (160 + 32 * action_limit + 2 * map_work) +
        limits.max_epochs * limits.max_stage_rows * 128; // sealed lease-directory release
    f.stage_work = limits.max_epochs * (1'024 + limits.max_stage_rows *
        (512 + 2 * row_map_work(limits.max_stage_rows) +
         2 * row_map_work(limits.max_rows_touched) + action_limit * stage_slot_work()));
    f.commit_work = limits.max_epochs * (2'048 + limits.max_stage_rows *
        (256 + row_map_work(limits.max_rows_touched) + 32 * action_limit + 256));
    f.enumeration_work = limits.max_epochs * limits.max_stage_rows *
        (256 + row_map_work(limits.max_stage_rows));
    f.export_work = 256 + 3 * limits.max_stage_rows *
        (256 + action_limit * (copy_cost(649) + copy_cost(382) + 8));
    f.max_quantized_rows = limits.max_epochs * limits.max_stage_rows;
    // Legacy/separate worst case at 649-bit R, 701-bit scaled weights,
    // four positives: 11,200 wide-kernel units plus 320 setup/LSB scans.
    f.quantizer_work = f.max_quantized_rows * 12'000;
    if (f.constructor_work > std::numeric_limits<std::uint64_t>::max() - f.lease_work ||
        f.constructor_work + f.lease_work > std::numeric_limits<std::uint64_t>::max() - f.read_work ||
        f.constructor_work + f.lease_work + f.read_work > std::numeric_limits<std::uint64_t>::max() - f.stage_work ||
        f.constructor_work + f.lease_work + f.read_work + f.stage_work > std::numeric_limits<std::uint64_t>::max() - f.commit_work ||
        f.constructor_work + f.lease_work + f.read_work + f.stage_work + f.commit_work > std::numeric_limits<std::uint64_t>::max() - f.enumeration_work ||
        f.constructor_work + f.lease_work + f.read_work + f.stage_work + f.commit_work + f.enumeration_work > std::numeric_limits<std::uint64_t>::max() - f.export_work ||
        f.constructor_work + f.lease_work + f.read_work + f.stage_work + f.commit_work + f.enumeration_work + f.export_work >
            std::numeric_limits<std::uint64_t>::max() - f.quantizer_work)
        throw Error(ErrorKind::invalid_limits, "sparse strategy forecast overflow");
    f.own_work = f.constructor_work + f.lease_work + f.read_work + f.stage_work +
        f.commit_work + f.enumeration_work + f.export_work;
    const auto catalog_map_steps = std::bit_width(limits.catalog_max_public_blocks + 1);
    const auto catalog_access = 512 + 256 * catalog::maximum_actions + 32 * catalog_map_steps +
        8 * ((limits.catalog_max_holding_count + 63) / 64) +
        (limits.catalog_seen_storage==catalog::Limits::SeenStorage::first_holding_inline?32:0);
    f.catalog_read_work = (limits.max_reads * 2 + limits.max_epochs * limits.max_stage_rows) * catalog_access;
    // resolve + view per policy read, and one validating view per staged row.
    // History decision key/actions, Catalog's full history identity, and the
    // first-block menu revalidation path, for every supported policy read.
    f.history_read_work = limits.max_reads *
        (32 + 24 + 16 * action_limit + 48 + 32 + 24 + 16 * action_limit);
    f.component_work = f.own_work + f.quantizer_work;
    f.work = f.own_work + f.quantizer_work + f.catalog_read_work + f.history_read_work;
    f.entries = 256 + 48 * limits.max_rows_touched + 16 * limits.max_slots_touched + 2'048;
    f.payload_bits = 2 * limits.max_slots_touched * (649 + 382 + 64) +
        2 * limits.max_rows_touched * 2'048 + 64 * 64'000;
    if (f.work > limits.max_work || f.entries > limits.max_entries || f.payload_bits > limits.max_payload_bits)
        throw Error(ErrorKind::invalid_limits, "sparse strategy forecast exceeds its admitted component caps");
    return f;
}

struct FrozenRow {
    std::uint64_t actor = 0;
    std::uint64_t holding_index = 0;
    std::uint64_t history_ordinal = 0;
    std::uint64_t offset = 0; // sentinel only; sparse identity is RowId/full ordinal
    std::span<const std::string> actions;
};
struct FrozenPolicyView {
    RowId id;
    FrozenRow row;
    std::span<const std::uint64_t> units;
};

class Store final {
public:
    class EpochLease;
private:
    using DefaultPolicyTable = std::array<std::array<std::uint64_t, action_limit>, action_limit + 1>;
    struct Entry {
        std::vector<Integer> regrets;
        std::vector<Integer> averages;
        std::vector<std::uint64_t> units;
        std::size_t payload_bits = 0;
        void swap(Entry& other) noexcept {
            regrets.swap(other.regrets); averages.swap(other.averages); units.swap(other.units);
            std::swap(payload_bits, other.payload_bits);
        }
    };
    struct Seen {
        std::size_t actions = 0;
        std::uint8_t reads = 0;
    };
    Limits limits_;
    Forecast forecast_;
    const ArithmeticContract arithmetic_;
    History* history_;
    Catalog* catalog_;
    std::array<std::size_t, 2> hand_counts_;
    policy::Quantizer quantizer_;
    std::map<RowId, Entry> current_;
    std::map<RowId, Entry> pending_;
    std::map<RowId, Seen> staged_ids_;
    DefaultPolicyTable uniform_defaults_{};
    Receipt receipt_{};
    std::uint64_t generation_ = 0;
    std::size_t committed_epochs_ = 0;
    std::size_t last_exported_epoch_ = 0;
    std::size_t epoch_stage_rows_ = 0;
    std::size_t epoch_stage_slots_ = 0;
    std::size_t current_payload_bits_ = 0;
    std::size_t pending_payload_bits_ = 0;
    std::size_t current_slots_ = 0;
    std::size_t pending_slots_ = 0;
    bool active_ = false;
    bool visitor_active_ = false;
    bool pending_ready_ = false;
    bool poisoned_ = false;

    static ArithmeticContract admit_arithmetic(ArithmeticContract arithmetic,const Limits& limits) {
        if (arithmetic!=ArithmeticContract::uniform_public_proof9 &&
            arithmetic!=ArithmeticContract::true_joint_proof9 &&
            arithmetic!=ArithmeticContract::weighted_joint_fixed_tree &&
            arithmetic!=ArithmeticContract::weighted_joint_single_pass)
            throw Error(ErrorKind::invalid_limits,"unknown sparse arithmetic contract");
        const auto expected=arithmetic==ArithmeticContract::weighted_joint_single_pass?1U:2U;
        if (limits.policy_reads_per_row!=expected)
            throw Error(ErrorKind::invalid_limits,"sparse read count differs from arithmetic contract");
        return arithmetic;
    }
    static policy::Limits quantizer_limits(const Limits& limits) {
        const auto f = forecast(limits);
        if (f.work > limits.max_work) throw Error(ErrorKind::invalid_limits, "no work remains for quantizer owner");
        policy::Limits q;
        q.work = f.quantizer_work;
        q.integer_bits = 704;
        q.entries = limits.max_entries;
        q.integer_payload_bits = limits.max_payload_bits;
        q.profile = policy::Profile::legacy;
        q.division_kernel = policy::DivisionKernel::separate;
        q.mixed_cache = false;
        return q;
    }
    [[noreturn]] void reject(ErrorKind kind, const char* message) {
        poisoned_ = true;
        throw Error(kind, message);
    }
    void healthy() const {
        if (poisoned_) throw Error(ErrorKind::failed_owner, "sparse strategy store failed closed");
        if (catalog_->failed()) throw Error(ErrorKind::failed_owner, "sparse strategy catalog failed");
    }
    void charge(std::uint64_t amount) {
        if (amount > forecast_.own_work - receipt_.work)
            reject(ErrorKind::resource_limit, "sparse strategy component work exceeded");
        receipt_.work += amount;
    }
    void check_epoch(const EpochLease& lease);
    void release(std::uint64_t generation, bool complete) noexcept {
        if (active_ && generation_ == generation) {
            active_ = false;
            if (!complete) poisoned_ = true;
        }
    }
    static DefaultPolicyTable make_uniform_defaults() noexcept {
        DefaultPolicyTable table{};
        for (std::size_t count = 1; count <= action_limit; ++count) {
            const auto base = grid / count;
            const auto remainder = grid % count;
            for (std::size_t action = 0; action < count; ++action)
                table[count][action] = base + (action < remainder ? 1 : 0);
        }
        return table;
    }
    static std::size_t entry_payload_bits(const Entry& entry) {
        std::size_t bits = 2'048 + 64 * entry.units.size();
        for (const auto& x : entry.regrets) bits += magnitude_bits(x);
        for (const auto& x : entry.averages) bits += magnitude_bits(x);
        return bits;
    }
    void refresh_receipt() {
        receipt_.current_rows = current_.size();
        receipt_.pending_rows = pending_.size();
        receipt_.current_slots = current_slots_;
        receipt_.pending_slots = pending_slots_;
        receipt_.peak_payload_bits = std::max(receipt_.peak_payload_bits,
            current_payload_bits_ + pending_payload_bits_ + 2'048 * (staged_ids_.size()));
    }
    static void validate_entry(const Entry& entry, std::size_t actions) {
        if (entry.regrets.size() != actions || entry.averages.size() != actions ||
            entry.units.size() != actions || !actions || actions > action_limit)
            throw Error(ErrorKind::row_or_menu, "sparse strategy entry/menu width");
        Integer positive_sum = 0;
        std::uint64_t unit_sum = 0;
        for (std::size_t i = 0; i < actions; ++i) {
            if (magnitude_bits(entry.regrets[i]) > 649 || entry.averages[i] < 0 ||
                magnitude_bits(entry.averages[i]) > 382)
                throw Error(ErrorKind::arithmetic, "sparse strategy cumulative integer bound");
            if (entry.regrets[i] > 0) positive_sum += entry.regrets[i];
            if (entry.units[i] > grid - unit_sum)
                throw Error(ErrorKind::arithmetic, "sparse strategy policy partition overflow");
            unit_sum += entry.units[i];
        }
        if (magnitude_bits(positive_sum) > 651 || unit_sum != grid)
            throw Error(ErrorKind::arithmetic, "sparse strategy positive sum or policy partition");
    }
    Entry default_entry(std::size_t actions) const {
        Entry result;
        result.regrets.resize(actions);
        result.averages.resize(actions);
        result.units = uniform_units(actions);
        return result;
    }
    void stage_impl(EpochLease& lease, RowId id, std::span<const Integer> raw_regrets,
                    std::span<const Integer> raw_averages, const Integer& raw_average_denominator,
                    const Integer& raw_regret_denominator);
    void commit_impl();

public:
    class EpochLease final {
        friend class Store;
        Store* owner_ = nullptr;
        std::uint64_t generation_ = 0;
        std::map<RowId, Seen> observed_;
        std::size_t slots_ = 0;
        std::uint64_t reads_ = 0;
        std::size_t complete_rows_ = 0;
        bool observed_rows_consumed_ = false;
        bool raw_complete_ = false;
        bool live_ = false;
        EpochLease(Store& owner, std::uint64_t generation) : owner_(&owner), generation_(generation), live_(true) {}
        void check() const {
            if (!owner_) throw Error(ErrorKind::lease_generation, "moved-from sparse epoch lease");
            owner_->check_epoch(*this);
        }
        [[nodiscard]] bool staged_complete() const noexcept {
            return owner_ && raw_complete_ && owner_->pending_ready_ &&
                owner_->epoch_stage_rows_==observed_.size() &&
                owner_->epoch_stage_slots_==slots_;
        }
    public:
        EpochLease() = default;
        EpochLease(const EpochLease&) = delete;
        EpochLease& operator=(const EpochLease&) = delete;
        EpochLease(EpochLease&& other) noexcept
            : owner_(std::exchange(other.owner_, nullptr)), generation_(other.generation_),
              observed_(std::move(other.observed_)), slots_(other.slots_), reads_(other.reads_),
              complete_rows_(other.complete_rows_), observed_rows_consumed_(other.observed_rows_consumed_),
              raw_complete_(other.raw_complete_),
              live_(std::exchange(other.live_, false)) {}
        EpochLease& operator=(EpochLease&& other) noexcept {
            if (this != &other) {
                if (live_ && owner_) owner_->release(generation_, staged_complete());
                owner_ = std::exchange(other.owner_, nullptr); generation_ = other.generation_;
                observed_ = std::move(other.observed_); slots_ = other.slots_; reads_ = other.reads_;
                complete_rows_ = other.complete_rows_; observed_rows_consumed_ = other.observed_rows_consumed_;
                raw_complete_ = other.raw_complete_;
                live_ = std::exchange(other.live_, false);
            }
            return *this;
        }
        ~EpochLease() { if (live_ && owner_) owner_->release(generation_, staged_complete()); }

        [[nodiscard]] bool raw_policy_ready() const noexcept {
            return owner_ && live_ && owner_->active_ && owner_->generation_ == generation_ &&
                   !owner_->poisoned_ && !owner_->catalog_->failed() && !raw_complete_;
        }
        [[nodiscard]] ArithmeticContract arithmetic_contract() const {
            check();
            return owner_->arithmetic_contract();
        }
        [[nodiscard]] const std::array<std::size_t,2>& declared_hand_counts() const {
            check();
            return owner_->hand_counts_;
        }
        [[nodiscard]] FrozenPolicyView frozen_policy(Cursor cursor, std::size_t actor, std::size_t holding) {
            check();
            try {
                if (raw_complete_ || actor > 1 || holding >= owner_->hand_counts_[actor])
                    owner_->reject(ErrorKind::row_or_menu, "sparse frozen policy read outside active walk");
                owner_->charge(160 + 32 * action_limit +
                    2 * row_map_work(owner_->limits_.max_rows_touched));
                if (++reads_ > owner_->limits_.max_reads || ++owner_->receipt_.reads > owner_->limits_.max_reads)
                    owner_->reject(ErrorKind::resource_limit, "sparse policy read limit exceeded");
                const auto info = owner_->history_->decision_key(cursor);
                if (info.actor != actor || !info.actions || info.actions > action_limit)
                    owner_->reject(ErrorKind::row_or_menu, "sparse policy history actor/menu mismatch");
                std::array<std::string_view, action_limit> tokens{};
                owner_->history_->decision_actions(cursor, std::span(tokens).first(info.actions));
                const auto id = owner_->catalog_->resolve(*owner_->history_, cursor, actor, holding,
                    owner_->hand_counts_[actor], info.source, std::span(tokens).first(info.actions));
                const auto catalog_row = owner_->catalog_->view(id);
                if (catalog_row.actor != actor || catalog_row.holding_index != holding ||
                    catalog_row.source_menu_ref != info.source || catalog_row.actions.size() != info.actions)
                    owner_->reject(ErrorKind::row_or_menu, "sparse catalog row/menu mismatch");
                const auto current = owner_->current_.find(id);
                auto observation = observed_.lower_bound(id);
                const bool needs_observation = observation == observed_.end() || observation->first != id;
                const auto next_entries = owner_->current_.size() + owner_->pending_.size() +
                    owner_->staged_ids_.size() + observed_.size() +
                    static_cast<std::size_t>(needs_observation);
                const auto next_payload = owner_->current_payload_bits_ + owner_->pending_payload_bits_ +
                    2'048 * (owner_->staged_ids_.size() + observed_.size() + static_cast<std::size_t>(needs_observation));
                if (next_entries > owner_->forecast_.entries || next_entries > owner_->limits_.max_entries ||
                    next_payload > owner_->limits_.max_payload_bits ||
                    (needs_observation && (observed_.size() + 1 > owner_->limits_.max_stage_rows ||
                        slots_ + info.actions > owner_->limits_.max_stage_slots)))
                    owner_->reject(ErrorKind::resource_limit, "sparse lease directory exceeds its reservation");
                auto seen_position = observation;
                bool inserted = false;
                if (needs_observation) {
                    seen_position = observed_.emplace_hint(observation, id, Seen{info.actions, 0});
                    inserted = true;
                }
                auto& seen = *seen_position;
                if (inserted) {
                    slots_ += info.actions;
                } else if (seen.second.actions != info.actions) {
                    owner_->reject(ErrorKind::row_or_menu, "sparse observed menu changed");
                }
                if (++seen.second.reads > owner_->limits_.policy_reads_per_row)
                    owner_->reject(ErrorKind::incomplete_walk, "sparse row read too many times");
                if (seen.second.reads == owner_->limits_.policy_reads_per_row) ++complete_rows_;
                std::span<const std::uint64_t> units;
                if (current != owner_->current_.end()) units = current->second.units;
                else units = std::span<const std::uint64_t>(owner_->uniform_defaults_[info.actions]).first(info.actions);
                const auto descriptor_bits = owner_->current_payload_bits_ + owner_->pending_payload_bits_ +
                    2'048 * (observed_.size() + owner_->staged_ids_.size());
                owner_->receipt_.peak_payload_bits = std::max(owner_->receipt_.peak_payload_bits, descriptor_bits);
                if (descriptor_bits > owner_->limits_.max_payload_bits ||
                    owner_->current_.size() + owner_->pending_.size() + observed_.size() + owner_->staged_ids_.size() >
                        owner_->forecast_.entries)
                    owner_->reject(ErrorKind::resource_limit, "sparse lease directory reservation exceeded");
                if (units.size() != info.actions) owner_->reject(ErrorKind::row_or_menu, "sparse policy row width");
                return {id, {static_cast<std::uint64_t>(actor), static_cast<std::uint64_t>(holding),
                         catalog_row.public_ordinal, 0, catalog_row.actions}, units};
            } catch (...) { owner_->poisoned_ = true; throw; }
        }

        // Call only after the raw front door has accepted complete row/slot/visit coverage.
        void seal_raw_walk(std::size_t rows, std::size_t slots, std::uint64_t reads) {
            check();
            try {
                if (raw_complete_ || rows != observed_.size() || slots != slots_ || reads != reads_ ||
                    reads != owner_->limits_.policy_reads_per_row * rows || complete_rows_ != observed_.size())
                    owner_->reject(ErrorKind::incomplete_walk, "sparse raw walk is not a complete two-seat pass");
                owner_->charge(rows * 128); // bounded seal plus eventual observed-directory release
                raw_complete_ = true;
            } catch (...) { owner_->poisoned_ = true; throw; }
        }
        template<class Callback>
        void consume_observed_rows(Callback&& callback) {
            check();
            if (!raw_complete_) owner_->reject(ErrorKind::incomplete_walk, "sparse rows are unavailable before walk seal");
            if (observed_rows_consumed_) owner_->reject(ErrorKind::incomplete_walk, "sparse row enumeration is one-shot");
            owner_->charge(owner_->forecast_.enumeration_work / owner_->limits_.max_epochs);
            observed_rows_consumed_ = true;
            try {
                for (const auto& [id, seen] : observed_) callback(id, seen.actions, seen.reads);
            } catch (...) { owner_->poisoned_ = true; throw; }
        }
        void stage(RowId id, std::span<const Integer> raw_regrets,
                   std::span<const Integer> raw_averages, const Integer& raw_average_denominator,
                   const Integer& raw_regret_denominator) {
            if (!owner_) throw Error(ErrorKind::lease_generation, "moved-from sparse epoch lease");
            owner_->stage_impl(*this, id, raw_regrets, raw_averages,
                               raw_average_denominator, raw_regret_denominator);
        }
        void stage(RowId id, std::span<const Integer> raw_regrets,
                   std::span<const Integer> raw_averages, const Integer& raw_average_denominator) {
            if (!owner_) throw Error(ErrorKind::lease_generation, "moved-from sparse epoch lease");
            owner_->stage_impl(*this, id, raw_regrets, raw_averages,
                               raw_average_denominator, owner_->regret_denominator_value());
        }
    };

private:
    static Limits admit_catalog_storage(const Catalog& owner,Limits limits) {
        if ((limits.catalog_seen_storage!=catalog::Limits::SeenStorage::eager_bitmap &&
             limits.catalog_seen_storage!=catalog::Limits::SeenStorage::first_holding_inline) ||
            owner.admitted_limits().seen_storage!=limits.catalog_seen_storage)
            throw Error(ErrorKind::invalid_limits,"sparse strategy Catalog storage contract mismatch");
        return limits;
    }
public:
    Store(Catalog& catalog_owner, History& history_owner, std::array<std::size_t, 2> declared_hand_counts,
          Limits limits = {},ArithmeticContract arithmetic=ArithmeticContract::uniform_public_proof9)
        : limits_(admit_catalog_storage(catalog_owner,limits)), forecast_(forecast(limits)), arithmetic_(admit_arithmetic(arithmetic,limits)),
          history_(&history_owner), catalog_(&catalog_owner),
          hand_counts_(declared_hand_counts), quantizer_(quantizer_limits(limits)),
          uniform_defaults_(make_uniform_defaults()) {
        const auto& catalog_limits = catalog_owner.admitted_limits();
        const auto& catalog_receipt = catalog_owner.receipt();
        const auto required_catalog_lookups = limits.max_reads * 2 + limits.max_epochs * limits.max_stage_rows;
        const bool weighted=arithmetic_==ArithmeticContract::weighted_joint_fixed_tree ||
            arithmetic_==ArithmeticContract::weighted_joint_single_pass;
        const bool dimensions_ok=weighted ?
            (declared_hand_counts[0] && declared_hand_counts[1] &&
             declared_hand_counts[0]<=limits.catalog_max_holding_count &&
             declared_hand_counts[1]<=limits.catalog_max_holding_count) :
            (declared_hand_counts==std::array<std::size_t,2>{2,2} && limits.catalog_max_holding_count==2);
        if (!dimensions_ok || catalog_owner.failed() ||
            !catalog_owner.owns_identity(history_owner, declared_hand_counts) ||
            catalog_limits.max_holding_count > limits.catalog_max_holding_count ||
            catalog_limits.max_public_blocks > limits.catalog_max_public_blocks ||
            catalog_receipt.lookups > catalog_limits.max_lookups ||
            required_catalog_lookups > catalog_limits.max_lookups - catalog_receipt.lookups ||
            catalog_receipt.work > catalog_limits.max_work ||
            forecast_.catalog_read_work > catalog_limits.max_work - catalog_receipt.work)
            throw Error(ErrorKind::invalid_limits, "sparse strategy epoch declared catalog contract mismatch");
        charge(forecast_.constructor_work);
    }
    Store(const Store&) = delete;
    Store& operator=(const Store&) = delete;
    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }
    [[nodiscard]] const Forecast& admitted_forecast() const noexcept { return forecast_; }
    [[nodiscard]] ArithmeticContract arithmetic_contract() const noexcept { return arithmetic_; }
    [[nodiscard]] const Integer& regret_denominator_value() const {
        if (arithmetic_==ArithmeticContract::uniform_public_proof9) return regret_denominator;
        // Immutable scalar constants fit the existing fixed scratch/metadata
        // envelope. Legacy construction never initializes these joint values.
        static const Integer joint=Integer(1)<<625;
        return joint;
    }
    [[nodiscard]] const Integer& average_denominator_value() const {
        if (arithmetic_==ArithmeticContract::uniform_public_proof9) return average_denominator;
        static const Integer joint=Integer(1)<<364;
        return joint;
    }
    [[nodiscard]] std::size_t committed_epochs() const noexcept { return committed_epochs_; }
    [[nodiscard]] bool failed() const noexcept { return poisoned_ || catalog_->failed() || quantizer_.failed(); }
    [[nodiscard]] bool raw_policy_ready() const noexcept { return active_ && !failed(); }
    // Optional read-only export, at most once per committed epoch. Spans are callback-scoped; the
    // callback cost is owned by its caller and must be metered there.
    template<class Callback>
    void visit_committed(Callback&& callback) {
        healthy();
        if (active_ || visitor_active_ || pending_ready_ || !committed_epochs_ ||
            last_exported_epoch_ >= committed_epochs_)
            reject(ErrorKind::active_lease, "sparse committed image export is out of phase");
        const auto rows = current_.size();
        const auto slots = current_slots_;
        if (receipt_.export_rows + rows > 3 * limits_.max_stage_rows ||
            receipt_.export_slots + slots > 3 * limits_.max_stage_slots)
            reject(ErrorKind::resource_limit, "sparse committed export census exceeded");
        const auto work = 128 + rows * 256 + slots * (copy_cost(649) + copy_cost(382) + 8);
        charge(work);
        ++receipt_.export_calls;
        last_exported_epoch_ = committed_epochs_;
        receipt_.export_rows += rows;
        receipt_.export_slots += slots;
        visitor_active_ = true;
        try {
            for (const auto& [id, entry] : current_)
                callback(id, std::span<const Integer>(entry.regrets),
                    std::span<const Integer>(entry.averages), std::span<const std::uint64_t>(entry.units));
            visitor_active_ = false;
        } catch (...) { visitor_active_ = false; poisoned_ = true; throw; }
    }
    [[nodiscard]] EpochLease begin_epoch(ProposalLaw law) {
        healthy();
        const auto expected=arithmetic_==ArithmeticContract::uniform_public_proof9?
            ProposalLaw::uniform_public:ProposalLaw::true_joint;
        if (law != expected)
            reject(ErrorKind::invalid_limits, "sparse proposal law differs from constructor-bound arithmetic");
        if (active_ || visitor_active_) reject(ErrorKind::active_lease, "one sparse epoch owner operation is already active");
        if (committed_epochs_ >= epoch_limit || pending_ready_)
            reject(ErrorKind::epoch_limit, "sparse strategy epoch transition unavailable");
        charge(128);
        if (++generation_ == 0) reject(ErrorKind::lease_generation, "sparse epoch generation exhausted");
        active_ = true;
        epoch_stage_rows_ = epoch_stage_slots_ = 0;
        staged_ids_.clear(); pending_.clear();
        return EpochLease(*this, generation_);
    }
    void commit() { healthy(); if (active_ || visitor_active_) reject(ErrorKind::active_lease, "cannot commit while sparse epoch owner is active"); commit_impl(); }
private:
    friend class EpochLease;
};

inline void Store::check_epoch(const EpochLease& lease) {
    healthy();
    if (!lease.live_ || lease.owner_ != this || !active_ || lease.generation_ != generation_)
        reject(ErrorKind::lease_generation, "stale or foreign sparse epoch lease");
}

inline void Store::stage_impl(EpochLease& lease, RowId id, std::span<const Integer> raw_regrets,
                              std::span<const Integer> raw_averages, const Integer& raw_average_denominator,
                              const Integer& raw_regret_denominator) {
    check_epoch(lease);
    try {
        if (!lease.raw_complete_ || committed_epochs_ >= epoch_limit || raw_regrets.empty() ||
            raw_regrets.size() != raw_averages.size() || raw_regrets.size() > action_limit)
            reject(ErrorKind::incomplete_walk, "sparse stage requires a complete walk and bounded row");
        const auto actions=raw_regrets.size();
        if (epoch_stage_rows_+1>limits_.max_stage_rows || epoch_stage_slots_+actions>limits_.max_stage_slots ||
            receipt_.staged_rows+1>limits_.max_rows_touched || receipt_.staged_slots+actions>limits_.max_slots_touched)
            reject(ErrorKind::resource_limit,"sparse stage row/slot limit exceeded before work");
        charge((epoch_stage_rows_ == 0 ? 1'024 : 0) + 512 +
            2 * row_map_work(limits_.max_stage_rows) +
            2 * row_map_work(limits_.max_rows_touched) + stage_slot_work() * actions);
        const auto seen = lease.observed_.find(id);
        if (seen == lease.observed_.end() || seen->second.reads != limits_.policy_reads_per_row ||
            seen->second.actions != raw_regrets.size())
            reject(ErrorKind::row_or_menu, "sparse stage row was not read in both target passes");
        auto staged_position = staged_ids_.lower_bound(id);
        if (staged_position != staged_ids_.end() && staged_position->first == id)
            reject(ErrorKind::duplicate_stage, "duplicate sparse row stage");
        const auto row = catalog_->view(id);
        if (row.actor > 1 || row.holding_index >= hand_counts_[row.actor] ||
            row.actions.size() != raw_regrets.size())
            reject(ErrorKind::row_or_menu, "sparse stage catalog identity/menu mismatch");
        if (magnitude_bits(raw_regret_denominator) > 638 || raw_regret_denominator <= 0 ||
            raw_regret_denominator != regret_denominator_value() ||
            magnitude_bits(raw_average_denominator) > 381 || raw_average_denominator <= 0 ||
            (arithmetic_!=ArithmeticContract::uniform_public_proof9?
                raw_average_denominator!=average_denominator_value():
                Integer(average_denominator) % raw_average_denominator != 0))
            reject(ErrorKind::arithmetic, "sparse raw denominator outside exact fixed contract");
        const Integer average_factor = average_denominator_value() / raw_average_denominator;
        if (magnitude_bits(average_factor) > 317)
            reject(ErrorKind::arithmetic, "sparse average scale bound");
        const auto predicted_entries = current_.size() + pending_.size() + staged_ids_.size() +
            lease.observed_.size() + 2;
        const auto predicted_payload = current_payload_bits_ + pending_payload_bits_ +
            2'048 + actions * (649 + 382 + 64) +
            2'048 * (lease.observed_.size() + staged_ids_.size() + 1) + 40'000;
        if (predicted_entries > forecast_.entries || predicted_entries > limits_.max_entries ||
            predicted_payload > limits_.max_payload_bits)
            reject(ErrorKind::resource_limit, "sparse stage temporary allocation exceeds its reservation");
        const auto old = current_.find(id);
        Entry next = old == current_.end() ? default_entry(raw_regrets.size()) : old->second;
        Integer regret_dot=0,raw_mass=0;
        for(std::size_t i=0;i<actions;++i) {
            if(magnitude_bits(raw_regrets[i])>648 || raw_averages[i]<0 || magnitude_bits(raw_averages[i])>383)
                reject(ErrorKind::arithmetic,"sparse raw integer exceeds source bound");
            regret_dot+=raw_regrets[i]*next.units[i];
            raw_mass+=raw_averages[i];
            if(magnitude_bits(regret_dot)>703 || magnitude_bits(raw_mass)>383)
                reject(ErrorKind::arithmetic,"sparse raw row accumulation bound");
        }
        if(regret_dot!=0)reject(ErrorKind::arithmetic,"raw regret does not center on the leased policy");
        for(std::size_t i=0;i<actions;++i)
            if(raw_averages[i]*grid!=raw_mass*next.units[i])
                reject(ErrorKind::arithmetic,"raw averages do not follow the leased policy");
        const bool regret_changed = std::any_of(raw_regrets.begin(), raw_regrets.end(),
                                                [](const Integer& x) { return x != 0; });
        for (std::size_t i = 0; i < raw_regrets.size(); ++i) {
            if (magnitude_bits(raw_regrets[i]) > 648 || raw_averages[i] < 0 ||
                magnitude_bits(raw_averages[i]) > 383)
                reject(ErrorKind::arithmetic, "sparse raw integer exceeds source bound");
            next.regrets[i] += raw_regrets[i];
            const Integer average_delta = raw_averages[i] * average_factor;
            if (magnitude_bits(average_delta) > 382)
                reject(ErrorKind::arithmetic, "sparse converted average bound");
            next.averages[i] += average_delta;
        }
        next.payload_bits = entry_payload_bits(next);
        Integer positive_sum = 0;
        for (std::size_t i = 0; i < next.regrets.size(); ++i) {
            if (magnitude_bits(next.regrets[i]) > 649 || next.averages[i] < 0 ||
                magnitude_bits(next.averages[i]) > 382)
                reject(ErrorKind::arithmetic, "sparse cumulative integer bound before quantization");
            if (next.regrets[i] > 0) positive_sum += next.regrets[i];
        }
        if (magnitude_bits(positive_sum) > 651)
            reject(ErrorKind::arithmetic, "sparse positive regret sum bound");
        if (regret_changed) {
            const auto before = quantizer_.receipt();
            receipt_.peak_payload_bits = std::max(receipt_.peak_payload_bits,
                current_payload_bits_ + pending_payload_bits_ +
                2'048 + actions * (649 + 382 + 64) +
                2'048 * (lease.observed_.size() + staged_ids_.size() + 1) + 40'000);
            const auto policy_image = quantizer_.regret_policy(std::span<const Integer>(next.regrets));
            next.units.assign(policy_image.units().begin(), policy_image.units().end());
            receipt_.quantizer_work = quantizer_.receipt().work;
            receipt_.quantized_rows = quantizer_.receipt().rows;
            if (receipt_.quantizer_work > forecast_.quantizer_work ||
                receipt_.quantized_rows > forecast_.max_quantized_rows ||
                quantizer_.receipt().work - before.work > limits_.max_work - forecast_.work + forecast_.quantizer_work)
                reject(ErrorKind::resource_limit, "sparse quantizer budget exceeded");
        }
        validate_entry(next, raw_regrets.size());
        if (std::any_of(next.regrets.begin(), next.regrets.end(), [](const auto& x) { return x != 0; }) ||
            std::any_of(next.averages.begin(), next.averages.end(), [](const auto& x) { return x != 0; })) {
            const auto payload = next.payload_bits;
            auto [pending, inserted] = pending_.emplace(id, std::move(next));
            if (!inserted) reject(ErrorKind::duplicate_stage, "duplicate pending sparse row");
            pending_payload_bits_ += payload;
            pending_slots_ += actions;
        }
        staged_ids_.emplace_hint(staged_position, id, Seen{raw_regrets.size(), 2});
        ++epoch_stage_rows_; epoch_stage_slots_ += raw_regrets.size();
        ++receipt_.staged_rows; receipt_.staged_slots += raw_regrets.size();
        pending_ready_ = true;
        refresh_receipt();
        receipt_.peak_payload_bits = std::max(receipt_.peak_payload_bits,
            current_payload_bits_ + pending_payload_bits_ +
            2'048 * (lease.observed_.size() + staged_ids_.size()));
        const auto active_entries = current_.size() + pending_.size() +
            staged_ids_.size() + lease.observed_.size();
        if (active_entries > forecast_.entries || active_entries > limits_.max_entries ||
            receipt_.peak_payload_bits > limits_.max_payload_bits)
            reject(ErrorKind::resource_limit, "sparse active storage reservation exceeded");
    } catch (...) { poisoned_ = true; throw; }
}

inline void Store::commit_impl() {
    try {
        if (!pending_ready_ || committed_epochs_ >= epoch_limit || staged_ids_.empty())
            reject(ErrorKind::epoch_limit, "sparse commit requires a staged complete epoch");
        charge(2'048 + pending_.size() *
            (256 + row_map_work(limits_.max_rows_touched) + 32 * action_limit + 128) +
            staged_ids_.size() * 128);
        // Inspect only staged rows. Maintained payload/slot counters make this
        // projection independent of the size of the full current strategy.
        std::size_t projected_rows = current_.size();
        std::size_t projected_slots = current_slots_;
        std::size_t projected_payload = current_payload_bits_;
        for (const auto& [id, entry] : pending_) {
            validate_entry(entry, entry.units.size());
            const auto found = current_.find(id);
            if (found == current_.end()) {
                ++projected_rows;
                projected_slots += entry.units.size();
                projected_payload += entry.payload_bits;
            } else {
                projected_slots -= found->second.units.size();
                projected_slots += entry.units.size();
                projected_payload -= found->second.payload_bits;
                projected_payload += entry.payload_bits;
            }
        }
        const auto transient_payload = current_payload_bits_ + pending_payload_bits_ +
            2'048 * staged_ids_.size();
        receipt_.peak_payload_bits = std::max(receipt_.peak_payload_bits, transient_payload);
        if (projected_rows > limits_.max_rows_touched || projected_slots > limits_.max_slots_touched ||
            projected_rows + pending_.size() + staged_ids_.size() > forecast_.entries ||
            projected_payload > limits_.max_payload_bits || transient_payload > limits_.max_payload_bits ||
            receipt_.work + receipt_.quantizer_work > limits_.max_work ||
            receipt_.work + receipt_.quantizer_work > forecast_.component_work)
            reject(ErrorKind::resource_limit, "sparse next image exceeds its admission before publication");
        static_assert(noexcept(std::declval<RowId>() < std::declval<RowId>()));
        for (auto it = pending_.begin(); it != pending_.end(); ++it) {
            const auto found = current_.find(it->first);
            if (found != current_.end()) {
                found->second.swap(it->second);
            }
        }
        current_.merge(pending_); // existing collisions retain old entries in pending_
        current_payload_bits_ = projected_payload;
        current_slots_ = projected_slots;
        pending_payload_bits_ = 0;
        pending_slots_ = 0;
        ++committed_epochs_; ++receipt_.commits;
        pending_.clear(); staged_ids_.clear(); pending_ready_ = false;
        refresh_receipt();
    } catch (...) { poisoned_ = true; throw; }
}

} // namespace openpoker::virtual_sparse_strategy_epoch
