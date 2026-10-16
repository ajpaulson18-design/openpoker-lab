/*
 * Bounded native full-board equity helper.
 *
 * The rank tuple is a local C implementation of pokerlab/cards.py:rank_hand
 * over five to seven distinct cards. No third-party source, ranking tables,
 * runtime dependencies, or generated lookup data are used.
 *
 * Input is fully parsed and validated before ranking. COUNT accepts at most
 * four ordered private-hand pairs and emits exact C(48,5) W/T/L counts.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define MAX_INPUT_BYTES (256u * 1024u)
#define MAX_COUNT_PAIRS 4u
#define MAX_RANK_REQUESTS 4096u
#define MAX_HAND_CARDS 7u
#define COUNT_BOARDS_PER_PAIR UINT64_C(1712304)

static unsigned char input_buffer[MAX_INPUT_BYTES + 1u];

typedef struct { int value[6]; } RankValue;
typedef struct { uint8_t arity; uint8_t card[MAX_HAND_CARDS]; } RankRequest;
typedef struct { uint64_t wins, ties, losses; } OutcomeCounts;
typedef struct { size_t position, length; } Parser;

static RankRequest rank_requests[MAX_RANK_REQUESTS];
static RankValue rank_results[MAX_RANK_REQUESTS];

static int is_ascii_space(unsigned char byte) {
    return byte == 0x20u || (byte >= 0x09u && byte <= 0x0du);
}

static int read_input(void) {
    size_t used = fread(input_buffer, 1u, MAX_INPUT_BYTES + 1u, stdin);
    size_t index;
    if (ferror(stdin) || used > MAX_INPUT_BYTES) return 0;
    for (index = 0u; index < used; ++index) {
        if (input_buffer[index] == 0u || input_buffer[index] > 0x7fu) return 0;
    }
    input_buffer[used] = 0u;
    return 1;
}

static int next_token(Parser *parser, const unsigned char **token, size_t *length) {
    size_t start, end;
    while (parser->position < parser->length
           && is_ascii_space(input_buffer[parser->position])) ++parser->position;
    if (parser->position >= parser->length) return 0;
    start = parser->position;
    end = start;
    while (end < parser->length && !is_ascii_space(input_buffer[end])) ++end;
    *token = input_buffer + start;
    *length = end - start;
    parser->position = end;
    return 1;
}

static int token_is(const unsigned char *token, size_t length, const char *expected) {
    size_t expected_length = strlen(expected);
    return length == expected_length && memcmp(token, expected, expected_length) == 0;
}

static int parse_decimal(const unsigned char *token, size_t length, uint64_t *value) {
    size_t index;
    uint64_t parsed = 0u;
    if (length == 0u) return 0;
    for (index = 0u; index < length; ++index) {
        unsigned char byte = token[index];
        uint64_t digit;
        if (byte < (unsigned char)'0' || byte > (unsigned char)'9') return 0;
        digit = (uint64_t)(byte - (unsigned char)'0');
        if (parsed > (UINT64_MAX - digit) / 10u) return 0;
        parsed = parsed * 10u + digit;
    }
    *value = parsed;
    return 1;
}

static int next_decimal(Parser *parser, uint64_t *value) {
    const unsigned char *token;
    size_t length;
    return next_token(parser, &token, &length) && parse_decimal(token, length, value);
}

static int next_card(Parser *parser, uint8_t *card) {
    uint64_t value;
    if (!next_decimal(parser, &value) || value > 51u) return 0;
    *card = (uint8_t)value;
    return 1;
}

static int cards_are_distinct(const uint8_t *cards, unsigned int count) {
    unsigned int left, right;
    for (left = 0u; left < count; ++left)
        for (right = left + 1u; right < count; ++right)
            if (cards[left] == cards[right]) return 0;
    return 1;
}

static int parse_input(char *mode, uint64_t *request_count,
                       uint8_t count_pairs[MAX_COUNT_PAIRS][4], Parser *parser) {
    const unsigned char *token;
    size_t length;
    uint64_t parsed_count, request_index;
    parser->position = 0u;
    parser->length = strlen((const char *)input_buffer);
    if (!next_token(parser, &token, &length)
            || !token_is(token, length, "OPENPOKER_NATIVE_V1")) return 0;
    if (!next_token(parser, &token, &length)) return 0;
    if (token_is(token, length, "COUNT")) *mode = 'C';
    else if (token_is(token, length, "RANK")) *mode = 'R';
    else return 0;
    if (!next_decimal(parser, &parsed_count)) return 0;
    if ((*mode == 'C' && (parsed_count < 1u || parsed_count > MAX_COUNT_PAIRS))
            || (*mode == 'R'
                && (parsed_count < 1u || parsed_count > MAX_RANK_REQUESTS))) return 0;
    *request_count = parsed_count;

    if (*mode == 'C') {
        for (request_index = 0u; request_index < parsed_count; ++request_index) {
            unsigned int card_index;
            for (card_index = 0u; card_index < 4u; ++card_index)
                if (!next_card(parser, &count_pairs[request_index][card_index])) return 0;
            if (!cards_are_distinct(count_pairs[request_index], 4u)) return 0;
        }
    } else {
        for (request_index = 0u; request_index < parsed_count; ++request_index) {
            uint64_t arity;
            unsigned int card_index;
            if (!next_decimal(parser, &arity) || arity < 5u || arity > MAX_HAND_CARDS)
                return 0;
            rank_requests[request_index].arity = (uint8_t)arity;
            for (card_index = 0u; card_index < (unsigned int)arity; ++card_index)
                if (!next_card(parser, &rank_requests[request_index].card[card_index]))
                    return 0;
            if (!cards_are_distinct(rank_requests[request_index].card, (unsigned int)arity))
                return 0;
        }
    }
    return !next_token(parser, &token, &length);
}

static int highest_straight(uint16_t rank_mask) {
    int high;
    for (high = 14; high >= 6; --high) {
        uint16_t required = (uint16_t)(0x1fu << (unsigned int)(high - 4));
        if ((rank_mask & required) == required) return high;
    }
    {
        uint16_t wheel = (uint16_t)((1u << 14) | (1u << 5) | (1u << 4)
                                    | (1u << 3) | (1u << 2));
        return (rank_mask & wheel) == wheel ? 5 : 0;
    }
}

static int highest_rank_with_min_count(const uint8_t counts[15], int minimum,
                                       int excluded_rank) {
    int rank;
    for (rank = 14; rank >= 2; --rank)
        if (rank != excluded_rank && counts[rank] >= (uint8_t)minimum) return rank;
    return 0;
}

/* Card ids follow DECK rank-major order with suits c,d,h,s inside each rank. */
static void rank_hand(const uint8_t *cards, unsigned int card_count, RankValue *result) {
    uint8_t rank_counts[15] = {0u}, suit_counts[4] = {0u};
    uint16_t suit_masks[4] = {0u, 0u, 0u, 0u}, rank_mask = 0u;
    unsigned int index;
    int rank, trip_rank, pair_rank, kicker_index;
    for (index = 0u; index < 6u; ++index) result->value[index] = 0;
    for (index = 0u; index < card_count; ++index) {
        unsigned int suit = (unsigned int)(cards[index] % 4u);
        rank = 2 + (int)(cards[index] / 4u);
        ++rank_counts[rank];
        ++suit_counts[suit];
        suit_masks[suit] = (uint16_t)(suit_masks[suit] | (uint16_t)(1u << rank));
        rank_mask = (uint16_t)(rank_mask | (uint16_t)(1u << rank));
    }

    for (index = 0u; index < 4u; ++index) {
        if (suit_counts[index] >= 5u) {
            int high = highest_straight(suit_masks[index]);
            if (high != 0) { result->value[0] = 8; result->value[1] = high; return; }
        }
    }
    for (rank = 14; rank >= 2; --rank) {
        if (rank_counts[rank] == 4u) {
            result->value[0] = 7;
            result->value[1] = rank;
            result->value[2] = highest_rank_with_min_count(rank_counts, 1, rank);
            return;
        }
    }

    trip_rank = highest_rank_with_min_count(rank_counts, 3, 0);
    if (trip_rank != 0) {
        pair_rank = highest_rank_with_min_count(rank_counts, 2, trip_rank);
        if (pair_rank != 0) {
            result->value[0] = 6; result->value[1] = trip_rank;
            result->value[2] = pair_rank; return;
        }
    }
    for (index = 0u; index < 4u; ++index) {
        if (suit_counts[index] >= 5u) {
            result->value[0] = 5;
            kicker_index = 1;
            for (rank = 14; rank >= 2 && kicker_index <= 5; --rank)
                if ((suit_masks[index] & (uint16_t)(1u << rank)) != 0u)
                    result->value[kicker_index++] = rank;
            return;
        }
    }
    {
        int high = highest_straight(rank_mask);
        if (high != 0) { result->value[0] = 4; result->value[1] = high; return; }
    }
    if (trip_rank != 0) {
        result->value[0] = 3; result->value[1] = trip_rank; kicker_index = 2;
        for (rank = 14; rank >= 2 && kicker_index <= 3; --rank)
            if (rank != trip_rank && rank_counts[rank] != 0u)
                result->value[kicker_index++] = rank;
        return;
    }
    {
        int top_pair = 0, second_pair = 0;
        for (rank = 14; rank >= 2; --rank) {
            if (rank_counts[rank] == 2u) {
                if (top_pair == 0) top_pair = rank;
                else { second_pair = rank; break; }
            }
        }
        if (second_pair != 0) {
            result->value[0] = 2; result->value[1] = top_pair;
            result->value[2] = second_pair;
            for (rank = 14; rank >= 2; --rank)
                if (rank != top_pair && rank != second_pair && rank_counts[rank] != 0u) {
                    result->value[3] = rank; break;
                }
            return;
        }
        if (top_pair != 0) {
            result->value[0] = 1; result->value[1] = top_pair; kicker_index = 2;
            for (rank = 14; rank >= 2 && kicker_index <= 4; --rank)
                if (rank != top_pair && rank_counts[rank] != 0u)
                    result->value[kicker_index++] = rank;
            return;
        }
    }
    result->value[0] = 0; kicker_index = 1;
    for (rank = 14; rank >= 2 && kicker_index <= 5; --rank)
        if (rank_counts[rank] != 0u) result->value[kicker_index++] = rank;
}

