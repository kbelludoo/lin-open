/*
 * Independent C11 oracle for Aave V3 cumulateToLiquidityIndex (uint64 scale).
 *
 * Two implementations of (a*b+add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_aave_cumulate.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm (ReserveLogic.cumulateToLiquidityIndex + WadRayMath):
 *   result = (wadToRay(amount).rayDiv(wadToRay(totalLiquidity)) + RAY).rayMul(index)
 * Experimental RAY' = 1e9 (mainnet RAY=1e27 does not fit i64).
 * Upstream Solidity is hash-pinned, not vendored. Oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAY 1000000000ULL
#define HALF_RAY 500000000ULL
#define WAD_RAY_RATIO 1000000000ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static uint64_t muldiv_add_i128(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b + (__uint128_t)add) / (__uint128_t)d;
    if (q > (uint64_t)INT64_MAX) return 0;
    return (uint64_t)q;
}

static void muldiv_add_limbs(uint64_t a, uint64_t b, uint64_t add, uint64_t d,
                             uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge, need_borrow;
    int i, ov;
    if (d == 0) {
        *q_out = 0;
        *r_out = 0;
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
    lo = lo + add;
    if (lo < add) hi = hi + 1;
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
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t muldiv_add_limbs_q(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_add_limbs(a, b, add, d, &q, &r, &ov);
    return q;
}

typedef uint64_t (*mdadd_fn)(uint64_t, uint64_t, uint64_t, uint64_t);

static uint64_t ray_mul(uint64_t a, uint64_t b, mdadd_fn md) {
    if (b == 0) return 0;
    return md(a, b, HALF_RAY, RAY);
}

static uint64_t ray_div(uint64_t a, uint64_t b, mdadd_fn md) {
    if (b == 0) return 0;
    return md(a, RAY, b / 2, b);
}

static uint64_t wad_to_ray(uint64_t a, mdadd_fn md) {
    return md(a, WAD_RAY_RATIO, 0, 1);
}

static uint64_t cumulate(uint64_t total_liq, uint64_t amount, uint64_t index, mdadd_fn md) {
    uint64_t a_ray, t_ray, ratio, sum;
    if (total_liq == 0) return 0;
    a_ray = wad_to_ray(amount, md);
    t_ray = wad_to_ray(total_liq, md);
    if (amount != 0 && a_ray == 0) return 0;
    if (t_ray == 0) return 0;
    ratio = ray_div(a_ray, t_ray, md);
    if (ratio > UINT64_MAX - RAY) return 0;
    sum = ratio + RAY;
    return ray_mul(sum, index, md);
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    uint64_t q_i, q_l, r;
    int ov;
    q_i = muldiv_add_i128(100, 200, 0, 50);
    q_l = muldiv_add_limbs_q(100, 200, 0, 50);
    if (q_i != 400 || q_l != 400) return 1;
    muldiv_add_limbs(100, 200, 0, 50, &q_l, &r, &ov);
    if (r != 0 || ov != 0) return 1;
    if (ray_mul(1, HALF_RAY, muldiv_add_i128) != 1) return 1;
    if (ray_mul(1, HALF_RAY, muldiv_add_limbs_q) != 1) return 1;
    if (ray_div(2, 3, muldiv_add_i128) != 666666667ULL) return 1;
    if (ray_div(2, 3, muldiv_add_limbs_q) != 666666667ULL) return 1;
    if (wad_to_ray(1, muldiv_add_i128) != e9) return 1;
    if (cumulate(e9, 0, e9, muldiv_add_i128) != e9) return 1;
    if (cumulate(e9, 0, e9, muldiv_add_limbs_q) != e9) return 1;
    if (cumulate(e9, 1000000ULL, e9, muldiv_add_i128) != 1001000000ULL) return 1;
    if (cumulate(e9, 1000000ULL, e9, muldiv_add_limbs_q) != 1001000000ULL) return 1;
    if (cumulate(e9, 900000ULL, e9, muldiv_add_i128) != 1000900000ULL) return 1;
    if (cumulate(0, 1000000ULL, e9, muldiv_add_i128) != 0) return 1;
    if (wad_to_ray(10000000000ULL, muldiv_add_i128) != 0) return 1;
    if (cumulate(e9, 10000000000ULL, e9, muldiv_add_i128) != 0) return 1;
    puts("PASS");
    return 0;
}

static mdadd_fn parse_md(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) return muldiv_add_limbs_q;
    }
    return muldiv_add_i128;
}

static void usage(void) {
    fprintf(stderr,
            "usage: aave_cumulate_c11 selftest\n"
            "       aave_cumulate_c11 ray_mul A B [--limbs]\n"
            "       aave_cumulate_c11 ray_div A B [--limbs]\n"
            "       aave_cumulate_c11 wad_to_ray A [--limbs]\n"
            "       aave_cumulate_c11 floor_mul A B [--limbs]\n"
            "       aave_cumulate_c11 floor_div A B [--limbs]\n"
            "       aave_cumulate_c11 cumulate LIQ AMT IDX [--limbs]\n");
}

int main(int argc, char **argv) {
    mdadd_fn md;
    if (argc < 2) {
        usage();
        return 2;
    }
    md = parse_md(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "ray_mul") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               ray_mul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "ray_div") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               ray_div(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "wad_to_ray") == 0 && argc >= 3) {
        printf("%" PRIu64 "\n", wad_to_ray(strtoull(argv[2], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "floor_mul") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), 0, RAY));
        return 0;
    }
    if (strcmp(argv[1], "floor_div") == 0 && argc >= 4) {
        uint64_t b = strtoull(argv[3], NULL, 10);
        printf("%" PRIu64 "\n",
               b == 0 ? 0 : md(strtoull(argv[2], NULL, 10), RAY, 0, b));
        return 0;
    }
    if (strcmp(argv[1], "cumulate") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               cumulate(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    usage();
    return 2;
}
