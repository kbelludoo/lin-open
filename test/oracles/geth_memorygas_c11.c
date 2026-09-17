/*
 * Independent C11 oracle for go-ethereum memoryGasCost (Yellow Paper Cmem).
 *
 * Two implementations:
 *   1. Geth uint64: words=(size+31)/32, total=3*words+words^2/512 using
 *      unsigned wrap on last>total; size>0x1FFFFFFFE0 is OVERFLOW.
 *   2. LIN fail-closed i64: negatives, size>cap, last>total return 0.
 *      words*words uses unsigned __int128 so the official cap is in range.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: ethereum/go-ethereum v1.16.9 core/vm/gas_table.go memoryGasCost
 * License of the algorithm: LGPL-3.0. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MEMORY_GAS 3ULL
#define QUAD_DIV 512ULL
#define MEM_CAP 0x1FFFFFFFE0ULL

static uint64_t geth_to_word(uint64_t size) {
    if (size > UINT64_MAX - 31ULL)
        return UINT64_MAX / 32ULL + 1ULL;
    return (size + 31ULL) / 32ULL;
}

static int geth_total(uint64_t words, uint64_t *out) {
    __uint128_t sq = (__uint128_t)words * (__uint128_t)words;
    __uint128_t tot = (__uint128_t)words * MEMORY_GAS + sq / QUAD_DIV;
    if (tot > UINT64_MAX)
        return -1;
    *out = (uint64_t)tot;
    return 0;
}

static int geth_fee(uint64_t new_size, uint64_t cur_len, uint64_t last, uint64_t *out) {
    uint64_t words, rounded, tot;
    if (new_size == 0) {
        *out = 0;
        return 0;
    }
    if (new_size > MEM_CAP)
        return 1;
    words = geth_to_word(new_size);
    rounded = words * 32ULL;
    if (rounded <= cur_len) {
        *out = 0;
        return 0;
    }
    if (geth_total(words, &tot) != 0)
        return 1;
    *out = tot - last; /* Geth: uint64 wrap if last > tot */
    return 0;
}

static int64_t lin_to_word(int64_t size) {
    if (size < 0)
        return 0;
    if (size > INT64_MAX - 31)
        return 0;
    return (size + 31) / 32;
}

static int64_t lin_total(int64_t words) {
    __uint128_t sq, tot;
    if (words < 0)
        return 0;
    sq = (__uint128_t)(uint64_t)words * (__uint128_t)(uint64_t)words;
    tot = (__uint128_t)(uint64_t)words * MEMORY_GAS + sq / QUAD_DIV;
    if (tot > (uint64_t)INT64_MAX)
        return 0;
    return (int64_t)tot;
}

static int64_t lin_fee(int64_t new_size, int64_t cur_len, int64_t last) {
    int64_t words, rounded, tot;
    if (new_size < 0 || cur_len < 0 || last < 0)
        return 0;
    if (new_size == 0)
        return 0;
    if ((uint64_t)new_size > MEM_CAP)
        return 0;
    words = lin_to_word(new_size);
    rounded = words * 32;
    if (rounded <= cur_len)
        return 0;
    tot = lin_total(words);
    if (last > tot)
        return 0;
    return tot - last;
}

static int selftest(void) {
    uint64_t g;
    if (lin_fee(0, 0, 0) != 0)
        return 1;
    if (lin_fee(32, 0, 0) != 3)
        return 2;
    if (lin_fee(1024, 0, 0) != 98)
        return 3;
    if (lin_fee(33, 32, 3) != 3)
        return 4;
    if (lin_fee(32, 32, 3) != 0)
        return 5;
    if (lin_fee(2048, 1024, 98) != 102)
        return 6;
    if (lin_fee(64, 0, 999) != 0)
        return 7;
    if (lin_fee((int64_t)MEM_CAP + 1, 0, 0) != 0)
        return 8;
    if (geth_fee(32, 0, 0, &g) != 0 || g != 3)
        return 9;
    if (geth_fee(1024, 0, 0, &g) != 0 || g != 98)
        return 10;
    if (geth_fee(64, 0, 999, &g) != 0 || g != (uint64_t)(6ULL - 999ULL))
        return 11;
    if (geth_fee(MEM_CAP + 1ULL, 0, 0, &g) != 1)
        return 12;
    if (lin_to_word(33) != 2)
        return 13;
    if (lin_fee(4096, 0, 0) != 416)
        return 14;
    return 0;
}

int main(int argc, char **argv) {
    uint64_t g;
    int rc;
    if (argc < 2) {
        fprintf(stderr, "usage: geth_memorygas_c11 selftest|fee s l last|geth-fee s l last|words s|total words\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        rc = selftest();
        if (rc == 0) {
            puts("PASS");
            return 0;
        }
        printf("FAIL %d\n", rc);
        return 1;
    }
    if (strcmp(argv[1], "fee") == 0 && argc >= 5) {
        printf("%" PRId64 "\n", lin_fee(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10), strtoll(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "geth-fee") == 0 && argc >= 5) {
        rc = geth_fee(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), strtoull(argv[4], NULL, 10), &g);
        if (rc != 0) {
            puts("OVERFLOW");
            return 0;
        }
        printf("%" PRIu64 "\n", g);
        return 0;
    }
    if (strcmp(argv[1], "words") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_to_word(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "total") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_total(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
