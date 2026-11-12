/*
 * Independent C11 oracle for Curve 3pool get_dy (uint64 scale, N=3, fee).
 *
 * Two implementations of (a*b+add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_curve_getdy.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: published stableswap Newton solver + quote fee
 *   dy = (xp[j] - get_y(...) - 1)
 *   return dy - floor(fee * dy / 1e10)
 * Equal rates (unit xp = balances). RATES 1e30 is NOT claimed.
 * Upstream bytes are pinned by sha256/git blob in the proof harness; the
 * Curve.Fi repository states all-rights-reserved / informational-only, so
 * this oracle is original C11 and does not vendor the Vyper source.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NCOINS 3
#define NEWTON 255
#define FEE_DEN 10000000000ULL

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

static uint64_t pick(int i, uint64_t x0, uint64_t x1, uint64_t x2) {
    if (i == 0) return x0;
    if (i == 1) return x1;
    if (i == 2) return x2;
    return 0;
}

static uint64_t get_d(uint64_t x0, uint64_t x1, uint64_t x2, uint64_t amp, mdadd_fn md) {
    uint64_t s, ann, d, dp, dprev, dp_n, sum, left, right, den;
    int iter;
    if (amp == 0 || x0 == 0 || x1 == 0 || x2 == 0) return 0;
    if (x0 > UINT64_MAX - x1) return 0;
    s = x0 + x1;
    if (s > UINT64_MAX - x2) return 0;
    s = s + x2;
    if (s == 0) return 0;
    if (amp > UINT64_MAX / NCOINS) return 0;
    ann = amp * NCOINS;
    d = s;
    for (iter = 0; iter < NEWTON; iter++) {
        dp = d;
        dp = md(dp, d, 0, x0 * (uint64_t)NCOINS);
        dp = md(dp, d, 0, x1 * (uint64_t)NCOINS);
        dp = md(dp, d, 0, x2 * (uint64_t)NCOINS);
        dprev = d;
        dp_n = md(dp, (uint64_t)NCOINS, 0, 1);
        sum = md(ann, s, dp_n, 1);
        left = md(ann - 1, d, 0, 1);
        right = md((uint64_t)(NCOINS + 1), dp, 0, 1);
        if (left > UINT64_MAX - right) return 0;
        den = left + right;
        d = md(sum, d, 0, den);
        if (d >= dprev) {
            if (d - dprev <= 1) break;
        } else if (dprev - d <= 1) {
            break;
        }
    }
    return d;
}

static uint64_t get_y(int i, int j, uint64_t x, uint64_t x0, uint64_t x1, uint64_t x2,
                      uint64_t amp, mdadd_fn md) {
    uint64_t d, c, s_, ann, ann_n, d_ann, b, y, yprev, two_y, tb, den, xk, _x;
    int k, iter;
    if (i == j || i < 0 || j < 0 || i > 2 || j > 2 || x == 0) return 0;
    d = get_d(x0, x1, x2, amp, md);
    if (d == 0) return 0;
    ann = amp * (uint64_t)NCOINS;
    c = d;
    s_ = 0;
    for (k = 0; k < NCOINS; k++) {
        if (k == j) continue;
        xk = pick(k, x0, x1, x2);
        _x = (k == i) ? x : xk;
        if (_x == 0) return 0;
        if (s_ > UINT64_MAX - _x) return 0;
        s_ += _x;
        c = md(c, d, 0, _x * (uint64_t)NCOINS);
        if (c == 0) return 0;
    }
    ann_n = md(ann, (uint64_t)NCOINS, 0, 1);
    if (ann_n == 0) return 0;
    c = md(c, d, 0, ann_n);
    if (c == 0) return 0;
    d_ann = md(d, 1, 0, ann);
    if (s_ > UINT64_MAX - d_ann) return 0;
    b = s_ + d_ann;
    y = d;
    for (iter = 0; iter < NEWTON; iter++) {
        yprev = y;
        if (y > UINT64_MAX - y) return 0;
        two_y = y + y;
        if (two_y > UINT64_MAX - b) return 0;
        tb = two_y + b;
        if (tb < d) return 0;
        den = tb - d;
        if (den == 0) return 0;
        y = md(y, y, c, den);
        if (y >= yprev) {
            if (y - yprev <= 1) break;
        } else if (yprev - y <= 1) {
            break;
        }
    }
    return y;
}

static uint64_t get_dy_nofee(int i, int j, uint64_t dx, uint64_t x0, uint64_t x1,
                            uint64_t x2, uint64_t amp, mdadd_fn md) {
    uint64_t xi, x, y, xj, raw;
    xi = pick(i, x0, x1, x2);
    if (xi == 0) return 0;
    if (xi > UINT64_MAX - dx) return 0;
    x = xi + dx;
    y = get_y(i, j, x, x0, x1, x2, amp, md);
    if (y == 0) return 0;
    xj = pick(j, x0, x1, x2);
    if (xj < y) return 0;
    raw = xj - y;
    if (raw == 0) return 0;
    return raw - 1;
}

static uint64_t fee_of(uint64_t dy, uint64_t fee, mdadd_fn md) {
    if (dy == 0 || fee > FEE_DEN) return 0;
    return md(fee, dy, 0, FEE_DEN);
}

static uint64_t get_dy(int i, int j, uint64_t dx, uint64_t x0, uint64_t x1, uint64_t x2,
                       uint64_t amp, uint64_t fee, mdadd_fn md) {
    uint64_t dy, f;
    if (fee > FEE_DEN) return 0;
    dy = get_dy_nofee(i, j, dx, x0, x1, x2, amp, md);
    if (dy == 0) return 0;
    f = fee_of(dy, fee, md);
    if (dy < f) return 0;
    return dy - f;
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    uint64_t fee = 4000000ULL;
    uint64_t d_i, d_l, y_i, y_l, dy_i, dy_l;
    uint64_t q_i, q_l, r;
    int ov;
    q_i = muldiv_add_i128(100, 200, 0, 50);
    q_l = muldiv_add_limbs_q(100, 200, 0, 50);
    if (q_i != 400 || q_l != 400) return 1;
    muldiv_add_limbs(100, 200, 0, 50, &q_l, &r, &ov);
    if (r != 0 || ov != 0) return 1;
    d_i = get_d(e9, e9, e9, 100, muldiv_add_i128);
    d_l = get_d(e9, e9, e9, 100, muldiv_add_limbs_q);
    if (d_i != 3000000000ULL || d_i != d_l) return 1;
    y_i = get_y(0, 1, 1100000000ULL, e9, e9, e9, 100, muldiv_add_i128);
    y_l = get_y(0, 1, 1100000000ULL, e9, e9, e9, 100, muldiv_add_limbs_q);
    if (y_i != 900099889ULL || y_i != y_l) return 1;
    dy_i = get_dy_nofee(0, 1, 100000000ULL, e9, e9, e9, 100, muldiv_add_i128);
    dy_l = get_dy_nofee(0, 1, 100000000ULL, e9, e9, e9, 100, muldiv_add_limbs_q);
    if (dy_i != 99900110ULL || dy_i != dy_l) return 1;
    dy_i = get_dy(0, 1, 100000000ULL, e9, e9, e9, 100, fee, muldiv_add_i128);
    dy_l = get_dy(0, 1, 100000000ULL, e9, e9, e9, 100, fee, muldiv_add_limbs_q);
    if (dy_i != 99860150ULL || dy_i != dy_l) return 1;
    dy_i = get_dy(0, 1, 100000000ULL, e9, e9, e9, 2000, fee, muldiv_add_i128);
    dy_l = get_dy(0, 1, 100000000ULL, e9, e9, e9, 2000, fee, muldiv_add_limbs_q);
    if (dy_i != 99954955ULL || dy_i != dy_l) return 1;
    if (get_dy(0, 1, 0, e9, e9, e9, 100, fee, muldiv_add_i128) != 0) return 1;
    if (get_dy(0, 1, 100000000ULL, e9, e9, e9, 100, FEE_DEN + 1ULL, muldiv_add_i128) != 0) return 1;
    if (fee_of(99900110ULL, fee, muldiv_add_i128) != 39960ULL) return 1;
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
            "usage: curve_getdy_c11 selftest\n"
            "       curve_getdy_c11 getd X0 X1 X2 AMP [--limbs]\n"
            "       curve_getdy_c11 gety I J X X0 X1 X2 AMP [--limbs]\n"
            "       curve_getdy_c11 dy_nofee I J DX X0 X1 X2 AMP [--limbs]\n"
            "       curve_getdy_c11 dy I J DX X0 X1 X2 AMP FEE [--limbs]\n"
            "       curve_getdy_c11 fee_of DY FEE [--limbs]\n");
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
    if (strcmp(argv[1], "gety") == 0 && argc >= 9) {
        printf("%" PRIu64 "\n",
               get_y(atoi(argv[2]), atoi(argv[3]), strtoull(argv[4], NULL, 10),
                     strtoull(argv[5], NULL, 10), strtoull(argv[6], NULL, 10),
                     strtoull(argv[7], NULL, 10), strtoull(argv[8], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "dy_nofee") == 0 && argc >= 9) {
        printf("%" PRIu64 "\n",
               get_dy_nofee(atoi(argv[2]), atoi(argv[3]), strtoull(argv[4], NULL, 10),
                            strtoull(argv[5], NULL, 10), strtoull(argv[6], NULL, 10),
                            strtoull(argv[7], NULL, 10), strtoull(argv[8], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "dy") == 0 && argc >= 10) {
        printf("%" PRIu64 "\n",
               get_dy(atoi(argv[2]), atoi(argv[3]), strtoull(argv[4], NULL, 10),
                      strtoull(argv[5], NULL, 10), strtoull(argv[6], NULL, 10),
                      strtoull(argv[7], NULL, 10), strtoull(argv[8], NULL, 10),
                      strtoull(argv[9], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "fee_of") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               fee_of(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    usage();
    return 2;
}
