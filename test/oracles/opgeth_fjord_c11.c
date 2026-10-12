/*
 * Independent C11 oracle for op-geth NewL1CostFuncFjord / estimatedDASizeScaled.
 *
 * Fjord: estimatedSize * (baseFeeScalar*l1BaseFee*16 + blobFeeScalar*l1BlobBaseFee) / 1e12
 * estimatedSize = max(100e6, 836500*fastlz - 42585600)   (intercept is negative)
 * Ecotone contrast: calldataGas * same_inner / 16e6
 *
 * FastLZ compressor is NOT implemented. FastLZ size is an explicit integer.
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: ethereum-optimism/op-geth v1.101702.3 core/types/rollup_cost.go
 * License of the algorithm: LGPL-3.0. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    COEF = 836500,
    INTERCEPT_ABS = 42585600,
    MIN_SCALED = 100000000
};

static const int64_t DIV1E12 = 1000000000000LL;
static const int64_t DIV16E6 = 16000000LL;
static const int64_t DIV1E6 = 1000000LL;

static int ok_nonneg(int64_t v) { return v >= 0; }

static int64_t muldiv(int64_t a, int64_t b, int64_t d) {
    unsigned __int128 prod;
    unsigned __int128 q;
    if (a < 0 || b < 0 || d <= 0)
        return 0;
    prod = (unsigned __int128)(uint64_t)a * (unsigned __int128)(uint64_t)b;
    q = prod / (unsigned __int128)(uint64_t)d;
    if (q > (unsigned __int128)INT64_MAX)
        return 0;
    return (int64_t)q;
}

static int64_t est(int64_t flz) {
    int64_t raw, unclamped;
    if (!ok_nonneg(flz))
        return 0;
    raw = muldiv(COEF, flz, 1);
    if (raw == 0 && flz != 0)
        return 0;
    if ((uint64_t)raw < (uint64_t)INTERCEPT_ABS)
        return MIN_SCALED;
    unclamped = raw - INTERCEPT_ABS;
    if ((uint64_t)unclamped < (uint64_t)MIN_SCALED)
        return MIN_SCALED;
    return unclamped;
}

static int64_t unclamped(int64_t flz) {
    int64_t raw;
    if (!ok_nonneg(flz))
        return 0;
    raw = muldiv(COEF, flz, 1);
    if (raw == 0 && flz != 0)
        return 0;
    if ((uint64_t)raw < (uint64_t)INTERCEPT_ABS)
        return 0;
    return raw - INTERCEPT_ABS;
}

static int64_t inner(int64_t bf, int64_t bb, int64_t bs, int64_t bbs) {
    int64_t a, a2, b, s;
    if (!ok_nonneg(bf) || !ok_nonneg(bb) || !ok_nonneg(bs) || !ok_nonneg(bbs))
        return 0;
    a = muldiv(bf, 16, 1);
    if (a == 0 && bf != 0)
        return 0;
    a2 = muldiv(a, bs, 1);
    if (a2 == 0 && a != 0 && bs != 0)
        return 0;
    b = muldiv(bb, bbs, 1);
    if (b == 0 && bb != 0 && bbs != 0)
        return 0;
    s = a2 + b;
    if ((uint64_t)s < (uint64_t)a2)
        return 0;
    return s;
}

static int64_t fjo_fee(int64_t flz, int64_t bf, int64_t bb, int64_t bs, int64_t bbs) {
    int64_t e = est(flz);
    int64_t inn = inner(bf, bb, bs, bbs);
    if (e == 0)
        return 0;
    if (inn == 0 && (bf != 0 || bb != 0) && (bs != 0 || bbs != 0))
        return 0;
    return muldiv(e, inn, DIV1E12);
}

static int64_t fjo_gas(int64_t flz) {
    int64_t e = est(flz);
    if (e == 0)
        return 0;
    return muldiv(e, 16, DIV1E6);
}

static int64_t fjo_eco(int64_t z, int64_t o, int64_t bf, int64_t bb, int64_t bs, int64_t bbs) {
    int64_t cg, inn;
    if (!ok_nonneg(z) || !ok_nonneg(o))
        return 0;
    cg = z * 4 + o * 16;
    inn = inner(bf, bb, bs, bbs);
    return muldiv(cg, inn, DIV16E6);
}

static int64_t fjo_vs(int64_t flz, int64_t z, int64_t o, int64_t bf, int64_t bb, int64_t bs, int64_t bbs) {
    int64_t full = fjo_fee(flz, bf, bb, bs, bbs);
    int64_t eco = fjo_eco(z, o, bf, bb, bs, bbs);
    if ((uint64_t)full < (uint64_t)eco)
        return 0;
    return full - eco;
}

static int selftest(void) {
    if (inner(1000000000LL, 10000000LL, 2, 3) != 32030000000LL)
        return 1;
    if (est(100) != 100000000LL || est(170) != 100000000LL)
        return 2;
    if (est(171) != 100455900LL || est(200) != 124714400LL)
        return 3;
    if (fjo_fee(100, 1000000000LL, 10000000LL, 2, 3) != 3203000LL)
        return 4;
    if (fjo_fee(171, 1000000000LL, 10000000LL, 2, 3) != 3217602LL)
        return 5;
    if (fjo_fee(235, 2000000LL, 3000000LL, 20, 15) != 105484LL)
        return 6;
    if (fjo_gas(100) != 1600LL || fjo_gas(235) != 2463LL)
        return 7;
    if (fjo_eco(0, 30, 1000000000LL, 10000000LL, 2, 3) != 960900LL)
        return 8;
    if (fjo_vs(31, 0, 30, 1000000000LL, 10000000LL, 2, 3) != 2242100LL)
        return 9;
    if (unclamped(31) != 0 || fjo_fee(-1, 1, 0, 1, 0) != 0)
        return 10;
    return 0;
}

static int64_t arg(char **argv, int i) { return strtoll(argv[i], NULL, 10); }

int main(int argc, char **argv) {
    int rc;
    if (argc < 2) {
        fprintf(stderr, "usage: opgeth_fjord_c11 selftest|est|unclamped|fee|gas|eco|vs|inner\n");
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
    if (strcmp(argv[1], "est") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", est(arg(argv, 2)));
        return 0;
    }
    if (strcmp(argv[1], "unclamped") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", unclamped(arg(argv, 2)));
        return 0;
    }
    if (strcmp(argv[1], "inner") == 0 && argc >= 6) {
        printf("%" PRId64 "\n", inner(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5)));
        return 0;
    }
    if (strcmp(argv[1], "fee") == 0 && argc >= 7) {
        printf("%" PRId64 "\n", fjo_fee(arg(argv, 2), arg(argv, 3), arg(argv, 4),
                                        arg(argv, 5), arg(argv, 6)));
        return 0;
    }
    if (strcmp(argv[1], "gas") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", fjo_gas(arg(argv, 2)));
        return 0;
    }
    if (strcmp(argv[1], "eco") == 0 && argc >= 8) {
        printf("%" PRId64 "\n", fjo_eco(arg(argv, 2), arg(argv, 3), arg(argv, 4),
                                        arg(argv, 5), arg(argv, 6), arg(argv, 7)));
        return 0;
    }
    if (strcmp(argv[1], "vs") == 0 && argc >= 9) {
        printf("%" PRId64 "\n", fjo_vs(arg(argv, 2), arg(argv, 3), arg(argv, 4),
                                       arg(argv, 5), arg(argv, 6), arg(argv, 7), arg(argv, 8)));
        return 0;
    }
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
