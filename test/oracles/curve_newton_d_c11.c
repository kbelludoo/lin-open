/*
 * Independent C11 oracle for Curve tricrypto newton_D (uint64 scale).
 *
 * Two implementations of 128-bit products:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_curve_newton_d.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: published Curve crypto Newton D-solver (tricrypto-ng newton_D).
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

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void umul_i128(uint64_t a, uint64_t b, uint64_t *hi, uint64_t *lo) {
    __uint128_t p = (__uint128_t)a * (__uint128_t)b;
    *hi = (uint64_t)(p >> 64);
    *lo = (uint64_t)p;
}

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > (uint64_t)INT64_MAX) return 0;
    return (uint64_t)q;
}

static void umul_limbs(uint64_t a, uint64_t b, uint64_t *hi_out, uint64_t *lo_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi, mid_carry, lo_carry;
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

static int lt128(uint64_t h1, uint64_t l1, uint64_t h2, uint64_t l2) {
    if (h1 != h2) return h1 < h2;
    return l1 < l2;
}

static uint64_t icbrt128(uint64_t hi, uint64_t lo, umul_fn um) {
    uint64_t l, h, mid, sh, sl, ch, cl;
    l = 0;
    h = 1ULL << 32;
    if (hi == 0 && lo < h) h = lo;
    while (l < h) {
        mid = l + ((h - l + 1) >> 1);
        um(mid, mid, &sh, &sl);
        if (sh != 0) {
            h = mid - 1;
            continue;
        }
        um(sl, mid, &ch, &cl);
        if (lt128(hi, lo, ch, cl))
            h = mid - 1;
        else
            l = mid;
    }
    return l;
}

static uint64_t newton_d(uint64_t ann, uint64_t gamma, uint64_t x0, uint64_t x1,
                         uint64_t x2, uint64_t k0_prev, md_fn md, umul_fn um) {
    uint64_t h, m, l, t, S, D, D_prev, K0, orig, g1, mul1, mul2;
    uint64_t t1, t2, t3, t4, lhs, neg, D_plus, D_minus, extra, diff, lim;
    uint64_t ph, pl, gm;
    int iter, done, outd;

    if (ann == 0 || gamma == 0 || k0_prev != 0) return 0;
    if (x0 == 0 || x1 == 0 || x2 == 0) return 0;
    h = x0;
    m = x1;
    l = x2;
    if (h < m) {
        t = h;
        h = m;
        m = t;
    }
    if (h < l) {
        t = h;
        h = l;
        l = t;
    }
    if (m < l) {
        t = m;
        m = l;
        l = t;
    }
    if (h > UINT64_MAX - m) return 0;
    S = h + m;
    if (S > UINT64_MAX - l) return 0;
    S = S + l;
    um(h, m, &ph, &pl);
    if (ph != 0) return 0;
    um(pl, l, &ph, &pl);
    gm = icbrt128(ph, pl, um);
    D = (uint64_t)NCOINS * gm;
    if (D == 0 || D > (uint64_t)INT64_MAX) return 0;
    outd = 0;
    done = 0;
    for (iter = 0; iter < NEWTON; iter++) {
        if (done) continue;
        D_prev = D;
        K0 = md(PREC, h * (uint64_t)NCOINS, D);
        K0 = md(K0, m * (uint64_t)NCOINS, D);
        K0 = md(K0, l * (uint64_t)NCOINS, D);
        if (K0 == 0) {
            done = 1;
            continue;
        }
        orig = gamma + PREC;
        g1 = (orig > K0) ? (orig - K0 + 1) : (K0 - orig + 1);
        t = md(PREC, D, gamma);
        t = md(t, g1, gamma);
        t = md(t, g1, 1);
        mul1 = md(t, AMUL, ann);
        if (mul1 == 0) {
            done = 1;
            continue;
        }
        mul2 = md(2ULL * PREC * (uint64_t)NCOINS, K0, g1);
        t1 = S;
        t2 = md(S, mul2, PREC);
        t3 = md(mul1, (uint64_t)NCOINS, K0);
        t4 = md(mul2, D, PREC);
        if (t1 > UINT64_MAX - t2) {
            done = 1;
            continue;
        }
        lhs = t1 + t2;
        if (lhs > UINT64_MAX - t3) {
            done = 1;
            continue;
        }
        lhs = lhs + t3;
        if (lhs < t4) {
            D = D_prev / 2;
            continue;
        }
        neg = lhs - t4;
        if (neg == 0) {
            done = 1;
            continue;
        }
        if (neg > UINT64_MAX - S) {
            done = 1;
            continue;
        }
        D_plus = md(D, neg + S, neg);
        D_minus = md(D, D, neg);
        if (PREC > K0) {
            extra = md(md(D, mul1 / neg, PREC), PREC - K0, K0);
            if (D_minus > UINT64_MAX - extra) {
                done = 1;
                continue;
            }
            D_minus = D_minus + extra;
        } else {
            extra = md(md(D, mul1 / neg, PREC), K0 - PREC, K0);
            if (D_minus < extra) {
                D = D_prev / 2;
                continue;
            }
            D_minus = D_minus - extra;
        }
        if (D_plus > D_minus)
            D = D_plus - D_minus;
        else
            D = (D_minus - D_plus) / 2;
        diff = (D >= D_prev) ? (D - D_prev) : (D_prev - D);
        lim = D / 100000ULL;
        if (lim < 100) lim = 100;
        if (diff < lim) {
            outd = 1;
            done = 1;
        }
    }
    return outd ? D : 0;
}

static uint64_t get_vp(uint64_t ann, uint64_t gamma, uint64_t x0, uint64_t x1,
                       uint64_t x2, md_fn md, umul_fn um) {
    uint64_t D, S;
    D = newton_d(ann, gamma, x0, x1, x2, 0, md, um);
    if (D == 0) return 0;
    if (x0 > UINT64_MAX - x1) return 0;
    S = x0 + x1;
    if (S > UINT64_MAX - x2) return 0;
    S = S + x2;
    if (S == 0) return 0;
    return md(D, PREC, S);
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    uint64_t ann = 1707629ULL;
    uint64_t g = 11809ULL;
    uint64_t di, dl, vi, vl, q, c;
    uint64_t hi, lo;
    q = muldiv_i128(100, 200, 50);
    if (q != 400 || muldiv_limbs(100, 200, 50) != 400) return 1;
    umul_i128(e9, e9, &hi, &lo);
    umul_i128(lo, e9, &hi, &lo);
    c = icbrt128(hi, lo, umul_i128);
    if (c != e9) return 1;
    di = newton_d(ann, g, e9, e9, e9, 0, muldiv_i128, umul_i128);
    dl = newton_d(ann, g, e9, e9, e9, 0, muldiv_limbs, umul_limbs);
    if (di != 3000000000ULL || di != dl) return 1;
    di = newton_d(ann, g, 1100000000ULL, e9, e9, 0, muldiv_i128, umul_i128);
    dl = newton_d(ann, g, 1100000000ULL, e9, e9, 0, muldiv_limbs, umul_limbs);
    if (di != 3096846429ULL || di != dl) return 1;
    vi = get_vp(ann, g, 1100000000ULL, e9, e9, muldiv_i128, umul_i128);
    vl = get_vp(ann, g, 1100000000ULL, e9, e9, muldiv_limbs, umul_limbs);
    if (vi != 998982719ULL || vi != vl) return 1;
    di = newton_d(ann, g, 1200000000ULL, 900000000ULL, e9, 0, muldiv_i128,
                  umul_i128);
    if (di != 3077962761ULL) return 1;
    if (newton_d(ann, 0, e9, e9, e9, 0, muldiv_i128, umul_i128) != 0) return 1;
    if (newton_d(2700ULL, g, e9, e9, e9, 0, muldiv_i128, umul_i128) != 0)
        return 1;
    if (newton_d(ann, g, e9, e9, e9, 1, muldiv_i128, umul_i128) != 0) return 1;
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
    int limbs;
    if (argc < 2) {
        fprintf(stderr, "usage: curve_newton_d_c11 selftest|nd|vp|muldiv|cbrt ... [--limbs]\n");
        return 2;
    }
    limbs = use_limbs(argc, argv);
    md = limbs ? muldiv_limbs : muldiv_i128;
    um = limbs ? umul_limbs : umul_i128;
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "cbrt") == 0 && argc >= 5) {
        uint64_t hi, lo;
        um(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), &hi, &lo);
        if (hi != 0) {
            printf("0\n");
            return 0;
        }
        um(lo, strtoull(argv[4], NULL, 10), &hi, &lo);
        printf("%" PRIu64 "\n", icbrt128(hi, lo, um));
        return 0;
    }
    if (strcmp(argv[1], "nd") == 0 && argc >= 8) {
        printf("%" PRIu64 "\n",
               newton_d(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                        strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                        md, um));
        return 0;
    }
    if (strcmp(argv[1], "vp") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               get_vp(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                      strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                      strtoull(argv[6], NULL, 10), md, um));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
