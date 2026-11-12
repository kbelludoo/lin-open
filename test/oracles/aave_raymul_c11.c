/*
 * Independent C11 oracle for Aave V3 WadRayMath.rayMul / rayDiv (uint64 scale).
 *
 * RAY' = 1e9 (mainnet RAY=1e27 does not fit uint64). Half-up:
 *   rayMul(a,b) = (a*b + HALF_RAY') / RAY'
 *   rayDiv(a,b) = (a*RAY' + b/2) / b
 *
 * Two implementations of (a*b + add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_aave_raymul.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: aave/aave-v3-core WadRayMath.sol (MIT after BUSL
 * Change Date 2023-01-27). This oracle is original C11 and does not vendor
 * the Solidity source.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAY_P 1000000000ULL
#define HALF_RAY_P 500000000ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_add_limbs_qr(uint64_t a, uint64_t b, uint64_t add, uint64_t d,
                                uint64_t *q_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo;
    uint64_t bit, ge, need_borrow, lo2;
    int i, ov;

    if (d == 0) {
        *q_out = 0;
        *ov_out = 1;
        return;
    }
    a0 = a & 0xffffffffULL;
    a1 = a >> 32;
    b0 = b & 0xffffffffULL;
    b1 = b >> 32;
    p0 = a0 * b0;
    p1 = a0 * b1;
    p2 = a1 * b0;
    p3 = a1 * b1;
    mid = p1 + p2;
    mid_carry = (mid < p1) ? 1 : 0;
    t = (mid & 0xffffffffULL) << 32;
    lo = p0 + t;
    lo_carry = (lo < p0) ? 1 : 0;
    hi = p3 + (mid >> 32);
    hi = hi + (mid_carry << 32);
    hi = hi + lo_carry;
    lo2 = lo + add;
    hi = hi + ((lo2 < lo) ? 1ULL : 0ULL);
    lo = lo2;

    r_hi = 0;
    r_lo = 0;
    q = 0;
    ov = 0;
    for (i = 127; i >= 0; i--) {
        bit = (i >= 64) ? ((hi >> (i - 64)) & 1ULL) : ((lo >> i) & 1ULL);
        new_hi = (r_hi << 1) | (r_lo >> 63);
        new_lo = (r_lo << 1) | bit;
        r_hi = new_hi;
        r_lo = new_lo;
        ge = (r_hi != 0) || (r_lo >= d);
        if (ge) {
            need_borrow = u_lt(r_lo, d);
            r_lo = r_lo - d;
            if (need_borrow) r_hi = r_hi - 1;
            if (i >= 64) ov = 1;
            if (i < 64) q = q | (1ULL << i);
        }
    }
    if ((int64_t)q < 0) ov = 1;
    *q_out = ov ? 0 : q;
    *ov_out = ov;
}

static uint64_t muldiv_add_limbs(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    uint64_t q;
    int ov;
    muldiv_add_limbs_qr(a, b, add, d, &q, &ov);
    return q;
}

static int muldiv_add_limbs_ov(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    uint64_t q;
    int ov;
    muldiv_add_limbs_qr(a, b, add, d, &q, &ov);
    return ov;
}

static uint64_t muldiv_add_i128(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    __uint128_t num, q;
    if (d == 0) return 0;
    num = (__uint128_t)a * (__uint128_t)b + (__uint128_t)add;
    q = num / (__uint128_t)d;
    if (q > (uint64_t)INT64_MAX) return 0;
    return (uint64_t)q;
}

static int muldiv_add_i128_ov(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    __uint128_t num, q;
    if (d == 0) return 1;
    num = (__uint128_t)a * (__uint128_t)b + (__uint128_t)add;
    q = num / (__uint128_t)d;
    return q > (uint64_t)INT64_MAX;
}

static uint64_t ray_mul(uint64_t a, uint64_t b,
                       uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    if (a == 0 || b == 0) return 0;
    return md(a, b, HALF_RAY_P, RAY_P);
}

static uint64_t ray_div(uint64_t a, uint64_t b,
                       uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    if (b == 0) return 0;
    return md(a, RAY_P, b / 2, b);
}

static uint64_t floor_mul(uint64_t a, uint64_t b,
                         uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    if (a == 0 || b == 0) return 0;
    return md(a, b, 0, RAY_P);
}

static uint64_t floor_div(uint64_t a, uint64_t b,
                         uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t)) {
    if (b == 0) return 0;
    return md(a, RAY_P, 0, b);
}

static int selftest(void) {
    int fail = 0;
    struct {
        uint64_t a, b;
        const char *kind;
        uint64_t want;
    } vec[] = {
        {RAY_P, RAY_P, "mul", RAY_P},
        {1, HALF_RAY_P, "mul", 1},
        {1, HALF_RAY_P, "floor_mul", 0},
        {3, HALF_RAY_P, "mul", 2},
        {3, HALF_RAY_P, "floor_mul", 1},
        {1, HALF_RAY_P - 1, "mul", 0},
        {2, 3, "div", 666666667ULL},
        {2, 3, "floor_div", 666666666ULL},
        {RAY_P, RAY_P + RAY_P, "div", HALF_RAY_P},
        {10000000000ULL, 10000000000ULL, "mul", 100000000000ULL},
        {4000000000000000000ULL, 3000000000000000000ULL, "mul", 0},
        {1, 1, "mul", 0},
        {0, RAY_P, "mul", 0},
        {1, 0, "div", 0},
        {1, 3, "div", 333333333ULL},
    };
    size_t i, n = sizeof(vec) / sizeof(vec[0]);
    for (i = 0; i < n; i++) {
        uint64_t a = vec[i].a, b = vec[i].b, got_i, got_l, want = vec[i].want;
        const char *k = vec[i].kind;
        if (strcmp(k, "mul") == 0) {
            got_i = ray_mul(a, b, muldiv_add_i128);
            got_l = ray_mul(a, b, muldiv_add_limbs);
        } else if (strcmp(k, "div") == 0) {
            got_i = ray_div(a, b, muldiv_add_i128);
            got_l = ray_div(a, b, muldiv_add_limbs);
        } else if (strcmp(k, "floor_mul") == 0) {
            got_i = floor_mul(a, b, muldiv_add_i128);
            got_l = floor_mul(a, b, muldiv_add_limbs);
        } else {
            got_i = floor_div(a, b, muldiv_add_i128);
            got_l = floor_div(a, b, muldiv_add_limbs);
        }
        if (got_i != want || got_l != want) {
            fprintf(stderr, "selftest fail %s a=%" PRIu64 " b=%" PRIu64
                            " i128=%" PRIu64 " limbs=%" PRIu64 " want=%" PRIu64 "\n",
                    k, a, b, got_i, got_l, want);
            fail = 1;
        }
    }
    if (muldiv_add_i128_ov(4000000000000000000ULL, 3000000000000000000ULL,
                           HALF_RAY_P, RAY_P) == 0)
        fail = 1;
    if (muldiv_add_limbs_ov(4000000000000000000ULL, 3000000000000000000ULL,
                            HALF_RAY_P, RAY_P) == 0)
        fail = 1;
    if (fail) {
        printf("FAIL\n");
        return 1;
    }
    printf("PASS\n");
    return 0;
}

static void usage(void) {
    fprintf(stderr,
            "usage: aave_raymul_c11 selftest\n"
            "       aave_raymul_c11 mul|div|floor_mul|floor_div A B [--limbs]\n"
            "       aave_raymul_c11 ov-mul A B [--limbs]\n");
}

int main(int argc, char **argv) {
    uint64_t a, b, got;
    int limbs = 0;
    const char *kind;
    uint64_t (*md)(uint64_t, uint64_t, uint64_t, uint64_t);

    if (argc < 2) {
        usage();
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (argc < 4) {
        usage();
        return 2;
    }
    kind = argv[1];
    a = strtoull(argv[2], NULL, 10);
    b = strtoull(argv[3], NULL, 10);
    if (argc >= 5 && strcmp(argv[4], "--limbs") == 0) limbs = 1;
    md = limbs ? muldiv_add_limbs : muldiv_add_i128;
    if (strcmp(kind, "mul") == 0) {
        got = ray_mul(a, b, md);
    } else if (strcmp(kind, "div") == 0) {
        got = ray_div(a, b, md);
    } else if (strcmp(kind, "floor_mul") == 0) {
        got = floor_mul(a, b, md);
    } else if (strcmp(kind, "floor_div") == 0) {
        got = floor_div(a, b, md);
    } else if (strcmp(kind, "ov-mul") == 0) {
        got = limbs ? (uint64_t)muldiv_add_limbs_ov(a, b, HALF_RAY_P, RAY_P)
                    : (uint64_t)muldiv_add_i128_ov(a, b, HALF_RAY_P, RAY_P);
    } else {
        usage();
        return 2;
    }
    printf("%" PRIu64 "\n", got);
    return 0;
}
