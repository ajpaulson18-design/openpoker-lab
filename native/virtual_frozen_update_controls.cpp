// Focused controls for the experimental frozen-update component.
// These controls do not constitute a full-game proof or a quality certificate.
#include "virtual_frozen_update.hpp"
#include "sampled_row_state.hpp"
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <new>
#include <stdexcept>
#include <sstream>
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
void sampled_row_publication_controls() {
  namespace sparse=openpoker::sampled_row_state;
  const sparse::Key root{0,1,2,{}};
  const sparse::Key distinct{0,1,2,{"board:3,4,5","check"}};
  const std::array<std::string,2> actions{"fold","call"};
  sparse::Limits limits;
  limits.retained={2,4,128};
  limits.pending={2,4,128};
  limits.integer_bits=32;
  limits.average_shift=8;
  sparse::State owner(64,limits);
  rejects<std::logic_error>([&] {owner.begin(0,32);},"changed regret scale admitted");
  owner.begin(0,64);
  owner.stage(0,root,actions,std::array<CommonInteger,2>{-7,3},
              std::array<CommonInteger,2>{3,5},8);
  require(!owner.committed_row(root) && owner.usage().pending.rows==1,
          "pending row leaked before publication");
  owner.commit(0);
  auto row=owner.committed_row(root);
  require(row && row->regrets[0]==-7 && row->regrets[1]==3 &&
              row->average[0]==96 && row->average[1]==160 &&
              row->average_odd_base==1 && row->average_shift==8,
          "first sparse update lost signs or scale");

  owner.begin(1,64);
  owner.stage(1,root,actions,std::array<CommonInteger,2>{9,-5},
              std::array<CommonInteger,2>{2,7},4);
  owner.stage(1,distinct,actions,std::array<CommonInteger,2>{1,-1},
              std::array<CommonInteger,2>{1,1},12);
  require(owner.committed_row(root)->regrets[0]==-7 && !owner.committed_row(distinct),
          "sparse generation read its own unpublished updates");
  owner.commit(1);
  const auto updated=owner.committed_row(root);
  require(updated && updated->regrets[0]==2 && updated->regrets[1]==-2 &&
              updated->average[0]==224 && updated->average[1]==608 &&
              owner.committed_row(distinct)->average_odd_base==3 &&
              owner.usage().committed.rows==2 && !owner.usage().pending.rows,
          "sparse publication changed values or aliased the public history");

  owner.begin(2,64);
  rejects<std::logic_error>([&] {owner.commit(1);},"stale sparse publication accepted");
  owner.stage(2,root,actions,std::array<CommonInteger,2>{1,1},
              std::array<CommonInteger,2>{1,1},4);
  const std::array<std::string,2> wrong_order{"call","fold"};
  rejects<std::invalid_argument>([&] {
      owner.stage(2,distinct,wrong_order,std::array<CommonInteger,2>{1,1},
                  std::array<CommonInteger,2>{1,1},12);
  },"reordered sparse action menu admitted");
  require(owner.failed() && owner.usage().iterations==2 &&
              !owner.usage().pending.rows && owner.committed_row(root)->regrets[0]==2 &&
              owner.committed_row(distinct)->regrets[0]==1,
          "failed sparse draw changed committed generation");
}

void sampled_row_precision_controls() {
  namespace sparse=openpoker::sampled_row_state;
  sparse::Limits limits;
  limits.integer_bits=32;
  limits.average_shift=8;
  const sparse::Key key{1,2,3,{}};
  const std::array<std::string,2> menu{"check","bet"};
  const std::array<CommonInteger,2> regret{-9,9};
  sparse::State owner(64,limits);
  owner.begin(0,64);
  owner.stage(0,key,menu,regret,std::array<CommonInteger,2>{256,512},65536);
  owner.commit(0);
  const auto row=owner.committed_row(key);
  require(row && row->average[0]==1 && row->average[1]==2,
          "exact cancellation lost average units");
  owner.begin(1,64);
  rejects<std::length_error>([&] {
      owner.stage(1,key,menu,regret,std::array<CommonInteger,2>{257,512},65536);
  },"inexact cancellation entered sampled row state");
  require(owner.failed() && owner.usage().iterations==1 && owner.committed_row(key)->average[0]==1,
          "precision rejection changed committed average units");
}

