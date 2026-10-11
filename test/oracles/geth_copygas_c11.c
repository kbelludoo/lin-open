/*
 * Independent C11 oracle for go-ethereum memoryCopierGas / gasKeccak256.
 *
 * Two implementations:
 *   1. Geth uint64: word gas = per_word * ((size+31)/32). CopyGas=3,
 *      Keccak256WordGas=6. Add overflow is OVERFLOW.
 *   2. LIN fail-closed i64: negatives and add wrap return 0.
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

enum { COPY_GAS = 3, KECCAK_WORD = 6 };

static int geth_more(int keccak, uint64_t size, uint64_t memgas, uint64_t *out) {
    uint64_t words, more, sum;
    words = (size + 31ULL) / 32ULL;
    more = (uint64_t)(keccak ? KECCAK_WORD : COPY_GAS) * words;
    if (memgas > UINT64_MAX - more)
        return 1;
    sum = memgas + more;
    *out = sum;
    return 0;
}

static int64_t lin_ok(int64_t size) {
    if (size < 0)
        return 0;
    return 1;
}

static int64_t lin_words(int64_t size) {
    if (!lin_ok(size))
        return 0;
    return (size + 31) / 32;
}

static int64_t lin_copy(int64_t size) {
    if (!lin_ok(size))
        return 0;
    return (int64_t)COPY_GAS * lin_words(size);
}

static int64_t lin_keccak(int64_t size) {
    if (!lin_ok(size))
        return 0;
    return (int64_t)KECCAK_WORD * lin_words(size);
}

static int64_t lin_with_mem(int64_t kind, int64_t memgas, int64_t size) {
    int64_t more, s;
    if (kind < 0 || memgas < 0 || !lin_ok(size))
        return 0;
    more = kind != 0 ? lin_keccak(size) : lin_copy(size);
    s = memgas + more;
    if ((uint64_t)s < (uint64_t)memgas)
        return 0;
    return s;
}

static int selftest(void) {
    uint64_t g;
    if (lin_copy(0) != 0)
        return 1;
    if (lin_copy(1) != 3)
        return 2;
    if (lin_copy(32) != 3)
        return 3;
    if (lin_copy(33) != 6)
        return 4;
    if (lin_copy(1024) != 96)
        return 5;
    if (lin_copy(-1) != 0)
        return 6;
    if (lin_keccak(1) != 6)
        return 7;
    if (lin_keccak(33) != 12)
        return 8;
    if (lin_keccak(49152) != 9216)
        return 9;
    if (lin_with_mem(0, 100, 32) != 103)
        return 10;
    if (lin_with_mem(1, 100, 32) != 106)
        return 11;
    if (geth_more(0, 32, 0, &g) != 0 || g != 3)
        return 12;
    if (geth_more(1, 32, 0, &g) != 0 || g != 6)
        return 13;
    if (lin_copy(24576) != 2304)
        return 14;
    if (lin_copy(49152) != 4608)
        return 15;
    return 0;
}

int main(int argc, char **argv) {
    uint64_t g;
    int rc;
    if (argc < 2) {
        fprintf(stderr,
                "usage: geth_copygas_c11 selftest|copy size|keccak size|"
                "with kind mem size|geth-copy size|geth-keccak size|"
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
    if (strcmp(argv[1], "copy") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_copy(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "keccak") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_keccak(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "with") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               lin_with_mem(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                            strtoll(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "geth-copy") == 0 && argc >= 3) {
        rc = geth_more(0, strtoull(argv[2], NULL, 10), 0, &g);
        if (rc != 0) {
            puts("OVERFLOW");
            return 0;
        }
        printf("%" PRIu64 "\n", g);
        return 0;
    }
    if (strcmp(argv[1], "geth-keccak") == 0 && argc >= 3) {
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
