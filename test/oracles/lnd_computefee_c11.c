/*
 * Independent C11 oracle for lnd BOLT07 ComputeFee / inbound CalcFee
 * (uint64 scale, 128-bit product).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_lnd_computefee.lin
 *
 * Also exposes Go's wrapping uint64 (amt*ppm)/1e6 so the harness can prove
 * LIN/C11-i128 disagree with silent wrap.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: lightningnetwork/lnd (MIT) v0.21.3-beta.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FEE_PARTS 1000000ULL
#define MAX_FEE_RATE (10ULL * FEE_PARTS)

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
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge;
    int i, ov, need_borrow;

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

static uint64_t compute_fee(uint64_t base, uint64_t ppm, uint64_t amt,
                            uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t prop = md(amt, ppm, FEE_PARTS);
    if (base > UINT64_MAX - prop) return 0;
    return base + prop;
}

static uint64_t incoming(uint64_t base, uint64_t ppm, uint64_t outgoing,
                         uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t f = compute_fee(base, ppm, outgoing, md);
    if (outgoing > UINT64_MAX - f) return 0;
    return outgoing + f;
}

static int64_t inbound_calc(int64_t base, int64_t rate, uint64_t amt) {
    int64_t mag, p_s;
    uint64_t p;
    if ((uint64_t)rate > 0 && rate > (int64_t)MAX_FEE_RATE) rate = (int64_t)MAX_FEE_RATE;
    if (rate < 0 && rate < -(int64_t)MAX_FEE_RATE) rate = -(int64_t)MAX_FEE_RATE;
    mag = rate < 0 ? -rate : rate;
    p = muldiv_i128(amt, (uint64_t)mag, FEE_PARTS);
    p_s = rate < 0 ? -(int64_t)p : (int64_t)p;
    return base + p_s;
}

static uint64_t go_wrap_fee(uint64_t base, uint64_t ppm, uint64_t amt) {
    return base + (amt * ppm) / FEE_PARTS;
}

static int selftest(void) {
    int fail = 0;
    uint64_t q1, q2;
    if (compute_fee(1000, 1, 1000000, muldiv_i128) != 1001) fail++;
    if (compute_fee(1000, 1, 1000000, muldiv_limbs) != 1001) fail++;
    if (compute_fee(1000, 100, 100000000, muldiv_i128) != 11000) fail++;
    if (incoming(1000, 100, 100000000, muldiv_i128) != 100011000ULL) fail++;
    if (inbound_calc(5, 500000, 2) != 6) fail++;
    if (inbound_calc(5, 500000, 3) != 6) fail++;
    if (inbound_calc(-5, -500000, 2) != -6) fail++;
    if (inbound_calc(-5, -500000, 3) != -6) fail++;
    if (inbound_calc(0, 20000000, 1000000) != 10000000) fail++;
    q1 = muldiv_i128(4294967296ULL, 4294967296ULL, FEE_PARTS);
    q2 = muldiv_limbs(4294967296ULL, 4294967296ULL, FEE_PARTS);
    if (q1 != 18446744073709ULL || q1 != q2) fail++;
    if (muldiv_rem_i128(7, 9, 2) != 1) fail++;
    if (go_wrap_fee(0, 4294967296ULL, 4294967296ULL) == q1) fail++;
    if (fail) {
        fprintf(stderr, "selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("PASS\n");
    return 0;
}

static int limbs_flag(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    uint64_t (*md)(uint64_t, uint64_t, uint64_t);
    if (argc < 2) {
        fprintf(stderr, "usage: lnd_computefee_c11 selftest|fee|incoming|inbound|wrap|muldiv ...\n");
        return 2;
    }
    md = limbs_flag(argc, argv) ? muldiv_limbs : muldiv_i128;
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "fee") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", compute_fee(strtoull(argv[2], NULL, 10),
                                            strtoull(argv[3], NULL, 10),
                                            strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "incoming") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", incoming(strtoull(argv[2], NULL, 10),
                                         strtoull(argv[3], NULL, 10),
                                         strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "inbound") == 0 && argc >= 5) {
        printf("%" PRId64 "\n", inbound_calc(strtoll(argv[2], NULL, 10),
                                             strtoll(argv[3], NULL, 10),
                                             strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "wrap") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", go_wrap_fee(strtoull(argv[2], NULL, 10),
                                            strtoull(argv[3], NULL, 10),
                                            strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", md(strtoull(argv[2], NULL, 10),
                                   strtoull(argv[3], NULL, 10),
                                   strtoull(argv[4], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
