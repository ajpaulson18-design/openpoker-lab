#include "../../native/virtual_dyadic_state.hpp"
#include <algorithm>
#include <array>
#include <fstream>
#include <functional>
#include <iostream>
#include <iterator>
#include <string>
#include <type_traits>
#include <vector>

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
void storage(std::string_view shape,const s::State& original,const s::State& compact) {
    const auto before=original.action_storage(),after=compact.action_storage();
    require(before.array_bytes()>after.array_bytes(),"catalog did not reduce owned action arrays");
    const auto original_receipt=original.receipt(),compact_receipt=compact.receipt();
    require(original_receipt.state_work==compact_receipt.state_work &&
        original_receipt.reserved_entries==compact_receipt.reserved_entries &&
        original_receipt.reserved_integer_and_text_payload_bits==compact_receipt.reserved_integer_and_text_payload_bits,
        "catalog changed legacy state admission or charges");
    std::cout<<"ACTION_STORAGE "<<shape<<' '<<before.token_slots<<' '<<after.token_slots<<' '<<after.catalog_keys
        <<' '<<after.token_slot_bytes<<' '<<after.catalog_key_bytes<<' '<<before.array_bytes()<<' '<<after.array_bytes()<<'\n';
}
void action_catalog_controls(h::History& history,const b::Template& source) {
    const std::array<std::size_t,2> hands{2,2};
    const Integer denominator=1;
    {
        // Same allocated capacities as the PROOF9 training driver. No row
        // registration, state freeze, sweep, or solver evaluation here.
        const auto plan=forecast(24420,58164,642);
        s::State original(history,hands,denominator,plan);
        s::State compact(history,hands,denominator,plan,{}, {source.nodes().size(),source.receipt().edges});
        storage("PROOF9",original,compact);
    }
    const auto root=history.root();
    const auto call=history.append_action(root,1);
    constexpr std::array<std::string_view,2> second{"check","raise@3"};
    const auto plan=forecast(4,8);
    {
        s::State original(history,hands,denominator,plan);
        s::State compact(history,hands,denominator,plan,{}, {2,4});
        const auto put=[&](auto cursor,std::size_t actor,std::size_t holding,std::size_t key,
                           std::span<const std::string_view> actions,std::size_t expected) {
            require(original.register_row(cursor,actor,holding,actions)==expected &&
                compact.register_catalog_row(cursor,actor,holding,key,actions)==expected,"catalog changed row identity");
        };
        {
            std::string token="fold";
            const std::array<std::string_view,2> borrowed{token,"call"};
            put(root,0,0,0,borrowed,0);
            token[0]='X';
        }
        put(root,0,0,0,menu,0);
        put(root,0,1,0,menu,1);
        put(call,1,0,1,second,2);
        put(call,1,1,1,second,3);
        require(original.rows()[0].actions.data()!=original.rows()[1].actions.data() &&
            compact.rows()[0].actions.data()==compact.rows()[1].actions.data() &&
            compact.rows()[2].actions.data()==compact.rows()[3].actions.data() &&
            compact.rows()[0].actions.data()!=compact.rows()[2].actions.data(),"owned menu sharing changed");
        for (std::size_t row=0;row<4;++row) {
            const auto& original_row=original.rows()[row];
            const auto& compact_row=compact.rows()[row];
            const auto& expected=row<2?menu:second;
            require(original_row.history_ordinal==compact_row.history_ordinal && original_row.actor==compact_row.actor &&
                original_row.holding_index==compact_row.holding_index && original_row.offset==2*row &&
                compact_row.offset==original_row.offset && original_row.actions.size()==2 && compact_row.actions.size()==2 &&
                std::equal(original_row.actions.begin(),original_row.actions.end(),expected.begin()) &&
                std::equal(compact_row.actions.begin(),compact_row.actions.end(),expected.begin()),"catalog changed ordered row data");
        }
        const auto used=compact.action_storage();
        require(used.stored_tokens==4 && used.stored_menus==2,"catalog retained duplicate menus");
        original.freeze();
        compact.freeze();
        storage("SMALL",original,compact);
    }
    reject("catalog_dimensions",ErrorCode::invalid_forecast,[&] {
        s::State invalid(history,hands,denominator,plan,{}, {1,0});
    });
    reject("catalog_footprint",ErrorCode::capacity,[&] {
        s::State invalid(history,hands,denominator,plan,{}, {1,8});
    });
    {
        s::State state(history,hands,denominator,plan,{}, {2,4});
        reject("catalog_key",ErrorCode::invalid_row,[&] {(void)state.register_catalog_row(root,0,0,2,menu);});
        require_poisoned(state);
    }
    {
        s::State state(history,hands,denominator,plan);
        reject("catalog_mode",ErrorCode::invalid_row,[&] {(void)state.register_catalog_row(root,0,0,0,menu);});
    }
    {
        s::State state(history,hands,denominator,plan,{}, {2,4});
        reject("catalog_requires_key",ErrorCode::invalid_row,[&] {(void)state.register_row(root,0,0,menu);});
    }
    {
        s::State state(history,hands,denominator,plan,{}, {2,4});
        (void)state.register_catalog_row(root,0,0,0,menu);
        reject("catalog_menu_change",ErrorCode::changed_menu,[&] {(void)state.register_catalog_row(root,0,1,0,reordered);});
        require(state.rows().size()==1 && state.rows()[0].actions[0]=="fold","catalog failure changed first row");
        require_poisoned(state);
    }
    {
        s::State state(history,hands,denominator,plan,{}, {2,2});
        (void)state.register_catalog_row(root,0,0,0,menu);
        reject("catalog_token_capacity",ErrorCode::capacity,[&] {(void)state.register_catalog_row(call,1,0,1,second);});
        require(state.rows().size()==1 && state.action_storage().stored_tokens==2,"catalog overflow wrote another row");
    }
    {
        s::State state(history,hands,denominator,plan,{}, {2,4});
        constexpr std::array<std::string_view,1> invalid{"\x01"};
        reject("catalog_invalid_token",ErrorCode::invalid_row,[&] {(void)state.register_catalog_row(root,0,0,0,invalid);});
    }
}
void sealed_catalog_controls(h::History& history,const b::Template& source) {
    const std::array<std::size_t,2> hands{2,2};
    const auto root=history.root(),call=history.append_action(root,1);
    const auto first=history.decision_key(root),next=history.decision_key(call);
    const auto slots=2*first.actions+next.actions;
    const auto plan=forecast(3,slots);
    const Integer denominator=1;
    constexpr std::size_t shift=190;
    // Two limbs per action in both images for the 256-bit control width.
    const s::PackedAverageCapacity packed{2*slots,2*slots};
    const s::ActionCatalogCapacity catalog{source.nodes().size(),first.actions+next.actions,true};
    {
        s::State state(history,hands,denominator,plan,{},catalog,packed);
        require(state.register_sealed_row(root,0,shift,shift)==0,"sealed first row index");
        require(state.register_sealed_row(root,1,shift,shift)==1,"sealed shared-source row index");
        require(state.register_sealed_row(call,0,shift,shift)==2,"sealed second source row index");
        require(state.register_sealed_row(root,0,shift,shift)==0 && state.rows().size()==3,"sealed duplicate row changed census");
        require(state.find_row(root,1)==1 && state.find_row(call,0)==2,"sealed lookup mismatch");
        const auto rows=state.rows();
        require(rows[0].actions.data()==rows[1].actions.data() && rows[0].actions.data()!=rows[2].actions.data(),
            "sealed rows did not share source catalog views by source only");
        const auto storage=state.action_storage();
        require(storage.stored_menus==2 && storage.stored_tokens==first.actions+next.actions &&
            storage.token_slot_bytes==sizeof(std::string_view),"sealed source-backed storage accounting");
        std::array<std::string_view,20> actions{};
        history.decision_actions(root,{actions.data(),first.actions});
        require(std::equal(rows[0].actions.begin(),rows[0].actions.end(),actions.begin()) &&
            rows[0].actions[0].data()==actions[0].data(),"sealed legal menu mismatch or copied token");
        history.decision_actions(call,{actions.data(),next.actions});
        require(std::equal(rows[2].actions.begin(),rows[2].actions.end(),actions.begin()),"sealed second legal menu mismatch");
        state.freeze();
        state.begin_sweep();
        require(state.policy_units(0).size()==first.actions,"sealed row unavailable after index release");
        reject("sealed_lookup_after_freeze",ErrorCode::phase,[&] {(void)state.find_row(root,0);});
    }
    {
        s::State state(history,hands,denominator,plan,{},catalog,packed);
        reject("sealed_generic_registration",ErrorCode::invalid_row,[&] {(void)state.register_row(root,0,0,menu);});
    }
    {
        h::History other(source,c::DeckDefinition::reduced(deck));
        s::State state(history,hands,denominator,plan,{},catalog,packed);
        bool rejected=false;
        try {(void)state.register_sealed_row(other.root(),0,shift,shift);} catch (const h::Error&) {rejected=true;}
        require(rejected && state.failed(),"sealed foreign history cursor accepted");
        std::cout<<"REJECT sealed_foreign_cursor\n";
    }
    {
        s::State state(history,hands,denominator,plan,{},catalog,packed);
        reject("sealed_invalid_shift",ErrorCode::invalid_row,[&] {
            (void)state.register_sealed_row(root,0,plan.value_bits,shift);
        });
    }
    {
        s::State state(history,hands,denominator,plan,{},catalog,packed);
        bool rejected=false;
        try {(void)state.register_sealed_row(history.append_action(root,0),0,shift,shift);} catch (const h::Error&) {rejected=true;}
        require(rejected && state.failed(),"sealed terminal history cursor accepted");
        std::cout<<"REJECT sealed_nondecision_cursor\n";
    }
}
void packed_average_controls(h::History& history) {
    const std::array<std::size_t,2> hands{2,2};
    const auto root=history.root();
    const auto plan=forecast(2,4);
    const Integer denominator=1;
    const std::array<std::size_t,2> shifts{190,201};
    {
        s::State dense(history,hands,denominator,plan);
        s::State packed(history,hands,denominator,plan,{}, {}, {6});
        for (std::size_t row=0;row<2;++row) {
            require(dense.register_row(root,0,row,menu)==row &&
                packed.register_row(root,0,row,menu,shifts[row])==row &&
                packed.average_row_shift(row)==shifts[row],"packed row order or shift changed");
        }
        dense.freeze();packed.freeze();
        require(packed.averages().empty(),"packed state exposed a dense average image");
        for (std::size_t sweep=0;sweep<2;++sweep) {
            dense.begin_sweep();packed.begin_sweep();
            for (std::size_t row=0;row<2;++row) {
                const auto shift=shifts[row];
                const Integer numerator=((Integer(1)<<(sweep?3:255-shift))+17)<<shift;
                const std::array<Integer,2> increments{numerator,sweep?Integer(5)<<shift:Integer(0)};
                require(dense.stage_row(row,zero_actions,increments)==packed.stage_row(row,zero_actions,increments),
                    "packed stage mixed value changed");
            }
            dense.commit_sweep();packed.commit_sweep();
            for (std::size_t row=0;row<2;++row) for (std::size_t action=0;action<2;++action)
                require(dense.averages()[row*2+action]==packed.average_numerator(row,action),
                    "packed committed numerator changed");
        }
        const auto expected=dense.export_average();
        const auto actual=packed.export_average(false);
        require(!actual.raw_masses && actual.kind==expected.kind && actual.rows==expected.rows && actual.slots==expected.slots &&
            std::equal(actual.units.get(),actual.units.get()+actual.slots,expected.units.get()) &&
            std::equal(actual.uniform_fallback.get(),actual.uniform_fallback.get()+actual.rows,expected.uniform_fallback.get()),
            "packed policy-only export changed allocation");
        std::cout<<"PACKED_AVERAGE exact_feedback\n";
    }
    {
        s::State packed(history,hands,denominator,plan,{}, {}, {4});
        for (std::size_t row=0;row<2;++row) (void)packed.register_row(root,0,row,menu,200);
        packed.freeze();packed.begin_sweep();
        const std::array<Integer,2> increments{Integer(1)<<200,Integer(2)<<200};
        for (std::size_t row=0;row<2;++row) packed.stage_row(row,zero_actions,increments);
        packed.commit_sweep();packed.begin_sweep();
        const std::array<Integer,2> invalid{increments[0],increments[1]+1};
        reject("packed_nondivisible",ErrorCode::arithmetic,[&] {packed.stage_row(0,zero_actions,invalid);});
        require(packed.average_numerator(0,0)==increments[0] && packed.average_numerator(0,1)==increments[1],
            "failed packed stage changed a committed average");
        require_poisoned(packed);
    }
    {
        s::State packed(history,hands,denominator,plan,{}, {}, {4});
        for (std::size_t row=0;row<2;++row) (void)packed.register_row(root,0,row,menu,200);
        packed.freeze();packed.begin_sweep();
        const std::array<Integer,2> increments{Integer(1)<<255,0};
        for (std::size_t row=0;row<2;++row) packed.stage_row(row,zero_actions,increments);
        packed.commit_sweep();packed.begin_sweep();
        reject("packed_cumulative_width",ErrorCode::integer_width,[&] {packed.stage_row(0,zero_actions,increments);});
        require(packed.average_numerator(0,0)==increments[0],"packed overflow changed a committed average");
        require_poisoned(packed);
    }
    {
        s::State packed(history,hands,denominator,plan,{}, {}, {5});
        for (std::size_t row=0;row<2;++row) (void)packed.register_row(root,0,row,menu,200);
        reject("packed_limb_census",ErrorCode::capacity,[&] {packed.freeze();});
        require_poisoned(packed);
    }
    {
        constexpr std::size_t shift=200;
        s::State dense(history,hands,denominator,plan);
        s::State raw(history,hands,denominator,plan,{}, {}, {4});
        s::State scaled(history,hands,denominator,plan,{}, {}, {4});
        for (std::size_t row=0;row<2;++row) {
            (void)dense.register_row(root,0,row,menu);
            (void)raw.register_row(root,0,row,menu,shift);
            (void)scaled.register_row(root,0,row,menu,shift);
        }
        dense.freeze();raw.freeze();scaled.freeze();
        const std::array<Integer,2> compact{5,0};
        const std::array<Integer,2> expanded{Integer(5)<<shift,0};
        const s::ScaledAverageIncrements increments{{compact.data(),compact.size()},shift};
        for (auto* state : {&dense,&raw,&scaled}) state->begin_sweep();
        for (std::size_t row=0;row<2;++row) {
            (void)dense.stage_row(row,zero_actions,expanded);
            (void)raw.stage_row(row,zero_actions,expanded);
            (void)scaled.stage_scaled_row(row,zero_actions,increments);
        }
        for (auto* state : {&dense,&raw,&scaled}) state->commit_sweep();
        for (std::size_t row=0;row<2;++row) for (std::size_t action=0;action<2;++action)
            require(dense.average_numerator(row,action)==raw.average_numerator(row,action) &&
                raw.average_numerator(row,action)==scaled.average_numerator(row,action),
                "already-scaled average differs from dense or raw packed feedback");
        std::cout<<"SCALED_AVERAGE exact_feedback\n";
    }
    {
        s::State packed(history,hands,denominator,plan,{}, {}, {4});
        (void)packed.register_row(root,0,0,menu,200);(void)packed.register_row(root,0,1,menu,200);
        packed.freeze();packed.begin_sweep();
        const std::array<Integer,2> compact{1,0};
        reject("scaled_wrong_shift",ErrorCode::invalid_row,[&] {
            (void)packed.stage_scaled_row(0,zero_actions,{{compact.data(),compact.size()},199});
        });
    }
    {
        s::State packed(history,hands,denominator,plan,{}, {}, {4});
        (void)packed.register_row(root,0,0,menu,200);(void)packed.register_row(root,0,1,menu,200);
        packed.freeze();packed.begin_sweep();
        const std::array<Integer,2> compact{Integer(1)<<57,0};
        reject("scaled_width",ErrorCode::integer_width,[&] {
            (void)packed.stage_scaled_row(0,zero_actions,{{compact.data(),compact.size()},200});
        });
    }
    {
        s::State dense(history,hands,denominator,plan);
        (void)dense.register_row(root,0,0,menu);(void)dense.register_row(root,0,1,menu);
        dense.freeze();dense.begin_sweep();
        const std::array<Integer,2> compact{1,0};
        reject("scaled_dense_mode",ErrorCode::invalid_row,[&] {
            (void)dense.stage_scaled_row(0,zero_actions,{{compact.data(),compact.size()},0});
        });
    }
}
void packed_dual_controls(h::History& history) {
    const std::array<std::size_t,2> hands{2,2};
    const auto root=history.root();
    const auto plan=forecast(2,4);
    const Integer denominator=1;
    constexpr std::size_t average_shift=200,regret_shift=190;
    // A 256-bit field leaves one average limb and two regret limbs per slot.
    constexpr s::PackedAverageCapacity capacity{4,8};
    const Integer value_scale=Integer(1)<<regret_shift;
    const std::array<Integer,2> values{0,2*value_scale};
    const Integer average_scale=Integer(1)<<average_shift;
    const std::array<Integer,2> increments{5*average_scale,3*average_scale};
    {
        s::State dense(history,hands,denominator,plan);
        s::State packed(history,hands,denominator,plan,{}, {},capacity);
        for (std::size_t row=0;row<2;++row) {
            require(dense.register_row(root,0,row,menu)==row &&
                packed.register_row(root,0,row,menu,average_shift,regret_shift)==row &&
                packed.average_row_shift(row)==average_shift && packed.regret_row_shift(row)==regret_shift,
                "dual packed row order or scale changed");
        }
        dense.freeze();packed.freeze();
        require(packed.averages().empty() && packed.regrets().empty(),"dual packed state exposed a dense image");
        for (std::size_t sweep=0;sweep<2;++sweep) {
            dense.begin_sweep();packed.begin_sweep();
            for (std::size_t row=0;row<2;++row) {
                require(dense.policy_units(row).size()==packed.policy_units(row).size() &&
                    std::equal(dense.policy_units(row).begin(),dense.policy_units(row).end(),packed.policy_units(row).begin()),
                    "dual packed regret quantization changed policy units");
                const auto mixed=dense.stage_row(row,values,increments);
                require(packed.stage_row(row,values,increments)==mixed,"dual packed mixed value changed");
            }
            dense.commit_sweep();packed.commit_sweep();
            for (std::size_t row=0;row<2;++row) for (std::size_t action=0;action<2;++action)
                require(dense.regrets()[2*row+action]==packed.regret_numerator(row,action) &&
                    dense.averages()[2*row+action]==packed.average_numerator(row,action),
                    "dual packed committed image changed");
        }
        const auto expected=dense.export_average();
        const auto actual=packed.export_average(false);
        require(actual.kind==expected.kind && actual.rows==expected.rows && actual.slots==expected.slots &&
            std::equal(actual.units.get(),actual.units.get()+actual.slots,expected.units.get()) &&
            std::equal(actual.uniform_fallback.get(),actual.uniform_fallback.get()+actual.rows,
                       expected.uniform_fallback.get()),"dual packed average policy export changed");
        std::cout<<"PACKED_DUAL exact_feedback\n";
    }
    {
        s::State packed(history,hands,denominator,plan,{}, {},capacity);
        for (std::size_t row=0;row<2;++row) (void)packed.register_row(root,0,row,menu,average_shift,regret_shift);
        packed.freeze();packed.begin_sweep();
        for (std::size_t row=0;row<2;++row) packed.stage_row(row,values,increments);
        packed.commit_sweep();packed.begin_sweep();
        packed.stage_row(1,values,increments);
        const std::array<Integer,2> off_grid{2,2*value_scale};
        reject("packed_regret_nondivisible",ErrorCode::arithmetic,[&] {packed.stage_row(0,off_grid,increments);});
        require(packed.regret_numerator(0,1)==value_scale && packed.average_numerator(1,0)==increments[0] &&
            packed.receipt().completed_sweeps==1,
            "failed dual packed stage changed a committed image");
        require_poisoned(packed);
    }
}
void paged_image_controls(const std::filesystem::path& scratch) {
    namespace pages=openpoker::virtual_dyadic_paged_image;
    const pages::Limits limits{9,4,2,100,27,30,2};
    const auto check_rejection=[]<class Error>(auto&& action) {
        try { action(); } catch (const Error&) { return; }
        throw std::runtime_error("invalid image operation was accepted");
    };
    require(std::filesystem::create_directory(scratch),"could not reserve paging control directory");
    const auto target=scratch/"transaction";
    pages::Image image(target,limits);
    check_rejection.operator()<std::runtime_error>([&] {pages::Image duplicate(target,limits);});
    const std::array<std::uint64_t,4> first{11,12,13,14},second{21,22,23,24};
    const std::array<std::uint64_t,1> tail{9};
    std::array<std::uint64_t,4> values{};
    image.begin_sweep();
    image.stage(0,first);
    check_rejection.operator()<std::logic_error>([&] {image.commit_sweep();});
    check_rejection.operator()<std::invalid_argument>([&] {image.stage(3,first);});
    image.read(3,values);
    require(values==std::array<std::uint64_t,4>{},"partial image exposed staged values");
    image.stage(4,first);
    image.stage(8,tail);
    image.commit_sweep();
    image.read(3,values,1);
    require(values==std::array<std::uint64_t,4>{14,11,12,13},"first commit or boundary read failed");
    image.begin_sweep();
    image.stage(4,second);
    image.read(3,values,1);
    require(values==std::array<std::uint64_t,4>{14,11,12,13},"second stage altered committed values");
    image.stage(0,second);
    image.stage(8,tail);
    image.commit_sweep();
    image.read(3,values,1);
    require(values==std::array<std::uint64_t,4>{24,21,22,23},"second commit retained a stale cache page");
    const auto& receipt=image.receipt();
    require(receipt.completed_sweeps==2 && receipt.stage_calls==6 && receipt.write_words==27,
        "transaction counters disagree");

    pages::Image capped(scratch/"read-limit",{8,4,1,8,8,3,1});
    std::array<std::uint64_t,2> boundary{99,99};
    capped.read(4,values);
    check_rejection.operator()<std::length_error>([&] {capped.read(3,boundary);});
    require(boundary==std::array<std::uint64_t,2>{99,99} && capped.receipt().read_words==4,
        "colliding boundary pages exceeded read admission");
    // A maximum-width row can span two cold pages even though it is only
    // 44 words long. Both page loads must be admitted before output changes.
    constexpr std::size_t row_words=44;
    constexpr std::size_t row_page=pages::default_page_words;
    std::array<std::uint64_t,row_words> row_values;
    row_values.fill(99);
    pages::Image row_short(scratch/"row-read-one-short",
        {2*row_page,row_page,2,2*row_page-1,2*row_page,3,2});
    check_rejection.operator()<std::length_error>([&] {row_short.read(row_page-row_words/2,row_values,1);});
    const auto& short_receipt=row_short.receipt();
    require(std::all_of(row_values.begin(),row_values.end(),[](auto value) {return value==99;}) &&
        short_receipt.read_calls==0 && short_receipt.read_words==0 &&
        short_receipt.cache_hits==0 && short_receipt.cache_misses==0,
        "row boundary read mutated output or counters before admission");
    pages::Image row_exact(scratch/"row-read-exact",
        {2*row_page,row_page,2,2*row_page,2*row_page,3,2});
    row_exact.read(row_page-row_words/2,row_values,1);
    require(std::all_of(row_values.begin(),row_values.end(),[](auto value) {return value==0;}) &&
        row_exact.receipt().read_calls==1 && row_exact.receipt().read_words==2*row_page &&
        row_exact.receipt().cache_misses==2 && row_exact.receipt().logical_read_words==row_words,
        "exact row boundary read budget or data differs");
    std::cout<<"PAGED_IMAGE exact_transaction\n";

    constexpr std::size_t page=pages::default_page_words, words=page+5, split=page+2;
    pages::Limits buffered{words,page,2,4*words,2*words,30,2,pages::Profile::legacy,split,6};
    const std::vector<std::uint64_t> head(page-2,42);
    const auto stage=[&](pages::Image& target) {
        target.begin_sweep();
        check_rejection.operator()<std::invalid_argument>([&] {target.stage(split-1,first);});
        target.stage(page-2,first);
        target.stage(split+1,tail);
        target.stage(0,head);
        check_rejection.operator()<std::invalid_argument>([&] {target.stage(page-2,tail);});
        target.stage(split,tail);
        target.stage(split+2,tail);
        target.read(page-2,values,1);
        require(values==std::array<std::uint64_t,4>{},"dirty buffers exposed staged values");
    };
    pages::Image batched(scratch/"buffered",buffered);
    stage(batched);
    require(batched.receipt().physical_write_requests==4,"unexpected early dirty flushes");
    batched.commit_sweep();
    batched.read(page-2,values,1);
    require(values==first,"cross-page buffer contents differ");
    std::array<std::uint64_t,3> shared_tail{};
    batched.read(split,shared_tail);
    require(shared_tail==std::array<std::uint64_t,3>{9,9,9},"shared page overwrote the other field");
    batched.read(0,values);
    require(values==std::array<std::uint64_t,4>{42,42,42,42} &&
        batched.receipt().physical_write_requests==6 && batched.receipt().write_words==2*words &&
        batched.receipt().stage_calls==5,"buffered image coverage or write receipt differs");

    buffered.write_requests=5;
    pages::Image failed(scratch/"failed-flush",buffered);
    stage(failed);
    check_rejection.operator()<std::length_error>([&] {failed.commit_sweep();});
    check_rejection.operator()<std::logic_error>([&] {failed.commit_sweep();});
    check_rejection.operator()<std::logic_error>([&] {failed.stage(0,tail);});
    failed.read(split,shared_tail);
    require(shared_tail==std::array<std::uint64_t,3>{} && failed.receipt().completed_sweeps==0 &&
        failed.receipt().physical_write_requests==5,"partially flushed sweep replaced the committed image");

    buffered.write_requests=6;
    buffered.write_words=words+1;
    pages::Image word_capped(scratch/"buffered-word-limit",buffered);
    word_capped.begin_sweep();
    word_capped.stage(0,tail);
    check_rejection.operator()<std::length_error>([&] {word_capped.stage(2,tail);});
    require(word_capped.receipt().write_words==words && word_capped.receipt().stage_calls==1,
        "pending staged word escaped write admission");
    std::cout<<"PAGED_IMAGE buffered_transaction\n";

    pages::Limits zero{words,page,2,4*words,2*words,30,2,pages::Profile::legacy,split,8,true};
    const auto virtual_dir=scratch/"virtual-zero";
    pages::Image virtual_image(virtual_dir,zero);
    require(std::filesystem::file_size(virtual_dir/"committed.bin")==0 &&
        std::filesystem::file_size(virtual_dir/"staged.bin")==0 &&
        virtual_image.receipt().physical_write_requests==0,"virtual image was initialized on disk");
    stage(virtual_image);
    require(virtual_image.receipt().synthetic_read_calls==1 && virtual_image.receipt().synthetic_read_words==4 &&
        virtual_image.receipt().physical_read_requests==0,"zero epoch touched the read cache or disk");
    virtual_image.commit_sweep();
    virtual_image.read(page-2,values,1);
    require(values==first && virtual_image.receipt().synthetic_read_calls==1 &&
        virtual_image.receipt().physical_read_requests==2,"first commit did not switch to physical reads");
    virtual_image.begin_sweep();
    virtual_image.stage(page-2,second);
    virtual_image.stage(split+1,tail);
    virtual_image.stage(0,head);
    virtual_image.stage(split,tail);
    virtual_image.stage(split+2,tail);
    virtual_image.commit_sweep();
    virtual_image.read(page-2,values,1);
    require(values==second && virtual_image.receipt().physical_write_requests==8 &&
        virtual_image.receipt().write_words==2*words && virtual_image.receipt().completed_sweeps==2,
        "virtual image lost the second committed sweep");

    zero.write_requests=3;
    pages::Image failed_zero(scratch/"failed-virtual-first",zero);
    stage(failed_zero);
    check_rejection.operator()<std::length_error>([&] {failed_zero.commit_sweep();});
    check_rejection.operator()<std::logic_error>([&] {failed_zero.commit_sweep();});
    failed_zero.read(page-2,values,1);
    require(values==std::array<std::uint64_t,4>{} && failed_zero.receipt().physical_write_requests==3 &&
        failed_zero.receipt().completed_sweeps==0,"failed first commit ended the virtual epoch");

    zero.write_requests=5;
    pages::Image failed_later(scratch/"failed-virtual-second",zero);
    stage(failed_later);
    failed_later.commit_sweep();
    failed_later.begin_sweep();
    failed_later.stage(page-2,second);
    check_rejection.operator()<std::length_error>([&] {failed_later.stage(0,head);});
    check_rejection.operator()<std::logic_error>([&] {failed_later.commit_sweep();});
    failed_later.read(page-2,values,1);
    require(values==first && failed_later.receipt().completed_sweeps==1,
        "failed second sweep exposed staged words or restored virtual zeros");

    zero.requests=2;
    zero.read_words=0;
    pages::Image logical_capped(scratch/"virtual-logical-limit",zero);
    values.fill(99);
    check_rejection.operator()<std::out_of_range>([&] {logical_capped.read(words,values);});
    check_rejection.operator()<std::out_of_range>([&] {logical_capped.read(0,values,2);});
    require(values==std::array<std::uint64_t,4>{99,99,99,99} &&
        logical_capped.receipt().synthetic_read_calls==0,"invalid virtual read mutated output or receipt");
    logical_capped.read(0,values);
    logical_capped.read(words,{});
    check_rejection.operator()<std::length_error>([&] {logical_capped.read(0,values);});
    require(values==std::array<std::uint64_t,4>{} && logical_capped.receipt().read_calls==2 &&
        logical_capped.receipt().synthetic_read_calls==2 && logical_capped.receipt().logical_read_words==4,
        "virtual reads escaped logical admission");
    std::cout<<"PAGED_IMAGE virtual_initial_epoch\n";
}