static int compare_ranks(const RankValue *left, const RankValue *right) {
    unsigned int index;
    for (index = 0u; index < 6u; ++index) {
        if (left->value[index] > right->value[index]) return 1;
        if (left->value[index] < right->value[index]) return -1;
    }
    return 0;
}

static int count_pair(const uint8_t pair[4], OutcomeCounts *counts) {
    uint8_t remaining[48], player_one[7], player_two[7];
    unsigned int remaining_count = 0u, card, first;
    uint64_t boards_seen = 0u;
    RankValue rank_one, rank_two;
    memset(counts, 0, sizeof(*counts));
    for (card = 0u; card < 52u; ++card) {
        if (card != pair[0] && card != pair[1] && card != pair[2] && card != pair[3])
            remaining[remaining_count++] = (uint8_t)card;
    }
    if (remaining_count != 48u) return 0;

    for (first = 0u; first < 44u; ++first) {
        unsigned int second;
        for (second = first + 1u; second < 45u; ++second) {
            unsigned int third;
            for (third = second + 1u; third < 46u; ++third) {
                unsigned int fourth;
                for (fourth = third + 1u; fourth < 47u; ++fourth) {
                    unsigned int fifth;
                    for (fifth = fourth + 1u; fifth < 48u; ++fifth) {
                        int comparison;
                        player_one[0] = pair[0]; player_one[1] = pair[1];
                        player_two[0] = pair[2]; player_two[1] = pair[3];
                        player_one[2] = player_two[2] = remaining[first];
                        player_one[3] = player_two[3] = remaining[second];
                        player_one[4] = player_two[4] = remaining[third];
                        player_one[5] = player_two[5] = remaining[fourth];
                        player_one[6] = player_two[6] = remaining[fifth];
                        rank_hand(player_one, 7u, &rank_one);
                        rank_hand(player_two, 7u, &rank_two);
                        comparison = compare_ranks(&rank_one, &rank_two);
                        if (comparison > 0) ++counts->wins;
                        else if (comparison < 0) ++counts->losses;
                        else ++counts->ties;
                        ++boards_seen;
                    }
                }
            }
        }
    }
    return boards_seen == COUNT_BOARDS_PER_PAIR
        && counts->wins + counts->ties + counts->losses == COUNT_BOARDS_PER_PAIR;
}

