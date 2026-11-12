/*
 * Independent C11 oracle for Compound CToken.accrueInterest (uint64 scale).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_compound_accrue.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: compound-finance/compound-protocol
 *   contracts/CToken.sol accrueInterest
 *   contracts/ExponentialNoError.sol mul_ScalarTruncate*
 *   contracts/CTokenInterfaces.sol borrowRateMaxMantissa = 0.0005e16
 * License of the algorithm: BSD-3-Clause (Compound). This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BASE_WAD 1000000000000000000ULL
#define RATE_MAX 5000000000000ULL /* 0.0005e16 */

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
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge, need_borrow;
    int i, ov;

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
            r_lo -= d;
            if (need_borrow) r_hi -= 1;
            if (i >= 64) ov = 1;
            else q |= (1ULL << i);
        }
    }
    if (ov) return 0;
    return q;
}

static int use_limbs = 0;

static uint64_t muldiv(uint64_t a, uint64_t b, uint64_t d) {
    return use_limbs ? muldiv_limbs(a, b, d) : muldiv_i128(a, b, d);
}

static int add_ok(uint64_t a, uint64_t b) { return (a + b) >= a; }

static int rate_ok(uint64_t rate) { return rate <= RATE_MAX; }

static uint64_t simple_factor(uint64_t rate, uint64_t delta) {
    if (!rate_ok(rate) || rate == 0 || delta == 0) return 0;
    return muldiv(rate, delta, 1);
}

static uint64_t interest(uint64_t borrows, uint64_t rate, uint64_t delta) {
    uint64_t factor = simple_factor(rate, delta);
    if (factor == 0) return 0;
    return muldiv(factor, borrows, BASE_WAD);
}

static uint64_t borrows_new(uint64_t borrows, uint64_t rate, uint64_t delta) {
    uint64_t acc;
    if (!rate_ok(rate)) return 0;
    acc = interest(borrows, rate, delta);
    if (!add_ok(borrows, acc)) return 0;
    return borrows + acc;
}

static uint64_t reserves_new(uint64_t reserves, uint64_t borrows, uint64_t rate,
                             uint64_t delta, uint64_t rf) {
    uint64_t acc, addend;
    if (!rate_ok(rate) || rf > BASE_WAD) return 0;
    acc = interest(borrows, rate, delta);
    addend = muldiv(rf, acc, BASE_WAD);
    if (!add_ok(reserves, addend)) return 0;
    return reserves + addend;
}

static uint64_t index_new(uint64_t index, uint64_t rate, uint64_t delta) {
    uint64_t factor, addend;
    if (!rate_ok(rate)) return 0;
    factor = simple_factor(rate, delta);
    addend = muldiv(factor, index, BASE_WAD);
    if (!add_ok(index, addend)) return 0;
    return index + addend;
}

static int selftest(void) {
    uint64_t a, b, d, q1, q2;
    uint64_t vecs[][3] = {
        {100, 200, 50},
        {7, 9, 1},
        {BASE_WAD, 1, 2},
        {10000000000ULL, 1, 1},
        {7000000000000000000ULL, 3000000000000000000ULL, 1},
        {10000000000ULL, BASE_WAD, BASE_WAD},
    };
    for (size_t i = 0; i < sizeof(vecs) / sizeof(vecs[0]); i++) {
        a = vecs[i][0];
        b = vecs[i][1];
        d = vecs[i][2];
        q1 = muldiv_i128(a, b, d);
        q2 = muldiv_limbs(a, b, d);
        if (q1 != q2) {
            fprintf(stderr, "limb mismatch %zu q1=%" PRIu64 " q2=%" PRIu64 "\n", i, q1, q2);
            return 1;
        }
    }
    if (interest(BASE_WAD, 10000000000ULL, 1) != 10000000000ULL) return 2;
    if (borrows_new(BASE_WAD, 10000000000ULL, 1) != 1000000010000000000ULL) return 3;
    if (index_new(BASE_WAD, 10000000000ULL, 1) != 1000000010000000000ULL) return 4;
    if (reserves_new(0, BASE_WAD, 10000000000ULL, 1, 100000000000000000ULL) != 1000000000ULL)
        return 5;
    if (borrows_new(1, RATE_MAX + 1, 1) != 0) return 6;
    if (muldiv_i128(7000000000000000000ULL, 3000000000000000000ULL, 1) != 0) return 7;
    puts("PASS");
    return 0;
}

int main(int argc, char **argv) {
    int argi = 1;
    if (argc < 2) {
        fprintf(stderr, "usage: compound_accrue_c11 selftest | interest|borrows|reserves|index ... [--limbs]\n");
        return 2;
    }
    if (argc > 1 && strcmp(argv[argc - 1], "--limbs") == 0) {
        use_limbs = 1;
        argc -= 1;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "interest") == 0 && argc == 5) {
        printf("%" PRIu64 "\n",
               interest(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "borrows") == 0 && argc == 5) {
        printf("%" PRIu64 "\n",
               borrows_new(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                           strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "index") == 0 && argc == 5) {
        printf("%" PRIu64 "\n",
               index_new(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                         strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "reserves") == 0 && argc == 7) {
        printf("%" PRIu64 "\n",
               reserves_new(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                            strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                            strtoull(argv[6], NULL, 10)));
        return 0;
    }
    (void)argi;
    fprintf(stderr, "bad args\n");
    return 2;
}
