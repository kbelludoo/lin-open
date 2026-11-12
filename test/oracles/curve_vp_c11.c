/*
 * Independent C11 oracle for Curve 3pool get_D / get_virtual_price
 * (uint64 scale, N=3, SCALE=1e9 standing in for PRECISION=1e18).
 *
 * Two implementations of (a*b+add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_curve_vp.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: published stableswap Newton get_D plus D * SCALE / supply.
 * Upstream bytes are pinned by sha256/git blob in the proof harness; the
 * Curve.Fi repository states all-rights-reserved / informational-only, so
 * this oracle is original C11 and does not vendor the Vyper source.
 *
 * Experimental uint64. Not mainnet uint256 / RATES / PRECISION / token.totalSupply.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NCOINS 3
#define NEWTON 255
#define SCALE 1000000000ULL
#define I64MAX ((uint64_t)INT64_MAX)

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static uint64_t muldiv_add_i128(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b + (__uint128_t)add) / (__uint128_t)d;
    if (q > I64MAX) return 0;
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

static uint64_t get_d(uint64_t x0, uint64_t x1, uint64_t x2, uint64_t amp, mdadd_fn md) {
    uint64_t xp[3], s, ann, d, dp, dprev, xkn, ann_s, dp_n, left, ann1_d, n1_dp, den;
    int k, iter;
    if (amp == 0 || x0 == 0 || x1 == 0 || x2 == 0) return 0;
    if (amp > I64MAX / (uint64_t)NCOINS) return 0;
    xp[0] = x0;
    xp[1] = x1;
    xp[2] = x2;
    s = 0;
    for (k = 0; k < NCOINS; k++) {
        if (s > I64MAX - xp[k]) return 0;
        s += xp[k];
    }
    if (s == 0) return 0;
    ann = amp * (uint64_t)NCOINS;
    d = s;
    for (iter = 0; iter < NEWTON; iter++) {
        dp = d;
        for (k = 0; k < NCOINS; k++) {
            xkn = md(xp[k], (uint64_t)NCOINS, 0, 1);
            if (xkn == 0) return 0;
            dp = md(dp, d, 0, xkn);
            if (dp == 0) return 0;
        }
        dprev = d;
        ann_s = md(ann, s, 0, 1);
        dp_n = md(dp, (uint64_t)NCOINS, 0, 1);
        if (ann_s == 0 || dp_n == 0) return 0;
        if (ann_s > I64MAX - dp_n) return 0;
        left = ann_s + dp_n;
        ann1_d = md(ann - 1, d, 0, 1);
        n1_dp = md((uint64_t)(NCOINS + 1), dp, 0, 1);
        if (ann1_d == 0 || n1_dp == 0) return 0;
        if (ann1_d > I64MAX - n1_dp) return 0;
        den = ann1_d + n1_dp;
        if (den == 0) return 0;
        d = md(left, d, 0, den);
        if (d == 0) return 0;
        if (d >= dprev) {
            if (d - dprev <= 1) break;
        } else if (dprev - d <= 1) {
            break;
        }
    }
    return d;
}

static uint64_t from_d(uint64_t d, uint64_t supply, mdadd_fn md) {
    if (d == 0 || supply == 0) return 0;
    return md(d, SCALE, 0, supply);
}

static uint64_t virtual_price(uint64_t x0, uint64_t x1, uint64_t x2, uint64_t amp,
                              uint64_t supply, mdadd_fn md) {
    return from_d(get_d(x0, x1, x2, amp, md), supply, md);
}

static uint64_t constant_sum_price(uint64_t x0, uint64_t x1, uint64_t x2,
                                   uint64_t supply, mdadd_fn md) {
    uint64_t s;
    if (supply == 0) return 0;
    if (x0 > I64MAX - x1) return 0;
    s = x0 + x1;
    if (s > I64MAX - x2) return 0;
    s += x2;
    if (s == 0) return 0;
    return md(s, SCALE, 0, supply);
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    uint64_t d0 = 3000000000ULL;
    uint64_t dimb = 3099778671ULL;
    uint64_t d_i, d_l, v_i, v_l;
    if (muldiv_add_i128(100, 200, 0, 50) != 400) return 1;
    if (muldiv_add_limbs_q(100, 200, 0, 50) != 400) return 1;
    d_i = get_d(e9, e9, e9, 100, muldiv_add_i128);
    d_l = get_d(e9, e9, e9, 100, muldiv_add_limbs_q);
    if (d_i != d0 || d_i != d_l) return 1;
    v_i = virtual_price(e9, e9, e9, 100, d0, muldiv_add_i128);
    v_l = virtual_price(e9, e9, e9, 100, d0, muldiv_add_limbs_q);
    if (v_i != e9 || v_i != v_l) return 1;
    d_i = get_d(1200000000ULL, 900000000ULL, e9, 100, muldiv_add_i128);
    d_l = get_d(1200000000ULL, 900000000ULL, e9, 100, muldiv_add_limbs_q);
    if (d_i != dimb || d_i != d_l) return 1;
    v_i = virtual_price(1200000000ULL, 900000000ULL, e9, 100, 3100000000ULL, muldiv_add_i128);
    v_l = virtual_price(1200000000ULL, 900000000ULL, e9, 100, 3100000000ULL, muldiv_add_limbs_q);
    if (v_i != 999928603ULL || v_i != v_l) return 1;
    if (from_d(3001000000ULL, d0, muldiv_add_i128) != 1000333333ULL) return 1;
    if (muldiv_add_i128(12000000000ULL, e9, 0, 1) != 0) return 1;
    if (virtual_price(e9, e9, 0, 100, d0, muldiv_add_i128) != 0) return 1;
    printf("PASS\n");
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
            "usage: curve_vp_c11 selftest\n"
            "       curve_vp_c11 getd X0 X1 X2 AMP [--limbs]\n"
            "       curve_vp_c11 vp X0 X1 X2 AMP SUPPLY [--limbs]\n"
            "       curve_vp_c11 fromd D SUPPLY [--limbs]\n"
            "       curve_vp_c11 csum X0 X1 X2 SUPPLY [--limbs]\n"
            "       curve_vp_c11 muldiv A B D [--limbs]\n");
}

int main(int argc, char **argv) {
    mdadd_fn md;
    if (argc < 2) {
        usage();
        return 2;
    }
    md = parse_md(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "getd") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               get_d(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                     strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "vp") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               virtual_price(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                             strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                             strtoull(argv[6], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "fromd") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               from_d(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "csum") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               constant_sum_price(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                  strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), 0,
                  strtoull(argv[4], NULL, 10)));
        return 0;
    }
    usage();
    return 2;
}
