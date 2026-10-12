/*
 * Independent C11 oracle for Uniswap V3 SqrtPriceMath getNextSqrtPriceFromOutput
 * (uint64 / Q32). Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_uniswap_v3_output.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: Uniswap/v3-core contracts/libraries/SqrtPriceMath.sol tag v1.0.0
 * Algorithm license: GPL-2.0-or-later after BUSL Change Date 2023-04-01.
 * This oracle is original C11 at Q32=2^32 (not Q96=2^96).
 * Named contrast vs getNextSqrtPriceFromInput (add=true), not a retread of it.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define Q32 4294967296ULL

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
    q = muldiv_i128(a, b, d);
    r = muldiv_rem_i128(a, b, d);
    if (((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d > UINT64_MAX) return 0;
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

static uint64_t floor_sub0(uint64_t sqrt_p, uint64_t liq, uint64_t amount) {
    uint64_t num1, product, denom;
    if (sqrt_p == 0 || liq == 0) return 0;
    if (amount == 0) return sqrt_p;
    num1 = muldiv_i128(liq, Q32, 1);
    if (num1 == 0 || mul_ov_i128(amount, sqrt_p)) return 0;
    product = amount * sqrt_p;
    if (num1 <= product) return 0;
    denom = num1 - product;
    if (denom == 0) return 0;
    return muldiv_i128(num1, sqrt_p, denom);
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

static uint64_t floor_sub1(uint64_t sqrt_p, uint64_t liq, uint64_t amount) {
    uint64_t shift, quot;
    if (sqrt_p == 0 || liq == 0) return 0;
    if (amount == 0) return sqrt_p;
    shift = muldiv_i128(amount, Q32, 1);
    if (shift == 0) {
        quot = muldiv_i128(amount, Q32, liq);
        if (quot == 0) return 0;
    } else {
        quot = shift / liq;
    }
    if (sqrt_p <= quot) return 0;
    return sqrt_p - quot;
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

static uint64_t next_from_output(uint64_t sqrt_p, uint64_t liq, uint64_t amount, int zfo) {
    if (sqrt_p == 0 || liq == 0) return 0;
    if (zfo) return next1_sub(sqrt_p, liq, amount);
    return next0_sub(sqrt_p, liq, amount);
}

static uint64_t as_input(uint64_t sqrt_p, uint64_t liq, uint64_t amount, int zfo) {
    if (sqrt_p == 0 || liq == 0) return 0;
    if (zfo) return next0_add(sqrt_p, liq, amount);
    return next1_add(sqrt_p, liq, amount);
}

static int64_t wmul(int64_t a, int64_t b) { return (int64_t)((uint64_t)a * (uint64_t)b); }
static int64_t wsub(int64_t a, int64_t b) { return (int64_t)((uint64_t)a - (uint64_t)b); }
static int64_t wdiv(int64_t a, int64_t b) {
    if (b == 0) return 0;
    if (a == INT64_MIN && b == -1) return a;
    return a / b;
}

static int64_t naive_wrap_sub0(int64_t sqrt_p, int64_t liq, int64_t amount) {
    int64_t den = wsub(liq, wmul(amount, sqrt_p));
    if (den == 0) return 0;
    return wdiv(wmul(liq, sqrt_p), den);
}

static int64_t naive_underflow(int64_t sqrt_p, int64_t liq, int64_t amount) {
    int64_t shift, quot, r;
    if (liq == 0) return 0;
    shift = wmul(amount, (int64_t)Q32);
    quot = wdiv(shift, liq);
    r = wsub(shift, wmul(quot, liq));
    if (r != 0) quot = quot + 1;
    return wsub(sqrt_p, quot);
}

static uint64_t limbs_or_die(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    (void)r;
    if (ov) return 0;
    return q;
}

static int selftest(void) {
    uint64_t q, r;
    int ov;
    if (muldiv_i128(100, 200, 50) != 400) return 1;
    if (limbs_or_die(100, 200, 50) != 400) return 2;
    muldiv_limbs_qr(7, 9, 2, &q, &r, &ov);
    if (ov || q != 31 || r != 1) return 3;
    if (muldiv_i128(1000000000000000000ULL, 1000000000000000000ULL, 1) != 0) return 4;
    if (next_from_output(Q32, 1000000ULL, 500000ULL, 1) != 2147483648ULL) return 5;
    if (as_input(Q32, 1000000ULL, 500000ULL, 1) != 2863311531ULL) return 6;
    if (next_from_output(Q32, 1000000ULL, 500000ULL, 0) != 8589934592ULL) return 7;
    if (as_input(Q32, 1000000ULL, 500000ULL, 0) != 6442450944ULL) return 8;
    if (next1_sub(Q32, 1000000ULL, 1ULL) != 4294963001ULL) return 9;
    if (floor_sub1(Q32, 1000000ULL, 1ULL) != 4294963002ULL) return 10;
    if (next0_sub(Q32, 1000000ULL, 1ULL) != 4294971591ULL) return 11;
    if (floor_sub0(Q32, 1000000ULL, 1ULL) != 4294971590ULL) return 12;
    if (next_from_output(Q32, 1000000ULL, 1000000ULL, 1) != 0) return 13;
    if (naive_wrap_sub0((int64_t)Q32, 1000000LL, 500000LL) != -2) return 14;
    if (naive_underflow((int64_t)Q32, 1000000LL, 1000001LL) != -4295) return 15;
    fprintf(stdout, "PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t a, b, c, d;
    int zfo;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldiv a b d | out p L amt zfo | asinput p L amt zfo | "
                "n0sub p L amt | n1sub p L amt | floor0 p L amt | floor1 p L amt | "
                "naive0 p L amt | under p L amt\n",
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
    if ((strcmp(kind, "out") == 0 || strcmp(kind, "asinput") == 0) && argc >= 6) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        zfo = (int)strtol(argv[5], NULL, 10);
        d = (strcmp(kind, "out") == 0) ? next_from_output(a, b, c, zfo) : as_input(a, b, c, zfo);
        printf("%" PRIu64 "\n", d);
        return 0;
    }
    if (argc >= 5 && (strcmp(kind, "n0sub") == 0 || strcmp(kind, "n1sub") == 0 ||
                      strcmp(kind, "floor0") == 0 || strcmp(kind, "floor1") == 0)) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        if (strcmp(kind, "n0sub") == 0) d = next0_sub(a, b, c);
        else if (strcmp(kind, "n1sub") == 0) d = next1_sub(a, b, c);
        else if (strcmp(kind, "floor0") == 0) d = floor_sub0(a, b, c);
        else d = floor_sub1(a, b, c);
        printf("%" PRIu64 "\n", d);
        return 0;
    }
    if ((strcmp(kind, "naive0") == 0 || strcmp(kind, "under") == 0) && argc >= 5) {
        int64_t sa = (int64_t)strtoll(argv[2], NULL, 10);
        int64_t sb = (int64_t)strtoll(argv[3], NULL, 10);
        int64_t sc = (int64_t)strtoll(argv[4], NULL, 10);
        int64_t out = (strcmp(kind, "naive0") == 0) ? naive_wrap_sub0(sa, sb, sc)
                                                    : naive_underflow(sa, sb, sc);
        printf("%" PRId64 "\n", out);
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
