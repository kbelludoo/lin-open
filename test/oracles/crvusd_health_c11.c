/*
 * Independent C11 oracle for crvUSD Controller._health (uint64-scale, SCALE=1e9).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_crvusd_health.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: curvefi/curve-stablecoin curve_stablecoin/controller.vy
 * (informational-only; no reproduction license). Vyper is hash-pinned only
 * and is not vendored. This oracle is original C11 of the uint64-scale formulas.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SCALE 1000000000ULL

typedef uint64_t (*md_fn)(uint64_t, uint64_t, uint64_t);
typedef int (*ov_fn)(uint64_t, uint64_t, uint64_t);

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > (uint64_t)INT64_MAX) return 0;
    return (uint64_t)q;
}

static int muldiv_ov_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 1;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    return q > (uint64_t)INT64_MAX;
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

static int muldiv_ov_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge, need_borrow;
    int i, ov;

    if (d == 0) return 1;
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
    if (ov) return 1;
    if ((int64_t)q < 0) return 1;
    return 0;
}

static int64_t chl_health(uint64_t x_down, uint64_t debt, uint64_t disc, int full,
                         int64_t ns0, int64_t active, uint64_t p, uint64_t p_up,
                         uint64_t y, md_fn md, ov_fn ov) {
    uint64_t hm, q, extra, dp;
    int64_t h;
    if (debt == 0 || disc > SCALE) return 0;
    hm = SCALE - disc;
    if (ov(x_down, hm, debt)) return 0;
    q = md(x_down, hm, debt);
    h = (int64_t)q - (int64_t)SCALE;
    if (full && ns0 > active && p > p_up) {
        dp = p - p_up;
        if (ov(dp, y, debt)) return 0;
        extra = md(dp, y, debt);
        h = h + (int64_t)extra;
    }
    return h;
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

    for (i = 0; i < sizeof(mdv) / sizeof(mdv[0]); i++) {
        uint64_t x = muldiv_i128(mdv[i].a, mdv[i].b, mdv[i].d);
        uint64_t y = muldiv_limbs(mdv[i].a, mdv[i].b, mdv[i].d);
        int ox = muldiv_ov_i128(mdv[i].a, mdv[i].b, mdv[i].d);
        int oy = muldiv_ov_limbs(mdv[i].a, mdv[i].b, mdv[i].d);
        if (x != y || ox != oy) {
            fprintf(stderr, "muldiv mismatch i=%zu i128=%" PRIu64 " limbs=%" PRIu64 " ov %d/%d\n",
                    i, x, y, ox, oy);
            fail++;
        }
    }
    if (muldiv_i128(100, 200, 50) != 400) fail++;
    if (chl_health(e9, e9, 0, 0, 0, 0, 0, 0, 0, muldiv_i128, muldiv_ov_i128) != 0) fail++;
    if (chl_health(2000000000ULL, e9, 0, 0, 0, 0, 0, 0, 0, muldiv_i128, muldiv_ov_i128) != (int64_t)e9)
        fail++;
    if (chl_health(e9, e9, 60000000ULL, 0, 0, 0, 0, 0, 0, muldiv_i128, muldiv_ov_i128) != -60000000LL)
        fail++;
    if (chl_health(1200000000ULL, e9, 60000000ULL, 0, 0, 0, 0, 0, 0, muldiv_i128, muldiv_ov_i128)
        != 128000000LL)
        fail++;
    if (chl_health(e9, 0, 0, 0, 0, 0, 0, 0, 0, muldiv_i128, muldiv_ov_i128) != 0) fail++;
    if (chl_health(e9, e9, 0, 1, 10, 5, 1100000000ULL, e9, e9, muldiv_i128, muldiv_ov_i128)
        != 100000000LL)
        fail++;
    if (chl_health(e9, e9, 0, 1, 3, 5, 1100000000ULL, e9, e9, muldiv_i128, muldiv_ov_i128) != 0)
        fail++;
    if (chl_health(e9, e9, 0, 1, 10, 5, e9, 1100000000ULL, e9, muldiv_i128, muldiv_ov_i128) != 0)
        fail++;
    if (chl_health(0, e9, 0, 0, 0, 0, 0, 0, 0, muldiv_i128, muldiv_ov_i128) != -(int64_t)e9) fail++;
    if (chl_health(1050000000ULL, e9, 60000000ULL, 0, 0, 0, 0, 0, 0, muldiv_i128, muldiv_ov_i128)
        != -13000000LL)
        fail++;
    if (chl_health(e9, e9, 0, 1, -5, -10, 1100000000ULL, e9, e9, muldiv_i128, muldiv_ov_i128)
        != 100000000LL)
        fail++;
    if (chl_health(e9, e9, 0, 1, -5, -10, 1100000000ULL, e9, e9, muldiv_limbs, muldiv_ov_limbs)
        != 100000000LL)
        fail++;
    if (muldiv_i128(4000000000ULL, 4000000000ULL, 1) != 0) fail++;
    if (muldiv_ov_i128(4000000000ULL, 4000000000ULL, 1) != 1) fail++;
    if (chl_health(10000000000ULL, 1, 0, 0, 0, 0, 0, 0, 0, muldiv_i128, muldiv_ov_i128) != 0) fail++;
    if (chl_health(e9, e9, 1000000001ULL, 0, 0, 0, 0, 0, 0, muldiv_i128, muldiv_ov_i128) != 0) fail++;
    if (fail) {
        fprintf(stderr, "selftest FAIL count=%d\n", fail);
        return 1;
    }
    puts("PASS");
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
    int limbs;
    md_fn md;
    ov_fn ov;
    if (argc < 2) {
        fprintf(stderr,
                "usage: crvusd_health_c11 selftest | md a b d | ov a b d | "
                "h x_down debt disc full ns0 active p p_up y [--limbs]\n");
        return 2;
    }
    limbs = use_limbs(argc, argv);
    md = limbs ? muldiv_limbs : muldiv_i128;
    ov = limbs ? muldiv_ov_limbs : muldiv_ov_i128;
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "md") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "ov") == 0 && argc >= 5) {
        printf("%d\n",
               ov(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "h") == 0 && argc >= 11) {
        printf("%" PRId64 "\n",
               chl_health(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                          strtoull(argv[4], NULL, 10), (int)strtoll(argv[5], NULL, 10),
                          strtoll(argv[6], NULL, 10), strtoll(argv[7], NULL, 10),
                          strtoull(argv[8], NULL, 10), strtoull(argv[9], NULL, 10),
                          strtoull(argv[10], NULL, 10), md, ov));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
