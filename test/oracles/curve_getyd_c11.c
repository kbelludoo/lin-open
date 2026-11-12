/*
 * Independent C11 oracle for Curve 3pool get_y_D / calc_withdraw_one_coin
 * (uint64 scale, N=3, FEE_DEN=1e9, baked 0.04% fee = 400000).
 *
 * Two implementations of (a*b+add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_curve_getyd.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: published stableswap Newton solver (Curve 3pool get_y_D) plus
 * the _calc_withdraw_one_coin fee reduction. Upstream bytes are pinned by
 * sha256/git blob in the proof harness; the Curve.Fi repository states
 * all-rights-reserved / informational-only, so this oracle is original C11
 * and does not vendor the Vyper source.
 *
 * Experimental uint64. Not mainnet uint256 / RATES / PRECISION_MUL.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NCOINS 3
#define NEWTON 255
#define FEE_DEN 1000000000ULL
#define POOL_FEE 400000ULL
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

static uint64_t pick(int i, uint64_t x0, uint64_t x1, uint64_t x2) {
    if (i == 0) return x0;
    if (i == 1) return x1;
    if (i == 2) return x2;
    return 0;
}

static uint64_t get_y_d(int i, uint64_t d, uint64_t x0, uint64_t x1, uint64_t x2,
                        uint64_t amp, mdadd_fn md) {
    uint64_t xp[3], c, s_, ann, ann_n, d_ann, b, y, yprev, two_y, tb, den, xk;
    int k, iter;
    if (i < 0 || i > 2 || d == 0 || amp == 0) return 0;
    if (x0 == 0 || x1 == 0 || x2 == 0) return 0;
    if (amp > I64MAX / (uint64_t)NCOINS) return 0;
    xp[0] = x0;
    xp[1] = x1;
    xp[2] = x2;
    ann = amp * (uint64_t)NCOINS;
    c = d;
    s_ = 0;
    for (k = 0; k < NCOINS; k++) {
        if (k == i) continue;
        xk = xp[k];
        if (s_ > I64MAX - xk) return 0;
        s_ += xk;
        if (xk > I64MAX / (uint64_t)NCOINS) return 0;
        c = md(c, d, 0, xk * (uint64_t)NCOINS);
        if (c == 0) return 0;
    }
    ann_n = md(ann, (uint64_t)NCOINS, 0, 1);
    if (ann_n == 0) return 0;
    c = md(c, d, 0, ann_n);
    if (c == 0) return 0;
    d_ann = md(d, 1, 0, ann);
    if (s_ > I64MAX - d_ann) return 0;
    b = s_ + d_ann;
    y = d;
    for (iter = 0; iter < NEWTON; iter++) {
        yprev = y;
        if (y > I64MAX - y) return 0;
        two_y = y + y;
        if (two_y > I64MAX - b) return 0;
        tb = two_y + b;
        if (tb < d) return 0;
        den = tb - d;
        if (den == 0) return 0;
        y = md(y, y, c, den);
        if (y == 0) return 0;
        if (y >= yprev) {
            if (y - yprev <= 1) break;
        } else if (yprev - y <= 1) {
            break;
        }
    }
    return y;
}

static uint64_t d1_after(uint64_t d0, uint64_t burn, uint64_t supply, mdadd_fn md) {
    uint64_t sub;
    if (d0 == 0 || burn == 0 || supply == 0 || burn >= supply) return 0;
    sub = md(burn, d0, 0, supply);
    if (d0 < sub) return 0;
    return d0 - sub;
}

static uint64_t dy0(int i, uint64_t d1, uint64_t x0, uint64_t x1, uint64_t x2,
                    uint64_t amp, mdadd_fn md) {
    uint64_t y, xi;
    y = get_y_d(i, d1, x0, x1, x2, amp, md);
    if (y == 0) return 0;
    xi = pick(i, x0, x1, x2);
    if (xi < y) return 0;
    return xi - y;
}

static uint64_t n_fee(mdadd_fn md) {
    return md(POOL_FEE, (uint64_t)NCOINS, 0, 4ULL * (uint64_t)(NCOINS - 1));
}

static uint64_t dx_expected(int j, int i, uint64_t xj, uint64_t new_y,
                            uint64_t d0, uint64_t d1, mdadd_fn md) {
    uint64_t prop = md(xj, d1, 0, d0);
    if (j == i) {
        if (prop < new_y) return 0;
        return prop - new_y;
    }
    if (xj < prop) return 0;
    return xj - prop;
}

static uint64_t reduce_xp(uint64_t xp, uint64_t dx, uint64_t nf, mdadd_fn md) {
    uint64_t cut = md(nf, dx, 0, FEE_DEN);
    if (xp < cut) return 0;
    return xp - cut;
}

static uint64_t withdraw_fee(int i, uint64_t d0, uint64_t d1, uint64_t x0,
                             uint64_t x1, uint64_t x2, uint64_t amp, mdadd_fn md) {
    uint64_t new_y, nf, r0, r1, r2, y2, xi, raw;
    uint64_t xp[3];
    int j;
    uint64_t red[3];
    if (d0 == 0 || d1 == 0) return 0;
    new_y = get_y_d(i, d1, x0, x1, x2, amp, md);
    if (new_y == 0) return 0;
    nf = n_fee(md);
    xp[0] = x0;
    xp[1] = x1;
    xp[2] = x2;
    for (j = 0; j < NCOINS; j++) {
        red[j] = reduce_xp(xp[j], dx_expected(j, i, xp[j], new_y, d0, d1, md), nf, md);
        if (red[j] == 0) return 0;
    }
    r0 = red[0];
    r1 = red[1];
    r2 = red[2];
    y2 = get_y_d(i, d1, r0, r1, r2, amp, md);
    if (y2 == 0) return 0;
    xi = pick(i, r0, r1, r2);
    if (xi < y2) return 0;
    raw = xi - y2;
    if (raw == 0) return 0;
    return raw - 1;
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    uint64_t d0 = 3000000000ULL;
    uint64_t d1_10 = 2700000000ULL;
    uint64_t y_i, y_l, dy_i, dy_l, w_i, w_l;
    if (muldiv_add_i128(100, 200, 0, 50) != 400) return 1;
    if (muldiv_add_limbs_q(100, 200, 0, 50) != 400) return 1;
    y_i = get_y_d(0, d0, e9, e9, e9, 100, muldiv_add_i128);
    y_l = get_y_d(0, d0, e9, e9, e9, 100, muldiv_add_limbs_q);
    if (y_i != e9 || y_i != y_l) return 1;
    y_i = get_y_d(0, d1_10, e9, e9, e9, 100, muldiv_add_i128);
    y_l = get_y_d(0, d1_10, e9, e9, e9, 100, muldiv_add_limbs_q);
    if (y_i != 700367933ULL || y_i != y_l) return 1;
    dy_i = dy0(0, d1_10, e9, e9, e9, 100, muldiv_add_i128);
    dy_l = dy0(0, d1_10, e9, e9, e9, 100, muldiv_add_limbs_q);
    if (dy_i != 299632067ULL || dy_i != dy_l) return 1;
    w_i = withdraw_fee(0, d0, d1_10, e9, e9, e9, 100, muldiv_add_i128);
    w_l = withdraw_fee(0, d0, d1_10, e9, e9, e9, 100, muldiv_add_limbs_q);
    if (w_i != 299572241ULL || w_i != w_l) return 1;
    if (d1_after(d0, 300000000ULL, d0, muldiv_add_i128) != d1_10) return 1;
    if (n_fee(muldiv_add_i128) != 150000ULL) return 1;
    if (get_y_d(0, 0, e9, e9, e9, 100, muldiv_add_i128) != 0) return 1;
    if (muldiv_add_i128(3099778671ULL, 3099778671ULL, 0, 1) != 0) return 1;
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
            "usage: curve_getyd_c11 selftest\n"
            "       curve_getyd_c11 getyd I D X0 X1 X2 AMP [--limbs]\n"
            "       curve_getyd_c11 d1 D0 BURN SUPPLY [--limbs]\n"
            "       curve_getyd_c11 dy0 I D1 X0 X1 X2 AMP [--limbs]\n"
            "       curve_getyd_c11 wfee I D0 D1 X0 X1 X2 AMP [--limbs]\n"
            "       curve_getyd_c11 muldiv A B D [--limbs]\n");
}

int main(int argc, char **argv) {
    mdadd_fn md;
    if (argc < 2) {
        usage();
        return 2;
    }
    md = parse_md(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "getyd") == 0 && argc >= 8) {
        printf("%" PRIu64 "\n",
               get_y_d(atoi(argv[2]), strtoull(argv[3], NULL, 10),
                       strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                       strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "d1") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               d1_after(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "dy0") == 0 && argc >= 8) {
        printf("%" PRIu64 "\n",
               dy0(atoi(argv[2]), strtoull(argv[3], NULL, 10),
                   strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                   strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "wfee") == 0 && argc >= 9) {
        printf("%" PRIu64 "\n",
               withdraw_fee(atoi(argv[2]), strtoull(argv[3], NULL, 10),
                            strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                            strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                            strtoull(argv[8], NULL, 10), md));
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
