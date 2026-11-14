#include "../../native/training_phase_profile.hpp"
#include <chrono>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
namespace trace=openpoker::training_phase_trace;
namespace profile=openpoker::training_phase_profile;
struct FakeClock {
    using duration=std::chrono::nanoseconds;
    using time_point=std::chrono::time_point<FakeClock,duration>;
    static inline std::int64_t tick=0, step=10;
    static time_point now() noexcept { const auto result=time_point(duration(tick)); tick+=step; return result; }
};
static void require(bool value,const char* message) { if (!value) throw std::runtime_error(message); }
int main() {
    try {
        std::ostringstream out;
        FakeClock::tick=0; FakeClock::step=10;
        profile::BasicRecorder<FakeClock> recorder;
        auto sink=recorder.sink();
        for (unsigned p=0;p<=static_cast<unsigned>(trace::Phase::footer);++p) {
            const auto phase=static_cast<trace::Phase>(p);
            trace::mark(&sink,phase,trace::Edge::begin,p);
            trace::mark(&sink,phase,trace::Edge::end,p);
        }
        require(recorder.healthy() && recorder.events().size()==26 && recorder.clock_reads()==27,"valid trace");
        std::size_t index=0;
        for (const auto& event:recorder.events()) {
            require(event.ns==10*(index+1),"relative clock");
            out<<"EVENT "<<index<<' '<<trace::name(event.phase)<<' '
                <<(event.edge==trace::Edge::begin?"begin":"end")<<' '<<event.sweep<<' '<<event.ns<<'\n';
            ++index;
        }
        const auto prior=recorder.clock_reads();
        trace::mark(nullptr,trace::Phase::walk,trace::Edge::begin);
        trace::Sink empty{}; trace::mark(&empty,trace::Phase::walk,trace::Edge::begin);
        require(recorder.clock_reads()==prior && recorder.events().size()==26,"null sink");
        FakeClock::tick=0; profile::BasicRecorder<FakeClock> full; auto full_sink=full.sink();
        for (std::size_t i=0;i<profile::capacity;++i) trace::mark(&full_sink,trace::Phase::walk,trace::Edge::begin);
        require(full.healthy() && full.events().size()==profile::capacity,"capacity fill");
        trace::mark(&full_sink,trace::Phase::walk,trace::Edge::end);
        require(!full.healthy() && full.events().size()==profile::capacity && full.clock_reads()==65,"capacity fail closed");
        FakeClock::tick=0; profile::BasicRecorder<FakeClock> backwards; auto back_sink=backwards.sink();
        trace::mark(&back_sink,trace::Phase::walk,trace::Edge::begin);
        FakeClock::tick=-1; trace::mark(&back_sink,trace::Phase::walk,trace::Edge::end);
        require(!backwards.healthy() && backwards.events().size()==1 && backwards.clock_reads()==3,"reverse clock");
        FakeClock::tick=0; profile::BasicRecorder<FakeClock> invalid; auto invalid_sink=invalid.sink();
        trace::mark(&invalid_sink,static_cast<trace::Phase>(255),trace::Edge::begin);
        require(!invalid.healthy() && invalid.events().empty() && invalid.clock_reads()==1,"invalid phase");
        FakeClock::tick=0; profile::BasicRecorder<FakeClock> bad_edge; auto edge_sink=bad_edge.sink();
        trace::mark(&edge_sink,trace::Phase::walk,static_cast<trace::Edge>(255));
        require(!bad_edge.healthy() && bad_edge.events().empty() && bad_edge.clock_reads()==1,"invalid edge");
        FakeClock::tick=0; profile::BasicRecorder<FakeClock> clocked;
        for (std::size_t i=1;i<profile::clock_limit;++i) (void)clocked.now_ns();
        require(clocked.healthy() && clocked.clock_reads()==profile::clock_limit,"clock limit fill");
        (void)clocked.now_ns();
        require(!clocked.healthy() && clocked.clock_reads()==profile::clock_limit,"clock limit fail closed");
        require(std::string(trace::name(static_cast<trace::Phase>(255)))=="unknown","unknown name");
        out<<"PROFILE_CONTROLS PASS\n";
        const auto result=out.str(); require(result.size()<=128*1024,"output limit");
        std::cout<<result; return 0;
    } catch (const std::exception& error) { std::cerr<<error.what()<<'\n'; return 1; }
}