void compact_directory_controls(h::History& history,const b::Template& source,
                                const std::filesystem::path& scratch) {
    const auto root=history.root(),call=history.append_action(root,1);
    const auto first=history.decision_key(root),next=history.decision_key(call);
    const auto slots=2*first.actions+next.actions;
    const auto plan=forecast(3,slots);
    constexpr std::size_t shift=190;
    const s::PackedAverageCapacity packed{2*slots,2*slots};
    const s::ActionCatalogCapacity catalog{source.nodes().size(),first.actions+next.actions,true};
    const openpoker::virtual_dyadic_paged_image::Limits pages{4*slots,4,2,500,12*slots,500,2};
    s::State compact(history,{2,2},1,plan,{},catalog,packed,s::PagedStrategy{scratch/"directory",pages,true});
    require(compact.register_sealed_row(root,1,shift,shift)==0 &&
        compact.register_sealed_row(call,0,shift,shift)==1 &&
        compact.register_sealed_row(root,0,shift,shift)==2 &&
        compact.register_sealed_row(root,1,shift,shift)==0,"compact directory aliased or repeated a full row key");
    require(compact.find_row(root,0)==2 && compact.find_row(call,0)==1 &&
        compact.row_at(2).history_ordinal==first.ordinal && compact.row_at(1).history_ordinal==next.ordinal &&
        compact.row_at(1).offset==first.actions && compact.row_at(2).offset==first.actions+next.actions &&
        compact.row_at(0).actions.data()==compact.row_at(2).actions.data(),
        "compact directory route or shared menu differs");
    compact.freeze();
    compact.begin_sweep();
    require(compact.policy_units(0).size()==first.actions && compact.average_row_shift(1)==shift &&
        compact.regret_row_shift(2)==shift,"compact row unavailable after construction lookup release");
    bool closed=false;
    try { (void)compact.find_row(root,0); } catch (const s::Error& error) {closed=error.code()==ErrorCode::phase;}
    require(closed && compact.failed(),"compact construction index still accessible after freeze");

    h::History foreign(source,c::DeckDefinition::reduced(deck));
    s::State guard(history,{2,2},1,plan,{},catalog,packed,s::PagedStrategy{scratch/"foreign",pages,true});
    bool rejected=false;
    try { (void)guard.register_sealed_row(foreign.root(),0,shift,shift); } catch (const h::Error&) {rejected=true;}
    require(rejected && guard.failed() && guard.row_count()==0,"compact directory accepted a foreign cursor");
    std::cout<<"PAGED_IMAGE compact_directory\n";

    s::State ordered(history,{2,2},1,plan,{},catalog,packed,s::PagedStrategy{scratch/"ordered",pages,true,true});
    s::State indexed(history,{2,2},1,plan,{},catalog,packed,s::PagedStrategy{scratch/"indexed-compare",pages,true});
    for (auto* state : {&ordered,&indexed}) {
        require(state->register_sealed_row(root,0,shift,shift)==0 &&
            state->register_sealed_row(root,1,shift,shift)==1 &&
            state->register_sealed_row(call,0,shift,shift)==2,"ordered registration differs from canonical rows");
        state->freeze();
    }
    const std::uint64_t* last_units=nullptr;
    for (std::size_t sweep=0;sweep<2;++sweep) {
        for (auto* state : {&ordered,&indexed}) {
            state->begin_sweep();
            if (state==&ordered) last_units=state->policy_units(0).data();
            for (std::size_t row=0;row<3;++row) {
                const auto menu_size=state->row_at(row).actions.size();
                std::array<Integer,20> values{},increments{};
                if (row==0) increments[0]=Integer(1)<<shift;
                (void)state->stage_row(row,std::span(values).first(menu_size),
                    std::span(increments).first(menu_size));
            }
            state->commit_sweep();
        }
    }
    const auto actual=ordered.export_average(false),expected=indexed.export_average(false);
    require(actual.units.get()==last_units && actual.rows==3 && actual.slots==slots &&
        std::equal(actual.units.get(),actual.units.get()+slots,expected.units.get()) &&
        std::equal(actual.uniform_fallback.get(),actual.uniform_fallback.get()+3,expected.uniform_fallback.get()) &&
        actual.uniform_fallback[0]==0 && actual.uniform_fallback[1]==1 &&
        ordered.receipt().reserved_entries<indexed.receipt().reserved_entries,
        "ordered export did not reuse the sweep workspace exactly");

    for (const auto& [initial,later] : {std::pair{root,root},std::pair{call,root}}) {
        s::State invalid(history,{2,2},1,plan,{},catalog,packed,s::PagedStrategy{scratch/"invalid-order",pages,true,true});
        (void)invalid.register_sealed_row(initial,1,shift,shift);
        if (history.ordinal(initial)==history.ordinal(later))
            (void)invalid.register_sealed_row(call,0,shift,shift);
        bool order_rejected=false;
        try { (void)invalid.register_sealed_row(later,1,shift,shift); }
        catch (const s::Error& error) {order_rejected=error.code()==ErrorCode::invalid_row;}
        require(order_rejected && invalid.failed(),"ordered directory accepted a repeated or backward key");
    }
    s::State reversed(history,{2,2},1,plan,{},catalog,packed,s::PagedStrategy{scratch/"reversed-holding",pages,true,true});
    (void)reversed.register_sealed_row(root,1,shift,shift);
    bool holding_rejected=false;
    try { (void)reversed.register_sealed_row(root,0,shift,shift); }
    catch (const s::Error& error) {holding_rejected=error.code()==ErrorCode::invalid_row;}
    require(holding_rejected && reversed.failed(),"ordered directory accepted a backward holding");
    std::cout<<"PAGED_IMAGE ordered_directory\n";
}

