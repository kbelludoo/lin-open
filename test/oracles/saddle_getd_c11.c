/*
 * Independent C11 oracle for Saddle SwapUtils getD / getY (uint64 scale, N=2).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_saddle_getd.lin
 *
 * Newton getD / getY match saddle-finance/saddle-contract SwapUtils.sol
 * (MIT, commit 2cfdd05580efb626d79d597034b2cf5ae89b5626) for two coins.
 * A is Saddle precise A (display A * A_PRECISION, A_PRECISION=100).
 * Fail-closed (LIN profile, not Saddle revert): bad inputs / no converge -> 0.
 * dy is the fee-less Saddle quote xp_to - y - 1.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm license: MIT (Saddle). This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define A_PREC 100ULL
#define NCOIN 2ULL
#define MAX_LOOP 256

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d,
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

static uint64_t md_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static uint64_t md_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov = 0;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    (void)r;
    return ov ? 0 : q;
}

static int add_ok(uint64_t a, uint64_t b, uint64_t *out) {
    *out = a + b;
    return *out >= a;
}

static uint64_t get_d_md(uint64_t x0, uint64_t x1, uint64_t a,
                         uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t s, nA, d, dp, prev, t1, t2, left, t3, t4, den, den0, den1;
    unsigned i;

    if (x0 == 0 || x1 == 0) return 0;
    if (!add_ok(x0, x1, &s) || s == 0) return 0;
    nA = md(a, NCOIN, 1);
    if (nA == 0 || nA < A_PREC) return 0;
    d = s;
    for (i = 0; i < MAX_LOOP; i++) {
        den0 = md(x0, NCOIN, 1);
        den1 = md(x1, NCOIN, 1);
        if (den0 == 0 || den1 == 0) return 0;
        dp = md(d, d, den0);
        dp = md(dp, d, den1);
        prev = d;
        t1 = md(nA, s, A_PREC);
        t2 = md(dp, NCOIN, 1);
        if (!add_ok(t1, t2, &left)) return 0;
        t3 = md(nA - A_PREC, d, A_PREC);
        t4 = md(NCOIN + 1, dp, 1);
        if (!add_ok(t3, t4, &den) || den == 0) return 0;
        d = md(left, d, den);
        if ((d > prev ? d - prev : prev - d) <= 1) return d;
    }
    return 0;
}

static uint64_t get_y_md(uint64_t x0, uint64_t x1, uint64_t a, uint64_t x_new,
                         uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t d, nA, c, tmp, denn, denx, b, b_add, y, prev, yy, num, two_y, tb, den;
    unsigned i;

    d = get_d_md(x0, x1, a, md);
    if (d == 0 || x_new == 0) return 0;
    nA = md(NCOIN, a, 1);
    if (nA == 0) return 0;
    denx = md(x_new, NCOIN, 1);
    denn = md(nA, NCOIN, 1);
    if (denx == 0 || denn == 0) return 0;
    c = md(d, d, denx);
    tmp = md(c, A_PREC, 1);
    c = md(tmp, d, denn);
    b_add = md(d, A_PREC, nA);
    if (!add_ok(x_new, b_add, &b)) return 0;
    y = d;
    for (i = 0; i < MAX_LOOP; i++) {
        prev = y;
        yy = md(y, y, 1);
        if (!add_ok(yy, c, &num)) return 0;
        two_y = md(y, 2, 1);
        if (!add_ok(two_y, b, &tb) || tb < d) return 0;
        den = tb - d;
        if (den == 0) return 0;
        y = md(num, 1, den);
        if ((y > prev ? y - prev : prev - y) <= 1) return y;
    }
    return 0;
}

static uint64_t dy_md(uint64_t x0, uint64_t x1, uint64_t a, uint64_t dx,
                      uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t x_new, y, raw;
    if (dx == 0 || !add_ok(x0, dx, &x_new)) return 0;
    y = get_y_md(x0, x1, a, x_new, md);
    if (y == 0 || x1 < y) return 0;
    raw = x1 - y;
    if (raw < 1) return 0;
    return raw - 1;
}

static uint64_t cp_dy(uint64_t x0, uint64_t x1, uint64_t dx) {
    uint64_t ain, den;
    if (x0 == 0 || x1 == 0 || dx == 0) return 0;
    ain = md_i128(dx, 997, 1);
    den = md_i128(x0, 1000, 1);
    if (!add_ok(den, ain, &den) || den == 0) return 0;
    return md_i128(ain, x1, den);
}

static int selftest(void) {
    if (get_d_md(1000, 1000, 10000, md_i128) != 2000) return 1;
    if (get_d_md(1000, 1000, 10000, md_limbs) != 2000) return 2;
    if (get_d_md(1000, 2000, 10000, md_i128) != 2998) return 3;
    if (get_d_md(1000000, 1000000, 20000, md_i128) != 2000000) return 4;
    if (get_d_md(1000000, 1100000, 20000, md_i128) != 2099988) return 5;
    if (get_d_md(0, 0, 10000, md_i128) != 0) return 6;
    if (get_y_md(1000, 1000, 10000, 1000, md_i128) != 1000) return 7;
    if (get_y_md(1000, 1000, 10000, 1010, md_i128) != 990) return 8;
    if (dy_md(1000, 1000, 10000, 10, md_i128) != 9) return 9;
    if (dy_md(1000000, 1000000, 20000, 10000, md_i128) != 9999) return 10;
    if (cp_dy(1000000, 1000000, 10000) != 9871) return 11;
    if (get_d_md(100, 200, 10000, md_i128) != 299) return 12;
    if (get_d_md(1000, 2000, 10000, md_i128) != get_d_md(1000, 2000, 10000, md_limbs))
        return 13;
    if (dy_md(1000000, 1000000, 20000, 10000, md_limbs) != 9999) return 14;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    uint64_t x0, x1, a, extra, out;
    const char *mode;
    int limbs = 0;

    if (argc < 2) {
        fprintf(stderr, "usage: sgd selftest | getd x0 x1 a [--limbs] | gety x0 x1 a xnew [--limbs] | dy x0 x1 a dx [--limbs] | cpdy x0 x1 dx\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    mode = argv[1];
    if (strcmp(mode, "cpdy") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", cp_dy(strtoull(argv[2], NULL, 10),
                                      strtoull(argv[3], NULL, 10),
                                      strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (argc < 5) return 2;
    x0 = strtoull(argv[2], NULL, 10);
    x1 = strtoull(argv[3], NULL, 10);
    a = strtoull(argv[4], NULL, 10);
    extra = (argc >= 6 && strcmp(argv[5], "--limbs") != 0) ? strtoull(argv[5], NULL, 10) : 0;
    limbs = (argc >= 6 && strcmp(argv[argc - 1], "--limbs") == 0);
    if (strcmp(mode, "getd") == 0) {
        out = limbs ? get_d_md(x0, x1, a, md_limbs) : get_d_md(x0, x1, a, md_i128);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(mode, "gety") == 0 && argc >= 6) {
        out = limbs ? get_y_md(x0, x1, a, extra, md_limbs)
                    : get_y_md(x0, x1, a, extra, md_i128);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(mode, "dy") == 0 && argc >= 6) {
        out = limbs ? dy_md(x0, x1, a, extra, md_limbs)
                    : dy_md(x0, x1, a, extra, md_i128);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    return 2;
}
