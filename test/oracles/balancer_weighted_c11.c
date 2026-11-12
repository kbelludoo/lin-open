/*
 * Independent C11 oracle for Balancer V2 WeightedMath._calcOutGivenIn
 * (uint64 scale, ONE=1e9).
 *
 * Two implementations of (a*b+add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_balancer_weighted.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm (WeightedMath._calcOutGivenIn + FixedPoint):
 *   reject amountIn > mulDown(balanceIn, 0.3*ONE)
 *   base = divUp(balanceIn, balanceIn+amountIn)
 *   power = powUp(base, weightIn/weightOut)  integer 1/2/4 or bounded Newton
 *   out = mulDown(balanceOut, complement(power))
 *
 * Experimental ONE=1e9. LogExpMath is NOT implemented.
 * Upstream Solidity is hash-pinned, not vendored. Oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ONE 1000000000ULL
#define MAX_IN 300000000ULL
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

static uint64_t div_up(uint64_t a, uint64_t b, mdadd_fn md) {
    uint64_t q, r;
    int ov;
    if (a == 0 || b == 0) return 0;
    if (md == muldiv_add_limbs_q) {
        muldiv_add_limbs(a, ONE, 0, b, &q, &r, &ov);
        if (ov) return 0;
        if (r == 0) return q;
        if (q + 1 < q) return 0;
        return q + 1;
    }
    q = muldiv_add_i128(a, ONE, 0, b);
    r = muldiv_add_rem_i128(a, ONE, 0, b);
    if (r == 0) return q;
    if (q + 1 < q) return 0;
    return q + 1;
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

static uint64_t pow_int_up(uint64_t base, uint64_t n, mdadd_fn md) {
    uint64_t r, sq, i;
    if (n == 0) return ONE;
    if (n == 1) return base;
    if (n == 2) return mul_up(base, base, md);
    if (n == 4) {
        sq = mul_up(base, base, md);
        return mul_up(sq, sq, md);
    }
    if (n > 16) return 0;
    r = ONE;
    for (i = 0; i < n; i++) r = mul_up(r, base, md);
    return r;
}

static uint64_t nth_root_up(uint64_t x, uint64_t n, mdadd_fn md) {
    uint64_t y, ynm1, term, nxt;
    int k;
    if (n <= 1) return x;
    if (n > 8 || x == 0) return 0;
    y = ONE;
    for (k = 0; k < 32; k++) {
        ynm1 = pow_int_up(y, n - 1, md);
        if (ynm1 == 0) return 0;
        term = div_up(x, ynm1, md);
        nxt = ((n - 1) * y + term) / n;
        if (nxt == y) return y;
        y = nxt;
    }
    return y;
}

static uint64_t pow_rat_up(uint64_t base, uint64_t num, uint64_t den, mdadd_fn md) {
    uint64_t root;
    if (den == 0) return 0;
    if (den == 1) return pow_int_up(base, num, md);
    root = nth_root_up(base, den, md);
    return pow_int_up(root, num, md);
}

static uint64_t out_given_in(uint64_t bi, uint64_t wi, uint64_t bo, uint64_t wo,
                            uint64_t ai, mdadd_fn md) {
    uint64_t cap, den, base, g, num, denw, power;
    if (bi == 0 || wi == 0 || bo == 0 || wo == 0 || ai == 0) return 0;
    cap = mul_down(bi, MAX_IN, md);
    if (cap < ai) return 0;
    den = bi + ai;
    if (den < bi) return 0;
    base = div_up(bi, den, md);
    g = gcd_u(wi, wo);
    if (g == 0) return 0;
    num = wi / g;
    denw = wo / g;
    if (num > 16 || denw > 8) return 0;
    power = pow_rat_up(base, num, denw, md);
    return mul_down(bo, complement(power), md);
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    uint64_t ain = 100000000ULL;
    if (out_given_in(e9, 50, e9, 50, ain, muldiv_add_i128) != 90909090ULL) return 1;
    if (out_given_in(e9, 50, e9, 50, ain, muldiv_add_limbs_q) != 90909090ULL) return 1;
    if (out_given_in(e9, 80, e9, 20, ain, muldiv_add_i128) != 316986541ULL) return 1;
    if (out_given_in(e9, 80, e9, 20, ain, muldiv_add_limbs_q) != 316986541ULL) return 1;
    if (out_given_in(e9, 20, e9, 80, ain, muldiv_add_i128) != 23545910ULL) return 1;
    if (out_given_in(e9, 60, e9, 40, ain, muldiv_add_i128) != 133215825ULL) return 1;
    if (out_given_in(e9, 70, e9, 30, ain, muldiv_add_i128) != 199397265ULL) return 1;
    if (out_given_in(e9, 50, e9, 50, 300000001ULL, muldiv_add_i128) != 0) return 1;
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
            "usage: balancer_weighted_c11 selftest\n"
            "       balancer_weighted_c11 out BI WI BO WO AI [--limbs]\n"
            "       balancer_weighted_c11 mul_down A B [--limbs]\n"
            "       balancer_weighted_c11 div_up A B [--limbs]\n");
}

int main(int argc, char **argv) {
    mdadd_fn md;
    if (argc < 2) {
        usage();
        return 2;
    }
    md = parse_md(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "out") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               out_given_in(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                            strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                            strtoull(argv[6], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "mul_down") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               mul_down(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "div_up") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               div_up(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), md));
        return 0;
    }
    usage();
    return 2;
}