static int run_count(uint64_t pair_count,
                     uint8_t pairs[MAX_COUNT_PAIRS][4],
                     OutcomeCounts counts[MAX_COUNT_PAIRS]) {
    uint64_t pair_index;
    for (pair_index = 0u; pair_index < pair_count; ++pair_index)
        if (!count_pair(pairs[pair_index], &counts[pair_index])) return 0;
    return 1;
}

static void run_rank(uint64_t request_count) {
    uint64_t request_index;
    for (request_index = 0u; request_index < request_count; ++request_index)
        rank_hand(rank_requests[request_index].card, rank_requests[request_index].arity,
                  &rank_results[request_index]);
}

static void print_count_result(uint64_t pair_count,
                               const OutcomeCounts counts[MAX_COUNT_PAIRS]) {
    uint64_t pair_index;
    uint64_t rank_calls = UINT64_C(2) * pair_count * COUNT_BOARDS_PER_PAIR;
    printf("{\"schema_version\":1,\"mode\":\"count\",\"counts\":[");
    for (pair_index = 0u; pair_index < pair_count; ++pair_index) {
        if (pair_index != 0u) putchar(',');
        printf("[%llu,%llu,%llu]", (unsigned long long)counts[pair_index].wins,
               (unsigned long long)counts[pair_index].ties,
               (unsigned long long)counts[pair_index].losses);
    }
    printf("],\"boards_per_pair\":%llu,\"rank_calls\":%llu}\n",
           (unsigned long long)COUNT_BOARDS_PER_PAIR,
           (unsigned long long)rank_calls);
}

