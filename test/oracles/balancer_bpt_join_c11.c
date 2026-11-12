/*
 * Independent C11 oracle for Balancer V2 WeightedMath._calcBptOutGivenExactTokenIn
 * (uint64 scale, ONE=1e9).
 *
 * Two implementations of (a*b+add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_balancer_bpt_join.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm (WeightedMath._calcBptOutGivenExactTokenIn + FixedPoint):
 *   balanceRatioWithFee = divDown(balance+amountIn, balance)
 *   invariantRatioWithFees = mulDown(ratio, weight) + complement(weight)
 *   if ratio > invariantRatioWithFees: charge mulUp fee on taxable excess
 *   invariantRatio = powDown(divDown(balance+amountInWithoutFee, balance), weight)
 *   bptOut = invariantRatio > ONE ? mulDown(supply, invariantRatio-ONE) : 0
 *
 * Experimental ONE=1e9. LogExpMath and uint256[] multi-token joins are NOT
 * implemented. Upstream Solidity is hash-pinned, not vendored.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ONE 1000000000ULL
#define I64MAX ((uint64_t)INT64_MAX)

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static uint64_t muldiv_add_i128(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b + (__uint128_t)add) / (__uint128_t)d;
    if (q > I64MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_add_rem_i128(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)a * (__uint128_t)b + (__uint128_t)add) % (__uint128_t)d);
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

static uint64_t mul_down(uint64_t a, uint64_t b, mdadd_fn md) {
    return md(a, b, 0, ONE);
}

static uint64_t mul_up(uint64_t a, uint64_t b, mdadd_fn md) {
    uint64_t q, r;
    int ov;
    if (a == 0 || b == 0) return 0;
    if (md == muldiv_add_limbs_q) {
        muldiv_add_limbs(a, b, 0, ONE, &q, &r, &ov);
        if (ov) return 0;
        if (r == 0) return q;
        if (q + 1 < q) return 0;
        return q + 1;
    }
    q = muldiv_add_i128(a, b, 0, ONE);
    r = muldiv_add_rem_i128(a, b, 0, ONE);
    if (r == 0) return q;
    if (q + 1 < q) return 0;
    return q + 1;
}

static uint64_t div_down(uint64_t a, uint64_t b, mdadd_fn md) {
    if (b == 0) return 0;
    return md(a, ONE, 0, b);
}

static uint64_t complement(uint64_t x) { return (x < ONE) ? (ONE - x) : 0; }

static uint64_t gcd_u(uint64_t a, uint64_t b) {
    uint64_t t;
    int k = 0;
    while (b != 0) {
        if (k++ >= 80) return 0;
        t = a % b;
        a = b;
        b = t;
    }
    return a;
}

static uint64_t pow_int_down(uint64_t base, uint64_t n, mdadd_fn md) {
    uint64_t r, sq, i;
    if (n == 0) return ONE;
    if (n == 1) return base;
    if (n == 2) return mul_down(base, base, md);
    if (n == 4) {
        sq = mul_down(base, base, md);
        return mul_down(sq, sq, md);
    }
    if (n > 16) return 0;
    r = ONE;
    for (i = 0; i < n; i++) r = mul_down(r, base, md);
    return r;
}

static uint64_t nth_root_down(uint64_t x, uint64_t n, mdadd_fn md) {
    uint64_t y, ynm1, term, nxt;
    int k;
    if (n <= 1) return x;
    if (n > 8 || x == 0) return 0;
    y = ONE;
    for (k = 0; k < 32; k++) {
        ynm1 = pow_int_down(y, n - 1, md);
        if (ynm1 == 0) return 0;
        term = div_down(x, ynm1, md);
        nxt = ((n - 1) * y + term) / n;
        if (nxt == y) return y;
        y = nxt;
    }
    return y;
}

static uint64_t pow_fp_down(uint64_t base, uint64_t fp_exp, mdadd_fn md) {
    uint64_t g, num, den, root;
    if (fp_exp == 0) return ONE;
    if (fp_exp == ONE) return base;
    g = gcd_u(fp_exp, ONE);
    if (g == 0) return 0;
    num = fp_exp / g;
    den = ONE / g;
    if (num > 16 || den > 8) return 0;
    if (den == 1) return pow_int_down(base, num, md);
    root = nth_root_down(base, den, md);
    return pow_int_down(root, num, md);
}

static uint64_t bpt_out(uint64_t bal, uint64_t w, uint64_t ain, uint64_t supply,
                       uint64_t fee, mdadd_fn md) {
    uint64_t den, br_fee, ir_fees, ain_nf, non_tax, tax, sf, den2, br, ir;
    if (bal == 0 || w == 0 || w >= ONE || supply == 0 || ain == 0) return 0;
    den = bal + ain;
    if (den < bal) return 0;
    br_fee = div_down(den, bal, md);
    ir_fees = mul_down(br_fee, w, md) + complement(w);
    ain_nf = ain;
    if (br_fee > ir_fees) {
        non_tax = (ir_fees > ONE) ? mul_down(bal, ir_fees - ONE, md) : 0;
        if (ain < non_tax) return 0;
        tax = ain - non_tax;
        sf = mul_up(tax, fee, md);
        if (tax < sf) return 0;
        ain_nf = non_tax + (tax - sf);
        if (ain_nf < non_tax) return 0;
    }
    if (ain_nf == 0) return 0;
    den2 = bal + ain_nf;
    if (den2 < bal) return 0;
    br = div_down(den2, bal, md);
    ir = pow_fp_down(br, w, md);
    if (ir <= ONE) return 0;
    return mul_down(supply, ir - ONE, md);
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    uint64_t ain = 100000000ULL;
    uint64_t w50 = 500000000ULL;
    uint64_t w80 = 800000000ULL;
    uint64_t fee = 3000000ULL;
    if (bpt_out(e9, w50, ain, e9, 0, muldiv_add_i128) != 48808848ULL) return 1;
    if (bpt_out(e9, w50, ain, e9, 0, muldiv_add_limbs_q) != 48808848ULL) return 1;
    if (bpt_out(e9, w50, ain, e9, fee, muldiv_add_i128) != 48737336ULL) return 1;
    if (bpt_out(e9, w50, ain, e9, fee, muldiv_add_limbs_q) != 48737336ULL) return 1;
    if (bpt_out(e9, w80, ain, e9, 0, muldiv_add_i128) != 79230342ULL) return 1;
    if (bpt_out(e9, w80, ain, e9, 0, muldiv_add_limbs_q) != 79230342ULL) return 1;
    if (bpt_out(e9, 200000000ULL, ain, e9, 0, muldiv_add_i128) != 19244876ULL) return 1;
    if (bpt_out(e9, 600000000ULL, ain, e9, 0, muldiv_add_i128) != 58852851ULL) return 1;
    if (bpt_out(e9, w50, 0, e9, 0, muldiv_add_i128) != 0) return 1;
    if (pow_fp_down(1100000000ULL, w80, muldiv_add_i128) != 1079230342ULL) return 1;
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
            "usage: balancer_bpt_join_c11 selftest\n"
            "       balancer_bpt_join_c11 bpt BAL W AIN SUPPLY FEE [--limbs]\n"
            "       balancer_bpt_join_c11 mul_down A B [--limbs]\n"
            "       balancer_bpt_join_c11 pow_down BASE EXP [--limbs]\n");
}

int main(int argc, char **argv) {
    mdadd_fn md;
    if (argc < 2) {
        usage();
        return 2;
    }
    md = parse_md(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "bpt") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               bpt_out(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                       strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                       strtoull(argv[6], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "mul_down") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               mul_down(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "pow_down") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               pow_fp_down(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    usage();
    return 2;
}
