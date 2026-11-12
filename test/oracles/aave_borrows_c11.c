/*
 * Independent C11 oracle for Aave V3 calculateAvailableBorrows and
 * isolation-mode debt-ceiling math (uint64 scale).
 *
 * Two implementations of (a*b+add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_aave_borrows.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm (GenericLogic.calculateAvailableBorrows + PercentageMath
 * + ValidationLogic isolation ceiling):
 *   cap = percentMul(collateral, ltv)
 *   available = cap < debt ? 0 : cap - debt
 *   isoUnits = amount / 10**(decimals - DEBT_CEILING_DECIMALS)
 *   ok = !active || current + isoUnits <= ceiling
 *
 * Experimental PERCENTAGE_FACTOR = 1e4 (same bps as Aave).
 * Upstream Solidity is hash-pinned, not vendored. Oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PCT 10000ULL
#define HALF_PCT 5000ULL
#define CEIL_DEC 2ULL

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

static uint64_t percent_mul(uint64_t v, uint64_t p, mdadd_fn md) {
    if (p == 0 || v == 0) return 0;
    return md(v, p, HALF_PCT, PCT);
}

static uint64_t percent_div(uint64_t v, uint64_t p, mdadd_fn md) {
    if (p == 0) return 0;
    return md(v, PCT, p / 2, p);
}

static uint64_t available(uint64_t coll, uint64_t debt, uint64_t ltv, mdadd_fn md) {
    uint64_t cap = percent_mul(coll, ltv, md);
    return (cap < debt) ? 0 : cap - debt;
}

static uint64_t cover_ok(uint64_t coll, uint64_t debt, uint64_t amount, uint64_t ltv, mdadd_fn md) {
    uint64_t sum, need;
    if (ltv == 0) return 0;
    sum = debt + amount;
    if (sum < debt) return 0;
    need = percent_div(sum, ltv, md);
    return (coll < need) ? 0 : 1;
}

static uint64_t pow10u(uint64_t e) {
    uint64_t p = 1, i;
    if (e > 18) return 0;
    for (i = 0; i < e; i++) {
        if (p > UINT64_MAX / 10ULL) return 0;
        p *= 10ULL;
    }
    return p;
}

static uint64_t iso_units(uint64_t amount, uint64_t decimals, mdadd_fn md) {
    uint64_t den;
    if (decimals < CEIL_DEC) return 0;
    den = pow10u(decimals - CEIL_DEC);
    if (den == 0) return 0;
    return md(amount, 1, 0, den);
}

static uint64_t iso_ok(uint64_t active, uint64_t current, uint64_t amount,
                       uint64_t decimals, uint64_t ceiling, mdadd_fn md) {
    uint64_t units, next;
    if (active == 0) return 1;
    units = iso_units(amount, decimals, md);
    next = current + units;
    if (next < current) return 0;
    return (next <= ceiling) ? 1 : 0;
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    uint64_t q_i, q_l, r;
    int ov;
    q_i = muldiv_add_i128(100, 200, 0, 50);
    q_l = muldiv_add_limbs_q(100, 200, 0, 50);
    if (q_i != 400 || q_l != 400) return 1;
    muldiv_add_limbs(100, 200, 0, 50, &q_l, &r, &ov);
    if (r != 0 || ov != 0) return 1;
    if (percent_mul(1, HALF_PCT, muldiv_add_i128) != 1) return 1;
    if (percent_mul(1, HALF_PCT, muldiv_add_limbs_q) != 1) return 1;
    if (available(e9, 100000000ULL, 8000, muldiv_add_i128) != 700000000ULL) return 1;
    if (available(e9, 100000000ULL, 8000, muldiv_add_limbs_q) != 700000000ULL) return 1;
    if (available(1000, 900, 8000, muldiv_add_i128) != 0) return 1;
    if (iso_units(1000000ULL, 6, muldiv_add_i128) != 100) return 1;
    if (iso_ok(1, 9999, 1000000ULL, 6, 10000, muldiv_add_i128) != 0) return 1;
    if (iso_ok(1, 9900, 1000000ULL, 6, 10000, muldiv_add_limbs_q) != 1) return 1;
    if (cover_ok(e9, 0, 800000000ULL, 8000, muldiv_add_i128) != 1) return 1;
    if (cover_ok(e9, 0, 800000001ULL, 8000, muldiv_add_limbs_q) != 0) return 1;
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
            "usage: aave_borrows_c11 selftest\n"
            "       aave_borrows_c11 percent_mul V P [--limbs]\n"
            "       aave_borrows_c11 floor_mul V P [--limbs]\n"
            "       aave_borrows_c11 available COLL DEBT LTV [--limbs]\n"
            "       aave_borrows_c11 cover_ok COLL DEBT AMT LTV [--limbs]\n"
            "       aave_borrows_c11 iso_units AMT DEC [--limbs]\n"
            "       aave_borrows_c11 iso_ok ACTIVE CUR AMT DEC CEIL [--limbs]\n");
}

int main(int argc, char **argv) {
    mdadd_fn md;
    if (argc < 2) {
        usage();
        return 2;
    }
    md = parse_md(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "percent_mul") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               percent_mul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "floor_mul") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), 0, PCT));
        return 0;
    }
    if (strcmp(argv[1], "available") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               available(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                         strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "cover_ok") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               cover_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "iso_units") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               iso_units(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "iso_ok") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               iso_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                      strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                      strtoull(argv[6], NULL, 10), md));
        return 0;
    }
    usage();
    return 2;
}
