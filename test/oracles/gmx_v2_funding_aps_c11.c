/*
 * Independent C11 oracle for GMX V2 getNextFundingAmountPerSize
 * (uint64 scale). (a*b)/d uses unsigned __int128 AND a portable 32-bit
 * limb muldiv that mirrors src/lin_gmx_v2_funding_aps.lin. Consensus is
 * required before any LIN comparison. This file is not linked into the
 * LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-synthetics
 *   contracts/market/MarketUtils.sol getNextFundingAmountPerSize
 *   contracts/market/MarketUtils.sol getFundingAmountPerSizeDelta
 *   contracts/market/MarketUtils.sol getPoolDivisor
 *   contracts/utils/Precision.sol applyFactor / FLOAT_PRECISION_SQRT
 * License of the algorithm: GPL-2.0-or-later after BUSL Change Date
 * 2026-08-31. This oracle is original C11 of the published formula, not a
 * Solidity dump.
 *
 * Kernel (FLOAT' = 1e6, SQRT' = 1e3, STORE' = 1e9; not FLOAT=1e30):
 *   if longOI==0 || shortOI==0: fundingUsd = 0
 *   size = longsPayShorts ? longOI : shortOI
 *   fundingUsd = size * duration * fps / FLOAT' / divisor
 *   divisor = sameToken ? 2 : 1
 *   split = fundingUsd * colOI / payingOI
 *   aps = (fundingUsd * STORE' / OI) / price  (round-up on fee path)
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FLOAT_P 1000000ULL
#define STORE_P 1000000000ULL

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

static uint64_t muldiv_rem_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return r;
}

static uint64_t md(uint64_t a, uint64_t b, uint64_t d, int use_limbs) {
    return use_limbs ? muldiv_limbs(a, b, d) : muldiv_i128(a, b, d);
}

static uint64_t md_rem(uint64_t a, uint64_t b, uint64_t d, int use_limbs) {
    return use_limbs ? muldiv_rem_limbs(a, b, d) : muldiv_rem_i128(a, b, d);
}

static uint64_t md_up(uint64_t a, uint64_t b, uint64_t d, int use_limbs) {
    uint64_t q = md(a, b, d, use_limbs);
    uint64_t r = md_rem(a, b, d, use_limbs);
    if (r == 0) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1;
}

static uint64_t div_up(uint64_t a, uint64_t b) {
    uint64_t q;
    if (b == 0 || a == 0) return 0;
    q = a / b;
    if (a == q * b) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1;
}

static uint64_t divisor_u(int same_token) { return same_token ? 2ULL : 1ULL; }

static uint64_t paying_u(uint64_t long_oi, uint64_t short_oi, int longs_pay) {
    return longs_pay ? long_oi : short_oi;
}

static uint64_t funding_u(uint64_t long_oi, uint64_t short_oi, int longs_pay,
                          uint64_t duration, uint64_t fps, int same_token,
                          int use_limbs) {
    uint64_t size, rate, raw;
    if (long_oi == 0 || short_oi == 0) return 0;
    size = paying_u(long_oi, short_oi, longs_pay);
    rate = md(duration, fps, 1, use_limbs);
    raw = md(size, rate, FLOAT_P, use_limbs);
    return md(raw, 1, divisor_u(same_token), use_limbs);
}

static uint64_t wrong_zero_u(uint64_t long_oi, uint64_t short_oi, int longs_pay,
                             uint64_t duration, uint64_t fps, int same_token,
                             int use_limbs) {
    uint64_t size, rate, raw;
    size = paying_u(long_oi, short_oi, longs_pay);
    if (size == 0) return 0;
    rate = md(duration, fps, 1, use_limbs);
    raw = md(size, rate, FLOAT_P, use_limbs);
    return md(raw, 1, divisor_u(same_token), use_limbs);
}

static uint64_t wrong_nofps_u(uint64_t long_oi, uint64_t short_oi, int longs_pay,
                              uint64_t duration, uint64_t fps, int same_token,
                              int use_limbs) {
    uint64_t size, raw;
    (void)fps;
    if (long_oi == 0 || short_oi == 0) return 0;
    size = paying_u(long_oi, short_oi, longs_pay);
    raw = md(size, duration, FLOAT_P, use_limbs);
    return md(raw, 1, divisor_u(same_token), use_limbs);
}

static uint64_t wrong_nodiv_u(uint64_t long_oi, uint64_t short_oi, int longs_pay,
                              uint64_t duration, uint64_t fps, int same_token,
                              int use_limbs) {
    uint64_t size, rate;
    (void)same_token;
    if (long_oi == 0 || short_oi == 0) return 0;
    size = paying_u(long_oi, short_oi, longs_pay);
    rate = md(duration, fps, 1, use_limbs);
    return md(size, rate, FLOAT_P, use_limbs);
}

static uint64_t split_u(uint64_t funding, uint64_t col_oi, uint64_t total_oi,
                        int use_limbs) {
    if (total_oi == 0) return 0;
    return md(funding, col_oi, total_oi, use_limbs);
}

static uint64_t aps_u(uint64_t funding, uint64_t oi, uint64_t price,
                      int round_up, int use_limbs) {
    uint64_t fpsz;
    if (funding == 0 || oi == 0 || price == 0) return 0;
    if (round_up) {
        fpsz = md_up(funding, STORE_P, oi, use_limbs);
        return div_up(fpsz, price);
    }
    fpsz = md(funding, STORE_P, oi, use_limbs);
    return fpsz / price;
}

static int64_t naive_i64(int64_t a, int64_t b, int64_t d) {
    int64_t s;
    if (d == 0) return 0;
    s = (int64_t)((uint64_t)a * (uint64_t)b);
    return s / d;
}

static void usage(void) {
    fprintf(stderr,
            "usage: gmx_v2_funding_aps_c11 selftest |\n"
            "  funding long short longsPay dur fps same |\n"
            "  wrongzero ... | wrongnofps ... | wrongnodiv ... |\n"
            "  split fund col total | aps fund oi price roundUp |\n"
            "  muldiv a b d | naive a b d [--limbs]\n");
}

static int six(char **argv, int argc) {
    return argc >= 8;
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
        if (md(100, 200, 50, 0) != 400) return 1;
        if (md(100, 200, 50, 1) != 400) return 1;
        if (muldiv_rem_i128(7, 9, 2) != 1) return 1;
        if (funding_u(200000000ULL, 100000000ULL, 1, 4000, 10, 0, 0) != 8000000ULL)
            return 1;
        if (funding_u(200000000ULL, 100000000ULL, 1, 4000, 10, 1, 0) != 4000000ULL)
            return 1;
        if (funding_u(200000000ULL, 100000000ULL, 1, 4000, 10, 1, 1) != 4000000ULL)
            return 1;
        if (wrong_nodiv_u(200000000ULL, 100000000ULL, 1, 4000, 10, 1, 0) !=
            8000000ULL)
            return 1;
        if (funding_u(0, 100000000ULL, 0, 4000, 10, 0, 0) != 0) return 1;
        if (wrong_zero_u(0, 100000000ULL, 0, 4000, 10, 0, 0) != 4000000ULL)
            return 1;
        if (funding_u(200000000ULL, 100000000ULL, 0, 4000, 10, 0, 0) != 4000000ULL)
            return 1;
        if (wrong_nofps_u(200000000ULL, 100000000ULL, 1, 4000, 10, 0, 0) !=
            800000ULL)
            return 1;
        if (split_u(500, 1000, 5000, 0) != 100) return 1;
        if (split_u(500, 4000, 5000, 0) != 400) return 1;
        if (aps_u(100, 10000, 2000, 1, 0) != 5000) return 1;
        if (aps_u(100, 5000, 2000, 0, 0) != 10000) return 1;
        if (aps_u(1, 3, 2, 0, 0) != 166666666ULL) return 1;
        if (aps_u(1, 3, 2, 1, 0) != 166666667ULL) return 1;
        if (aps_u(1, 3, 2, 1, 1) != 166666667ULL) return 1;
        if (aps_u(0, 10000, 2000, 1, 0) != 0) return 1;
        if (md(7000000000ULL, 2000000000ULL, 1000000ULL, 0) != 14000000000000ULL)
            return 1;
        if (md(7000000000ULL, 2000000000ULL, 1000000ULL, 1) != 14000000000000ULL)
            return 1;
        if (naive_i64(7000000000LL, 2000000000LL, 1000000LL) == 14000000000000LL)
            return 1;
        printf("PASS\n");
        return 0;
    }
    if (strcmp(argv[1], "funding") == 0 && six(argv, argc)) {
        printf("%" PRIu64 "\n",
               funding_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                         atoi(argv[4]), (uint64_t)atoll(argv[5]),
                         (uint64_t)atoll(argv[6]), atoi(argv[7]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongzero") == 0 && six(argv, argc)) {
        printf("%" PRIu64 "\n",
               wrong_zero_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                            atoi(argv[4]), (uint64_t)atoll(argv[5]),
                            (uint64_t)atoll(argv[6]), atoi(argv[7]),
                            use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongnofps") == 0 && six(argv, argc)) {
        printf("%" PRIu64 "\n",
               wrong_nofps_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                             atoi(argv[4]), (uint64_t)atoll(argv[5]),
                             (uint64_t)atoll(argv[6]), atoi(argv[7]),
                             use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongnodiv") == 0 && six(argv, argc)) {
        printf("%" PRIu64 "\n",
               wrong_nodiv_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                             atoi(argv[4]), (uint64_t)atoll(argv[5]),
                             (uint64_t)atoll(argv[6]), atoi(argv[7]),
                             use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "split") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               split_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                       (uint64_t)atoll(argv[4]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "aps") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               aps_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                     (uint64_t)atoll(argv[4]), atoi(argv[5]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               md((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                  (uint64_t)atoll(argv[4]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "naive") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               naive_i64(atoll(argv[2]), atoll(argv[3]), atoll(argv[4])));
        return 0;
    }
    usage();
    return 2;
}
