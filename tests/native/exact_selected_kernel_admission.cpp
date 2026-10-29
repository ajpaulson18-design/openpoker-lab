#include "exact_selected_kernel.hpp"
#include <iostream>
#include <vector>
#include <limits>
#include <array>
#include <bit>
using namespace openpoker::exact_selected_kernel;
void need(bool v, const char* text) {if(!v) throw std::runtime_error(text);}
ExactSelectedKernel* make(Limits l) {
  return new ExactSelectedKernel({{{0,1}, 0x3ff0000000000000ULL}}, {{{2,3}, 0x3ff0000000000000ULL}}, {{{4,5,6,7,8}}}, 1, l);
}
void rejection(Limits l, double reach, ErrorCode expected) {
  auto* p = make(l); std::array<std::size_t,1> board{0}; std::array<double,1> values{reach};
  try { (void)p->terminal(0, board, TerminalKind::showdown, 1.0, values); delete p; throw std::runtime_error("expected rejection"); }
  catch(const KernelError& e) { need(e.code()==expected,"unexpected error code"); need(p->receipt().rank_calls==0,"rank before rejection"); need(p->rank_cache_size()==0,"rank cache before rejection"); delete p; }
}
int main(){try {
  Limits a; a.max_modeled_work=1300; rejection(a,1.0,ErrorCode::modeled_work_limit);
  Limits b; b.max_integer_bits=200; rejection(b,std::numeric_limits<double>::denorm_min(),ErrorCode::integer_bit_limit);
  Limits c; c.max_integer_payload_bits=20000; rejection(c,1.0,ErrorCode::integer_payload_limit);
  Limits d; rejection(d,std::numeric_limits<double>::quiet_NaN(),ErrorCode::invalid_dyadic);
  Limits e; rejection(e,-0.25,ErrorCode::invalid_dyadic);
  std::cout << "5 direct API rejection checks passed; rank_calls and rank_cache_size remained zero\n"; return 0;
} catch(const std::exception& e) {std::cerr << e.what() << "\n";return 1;}}
