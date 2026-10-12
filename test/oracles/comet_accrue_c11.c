/*
 * Independent C11 oracle for Compound III accruedInterestIndices math
 * (uint64 scale, per-second index update).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_comet_accrue.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: compound-finance/comet
 *   contracts/CometWithExtendedAssetList.sol (accruedInterestIndices,
 *   getSupplyRate, getBorrowRate, mulFactor, getUtilization)
 *   contracts/CometCore.sol (SECONDS_PER_YEAR=31536000, FACTOR_SCALE=1e18,
 *   BASE_INDEX_SCALE=1e15)
 * Algorithm license: BUSL-1.1 Change Date 2025-12-31 elapsed;
 * Change License GPL-2.0-or-later. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FACTOR_SCALE 1000000000000000000ULL
#define INDEX_SCALE 1000000000000000ULL
#define SECONDS_PER_YEAR 31536000ULL
#define BLOCKS_PER_YEAR 2102400ULL

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static int ov_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 1;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    return q > UINT64_MAX;
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

static int ov_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return ov;
}

static int rate_time_ok(uint64_t rate, uint64_t dt, int (*ov)(uint64_t, uint64_t, uint64_t)) {
    if (rate == 0 || dt == 0) return 1;
    return ov(rate, dt, 1) ? 0 : 1;
}

static uint64_t mul_factor(uint64_t n, uint64_t factor,
                          uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    return md(n, factor, FACTOR_SCALE);
}

static uint64_t delta(uint64_t index, uint64_t rate, uint64_t dt,
                     uint64_t (*md)(uint64_t, uint64_t, uint64_t),
                     int (*ov)(uint64_t, uint64_t, uint64_t)) {
    uint64_t rt;
    if (!rate_time_ok(rate, dt, ov)) return 0;
    rt = md(rate, dt, 1);
    return mul_factor(index, rt, md);
}

static uint64_t delta_twostep(uint64_t index, uint64_t rate, uint64_t dt,
                             uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    return md(md(index, rate, FACTOR_SCALE), dt, 1);
}

static uint64_t accrue(uint64_t index, uint64_t rate, uint64_t dt,
                      uint64_t (*md)(uint64_t, uint64_t, uint64_t),
                      int (*ov)(uint64_t, uint64_t, uint64_t)) {
    uint64_t inc;
    if (dt == 0) return index;
    inc = delta(index, rate, dt, md, ov);
    if (index > UINT64_MAX - inc) return 0;
    return index + inc;
}

static uint64_t kink_rate(uint64_t util, uint64_t base, uint64_t slope_low,
                         uint64_t slope_high, uint64_t kink,
                         uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t add, low, high, s1;
    if (util <= kink) {
        add = mul_factor(slope_low, util, md);
        if (base > UINT64_MAX - add) return 0;
        return base + add;
    }
    low = mul_factor(slope_low, kink, md);
    high = mul_factor(slope_high, util - kink, md);
    if (base > UINT64_MAX - low) return 0;
    s1 = base + low;
    if (s1 > UINT64_MAX - high) return 0;
    return s1 + high;
}

static uint64_t utilization(uint64_t total_borrow, uint64_t total_supply,
                           uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (total_supply == 0) return 0;
    return md(total_borrow, FACTOR_SCALE, total_supply);
}

static int selftest(void) {
    int fail = 0;
    uint64_t apy = 10000000000000000ULL;
    uint64_t ps, pb, d_iii, d_bad, a50, b50, a90, b90;

    if (muldiv_i128(100, 200, 50) != 400) fail++;
    if (muldiv_i128(100, 200, 50) != muldiv_limbs(100, 200, 50)) fail++;
    if (mul_factor(FACTOR_SCALE, 500000000000000000ULL, muldiv_i128)
        != 500000000000000000ULL) fail++;
    if (utilization(500, 1000, muldiv_i128) != 500000000000000000ULL) fail++;
    if (utilization(500, 1000, muldiv_i128) != utilization(500, 1000, muldiv_limbs))
        fail++;
    if (utilization(1, 0, muldiv_i128) != 0) fail++;
    if (accrue(INDEX_SCALE, 1, 0, muldiv_i128, ov_i128) != INDEX_SCALE) fail++;
    if (delta(INDEX_SCALE, 1, 1000, muldiv_i128, ov_i128) != 1) fail++;
    if (delta_twostep(INDEX_SCALE, 1, 1000, muldiv_i128) != 0) fail++;
    if (delta(INDEX_SCALE, 1, 1000, muldiv_i128, ov_i128)
        != delta(INDEX_SCALE, 1, 1000, muldiv_limbs, ov_limbs)) fail++;

    ps = muldiv_i128(apy, 1, SECONDS_PER_YEAR);
    pb = muldiv_i128(apy, 1, BLOCKS_PER_YEAR);
    if (ps != 317097919ULL) fail++;
    if (pb != 4756468797ULL) fail++;
    d_iii = delta(INDEX_SCALE, ps, SECONDS_PER_YEAR, muldiv_i128, ov_i128);
    d_bad = delta(INDEX_SCALE, pb, SECONDS_PER_YEAR, muldiv_i128, ov_i128);
    if (d_iii != 9999999973584ULL) fail++;
    if (d_bad != 149999999982192ULL) fail++;
    if (d_iii != delta(INDEX_SCALE, ps, SECONDS_PER_YEAR, muldiv_limbs, ov_limbs))
        fail++;
    if (!(d_iii * 14ULL < d_bad && d_bad < d_iii * 16ULL)) fail++;

    a50 = kink_rate(500000000000000000ULL, 0, 100, 200, 800000000000000000ULL,
                    muldiv_i128);
    b50 = kink_rate(500000000000000000ULL, 0, 100, 200, 800000000000000000ULL,
                    muldiv_limbs);
    a90 = kink_rate(900000000000000000ULL, 1, 100, 200, 800000000000000000ULL,
                    muldiv_i128);
    b90 = kink_rate(900000000000000000ULL, 1, 100, 200, 800000000000000000ULL,
                    muldiv_limbs);
    if (a50 != 50 || a50 != b50) fail++;
    if (a90 != 101 || a90 != b90) fail++;
    if (rate_time_ok(4294967296ULL, 4294967296ULL, ov_i128) != 0) fail++;
    if (ov_i128(FACTOR_SCALE, FACTOR_SCALE, 1) != 1) fail++;
    if (muldiv_i128(FACTOR_SCALE, FACTOR_SCALE, 1) != 0) fail++;

    if (fail) {
        fprintf(stderr, "comet_accrue_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("comet_accrue_c11 selftest PASS\n");
    printf("vector.ps=%" PRIu64 "\n", ps);
    printf("vector.pb=%" PRIu64 "\n", pb);
    printf("vector.delta_iii=%" PRIu64 "\n", d_iii);
    printf("vector.delta_v2mis=%" PRIu64 "\n", d_bad);
    printf("vector.accrue_iii=%" PRIu64 "\n",
           accrue(INDEX_SCALE, ps, SECONDS_PER_YEAR, muldiv_i128, ov_i128));
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    uint64_t (*md)(uint64_t, uint64_t, uint64_t) = muldiv_i128;
    int (*ov)(uint64_t, uint64_t, uint64_t) = ov_i128;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldiv a b d | mulfactor n f | "
                "delta ix rate dt | twostep ix rate dt | accrue ix rate dt | "
                "kink util base lo hi kink | util borrow supply | "
                "apysec wad | apyblk wad\n",
                argv[0]);
        return 2;
    }
    cmd = argv[1];
    if (argc >= 3 && strcmp(argv[argc - 1], "--limbs") == 0) {
        md = muldiv_limbs;
        ov = ov_limbs;
        argc--;
    }
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "muldiv") == 0 && argc == 5) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "mulfactor") == 0 && argc == 4) {
        printf("%" PRIu64 "\n",
               mul_factor(strtoull(argv[2], NULL, 10),
                          strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "delta") == 0 && argc == 5) {
        printf("%" PRIu64 "\n",
               delta(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                     strtoull(argv[4], NULL, 10), md, ov));
        return 0;
    }
    if (strcmp(cmd, "twostep") == 0 && argc == 5) {
        printf("%" PRIu64 "\n",
               delta_twostep(strtoull(argv[2], NULL, 10),
                             strtoull(argv[3], NULL, 10),
                             strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "accrue") == 0 && argc == 5) {
        printf("%" PRIu64 "\n",
               accrue(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                      strtoull(argv[4], NULL, 10), md, ov));
        return 0;
    }
    if (strcmp(cmd, "kink") == 0 && argc == 7) {
        printf("%" PRIu64 "\n",
               kink_rate(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                         strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                         strtoull(argv[6], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "util") == 0 && argc == 4) {
        printf("%" PRIu64 "\n",
               utilization(strtoull(argv[2], NULL, 10),
                           strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "apysec") == 0 && argc == 3) {
        printf("%" PRIu64 "\n", md(strtoull(argv[2], NULL, 10), 1, SECONDS_PER_YEAR));
        return 0;
    }
    if (strcmp(cmd, "apyblk") == 0 && argc == 3) {
        printf("%" PRIu64 "\n", md(strtoull(argv[2], NULL, 10), 1, BLOCKS_PER_YEAR));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
