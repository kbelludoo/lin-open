/*
 * Independent C11 oracle for Uniswap V2 _mintFee / Math.sqrt (uint64 scale).
 *
 * Two implementations of (a*b)/d and of Babylonian integer sqrt:
 *   1. GCC/Clang unsigned __int128 / native uint64 division
 *   2. Portable 32-bit limbs matching src/lin_uniswap_v2_mintfee.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: Uniswap/v2-core v1.0.1
 *   contracts/UniswapV2Pair.sol _mintFee
 *   contracts/libraries/Math.sol sqrt (Babylonian)
 *   contracts/libraries/SafeMath.sol mul/add/sub
 * License of the algorithm: GPL-3.0-or-later (Uniswap). This oracle is original C11.
 * Full Solidity is NOT copied here (hash-only pin lives in the Python harness).
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

static uint64_t udiv(uint64_t a, uint64_t b) {
    if (b == 0) return 0;
    return muldiv(a, 1, b);
}

/* Uniswap V2 Math.sqrt (Babylonian), uint64, with a 80-step bound. */
static uint64_t usqrt(uint64_t y) {
    uint64_t z, x, q, s;
    int i;
    if (y == 0) return 0;
    if (y < 4) return 1;
    z = y;
    x = udiv(y, 2);
    if (x + 1 < x) return 0;
    x = x + 1;
    for (i = 0; i < 80; i++) {
        if (x >= z) return z;
        z = x;
        if (z == 0) return 0;
        q = udiv(y, z);
        if (q + z < q) return 0;
        s = q + z;
        x = udiv(s, 2);
    }
    return 0;
}

static uint64_t mint_fee(uint64_t r0, uint64_t r1, uint64_t k_last, uint64_t supply,
                         int fee_on) {
    uint64_t k, root_k, root_kl, droot, den5, den;
    if (!fee_on || k_last == 0) return 0;
    k = muldiv(r0, r1, 1);
    if (k == 0) return 0;
    root_k = usqrt(k);
    root_kl = usqrt(k_last);
    if (root_k <= root_kl) return 0;
    droot = root_k - root_kl;
    den5 = muldiv(root_k, 5, 1);
    if (den5 == 0 && root_k != 0) return 0;
    if (den5 + root_kl < den5) return 0;
    den = den5 + root_kl;
    if (den == 0) return 0;
    return muldiv(supply, droot, den);
}

static int selftest(void) {
    uint64_t a, b, d, q1, q2;
    uint64_t vecs[][3] = {
        {100, 200, 50},
        {7, 9, 1},
        {1000000000000000000ULL, 1, 2},
        {7000000000000000000ULL, 3000000000000000000ULL, 1},
        {10000, 10000, 1},
    };
    uint64_t sq[] = {0, 1, 2, 3, 4, 8, 9, 15, 16, 1000000000000000000ULL};
    size_t i;
    for (i = 0; i < sizeof(vecs) / sizeof(vecs[0]); i++) {
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
    use_limbs = 0;
    for (i = 0; i < sizeof(sq) / sizeof(sq[0]); i++) {
        uint64_t s1, s2;
        use_limbs = 0;
        s1 = usqrt(sq[i]);
        use_limbs = 1;
        s2 = usqrt(sq[i]);
        if (s1 != s2) {
            fprintf(stderr, "sqrt limb mismatch y=%" PRIu64 " s1=%" PRIu64 " s2=%" PRIu64 "\n",
                    sq[i], s1, s2);
            return 2;
        }
    }
    use_limbs = 0;
    if (usqrt(0) != 0 || usqrt(1) != 1 || usqrt(4) != 2 || usqrt(9) != 3) return 3;
    if (usqrt(1000000000000000000ULL) != 1000000000ULL) return 4;
    if (mint_fee(1000, 1000, 1000000, 1000, 1) != 0) return 5;
    if (mint_fee(1100, 1100, 1000000, 1000, 1) != 15) return 6;
    if (mint_fee(2000, 2000, 1000000, 1000, 1) != 90) return 7;
    if (mint_fee(1100, 1100, 1000000, 1000, 0) != 0) return 8;
    if (mint_fee(900, 900, 1000000, 1000, 1) != 0) return 9;
    if (mint_fee(1000000000ULL, 1000000000ULL, 1000000000000ULL, 1000000000ULL, 1) != 199760047ULL)
        return 10;
    if (muldiv_i128(7000000000000000000ULL, 3000000000000000000ULL, 1) != 0) return 11;
    puts("PASS");
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: uniswap_v2_mintfee_c11 selftest | sqrt|k|mint ... [--limbs]\n");
        return 2;
    }
    if (argc > 1 && strcmp(argv[argc - 1], "--limbs") == 0) {
        use_limbs = 1;
        argc -= 1;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "sqrt") == 0 && argc == 3) {
        printf("%" PRIu64 "\n", usqrt(strtoull(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "k") == 0 && argc == 4) {
        printf("%" PRIu64 "\n",
               muldiv(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), 1));
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc == 5) {
        printf("%" PRIu64 "\n",
               muldiv(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                      strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "mint") == 0 && argc == 7) {
        printf("%" PRIu64 "\n",
               mint_fee(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                        atoi(argv[6])));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