void paged_directory_controls(h::History& history,const b::Template& source,
                              const std::filesystem::path& scratch) {
    namespace pages=openpoker::virtual_dyadic_paged_image;
    const auto root=history.root();
    const auto menu_size=history.decision_key(root).actions;
    const auto slots=2*menu_size;
    constexpr std::size_t shift=190;
    const s::Forecast small_plan=forecast(2,slots);
    const s::PackedAverageCapacity small_packed{2*slots,2*slots};
    const s::ActionCatalogCapacity small_catalog{source.nodes().size(),menu_size,true};
    const pages::Limits small_limits{4*slots,pages::default_page_words,2,1000,8*slots,500,2,
        pages::Profile::legacy,2*slots,4,true};
    const s::PagedStrategy shared_strategy{scratch/"directory-shared",small_limits,true,true,true,true};
    const s::PagedStrategy directory_strategy{scratch/"directory-snapshots",small_limits,true,true,true,true,true,20};
    s::State shared(history,{2,2},1,small_plan,{},small_catalog,small_packed,shared_strategy);
    s::State directory(history,{2,2},1,small_plan,{},small_catalog,small_packed,directory_strategy);
    const auto register_rows=[&](s::State& state) {
        require(state.register_sealed_row(root,0,shift,shift)==0 &&
            state.register_sealed_row(root,1,shift,shift)==1,"paged directory row order changed");
        state.freeze();
    };
    register_rows(shared);
    register_rows(directory);
    static_assert(std::is_copy_constructible_v<s::PolicySnapshot>);
    static_assert(std::is_same_v<decltype(std::declval<s::State&>().copy_policy_snapshot(
        std::size_t{},std::span<std::uint64_t>{})),s::PolicySnapshot>);
    std::array<Integer,20> mixed_values{},increments{};
    mixed_values[menu_size-2]=Integer(5)<<(shift+52);
    mixed_values[menu_size-1]=Integer(6)<<(shift+52);
    const auto value_span=std::span<const Integer>(mixed_values).first(menu_size);
    for (std::size_t sweep=0;sweep<2;++sweep) {
        shared.begin_sweep();
        directory.begin_sweep();
        std::array<std::array<std::uint64_t,20>,2> saved{};
        std::array<s::PolicySnapshot,2> snapshots{};
        for (std::size_t row=0;row<2;++row) {
            std::array<std::uint64_t,20> expected{};
            const auto before=directory.row_directory_receipt();
            snapshots[row]=directory.copy_policy_snapshot(row,std::span(saved[row]).first(menu_size));
            const auto after=directory.row_directory_receipt();
            require(before && after && after->read_calls==before->read_calls+1,
                "policy snapshot did not perform exactly one directory metadata lookup");
            const auto& snapshot=snapshots[row];
            const auto expected_row=shared.row_at(row);
            require(snapshot.descriptor.row.history_ordinal==expected_row.history_ordinal &&
                snapshot.descriptor.row.actor==expected_row.actor &&
                snapshot.descriptor.row.holding_index==expected_row.holding_index &&
                snapshot.descriptor.row.offset==expected_row.offset &&
                snapshot.descriptor.average_shift==shared.average_row_shift(row) &&
                snapshot.descriptor.regret_shift==shared.regret_row_shift(row) &&
                snapshot.descriptor.row.actions.size()==menu_size &&
                snapshot.units.data()==saved[row].data() && snapshot.units.size()==menu_size &&
                std::equal(snapshot.units.begin(),snapshot.units.end(),saved[row].begin()),
                "policy snapshot descriptor or caller-owned units differ");
            shared.copy_policy_units(row,std::span(expected).first(menu_size));
            require(std::equal(saved[row].begin(),saved[row].begin()+menu_size,expected.begin()),
                "paged snapshot policy differs from shared policy output");
            increments.fill(0);
            if (row==0) increments[0]=Integer(1)<<shift;
            const auto mass_span=std::span<const Integer>(increments).first(menu_size);
            require(directory.stage_row(row,value_span,mass_span)==shared.stage_row(row,value_span,mass_span),
                "paged directory mixed value differs from shared state");
        }
        require(snapshots[0].units.data()==saved[0].data() &&
            std::equal(snapshots[0].units.begin(),snapshots[0].units.end(),saved[0].begin()) &&
            snapshots[0].descriptor.row.holding_index==0,
            "later metadata lookup changed an earlier value snapshot");
        directory.commit_sweep();
        shared.commit_sweep();
    }
    const auto directory_receipt=directory.row_directory_receipt();
    const auto directory_spill=directory.policy_spill_receipt();
    const auto shared_spill=shared.policy_spill_receipt();
    require(directory_receipt && directory_receipt->appended_rows==2 &&
        directory_receipt->written_rows==2 && directory_receipt->read_calls==12 &&
        directory_spill && shared_spill &&
        (*directory_spill)[0].uniform_rows==(*shared_spill)[0].uniform_rows &&
        (*directory_spill)[0].write_words==(*shared_spill)[0].write_words &&
        (*directory_spill)[1].mixed_rows==(*shared_spill)[1].mixed_rows &&
        (*directory_spill)[1].write_words==(*shared_spill)[1].write_words &&
        (*directory_spill)[1].extent_words==(*shared_spill)[1].extent_words &&
        (*directory_spill)[1].read_calls==(*shared_spill)[1].read_calls &&
        (*directory_spill)[1].read_words==(*shared_spill)[1].read_words,
        "paged directory or shared policy receipt differs");
    for (const auto* name:{"committed.bin","staged.bin"}) {
        std::ifstream a(directory_strategy.scratch/name,std::ios::binary);
        std::ifstream b(shared_strategy.scratch/name,std::ios::binary);
        require(bool(a) && bool(b) && std::string(std::istreambuf_iterator<char>(a),{})==
            std::string(std::istreambuf_iterator<char>(b),{}),"paged directory changed checkpoint image bytes");
    }
    std::vector<std::uint64_t> directory_export,shared_export;
    const auto directory_flags=directory.stream_average([&](std::span<const std::uint64_t> units) {
        directory_export.insert(directory_export.end(),units.begin(),units.end());
    });
    const auto shared_flags=shared.stream_average([&](std::span<const std::uint64_t> units) {
        shared_export.insert(shared_export.end(),units.begin(),units.end());
    });
    const auto export_receipt=directory.row_directory_receipt();
    require(directory_export==shared_export && directory_flags.size()==shared_flags.size() &&
        std::equal(directory_flags.begin(),directory_flags.end(),shared_flags.begin()) &&
        export_receipt && export_receipt->read_calls==14,
        "paged directory streamed export differs from prior shared state or read cap");
    std::cout<<"PAGED_IMAGE paged_directory\n";

    // A non-multiple of the fixed 128-row page size must write and read the exact short tail.
    constexpr std::size_t many_rows=129;
    std::vector<h::History::Cursor> decisions;
    constexpr std::array<std::uint8_t,5> board{16,17,24,32,33};
    std::function<void(h::History::Cursor)> walk=[&](h::History::Cursor cursor) {
        if (decisions.size()>=many_rows) return;
        const auto node_id=history.source_node(cursor);
        const auto& node=source.nodes()[node_id];
        if (node.state.phase==b::Phase::decision) decisions.push_back(cursor);
        if (decisions.size()>=many_rows) return;
        if (node.state.phase==b::Phase::reveal) {
            walk(history.append_reveal(cursor,{board.data(),node.state.next_street}));
        } else if (node.state.phase==b::Phase::decision) {
            for (std::size_t edge=0;edge<node.edges.size() && decisions.size()<many_rows;++edge)
                walk(history.append_action(cursor,edge));
        }
    };
    walk(history.root());
    require(decisions.size()==many_rows,"fixed-board DFS did not find 129 ordered decisions");
    std::size_t many_slots=0;
    for (const auto cursor:decisions) many_slots+=history.decision_key(cursor).actions;
    const s::Forecast many_plan=forecast(many_rows,many_slots);
    const s::PackedAverageCapacity many_packed{2*many_slots,2*many_slots};
    const s::ActionCatalogCapacity many_catalog{source.nodes().size(),many_slots,true};
    const pages::Limits many_limits{4*many_slots,pages::default_page_words,2,1000,8*many_slots,500,2,
        pages::Profile::legacy,2*many_slots,4,true};
    const auto register_many=[&](s::State& state) {
        for (std::size_t row=0;row<many_rows;++row)
            require(state.register_sealed_row(decisions[row],0,shift,shift)==row,
                "many-row directory registration changed order");
        state.freeze();
    };
    const auto tail_path=scratch/"directory-short-tail";
    s::State tail(history,{2,2},1,many_plan,{},many_catalog,many_packed,
        s::PagedStrategy{tail_path,many_limits,true,true,true,true,true,10*many_rows});
    register_many(tail);
    require(std::filesystem::file_size(std::filesystem::path(tail_path.string()+"-rows")/"rows.bin")==32*many_rows,
        "directory final short page extent differs");
    require(tail.row_at(many_rows-1).history_ordinal==history.ordinal(decisions.back()),
        "directory final short-page row differs");
    const auto tail_receipt=tail.row_directory_receipt();
    require(tail_receipt && tail_receipt->page_reads==1 && tail_receipt->read_rows==1,
        "directory did not account for its one-row final page");

    const auto capped_path=scratch/"directory-page-cap";
    s::State capped(history,{2,2},1,many_plan,{},many_catalog,many_packed,
        s::PagedStrategy{capped_path,many_limits,true,true,true,true,true,1});
    register_many(capped);
    (void)capped.row_at(0);
    bool page_rejected=false;
    try { (void)capped.row_at(128); }
    catch (const std::length_error&) {page_rejected=true;}
    if (page_rejected) require_poisoned(capped);
    const auto capped_receipt=capped.row_directory_receipt();
    require(page_rejected && capped.failed() && capped_receipt && capped_receipt->page_reads==1 &&
        capped_receipt->read_calls==1 && capped_receipt->read_rows==128,
        "directory page-read cap did not poison at the exact admitted count");

    const auto short_path=scratch/"directory-short-read";
    s::State short_read(history,{2,2},1,many_plan,{},many_catalog,many_packed,
        s::PagedStrategy{short_path,many_limits,true,true,true,true,true,10*many_rows});
    register_many(short_read);
    const auto file=std::filesystem::path(short_path.string()+"-rows")/"rows.bin";
    std::filesystem::resize_file(file,32*128);
    bool short_rejected=false;
    try { (void)short_read.row_at(128); }
    catch (const std::runtime_error&) {short_rejected=true;}
    if (short_rejected) require_poisoned(short_read);
    const auto short_receipt=short_read.row_directory_receipt();
    require(short_rejected && short_read.failed() && short_receipt &&
        short_receipt->page_reads==0 && short_receipt->read_calls==0,
        "short row-directory read did not poison without crediting a page");

    const auto invalid_path=scratch/"directory-invalid-bounds";
    bool bounds_rejected=false;
    try {
        s::State invalid(history,{2,2},1,small_plan,{},small_catalog,small_packed,
            s::PagedStrategy{invalid_path,small_limits,true,true,true,true,true,21});
    } catch (const s::Error& error) {bounds_rejected=error.code()==ErrorCode::invalid_forecast;}
    require(bounds_rejected && !std::filesystem::exists(invalid_path.string()+"-rows"),
        "invalid row-directory page bound reached directory allocation");
}

