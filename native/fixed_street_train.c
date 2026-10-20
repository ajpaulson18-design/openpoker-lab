/*
 * Project-owned scalar CFR trainer for validated finite public trees.
 *
 * No external evaluator, game library, generated table, runtime dependency,
 * sampling or arbitrary callback is used. Input and every structural/world
 * invariant are validated before training and before any stdout is written.
 */
#include <float.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#include <stdlib.h>
#include <string.h>

#define MAX_INPUT_BYTES (8u * 1024u * 1024u)
#define MAX_HANDS 128u
#define MAX_NODES 250000u
#define MAX_WORLDS 384u
#define MAX_SLOTS 1000000u
#define MAX_ACTIONS 12u
#define MAX_DEPTH 32u
#define MAX_ITERATIONS 10000u
#define MAX_MODELED_WORK UINT64_C(500000000)
#define MAX_HEAP_BYTES (UINT64_C(64) * 1024u * 1024u)
#define MODEL_HEADER "OPENPOKER_FIXED_TRAIN_V2"

_Static_assert(CHAR_BIT == 8, "protocol requires 8-bit bytes");
_Static_assert(sizeof(double) == 8, "protocol requires binary64 double");
_Static_assert(sizeof(uint64_t) == 8, "protocol requires 64-bit uint64_t");
_Static_assert(DBL_MANT_DIG == 53 && DBL_MAX_EXP == 1024 && DBL_MIN_EXP == -1021,
               "protocol requires IEEE-754 binary64 double");

typedef struct {
    double constant;
    double coefficient;
    uint32_t children[MAX_ACTIONS];
    uint32_t slot_base;
    uint8_t kind;       /* 0 = decision, 1 = terminal */
    uint8_t player;
    uint8_t action_count;
    uint8_t depth;      /* UINT8_MAX means not reached during tree validation */
} Node;

typedef struct {
    double mass;
    /* Mode 0: sign. Mode 1: pair signed mass. */
    double measure;
    uint8_t hand0;
    uint8_t hand1;
} World;

typedef struct {
    size_t position;
} Parser;

typedef struct {
    size_t start;
    size_t length;
} Token;

static unsigned char input_buffer[MAX_INPUT_BYTES + 1u];

static int fail(const char *message) {
    fprintf(stderr, "error: %s\n", message);
    return 2;
}

static int ascii_space(unsigned char value) {
    return value == (unsigned char)' ' || value == (unsigned char)'\t' ||
           value == (unsigned char)'\r' || value == (unsigned char)'\n';
}

static int read_input(size_t *length_out) {
    size_t length = 0u;
    while (length <= (size_t)MAX_INPUT_BYTES) {
        size_t capacity = (size_t)MAX_INPUT_BYTES + 1u - length;
        size_t count = fread(input_buffer + length, 1u, capacity, stdin);
        length += count;
        if (length > (size_t)MAX_INPUT_BYTES) {
            return 0;
        }
        if (count == 0u) {
            if (ferror(stdin)) {
                return 0;
            }
            if (feof(stdin)) {
                break;
            }
        }
    }
    for (size_t index = 0u; index < length; ++index) {
        if (input_buffer[index] == 0u || input_buffer[index] > 0x7fu) {
            return 0;
        }
    }
    *length_out = length;
    return 1;
}

static int next_token(Parser *parser, size_t input_length, Token *token) {
    while (parser->position < input_length && ascii_space(input_buffer[parser->position])) {
        ++parser->position;
    }
    if (parser->position >= input_length) {
        return 0;
    }
    token->start = parser->position;
    while (parser->position < input_length && !ascii_space(input_buffer[parser->position])) {
        ++parser->position;
    }
    token->length = parser->position - token->start;
    return token->length != 0u;
}

/* Fields remain on their declared record; only the final completeness scan
 * accepts arbitrary protocol whitespace between trailing characters. */
static int next_field(Parser *parser, size_t input_length, Token *token) {
    while (parser->position < input_length &&
           (input_buffer[parser->position] == (unsigned char)' ' ||
            input_buffer[parser->position] == (unsigned char)'\t')) {
        ++parser->position;
    }
    if (parser->position >= input_length ||
        input_buffer[parser->position] == (unsigned char)'\r' ||
        input_buffer[parser->position] == (unsigned char)'\n') {
        return 0;
    }
    token->start = parser->position;
    while (parser->position < input_length && !ascii_space(input_buffer[parser->position])) {
        ++parser->position;
    }
    token->length = parser->position - token->start;
    return token->length != 0u;
}

static int token_equals(Token token, const char *literal) {
    size_t length = strlen(literal);
    return token.length == length && memcmp(input_buffer + token.start, literal, length) == 0;
}

static int parse_unsigned(Token token, uint64_t maximum, uint64_t *value_out) {
    uint64_t value = 0u;
    if (token.length == 0u) {
        return 0;
    }
    for (size_t index = 0u; index < token.length; ++index) {
        unsigned char ch = input_buffer[token.start + index];
        uint64_t digit;
        if (ch < (unsigned char)'0' || ch > (unsigned char)'9') {
            return 0;
        }
        digit = (uint64_t)(ch - (unsigned char)'0');
        if (digit > maximum) {
            return 0;
        }
        if (value > (maximum - digit) / 10u) {
            return 0;
        }
        value = value * 10u + digit;
    }
    if (value > maximum) {
        return 0;
    }
    *value_out = value;
    return 1;
}

