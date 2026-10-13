/*
 * Independent C11 oracle for GMX V2 getCappedPnl (uint64 scale).
 *
 * (a*b)/d uses unsigned __int128 AND a portable 32-bit limb muldiv that
 * mirrors src/lin_gmx_v2_capped_pnl.lin. Consensus is required before any
 * LIN comparison. This file is not linked into the LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-synthetics
 *   contracts/market/MarketUtils.sol getCappedPnl
 *   contracts/utils/Precision.sol applyFactor
 *   contracts/data/Keys.sol MAX_PNL_FACTOR_FOR_TRADERS
 *   contracts/position/PositionUtils.sol trader mulDiv after pool cap
 * License of the algorithm: GPL-2.0-or-later after BUSL Change Date
 * 2026-08-31. This oracle is original C11 of the published formula, not a
 * Solidity dump.
 *
 * Kernel (FLOAT' = 1e6, not FLOAT_PRECISION=1e30):
 *   maxPnl = poolUsd * factor / FLOAT'
 *   getCappedPnl: pnl < 0 ? pnl : (pnl > maxPnl ? maxPnl : pnl)
 *   trader scale (getPositionPnlUsd): if trader>0 and
 *     capped!=pool && capped>0 && pool>0 then trader * capped / pool
 *     else trader (zero-factor does NOT zero trader PnL)
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

static uint64_t md(uint64_t a, uint64_t b, uint64_t d, int use_limbs) {
    return use_limbs ? muldiv_limbs(a, b, d) : muldiv_i128(a, b, d);
}

static int64_t smuldiv(int64_t a, uint64_t b, uint64_t d, int use_limbs) {
    int neg = 0;
    uint64_t aa;
    uint64_t q;
    if (a < 0) {
        neg = 1;
        aa = (uint64_t)(-(a + 1)) + 1ULL;
    } else {
        aa = (uint64_t)a;
    }
    q = md(aa, b, d, use_limbs);
    if (q > (uint64_t)INT64_MAX) return 0;
    return neg ? -(int64_t)q : (int64_t)q;
}

static uint64_t apply_u(uint64_t pool_usd, uint64_t factor, int use_limbs) {
    return md(pool_usd, factor, FLOAT_P, use_limbs);
}

static int64_t capped_u(int64_t pnl, uint64_t pool_usd, uint64_t factor,
                        int use_limbs) {
    int64_t maxp;
    if (pnl < 0) return pnl;
    maxp = (int64_t)apply_u(pool_usd, factor, use_limbs);
    return pnl > maxp ? maxp : pnl;
}

static int64_t wrong_sym(int64_t pnl, uint64_t pool_usd, uint64_t factor,
                         int use_limbs) {
    int64_t maxp = (int64_t)apply_u(pool_usd, factor, use_limbs);
    if (pnl < 0) {
        int64_t neg = -pnl;
        return neg > maxp ? -maxp : pnl;
    }
    return pnl > maxp ? maxp : pnl;
}

static int64_t wrong_pos(int64_t trader, uint64_t pool_usd, uint64_t factor,
                         int use_limbs) {
    int64_t maxp;
    if (trader <= 0) return trader;
    maxp = (int64_t)apply_u(pool_usd, factor, use_limbs);
    return trader > maxp ? maxp : trader;
}

static int64_t trader_u(int64_t trader, int64_t pool_pnl, uint64_t pool_usd,
                        uint64_t factor, int use_limbs) {
    int64_t capped;
    if (trader <= 0) return trader;
    capped = capped_u(pool_pnl, pool_usd, factor, use_limbs);
    if (capped == pool_pnl) return trader;
    if (capped <= 0) return trader;
    if (pool_pnl <= 0) return trader;
    return smuldiv(trader, (uint64_t)capped, (uint64_t)pool_pnl, use_limbs);
}

static int64_t naive_i64(int64_t a, int64_t b, int64_t d) {
    int64_t s;
    if (d == 0) return 0;
    s = (int64_t)((uint64_t)a * (uint64_t)b);
    return s / d;
}

static void usage(void) {
    fprintf(stderr,
            "usage: gmx_v2_capped_pnl_c11 selftest | apply pool factor |\n"
            "  capped pnl pool factor | wrongsym pnl pool factor |\n"
            "  wrongpos trader pool factor |\n"
            "  trader traderPnl poolPnl pool factor |\n"
            "  muldiv a b d | naive a b d [--limbs]\n");
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
        if (apply_u(200000000ULL, 500000ULL, 0) != 100000000ULL) return 1;
        if (apply_u(200000000ULL, 500000ULL, 1) != 100000000ULL) return 1;
        if (capped_u(150000000LL, 200000000ULL, 500000ULL, 0) != 100000000LL)
            return 1;
        if (capped_u(50000000LL, 200000000ULL, 500000ULL, 0) != 50000000LL)
            return 1;
        if (capped_u(100000000LL, 200000000ULL, 500000ULL, 0) != 100000000LL)
            return 1;
        if (capped_u(-200000000LL, 200000000ULL, 500000ULL, 0) != -200000000LL)
            return 1;
        if (wrong_sym(-200000000LL, 200000000ULL, 500000ULL, 0) != -100000000LL)
            return 1;
        if (trader_u(150000000LL, 300000000LL, 200000000ULL, 500000ULL, 0) !=
            50000000LL)
            return 1;
        if (wrong_pos(150000000LL, 200000000ULL, 500000ULL, 0) != 100000000LL)
            return 1;
        if (capped_u(150000000LL, 200000000ULL, 0, 0) != 0) return 1;
        if (trader_u(150000000LL, 300000000LL, 200000000ULL, 0, 0) !=
            150000000LL)
            return 1;
        if (trader_u(50000000LL, 80000000LL, 200000000ULL, 500000ULL, 0) !=
            50000000LL)
            return 1;
        if (md(7000000000ULL, 2000000000ULL, 1000000ULL, 0) != 14000000000000ULL)
            return 1;
        if (md(7000000000ULL, 2000000000ULL, 1000000ULL, 1) != 14000000000000ULL)
            return 1;
        if (apply_u(7000000000ULL, 2000000000ULL, 0) != 14000000000000ULL)
            return 1;
        if (naive_i64(7000000000LL, 2000000000LL, 1000000LL) == 14000000000000LL)
            return 1;
        printf("PASS\n");
        return 0;
    }
    if (strcmp(argv[1], "apply") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               apply_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                       use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "capped") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               capped_u(atoll(argv[2]), (uint64_t)atoll(argv[3]),
                        (uint64_t)atoll(argv[4]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongsym") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               wrong_sym(atoll(argv[2]), (uint64_t)atoll(argv[3]),
                         (uint64_t)atoll(argv[4]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongpos") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               wrong_pos(atoll(argv[2]), (uint64_t)atoll(argv[3]),
                         (uint64_t)atoll(argv[4]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "trader") == 0 && argc >= 6) {
        printf("%" PRId64 "\n",
               trader_u(atoll(argv[2]), atoll(argv[3]), (uint64_t)atoll(argv[4]),
                        (uint64_t)atoll(argv[5]), use_limbs));
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
