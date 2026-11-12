/*
 * Independent C11 oracle for Aave V3 DefaultReserveInterestRateStrategy
 * variable-rate math (RAY'=1e9, not RAY=1e27).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_aave_irm.lin
 *
 * rayMul/rayDiv/percentMul are unsigned half-up on the remainder.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: aave/aave-v3-core DefaultReserveInterestRateStrategy.sol
 * Algorithm license: MIT after BUSL-1.1 Change Date 2023-01-27.
 * This oracle is original C11. Solidity is not compiled or vendored.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAY 1000000000ULL
#define HALF_RAY 500000000ULL
#define PCT 10000ULL
#define HALF_PCT 5000ULL

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_rem_i128(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)a * (__uint128_t)b) % (__uint128_t)d);
}

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
            else q |= (1ULL << i);
        }
    }
    *q_out = ov ? 0 : q;
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return q;
}

static uint64_t muldiv_rem_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return r;
}

static uint64_t ray_mul(uint64_t a, uint64_t b, int limbs) {
    uint64_t q, r;
    if (a == 0 || b == 0) return 0;
    if (limbs) {
        q = muldiv_limbs(a, b, RAY);
        r = muldiv_rem_limbs(a, b, RAY);
    } else {
        q = muldiv_i128(a, b, RAY);
        r = muldiv_rem_i128(a, b, RAY);
    }
    if (r < HALF_RAY) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1;
}

static uint64_t ray_div(uint64_t a, uint64_t b, int limbs) {
    uint64_t q, r, half_b;
    if (b == 0) return 0;
    half_b = b / 2;
    if (limbs) {
        q = muldiv_limbs(a, RAY, b);
        r = muldiv_rem_limbs(a, RAY, b);
    } else {
        q = muldiv_i128(a, RAY, b);
        r = muldiv_rem_i128(a, RAY, b);
    }
    if (r < b - half_b) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1;
}

static uint64_t pct_mul(uint64_t a, uint64_t bps, int limbs) {
    uint64_t q, r;
    if (limbs) {
        q = muldiv_limbs(a, bps, PCT);
        r = muldiv_rem_limbs(a, bps, PCT);
    } else {
        q = muldiv_i128(a, bps, PCT);
        r = muldiv_rem_i128(a, bps, PCT);
    }
    if (r < HALF_PCT) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1;
}

static uint64_t usage(uint64_t liq, uint64_t debt, int limbs) {
    uint64_t den;
    if (debt == 0) return 0;
    den = liq + debt;
    if (den < liq) return 0;
    return ray_div(debt, den, limbs);
}

static uint64_t var_rate(uint64_t liq, uint64_t debt, uint64_t opt, uint64_t base,
                         uint64_t s1, uint64_t s2, int limbs) {
    uint64_t u, excess, extra, stepped;
    if (opt == 0 || opt > RAY) return 0;
    u = usage(liq, debt, limbs);
    if (u > opt) {
        excess = ray_div(u - opt, RAY - opt, limbs);
        extra = ray_mul(s2, excess, limbs);
        return base + s1 + extra;
    }
    stepped = ray_div(ray_mul(s1, u, limbs), opt, limbs);
    return base + stepped;
}

static uint64_t liq_rate(uint64_t vr, uint64_t u, uint64_t rf, int limbs) {
    if (rf > PCT) return 0;
    return pct_mul(ray_mul(vr, u, limbs), PCT - rf, limbs);
}

static int selftest(void) {
    int fail = 0;
    uint64_t opt = 800000000ULL, s1 = 40000000ULL, s2 = 800000000ULL;
    if (muldiv_i128(100, 200, 50) != 400) fail++;
    if (muldiv_limbs(100, 200, 50) != 400) fail++;
    if (ray_mul(1, HALF_RAY, 0) != 1 || ray_mul(1, HALF_RAY, 1) != 1) fail++;
    if (muldiv_i128(1, HALF_RAY, RAY) != 0) fail++;
    if (ray_div(2, 3, 0) != 666666667ULL || ray_div(2, 3, 1) != 666666667ULL) fail++;
    if (muldiv_i128(2, RAY, 3) != 666666666ULL) fail++;
    if (pct_mul(1, 5000, 0) != 1 || pct_mul(1, 5000, 1) != 1) fail++;
    if (usage(1000000000ULL, 1000000000ULL, 0) != 500000000ULL) fail++;
    if (var_rate(1000000000ULL, 1000000000ULL, opt, 0, s1, s2, 0) != 25000000ULL) fail++;
    if (var_rate(200000000ULL, 800000000ULL, opt, 0, s1, s2, 0) != 40000000ULL) fail++;
    if (var_rate(100000000ULL, 900000000ULL, opt, 0, s1, s2, 0) != 440000000ULL) fail++;
    if (var_rate(0, 1000000000ULL, opt, 0, s1, s2, 0) != 840000000ULL) fail++;
    if (var_rate(1000000000ULL, 1000000000ULL, opt, 0, s1, s2, 1) != 25000000ULL) fail++;
    if (liq_rate(25000000ULL, 500000000ULL, 1500, 0) != 10625000ULL) fail++;
    if (ray_mul(10000000000ULL, 10000000000ULL, 0) != 100000000000ULL) fail++;
    if (ray_mul(10000000000ULL, 10000000000ULL, 1) != 100000000000ULL) fail++;
    if (fail) {
        fprintf(stderr, "aave_irm_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("aave_irm_c11 selftest PASS\n");
    printf("vector.usage_50=%" PRIu64 "\n", usage(1000000000ULL, 1000000000ULL, 0));
    printf("vector.var_50=%" PRIu64 "\n",
           var_rate(1000000000ULL, 1000000000ULL, opt, 0, s1, s2, 0));
    printf("vector.var_90=%" PRIu64 "\n",
           var_rate(100000000ULL, 900000000ULL, opt, 0, s1, s2, 0));
    printf("vector.liq_50=%" PRIu64 "\n", liq_rate(25000000ULL, 500000000ULL, 1500, 0));
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    int limbs = 0;
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest | raymul a b | raydiv a b | pct a bps | usage liq debt | var liq debt opt base s1 s2 | liq vr u rf\n",
                argv[0]);
        return 2;
    }
    cmd = argv[1];
    if (argc >= 3 && strcmp(argv[argc - 1], "--limbs") == 0) {
        limbs = 1;
        argc--;
    }
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "raymul") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", ray_mul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), limbs));
        return 0;
    }
    if (strcmp(cmd, "raydiv") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", ray_div(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), limbs));
        return 0;
    }
    if (strcmp(cmd, "pct") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", pct_mul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), limbs));
        return 0;
    }
    if (strcmp(cmd, "usage") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", usage(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), limbs));
        return 0;
    }
    if (strcmp(cmd, "var") == 0 && argc == 8) {
        printf("%" PRIu64 "\n",
               var_rate(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                        strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10), limbs));
        return 0;
    }
    if (strcmp(cmd, "liq") == 0 && argc == 5) {
        printf("%" PRIu64 "\n",
               liq_rate(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoull(argv[4], NULL, 10), limbs));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