static int parse_hex_double(Token token, double *value_out) {
    uint64_t bits = 0u;
    if (token.length != 16u) {
        return 0;
    }
    for (size_t index = 0u; index < 16u; ++index) {
        unsigned char ch = input_buffer[token.start + index];
        uint64_t nibble;
        if (ch >= (unsigned char)'0' && ch <= (unsigned char)'9') {
            nibble = (uint64_t)(ch - (unsigned char)'0');
        } else if (ch >= (unsigned char)'a' && ch <= (unsigned char)'f') {
            nibble = (uint64_t)(ch - (unsigned char)'a') + 10u;
        } else {
            return 0;
        }
        bits = (bits << 4u) | nibble;
    }
    memcpy(value_out, &bits, sizeof(bits));
    return isfinite(*value_out) != 0;
}

static int header_newline(Parser *parser, size_t input_length) {
    if (parser->position >= input_length) {
        return 0;
    }
    if (input_buffer[parser->position] == (unsigned char)'\n') {
        ++parser->position;
        return 1;
    }
    if (input_buffer[parser->position] == (unsigned char)'\r' &&
        parser->position + 1u < input_length &&
        input_buffer[parser->position + 1u] == (unsigned char)'\n') {
        parser->position += 2u;
        return 1;
    }
    return 0;
}

static int record_newline(Parser *parser, size_t input_length) {
    while (parser->position < input_length &&
           (input_buffer[parser->position] == (unsigned char)' ' ||
            input_buffer[parser->position] == (unsigned char)'\t')) {
        ++parser->position;
    }
    if (parser->position < input_length &&
        input_buffer[parser->position] == (unsigned char)'\n') {
        ++parser->position;
        return 1;
    }
    if (parser->position + 1u < input_length &&
        input_buffer[parser->position] == (unsigned char)'\r' &&
        input_buffer[parser->position + 1u] == (unsigned char)'\n') {
        parser->position += 2u;
        return 1;
    }
    return 0;
}

static int read_u32(Parser *parser, size_t input_length, uint64_t maximum,
                    uint32_t *value_out) {
    Token token;
    uint64_t value;
    if (!next_field(parser, input_length, &token) ||
        !parse_unsigned(token, maximum, &value)) {
        return 0;
    }
    *value_out = (uint32_t)value;
    return 1;
}

static int read_hex_value(Parser *parser, size_t input_length, double *value_out) {
    Token token;
    return next_field(parser, input_length, &token) && parse_hex_double(token, value_out);
}

static int checked_add_u64(uint64_t left, uint64_t right, uint64_t *out) {
    if (UINT64_MAX - left < right) {
        return 0;
    }
    *out = left + right;
    return 1;
}

static int checked_mul_u64(uint64_t left, uint64_t right, uint64_t *out) {
    if (left != 0u && right > UINT64_MAX / left) {
        return 0;
    }
    *out = left * right;
    return 1;
}

static int add_product(uint64_t *total, uint64_t left, uint64_t right) {
    uint64_t product;
    return checked_mul_u64(left, right, &product) && checked_add_u64(*total, product, total);
}

static int memory_fits(uint32_t mode, uint32_t node_count, uint32_t world_count,
                       uint32_t slot_count, uint32_t hand0_count, uint32_t hand1_count) {
    uint64_t bytes = (uint64_t)MAX_INPUT_BYTES + 1u;
    uint64_t hand_sum = (uint64_t)hand0_count + hand1_count;
    if (!add_product(&bytes, node_count, (uint64_t)sizeof(Node)) ||
        !add_product(&bytes, world_count, (uint64_t)sizeof(World)) ||
        !add_product(&bytes, node_count, (uint64_t)sizeof(uint8_t)) ||
        !add_product(&bytes, node_count, (uint64_t)sizeof(uint32_t)) ||
        !add_product(&bytes, slot_count, (uint64_t)(4u * sizeof(double))) ||
        (mode == 1u &&
         (!add_product(&bytes, MAX_DEPTH + 1u,
                       UINT64_C(16) * hand_sum * (uint64_t)sizeof(double)) ||
          !add_product(&bytes, 2u, hand_sum * (uint64_t)sizeof(double))) ) ||
        !checked_add_u64(bytes, UINT64_C(65536), &bytes)) {
        return 0;
    }
    return bytes <= MAX_HEAP_BYTES;
}

static int work_fits(uint32_t mode, uint32_t iterations, uint32_t algorithm,
                     uint32_t node_count, uint32_t world_count, uint32_t slot_count,
                     uint32_t hand0_count, uint32_t hand1_count, size_t input_length) {
    uint64_t per_iteration = 0u;
    uint64_t work = 0u;
    uint64_t setup = UINT64_C(4352);
    uint64_t pass_count = algorithm == 2u ? 3u : 1u;
    if (mode == 0u) {
        if (!add_product(&per_iteration, 8u * (uint64_t)world_count,
                         (uint64_t)node_count * pass_count)) {
            return 0;
        }
    } else {
        uint64_t one_public_pass = 0u;
        uint64_t hand_sum = (uint64_t)hand0_count + hand1_count;
        if (!add_product(&one_public_pass, 8u, node_count) ||
            !add_product(&one_public_pass, 4u * (uint64_t)world_count, node_count) ||
            !add_product(&one_public_pass, 12u * hand_sum, node_count) ||
            !checked_mul_u64(one_public_pass, pass_count, &per_iteration)) {
            return 0;
        }
    }
    if (!add_product(&per_iteration, 24u, (uint64_t)slot_count) ||
        !add_product(&setup, 400u, (uint64_t)node_count) ||
        !add_product(&setup, 336u, (uint64_t)world_count) ||
        !add_product(&setup, 272u, (uint64_t)slot_count) ||
        !checked_mul_u64((uint64_t)iterations, per_iteration, &work) ||
        !checked_add_u64(work, setup, &work)) {
        return 0;
    }
    (void)input_length;
    return work <= MAX_MODELED_WORK;
}

