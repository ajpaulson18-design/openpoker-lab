#pragma once
// Scoped role facade: the existing sparse Store remains the only policy owner.
// This is not a recursive-walk completeness proof or a longer learning contract.
#include "virtual_sparse_strategy_epoch.hpp"
#include "prepared_public_chance.hpp"
#include <functional>
#include <memory>
#include <tuple>

namespace openpoker::virtual_opponent_role_epoch {
namespace e=virtual_sparse_strategy_epoch;
namespace h=virtual_dyadic_history;
namespace c=virtual_strategy_catalog;
namespace p=prepared_public_chance;
using Integer=e::Integer;
using Certificate=p::PreparedPublicChance::JointTicketCertificate;
using Key=std::tuple<std::size_t,std::size_t,std::size_t>;
inline constexpr std::size_t maximum_rows=204,maximum_slots=816,maximum_encounters=204;

struct Limits {
    std::size_t rows=maximum_rows,slots=maximum_slots,encounters=maximum_encounters;
    std::size_t catalog_blocks=408,holding_count=1326;
    std::uint64_t work=e::work_cap;
    std::size_t entries=e::entries_cap,payload_bits=e::payload_bits_cap;
};
struct Forecast {
    e::Limits storage_limits{};
    e::Forecast storage{};
    std::uint64_t own_work=0,extra_history_work=0,work=0;
    std::size_t cache_entries=0,cache_payload_bits=0,entries=0,payload_bits=0;
};
inline void require(bool condition,const char* message) {
    if(!condition)throw std::runtime_error(message);
}
inline std::uint64_t observe_work(std::size_t rows) {return 512+64*std::bit_width(rows+1);}
inline Forecast forecast(Limits l) {
    require(l.rows && l.rows<=maximum_rows && l.slots>=2 && l.slots<=maximum_slots &&
        l.encounters>=2 && l.encounters<=maximum_encounters && l.catalog_blocks && l.catalog_blocks<=408 &&
        l.holding_count && l.holding_count<=1326 && l.work && l.work<=e::work_cap &&
        l.entries && l.entries<=e::entries_cap && l.payload_bits && l.payload_bits<=e::payload_bits_cap,
        "role epoch reduce-only limits");
    Forecast f;auto& s=f.storage_limits;
    s.max_stage_rows=l.rows;s.max_stage_slots=l.slots;s.max_rows_touched=2*l.rows;s.max_slots_touched=2*l.slots;
    s.policy_reads_per_row=1;s.max_reads=2*l.rows;s.catalog_max_public_blocks=l.catalog_blocks;
    s.catalog_max_holding_count=l.holding_count;s.max_work=l.work;s.max_entries=l.entries;s.max_payload_bits=l.payload_bits;
    f.storage=e::forecast(s);
    // Per step: begin, every observed role, stage + directory release, two
    // target seals, one raw seal and commit. Exports are separately bounded.
    f.own_work=512+2*(256+l.encounters*observe_work(l.rows)+l.rows*(4096+128)+512+256+256)+2*256;
    // decision_key (32), visible_size (8), visible_board (8), per role visit.
    f.extra_history_work=2*l.encounters*48;
    f.cache_entries=256+64*l.rows;
    f.cache_payload_bits=64*f.cache_entries+2*(4*630+4*365+425);
    f.work=f.storage.work+f.own_work+f.extra_history_work;
    f.entries=f.storage.entries+f.cache_entries;f.payload_bits=f.storage.payload_bits+f.cache_payload_bits;
    require(f.work<=l.work && f.entries<=l.entries && f.payload_bits<=l.payload_bits,
        "role epoch combined Store/cache/History forecast rejected");
    return f;
}
struct Receipt {
    std::uint64_t own_work=0,encounters=0,frozen_reads=0,cache_hits=0,staged_rows=0,staged_slots=0,commits=0;
    std::size_t peak_cache_rows=0,peak_cache_slots=0;
};
class Store final {
    struct Identity final {};
public:
    class Epoch;
    class Token final {
        friend class Epoch;
        std::shared_ptr<const Identity> owner_;
        std::uint64_t generation_=0;
        Key key_{};
        c::RowId id_{};
        Token(std::shared_ptr<const Identity> owner,std::uint64_t generation,Key key,c::RowId id)
            :owner_(std::move(owner)),generation_(generation),key_(key),id_(id) {}
    public:
        Token()=default;
    };
    struct Row {
        Token token;
        e::FrozenRow descriptor;
        std::span<const std::uint64_t> units;
        std::uint8_t roles=0;
    };
private:
    struct Cached {
        e::FrozenPolicyView view;
        std::size_t source=0;
        std::uint8_t roles=0;
        bool staged=false;
    };
    static_assert(sizeof(Cached)+sizeof(Key)+64<=64*sizeof(std::uint64_t),"role cache node reservation");
    const Limits limits_;
    const Forecast forecast_;
    h::History& history_;
    p::PreparedPublicChance& chance_;
    const std::array<std::size_t,2> hands_;
    const std::shared_ptr<const Identity> identity_;
    e::Store storage_;
    Receipt receipt_{};
    std::uint64_t generation_=0;
    bool active_=false,failed_=false,visiting_=false;
    static Limits admit(c::Catalog& catalog,h::History& history,p::PreparedPublicChance& chance,std::array<std::size_t,2> hands,Limits l) {
        (void)forecast(l);
        require(hands[0] && hands[1] && hands[0]<=l.holding_count && hands[1]<=l.holding_count &&
            !catalog.failed() && catalog.owns_identity(history,hands) && !chance.failed() &&
            chance.purpose()==p::Purpose::joint_tickets_v1 && chance.declared_hand_counts()==hands &&
            catalog.admitted_limits().seen_storage==c::Limits::SeenStorage::eager_bitmap,
            "role epoch same eager Catalog/History/range owner required");
        return l;
    }
    void healthy() const {require(!failed_ && !storage_.failed() && !chance_.failed(),"role epoch owner failed closed");}
    void charge(std::uint64_t amount) {
        require(amount<=forecast_.own_work-receipt_.own_work,"role epoch own work exhausted");receipt_.own_work+=amount;
    }
public:
    Store(c::Catalog& catalog,h::History& history,p::PreparedPublicChance& chance,std::array<std::size_t,2> hands,Limits limits={})
        :limits_(admit(catalog,history,chance,hands,limits)),forecast_(forecast(limits_)),history_(history),chance_(chance),hands_(hands),
         identity_(std::make_shared<Identity>()),
         storage_(catalog,history,hands,forecast_.storage_limits,e::ArithmeticContract::weighted_joint_single_pass) {charge(512);}
    Store(const Store&)=delete;Store& operator=(const Store&)=delete;
    [[nodiscard]] bool failed() const {return failed_ || storage_.failed() || chance_.failed();}
    [[nodiscard]] const Receipt& receipt() const {return receipt_;}
    [[nodiscard]] const e::Receipt& storage_receipt() const {return storage_.receipt();}
    [[nodiscard]] const Forecast& admitted_forecast() const {return forecast_;}
    [[nodiscard]] const std::array<std::size_t,2>& declared_hand_counts() const {return hands_;}

