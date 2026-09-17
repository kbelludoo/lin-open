/*
 * Independent C11 oracle for go-ethereum calcRefund (EIP-3529), uint64 / i64.
 *
 * Two implementations:
 *   1. Geth uint64 wrap: gasUsed = initial - remaining (C unsigned wrap),
 *      refund = min(used / quotient, state_refund). Quotient is 2 pre-London
 *      and 5 after EIP-3529.
 *   2. LIN fail-closed i64: remaining > initial, negatives, or remaining+refund
 *      overflow at INT64_MAX (Geth MaxGasLimit) returns 0.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: ethereum/go-ethereum v1.16.9 core/state_transition.go calcRefund
 * License of the algorithm: LGPL-3.0. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define Q_PRE 2ULL
#define Q_LONDON 5ULL

static uint64_t geth_gas_used(uint64_t initial, uint64_t remaining) {
    return initial - remaining; /* Geth: no underflow check */
}

static uint64_t geth_refund(uint64_t used, uint64_t state_refund, int london) {
    uint64_t refund = london ? (used / Q_LONDON) : (used / Q_PRE);
    if (refund > state_refund)
        refund = state_refund;
    return refund;
}

static int64_t lin_gas_used(int64_t initial, int64_t remaining) {
    if (initial < 0 || remaining < 0)
        return 0;
    if (remaining > initial)
        return 0;
    return initial - remaining;
}

static int64_t lin_refund(int64_t used, int64_t state_refund, int london) {
    int64_t cap;
    if (used < 0 || state_refund < 0 || london < 0)
        return 0;
    cap = london ? (used / (int64_t)Q_LONDON) : (used / (int64_t)Q_PRE);
    return cap < state_refund ? cap : state_refund;
}

static int64_t lin_london_kept(int64_t used, int64_t state_refund) {
    int64_t pre = lin_refund(used, state_refund, 0);
    int64_t lon = lin_refund(used, state_refund, 1);
    if (lon > pre)
        return 0;
    return pre - lon;
}

static int64_t lin_paid(int64_t used, int64_t refund) {
    if (used < 0 || refund < 0 || refund > used)
        return 0;
    return used - refund;
}

static int64_t lin_apply(int64_t remaining, int64_t refund) {
    if (remaining < 0 || refund < 0)
        return 0;
    if (remaining > INT64_MAX - refund)
        return 0;
    return remaining + refund;
}

static int selftest(void) {
    if (lin_refund(21000, 0, 1) != 0)
        return 1;
    if (lin_refund(21000, 100000, 1) != 4200)
        return 2;
    if (lin_refund(21000, 100000, 0) != 10500)
        return 3;
    if (lin_refund(21000, 1000, 1) != 1000)
        return 4;
    if (lin_refund(5, 100, 1) != 1)
        return 5;
    if (lin_refund(4, 100, 1) != 0)
        return 6;
    if (lin_london_kept(21000, 100000) != 6300)
        return 7;
    if (lin_gas_used(21000, 21001) != 0)
        return 8;
    if (geth_gas_used(21000ULL, 21001ULL) != UINT64_MAX)
        return 9;
    if (geth_refund(21000ULL, 100000ULL, 1) != 4200ULL)
        return 10;
    if (geth_refund(21000ULL, 100000ULL, 0) != 10500ULL)
        return 11;
    if (lin_paid(21000, 4200) != 16800)
        return 12;
    if (lin_apply(0, 4200) != 4200)
        return 13;
    return 0;
}

int main(int argc, char **argv) {
    int64_t a, b, c;
    int london;
    if (argc < 2) {
        fprintf(stderr, "usage: geth_calcrefund_c11 selftest|refund used state london|used initial remaining|geth-used i r|geth-refund used state london|kept used state|paid used refund|apply rem refund\n");
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
    if (strcmp(argv[1], "refund") == 0 && argc >= 5) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        london = (int)strtol(argv[4], NULL, 10);
        printf("%" PRId64 "\n", lin_refund(a, b, london));
        return 0;
    }
    if (strcmp(argv[1], "used") == 0 && argc >= 4) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        printf("%" PRId64 "\n", lin_gas_used(a, b));
        return 0;
    }
    if (strcmp(argv[1], "geth-used") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n", geth_gas_used(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "geth-refund") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", geth_refund(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), (int)strtol(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "kept") == 0 && argc >= 4) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        printf("%" PRId64 "\n", lin_london_kept(a, b));
        return 0;
    }
    if (strcmp(argv[1], "paid") == 0 && argc >= 4) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        printf("%" PRId64 "\n", lin_paid(a, b));
        return 0;
    }
    if (strcmp(argv[1], "apply") == 0 && argc >= 4) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        printf("%" PRId64 "\n", lin_apply(a, b));
        return 0;
    }
    (void)c;
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