static int validate_tree(Node *nodes, uint8_t *indegree, uint32_t *stack,
                         uint32_t node_count) {
    uint32_t top = 0u;
    uint32_t visited = 0u;
    if (indegree[0] != 0u) {
        return 0;
    }
    for (uint32_t index = 1u; index < node_count; ++index) {
        if (indegree[index] != 1u) {
            return 0;
        }
    }
    nodes[0].depth = 0u;
    stack[top++] = 0u;
    while (top != 0u) {
        uint32_t current = stack[--top];
        Node *node = &nodes[current];
        ++visited;
        if (node->kind == 0u) {
            uint32_t child_depth = (uint32_t)node->depth + 1u;
            if (child_depth > MAX_DEPTH) {
                return 0;
            }
            for (uint32_t action = 0u; action < (uint32_t)node->action_count; ++action) {
                uint32_t child = node->children[action];
                if (nodes[child].depth != UINT8_MAX) {
                    return 0;
                }
                nodes[child].depth = (uint8_t)child_depth;
                if (top >= node_count) {
                    return 0;
                }
                stack[top++] = child;
            }
        }
    }
    return visited == node_count;
}

static double compensated_sum_add(double value, double *sum, double *correction) {
    double next = *sum + value;
    if (fabs(*sum) >= fabs(value)) {
        *correction += (*sum - next) + value;
    } else {
        *correction += (value - next) + *sum;
    }
    *sum = next;
    return *sum + *correction;
}

static double compensated_sum_finish(double sum, double correction) {
    return sum + correction;
}

static double regret_match_sum(const double *regrets, uint32_t base, uint32_t count,
                               int compensated) {
    double sum = 0.0;
    double correction = 0.0;
    for (uint32_t action = 0u; action < count; ++action) {
        double regret = regrets[base + action];
        if (!isfinite(regret)) {
            return NAN;
        }
        if (regret > 0.0) {
            if (compensated) {
                (void)compensated_sum_add(regret, &sum, &correction);
            } else {
                sum += regret;
            }
        }
    }
    return compensated_sum_finish(sum, correction);
}

static int rematch(const Node *nodes, uint32_t node_count, const uint32_t hands[2],
                   const double *regrets, double *current, int compensated) {
    for (uint32_t index = 0u; index < node_count; ++index) {
        const Node *node = &nodes[index];
        if (node->kind != 0u) {
            continue;
        }
        uint32_t hand_count = hands[node->player];
        uint32_t action_count = (uint32_t)node->action_count;
        for (uint32_t hand = 0u; hand < hand_count; ++hand) {
            uint32_t base = node->slot_base + hand * action_count;
            double total = regret_match_sum(regrets, base, action_count, compensated);
            if (!isfinite(total)) {
                return 0;
            }
            if (total > 0.0) {
                for (uint32_t action = 0u; action < action_count; ++action) {
                    double regret = regrets[base + action];
                    current[base + action] = regret > 0.0 ? regret / total : 0.0;
                }
            } else {
                double uniform = 1.0 / (double)action_count;
                for (uint32_t action = 0u; action < action_count; ++action) {
                    current[base + action] = uniform;
                }
            }
        }
    }
    return 1;
}

static int rematch_player(const Node *nodes, uint32_t node_count,
                          const uint32_t hands[2], const double *regrets,
                          double *current, int compensated, uint32_t player) {
    for (uint32_t index = 0u; index < node_count; ++index) {
        const Node *node = &nodes[index];
        if (node->kind != 0u || (uint32_t)node->player != player) {
            continue;
        }
        uint32_t hand_count = hands[player];
        uint32_t action_count = (uint32_t)node->action_count;
        for (uint32_t hand = 0u; hand < hand_count; ++hand) {
            uint32_t base = node->slot_base + hand * action_count;
            double total = regret_match_sum(regrets, base, action_count, compensated);
            if (!isfinite(total)) {
                return 0;
            }
            if (total > 0.0) {
                for (uint32_t action = 0u; action < action_count; ++action) {
                    double regret = regrets[base + action];
                    current[base + action] = regret > 0.0 ? regret / total : 0.0;
                }
            } else {
                double uniform = 1.0 / (double)action_count;
                for (uint32_t action = 0u; action < action_count; ++action) {
                    current[base + action] = uniform;
                }
            }
        }
    }
    return 1;
}

