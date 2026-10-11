/*
 * Independent C11 oracle for go-ethereum gasExpEIP158 / ExpByteEIP158=50.
 *
 * Two implementations:
 *   1. Geth uint64: gas = ExpGas + expByteLen * ExpByteEIP158 (10 + n*50).
 *      SafeAdd overflow is OVERFLOW. Mul is unchecked (Geth comment).
 *   2. LIN fail-closed i64: bitLen outside 0..2048, expByteLen outside
 *      0..256, and negatives return 0.
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

enum { EXP_GAS = 10, EXP_BYTE = 50, MAX_BYTELEN = 256, MAX_BITLEN = 2048 };

static int geth_exp(uint64_t n, uint64_t *out) {
    uint64_t prod = n * (uint64_t)EXP_BYTE;
    if ((uint64_t)EXP_GAS > UINT64_MAX - prod)
        return 1;
    *out = (uint64_t)EXP_GAS + prod;
    return 0;
}

static int64_t lin_byte_len(int64_t bitLen) {
    if (bitLen < 0 || bitLen > MAX_BITLEN)
        return 0;
    return (bitLen + 7) / 8;
}

static int64_t lin_exp(int64_t n) {
    int64_t prod, s;
    if (n < 0 || n > MAX_BYTELEN)
        return 0;
    prod = n * (int64_t)EXP_BYTE;
    s = (int64_t)EXP_GAS + prod;
    if ((uint64_t)s < (uint64_t)prod)
        return 0;
    return s;
}

static int64_t lin_from_bitlen(int64_t bitLen) {
    int64_t n;
    if (bitLen < 0 || bitLen > MAX_BITLEN)
        return 0;
    n = lin_byte_len(bitLen);
    if (bitLen > 0 && n == 0)
        return 0;
    return lin_exp(n);
}

static int selftest(void) {
    uint64_t g;
    if (lin_exp(0) != 10)
        return 1;
    if (lin_exp(1) != 60)
        return 2;
    if (lin_exp(32) != 1610)
        return 3;
    if (lin_exp(256) != 12810)
        return 4;
    if (lin_from_bitlen(0) != 10)
        return 5;
    if (lin_from_bitlen(9) != 110)
        return 6;
    if (lin_from_bitlen(256) != 1610)
        return 7;
    if (lin_from_bitlen(-1) != 0)
        return 8;
    if (lin_exp(257) != 0)
        return 9;
    if (geth_exp(32, &g) != 0 || g != 1610)
        return 10;
    if (geth_exp(0, &g) != 0 || g != 10)
        return 11;
    if (lin_byte_len(2048) != 256)
        return 12;
    return 0;
}

int main(int argc, char **argv) {
    uint64_t g;
    int rc;
    if (argc < 2) {
        fprintf(stderr,
                "usage: geth_gasexp_c11 selftest|exp n|from-bitlen bitLen|"
                "byte-len bitLen|geth-exp n\n");
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
    if (strcmp(argv[1], "exp") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_exp(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "from-bitlen") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_from_bitlen(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "byte-len") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_byte_len(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "geth-exp") == 0 && argc >= 3) {
        rc = geth_exp(strtoull(argv[2], NULL, 10), &g);
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
