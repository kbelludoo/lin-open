/*
 * Independent C11 oracle for go-ethereum makeCallVariantGasCallEIP7702.
 *
 * Precharge: 2500 if call target is cold (Berlin cold-warm), plus
 * 100 if ParseDelegation target is warm or 2600 if that target is cold.
 * Then oldCalculator extras + EIP-150 63/64, then add the precharge back.
 * kind 0=CALL (9000 if value + 25000 if value&&new)
 * kind 1=CALLCODE (9000 if value; never new-account)
 * kind 2=DELEGATECALL / 3=STATICCALL (memory only)
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: ethereum/go-ethereum v1.16.9 operations_acl.go + tx_setcode.go
 * License of the algorithm: LGPL-3.0. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    KIND_CALL = 0,
    KIND_CALLCODE = 1,
    KIND_DELEGATE = 2,
    KIND_STATIC = 3,
    WARM = 100,
    COLD = 2600,
    SURCHARGE = 2500,
    VALUE_GAS = 9000,
    NEW_ACCT = 25000,
    DESIGNATOR_LEN = 23
};

static int ok_nonneg(int64_t v) { return v >= 0; }
static int ok_flag(int64_t v) { return v == 0 || v == 1; }
static int ok_kind(int64_t k) { return k >= 0 && k <= 3; }

static int64_t lin_parse_ok(int64_t code_len, int64_t prefix_ok) {
    if (!ok_nonneg(code_len) || !ok_flag(prefix_ok))
        return 0;
    return (code_len == DESIGNATOR_LEN && prefix_ok == 1) ? 1 : 0;
}

static int64_t lin_precharge(int64_t addr_cold, int64_t is_del, int64_t target_cold) {
    int64_t p;
    if (!ok_flag(addr_cold) || !ok_flag(is_del) || !ok_flag(target_cold))
        return 0;
    p = addr_cold ? SURCHARGE : 0;
    if (!is_del)
        return p;
    return p + (target_cold ? COLD : WARM);
}

static int64_t lin_extra(int64_t kind, int64_t transfers, int64_t new_acct, int64_t memory_gas) {
    int64_t g;
    if (!ok_kind(kind) || !ok_flag(transfers) || !ok_flag(new_acct) || !ok_nonneg(memory_gas))
        return 0;
    g = memory_gas;
    if (kind == KIND_DELEGATE || kind == KIND_STATIC)
        return g;
    if (kind == KIND_CALLCODE)
        return transfers ? g + VALUE_GAS : g;
    if (transfers) {
        if ((uint64_t)g + (uint64_t)VALUE_GAS < (uint64_t)g)
            return 0;
        g += VALUE_GAS;
        if (new_acct) {
            if ((uint64_t)g + (uint64_t)NEW_ACCT < (uint64_t)g)
                return 0;
            g += NEW_ACCT;
        }
    }
    return g;
}

static int64_t lin_forward(int64_t available, int64_t base, int64_t requested) {
    int64_t left, cap;
    if (!ok_nonneg(available) || !ok_nonneg(base) || !ok_nonneg(requested))
        return 0;
    if ((uint64_t)available < (uint64_t)base)
        return 0;
    left = available - base;
    cap = left - (left / 64);
    return requested < cap ? requested : cap;
}

static int lin_ok(int64_t kind, int64_t available, int64_t requested, int64_t memory_gas,
                  int64_t transfers, int64_t new_acct, int64_t addr_cold, int64_t is_del,
                  int64_t target_cold) {
    int64_t pre, avail2, ex;
    if (!ok_kind(kind) || !ok_nonneg(available) || !ok_nonneg(requested) || !ok_nonneg(memory_gas))
        return 0;
    if (!ok_flag(transfers) || !ok_flag(new_acct) || !ok_flag(addr_cold) || !ok_flag(is_del) ||
        !ok_flag(target_cold))
        return 0;
    pre = lin_precharge(addr_cold, is_del, target_cold);
    if ((uint64_t)available < (uint64_t)pre)
        return 0;
    avail2 = available - pre;
    ex = lin_extra(kind, transfers, new_acct, memory_gas);
    return (uint64_t)avail2 >= (uint64_t)ex;
}

static int64_t lin_dynamic(int64_t kind, int64_t available, int64_t requested, int64_t memory_gas,
                           int64_t transfers, int64_t new_acct, int64_t addr_cold, int64_t is_del,
                           int64_t target_cold) {
    int64_t pre, avail2, ex, f, s, out;
    if (!lin_ok(kind, available, requested, memory_gas, transfers, new_acct, addr_cold, is_del,
                target_cold))
        return 0;
    pre = lin_precharge(addr_cold, is_del, target_cold);
    avail2 = available - pre;
    ex = lin_extra(kind, transfers, new_acct, memory_gas);
    f = lin_forward(avail2, ex, requested);
    s = ex + f;
    if ((uint64_t)s < (uint64_t)ex)
        return 0;
    out = s + pre;
    if ((uint64_t)out < (uint64_t)s)
        return 0;
    return out;
}

static int64_t lin_total(int64_t kind, int64_t available, int64_t requested, int64_t memory_gas,
                         int64_t transfers, int64_t new_acct, int64_t addr_cold, int64_t is_del,
                         int64_t target_cold) {
    int64_t d, s;
    if (!lin_ok(kind, available, requested, memory_gas, transfers, new_acct, addr_cold, is_del,
                target_cold))
        return 0;
    d = lin_dynamic(kind, available, requested, memory_gas, transfers, new_acct, addr_cold, is_del,
                    target_cold);
    s = WARM + d;
    if ((uint64_t)s < (uint64_t)d)
        return 0;
    return s;
}

static int64_t lin_vs(int64_t kind, int64_t available, int64_t requested, int64_t memory_gas,
                      int64_t transfers, int64_t new_acct, int64_t addr_cold, int64_t is_del,
                      int64_t target_cold) {
    if (!lin_ok(kind, available, requested, memory_gas, transfers, new_acct, addr_cold, 0, 0))
        return 0;
    if (!lin_ok(kind, available, requested, memory_gas, transfers, new_acct, addr_cold, is_del,
                target_cold))
        return 0;
    return lin_dynamic(kind, available, requested, memory_gas, transfers, new_acct, addr_cold, is_del,
                       target_cold) -
           lin_dynamic(kind, available, requested, memory_gas, transfers, new_acct, addr_cold, 0, 0);
}

static int selftest(void) {
    if (lin_parse_ok(23, 1) != 1 || lin_parse_ok(22, 1) != 0)
        return 1;
    if (lin_precharge(0, 1, 1) != 2600 || lin_precharge(1, 1, 1) != 5100)
        return 2;
    if (lin_dynamic(0, 64000, 1000000, 0, 0, 0, 0, 1, 0) != 63002)
        return 3;
    if (lin_dynamic(0, 64000, 1000000, 0, 0, 0, 0, 1, 1) != 63041)
        return 4;
    if (lin_vs(0, 64000, 1000000, 0, 0, 0, 0, 1, 0) != 2)
        return 5;
    if (lin_vs(0, 64000, 1000000, 0, 0, 0, 0, 1, 1) != 41)
        return 6;
    if (lin_dynamic(0, 100000, 1000000, 0, 1, 1, 0, 1, 1) != 99010)
        return 7;
    if (lin_dynamic(0, 64000, 1000, 0, 0, 0, 0, 1, 1) != 3600)
        return 8;
    if (lin_dynamic(0, 2599, 0, 0, 0, 0, 0, 1, 1) != 0)
        return 9;
    if (lin_dynamic(1, 64000, 1000000, 0, 1, 0, 0, 1, 1) != 63182)
        return 10;
    return 0;
}

static int64_t arg(char **argv, int i) { return strtoll(argv[i], NULL, 10); }

int main(int argc, char **argv) {
    int rc;
    if (argc < 2) {
        fprintf(stderr, "usage: geth_eip7702_c11 selftest|parse len pre|pre a d t|"
                        "dynamic k a r m x n c d t|total ...|vs ...\n");
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
    if (strcmp(argv[1], "parse") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", lin_parse_ok(arg(argv, 2), arg(argv, 3)));
        return 0;
    }
    if (strcmp(argv[1], "pre") == 0 && argc >= 5) {
        printf("%" PRId64 "\n", lin_precharge(arg(argv, 2), arg(argv, 3), arg(argv, 4)));
        return 0;
    }
    if (argc < 11) {
        fprintf(stderr, "need kind + 8 ints\n");
        return 2;
    }
    if (strcmp(argv[1], "dynamic") == 0) {
        printf("%" PRId64 "\n",
               lin_dynamic(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5), arg(argv, 6),
                           arg(argv, 7), arg(argv, 8), arg(argv, 9), arg(argv, 10)));
        return 0;
    }
    if (strcmp(argv[1], "total") == 0) {
        printf("%" PRId64 "\n",
               lin_total(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5), arg(argv, 6),
                         arg(argv, 7), arg(argv, 8), arg(argv, 9), arg(argv, 10)));
        return 0;
    }
    if (strcmp(argv[1], "vs") == 0) {
        printf("%" PRId64 "\n",
               lin_vs(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5), arg(argv, 6),
                      arg(argv, 7), arg(argv, 8), arg(argv, 9), arg(argv, 10)));
        return 0;
    }
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
