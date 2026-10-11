/*
 * Independent C11 oracle for go-ethereum makeGasSStoreFunc / EIP-3529.
 *
 * Two implementations:
 *   1. Geth uint64 gas + signed refund delta (AddRefund/SubRefund intent).
 *   2. LIN fail-closed i64: slot tokens outside 0..3, is_warm outside 0..1,
 *      unknown refund schedule, and sentry (gas_left<=2300) return 0.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: ethereum/go-ethereum v1.16.9 core/vm/operations_acl.go
 * License of the algorithm: LGPL-3.0. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    SENTRY = 2300,
    SET_GAS = 20000,
    RESET_GAS = 5000,
    COLD = 2100,
    WARM = 100,
    ACCESS_KEY = 1900,
    CLEAR_2200 = 15000
};

static int64_t clear_3529(void) { return (int64_t)RESET_GAS - COLD + ACCESS_KEY; }

static int64_t lin_sload(int64_t is_warm) {
    if (is_warm == 1)
        return WARM;
    if (is_warm == 0)
        return COLD;
    return 0;
}

static int64_t lin_gas(int64_t orig, int64_t curr, int64_t val, int64_t is_warm, int64_t gas_left) {
    int64_t cost;
    if (orig < 0 || orig > 3 || curr < 0 || curr > 3 || val < 0 || val > 3)
        return 0;
    if (is_warm != 0 && is_warm != 1)
        return 0;
    if (gas_left <= SENTRY)
        return 0;
    cost = (is_warm == 0) ? COLD : 0;
    if (curr == val)
        return cost + WARM;
    if (orig == curr) {
        if (orig == 0)
            return cost + SET_GAS;
        return cost + (RESET_GAS - COLD);
    }
    return cost + WARM;
}

static int64_t lin_refund(int64_t orig, int64_t curr, int64_t val, int64_t gas_left, int64_t sched) {
    int64_t r = 0;
    if (orig < 0 || orig > 3 || curr < 0 || curr > 3 || val < 0 || val > 3)
        return 0;
    if (sched != CLEAR_2200 && sched != clear_3529())
        return 0;
    if (gas_left <= SENTRY)
        return 0;
    if (curr == val)
        return 0;
    if (orig == curr) {
        if (orig == 0)
            return 0;
        return (val == 0) ? sched : 0;
    }
    if (orig != 0) {
        if (curr == 0)
            r -= sched;
        else if (val == 0)
            r += sched;
    }
    if (orig == val) {
        if (orig == 0)
            r += (SET_GAS - WARM);
        else
            r += ((RESET_GAS - COLD) - WARM);
    }
    return r;
}

static int selftest(void) {
    if (clear_3529() != 4800)
        return 1;
    if (lin_gas(0, 0, 1, 1, 100000) != 20000)
        return 2;
    if (lin_gas(1, 1, 0, 1, 100000) != 2900)
        return 3;
    if (lin_gas(0, 0, 1, 0, 100000) != 22100)
        return 4;
    if (lin_gas(1, 1, 0, 0, 100000) != 5000)
        return 5;
    if (lin_gas(0, 0, 1, 1, 2300) != 0)
        return 6;
    if (lin_refund(1, 1, 0, 100000, 4800) != 4800)
        return 7;
    if (lin_refund(1, 0, 1, 100000, 4800) != -2000)
        return 8;
    if (lin_refund(0, 1, 0, 100000, 4800) != 19900)
        return 9;
    if (lin_refund(1, 2, 1, 100000, 4800) != 2800)
        return 10;
    if (lin_sload(1) != 100 || lin_sload(0) != 2100)
        return 11;
    if (lin_gas(-1, 0, 1, 1, 100000) != 0)
        return 12;
    return 0;
}

int main(int argc, char **argv) {
    int rc;
    if (argc < 2) {
        fprintf(stderr,
                "usage: geth_sstore_c11 selftest|gas o c v w gl|"
                "refund o c v gl sched|sload w|clear-3529\n");
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
    if (strcmp(argv[1], "clear-3529") == 0) {
        printf("%" PRId64 "\n", clear_3529());
        return 0;
    }
    if (strcmp(argv[1], "sload") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_sload(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "gas") == 0 && argc >= 7) {
        printf("%" PRId64 "\n",
               lin_gas(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                       strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                       strtoll(argv[6], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "refund") == 0 && argc >= 7) {
        printf("%" PRId64 "\n",
               lin_refund(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                          strtoll(argv[4], NULL, 10), strtoll(argv[5], NULL, 10),
                          strtoll(argv[6], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
