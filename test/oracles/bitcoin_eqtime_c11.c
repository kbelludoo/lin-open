/*
 * Independent C11 oracle for Bitcoin Core GetBlockProofEquivalentTime
 * (uint64-scale chain work, 128-bit product).
 *
 * Consensus between unsigned __int128 and a portable 32-bit limb muldiv is
 * required before any LIN comparison. Not linked into the LIN compiler TCB.
 *
 * Upstream: bitcoin/bitcoin v27.1 src/chain.cpp (MIT).
 * This file is an original C11 oracle of the scalar formula, not a copy of Core.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64_MAX 9223372036854775807LL

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
    *q_out = q;
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d, int *sat) {
    if (d == 0) {
        *sat = 1;
        return 0;
    }
    __uint128_t prod = (__uint128_t)a * (__uint128_t)b;
    __uint128_t q = prod / (__uint128_t)d;
    if (q > (__uint128_t)INT64_MAX) {
        *sat = 1;
        return 0;
    }
    *sat = 0;
    return (uint64_t)q;
}

static int64_t eqtime_i128(int64_t to_work, int64_t from_work, int64_t tip_proof, int64_t spacing) {
    int sat;
    uint64_t q;
    int sign = 1;
    uint64_t hi, lo, delta;
    if (to_work < 0 || from_work < 0 || tip_proof <= 0 || spacing < 0) return 0;
    if ((uint64_t)to_work < (uint64_t)from_work) {
        sign = -1;
        hi = (uint64_t)from_work;
        lo = (uint64_t)to_work;
    } else {
        hi = (uint64_t)to_work;
        lo = (uint64_t)from_work;
    }
    delta = hi - lo;
    q = muldiv_i128(delta, (uint64_t)spacing, (uint64_t)tip_proof, &sat);
    if (sat) return sign * I64_MAX;
    return sign * (int64_t)q;
}

static int64_t eqtime_limbs(int64_t to_work, int64_t from_work, int64_t tip_proof, int64_t spacing) {
    uint64_t q, r;
    int ov, sign = 1;
    uint64_t hi, lo, delta;
    if (to_work < 0 || from_work < 0 || tip_proof <= 0 || spacing < 0) return 0;
    if ((uint64_t)to_work < (uint64_t)from_work) {
        sign = -1;
        hi = (uint64_t)from_work;
        lo = (uint64_t)to_work;
    } else {
        hi = (uint64_t)to_work;
        lo = (uint64_t)from_work;
    }
    delta = hi - lo;
    muldiv_limbs_qr(delta, (uint64_t)spacing, (uint64_t)tip_proof, &q, &r, &ov);
    if (ov || (q >> 63)) return sign * I64_MAX;
    return sign * (int64_t)q;
}

static int selftest(void) {
    int64_t a, b;
    if (eqtime_i128(2, 0, 2, 600) != 600) return 1;
    if (eqtime_limbs(2, 0, 2, 600) != 600) return 2;
    if (eqtime_i128(0, 2, 2, 600) != -600) return 3;
    if (eqtime_i128(200, 80, 2, 600) != 36000) return 4;
    if (eqtime_limbs(200, 80, 2, 600) != 36000) return 5;
    if (eqtime_i128(0, 0, 0, 600) != 0) return 6;
    a = eqtime_i128(4611686018427387904LL, 0, 1, 2);
    b = eqtime_limbs(4611686018427387904LL, 0, 1, 2);
    if (a != I64_MAX || b != I64_MAX) return 7;
    if (eqtime_i128(1000000000000000000LL, 0, 100, 10) != 100000000000000000LL) return 8;
    if (eqtime_limbs(1000000000000000000LL, 0, 100, 10) != 100000000000000000LL) return 9;
    return 0;
}

int main(int argc, char **argv) {
    int64_t to_w, from_w, proof, spacing, vi, vl;
    if (argc < 2) {
        fprintf(stderr, "usage: bitcoin_eqtime_c11 selftest | eqtime TO FROM PROOF SPACING [--limbs]\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        int rc = selftest();
        if (rc == 0) {
            printf("PASS\n");
            return 0;
        }
        printf("FAIL %d\n", rc);
        return 1;
    }
    if (strcmp(argv[1], "eqtime") != 0 || argc < 6) return 2;
    to_w = strtoll(argv[2], NULL, 10);
    from_w = strtoll(argv[3], NULL, 10);
    proof = strtoll(argv[4], NULL, 10);
    spacing = strtoll(argv[5], NULL, 10);
    vi = eqtime_i128(to_w, from_w, proof, spacing);
    vl = eqtime_limbs(to_w, from_w, proof, spacing);
    if (vi != vl) {
        fprintf(stderr, "i128/limbs mismatch %" PRId64 " vs %" PRId64 "\n", vi, vl);
        return 1;
    }
    if (argc >= 7 && strcmp(argv[6], "--limbs") == 0) printf("%" PRId64 "\n", vl);
    else printf("%" PRId64 "\n", vi);
    return 0;
}
