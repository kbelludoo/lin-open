/*
 * Independent C11 oracle for Uniswap V3 SwapMath.computeSwapStep (uint64 / Q32).
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_uniswap_v3_step.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: Uniswap/v3-core contracts/libraries/SwapMath.sol tag v1.0.0
 * Algorithm license: GPL-2.0-or-later after BUSL Change Date 2023-04-01.
 * This oracle is original C11 at Q32=2^32 (not Q96=2^96).
 * Kernel is the fee/cap step, not a retread of FromInput / FromOutput / amount-delta.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define Q32 4294967296ULL
#define FEE_DEN 1000000ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d,
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
            if (need_borrow) r_hi -= 1;
            if (i >= 64) ov = 1;
            else q |= (1ULL << i);
        }
    }
    *q_out = ov ? 0 : q;
    *r_out = r_lo;
    *ov_out = ov;
}

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

static int mul_ov_i128(uint64_t a, uint64_t b) {
    return ((__uint128_t)a * (__uint128_t)b) > UINT64_MAX;
}

static uint64_t muldiv_up_i128(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    if (d == 0) return 0;
    if (((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d > UINT64_MAX) return 0;
    q = muldiv_i128(a, b, d);
    r = muldiv_rem_i128(a, b, d);
    if (r == 0) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1;
}

static uint64_t div_up(uint64_t a, uint64_t d) {
    uint64_t q;
    if (d == 0) return 0;
    q = a / d;
    if (a % d == 0) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1;
}

static uint64_t limbs_or_die(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    (void)r;
    if (ov) return 0;
    return q;
}

static uint64_t amount0(uint64_t sa, uint64_t sb, uint64_t liq, int round_up) {
    uint64_t a = sa, b = sb, num1, num2, t;
    if (b < a) {
        a = sb;
        b = sa;
    }
    if (a == 0) return 0;
    num1 = muldiv_i128(liq, Q32, 1);
    if (num1 == 0) return 0;
    num2 = b - a;
    if (round_up) {
        t = muldiv_up_i128(num1, num2, b);
        return div_up(t, a);
    }
    t = muldiv_i128(num1, num2, b);
    return muldiv_i128(t, 1, a);
}

static uint64_t amount1(uint64_t sa, uint64_t sb, uint64_t liq, int round_up) {
    uint64_t a = sa, b = sb, d;
    if (b < a) {
        a = sb;
        b = sa;
    }
    d = b - a;
    return round_up ? muldiv_up_i128(liq, d, Q32) : muldiv_i128(liq, d, Q32);
}

static uint64_t next0_add(uint64_t sqrt_p, uint64_t liq, uint64_t amount) {
    uint64_t num1, product, denom;
    if (sqrt_p == 0 || liq == 0) return 0;
    if (amount == 0) return sqrt_p;
    num1 = muldiv_i128(liq, Q32, 1);
    if (num1 == 0 || mul_ov_i128(amount, sqrt_p)) return 0;
    product = amount * sqrt_p;
    denom = num1 + product;
    if (denom < num1) return 0;
    return muldiv_up_i128(num1, sqrt_p, denom);
}

static uint64_t next1_add(uint64_t sqrt_p, uint64_t liq, uint64_t amount) {
    uint64_t shift, quot, s;
    if (sqrt_p == 0 || liq == 0) return 0;
    if (amount == 0) return sqrt_p;
    shift = muldiv_i128(amount, Q32, 1);
    if (shift == 0) {
        quot = muldiv_i128(amount, Q32, liq);
        if (quot == 0) return 0;
    } else {
        quot = shift / liq;
    }
    s = sqrt_p + quot;
    if (s < sqrt_p) return 0;
    return s;
}

static uint64_t next0_sub(uint64_t sqrt_p, uint64_t liq, uint64_t amount) {
    uint64_t num1, product, denom;
    if (sqrt_p == 0 || liq == 0) return 0;
    if (amount == 0) return sqrt_p;
    num1 = muldiv_i128(liq, Q32, 1);
    if (num1 == 0 || mul_ov_i128(amount, sqrt_p)) return 0;
    product = amount * sqrt_p;
    if (num1 <= product) return 0;
    denom = num1 - product;
    if (denom == 0) return 0;
    return muldiv_up_i128(num1, sqrt_p, denom);
}

static uint64_t next1_sub(uint64_t sqrt_p, uint64_t liq, uint64_t amount) {
    uint64_t shift, quot;
    if (sqrt_p == 0 || liq == 0) return 0;
    if (amount == 0) return sqrt_p;
    shift = muldiv_i128(amount, Q32, 1);
    if (shift == 0) {
        quot = muldiv_up_i128(amount, Q32, liq);
        if (quot == 0) return 0;
    } else {
        quot = div_up(shift, liq);
    }
    if (sqrt_p <= quot) return 0;
    return sqrt_p - quot;
}

static uint64_t remaining_less_fee(int64_t remaining, uint64_t fee_pips) {
    if (remaining < 0) return 0;
    if (fee_pips > FEE_DEN) return 0;
    return muldiv_i128((uint64_t)remaining, FEE_DEN - fee_pips, FEE_DEN);
}

static int64_t naive_fee_wrap(int64_t remaining, int64_t fee_pips) {
    int64_t den = (int64_t)FEE_DEN;
    return (int64_t)((uint64_t)remaining * (uint64_t)(den - fee_pips)) / den;
}

static uint64_t step_next(uint64_t sqrt_p, uint64_t target, uint64_t liq,
                         int64_t remaining, uint64_t fee_pips) {
    int zfo, exact_in;
    uint64_t less, ain, aout, absr;
    if (sqrt_p == 0 || liq == 0) return 0;
    zfo = sqrt_p >= target;
    exact_in = remaining >= 0;
    if (exact_in) {
        less = remaining_less_fee(remaining, fee_pips);
        ain = zfo ? amount0(target, sqrt_p, liq, 1) : amount1(sqrt_p, target, liq, 1);
        if (less >= ain) return target;
        return zfo ? next0_add(sqrt_p, liq, less) : next1_add(sqrt_p, liq, less);
    }
    absr = (uint64_t)(-remaining);
    aout = zfo ? amount1(target, sqrt_p, liq, 0) : amount0(sqrt_p, target, liq, 0);
    if (absr >= aout) return target;
    return zfo ? next1_sub(sqrt_p, liq, absr) : next0_sub(sqrt_p, liq, absr);
}

static uint64_t skip_fee_next(uint64_t sqrt_p, uint64_t target, uint64_t liq,
                             int64_t remaining, uint64_t fee_pips) {
    int zfo;
    uint64_t ain, rem;
    (void)fee_pips;
    if (sqrt_p == 0 || liq == 0 || remaining < 0) return 0;
    zfo = sqrt_p >= target;
    rem = (uint64_t)remaining;
    ain = zfo ? amount0(target, sqrt_p, liq, 1) : amount1(sqrt_p, target, liq, 1);
    if (rem >= ain) return target;
    return zfo ? next0_add(sqrt_p, liq, rem) : next1_add(sqrt_p, liq, rem);
}

static uint64_t step_amount_in(uint64_t sqrt_p, uint64_t target, uint64_t liq,
                              int64_t remaining, uint64_t fee_pips) {
    uint64_t nxt = step_next(sqrt_p, target, liq, remaining, fee_pips);
    if (sqrt_p >= target) return amount0(nxt, sqrt_p, liq, 1);
    return amount1(sqrt_p, nxt, liq, 1);
}

static uint64_t step_amount_out(uint64_t sqrt_p, uint64_t target, uint64_t liq,
                               int64_t remaining, uint64_t fee_pips) {
    uint64_t nxt = step_next(sqrt_p, target, liq, remaining, fee_pips);
    uint64_t aout, absr;
    int zfo = sqrt_p >= target;
    aout = zfo ? amount1(nxt, sqrt_p, liq, 0) : amount0(sqrt_p, nxt, liq, 0);
    if (remaining < 0) {
        absr = (uint64_t)(-remaining);
        if (absr < aout) return absr;
    }
    return aout;
}

static uint64_t step_fee(uint64_t sqrt_p, uint64_t target, uint64_t liq,
                        int64_t remaining, uint64_t fee_pips) {
    uint64_t nxt = step_next(sqrt_p, target, liq, remaining, fee_pips);
    uint64_t ain = step_amount_in(sqrt_p, target, liq, remaining, fee_pips);
    if (remaining >= 0 && nxt != target) return (uint64_t)remaining - ain;
    if (fee_pips > FEE_DEN) return 0;
    return muldiv_up_i128(ain, fee_pips, FEE_DEN - fee_pips);
}

static int selftest(void) {
    uint64_t q = Q32, l = 1000000ULL, t0 = 2147483648ULL, t1 = 8589934592ULL, fee = 3000ULL;
    uint64_t qr, rr;
    int ov;
    if (muldiv_i128(100, 200, 50) != 400) return 1;
    if (limbs_or_die(100, 200, 50) != 400) return 2;
    muldiv_limbs_qr(7, 9, 2, &qr, &rr, &ov);
    if (ov || qr != 31 || rr != 1) return 3;
    if (muldiv_i128(1000000000000000000ULL, 1000000000000000000ULL, 1) != 0) return 4;
    if (step_next(q, t0, l, 1000000LL, fee) != 2150709713ULL) return 5;
    if (skip_fee_next(q, t0, l, 1000000LL, fee) != t0) return 6;
    if (step_next(q, t0, l, 1003011LL, fee) != t0) return 7;
    if (step_fee(q, t0, l, 1000000LL, fee) != 3000ULL) return 8;
    if (step_fee(q, t0, l, 1003011LL, fee) != 3010ULL) return 9;
    if (step_next(q, t0, l, -500000LL, fee) != t0) return 10;
    if (step_next(q, t0, l, 500000LL, fee) != 2866177709ULL) return 11;
    if (step_next(q, t0, l, -499999LL, fee) != 2147487942ULL) return 12;
    if (step_next(q, t1, l, 1000000LL, fee) != 8577049690ULL) return 13;
    if (naive_fee_wrap(10000000000000LL, 3000LL) != -8476744073709LL) return 14;
    if (remaining_less_fee(10000000000000LL, 3000ULL) != 9970000000000ULL) return 15;
    if (step_amount_out(q, t0, l, 1000000LL, fee) != 499248ULL) return 16;
    if (amount0(t0, q, l, 1) != 1000000ULL) return 17;
    fprintf(stdout, "PASS\n");
    return 0;
}

static int parse_step_args(int argc, char **argv, uint64_t *p, uint64_t *t, uint64_t *l,
                           int64_t *r, uint64_t *f) {
    if (argc < 7) return 0;
    *p = strtoull(argv[2], NULL, 10);
    *t = strtoull(argv[3], NULL, 10);
    *l = strtoull(argv[4], NULL, 10);
    *r = strtoll(argv[5], NULL, 10);
    *f = strtoull(argv[6], NULL, 10);
    return 1;
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t a, b, c, p, t, l, f, out;
    int64_t r;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldiv a b d | next/ain/aout/fee/reached/skipfee p t L rem fee | "
                "less rem fee | wrap rem fee | amt0 sa sb L up\n",
                argv[0]);
        return 2;
    }
    kind = argv[1];
    if (strcmp(kind, "selftest") == 0) return selftest();
    if (strcmp(kind, "muldiv") == 0 && argc >= 5) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n",
               (argc >= 6 && strcmp(argv[5], "--limbs") == 0) ? limbs_or_die(a, b, c)
                                                             : muldiv_i128(a, b, c));
        return 0;
    }
    if (parse_step_args(argc, argv, &p, &t, &l, &r, &f) &&
        (strcmp(kind, "next") == 0 || strcmp(kind, "ain") == 0 || strcmp(kind, "aout") == 0 ||
         strcmp(kind, "fee") == 0 || strcmp(kind, "reached") == 0 || strcmp(kind, "skipfee") == 0)) {
        if (strcmp(kind, "next") == 0) out = step_next(p, t, l, r, f);
        else if (strcmp(kind, "ain") == 0) out = step_amount_in(p, t, l, r, f);
        else if (strcmp(kind, "aout") == 0) out = step_amount_out(p, t, l, r, f);
        else if (strcmp(kind, "fee") == 0) out = step_fee(p, t, l, r, f);
        else if (strcmp(kind, "reached") == 0) out = (step_next(p, t, l, r, f) == t) ? 1 : 0;
        else out = skip_fee_next(p, t, l, r, f);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "less") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n", remaining_less_fee(strtoll(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "wrap") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", naive_fee_wrap(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "amt0") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n",
               amount0(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                       strtoull(argv[4], NULL, 10), (int)strtol(argv[5], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
