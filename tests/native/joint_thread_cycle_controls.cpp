#include "../../native/joint_thread_cycle_recorder.hpp"
#include <iostream>
#include <sstream>
#include <utility>
namespace d=openpoker::joint_thread_cycles;
struct FakeClock {
    static constexpr std::string_view units="synthetic_cycles";
    static inline std::uint64_t now=0,owner=7;
    static inline bool failure=false,backward=false;
    static std::uint64_t thread_id(){return owner;}
    static std::uint64_t read(){
        if(failure)throw std::runtime_error("injected clock failure");
        if(backward)return 0;
        return now+=1000;
    }
    static void reset(){now=0;owner=7;failure=false;backward=false;}
};
using R=d::Recorder<FakeClock>;
template<class F> void reject(std::string_view label,F&& action){
    bool caught=false;try{action();}catch(const std::exception&){caught=true;}
    if(!caught)throw std::runtime_error("control did not reject");
    std::cout<<"GUARD "<<label<<" PASS\n";
}
int main(){try{
    for(unsigned offset=0;offset<4;++offset){
        FakeClock::reset();R recorder(offset,false);d::Install install(recorder);
        for(const auto& phase:d::phases){
            if(phase.name=="walk")for(unsigned read=0;read<434;++read){
                d::ReadScope scope;FakeClock::now+=7000;scope.close();
            }
            recorder.mark(phase.name,phase.epoch);
        }
        recorder.write(std::cout);
    }
    FakeClock::reset();reject("offset",[]{R bad(4,false);});
    reject("missing-observer",[]{d::ReadScope bad;});
    {R r(0,false);d::Install install(r);
        reject("nested-install",[&]{d::Install bad(r);});
        reject("wrong-phase",[&]{r.mark("ticket",1);});
        reject("read-context",[]{d::ReadScope bad;});
        reject("incomplete",[&]{r.write(std::cout);});
        FakeClock::owner=8;reject("foreign-thread",[&]{r.mark("begin",0);});FakeClock::owner=7;
        FakeClock::failure=true;reject("clock-failure",[&]{r.mark("begin",0);});FakeClock::failure=false;
        FakeClock::backward=true;reject("nonmonotone",[&]{r.mark("begin",0);});FakeClock::backward=false;
    }
    {R r(0,false);d::Install install(r);
        for(std::size_t i=0;i<8;++i)r.mark(d::phases[i].name,d::phases[i].epoch);
        {d::ReadScope scope;
            reject("nested-read",[]{d::ReadScope bad;});
            reject("phase-during-read",[&]{r.mark("walk",1);});
            scope.close();reject("double-close",[&]{scope.close();});
        }
        {d::ReadScope abandoned;}
        reject("abandoned",[&]{r.mark("walk",1);});
    }
    if(d::active)throw std::runtime_error("observer lifetime leak");
    std::cout<<"JOINT_THREAD_CYCLE_GUARDS_V1 PASS 13\n";return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}}
