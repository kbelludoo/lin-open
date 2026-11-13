/*
 * Independent C11 oracle for Curve tricrypto _newton_y / get_dy (uint64 scale).
 *
 * Two implementations of 128-bit products:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_curve_newton_y.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: published Curve crypto Newton solver (tricrypto-ng _newton_y).
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
#define PREC 1000000000ULL
#define AMUL 10000ULL
#define FEE_DEN 10000000000ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void umul_i128(uint64_t a, uint64_t b, uint64_t *hi, uint64_t *lo) {
    __uint128_t p = (__uint128_t)a * (__uint128_t)b;
    *hi = (uint64_t)(p >> 64);
    *lo = (uint64_t)p;
}

static uint64_t div128_i128(uint64_t hi, uint64_t lo, uint64_t d) {
    __uint128_t n;
    __uint128_t q;
    if (d == 0) return 0;
    n = ((__uint128_t)hi << 64) | (__uint128_t)lo;
    q = n / (__uint128_t)d;
    /* LIN values are signed i64; quotient with the high bit set fail-closes. */
    if (q > (uint64_t)INT64_MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > (uint64_t)INT64_MAX) return 0;
    return (uint64_t)q;
}

static void umul_limbs(uint64_t a, uint64_t b, uint64_t *hi_out, uint64_t *lo_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry;
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
    *hi_out = hi;
    *lo_out = lo;
}

static uint64_t div128_limbs(uint64_t hi, uint64_t lo, uint64_t d) {
    uint64_t r_hi, r_lo, q, new_hi, new_lo, bit, ge, need_borrow;
    int i, ov;
    if (d == 0) return 0;
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
    if (ov || (int64_t)q < 0) return 0;
    return q;
}

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t hi, lo;
    umul_limbs(a, b, &hi, &lo);
    return div128_limbs(hi, lo, d);
}

typedef uint64_t (*md_fn)(uint64_t, uint64_t, uint64_t);
typedef void (*umul_fn)(uint64_t, uint64_t, uint64_t *, uint64_t *);
typedef uint64_t (*div_fn)(uint64_t, uint64_t, uint64_t);

static int lt128(uint64_t h1, uint64_t l1, uint64_t h2, uint64_t l2) {
    if (h1 != h2) return h1 < h2;
    return l1 < l2;
}

static void add128(uint64_t h1, uint64_t l1, uint64_t h2, uint64_t l2,
                   uint64_t *ho, uint64_t *lo, int *ov) {
    uint64_t l, h, c;
    l = l1 + l2;
    c = (l < l1) ? 1 : 0;
    h = h1 + h2;
    if (h < h1) {
        *ov = 1;
        *ho = 0;
        *lo = 0;
        return;
    }
    h = h + c;
    if (c && h < c) {
        *ov = 1;
        *ho = 0;
        *lo = 0;
        return;
    }
    *ov = 0;
    *ho = h;
    *lo = l;
}

static void sub128(uint64_t h1, uint64_t l1, uint64_t h2, uint64_t l2,
                   uint64_t *ho, uint64_t *lo) {
    if (l1 < l2) {
        *lo = l1 - l2;
        *ho = h1 - h2 - 1;
        return;
    }
    *lo = l1 - l2;
    *ho = h1 - h2;
}

static uint64_t wide_fprime(uint64_t y, uint64_t S, uint64_t D, uint64_t mul1,
                            uint64_t mul2, int want, umul_fn um, div_fn dv) {
    uint64_t ph, pl, sh, sl, dh, dl, h1, l1, h2, l2, yh, yl, fp;
    uint64_t pdh, pdl, ah, al;
    int ov;
    if (y == 0) return 0;
    um(PREC, y, &ph, &pl);
    um(S, mul2, &sh, &sl);
    um(D, mul2, &dh, &dl);
    add128(ph, pl, sh, sl, &h1, &l1, &ov);
    if (ov) return 0;
    add128(h1, l1, 0, mul1, &h2, &l2, &ov);
    if (ov) return 0;
    if (lt128(h2, l2, dh, dl)) return (want == 1) ? 1 : 0;
    if (want == 1) return 0;
    sub128(h2, l2, dh, dl, &yh, &yl);
    fp = dv(yh, yl, y);
    if (want == 0) return fp;
    um(PREC, D, &pdh, &pdl);
    add128(yh, yl, pdh, pdl, &ah, &al, &ov);
    if (ov) return 0;
    return dv(ah, al, fp);
}

