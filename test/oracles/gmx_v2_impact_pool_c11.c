/*
 * Independent C11 oracle for GMX V2
 * capPositiveImpactUsdByPositionImpactPool / getMaxLendableUsdAvailable
 * (uint64 scale, signed impact). (a*b)/d uses unsigned __int128 AND a
 * portable 32-bit limb muldiv that mirrors src/lin_gmx_v2_impact_pool.lin.
 * Consensus is required before any LIN comparison. This file is not linked
 * into the LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-synthetics
 *   contracts/market/MarketUtils.sol capPositiveImpactUsdByPositionImpactPool
 *   getMaxLendableUsdAvailable
 *   contracts/utils/Precision.sol applyFactor
 * License of the algorithm: GPL-2.0-or-later after BUSL Change Date
 * 2026-08-31. This oracle is original C11 of the published formula, not a
 * Solidity dump.
 *
 * Kernel (FLOAT' = 1e6):
 *   impact <= 0 -> impact
 *   avail = min(applyFactor(poolUsd, factor), configUsd) - lentUsd
 *           (0 if lentUsd > that cap)
 *   if impact <= impactPoolUsd -> impact
 *   need = impact - impactPoolUsd
 *   if need > avail -> impactPoolUsd + avail else impact
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FLOAT_P 1000000ULL

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

static uint64_t md(uint64_t a, uint64_t b, uint64_t d, int use_limbs) {
    return use_limbs ? muldiv_limbs(a, b, d) : muldiv_i128(a, b, d);
}

static uint64_t apply_u(uint64_t v, uint64_t f, int use_limbs) {
    return md(v, f, FLOAT_P, use_limbs);
}

static uint64_t max_lendable_u(uint64_t poolUsd, uint64_t factor,
                              uint64_t configUsd, uint64_t lentUsd,
                              int use_limbs) {
    uint64_t mx = apply_u(poolUsd, factor, use_limbs);
    if (mx > configUsd) mx = configUsd;
    if (lentUsd > mx) return 0;
    return mx - lentUsd;
}

static int64_t cap_u(int64_t impact, uint64_t impactPoolUsd, uint64_t poolUsd,
                     uint64_t factor, uint64_t configUsd, uint64_t lentUsd,
                     int use_limbs) {
    uint64_t avail, need;
    if (impact <= 0) return impact;
    avail = max_lendable_u(poolUsd, factor, configUsd, lentUsd, use_limbs);
    if ((uint64_t)impact <= impactPoolUsd) return impact;
    need = (uint64_t)impact - impactPoolUsd;
    if (need > avail) return (int64_t)(impactPoolUsd + avail);
    return impact;
}

static int64_t wrong_uncapped_u(int64_t impact, uint64_t impactPoolUsd,
                                uint64_t poolUsd, uint64_t factor,
                                uint64_t configUsd, uint64_t lentUsd,
                                int use_limbs) {
    (void)impactPoolUsd; (void)poolUsd; (void)factor;
    (void)configUsd; (void)lentUsd; (void)use_limbs;
    return impact;
}

static int64_t wrong_pool_only_u(int64_t impact, uint64_t impactPoolUsd,
                                 uint64_t poolUsd, uint64_t factor,
                                 uint64_t configUsd, uint64_t lentUsd,
                                 int use_limbs) {
    (void)poolUsd; (void)factor; (void)configUsd;
    (void)lentUsd; (void)use_limbs;
    if (impact <= 0) return impact;
    if ((uint64_t)impact > impactPoolUsd) return (int64_t)impactPoolUsd;
    return impact;
}

static int64_t wrong_noconfig_u(int64_t impact, uint64_t impactPoolUsd,
                                uint64_t poolUsd, uint64_t factor,
                                uint64_t configUsd, uint64_t lentUsd,
                                int use_limbs) {
    (void)configUsd;
    return cap_u(impact, impactPoolUsd, poolUsd, factor, INT64_MAX,
                 lentUsd, use_limbs);
}

static int64_t wrong_nolent_u(int64_t impact, uint64_t impactPoolUsd,
                              uint64_t poolUsd, uint64_t factor,
                              uint64_t configUsd, uint64_t lentUsd,
                              int use_limbs) {
    (void)lentUsd;
    return cap_u(impact, impactPoolUsd, poolUsd, factor, configUsd, 0,
                 use_limbs);
}

static int64_t wrong_size_u(int64_t impact, uint64_t size, uint64_t factor,
                            int use_limbs) {
    uint64_t maxv;
    if (impact <= 0) return impact;
    maxv = apply_u(size, factor, use_limbs);
    if (impact > (int64_t)maxv) return (int64_t)maxv;
    return impact;
}

static int64_t wrong_abs_u(int64_t impact, uint64_t impactPoolUsd,
                           uint64_t poolUsd, uint64_t factor,
                           uint64_t configUsd, uint64_t lentUsd,
                           int use_limbs) {
    int64_t capv;
    uint64_t avail = max_lendable_u(poolUsd, factor, configUsd, lentUsd,
                                    use_limbs);
    capv = (int64_t)(impactPoolUsd + avail);
    if (impact < 0) {
        int64_t nmax = -capv;
        return (impact < nmax) ? nmax : impact;
    }
    return (impact > capv) ? capv : impact;
}

static int64_t wrong_factor0_stay_u(int64_t impact, uint64_t impactPoolUsd,
                                    uint64_t poolUsd, uint64_t factor,
                                    uint64_t configUsd, uint64_t lentUsd,
                                    int use_limbs) {
    if (factor == 0) return impact;
    return cap_u(impact, impactPoolUsd, poolUsd, factor, configUsd, lentUsd,
                 use_limbs);
}

static int64_t wrong_long_u(int64_t impact, uint64_t impactPoolUsd,
                            uint64_t longUsd, uint64_t factor,
                            uint64_t configUsd, uint64_t lentUsd,
                            int use_limbs) {
    return cap_u(impact, impactPoolUsd, longUsd, factor, configUsd, lentUsd,
                 use_limbs);
}

static int64_t naive_i64(int64_t a, int64_t b, int64_t d) {
    int64_t s;
    if (d == 0) return 0;
    s = (int64_t)((uint64_t)a * (uint64_t)b);
    return s / d;
}

static int selftest(void) {
    int limb;
    for (limb = 0; limb < 2; limb++) {
        if (md(100, 200, 50, limb) != 400) return 1;
        if (cap_u(200000000, 100000000, 200000000, 250000, 1000000000, 0,
                  limb) != 150000000)
            return 1;
        if (wrong_uncapped_u(200000000, 100000000, 200000000, 250000,
                             1000000000, 0, limb) != 200000000)
            return 1;
        if (wrong_pool_only_u(200000000, 100000000, 200000000, 250000,
                              1000000000, 0, limb) != 100000000)
            return 1;
        if (wrong_size_u(200000000, 200000000, 250000, limb) != 50000000)
            return 1;
        if (cap_u(80000000, 100000000, 200000000, 250000, 1000000000, 0,
                  limb) != 80000000)
            return 1;
        if (cap_u(140000000, 100000000, 200000000, 250000, 1000000000, 0,
                  limb) != 140000000)
            return 1;
        if (cap_u(150000000, 100000000, 200000000, 250000, 1000000000, 0,
                  limb) != 150000000)
            return 1;
        if (cap_u(200000000, 100000000, 200000000, 500000, 40000000, 0,
                  limb) != 140000000)
            return 1;
        if (wrong_noconfig_u(200000000, 100000000, 200000000, 500000, 40000000,
                             0, limb) != 200000000)
            return 1;
        if (cap_u(200000000, 100000000, 200000000, 500000, 100000000, 80000000,
                  limb) != 120000000)
            return 1;
        if (wrong_nolent_u(200000000, 100000000, 200000000, 500000, 100000000,
                           80000000, limb) != 200000000)
            return 1;
        if (cap_u(200000000, 100000000, 200000000, 500000, 100000000, 150000000,
                  limb) != 100000000)
            return 1;
        if (cap_u(-200000000, 100000000, 200000000, 250000, 1000000000, 0,
                  limb) != -200000000)
            return 1;
        if (wrong_abs_u(-200000000, 100000000, 200000000, 250000, 1000000000, 0,
                        limb) != -150000000)
            return 1;
        if (cap_u(100000000, 0, 0, 0, 0, 0, limb) != 0) return 1;
        if (cap_u(200000000, 100000000, 200000000, 0, 1000000000, 0, limb) !=
            100000000)
            return 1;
        if (wrong_factor0_stay_u(200000000, 100000000, 200000000, 0, 1000000000,
                                 0, limb) != 200000000)
            return 1;
        if (wrong_long_u(200000000, 100000000, 100000000, 250000, 1000000000, 0,
                         limb) != 125000000)
            return 1;
        if (max_lendable_u(200000000, 250000, 1000000000, 0, limb) != 50000000)
            return 1;
        if (md(7000000000ULL, 2000000000ULL, 1000000ULL, limb) !=
            14000000000000ULL)
            return 1;
    }
    if (naive_i64(7000000000LL, 2000000000LL, 1000000LL) == 14000000000000LL)
        return 1;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    int use_limbs = 0;
    int i;
    int64_t impact;
    uint64_t a, b, c, d, e;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) use_limbs = 1;
    }
    if (argc < 2) return 2;
    if (strcmp(argv[1], "selftest") == 0) return selftest();
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
    if (strcmp(argv[1], "size") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               wrong_size_u(atoll(argv[2]), (uint64_t)atoll(argv[3]),
                            (uint64_t)atoll(argv[4]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "lendable") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               max_lendable_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                              (uint64_t)atoll(argv[4]), (uint64_t)atoll(argv[5]),
                              use_limbs));
        return 0;
    }
    if (argc < 8) return 2;
    impact = atoll(argv[2]);
    a = (uint64_t)atoll(argv[3]);
    b = (uint64_t)atoll(argv[4]);
    c = (uint64_t)atoll(argv[5]);
    d = (uint64_t)atoll(argv[6]);
    e = (uint64_t)atoll(argv[7]);
    if (strcmp(argv[1], "cap") == 0) {
        printf("%" PRId64 "\n", cap_u(impact, a, b, c, d, e, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wronguncapped") == 0) {
        printf("%" PRId64 "\n",
               wrong_uncapped_u(impact, a, b, c, d, e, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongpool") == 0) {
        printf("%" PRId64 "\n",
               wrong_pool_only_u(impact, a, b, c, d, e, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongnoconfig") == 0) {
        printf("%" PRId64 "\n",
               wrong_noconfig_u(impact, a, b, c, d, e, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongnolent") == 0) {
        printf("%" PRId64 "\n",
               wrong_nolent_u(impact, a, b, c, d, e, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongabs") == 0) {
        printf("%" PRId64 "\n", wrong_abs_u(impact, a, b, c, d, e, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongstay") == 0) {
        printf("%" PRId64 "\n",
               wrong_factor0_stay_u(impact, a, b, c, d, e, use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wronglong") == 0) {
        printf("%" PRId64 "\n", wrong_long_u(impact, a, b, c, d, e, use_limbs));
        return 0;
    }
    return 2;
}