static double traverse_train_scalar(uint32_t node_id, const Node *nodes, const World *world,
                             const uint32_t hands[2], const double *current,
                             double *deltas, double *sums, int algorithm,
                             int target_player, int accumulate_average,
                             double iteration_weight, double reach0, double reach1) {
    const Node *node = &nodes[node_id];
    if (node->kind == 1u) {
        return node->constant + node->coefficient * world->measure;
    }
    uint32_t action_count = (uint32_t)node->action_count;
    uint32_t hand = (uint32_t)(node->player == 0u ? world->hand0 : world->hand1);
    uint32_t base = node->slot_base + hand * action_count;
    double action_values[MAX_ACTIONS];
    double expected = 0.0;
    for (uint32_t action = 0u; action < action_count; ++action) {
        double probability = current[base + action];
        double next0 = reach0 * (node->player == 0u ? probability : 1.0);
        double next1 = reach1 * (node->player == 1u ? probability : 1.0);
        action_values[action] = traverse_train_scalar(node->children[action], nodes, world, hands,
                                               current, deltas, sums, algorithm,
                                               target_player, accumulate_average,
                                               iteration_weight, next0, next1);
        expected += probability * action_values[action];
    }
    if (target_player < 0 || (uint32_t)target_player == (uint32_t)node->player) {
        double opponent_reach = node->player == 0u ? reach1 : reach0;
        double utility_sign = node->player == 0u ? 1.0 : -1.0;
        for (uint32_t action = 0u; action < action_count; ++action) {
            double change = world->mass * opponent_reach * utility_sign *
                            (action_values[action] - expected);
            deltas[base + action] += change;
        }
    }
    if (accumulate_average) {
        double own_reach = node->player == 0u ? reach0 : reach1;
        if (algorithm == 2) {
            double factor = world->mass * own_reach * iteration_weight;
            for (uint32_t action = 0u; action < action_count; ++action) {
                sums[base + action] += factor * current[base + action];
            }
        } else {
            for (uint32_t action = 0u; action < action_count; ++action) {
                sums[base + action] += world->mass * own_reach * current[base + action] *
                                       iteration_weight;
            }
        }
    }
    (void)hands;
    return expected;
}

static void traverse_average_scalar(uint32_t node_id, const Node *nodes, const World *world,
                             const double *current, double *sums, double iteration_weight,
                             double reach0, double reach1) {
    const Node *node = &nodes[node_id];
    if (node->kind == 1u) {
        return;
    }
    uint32_t action_count = (uint32_t)node->action_count;
    uint32_t hand = (uint32_t)(node->player == 0u ? world->hand0 : world->hand1);
    uint32_t base = node->slot_base + hand * action_count;
    double own_reach = node->player == 0u ? reach0 : reach1;
    double factor = world->mass * own_reach * iteration_weight;
    for (uint32_t action = 0u; action < action_count; ++action) {
        sums[base + action] += factor * current[base + action];
    }
    for (uint32_t action = 0u; action < action_count; ++action) {
        double probability = current[base + action];
        double next0 = reach0 * (node->player == 0u ? probability : 1.0);
        double next1 = reach1 * (node->player == 1u ? probability : 1.0);
        traverse_average_scalar(node->children[action], nodes, world, current, sums,
                         iteration_weight, next0, next1);
    }
}

static int update_regrets(const Node *nodes, uint32_t node_count, const uint32_t hands[2],
                          double *regrets, const double *deltas, int algorithm,
                          int target_player, double positive_discount) {
    for (uint32_t index = 0u; index < node_count; ++index) {
        const Node *node = &nodes[index];
        if (node->kind != 0u ||
            (target_player >= 0 && (uint32_t)target_player != (uint32_t)node->player)) {
            continue;
        }
        uint32_t action_count = (uint32_t)node->action_count;
        for (uint32_t hand = 0u; hand < hands[node->player]; ++hand) {
            uint32_t base = node->slot_base + hand * action_count;
            for (uint32_t action = 0u; action < action_count; ++action) {
                double updated = regrets[base + action] + deltas[base + action];
                if (algorithm == 1) {
                    updated *= updated > 0.0 ? positive_discount : 0.5;
                } else if (algorithm == 2 && updated < 0.0) {
                    updated = 0.0;
                }
                if (!isfinite(updated)) {
                    return 0;
                }
                regrets[base + action] = updated;
            }
        }
    }
    return 1;
}

static int train_scalar(Node *nodes, uint32_t node_count, const World *worlds,
                 uint32_t world_count, const uint32_t hands[2], uint32_t slot_count,
                 uint32_t iterations, int algorithm, double *regrets, double *current,
                 double *deltas, double *sums) {
    for (uint32_t iteration = 1u; iteration <= iterations; ++iteration) {
        double iteration_weight;
        double positive_discount = 1.0;
        if (algorithm == 1) {
            double t15 = pow((double)iteration, 1.5);
            positive_discount = t15 / (t15 + 1.0);
            iteration_weight = (double)iteration * (double)iteration;
        } else if (algorithm == 2) {
            iteration_weight = (double)iteration;
        } else {
            iteration_weight = 1.0;
        }
        if (!isfinite(iteration_weight) || !isfinite(positive_discount) ||
            !rematch(nodes, node_count, hands, regrets, current, 0)) {
            return 0;
        }
        if (algorithm == 2) {
            for (int player = 0; player <= 1; ++player) {
                if (slot_count != 0u) {
                    memset(deltas, 0, (size_t)slot_count * sizeof(double));
                }
                for (uint32_t world_index = 0u; world_index < world_count; ++world_index) {
                    (void)traverse_train_scalar(0u, nodes, &worlds[world_index], hands, current,
                                         deltas, sums, algorithm, player, 0,
                                         iteration_weight, 1.0, 1.0);
                }
                if (!update_regrets(nodes, node_count, hands, regrets, deltas,
                                    algorithm, player, positive_discount) ||
                    !rematch(nodes, node_count, hands, regrets, current, 0)) {
                    return 0;
                }
            }
            for (uint32_t world_index = 0u; world_index < world_count; ++world_index) {
                traverse_average_scalar(0u, nodes, &worlds[world_index], current, sums,
                                 iteration_weight, 1.0, 1.0);
            }
        } else {
            if (slot_count != 0u) {
                memset(deltas, 0, (size_t)slot_count * sizeof(double));
            }
            for (uint32_t world_index = 0u; world_index < world_count; ++world_index) {
                (void)traverse_train_scalar(0u, nodes, &worlds[world_index], hands, current,
                                     deltas, sums, algorithm, -1, 1,
                                     iteration_weight, 1.0, 1.0);
            }
            if (!update_regrets(nodes, node_count, hands, regrets, deltas,
                                algorithm, -1, positive_discount)) {
                return 0;
            }
        }
    }
    return 1;
}

