/*
 * Independent C11 oracle for EIP-4844 fakeExponential / CalcBlobFee (uint64 scale).
 *
 * Two products for (accum * numerator) / denominator:
 *   1. unsigned __int128
 *   2. portable 32-bit limbs matching src/lin_eip4844_blobfee.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: ethereum/go-ethereum v1.14.12 consensus/misc/eip4844/eip4844.go
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

static uint64_t fake_exp(uint64_t factor, uint64_t numerator, uint64_t denominator, int limbs) {
    uint64_t output = 0;
    uint64_t accum;
    uint64_t i = 1;
    uint64_t sum;
    if ((int64_t)factor < 0 || (int64_t)numerator < 0 || denominator == 0) return 0;
    accum = limbs ? muldiv_limbs(factor, denominator, 1) : muldiv_i128(factor, denominator, 1);
    if (factor != 0 && denominator != 0 && accum == 0) return 0;
    while (accum > 0) {
        sum = output + accum;
        if (sum < output) return 0;
        output = sum;
        accum = limbs ? muldiv_limbs(accum, numerator, denominator) : muldiv_i128(accum, numerator, denominator);
        accum = limbs ? muldiv_limbs(accum, 1, i) : muldiv_i128(accum, 1, i);
        i++;
        if (i > 4096) return 0;
    }
    return limbs ? muldiv_limbs(output, 1, denominator) : muldiv_i128(output, 1, denominator);
}

static uint64_t calc_excess(uint64_t parent_excess, uint64_t parent_used, uint64_t target) {
    uint64_t excess;
    if ((int64_t)parent_excess < 0 || (int64_t)parent_used < 0) return 0;
    excess = parent_excess + parent_used;
    if (excess < parent_excess) return 0;
    if (excess < target) return 0;
    return excess - target;
}

static uint64_t naive_u64_muldiv(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 0;
    return (a * b) / d; /* wrapping uint64 */
}

static int selftest(void) {
    uint64_t a, b;
    a = fake_exp(1, 0, 1, 0);
    b = fake_exp(1, 0, 1, 1);
    if (a != 1 || a != b) return 1;
    a = fake_exp(1, 2, 1, 0);
    b = fake_exp(1, 2, 1, 1);
    if (a != 6 || a != b) return 2;
    a = fake_exp(1, 2314058, 3338477, 0);
    b = fake_exp(1, 2314058, 3338477, 1);
    if (a != 2 || a != b) return 3;
    a = fake_exp(1, 10485760, 3338477, 0);
    b = fake_exp(1, 10485760, 3338477, 1);
    if (a != 23 || a != b) return 4;
    a = fake_exp(1, 50000000, 2225652, 0);
    b = fake_exp(1, 50000000, 2225652, 1);
    if (a != 5709098764ULL || a != b) return 5;
    a = calc_excess(0, 524288, 393216);
    if (a != 131072) return 6;
    a = muldiv_i128(100, 200, 50);
    b = muldiv_limbs(100, 200, 50);
    if (a != 400 || a != b) return 7;
    return 0;
}

int main(int argc, char **argv) {
    uint64_t factor, numerator, denominator, excess, parent_excess, parent_used, target;
    int limbs = 0;
    int i;
    if (argc < 2) {
        fprintf(stderr, "usage: eip4844_blobfee_c11 selftest | exp f n d [--limbs] | fee excess [--limbs] | excess pe pu tgt | muldiv a b d [--limbs] | naive-muldiv a b d\n");
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
    if (strcmp(argv[1], "naive-muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", naive_u64_muldiv(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "exp") == 0 && argc >= 5) {
        factor = strtoull(argv[2], NULL, 10);
        numerator = strtoull(argv[3], NULL, 10);
        denominator = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", fake_exp(factor, numerator, denominator, limbs));
        return 0;
    }
    if (strcmp(argv[1], "fee") == 0 && argc >= 3) {
        excess = strtoull(argv[2], NULL, 10);
        printf("%" PRIu64 "\n", fake_exp(1, excess, 3338477ULL, limbs));
        return 0;
    }
    if (strcmp(argv[1], "excess") == 0 && argc >= 5) {
        parent_excess = strtoull(argv[2], NULL, 10);
        parent_used = strtoull(argv[3], NULL, 10);
        target = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", calc_excess(parent_excess, parent_used, target));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
