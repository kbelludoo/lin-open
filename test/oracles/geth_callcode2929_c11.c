/*
 * Independent C11 oracle for go-ethereum gasCallCodeEIP2929 /
 * gasDelegateCallEIP2929 / gasStaticCallEIP2929 vs CALL extras.
 *
 * Shared Berlin wrapper: cold-warm 2500 before EIP-150 63/64, then add-back.
 * kind 0=CALL (9000 if value + 25000 if value&&new)
 * kind 1=CALLCODE (9000 if value; never new-account)
 * kind 2=DELEGATECALL / 3=STATICCALL (memory only)
 * Cmem quadratic and CallStipend 2300 are omitted.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: ethereum/go-ethereum v1.16.9 operations_acl.go + gas_table.go
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
    NEW_ACCT = 25000
};

static int ok_nonneg(int64_t v) { return v >= 0; }
static int ok_flag(int64_t v) { return v == 0 || v == 1; }
static int ok_kind(int64_t k) { return k >= 0 && k <= 3; }

static int64_t lin_surcharge(int64_t is_cold) {
    if (!ok_flag(is_cold))
        return 0;
    return is_cold ? SURCHARGE : 0;
}

static int64_t lin_extra(int64_t kind, int64_t transfers, int64_t new_acct, int64_t memory_gas) {
    int64_t g;
    if (!ok_kind(kind) || !ok_flag(transfers) || !ok_flag(new_acct) || !ok_nonneg(memory_gas))
        return 0;
    g = memory_gas;
    if (kind == KIND_DELEGATE || kind == KIND_STATIC)
        return g;
    if (kind == KIND_CALLCODE) {
        if (transfers) {
            if ((uint64_t)g + (uint64_t)VALUE_GAS < (uint64_t)g)
                return 0;
            g += VALUE_GAS;
        }
        return g;
    }
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
    int64_t left;
    int64_t cap;
    if (!ok_nonneg(available) || !ok_nonneg(base) || !ok_nonneg(requested))
        return 0;
    if ((uint64_t)available < (uint64_t)base)
        return 0;
    left = available - base;
    cap = left - (left / 64);
    return requested < cap ? requested : cap;
}

static int lin_ok(int64_t kind, int64_t available, int64_t requested, int64_t memory_gas,
                  int64_t transfers, int64_t new_acct, int64_t is_cold) {
    int64_t cold;
    int64_t avail2;
    int64_t ex;
    if (!ok_kind(kind) || !ok_nonneg(available) || !ok_nonneg(requested) || !ok_nonneg(memory_gas))
        return 0;
    if (!ok_flag(transfers) || !ok_flag(new_acct) || !ok_flag(is_cold))
        return 0;
    cold = lin_surcharge(is_cold);
    if ((uint64_t)available < (uint64_t)cold)
        return 0;
    avail2 = available - cold;
    ex = lin_extra(kind, transfers, new_acct, memory_gas);
    if ((uint64_t)avail2 < (uint64_t)ex)
        return 0;
    return 1;
}

static int64_t lin_dynamic(int64_t kind, int64_t available, int64_t requested, int64_t memory_gas,
                           int64_t transfers, int64_t new_acct, int64_t is_cold) {
    int64_t cold, avail2, ex, f, s, out;
    if (!lin_ok(kind, available, requested, memory_gas, transfers, new_acct, is_cold))
        return 0;
    cold = lin_surcharge(is_cold);
    avail2 = available - cold;
    ex = lin_extra(kind, transfers, new_acct, memory_gas);
    f = lin_forward(avail2, ex, requested);
    s = ex + f;
    if ((uint64_t)s < (uint64_t)ex)
        return 0;
    out = s + cold;
    if ((uint64_t)out < (uint64_t)s)
        return 0;
    return out;
}

static int64_t lin_total(int64_t kind, int64_t available, int64_t requested, int64_t memory_gas,
                         int64_t transfers, int64_t new_acct, int64_t is_cold) {
    int64_t d, s;
    if (!lin_ok(kind, available, requested, memory_gas, transfers, new_acct, is_cold))
        return 0;
    d = lin_dynamic(kind, available, requested, memory_gas, transfers, new_acct, is_cold);
    s = WARM + d;
    if ((uint64_t)s < (uint64_t)d)
        return 0;
    return s;
}

static int64_t lin_forwarded(int64_t kind, int64_t available, int64_t requested, int64_t memory_gas,
                             int64_t transfers, int64_t new_acct, int64_t is_cold) {
    int64_t cold, avail2, ex;
    if (!lin_ok(kind, available, requested, memory_gas, transfers, new_acct, is_cold))
        return 0;
    cold = lin_surcharge(is_cold);
    avail2 = available - cold;
    ex = lin_extra(kind, transfers, new_acct, memory_gas);
    return lin_forward(avail2, ex, requested);
}

static int64_t lin_vs_call(int64_t kind, int64_t available, int64_t requested, int64_t memory_gas,
                           int64_t transfers, int64_t new_acct, int64_t is_cold) {
    if (!lin_ok(KIND_CALL, available, requested, memory_gas, transfers, new_acct, is_cold))
        return 0;
    if (!lin_ok(kind, available, requested, memory_gas, transfers, new_acct, is_cold))
        return 0;
    return lin_dynamic(KIND_CALL, available, requested, memory_gas, transfers, new_acct, is_cold) -
           lin_dynamic(kind, available, requested, memory_gas, transfers, new_acct, is_cold);
}

static int selftest(void) {
    if (lin_extra(KIND_CALL, 1, 1, 0) != 34000)
        return 1;
    if (lin_extra(KIND_CALLCODE, 1, 1, 0) != 9000)
        return 2;
    if (lin_extra(KIND_DELEGATE, 1, 1, 0) != 0)
        return 3;
    if (lin_dynamic(KIND_DELEGATE, 64000, 1000000, 0, 0, 0, 0) != 63000)
        return 4;
    if (lin_dynamic(KIND_STATIC, 64000, 1000000, 0, 0, 0, 1) != 63040)
        return 5;
    if (lin_dynamic(KIND_CALLCODE, 64000, 1000000, 0, 1, 0, 0) != 63141)
        return 6;
    if (lin_dynamic(KIND_CALLCODE, 64000, 1000000, 0, 1, 0, 1) != 63180)
        return 7;
    if (lin_dynamic(KIND_CALLCODE, 100000, 1000000, 0, 1, 1, 0) != 98579)
        return 8;
    if (lin_vs_call(KIND_CALLCODE, 100000, 1000000, 0, 1, 1, 0) != 390)
        return 9;
    if (lin_vs_call(KIND_STATIC, 100000, 1000000, 0, 1, 1, 0) != 531)
        return 10;
    if (lin_dynamic(KIND_CALLCODE, 2499, 0, 0, 0, 0, 1) != 0)
        return 11;
    return 0;
}

static int64_t arg(char **argv, int i) { return strtoll(argv[i], NULL, 10); }

int main(int argc, char **argv) {
    int rc;
    if (argc < 2) {
        fprintf(stderr,
                "usage: geth_callcode2929_c11 selftest|extra k x n m|"
                "dynamic k a r m x n c|total k a r m x n c|fwd k a r m x n c|vs k a r m x n c\n");
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
    if (strcmp(argv[1], "extra") == 0 && argc >= 6) {
        printf("%" PRId64 "\n", lin_extra(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5)));
        return 0;
    }
    if (argc < 9) {
        fprintf(stderr, "need kind + 6 ints\n");
        return 2;
    }
    if (strcmp(argv[1], "dynamic") == 0) {
        printf("%" PRId64 "\n",
               lin_dynamic(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5), arg(argv, 6),
                           arg(argv, 7), arg(argv, 8)));
        return 0;
    }
    if (strcmp(argv[1], "total") == 0) {
        printf("%" PRId64 "\n",
               lin_total(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5), arg(argv, 6),
                         arg(argv, 7), arg(argv, 8)));
        return 0;
    }
    if (strcmp(argv[1], "fwd") == 0) {
        printf("%" PRId64 "\n",
               lin_forwarded(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5), arg(argv, 6),
                             arg(argv, 7), arg(argv, 8)));
        return 0;
    }
    if (strcmp(argv[1], "vs") == 0) {
        printf("%" PRId64 "\n",
               lin_vs_call(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5), arg(argv, 6),
                           arg(argv, 7), arg(argv, 8)));
        return 0;
    }
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
