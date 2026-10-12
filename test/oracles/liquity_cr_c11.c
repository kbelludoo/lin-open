/*
 * Independent C11 oracle for Liquity ICR / decMul / decPow (uint64 scale).
 *
 * Two implementations of (x*y)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_liquity_cr.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: liquity/dev
 *   packages/contracts/contracts/Dependencies/LiquityMath.sol (MIT)
 * This oracle is original C11 (not a verbatim port of the Solidity).
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WAD 1000000000000000000ULL
#define HALF 500000000000000000ULL
#define POW_CAP 525600000ULL
#define MINUTE_DECAY 999037758833783000ULL
#define BPS 10000ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d,
                            uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge;
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
            if (u_lt(r_lo, d)) r_hi = r_hi - 1;
            r_lo = r_lo - d;
            if (i >= 64) ov = 1;
            else q = q | (1ULL << i);
        }
    }
    *q_out = ov ? 0 : q;
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t floor_i128(uint64_t x, uint64_t y, uint64_t d, int *ov) {
    __uint128_t q;
    if (d == 0) {
        *ov = 1;
        return 0;
    }
    q = ((__uint128_t)x * (__uint128_t)y) / (__uint128_t)d;
    if (q > UINT64_MAX) {
        *ov = 1;
        return 0;
    }
    *ov = 0;
    return (uint64_t)q;
}

static uint64_t rem_i128(uint64_t x, uint64_t y, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)x * (__uint128_t)y) % (__uint128_t)d);
}

static uint64_t dec_mul(uint64_t x, uint64_t y, int *ov) {
    uint64_t q, r;
    q = floor_i128(x, y, WAD, ov);
    if (*ov) return 0;
    r = rem_i128(x, y, WAD);
    if (r < HALF) return q;
    if (q == UINT64_MAX) {
        *ov = 1;
        return 0;
    }
    return q + 1;
}

static uint64_t compute_cr(uint64_t coll, uint64_t debt, uint64_t price, int *ov) {
    if (debt == 0) {
        *ov = 1;
        return 0;
    }
    return floor_i128(coll, price, debt, ov);
}

static uint64_t aave_hf(uint64_t coll, uint64_t debt, uint64_t lt, int *ov) {
    uint64_t adj;
    if (debt == 0) {
        *ov = 1;
        return 0;
    }
    adj = floor_i128(coll, lt, BPS, ov);
    if (*ov) return 0;
    return floor_i128(adj, WAD, debt, ov);
}

static uint64_t dec_pow(uint64_t base, uint64_t minutes, int *ov) {
    uint64_t y, x, n;
    int local = 0;
    if (minutes > POW_CAP) minutes = POW_CAP;
    if (minutes == 0) {
        *ov = 0;
        return WAD;
    }
    y = WAD;
    x = base;
    n = minutes;
    while (n > 1) {
        if ((n & 1ULL) == 0) {
            x = dec_mul(x, x, &local);
            n = n / 2;
        } else {
            y = dec_mul(x, y, &local);
            x = dec_mul(x, x, &local);
            n = (n - 1) / 2;
        }
        if (local) {
            *ov = 1;
            return 0;
        }
    }
    return dec_mul(x, y, ov);
}

static int selftest(void) {
    uint64_t qL, rL, qI;
    int ovL, ovI;
    muldiv_limbs_qr(7, 9, 2, &qL, &rL, &ovL);
    qI = floor_i128(7, 9, 2, &ovI);
    if (ovL || ovI || qL != 31 || rL != 1 || qI != 31) return 1;
    muldiv_limbs_qr(WAD, WAD, 1ULL, &qL, &rL, &ovL);
    qI = floor_i128(WAD, WAD, 1ULL, &ovI);
    if (!ovL || !ovI || qL != 0 || qI != 0) return 1;
    qI = dec_mul(3, HALF, &ovI);
    if (ovI || qI != 2) return 1;
    qI = floor_i128(3, HALF, WAD, &ovI);
    if (ovI || qI != 1) return 1;
    qI = compute_cr(10, 5, 3, &ovI);
    if (ovI || qI != 6) return 1;
    qI = compute_cr(1000, 0, 2000, &ovI);
    if (qI != 0) return 1;
    qI = aave_hf(10000, 10000, 8500, &ovI);
    if (ovI || qI != 850000000000000000ULL) return 1;
    qI = dec_pow(2 * WAD, 3, &ovI);
    if (ovI || qI != 8 * WAD) return 1;
    qI = dec_pow(MINUTE_DECAY, 2, &ovI);
    if (ovI || qI != 998076443575627963ULL) return 1;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t a, b, c, out;
    int ov = 0, use_limbs = 0, i;
    uint64_t qL, rL;

    if (argc < 2) {
        fprintf(stderr,
                "usage: liquity_cr_c11 selftest | floor x y d [--limbs] | rem x y d | "
                "decmul x y | cr coll debt price | aave coll debt lt | "
                "pow base minutes | min a b | max a b | abs a b\n");
        return 2;
    }
    kind = argv[1];
    if (strcmp(kind, "selftest") == 0) return selftest();
    for (i = 2; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) use_limbs = 1;
    }
    if (strcmp(kind, "floor") == 0 || strcmp(kind, "rem") == 0 || strcmp(kind, "ov") == 0) {
        if (argc < 5) return 2;
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        if (use_limbs) {
            muldiv_limbs_qr(a, b, c, &qL, &rL, &ov);
            if (strcmp(kind, "rem") == 0) out = rL;
            else if (strcmp(kind, "ov") == 0) out = (uint64_t)ov;
            else out = qL;
        } else if (strcmp(kind, "rem") == 0) out = rem_i128(a, b, c);
        else if (strcmp(kind, "ov") == 0) {
            floor_i128(a, b, c, &ov);
            out = (uint64_t)ov;
        } else out = floor_i128(a, b, c, &ov);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "decmul") == 0 || strcmp(kind, "pow") == 0 ||
        strcmp(kind, "min") == 0 || strcmp(kind, "max") == 0 || strcmp(kind, "abs") == 0) {
        if (argc < 4) return 2;
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        if (strcmp(kind, "decmul") == 0) out = dec_mul(a, b, &ov);
        else if (strcmp(kind, "pow") == 0) out = dec_pow(a, b, &ov);
        else if (strcmp(kind, "min") == 0) out = (a < b) ? a : b;
        else if (strcmp(kind, "max") == 0) out = (a >= b) ? a : b;
        else out = (a >= b) ? (a - b) : (b - a);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (argc < 5) return 2;
    a = strtoull(argv[2], NULL, 10);
    b = strtoull(argv[3], NULL, 10);
    c = strtoull(argv[4], NULL, 10);
    if (strcmp(kind, "cr") == 0) out = compute_cr(a, b, c, &ov);
    else if (strcmp(kind, "aave") == 0) out = aave_hf(a, b, c, &ov);
    else {
        fprintf(stderr, "unknown kind %s\n", kind);
        return 2;
    }
    (void)use_limbs;
    printf("%" PRIu64 "\n", out);
    return 0;
}
