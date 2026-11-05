#include "../../native/virtual_dyadic_state.hpp"
#include <array>
#include <iostream>
#include <type_traits>

namespace s=openpoker::virtual_dyadic_state;
namespace h=openpoker::virtual_dyadic_history;
namespace b=openpoker::virtual_betting_template;
namespace c=openpoker::full_deck_public_chance;
namespace p=openpoker::dyadic_policy;
using s::Integer;
using s::ErrorCode;
static_assert(!std::is_copy_constructible_v<s::State> && !std::is_copy_assignable_v<s::State>);
static_assert(!std::is_move_constructible_v<s::State> && !std::is_move_assignable_v<s::State>);

namespace {
constexpr std::array<std::uint8_t,9> deck{16,17,24,32,33,35,37,43,48};
constexpr std::array<std::string_view,2> menu{"fold","call"};
constexpr std::array<std::string_view,2> reordered{"call","fold"};
const std::array<Integer,2> zero_actions{0,0};

b::Config configuration() {
    b::Config config;
    config.stacks={8.,8.};
    config.sb=.5;
    config.bb=1.;
    config.stages[0]={{.5},{1.},1,true};
    for (std::size_t i=1;i<4;++i) config.stages[i]={{.5,1.},{.25},1,true};
    return config;
}
s::Forecast forecast(std::size_t rows=1,std::size_t slots=2,std::size_t bits=256) {
    return {rows,slots,2,64,bits,10000000,20000000};
}
void require(bool condition,const char* message) {
    if (!condition) throw std::runtime_error(message);
}
template<class F> void reject(const char* label,ErrorCode code,F&& operation) {
    try { operation(); }
    catch (const s::Error& error) {
        require(error.code()==code,"wrong state rejection");
        std::cout<<"REJECT "<<label<<'\n';
        return;
    }
    throw std::runtime_error("state guard did not reject");
}
void require_poisoned(s::State& state) {
    require(state.failed(),"state owner did not fail closed");
    try { state.begin_sweep(); }
    catch (const s::Error& error) {
        require(error.code()==ErrorCode::failed_owner,"poisoned state error changed");
        return;
    }
    throw std::runtime_error("poisoned state resumed");
}
void one_row(s::State& state,const h::History& history) {
    require(state.register_row(history.root(),0,0,menu)==0,"one row registration");
    state.freeze();
}
void feedback(h::History& history,const b::Template& source) {
    const auto root=history.root();
    const auto call=history.append_action(root,1), raise=history.append_action(root,2);
    const std::array<h::History::Cursor,4> cursors{root,root,call,raise};
    constexpr std::array<std::size_t,4> holding{0,1,0,0};
    std::size_t slots=0;
    for (const auto cursor:cursors) slots+=source.nodes()[history.source_node(cursor)].edges.size();
    for (const unsigned shift:{104U,780U,1800U}) {
        const Integer scale=Integer(1)<<shift, denominator=Integer(580)<<(shift+100);
        s::State state(history,{2,2},denominator,forecast(cursors.size(),slots,shift+256));
        std::cout<<"CASE "<<shift<<' '<<state.denominator()<<'\n';
        for (std::size_t row=0;row<cursors.size();++row) {
            const auto& node=source.nodes()[history.source_node(cursors[row])];
            require(node.state.phase==b::Phase::decision,"synthetic row must be a decision");
            std::array<std::string_view,20> tokens{};
            for (std::size_t a=0;a<node.edges.size();++a) tokens[a]=node.edges[a].action.token;
            const std::span<const std::string_view> legal(tokens.data(),node.edges.size());
            const auto id=state.register_row(cursors[row],node.state.actor,holding[row],legal);
            require(id==row && state.register_row(cursors[row],node.state.actor,holding[row],legal)==id,
                    "same exact key did not retain its row");
            const auto& r=state.rows()[id];
            std::cout<<"KEY "<<row<<' '<<r.history_ordinal<<' '<<r.actor<<' '<<r.holding_index<<' '
                     <<r.offset<<' '<<r.actions.size();
            for (const auto token:r.actions) std::cout<<' '<<token;
            std::cout<<'\n';
        }
        state.freeze();
        for (std::size_t sweep=0;sweep<2;++sweep) {
            state.begin_sweep();
            for (std::size_t row=0;row<cursors.size();++row) {
                const auto& info=state.rows()[row];
                require(state.find_row(cursors[row],info.actor,info.holding_index)==row,"lookup changed row");
                const auto units=state.policy_units(row);
                const auto count=units.size();
                std::array<Integer,20> values{}, increments{};
                std::cout<<"ROW "<<sweep<<' '<<row<<' '<<count;
                for (std::size_t a=0;a<count;++a) {
                    const auto raw=sweep ? (5*(a+row+1))%11 : (3*(a+2*row+1))%11;
                    const int coefficient=(static_cast<int>(raw)-5)*((sweep+row)%2 ? -1 : 1);
                    values[a]=scale*coefficient;
                    if (row!=1) increments[a]=(Integer(1)<<52)*(sweep+1)*(row+1)*units[a];
                    std::cout<<' '<<units[a]<<' '<<values[a]<<' '<<increments[a];
                }
                const auto mixed=state.stage_row(row,{values.data(),count},{increments.data(),count});
                std::cout<<' '<<mixed<<'\n';
                if (!sweep) for (const auto& regret:state.regrets()) require(regret==0,"partial regret commit");
            }
            state.commit_sweep();
            for (std::size_t row=0;row<cursors.size();++row) {
                const auto& r=state.rows()[row];
                std::cout<<"COMMIT "<<sweep<<' '<<row<<' '<<r.actions.size();
                for (std::size_t a=0;a<r.actions.size();++a)
                    std::cout<<' '<<state.regrets()[r.offset+a]<<' '<<state.averages()[r.offset+a];
                std::cout<<'\n';
            }
        }
        const auto image=state.export_average();
        require(image.kind==p::ImageKind::exported_average && image.rows==cursors.size() && image.slots==slots,
                "export identity changed");
        for (std::size_t row=0;row<image.rows;++row) {
            const auto& r=state.rows()[row];
            std::cout<<"EXPORT "<<row<<' '<<r.actions.size()<<' '<<unsigned(image.uniform_fallback[row]);
            for (std::size_t a=0;a<r.actions.size();++a)
                std::cout<<' '<<image.units[r.offset+a]<<' '<<image.raw_masses[r.offset+a];
            std::cout<<'\n';
        }
        const auto rec=state.receipt();
        require(rec.rows==cursors.size() && rec.slots==slots && rec.completed_sweeps==2,"state receipt count");
        std::cout<<"RECEIPT "<<rec.work<<' '<<rec.state_work<<' '<<rec.quantizer_work<<' '
                 <<rec.reserved_entries<<' '<<rec.reserved_integer_and_text_payload_bits<<' '
                 <<rec.peak_input_bits<<' '<<rec.peak_arithmetic_bits<<'\n';
    }
}
void guards(h::History& history,const b::Template& source) {
    const auto root=history.root();
    const Integer denominator=1;
    const std::array<std::size_t,2> hands{2,2};
    reject("raised_work",ErrorCode::invalid_limits,[&] {
        s::Limits limits;limits.work=500000001;s::State state(history,hands,denominator,forecast(),limits);
    });
    reject("raised_bits",ErrorCode::invalid_limits,[&] {
        s::Limits limits;limits.integer_bits=65537;s::State state(history,hands,denominator,forecast(),limits);
    });
    reject("raised_entries",ErrorCode::invalid_limits,[&] {
        s::Limits limits;limits.entries=2000001;s::State state(history,hands,denominator,forecast(),limits);
    });
    reject("raised_payload",ErrorCode::invalid_limits,[&] {
        s::Limits limits;limits.integer_payload_bits=(std::size_t{1}<<30)+1;
        s::State state(history,hands,denominator,forecast(),limits);
    });
    reject("zero_sweeps",ErrorCode::invalid_forecast,[&] {
        auto plan=forecast();plan.sweeps=0;s::State state(history,hands,denominator,plan);
    });
    reject("unadmitted_mix_width",ErrorCode::invalid_forecast,[&] {
        s::Limits limits;limits.integer_bits=300;s::State state(history,hands,denominator,forecast(),limits);
    });
    reject("work_partition",ErrorCode::invalid_forecast,[&] {
        auto plan=forecast();plan.own_work=300000000;plan.quantizer_work=300000000;
        s::State state(history,hands,denominator,plan);
    });
    reject("negative_denominator",ErrorCode::invalid_scale,[&] {
        s::State state(history,hands,Integer(-1),forecast());
    });
    reject("wide_denominator",ErrorCode::integer_width,[&] {
        s::State state(history,hands,Integer(1)<<257,forecast());
    });
    reject("entry_footprint",ErrorCode::capacity,[&] {
        s::Limits limits;limits.entries=100;s::State state(history,hands,denominator,forecast(),limits);
    });
    reject("payload_footprint",ErrorCode::capacity,[&] {
        s::Limits limits;limits.integer_payload_bits=100;s::State state(history,hands,denominator,forecast(),limits);
    });
    {
        s::State state(history,hands,denominator,forecast());
        reject("actor",ErrorCode::invalid_row,[&] {(void)state.register_row(root,2,0,menu);});
        require_poisoned(state);
    }
    {
        s::State state(history,hands,denominator,forecast());
        reject("holding",ErrorCode::invalid_row,[&] {(void)state.register_row(root,0,2,menu);});
        require_poisoned(state);
    }
    {
        h::History other(source,c::DeckDefinition::reduced(deck));
        s::State state(history,hands,denominator,forecast());
        bool rejected=false;
        try { (void)state.register_row(other.root(),0,0,menu); }
        catch (const h::Error&) { rejected=true; }
        require(rejected,"foreign cursor accepted");
        require_poisoned(state);
        std::cout<<"REJECT foreign_cursor\n";
    }
    {
        s::State state(history,hands,denominator,forecast());
        std::string token="fold";
        const std::array<std::string_view,2> input{token,"call"};
        (void)state.register_row(root,0,0,input);
        token[0]='X';
        require(state.rows()[0].actions[0]=="fold","registered row borrowed caller text");
        reject("changed_menu",ErrorCode::changed_menu,[&] {(void)state.register_row(root,0,0,reordered);});
        require_poisoned(state);
    }
    {
        s::State state(history,hands,denominator,forecast(2,3));
        (void)state.register_row(root,0,0,menu);
        reject("slot_capacity",ErrorCode::capacity,[&] {(void)state.register_row(root,0,1,menu);});
    }
    {
        s::State state(history,hands,denominator,forecast(2,4));
        (void)state.register_row(root,0,0,menu);
        reject("incomplete_freeze",ErrorCode::phase,[&] {state.freeze();});
    }
    {
        s::State state(history,hands,denominator,forecast(2,4));
        (void)state.register_row(root,0,0,menu);
        (void)state.register_row(root,0,1,menu);
        state.freeze();state.begin_sweep();
        const std::array<Integer,2> values{Integer(1)<<52,0}, increments{0,5};
        state.stage_row(0,values,increments);
        reject("incomplete_commit",ErrorCode::phase,[&] {state.commit_sweep();});
        require(state.regrets()[0]==0 && state.averages()[1]==0,"partial committed values escaped");
        require_poisoned(state);
    }
    {
        s::State state(history,hands,denominator,forecast());
        one_row(state,history);state.begin_sweep();state.stage_row(0,zero_actions,zero_actions);
        reject("duplicate_stage",ErrorCode::invalid_row,[&] {state.stage_row(0,zero_actions,zero_actions);});
        require_poisoned(state);
    }
    {
        s::State state(history,hands,denominator,forecast());
        one_row(state,history);state.begin_sweep();
        const std::array<Integer,2> invalid{1,0};
        reject("nonmember_grid",ErrorCode::arithmetic,[&] {state.stage_row(0,invalid,zero_actions);});
    }
    {
        s::State state(history,hands,denominator,forecast());
        one_row(state,history);state.begin_sweep();
        const std::array<Integer,2> invalid{0,-1};
        reject("negative_average",ErrorCode::invalid_row,[&] {state.stage_row(0,zero_actions,invalid);});
    }
    {
        s::State state(history,hands,denominator,forecast(1,2,100));
        one_row(state,history);state.begin_sweep();
        const std::array<Integer,2> increments{Integer(1)<<99,0};
        state.stage_row(0,zero_actions,increments);state.commit_sweep();state.begin_sweep();
        reject("cumulative_width",ErrorCode::integer_width,[&] {state.stage_row(0,zero_actions,increments);});
        require(state.averages()[0]==increments[0] && state.receipt().completed_sweeps==1,"old sweep changed after overflow");
    }
    {
        s::State state(history,hands,denominator,forecast());
        one_row(state,history);state.begin_sweep();
        const std::array<Integer,2> invalid{Integer(1)<<65536,0};
        reject("oversized_input",ErrorCode::integer_width,[&] {state.stage_row(0,invalid,zero_actions);});
    }
    {
        auto plan=forecast();plan.own_work=1800;
        s::State state(history,hands,denominator,plan);
        one_row(state,history);state.begin_sweep();
        reject("state_exhaustion",ErrorCode::work_limit,[&] {state.stage_row(0,zero_actions,zero_actions);});
        require(state.receipt().state_work<=plan.own_work,"state work allowance exceeded");
    }
    {
        auto plan=forecast();plan.quantizer_work=1;
        s::State state(history,hands,denominator,plan);
        one_row(state,history);
        bool rejected=false;
        try { state.begin_sweep(); }
        catch (const p::Error& error) { rejected=error.code()==p::ErrorCode::work_limit; }
        require(rejected && state.receipt().quantizer_work<=plan.quantizer_work,"quantizer work allowance exceeded");
        require_poisoned(state);
        std::cout<<"REJECT quantizer_exhaustion\n";
    }
    {
        s::State state(history,hands,denominator,forecast());
        one_row(state,history);
        reject("early_export",ErrorCode::phase,[&] {(void)state.export_average();});
    }
    {
        auto plan=forecast();plan.sweeps=1;
        s::State state(history,hands,denominator,plan);
        one_row(state,history);state.begin_sweep();state.stage_row(0,zero_actions,zero_actions);state.commit_sweep();
        (void)state.export_average();
        reject("second_export",ErrorCode::phase,[&] {(void)state.export_average();});
    }
}
} // namespace

int main() {
    try {
        const b::Template source(configuration());
        h::History history(source,c::DeckDefinition::reduced(deck));
        std::cout<<"VIRTUAL_DYADIC_STATE_V1\n";
        feedback(history,source);
        guards(history,source);
        std::cout<<"END\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n';
        return 2;
    }
}
