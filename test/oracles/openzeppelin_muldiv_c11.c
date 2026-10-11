/*
 * Independent C11 oracle for OpenZeppelin Math.mulDiv rounding (uint64 scale).
 *
 * Two implementations of (x*y)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_openzeppelin_muldiv.lin
 *
 * Rounding matches OZ v5.0.2 unsignedRoundsUp: odd modes (Ceil=1, Expand=3)
 * round away from zero for unsigned values. Floor=0 and Trunc=2 stay floor.
 *
 * Fail-closed (LIN profile, not OZ revert): d==0, overflow, negative, rounding
 * outside 0..3 -> 0.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm license: MIT (OpenZeppelin). This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static uint64_t muldiv_i128_floor(uint64_t x, uint64_t y, uint64_t d, int *ov) {
    __uint128_t q, r;
    if (d == 0) {
        *ov = 1;
        return 0;
    }
    q = ((__uint128_t)x * (__uint128_t)y) / (__uint128_t)d;
    r = ((__uint128_t)x * (__uint128_t)y) % (__uint128_t)d;
    (void)r;
    if (q > UINT64_MAX) {
        *ov = 1;
        return 0;
    }
    *ov = 0;
    return (uint64_t)q;
}

static uint64_t muldiv_i128_rem(uint64_t x, uint64_t y, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)x * (__uint128_t)y) % (__uint128_t)d);
}

static uint64_t apply_round(uint64_t q, uint64_t r, int ov, int rounding) {
    if (rounding < 0 || rounding > 3) return 0;
    if (ov) return 0;
    if ((rounding % 2) == 0) return q;
    if (r == 0) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1;
}

static uint64_t ozmd_i128(uint64_t x, uint64_t y, uint64_t d, int rounding) {
    int ov = 0;
    uint64_t q, r;
    if (d == 0 || rounding < 0 || rounding > 3) return 0;
    q = muldiv_i128_floor(x, y, d, &ov);
    r = muldiv_i128_rem(x, y, d);
    return apply_round(q, r, ov, rounding);
}

static uint64_t ozmd_limbs(uint64_t x, uint64_t y, uint64_t d, int rounding) {
    uint64_t q, r;
    int ov = 0;
    if (d == 0 || rounding < 0 || rounding > 3) return 0;
    muldiv_limbs_qr(x, y, d, &q, &r, &ov);
    return apply_round(q, r, ov, rounding);
}

static uint64_t ceil_div(uint64_t a, uint64_t b) {
    if (b == 0 || a == 0) return 0;
    return (a - 1) / b + 1;
}

static int selftest(void) {
    uint64_t q, r;
    int ov;
    const uint64_t WAD = 1000000000000000000ULL;

    if (ozmd_i128(100, 200, 50, 0) != 400) return 1;
    if (ozmd_limbs(100, 200, 50, 0) != 400) return 2;
    if (ozmd_i128(7, 9, 2, 0) != 31) return 3;
    if (ozmd_i128(7, 9, 2, 1) != 32) return 4;
    if (ozmd_i128(7, 9, 2, 2) != 31) return 5;
    if (ozmd_i128(7, 9, 2, 3) != 32) return 6;
    if (ozmd_limbs(7, 9, 2, 1) != 32) return 7;
    if (ozmd_i128(1, 1, 2, 0) != 0) return 8;
    if (ozmd_i128(1, 1, 2, 1) != 1) return 9;
    if (ozmd_i128(WAD, 1, 2, 0) != WAD / 2) return 10;
    if (ozmd_i128(WAD, WAD, 1, 0) != 0) return 11;
    if (ozmd_i128(7, 9, 0, 1) != 0) return 12;
    if (ozmd_i128(7, 9, 2, 4) != 0) return 13;
    if (ozmd_i128(7, 2, 3, 1) != 5) return 14;
    if (ceil_div(7, 3) != 3) return 15;
    if (ozmd_i128(100, 50, 200, 0) != 25) return 16;
    if (ozmd_i128(25, 200, 50, 1) != 100) return 17;
    if (ozmd_i128(1, 100, 3, 1) != 34) return 18;
    muldiv_limbs_qr(7, 9, 2, &q, &r, &ov);
    if (q != 31 || r != 1 || ov != 0) return 19;
    if (ozmd_i128(7, 9, 2, 0) != ozmd_limbs(7, 9, 2, 0)) return 20;
    if (ozmd_i128(7, 9, 2, 1) != ozmd_limbs(7, 9, 2, 1)) return 21;
    if (muldiv_i128_rem(7, 9, 2) != 1) return 22;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    uint64_t x, y, d, out;
    int rounding;
    const char *mode;

    if (argc < 2) {
        fprintf(stderr, "usage: ozmd selftest | floor x y d | ceil x y d | rem x y d | ov x y d | muldiv x y d rounding | ceildiv a b\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    mode = argv[1];
    if (strcmp(mode, "ceildiv") == 0 && argc == 4) {
        printf("%" PRIu64 "\n", ceil_div(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
        return 0;
    }
    if (argc < 5) return 2;
    x = strtoull(argv[2], NULL, 10);
    y = strtoull(argv[3], NULL, 10);
    d = strtoull(argv[4], NULL, 10);
    if (strcmp(mode, "floor") == 0) {
        out = ozmd_i128(x, y, d, 0);
        if (argc > 5 && strcmp(argv[5], "--limbs") == 0) out = ozmd_limbs(x, y, d, 0);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(mode, "ceil") == 0) {
        out = ozmd_i128(x, y, d, 1);
        if (argc > 5 && strcmp(argv[5], "--limbs") == 0) out = ozmd_limbs(x, y, d, 1);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(mode, "rem") == 0) {
        printf("%" PRIu64 "\n", muldiv_i128_rem(x, y, d));
        return 0;
    }
    if (strcmp(mode, "ov") == 0) {
        int ov = 0;
        (void)muldiv_i128_floor(x, y, d, &ov);
        printf("%d\n", ov);
        return 0;
    }
    if (strcmp(mode, "muldiv") == 0 && argc >= 6) {
        rounding = atoi(argv[5]);
        out = ozmd_i128(x, y, d, rounding);
        if (argc > 6 && strcmp(argv[6], "--limbs") == 0) out = ozmd_limbs(x, y, d, rounding);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    return 2;
}
