#pragma once

#include "virtual_dyadic_history.hpp"
#include "virtual_information_identity.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <compare>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <map>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace openpoker::virtual_strategy_catalog {
using History = virtual_dyadic_history::History;
inline constexpr std::size_t maximum_holding_count = 1326;
inline constexpr std::size_t maximum_actions = 20;
inline constexpr std::uint64_t work_cap = 75000000;
inline constexpr std::size_t entries_cap = 2000000;
inline constexpr std::size_t payload_bits_cap = std::size_t{1} << 30;
inline constexpr std::uint64_t maximum_depth = 15;

enum class ErrorKind { invalid_limits, actor_holding, depth, foreign_cursor,
                       foreign_row, unknown_holding, changed_menu, capacity, failed_owner };
class Error final : public std::runtime_error {
    ErrorKind kind_;
public:
    Error(ErrorKind kind, const char* message) : std::runtime_error(message), kind_(kind) {}
    [[nodiscard]] ErrorKind kind() const noexcept { return kind_; }
};

struct Limits {
    std::size_t max_public_blocks=0, max_information_rows_seen=0,
                max_action_slots_seen=0, max_menus=0, max_holding_count=0;
    std::uint64_t max_lookups=0, max_work=0;
    std::size_t max_metadata_entries=0, max_metadata_payload_bits=0;
};
struct Receipt {
    std::uint64_t work=0, lookups=0;
    std::size_t public_blocks=0, information_rows_seen=0,
                action_slots_seen=0, menus=0, metadata_entries=0,
                metadata_payload_bits=0;
};

// Owner-qualified stable two-coordinate handle. It contains no pointers and is
// intentionally not a serialized policy key.
class RowId final {
    friend class Catalog;
    std::uint64_t owner_=0;
    std::size_t block_=0, holding_=0;
    RowId(std::uint64_t owner,std::size_t block,std::size_t holding)
        : owner_(owner),block_(block),holding_(holding) {}
public:
    RowId()=default;
    friend auto operator<=>(const RowId&,const RowId&)=default;
};

struct RowView {
    std::uint64_t public_ordinal=0;
    std::size_t actor=0, source_menu_ref=0, holding_index=0;
    std::span<const std::string> actions;
};

class Catalog final {
    struct Menu { std::size_t source_ref=0; std::vector<std::string> actions; };
    struct Block {
        std::uint64_t ordinal=0;
        std::size_t actor=0, source_ref=0, menu_index=0, hand_count=0;
        std::vector<std::uint64_t> seen;
        std::size_t seen_count=0;
    };
    Limits limits_;
    const History* history_owner_;
    std::array<std::size_t,2> hand_counts_;
    Receipt receipt_{};
    std::uint64_t owner_=0;
    bool failed_=false;
    std::vector<std::unique_ptr<Block>> blocks_;
    std::vector<std::unique_ptr<Menu>> menus_;
    std::map<std::pair<std::uint64_t,std::size_t>,std::size_t> directory_;
    std::map<std::size_t,std::size_t> source_menus_;
    inline static std::atomic<std::uint64_t> next_owner_{1};