void row_coverage_controls(h::History& history,const b::Template& source,
                           const std::filesystem::path& scratch) {
    namespace pages=openpoker::virtual_dyadic_paged_image;
    const auto root=history.root();
    const auto menu_size=history.decision_key(root).actions;
    const auto slots=2*menu_size;
    constexpr std::size_t shift=190;
    const s::Forecast plan=forecast(2,slots);
    const s::PackedAverageCapacity packed{2*slots,2*slots};
    const s::ActionCatalogCapacity catalog{source.nodes().size(),menu_size,true};
    const pages::Limits limits{4*slots,pages::default_page_words,2,1000,8*slots,500,2,
        pages::Profile::legacy,2*slots,4,true};
    const auto register_rows=[&](s::State& state) {
        require(state.register_sealed_row(root,0,shift,shift)==0 &&
            state.register_sealed_row(root,1,shift,shift)==1,"row coverage order changed");
        state.freeze();
    };
    std::array<Integer,20> zero{},increments{};
    const auto actions=std::span<const Integer>(zero).first(menu_size);
    const auto stage=[&](s::State& state,std::size_t row) {
        (void)state.stage_row(row,actions,std::span<const Integer>(increments).first(menu_size));
    };
    const auto file_bytes=[](const std::filesystem::path& path) {
        std::ifstream input(path,std::ios::binary);
        require(bool(input),"cannot inspect coverage control image");
        return std::string(std::istreambuf_iterator<char>(input),std::istreambuf_iterator<char>());
    };
    const auto covered=scratch/"covered",checked=scratch/"checked-words";
    s::State a(history,{2,2},1,plan,{},catalog,packed,s::PagedStrategy{covered,limits,true,true,true});
    s::State b(history,{2,2},1,plan,{},catalog,packed,s::PagedStrategy{checked,limits,true,true});
    require(pages::Image::resident_bytes(limits)-s::State::pager_resident_bytes(limits,true)==(4*slots+7)/8,
        "row coverage residency retained the word bitmap");
    for (auto* state:{&a,&b}) {
        register_rows(*state);
        for (std::size_t sweep=0;sweep<2;++sweep) {
            state->begin_sweep();
            increments[0]=Integer(sweep+1)<<shift;
            stage(*state,1);
            stage(*state,0);
            state->commit_sweep();
        }
    }
    for (const auto* name:{"committed.bin","staged.bin"}) {
        const auto bytes=file_bytes(covered/name);
        require(bytes.size()==32*slots && bytes==file_bytes(checked/name),"covered image differs from word guard");
    }
    require(a.paged_receipt()->write_words==8*slots && a.paged_receipt()->physical_write_requests==4,
        "covered pager word or request count differs");

    const auto reject_state=[&](s::State& state,ErrorCode code,auto operation) {
        bool rejected=false;
        try {operation();} catch (const s::Error& error) {rejected=error.code()==code;}
        require(rejected && state.failed(),"invalid row coverage was accepted");
    };
    for (const bool duplicate:{false,true}) {
        s::State state(history,{2,2},1,plan,{},catalog,packed,
            s::PagedStrategy{scratch/(duplicate?"covered-duplicate":"covered-missing"),limits,true,true,true});
        register_rows(state);
        state.begin_sweep();
        stage(state,0);
        if (duplicate) reject_state(state,ErrorCode::invalid_row,[&] {stage(state,0);});
        else reject_state(state,ErrorCode::phase,[&] {state.commit_sweep();});
        require(state.paged_receipt()->completed_sweeps==0,"incomplete covered image was committed");
    }
    bool bad_split=false;
    auto invalid=limits;
    ++invalid.stage_split_words;
    try { (void)s::State::storage_forecast(plan,catalog,packed,invalid,true,true,true); }
    catch (const s::Error& error) {bad_split=error.code()==ErrorCode::invalid_forecast;}
    require(bad_split,"row coverage accepted a foreign field partition");

    const auto partial=scratch/"covered-partial";
    s::State state(history,{2,2},1,plan,{},catalog,packed,s::PagedStrategy{partial,limits,true,true,true});
    register_rows(state);
    state.begin_sweep();
    increments[1]=((Integer(1)<<(plan.value_bits-shift))-1)<<shift;
    stage(state,0);
    increments[1]=0;
    stage(state,1);
    state.commit_sweep();
    const auto previous=file_bytes(partial/"staged.bin");
    state.begin_sweep();
    increments[1]=Integer(1)<<shift;
    const auto calls=state.paged_receipt()->stage_calls;
    reject_state(state,ErrorCode::integer_width,[&] {stage(state,0);});
    require(state.paged_receipt()->stage_calls>calls && state.paged_receipt()->completed_sweeps==1 &&
        file_bytes(partial/"staged.bin")==previous,"partially staged row changed the prior committed image");

    auto limited=limits;
    limited.write_requests=3;
    const auto failed_flush=scratch/"covered-failed-flush";
    s::State capped(history,{2,2},1,plan,{},catalog,packed,s::PagedStrategy{failed_flush,limited,true,true,true});
    register_rows(capped);
    increments[1]=0;
    for (std::size_t sweep=0;sweep<2;++sweep) {
        capped.begin_sweep();
        stage(capped,0);
        stage(capped,1);
        if (!sweep) capped.commit_sweep();
    }
    const auto prior=file_bytes(failed_flush/"staged.bin");
    bool flush_rejected=false;
    try {capped.commit_sweep();} catch (const std::length_error&) {flush_rejected=true;}
    require(flush_rejected && capped.failed() && capped.paged_receipt()->completed_sweeps==1 &&
        capped.paged_receipt()->physical_write_requests==3 && file_bytes(failed_flush/"staged.bin")==prior,
        "covered flush failure replaced the committed image");
    std::cout<<"PAGED_IMAGE row_coverage\n";

    require(menu_size>=3,"shared policy fixture needs two positive regret actions");
    const auto shared_path=scratch/"shared-policy",dense_path=scratch/"dense-policy";
    s::State shared(history,{2,2},1,plan,{},catalog,packed,
        s::PagedStrategy{shared_path,limits,true,true,true,true});
    s::State dense(history,{2,2},1,plan,{},catalog,packed,
        s::PagedStrategy{dense_path,limits,true,true,true});
    register_rows(shared);
    register_rows(dense);
    std::array<Integer,20> mixed_values{};
    mixed_values[menu_size-2]=Integer(5)<<(shift+52);
    mixed_values[menu_size-1]=Integer(6)<<(shift+52);
    const auto all_mixed=std::span<const Integer>(mixed_values).first(menu_size);
    for (std::size_t sweep=0;sweep<2;++sweep) {
        shared.begin_sweep();
        dense.begin_sweep();
        std::array<std::array<std::uint64_t,20>,2> copies{};
        for (std::size_t row=0;row<2;++row) {
            auto units=std::span(copies[row]).first(menu_size);
            shared.copy_policy_units(row,units);
            shared.copy_policy_units(row,units);
        }
        for (std::size_t row=0;row<2;++row) {
            const auto expected=dense.policy_units(row);
            require(std::equal(expected.begin(),expected.end(),copies[row].begin()),"copied policy units differ");
            increments[0]=row==0?Integer(1)<<shift:Integer(0);
            const auto masses=std::span<const Integer>(increments).first(menu_size);
            require(shared.stage_row(row,all_mixed,masses)==dense.stage_row(row,all_mixed,masses),
                "shared-policy mixed value differs");
        }
        shared.commit_sweep();
        dense.commit_sweep();
    }
    const auto spill=shared.policy_spill_receipt();
    require(spill && (*spill)[0].uniform_rows==2 && (*spill)[0].write_words==0 &&
        (*spill)[1].mixed_rows==2 && (*spill)[1].write_words==slots-2 &&
        (*spill)[1].extent_words==slots-2 && (*spill)[1].read_calls==6 &&
        (*spill)[1].mixed_read_calls==6 && (*spill)[1].read_words==3*(slots-2),
        "all-mixed fallback did not use its exact word and request bounds");
    for (const auto* name:{"committed.bin","staged.bin"})
        require(file_bytes(shared_path/name)==file_bytes(dense_path/name),"shared policy changed checkpoint bytes");
    std::vector<std::uint64_t> streamed;
    const auto flags=shared.stream_average([&](std::span<const std::uint64_t> units) {
        streamed.insert(streamed.end(),units.begin(),units.end());
    });
    const auto legacy=dense.export_average(false);
    require(streamed.size()==slots && std::equal(streamed.begin(),streamed.end(),legacy.units.get()) &&
        flags.size()==2 && std::equal(flags.begin(),flags.end(),legacy.uniform_fallback.get()) &&
        flags[0]==0 && flags[1]==1,"shared average stream or fallback flags changed");
    std::cout<<"PAGED_IMAGE shared_policy\n";
}
void proof9_t4_pager_controls() {
    namespace pages=openpoker::virtual_dyadic_paged_image;
    const pages::Limits extended{606730,4096,16,3203674,2426920,1221444,2,
        pages::Profile::proof9_t4,258694,7908,true};
    auto earlier=extended;
    earlier.profile=pages::Profile::legacy;
    earlier.read_words=2223164;
    earlier.write_words=1820190;
    earlier.requests=930624;
    earlier.write_requests=5931;
    require(s::State::pager_resident_bytes(extended,true)==591008 &&
            s::State::pager_resident_bytes(earlier,true)==591008,
            "four-sweep pager altered resident geometry");
    const auto reject_pager=[](const pages::Limits& limits) {
        try { (void)pages::Image::resident_bytes(limits); }
        catch (const std::invalid_argument&) { return; }
        throw std::runtime_error("foreign four-sweep pager limits accepted");
    };
    auto invalid=extended; invalid.profile=pages::Profile::legacy; reject_pager(invalid);
    invalid=extended; ++invalid.read_words; reject_pager(invalid);
    invalid=extended; ++invalid.write_words; reject_pager(invalid);
    invalid=extended; ++invalid.requests; reject_pager(invalid);
    invalid=extended; ++invalid.write_requests; reject_pager(invalid);
    invalid=extended; --invalid.stage_split_words; reject_pager(invalid);
    invalid=extended; invalid.virtual_initial_zero=false; reject_pager(invalid);

    constexpr s::ActionCatalogCapacity catalog{146,371,true};
    constexpr s::PackedAverageCapacity packed{258694,348036};
    const s::Forecast t3{24420,58164,3,15,642,76104624,182766664};
    const s::Forecast t4{24420,58164,4,15,642,98317056,261273056};
    const auto storage=[&](const s::Forecast& plan,const pages::Limits& limits,s::Lifecycle lifecycle) {
        return s::State::storage_forecast(plan,catalog,packed,limits,true,true,true,true,true,lifecycle);
    };
    const auto before=storage(t3,earlier,s::Lifecycle::bounded_v1);
    const auto after=storage(t4,extended,s::Lifecycle::bounded_v1);
    require(after.entries==before.entries+8 && after.payload_bits==before.payload_bits+512,
            "four-sweep State receipt storage differs");
    for (const auto lifecycle:{s::Lifecycle::fixed_two_sweep,s::Lifecycle::bounded_v1}) {
        bool rejected=false;
        try { (void)storage(t3,extended,lifecycle); }
        catch (const s::Error& error) { rejected=error.code()==ErrorCode::invalid_forecast; }
        require(rejected,"four-sweep pager accepted an earlier State horizon");
    }
    std::cout<<"PROOF9_T4_GUARDS 7 2 8 512\n";
}

