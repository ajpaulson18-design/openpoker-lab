#pragma once
// Setup ownership only for a future admitted frozen update; no traversal or training.
#include "full_deck_public_chance.hpp"
#include "virtual_betting_template.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <stdexcept>
#include <vector>

namespace openpoker::virtual_frozen_update {
namespace chance = full_deck_public_chance;
namespace betting = virtual_betting_template;
class FrozenGameError final : public std::runtime_error {
public:
  explicit FrozenGameError(const char *s) : std::runtime_error(s) {}
};
struct FrozenGameLimits {
  std::uint64_t work = 500000000;
  std::size_t entries = 2000000;
  std::size_t integer_bits = 65536;
  std::size_t integer_payload_bits = std::size_t{1} << 30;
  std::size_t max_hands_per_side = 1326;
};
struct FrozenGameSetupReceipt {
  std::uint64_t work = 0;
  std::size_t retained_entries_upper = 0;
  std::size_t peak_setup_entries_upper = 0;
  std::size_t peak_setup_integer_bits_upper = 0,
              peak_setup_integer_payload_bits_upper = 0;
};
class FrozenUpdate;
class FrozenGame final {
  friend class FrozenUpdate;
  FrozenGameLimits limits_;
  chance::DeckDefinition deck_;
  std::array<std::vector<chance::WeightedHand>, 2> hands_;
  std::unique_ptr<betting::Template> template_;
  std::unique_ptr<chance::PublicChanceKernel> chance_;
  FrozenGameSetupReceipt receipt_{};
  bool update_used_ = false;

public:
  FrozenGame(const betting::Config &config, const chance::DeckDefinition &deck,
             std::span<const chance::WeightedHand> sb,
             std::span<const chance::WeightedHand> bb,
             FrozenGameLimits limits = {})
      : limits_(limits), deck_(deck) {
    if (!limits.work || limits.work > 500000000 || !limits.entries ||
        limits.entries > 2000000 || !limits.integer_bits ||
        limits.integer_bits > 65536 || !limits.integer_payload_bits ||
        limits.integer_payload_bits > (std::size_t{1} << 30) ||
        !limits.max_hands_per_side || limits.max_hands_per_side > 1326)
      throw FrozenGameError("invalid reduce-only frozen-game limits");
    // The published template's money quantizer admits up to 181-bit
    // conversion intermediates and 32 such logical integer slots.  Bridge
    // the parent limits before entering its constructor; chance and the
    // update retain their own separately admitted peak accounting.
    if (limits.integer_bits < 181 || limits.integer_payload_bits < 32U * 181U)
      throw FrozenGameError(
          "frozen-game money setup exceeds integer admission");
    if (!config.initial_history_empty)
      throw FrozenGameError(
          "frozen game requires the original empty-history root");
    if (sb.empty() || bb.empty() || sb.size() > limits.max_hands_per_side ||
        bb.size() > limits.max_hands_per_side)
      throw FrozenGameError("invalid frozen-game range dimensions");
    std::size_t sizes = 0;
    for (const auto &stage : config.stages) {
      if (stage.bets.size() > 8 || stage.raises.size() > 8)
        throw FrozenGameError("invalid frozen-game stage dimensions");
      sizes += stage.bets.size() + stage.raises.size();
    }
    const auto h = sb.size() + bb.size();
    const auto owner_entries = 512 + 4 * h + 4 * sizes;
    const std::uint64_t owner_work = 16384 + 512 * h + 64 * sizes;
    if (owner_entries >= limits.entries || owner_work >= limits.work)
      throw FrozenGameError("frozen-game owner setup exceeds admission");
    // Fixed scratch: two 1,326-bit hand sets, card incidence counts and deck mask;
    // this fits within owner_entries before any input copy or template construction.
    if ((deck.mode != chance::DeckMode::full52 &&
         deck.mode != chance::DeckMode::reduced_proof) ||
        deck.count < 9 || deck.count > 52 ||
        (deck.mode == chance::DeckMode::full52 && deck.count != 52))
      throw FrozenGameError("invalid frozen-game deck mode or size");
    std::uint64_t deck_mask = 0;
    for (std::size_t i = 0; i < deck.count; ++i) {
      const auto c = deck.cards[i];
      if (c >= 52 || (i && deck.cards[i - 1] >= c))
        throw FrozenGameError("invalid frozen-game deck order");
      deck_mask |= std::uint64_t{1} << c;
    }
    std::array<std::array<std::uint64_t, 21>, 2> hand_sets{};
    std::array<std::array<std::size_t, 52>, 2> card_counts{};
    const std::array<std::span<const chance::WeightedHand>, 2> ranges{sb, bb};
    auto key = [](chance::Hand hand) -> std::size_t {
      return static_cast<std::size_t>(hand.first) * (103U - hand.first) / 2U +
             hand.second - hand.first - 1U;
    };
    for (std::size_t side = 0; side < 2; ++side)
      for (const auto &row : ranges[side]) {
        const auto hand = row.hand;
        if (hand.first >= hand.second || hand.second >= 52 ||
            !(deck_mask & (std::uint64_t{1} << hand.first)) ||
            !(deck_mask & (std::uint64_t{1} << hand.second)))
          throw FrozenGameError("invalid frozen-game holding");
        const auto bits = row.binary64_weight_bits;
        if ((bits >> 63) || ((bits >> 52) & 0x7ffU) == 0x7ffU ||
            !(bits & 0x7fffffffffffffffULL))
          throw FrozenGameError("invalid frozen-game positive weight");
        const auto k = key(hand), word = k / 64,
                   bit = std::uint64_t{1} << (k % 64);
        if (hand_sets[side][word] & bit)
          throw FrozenGameError("duplicate frozen-game holding");
        hand_sets[side][word] |= bit;
        ++card_counts[side][hand.first];
        ++card_counts[side][hand.second];
      }
    bool compatible = false;
    for (const auto &row : sb) {
      const auto hand = row.hand;
      const auto k = key(hand);
      const auto same = (hand_sets[1][k / 64] >> (k % 64)) & 1U;
      const auto blocked =
          card_counts[1][hand.first] + card_counts[1][hand.second] - same;
      if (blocked < bb.size()) {
        compatible = true;
        break;
      }
    }
    if (!compatible)
      throw FrozenGameError(
          "frozen-game ranges have no compatible private deal");
    hands_[0].assign(sb.begin(), sb.end());
    hands_[1].assign(bb.begin(), bb.end());
    betting::Limits template_limits;
    template_limits.work = limits.work - owner_work;
    template_limits.entries = limits.entries - owner_entries;
    template_ = std::make_unique<betting::Template>(config, template_limits);
    const auto &tr = template_->receipt();
    if (tr.history_suffix_only ||
        tr.entries >= limits.entries - owner_entries ||
        tr.work >= limits.work - owner_work)
      throw FrozenGameError("frozen-game template setup exceeds admission");
    chance::Limits chance_limits;
    chance_limits.max_hands_per_side = limits.max_hands_per_side;
    chance_limits.max_integer_bits = limits.integer_bits;
    chance_limits.max_integer_payload_bits = limits.integer_payload_bits;
    chance_limits.max_modeled_work = limits.work - owner_work - tr.work;
    chance_limits.max_storage_entries =
        limits.entries - owner_entries - tr.entries;
    chance_ = std::make_unique<chance::PublicChanceKernel>(
        hands_[0], hands_[1], deck_, chance_limits);
    const auto &cr = chance_->receipt();
    receipt_.work = owner_work + tr.work + cr.modeled_work;
    receipt_.retained_entries_upper =
        owner_entries + tr.entries + cr.retained_entries;
    // Template quantization scratch is released before chance construction;
    // retain the larger setup peak, not a fabricated simultaneous sum.
    receipt_.peak_setup_integer_bits_upper =
        std::max<std::size_t>(181, cr.peak_integer_bits);
    receipt_.peak_setup_integer_payload_bits_upper =
        std::max<std::size_t>(32U * 181U, cr.peak_integer_payload_bits);
    receipt_.peak_setup_entries_upper =
        std::max(owner_entries + tr.entries + tr.peak_scratch_entries,
                 owner_entries + tr.entries + cr.retained_entries +
                     cr.peak_scratch_entries);
    if (receipt_.work > limits.work ||
        receipt_.retained_entries_upper > limits.entries ||
        receipt_.peak_setup_entries_upper > limits.entries)
      throw FrozenGameError("frozen-game combined setup exceeds admission");
  }
  FrozenGame(const FrozenGame &) = delete;
  FrozenGame &operator=(const FrozenGame &) = delete;
  FrozenGame(FrozenGame &&) = delete;
  FrozenGame &operator=(FrozenGame &&) = delete;
  [[nodiscard]] const FrozenGameSetupReceipt &setup_receipt() const noexcept {
    return receipt_;
  }
  [[nodiscard]] const betting::Receipt &template_receipt() const noexcept {
    return template_->receipt();
  }
  [[nodiscard]] const chance::Receipt &chance_receipt() const noexcept {
    return chance_->receipt();
  }
};
} // namespace openpoker::virtual_frozen_update
