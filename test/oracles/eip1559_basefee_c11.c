/*
 * Independent C11 oracle for EIP-1559 CalcBaseFee (uint64 scale).
 *
 * Two products for (fee * gas_delta) / target:
 *   1. unsigned __int128
 *   2. portable 32-bit limbs matching src/lin_eip1559_basefee.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: ethereum/go-ethereum v1.14.12 consensus/misc/eip1559/eip1559.go
 * License of the upstream file: LGPL-3.0. This oracle is original C11.
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

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge;
    int i, ov, need_borrow;

    if (d == 0) return 0;
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
            else q = q | (1ULL << i);
        }
    }
    if (ov) return 0;
    return q;
}

static uint64_t fee_delta(uint64_t fee, uint64_t gas_delta, uint64_t target, uint64_t denom, int limbs) {
    uint64_t x;
    if (target == 0 || denom == 0) return 0;
    if (limbs) x = muldiv_limbs(fee, gas_delta, target);
    else x = muldiv_i128(fee, gas_delta, target);
    if (limbs) return muldiv_limbs(x, 1, denom);
    return muldiv_i128(x, 1, denom);
}

static uint64_t calc_base_fee(uint64_t limit, uint64_t used, uint64_t fee,
                              uint64_t elasticity, uint64_t denom, uint64_t london, int limbs) {
    uint64_t target, delta, sum;
    if ((int64_t)limit < 0 || (int64_t)used < 0 || (int64_t)fee < 0) return 0;
    if (elasticity == 0 || denom == 0) return 0;
    if (london == 0) return 1000000000ULL;
    target = limit / elasticity;
    if (used == target) return fee;
    if (used > target) {
        delta = fee_delta(fee, used - target, target, denom, limbs);
        if (delta < 1) delta = 1;
        sum = fee + delta;
        if (sum < fee) return 0;
        return sum;
    }
    delta = fee_delta(fee, target - used, target, denom, limbs);
    if (fee < delta) return 0;
    return fee - delta;
}

static uint64_t naive_u64_delta(uint64_t fee, uint64_t gas_delta, uint64_t target, uint64_t denom) {
    uint64_t x;
    if (target == 0 || denom == 0) return 0;
    x = (fee * gas_delta) / target; /* wrapping uint64 */
    return x / denom;
}

static int selftest(void) {
    uint64_t a, b;
    a = calc_base_fee(30000000ULL, 15000000ULL, 1000000000ULL, 2, 8, 1, 0);
    b = calc_base_fee(30000000ULL, 15000000ULL, 1000000000ULL, 2, 8, 1, 1);
    if (a != 1000000000ULL || a != b) return 1;
    a = calc_base_fee(30000000ULL, 30000000ULL, 1000000000ULL, 2, 8, 1, 0);
    b = calc_base_fee(30000000ULL, 30000000ULL, 1000000000ULL, 2, 8, 1, 1);
    if (a != 1125000000ULL || a != b) return 2;
    a = calc_base_fee(30000000ULL, 0ULL, 1000000000ULL, 2, 8, 1, 0);
    b = calc_base_fee(30000000ULL, 0ULL, 1000000000ULL, 2, 8, 1, 1);
    if (a != 875000000ULL || a != b) return 3;
    a = muldiv_i128(100, 200, 50);
    b = muldiv_limbs(100, 200, 50);
    if (a != 400 || a != b) return 4;
    return 0;
}

int main(int argc, char **argv) {
    uint64_t limit, used, fee, elasticity, denom, london;
    int limbs = 0;
    int i;
    if (argc < 2) {
        fprintf(stderr, "usage: eip1559_basefee_c11 selftest | calc limit used fee elast denom london [--limbs] | naive-delta fee dgas target denom | muldiv a b d [--limbs]\n");
        return 2;
    }
    for (i = 2; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) limbs = 1;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        i = selftest();
        if (i != 0) {
            printf("FAIL %d\n", i);
            return 1;
        }
        printf("PASS\n");
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", limbs ? muldiv_limbs(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), strtoull(argv[4], NULL, 10))
                                      : muldiv_i128(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "naive-delta") == 0 && argc >= 6) {
        printf("%" PRIu64 "\n", naive_u64_delta(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                                strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "calc") == 0 && argc >= 8) {
        limit = strtoull(argv[2], NULL, 10);
        used = strtoull(argv[3], NULL, 10);
        fee = strtoull(argv[4], NULL, 10);
        elasticity = strtoull(argv[5], NULL, 10);
        denom = strtoull(argv[6], NULL, 10);
        london = strtoull(argv[7], NULL, 10);
        printf("%" PRIu64 "\n", calc_base_fee(limit, used, fee, elasticity, denom, london, limbs));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
