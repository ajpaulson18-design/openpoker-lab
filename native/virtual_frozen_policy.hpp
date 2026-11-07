#pragma once
// Pinned complete procedural frozen profile; not a strategy-row identity.
#include "virtual_frozen_history.hpp"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>

namespace openpoker::virtual_frozen_update {
// -1 is exact zero, 0 is one, and positive n denotes 2^-n.
struct PowerPolicy {
  std::array<int, 20> exponent{};
  std::size_t size = 0;
};
inline PowerPolicy
frozen_power_policy(HistoryArena &arena, HistoryArena::Cursor history,
                    std::uint8_t actor, std::uint8_t hand_first,
                    std::uint8_t hand_second, std::size_t action_count) {
  if (!action_count || action_count > 20)
    throw HistoryError("invalid frozen menu width");
  const auto hash =
      arena.selector_hash(history, actor, hand_first, hand_second,
                          static_cast<std::uint8_t>(action_count));
  PowerPolicy policy;
  policy.size = action_count;
  policy.exponent.fill(-1);
  const auto rotation = static_cast<std::size_t>((hash >> 32) % action_count);
  const bool remove = action_count > 1 && (hash & 3U) == 0;
  const auto zero = remove
                        ? static_cast<std::size_t>((hash >> 8) % action_count)
                        : action_count;
  const auto active = action_count - (remove ? 1U : 0U);
  std::size_t assigned = 0;
  for (std::size_t i = 0; i < action_count; ++i) {
    const auto index = (i + rotation) % action_count;
    if (index == zero)
      continue;
    policy.exponent[index] =
        active == 1 ? 0 : static_cast<int>(std::min(assigned + 1, active - 1));
    ++assigned;
  }
  if (assigned != active)
    throw HistoryError("frozen profile assignment invariant");
  return policy;
}
} // namespace openpoker::virtual_frozen_update