void publish_frozen_sample_controls() {
  namespace sparse=openpoker::sampled_row_state;
  Fixture f;
  f.config.stacks={4,4};
  FrozenGame game(f.config,f.deck,f.sb,f.bb);
  const std::array<std::uint8_t,5> board{4,5,6,7,0};
  const auto stage=FrozenUpdate::run(game,board,ProposalKind::uniform_public,true);
  sparse::Limits limits;
  limits.average_shift=96;
  sparse::State owner(stage.regret_denominator,limits);
  owner.begin(0,stage.regret_denominator);
  for (const auto& row : stage.rows) {
    const sparse::Key key{row.actor,row.first,row.second,row.history};
    owner.stage(0,key,row.actions,row.regret_numerators,row.average_numerators,
                row.average_denominator);
  }
  require(owner.usage().pending.rows==stage.rows.size() &&
              !owner.usage().committed.rows,"sample publication created unvisited rows");
  owner.commit(0);
  require(owner.usage().committed.rows==stage.rows.size() && owner.usage().iterations==1,
          "sample publication row census differs");
  bool saw_negative=false;
  for (const auto& row : stage.rows) {
    const sparse::Key key{row.actor,row.first,row.second,row.history};
    const auto stored=owner.committed_row(key);
    require(stored && std::ranges::equal(stored->actions,row.actions) &&
        std::ranges::equal(stored->regrets,row.regret_numerators),
        "published sampled policy key, menu or regret differs");
    const CommonInteger denominator=stored->average_odd_base<<stored->average_shift;
    for (std::size_t i=0;i<row.actions.size();++i) {
      require(stored->average[i]*row.average_denominator==row.average_numerators[i]*denominator,
              "published sampled average mass differs");
      saw_negative=saw_negative || stored->regrets[i]<0;
    }
  }
  require(saw_negative,"sample fixture lost negative cumulative regret coverage");
}