    class Epoch final {
        friend class Store;
        Store& owner_;
        const Certificate& certificate_;
        const std::uint64_t generation_;
        e::Store::EpochLease lease_;
        std::map<Key,Cached> cache_;
        std::array<std::size_t,2> target_counts_{};
        std::size_t target_=0,encounters_=0,slots_=0,staged_=0;
        bool sealed_=false,closed_=false,enumerated_=false;
        Epoch(Store& owner,const Certificate& certificate)
            :owner_(owner),certificate_(certificate),generation_(owner.generation_),
             lease_(owner.storage_.begin_epoch(e::ProposalLaw::true_joint)) {}
        void check() const {
            owner_.healthy();require(owner_.active_ && !closed_ && generation_==owner_.generation_,"stale role epoch lease");
            certificate_.require_active();
        }
        Row row(const Key& key,const Cached& cached) const {
            return {Token(owner_.identity_,generation_,key,cached.view.id),cached.view.row,cached.view.units,cached.roles};
        }
        void complete() {
            check();require(target_==2 && sealed_ && staged_==cache_.size(),"role epoch incomplete staging");
            lease_=e::Store::EpochLease{};closed_=true;
        }
    public:
        Epoch(const Epoch&)=delete;Epoch& operator=(const Epoch&)=delete;
        Epoch(Epoch&&)=delete;Epoch& operator=(Epoch&&)=delete;
        // Views borrow the existing current Store image, valid only during
        // this callback. Tokens are values but revalidate owner + generation.
        Row observe(h::History::Cursor cursor,std::size_t actor,std::size_t holding) {
            try {
                check();require(!sealed_ && target_<2 && actor<2 && holding==certificate_.holding_indices()[actor],
                    "role epoch actor/selected holding/phase");
                require(encounters_<owner_.limits_.encounters && owner_.receipt_.encounters<2*owner_.limits_.encounters,
                    "role epoch role encounter bound");
                owner_.charge(observe_work(owner_.limits_.rows));
                const auto info=owner_.history_.decision_key(cursor);
                const auto visible=owner_.history_.visible_size(cursor);const auto board=owner_.history_.visible_board(cursor);
                require(info.actor==actor && info.actions>=2 && info.actions<=4 && visible<=5 &&
                    std::equal(board.begin(),board.begin()+visible,certificate_.board().begin()),"role epoch certified visible information");
                const Key key{actor,holding,info.ordinal};auto found=cache_.find(key);
                if(found==cache_.end()) {
                    require(cache_.size()<owner_.limits_.rows && info.actions<=owner_.limits_.slots-slots_,"role epoch cache row/slot bound");
                    const auto view=lease_.frozen_policy(cursor,actor,holding);
                    require(view.row.actor==actor && view.row.holding_index==holding && view.row.history_ordinal==info.ordinal &&
                        view.units.size()==info.actions,"role epoch borrowed full row identity");
                    found=cache_.emplace(key,Cached{view,info.source,0,false}).first;
                    slots_+=info.actions;++owner_.receipt_.frozen_reads;
                    owner_.receipt_.peak_cache_rows=std::max(owner_.receipt_.peak_cache_rows,cache_.size());
                    owner_.receipt_.peak_cache_slots=std::max(owner_.receipt_.peak_cache_slots,slots_);
                } else ++owner_.receipt_.cache_hits;
                auto& cached=found->second;const auto bit=static_cast<std::uint8_t>(1U<<target_);
                require(cached.source==info.source && cached.view.units.size()==info.actions && !(cached.roles&bit),
                    "role epoch duplicate role or changed menu");
                cached.roles|=bit;++target_counts_[target_];++encounters_;++owner_.receipt_.encounters;
                return row(key,cached);
            }catch(...){owner_.failed_=true;throw;}
        }
        void finish_target(std::size_t target) {
            try {
                check();require(!sealed_ && target==target_ && target<2 && target_counts_[target],"role epoch target completion order");
                const Key root{0,certificate_.holding_indices()[0],0};const auto found=cache_.find(root);
                require(found!=cache_.end() && (found->second.roles&(1U<<target)),"role epoch target did not visit certified root");
                owner_.charge(256);++target_;
            }catch(...){owner_.failed_=true;throw;}
        }
        void seal() {
            try {
                check();require(target_==2 && !sealed_ && !cache_.empty(),"role epoch both targets required before seal");
                owner_.charge(256+128*cache_.size());
                lease_.seal_raw_walk(cache_.size(),slots_,cache_.size());sealed_=true;
            }catch(...){owner_.failed_=true;throw;}
        }
        template<class Callback> void consume_rows(Callback&& callback) {
            try {
                check();require(sealed_ && !enumerated_,"role epoch row enumeration phase");enumerated_=true;
                for(const auto& [key,cached]:cache_)callback(row(key,cached));
            }catch(...){owner_.failed_=true;throw;}
        }
        void stage(const Token& token,std::span<const Integer> regrets,std::span<const std::uint64_t> averages) {
            try {
                check();require(sealed_ && token.owner_==owner_.identity_ && token.generation_==generation_,"role epoch foreign/stale row token");
                const auto found=cache_.find(token.key_);
                require(found!=cache_.end() && found->second.view.id==token.id_ && !found->second.staged,
                    "role epoch unknown or duplicate stage");
                auto& cached=found->second;const auto k=cached.view.units.size();const auto actor=cached.view.row.actor;
                require(regrets.size()==k && averages.size()==k,"role epoch staged menu");owner_.charge(4096);
                const Integer dr=Integer(1)<<365;Integer dot=0;
                for(std::size_t a=0;a<k;++a) {
                    require(e::magnitude_bits(regrets[a])<=370 && regrets[a]>=-16*dr && regrets[a]<=16*dr &&
                        ((cached.roles&(1U<<actor)) || regrets[a]==0),"role epoch unvisited/overbound regret");
                    const auto expected=(cached.roles&(1U<<(1-actor)))?cached.view.units[a]:0;
                    require(averages[a]==expected,"role epoch average differs from authorized frozen units");
                    dot+=regrets[a]*cached.view.units[a];require(e::magnitude_bits(dot)<=424,"role epoch regret center intermediate");
                }
                require(dot==0,"role epoch regret not centered");
                std::array<Integer,4> rr{},aa{};
                for(std::size_t a=0;a<k;++a){rr[a]=regrets[a]<<260;aa[a]=Integer(averages[a])<<312;}
                lease_.stage(token.id_,std::span(rr).first(k),std::span(aa).first(k),
                    owner_.storage_.average_denominator_value(),owner_.storage_.regret_denominator_value());
                cached.staged=true;++staged_;++owner_.receipt_.staged_rows;owner_.receipt_.staged_slots+=k;
            }catch(...){owner_.failed_=true;throw;}
        }
        [[nodiscard]] std::size_t current_target() const {check();return target_;}
    };

