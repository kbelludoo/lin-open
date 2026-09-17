/*
 * Independent C11 oracle for go-ethereum callGas (EIP-150 63/64).
 *
 * Two implementations:
 *   1. Geth uint64: available-base wraps; stipend = remaining - remaining/64;
 *      *uint256.Int is (cost, cost_hi). Pre-EIP-150 overflow is OVERFLOW.
 *   2. LIN fail-closed i64: negatives, available<base, and pre-EIP-150
 *      cost_hi return 0. Same 63/64 form (not remaining*63/64).
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: ethereum/go-ethereum v1.16.9 core/vm/gas.go callGas
 * License of the algorithm: LGPL-3.0. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int geth_callgas(int eip150, uint64_t available, uint64_t base,
                        uint64_t cost, uint64_t cost_hi, uint64_t *out) {
    uint64_t gas;
    if (eip150) {
        available = available - base; /* Geth: uint64 wrap */
        gas = available - available / 64ULL;
        if (cost_hi != 0 || gas < cost) {
            *out = gas;
            return 0;
        }
    }
    if (cost_hi != 0)
        return 1;
    *out = cost;
    return 0;
}

static int64_t lin_stipend(int64_t available) {
    if (available < 0)
        return 0;
    return available - (available / 64);
}

static int64_t lin_callgas(int64_t eip150, int64_t available, int64_t base,
                           int64_t cost, int64_t cost_hi) {
    int64_t rem, gas;
    if (eip150 < 0 || available < 0 || base < 0 || cost < 0 || cost_hi < 0)
        return 0;
    if (eip150 != 0) {
        if ((uint64_t)available < (uint64_t)base)
            return 0;
        rem = available - base;
        gas = lin_stipend(rem);
        if (cost_hi != 0)
            return gas;
        if ((uint64_t)gas < (uint64_t)cost)
            return gas;
        return cost;
    }
    if (cost_hi != 0)
        return 0;
    return cost;
}

static int selftest(void) {
    uint64_t g;
    if (lin_stipend(64000) != 63000)
        return 1;
    if (lin_callgas(1, 64000, 0, 64000, 0) != 63000)
        return 2;
    if (lin_callgas(1, 64000, 700, 1000, 0) != 1000)
        return 3;
    if (lin_callgas(1, 64, 0, 100, 0) != 63)
        return 4;
    if (lin_callgas(1, 65, 0, 65, 0) != 64)
        return 5;
    if (lin_callgas(0, 1000, 0, 1000, 0) != 1000)
        return 6;
    if (lin_callgas(0, 1000, 0, 1000, 1) != 0)
        return 7;
    if (lin_callgas(1, 1000, 0, 0, 1) != 985)
        return 8;
    if (lin_callgas(1, 10, 20, 5, 0) != 0)
        return 9;
    if (lin_callgas(1, 21000, 0, 21000, 0) != 20672)
        return 10;
    if (geth_callgas(1, 64000, 0, 64000, 0, &g) != 0 || g != 63000)
        return 11;
    if (geth_callgas(1, 10, 20, 5, 0, &g) != 0 || g != 5)
        return 12;
    if (geth_callgas(0, 1000, 0, 1000, 1, &g) != 1)
        return 13;
    if (geth_callgas(1, 10, 20, 0, 1, &g) != 0 || g != (10ULL - 20ULL) - ((10ULL - 20ULL) / 64ULL))
        return 14;
    if (lin_callgas(1, 2300, 0, 2300, 0) != 2265)
        return 15;
    return 0;
}

int main(int argc, char **argv) {
    uint64_t g;
    int rc;
    if (argc < 2) {
        fprintf(stderr,
                "usage: geth_callgas_c11 selftest|call eip av base cost hi|geth-call eip av base cost hi|stipend av\n");
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
    if (strcmp(argv[1], "stipend") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_stipend(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "call") == 0 && argc >= 7) {
        printf("%" PRId64 "\n",
               lin_callgas(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                           strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                           strtoll(argv[6], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "geth-call") == 0 && argc >= 7) {
        rc = geth_callgas((int)strtol(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                          strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                          strtoull(argv[6], NULL, 10), &g);
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
