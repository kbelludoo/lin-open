/*
 * Independent C11 oracle for GMX V1 VaultUtils.validateLiquidation (uint64 scale).
 *
 * Wide remaining*maxLeverage vs size*10000 uses unsigned __int128 AND a portable
 * 32-bit limb product that mirrors src/lin_gmx_liq.lin. Consensus is required
 * before any LIN comparison. This file is not linked into the LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-contracts contracts/core/VaultUtils.sol (MIT).
 * This oracle is original C11 of the published formula, not a Solidity dump.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BPS 10000ULL

static void prod_limbs(uint64_t a, uint64_t b, uint64_t *hi_out, uint64_t *lo_out) {
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

static int mul_lt_limbs(uint64_t a, uint64_t b, uint64_t c, uint64_t d) {
    uint64_t ahi, alo, bhi, blo;
    prod_limbs(a, b, &ahi, &alo);
    prod_limbs(c, d, &bhi, &blo);
    if (ahi != bhi) return ahi < bhi;
    return alo < blo;
}

static int mul_lt_i128(uint64_t a, uint64_t b, uint64_t c, uint64_t d) {
    __uint128_t left = (__uint128_t)a * (__uint128_t)b;
    __uint128_t right = (__uint128_t)c * (__uint128_t)d;
    return left < right;
}

static uint64_t margin_fees(int64_t funding, int64_t position) {
    if (funding < 0 || position < 0) return 0;
    uint64_t f = (uint64_t)funding, p = (uint64_t)position;
    if (f > UINT64_MAX - p) return 0;
    return f + p;
}

static uint64_t remaining(int64_t collateral, int has_profit, int64_t delta, int raise) {
    if (collateral < 0 || delta < 0) return 0;
    uint64_t col = (uint64_t)collateral, dlt = (uint64_t)delta;
    if (!has_profit) {
        if (col < dlt) return 0;
        return col - dlt;
    }
    if (!raise) {
        if (col > UINT64_MAX - dlt) return 0;
        return col + dlt;
    }
    return col;
}

static int losses_exceed(int64_t collateral, int has_profit, int64_t delta) {
    if (has_profit || collateral < 0 || delta < 0) return 0;
    return (uint64_t)collateral < (uint64_t)delta;
}

static void eval_liq(int64_t size, int64_t collateral, int has_profit, int64_t delta,
                     int64_t funding, int64_t position, int64_t liq, int64_t max_lev,
                     int raise, int64_t *state, int64_t *fees, int64_t *rem_out,
                     int use_limbs) {
    *state = 0;
    *fees = 0;
    *rem_out = 0;
    if (size < 0 || liq < 0 || max_lev <= 0) return;
    uint64_t margin = margin_fees(funding, position);
    if (losses_exceed(collateral, has_profit, delta)) {
        if (raise) {
            *state = -1;
            return;
        }
        *state = 1;
        *fees = (int64_t)margin;
        return;
    }
    uint64_t rem = remaining(collateral, has_profit, delta, raise);
    *rem_out = (int64_t)rem;
    if (rem < margin) {
        if (raise) {
            *state = -2;
            *rem_out = 0;
            return;
        }
        *state = 1;
        *fees = (int64_t)rem;
        return;
    }
    if ((uint64_t)liq > UINT64_MAX - margin) return;
    uint64_t liq_tot = margin + (uint64_t)liq;
    if (rem < liq_tot) {
        if (raise) {
            *state = -3;
            return;
        }
        *state = 1;
        *fees = (int64_t)margin;
        return;
    }
    int lev = use_limbs
                  ? mul_lt_limbs(rem, (uint64_t)max_lev, (uint64_t)size, BPS)
                  : mul_lt_i128(rem, (uint64_t)max_lev, (uint64_t)size, BPS);
    if (lev) {
        if (raise) {
            *state = -4;
            return;
        }
        *state = 2;
        *fees = (int64_t)margin;
        return;
    }
    *state = 0;
    *fees = (int64_t)margin;
}

static int64_t naive_lev(int64_t rem, int64_t max_lev, int64_t size) {
    return (rem * max_lev < size * (int64_t)BPS) ? 1 : 0;
}

static void usage(void) {
    fprintf(stderr,
            "usage: gmx_liq_c11 selftest | remaining col hp delta raise |\n"
            "  margin fund pos | state ... | fees ... | rem ... |\n"
            "  nocap col hp delta fund pos | incliq col hp delta fund pos liq |\n"
            "  naivelev rem ml size | widelev rem ml size [--limbs]\n");
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
        int64_t st, fe, rm;
        eval_liq(100000, 1000, 0, 100, 800, 150, 5, 500000, 0, &st, &fe, &rm, 0);
        if (st != 1 || fe != 900 || rm != 900) {
            fprintf(stderr, "cap fail %ld %ld %ld\n", (long)st, (long)fe, (long)rm);
            return 1;
        }
        eval_liq(100000, 1000, 0, 100, 800, 150, 5, 500000, 0, &st, &fe, &rm, 1);
        if (st != 1 || fe != 900) return 1;
        eval_liq(100000, 1020, 0, 100, 850, 50, 50, 500000, 0, &st, &fe, &rm, 0);
        if (st != 1 || fe != 900) return 1;
        eval_liq(100000, 500, 0, 600, 80, 20, 5, 500000, 0, &st, &fe, &rm, 0);
        if (st != 1 || fe != 100) return 1;
        eval_liq(100000, 1500, 0, 0, 8, 2, 5, 500000, 0, &st, &fe, &rm, 0);
        if (st != 2 || fe != 10) return 1;
        eval_liq(100000, 3000, 0, 0, 8, 2, 5, 500000, 0, &st, &fe, &rm, 1);
        if (st != 0 || fe != 10) return 1;
        eval_liq(60000, 1000, 1, 500, 8, 2, 5, 500000, 1, &st, &fe, &rm, 0);
        if (st != -4) return 1;
        eval_liq(60000, 1000, 1, 500, 8, 2, 5, 500000, 0, &st, &fe, &rm, 0);
        if (st != 0 || fe != 10) return 1;
        if (naive_lev(4000000000LL, 3000000000LL, 2000000000LL) != 1) return 1;
        if (mul_lt_i128(4000000000ULL, 3000000000ULL, 2000000000ULL, BPS) != 0) return 1;
        if (mul_lt_limbs(4000000000ULL, 3000000000ULL, 2000000000ULL, BPS) != 0) return 1;
        if (remaining(1000, 1, 500, 1) != 1000 || remaining(1000, 1, 500, 0) != 1500) return 1;
        printf("PASS\n");
        return 0;
    }
    if (strcmp(argv[1], "remaining") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               remaining(atoll(argv[2]), atoi(argv[3]), atoll(argv[4]), atoi(argv[5])));
        return 0;
    }
    if (strcmp(argv[1], "margin") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n", margin_fees(atoll(argv[2]), atoll(argv[3])));
        return 0;
    }
    if ((strcmp(argv[1], "state") == 0 || strcmp(argv[1], "fees") == 0 ||
         strcmp(argv[1], "rem") == 0) &&
        argc >= 11) {
        int64_t st, fe, rm;
        eval_liq(atoll(argv[2]), atoll(argv[3]), atoi(argv[4]), atoll(argv[5]),
                 atoll(argv[6]), atoll(argv[7]), atoll(argv[8]), atoll(argv[9]),
                 atoi(argv[10]), &st, &fe, &rm, use_limbs);
        if (argv[1][0] == 's') printf("%" PRId64 "\n", st);
        else if (argv[1][0] == 'f') printf("%" PRId64 "\n", fe);
        else printf("%" PRId64 "\n", rm);
        return 0;
    }
    if (strcmp(argv[1], "nocap") == 0 && argc >= 7) {
        uint64_t margin = margin_fees(atoll(argv[5]), atoll(argv[6]));
        uint64_t rem = remaining(atoll(argv[2]), atoi(argv[3]), atoll(argv[4]), 0);
        if (losses_exceed(atoll(argv[2]), atoi(argv[3]), atoll(argv[4]))) {
            printf("%" PRIu64 "\n", margin);
            return 0;
        }
        printf("%" PRIu64 "\n", rem < margin ? margin : rem);
        return 0;
    }
    if (strcmp(argv[1], "incliq") == 0 && argc >= 8) {
        uint64_t margin = margin_fees(atoll(argv[5]), atoll(argv[6]));
        uint64_t rem = remaining(atoll(argv[2]), atoi(argv[3]), atoll(argv[4]), 0);
        uint64_t liq = (uint64_t)atoll(argv[7]);
        if (losses_exceed(atoll(argv[2]), atoi(argv[3]), atoll(argv[4]))) {
            printf("%" PRIu64 "\n", margin);
            return 0;
        }
        printf("%" PRIu64 "\n", rem < margin + liq ? margin + liq : margin);
        return 0;
    }
    if (strcmp(argv[1], "naivelev") == 0 && argc >= 5) {
        printf("%" PRId64 "\n", naive_lev(atoll(argv[2]), atoll(argv[3]), atoll(argv[4])));
        return 0;
    }
    if (strcmp(argv[1], "widelev") == 0 && argc >= 5) {
        uint64_t rem = (uint64_t)atoll(argv[2]);
        uint64_t ml = (uint64_t)atoll(argv[3]);
        uint64_t sz = (uint64_t)atoll(argv[4]);
        int v = use_limbs ? mul_lt_limbs(rem, ml, sz, BPS) : mul_lt_i128(rem, ml, sz, BPS);
        printf("%d\n", v);
        return 0;
    }
    usage();
    return 2;
}