/* The public-batched layout keeps a bounded frame at every tree depth. Each
 * frame contains returned player values, both reach vectors, up to twelve
 * actor-action value vectors, and compensation for action-value summation. */
#define PUBLIC_FRAME_VECTORS 16u

static double *public_frame(double *arena, uint32_t depth, uint32_t hand_sum) {
    return arena + (size_t)depth * PUBLIC_FRAME_VECTORS * (size_t)hand_sum;
}

static int traverse_public(uint32_t node_id, uint32_t depth, const Node *nodes,
                           const World *worlds, uint32_t world_count,
                           const uint32_t hands[2], const double *current,
                           double *deltas, double *averages, const double *marginals,
                           double *arena, uint32_t hand_sum, int target_player,
                           int average_only, double average_factor,
                           const double *reach0, const double *reach1,
                           int compensate_other_sum) {
    const Node *node = &nodes[node_id];
    double *frame = public_frame(arena, depth, hand_sum);
    double *value0 = frame;
    double *value1 = value0 + hands[0];
    double *next_reach0 = frame + hand_sum;
    double *next_reach1 = next_reach0 + hands[0];
    double *action_values = frame + (size_t)2u * hand_sum;
    double *other_correction = action_values + (size_t)MAX_ACTIONS * hand_sum;
    memset(value0, 0, (size_t)hands[0] * sizeof(double));
    memset(value1, 0, (size_t)hands[1] * sizeof(double));
    if (average_only && node->kind == 1u) {
        return 1;
    }
    if (node->kind == 1u) {
        for (uint32_t world_index = 0u; world_index < world_count; ++world_index) {
            const World *world = &worlds[world_index];
            uint32_t hand0 = (uint32_t)world->hand0;
            uint32_t hand1 = (uint32_t)world->hand1;
            double scale0 = reach1[hand1];
            double scale1 = reach0[hand0];
            if (node->constant != 0.0) {
                value0[hand0] += world->mass * scale0 * node->constant;
                value1[hand1] -= world->mass * scale1 * node->constant;
            }
            if (node->coefficient != 0.0) {
                value0[hand0] += world->measure * scale0 * node->coefficient;
                value1[hand1] -= world->measure * scale1 * node->coefficient;
            }
        }
        return 1;
    }

    uint32_t actor = (uint32_t)node->player;
    uint32_t opponent = 1u - actor;
    uint32_t action_count = (uint32_t)node->action_count;
    uint32_t actor_hands = hands[actor];
    uint32_t actor_base = node->slot_base;
    double *actor_values = actor == 0u ? value0 : value1;
    double *other_values = actor == 0u ? value1 : value0;
    double *actor_child_values = action_values;
    memset(other_correction, 0, (size_t)hands[opponent] * sizeof(double));
    for (uint32_t hand = 0u; hand < actor_hands; ++hand) {
        uint32_t row = actor_base + hand * action_count;
        if (average_factor != 0.0) {
            double own_reach = actor == 0u ? reach0[hand] : reach1[hand];
            uint32_t marginal_base = actor == 0u ? 0u : hands[0];
            for (uint32_t action = 0u; action < action_count; ++action) {
                /* Match Python public_cfr's ordinary ordered += averaging. */
                averages[row + action] += marginals[marginal_base + hand] * own_reach *
                                          current[row + action] * average_factor;
            }
        }
    }

    for (uint32_t action = 0u; action < action_count; ++action) {
        for (uint32_t hand = 0u; hand < hands[0]; ++hand) {
            double probability = actor == 0u ? current[actor_base + hand * action_count + action] : 1.0;
            next_reach0[hand] = reach0[hand] * probability;
        }
        for (uint32_t hand = 0u; hand < hands[1]; ++hand) {
            double probability = actor == 1u ? current[actor_base + hand * action_count + action] : 1.0;
            next_reach1[hand] = reach1[hand] * probability;
        }
        if (!traverse_public(node->children[action], depth + 1u, nodes, worlds,
                             world_count, hands, current, deltas, averages, marginals,
                             arena, hand_sum, target_player, average_only,
                             average_factor, next_reach0, next_reach1,
                             compensate_other_sum)) {
            return 0;
        }
        double *child = public_frame(arena, depth + 1u, hand_sum);
        const double *child0 = child;
        const double *child1 = child0 + hands[0];
        const double *child_actor = actor == 0u ? child0 : child1;
        const double *child_other = actor == 0u ? child1 : child0;
        for (uint32_t hand = 0u; hand < actor_hands; ++hand) {
            actor_child_values[(size_t)action * actor_hands + hand] = child_actor[hand];
        }
        if (compensate_other_sum) {
            for (uint32_t hand = 0u; hand < hands[opponent]; ++hand) {
                (void)compensated_sum_add(child_other[hand], &other_values[hand],
                                          &other_correction[hand]);
            }
        } else {
            for (uint32_t hand = 0u; hand < hands[opponent]; ++hand) {
                other_values[hand] += child_other[hand];
            }
        }
    }
    if (compensate_other_sum) {
        for (uint32_t hand = 0u; hand < hands[opponent]; ++hand) {
            other_values[hand] = compensated_sum_finish(other_values[hand],
                                                         other_correction[hand]);
        }
    }
    if (average_only) {
        return 1;
    }

    for (uint32_t hand = 0u; hand < actor_hands; ++hand) {
        uint32_t row = actor_base + hand * action_count;
        double expected = 0.0;
        double correction = 0.0;
        for (uint32_t action = 0u; action < action_count; ++action) {
            (void)compensated_sum_add(current[row + action] *
                                      actor_child_values[(size_t)action * actor_hands + hand],
                                      &expected, &correction);
        }
        actor_values[hand] = compensated_sum_finish(expected, correction);
        if (target_player < 0 || target_player == (int)actor) {
            for (uint32_t action = 0u; action < action_count; ++action) {
                deltas[row + action] +=
                    actor_child_values[(size_t)action * actor_hands + hand] - actor_values[hand];
            }
        }
    }
    return 1;
}

