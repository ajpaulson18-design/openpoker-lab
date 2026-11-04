#pragma once
// Internal implementation of the single-board, two-responder exact staging walk.
#include <cmath>
#include <functional>
#include <string>
#include <set>
#include <tuple>
#include <vector>

namespace openpoker::virtual_frozen_update {
struct FrozenUpdateRow {
  std::uint8_t actor = 0, first = 0, second = 0;
  std::vector<std::string> history, actions;
  std::vector<int> policy_exponents;
  std::vector<CommonInteger> regret_numerators, average_numerators;
  CommonInteger average_denominator = 1, average_mass_numerator = 0;
};
struct FrozenUpdateStage {
  FrozenUpdateForecast forecast;
  CommonInteger regret_denominator = 1;
  std::vector<FrozenUpdateRow> rows;
  std::uint64_t chance_work = 0, history_work = 0, common_regret_work = 0,
                average_work = 0;
};
inline FrozenUpdateStage
FrozenUpdate::run(FrozenGame &game, const std::array<std::uint8_t, 5> &board,
                  ProposalKind proposal) {
  const auto f = forecast(game, board, proposal);
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
  const auto shift = add(add(52, mul(2, f.reach_exponent_upper)), maxneg);
  const auto n = game.deck_.count - 4;
  const auto divisor = static_cast<std::uint64_t>(n) * (n - 1) * (n - 2) / 6 *
                       (game.deck_.count - 7) * (game.deck_.count - 8);
  CommonDenominatorLimits math_limits;
  math_limits.work = f.arithmetic_work_upper - f.average_work_upper;
  math_limits.integer_bits = f.integer_bits_upper;
  math_limits.temporary_payload_bits =
      game.limits_.integer_payload_bits -
      game.chance_->receipt().setup_integer_payload_bits;
  CommonDenominator math(game.chance_->normalizer_integer(), divisor,
                         law.board.numerator, static_cast<std::size_t>(shift),
                         math_limits);
  (void)norm_bits;
  const auto chance_before = game.chance_->receipt().modeled_work;
  const std::array<std::size_t, 4> lengths{0, 3, 4, 5};
  std::array<chance::PrefixResult, 4> prefixes;
  for (std::size_t k = 0; k < 4; ++k)
    prefixes[k] = game.chance_->prefix(
        std::span<const std::uint8_t>(board.data(), lengths[k]));
  HistoryLimits history_limits;
  history_limits.nodes = static_cast<std::size_t>(f.edge_occurrences + 1);
  history_limits.entries =
      game.limits_.entries - game.receipt_.retained_entries_upper;
  history_limits.work = f.history_work_upper;
  history_limits.depth = std::max<std::size_t>(1, t.receipt().max_depth);
  HistoryArena history(history_limits);
  FrozenUpdateStage stage;
  stage.forecast = f;
  stage.regret_denominator = math.denominator();
  stage.rows.reserve(static_cast<std::size_t>(f.rows_upper));
  std::set<std::tuple<std::size_t, std::uint8_t, std::uint8_t, std::uint8_t>>
      seen;
  std::uint64_t staged_slots = 0, staged_text_upper = 0, average_work = 0;
  using Reaches = std::array<std::vector<int>, 2>;
  const Reaches initial{std::vector<int>(game.hands_[0].size(), 0),
                        std::vector<int>(game.hands_[1].size(), 0)};
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
        reach.reserve(reaches[opponent].size());
        for (int e : reaches[opponent])
          reach.push_back(e < 0 ? 0.0 : std::ldexp(1.0, -e));
        const auto matched =
            std::min(node.state.committed[0], node.state.committed[1]);
        const auto kind = node.state.phase == betting::Phase::fold
                              ? chance::TerminalKind::fold
                              : chance::TerminalKind::showdown;
        const double payoff =
            kind == chance::TerminalKind::fold && node.state.winner != target
                ? -matched
                : matched;
        const auto vector =
            game.chance_->terminal(target, board, kind, payoff, reach,
                                   CommonInteger(law.board.numerator),
                                   CommonInteger(law.board.denominator));
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
        const auto child = history.append_reveal(
            cursor, std::span<const std::uint8_t>(board.data(), count));
        return walk(node.edges[0].child, child, reaches);
      }
      if (node.state.phase != betting::Phase::decision || actor > 1 ||
          node.edges.empty())
        throw FrozenUpdateError("invalid decision node");
      std::vector<PowerPolicy> policies;
      policies.reserve(game.hands_[actor].size());
      for (const auto &row : game.hands_[actor])
        policies.push_back(frozen_power_policy(history, cursor, actor,
                                               row.hand.first, row.hand.second,
                                               node.edges.size()));
      const auto row_begin = stage.rows.size();
      if (actor == target) {
        const auto p = prefix_index(node.state.street);
        const auto &snapshot = prefixes[p];
        const auto ratio = law.prefix[p];
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
          const auto avg_cost = add(
              add(mul(128, f.integer_bits_upper), 4096),
              mul(node.edges.size(), add(mul(32, f.integer_bits_upper), 1024)));
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
          row.policy_exponents.reserve(node.edges.size());
          row.regret_numerators.resize(node.edges.size());
          row.average_numerators.resize(node.edges.size());
          int maxexp = 0;
          for (std::size_t a = 0; a < node.edges.size(); ++a) {
            row.actions.push_back(node.edges[a].action.token);
            row.policy_exponents.push_back(policies[i].exponent[a]);
            maxexp = std::max(maxexp, policies[i].exponent[a]);
          }
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
          stage.rows.push_back(std::move(row));
        }
      }
      std::vector<Vector> children;
      children.reserve(node.edges.size());
      for (std::size_t a = 0; a < node.edges.size(); ++a) {
        auto next = reaches;
        for (std::size_t i = 0; i < next[actor].size(); ++i) {
          const auto e = policies[i].exponent[a];
          if (next[actor][i] < 0 || e < 0)
            next[actor][i] = -1;
          else {
            next[actor][i] += e;
            if (next[actor][i] > 1022)
              throw FrozenUpdateError("reach exponent overflow");
          }
        }
        auto child = history.append_action(cursor, node.edges[a].action.token);
        children.push_back(walk(node.edges[a].child, child, next));
      }
      Vector mixed(game.hands_[target].size());
      for (std::size_t i = 0; i < mixed.size(); ++i)
        for (std::size_t a = 0; a < children.size(); ++a) {
          if (actor == target) {
            const int e = policies[i].exponent[a];
            if (e < 0)
              continue;
            mixed[i] = math.add(
                mixed[i], math.divide_power_two(children[a][i],
                                                static_cast<std::size_t>(e)));
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
  stage.chance_work = game.chance_->receipt().modeled_work - chance_before;
  stage.history_work = history.receipt().work;
  stage.common_regret_work = math.receipt().work;
  stage.average_work = average_work;
  if (stage.rows.size() > f.rows_upper ||
      stage.chance_work > f.chance_work_upper ||
      stage.history_work > f.history_work_upper ||
      stage.common_regret_work >
          f.arithmetic_work_upper - f.average_work_upper ||
      stage.average_work > f.average_work_upper)
    throw FrozenUpdateError("actual update counters exceeded preflight");
  return stage;
}
} // namespace openpoker::virtual_frozen_update
