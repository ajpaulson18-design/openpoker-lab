#pragma once
// Owned public proposal laws used by the first frozen-update proof.
#include "full_deck_public_chance.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <stdexcept>

namespace openpoker::virtual_frozen_update {
enum class ProposalKind { uniform_public, weighted_river_proof9 };
struct SmallRatio {
  std::uint64_t numerator = 1, denominator = 1;
};
struct ProposalSnapshot {
  SmallRatio board;
  std::array<SmallRatio, 4> prefix;
};
inline std::uint64_t public_proposal_deck_mask(
    const full_deck_public_chance::DeckDefinition &deck) {
  if (deck.count < 9 || deck.count > 52)
    throw std::invalid_argument("invalid proposal deck size");
  std::uint64_t mask = 0;
  for (std::size_t i = 0; i < deck.count; ++i) {
    const auto card = deck.cards[i];
    if (card >= 52 || (i && deck.cards[i - 1] >= card))
      throw std::invalid_argument("invalid proposal deck");
    mask |= std::uint64_t{1} << card;
  }
  return mask;
}

inline std::array<std::uint64_t, 4> uniform_public_prefix_counts(std::size_t n) {
  if (n < 9 || n > 52)
    throw std::invalid_argument("invalid proposal deck size");
  const auto flop = static_cast<std::uint64_t>(n) * (n - 1) * (n - 2) / 6;
  return {1, flop, flop * (n - 3), flop * (n - 3) * (n - 4)};
}

// Direct address of a physical board. The proposal is over public cards only;
// private blockers affect target mass in the solver's chance kernel.
class UniformPublicBoards final {
  full_deck_public_chance::DeckDefinition deck_;
  std::uint64_t mask_;
  std::uint64_t count_;

  static std::uint8_t select(std::uint64_t mask, std::uint64_t ordinal) {
    for (; ordinal && mask; --ordinal)
      mask &= mask - 1;
    if (!mask)
      throw std::logic_error("public suffix ordinal outside support");
    return static_cast<std::uint8_t>(std::countr_zero(mask));
  }

public:
  explicit UniformPublicBoards(full_deck_public_chance::DeckDefinition deck)
      : deck_(deck), mask_(public_proposal_deck_mask(deck_)),
        count_(uniform_public_prefix_counts(deck_.count).back()) {}

  // Select a board from the remaining deck of one physical private deal.
  // The caller uses the original deck for chance and betting semantics.
  UniformPublicBoards(full_deck_public_chance::DeckDefinition deck,std::uint64_t private_mask)
      : UniformPublicBoards(deck) {
    if ((private_mask&mask_)!=private_mask || std::popcount(private_mask)!=4)
      throw std::invalid_argument("invalid private blockers for a legal-board proposal");
    mask_&=~private_mask;
    deck_.count=0;
    for (std::size_t i=0;i<deck.count;++i)
      if (!(private_mask&(std::uint64_t{1}<<deck.cards[i]))) deck_.cards[deck_.count++]=deck.cards[i];
    const auto n=static_cast<std::uint64_t>(deck_.count);
    count_=n*(n-1)*(n-2)/6*(n-3)*(n-4);
  }

  [[nodiscard]] std::uint64_t size() const noexcept { return count_; }

  // Uniform uint64 input on the accepted interval maps exactly equally to
  // every ordinal. A rejected word emits no board and changes no owner state.
  [[nodiscard]] std::uint64_t rejection_prefix() const noexcept {
    return (std::uint64_t{0} - count_) % count_;
  }

  [[nodiscard]] std::optional<std::uint64_t>
  ordinal_from_word(std::uint64_t word) const noexcept {
    if (word < rejection_prefix())
      return std::nullopt;
    return word % count_;
  }

  [[nodiscard]] std::array<std::uint8_t, 5> at(std::uint64_t ordinal) const {
    if (ordinal >= count_)
      throw std::out_of_range("public board ordinal outside support");
    const auto n = deck_.count;
    const auto suffixes = (n - 3) * (n - 4);
    auto flop = ordinal / suffixes;
    const auto suffix = ordinal % suffixes;

    std::size_t first = 0;
    for (; first + 2 < n; ++first) {
      const auto after_first = n - first - 1;
      const auto combinations = after_first * (after_first - 1) / 2;
      if (flop < combinations)
        break;
      flop -= combinations;
    }
    std::size_t second = first + 1;
    for (; second + 1 < n; ++second) {
      const auto after_second = n - second - 1;
      if (flop < after_second)
        break;
      flop -= after_second;
    }
    const auto third = second + 1 + static_cast<std::size_t>(flop);
    if (third >= n)
      throw std::logic_error("public flop ordinal outside support");

    const auto x = deck_.cards[first], y = deck_.cards[second], z = deck_.cards[third];
    auto remaining = mask_ & ~((std::uint64_t{1} << x) |
        (std::uint64_t{1} << y) | (std::uint64_t{1} << z));
    const auto turn = select(remaining, suffix / (n - 4));
    remaining &= ~(std::uint64_t{1} << turn);
    return {x, y, z, turn, select(remaining, suffix % (n - 4))};
  }
};

inline ProposalSnapshot
proposal_for(const full_deck_public_chance::DeckDefinition &deck,
             const std::array<std::uint8_t, 5> &board, ProposalKind kind) {
  if (deck.count < 9 || deck.count > 52)
    throw std::invalid_argument("invalid proposal deck size");
  if (kind != ProposalKind::uniform_public &&
      kind != ProposalKind::weighted_river_proof9)
    throw std::invalid_argument("unknown proposal law");
  if (kind == ProposalKind::weighted_river_proof9 &&
      (deck.count != 9 ||
       deck.mode != full_deck_public_chance::DeckMode::reduced_proof))
    throw std::invalid_argument(
        "weighted-river proposal requires reduced nine-card deck");
  const auto seen = public_proposal_deck_mask(deck);
  std::uint64_t used = 0;
  for (auto c : board) {
    if (c >= 52 || !(seen & (std::uint64_t{1} << c)) ||
        (used & (std::uint64_t{1} << c)))
      throw std::invalid_argument("invalid proposal board");
    used |= std::uint64_t{1} << c;
  }
  if (!(board[0] < board[1] && board[1] < board[2]))
    throw std::invalid_argument("proposal flop must be canonical");
  ProposalSnapshot result;
  if (kind == ProposalKind::uniform_public) {
    const auto counts = uniform_public_prefix_counts(deck.count);
    for (std::size_t p = 0; p < counts.size(); ++p)
      result.prefix[p] = SmallRatio{1, counts[p]};
  } else {
    std::uint64_t after_flop = 0, after_turn = 0, river = 0;
    for (std::size_t i = 0; i < deck.count; ++i) {
      const auto c = deck.cards[i];
      const auto w = static_cast<std::uint64_t>(i + 1);
      if (c != board[0] && c != board[1] && c != board[2]) {
        after_flop += w;
        if (c != board[3])
          after_turn += w;
      }
      if (c == board[4])
        river = w;
    }
    result.prefix = {SmallRatio{1, 1}, SmallRatio{5 * after_flop, 12600},
                     SmallRatio{after_turn, 12600}, SmallRatio{river, 12600}};
  }
  result.board = result.prefix[3];
  return result;
}
} // namespace openpoker::virtual_frozen_update
