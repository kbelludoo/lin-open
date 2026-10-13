/*
 * Independent C11 oracle for Compound III accrualDescaleFactor /
 * baseTrackingAccrued (uint64 scale).
 *
 * (a*b)/d uses unsigned __int128 AND a portable 32-bit limb muldiv that
 * mirrors src/lin_comet_descale.lin. Consensus is required before any LIN
 * comparison. This file is not linked into the LIN compiler TCB.
 *
 * Upstream: compound-finance/comet
 *   contracts/CometWithExtendedAssetList.sol updateBasePrincipal
 *   contracts/CometCore.sol BASE_ACCRUAL_SCALE=1e6
 * License of the algorithm: GPL-2.0-or-later after BUSL Change Date
 * 2025-12-31. This oracle is original C11 of the published formula, not a
 * Solidity dump.
 *
 * Kernel: factor = baseScale / 1e6 (0 if baseScale < 1e6);
 * accrued = (principal * indexDelta / trackingIndexScale) / factor
 * left-associative, matching Solidity. tscale*factor can be 1e27 (WETH)
 * and does not fit uint64, so the two-step divide is mandatory.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BASE_ACCRUAL 1000000ULL
#define WAD 1000000000000000000ULL

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

static uint64_t factor_u(uint64_t base_scale, int use_limbs) {
    if (base_scale < BASE_ACCRUAL) return 0;
    return use_limbs ? muldiv_limbs(base_scale, 1, BASE_ACCRUAL)
                     : muldiv_i128(base_scale, 1, BASE_ACCRUAL);
}

static uint64_t accrued_u(uint64_t principal, uint64_t index_delta,
                          uint64_t tracking_scale, uint64_t base_scale,
                          int use_limbs) {
    uint64_t f, step;
    if (principal == 0 || tracking_scale == 0) return 0;
    f = factor_u(base_scale, use_limbs);
    if (f == 0) return 0;
    step = use_limbs ? muldiv_limbs(principal, index_delta, tracking_scale)
                     : muldiv_i128(principal, index_delta, tracking_scale);
    return use_limbs ? muldiv_limbs(step, 1, f) : muldiv_i128(step, 1, f);
}

static int64_t naive_i64(int64_t principal, int64_t index_delta,
                         int64_t tracking_scale, uint64_t base_scale) {
    uint64_t f;
    int64_t s;
    if (tracking_scale == 0) return 0;
    f = factor_u(base_scale, 0);
    if (f == 0) return 0;
    s = (int64_t)((uint64_t)principal * (uint64_t)index_delta);
    return (s / tracking_scale) / (int64_t)f;
}

static void usage(void) {
    fprintf(stderr,
            "usage: comet_descale_c11 selftest | factor scale |\n"
            "  accrued prin dindex tscale base |\n"
            "  forget prin dindex tscale | gmxup amt base |\n"
            "  naive prin dindex tscale base [--limbs]\n");
}

int main(int argc, char **argv) {
    int use_limbs = 0;
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) use_limbs = 1;
    }
    if (argc < 2) {
        usage();
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        if (factor_u(1000000ULL, 0) != 1ULL) return 1;
        if (factor_u(1000000000000000000ULL, 0) != 1000000000000ULL) return 1;
        if (factor_u(100000000ULL, 1) != 100ULL) return 1;
        if (factor_u(10000ULL, 0) != 0) return 1;
        if (accrued_u(1000000ULL, 1000000000000000ULL, 1000000000000000ULL,
                      1000000ULL, 0) != 1000000ULL)
            return 1;
        if (accrued_u(1000000ULL, 1000000000000000ULL, 1000000000000000ULL,
                      1000000ULL, 1) != 1000000ULL)
            return 1;
        if (accrued_u(1000000000000000000ULL, 1000000000000000ULL,
                      1000000000000000ULL, 1000000000000000000ULL,
                      0) != 1000000ULL)
            return 1;
        if (accrued_u(1000000000000000000ULL, 1000000000000000ULL,
                      1000000000000000ULL, 1000000000000000000ULL,
                      1) != 1000000ULL)
            return 1;
        if (accrued_u(1000000ULL, 1000000000000000ULL, 1000000000000000ULL,
                      1000000000000000000ULL, 0) != 0)
            return 1;
        if (accrued_u(100000000ULL, 1000000000000000ULL, 1000000000000000ULL,
                      100000000ULL, 0) != 1000000ULL)
            return 1;
        if (accrued_u(5000000000ULL, 10000000000ULL, 1000000ULL, 1000000ULL,
                      0) != 50000000000000ULL)
            return 1;
        if (naive_i64(5000000000LL, 10000000000LL, 1000000LL, 1000000ULL) ==
            50000000000000LL)
            return 1;
        if (muldiv_i128(100, 200, 50) != 400) return 1;
        if (muldiv_limbs(100, 200, 50) != 400) return 1;
        if (muldiv_rem_i128(7, 9, 2) != 1) return 1;
        printf("PASS\n");
        return 0;
    }
    if (strcmp(argv[1], "factor") == 0 && argc >= 3) {
        printf("%" PRIu64 "\n", factor_u((uint64_t)atoll(argv[2]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "accrued") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               accrued_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                         (uint64_t)atoll(argv[4]), (uint64_t)atoll(argv[5]),
                         use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "forget") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               muldiv_i128((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                           (uint64_t)atoll(argv[4])));
        return 0;
    }
    if (strcmp(argv[1], "gmxup") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               muldiv_i128((uint64_t)atoll(argv[2]), WAD, (uint64_t)atoll(argv[3])));
        return 0;
    }
    if (strcmp(argv[1], "naive") == 0 && argc >= 6) {
        printf("%" PRId64 "\n",
               naive_i64(atoll(argv[2]), atoll(argv[3]), atoll(argv[4]),
                         (uint64_t)atoll(argv[5])));
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        uint64_t a = (uint64_t)atoll(argv[2]);
        uint64_t b = (uint64_t)atoll(argv[3]);
        uint64_t d = (uint64_t)atoll(argv[4]);
        printf("%" PRIu64 "\n", use_limbs ? muldiv_limbs(a, b, d) : muldiv_i128(a, b, d));
        return 0;
    }
    usage();
    return 2;
}
