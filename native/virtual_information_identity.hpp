#pragma once

#include "virtual_dyadic_history.hpp"
#include <cstddef>
#include <stdexcept>
#include <tuple>
#include <tuple>

namespace openpoker::virtual_information_identity {

enum class ErrorKind { actor_holding, depth };

class Error final : public std::runtime_error {
    ErrorKind kind_;
public:
    Error(ErrorKind kind, const char* message) : std::runtime_error(message), kind_(kind) {}
    [[nodiscard]] ErrorKind kind() const noexcept { return kind_; }
};

using Key = std::tuple<std::size_t, std::size_t, std::size_t>;

// Keep query order and cost aligned with State::key: validate actor/holding,
// obtain ordinal, then query depth. The caller maps these error kinds to its
// established public messages.
inline Key key(const virtual_dyadic_history::History& history,
               virtual_dyadic_history::History::Cursor cursor,
               std::size_t actor, std::size_t holding,
               const std::size_t* hand_counts, std::size_t max_depth) {
    if (actor > 1 || hand_counts == nullptr || holding >= hand_counts[actor])
        throw Error(ErrorKind::actor_holding, "actor or original holding index");
    const auto ordinal = history.ordinal(cursor);
    if (history.depth(cursor) > max_depth)
        throw Error(ErrorKind::depth, "history depth exceeds forecast");
    return {ordinal, actor, holding};
}

} // namespace openpoker::virtual_information_identity
