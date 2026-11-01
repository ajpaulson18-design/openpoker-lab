#include "../../native/virtual_betting_template.hpp"
#include <array>
#include <bit>
#include <cfenv>
#include <cstdint>
#include <exception>
#include <iostream>
#include <string_view>

namespace v = openpoker::virtual_betting_template;
namespace {
bool need(bool condition, const char *label) {
    if (!condition)
        std::cerr << "FAIL " << label << '\n';
    return condition;
}
template <class F> bool rejects(F &&fn, const char *fragment) {
    try {
        fn();
        return false;
    } catch (const v::Error &error) {
        return std::string_view(error.what()).find(fragment) != std::string_view::npos;
    }
}
v::Config config() {
    v::Config c;
    c.stacks = {4., 4.};
    c.sb = .5;
    c.bb = 1.;
    c.stages[0].raises = {.5};
    c.stages[0].max_raises = 1;
    for (std::size_t i = 1; i < 4; ++i) {
        c.stages[i].bets = {.5};
        c.stages[i].raises = {};
        c.stages[i].max_raises = 0;
        c.stages[i].all_in = false;
    }
    return c;
}
}
int main() {
    bool ok = true;
    // Expected encodings are independent CPython 3.12 round(x,9) anchors,
    // with negative zero canonicalized as in the independent money rules.
    constexpr std::array<std::array<std::uint64_t, 2>, 13> anchors{
        {{{0x0000000000000000ULL, 0x0000000000000000ULL}},
         {{0x8000000000000000ULL, 0x0000000000000000ULL}},
         {{0x0000000000000001ULL, 0x0000000000000000ULL}},
         {{0x8000000000000001ULL, 0x0000000000000000ULL}},
         {{0x3e012e0be826d695ULL, 0x3e112e0be826d695ULL}},
         {{0x3e012e0be826d694ULL, 0x0000000000000000ULL}},
         {{0x3e012e0be826d696ULL, 0x3e112e0be826d695ULL}},
         {{0xbe012e0be826d695ULL, 0xbe112e0be826d695ULL}},
         {{0x3fe000000044b830ULL, 0x3fe000000089705fULL}},
         {{0x3fe000000044b82fULL, 0x3fe0000000000000ULL}},
         {{0x3fe000000044b831ULL, 0x3fe000000089705fULL}},
         {{0x412e847ffffffffcULL, 0x412e848000000000ULL}},
         {{0x412e848000000000ULL, 0x412e848000000000ULL}}}};
    for (const auto &pair : anchors) {
        v::Meter m{v::Limits{}, {}};
        const auto x = v::money_with_units(std::bit_cast<double>(pair[0]), m);
        ok &= need(std::bit_cast<std::uint64_t>(x.first) == pair[1],
                   "nine-place ties/adjacent anchor");
    }
    auto c = config();
    v::Limits low_work;
    low_work.work = 1;
    v::Meter m{low_work, {}};
    ok &= need(rejects([&] { (void)v::money_with_units(.5, m); }, "work limit"),
               "money precharge work reject");
    ok &= need(m.receipt.work == 0 && m.receipt.peak_scratch_entries == 0,
               "money reject before charged work/scratch");
    for (int kind = 0; kind < 5; ++kind) {
        v::Limits lim;
        if (kind == 0)
            lim.nodes = 1;
        if (kind == 1)
            lim.edges = 1;
        if (kind == 2)
            lim.entries = 100;
        if (kind == 3)
            lim.depth = 1;
        if (kind == 4)
            lim.occurrences = 1;
        ok &= need(rejects([&] { (void)v::Template(c, lim); }, "exceeded"),
                   "bounded template limit rejection");
    }
    auto bad_blinds = c;
    bad_blinds.sb = .5000000002;
    bad_blinds.bb = .5000000013;
    ok &= need(rejects([&] { (void)v::Template(bad_blinds); }, "rounded stack or blinds"),
               "blind ordering checked after cleanup");
    v::State invalid;
    invalid.history_empty = false;
    invalid.street = 3;
    invalid.actor = 1;
    invalid.committed = {1., 1.};
    ok &= need(rejects([&] { (void)v::Template(c, {}, &invalid); }, "requires a local ledger"),
               "postflop origin required");
    invalid.origin_present = true;
    invalid.origin = 1.;
    invalid.boundary_pot = 123.;
    invalid.local_present = true;
    invalid.local = {0, 0};
    ok &= need(rejects([&] { (void)v::Template(c, {}, &invalid); }, "boundary pot"),
               "boundary ledger mismatch");
    invalid.boundary_pot = 2.;
    invalid.committed[1] = 1.5;
    ok &= need(rejects([&] { (void)v::Template(c, {}, &invalid); }, "commitment mismatch"),
               "local commitment mismatch");
    auto blind = c;
    blind.stacks = {.5, 1.};
    const v::Template allin(blind);
    const auto &state = allin.nodes()[allin.root()].state;
    ok &=
        need(state.phase == v::Phase::showdown && state.committed[0] == .5 &&
                 state.committed[1] == 1. && std::min(state.committed[0], state.committed[1]) == .5,
             "blind all-in original commitments and matched transfer");
    const int old = std::fegetround();
    if (std::fesetround(FE_UPWARD) != 0) {
        std::cerr << "FAIL set rounding\n";
        return 1;
    }
    ok &= need(rejects([&] { (void)v::Template(c); }, "nearest rounding required"),
               "rounding mode reject");
    if (std::fesetround(old) != 0) {
        std::cerr << "FAIL restore rounding\n";
        return 1;
    }
    if (!ok)
        return 1;
    std::cout << "ALL VIRTUAL BETTING TEMPLATE CONTROLS PASSED\n";
    return 0;
}
