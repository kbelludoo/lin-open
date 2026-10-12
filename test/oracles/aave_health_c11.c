/*
 * Independent C11 oracle for Aave V3 health-factor math (uint64 scale).
 *
 * Two implementations of (a*b + addend)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_aave_health.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: aave/aave-v3-core v1.19.4 GenericLogic.sol / PercentageMath.sol /
 * WadRayMath.sol. Algorithm license: MIT (BUSL-1.1 Change Date 2023-01-27
 * elapsed). This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WAD 1000000000000000000ULL
#define PCT 10000ULL
#define HALF_PCT 5000ULL

static uint64_t muldiv_add_i128(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b + (__uint128_t)add) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    return muldiv_add_i128(a, b, 0, d);
}

static uint64_t muldiv_rem_i128(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)a * (__uint128_t)b) % (__uint128_t)d);
}

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_add_limbs_qr(uint64_t a, uint64_t b, uint64_t add, uint64_t d,
                                uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, lo2;
    uint64_t bit, ge, need_borrow;
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
    lo2 = lo + add;
    if (lo2 < lo) hi = hi + 1;
    lo = lo2;

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

static uint64_t muldiv_add_limbs(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_add_limbs_qr(a, b, add, d, &q, &r, &ov);
    return q;
}

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d) {
    return muldiv_add_limbs(a, b, 0, d);
}

typedef uint64_t (*md_add_fn)(uint64_t, uint64_t, uint64_t, uint64_t);

static uint64_t percent_mul(uint64_t v, uint64_t p, md_add_fn md) {
    return md(v, p, HALF_PCT, PCT);
}

static uint64_t percent_mul_floor(uint64_t v, uint64_t p, md_add_fn md) {
    return md(v, p, 0, PCT);
}

static uint64_t wad_div(uint64_t a, uint64_t b, md_add_fn md) {
    if (b == 0) return 0;
    return md(a, WAD, b >> 1, b);
}

static uint64_t wad_div_floor(uint64_t a, uint64_t b, md_add_fn md) {
    if (b == 0) return 0;
    return md(a, WAD, 0, b);
}

static uint64_t health(uint64_t coll, uint64_t lt, uint64_t debt, md_add_fn md) {
    if (debt == 0) return 0;
    return wad_div(percent_mul(coll, lt, md), debt, md);
}

static uint64_t skip_lt(uint64_t coll, uint64_t debt, md_add_fn md) {
    if (debt == 0) return 0;
    return wad_div(coll, debt, md);
}

static uint64_t available(uint64_t coll, uint64_t ltv, uint64_t debt, md_add_fn md) {
    uint64_t cap = percent_mul(coll, ltv, md);
    if (cap < debt) return 0;
    return cap - debt;
}

static int selftest(void) {
    int fail = 0;
    md_add_fn a = muldiv_add_i128;
    md_add_fn b = muldiv_add_limbs;
    if (muldiv_i128(100, 200, 50) != 400) fail++;
    if (muldiv_i128(100, 200, 50) != muldiv_limbs(100, 200, 50)) fail++;
    if (percent_mul(10000, 8000, a) != 8000) fail++;
    if (percent_mul(10000, 8000, a) != percent_mul(10000, 8000, b)) fail++;
    if (percent_mul(1, 5000, a) != 1) fail++;
    if (percent_mul_floor(1, 5000, a) != 0) fail++;
    if (wad_div(8000, 5000, a) != 1600000000000000000ULL) fail++;
    if (wad_div(8000, 5000, a) != wad_div(8000, 5000, b)) fail++;
    if (wad_div(2, 3, a) != 666666666666666667ULL) fail++;
    if (wad_div_floor(2, 3, a) != 666666666666666666ULL) fail++;
    if (health(10000, 8000, 5000, a) != 1600000000000000000ULL) fail++;
    if (health(10000, 8000, 8500, a) != 941176470588235294ULL) fail++;
    if (skip_lt(10000, 8500, a) != 1176470588235294118ULL) fail++;
    if (health(10000, 8000, 8500, a) != health(10000, 8000, 8500, b)) fail++;
    if (skip_lt(10000, 8500, a) != skip_lt(10000, 8500, b)) fail++;
    if (available(10000, 7500, 1000, a) != 6500) fail++;
    if (available(10000, 7500, 8000, a) != 0) fail++;
    if (health(10000, 8000, 0, a) != 0) fail++;
    if (percent_mul(10000, 0, a) != 0) fail++;
    if (muldiv_i128(WAD, WAD, 1) != 0) fail++;
    if (muldiv_limbs(WAD, WAD, 1) != 0) fail++;
    if (muldiv_rem_i128(7, 9, 2) != 1) fail++;
    if (fail) {
        fprintf(stderr, "aave_health_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("aave_health_c11 selftest PASS\n");
    printf("vector.hf_80_50=%" PRIu64 "\n", health(10000, 8000, 5000, a));
    printf("vector.hf_80_85=%" PRIu64 "\n", health(10000, 8000, 8500, a));
    printf("vector.skip_85=%" PRIu64 "\n", skip_lt(10000, 8500, a));
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    md_add_fn md = muldiv_add_i128;
    int limbs = 0;
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest | muldiv a b d | muldivadd a b add d | percentmul v p | waddiv a b | health c lt d | skiplt c d | avail c ltv d\n", argv[0]);
        return 2;
    }
    cmd = argv[1];
    if (argc >= 3 && strcmp(argv[argc - 1], "--limbs") == 0) {
        md = muldiv_add_limbs;
        limbs = 1;
        argc--;
    }
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "muldiv") == 0 && argc == 5) {
        printf("%" PRIu64 "\n", md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), 0, strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "muldivadd") == 0 && argc == 6) {
        printf("%" PRIu64 "\n", md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "percentmul") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", percent_mul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "percentmulfloor") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", percent_mul_floor(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "waddiv") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", wad_div(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "waddivfloor") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", wad_div_floor(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "health") == 0 && argc == 5) {
        printf("%" PRIu64 "\n", health(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "skiplt") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", skip_lt(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "avail") == 0 && argc == 5) {
        printf("%" PRIu64 "\n", available(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "rem") == 0 && argc == 5) {
        uint64_t x = strtoull(argv[2], NULL, 10);
        uint64_t y = strtoull(argv[3], NULL, 10);
        uint64_t d = strtoull(argv[4], NULL, 10);
        uint64_t q, r;
        int ov;
        if (limbs) {
            muldiv_add_limbs_qr(x, y, 0, d, &q, &r, &ov);
            printf("%" PRIu64 "\n", r);
        } else {
            printf("%" PRIu64 "\n", muldiv_rem_i128(x, y, d));
        }
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
