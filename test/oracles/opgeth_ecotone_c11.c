/*
 * Independent C11 oracle for op-geth newL1CostFuncEcotone / Bedrock / operator.
 *
 * Ecotone: calldataGas * (l1BaseFee*16*baseScalar + blobBaseFee*blobScalar) / 16e6
 * Bedrock: (calldataGas[+68*16] + overhead) * l1BaseFee * scalar / 1e6
 * Isthmus operator: gas * scalar / 1e6 + constant
 * Jovian operator: gas * scalar * 100 + constant
 *
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
    ZERO_GAS = 4,
    NZ_GAS = 16,
    PRE_PAD = 68,
    DIV16E6 = 16000000,
    DIV1E6 = 1000000
};

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

static int64_t calldata(int64_t zeroes, int64_t ones) {
    int64_t z, n, s;
    if (!ok_nonneg(zeroes) || !ok_nonneg(ones))
        return 0;
    z = muldiv(zeroes, ZERO_GAS, 1);
    n = muldiv(ones, NZ_GAS, 1);
    if ((z == 0 && zeroes != 0) || (n == 0 && ones != 0))
        return 0;
    s = z + n;
    if ((uint64_t)s < (uint64_t)z)
        return 0;
    return s;
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

static int64_t eco_fee(int64_t z, int64_t o, int64_t bf, int64_t bb, int64_t bs, int64_t bbs) {
    int64_t cg = calldata(z, o);
    int64_t inn = inner(bf, bb, bs, bbs);
    if (cg == 0 && (z != 0 || o != 0))
        return 0;
    if (inn == 0 && (bf != 0 || bb != 0) && (bs != 0 || bbs != 0))
        return 0;
    return muldiv(cg, inn, DIV16E6);
}

static int64_t eco_noblob(int64_t z, int64_t o, int64_t bf, int64_t bs) {
    return eco_fee(z, o, bf, 0, bs, 0);
}

static int64_t eco_vs(int64_t z, int64_t o, int64_t bf, int64_t bb, int64_t bs, int64_t bbs) {
    int64_t full = eco_fee(z, o, bf, bb, bs, bbs);
    int64_t drop = eco_noblob(z, o, bf, bs);
    if ((uint64_t)full < (uint64_t)drop)
        return 0;
    return full - drop;
}

static int64_t bedrock(int64_t z, int64_t o, int64_t overhead, int64_t bf, int64_t scalar, int64_t regolith) {
    int64_t cg, g, tmp;
    if (!ok_nonneg(overhead) || !ok_nonneg(bf) || !ok_nonneg(scalar))
        return 0;
    if (regolith != 0 && regolith != 1)
        return 0;
    cg = calldata(z, o);
    if (regolith == 0) {
        int64_t pad = muldiv(PRE_PAD, NZ_GAS, 1);
        int64_t t = cg + pad;
        if ((uint64_t)t < (uint64_t)cg)
            return 0;
        cg = t;
    }
    g = cg + overhead;
    if ((uint64_t)g < (uint64_t)cg)
        return 0;
    tmp = muldiv(g, bf, 1);
    if (tmp == 0 && g != 0 && bf != 0)
        return 0;
    return muldiv(tmp, scalar, DIV1E6);
}

static int64_t op_isthmus(int64_t gas, int64_t scalar, int64_t constant) {
    int64_t q, s;
    if (!ok_nonneg(gas) || !ok_nonneg(scalar) || !ok_nonneg(constant))
        return 0;
    q = muldiv(gas, scalar, DIV1E6);
    s = q + constant;
    if ((uint64_t)s < (uint64_t)q)
        return 0;
    return s;
}

static int64_t op_jovian(int64_t gas, int64_t scalar, int64_t constant) {
    int64_t p, p2, s;
    if (!ok_nonneg(gas) || !ok_nonneg(scalar) || !ok_nonneg(constant))
        return 0;
    p = muldiv(gas, scalar, 1);
    if (p == 0 && gas != 0 && scalar != 0)
        return 0;
    p2 = muldiv(p, 100, 1);
    if (p2 == 0 && p != 0)
        return 0;
    s = p2 + constant;
    if ((uint64_t)s < (uint64_t)p2)
        return 0;
    return s;
}

static int selftest(void) {
    if (calldata(0, 30) != 480)
        return 1;
    if (eco_fee(0, 30, 1000000000LL, 10000000LL, 2, 3) != 960900)
        return 2;
    if (eco_noblob(0, 30, 1000000000LL, 2) != 960000)
        return 3;
    if (eco_vs(0, 30, 1000000000LL, 10000000LL, 2, 3) != 900)
        return 4;
    if (bedrock(0, 30, 50, 1000000000LL, 7000000LL, 0) != 11326000000000LL)
        return 5;
    if (bedrock(0, 30, 50, 1000000000LL, 7000000LL, 1) != 3710000000000LL)
        return 6;
    if (op_isthmus(1618, 1439103868LL, 1256417826609331460LL) != 1256417826611659930LL)
        return 7;
    if (op_jovian(1618, 1439103868LL, 1256417826609331460LL) != 1256650673615173860LL)
        return 8;
    if (eco_fee(-1, 0, 1, 0, 1, 0) != 0)
        return 9;
    return 0;
}

static int64_t arg(char **argv, int i) { return strtoll(argv[i], NULL, 10); }

int main(int argc, char **argv) {
    int rc;
    if (argc < 2) {
        fprintf(stderr, "usage: opgeth_ecotone_c11 selftest|calldata|fee|noblob|vs|bedrock|isthmus|jovian\n");
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
    if (strcmp(argv[1], "calldata") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", calldata(arg(argv, 2), arg(argv, 3)));
        return 0;
    }
    if (strcmp(argv[1], "fee") == 0 && argc >= 8) {
        printf("%" PRId64 "\n", eco_fee(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5),
                                        arg(argv, 6), arg(argv, 7)));
        return 0;
    }
    if (strcmp(argv[1], "noblob") == 0 && argc >= 6) {
        printf("%" PRId64 "\n", eco_noblob(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5)));
        return 0;
    }
    if (strcmp(argv[1], "vs") == 0 && argc >= 8) {
        printf("%" PRId64 "\n", eco_vs(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5),
                                       arg(argv, 6), arg(argv, 7)));
        return 0;
    }
    if (strcmp(argv[1], "bedrock") == 0 && argc >= 8) {
        printf("%" PRId64 "\n", bedrock(arg(argv, 2), arg(argv, 3), arg(argv, 4), arg(argv, 5),
                                        arg(argv, 6), arg(argv, 7)));
        return 0;
    }
    if (strcmp(argv[1], "isthmus") == 0 && argc >= 5) {
        printf("%" PRId64 "\n", op_isthmus(arg(argv, 2), arg(argv, 3), arg(argv, 4)));
        return 0;
    }
    if (strcmp(argv[1], "jovian") == 0 && argc >= 5) {
        printf("%" PRId64 "\n", op_jovian(arg(argv, 2), arg(argv, 3), arg(argv, 4)));
        return 0;
    }
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
