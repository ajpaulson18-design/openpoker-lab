#pragma once
// Internal implementation of the single-board, two-responder exact staging walk.
#include <cmath>
#include <functional>
#include <string>
#include <set>
#include <tuple>
#include <type_traits>
#include <vector>

namespace openpoker::virtual_frozen_update {
struct FrozenUpdateRow {
  std::uint8_t actor = 0, first = 0, second = 0;
  std::vector<std::string> history, actions;
  std::vector<int> policy_exponents;
  std::vector<std::uint64_t> grid_policy_units;
  std::vector<CommonInteger> regret_numerators, average_numerators;
  CommonInteger average_denominator = 1, average_mass_numerator = 0;
};
struct FrozenUpdateStage {
  FrozenUpdateForecast forecast;
  CommonInteger regret_denominator = 1;
  std::vector<FrozenUpdateRow> rows;
  std::uint64_t prefix_fold_queries = 0, full_board_queries = 0;
  std::uint64_t chance_work = 0, history_work = 0, common_regret_work = 0,
                average_work = 0, policy_work = 0, prepared_rank_calls = 0;
};
inline FrozenUpdateStage
FrozenUpdate::run(FrozenGame &game, const std::array<std::uint8_t, 5> &board,
                  ProposalKind proposal, bool prefix_fold) {
  return walk<false>(game,board,proposal,prefix_fold,nullptr,SampledContraction::direct);
}
inline FrozenUpdateStage
FrozenUpdate::run_sampled(FrozenGame &game, const std::array<std::uint8_t,5> &board,
                          const sampled_row_state::State *committed, SampledContraction contraction) {
  return walk<true>(game,board,ProposalKind::uniform_public,true,committed,contraction);
}
template<bool Changing>
FrozenUpdateStage
FrozenUpdate::walk(FrozenGame &game, const std::array<std::uint8_t,5> &board,
                   ProposalKind proposal, bool prefix_fold, const sampled_row_state::State *committed,
                   SampledContraction contraction) {
  const auto f = forecast(game, board, proposal, prefix_fold, Changing, contraction);
  if (!f.admitted)
    throw FrozenUpdateError("whole frozen-update admission rejected");
  const auto &t = *game.template_;
  const auto law = proposal_for(game.deck_, board, proposal);
  const auto norm_bits = width(game.chance_->normalizer_integer());
  std::uint64_t maxneg = 0;
  for (const auto &node : t.nodes())
    if (node.state.phase == betting::Phase::fold ||
        node.state.phase == betting::Phase::showdown) {
      const auto pay =
          std::min(node.state.committed[0], node.state.committed[1]);
      const auto p =
          chance::prior::decode_parts(std::bit_cast<std::uint64_t>(pay), false,
                                      true, "invalid matched payoff");
      if (p.significand && p.exponent < 0)
        maxneg = std::max(maxneg, static_cast<std::uint64_t>(-p.exponent));
    }
  const auto shift = denominator_shift(Changing, f.reach_exponent_upper, maxneg);
  const auto n = game.deck_.count - 4;
  const auto divisor = static_cast<std::uint64_t>(n) * (n - 1) * (n - 2) / 6 *
                       (game.deck_.count - 7) * (game.deck_.count - 8);
  CommonDenominatorLimits math_limits;
  math_limits.work = f.arithmetic_work_upper - f.average_work_upper;
  math_limits.integer_bits = f.integer_bits_upper;
  const bool policy_replay=contraction==SampledContraction::dealt_policy_replay;
  const bool history_replay=policy_replay || contraction==SampledContraction::dealt_history_replay;
  const bool dealt=history_replay || contraction==SampledContraction::dealt;
  math_limits.word_work = contraction!=SampledContraction::direct;
  math_limits.temporary_payload_bits =
      game.limits_.integer_payload_bits -
      game.chance_->receipt().setup_integer_payload_bits;
  CommonDenominator math(game.chance_->normalizer_integer(), divisor,
                         law.board.numerator, static_cast<std::size_t>(shift),
                         math_limits);
  (void)norm_bits;
  std::optional<dyadic_policy::Quantizer> quantizer;
  if constexpr (Changing) {
    if (committed && (committed->failed() || committed->regret_denominator()!=math.denominator()))
      throw FrozenUpdateError("committed regret image cannot be used with this draw");
    dyadic_policy::Limits limits;
    limits.work=std::max<std::uint64_t>(1,f.policy_work_upper);
    limits.integer_bits=std::min<std::size_t>(65536,f.integer_bits_upper+dyadic_policy::grid_bits);
    quantizer.emplace(limits);
  }
  std::optional<prepared_public_chance::PreparedPublicChance> prepared;
  std::size_t prior_shift=0;
  if constexpr (Changing) {
    if (contraction!=SampledContraction::direct) {
      chance::Limits limits;
      limits.max_hands_per_side=game.limits_.max_hands_per_side;
      limits.max_modeled_work=f.chance_work_upper;
      limits.max_integer_bits=f.integer_bits_upper;
      limits.max_storage_entries=8192+64*(game.hands_[0].size()+game.hands_[1].size());
      limits.max_integer_payload_bits=limits.max_storage_entries*f.integer_bits_upper;
      prepared.emplace(game.hands_[0],game.hands_[1],game.deck_,limits,1);
      const auto reduced_bits=width(prepared->normalizer_integer());
      if (reduced_bits>norm_bits)
        throw FrozenUpdateError("prepared prior exceeds raw normalizer width");
      prior_shift=norm_bits-reduced_bits;
      if ((prepared->normalizer_integer()<<prior_shift)!=game.chance_->normalizer_integer())
        throw FrozenUpdateError("prepared and raw prior normalizers differ");
    }
  }
  const auto chance_before = game.chance_->receipt().modeled_work;
  const auto terminal_before = game.chance_->receipt().terminal_queries;
  const std::array<std::size_t, 4> lengths{0, 3, 4, 5};
  std::array<chance::PrefixResult, 4> prefixes;
  for (std::size_t k = 0; k < 4; ++k)
    prefixes[k] = game.chance_->prefix(
        std::span<const std::uint8_t>(board.data(), lengths[k]));
  if (dealt && (!prefixes.back().physical_support[0][0] || !prefixes.back().physical_support[1][0]))
    throw FrozenUpdateError("dealt board conflicts with its private holdings");
  HistoryLimits history_limits;
  history_limits.nodes = static_cast<std::size_t>(f.edge_occurrences + 1);
  history_limits.entries =
      game.limits_.entries - game.receipt_.retained_entries_upper;
  history_limits.work = f.history_work_upper;
  history_limits.depth = std::max<std::size_t>(1, t.receipt().max_depth);
  HistoryArena history(history_limits);
  struct Step {
    std::size_t parent, edge;
    HistoryArena::Cursor child;
  };
  std::vector<Step> steps;
  if (history_replay) steps.reserve(static_cast<std::size_t>(f.edge_occurrences));
  std::size_t replayed_steps=0;
  FrozenUpdateStage stage;
  stage.forecast = f;
  stage.regret_denominator = math.denominator();
  stage.rows.reserve(static_cast<std::size_t>(f.rows_upper));
  std::set<std::tuple<std::size_t, std::uint8_t, std::uint8_t, std::uint8_t>>
      seen;
  std::uint64_t staged_slots = 0, staged_text_upper = 0, average_work = 0, transport_work=0;
  struct GridReach {
    std::vector<CommonInteger> numerators;
    std::size_t exponent=0;
  };
  using Reach = std::conditional_t<Changing,GridReach,std::vector<int>>;
  using Policy = std::conditional_t<Changing,dyadic_policy::Policy,PowerPolicy>;
  struct SavedPolicy {
    std::size_t cursor;
    std::uint8_t actor;
    Policy policy;
  };
  std::vector<SavedPolicy> saved_policies;
  if (policy_replay) saved_policies.reserve(static_cast<std::size_t>(f.rows_upper));
  std::size_t replayed_policies=0;
  using Reaches = std::array<Reach,2>;
  Reaches initial;
  for (std::size_t p=0;p<2;++p) {
    if constexpr (Changing) initial[p].numerators.assign(game.hands_[p].size(),1);
    else initial[p].resize(game.hands_[p].size());
  }
  const auto prefix_index = [](std::uint8_t street) -> std::size_t {
    if (street == 0)
      return 0;
    if (street == 3)
      return 1;
    if (street == 4)
      return 2;
    if (street == 5)
      return 3;
    throw FrozenUpdateError("invalid visible street");
  };
  for (std::size_t target = 0; target < 2; ++target) {
    const auto transition=[&](HistoryArena::Cursor parent,std::size_t edge,auto append) {
      if (!history_replay) return append();
      const auto parent_id=history.ordinal(parent);
      if (target==0) {
        if (steps.size()>=f.edge_occurrences)
          throw FrozenUpdateError("history trace exceeded admitted edge count");
        const auto child=append();
        steps.push_back({parent_id,edge,child});
        return child;
      }
      if (replayed_steps>=steps.size())
        throw FrozenUpdateError("history replay exhausted its trace");
      const auto& step=steps[replayed_steps++];
      if (step.parent!=parent_id || step.edge!=edge)
        throw FrozenUpdateError("history replay transition differs from first visit");
      return step.child;
    };
    using Vector = std::vector<CommonInteger>;
    std::function<Vector(std::size_t, HistoryArena::Cursor, const Reaches &)>
        walk;
    walk = [&](std::size_t id, HistoryArena::Cursor cursor,
               const Reaches &reaches) -> Vector {
      const auto &node = t.nodes().at(id);
      const auto actor = node.state.actor;
      if (history.visible_size(cursor) != node.state.street)
        throw FrozenUpdateError("visible prefix and template street differ");
      if (node.state.phase == betting::Phase::fold ||
          node.state.phase == betting::Phase::showdown) {
        const auto opponent = 1 - target;
        std::vector<double> reach;
        CommonInteger reach_denominator;
        if constexpr (Changing) {
          if (!prepared) reach_denominator=CommonInteger(1)<<reaches[opponent].exponent;
        } else {
          reach.reserve(reaches[opponent].size());
          for (int e : reaches[opponent])
            reach.push_back(e < 0 ? 0.0 : std::ldexp(1.0, -e));
        }
        const auto matched =
            std::min(node.state.committed[0], node.state.committed[1]);
        const auto kind = node.state.phase == betting::Phase::fold
                              ? chance::TerminalKind::fold
                              : chance::TerminalKind::showdown;
        const double payoff =
            kind == chance::TerminalKind::fold && node.state.winner != target
                ? -matched
                : matched;
        chance::ExactVector vector;
        const auto via_prepared=[&]([[maybe_unused]] std::span<const std::uint8_t> prefix,
                                    [[maybe_unused]] std::uint64_t qden,
                                    [[maybe_unused]] std::uint64_t prefix_divisor) {
          Vector result;
          if constexpr (Changing) {
            const auto words=[](std::uint64_t bits) {return std::max<std::uint64_t>(1,(bits+63)/64);};
            const auto w=words(f.integer_bits_upper), copy=1+2*w, product=2+2*(w+1)+w;
            const auto cost=128+8*copy+game.hands_[target].size()*(64+2*product+4*copy);
            transport_work=add(transport_work,cost);
            if (transport_work>f.chance_work_upper-prepared->receipt().modeled_work)
              throw FrozenUpdateError("prepared transport exceeded its chance allowance");
            auto values=prepared->contraction(target,prefix,kind,reaches[opponent].numerators,
                                                reaches[opponent].exponent);
            const auto p=chance::prior::decode_parts(std::bit_cast<std::uint64_t>(payoff),true,true,
                                                      "invalid prepared matched payoff");
            if (values.prefix_divisor!=prefix_divisor ||
                values.reach_exponent!=reaches[opponent].exponent ||
                transport_work>f.chance_work_upper-prepared->receipt().modeled_work)
              throw FrozenUpdateError("prepared terminal scale or transport allowance differs");
            // Prior identity was authenticated once. Align the prepared
            // numerator straight to the walk's fixed denominator.
            const auto shift=static_cast<int>(math.shift())+static_cast<int>(prior_shift)
                +p.exponent-static_cast<int>(values.reach_exponent);
            if (shift<0) throw FrozenUpdateError("prepared terminal lacks exact scale");
            result=std::move(values.numerators);
            for (auto &value:result) {
              value*=p.significand;
              value*=qden;
              value<<=static_cast<unsigned>(shift);
              if (payoff<0) value=-value;
            }
          }
          return result;
        };
        if (prefix_fold && kind==chance::TerminalKind::fold) {
          const auto length=static_cast<std::size_t>(node.state.street);
          const auto p=prefix_index(node.state.street);
          const std::uint64_t a=game.deck_.count-4;
          const std::uint64_t flop=a*(a-1)*(a-2)/6;
          const std::uint64_t prefix_divisor=length==0?1:length==3?flop:
              length==4?flop*(game.deck_.count-7):divisor;
          if (!prefix_divisor || divisor%prefix_divisor || law.prefix[p].numerator!=1)
            throw FrozenUpdateError("invalid prefix fold factor");
          const auto factor=divisor/prefix_divisor;
          const auto qden=dealt ? divisor : mul(law.prefix[p].denominator,factor);
          if (qden>law.board.denominator)
            throw FrozenUpdateError("prefix proposal exceeds forecast width");
          const auto prefix=std::span<const std::uint8_t>(board.data(),length);
          ++stage.prefix_fold_queries;
          if constexpr (Changing) {
            if (prepared) return via_prepared(prefix,qden,prefix_divisor);
            vector=game.chance_->sampled_fold_prefix_exact_reach(target,prefix,payoff,
                    reaches[opponent].numerators,reach_denominator,CommonInteger(factor),CommonInteger(qden));
          } else
            vector=game.chance_->sampled_fold_prefix_dyadic_reach(target,prefix,payoff,reach,
                CommonInteger(factor),CommonInteger(qden));
        } else {
          ++stage.full_board_queries;
          if constexpr (Changing) {
            if (prepared) return via_prepared(board,dealt ? divisor : law.board.denominator,divisor);
            vector=game.chance_->terminal_exact_reach(target,board,kind,payoff,
                    reaches[opponent].numerators,reach_denominator,
                    CommonInteger(law.board.numerator),CommonInteger(law.board.denominator));
          } else
            vector=game.chance_->terminal(target,board,kind,payoff,reach,
                CommonInteger(law.board.numerator),CommonInteger(law.board.denominator));
        }
        Vector result;
        result.reserve(vector.numerators.size());
        for (const auto &x : vector.numerators)
          result.push_back(math.scale_terminal(x, vector.denominator));
        return result;
      }
      if (node.state.phase == betting::Phase::reveal) {
        if (node.edges.size() != 1)
          throw FrozenUpdateError("invalid reveal edge count");
        const auto count = static_cast<std::size_t>(node.state.next_street);
        const auto child=transition(cursor,0,[&] {
          return history.append_reveal(cursor,std::span<const std::uint8_t>(board.data(),count));
        });
        return walk(node.edges[0].child, child, reaches);
      }
      if (node.state.phase != betting::Phase::decision || actor > 1 ||
          node.edges.empty())
        throw FrozenUpdateError("invalid decision node");
      std::vector<Policy> constructed;
      std::span<const Policy> policies;
      if constexpr (Changing) {
        if (policy_replay && target==1) {
          if (replayed_policies>=saved_policies.size())
            throw FrozenUpdateError("policy replay exhausted its trace");
          const auto& saved=saved_policies[replayed_policies++];
          if (saved.cursor!=history.ordinal(cursor) || saved.actor!=actor ||
              saved.policy.size()!=node.edges.size())
            throw FrozenUpdateError("policy replay differs from first responder");
          policies={&saved.policy,1};
        } else {
          if (!policy_replay) constructed.reserve(game.hands_[actor].size());
          sampled_row_state::Key key{actor,0,0,history.materialize(cursor)};
          std::array<CommonInteger,dyadic_policy::maximum_actions> zero{};
          for (const auto &row : game.hands_[actor]) {
            key.first_card=row.hand.first;
            key.second_card=row.hand.second;
            const auto previous=committed ? committed->committed_row(key) : std::nullopt;
            if (previous && !std::ranges::equal(previous->actions,node.edges,{},
                                                std::identity{},[](const auto &edge)->const auto& {
                                                  return edge.action.token;
                                                }))
              throw FrozenUpdateError("committed row ordered menu differs");
            const std::span<const CommonInteger> regrets=previous ? previous->regrets :
                std::span<const CommonInteger>(zero.data(),node.edges.size());
            auto policy=quantizer->regret_policy(regrets);
            if (policy_replay) {
              if (saved_policies.size()>=f.rows_upper)
                throw FrozenUpdateError("policy trace exceeded admitted row count");
              saved_policies.push_back({history.ordinal(cursor),actor,std::move(policy)});
              policies={&saved_policies.back().policy,1};
            } else {
              constructed.push_back(std::move(policy));
            }
          }
          if (!policy_replay) policies=constructed;
        }
      } else {
        constructed.reserve(game.hands_[actor].size());
        for (const auto &row : game.hands_[actor])
          constructed.push_back(frozen_power_policy(history,cursor,actor,
                                                   row.hand.first,row.hand.second,node.edges.size()));
        policies=constructed;
      }
      const auto row_begin = stage.rows.size();
      if (actor == target) {
        const auto p = prefix_index(node.state.street);
        const auto &snapshot = prefixes[p];
        const auto lengths_remaining=game.deck_.count-4;
        const auto flop_count=static_cast<std::uint64_t>(lengths_remaining)*(lengths_remaining-1)*(lengths_remaining-2)/6;
        const std::array<std::uint64_t,4> dealt_inverse{1,flop_count,flop_count*(game.deck_.count-7),divisor};
        const auto ratio=dealt ? SmallRatio{1,dealt_inverse[p]} : law.prefix[p];
        for (std::size_t i = 0; i < policies.size(); ++i) {
          if (!snapshot.physical_support[target][i])
            continue;
          if (stage.rows.size() >= f.rows_upper ||
              node.edges.size() > f.slots_upper - staged_slots)
            throw FrozenUpdateError(
                "staged row or action slot exceeds preflight");
          const auto text_upper =
              add(mul(64, history.depth(cursor)), mul(64, node.edges.size()));
          if (text_upper > f.retained_text_bytes_upper - staged_text_upper)
            throw FrozenUpdateError("staged retained text exceeds preflight");
          staged_slots += node.edges.size();
          staged_text_upper += text_upper;
          const auto avg_cost=average_row_work(f.integer_bits_upper,node.edges.size(),bool(prepared));
          if (avg_cost > f.average_work_upper - average_work)
            throw FrozenUpdateError("average arithmetic exceeds preflight");
          average_work += avg_cost;
          FrozenUpdateRow row;
          row.actor = static_cast<std::uint8_t>(target);
          row.first = game.hands_[target][i].hand.first;
          row.second = game.hands_[target][i].hand.second;
          if (!seen.emplace(history.ordinal(cursor), row.actor, row.first,
                            row.second)
                   .second)
            throw FrozenUpdateError("duplicate full-history row");
          row.history = history.materialize(cursor);
          row.actions.reserve(node.edges.size());
          if constexpr (Changing) {
            const auto units=policies[i].units();
            row.grid_policy_units.assign(units.begin(),units.end());
          } else {
            row.policy_exponents.reserve(node.edges.size());
          }
          row.regret_numerators.resize(node.edges.size());
          row.average_numerators.resize(node.edges.size());
          int maxexp = 0;
          for (std::size_t a = 0; a < node.edges.size(); ++a) {
            row.actions.push_back(node.edges[a].action.token);
            if constexpr (!Changing) {
              row.policy_exponents.push_back(policies[i].exponent[a]);
              maxexp = std::max(maxexp, policies[i].exponent[a]);
            }
          }
          if constexpr (Changing) {
            const auto &own=reaches[target];
            CommonInteger base=snapshot.hand_masses[target].numerators[i]*ratio.denominator;
            base*=own.numerators[i];
            row.average_denominator=(snapshot.denominator*ratio.numerator)
                                     <<(own.exponent+dyadic_policy::grid_bits);
            row.average_mass_numerator=base<<dyadic_policy::grid_bits;
            for (std::size_t a=0;a<node.edges.size();++a)
              row.average_numerators[a]=base*row.grid_policy_units[a];
          } else {
            const int own = reaches[target][i];
            const int e = own < 0 ? 0 : own;
            row.average_denominator = (snapshot.denominator * ratio.numerator)
                                      << (e + maxexp);
            if (own >= 0) {
              const CommonInteger base =
                  snapshot.hand_masses[target].numerators[i] * ratio.denominator;
              row.average_mass_numerator = base << maxexp;
              for (std::size_t a = 0; a < node.edges.size(); ++a)
                if (policies[i].exponent[a] >= 0)
                  row.average_numerators[a] =
                      base << (maxexp - policies[i].exponent[a]);
            }
          }
          stage.rows.push_back(std::move(row));
        }
      }
      std::vector<Vector> children;
      children.reserve(node.edges.size());
      for (std::size_t a = 0; a < node.edges.size(); ++a) {
        auto next = reaches;
        if constexpr (Changing) {
          auto &side=next[actor];
          unsigned common=dyadic_policy::grid_bits;
          for (std::size_t i=0;i<side.numerators.size();++i) {
            const auto units=policies[i].units()[a];
            if (side.numerators[i]!=0 && units)
              common=std::min(common,static_cast<unsigned>(std::countr_zero(units)));
          }
          side.exponent+=dyadic_policy::grid_bits-common;
          if (side.exponent>f.reach_exponent_upper)
            throw FrozenUpdateError("grid sequence reach exceeds admission");
          for (std::size_t i=0;i<side.numerators.size();++i)
            side.numerators[i]*=policies[i].units()[a]>>common;
        } else for (std::size_t i = 0; i < next[actor].size(); ++i) {
          const auto e = policies[i].exponent[a];
          if (next[actor][i] < 0 || e < 0)
            next[actor][i] = -1;
          else {
            next[actor][i] += e;
            if (next[actor][i] > 1022)
              throw FrozenUpdateError("reach exponent overflow");
          }
        }
        const auto child=transition(cursor,a,[&] {
          return history.append_action(cursor,node.edges[a].action.token);
        });
        children.push_back(walk(node.edges[a].child, child, next));
      }
      Vector mixed(game.hands_[target].size());
      for (std::size_t i = 0; i < mixed.size(); ++i)
        for (std::size_t a = 0; a < children.size(); ++a) {
          if (actor == target) {
            if constexpr (Changing) {
              mixed[i]=math.add(mixed[i],math.weight_grid(children[a][i],policies[i].units()[a]));
            } else {
              const int e = policies[i].exponent[a];
              if (e < 0)
                continue;
              mixed[i] = math.add(
                  mixed[i], math.divide_power_two(children[a][i],
                                                  static_cast<std::size_t>(e)));
            }
          } else
            mixed[i] = math.add(mixed[i], children[a][i]);
        }
      if (actor == target) {
        std::size_t r = row_begin;
        const auto p = prefix_index(node.state.street);
        for (std::size_t i = 0; i < mixed.size(); ++i)
          if (prefixes[p].physical_support[target][i]) {
            // Descendants were appended after this node's rows; row_begin remains stable by index.
            auto &row = stage.rows[r++];
            for (std::size_t a = 0; a < children.size(); ++a)
              row.regret_numerators[a] =
                  math.subtract(children[a][i], mixed[i]);
          }
      }
      return mixed;
    };
    (void)walk(t.root(), history.root(), initial);
  }
  if (prefix_fold && (stage.prefix_fold_queries+stage.full_board_queries!=2*f.terminal_occurrences ||
      (prepared ? prepared->receipt().completed_contractions
                : game.chance_->receipt().terminal_queries-terminal_before)!=
          stage.prefix_fold_queries+stage.full_board_queries))
    throw FrozenUpdateError("prefix/full terminal query census differs");
  stage.chance_work = game.chance_->receipt().modeled_work - chance_before;
  if (prepared) {
    stage.chance_work=add(stage.chance_work,add(prepared->receipt().modeled_work,transport_work));
    stage.prepared_rank_calls=prepared->receipt().rank_calls;
  }
  if (history_replay && (steps.size()!=f.edge_occurrences || replayed_steps!=steps.size()))
    throw FrozenUpdateError("incomplete history transition census");
  stage.history_work=add(history.receipt().work,mul(64,replayed_steps));
  stage.common_regret_work = math.receipt().work;
  stage.average_work = average_work;
  if (policy_replay && (saved_policies.size()!=f.rows_upper ||
                        replayed_policies!=saved_policies.size()))
    throw FrozenUpdateError("incomplete sampled policy trace");
  if constexpr (Changing)
    stage.policy_work=add(quantizer->receipt().work,mul(128,replayed_policies));
  if (stage.rows.size() > f.rows_upper ||
      stage.chance_work > f.chance_work_upper ||
      stage.history_work > f.history_work_upper ||
      stage.common_regret_work >
          f.arithmetic_work_upper - f.average_work_upper ||
      stage.average_work > f.average_work_upper ||
      stage.policy_work > f.policy_work_upper)
    throw FrozenUpdateError("actual update counters exceeded preflight");
  return stage;
}
} // namespace openpoker::virtual_frozen_update
