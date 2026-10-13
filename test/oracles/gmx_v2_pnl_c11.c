/*
 * Independent C11 oracle for GMX V2 uncapped getPositionPnlUsd
 * (uint64 scale).
 *
 * (a*b)/d uses unsigned __int128 AND a portable 32-bit limb muldiv that
 * mirrors src/lin_gmx_v2_pnl.lin. Consensus is required before any LIN
 * comparison. This file is not linked into the LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-synthetics
 *   contracts/position/PositionUtils.sol getPositionPnlUsd
 *   contracts/price/Price.sol pickPriceForPnl
 *   contracts/utils/Calc.sol roundUpDivision
 * License of the algorithm: GPL-2.0-or-later after BUSL Change Date
 * 2026-08-31. This oracle is original C11 of the published formula, not a
 * Solidity dump.
 *
 * Kernel (uncapped; pool DataStore cap skipped):
 *   price = pickPriceForPnl(isLong, false)  // long->min, short->max
 *   value = tokens * price
 *   pnl   = isLong ? value - sizeUsd : sizeUsd - value
 *   dt    = sizeDeltaUsd==sizeUsd ? tokens
 *         : isLong ? ceil(tokens*sizeDeltaUsd/sizeUsd)
 *                  : floor(tokens*sizeDeltaUsd/sizeUsd)
 *   pnlUsd = pnl * dt / tokens     (toward-zero)
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static uint64_t mdr(uint64_t a, uint64_t b, uint64_t d, int use_limbs) {
    return use_limbs ? muldiv_rem_limbs(a, b, d) : muldiv_rem_i128(a, b, d);
}

static uint64_t pick_u(int is_long, int maximize, uint64_t pmin, uint64_t pmax) {
    if (pmin == 0 || pmax == 0 || pmax < pmin) return 0;
    if (is_long) return maximize ? pmax : pmin;
    return maximize ? pmin : pmax;
}

static uint64_t size_dt(int is_long, uint64_t tokens, uint64_t size_usd,
                        uint64_t size_delta, int use_limbs) {
    uint64_t q, r;
    if (tokens == 0 || size_usd == 0) return 0;
    if (size_delta == 0) return 0;
    if (size_delta == size_usd) return tokens;
    q = md(tokens, size_delta, size_usd, use_limbs);
    r = mdr(tokens, size_delta, size_usd, use_limbs);
    if (is_long && r != 0) {
        if (q == UINT64_MAX) return 0;
        return q + 1;
    }
    return q;
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

static int64_t pnl_u(int is_long, uint64_t tokens, uint64_t size_usd,
                     uint64_t price, int use_limbs) {
    uint64_t val;
    if (tokens == 0 || price == 0) return 0;
    val = md(tokens, price, 1, use_limbs);
    if (val > (uint64_t)INT64_MAX) return 0;
    if (is_long) return (int64_t)val - (int64_t)size_usd;
    return (int64_t)size_usd - (int64_t)val;
}

static int64_t pnl_usd(int is_long, uint64_t tokens, uint64_t size_usd,
                       uint64_t size_delta, uint64_t pmin, uint64_t pmax,
                       int maximize, int use_limbs) {
    uint64_t price, dt;
    int64_t pnl;
    if (tokens == 0 || size_usd == 0) return 0;
    price = pick_u(is_long, maximize, pmin, pmax);
    if (price == 0) return 0;
    pnl = pnl_u(is_long, tokens, size_usd, price, use_limbs);
    dt = size_dt(is_long, tokens, size_usd, size_delta, use_limbs);
    if (dt == 0) return 0;
    return smuldiv(pnl, dt, tokens, use_limbs);
}

static int64_t v1_style(uint64_t size_usd, uint64_t entry, int64_t price) {
    int64_t d;
    if (entry == 0) return 0;
    d = price - (int64_t)entry;
    return smuldiv(d, size_usd, entry, 0);
}

static int64_t naive_i64(int64_t a, int64_t b, int64_t d) {
    int64_t s;
    if (d == 0) return 0;
    s = (int64_t)((uint64_t)a * (uint64_t)b);
    return s / d;
}

static void usage(void) {
    fprintf(stderr,
            "usage: gmx_v2_pnl_c11 selftest | pick long max pmin pmax |\n"
            "  dt long tokens size sizeDelta |\n"
            "  pnl long tokens size price |\n"
            "  pnlusd long tokens size sizeDelta pmin pmax |\n"
            "  wrongmax long tokens size sizeDelta pmin pmax |\n"
            "  v1 size entry price | naive a b d [--limbs]\n");
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
        if (pick_u(1, 0, 2000, 2100) != 2000) return 1;
        if (pick_u(1, 1, 2000, 2100) != 2100) return 1;
        if (pick_u(0, 0, 2000, 2100) != 2100) return 1;
        if (pick_u(0, 1, 2000, 2100) != 2000) return 1;
        if (size_dt(1, 3, 100, 50, 0) != 2) return 1;
        if (size_dt(0, 3, 100, 50, 0) != 1) return 1;
        if (size_dt(1, 3, 100, 100, 0) != 3) return 1;
        if (pnl_u(1, 1000000ULL, 2000000000000000ULL, 2100000000ULL, 0) !=
            100000000000000LL)
            return 1;
        if (pnl_u(1, 1000000ULL, 2000000000000000ULL, 1900000000ULL, 0) !=
            -100000000000000LL)
            return 1;
        if (pnl_usd(0, 1000000ULL, 2000000000000000ULL, 2000000000000000ULL,
                    1900000000ULL, 1950000000ULL, 0, 0) != 50000000000000LL)
            return 1;
        if (pnl_usd(1, 1000000ULL, 2000000000000000ULL, 2000000000000000ULL,
                    2000000000ULL, 2100000000ULL, 0, 0) != 0)
            return 1;
        if (pnl_usd(1, 1000000ULL, 2000000000000000ULL, 2000000000000000ULL,
                    2000000000ULL, 2100000000ULL, 1, 0) != 100000000000000LL)
            return 1;
        if (pnl_u(1, 3, 3001, 1100, 0) != 299) return 1;
        if (v1_style(3001, 1000, 1100) != 300) return 1;
        if (pnl_usd(1, 3, 3000, 1500, 1100, 1100, 0, 0) != 200) return 1;
        if (md(7000000000ULL, 2000000000ULL, 1000000ULL, 0) != 14000000000000ULL)
            return 1;
        if (md(7000000000ULL, 2000000000ULL, 1000000ULL, 1) != 14000000000000ULL)
            return 1;
        if (naive_i64(7000000000LL, 2000000000LL, 1000000LL) == 14000000000000LL)
            return 1;
        printf("PASS\n");
        return 0;
    }
    if (strcmp(argv[1], "pick") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               pick_u(atoi(argv[2]), atoi(argv[3]), (uint64_t)atoll(argv[4]),
                      (uint64_t)atoll(argv[5])));
        return 0;
    }
    if (strcmp(argv[1], "dt") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               size_dt(atoi(argv[2]), (uint64_t)atoll(argv[3]),
                       (uint64_t)atoll(argv[4]), (uint64_t)atoll(argv[5]),
                       use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "pnl") == 0 && argc >= 6) {
        printf("%" PRId64 "\n",
               pnl_u(atoi(argv[2]), (uint64_t)atoll(argv[3]),
                     (uint64_t)atoll(argv[4]), (uint64_t)atoll(argv[5]),
                     use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "pnlusd") == 0 && argc >= 8) {
        printf("%" PRId64 "\n",
               pnl_usd(atoi(argv[2]), (uint64_t)atoll(argv[3]),
                       (uint64_t)atoll(argv[4]), (uint64_t)atoll(argv[5]),
                       (uint64_t)atoll(argv[6]), (uint64_t)atoll(argv[7]), 0,
                       use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "wrongmax") == 0 && argc >= 8) {
        printf("%" PRId64 "\n",
               pnl_usd(atoi(argv[2]), (uint64_t)atoll(argv[3]),
                       (uint64_t)atoll(argv[4]), (uint64_t)atoll(argv[5]),
                       (uint64_t)atoll(argv[6]), (uint64_t)atoll(argv[7]), 1,
                       use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "v1") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               v1_style((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                        atoll(argv[4])));
        return 0;
    }
    if (strcmp(argv[1], "naive") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               naive_i64(atoll(argv[2]), atoll(argv[3]), atoll(argv[4])));
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               md((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                  (uint64_t)atoll(argv[4]), use_limbs));
        return 0;
    }
    usage();
    return 2;
}