static int train_public(Node *nodes, uint32_t node_count, const World *worlds,
                        uint32_t world_count, const uint32_t hands[2],
                        uint32_t slot_count, uint32_t iterations, int algorithm,
                        double *regrets, double *current, double *deltas,
                        double *sums, double *arena, double *marginals) {
    uint32_t hand_sum = hands[0] + hands[1];
    memset(marginals, 0, (size_t)hand_sum * sizeof(double));
    for (uint32_t index = 0u; index < world_count; ++index) {
        const World *world = &worlds[index];
        marginals[(size_t)world->hand0] += world->mass;
        marginals[(size_t)hands[0] + world->hand1] += world->mass;
    }
    double reach0[MAX_HANDS];
    double reach1[MAX_HANDS];
    for (uint32_t hand = 0u; hand < hands[0]; ++hand) reach0[hand] = 1.0;
    for (uint32_t hand = 0u; hand < hands[1]; ++hand) reach1[hand] = 1.0;
    for (uint32_t iteration = 1u; iteration <= iterations; ++iteration) {
        double average_factor = algorithm == 1 ? (double)iteration * (double)iteration :
                                (algorithm == 2 ? (double)iteration : 1.0);
        double positive_discount = 1.0;
        if (algorithm == 1) {
            double t15 = pow((double)iteration, 1.5);
            positive_discount = t15 / (t15 + 1.0);
        }
        if (!isfinite(average_factor) || !isfinite(positive_discount) ||
            ((algorithm != 2 || iteration == 1u) &&
             !rematch(nodes, node_count, hands, regrets, current, 1))) return 0;
        if (algorithm == 2) {
            for (int player = 0; player <= 1; ++player) {
                if (slot_count != 0u) memset(deltas, 0, (size_t)slot_count * sizeof(double));
                if (!traverse_public(0u, 0u, nodes, worlds, world_count, hands,
                                     current, deltas, sums, marginals, arena, hand_sum,
                                     player, 0, 0.0, reach0, reach1, 0) ||
                    !update_regrets(nodes, node_count, hands, regrets, deltas,
                                   algorithm, player, positive_discount) ||
                    !rematch_player(nodes, node_count, hands, regrets, current, 1,
                                    (uint32_t)player)) return 0;
            }
            if (slot_count != 0u) memset(deltas, 0, (size_t)slot_count * sizeof(double));
            if (!traverse_public(0u, 0u, nodes, worlds, world_count, hands,
                                 current, deltas, sums, marginals, arena, hand_sum,
                                 -1, 1, average_factor, reach0, reach1, 0)) return 0;
        } else {
            if (slot_count != 0u) memset(deltas, 0, (size_t)slot_count * sizeof(double));
            if (!traverse_public(0u, 0u, nodes, worlds, world_count, hands,
                                 current, deltas, sums, marginals, arena, hand_sum,
                                 -1, 0, average_factor, reach0, reach1, 1) ||
                !update_regrets(nodes, node_count, hands, regrets, deltas,
                               algorithm, -1, positive_discount)) return 0;
        }
        for (uint32_t slot = 0u; slot < slot_count; ++slot) {
            if (!isfinite(regrets[slot]) || !isfinite(sums[slot])) return 0;
        }
    }
    return 1;
}

static int normalize_and_validate(const Node *nodes, uint32_t node_count,
                                  const uint32_t hands[2], const double *sums,
                                  double *output, uint32_t slot_count, int compensated) {
    for (uint32_t index = 0u; index < node_count; ++index) {
        const Node *node = &nodes[index];
        if (node->kind != 0u) {
            continue;
        }
        uint32_t action_count = (uint32_t)node->action_count;
        for (uint32_t hand = 0u; hand < hands[node->player]; ++hand) {
            uint32_t base = node->slot_base + hand * action_count;
            double total = 0.0;
            double total_correction = 0.0;
            for (uint32_t action = 0u; action < action_count; ++action) {
                double value = sums[base + action];
                if (!isfinite(value) || value < 0.0) {
                    return 0;
                }
                if (compensated) {
                    (void)compensated_sum_add(value, &total, &total_correction);
                } else {
                    total += value;
                }
            }
            if (compensated) total = compensated_sum_finish(total, total_correction);
            if (!isfinite(total)) {
                return 0;
            }
            if (total > 0.0) {
                for (uint32_t action = 0u; action < action_count; ++action) {
                    output[base + action] = sums[base + action] / total;
                }
            } else {
                double uniform = 1.0 / (double)action_count;
                for (uint32_t action = 0u; action < action_count; ++action) {
                    output[base + action] = uniform;
                }
            }
            double check = 0.0;
            double check_correction = 0.0;
            for (uint32_t action = 0u; action < action_count; ++action) {
                double probability = output[base + action];
                if (!isfinite(probability) || probability < 0.0 || probability > 1.0) {
                    return 0;
                }
                if (compensated) {
                    (void)compensated_sum_add(probability, &check, &check_correction);
                } else {
                    check += probability;
                }
            }
            if (compensated) check = compensated_sum_finish(check, check_correction);
            if (!isfinite(check) || fabs(check - 1.0) > 1e-9) {
                return 0;
            }
        }
    }
    (void)slot_count;
    return 1;
}