    template<class Callback> void apply_world(std::uint64_t private_ticket,std::uint64_t board_rank,Callback&& callback) {
        static_assert(std::is_void_v<std::invoke_result_t<Callback,Epoch&,const Certificate&>>,"role epoch callback returns no borrowed state");
        try {
            healthy();require(!active_ && !visiting_ && storage_.committed_epochs()<2,"role epoch active/reentrant/lifetime");
            charge(256);++generation_;active_=true;
            // The bound chance owner creates the only admissible certificate.
            // Neither the certificate nor a movable lease leaves this callback.
            chance_.with_joint_ticket(private_ticket,board_rank,[&](const Certificate& certificate) {
                certificate.require_active();require(certificate.purpose()==p::Purpose::joint_tickets_v1 &&
                    certificate.declared_hand_counts()==hands_ && history_.supports_deck(certificate.deck()),"role epoch certificate/range/deck binding");
                Epoch epoch(*this,certificate);callback(epoch,certificate);epoch.complete();
            });
            // Publish only after Prepared has also accepted callback completion.
            healthy();
            charge(256);storage_.commit();++receipt_.commits;active_=false;
        }catch(...){failed_=true;active_=false;throw;}
    }
    template<class Callback> void visit_committed(Callback&& callback) {
        try {
            healthy();require(!active_ && !visiting_,"role epoch export while active");charge(256);visiting_=true;
            storage_.visit_committed(std::forward<Callback>(callback));visiting_=false;
        }catch(...){failed_=true;visiting_=false;throw;}
    }
};
}
