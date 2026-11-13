/*
 * Independent C11 oracle for Pendle SYUtils math (uint64 scale).
 *
 * Two implementations of floor/ceil (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_pendle_syutils.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: pendle-finance/pendle-core-v2-public
 *   contracts/core/StandardizedYield/SYUtils.sol (GPL-3.0-or-later, hash-pinned,
 *   not vendored). This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ONE_WAD 1000000000000000000ULL

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

static uint64_t muldiv_ceil_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t prod, q, r;
    if (d == 0) return 0;
    prod = (__uint128_t)a * (__uint128_t)b;
    q = prod / (__uint128_t)d;
    r = prod % (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    if (r == 0) return (uint64_t)q;
    if (q == UINT64_MAX) return 0;
    return (uint64_t)q + 1u;
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

static uint64_t muldiv_ceil_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    if (d == 0) return 0;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    if (ov) return 0;
    if (r == 0) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1u;
}

static uint64_t sy_to_asset(uint64_t rate, uint64_t sy, int ceil, int limbs) {
    if (ceil) {
        return limbs ? muldiv_ceil_limbs(sy, rate, ONE_WAD)
                     : muldiv_ceil_i128(sy, rate, ONE_WAD);
    }
    return limbs ? muldiv_limbs(sy, rate, ONE_WAD) : muldiv_i128(sy, rate, ONE_WAD);
}

static uint64_t asset_to_sy(uint64_t rate, uint64_t asset, int ceil, int limbs) {
    if (rate == 0) return 0;
    if (ceil) {
        return limbs ? muldiv_ceil_limbs(asset, ONE_WAD, rate)
                     : muldiv_ceil_i128(asset, ONE_WAD, rate);
    }
    return limbs ? muldiv_limbs(asset, ONE_WAD, rate)
                 : muldiv_i128(asset, ONE_WAD, rate);
}

static int selftest(void) {
    int fail = 0;
    uint64_t one = ONE_WAD;
    uint64_t three = one + one + one;

    if (muldiv_i128(100, 200, 50) != 400) fail++;
    if (muldiv_i128(100, 200, 50) != muldiv_limbs(100, 200, 50)) fail++;
    if (muldiv_ceil_i128(10, one, three) != 4) fail++;
    if (muldiv_ceil_i128(10, one, three) != muldiv_ceil_limbs(10, one, three)) fail++;
    if (muldiv_i128(10, one, three) != 3) fail++;
    if (muldiv_rem_i128(10, one, three) != one) fail++;
    if (muldiv_rem_i128(10, one, three) != muldiv_rem_limbs(10, one, three)) fail++;
    if (sy_to_asset(one, one, 0, 0) != one) fail++;
    if (sy_to_asset(one, one, 0, 1) != one) fail++;
    if (asset_to_sy(one, one, 0, 0) != one) fail++;
    if (sy_to_asset(one + one, one, 0, 0) != one + one) fail++;
    if (asset_to_sy(three, 10, 0, 0) != 3) fail++;
    if (asset_to_sy(three, 10, 1, 0) != 4) fail++;
    if (asset_to_sy(three, 10, 1, 1) != 4) fail++;
    if (sy_to_asset(3, 10, 0, 0) != 0) fail++;
    if (sy_to_asset(3, 10, 1, 0) != 1) fail++;
    if (sy_to_asset(3, 10, 1, 1) != 1) fail++;
    if (asset_to_sy(0, 10, 0, 0) != 0) fail++;
    if (asset_to_sy(0, 10, 1, 0) != 0) fail++;
    if (muldiv_i128(one, one, 1) != 0) fail++;
    if (muldiv_limbs(one, one, 1) != 0) fail++;
    if (muldiv_ceil_i128(one, one, 1) != 0) fail++;
    if (muldiv_ceil_limbs(one, one, 1) != 0) fail++;

    if (fail) {
        fprintf(stderr, "pendle_syutils_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("pendle_syutils_c11 selftest PASS\n");
    printf("vector.id=%" PRIu64 "\n", sy_to_asset(one, one, 0, 0));
    printf("vector.a2sy_floor10=%" PRIu64 "\n", asset_to_sy(three, 10, 0, 0));
    printf("vector.a2sy_ceil10=%" PRIu64 "\n", asset_to_sy(three, 10, 1, 0));
    printf("vector.sy2a_up=%" PRIu64 "\n", sy_to_asset(3, 10, 1, 0));
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    int limbs = 0;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | md a b d | mdup a b d | rem a b d | sy2a rate sy | sy2aup rate sy | a2sy rate asset | a2syup rate asset\n",
                argv[0]);
        return 2;
    }
    cmd = argv[1];
    if (argc >= 3 && strcmp(argv[argc - 1], "--limbs") == 0) {
        limbs = 1;
        argc--;
    }
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if ((strcmp(cmd, "md") == 0 || strcmp(cmd, "mdup") == 0 || strcmp(cmd, "rem") == 0) && argc == 5) {
        uint64_t a = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t d = strtoull(argv[4], NULL, 10);
        if (strcmp(cmd, "rem") == 0) {
            printf("%" PRIu64 "\n", limbs ? muldiv_rem_limbs(a, b, d) : muldiv_rem_i128(a, b, d));
        } else if (strcmp(cmd, "mdup") == 0) {
            printf("%" PRIu64 "\n", limbs ? muldiv_ceil_limbs(a, b, d) : muldiv_ceil_i128(a, b, d));
        } else {
            printf("%" PRIu64 "\n", limbs ? muldiv_limbs(a, b, d) : muldiv_i128(a, b, d));
        }
        return 0;
    }
    if ((strcmp(cmd, "sy2a") == 0 || strcmp(cmd, "sy2aup") == 0) && argc == 4) {
        uint64_t rate = strtoull(argv[2], NULL, 10);
        uint64_t sy = strtoull(argv[3], NULL, 10);
        printf("%" PRIu64 "\n", sy_to_asset(rate, sy, strcmp(cmd, "sy2aup") == 0, limbs));
        return 0;
    }
    if ((strcmp(cmd, "a2sy") == 0 || strcmp(cmd, "a2syup") == 0) && argc == 4) {
        uint64_t rate = strtoull(argv[2], NULL, 10);
        uint64_t asset = strtoull(argv[3], NULL, 10);
        printf("%" PRIu64 "\n", asset_to_sy(rate, asset, strcmp(cmd, "a2syup") == 0, limbs));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
