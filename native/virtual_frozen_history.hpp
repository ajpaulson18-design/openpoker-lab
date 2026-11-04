#pragma once
// Exact visible-history ownership for the experimental frozen update.
// Cursor use requires its arena to remain alive; owner generations do not recycle.
#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <map>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace openpoker::virtual_frozen_update {
struct HistoryLimits {
    std::size_t nodes=250000, entries=2000000, owned_bytes=32*1024*1024, depth=64;
    std::uint64_t work=500000000;
};
struct HistoryReceipt {
    std::size_t nodes=0,entries=0,owned_bytes=0,max_depth=0,peak_scratch_entries=0,peak_total_bytes=0;
    std::uint64_t work=0;
};
class HistoryError final:public std::runtime_error {public:explicit HistoryError(const char* s):std::runtime_error(s){}};
class HistoryArena final {
    struct Node {std::size_t parent=0,depth=0;std::string token;std::array<std::uint8_t,5> board{};std::size_t board_size=0;};
    struct Less {
        using is_transparent=void;
        template<class A,class B> bool operator()(const std::pair<std::size_t,A>& a,const std::pair<std::size_t,B>& b)const{
            return a.first!=b.first ? a.first<b.first : std::string_view(a.second)<std::string_view(b.second);
        }
    };
    static std::uint64_t allocate_generation(){
        auto value=next_generation_.load(std::memory_order_relaxed);
        for(std::size_t attempt=0;attempt<64;++attempt){if(value==std::numeric_limits<std::uint64_t>::max())throw HistoryError("history owner generation exhausted");
            if(next_generation_.compare_exchange_weak(value,value+1,std::memory_order_relaxed))return value;}
        throw HistoryError("history owner generation contention limit exceeded");
    }
public:
    class Cursor final {
        friend class HistoryArena;
        const HistoryArena* owner_=nullptr;std::size_t index_=0;std::uint64_t generation_=0;
        Cursor(const HistoryArena* owner,std::size_t index,std::uint64_t generation):owner_(owner),index_(index),generation_(generation){}
    public: Cursor()=default;
    };
    explicit HistoryArena(HistoryLimits limits={}):limits_(limits),generation_(0){
        if(!limits.nodes||limits.nodes>250000||limits.entries<192||limits.entries>2000000||!limits.owned_bytes||limits.owned_bytes>32*1024*1024||
           !limits.depth||limits.depth>64||!limits.work||limits.work>500000000)
            throw HistoryError("invalid reduce-only history limits");
        charge(4096); generation_=allocate_generation();
        nodes_.push_back(Node{});receipt_.nodes=1;receipt_.entries=192;
    }
    HistoryArena(const HistoryArena&)=delete;HistoryArena& operator=(const HistoryArena&)=delete;
    HistoryArena(HistoryArena&&)=delete;HistoryArena& operator=(HistoryArena&&)=delete;
    [[nodiscard]] Cursor root()const noexcept{return Cursor(this,0,generation_);}
    // Action token text comes from a separately validated ordered template menu.
    [[nodiscard]] Cursor append_action(Cursor parent,std::string_view token){
        validate(parent);
        if(token.empty()||token.size()>64)throw HistoryError("invalid action token length");
        charge(128+8*token.size());
        for(unsigned char c:token)if(c<0x20||c>0x7e)throw HistoryError("action token must be printable ASCII");
        bool plain=token=="fold"||token=="call"||token=="check";
        const auto at=token.find('@');
        if(!plain){
            if(at==std::string_view::npos || (token.substr(0,at)!="bet"&&token.substr(0,at)!="raise"&&token.substr(0,at)!="all_in"))
                throw HistoryError("invalid action token");
            const auto amount=token.substr(at+1);if(amount.empty())throw HistoryError("invalid action amount token");
            bool dot=false;std::size_t dot_at=0;
            for(std::size_t i=0;i<amount.size();++i){const char c=amount[i];if(c=='.'&&!dot){dot=true;dot_at=i;}
                else if(c<'0'||c>'9')throw HistoryError("invalid action amount token");}
            if((amount.size()>1&&amount[0]=='0'&&amount[1]!='.')||(dot&&(dot_at==0||dot_at+1==amount.size()||amount.size()-dot_at-1>9||amount.back()=='0')))
                throw HistoryError("noncanonical action amount token");
        }
        return append_token(parent,token,nodes_[parent.index_].board,nodes_[parent.index_].board_size);
    }
    // Cards are the complete newly visible prefix, not a sampled hidden suffix.
    [[nodiscard]] Cursor append_reveal(Cursor parent,std::span<const std::uint8_t> prefix){
        validate(parent);charge(128);
        const auto& old=nodes_[parent.index_];const auto n=prefix.size();
        if(!((old.board_size==0&&n==3)||(old.board_size==3&&n==4)||(old.board_size==4&&n==5)))
            throw HistoryError("invalid reveal sequence");
        std::uint64_t seen=0;for(std::size_t i=0;i<n;++i){const auto c=prefix[i];
            if(c>=52||(seen&(std::uint64_t{1}<<c))||(i<old.board_size&&old.board[i]!=c))throw HistoryError("duplicate or changed visible card");seen|=std::uint64_t{1}<<c;}
        if(!(prefix[0]<prefix[1]&&prefix[1]<prefix[2]))throw HistoryError("noncanonical visible flop");
        constexpr std::string_view ranks="23456789TJQKA", suits="cdhs";
        std::array<char,11> text{};std::size_t length=0;
        const auto label=n==3?std::string_view("flop@"):n==4?std::string_view("turn@"):std::string_view("river@");
        for(char c:label)text[length++]=c;
        const auto first=n==3?0:n-1;
        for(std::size_t i=first;i<n;++i){text[length++]=ranks[prefix[i]/4];text[length++]=suits[prefix[i]%4];}
        std::array<std::uint8_t,5> board{};std::copy(prefix.begin(),prefix.end(),board.begin());
        return append_token(parent,std::string_view(text.data(),length),board,n);
    }
    // The enclosing update must separately admit retained returned strings.
    [[nodiscard]] std::vector<std::string> materialize(Cursor cursor){
        validate(cursor);const auto n=nodes_[cursor.index_].depth;charge(256+256*n);reserve_scratch(4*n+4,64*n);
        std::vector<std::string> out;out.reserve(n);
        for(auto id=cursor.index_;id;id=nodes_[id].parent)out.push_back(nodes_[id].token);
        std::reverse(out.begin(),out.end());return out;
    }
    [[nodiscard]] std::size_t depth(Cursor cursor)const{validate(cursor);return nodes_[cursor.index_].depth;}
    // Unique only within this live owner; detached keys still materialize every token.
    [[nodiscard]] std::size_t ordinal(Cursor cursor)const{validate(cursor);return cursor.index_;}
    [[nodiscard]] std::array<std::uint8_t,5> visible_board(Cursor cursor)const{validate(cursor);return nodes_[cursor.index_].board;}
    [[nodiscard]] std::size_t visible_size(Cursor cursor)const{validate(cursor);return nodes_[cursor.index_].board_size;}
    [[nodiscard]] std::uint64_t selector_hash(Cursor cursor,std::uint8_t actor,std::uint8_t first,std::uint8_t second,std::uint8_t actions){
        validate(cursor);const auto n=nodes_[cursor.index_].depth;charge(512+256*n);
        if(actor>1||first>=second||second>=52||!actions||actions>20)throw HistoryError("invalid policy selector inputs");
        std::uint64_t h=14695981039346656037ULL;
        auto byte=[&](unsigned char b){h^=b;h*=1099511628211ULL;};
        constexpr std::string_view domain="OPL-FROZEN-POLICY-V1";
        for(unsigned char c:domain)byte(c);byte(0);byte(actor);byte(first);byte(second);
        byte(static_cast<unsigned char>(n&255U));byte(static_cast<unsigned char>((n>>8)&255U));
        std::size_t ids[64]{};auto id=cursor.index_;
        for(std::size_t at=n;at>0;--at){ids[at-1]=id;id=nodes_[id].parent;}
        for(std::size_t i=0;i<n;++i){const auto& token=nodes_[ids[i]].token;byte(static_cast<unsigned char>(token.size()&255U));byte(static_cast<unsigned char>((token.size()>>8)&255U));for(unsigned char c:token)byte(c);}
        byte(actions);return h;
    }
    [[nodiscard]]const HistoryReceipt& receipt()const noexcept{return receipt_;}
private:
    [[nodiscard]] Cursor append_token(Cursor parent,std::string_view token,const std::array<std::uint8_t,5>& board,std::size_t board_size){
        const auto depth=nodes_[parent.index_].depth+1;
        if(depth>limits_.depth)throw HistoryError("history depth limit exceeded");
        charge((512ULL+256ULL*token.size())*(1+std::bit_width(nodes_.size()+1)));
        // Heterogeneous lookup needs no temporary string allocation, including hits.
        reserve_scratch(8,0);
        const auto lookup=std::pair<std::size_t,std::string_view>{parent.index_,token};
        auto found=index_.find(lookup);
        if(found!=index_.end())return Cursor(this,found->second,generation_);
        if(nodes_.size()>=limits_.nodes)throw HistoryError("history node limit exceeded");
        if(64>limits_.entries-receipt_.entries)throw HistoryError("history entry limit exceeded");
        if(2*token.size()>limits_.owned_bytes-receipt_.owned_bytes)throw HistoryError("history byte limit exceeded");
        const auto id=nodes_.size();
        auto inserted=index_.emplace(std::pair<std::size_t,std::string>{parent.index_,std::string(token)},id);
        try{nodes_.push_back(Node{parent.index_,depth,std::string(token),board,board_size});}
        catch(...){index_.erase(inserted.first);throw;}
        receipt_.nodes=nodes_.size();receipt_.entries+=64;receipt_.owned_bytes+=2*token.size();
        receipt_.max_depth=std::max(receipt_.max_depth,depth);
        receipt_.peak_total_bytes=std::max(receipt_.peak_total_bytes,receipt_.owned_bytes);
        return Cursor(this,id,generation_);
    }
    void charge(std::uint64_t n){if(n>limits_.work-receipt_.work)throw HistoryError("history work limit exceeded");receipt_.work+=n;}
    void reserve_scratch(std::size_t entries,std::size_t bytes){
        if(entries>limits_.entries-receipt_.entries)throw HistoryError("history scratch entry limit exceeded");
        if(bytes>limits_.owned_bytes-receipt_.owned_bytes)throw HistoryError("history scratch byte limit exceeded");
        receipt_.peak_scratch_entries=std::max(receipt_.peak_scratch_entries,entries);
        receipt_.peak_total_bytes=std::max(receipt_.peak_total_bytes,receipt_.owned_bytes+bytes);
    }
    void validate(Cursor c)const{if(c.owner_!=this||c.generation_!=generation_||c.index_>=nodes_.size())throw HistoryError("foreign or stale history cursor");}
    inline static std::atomic<std::uint64_t> next_generation_{1};
    HistoryLimits limits_;HistoryReceipt receipt_{};std::uint64_t generation_;
    std::vector<Node> nodes_;std::map<std::pair<std::size_t,std::string>,std::size_t,Less> index_;
};
} // namespace openpoker::virtual_frozen_update
