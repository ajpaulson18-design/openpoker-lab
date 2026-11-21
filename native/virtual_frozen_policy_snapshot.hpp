#pragma once
// Versioned immutable Q52 input and bounded output. History/State own identity.
#include "virtual_dyadic_training.hpp"
#include <fstream>
#include <iostream>
#include <string>

namespace openpoker::virtual_frozen_policy_snapshot {
namespace t=virtual_dyadic_training;
namespace h=virtual_dyadic_history;
namespace b=virtual_betting_template;
namespace s=virtual_dyadic_state;
inline constexpr auto Q=dyadic_policy::grid_units;
inline void require(bool value,const char* message) {if (!value) throw std::runtime_error(message);}
struct Header {std::uint64_t rows=0,slots=0,tokens=0,history_bytes=0,action_bytes=0,q=0;};
constexpr std::uint64_t input_cap=8*1024*1024,output_cap=2100000;
class Input {
    std::ifstream file_;
    std::uint64_t size_,used_=0;
public:
    explicit Input(const std::filesystem::path& path):size_(std::filesystem::file_size(path)) {
        require(path.native().size()<=1024 && std::filesystem::is_regular_file(path) && size_<=input_cap,"snapshot input boundary");
        file_.open(path,std::ios::binary);require(bool(file_),"snapshot input open");
    }
    void bytes(void* out,std::size_t n) {
        require(n<=size_-used_,"truncated snapshot input");
        file_.read(static_cast<char*>(out),static_cast<std::streamsize>(n));
        require(bool(file_),"snapshot input read");used_+=n;
    }
    std::uint64_t word() {std::uint64_t v;bytes(&v,8);return v;}
    std::string token() {
        std::uint8_t n;bytes(&n,1);require(n && n<=64,"snapshot token bound");
        std::string result(n,'\0');bytes(result.data(),n);return result;
    }
    std::uint64_t size() const {return size_;}
    std::uint64_t used() const {return used_;}
};
class Output {
    std::uint64_t written_=0;
public:
    void bytes(const void* data,std::size_t n) {
        require(n<=output_cap-written_,"snapshot output boundary");
        std::cout.write(static_cast<const char*>(data),static_cast<std::streamsize>(n));
        require(bool(std::cout),"snapshot output write");written_+=n;
    }
    void word(std::uint64_t value) {bytes(&value,8);}
    std::uint64_t written() const {return written_;}
};
inline std::uint8_t card(std::string_view text) {
    constexpr std::string_view ranks="23456789TJQKA",suits="cdhs";
    require(text.size()==2,"snapshot card token");
    const auto rank=ranks.find(text[0]),suit=suits.find(text[1]);
    require(rank<13 && suit<4,"snapshot card grammar");
    return static_cast<std::uint8_t>(4*rank+suit);
}
inline h::History::Cursor reconstruct(h::History& history,const b::Template& source,
                              std::span<const std::string> tokens) {
    auto cursor=history.root();auto node_id=source.root();std::array<std::uint8_t,5> board{};std::size_t visible=0;
    for (const auto& token:tokens) {
        const auto& node=source.nodes().at(node_id);
        if (node.state.phase==b::Phase::decision) {
            std::size_t edge=0;
            while (edge<node.edges.size() && node.edges[edge].action.token!=token) ++edge;
            require(edge<node.edges.size(),"snapshot history action");
            cursor=history.append_action(cursor,edge);node_id=node.edges[edge].child;
        } else {
            require(node.state.phase==b::Phase::reveal && node.edges.size()==1,"snapshot history phase");
            const auto next=node.state.next_street;
            if (next==3) {
                require(!visible && token.size()==11 && token.starts_with("flop@"),"snapshot flop token");
                for (std::size_t i=0;i<3;++i) board[i]=card(std::string_view(token).substr(5+2*i,2));
            } else {
                require(visible+1==next && (next==4 || next==5),"snapshot ordered reveal");
                const std::string_view label=next==4?"turn@":"river@";
                require(token.size()==label.size()+2 && token.starts_with(label),"snapshot reveal token");
                board[visible]=card(std::string_view(token).substr(label.size(),2));
            }
            visible=next;cursor=history.append_reveal(cursor,std::span(board).first(visible));node_id=node.edges[0].child;
        }
    }
    require(source.nodes().at(node_id).state.phase==b::Phase::decision,"snapshot row must be a decision");
    return cursor;
}

inline Header read_header(Input& input) {
    std::array<char,8> magic{};input.bytes(magic.data(),magic.size());
    require(std::string_view(magic.data(),magic.size())=="OPLFGS01","snapshot input version");
    const Header header{input.word(),input.word(),input.word(),input.word(),input.word(),input.word()};
    require(header.rows==24420 && header.slots==58164 && header.tokens==249662 &&
        header.history_bytes==1500675 && header.action_bytes==294353 && header.q==Q,"snapshot fixed complete census");
    const auto expected=56+40*header.rows+header.tokens+header.history_bytes+header.slots+header.action_bytes+8*header.slots;
    require(input.size()==expected,"snapshot complete byte count");
    return header;
}

inline void import_rows(Input& input,const Header& header,h::History& history,const b::Template& source,s::State& state) {
    std::uint64_t tokens=0,history_bytes=0,actions=0,action_bytes=0;
    for (std::size_t row=0;row<header.rows;++row) {
        const auto actor=input.word(),first=input.word(),second=input.word(),n=input.word(),m=input.word();
        require(actor<2 && first<second && second<52 && n<=15 && m>=2 && m<=20 &&
            n<=header.tokens-tokens && m<=header.slots-actions,"snapshot row header");
        std::size_t holding=0;
        while (holding<2 && (t::ranges[actor][holding].hand.first!=first || t::ranges[actor][holding].hand.second!=second)) ++holding;
        require(holding<2,"snapshot original holding identity");
        std::array<std::string,15> history_tokens{};
        std::array<std::string,20> action_tokens{};std::array<std::string_view,20> action_views{};
        std::array<std::uint64_t,20> units{};
        for (std::size_t i=0;i<n;++i) {
            history_tokens[i]=input.token();require(history_tokens[i].size()<=header.history_bytes-history_bytes,"snapshot history text count");
            history_bytes+=history_tokens[i].size();
        }
        for (std::size_t i=0;i<m;++i) {
            action_tokens[i]=input.token();require(action_tokens[i].size()<=header.action_bytes-action_bytes,"snapshot action text count");
            action_bytes+=action_tokens[i].size();action_views[i]=action_tokens[i];
        }
        for (std::size_t i=0;i<m;++i) units[i]=input.word();
        const auto cursor=reconstruct(history,source,std::span(history_tokens).first(static_cast<std::size_t>(n)));
        state.import_frozen_policy_row(row,cursor,actor,holding,std::span(action_views).first(static_cast<std::size_t>(m)),
            std::span(units).first(static_cast<std::size_t>(m)));
        tokens+=n;actions+=m;
    }
    require(tokens==header.tokens && actions==header.slots && history_bytes==header.history_bytes &&
        action_bytes==header.action_bytes && input.used()==input.size(),"snapshot final input census");
    state.seal_frozen_policy();
}
} // namespace openpoker::virtual_frozen_policy_snapshot
