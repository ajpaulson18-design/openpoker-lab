#include "../../native/virtual_dyadic_state.hpp"
#include <algorithm>
#include <array>
#include <iostream>
#include <string>
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
} // namespace

int main() {
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
        std::cout<<"END\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n';
        return 2;
    }
}