void proof9_q32_controls(h::History& history,const b::Template& source,const std::filesystem::path& scratch) {
    namespace pages=openpoker::virtual_dyadic_paged_image;
    constexpr s::Forecast plan{24420,58164,32,15,644,720265152,1867537648};
    constexpr s::ActionCatalogCapacity catalog{388,410,true};
    constexpr s::PackedAverageCapacity packed{258694,348036};
    const pages::Limits page_limits{606730,4096,16,pages::n9_q32_read_words,pages::n9_q32_write_words,
        pages::n9_q32_logical_requests,2,pages::Profile::proof9_q32,pages::n9_q32_stage_split_words,
        pages::n9_q32_write_requests,true};
    const auto storage=s::State::storage_forecast(plan,catalog,packed,page_limits,true,true,true,true,true,
        s::Lifecycle::quality32,s::PayloadModel::legacy,true);
    require(storage.entries==106399 && storage.payload_bits==241969528,
        "Q32 State payload, 32 generation receipts or row codec forecast differs");
    const auto make_strategy=[&](const std::filesystem::path& path) {
        return s::PagedStrategy{path,page_limits,true,true,true,true,true,s::State::proof9_q32_directory_page_limit,
            s::Lifecycle::quality32,p::DivisionKernel::combined,s::PayloadModel::legacy,true};
    };
    const auto expect_preflight_rejection=[&](const char* name,s::Forecast altered,s::Limits limits,
                                               ErrorCode code) {
        const auto reject_path=scratch/(std::string("q32-")+name);
        bool failed=false;
        try {s::State state(history,{2,2},1,altered,limits,catalog,packed,make_strategy(reject_path));}
        catch (const s::Error& error) {failed=error.code()==code;}
        require(failed && !std::filesystem::exists(reject_path) &&
            !std::filesystem::exists(reject_path.string()+"-rows"),
            "Q32 State preflight rejection allocated files");
    };
    const s::Limits adequate{2600000000ULL,702,2000000,storage.payload_bits};
    auto too_short=adequate;too_short.integer_payload_bits=storage.payload_bits-1;
    expect_preflight_rejection("payload-short",plan,too_short,ErrorCode::capacity);
    auto entries_short=adequate;entries_short.entries=storage.entries-1;
    expect_preflight_rejection("entries-short",plan,entries_short,ErrorCode::capacity);
    auto bits_short=adequate;bits_short.integer_bits=701;
    expect_preflight_rejection("bits-short",plan,bits_short,ErrorCode::invalid_forecast);
    auto work_short=adequate;work_short.work=plan.own_work+plan.quantizer_work-1;
    expect_preflight_rejection("work-partition-short",plan,work_short,ErrorCode::invalid_forecast);
    auto quantizer_high=plan;quantizer_high.quantizer_work=p::proof9_q32_work_cap+1;
    expect_preflight_rejection("quantizer-high",quantizer_high,adequate,ErrorCode::invalid_forecast);
    auto wrong_width=plan;wrong_width.value_bits=643;
    expect_preflight_rejection("wrong-width",wrong_width,adequate,ErrorCode::invalid_forecast);
    auto too_many=plan;too_many.sweeps=33;
    expect_preflight_rejection("sweep33",too_many,adequate,ErrorCode::invalid_forecast);
    auto bad_directory_strategy=make_strategy(scratch/"q32-directory-over-cap");
    bad_directory_strategy.directory_page_limit=s::State::proof9_q32_directory_page_limit+1;
    bool directory_rejected=false;
    try {s::State state(history,{2,2},1,plan,adequate,catalog,packed,bad_directory_strategy);}
    catch (const s::Error& error) {directory_rejected=error.code()==ErrorCode::invalid_forecast;}
    require(directory_rejected && !std::filesystem::exists(bad_directory_strategy.scratch) &&
        !std::filesystem::exists(bad_directory_strategy.scratch.string()+"-rows"),
        "Q32 invalid directory page bound allocated files");
    const auto reject_forecast=[&](s::Forecast altered,s::ActionCatalogCapacity menus,
                                   s::PackedAverageCapacity image,bool batch) {
        try { (void)s::State::storage_forecast(altered,menus,image,page_limits,true,true,true,true,true,
            s::Lifecycle::quality32,s::PayloadModel::legacy,batch); }
        catch (const s::Error&) { return; }
        throw std::runtime_error("unsupported Q32 State forecast accepted");
    };
    auto altered=plan;altered.sweeps=31;reject_forecast(altered,catalog,packed,true);
    reject_forecast(plan,{388,410,false},packed,true);
    reject_forecast(plan,catalog,packed,false);
    auto invalid_pages=page_limits;++invalid_pages.requests;
    bool pager_rejected=false;
    try {(void)pages::Image::resident_bytes(invalid_pages);}
    catch (const std::invalid_argument&) {pager_rejected=true;}
    require(pager_rejected,"Q32 pager accepted a raised logical request cap");
    require(s::PolicySpillSweep{}.write_words==0 && sizeof(s::PolicySpillSweep)==64,
        "Q32 per-generation spill receipt ABI differs");
    std::cout<<"PROOF9_Q32_STATE "<<storage.entries<<' '<<storage.payload_bits<<" PASS\n";
    std::cout<<"PROOF9_Q32_GUARDS 8 PASS\n";
    (void)source;
}