static uint64_t newton_y(uint64_t ann, uint64_t gamma, uint64_t x0, uint64_t x1,
                         uint64_t x2, uint64_t D, int i, md_fn md, umul_fn um,
                         div_fn dv) {
    uint64_t z0, z1, z2, hi, mid, lo, y, K0_i, S_i, q, conv, y_prev, K0, S;
    uint64_t orig, g1, t, mul1, mul2, t2, fp, y_minus, yp1, extra, extra2;
    uint64_t y_plus, diff, lim, outy;
    int iter, done;

    if (i < 0 || i > 2 || D == 0 || ann == 0 || gamma == 0) return 0;
    if (x0 == 0 || x1 == 0 || x2 == 0) return 0;
    z0 = x0;
    z1 = x1;
    z2 = x2;
    if (i == 0) z0 = 0;
    if (i == 1) z1 = 0;
    if (i == 2) z2 = 0;
    hi = z0;
    if (z1 > hi) hi = z1;
    if (z2 > hi) hi = z2;
    lo = z0;
    if (z1 < lo) lo = z1;
    if (z2 < lo) lo = z2;
    if (z0 > UINT64_MAX - z1) return 0;
    mid = z0 + z1;
    if (mid > UINT64_MAX - z2) return 0;
    mid = mid + z2;
    mid = (mid - hi) - lo;
    y = md(D, 1, NCOINS);
    if (y == 0) return 0;
    K0_i = PREC;
    S_i = 0;
    q = md(y, D, mid * (uint64_t)NCOINS);
    if (q == 0) return 0;
    y = q;
    S_i = S_i + mid;
    q = md(y, D, hi * (uint64_t)NCOINS);
    if (q == 0) return 0;
    y = q;
    if (S_i > UINT64_MAX - hi) return 0;
    S_i = S_i + hi;
    K0_i = md(K0_i, hi * (uint64_t)NCOINS, D);
    K0_i = md(K0_i, mid * (uint64_t)NCOINS, D);
    conv = hi / 100000ULL;
    if (D / 100000ULL > conv) conv = D / 100000ULL;
    if (conv < 100) conv = 100;
    outy = 0;
    done = 0;
    for (iter = 0; iter < NEWTON; iter++) {
        if (done) continue;
        y_prev = y;
        K0 = md(K0_i, y * (uint64_t)NCOINS, D);
        if (K0 == 0) {
            done = 1;
            continue;
        }
        if (S_i > UINT64_MAX - y) {
            done = 1;
            continue;
        }
        S = S_i + y;
        orig = gamma + PREC;
        if (orig < K0)
            g1 = (K0 - orig) + 1;
        else
            g1 = (orig - K0) + 1;
        t = md(PREC, D, gamma);
        t = md(t, g1, gamma);
        t = md(t, AMUL, ann);
        t = md(t, g1, 1);
        if (t == 0) {
            done = 1;
            continue;
        }
        mul1 = t;
        t2 = md(PREC + PREC, K0, g1);
        if (PREC > UINT64_MAX - t2) {
            done = 1;
            continue;
        }
        mul2 = PREC + t2;
        if (wide_fprime(y, S, D, mul1, mul2, 1, um, dv) == 1) {
            y = y_prev / 2;
            continue;
        }
        fp = wide_fprime(y, S, D, mul1, mul2, 0, um, dv);
        if (fp == 0) {
            done = 1;
            continue;
        }
        y_minus = md(mul1, 1, fp);
        yp1 = wide_fprime(y, S, D, mul1, mul2, 2, um, dv);
        extra = md(y_minus, PREC, K0);
        if (yp1 > UINT64_MAX - extra) {
            done = 1;
            continue;
        }
        y_plus = yp1 + extra;
        extra2 = md(PREC, S, fp);
        if (y_minus > UINT64_MAX - extra2) {
            done = 1;
            continue;
        }
        y_minus = y_minus + extra2;
        if (y_plus < y_minus)
            y = y_prev / 2;
        else
            y = y_plus - y_minus;
        diff = (y >= y_prev) ? (y - y_prev) : (y_prev - y);
        lim = y / 100000ULL;
        if (conv > lim) lim = conv;
        if (diff < lim) {
            outy = y;
            done = 1;
        }
    }
    return outy;
}

static uint64_t pick(int i, uint64_t x0, uint64_t x1, uint64_t x2) {
    if (i == 0) return x0;
    if (i == 1) return x1;
    if (i == 2) return x2;
    return 0;
}

