/*
 * Independent C11 oracle for Uniswap V3 SqrtPriceMath amount deltas (uint64 scale).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_uniswap_v3_sqrt.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: Uniswap/v3-core contracts/libraries/SqrtPriceMath.sol
 * License of the algorithm: GPL-2.0-or-later after BUSL Change Date 2023-04-01.
 * This oracle is original C11. Experimental Q32=2^32 scale, not Q96=2^96.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define Q32 4294967296ULL

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

static int muldiv_ov_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 1;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    return q > UINT64_MAX;
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

static uint64_t (*MD)(uint64_t, uint64_t, uint64_t) = muldiv_i128;
static int use_limb_ov;

static int md_ov(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    if (!use_limb_ov) return muldiv_ov_i128(a, b, d);
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return ov;
}

static uint64_t md_rem(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    if (!use_limb_ov) return muldiv_rem_i128(a, b, d);
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return r;
}

static uint64_t muldiv_up(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r, s;
    if (d == 0) return 0;
    if (md_ov(a, b, d)) return 0;
    q = MD(a, b, d);
    r = md_rem(a, b, d);
    if (r == 0) return q;
    s = q + 1;
    if (s < q) return 0;
    return s;
}

static void sort2(uint64_t a, uint64_t b, uint64_t *lo, uint64_t *hi) {
    if (b < a) {
        *lo = b;
        *hi = a;
    } else {
        *lo = a;
        *hi = b;
    }
}

static uint64_t num1(uint64_t liq) {
    if (liq == 0) return 0;
    if (md_ov(liq, Q32, 1)) return 0;
    return MD(liq, Q32, 1);
}

static uint64_t amount0(uint64_t sa, uint64_t sb, uint64_t liq, int round_up) {
    uint64_t lo, hi, n1, n2, inner;
    sort2(sa, sb, &lo, &hi);
    if (lo == 0) return 0;
    n1 = num1(liq);
    if (liq != 0 && n1 == 0) return 0;
    n2 = hi - lo;
    if (round_up) {
        inner = muldiv_up(n1, n2, hi);
        return muldiv_up(inner, 1, lo);
    }
    inner = MD(n1, n2, hi);
    return MD(inner, 1, lo);
}

static uint64_t amount1(uint64_t sa, uint64_t sb, uint64_t liq, int round_up) {
    uint64_t lo, hi, n2;
    sort2(sa, sb, &lo, &hi);
    n2 = hi - lo;
    if (round_up) return muldiv_up(liq, n2, Q32);
    return MD(liq, n2, Q32);
}

static uint64_t naive_amt0(uint64_t sa, uint64_t sb, uint64_t liq) {
    uint64_t lo, hi, den, n2;
    sort2(sa, sb, &lo, &hi);
    if (lo == 0) return 0;
    den = MD(lo, hi, 1);
    if (den == 0) return 0;
    n2 = hi - lo;
    return MD(liq, n2, den);
}

static int selftest(void) {
    uint64_t q1, r1, q2, r2;
    int ov;
    uint64_t a, b, d;
    const uint64_t vec[][3] = {
        {100, 200, 50}, {7, 9, 1}, {7, 9, 2}, {1000000ULL, Q32, 1}
    };
    size_t i;
    uint64_t Q = Q32;
    uint64_t L = 1000000ULL;
    for (i = 0; i < sizeof(vec) / sizeof(vec[0]); i++) {
        a = vec[i][0];
        b = vec[i][1];
        d = vec[i][2];
        q1 = muldiv_i128(a, b, d);
        muldiv_limbs_qr(a, b, d, &q2, &r2, &ov);
        (void)ov;
        r1 = muldiv_rem_i128(a, b, d);
        if (q1 != q2 || r1 != r2) {
            printf("SELFTEST FAIL muldiv\n");
            return 1;
        }
    }
    MD = muldiv_i128;
    use_limb_ov = 0;
    if (amount0(Q, Q + Q, L, 0) != 500000ULL) return 1;
    if (amount1(Q, Q + Q, L, 0) != 1000000ULL) return 1;
    MD = muldiv_limbs;
    use_limb_ov = 1;
    if (amount0(Q, Q + Q, L, 0) != 500000ULL) return 1;
    if (amount0(Q, Q + 1, 1, 1) != 1ULL) return 1;
    MD = muldiv_i128;
    use_limb_ov = 0;
    printf("PASS\n");
    return 0;
}

static void use_limbs(int argc, char **argv) {
    int i;
    MD = muldiv_i128;
    use_limb_ov = 0;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) {
            MD = muldiv_limbs;
            use_limb_ov = 1;
        }
    }
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t a, b, c, e, out;
    int up;
    if (argc < 2) {
        fprintf(stderr, "usage: uniswap_v3_sqrt_c11 selftest | muldiv A B D [--limbs] | muldivup A B D | amount0 SA SB L UP | amount1 SA SB L UP | naive0 SA SB L\n");
        return 2;
    }
    kind = argv[1];
    if (strcmp(kind, "selftest") == 0) return selftest();
    use_limbs(argc, argv);
    if (strcmp(kind, "muldiv") == 0 && argc >= 5) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", MD(a, b, c));
        return 0;
    }
    if (strcmp(kind, "muldivup") == 0 && argc >= 5) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", muldiv_up(a, b, c));
        return 0;
    }
    if ((strcmp(kind, "amount0") == 0 || strcmp(kind, "amount1") == 0) && argc >= 6) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        up = (int)strtol(argv[5], NULL, 10);
        out = (strcmp(kind, "amount0") == 0) ? amount0(a, b, c, up) : amount1(a, b, c, up);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "naive0") == 0 && argc >= 5) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        e = naive_amt0(a, b, c);
        printf("%" PRIu64 "\n", e);
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
