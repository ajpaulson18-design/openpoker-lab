#include "exact_public_graph.hpp"
#include <iostream>
#include <vector>
#include <string>
using namespace openpoker::exact_public_graph;
constexpr std::uint64_t money_one_bits=0x3ff0000000000000ULL;
Graph simple() {
  Action a{"check",0,0,false,"check"};
  Graph g; g.vertices.push_back(Vertex::decision(0,{a},{1}));
  g.vertices.push_back(Vertex::terminal(TerminalKind::showdown,2,{money_one_bits,money_one_bits})); return g;
}
void run(const char* name, Graph g, bool reject) {
  try {
    Plan p(std::move(g),{{{48,49},money_one_bits}},{{{44,45},money_one_bits}},{{{0,4,8,12,16}}},10);
    std::cout<<name<<": accepted, group="<<p.group().size()<<", rows="<<p.rows().size()<<"\n";
    if(reject) throw std::runtime_error("unexpected acceptance");
  } catch (const PlanError& e) {
    std::cout<<name<<": rejected: "<<e.what()<<"\n";
    if(!reject) throw;
  }
}
int main() {
  int errors=0;
  {
    const detail::PrefixLess compare;
    const std::vector<std::vector<Card>> ordered{{},{0},{0,4,8},{0,4,8,12},{0,4,8,12,16},{0,4,8,12,17},{0,4,9},{1}};
    for(std::size_t i=0;i<ordered.size();++i) for(std::size_t j=0;j<ordered.size();++j)
      if(compare(ordered[i],ordered[j])!=(i<j)) {++errors;std::cout<<"FAIL prefix lexical order\n";}
    try {(void)compare(std::vector<Card>(6,0),{});++errors;std::cout<<"FAIL oversized prefix comparator\n";}
    catch(const PlanError&) {std::cout<<"bounded prefix comparator: passed\n";}
  }
  auto check=[&](const char* n, Graph g, bool bad) {try {run(n,std::move(g),bad);} catch(const std::exception& e){++errors; std::cout<<"FAIL "<<n<<": "<<e.what()<<"\n";}};
  check("clean",simple(),false);
  // Root regression for Terra's later combined retained+support-scratch finding.
  // 880 admits this kernel's constructor (844 slots), but not its first
  // support query (928 slots). Plan must reject before constructing the kernel.
  try {
    Limits low; low.kernel.max_storage_entries=880;
    Plan p(simple(),{{{48,49},money_one_bits}},{{{44,45},money_one_bits}},{{{0,4,8,12,16}}},10,1,low);
    ++errors; std::cout<<"FAIL low kernel scratch allowance accepted\n";
  } catch(const PlanError& e) {
    if(e.code()!=ErrorCode::storage_limit) {++errors; std::cout<<"FAIL wrong Plan rejection for low kernel scratch\n";}
    else std::cout<<"low kernel scratch: rejected before kernel construction\n";
  } catch(const std::exception& e) {++errors; std::cout<<"FAIL late kernel allocation rejection: "<<e.what()<<"\n";}
  {auto g=simple();g.vertices[1].children.push_back(0);check("terminal inactive cycle",std::move(g),true);}
  {auto g=simple();g.vertices[0].branches.push_back({"2c3c4c",0});check("decision inactive branch",std::move(g),true);}
  {auto g=simple();g.vertices[0].children[0]=0;check("active cycle",std::move(g),true);}
  {auto g=simple();g.vertices.push_back(Vertex::terminal(TerminalKind::showdown,2,{money_one_bits,money_one_bits}));check("unreachable vertex",std::move(g),true);}
  {Graph g;g.vertices.push_back(Vertex::chance(Street::flop,9,{{"2c3c4c",1}}));g.vertices.push_back(Vertex::terminal(TerminalKind::showdown,2,{money_one_bits,money_one_bits}));check("flop wrong card index",std::move(g),true);}
  {auto g=simple();g.initial_history={"turn@5c"};check("turn before flop",std::move(g),true);}
  try {
    Graph g; g.initial_history={"flop@2c3c4c","turn@5c"};
    g.vertices.push_back(Vertex::chance(Street::river,6,{{"6c",1}}));
    g.vertices.push_back(Vertex::terminal(TerminalKind::showdown,2,{money_one_bits,money_one_bits}));
    Plan p(std::move(g),{{{48,49},money_one_bits}},{{{44,45},money_one_bits}},
      {{{0,4,8,12,16}},{{0,4,8,12,21}}},10);
    const auto indexes=p.prefix_board_indexes(History{"flop@2c3c4c","turn@5c"});
    std::cout<<"incomplete chance: ACCEPTED matching_boards="<<indexes.size()<<" branches=1\n";
    ++errors;
  } catch(const PlanError& e) {std::cout<<"incomplete chance: rejected: "<<e.what()<<"\n";}
  try {
    Graph g; g.initial_history={"flop@2c3c4c","turn@5c"};
    g.vertices.push_back(Vertex::chance(Street::river,6,{{"6c",1}}));
    g.vertices.push_back(Vertex::terminal(TerminalKind::showdown,2,{money_one_bits,money_one_bits}));
    Plan p(std::move(g),{{{48,49},money_one_bits}},{{{44,45},money_one_bits}},
      {{{0,4,8,12,16}},{{0,4,8,12,48}}},10);
    std::cout<<"zero-mass outcome omitted: accepted\n";
  } catch(const std::exception& e) {++errors;std::cout<<"FAIL zero-mass omitted: "<<e.what()<<"\n";}
  try {
    Plan p(simple(),{{{50,51},money_one_bits},{{51,49},money_one_bits}},{{{46,47},money_one_bits}},{{{0,4,8,12,16}}},10);
    std::cout<<"weighted unequal-shape group="<<p.group().size()<<"\n";
  } catch(const std::exception& e) {++errors;std::cout<<"FAIL asymmetric group fixture: "<<e.what()<<"\n";}
  try {
    Plan p(simple(),{{{50,48},money_one_bits},{{51,48},money_one_bits}},
      {{{46,44},money_one_bits},{{47,44},money_one_bits}},{{{0,4,8,12,16}}},10);
    if(p.group().size()!=2 || p.rows().size()!=1 || p.rows()[0].orbit_size!=2 || p.rows()[0].expected_mask!=3)
      throw std::runtime_error("unexpected weighted group or quotient orbit");
    const auto a=p.locate(RowKey{0,0,{}}), b=p.locate(RowKey{0,1,{}});
    if(a.q!=b.q || a.member_bit==b.member_bit || (a.member_bit|b.member_bit)!=3)
      throw std::runtime_error("member masks fail to partition orbit");
    std::cout<<"weighted group/orbit: two members, mask 3\n";
    try { (void)p.locate(RowKey{1,0,{}}); throw std::runtime_error("wrong actor accepted"); }
    catch(const PlanError&) {std::cout<<"wrong actor: rejected\n";}
    try { std::vector<Action> menu{}; (void)p.locate_decision_rows(0,History{},menu); throw std::runtime_error("empty menu accepted"); }
    catch(const PlanError&) {std::cout<<"wrong menu: rejected\n";}
    try { (void)p.locate(RowKey{0,0,{"flop@2c3c4c"}}); throw std::runtime_error("bad history accepted"); }
    catch(const PlanError&) {std::cout<<"bad history: rejected\n";}
  } catch(const std::exception& e) {++errors;std::cout<<"FAIL weighted group/orbit queries: "<<e.what()<<"\n";}
  std::cout<<"failures="<<errors<<"\n";return errors?1:0;
}



