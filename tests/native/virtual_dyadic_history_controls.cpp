#include "../../native/virtual_dyadic_history.hpp"
#include <algorithm>
#include <functional>
#include <vector>
#include <iostream>
#include <string_view>
#include <type_traits>

namespace h=openpoker::virtual_dyadic_history;
namespace c=openpoker::full_deck_public_chance;
namespace b=openpoker::virtual_betting_template;
static_assert(!std::is_copy_constructible_v<h::History> && !std::is_copy_assignable_v<h::History>);
static_assert(!std::is_move_constructible_v<h::History> && !std::is_move_assignable_v<h::History>);
namespace {
constexpr std::array<std::uint8_t,9> deck{16,17,24,32,33,35,37,43,48};
constexpr std::array<std::array<std::uint8_t,5>,5> boards{{
    {16,17,24,32,33},{16,17,24,32,35},{16,17,24,33,32},
    {16,17,24,48,43},{17,24,32,33,35}}};
b::Config configuration() {
    b::Config x;x.stacks={8.,8.};x.sb=.5;x.bb=1.;
    x.stages[0]={{.5},{1.},1,true};
    for (std::size_t i=1;i<4;++i) x.stages[i]={{.5,1.},{.25},1,true};
    return x;
}
template<class F> void rejected(std::string_view label,F&& attempt) {
    try {attempt();} catch(const h::Error&) {std::cout<<"REJECT "<<label<<'\n';return;}
    throw std::runtime_error("expected compact history rejection");
}
}
int main() {
    try {
        const b::Template source(configuration());const auto physical=c::DeckDefinition::reduced(deck);
        h::History history(source,physical);
        std::cout<<"COMPACT_HISTORY_V1 "<<history.receipt().nodes<<' '<<source.nodes().size()<<'\n';
        for (std::size_t variant=0;variant<boards.size();++variant) {
            const auto& board=boards[variant];
            std::function<void(h::History::Cursor)> walk=[&](auto cursor) {
                const auto key=history.ordinal(cursor),literal=history.literal_ordinal(cursor);
                const auto visible=history.visible_size(cursor),id=history.source_node(cursor);
                const auto& node=source.nodes().at(id);const auto tokens=history.materialize(cursor);
                std::cout<<"ROW "<<variant<<' '<<key<<' '<<literal<<' '<<id<<' '<<visible<<' '
                    <<static_cast<unsigned>(node.state.phase)<<' '<<tokens.size();
                for (const auto& token:tokens) std::cout<<' '<<token;
                std::cout<<'\n';
                if (node.state.phase==b::Phase::reveal) {
                    walk(history.append_reveal(cursor,{board.data(),node.state.next_street}));
                } else {
                    for (std::size_t j=0;j<node.edges.size();++j) walk(history.append_action(cursor,j));
                }
            };
            walk(history.root());
        }
        const auto& rec=history.receipt();
        std::cout<<"RECEIPT "<<rec.work<<' '<<rec.nodes<<' '<<rec.entries<<' '<<rec.owned_bytes
            <<' '<<rec.max_depth<<' '<<rec.peak_scratch_entries<<' '<<rec.peak_total_bytes<<'\n';
        // A separate owner preserves the original output and receipt. Build
        // the expected byte path from raw action indices and board cards;
        // never derive it from History's encoded ordinal or occurrence data.
        {
            h::History ordered(source,physical);
            h::History::DecisionPath previous{};
            bool have_previous=false;
            std::size_t checked=0;
            std::function<void(h::History::Cursor,std::vector<std::uint8_t>,std::vector<std::size_t>)> check;
            check=[&](auto cursor,auto expected,auto selected) {
                const auto id=ordered.source_node(cursor);
                const auto& node=source.nodes().at(id);
                if (node.state.phase==b::Phase::decision) {
                    h::History::DecisionPath actual{};
                    actual.fill(255); // verifies zero padding is written
                    const auto plain=ordered.decision_key(cursor);
                    const auto keyed=ordered.decision_key(cursor,&actual);
                    if (plain.ordinal!=keyed.ordinal || plain.source!=keyed.source ||
                        plain.depth!=keyed.depth || plain.actor!=keyed.actor || plain.actions!=keyed.actions ||
                        expected.size()>actual.size() ||
                        !std::equal(expected.begin(),expected.end(),actual.begin()) ||
                        !std::all_of(actual.begin()+expected.size(),actual.end(),[](auto v){return v==0;}))
                        throw std::runtime_error("independent decision path mismatch");
                    if (have_previous && !(previous<actual))
                        throw std::runtime_error("decision paths are not strictly canonical");
                    previous=actual;have_previous=true;++checked;
                    for (std::size_t j=0;j<node.edges.size();++j) {
                        auto next=expected;next.push_back(static_cast<std::uint8_t>(1+j));
                        check(ordered.append_action(cursor,j),std::move(next),selected);
                    }
                } else if (node.state.phase==b::Phase::reveal) {
                    const auto prior=ordered.visible_size(cursor);
                    const auto next=static_cast<std::size_t>(node.state.next_street);
                    std::sort(selected.begin(),selected.end(),[&](auto a,auto b){
                        return std::lexicographical_compare(boards[a].begin(),boards[a].begin()+next,
                                                            boards[b].begin(),boards[b].begin()+next);
                    });
                    for (std::size_t i=0;i<selected.size();) {
                        const auto chosen=selected[i];std::size_t end=i+1;
                        while (end<selected.size() &&
                               std::equal(boards[chosen].begin(),boards[chosen].begin()+next,boards[selected[end]].begin())) ++end;
                        auto path=expected;
                        for (auto k=prior;k<next;++k) path.push_back(static_cast<std::uint8_t>(1+boards[chosen][k]));
                        check(ordered.append_reveal(cursor,{boards[chosen].data(),next}),std::move(path),
                              std::vector<std::size_t>(selected.begin()+i,selected.begin()+end));
                        i=end;
                    }
                }
            };
            check(ordered.root(),{}, {0,1,2,3,4});
            if (checked<1000) throw std::runtime_error("decision path coverage incomplete");
        }
        rejected("raised_work",[&]{h::Limits l;l.work=500000001;h::History x(source,physical,l);});
        rejected("literal_nodes",[&]{h::Limits l;l.nodes=1;h::History x(source,physical,l);});
        rejected("literal_entries",[&]{h::Limits l;l.entries=32;h::History x(source,physical,l);});
        rejected("literal_bytes",[&]{h::Limits l;l.owned_bytes=512;h::History x(source,physical,l);});
        rejected("source_depth",[&]{h::Limits l;l.depth=1;h::History x(source,physical,l);});
        rejected("construction_work",[&]{h::Limits l;l.work=2048;h::History x(source,physical,l);});
        rejected("default_cursor",[&]{(void)history.ordinal({});});
        rejected("foreign_cursor",[&]{h::History other(source,physical);(void)other.ordinal(history.root());});
        h::History malformed(source,physical);
        rejected("action_menu",[&]{(void)malformed.append_action(malformed.root(),20);});
        rejected("poisoned_root",[&]{(void)malformed.root();});
        rejected("reveal_phase",[&]{h::History other(source,physical);(void)other.append_reveal(other.root(),boards[0]);});
        rejected("export_scratch",[&]{h::Limits l;l.owned_bytes=rec.owned_bytes;h::History other(source,physical,l);(void)other.materialize(other.root());});
        const auto first_reveal=[&](h::History& owner) {
            std::function<h::History::Cursor(h::History::Cursor)> seek=[&](auto cursor)->h::History::Cursor {
                const auto& node=source.nodes()[owner.source_node(cursor)];
                if (node.state.phase==b::Phase::reveal) return cursor;
                if (node.state.phase!=b::Phase::decision) return {};
                for (std::size_t j=0;j<node.edges.size();++j) {
                    auto child=owner.append_action(cursor,j);
                    const auto& child_node=source.nodes()[owner.source_node(child)];
                    if (child_node.state.phase==b::Phase::reveal) return child;
                    // Search only nonterminal children. The fixed first viable
                    // branch reaches flop before any later-street reveal.
                    if (child_node.state.phase==b::Phase::decision) return seek(child);
                }
                throw std::runtime_error("no fixture reveal found");
            };
            return seek(owner.root());
        };
        rejected("noncanonical_flop",[&]{h::History other(source,physical);const std::array<std::uint8_t,3> cards{17,16,24};(void)other.append_reveal(first_reveal(other),cards);});
        rejected("foreign_flop",[&]{h::History other(source,physical);const std::array<std::uint8_t,3> cards{0,17,24};(void)other.append_reveal(first_reveal(other),cards);});
        std::cout<<"END\n";return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 2;}
}
