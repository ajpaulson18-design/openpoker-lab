#pragma once
// Single-board frozen update: bounded setup and preflight. Execution follows in this component.
#include "virtual_frozen_game.hpp"
#include "virtual_frozen_history.hpp"
#include "virtual_frozen_policy.hpp"
#include "virtual_frozen_proposal.hpp"
#include "virtual_frozen_common_denominator.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>

namespace openpoker::virtual_frozen_update {
class FrozenUpdateError final : public std::runtime_error {
public:
  explicit FrozenUpdateError(const char *s) : std::runtime_error(s) {}
};
struct FrozenUpdateForecast {
  std::uint64_t work_upper = 0, chance_work_upper = 0, history_work_upper = 0,
                arithmetic_work_upper = 0;
  std::uint64_t rows_upper = 0, slots_upper = 0, edge_occurrences = 0,
                token_bytes = 0, terminal_occurrences = 0;
  std::size_t integer_bits_upper = 0, integer_payload_bits_upper = 0,
              entries_upper = 0, reach_exponent_upper = 0;
  std::uint64_t row_history_tokens_upper = 0, average_work_upper = 0,
                retained_text_bytes_upper = 0;
  bool admitted = false;
};
struct FrozenUpdateStage;
class FrozenUpdate final {
  static std::uint64_t add(std::uint64_t a, std::uint64_t b) {
    if (b > UINT64_MAX - a)
      throw FrozenUpdateError("update forecast addition overflow");
    return a + b;
  }
  static std::uint64_t mul(std::uint64_t a, std::uint64_t b) {
    if (a && b > UINT64_MAX / a)
      throw FrozenUpdateError("update forecast multiplication overflow");
    return a * b;
  }
  static std::size_t width(const CommonInteger &n) {
    return chance::prior::magnitude_bits(n);
  }
  static std::uint64_t logceil(std::uint64_t n) {
    return n <= 1 ? 0 : std::bit_width(n - 1);
  }

public:
  // Preliminary structural/numeric envelope only. The execution method must be
  // paired with this exact ledger; this function performs no terminal callback.
  static FrozenUpdateStage run(FrozenGame &game,
                               const std::array<std::uint8_t, 5> &board,
                               ProposalKind proposal);
  static FrozenUpdateForecast forecast(FrozenGame &game,
                                       const std::array<std::uint8_t, 5> &board,
                                       ProposalKind proposal) {
    if (game.update_used_)
      throw FrozenUpdateError("frozen game already consumed");
    game.update_used_ = true; // failure does not permit resetting child meters
    const auto &t = *game.template_;
    const auto &rec = t.receipt();
    const auto nodes = t.nodes().size(), edges = rec.edges,
               h = game.hands_[0].size() + game.hands_[1].size();
    const auto scan = add(4096, add(mul(512, nodes), mul(256, edges)));
    if (scan > game.limits_.work - game.receipt_.work)
      throw FrozenUpdateError("update forecast scan exceeds remaining work");
    const auto law = proposal_for(game.deck_, board, proposal);
    std::uint64_t rows = 0, slots = 0, rowtokens = 0, edgeocc = 0,
                  tokenbytes = 0, terms = 0, maxmenu = 0, maxpayneg = 0,
                  maxpaypos = 0;
    double maximum_payoff = 0;
    for (std::size_t id = 0; id < nodes; ++id) {
      const auto &node = t.nodes()[id];
      const auto paths = t.histories()[id][0];
      if (node.state.phase == betting::Phase::decision) {
        if (node.state.actor > 1 || node.edges.empty() ||
            node.edges.size() > 20)
          throw FrozenUpdateError("invalid decision menu");
        const auto actor_h = game.hands_[node.state.actor].size();
        rows = add(rows, mul(paths, actor_h));
        rowtokens = add(rowtokens, mul(t.histories()[id][1], actor_h));
        slots = add(slots, mul(mul(paths, actor_h), node.edges.size()));
        maxmenu = std::max<std::uint64_t>(maxmenu, node.edges.size());
      } else if (node.state.phase == betting::Phase::fold ||
                 node.state.phase == betting::Phase::showdown) {
        terms = add(terms, paths);
        const auto pay =
            std::min(node.state.committed[0], node.state.committed[1]);
        maximum_payoff = std::max(maximum_payoff, pay);
        const auto decoded =
            chance::prior::decode_parts(std::bit_cast<std::uint64_t>(pay),
                                        false, true, "invalid matched payoff");
        if (decoded.significand) {
          if (decoded.exponent < 0)
            maxpayneg = std::max<std::uint64_t>(
                maxpayneg, static_cast<std::uint64_t>(-decoded.exponent));
          else
            maxpaypos = std::max<std::uint64_t>(
                maxpaypos, static_cast<std::uint64_t>(decoded.exponent));
        }
      }
      for (const auto &edge : node.edges) {
        std::size_t n = 0;
        if (node.state.phase == betting::Phase::decision)
          n = edge.action.token.size();
        else if (node.state.phase == betting::Phase::reveal)
          n = node.state.next_street == 3   ? 11
              : node.state.next_street == 4 ? 7
                                            : 8;
        else
          throw FrozenUpdateError("terminal node has edge");
        if (!n || n > 64)
          throw FrozenUpdateError("invalid symbolic history token");
        edgeocc = add(edgeocc, paths);
        tokenbytes = add(tokenbytes, mul(paths, n));
      }
    }
    const auto reach = mul(rec.max_depth, maxmenu ? maxmenu - 1 : 0);
    if (reach > 1022)
      throw FrozenUpdateError(
          "normal binary64 reach exponent admission exceeded");
    const auto normalizer_width = width(game.chance_->normalizer_integer());
    const auto denominator_exponents =
        game.chance_->weight_denominator_exponents();
    std::array<std::size_t, 2> weight_width{};
    for (std::size_t p = 0; p < 2; ++p)
      for (const auto &hand : game.hands_[p]) {
        const auto part = chance::prior::decode_parts(
            hand.binary64_weight_bits, false, false, "invalid frozen prior");
        const int alignment = part.exponent + denominator_exponents[p];
        if (alignment < 0)
          throw FrozenUpdateError("invalid prior denominator exponent");
        weight_width[p] = std::max(
            weight_width[p],
            static_cast<std::size_t>(std::bit_width(part.significand)) +
                static_cast<std::size_t>(alignment));
      }
    const auto deck_n = game.deck_.count - 4;
    const auto divisor = static_cast<std::uint64_t>(deck_n) * (deck_n - 1) *
                         (deck_n - 2) / 6 * (game.deck_.count - 7) *
                         (game.deck_.count - 8);
    const auto shift = add(add(52, add(reach, maxpayneg)), reach);
    const auto denominator_width =
        add(add(add(normalizer_width, std::bit_width(divisor)),
                std::bit_width(law.board.numerator)),
            shift);
    const auto payoff_ceiling =
        static_cast<std::uint64_t>(std::ceil(maximum_payoff));
    const auto payoff_factor = std::max<std::uint64_t>(
        1, mul(mul(2, payoff_ceiling), law.board.denominator));
    // Nonnegative own-policy mixtures and opponent-reach partitions have
    // absolute mass at most one. Hence |partial value|<=U/q(B) and
    // |regret|<=2U/q(B); multiply that bound by the exact common D.
    const auto value_width =
        add(add(denominator_width, std::bit_width(payoff_factor)), 3);
    std::size_t qprefix_num_bits = 0, qprefix_den_bits = 0;
    for (const auto &q : law.prefix) {
      qprefix_num_bits =
          std::max(qprefix_num_bits,
                   static_cast<std::size_t>(std::bit_width(q.numerator)));
      qprefix_den_bits =
          std::max(qprefix_den_bits,
                   static_cast<std::size_t>(std::bit_width(q.denominator)));
    }
    const auto average_den_width = add(
        add(add(normalizer_width, std::bit_width(divisor)), qprefix_num_bits),
        add(reach, add(maxmenu, 3)));
    const auto average_num_width =
        add(add(normalizer_width, qprefix_den_bits), add(maxmenu, 3));
    // The native query constructs unnormalized bucket products before the
    // value bound applies: admit its documented numerator and denominator
    // width formulas independently, including binary64 reach alignment.
    const auto prior_width = add(weight_width[0], weight_width[1]);
    const auto native_num = add(
        add(prior_width, add(53, reach)),
        add(add(logceil(std::max(game.hands_[0].size(), game.hands_[1].size())),
                6),
            add(add(53, std::bit_width(law.board.denominator)),
                add(maxpaypos, 12))));
    const auto native_den =
        add(add(add(normalizer_width, std::bit_width(divisor)),
                std::bit_width(law.board.numerator)),
            add(add(52, reach), add(maxpayneg, 8)));
    const auto prefix_width =
        std::max(add(add(normalizer_width, std::bit_width(divisor)), 2),
                 add(prior_width, add(add(logceil(game.hands_[0].size()),
                                          logceil(game.hands_[1].size())),
                                      8)));
    const auto bits =
        std::max({value_width, average_den_width, average_num_width, native_num,
                  native_den, prefix_width, denominator_width});
    if (bits > game.limits_.integer_bits)
      throw FrozenUpdateError("update integer width admission exceeded");
    const auto history_nodes = add(rec.logical_occurrences, 1);
    if (history_nodes > 250000)
      throw FrozenUpdateError("update history node admission exceeded");
    const auto history = add(
        4096, add(mul(2, mul(add(mul(512, edgeocc), mul(256, tokenbytes)),
                             add(1, std::bit_width(history_nodes + 1)))),
                  add(mul(2, mul(edgeocc, 640)),
                      add(mul(mul(2, rows), add(512, mul(256, rec.max_depth))),
                          mul(rows, add(256, mul(256, rec.max_depth)))))));
    const auto perterminal = add(
        add(128,
            mul(32, std::max(game.hands_[0].size(), game.hands_[1].size()))),
        add(4096, add(mul(512, h), mul(mul(64, h), add(1, logceil(h))))));
    const auto chancework =
        add(mul(mul(2, terms), perterminal), mul(4, add(576, mul(128, h))));
    const auto terminalhands = mul(
        mul(2, terms), std::max(game.hands_[0].size(), game.hands_[1].size()));
    const auto units = add(add(mul(64, terminalhands), mul(160, slots)),
                           add(mul(mul(64, edgeocc), h), mul(128, rows)));
    const auto arith =
        add(add(mul(bits, units),
                mul(1024, add(add(terminalhands, mul(5, slots)),
                              add(mul(4, rows), mul(edgeocc, h))))),
            add(mul(512, bits), 1024));
    const auto avgwork = add(mul(bits, add(mul(128, rows), mul(32, slots))),
                             add(mul(4096, rows), mul(1024, slots)));
    // Fixed owner startup, common-denominator setup, frame and row bookkeeping.
    const auto other =
        add(8192, add(mul(mul(256, rec.logical_occurrences), h),
                      add(mul(256, rows),
                          add(mul(128, slots),
                              mul(mul(64, rows),
                                  add(1, std::bit_width(add(rows, 1))))))));
    const auto work =
        add(game.receipt_.work,
            add(scan, add(history, add(chancework, add(arith, other)))));
    // Row headers and vectors: 32 fields/row; full history string slots: 4/token;
    // ordered actions/numbers: 8/slot; seen-key tree: 16/row. Remaining
    // terms cover arena records, depth frames, four prefixes, and fixed scratch.
    const auto entries = add(
        game.receipt_.retained_entries_upper,
        add(mul(48, rows),
            add(mul(8, slots),
                add(mul(4, rowtokens),
                    add(mul(64, history_nodes),
                        add(mul(mul(128, h), add(rec.max_depth, 1)), 8192))))));
    const auto payload =
        mul(bits, add(mul(8, add(rows, slots)),
                      add(mul(mul(64, h), add(rec.max_depth, 1)), 4096)));
    const auto retained_text_bytes =
        add(add(mul(mul(64, rec.max_depth), rows), mul(64, slots)),
            mul(2, tokenbytes));
    const bool admitted =
        work <= game.limits_.work && entries <= game.limits_.entries &&
        payload <= game.limits_.integer_payload_bits -
                       game.chance_->receipt().setup_integer_payload_bits &&
        retained_text_bytes <= 64ULL * 1024 * 1024 &&
        mul(2, tokenbytes) <= 32ULL * 1024 * 1024;
    return {work,
            chancework,
            history,
            arith,
            rows,
            slots,
            edgeocc,
            tokenbytes,
            terms,
            static_cast<std::size_t>(bits),
            static_cast<std::size_t>(payload),
            static_cast<std::size_t>(entries),
            static_cast<std::size_t>(reach),
            rowtokens,
            avgwork,
            retained_text_bytes,
            admitted};
  }
};
} // namespace openpoker::virtual_frozen_update

#include "virtual_frozen_walk.hpp"
