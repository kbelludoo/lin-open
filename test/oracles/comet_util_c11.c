/*
 * Independent C11 oracle for Compound III getUtilization (uint64 scale).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_comet_util.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: compound-finance/comet
 *   contracts/CometWithExtendedAssetList.sol getUtilization
 *   contracts/CometCore.sol FACTOR_SCALE = 1e18
 * License of the algorithm: GPL-2.0-or-later after BUSL-1.1 Change Date
 * 2025-12-31. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FACTOR_SCALE 1000000000000000000ULL

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d,
                            uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo;
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

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return q;
}

static uint64_t utilization(uint64_t supply_pv, uint64_t borrow_pv,
                            uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (supply_pv == 0) return 0;
    return md(borrow_pv, FACTOR_SCALE, supply_pv);
}

static uint64_t twostep(uint64_t supply_pv, uint64_t borrow_pv) {
    if (supply_pv == 0) return 0;
    return (borrow_pv / supply_pv) * FACTOR_SCALE;
}

static int selftest(void) {
    uint64_t a, b, d, q1, q2, r;
    int ov;
    uint64_t vecs[][3] = {
        {100, 200, 50},
        {7, 9, 1},
        {FACTOR_SCALE, 1, 2},
        {FACTOR_SCALE, FACTOR_SCALE, FACTOR_SCALE},
        {1, FACTOR_SCALE, 2},
    };
    size_t i, n = sizeof(vecs) / sizeof(vecs[0]);
    for (i = 0; i < n; i++) {
        a = vecs[i][0];
        b = vecs[i][1];
        d = vecs[i][2];
        q1 = muldiv_i128(a, b, d);
        q2 = muldiv_limbs(a, b, d);
        if (q1 != q2) {
            fprintf(stderr, "selftest muldiv mismatch %" PRIu64 "\n", q1);
            return 1;
        }
        muldiv_limbs_qr(a, b, d, &q2, &r, &ov);
        if (!ov && ((__uint128_t)a * b) % d != r) {
            fprintf(stderr, "selftest rem mismatch\n");
            return 1;
        }
    }
    if (utilization(0, 100, muldiv_i128) != 0) return 1;
    if (utilization(FACTOR_SCALE, FACTOR_SCALE, muldiv_i128) != FACTOR_SCALE)
        return 1;
    if (utilization(2 * FACTOR_SCALE, FACTOR_SCALE, muldiv_i128) != FACTOR_SCALE / 2)
        return 1;
    if (twostep(2 * FACTOR_SCALE, FACTOR_SCALE) != 0) return 1;
    if (twostep(2 * FACTOR_SCALE, FACTOR_SCALE) ==
        utilization(2 * FACTOR_SCALE, FACTOR_SCALE, muldiv_i128))
        return 1;
    if (utilization(FACTOR_SCALE, 2 * FACTOR_SCALE, muldiv_i128) != 2 * FACTOR_SCALE)
        return 1;
    if (muldiv_i128(FACTOR_SCALE, FACTOR_SCALE, 1) != 0) return 1;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t x, y, z;
    int limbs = 0;
    uint64_t (*md)(uint64_t, uint64_t, uint64_t);
    int i;

    if (argc < 2) {
        fprintf(stderr, "usage: comet_util_c11 selftest | muldiv a b d | util supply borrow | twostep supply borrow\n");
        return 2;
    }
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) limbs = 1;
    }
    md = limbs ? muldiv_limbs : muldiv_i128;
    kind = argv[1];
    if (strcmp(kind, "selftest") == 0) return selftest();
    if (argc < 4) return 2;
    x = strtoull(argv[2], NULL, 10);
    y = strtoull(argv[3], NULL, 10);
    if (strcmp(kind, "muldiv") == 0) {
        if (argc < 5) return 2;
        z = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", md(x, y, z));
        return 0;
    }
    if (strcmp(kind, "util") == 0) {
        printf("%" PRIu64 "\n", utilization(x, y, md));
        return 0;
    }
    if (strcmp(kind, "twostep") == 0) {
        printf("%" PRIu64 "\n", twostep(x, y));
        return 0;
    }
    fprintf(stderr, "unknown kind %s\n", kind);
    return 2;
}
