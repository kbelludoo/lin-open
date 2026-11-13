/*
 * Independent C11 oracle for Velodrome/Aerodrome Pool.getAmountOut
 * (uint64-scale, SCALE=1e9).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_velo_getout.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: velodrome-finance/contracts contracts/Pool.sol
 * (GPL-3.0-or-later). Solidity is hash-pinned only and is not vendored.
 * This oracle is original C11 of the uint64-scale formulas.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SCALE 1000000000ULL
#define FEE_DEN 10000ULL

typedef uint64_t (*md_fn)(uint64_t, uint64_t, uint64_t);

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > (uint64_t)INT64_MAX) return 0;
    return (uint64_t)q;
}

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge, need_borrow;
    int i, ov;

    if (d == 0) return 0;
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
    if (ov) return 0;
    if ((int64_t)q < 0) return 0;
    return q;
}

static uint64_t vgo_f(uint64_t x0, uint64_t y, md_fn md) {
    uint64_t a, xx, yy, b;
    if (x0 == 0 || y == 0) return 0;
    a = md(x0, y, SCALE);
    xx = md(x0, x0, SCALE);
    yy = md(y, y, SCALE);
    if (xx > UINT64_MAX - yy) return 0;
    b = xx + yy;
    return md(a, b, SCALE);
}

static uint64_t vgo_d(uint64_t x0, uint64_t y, md_fn md) {
    uint64_t yy, t1, xx, t2, s;
    if (x0 == 0 || y == 0) return 0;
    yy = md(y, y, SCALE);
    t1 = md(md(3, x0, 1), yy, SCALE);
    xx = md(x0, x0, SCALE);
    t2 = md(xx, x0, SCALE);
    if (t1 > UINT64_MAX - t2) return 0;
    s = t1 + t2;
    return s;
}

static uint64_t vgo_get_y(uint64_t x0, uint64_t xy, uint64_t y, md_fn md) {
    int iter;
    if (x0 == 0 || xy == 0 || y == 0) return 0;
    for (iter = 0; iter < 255; iter++) {
        uint64_t k = vgo_f(x0, y, md);
        uint64_t den = vgo_d(x0, y, md);
        uint64_t dy, yp, ny;
        if (den == 0) return 0;
        if (k < xy) {
            dy = md(xy - k, SCALE, den);
            if (dy == 0) {
                if (k == xy) return y;
                if (y == UINT64_MAX) return 0;
                yp = y + 1;
                if (vgo_f(x0, yp, md) > xy) return yp;
                dy = 1;
            }
            if (y > UINT64_MAX - dy) return 0;
            ny = y + dy;
            y = ny;
        } else {
            dy = md(k - xy, SCALE, den);
            if (dy == 0) {
                if (k == xy || (y > 0 && vgo_f(x0, y - 1, md) < xy)) return y;
                dy = 1;
            }
            if (y <= dy) return 0;
            y = y - dy;
        }
    }
    return 0;
}

static uint64_t vgo_get_amount_out(uint64_t amount_in, uint64_t ra, uint64_t rb,
                                   uint64_t stable, uint64_t fee, md_fn md) {
    uint64_t net, den, xy, x0, y;
    if (amount_in == 0 || ra == 0 || rb == 0) return 0;
    if (fee > FEE_DEN) return 0;
    net = amount_in - md(amount_in, fee, FEE_DEN);
    if (net == 0 || net > amount_in) return 0;
    if (stable == 0) {
        if (ra > UINT64_MAX - net) return 0;
        den = ra + net;
        return md(net, rb, den);
    }
    xy = vgo_f(ra, rb, md);
    if (xy == 0) return 0;
    if (ra > UINT64_MAX - net) return 0;
    x0 = ra + net;
    y = vgo_get_y(x0, xy, rb, md);
    if (y == 0 || rb <= y) return 0;
    return rb - y;
}

static int selftest(void) {
    int fail = 0;
    uint64_t e9 = SCALE;
    struct {
        uint64_t a, b, d;
    } mdv[] = {
        {100, 200, 50},
        {7, 9, 1},
        {e9, e9, e9},
        {4000000000ULL, 4000000000ULL, 1},
        {0, 100, 5},
    };
    size_t i;
    uint64_t named[][2] = {
        /* kind packed later; check named goldens via both oracles */
    };
    (void)named;

    for (i = 0; i < sizeof(mdv) / sizeof(mdv[0]); i++) {
        uint64_t x = muldiv_i128(mdv[i].a, mdv[i].b, mdv[i].d);
        uint64_t y = muldiv_limbs(mdv[i].a, mdv[i].b, mdv[i].d);
        if (x != y) {
            fprintf(stderr, "muldiv mismatch i=%zu i128=%" PRIu64 " limbs=%" PRIu64 "\n", i, x, y);
            fail++;
        }
    }
    if (muldiv_i128(100, 200, 50) != 400) fail++;
    if (vgo_f(e9, e9, muldiv_i128) != 2000000000ULL) fail++;
    if (vgo_f(e9, e9, muldiv_i128) != vgo_f(e9, e9, muldiv_limbs)) fail++;
    if (vgo_get_y(e9, 2000000000ULL, e9, muldiv_i128) != e9) fail++;
    if (vgo_get_y(e9, 2000000000ULL, e9, muldiv_limbs) != e9) fail++;
    if (vgo_get_amount_out(100000000ULL, e9, e9, 0, 0, muldiv_i128) != 90909090ULL) fail++;
    if (vgo_get_amount_out(100000000ULL, e9, e9, 0, 5, muldiv_i128) != 90867766ULL) fail++;
    if (vgo_get_amount_out(100000000ULL, e9, e9, 0, 30, muldiv_i128) != 90661089ULL) fail++;
    if (vgo_get_amount_out(100000000ULL, e9, e9, 1, 0, muldiv_i128) != 99950051ULL) fail++;
    if (vgo_get_amount_out(100000000ULL, e9, e9, 1, 1, muldiv_i128) != 99940071ULL) fail++;
    if (vgo_get_amount_out(10000000ULL, e9, e9, 1, 1, muldiv_i128) != 9998994ULL) fail++;
    if (vgo_get_amount_out(0, e9, e9, 0, 5, muldiv_i128) != 0) fail++;
    if (vgo_get_amount_out(100000000ULL, e9, e9, 0, 10001, muldiv_i128) != 0) fail++;
    if (vgo_get_y(1100000000ULL, 2000000000ULL, e9, muldiv_i128) != 900049949ULL) fail++;
    if (vgo_get_amount_out(100000000ULL, e9, e9, 1, 1, muldiv_i128)
        != vgo_get_amount_out(100000000ULL, e9, e9, 1, 1, muldiv_limbs))
        fail++;
    if (muldiv_i128(4000000000ULL, 4000000000ULL, 1) != 0) fail++;
    if (fail) {
        fprintf(stderr, "selftest FAIL count=%d\n", fail);
        return 1;
    }
    puts("PASS");
    return 0;
}

static md_fn pick_md(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) return muldiv_limbs;
    }
    return muldiv_i128;
}

int main(int argc, char **argv) {
    md_fn md;
    if (argc < 2) {
        fprintf(stderr, "usage: velo_getout_c11 selftest | md a b d | f x0 y | d x0 y | gy x0 xy y | out ain ra rb stable fee [--limbs]\n");
        return 2;
    }
    md = pick_md(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "md") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                   strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "f") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n", vgo_f(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "d") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n", vgo_d(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "gy") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", vgo_get_y(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                          strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "out") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               vgo_get_amount_out(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                  strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                                  strtoull(argv[6], NULL, 10), md));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
