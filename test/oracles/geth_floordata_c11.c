/*
 * Independent C11 oracle for go-ethereum FloorDataGas (EIP-7623), uint64 / i64.
 *
 * Two implementations:
 *   1. Geth uint64 wrap: tokens = nz*4 + z (C unsigned wrap) then
 *      (UINT64_MAX-21000)/10 < tokens ? 0 : 21000 + tokens*10
 *   2. LIN fail-closed i64: overflow of nz*4, tokens*10, or +21000 returns 0
 *      at INT64_MAX (Geth MaxGasLimit).
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: ethereum/go-ethereum v1.16.9 core/state_transition.go FloorDataGas
 * License of the algorithm: LGPL-3.0. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TX_GAS 21000ULL
#define TOKEN_NZ 4ULL
#define TOKEN_Z 1ULL
#define COST 10ULL
#define NZ_ISTANBUL 16ULL
#define Z_INTRINSIC 4ULL

static uint64_t geth_uint64_floor(uint64_t z, uint64_t nz) {
    uint64_t tokens = nz * TOKEN_NZ + z; /* Geth: no mul overflow check */
    if ((UINT64_MAX - TX_GAS) / COST < tokens)
        return 0;
    return TX_GAS + tokens * COST;
}

static int lin_mul_ok(int64_t count, int64_t cost) {
    if (count < 0 || cost < 0)
        return 0;
    if (cost == 0)
        return 1;
    return count <= (INT64_MAX / cost);
}

static int lin_add_ok(int64_t a, int64_t b) {
    if (a < 0 || b < 0)
        return 0;
    return a <= (INT64_MAX - b);
}

static int64_t lin_charge(int64_t gas, int64_t count, int64_t cost) {
    int64_t add;
    if (!lin_mul_ok(count, cost))
        return 0;
    add = count * cost;
    if (!lin_add_ok(gas, add))
        return 0;
    return gas + add;
}

static int64_t lin_tokens(int64_t z, int64_t nz) {
    int64_t t;
    if (z < 0 || nz < 0)
        return 0;
    t = lin_charge(0, nz, (int64_t)TOKEN_NZ);
    if (nz > 0 && t == 0)
        return 0;
    t = lin_charge(t, z, (int64_t)TOKEN_Z);
    if (z > 0 && t == 0)
        return 0;
    return t;
}

static int64_t lin_floor(int64_t z, int64_t nz) {
    int64_t tokens;
    if (z < 0 || nz < 0)
        return 0;
    tokens = lin_tokens(z, nz);
    if (tokens == 0) {
        if (z == 0 && nz == 0)
            return (int64_t)TX_GAS;
        return 0;
    }
    return lin_charge((int64_t)TX_GAS, tokens, (int64_t)COST);
}

static int64_t lin_istanbul_intrinsic(int64_t z, int64_t nz) {
    int64_t gas;
    if (z < 0 || nz < 0)
        return 0;
    gas = (int64_t)TX_GAS;
    gas = lin_charge(gas, nz, (int64_t)NZ_ISTANBUL);
    if (nz > 0 && gas == 0)
        return 0;
    gas = lin_charge(gas, z, (int64_t)Z_INTRINSIC);
    if (z > 0 && gas == 0)
        return 0;
    return gas;
}

static int64_t lin_prague(int64_t z, int64_t nz) {
    int64_t floor = lin_floor(z, nz);
    int64_t inn = lin_istanbul_intrinsic(z, nz);
    if (floor == 0 || inn == 0)
        return 0;
    return floor > inn ? floor : inn;
}

static int selftest(void) {
    if (lin_floor(0, 0) != 21000)
        return 1;
    if (lin_floor(1, 0) != 21010)
        return 2;
    if (lin_floor(0, 1) != 21040)
        return 3;
    if (lin_floor(1, 1) != 21050)
        return 4;
    if (lin_floor(100, 0) != 22000)
        return 5;
    if (lin_floor(0, 100) != 25000)
        return 6;
    if (lin_floor(500, 1000) != 66000)
        return 7;
    if (lin_istanbul_intrinsic(0, 1) != 21016)
        return 8;
    if (lin_prague(0, 1) != 21040)
        return 9;
    if (geth_uint64_floor(0, 0) != 21000)
        return 10;
    if (geth_uint64_floor(0, 1) != 21040)
        return 11;
    /* nz = 2^62: uint64 nz*4 wraps to 0; i64 fail-closed stays 0 */
    if (geth_uint64_floor(0, 4611686018427387904ULL) != 21000)
        return 12;
    if (lin_floor(0, (int64_t)4611686018427387904LL) != 0)
        return 13;
    return 0;
}

int main(int argc, char **argv) {
    int64_t z, nz;
    if (argc < 2) {
        fprintf(stderr, "usage: geth_floordata_c11 selftest|floor z nz|tokens z nz|intrinsic z nz|prague z nz|geth z nz\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        int rc = selftest();
        if (rc == 0) {
            puts("PASS");
            return 0;
        }
        printf("FAIL %d\n", rc);
        return 1;
    }
    if (argc < 4) {
        fprintf(stderr, "need z nz\n");
        return 2;
    }
    z = (int64_t)strtoll(argv[2], NULL, 10);
    nz = (int64_t)strtoll(argv[3], NULL, 10);
    if (strcmp(argv[1], "floor") == 0)
        printf("%" PRId64 "\n", lin_floor(z, nz));
    else if (strcmp(argv[1], "tokens") == 0)
        printf("%" PRId64 "\n", lin_tokens(z, nz));
    else if (strcmp(argv[1], "intrinsic") == 0)
        printf("%" PRId64 "\n", lin_istanbul_intrinsic(z, nz));
    else if (strcmp(argv[1], "prague") == 0)
        printf("%" PRId64 "\n", lin_prague(z, nz));
    else if (strcmp(argv[1], "geth") == 0)
        printf("%" PRIu64 "\n", geth_uint64_floor((uint64_t)z, (uint64_t)nz));
    else {
        fprintf(stderr, "unknown op %s\n", argv[1]);
        return 2;
    }
    return 0;
}
