#pragma once
// Literal card-free path + complete visible prefix. No shared-state row alias.
#include "full_deck_public_chance.hpp"
#include "virtual_betting_template.hpp"
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace openpoker::virtual_dyadic_history {
namespace betting = virtual_betting_template;
struct Limits {
    std::size_t nodes=250000, entries=2000000, owned_bytes=32*1024*1024, depth=64;
    std::uint64_t work=500000000;
};
struct Receipt {
    std::uint64_t work=0;
    std::size_t nodes=0, entries=0, owned_bytes=0, max_depth=0,
                peak_scratch_entries=0,peak_total_bytes=0;
};
class Error final : public std::runtime_error {
public: explicit Error(const char* message):std::runtime_error(message){}
};
class History final {
    struct Occurrence {
        std::array<std::size_t,20> children{};
        std::array<char,64> incoming{};
        std::size_t source=0,parent=0,depth=0,count=0,incoming_size=0,visible=0;
        betting::Phase phase=betting::Phase::decision;
        std::uint8_t next_street=0,actor=0;
        bool reveal=false;
    };
    Limits limits_;
    mutable Receipt receipt_{};
    std::unique_ptr<Occurrence[]> paths_;
    std::size_t path_count_=0;
    std::uint64_t deck_mask_=0,generation_=0;
    mutable bool failed_=false;
    inline static std::atomic<std::uint64_t> next_generation_{1};
    static std::uint64_t generation() {
        auto value=next_generation_.load(std::memory_order_relaxed);
        for (unsigned i=0;i<64;++i) {
            if (value==UINT64_MAX) throw Error("history generation exhausted");
            if (next_generation_.compare_exchange_weak(value,value+1,std::memory_order_relaxed)) return value;
        }
        throw Error("history generation contention bound");
    }
    void charge(std::uint64_t work) const {
        if (work>limits_.work-receipt_.work) {failed_=true;throw Error("compact history work exceeded");}
        receipt_.work+=work;
    }
    std::uint64_t board_code(std::span<const std::uint8_t> board) const {
        const auto n=board.size();
        if (n!=0 && n!=3 && n!=4 && n!=5) throw Error("compact history prefix length");
        if (n>=3 && !(board[0]<board[1] && board[1]<board[2])) throw Error("compact history flop order");
        std::uint64_t mask=0,code=static_cast<std::uint64_t>(n)<<30;
        for (std::size_t i=0;i<n;++i) {
            const auto c=board[i];
            if (c>=52 || !(deck_mask_&(std::uint64_t{1}<<c)) || (mask&(std::uint64_t{1}<<c)))
                throw Error("compact history foreign or repeated card");
            mask|=std::uint64_t{1}<<c;code|=static_cast<std::uint64_t>(c)<<(6*i);
        }
        return code;
    }
public:
    class Cursor final {
        friend class History;
        const History* owner_=nullptr;
        std::uint64_t generation_=0;
        std::size_t path_=0,size_=0;
        std::array<std::uint8_t,5> board_{};
        Cursor(const History* owner,std::uint64_t gen,std::size_t path,std::size_t size,
               std::array<std::uint8_t,5> board):owner_(owner),generation_(gen),path_(path),size_(size),board_(board){}
    public: Cursor()=default;
    };
    struct DecisionKey {
        std::size_t ordinal,source,depth,actor,actions;
    };
private:
    const Occurrence& validate(Cursor c) const {
        if (failed_) throw Error("compact history owner failed");
        charge(8);
        if (c.owner_!=this || c.generation_!=generation_ || c.path_>=path_count_)
            throw Error("foreign compact history cursor");
        const auto& p=paths_[c.path_];
        if (c.size_!=p.visible) throw Error("compact history cursor prefix mismatch");
        return p;
    }
    [[nodiscard]] std::size_t encoded_ordinal(Cursor c) const {
        return static_cast<std::size_t>((static_cast<std::uint64_t>(c.path_)<<33)|
            board_code({c.board_.data(),c.size_}));
    }
public:
    // Template construction is separately charged by the enclosing training owner.
    // This constructor captures literal path/token data; no borrowed source survives.
    explicit History(const betting::Template& source,
                     full_deck_public_chance::DeckDefinition deck,
                     Limits limits={}):limits_(limits) {
        static_assert(sizeof(std::size_t)>=8,"compact history keys require 64-bit size_t");
        if (!limits.nodes || limits.nodes>250000 || !limits.entries || limits.entries>2000000 ||
            !limits.owned_bytes || limits.owned_bytes>32*1024*1024 || !limits.depth || limits.depth>64 ||
            !limits.work || limits.work>500000000) throw Error("compact history reduce-only limits");
        charge(256);
        if (deck.count<9 || deck.count>52 ||
            (deck.mode!=full_deck_public_chance::DeckMode::full52 && deck.mode!=full_deck_public_chance::DeckMode::reduced_proof) ||
            (deck.mode==full_deck_public_chance::DeckMode::full52 && deck.count!=52)) throw Error("compact history deck mode");
        for (std::size_t i=0;i<deck.count;++i) {
            if (deck.cards[i]>=52 || (i && deck.cards[i-1]>=deck.cards[i])) throw Error("compact history deck order");
            deck_mask_|=std::uint64_t{1}<<deck.cards[i];
        }
        const auto count=source.receipt().logical_occurrences;
        if (!count || count>limits.nodes || count>((limits.entries-1)/32) ||
            count>(limits.owned_bytes/sizeof(Occurrence))) throw Error("compact literal history storage admission");
        if (source.receipt().history_suffix_only || source.root()>=source.nodes().size() ||
            source.nodes()[source.root()].state.street!=0 || source.receipt().max_depth>limits.depth)
            throw Error("compact history requires whole preflop root");
        // One fixed-size record, up to 20 child slots and 64 token bytes per literal
        // occurrence, with bounded source-menu validation. Reserve before allocation.
        charge(1024+4096*count);
        // Exact-sized record storage avoids implementation-dependent reserve
        // overcapacity in the logical owned-record byte admission.
        paths_=std::make_unique<Occurrence[]>(static_cast<std::size_t>(count));
        paths_[0].source=source.root();path_count_=1;
        for (std::size_t at=0;at<path_count_;++at) {
            const auto id=paths_[at].source;
            if (id>=source.nodes().size()) throw Error("compact history source edge");
            const auto& node=source.nodes()[id];
            const auto width=node.edges.size();
            if (node.state.street!=paths_[at].visible) throw Error("compact history source street mismatch");
            if (width>20 || paths_[at].depth>limits.depth) throw Error("compact history menu or depth");
            // At menu20, pairwise token equality may scan 64 bytes per pair.
            // The original fixed reservation covers menu4; charge larger menus
            // before their additional token loops, without changing old caps.
            const auto menu_work=256+224*width+32*width*(width?width-1:0);
            if (menu_work>4096) charge(menu_work-4096);
            if ((node.state.phase==betting::Phase::decision && (!width || node.state.actor>1)) ||
                (node.state.phase==betting::Phase::reveal && width!=1) ||
                ((node.state.phase==betting::Phase::fold || node.state.phase==betting::Phase::showdown) && width))
                throw Error("compact history source phase");
            paths_[at].phase=node.state.phase;paths_[at].actor=node.state.actor;
            paths_[at].next_street=node.state.next_street;paths_[at].count=width;
            for (std::size_t j=0;j<width;++j) {
                if (path_count_>=count) throw Error("compact history occurrence census mismatch");
                const auto& edge=node.edges[j];
                Occurrence child;child.source=edge.child;child.parent=at;child.depth=paths_[at].depth+1;
                child.reveal=node.state.phase==betting::Phase::reveal;
                child.visible=child.reveal?node.state.next_street:paths_[at].visible;
                if (child.reveal) {
                    const auto old=paths_[at].visible;
                    if (!((old==0 && child.visible==3)||(old==3 && child.visible==4)||(old==4 && child.visible==5)))
                        throw Error("compact history reveal order");
                } else {
                    if (edge.action.token.empty() || edge.action.token.size()>64) throw Error("compact history action token width");
                    for (unsigned char c:edge.action.token) if (c<32 || c>126) throw Error("compact history action token text");
                    for (std::size_t k=0;k<j;++k) if (node.edges[k].action.token==edge.action.token)
                        throw Error("compact history duplicate action token");
                    child.incoming_size=edge.action.token.size();
                    std::copy(edge.action.token.begin(),edge.action.token.end(),child.incoming.begin());
                }
                paths_[at].children[j]=path_count_;paths_[path_count_++]=child;
            }
            receipt_.max_depth=std::max(receipt_.max_depth,paths_[at].depth);
        }
        if (path_count_!=count) throw Error("compact history incomplete literal census");
        receipt_.nodes=path_count_;receipt_.entries=32*path_count_+1;
        receipt_.owned_bytes=sizeof(Occurrence)*path_count_;generation_=generation();
        receipt_.peak_total_bytes=receipt_.owned_bytes;
    }
    History(const History&)=delete;History& operator=(const History&)=delete;
    History(History&&)=delete;History& operator=(History&&)=delete;
    [[nodiscard]] Cursor root() const {
        if (failed_) throw Error("compact history owner failed");
        charge(8);return Cursor(this,generation_,0,0,{});
    }
    [[nodiscard]] std::size_t ordinal(Cursor c) const {
        validate(c);
        charge(24);
        return encoded_ordinal(c);
    }
    [[nodiscard]] DecisionKey decision_key(Cursor c) const {
        const auto& p=validate(c);
        if (p.phase!=betting::Phase::decision) throw Error("compact history cursor is not a decision");
        charge(24);
        return {encoded_ordinal(c),p.source,p.depth,p.actor,p.count};
    }
    // The returned views borrow the immutable occurrence records from History.
    void decision_actions(Cursor c,std::span<std::string_view> out) const {
        const auto& p=validate(c);
        if (p.phase!=betting::Phase::decision || out.size()>p.children.size() || out.size()!=p.count)
            throw Error("compact history decision menu extent");
        charge(16+16*out.size());
        for (std::size_t action=0;action<out.size();++action) {
            const auto index=p.children[action];
            if (index>=path_count_) throw Error("compact history decision child index");
            const auto& child=paths_[index];
            if (child.parent!=c.path_ || child.reveal || !child.incoming_size || child.incoming_size>child.incoming.size())
                throw Error("compact history decision child token");
            out[action]={child.incoming.data(),child.incoming_size};
        }
    }
    [[nodiscard]] std::size_t literal_ordinal(Cursor c) const {validate(c);return c.path_;}
    [[nodiscard]] std::size_t source_node(Cursor c) const {return validate(c).source;}
    [[nodiscard]] std::size_t depth(Cursor c) const {return validate(c).depth;}
    [[nodiscard]] std::size_t visible_size(Cursor c) const {validate(c);return c.size_;}
    [[nodiscard]] std::array<std::uint8_t,5> visible_board(Cursor c) const {validate(c);return c.board_;}
    [[nodiscard]] Cursor append_action(Cursor c,std::size_t edge) {
        try {
            const auto& p=validate(c);charge(32);
            if (edge>=p.children.size() || p.phase!=betting::Phase::decision || edge>=p.count)
                throw Error("compact history invalid action");
            return Cursor(this,generation_,p.children[edge],c.size_,c.board_);
        } catch (...) {failed_=true;throw;}
    }
    [[nodiscard]] Cursor append_reveal(Cursor c,std::span<const std::uint8_t> prefix) {
        try {
            const auto& p=validate(c);charge(64);
            if (p.phase!=betting::Phase::reveal || prefix.size()!=p.next_street)
                throw Error("compact history invalid reveal phase");
            (void)board_code(prefix);
            for (std::size_t i=0;i<c.size_;++i) if (prefix[i]!=c.board_[i]) throw Error("compact history changed past card");
            std::array<std::uint8_t,5> board{};std::copy(prefix.begin(),prefix.end(),board.begin());
            return Cursor(this,generation_,p.children[0],prefix.size(),board);
        } catch (...) {failed_=true;throw;}
    }
    // Export is charged separately; returned strings belong to the enclosing owner.
    [[nodiscard]] std::vector<std::string> materialize(Cursor c) {
        try {
            const auto depth=validate(c).depth;
            charge(128+192*depth);
            const auto scratch=4*depth+4,bytes=128*depth+128;
            if (scratch>limits_.entries-receipt_.entries || bytes>limits_.owned_bytes-receipt_.owned_bytes)
                throw Error("compact history export scratch admission");
            receipt_.peak_scratch_entries=std::max(receipt_.peak_scratch_entries,scratch);
            receipt_.peak_total_bytes=std::max(receipt_.peak_total_bytes,receipt_.owned_bytes+bytes);
            std::vector<std::string> result;result.reserve(depth);
            for (auto at=c.path_;at;at=paths_[at].parent) {
                const auto& p=paths_[at];
                if (!p.reveal) result.emplace_back(p.incoming.data(),p.incoming_size);
                else {
                    constexpr char ranks[]="23456789TJQKA",suits[]="cdhs";
                    std::string token=p.visible==3?"flop@":p.visible==4?"turn@":"river@";
                    const auto first=p.visible==3?0:p.visible-1;
                    for (std::size_t i=first;i<p.visible;++i) {token+=ranks[c.board_[i]/4];token+=suits[c.board_[i]%4];}
                    result.push_back(std::move(token));
                }
            }
            std::reverse(result.begin(),result.end());return result;
        } catch (...) {failed_=true;throw;}
    }
    [[nodiscard]] const Receipt& receipt() const noexcept{return receipt_;}
    [[nodiscard]] bool failed() const noexcept{return failed_;}
};
} // namespace openpoker::virtual_dyadic_history
