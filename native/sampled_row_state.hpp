#pragma once
// Single-writer sparse storage for signed sampled updates. The walker owns
// row identity and supplies exact increments. Publication exposes only
// committed rows and never scans the untouched part of the state.
#include "exact_binary64.hpp"
#include <boost/multiprecision/integer.hpp>
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <map>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace openpoker::sampled_row_state {
using Integer = exact_binary64::Integer;

struct Extent {
    std::size_t rows=0, slots=0, text_bytes=0;
};

struct Limits {
    Extent retained{100000,400000,16U<<20};
    Extent pending{1000,4000,1U<<20};
    std::size_t integer_bits=1024;
    std::size_t integer_payload_bits=std::size_t{1}<<30;
    std::size_t average_shift=768;
    std::uint64_t iterations=10000;
    std::uint64_t stage_calls=10000000;
};

struct Key {
    std::uint8_t actor=0, first_card=0, second_card=0;
    std::vector<std::string> history;

    [[nodiscard]] bool operator<(const Key& other) const noexcept {
        const auto head=std::tie(actor,first_card,second_card);
        const auto other_head=std::tie(other.actor,other.first_card,other.second_card);
        if (head!=other_head) return head<other_head;
        return std::lexicographical_compare(history.begin(),history.end(),
                                            other.history.begin(),other.history.end(),
            [](const std::string& a,const std::string& b) noexcept {return a.compare(b)<0;});
    }
};

struct RowView {
    std::span<const std::string> actions;
    std::span<const Integer> regrets, average;
    // Actual average denominator is average_odd_base * 2^average_shift.
    const Integer& average_odd_base;
    std::size_t average_shift;
};

struct Usage {
    Extent committed{}, pending{};
    std::size_t peak_integer_payload_bits=0;
    std::uint64_t iterations=0, stage_calls=0;
};

class State final {
    struct Row {
        std::vector<std::string> actions;
        std::vector<Integer> regrets, average;
        Integer average_odd_base;
    };
    using Rows=std::map<Key,Row>;
    Limits limits_;
    Integer denominator_;
    Rows committed_, pending_;
    Extent new_rows_;
    Usage usage_;
    bool active_=false, failed_=false;

    [[nodiscard]] static std::size_t width(const Integer& value) {
        return exact_binary64::detail::magnitude_bits(
            value,65536,exact_binary64::ErrorCode::input_bit_limit);
    }

    [[nodiscard]] static bool fits(Extent used, Extent extra, Extent cap) noexcept {
        return used.rows<=cap.rows && extra.rows<=cap.rows-used.rows &&
               used.slots<=cap.slots && extra.slots<=cap.slots-used.slots &&
               used.text_bytes<=cap.text_bytes && extra.text_bytes<=cap.text_bytes-used.text_bytes;
    }

    static void accumulate(Extent& used, Extent extra) noexcept {
        used.rows+=extra.rows;
        used.slots+=extra.slots;
        used.text_bytes+=extra.text_bytes;
    }

    [[nodiscard]] static std::size_t text_width(const std::string& text) {
        if (text.empty() || text.size()>64 ||
            std::any_of(text.begin(),text.end(),[](unsigned char c) {return c<33 || c>126;}))
            throw std::invalid_argument("sampled row has invalid token");
        return text.size();
    }

    [[nodiscard]] static std::size_t history_width(const Key& key) {
        if (key.actor>1 || key.first_card>=key.second_card || key.second_card>=52 ||
            key.history.size()>64)
            throw std::invalid_argument("sampled row identity exceeds bounds");
        std::size_t size=0;
        for (const auto& token : key.history) size+=text_width(token);
        return size;
    }

    [[nodiscard]] static Extent row_extent(const Key& key, std::span<const std::string> actions) {
        if (actions.size()<2 || actions.size()>20)
            throw std::invalid_argument("sampled row menu exceeds bounds");
        Extent shape{1,actions.size(),history_width(key)};
        for (std::size_t i=0;i<actions.size();++i) {
            shape.text_bytes+=text_width(actions[i]);
            if (std::find(actions.begin(),actions.begin()+i,actions[i])!=actions.begin()+i)
                throw std::invalid_argument("sampled row has duplicate action");
        }
        return shape;
    }

    [[nodiscard]] Integer average_units(const Integer& value, std::size_t source_shift) const {
        const auto bits=width(value);
        if (value<0 || bits>limits_.integer_bits)
            throw std::length_error("sampled row average input exceeds width or sign bounds");
        if (!bits) return 0;
        if (source_shift>limits_.average_shift) {
            const auto cancel=source_shift-limits_.average_shift;
            if (boost::multiprecision::lsb(value)<cancel)
                throw std::length_error("sampled row average precision exceeds admission");
            return value>>cancel;
        }
        const auto extend=limits_.average_shift-source_shift;
        if (bits>limits_.integer_bits-extend)
            throw std::length_error("sampled row average shift exceeds width");
        return value<<extend;
    }

    void check_writer(std::uint64_t generation) const {
        if (!active_ || failed_ || generation!=usage_.iterations)
            throw std::logic_error("sampled row writer generation mismatch");
    }

    void discard() noexcept {
        pending_.clear();
        usage_.pending={};
        new_rows_={};
        active_=false;
    }

    void charge_payload(Extent extra) {
        // A fixed integer-width reservation covers both images, plus scalar
        // arithmetic scratch. Caller-owned views and process RSS are separate.
        const auto integers=2*(usage_.committed.slots+usage_.pending.slots+extra.slots)
            +usage_.committed.rows+usage_.pending.rows+extra.rows+1;
        const auto scratch=4*(limits_.integer_bits+1);
        if (scratch>limits_.integer_payload_bits ||
            integers>(limits_.integer_payload_bits-scratch)/limits_.integer_bits)
            throw std::length_error("sampled row integer payload exceeds admission");
        const auto payload=integers*limits_.integer_bits+scratch;
        usage_.peak_integer_payload_bits=std::max(usage_.peak_integer_payload_bits,payload);
    }

public:
    State(const Integer& regret_denominator, Limits limits={}) : limits_(limits) {
        constexpr Extent cap{2000000,2000000,64U<<20};
        if (!fits(limits_.retained,limits_.pending,cap) ||
            !limits_.retained.rows || !limits_.pending.rows ||
            !limits_.retained.slots || !limits_.pending.slots ||
            !limits_.retained.text_bytes || !limits_.pending.text_bytes ||
            !limits_.integer_bits || limits_.integer_bits>65536 ||
            limits_.average_shift>=limits_.integer_bits ||
            !limits_.integer_payload_bits || limits_.integer_payload_bits>(std::size_t{1}<<30) ||
            !limits_.iterations || limits_.iterations>1000000 ||
            !limits_.stage_calls || limits_.stage_calls>100000000 ||
            regret_denominator<=0 || width(regret_denominator)>limits_.integer_bits)
            throw std::invalid_argument("invalid sampled row admission");
        charge_payload({});
        denominator_=regret_denominator;
    }
    State(const State&)=delete;
    State& operator=(const State&)=delete;

    [[nodiscard]] const Usage& usage() const noexcept {return usage_;}
    [[nodiscard]] bool failed() const noexcept {return failed_;}
    [[nodiscard]] const Integer& regret_denominator() const noexcept {return denominator_;}

    // The view remains valid until the next publication or owner destruction.
    [[nodiscard]] std::optional<RowView> committed_row(const Key& key) const {
        (void)history_width(key);
        const auto found=committed_.find(key);
        if (found==committed_.end()) return std::nullopt;
        const auto& row=found->second;
        return RowView{row.actions,row.regrets,row.average,row.average_odd_base,limits_.average_shift};
    }

    void begin(std::uint64_t generation, const Integer& regret_denominator) {
        if (active_ || failed_ || generation!=usage_.iterations ||
            generation>=limits_.iterations || width(regret_denominator)>limits_.integer_bits ||
            regret_denominator!=denominator_)
            throw std::logic_error("sampled row begin violates generation or scale");
        active_=true;
    }

    void stage(std::uint64_t generation, const Key& key, std::span<const std::string> actions,
               std::span<const Integer> regret, std::span<const Integer> average,
               const Integer& average_denominator) {
        check_writer(generation);
        try {
            if (usage_.stage_calls==limits_.stage_calls)
                throw std::length_error("sampled row call capacity exhausted");
            ++usage_.stage_calls;
            const auto shape=row_extent(key,actions);
            if (regret.size()!=shape.slots || average.size()!=shape.slots ||
                average_denominator<=0 || width(average_denominator)>limits_.integer_bits)
                throw std::invalid_argument("sampled row value shape or average denominator differs");
            if (!fits(usage_.pending,shape,limits_.pending))
                throw std::length_error("sampled row pending capacity exhausted");
            if (pending_.contains(key))
                throw std::invalid_argument("sampled row staged twice in one draw");
            const auto previous=committed_.find(key);
            const bool fresh=previous==committed_.end();
            if (fresh) {
                auto retained=usage_.committed;
                accumulate(retained,new_rows_);
                if (!fits(retained,shape,limits_.retained))
                    throw std::length_error("sampled row retained capacity exhausted");
            } else if (!std::ranges::equal(previous->second.actions,actions)) {
                throw std::invalid_argument("sampled row ordered menu changed");
            }
            charge_payload(shape);
            const auto shift=boost::multiprecision::lsb(average_denominator);
            Integer odd_base=average_denominator>>shift;
            if (width(odd_base)>limits_.integer_bits-limits_.average_shift ||
                (!fresh && previous->second.average_odd_base!=odd_base))
                throw std::invalid_argument("sampled row average base differs");
            Row next;
            next.actions.assign(actions.begin(),actions.end());
            next.average_odd_base=std::move(odd_base);
            next.regrets.reserve(shape.slots);
            next.average.reserve(shape.slots);
            for (std::size_t i=0;i<shape.slots;++i) {
                if (width(regret[i])>limits_.integer_bits)
                    throw std::length_error("sampled row regret input exceeds width");
                Integer signed_regret=regret[i], mass=average_units(average[i],shift);
                if (!fresh) {
                    signed_regret+=previous->second.regrets[i];
                    mass+=previous->second.average[i];
                }
                if (width(signed_regret)>limits_.integer_bits || width(mass)>limits_.integer_bits)
                    throw std::length_error("sampled row accumulated value exceeds width");
                next.regrets.push_back(std::move(signed_regret));
                next.average.push_back(std::move(mass));
            }
            pending_.emplace(key,std::move(next));
            accumulate(usage_.pending,shape);
            if (fresh) accumulate(new_rows_,shape);
        } catch (...) {
            discard();
            failed_=true;
            throw;
        }
    }

    void commit(std::uint64_t generation) {
        check_writer(generation);
        // Same allocator and a noexcept key comparator mean that node
        // transfer and vector swaps require no allocation or arithmetic.
        while (!pending_.empty()) {
            const auto next=pending_.begin();
            const auto previous=committed_.find(next->first);
            if (previous==committed_.end()) {
                committed_.insert(pending_.extract(next));
            } else {
                previous->second.regrets.swap(next->second.regrets);
                previous->second.average.swap(next->second.average);
                pending_.erase(next);
            }
        }
        accumulate(usage_.committed,new_rows_);
        discard();
        ++usage_.iterations;
    }

    // A failed walk consumes the writer. Previously committed rows survive.
    void abort(std::uint64_t generation) {
        check_writer(generation);
        discard();
        failed_=true;
    }
};
} // namespace openpoker::sampled_row_state