void proof9_q32_pager_controls(const std::filesystem::path& scratch) {
    namespace pages=openpoker::virtual_dyadic_paged_image;
    const pages::Limits limits{606730,4096,16,pages::n9_q32_read_words,pages::n9_q32_write_words,
        pages::n9_q32_logical_requests,2,pages::Profile::proof9_q32,pages::n9_q32_stage_split_words,
        pages::n9_q32_write_requests,true};
    constexpr std::size_t split=pages::n9_q32_stage_split_words,total=pages::n9_image_words;
    pages::Image image(scratch/"proof9-q32-pager",limits);
    require(image.receipt().physical_write_requests==0 &&
        std::filesystem::file_size(scratch/"proof9-q32-pager"/"committed.bin")==0,
        "Q32 virtual initial image was written eagerly");
    std::vector<std::uint64_t> words(total);
    for (std::size_t i=0;i<total;++i) words[i]=0x9e3779b97f4a7c15ULL^i;
    image.begin_sweep();
    const auto stage_range=[&](std::size_t begin,std::size_t end) {
        for (auto at=begin;at<end;) {
            const auto count=std::min(end-at,limits.page_words-at%limits.page_words);
            image.stage(at,std::span<const std::uint64_t>(words).subspan(at,count));
            at+=count;
        }
    };
    stage_range(0,split);
    stage_range(split,total);
    image.commit_sweep();
    std::array<std::uint64_t,4> crossing{};
    image.read(4094,crossing,0);
    require(std::equal(crossing.begin(),crossing.end(),words.begin()+4094),
        "Q32 row-batched extent lost words across a physical page boundary");
    const std::array<std::uint64_t,4> next{1,2,3,4};
    image.begin_sweep();
    image.stage(0,next);
    image.read(4094,crossing,1);
    require(std::equal(crossing.begin(),crossing.end(),words.begin()+4094) &&
        image.receipt().completed_sweeps==1,
        "Q32 staged next generation changed the prior committed image");
    require(image.receipt().write_words==total && image.receipt().stage_calls==151,
        "Q32 early pager receipt differs");
    std::cout<<"PROOF9_Q32_PAGER "<<image.receipt().read_words<<' '
        <<image.receipt().physical_read_requests<<' '<<image.receipt().stage_calls<<" PASS\n";
}

