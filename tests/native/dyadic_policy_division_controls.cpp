#include "../../native/dyadic_policy_division.hpp"
#include <iostream>
#include <random>
#include <stdexcept>
using namespace openpoker::dyadic_policy_division;
int main() {
    std::mt19937_64 rng(123456789);
    auto check=[](const Integer& w,const Integer& s,bool emit) {
        auto r=divide_grid(w,s); Integer x=w<<52;
        if (Integer(r.quotient)!=x/s || r.remainder!=x%s) throw std::runtime_error("division mismatch");
        if (emit) std::cout<<"vector\t"<<w<<'\t'<<s<<'\t'<<r.quotient<<'\t'<<r.remainder<<'\n';
    };
    for (unsigned i=0;i<10000;++i) {
        unsigned bits=1+((i*137)%704); Integer s=1;
        for(unsigned j=0;j<bits;j+=64) { s<<=64; s+=rng(); }
        s &= (Integer(1)<<bits)-1; s |= Integer(1)<<(bits-1);
        Integer w=0;
        for(unsigned j=0;j<bits;j+=64) { w<<=64; w+=rng(); }
        w%=s+1;
        if (i%16==0) w=0; else if(i%16==1) w=s; else if(i%16==2) w=s-1;
        check(w,s,i<96);
    }
    // Constructed cases exercise multi-correction and add-back under Q52.
    Trace correction, addback;
    auto c=divide_grid(Integer("8796093018112"),Integer("9223372041149743103"),&correction);
    auto a=divide_grid(Integer("17592186044416"),Integer("79228162514264337593543950337"),&addback);
    if (c.quotient!=4294967292ULL || c.remainder!=Integer("21474836476") ||
        a.quotient!=0 || a.remainder!=Integer("79228162514264337593543950336"))
        throw std::runtime_error("crafted quotient or remainder differs");
    if (correction.max_digit_corrections<2 || addback.addbacks==0) throw std::runtime_error("division branch coverage");
    for (unsigned bits : {31u,32u,33u,63u,64u,65u,703u,704u}) {
        Integer s=(Integer(1)<<(bits-1)) + 1;
        check(s/2,s,false);
    }
    Trace norm0, norm31;
    (void)divide_grid(Integer(1),Integer(1)<<31,&norm0);
    (void)divide_grid(Integer(1),(Integer(1)<<32)+1,&norm31);
    if (norm0.normalization!=0 || norm31.normalization!=31) throw std::runtime_error("normalization coverage");
    unsigned failures=0;
    for (auto pair : {std::pair<Integer,Integer>{-1,1},{0,0},{2,1},{0,-1},{0,Integer(1)<<704},{Integer(1)<<704,Integer(1)<<704}}) {
        try { (void)divide_grid(pair.first,pair.second); } catch (const std::invalid_argument&) { ++failures; }
    }
    if(failures!=6) throw std::runtime_error("guard failure");
    std::cout<<"grid division controls passed\n";
}




