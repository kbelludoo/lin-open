/*
 * Independent C11 oracle for GMX V1 VaultUtils.validateLiquidation (uint64).
 * Two implementations of remaining*maxLeverage vs size*10000:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_gmx_liq.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-contracts contracts/core/VaultUtils.sol
 * Algorithm license: MIT. This oracle is original C11.
 * Kernel is remaining-after-PnL vs marginFees+liquidationFeeUsd then
 * remaining*maxLeverage < size*BASIS. Not getFundingFee, not next-rate,
 * not USDG tax-rebate, not Uniswap xy, not Solidly x3y+y3x, not Maker rpow.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BPS 10000ULL
#define FUNDING_PREC 1000000ULL

static void mul_limbs(uint64_t a, uint64_t b, uint64_t *hi_out, uint64_t *lo_out) {
    uint64_t a0 = a & 0xffffffffULL, a1 = a >> 32;
    uint64_t b0 = b & 0xffffffffULL, b1 = b >> 32;
    uint64_t p0 = a0 * b0, p1 = a0 * b1, p2 = a1 * b0, p3 = a1 * b1;
    uint64_t mid = p1 + p2;
    uint64_t mid_carry = (mid < p1) ? 1 : 0;
    uint64_t t = (mid & 0xffffffffULL) << 32;
    uint64_t lo = p0 + t;
    uint64_t lo_carry = (lo < p0) ? 1 : 0;
    uint64_t hi = p3 + (mid >> 32);
    hi = hi + (mid_carry << 32);
    hi = hi + lo_carry;
    *hi_out = hi;
    *lo_out = lo;
}

static int u128_lt(uint64_t a_hi, uint64_t a_lo, uint64_t b_hi, uint64_t b_lo) {
    if (a_hi < b_hi) return 1;
    if (a_hi > b_hi) return 0;
    return a_lo < b_lo;
}

static int lev_exceeded_i128(uint64_t remaining, uint64_t size, uint64_t max_lev) {
    __uint128_t left = (__uint128_t)remaining * (__uint128_t)max_lev;
    __uint128_t right = (__uint128_t)size * (__uint128_t)BPS;
    return left < right;
}

static int lev_exceeded_limbs(uint64_t remaining, uint64_t size, uint64_t max_lev) {
    uint64_t a_hi, a_lo, b_hi, b_lo;
    mul_limbs(remaining, max_lev, &a_hi, &a_lo);
    mul_limbs(size, BPS, &b_hi, &b_lo);
    return u128_lt(a_hi, a_lo, b_hi, b_lo);
}

static uint64_t remaining_of(uint64_t collateral, int has_profit, uint64_t delta, int raise) {
    if (!has_profit) {
        if (collateral < delta) return 0;
        return collateral - delta;
    }
    if (!raise) {
        if (collateral > UINT64_MAX - delta) return 0;
        return collateral + delta;
    }
    return collateral;
}

static int wiped_of(uint64_t collateral, int has_profit, uint64_t delta) {
    return (!has_profit && collateral < delta) ? 1 : 0;
}

static int64_t liq_state(uint64_t collateral, uint64_t size, int has_profit, uint64_t delta,
                         uint64_t margin_fees, uint64_t liq_fee, uint64_t max_lev, int raise,
                         int (*lev)(uint64_t, uint64_t, uint64_t)) {
    uint64_t rem;
    if (max_lev == 0) return -1;
    if (wiped_of(collateral, has_profit, delta)) return raise ? -1 : 1;
    rem = remaining_of(collateral, has_profit, delta, raise);
    if (rem < margin_fees) return raise ? -1 : 1;
    if (margin_fees > UINT64_MAX - liq_fee) return -1;
    if (rem < margin_fees + liq_fee) return raise ? -1 : 1;
    if (lev(rem, size, max_lev)) return raise ? -1 : 2;
    return 0;
}

static uint64_t liq_fees(uint64_t collateral, uint64_t size, int has_profit, uint64_t delta,
                         uint64_t margin_fees, uint64_t liq_fee, uint64_t max_lev, int raise,
                         int (*lev)(uint64_t, uint64_t, uint64_t)) {
    int64_t st = liq_state(collateral, size, has_profit, delta, margin_fees, liq_fee, max_lev,
                           raise, lev);
    uint64_t rem;
    if (st < 0) return 0;
    if (wiped_of(collateral, has_profit, delta)) return margin_fees;
    rem = remaining_of(collateral, has_profit, delta, raise);
    if (rem < margin_fees) return rem;
    (void)liq_fee;
    (void)max_lev;
    (void)size;
    return margin_fees;
}

static uint64_t uncapped_fees(uint64_t collateral, int has_profit, uint64_t delta,
                              uint64_t margin_fees, int raise) {
    (void)raise;
    (void)collateral;
    (void)has_profit;
    (void)delta;
    return margin_fees;
}

static int ignore_liq_state(uint64_t collateral, uint64_t size, int has_profit, uint64_t delta,
                            uint64_t margin_fees, uint64_t max_lev, int raise) {
    uint64_t rem;
    if (wiped_of(collateral, has_profit, delta)) return raise ? -1 : 1;
    rem = remaining_of(collateral, has_profit, delta, raise);
    if (rem < margin_fees) return raise ? -1 : 1;
    if (lev_exceeded_i128(rem, size, max_lev)) return raise ? -1 : 2;
    return 0;
}

static int missing_bps_lev(uint64_t remaining, uint64_t size, uint64_t max_lev) {
    __uint128_t left = (__uint128_t)remaining * (__uint128_t)max_lev;
    return left < (__uint128_t)size;
}

static int naive_lev_exceeded(int64_t remaining, int64_t size, int64_t max_lev) {
    int64_t left = (int64_t)((uint64_t)remaining * (uint64_t)max_lev);
    int64_t right = size * (int64_t)BPS;
    return left < right;
}

static uint64_t as_funding_fee(uint64_t size, uint64_t rate) {
    if (size == 0 || rate == 0) return 0;
    return (uint64_t)(((__uint128_t)size * (__uint128_t)rate) / (__uint128_t)FUNDING_PREC);
}

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static int selftest(void) {
    if (muldiv_i128(100, 200, 50) != 400) return 1;
    if (liq_state(100000, 2000000, 1, 20000, 8000, 5000, 500000, 0, lev_exceeded_i128) != 0)
        return 2;
    if (liq_fees(100000, 2000000, 1, 20000, 8000, 5000, 500000, 0, lev_exceeded_i128) != 8000)
        return 3;
    if (remaining_of(100000, 1, 20000, 0) != 120000) return 4;
    if (liq_state(100000, 2000000, 0, 20000, 90000, 5000, 500000, 0, lev_exceeded_i128) != 1)
        return 5;
    if (liq_fees(100000, 2000000, 0, 20000, 90000, 5000, 500000, 0, lev_exceeded_i128) != 80000)
        return 6;
    if (uncapped_fees(100000, 0, 20000, 90000, 0) != 90000) return 7;
    if (liq_state(100000, 2000000, 0, 150000, 8000, 5000, 500000, 0, lev_exceeded_i128) != 1)
        return 8;
    if (liq_fees(100000, 2000000, 0, 150000, 8000, 5000, 500000, 0, lev_exceeded_i128) != 8000)
        return 9;
    if (liq_state(13000, 100000, 0, 1000, 8000, 5000, 500000, 0, lev_exceeded_i128) != 1)
        return 10;
    if (ignore_liq_state(13000, 100000, 0, 1000, 8000, 500000, 0) != 0) return 11;
    if (liq_state(100000, 6000000, 1, 0, 8000, 5000, 500000, 0, lev_exceeded_i128) != 2)
        return 12;
    if (missing_bps_lev(100000, 6000000, 500000) != 0) return 13;
    if (liq_state(10000, 100000, 1, 20000, 15000, 5000, 500000, 0, lev_exceeded_i128) != 0)
        return 14;
    if (liq_state(10000, 100000, 1, 20000, 15000, 5000, 500000, 1, lev_exceeded_i128) != -1)
        return 15;
    if (remaining_of(10000, 1, 20000, 1) != 10000) return 16;
    if (liq_state(100000, 2000000, 0, 20000, 90000, 5000, 500000, 1, lev_exceeded_i128) != -1)
        return 17;
    if (naive_lev_exceeded(4000000000LL, 1000000000LL, 3000000000LL) != 1) return 18;
    if (lev_exceeded_i128(4000000000ULL, 1000000000ULL, 3000000000ULL) != 0) return 19;
    if (lev_exceeded_limbs(4000000000ULL, 1000000000ULL, 3000000000ULL) != 0) return 20;
    if (liq_state(4000000000ULL, 1000000000ULL, 1, 0, 1, 1, 3000000000ULL, 0,
                  lev_exceeded_i128) != 0)
        return 21;
    if (as_funding_fee(2000000, 100) != 200) return 22;
    if (liq_state(100000, 2000000, 1, 20000, 8000, 5000, 500000, 0, lev_exceeded_i128)
        != liq_state(100000, 2000000, 1, 20000, 8000, 5000, 500000, 0, lev_exceeded_limbs))
        return 23;
    fprintf(stdout, "PASS\n");
    return 0;
}

static void parse8(char **argv, uint64_t *col, uint64_t *size, int *hp, uint64_t *delta,
                   uint64_t *fees, uint64_t *liq, uint64_t *lev, int *raise) {
    *col = strtoull(argv[2], NULL, 10);
    *size = strtoull(argv[3], NULL, 10);
    *hp = atoi(argv[4]);
    *delta = strtoull(argv[5], NULL, 10);
    *fees = strtoull(argv[6], NULL, 10);
    *liq = strtoull(argv[7], NULL, 10);
    *lev = strtoull(argv[8], NULL, 10);
    *raise = atoi(argv[9]);
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t col, size, delta, fees, liq, lev;
    int hp, raise;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | state col size hp delta fees liq lev raise | "
                "fees col size hp delta fees liq lev raise | rem col hp delta raise | "
                "uncap col hp delta fees raise | ignore col size hp delta fees lev raise | "
                "missbps rem size lev | naive rem size lev | wraplev rem size lev | "
                "fundfee size rate | muldiv a b d\n",
                argv[0]);
        return 2;
    }
    kind = argv[1];
    if (strcmp(kind, "selftest") == 0) return selftest();
    if (strcmp(kind, "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               muldiv_i128(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                           strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "state") == 0 && argc >= 10) {
        parse8(argv, &col, &size, &hp, &delta, &fees, &liq, &lev, &raise);
        printf("%" PRId64 "\n",
               liq_state(col, size, hp, delta, fees, liq, lev, raise, lev_exceeded_i128));
        return 0;
    }
    if (strcmp(kind, "fees") == 0 && argc >= 10) {
        parse8(argv, &col, &size, &hp, &delta, &fees, &liq, &lev, &raise);
        printf("%" PRIu64 "\n",
               liq_fees(col, size, hp, delta, fees, liq, lev, raise, lev_exceeded_i128));
        return 0;
    }
    if (strcmp(kind, "rem") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               remaining_of(strtoull(argv[2], NULL, 10), atoi(argv[3]),
                            strtoull(argv[4], NULL, 10), atoi(argv[5])));
        return 0;
    }
    if (strcmp(kind, "uncap") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               uncapped_fees(strtoull(argv[2], NULL, 10), atoi(argv[3]),
                             strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                             atoi(argv[6])));
        return 0;
    }
    if (strcmp(kind, "ignore") == 0 && argc >= 9) {
        printf("%d\n",
               ignore_liq_state(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                atoi(argv[4]), strtoull(argv[5], NULL, 10),
                                strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                                atoi(argv[8])));
        return 0;
    }
    if (strcmp(kind, "missbps") == 0 && argc >= 5) {
        printf("%d\n",
               missing_bps_lev(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                               strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "naive") == 0 && argc >= 5) {
        printf("%d\n",
               naive_lev_exceeded(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                                  strtoll(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "fundfee") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               as_funding_fee(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