void bounded_lifecycle_controls(h::History& history,const b::Template& source,
                                const std::filesystem::path& scratch) {
    namespace pages=openpoker::virtual_dyadic_paged_image;
    constexpr std::size_t shift=190;
    const auto root=history.root(),call=history.append_action(root,1);
    const std::array<h::History::Cursor,4> cursors{root,root,call,call};
    std::size_t slots=0;
    for (auto cursor:cursors) slots+=history.decision_key(cursor).actions;
    {
        auto invalid_plan=forecast(4,slots);invalid_plan.sweeps=9;
        const auto invalid_path=scratch/"bounded-invalid-nine";
        const pages::Limits invalid_limits{4*slots,pages::default_page_words,2,100000,36*slots,
            10000,2,pages::Profile::legacy,2*slots,36,true};
        bool rejected=false;
        try {s::State invalid(history,{2,2},1,invalid_plan,{},
            {source.nodes().size(),slots,true},{2*slots,2*slots},
            s::PagedStrategy{invalid_path,invalid_limits,true,true,true,true,true,100,
                             s::Lifecycle::bounded_v1});}
        catch (const s::Error&) {rejected=true;}
        require(rejected && !std::filesystem::exists(invalid_path) &&
            !std::filesystem::exists(invalid_path.string()+"-rows"),"invalid lifecycle allocated files");
    }
    // Separate owners ensure every phase guard is tested without recovery from
    // a poisoned owner. Two successful commits precede every failure below.
    for (const std::string scenario:{"io-cap","flush-cap","missing-row","early-export","max-sweeps","second-export"}) {
        auto plan=forecast(4,slots);plan.sweeps=3;
        const auto path=scratch/("bounded-guard-"+scenario);
        const auto image_words=4*slots;
        const pages::Limits limits{image_words,pages::default_page_words,2,100000,
            (scenario=="io-cap"?2:3)*image_words,10000,2,pages::Profile::legacy,2*slots,
            scenario=="flush-cap"?5u:12u,true};
        s::State state(history,{2,2},1,plan,{},
            {source.nodes().size(),slots,true},{2*slots,2*slots},
            s::PagedStrategy{path,limits,true,true,true,true,true,56,s::Lifecycle::bounded_v1});
        for (std::size_t row=0;row<4;++row)
            require(state.register_sealed_row(cursors[row],row%2,shift,shift)==row,"guard row order");
        state.freeze();
        const auto stage=[&](std::size_t row) {
            const auto n=history.decision_key(cursors[row]).actions;
            std::array<Integer,20> values{},increments{};
            for (std::size_t action=0;action<n;++action) increments[action]=row+action+1;
            (void)state.stage_scaled_row(row,std::span<const Integer>(values).first(n),
                                         {std::span<const Integer>(increments).first(n),shift});
        };
        for (std::size_t sweep=0;sweep<2;++sweep) {
            state.begin_sweep();
            for (std::size_t row=0;row<4;++row) stage(row);
            state.commit_sweep();
        }
        const auto prior_epoch=state.checkpoint_epoch();
        const auto current=path/(prior_epoch.current_slot?"staged.bin":"committed.bin");
        const auto read_file=[](const std::filesystem::path& file) {
            std::ifstream in(file,std::ios::binary);
            require(bool(in),"guard checkpoint missing");
            return std::string(std::istreambuf_iterator<char>(in),{});
        };
        const auto before=read_file(current);
        bool rejected=false;
        try {
            if (scenario=="early-export") {
                (void)state.stream_average([](std::span<const std::uint64_t>){});
            } else {
                state.begin_sweep();
                if (scenario=="io-cap") stage(0);
                else if (scenario=="missing-row") {stage(0);state.commit_sweep();}
                else {
                    for (std::size_t row=0;row<4;++row) stage(row);
                    state.commit_sweep();
                    if (scenario=="max-sweeps") state.begin_sweep();
                    else {
                        (void)state.stream_average([](std::span<const std::uint64_t>){});
                        (void)state.stream_average([](std::span<const std::uint64_t>){});
                    }
                }
            }
        } catch (const std::exception&) {rejected=true;}
        require(rejected && state.failed(),"bounded lifecycle failure was not poisoned");
        const bool before_third_commit=scenario=="io-cap" || scenario=="flush-cap" ||
            scenario=="missing-row" || scenario=="early-export";
        if (before_third_commit) {
            require(state.receipt().completed_sweeps==2 && read_file(current)==before,
                "failed third generation changed committed checkpoint");
            if (scenario!="early-export")
                require(state.policy_sweep_receipts().size()==3,"opened third spill receipt lost");
            if (scenario=="flush-cap")
                require(state.paged_receipt()->physical_write_requests==5,
                    "third commit did not stop after the admitted partial flush");
        } else require(state.receipt().completed_sweeps==3,"completed third generation lost");
        bool epoch_rejected=false;
        try {(void)state.checkpoint_epoch();} catch(const s::Error&) {epoch_rejected=true;}
        require(epoch_rejected,"poisoned owner exposed checkpoint epoch");
        std::cout<<"LIFECYCLE GUARD "<<scenario<<'\n';
    }
    for (const std::size_t count:{1,2,3,4,8}) {
        auto plan=forecast(4,slots);plan.sweeps=count;
        const auto name=scratch/("bounded-"+std::to_string(count));
        const s::PackedAverageCapacity packed{2*slots,2*slots};
        const s::ActionCatalogCapacity catalog{source.nodes().size(),slots,true};
        const pages::Limits limits{4*slots,pages::default_page_words,2,100000,4*slots*count,
            10000,2,pages::Profile::legacy,2*slots,4*count,true};
        s::State state(history,{2,2},1,plan,{},catalog,packed,
            s::PagedStrategy{name,limits,true,true,true,true,true,(2+4*count)*4,s::Lifecycle::bounded_v1});
        for (std::size_t row=0;row<4;++row)
            require(state.register_sealed_row(cursors[row],row%2,shift,shift)==row,"bounded row order");
        state.freeze();
        for (std::size_t sweep=0;sweep<count;++sweep) {
            state.begin_sweep();
            for (std::size_t row=0;row<4;++row) {
                const auto menu_size=history.decision_key(cursors[row]).actions;
                std::array<std::uint64_t,20> policy{};
                (void)state.copy_policy_snapshot(row,std::span(policy).first(menu_size));
                std::array<Integer,20> values{},average{};
                std::cout<<"LIFECYCLE ROW "<<count<<' '<<sweep<<' '<<row<<' '<<menu_size;
                for (std::size_t action=0;action<menu_size;++action) {
                    const int coefficient=static_cast<int>((3*action+2*row+5*sweep)%11)-5;
                    values[action]=(Integer(1)<<(shift+52))*coefficient;
                    average[action]=Integer(policy[action]);
                    std::cout<<' '<<policy[action]<<' '<<coefficient;
                }
                const auto mixed=state.stage_scaled_row(row,std::span<const Integer>(values).first(menu_size),
                    {std::span<const Integer>(average).first(menu_size),shift});
                std::cout<<' '<<mixed<<'\n';
            }
            state.commit_sweep();
            const auto epoch=state.checkpoint_epoch();
            require(epoch.sweep==sweep+1 && epoch.current_slot==(sweep%2?0:1) &&
                epoch.previous_sweep==sweep && epoch.previous_slot==(sweep%2?1:0) &&
                epoch.image_words==4*slots && epoch.previous_is_virtual==(sweep==0),"bounded checkpoint epoch differs");
            const auto image=name/((sweep%2)?"committed.bin":"staged.bin");
            std::ifstream in(image,std::ios::binary);
            require(bool(in),"bounded image missing");
            std::vector<std::uint64_t> words(4*slots);
            in.read(reinterpret_cast<char*>(words.data()),static_cast<std::streamsize>(words.size()*8));
            require(bool(in) && in.peek()==std::char_traits<char>::eof(),"bounded image extent");
            std::cout<<"LIFECYCLE IMAGE "<<count<<' '<<sweep<<' '<<words.size();
            for (const auto word:words) std::cout<<' '<<word;
            std::cout<<'\n';
        }
        require(state.policy_sweep_receipts().size()==count,"bounded policy receipt count");
        for (std::size_t i=0;i<count;++i) {
            const auto& r=state.policy_sweep_receipts()[i];
            std::cout<<"LIFECYCLE SPILL "<<count<<' '<<i<<' '<<r.uniform_rows<<' '<<r.pure_rows
                <<' '<<r.mixed_rows<<' '<<r.extent_words<<' '<<r.write_words<<' '<<r.read_calls
                <<' '<<r.mixed_read_calls<<' '<<r.read_words<<'\n';
        }
        const auto flags=state.stream_average([&](std::span<const std::uint64_t> units) {
            std::cout<<"LIFECYCLE EXPORT "<<count<<' '<<units.size();
            for (auto unit:units) std::cout<<' '<<unit;
            std::cout<<'\n';
        });
        std::cout<<"LIFECYCLE FLAGS "<<count;
        for (auto flag:flags) std::cout<<' '<<static_cast<unsigned>(flag);
        std::cout<<'\n';
        bool legacy_rejected=false;
        try {(void)state.policy_spill_receipt();} catch (const s::Error&) {legacy_rejected=true;}
        require(legacy_rejected,"legacy receipt truncated bounded lifecycle");
        std::cout<<"LIFECYCLE DONE "<<count<<'\n';
    }
}
void phase_payload_controls(h::History& history,const b::Template& source,const std::filesystem::path& scratch) {
    namespace pages=openpoker::virtual_dyadic_paged_image;
    const s::Forecast plan{119196,281066,2,15,644,261025384,513301416};
    const s::ActionCatalogCapacity catalog{source.nodes().size(),source.receipt().edges,true};
    require(catalog.keys==388 && catalog.token_slots==410,"phase payload catalog census differs");
    const s::PackedAverageCapacity packed{1295812,1666910};
    const pages::Limits pages_limits{2962722,4096,16,6130244,5925444,3091726,2,
        pages::Profile::proof10,1295812,18836,true};
    const auto legacy=s::State::storage_forecast(plan,catalog,packed,pages_limits,true,true,true,true,true);
    const auto phased=s::State::storage_forecast(plan,catalog,packed,pages_limits,true,true,true,true,true,
        s::Lifecycle::fixed_two_sweep,s::PayloadModel::paged_phases);
    const auto batched=s::State::storage_forecast(plan,catalog,packed,pages_limits,true,true,true,true,true,
        s::Lifecycle::fixed_two_sweep,s::PayloadModel::paged_phases,true);
    require(phased.entries==200886 && phased.entries==legacy.entries && phased.payload_bits==6398880 &&
        legacy.payload_bits==1168510748,"phase payload reservation or legacy parity differs");
    require(batched.entries==phased.entries+33 && batched.payload_bits==phased.payload_bits+2112,
        "row-batched codec reservation differs");
    const std::size_t fixed=16384,directory_bytes=36864,views=(410+388)*16,pager=591008,
        tags=119196,spill=1024,codec=88,arithmetic=256*11*8;
    require(8*(fixed+directory_bytes+views+pager+tags+spill+codec+arithmetic)==phased.payload_bits,
        "independent phase payload breakdown differs");
    std::cout<<"PHASE_PAYLOAD "<<legacy.entries<<' '<<legacy.payload_bits<<' '
        <<phased.entries<<' '<<phased.payload_bits<<'\n';
    const auto path=scratch/"payload-short";
    s::Limits limits{plan.own_work+plan.quantizer_work,702,2000000,phased.payload_bits-1};
    bool short_rejected=false;
    try {
        s::State state(history,{2,2},1,plan,limits,catalog,packed,
            s::PagedStrategy{path,pages_limits,true,true,true,true,true,7656,
                s::Lifecycle::fixed_two_sweep,p::DivisionKernel::separate,s::PayloadModel::paged_phases});
    } catch (const s::Error& error) {short_rejected=error.code()==ErrorCode::capacity;}
    require(short_rejected && !std::filesystem::exists(path) &&
        !std::filesystem::exists(path.string()+"-rows"),"short payload allocated scratch or escaped admission");
    const auto batched_path=scratch/"batched-payload-short";
    s::Limits batched_limits{plan.own_work+plan.quantizer_work,702,batched.entries,batched.payload_bits-1};
    bool batched_short_rejected=false;
    try {
        s::State state(history,{2,2},1,plan,batched_limits,catalog,packed,
            s::PagedStrategy{batched_path,pages_limits,true,true,true,true,true,7656,
                s::Lifecycle::fixed_two_sweep,p::DivisionKernel::separate,s::PayloadModel::paged_phases,true});
    } catch (const s::Error& error) {batched_short_rejected=error.code()==ErrorCode::capacity;}
    require(batched_short_rejected && !std::filesystem::exists(batched_path) &&
        !std::filesystem::exists(batched_path.string()+"-rows"),
        "one-bit-short batched payload allocated scratch");
    const s::Limits packed_policy_limits{plan.own_work+plan.quantizer_work,702,2000000,1200000000};
    openpoker::factored_dyadic::Execution packed_policy_factored(1000000000);
    const auto make_packed_policy_strategy=[&](const std::filesystem::path& path) {
        s::PagedStrategy strategy{path,pages_limits,true,true,true,true,true,7656,
            s::Lifecycle::fixed_two_sweep,p::DivisionKernel::bounded_complement,
            s::PayloadModel::paged_phases,true};
        strategy.factored=&packed_policy_factored;
        strategy.reuse_snapshot=true;
        strategy.zero_policy_bootstrap=true;
        strategy.first_regret_bound=true;
        strategy.packed_policy=true;
        return strategy;
    };
    const auto valid_path=scratch/"packed-policy-valid";
    {
        auto strategy=make_packed_policy_strategy(valid_path);
        s::State accepted(history,{2,2},1,plan,packed_policy_limits,catalog,packed,strategy);
        require(std::filesystem::exists(valid_path.string()+"-rows"),
            "valid packed policy shortcut baseline was not admitted");
    }
    for (int variant=0;variant<5;++variant) {
        const auto guard_path=scratch/("packed-policy-guard-"+std::to_string(variant));
        auto guard_plan=plan;
        auto strategy=make_packed_policy_strategy(guard_path);
        const auto guard_packed=variant==4?s::PackedAverageCapacity{packed.limb_count,0}:packed;
        if (variant==0) strategy.division_kernel=p::DivisionKernel::separate;
        if (variant==1) strategy.row_batched=false;
        if (variant==2) strategy.zero_policy_bootstrap=false;
        if (variant==3) guard_plan.sweeps=1;
        bool expected_error=false;
        try {s::State state(history,{2,2},1,guard_plan,packed_policy_limits,catalog,guard_packed,strategy);}
        catch (const s::Error& error) {expected_error=error.code()==ErrorCode::invalid_forecast;}
        require(expected_error && !std::filesystem::exists(guard_path) &&
            !std::filesystem::exists(guard_path.string()+"-rows"),
            "packed policy shortcut guard did not reject its isolated invalid condition before scratch allocation");
    }
    std::cout<<"PACKED_POLICY_GUARDS PASS\n";
    bool mode_mismatch_rejected=false;
    try {(void)s::State::storage_forecast(plan,catalog,packed,pages_limits,true,true,true,true,true,
        s::Lifecycle::fixed_two_sweep,s::PayloadModel::legacy,true);}
    catch (const s::Error&) {mode_mismatch_rejected=true;}
    require(mode_mismatch_rejected,"row batching escaped its phase payload model");
    for (int variant=0;variant<5;++variant) {
        bool rejected=false;
        try {
            auto altered=plan; auto menus=catalog; auto image=packed;
            bool compact=true,ordered=true,coverage=true,shared=true,directory=true;
            if (variant==0) altered.sweeps=1;
            if (variant==1) menus.sealed=false;
            if (variant==2) shared=false;
            if (variant==3) directory=false;
            if (variant==4) ordered=false;
            (void)s::State::storage_forecast(altered,menus,image,pages_limits,compact,ordered,coverage,shared,directory,
                s::Lifecycle::fixed_two_sweep,s::PayloadModel::paged_phases);
        } catch (const s::Error&) {rejected=true;}
        require(rejected,"incompatible phase payload layout accepted");
    }
    std::cout<<"PHASE_PAYLOAD_GUARDS PASS\n";
}
} // namespace

int main(int argc,char** argv) {
    try {
        const b::Template source(configuration());
        h::History history(source,c::DeckDefinition::reduced(deck));
        std::cout<<"VIRTUAL_DYADIC_STATE_V1\n";
        feedback(history,source);
        guards(history,source);
        action_catalog_controls(history,source);
        sealed_catalog_controls(history,source);
        packed_average_controls(history);
        packed_dual_controls(history);
        if (argc==2) {
            paged_image_controls(argv[1]);
            compact_directory_controls(history,source,argv[1]);
            paged_directory_controls(history,source,argv[1]);
            phase_payload_controls(history,source,argv[1]);
            row_coverage_controls(history,source,argv[1]);
            bounded_lifecycle_controls(history,source,argv[1]);
            proof9_t4_pager_controls();
            proof9_q32_controls(history,source,argv[1]);
            proof9_q32_pager_controls(argv[1]);
        }
        std::cout<<"END\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n';
        return 2;
    }
}
