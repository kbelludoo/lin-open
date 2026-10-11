/*
 * Independent C11 oracle for go-ethereum makeSelfdestructGasFn / EIP-3529.
 *
 * Geth dynamic gas: cold 2600 + CreateBySelfdestruct 25000 when empty&&value.
 * EIP-3529: refundsEnabled=false so intended AddRefund is 0.
 * EIP-2929: first SELFDESTRUCT refunds 24000 (not added to gas).
 * gasEip2929AccountCheck: cold-warm = 2500.
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
    COLD = 2600,
    CREATE = 25000,
    REFUND = 24000,
    WARM = 100,
    STATIC_GAS = 5000
};

static int ok_flag(int64_t v) { return v == 0 || v == 1; }

static int64_t lin_account_check(int64_t is_cold) {
    if (!ok_flag(is_cold))
        return 0;
    return is_cold ? (COLD - WARM) : 0;
}

static int64_t lin_gas(int64_t is_cold, int64_t target_empty, int64_t has_value) {
    int64_t gas = 0;
    if (!ok_flag(is_cold) || !ok_flag(target_empty) || !ok_flag(has_value))
        return 0;
    if (is_cold)
        gas += COLD;
    if (target_empty && has_value)
        gas += CREATE;
    return gas;
}

static int64_t lin_refund(int64_t refunds_enabled, int64_t already) {
    if (!ok_flag(refunds_enabled) || !ok_flag(already))
        return 0;
    if (!refunds_enabled || already)
        return 0;
    return REFUND;
}

static int64_t lin_total(int64_t is_cold, int64_t target_empty, int64_t has_value) {
    if (!ok_flag(is_cold) || !ok_flag(target_empty) || !ok_flag(has_value))
        return 0;
    return STATIC_GAS + lin_gas(is_cold, target_empty, has_value);
}

static int selftest(void) {
    if (lin_account_check(1) != 2500)
        return 1;
    if (lin_account_check(0) != 0)
        return 2;
    if (lin_gas(0, 0, 0) != 0)
        return 3;
    if (lin_gas(1, 0, 0) != 2600)
        return 4;
    if (lin_gas(0, 1, 1) != 25000)
        return 5;
    if (lin_gas(1, 1, 1) != 27600)
        return 6;
    if (lin_gas(0, 1, 0) != 0)
        return 7;
    if (lin_refund(0, 0) != 0)
        return 8;
    if (lin_refund(1, 0) != 24000)
        return 9;
    if (lin_refund(1, 1) != 0)
        return 10;
    if (lin_total(0, 0, 0) != 5000)
        return 11;
    if (lin_total(1, 1, 1) != 32600)
        return 12;
    if (lin_gas(-1, 0, 0) != 0)
        return 13;
    return 0;
}

int main(int argc, char **argv) {
    int rc;
    if (argc < 2) {
        fprintf(stderr,
                "usage: geth_selfdestruct_c11 selftest|gas c e v|"
                "refund en dest|check c|total c e v|create-cold|delta\n");
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
    if (strcmp(argv[1], "create-cold") == 0) {
        printf("%" PRId64 "\n", lin_gas(1, 1, 1));
        return 0;
    }
    if (strcmp(argv[1], "delta") == 0) {
        printf("%" PRId64 "\n", lin_refund(1, 0) - lin_refund(0, 0));
        return 0;
    }
    if (strcmp(argv[1], "check") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_account_check(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "gas") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               lin_gas(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                       strtoll(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "refund") == 0 && argc >= 4) {
        printf("%" PRId64 "\n",
               lin_refund(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "total") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               lin_total(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                         strtoll(argv[4], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
