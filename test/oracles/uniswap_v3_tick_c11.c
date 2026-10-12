/*
 * Independent C11 oracle for Uniswap V3 TickMath.getSqrtRatioAtTick (Q32 scale).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_uniswap_v3_tick.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: Uniswap/v3-core contracts/libraries/TickMath.sol
 * (GPL-2.0-or-later after BUSL Change Date 2023-04-01). Reduced Q32, 14-bit
 * |tick|<=16383. Not Q64.96 / uint160 mainnet parity.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define Q32 4294967296ULL
#define MAX_TICK 16383

static const uint64_t MAGIC[14] = {
    4294752563ULL, 4294537842ULL, 4294108431ULL, 4293249738ULL,
    4291532867ULL, 4288101185ULL, 4281246052ULL, 4267568644ULL,
    4240344775ULL, 4186416933ULL, 4080610056ULL, 3876951157ULL,
    3499619261ULL, 2851554886ULL
};

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
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

static uint64_t sqrt_neg(uint64_t abs, uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t ratio = Q32;
    int i;
    if (abs & 1ULL) ratio = MAGIC[0];
    for (i = 1; i < 14; i++) {
        if (abs & (1ULL << i)) ratio = md(ratio, MAGIC[i], Q32);
    }
    return ratio;
}

static uint64_t sqrt_at_tick(int64_t tick, uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    int64_t abs_t = tick < 0 ? -tick : tick;
    uint64_t ratio;
    if (abs_t > MAX_TICK) return 0;
    ratio = sqrt_neg((uint64_t)abs_t, md);
    if (ratio == 0) return 0;
    if (tick > 0) return md(Q32, Q32, ratio);
    return ratio;
}

static int64_t naive_linear(int64_t tick) {
    int64_t q = (int64_t)Q32;
    return q + (q * tick) / 20000;
}

static int64_t naive_invert(uint64_t ratio) {
    int64_t q = (int64_t)Q32;
    if (ratio == 0) return 0;
    return (q * q) / (int64_t)ratio;
}

static int selftest(void) {
    int fail = 0;
    uint64_t t0a, t0b, t1a, t1b, tn1a, tn1b, t8a, t8b, tma, tmb;
    if (muldiv_i128(100, 200, 50) != 400) fail++;
    if (muldiv_limbs(100, 200, 50) != 400) fail++;
    if (muldiv_i128(Q32, Q32, MAGIC[0]) != muldiv_limbs(Q32, Q32, MAGIC[0])) fail++;
    t0a = sqrt_at_tick(0, muldiv_i128);
    t0b = sqrt_at_tick(0, muldiv_limbs);
    if (t0a != Q32 || t0a != t0b) fail++;
    t1a = sqrt_at_tick(1, muldiv_i128);
    t1b = sqrt_at_tick(1, muldiv_limbs);
    if (t1a != 4295182039ULL || t1a != t1b) fail++;
    tn1a = sqrt_at_tick(-1, muldiv_i128);
    tn1b = sqrt_at_tick(-1, muldiv_limbs);
    if (tn1a != MAGIC[0] || tn1a != tn1b) fail++;
    if (sqrt_at_tick(2, muldiv_i128) != 4295396792ULL) fail++;
    t8a = sqrt_at_tick(8192, muldiv_i128);
    t8b = sqrt_at_tick(8192, muldiv_limbs);
    if (t8a != 6469012455ULL || t8a != t8b) fail++;
    if ((uint64_t)naive_linear(8192) >= t8a) fail++;
    tma = sqrt_at_tick(MAX_TICK, muldiv_i128);
    tmb = sqrt_at_tick(MAX_TICK, muldiv_limbs);
    if (tma != 9743038112ULL || tma != tmb) fail++;
    if (sqrt_at_tick(-MAX_TICK, muldiv_i128) != 1893325661ULL) fail++;
    if (sqrt_at_tick(16384, muldiv_i128) != 0) fail++;
    if (naive_invert(MAGIC[0]) != 0) fail++;
    if (t1a == (uint64_t)naive_invert(MAGIC[0])) fail++;
    if (sqrt_at_tick(1000, muldiv_i128) != 4515163696ULL) fail++;
    if (fail) {
        fprintf(stderr, "uniswap_v3_tick_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("uniswap_v3_tick_c11 selftest PASS\n");
    printf("vector.tick0=%" PRIu64 "\n", t0a);
    printf("vector.tick1=%" PRIu64 "\n", t1a);
    printf("vector.tick_m1=%" PRIu64 "\n", tn1a);
    printf("vector.tick8192=%" PRIu64 "\n", t8a);
    printf("vector.tick16383=%" PRIu64 "\n", tma);
    printf("vector.linear8192=%" PRId64 "\n", naive_linear(8192));
    printf("vector.naive_invert_magic0=%" PRId64 "\n", naive_invert(MAGIC[0]));
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    uint64_t (*md)(uint64_t, uint64_t, uint64_t) = muldiv_i128;
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest | muldiv a b d | tick t | linear t | invert ratio\n",
                argv[0]);
        return 2;
    }
    cmd = argv[1];
    if (argc >= 3 && strcmp(argv[argc - 1], "--limbs") == 0) {
        md = muldiv_limbs;
        argc--;
    }
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "muldiv") == 0 && argc == 5) {
        uint64_t a = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t d = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", md(a, b, d));
        return 0;
    }
    if (strcmp(cmd, "tick") == 0 && argc == 3) {
        int64_t t = strtoll(argv[2], NULL, 10);
        printf("%" PRIu64 "\n", sqrt_at_tick(t, md));
        return 0;
    }
    if (strcmp(cmd, "linear") == 0 && argc == 3) {
        int64_t t = strtoll(argv[2], NULL, 10);
        printf("%" PRId64 "\n", naive_linear(t));
        return 0;
    }
    if (strcmp(cmd, "invert") == 0 && argc == 3) {
        uint64_t r = strtoull(argv[2], NULL, 10);
        printf("%" PRId64 "\n", naive_invert(r));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
