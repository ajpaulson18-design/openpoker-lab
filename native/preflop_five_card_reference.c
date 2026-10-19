/* Project-owned validation reference: sorted five-card patterns and exhaustive
 * best-five subsets. No production evaluator, lookup data or third-party code.
 * Fixed finite modes only; not a public solver backend or installed binary. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static uint64_t five_calls = UINT64_C(0);
static uint64_t seven_calls = UINT64_C(0);

static uint32_t encode(unsigned int category, const unsigned int values[5]) {
    unsigned int k;
    uint32_t result = category;
    for (k = 0u; k < 5u; ++k) result = (result << 4u) | values[k];
    return result;
}

static uint32_t five(const unsigned int cards[5]) {
    unsigned int ranks[5], histogram[15] = {0u}, values[5] = {0u};
    unsigned int i, j, key, distinct = 0u, straight = 0u, flush = 1u;
    unsigned int quad = 0u, trip = 0u, pairs[2] = {0u}, singles[5] = {0u};
    unsigned int pair_count = 0u, single_count = 0u;
    int rank;
    ++five_calls;
    for (i = 0u; i < 5u; ++i) {
        ranks[i] = 2u + cards[i] / 4u;
        ++histogram[ranks[i]];
        if (cards[i] % 4u != cards[0] % 4u) flush = 0u;
    }
    /* Sort five ranks directly; this reference never uses seven-card masks. */
    for (i = 1u; i < 5u; ++i) {
        key = ranks[i]; j = i;
        while (j > 0u && ranks[j - 1u] < key) {
            ranks[j] = ranks[j - 1u]; --j;
        }
        ranks[j] = key;
    }
    for (rank = 14; rank >= 2; --rank) {
        unsigned int n = histogram[rank];
        if (n != 0u) ++distinct;
        if (n == 4u) quad = (unsigned int)rank;
        if (n == 3u) trip = (unsigned int)rank;
        if (n == 2u) pairs[pair_count++] = (unsigned int)rank;
        if (n == 1u) singles[single_count++] = (unsigned int)rank;
    }
    if (distinct == 5u) {
        if (ranks[0] - ranks[4] == 4u) straight = ranks[0];
        else if (ranks[0] == 14u && ranks[1] == 5u && ranks[2] == 4u &&
                 ranks[3] == 3u && ranks[4] == 2u) straight = 5u;
    }
    if (straight != 0u && flush != 0u) {
        values[0] = straight; return encode(8u, values);
    }
    if (quad != 0u) {
        values[0] = quad; values[1] = singles[0]; return encode(7u, values);
    }
    if (trip != 0u && pair_count == 1u) {
        values[0] = trip; values[1] = pairs[0]; return encode(6u, values);
    }
    if (flush != 0u) return encode(5u, ranks);
    if (straight != 0u) { values[0] = straight; return encode(4u, values); }
    if (trip != 0u) {
        values[0] = trip; values[1] = singles[0]; values[2] = singles[1];
        return encode(3u, values);
    }
    if (pair_count == 2u) {
        values[0] = pairs[0]; values[1] = pairs[1]; values[2] = singles[0];
        return encode(2u, values);
    }
    if (pair_count == 1u) {
        values[0] = pairs[0];
        for (i = 0u; i < 3u; ++i) values[i + 1u] = singles[i];
        return encode(1u, values);
    }
    return encode(0u, ranks);
}

static uint32_t seven(const unsigned int cards[7]) {
    unsigned int a, b, k, used, subset[5];
    uint32_t best = 0u;
    ++seven_calls;
    for (a = 0u; a < 6u; ++a) for (b = a + 1u; b < 7u; ++b) {
        uint32_t candidate;
        used = 0u;
        for (k = 0u; k < 7u; ++k) if (k != a && k != b) subset[used++] = cards[k];
        candidate = five(subset);
        if (candidate > best) best = candidate;
    }
    return best;
}

static int all_five(void) {
    unsigned int a, b, c, d, e, hand[5], k;
    unsigned char row[6];
    for (a = 0u; a < 48u; ++a) for (b = a + 1u; b < 49u; ++b)
    for (c = b + 1u; c < 50u; ++c) for (d = c + 1u; d < 51u; ++d)
    for (e = d + 1u; e < 52u; ++e) {
        uint32_t score;
        hand[0] = a; hand[1] = b; hand[2] = c; hand[3] = d; hand[4] = e;
        score = five(hand);
        for (k = 0u; k < 6u; ++k) row[k] = (unsigned char)((score >> (4u * (5u - k))) & 15u);
        if (fwrite(row, 1u, 6u, stdout) != 6u) return 3;
    }
    return fflush(stdout) == 0 ? 0 : 3;
}

