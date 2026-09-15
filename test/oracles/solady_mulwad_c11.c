/*
 * Independent C11 oracle for Solady FixedPointMathLib wad mul/div (uint64 scale).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_solady_mulwad.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: Vectorized/solady src/utils/FixedPointMathLib.sol (MIT).
 * This oracle is original C11, not a copy of the Yul assembly.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WAD 1000000000000000000ULL

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

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d, int *ov) {
    __uint128_t q;
    if (d == 0) {
        *ov = 1;
        return 0;
    }
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) {
        *ov = 1;
        return 0;
    }
    *ov = 0;
    return (uint64_t)q;
}

static uint64_t muldiv_rem_i128(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)a * (__uint128_t)b) % (__uint128_t)d);
}

static uint64_t mulwad(uint64_t x, uint64_t y, int limbs) {
    uint64_t q, r;
    int ov = 0;
    if (y == 0) return 0;
    if (limbs) {
        muldiv_limbs_qr(x, y, WAD, &q, &r, &ov);
        return ov ? 0 : q;
    }
    return muldiv_i128(x, y, WAD, &ov);
}

static uint64_t mulwad_up(uint64_t x, uint64_t y, int limbs) {
    uint64_t q, r;
    int ov = 0;
    if (y == 0) return 0;
    if (limbs) {
        muldiv_limbs_qr(x, y, WAD, &q, &r, &ov);
    } else {
        q = muldiv_i128(x, y, WAD, &ov);
        r = muldiv_rem_i128(x, y, WAD);
    }
    if (ov) return 0;
    if (r == 0) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1;
}

static uint64_t divwad(uint64_t x, uint64_t y, int limbs) {
    uint64_t q, r;
    int ov = 0;
    if (y == 0) return 0;
    if (limbs) {
        muldiv_limbs_qr(x, WAD, y, &q, &r, &ov);
        return ov ? 0 : q;
    }
    return muldiv_i128(x, WAD, y, &ov);
}

static uint64_t divwad_up(uint64_t x, uint64_t y, int limbs) {
    uint64_t q, r;
    int ov = 0;
    if (y == 0) return 0;
    if (limbs) {
        muldiv_limbs_qr(x, WAD, y, &q, &r, &ov);
    } else {
        q = muldiv_i128(x, WAD, y, &ov);
        r = muldiv_rem_i128(x, WAD, y);
    }
    if (ov) return 0;
    if (r == 0) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1;
}

static int selftest(void) {
    uint64_t q1, r1, q2, r2;
    int ov1, ov2;
    uint64_t vecs[][3] = {
        {100, 200, 50},
        {7, 9, 4},
        {WAD, 2, 3},
        {WAD * 2, WAD * 3, WAD},
        {1, 1, WAD},
    };
    size_t i;
    for (i = 0; i < sizeof(vecs) / sizeof(vecs[0]); i++) {
        muldiv_limbs_qr(vecs[i][0], vecs[i][1], vecs[i][2], &q1, &r1, &ov1);
        q2 = muldiv_i128(vecs[i][0], vecs[i][1], vecs[i][2], &ov2);
        r2 = muldiv_rem_i128(vecs[i][0], vecs[i][1], vecs[i][2]);
        if (ov1 != ov2 || q1 != q2 || r1 != r2) return 1;
    }
    if (mulwad(WAD * 2, WAD * 3, 0) != WAD * 6) return 1;
    if (mulwad(WAD * 2, WAD * 3, 1) != WAD * 6) return 1;
    if (mulwad_up(1, 1, 0) != 1 || mulwad_up(1, 1, 1) != 1) return 1;
    if (divwad(WAD * 6, WAD * 2, 0) != WAD * 3) return 1;
    if (divwad_up(1, WAD * 2, 0) != 1 || divwad_up(1, WAD * 2, 1) != 1) return 1;
    if (divwad(1, 0, 0) != 0) return 1;
    return 0;
}

int main(int argc, char **argv) {
    int limbs = 0;
    const char *op;
    uint64_t a, b, d;
    int i;

    if (argc < 2) {
        fprintf(stderr, "usage: solady_mulwad_c11 selftest | muldiv a b d | mulwad x y | mulwadup x y | divwad x y | divwadup x y [--limbs]\n");
        return 2;
    }
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) limbs = 1;
    }
    op = argv[1];
    if (strcmp(op, "selftest") == 0) {
        if (selftest() != 0) {
            printf("FAIL\n");
            return 1;
        }
        printf("PASS\n");
        return 0;
    }
    if (argc < 4) return 2;
    a = strtoull(argv[2], NULL, 10);
    b = strtoull(argv[3], NULL, 10);
    if (strcmp(op, "muldiv") == 0) {
        int ov = 0;
        uint64_t q, r;
        if (argc < 5) return 2;
        d = strtoull(argv[4], NULL, 10);
        if (limbs) {
            muldiv_limbs_qr(a, b, d, &q, &r, &ov);
            printf("%" PRIu64 "\n", ov ? 0 : q);
        } else {
            printf("%" PRIu64 "\n", muldiv_i128(a, b, d, &ov));
        }
        return 0;
    }
    if (strcmp(op, "mulwad") == 0) {
        printf("%" PRIu64 "\n", mulwad(a, b, limbs));
        return 0;
    }
    if (strcmp(op, "mulwadup") == 0) {
        printf("%" PRIu64 "\n", mulwad_up(a, b, limbs));
        return 0;
    }
    if (strcmp(op, "divwad") == 0) {
        printf("%" PRIu64 "\n", divwad(a, b, limbs));
        return 0;
    }
    if (strcmp(op, "divwadup") == 0) {
        printf("%" PRIu64 "\n", divwad_up(a, b, limbs));
        return 0;
    }
    return 2;
}