    static std::size_t checked_add(std::size_t a,std::size_t b) {
        if (b>std::numeric_limits<std::size_t>::max()-a) throw Error(ErrorKind::invalid_limits,"catalog size overflow");
        return a+b;
    }
    static std::size_t checked_mul(std::size_t a,std::size_t b) {
        if (a && b>std::numeric_limits<std::size_t>::max()/a) throw Error(ErrorKind::invalid_limits,"catalog size overflow");
        return a*b;
    }
    static void validate_geometry(const Limits& l) {
        if (!l.max_public_blocks || l.max_public_blocks>entries_cap ||
            !l.max_menus || l.max_menus>entries_cap ||
            !l.max_information_rows_seen || l.max_information_rows_seen>entries_cap ||
            !l.max_action_slots_seen || l.max_action_slots_seen>entries_cap ||
            !l.max_holding_count || l.max_holding_count>maximum_holding_count || !l.max_lookups)
            throw Error(ErrorKind::invalid_limits,"invalid strategy catalog geometry");
    }
    static std::size_t words_for(const Limits& l) {
        validate_geometry(l);
        const auto bitmap_words=(l.max_holding_count+63)/64;
        // Logical descriptor/directory allowance, including stable block
        // ownership and map/vector bookkeeping; not an allocator/RSS metric.
        const auto words=checked_add(checked_add(1024,checked_add(checked_mul(32,l.max_public_blocks),
                  checked_mul(320,l.max_menus))),checked_mul(l.max_public_blocks,bitmap_words));
        if (words>entries_cap) throw Error(ErrorKind::invalid_limits,"strategy catalog metadata entries exceed cap");
        return words;
    }
    static std::uint64_t operation_bound(const Limits& l) {
        validate_geometry(l);
        const auto map_steps=static_cast<std::uint64_t>(std::bit_width(l.max_public_blocks+1));
        const auto bitmap_words=(l.max_holding_count+63)/64;
        return 512+256*maximum_actions+32*map_steps+8*bitmap_words;
    }
    static std::uint64_t lifetime_bound(const Limits& l) {
        validate_geometry(l);
        const auto per=operation_bound(l);
        const auto fixed=std::uint64_t{1024}+8*l.max_public_blocks+8*l.max_menus;
        if (l.max_lookups>(std::numeric_limits<std::uint64_t>::max()-fixed)/per)
            throw Error(ErrorKind::invalid_limits,"catalog work forecast overflow");
        return fixed+l.max_lookups*per;
    }
    static std::uint64_t new_owner() {
        auto v=next_owner_.load(std::memory_order_relaxed);
        for (;;) {
            if (!v || v==std::numeric_limits<std::uint64_t>::max())
                throw Error(ErrorKind::capacity,"catalog owner ids exhausted");
            if (next_owner_.compare_exchange_weak(v,v+1,std::memory_order_relaxed)) return v;
        }
    }
    void healthy() const { if (failed_) throw Error(ErrorKind::failed_owner,"strategy catalog owner failed"); }
    void charge(std::uint64_t n) {
        if (n>limits_.max_work-receipt_.work) throw Error(ErrorKind::capacity,"strategy catalog work exceeded");
        receipt_.work+=n;
    }
    [[noreturn]] void reject(ErrorKind k,const char* message) { failed_=true; throw Error(k,message); }
    void charge_access() {
        if (receipt_.lookups>=limits_.max_lookups) reject(ErrorKind::capacity,"strategy catalog lookup cap exceeded");
        ++receipt_.lookups;
        charge(operation_bound(limits_));
    }
    static bool same_menu(std::span<const std::string> owned,std::span<const std::string_view> input) {
        if (owned.size()!=input.size()) return false;
        for (std::size_t i=0;i<input.size();++i) if (owned[i]!=input[i]) return false;
        return true;
    }
public:
    [[nodiscard]] static std::size_t metadata_word_forecast(const Limits& limits) { return words_for(limits); }
    [[nodiscard]] static std::uint64_t work_forecast(const Limits& limits) { return lifetime_bound(limits); }
    explicit Catalog(const History& history,std::array<std::size_t,2> hand_counts,Limits limits)
        : limits_(limits),history_owner_(&history),hand_counts_(hand_counts),owner_(new_owner()) {
        if (!limits.max_public_blocks || limits.max_public_blocks>entries_cap || !limits.max_information_rows_seen ||
            limits.max_information_rows_seen>entries_cap || !limits.max_action_slots_seen ||
            limits.max_action_slots_seen>entries_cap ||
            !limits.max_menus || limits.max_menus>entries_cap || !limits.max_holding_count || limits.max_holding_count>maximum_holding_count ||
            !limits.max_lookups || !limits.max_work || limits.max_work>work_cap)
            throw Error(ErrorKind::invalid_limits,"invalid strategy catalog limits");
        if (!hand_counts[0] || !hand_counts[1] || hand_counts[0]>limits.max_holding_count ||
            hand_counts[1]>limits.max_holding_count || lifetime_bound(limits)>limits.max_work)
            throw Error(ErrorKind::invalid_limits,"invalid strategy catalog holding or work forecast");
        const auto entries=words_for(limits);
        const auto payload=checked_mul(entries,64);
        if (entries>entries_cap || entries>limits.max_metadata_entries || payload>payload_bits_cap ||
            payload>limits.max_metadata_payload_bits)
            throw Error(ErrorKind::invalid_limits,"strategy catalog metadata reservation exceeds cap");
        receipt_.metadata_entries=entries;
        receipt_.metadata_payload_bits=payload;
        receipt_.work=std::uint64_t{1024}+8*limits.max_public_blocks+8*limits.max_menus;
        blocks_.reserve(limits.max_public_blocks);
        menus_.reserve(limits.max_menus);
    }
    Catalog(const Catalog&)=delete; Catalog& operator=(const Catalog&)=delete;
    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }
    [[nodiscard]] bool failed() const noexcept { return failed_; }
    [[nodiscard]] const Limits& admitted_limits() const noexcept { return limits_; }
    [[nodiscard]] bool owns_identity(const History& owner,std::array<std::size_t,2> hands) const noexcept {
        return history_owner_==&owner && hand_counts_==hands;
    }

    RowId resolve(const History& history,History::Cursor cursor,std::size_t actor,
                  std::size_t holding,std::size_t hand_count,std::size_t source_menu_ref,
                  std::span<const std::string_view> actions) {
        healthy();
        try {
            if (&history!=history_owner_) reject(ErrorKind::foreign_cursor,"foreign history owner");
            charge_access();
            if (actor>1 || hand_count!=hand_counts_[actor] || holding>=hand_count)
                reject(ErrorKind::actor_holding,"invalid actor or original holding index");
            const auto identity=virtual_information_identity::key(history,cursor,actor,holding,
                                                                  hand_counts_.data(),maximum_depth);
            const auto ordinal=std::get<0>(identity);
            const auto key=std::pair{static_cast<std::uint64_t>(ordinal),actor};
            auto found=directory_.find(key);
            if (found!=directory_.end()) {
                auto& block=*blocks_[found->second];
                if (block.hand_count!=hand_count) reject(ErrorKind::actor_holding,"catalog row declared hand count changed");
                if (block.source_ref!=source_menu_ref) reject(ErrorKind::changed_menu,"catalog source menu reference changed");
                const auto& menu=*menus_[block.menu_index];
                if (!same_menu(menu.actions,actions)) reject(ErrorKind::changed_menu,"catalog source menu contents changed");
                if (holding>=block.hand_count) reject(ErrorKind::unknown_holding,"unknown holding index");
                const bool seen=(block.seen[holding/64]>>(holding%64))&1U;
                if (!seen) {
                    if (receipt_.information_rows_seen>=limits_.max_information_rows_seen ||
                        menu.actions.size()>limits_.max_action_slots_seen-receipt_.action_slots_seen)
                        reject(ErrorKind::capacity,"strategy catalog row or slot cap exceeded");
                    block.seen[holding/64]|=std::uint64_t{1}<<(holding%64);
                    ++block.seen_count; ++receipt_.information_rows_seen;
                    receipt_.action_slots_seen+=menu.actions.size();
                }
                return RowId(owner_,found->second,holding);
            }
            const auto info=history.decision_key(cursor);
            if (info.actor!=actor) reject(ErrorKind::actor_holding,"history actor mismatch");
            if (info.source!=source_menu_ref) reject(ErrorKind::changed_menu,"source menu reference differs from history node");
            if (actions.empty() || actions.size()>maximum_actions || actions.size()!=info.actions)
                reject(ErrorKind::changed_menu,"history action menu extent changed");
            std::array<std::string_view,maximum_actions> expected{};
            history.decision_actions(cursor,std::span(expected).first(info.actions));
            if (!std::equal(actions.begin(),actions.end(),expected.begin()))
                reject(ErrorKind::changed_menu,"source menu differs from history menu");
            auto menu_found=source_menus_.find(source_menu_ref);
            const bool new_menu=menu_found==source_menus_.end();
            if (receipt_.public_blocks>=limits_.max_public_blocks || (new_menu && receipt_.menus>=limits_.max_menus) ||
                receipt_.information_rows_seen>=limits_.max_information_rows_seen ||
                actions.size()>limits_.max_action_slots_seen-receipt_.action_slots_seen)
                reject(ErrorKind::capacity,"strategy catalog block, menu, row, or slot cap exceeded");
            std::size_t menu_index=0;
            if (!new_menu) {
                menu_index=menu_found->second;
                if (!same_menu(menus_[menu_index]->actions,actions)) reject(ErrorKind::changed_menu,"source menu reference changed contents");
            } else {
                auto menu=std::make_unique<Menu>();
                menu->source_ref=source_menu_ref;
                menu->actions.reserve(actions.size());
                for (auto a:actions) {
                    if (a.empty() || a.size()>64) reject(ErrorKind::changed_menu,"invalid catalog action token");
                    for (const unsigned char c:a) if (c<0x20 || c>0x7e) reject(ErrorKind::changed_menu,"invalid catalog action encoding");
                    menu->actions.emplace_back(a);
                }
                menu_index=menus_.size();
                menus_.push_back(std::move(menu));
                source_menus_.emplace(source_menu_ref,menu_index);
            }
            auto block=std::make_unique<Block>();
            block->ordinal=key.first; block->actor=actor; block->source_ref=source_menu_ref;
            block->menu_index=menu_index; block->hand_count=hand_count;
            block->seen.assign((hand_count+63)/64,0);
            block->seen[holding/64]|=std::uint64_t{1}<<(holding%64);
            block->seen_count=1;
            const auto index=blocks_.size();
            blocks_.push_back(std::move(block));
            directory_.emplace(key,index);
            ++receipt_.public_blocks; if (new_menu) ++receipt_.menus; ++receipt_.information_rows_seen;
            receipt_.action_slots_seen+=actions.size();
            return RowId(owner_,index,holding);
        } catch (const virtual_information_identity::Error& e) {
            failed_=true;
            if (e.kind()==virtual_information_identity::ErrorKind::depth)
                throw Error(ErrorKind::depth,"strategy catalog history depth exceeds forecast");
            throw Error(ErrorKind::actor_holding,"invalid actor or original holding index");
        } catch (const virtual_dyadic_history::Error&) {
            failed_=true;
            throw Error(ErrorKind::foreign_cursor,"foreign or invalid history cursor");
        } catch (...) { failed_=true; throw; }
    }

    [[nodiscard]] RowView view(RowId id) {
        healthy();
        try {
        charge_access();
        if (id.owner_!=owner_) reject(ErrorKind::foreign_row,"foreign strategy catalog row id");
        if (id.block_>=blocks_.size()) reject(ErrorKind::foreign_row,"invalid strategy catalog row id");
        const auto& b=*blocks_[id.block_];
        if (id.holding_>=b.hand_count || !((b.seen[id.holding_/64]>>(id.holding_%64))&1U))
            reject(ErrorKind::unknown_holding,"unknown strategy catalog holding");
        const auto& m=*menus_[b.menu_index];
        return {b.ordinal,b.actor,m.source_ref,id.holding_,m.actions};
        } catch (...) { failed_=true; throw; }
    }
};
} // namespace openpoker::virtual_strategy_catalog