static int output_policy(const double *policy, uint32_t slot_count) {
    if (printf(MODEL_HEADER " POLICY %" PRIu32 "\n", slot_count) < 0) {
        return 0;
    }
    for (uint32_t index = 0u; index < slot_count; ++index) {
        uint64_t bits;
        memcpy(&bits, &policy[index], sizeof(bits));
        if (printf("%016" PRIx64 "\n", bits) < 0) {
            return 0;
        }
    }
    return fflush(stdout) == 0;
}

int main(void) {
#ifdef _WIN32
    /* Text-mode Ctrl+Z must never truncate a request before complete-input
     * validation; binary output also keeps protocol bytes platform-neutral. */
    if (_setmode(_fileno(stdin), _O_BINARY) == -1 ||
        _setmode(_fileno(stdout), _O_BINARY) == -1) {
        fprintf(stderr, "error: cannot select binary protocol streams\n");
        return 2;
    }
#endif
    size_t input_length = 0u;
    Parser parser = {0u};
    Token token;
    uint32_t mode_u32, algorithm_u32, iterations, hand0_count, hand1_count;
    uint32_t node_count, world_count, slot_count;
    uint32_t hands[2];
    Node *nodes = NULL;
    World *worlds = NULL;
    uint8_t *indegree = NULL;
    uint32_t *stack = NULL;
    double *regrets = NULL, *current = NULL, *deltas = NULL, *sums = NULL;
    double *arena = NULL, *marginals = NULL;
    uint64_t slot_total = 0u;
    uint8_t active0[MAX_HANDS] = {0u};
    uint8_t active1[MAX_HANDS] = {0u};
    long double mass_total = 0.0L;
    int status = 2;

    if (!read_input(&input_length)) {
        return fail("input must be ASCII, NUL-free, complete and at most 8 MiB");
    }
    if (!next_field(&parser, input_length, &token) || !token_equals(token, MODEL_HEADER) ||
        !read_u32(&parser, input_length, 1u, &mode_u32) ||
        !read_u32(&parser, input_length, 2u, &algorithm_u32) ||
        !read_u32(&parser, input_length, MAX_ITERATIONS, &iterations) || iterations == 0u ||
        !read_u32(&parser, input_length, MAX_HANDS, &hand0_count) || hand0_count == 0u ||
        !read_u32(&parser, input_length, MAX_HANDS, &hand1_count) || hand1_count == 0u ||
        !read_u32(&parser, input_length, MAX_NODES, &node_count) || node_count == 0u ||
        !read_u32(&parser, input_length, MAX_WORLDS, &world_count) || world_count == 0u ||
        !read_u32(&parser, input_length, MAX_SLOTS, &slot_count) ||
        !header_newline(&parser, input_length)) {
        return fail("invalid protocol header or header newline");
    }
    hands[0] = hand0_count;
    hands[1] = hand1_count;
    if (!memory_fits(mode_u32, node_count, world_count, slot_count,
                     hand0_count, hand1_count)) {
        return fail("bounded memory estimate exceeds 64 MiB");
    }
    if (!work_fits(mode_u32, iterations, algorithm_u32, node_count, world_count,
                   slot_count, hand0_count, hand1_count, input_length)) {
        return fail("full requested training exceeds the 500,000,000 modeled-work limit");
    }

    nodes = (Node *)calloc((size_t)node_count, sizeof(Node));
    worlds = (World *)calloc((size_t)world_count, sizeof(World));
    indegree = (uint8_t *)calloc((size_t)node_count, sizeof(uint8_t));
    stack = (uint32_t *)malloc((size_t)node_count * sizeof(uint32_t));
    if (slot_count != 0u) {
        regrets = (double *)calloc((size_t)slot_count, sizeof(double));
        current = (double *)malloc((size_t)slot_count * sizeof(double));
        deltas = (double *)malloc((size_t)slot_count * sizeof(double));
        sums = (double *)calloc((size_t)slot_count, sizeof(double));
    }
    if (mode_u32 == 1u) {
        uint32_t hand_sum = hand0_count + hand1_count;
        size_t arena_count = ((size_t)MAX_DEPTH + 1u) * PUBLIC_FRAME_VECTORS * hand_sum;
        arena = (double *)calloc(arena_count, sizeof(double));
        marginals = (double *)calloc((size_t)hand_sum, sizeof(double));
    }
    if (nodes == NULL || worlds == NULL || indegree == NULL || stack == NULL ||
        (slot_count != 0u && (regrets == NULL || current == NULL || deltas == NULL || sums == NULL)) ||
        (mode_u32 == 1u && (arena == NULL || marginals == NULL))) {
        status = fail("bounded allocation failed");
        goto cleanup;
    }

    for (uint32_t node_index = 0u; node_index < node_count; ++node_index) {
        Node *node = &nodes[node_index];
        node->depth = UINT8_MAX;
        if (!next_field(&parser, input_length, &token)) {
            status = fail("truncated node table");
            goto cleanup;
        }
        if (token_equals(token, "D")) {
            uint32_t player, action_count;
            node->kind = 0u;
            if (!read_u32(&parser, input_length, 1u, &player) ||
                !read_u32(&parser, input_length, MAX_ACTIONS, &action_count) || action_count == 0u) {
                status = fail("invalid decision-node header");
                goto cleanup;
            }
            node->player = (uint8_t)player;
            node->action_count = (uint8_t)action_count;
            if (slot_total > UINT32_MAX) {
                status = fail("policy offset overflow");
                goto cleanup;
            }
            node->slot_base = (uint32_t)slot_total;
            uint64_t node_slots = (uint64_t)hands[player] * (uint64_t)action_count;
            if (!checked_add_u64(slot_total, node_slots, &slot_total) || slot_total > MAX_SLOTS) {
                status = fail("computed information-action slots exceed 1,000,000");
                goto cleanup;
            }
            for (uint32_t action = 0u; action < action_count; ++action) {
                uint32_t child;
                if (!read_u32(&parser, input_length, (uint64_t)node_count - 1u, &child) ||
                    child <= node_index) {
                    status = fail("decision child ids must point forward");
                    goto cleanup;
                }
                node->children[action] = child;
                if (indegree[child] == UINT8_MAX) {
                    status = fail("node indegree overflow");
                    goto cleanup;
                }
                ++indegree[child];
                if (indegree[child] > 1u) {
                    status = fail("public tree child must have exactly one parent");
                    goto cleanup;
                }
            }
        } else if (token_equals(token, "T")) {
            node->kind = 1u;
            if (!read_hex_value(&parser, input_length, &node->constant) ||
                !read_hex_value(&parser, input_length, &node->coefficient) ||
                fabs(node->constant) > 1e12 || fabs(node->coefficient) > 1e12) {
                status = fail("invalid terminal utility; finite magnitudes must be at most 1e12");
                goto cleanup;
            }
        } else {
            status = fail("node row must start with D or T");
            goto cleanup;
        }
        if (!record_newline(&parser, input_length)) {
            status = fail("node row must end at a line boundary");
            goto cleanup;
        }
    }
    if (slot_total != (uint64_t)slot_count) {
        status = fail("header slot count differs from computed player-hand action slots");
        goto cleanup;
    }
    if (!validate_tree(nodes, indegree, stack, node_count)) {
        status = fail("nodes must form one rooted tree of depth at most 32");
        goto cleanup;
    }

    for (uint32_t world_index = 0u; world_index < world_count; ++world_index) {
        uint32_t hand0, hand1;
        World *world = &worlds[world_index];
        if (!read_u32(&parser, input_length, (uint64_t)hand0_count - 1u, &hand0) ||
            !read_u32(&parser, input_length, (uint64_t)hand1_count - 1u, &hand1) ||
            !read_hex_value(&parser, input_length, &world->mass) ||
            !read_hex_value(&parser, input_length, &world->measure) ||
            world->mass <= 0.0 || world->mass > 1.0 ||
            (mode_u32 == 0u && (world->measure < -1.0 || world->measure > 1.0)) ||
            (mode_u32 == 1u && fabs(world->measure) > world->mass)) {
            status = fail("invalid world hand, positive mass, or mode-specific terminal measure");
            goto cleanup;
        }
        world->hand0 = (uint8_t)hand0;
        world->hand1 = (uint8_t)hand1;
        active0[hand0] = 1u;
        active1[hand1] = 1u;
        mass_total += (long double)world->mass;
        if (!record_newline(&parser, input_length)) {
            status = fail("world row must end at a line boundary");
            goto cleanup;
        }
    }
    for (uint32_t hand = 0u; hand < hand0_count; ++hand) {
        if (active0[hand] == 0u) {
            status = fail("world table omits a declared player-0 hand");
            goto cleanup;
        }
    }
    for (uint32_t hand = 0u; hand < hand1_count; ++hand) {
        if (active1[hand] == 0u) {
            status = fail("world table omits a declared player-1 hand");
            goto cleanup;
        }
    }
    if (fabsl(mass_total - 1.0L) > 1e-9L) {
        status = fail("world masses must sum to one within 1e-9");
        goto cleanup;
    }
    if (next_token(&parser, input_length, &token)) {
        status = fail("trailing input after declared worlds");
        goto cleanup;
    }

    int trained = mode_u32 == 0u ?
        train_scalar(nodes, node_count, worlds, world_count, hands, slot_count,
                     iterations, (int)algorithm_u32, regrets, current, deltas, sums) :
        train_public(nodes, node_count, worlds, world_count, hands, slot_count,
                     iterations, (int)algorithm_u32, regrets, current, deltas,
                     sums, arena, marginals);
    if (!trained) {
        status = fail("training produced non-finite strategy or regret values");
        goto cleanup;
    }
    if (!normalize_and_validate(nodes, node_count, hands, sums, current, slot_count,
                                mode_u32 == 1u)) {
        status = fail("average policy is not finite and normalized");
        goto cleanup;
    }
    if (!output_policy(current, slot_count)) {
        status = fail("writing the complete policy output failed");
        goto cleanup;
    }
    status = 0;

cleanup:
    free(marginals);
    free(arena);
    free(sums);
    free(deltas);
    free(current);
    free(regrets);
    free(stack);
    free(indegree);
    free(worlds);
    free(nodes);
    return status;
}
