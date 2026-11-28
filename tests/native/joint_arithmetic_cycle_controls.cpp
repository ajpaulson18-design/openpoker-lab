#ifdef OPENPOKER_JOINT_ARITHMETIC_LIGHT_CYCLES
#include "../../native/joint_arithmetic_light_recorder.hpp"
#include <thread>
namespace a=openpoker::joint_arithmetic_light_cycles;
template<class C>using Observation=a::Scope<C>;
#else
#include "../../native/joint_arithmetic_cycle_recorder.hpp"
namespace a=openpoker::joint_arithmetic_cycles;
template<class C>using Observation=a::Scope;
#endif
#include <iostream>
struct Clock {
    static constexpr std::string_view units="synthetic_cycles";
    static inline std::uint64_t now=0,owner=9;
    static inline bool failure=false,backward=false;
    static std::uint64_t thread_id(){return owner;}
    static std::uint64_t read(){
        if(failure)throw std::runtime_error("injected failure");
        if(backward)return 0;
        return now+=1000;
    }
    static void reset(){now=0;owner=9;failure=false;backward=false;}
};
using R=a::Recorder<Clock>;
template<class F>void reject(std::string_view label,F&& action){
    bool caught=false;try{action();}catch(const std::exception&){caught=true;}
    if(!caught)throw std::runtime_error("guard did not reject");
    std::cout<<"GUARD "<<label<<" PASS\n";
}
int main(){try{
    constexpr std::array<std::uint64_t,4> bodies{3000,5000,7000,11000};
    for(unsigned offset=0;offset<32;++offset){
        Clock::reset();R r(offset,false);a::Install install(r);
        for(const auto& phase:a::base::phases){
            if(phase.name=="walk")for(unsigned family=0;family<4;++family)
                for(std::uint64_t call=0;call<a::epoch_calls[family];++call){
                    Observation<Clock> scope(static_cast<a::Family>(family));Clock::now+=bodies[family];scope.close();
                }
            r.mark(phase.name,phase.epoch);
        }
        r.write(std::cout);
    }
    Clock::reset();reject("offset",[]{R r(32,false);});reject("lazy",[]{R r(0,true);});
    reject("missing-observer",[]{Observation<Clock> scope(a::Family::reach);});
    {R r(0,false);a::Install install(r);
        reject("nested-install",[&]{a::Install nested(r);});
        reject("wrong-phase",[&]{r.mark("walk",1);});
        reject("read-context",[]{Observation<Clock> scope(a::Family::reach);});
        reject("incomplete",[&]{r.write(std::cout);});
        Clock::owner=10;reject("foreign-thread",[&]{r.mark("begin",0);});Clock::owner=9;
        Clock::failure=true;reject("clock-failure",[&]{r.mark("begin",0);});Clock::failure=false;
        Clock::backward=true;reject("nonmonotone",[&]{r.mark("begin",0);});Clock::backward=false;
    }
    {R r(0,false);a::Install install(r);
        for(std::size_t i=0;i<8;++i)r.mark(a::base::phases[i].name,a::base::phases[i].epoch);
        reject("invalid-family",[]{Observation<Clock> scope(static_cast<a::Family>(4));});
#ifdef OPENPOKER_JOINT_ARITHMETIC_LIGHT_CYCLES
        bool foreign_rejected=false;
        std::thread worker([&]{try{Observation<Clock> scope(a::Family::reach);}catch(const std::exception&){foreign_rejected=true;}});
        worker.join();
        if(!foreign_rejected)throw std::runtime_error("foreign TLS scope accepted");
        std::cout<<"GUARD foreign-tls-thread PASS\n";
#endif
        {Observation<Clock> scope(a::Family::reach);
            reject("nested-scope",[]{Observation<Clock> nested(a::Family::mix);});
            scope.close();reject("double-close",[&]{scope.close();});
        }
        {Observation<Clock> abandoned(a::Family::average);}
        reject("abandoned",[&]{r.mark("walk",1);});
    }
    if(a::base::active)throw std::runtime_error("observer leak");
#ifdef OPENPOKER_JOINT_ARITHMETIC_LIGHT_CYCLES
    if(a::installed)throw std::runtime_error("light observer leak");
    std::cout<<"JOINT_ARITHMETIC_LIGHT_GUARDS_V1 PASS 15\n";
#else
    std::cout<<"JOINT_ARITHMETIC_CYCLE_GUARDS_V1 PASS 14\n";
#endif
    return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}}