void implicit_public_board_controls() {
  constexpr std::array<std::uint8_t,11> cards{0,2,3,7,8,9,16,21,29,39,51};
  for (const std::size_t n : {9U,11U}) {
    const auto deck=chance::DeckDefinition::reduced(std::span(cards).first(n));
    const UniformPublicBoards boards(deck);
    std::uint64_t ordinal=0;
    for (std::size_t a=0; a+2<n; ++a)
      for (std::size_t b=a+1; b+1<n; ++b)
        for (std::size_t c=b+1; c<n; ++c)
          for (std::size_t t=0; t<n; ++t) {
            if (t==a || t==b || t==c) continue;
            for (std::size_t r=0; r<n; ++r) {
              if (r==a || r==b || r==c || r==t) continue;
              require(boards.at(ordinal++)==std::array{cards[a],cards[b],cards[c],cards[t],cards[r]},
                      "public board ordinal differs from physical enumeration");
            }
          }
    require(ordinal==boards.size() && ordinal==(n==9?2520U:9240U),
            "reduced public board census differs");
    const auto ratio=proposal_for(deck,boards.at(ordinal-1),ProposalKind::uniform_public);
    require(ratio.board.numerator==1 && ratio.board.denominator==ordinal &&
                ratio.prefix[1].denominator==(n==9?84U:165U) &&
                ratio.prefix[2].denominator==(n==9?504U:1320U),
            "public board ordinal and independent prefix census differ");
    rejects<std::out_of_range>([&] { (void)boards.at(ordinal); },
                              "out-of-range public board ordinal accepted");
  }
  const UniformPublicBoards complete(chance::DeckDefinition::full52());
  require(complete.size()==51979200 &&
              complete.at(0)==std::array<std::uint8_t,5>{0,1,2,3,4} &&
              complete.at(complete.size()-1)==std::array<std::uint8_t,5>{49,50,51,48,47},
          "complete deck endpoint census differs");
  const auto cut=complete.rejection_prefix();
  const auto high=std::numeric_limits<std::uint64_t>::max();
  require(cut>0 && cut<complete.size() && (high-cut+1)%complete.size()==0 &&
              !complete.ordinal_from_word(cut-1) &&
              complete.ordinal_from_word(cut)==cut%complete.size() &&
              complete.ordinal_from_word(high)==high%complete.size(),
          "uniform word-to-ordinal rejection bound differs");
  auto bad=chance::DeckDefinition::full52();
  bad.cards[17]=bad.cards[16];
  rejects<std::invalid_argument>([&] { (void)UniformPublicBoards(bad); },
                                "duplicated deck card accepted");
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
struct SampledFrontierFixture {
  betting::Config config=Fixture().config;
  chance::DeckDefinition deck;
  std::array<chance::WeightedHand,2> sb{{
      {{43,48},std::bit_cast<std::uint64_t>(.125)},
      {{32,43},std::bit_cast<std::uint64_t>(.75)}}};
  std::array<chance::WeightedHand,2> bb{{
      {{24,37},std::bit_cast<std::uint64_t>(.375)},
      {{16,32},std::bit_cast<std::uint64_t>(1.)}}};
  SampledFrontierFixture() {
    config.stacks={8,8};
    config.stages[0].bets={.5};
    for (std::size_t street=1;street<4;++street) {
      config.stages[street].bets={.5,1.};
      config.stages[street].raises={.25};
      config.stages[street].max_raises=1;
    }
    const std::array<std::uint8_t,9> cards{16,17,24,32,33,35,37,43,48};
    deck=chance::DeckDefinition::reduced(cards);
  }
};

void private_deal_controls() {
  const SampledFrontierFixture f;
  chance::PublicChanceKernel prior(f.sb,f.bb,f.deck);
  const CommonInteger total=prior.normalizer_integer();
  const CommonInteger unit=total/29;
  require(total==unit*29,"dealt fixture prior normalization");
  const std::array<std::array<chance::Hand,2>,3> pairs{{
      {{{43,48},{24,37}}}, {{{43,48},{16,32}}}, {{{32,43},{24,37}}}}};
  std::array<int,4> bounds{0,3,11,29};
  for (std::size_t i=0;i<pairs.size();++i) {
    const std::array<CommonInteger,2> tickets{unit*bounds[i],unit*bounds[i+1]-1};
    for (const auto& ticket:tickets) {
      const auto selected=prior.private_deal(ticket);
      require(selected[0].first==pairs[i][0].first && selected[0].second==pairs[i][0].second &&
              selected[1].first==pairs[i][1].first && selected[1].second==pairs[i][1].second,
              "dealt ticket crossed a physical prior interval");
    }
  }
  rejects<chance::KernelError>([&] { (void)prior.private_deal(-1); },"dealt negative ticket accepted");
  rejects<chance::KernelError>([&] { (void)prior.private_deal(total); },"dealt end ticket accepted");
}

void sampled_grid_controls(SampledContraction route, bool frontier=false) {
  namespace sparse=openpoker::sampled_row_state;
  Fixture f;
  SampledFrontierFixture large;
  const std::array<std::array<std::uint8_t,5>,3> boards=frontier ?
      std::array<std::array<std::uint8_t,5>,3>{{{16,17,32,33,35},{16,17,32,33,35},{16,17,32,33,48}}} :
      std::array<std::array<std::uint8_t,5>,3>{{{4,5,6,7,8},{4,5,6,7,8},{4,5,6,7,0}}};
  const auto sb=frontier ? std::span<const chance::WeightedHand>(large.sb) :
                           std::span<const chance::WeightedHand>(f.sb);
  const auto bb=frontier ? std::span<const chance::WeightedHand>(large.bb) :
                           std::span<const chance::WeightedHand>(f.bb);
  std::optional<sparse::State> state;
  bool saw_zero=false, saw_negative=false, saw_changed=false;
  for (std::size_t draw=0;draw<boards.size();++draw) {
    FrozenGame game(frontier ? large.config : f.config,frontier ? large.deck : f.deck,sb,bb);
    const auto stage=FrozenUpdate::run_sampled(game,boards[draw],state ? &*state : nullptr,route);
    require(!stage.rows.empty() && stage.prefix_fold_queries && stage.full_board_queries,
            "changing draw did not exercise fold and showdown");
    if (!state) state.emplace(stage.regret_denominator);
    require(state->usage().iterations==draw && !state->usage().pending.rows,
            "evaluating the changing draw mutated the row store");
    state->begin(draw,stage.regret_denominator);
    {
      require(stage.rows.size()<=868,"sampled control output row limit");
      std::cout<<"DRAW "<<draw<<' '<<stage.rows.size()<<' '<<stage.regret_denominator
               <<' '<<stage.forecast.work_upper<<' '<<stage.chance_work<<' '
               <<stage.history_work<<' '<<stage.common_regret_work<<' '
               <<stage.average_work<<' '<<stage.policy_work<<' '<<stage.prepared_rank_calls<<'\n';
    }
    for (const auto &row : stage.rows) {
      const sparse::Key key{row.actor,row.first,row.second,row.history};
      const auto previous=state->committed_row(key);
      require(row.grid_policy_units.size()==row.actions.size() && row.policy_exponents.empty(),
              "changing draw used the wrong action representation");
      if (previous) {
        const auto all=std::ranges::all_of(row.grid_policy_units,[&](auto units) {
          return units==openpoker::dyadic_policy::grid_units/row.actions.size() ||
                 units==openpoker::dyadic_policy::grid_units/row.actions.size()+1;
        });
        saw_changed=saw_changed || !all;
      }
      {
        std::cout<<"ROW "<<static_cast<unsigned>(row.actor)<<' '<<static_cast<unsigned>(row.first)
                 <<' '<<static_cast<unsigned>(row.second)<<' '<<row.history.size();
        for (const auto& token:row.history) std::cout<<' '<<token;
        std::cout<<' '<<row.actions.size()<<' '<<row.average_denominator<<' '
                 <<row.average_mass_numerator;
      }
      for (std::size_t a=0;a<row.actions.size();++a) {
        saw_zero=saw_zero || (row.grid_policy_units[a]==0 && row.regret_numerators[a]!=0);
        saw_negative=saw_negative || row.regret_numerators[a]<0;
        std::cout<<' '<<row.actions[a]<<' '<<row.grid_policy_units[a]
                           <<' '<<row.regret_numerators[a]<<' '<<row.average_numerators[a];
      }
      std::cout<<'\n';
      state->stage(draw,key,row.actions,row.regret_numerators,row.average_numerators,
                   row.average_denominator);
    }
    state->commit(draw);
  }
  require(state->usage().iterations==boards.size() && saw_negative && saw_changed && saw_zero,
          "changing draw did not exercise signed, changing and zero-action policies");
}
void widen_sampled_bets(betting::Config& config,unsigned streets) {
  if (streets>3) throw std::invalid_argument("invalid sampled menu profile");
  for (std::size_t street=4-streets;street<4;++street)
    config.stages[street].bets={.5,.75,1.};
}

enum class SeededGame { uniform9, dealt9, dealt11, history11, full52, full52_policy, wide52, wide52_reuse };

struct QualityRun {
  std::uint64_t seed, draws;
};

void sampled_grid_seeded(SeededGame profile,std::optional<QualityRun> quality=std::nullopt,
                         bool linear=false) {
  const bool curve=bool(quality);
  const bool dealt=profile!=SeededGame::uniform9;
  const bool eleven=profile==SeededGame::dealt11 || profile==SeededGame::history11;
  const bool reuse_template=profile==SeededGame::wide52_reuse;
  const bool wide=reuse_template || profile==SeededGame::wide52;
  const bool packed=wide || curve;
  const bool policy_replay=curve || wide || profile==SeededGame::full52_policy;
  const bool full_deck=wide || profile==SeededGame::full52_policy || profile==SeededGame::full52;
  const bool history_replay=policy_replay || full_deck || profile==SeededGame::history11;
  namespace sparse=openpoker::sampled_row_state;
  namespace grid=openpoker::dyadic_policy;
  SampledFrontierFixture f;
  if (wide) widen_sampled_bets(f.config,3);
  if (eleven) {
    require(dealt,"eleven-card seeded route requires physical deals");
    const std::array<std::uint8_t,11> cards{0,1,16,17,24,32,33,35,37,43,48};
    f.deck=chance::DeckDefinition::reduced(cards);
  }
  std::array<std::vector<chance::WeightedHand>,2> full_ranges;
  if (full_deck) {
    require(dealt && history_replay,"full-deck control requires dealt history replay");
    f.deck=chance::DeckDefinition::full52();
    for (std::size_t seat=0;seat<2;++seat) {
      auto& range=full_ranges[seat];
      range.reserve(1326);
      for (std::uint8_t first=0;first<52;++first)
        for (std::uint8_t second=first+1;second<52;++second) {
          const auto index=range.size();
          const auto weight=1+(index*(seat==0 ? 17 : 29)+3*seat)%31;
          range.push_back({{first,second},std::bit_cast<std::uint64_t>(static_cast<double>(weight))});
        }
      require(range.size()==1326,"full-deck range census");
    }
  }
  const UniformPublicBoards boards(f.deck);
  const std::uint64_t seed=curve ? quality->seed : 0x4f504c2026111601ULL;
  const std::uint64_t draws=curve ? quality->draws : 32;
  constexpr std::uint64_t draw_work_cap=500000000;
  const std::uint64_t attempt_cap=dealt ? 8*draws : 64;
  constexpr std::size_t output_cap=2U<<20;
  // Each word is reproducible from the retained seed, including rejections.
  std::uint64_t random_state=seed;
  const auto next_word=[&] {
    auto z=(random_state+=0x9e3779b97f4a7c15ULL);
    z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL;
    z=(z^(z>>27))*0x94d049bb133111ebULL;
    return z^(z>>31);
  };
  std::size_t bytes=0;
  const auto emit=[&](const std::ostringstream& line) {
    const auto text=line.str();
    if (text.size()+1>output_cap-bytes)
      throw std::length_error("seeded policy output bound exceeded");
    bytes+=text.size()+1;
    std::cout<<text<<'\n';
    if (!std::cout) throw std::runtime_error("seeded policy output failed");
  };
  std::ostringstream header;
  header<<(linear ? "SAMPLED_PROOF9_LINEAR_QUALITY_V1 " :
             curve ? "SAMPLED_PROOF9_QUALITY_V1 " :
             wide ? "SAMPLED_FULL52_WIDE_POLICY_REPLAY_V1 " :
             policy_replay ? "SAMPLED_FULL52_POLICY_REPLAY_V1 " :
             full_deck ? "SAMPLED_FULL52_DEALT_REPLAY_V1 " :
             history_replay ? "SAMPLED_PROOF11_DEALT_HISTORY_REPLAY_V1 " :
             eleven ? "SAMPLED_PROOF11_DEALT_V1 " :
             dealt ? "SAMPLED_PROOF9_DEALT_V1 " : "SAMPLED_PROOF9_V1 ")
        <<seed<<' '<<draws<<' '<<attempt_cap<<' '<<draw_work_cap;
  emit(header);
  std::optional<sparse::State> state;
  std::optional<FrozenBettingPlan> plan;
  std::uint64_t attempts=0, reserved=0, rank_calls=0;
  std::optional<chance::PublicChanceKernel> prior;
  if (dealt) {
    if (full_deck) prior.emplace(full_ranges[0],full_ranges[1],f.deck);
    else prior.emplace(f.sb,f.bb,f.deck);
  }
  const auto word_attempt=[&] {
    if (attempts==attempt_cap) throw std::length_error("sampled word attempts exceeded");
    ++attempts;
    return next_word();
  };
  const auto ticket=[&](const CommonInteger& limit) {
    const CommonInteger top=limit-1;
    const auto bits=chance::prior::magnitude_bits(top);
    CommonInteger candidate;
    do {
      candidate=0;
      for (std::size_t offset=0;offset<bits;offset+=64) {
        const auto take=std::min<std::size_t>(64,bits-offset);
        auto word=word_attempt();
        if (take<64) word&=(std::uint64_t{1}<<take)-1;
        candidate|=CommonInteger(word)<<offset;
      }
    } while (candidate>=limit);
    return candidate;
  };
  sparse::Limits state_limits;
  state_limits.iterations=draws;
  state_limits.stage_calls=draws*868;
  for (std::uint64_t draw=0;draw<draws;++draw) {
    auto proposal=boards;
    CommonInteger selected_ticket;
    std::array<chance::Hand,2> private_deal{};
    std::array<chance::WeightedHand,1> sb{}, bb{};
    if (dealt) {
      selected_ticket=ticket(prior->normalizer_integer());
      private_deal=prior->private_deal(selected_ticket);
      const auto mask=[](chance::Hand h) {return (1ULL<<h.first)|(1ULL<<h.second);};
      proposal=UniformPublicBoards(f.deck,mask(private_deal[0])|mask(private_deal[1]));
      sb[0]={private_deal[0],std::bit_cast<std::uint64_t>(1.)};
      bb[0]={private_deal[1],std::bit_cast<std::uint64_t>(1.)};
    }
    std::optional<std::uint64_t> ordinal;
    std::uint64_t word=0;
    do {
      word=word_attempt();
      ordinal=proposal.ordinal_from_word(word);
    } while (!ordinal);
    const auto board=proposal.at(*ordinal);
    const auto sb_range=dealt ? std::span<const chance::WeightedHand>(sb) :
                                std::span<const chance::WeightedHand>(f.sb);
    const auto bb_range=dealt ? std::span<const chance::WeightedHand>(bb) :
                                std::span<const chance::WeightedHand>(f.bb);
    std::optional<FrozenGame> game;
    if (plan) game.emplace(*plan,sb_range,bb_range);
    else game.emplace(f.config,f.deck,sb_range,bb_range);
    if (reuse_template && !plan) plan.emplace(game->betting_plan());
    const auto contraction=policy_replay ? SampledContraction::dealt_policy_replay :
        history_replay ? SampledContraction::dealt_history_replay :
        dealt ? SampledContraction::dealt : SampledContraction::prepared;
    const auto stage=FrozenUpdate::run_sampled(*game,board,state ? &*state : nullptr,
                                               contraction,linear ? draw+1 : 1);
    if (stage.rows.size()>868 || stage.forecast.work_upper>draw_work_cap)
      throw std::length_error("seeded draw exceeds pinned envelope");
    reserved+=stage.forecast.work_upper;
    rank_calls+=stage.prepared_rank_calls;
    if (!state) state.emplace(stage.regret_denominator,state_limits);
    state->begin(draw,stage.regret_denominator);
    for (const auto& row:stage.rows)
      state->stage(draw,{row.actor,row.first,row.second,row.history},row.actions,
                   row.regret_numerators,row.average_numerators,row.average_denominator);
    state->commit(draw);
    std::ostringstream line;
    line<<"DRAW "<<draw<<' '<<attempts<<' '<<word<<' '<<*ordinal;
    if (dealt) {
      line<<' '<<selected_ticket;
      for (const auto hand:private_deal)
        line<<' '<<static_cast<unsigned>(hand.first)<<' '<<static_cast<unsigned>(hand.second);
    }
    for (const auto card:board) line<<' '<<static_cast<unsigned>(card);
    line<<' '<<stage.rows.size()<<' '<<stage.forecast.work_upper<<' '<<stage.prepared_rank_calls;
    if (eleven || full_deck || curve) line<<' '<<stage.chance_work<<' '<<stage.history_work<<' '<<stage.common_regret_work
                     <<' '<<stage.average_work<<' '<<stage.policy_work;
    emit(line);
  }
  grid::Quantizer quantizer;
  const auto usage=state->usage();
  std::ostringstream summary;
  summary<<"POLICY "<<usage.iterations<<' '<<usage.committed.rows<<' '<<usage.committed.slots<<' '
         <<usage.stage_calls<<' '<<reserved<<' '<<rank_calls<<' '<<attempts;
  emit(summary);
  const std::vector<std::string>* previous_history=nullptr;
  state->visit_committed([&](const sparse::Key& key,const sparse::RowView& row) {
    const auto policy=quantizer.average_export(row.average);
    std::ostringstream line;
    line<<(packed ? "PACK " : "ROW ")<<static_cast<unsigned>(key.actor)<<' '
        <<static_cast<unsigned>(key.first_card)<<' '<<static_cast<unsigned>(key.second_card);
    if (packed) {
      std::size_t common=0;
      if (previous_history) {
        const auto different=std::ranges::mismatch(*previous_history,key.history);
        common=static_cast<std::size_t>(different.in2-key.history.begin());
      }
      line<<' '<<common<<' '<<key.history.size()-common;
      for (std::size_t k=common;k<key.history.size();++k) line<<' '<<key.history[k];
      line<<' '<<row.actions.size()<<std::hex;
      for (const auto unit:policy.units()) line<<' '<<unit;
      emit(line);
      previous_history=&key.history;
      return;
    }
    line<<' '<<key.history.size();
    for (const auto& token:key.history) line<<' '<<token;
    line<<' '<<row.actions.size();
    for (std::size_t a=0;a<row.actions.size();++a)
      line<<' '<<row.actions[a]<<' '<<policy.units()[a];
    emit(line);
  });
  std::ostringstream footer;
  footer<<"END "<<quantizer.receipt().rows<<' '<<quantizer.receipt().work;
  if (full_deck) {
    const auto& receipt=prior->receipt();
    footer<<' '<<receipt.modeled_work<<' '<<receipt.retained_entries
          <<' '<<receipt.peak_scratch_entries<<' '<<receipt.peak_integer_payload_bits
          <<' '<<receipt.prefix_queries<<' '<<receipt.terminal_queries<<' '<<receipt.rank_calls;
  }
  emit(footer);
}

void sampled_menu_frontier() {
  for (unsigned wider=0;wider<=3;++wider) {
    Fixture f;
    auto config=SampledFrontierFixture().config;
    widen_sampled_bets(config,wider);
    FrozenGame game(config,chance::DeckDefinition::full52(),f.sb,f.bb);
    const auto &shape=game.template_receipt();
    FrozenGame cached_game(config,chance::DeckDefinition::full52(),f.sb,f.bb);
    const auto forecast=FrozenUpdate::forecast(game,{4,5,6,7,8},ProposalKind::uniform_public,
        true,true,SampledContraction::dealt_history_replay);
    const auto cached=FrozenUpdate::forecast(cached_game,{4,5,6,7,8},ProposalKind::uniform_public,
        true,true,SampledContraction::dealt_policy_replay);
    require(game.chance_receipt().terminal_queries==0,"menu forecast entered terminal");
    std::cout<<"MENUS "<<wider<<' '<<shape.nodes<<' '<<shape.logical_occurrences
             <<' '<<forecast.rows_upper<<' '<<forecast.slots_upper<<' '
             <<forecast.work_upper<<' '<<forecast.admitted<<' '
             <<cached.work_upper<<' '<<cached.admitted<<'\n';
  }
}

void betting_plan_reuse_controls() {
  const Fixture f;
  const auto plan=[&] {
    const FrozenGame initial(f.config,f.deck,f.sb,f.bb);
    auto admitted=initial.betting_plan();
    const FrozenGame reused(admitted,f.sb,f.bb);
    require(&initial.template_receipt()==&reused.template_receipt() &&
            &initial.chance_receipt()!=&reused.chance_receipt() &&
            initial.setup_receipt().work==reused.setup_receipt().work,
            "reused betting template or independent chance owner differs");
    return admitted;
  }();
  FrozenGame another(plan,f.sb,f.bb);
  require(another.template_receipt().nodes>0,"reused betting plan did not outlive genesis");
}

void sampled_average_weight_controls() {
  const Fixture f;
  const std::array<std::uint8_t,5> board{4,5,6,7,8};
  FrozenGame equal(f.config,f.deck,f.sb,f.bb), linear(f.config,f.deck,f.sb,f.bb);
  constexpr auto route=SampledContraction::dealt_policy_replay;
  const auto a=FrozenUpdate::run_sampled(equal,board,nullptr,route);
  const auto b=FrozenUpdate::run_sampled(linear,board,nullptr,route,7);
  require(a.rows.size()==b.rows.size() && a.regret_denominator==b.regret_denominator,
          "linear average changed admitted regret image");
  for (std::size_t i=0;i<a.rows.size();++i) {
    const auto& before=a.rows[i];
    const auto& after=b.rows[i];
    require(before.actor==after.actor && before.first==after.first && before.second==after.second &&
            before.history==after.history && before.actions==after.actions &&
            before.grid_policy_units==after.grid_policy_units && before.regret_numerators==after.regret_numerators &&
            before.average_denominator==after.average_denominator &&
            before.average_mass_numerator*7==after.average_mass_numerator,"linear average changed the unweighted draw");
    for (std::size_t action=0;action<before.actions.size();++action)
      require(before.average_numerators[action]*7==after.average_numerators[action],"linear own-reach average differs");
  }
  for (const auto weight:std::array<std::uint64_t,2>{0,513}) {
    FrozenGame outside(f.config,f.deck,f.sb,f.bb);
    rejects<FrozenUpdateError>([&] { (void)FrozenUpdate::run_sampled(outside,board,nullptr,route,weight); },
                               "out-of-range average weight accepted");
  }
}

void sampled_grid_frontier(SampledContraction route) {
  SampledFrontierFixture f;
  FrozenGame game(f.config,f.deck,f.sb,f.bb);
  const auto &geometry=game.template_receipt();
  require(geometry.nodes==388 && geometry.logical_occurrences==1105 && geometry.max_depth==15,
          "sampled frontier fixture geometry changed");
  const auto fcast=FrozenUpdate::forecast(game,{16,17,24,33,35},
      ProposalKind::uniform_public,true,true,route);
  require(game.chance_receipt().terminal_queries==0,"sampled frontier executed a terminal");
  std::cout<<"FRONTIER "<<fcast.admitted<<' '<<fcast.work_upper<<' '<<fcast.chance_work_upper<<' '
           <<fcast.history_work_upper<<' '<<fcast.arithmetic_work_upper<<' '<<fcast.policy_work_upper
           <<' '<<fcast.integer_bits_upper<<' '<<fcast.rows_upper<<' '<<fcast.slots_upper
           <<' '<<fcast.terminal_occurrences<<'\n';
}
} // namespace
int main(int argc,char **argv) {
  try {
    if (argc==2 || (argc==3 && std::string_view(argv[2])=="--linear")) {
      const std::string_view argument(argv[1]);
      const bool linear=argc==3;
      constexpr std::array<std::pair<std::string_view,QualityRun>,5> quality_runs{{
          {"sampled-grid-quality-a32",{0x4f504c2026111601ULL,32}},
          {"sampled-grid-quality-a128",{0x4f504c2026111601ULL,128}},
          {"sampled-grid-quality-a512",{0x4f504c2026111601ULL,512}},
          {"sampled-grid-quality-b128",{0x243f6a8885a308d3ULL,128}},
          {"sampled-grid-quality-c128",{0x13198a2e03707344ULL,128}}
      }};
      for (const auto& [name,run]:quality_runs) {
        if (argument!=name) continue;
        sampled_grid_seeded(SeededGame::dealt9,run,linear);
        return 0;
      }
      require(!linear,"linear averaging requires a named quality case");
      if (argument=="sampled-grid" || argument=="sampled-grid-prepared") {
        sampled_grid_controls(argument=="sampled-grid" ? SampledContraction::direct : SampledContraction::prepared);
        return 0;
      }
      if (argument=="sampled-grid-seeded" || argument=="sampled-grid-dealt-seeded") {
        sampled_grid_seeded(argument=="sampled-grid-dealt-seeded" ? SeededGame::dealt9 : SeededGame::uniform9);
        return 0;
      }
      if (argument=="sampled-grid-dealt-eleven-seeded" || argument=="sampled-grid-eleven-history-replay") {
        sampled_grid_seeded(argument=="sampled-grid-eleven-history-replay" ?
                            SeededGame::history11 : SeededGame::dealt11);
        return 0;
      }
      if (argument=="sampled-grid-full52-dealt-seeded") {
        sampled_grid_seeded(SeededGame::full52);
        return 0;
      }
      if (argument=="sampled-grid-full52-policy-replay" || argument=="sampled-grid-full52-wide") {
        sampled_grid_seeded(argument=="sampled-grid-full52-wide" ?
                            SeededGame::wide52 : SeededGame::full52_policy);
        return 0;
      }
      if (argument=="sampled-grid-full52-wide-template-reuse") {
        sampled_grid_seeded(SeededGame::wide52_reuse);
        return 0;
      }
      if (argument=="sampled-grid-full52-menu-frontier") {
        sampled_menu_frontier();
        return 0;
      }
      if (argument=="sampled-grid-prepared-frontier-draws") {
        sampled_grid_controls(SampledContraction::prepared,true);
        return 0;
      }
      if (argument=="sampled-grid-frontier" || argument=="sampled-grid-prepared-frontier") {
        sampled_grid_frontier(argument=="sampled-grid-frontier" ? SampledContraction::direct
                                                               : SampledContraction::prepared);
        return 0;
      }
    }
    require(argc==1,"unexpected control argument");
    arithmetic_controls();
    parent_and_reuse_controls();
    history_and_profile_controls();
    zero_target_and_action_controls();
    implicit_public_board_controls();
    private_deal_controls();
    sampled_row_publication_controls();
    sampled_row_precision_controls();
    sampled_average_weight_controls();
    betting_plan_reuse_controls();
    publish_frozen_sample_controls();
    std::cout
        << "PASS frozen-update primitive, admission, identity and zero-target controls"
        << std::endl;
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "FAIL " << e.what() << std::endl;
    return 2;
  }
}