static uint64_t get_dy(uint64_t ann, uint64_t gamma, uint64_t x0, uint64_t x1,
                       uint64_t x2, uint64_t D, int i, int j, uint64_t dx,
                       uint64_t fee, md_fn md, umul_fn um, div_fn dv) {
    uint64_t xi, x, nx0, nx1, nx2, y, xj, raw;
    if (dx == 0 || i == j || i < 0 || j < 0 || i > 2 || j > 2) return 0;
    if (fee > FEE_DEN) return 0;
    xi = pick(i, x0, x1, x2);
    if (xi > UINT64_MAX - dx) return 0;
    x = xi + dx;
    nx0 = x0;
    nx1 = x1;
    nx2 = x2;
    if (i == 0) nx0 = x;
    if (i == 1) nx1 = x;
    if (i == 2) nx2 = x;
    y = newton_y(ann, gamma, nx0, nx1, nx2, D, j, md, um, dv);
    if (y == 0) return 0;
    xj = pick(j, nx0, nx1, nx2);
    if (xj < y) return 0;
    raw = xj - y;
    if (raw == 0) return 0;
    raw = raw - 1;
    if (fee == 0) return raw;
    return md(raw, FEE_DEN - fee, FEE_DEN);
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    uint64_t D = 3000000000ULL;
    uint64_t ann = 1707629ULL;
    uint64_t g = 11809ULL;
    uint64_t yi, yl, dyi, dyl, q;
    q = muldiv_i128(100, 200, 50);
    if (q != 400 || muldiv_limbs(100, 200, 50) != 400) return 1;
    yi = newton_y(ann, g, e9, e9, e9, D, 1, muldiv_i128, umul_i128, div128_i128);
    yl = newton_y(ann, g, e9, e9, e9, D, 1, muldiv_limbs, umul_limbs, div128_limbs);
    if (yi != e9 || yi != yl) return 1;
    yi = newton_y(ann, g, 1100000000ULL, e9, e9, D, 1, muldiv_i128, umul_i128,
                  div128_i128);
    yl = newton_y(ann, g, 1100000000ULL, e9, e9, D, 1, muldiv_limbs, umul_limbs,
                  div128_limbs);
    if (yi != 909085543ULL || yi != yl) return 1;
    dyi = get_dy(ann, g, e9, e9, e9, D, 0, 1, 100000000ULL, 0, muldiv_i128,
                 umul_i128, div128_i128);
    dyl = get_dy(ann, g, e9, e9, e9, D, 0, 1, 100000000ULL, 0, muldiv_limbs,
                 umul_limbs, div128_limbs);
    if (dyi != 90914456ULL || dyi != dyl) return 1;
    dyi = get_dy(ann, g, e9, e9, e9, D, 0, 1, 100000000ULL, 3000000ULL,
                 muldiv_i128, umul_i128, div128_i128);
    if (dyi != 90887181ULL) return 1;
    if (get_dy(ann, g, e9, e9, e9, D, 0, 1, 0, 0, muldiv_i128, umul_i128,
               div128_i128) != 0)
        return 1;
    dyi = get_dy(2700ULL, g, e9, e9, e9, D, 0, 1, 100000000ULL, 0, muldiv_i128,
                 umul_i128, div128_i128);
    dyl = get_dy(2700ULL, g, e9, e9, e9, D, 0, 1, 100000000ULL, 0, muldiv_limbs,
                 umul_limbs, div128_limbs);
    /* MIN_A=2700 makes mul1 exceed signed i64; fail-closed 0, not wrap. */
    if (dyi != 0 || dyl != 0) return 1;
    yi = newton_y(ann, g, 1200000000ULL, 900000000ULL, e9, D, 1, muldiv_i128,
                  umul_i128, div128_i128);
    if (yi != 833328413ULL) return 1;
    if (newton_y(ann, 0, e9, e9, e9, D, 1, muldiv_i128, umul_i128, div128_i128) !=
        0)
        return 1;
    printf("PASS\n");
    return 0;
}

static int use_limbs(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    md_fn md;
    umul_fn um;
    div_fn dv;
    int limbs;
    if (argc < 2) {
        fprintf(stderr, "usage: curve_newton_y_c11 selftest|ny|dy|muldiv ... [--limbs]\n");
        return 2;
    }
    limbs = use_limbs(argc, argv);
    md = limbs ? muldiv_limbs : muldiv_i128;
    um = limbs ? umul_limbs : umul_i128;
    dv = limbs ? div128_limbs : div128_i128;
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "ny") == 0 && argc >= 9) {
        printf("%" PRIu64 "\n",
               newton_y(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                        strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                        atoi(argv[8]), md, um, dv));
        return 0;
    }
    if (strcmp(argv[1], "dy") == 0 && argc >= 12) {
        printf("%" PRIu64 "\n",
               get_dy(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                      strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                      strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                      atoi(argv[8]), atoi(argv[9]), strtoull(argv[10], NULL, 10),
                      strtoull(argv[11], NULL, 10), md, um, dv));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
