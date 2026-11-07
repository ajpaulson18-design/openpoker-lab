#pragma once
// Owned public proposal laws used by the first frozen-update proof.
#include "full_deck_public_chance.hpp"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
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
  std::uint64_t seen = 0;
  for (std::size_t i = 0; i < deck.count; ++i) {
    const auto c = deck.cards[i];
    if (c >= 52 || (i && deck.cards[i - 1] >= c))
      throw std::invalid_argument("invalid proposal deck");
    seen |= std::uint64_t{1} << c;
  }
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
    const std::uint64_t n = deck.count, flop = n * (n - 1) * (n - 2) / 6;
    result.prefix = {SmallRatio{1, 1}, SmallRatio{1, flop},
                     SmallRatio{1, flop * (n - 3)},
                     SmallRatio{1, flop * (n - 3) * (n - 4)}};
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
