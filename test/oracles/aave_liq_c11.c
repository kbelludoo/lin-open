/*
 * Independent C11 oracle for Aave V3 liquidation available-collateral math
 * (uint64 scale).
 *
 * Two implementations of (a*b+add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_aave_liq.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm (LiquidationLogic._calculateAvailableCollateralToLiquidate
 * + _calculateDebt + PercentageMath):
 *   base = (debtPrice * debtToCover * collUnit) / (collPrice * debtUnit)
 *   maxColl = percentMul(base, liquidationBonus)
 *   closeFactor = hf > 0.95*WAD' ? 0.5e4 : 1e4
 *
 * Experimental WAD' = 1e9 (mainnet WAD=1e18 HF threshold still fits i64).
 * PERCENTAGE_FACTOR = 1e4 (same bps as Aave). Upstream Solidity is
 * hash-pinned, not vendored. Oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PCT 10000ULL
#define HALF_PCT 5000ULL
#define HF_THR 950000000ULL
#define DEFAULT_CLOSE 5000ULL
#define MAX_CLOSE 10000ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static uint64_t muldiv_add_i128(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b + (__uint128_t)add) / (__uint128_t)d;
    if (q > (uint64_t)INT64_MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_rem_i128(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)a * (__uint128_t)b) % (__uint128_t)d);
}

static void muldiv_add_limbs(uint64_t a, uint64_t b, uint64_t add, uint64_t d,
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
    lo = lo + add;
    if (lo < add) hi = hi + 1;
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
    if ((int64_t)q < 0) ov = 1;
    *q_out = ov ? 0 : q;
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t muldiv_add_limbs_q(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_add_limbs(a, b, add, d, &q, &r, &ov);
    return q;
}

typedef uint64_t (*mdadd_fn)(uint64_t, uint64_t, uint64_t, uint64_t);

static uint64_t percent_mul(uint64_t v, uint64_t p, mdadd_fn md) {
    if (p == 0 || v == 0) return 0;
    return md(v, p, HALF_PCT, PCT);
}

static uint64_t percent_div(uint64_t v, uint64_t p, mdadd_fn md) {
    if (p == 0) return 0;
    return md(v, PCT, p / 2, p);
}

static uint64_t mul3div1(uint64_t a, uint64_t b, uint64_t c, uint64_t den, mdadd_fn md) {
    uint64_t q_ab, r_ab, qc, extra, s, qq, rr;
    int ov;
    if (den == 0) return 0;
    if (md == muldiv_add_i128) {
        __uint128_t q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)den;
        if (q > (uint64_t)INT64_MAX) return 0;
        q_ab = (uint64_t)q;
        r_ab = muldiv_rem_i128(a, b, den);
    } else {
        muldiv_add_limbs(a, b, 0, den, &qq, &rr, &ov);
        if (ov) return 0;
        q_ab = qq;
        r_ab = rr;
    }
    qc = md(q_ab, c, 0, 1);
    if (q_ab != 0 && c != 0 && qc == 0) return 0;
    extra = md(r_ab, c, 0, den);
    s = qc + extra;
    if (s < qc || (int64_t)s < 0) return 0;
    return s;
}

static uint64_t base_collateral(uint64_t dp, uint64_t debt, uint64_t cu,
                                uint64_t cp, uint64_t du, mdadd_fn md) {
    uint64_t den;
    if (dp == 0 || cu == 0 || cp == 0 || du == 0) return 0;
    den = cp * du;
    if (du != 0 && den / cp != du) return 0;
    return mul3div1(dp, debt, cu, den, md);
}

static uint64_t avail(uint64_t dp, uint64_t debt, uint64_t cu, uint64_t cp, uint64_t du,
                      uint64_t user_bal, uint64_t bonus, uint64_t fee_pct, int want,
                      mdadd_fn md) {
    uint64_t base, maxc, coll, dneed, fee, t, unbonus, bonus_coll;
    if (bonus == 0) return 0;
    base = base_collateral(dp, debt, cu, cp, du, md);
    maxc = percent_mul(base, bonus, md);
    coll = maxc;
    dneed = debt;
    if (user_bal < maxc) {
        coll = user_bal;
        t = mul3div1(cp, coll, du, dp, md);
        dneed = percent_div(md(t, 1, 0, cu), bonus, md);
    }
    fee = 0;
    if (fee_pct != 0) {
        unbonus = percent_div(coll, bonus, md);
        if (coll < unbonus) return 0;
        bonus_coll = coll - unbonus;
        fee = percent_mul(bonus_coll, fee_pct, md);
        if (coll < fee) return 0;
        coll = coll - fee;
    }
    if (want == 1) return dneed;
    if (want == 2) return fee;
    return coll;
}

static uint64_t close_factor(uint64_t hf) {
    return (hf > HF_THR) ? DEFAULT_CLOSE : MAX_CLOSE;
}

static uint64_t close_debt(uint64_t total, uint64_t cover, uint64_t hf, mdadd_fn md) {
    uint64_t maxd = percent_mul(total, close_factor(hf), md);
    return (cover > maxd) ? maxd : cover;
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    uint64_t q_i, q_l, r;
    int ov;
    q_i = muldiv_add_i128(100, 200, 0, 50);
    q_l = muldiv_add_limbs_q(100, 200, 0, 50);
    if (q_i != 400 || q_l != 400) return 1;
    muldiv_add_limbs(100, 200, 0, 50, &q_l, &r, &ov);
    if (r != 0 || ov != 0) return 1;
    if (percent_mul(1, HALF_PCT, muldiv_add_i128) != 1) return 1;
    if (percent_mul(1, HALF_PCT, muldiv_add_limbs_q) != 1) return 1;
    if (percent_div(2, 3, muldiv_add_i128) != 6667ULL) return 1;
    if (avail(1000, e9, e9, 1000, e9, 10000000000ULL, 10500, 0, 0, muldiv_add_i128) != 1050000000ULL)
        return 1;
    if (avail(1000, e9, e9, 1000, e9, 10000000000ULL, 10500, 0, 0, muldiv_add_limbs_q) != 1050000000ULL)
        return 1;
    if (avail(1000, e9, e9, 1000, e9, 10000000000ULL, 10500, 1000, 2, muldiv_add_i128) != 5000000ULL)
        return 1;
    if (avail(1000, e9, e9, 0, e9, 10000000000ULL, 10500, 0, 0, muldiv_add_i128) != 0) return 1;
    if (close_debt(e9, e9, 960000000ULL, muldiv_add_i128) != 500000000ULL) return 1;
    if (close_debt(e9, e9, 900000000ULL, muldiv_add_limbs_q) != e9) return 1;
    puts("PASS");
    return 0;
}

static mdadd_fn parse_md(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) return muldiv_add_limbs_q;
    }
    return muldiv_add_i128;
}

static void usage(void) {
    fprintf(stderr,
            "usage: aave_liq_c11 selftest\n"
            "       aave_liq_c11 percent_mul V P [--limbs]\n"
            "       aave_liq_c11 percent_div V P [--limbs]\n"
            "       aave_liq_c11 floor_mul V P [--limbs]\n"
            "       aave_liq_c11 floor_div V P [--limbs]\n"
            "       aave_liq_c11 avail DP DEBT CU CP DU BAL BONUS FEE WANT [--limbs]\n"
            "       aave_liq_c11 close_debt TOTAL COVER HF [--limbs]\n"
            "       aave_liq_c11 close_factor HF\n");
}

int main(int argc, char **argv) {
    mdadd_fn md;
    if (argc < 2) {
        usage();
        return 2;
    }
    md = parse_md(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "percent_mul") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               percent_mul(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "percent_div") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               percent_div(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "floor_mul") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), 0, PCT));
        return 0;
    }
    if (strcmp(argv[1], "floor_div") == 0 && argc >= 4) {
        uint64_t p = strtoull(argv[3], NULL, 10);
        printf("%" PRIu64 "\n",
               p == 0 ? 0 : md(strtoull(argv[2], NULL, 10), PCT, 0, p));
        return 0;
    }
    if (strcmp(argv[1], "avail") == 0 && argc >= 11) {
        printf("%" PRIu64 "\n",
               avail(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                     strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                     strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10),
                     strtoull(argv[8], NULL, 10), strtoull(argv[9], NULL, 10),
                     atoi(argv[10]), md));
        return 0;
    }
    if (strcmp(argv[1], "close_debt") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               close_debt(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                          strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "close_factor") == 0 && argc >= 3) {
        printf("%" PRIu64 "\n", close_factor(strtoull(argv[2], NULL, 10)));
        return 0;
    }
    usage();
    return 2;
}