static int count_pairs(const unsigned int *holes, unsigned int pair_count, const char *reference) {
    unsigned int pair, k, deck[48], size, a, b, c, d, e, sb[7], bb[7];
    uint64_t boards_total = UINT64_C(0);
    if (printf("{\"schema_version\":1,\"reference\":\"%s\",\"pairs\":[", reference) < 0) return 3;
    for (pair = 0u; pair < pair_count; ++pair) {
        uint64_t wins = 0u, ties = 0u, losses = 0u;
        size = 0u;
        for (k = 0u; k < 52u; ++k) {
            if (k != holes[4u * pair + 0u] && k != holes[4u * pair + 1u] &&
                k != holes[4u * pair + 2u] && k != holes[4u * pair + 3u]) deck[size++] = k;
        }
        if (size != 48u) return 4;
        sb[0] = holes[4u * pair + 0u]; sb[1] = holes[4u * pair + 1u];
        bb[0] = holes[4u * pair + 2u]; bb[1] = holes[4u * pair + 3u];
        for (a = 0u; a < 44u; ++a) for (b = a + 1u; b < 45u; ++b)
        for (c = b + 1u; c < 46u; ++c) for (d = c + 1u; d < 47u; ++d)
        for (e = d + 1u; e < 48u; ++e) {
            uint32_t left, right;
            sb[2] = bb[2] = deck[a]; sb[3] = bb[3] = deck[b];
            sb[4] = bb[4] = deck[c]; sb[5] = bb[5] = deck[d]; sb[6] = bb[6] = deck[e];
            left = seven(sb); right = seven(bb);
            if (left > right) ++wins;
            else if (left < right) ++losses;
            else ++ties;
        }
        if (wins + ties + losses != UINT64_C(1712304)) return 4;
        boards_total += wins + ties + losses;
        if (printf("%s{\"sb_ids\":[%u,%u],\"bb_ids\":[%u,%u],\"wins\":%" PRIu64
                   ",\"ties\":%" PRIu64 ",\"losses\":%" PRIu64 ",\"boards\":1712304}",
                   pair == 0u ? "" : ",", sb[0], sb[1], bb[0], bb[1], wins, ties, losses) < 0) return 3;
    }
    if (printf("],\"boards_total\":%" PRIu64 ",\"five_card_rank_calls\":%" PRIu64
               ",\"seven_card_rank_calls\":%" PRIu64 "}\n",
               boards_total, five_calls, seven_calls) < 0) return 3;
    return fflush(stdout) == 0 ? 0 : 3;
}

static int parse_card_id(const char *text, unsigned int *value) {
    size_t length = strlen(text);
    unsigned int n;
    if (length < 1u || length > 2u || text[0] < '0' || text[0] > '9') return 0;
    n = (unsigned int)(text[0] - '0');
    if (length == 2u) {
        if (text[1] < '0' || text[1] > '9') return 0;
        n = n * 10u + (unsigned int)(text[1] - '0');
    }
    if (n >= 52u) return 0;
    *value = n; return 1;
}

static int explicit_pairs(int argc, char **argv) {
    unsigned int selected[16], canonical[16], pairs, p, k, j;
    if (argc < 6 || argc > 18 || (argc - 2) % 4 != 0) return 2;
    pairs = (unsigned int)(argc - 2) / 4u;
    for (p = 0u; p < pairs; ++p) {
        for (k = 0u; k < 4u; ++k) {
            if (!parse_card_id(argv[2u + 4u * p + k], &selected[4u * p + k])) return 2;
            for (j = 0u; j < k; ++j)
                if (selected[4u * p + k] == selected[4u * p + j]) return 2;
        }
        for (k = 0u; k < 4u; k += 2u) {
            unsigned int a = selected[4u * p + k], b = selected[4u * p + k + 1u];
            canonical[4u * p + k] = a < b ? a : b;
            canonical[4u * p + k + 1u] = a < b ? b : a;
        }
        for (j = 0u; j < p; ++j) {
            int duplicate = 1;
            for (k = 0u; k < 4u; ++k)
                if (canonical[4u * p + k] != canonical[4u * j + k]) duplicate = 0;
            if (duplicate != 0) return 2;
        }
    }
    return count_pairs(selected, pairs, "preflop-five-card-pairs-v2");
}

int main(int argc, char **argv) {
    static const unsigned int basis[12] = {49u,51u,45u,47u,49u,51u,44u,45u,49u,51u,44u,46u};
#ifdef _WIN32
    if (_setmode(_fileno(stdout), _O_BINARY) == -1) return 3;
#endif
    if (argc < 2) return 2;
    if (strcmp(argv[1], "--count-pairs") == 0) return explicit_pairs(argc, argv);
    if (argc != 2) return 2;
    if (strcmp(argv[1], "--all-five") == 0) return all_five();
    if (strcmp(argv[1], "--count-basis") == 0) return count_pairs(basis, 3u, "preflop-five-card-basis-v1");
    return 2;
}