static void print_rank_result(uint64_t request_count) {
    uint64_t request_index;
    printf("{\"schema_version\":1,\"mode\":\"rank\",\"ranks\":[");
    for (request_index = 0u; request_index < request_count; ++request_index) {
        unsigned int value_index;
        if (request_index != 0u) putchar(',');
        putchar('[');
        for (value_index = 0u; value_index < 6u; ++value_index) {
            if (value_index != 0u) putchar(',');
            printf("%d", rank_results[request_index].value[value_index]);
        }
        putchar(']');
    }
    printf("]}\n");
}

int main(void) {
    Parser parser;
    char mode = 0;
    uint64_t request_count = 0u;
    uint8_t count_pairs[MAX_COUNT_PAIRS][4] = {{0u}};
    OutcomeCounts counts[MAX_COUNT_PAIRS];
    if (!read_input() || !parse_input(&mode, &request_count, count_pairs, &parser)) {
        fputs("invalid input\n", stderr);
        return 2;
    }
    if (mode == 'C') {
        if (!run_count(request_count, count_pairs, counts)) {
            fputs("count failure\n", stderr);
            return 3;
        }
        print_count_result(request_count, counts);
    } else {
        run_rank(request_count);
        print_rank_result(request_count);
    }
    if (fflush(stdout) == EOF || ferror(stdout)) {
        fputs("output failure\n", stderr);
        return 4;
    }
    return 0;
}
