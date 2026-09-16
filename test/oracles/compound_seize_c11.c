/*
 * Independent C11 oracle for Compound liquidateCalculateSeizeTokens
 * (uint64 scale). Two (a*b)/d implementations:
 *   1. unsigned __int128
 *   2. portable 32-bit limbs matching src/lin_compound_seize.lin
 * Consensus between (1) and (2) is required before any LIN comparison.
 * Not linked into the LIN compiler TCB.
 *
 * Algorithm: compound-finance/compound-protocol Comptroller.sol +
 * ExponentialNoError.sol (BSD-3-Clause). This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BASE_WAD 1000000000000000000ULL

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
            if (need_borrow) r_hi = r_hi - 1;
            if (i >= 64) ov = 1;
            if (i < 64) q = q | (1ULL << i);
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

static uint64_t muldiv_rem_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return r;
}

static uint64_t seize_with(uint64_t repay, uint64_t incentive, uint64_t pb,
                           uint64_t pc, uint64_t exch,
                           uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t num_m, den_m, ratio_m;
    if (pb == 0 || pc == 0 || exch == 0) return 0;
    num_m = md(incentive, pb, BASE_WAD);
    den_m = md(pc, exch, BASE_WAD);
    if (den_m == 0) return 0;
    ratio_m = md(num_m, BASE_WAD, den_m);
    return md(ratio_m, repay, BASE_WAD);
}

static int selftest(void) {
    uint64_t a, b, d, q1, q2, r1, r2, s1, s2;
    const uint64_t base = BASE_WAD;
    const uint64_t vec[][3] = {
        {100, 200, 50},
        {7, 9, 1},
        {base, 1, 2},
        {base, base, 1},
        {1080000000000000000ULL, base, base},
    };
    size_t i;
    for (i = 0; i < sizeof(vec) / sizeof(vec[0]); i++) {
        a = vec[i][0];
        b = vec[i][1];
        d = vec[i][2];
        q1 = muldiv_i128(a, b, d);
        q2 = muldiv_limbs(a, b, d);
        r1 = muldiv_rem_i128(a, b, d);
        r2 = muldiv_rem_limbs(a, b, d);
        if (q1 != q2 || r1 != r2) {
            fprintf(stderr, "muldiv mismatch i=%zu\n", i);
            return 1;
        }
    }
    s1 = seize_with(1000, 1080000000000000000ULL, base, base, 200000000000000000ULL, muldiv_i128);
    s2 = seize_with(1000, 1080000000000000000ULL, base, base, 200000000000000000ULL, muldiv_limbs);
    if (s1 != 5400ULL || s1 != s2) {
        fprintf(stderr, "seize canonical mismatch %" PRIu64 " %" PRIu64 "\n", s1, s2);
        return 1;
    }
    printf("PASS\n");
    return 0;
}

static int use_limbs(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    uint64_t (*md)(uint64_t, uint64_t, uint64_t);
    uint64_t (*mdr)(uint64_t, uint64_t, uint64_t);
    if (argc < 2) {
        fprintf(stderr, "usage: compound_seize_c11 selftest|muldiv|seize ... [--limbs]\n");
        return 2;
    }
    md = use_limbs(argc, argv) ? muldiv_limbs : muldiv_i128;
    mdr = use_limbs(argc, argv) ? muldiv_rem_limbs : muldiv_rem_i128;
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                   strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "muldiv-rem") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", mdr(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                    strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "seize") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               seize_with(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                          strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                          strtoull(argv[6], NULL, 10), md));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
