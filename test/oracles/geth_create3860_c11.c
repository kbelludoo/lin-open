/*
 * Independent C11 oracle for go-ethereum gasCreateEip3860 / gasCreate2Eip3860.
 *
 * Two implementations:
 *   1. Geth uint64: size>MaxInitCodeSize or add overflow is OVERFLOW;
 *      surcharge = word_gas * ((size+31)/32). CREATE2 adds Keccak256WordGas.
 *   2. LIN fail-closed i64: negatives, oversize, and add wrap return 0.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: ethereum/go-ethereum v1.16.9 core/vm/gas_table.go
 * License of the algorithm: LGPL-3.0. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { MAX_INIT = 49152, WORD_GAS = 2, KECCAK_WORD = 6 };

static int geth_more(int create2, uint64_t size, uint64_t memgas, uint64_t *out) {
    uint64_t words, more, sum;
    if (size > (uint64_t)MAX_INIT)
        return 1;
    words = (size + 31ULL) / 32ULL;
    more = (uint64_t)(create2 ? (WORD_GAS + KECCAK_WORD) : WORD_GAS) * words;
    if (memgas > UINT64_MAX - more)
        return 1;
    sum = memgas + more;
    *out = sum;
    return 0;
}

static int64_t lin_ok(int64_t size) {
    if (size < 0 || size > MAX_INIT)
        return 0;
    return 1;
}

static int64_t lin_words(int64_t size) {
    if (!lin_ok(size))
        return 0;
    return (size + 31) / 32;
}

static int64_t lin_create(int64_t size) {
    if (!lin_ok(size))
        return 0;
    return (int64_t)WORD_GAS * lin_words(size);
}

static int64_t lin_create2(int64_t size) {
    if (!lin_ok(size))
        return 0;
    return (int64_t)(WORD_GAS + KECCAK_WORD) * lin_words(size);
}

static int64_t lin_with_mem(int64_t kind, int64_t memgas, int64_t size) {
    int64_t more, s;
    if (kind < 0 || memgas < 0 || !lin_ok(size))
        return 0;
    more = kind != 0 ? lin_create2(size) : lin_create(size);
    s = memgas + more;
    if ((uint64_t)s < (uint64_t)memgas)
        return 0;
    return s;
}

static int selftest(void) {
    uint64_t g;
    if (lin_create(0) != 0)
        return 1;
    if (lin_create(1) != 2)
        return 2;
    if (lin_create(32) != 2)
        return 3;
    if (lin_create(33) != 4)
        return 4;
    if (lin_create(49152) != 3072)
        return 5;
    if (lin_create(49153) != 0)
        return 6;
    if (lin_create2(1) != 8)
        return 7;
    if (lin_create2(49152) != 12288)
        return 8;
    if (lin_with_mem(0, 100, 32) != 102)
        return 9;
    if (geth_more(0, 32, 0, &g) != 0 || g != 2)
        return 10;
    if (geth_more(1, 32, 0, &g) != 0 || g != 8)
        return 11;
    if (geth_more(0, 49153, 100, &g) != 1)
        return 12;
    if (lin_with_mem(0, 100, 49153) != 0)
        return 13;
    if (lin_create(24576) != 1536)
        return 14;
    return 0;
}

int main(int argc, char **argv) {
    uint64_t g;
    int rc;
    if (argc < 2) {
        fprintf(stderr,
                "usage: geth_create3860_c11 selftest|create size|create2 size|"
                "with kind mem size|geth-create size|geth-create2 size|"
                "geth-with kind mem size\n");
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
    if (strcmp(argv[1], "create") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_create(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "create2") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_create2(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "with") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               lin_with_mem(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                            strtoll(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "geth-create") == 0 && argc >= 3) {
        rc = geth_more(0, strtoull(argv[2], NULL, 10), 0, &g);
        if (rc != 0) {
            puts("OVERFLOW");
            return 0;
        }
        printf("%" PRIu64 "\n", g);
        return 0;
    }
    if (strcmp(argv[1], "geth-create2") == 0 && argc >= 3) {
        rc = geth_more(1, strtoull(argv[2], NULL, 10), 0, &g);
        if (rc != 0) {
            puts("OVERFLOW");
            return 0;
        }
        printf("%" PRIu64 "\n", g);
        return 0;
    }
    if (strcmp(argv[1], "geth-with") == 0 && argc >= 5) {
        rc = geth_more((int)strtol(argv[2], NULL, 10), strtoull(argv[4], NULL, 10),
                       strtoull(argv[3], NULL, 10), &g);
        if (rc != 0) {
            puts("OVERFLOW");
            return 0;
        }
        printf("%" PRIu64 "\n", g);
        return 0;
    }
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
