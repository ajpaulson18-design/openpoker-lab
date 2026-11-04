// Focused controls for the experimental frozen-update component.
// These controls do not constitute a full-game proof or a quality certificate.
#include "virtual_frozen_update.hpp"
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <new>
#include <stdexcept>
#include <string>

using namespace openpoker::virtual_frozen_update;
namespace {
void require(bool condition, const char *message) {
  if (!condition)
    throw std::runtime_error(message);
}
template <class Exception, class Function>
void rejects(Function &&fn, const char *message) {
  try {
    fn();
  } catch (const Exception &) {
    return;
  }
  throw std::runtime_error(message);
}
struct Fixture {
  betting::Config config;
  chance::DeckDefinition deck;
  std::array<chance::WeightedHand, 1> sb;
  std::array<chance::WeightedHand, 1> bb;
  Fixture() {
    config.stacks = {2, 2};
    config.sb = .5;
    config.bb = 1;
    config.stages[0].raises = {1};
    config.stages[0].max_raises = 1;
    config.stages[0].all_in = true;
    for (std::size_t s = 1; s < 4; ++s) {
      config.stages[s].bets = {.5};
      config.stages[s].all_in = true;
    }
    const std::array<std::uint8_t, 9> cards{0, 1, 2, 3, 4, 5, 6, 7, 8};
    deck = chance::DeckDefinition::reduced(cards);
    sb[0] = {{0, 1}, std::bit_cast<std::uint64_t>(1.0)};
    bb[0] = {{2, 3}, std::bit_cast<std::uint64_t>(1.0)};
  }
};
void arithmetic_controls() {
  CommonDenominator c(CommonInteger(29), 20, 3, 12);
  require(c.denominator() == 7127040, "common denominator value");
  require(c.scale_terminal(CommonInteger(-3), CommonInteger(1740) << 4) == -768,
          "negative exact scaling");
  require(c.divide_power_two(CommonInteger(-768), 4) == -48,
          "negative exact division");
  require(c.divide_power_two(CommonInteger(0), 500) == 0,
          "zero division result");
  rejects<CommonDenominatorError>(
      [&] { (void)c.divide_power_two(CommonInteger(-3), 1); },
      "inexact signed division accepted");
  rejects<CommonDenominatorError>(
      [&] { (void)c.scale_terminal(CommonInteger(1), CommonInteger(1741)); },
      "foreign denominator accepted");
  rejects<CommonDenominatorError>(
      [&] {
        (void)c.scale_terminal(CommonInteger(1), CommonInteger(1740) << 13);
      },
      "excess shift accepted");
  require(c.add(CommonInteger(-9), CommonInteger(4)) == -5, "signed add");
  require(c.subtract(CommonInteger(4), CommonInteger(9)) == -5,
          "signed subtract");
}
void parent_and_reuse_controls() {
  Fixture f;
  auto bad = f.config;
  bad.stacks = {0, 0};
  auto floor = [](auto &&fn) {
    try {
      fn();
    } catch (const FrozenGameError &e) {
      require(std::string(e.what()) ==
                  "frozen-game money setup exceeds integer admission",
              "wrong low-limit failure");
      return;
    }
    throw std::runtime_error("low integer cap accepted");
  };
  FrozenGameLimits bits;
  bits.integer_bits = 180;
  floor([&] { FrozenGame g(bad, f.deck, f.sb, f.bb, bits); });
  FrozenGameLimits payload;
  payload.integer_payload_bits = 32U * 181U - 1U;
  floor([&] { FrozenGame g(bad, f.deck, f.sb, f.bb, payload); });
  const auto one = std::bit_cast<std::uint64_t>(1.0);
  const std::array<chance::WeightedHand, 2> duplicate{
      {{{0, 1}, one}, {{0, 1}, one}}};
  const std::array<chance::WeightedHand, 1> blocked{{{{0, 2}, one}}};
  const std::array<chance::WeightedHand, 1> nan{
      {{{0, 1}, 0x7ff8000000000000ULL}}};
  FrozenGameLimits low;
  low.work = 200000;
  rejects<FrozenGameError>(
      [&] { FrozenGame g(f.config, f.deck, duplicate, f.bb, low); },
      "duplicate range accepted");
  rejects<FrozenGameError>(
      [&] { FrozenGame g(f.config, f.deck, f.sb, blocked, low); },
      "no compatible private deal accepted");
  rejects<FrozenGameError>(
      [&] { FrozenGame g(f.config, f.deck, nan, f.bb, low); },
      "nonfinite prior accepted");
  auto malformed = f.deck;
  malformed.cards[1] = malformed.cards[0];
  rejects<FrozenGameError>(
      [&] { FrozenGame g(f.config, malformed, f.sb, f.bb, low); },
      "duplicate deck card accepted");
  FrozenGame game(f.config, f.deck, f.sb, f.bb);
  const std::array<std::uint8_t, 5> invalid{4, 4, 6, 7, 8},
      valid{4, 5, 6, 7, 8};
  rejects<std::exception>(
      [&] {
        (void)FrozenUpdate::run(game, invalid, ProposalKind::uniform_public);
      },
      "invalid board accepted");
  rejects<FrozenUpdateError>(
      [&] {
        (void)FrozenUpdate::run(game, valid, ProposalKind::uniform_public);
      },
      "failed owner reused");
  require(game.chance_receipt().prefix_queries == 0 &&
              game.chance_receipt().terminal_queries == 0 &&
              game.chance_receipt().rank_calls == 0,
          "invalid board entered chance callback");
  require(game.setup_receipt().peak_setup_integer_bits_upper >= 181 &&
              game.setup_receipt().peak_setup_integer_payload_bits_upper >=
                  32U * 181U,
          "setup peak receipt omitted template");
}
void history_and_profile_controls() {
  alignas(HistoryArena) std::array<std::byte, sizeof(HistoryArena)> storage{};
  auto *old = new (storage.data()) HistoryArena;
  const auto root = old->root();
  const auto a = old->append_action(root, "bet@2"),
             b = old->append_action(root, "check");
  const auto aa = old->append_action(a, "call"),
             aa2 = old->append_action(a, "call"),
             bb = old->append_action(b, "call");
  require(old->ordinal(aa) == old->ordinal(aa2) &&
              old->ordinal(aa) != old->ordinal(bb),
          "history interning or separation");
  const std::array<std::uint8_t, 3> flop{2, 5, 10};
  const auto revealed = old->append_reveal(aa, flop);
  require(old->materialize(revealed).back() == "flop@2h3d4h" &&
              old->visible_size(revealed) == 3,
          "visible reveal mismatch");
  rejects<HistoryError>([&] { (void)old->append_action(revealed, "turn@5c"); },
                        "reveal token accepted as action");
  require(old->selector_hash(root, 0, 43, 48, 3) == 16742080263518101358ULL,
          "pinned root profile hash");
  const auto bet = old->append_action(root, "bet@2");
  const auto board = old->append_reveal(bet, flop);
  require(old->selector_hash(board, 1, 43, 48, 4) == 10341476553546665735ULL,
          "pinned visible-history profile hash");
  bool zero_seen = false;
  for (std::uint8_t second = 1; second < 52 && !zero_seen; ++second) {
    const auto p = frozen_power_policy(*old, root, 0, 0, second, 3);
    unsigned units = 0;
    for (std::size_t i = 0; i < p.size; ++i) {
      if (p.exponent[i] < 0) {
        zero_seen = true;
        continue;
      }
      units += 1U << (2 - p.exponent[i]);
    }
    require(units == 4, "power policy does not sum to one");
  }
  require(zero_seen, "no pinned zero-policy action found");
  old->~HistoryArena();
  auto *current = new (storage.data()) HistoryArena;
  bool rejected = false;
  try {
    (void)current->depth(root);
  } catch (const HistoryError &) {
    rejected = true;
  }
  current->~HistoryArena();
  require(rejected, "reused address accepted stale cursor");
}
void zero_target_and_action_controls() {
  Fixture f;
  f.config.stacks = {4, 4};
  FrozenGame game(f.config, f.deck, f.sb, f.bb);
  const std::array<std::uint8_t, 5> board{4, 5, 6, 7, 0};
  auto stage = FrozenUpdate::run(game, board, ProposalKind::uniform_public);
  bool root_average = false, zero_action = false,
       zero_reach_continuation = false;
  for (const auto &row : stage.rows) {
    if (row.history.empty() && row.average_mass_numerator > 0)
      root_average = true;
    require(row.actions.size() == row.policy_exponents.size() &&
                row.actions.size() == row.regret_numerators.size() &&
                row.actions.size() == row.average_numerators.size(),
            "incomplete action vectors");
    for (std::size_t a = 0; a < row.actions.size(); ++a) {
      require(row.regret_numerators[a] == 0,
              "zero-target board produced regret");
      if (row.policy_exponents[a] < 0) {
        zero_action = true;
        require(row.average_numerators[a] == 0, "zero action has average mass");
        for (const auto &later : stage.rows) {
          if (later.actor != row.actor || later.first != row.first ||
              later.second != row.second ||
              later.history.size() <= row.history.size())
            continue;
          bool same = true;
          for (std::size_t k = 0; k < row.history.size(); ++k)
            if (later.history[k] != row.history[k])
              same = false;
          if (same && later.history[row.history.size()] == row.actions[a]) {
            require(later.average_mass_numerator == 0,
                    "zero-own-reach continuation has average mass");
            zero_reach_continuation = true;
          }
        }
      }
    }
  }
  require(root_average, "zero-target board lost root average");
  require(zero_action, "zero-policy legal action was not retained in stage");
  require(zero_reach_continuation,
          "zero-policy legal continuation was not staged");
  require(stage.chance_work <= stage.forecast.chance_work_upper &&
              stage.history_work <= stage.forecast.history_work_upper &&
              stage.common_regret_work <=
                  stage.forecast.arithmetic_work_upper -
                      stage.forecast.average_work_upper &&
              stage.average_work <= stage.forecast.average_work_upper,
          "counter exceeded forecast");
}
} // namespace
int main() {
  try {
    arithmetic_controls();
    parent_and_reuse_controls();
    history_and_profile_controls();
    zero_target_and_action_controls();
    std::cout
        << "PASS frozen-update primitive, admission, identity and zero-target controls"
        << std::endl;
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "FAIL " << e.what() << std::endl;
    return 2;
  }
}
