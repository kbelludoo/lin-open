/*
 * Independent C11 oracle for crvUSD Controller._get_f_remove (uint64 scale).
 *
 * Two implementations of 128-bit (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_crvusd_f_remove.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: published crvUSD liquidation collateral-withdraw fraction.
 * Upstream bytes are pinned by sha256/git blob in the proof harness; the
 * Curve.Fi repository states all-rights-reserved / informational-only, so
 * this oracle is original C11 and does not vendor the Vyper source.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WAD 1000000000ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

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

static uint64_t f_remove(uint64_t frac, uint64_t h, md_fn md) {
    uint64_t denom, left, one_m, inner, sum;
    if (frac > WAD) return 0;
    if (h == 0) return frac;
    if (frac == WAD) return WAD;
    if (WAD > UINT64_MAX - h) return 0;
    denom = WAD + h;
    left = WAD + (h / 2);
    one_m = WAD - frac;
    inner = md(left, one_m, denom);
    if (inner > UINT64_MAX - frac) return 0;
    sum = inner + frac;
    return md(sum, frac, WAD);
}

static uint64_t collateral_out(uint64_t y, uint64_t frac, uint64_t h, md_fn md) {
    return md(y, f_remove(frac, h, md), WAD);
}

static uint64_t naive_frac_out(uint64_t y, uint64_t frac, md_fn md) {
    return md(y, frac, WAD);
}

static int selftest(void) {
    uint64_t e9 = WAD;
    uint64_t a, b;
    if (muldiv_i128(100, 200, 50) != 400) return 1;
    if (muldiv_limbs(100, 200, 50) != 400) return 1;
    a = f_remove(500000000ULL, 0, muldiv_i128);
    b = f_remove(500000000ULL, 0, muldiv_limbs);
    if (a != 500000000ULL || a != b) return 1;
    a = f_remove(e9, 100000000ULL, muldiv_i128);
    b = f_remove(e9, 100000000ULL, muldiv_limbs);
    if (a != e9 || a != b) return 1;
    a = f_remove(500000000ULL, 100000000ULL, muldiv_i128);
    b = f_remove(500000000ULL, 100000000ULL, muldiv_limbs);
    if (a != 488636363ULL || a != b) return 1;
    a = f_remove(100000000ULL, 50000000ULL, muldiv_i128);
    if (a != 97857142ULL) return 1;
    if (f_remove(0, 100000000ULL, muldiv_i128) != 0) return 1;
    a = f_remove(900000000ULL, 40000000ULL, muldiv_i128);
    if (a != 898269230ULL) return 1;
    a = f_remove(10000000ULL, 10000000ULL, muldiv_i128);
    if (a != 9950990ULL) return 1;
    a = collateral_out(e9, 500000000ULL, 100000000ULL, muldiv_i128);
    if (a != 488636363ULL) return 1;
    if (naive_frac_out(e9, 500000000ULL, muldiv_i128) != 500000000ULL) return 1;
    if (muldiv_i128(7000000000000000000ULL, 3000000000000000000ULL, 1) != 0)
        return 1;
    if (f_remove(e9 + 1, 0, muldiv_i128) != 0) return 1;
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
    int limbs;
    if (argc < 2) {
        fprintf(stderr, "usage: crvusd_f_remove_c11 selftest|fr|out|naive|muldiv ... [--limbs]\n");
        return 2;
    }
    limbs = use_limbs(argc, argv);
    md = limbs ? muldiv_limbs : muldiv_i128;
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "fr") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               f_remove(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "out") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               collateral_out(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                              strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "naive") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               naive_frac_out(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                              md));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
