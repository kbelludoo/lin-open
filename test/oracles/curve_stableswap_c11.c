/*
 * Independent C11 oracle for Curve StableSwap 3-coin get_D / get_y / get_dy
 * (uint64 scale, 128-bit product).
 *
 * Two implementations of (a*b + addend)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_curve_stableswap.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: published StableSwap invariant (Egorov 2019) as used by
 * curvefi/curve-contract contracts/pools/3pool/StableSwap3Pool.vy get_D/get_y.
 * Original LIN + C11 code; the Vyper source is not vendored (upstream LICENSE
 * grants no redistribution right).
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define N_COINS 3u
#define FEE_DEN 10000000000ULL

static uint64_t muladd_i128(uint64_t a, uint64_t b, uint64_t addend, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b + (__uint128_t)addend) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    return muladd_i128(a, b, 0, d);
}

static uint64_t muladd_rem_i128(uint64_t a, uint64_t b, uint64_t addend, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)a * (__uint128_t)b + (__uint128_t)addend) % (__uint128_t)d);
}

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muladd_limbs_qr(uint64_t a, uint64_t b, uint64_t addend, uint64_t d,
                            uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, add_carry, r_hi, r_lo, q, new_hi, new_lo;
    uint64_t bit, ge, need_borrow, t2;
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
    t2 = lo + addend;
    add_carry = (t2 < lo) ? 1 : 0;
    if (add_carry) {
        if (hi == UINT64_MAX) {
            *q_out = 0;
            *r_out = 0;
            *ov_out = 1;
            return;
        }
        hi = hi + 1;
    }
    lo = t2;

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
    *q_out = ov ? 0 : q;
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t muladd_limbs(uint64_t a, uint64_t b, uint64_t addend, uint64_t d) {
    uint64_t q, r;
    int ov;
    muladd_limbs_qr(a, b, addend, d, &q, &r, &ov);
    return q;
}

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d) {
    return muladd_limbs(a, b, 0, d);
}

typedef uint64_t (*muladd_fn)(uint64_t, uint64_t, uint64_t, uint64_t);

static int umul_ok(uint64_t a, uint64_t b) {
    if (a == 0 || b == 0) return 1;
    return b <= UINT64_MAX / a;
}

static uint64_t get_d(uint64_t x0, uint64_t x1, uint64_t x2, uint64_t amp, muladd_fn md) {
    uint64_t S, Ann, D, D_P, Dprev, t, u, num, left, right, den, diff, xn0, xn1, xn2;
    unsigned i;

    if (x0 < 1 || x1 < 1 || x2 < 1 || amp < 1) return 0;
    if (!umul_ok(x0, 1) || x0 > UINT64_MAX - x1) return 0;
    S = x0 + x1;
    if (S > UINT64_MAX - x2) return 0;
    S = S + x2;
    if (S == 0) return 0;
    Ann = md(amp, N_COINS, 0, 1);
    if (Ann == 0) return 0;
    D = S;
    for (i = 0; i < 255; i++) {
        D_P = D;
        xn0 = md(x0, N_COINS, 0, 1);
        xn1 = md(x1, N_COINS, 0, 1);
        xn2 = md(x2, N_COINS, 0, 1);
        if (xn0 == 0 || xn1 == 0 || xn2 == 0) return 0;
        D_P = md(D_P, D, 0, xn0);
        D_P = md(D_P, D, 0, xn1);
        D_P = md(D_P, D, 0, xn2);
        Dprev = D;
        t = md(Ann, S, 0, 1);
        u = md(D_P, N_COINS, 0, 1);
        if (t > UINT64_MAX - u) return 0;
        num = t + u;
        left = md(Ann - 1, D, 0, 1);
        right = md(N_COINS + 1, D_P, 0, 1);
        if (left > UINT64_MAX - right) return 0;
        den = left + right;
        if (den == 0) return 0;
        D = md(num, D, 0, den);
        diff = (D < Dprev) ? (Dprev - D) : (D - Dprev);
        if (diff <= 1) break;
    }
    return D;
}

static uint64_t xp_at(unsigned k, uint64_t x0, uint64_t x1, uint64_t x2) {
    if (k == 0) return x0;
    if (k == 1) return x1;
    if (k == 2) return x2;
    return 0;
}

static uint64_t get_y(unsigned i, unsigned j, uint64_t x,
                      uint64_t x0, uint64_t x1, uint64_t x2, uint64_t amp,
                      muladd_fn md) {
    uint64_t D, Ann, c, S_, _x, xn, ann_n, d_ann, b, y, y_prev, two_y, tb, den, diff;
    unsigned k, it;

    if (i == j || i > 2 || j > 2 || x < 1) return 0;
    D = get_d(x0, x1, x2, amp, md);
    if (D == 0) return 0;
    Ann = md(amp, N_COINS, 0, 1);
    if (Ann == 0) return 0;
    c = D;
    S_ = 0;
    for (k = 0; k < 3; k++) {
        if (k == j) continue;
        _x = (k == i) ? x : xp_at(k, x0, x1, x2);
        if (_x < 1) return 0;
        if (S_ > UINT64_MAX - _x) return 0;
        S_ += _x;
        xn = md(_x, N_COINS, 0, 1);
        if (xn == 0) return 0;
        c = md(c, D, 0, xn);
    }
    ann_n = md(Ann, N_COINS, 0, 1);
    if (ann_n == 0) return 0;
    c = md(c, D, 0, ann_n);
    d_ann = md(D, 1, 0, Ann);
    if (S_ > UINT64_MAX - d_ann) return 0;
    b = S_ + d_ann;
    y = D;
    for (it = 0; it < 255; it++) {
        y_prev = y;
        two_y = md(2, y, 0, 1);
        if (two_y > UINT64_MAX - b) return 0;
        tb = two_y + b;
        if (tb < D) return 0;
        den = tb - D;
        if (den == 0) return 0;
        y = md(y, y, c, den);
        diff = (y < y_prev) ? (y_prev - y) : (y - y_prev);
        if (diff <= 1) break;
    }
    return y;
}

static uint64_t get_dy(unsigned i, unsigned j, uint64_t dx,
                       uint64_t x0, uint64_t x1, uint64_t x2, uint64_t amp,
                       uint64_t fee, muladd_fn md) {
    uint64_t xp_i, xp_j, x, y, y1, dy, fee_amt;
    if (dx < 1 || i > 2 || j > 2) return 0;
    xp_i = xp_at(i, x0, x1, x2);
    xp_j = xp_at(j, x0, x1, x2);
    if (xp_i > UINT64_MAX - dx) return 0;
    x = xp_i + dx;
    y = get_y(i, j, x, x0, x1, x2, amp, md);
    if (y == 0) return 0;
    if (y == UINT64_MAX) return 0;
    y1 = y + 1;
    if (xp_j < y1) return 0;
    dy = xp_j - y1;
    fee_amt = md(dy, fee, 0, FEE_DEN);
    if (dy < fee_amt) return 0;
    return dy - fee_amt;
}

static int selftest(void) {
    int fail = 0;
    uint64_t d_i, d_l, y_i, y_l, dy_i, dy_l, q_i, q_l, r_i, r_l;
    uint64_t a, b, add, den;

    a = 7; b = 9; add = 1; den = 2;
    q_i = muladd_i128(a, b, add, den);
    q_l = muladd_limbs(a, b, add, den);
    if (q_i != 32 || q_i != q_l) fail++;
    r_i = muladd_rem_i128(7, 9, 0, 2);
    {
        uint64_t qq, rr;
        int ov;
        muladd_limbs_qr(7, 9, 0, 2, &qq, &rr, &ov);
        r_l = rr;
    }
    if (r_i != 1 || r_i != r_l) fail++;

    d_i = get_d(1000000ULL, 1000000ULL, 1000000ULL, 100ULL, muladd_i128);
    d_l = get_d(1000000ULL, 1000000ULL, 1000000ULL, 100ULL, muladd_limbs);
    if (d_i != 3000000ULL || d_i != d_l) fail++;

    d_i = get_d(10000000000ULL, 10000000000ULL, 10000000000ULL, 2000ULL, muladd_i128);
    d_l = get_d(10000000000ULL, 10000000000ULL, 10000000000ULL, 2000ULL, muladd_limbs);
    if (d_i != 30000000000ULL || d_i != d_l) fail++;

    d_i = get_d(10000000000ULL, 9000000000ULL, 11000000000ULL, 2000ULL, muladd_i128);
    d_l = get_d(10000000000ULL, 9000000000ULL, 11000000000ULL, 2000ULL, muladd_limbs);
    if (d_i != 29999949520ULL || d_i != d_l) fail++;

    if (get_d(0, 1000000ULL, 1000000ULL, 100ULL, muladd_i128) != 0) fail++;

    y_i = get_y(0, 1, 10000000000ULL + 10000000ULL,
                10000000000ULL, 10000000000ULL, 10000000000ULL, 2000ULL, muladd_i128);
    y_l = get_y(0, 1, 10000000000ULL + 10000000ULL,
                10000000000ULL, 10000000000ULL, 10000000000ULL, 2000ULL, muladd_limbs);
    if (y_i != 9990000004ULL || y_i != y_l) fail++;

    dy_i = get_dy(0, 1, 10000000ULL,
                  10000000000ULL, 10000000000ULL, 10000000000ULL,
                  2000ULL, 4000000ULL, muladd_i128);
    dy_l = get_dy(0, 1, 10000000ULL,
                  10000000000ULL, 10000000000ULL, 10000000000ULL,
                  2000ULL, 4000000ULL, muladd_limbs);
    if (dy_i != 9995996ULL || dy_i != dy_l) fail++;

    if (muldiv_i128(10000000000ULL, 10000000000ULL, 10000000000ULL) != 10000000000ULL) fail++;
    if (muldiv_limbs(10000000000ULL, 10000000000ULL, 10000000000ULL) != 10000000000ULL) fail++;
    if (muldiv_i128(10000000000ULL, 10000000000ULL, 1) != 0) fail++; /* 1e20 does not fit u64 */

    if (fail) {
        fprintf(stderr, "curve_stableswap_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("curve_stableswap_c11 selftest PASS\n");
    printf("vector.d_bal_1e6=%" PRIu64 "\n", get_d(1000000ULL, 1000000ULL, 1000000ULL, 100ULL, muladd_i128));
    printf("vector.d_bal_1e10=%" PRIu64 "\n",
           get_d(10000000000ULL, 10000000000ULL, 10000000000ULL, 2000ULL, muladd_i128));
    printf("vector.d_imbal=%" PRIu64 "\n",
           get_d(10000000000ULL, 9000000000ULL, 11000000000ULL, 2000ULL, muladd_i128));
    printf("vector.dy_1e9=%" PRIu64 "\n", dy_i);
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    muladd_fn md = muladd_i128;
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest | get_d x0 x1 x2 amp | get_y i j x x0 x1 x2 amp | get_dy i j dx x0 x1 x2 amp fee | muldiv a b d | muladd a b c d\n",
                argv[0]);
        return 2;
    }
    cmd = argv[1];
    if (argc >= 3 && strcmp(argv[argc - 1], "--limbs") == 0) {
        md = muladd_limbs;
        argc--;
    }
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "muldiv") == 0 && argc == 5) {
        printf("%" PRIu64 "\n", md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), 0, strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "muladd") == 0 && argc == 6) {
        printf("%" PRIu64 "\n", md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                   strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "get_d") == 0 && argc == 6) {
        printf("%" PRIu64 "\n", get_d(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                      strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "get_y") == 0 && argc == 9) {
        printf("%" PRIu64 "\n", get_y((unsigned)strtoul(argv[2], NULL, 10), (unsigned)strtoul(argv[3], NULL, 10),
                                      strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                                      strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                                      strtoull(argv[8], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "get_dy") == 0 && argc == 10) {
        printf("%" PRIu64 "\n", get_dy((unsigned)strtoul(argv[2], NULL, 10), (unsigned)strtoul(argv[3], NULL, 10),
                                       strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                                       strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                                       strtoull(argv[8], NULL, 10), strtoull(argv[9], NULL, 10), md));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
