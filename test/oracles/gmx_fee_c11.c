/*
 * Independent C11 oracle for GMX V1 VaultUtils.getFeeBasisPoints (uint64).
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_gmx_fee.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-contracts contracts/core/VaultUtils.sol
 * Algorithm license: MIT. This oracle is original C11.
 * Kernel is USDG tax/rebate vs target weight, not Uniswap xy, not Solidly
 * x3y+y3x, not Maker rpow, not Curve/Saddle getD.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BPS 10000ULL

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
    *q_out = ov ? 0 : q;
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static uint64_t md_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    (void)r;
    return ov ? 0 : q;
}

static uint64_t abs_diff(uint64_t a, uint64_t b) {
    return a > b ? a - b : b - a;
}

static uint64_t next_amount(uint64_t initial, uint64_t delta, int increment) {
    if (increment) return initial + delta;
    return delta > initial ? 0 : initial - delta;
}

static uint64_t fee_bps(uint64_t initial, uint64_t delta, uint64_t target,
                        uint64_t fee, uint64_t tax, int increment, int has_dyn,
                        uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t next, idiff, ndiff, rebate, avg, taxb;
    if (!has_dyn) return fee;
    next = next_amount(initial, delta, increment);
    if (target == 0) return fee;
    idiff = abs_diff(initial, target);
    ndiff = abs_diff(next, target);
    if (ndiff < idiff) {
        rebate = md(tax, idiff, target);
        return rebate > fee ? 0 : fee - rebate;
    }
    avg = (idiff + ndiff) / 2;
    if (avg > target) avg = target;
    taxb = md(tax, avg, target);
    return fee + taxb;
}

static uint64_t target_usdg(uint64_t weight, uint64_t supply, uint64_t total_w,
                            uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (total_w == 0) return 0;
    return md(weight, supply, total_w);
}

static uint64_t usd_to_token(uint64_t usd, uint64_t token_pow, uint64_t price,
                             uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (usd == 0 || token_pow == 0 || price == 0) return 0;
    return md(usd, token_pow, price);
}

static uint64_t position_fee(uint64_t size, uint64_t margin_bps,
                             uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t after;
    if (size == 0 || margin_bps > BPS) return 0;
    after = md(size, BPS - margin_bps, BPS);
    return size - after;
}

static int64_t naive_mul_wrap(int64_t a, int64_t b, int64_t d) {
    return (int64_t)((uint64_t)a * (uint64_t)b) / d;
}

static int selftest(void) {
    uint64_t q, r;
    int ov;
    if (muldiv_i128(100, 200, 50) != 400) return 1;
    if (md_limbs(100, 200, 50) != 400) return 2;
    muldiv_limbs_qr(7, 9, 2, &q, &r, &ov);
    if (ov || q != 31 || r != 1) return 3;
    if (muldiv_i128(1000000000000000000ULL, 1000000000000000000ULL, 1) != 0) return 4;
    if (fee_bps(10000, 2000, 10000, 100, 50, 1, 1, muldiv_i128) != 105) return 5;
    if (fee_bps(5000, 2000, 10000, 100, 50, 1, 1, muldiv_i128) != 75) return 6;
    if (fee_bps(15000, 2000, 10000, 100, 50, 0, 1, muldiv_i128) != 75) return 7;
    if (fee_bps(15000, 2000, 10000, 100, 50, 1, 1, muldiv_i128) != 130) return 8;
    if (fee_bps(15000, 2000, 10000, 100, 50, 1, 0, muldiv_i128) != 100) return 9;
    if (fee_bps(29700, 1000, 29700, 100, 50, 1, 1, muldiv_i128) != 100) return 10;
    if (fee_bps(29700, 5000, 29700, 100, 50, 1, 1, muldiv_i128) != 104) return 11;
    if (fee_bps(23760, 1000, 29700, 100, 50, 1, 1, muldiv_i128) != 90) return 12;
    if (target_usdg(2000, 1000000, 10000, muldiv_i128) != 200000) return 13;
    if (position_fee(1000000, 10, muldiv_i128) != 1000) return 14;
    if (naive_mul_wrap(5000000000LL, 5000000000LL, 1000000LL) != 6553255926290LL) return 15;
    if (muldiv_i128(5000000000ULL, 5000000000ULL, 1000000ULL) != 25000000000000ULL) return 16;
    if (fee_bps(15000, 2000, 10000, 100, 50, 1, 1, muldiv_i128) !=
        fee_bps(15000, 2000, 10000, 100, 50, 1, 1, md_limbs))
        return 17;
    if (usd_to_token(1000000000ULL, 1000000ULL, 2000ULL, muldiv_i128) != 500000000000ULL)
        return 18;
    fprintf(stdout, "PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t a, b, c, d, e, f, g, out;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldiv a b d | fee init dlt tgt fee tax inc dyn | "
                "target w s tot | usd usd pow price | pos size mbps | wrap a b d | next init dlt inc\n",
                argv[0]);
        return 2;
    }
    kind = argv[1];
    if (strcmp(kind, "selftest") == 0) return selftest();
    if (strcmp(kind, "muldiv") == 0 && argc >= 5) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        out = (argc >= 6 && strcmp(argv[5], "--limbs") == 0) ? md_limbs(a, b, c)
                                                            : muldiv_i128(a, b, c);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "fee") == 0 && argc >= 9) {
        printf("%" PRIu64 "\n",
               fee_bps(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                       strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                       strtoull(argv[6], NULL, 10), (int)strtol(argv[7], NULL, 10),
                       (int)strtol(argv[8], NULL, 10), muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "target") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               target_usdg(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                           strtoull(argv[4], NULL, 10), muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "usd") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               usd_to_token(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                            strtoull(argv[4], NULL, 10), muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "pos") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               position_fee(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                            muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "wrap") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               naive_mul_wrap(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                              strtoll(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "next") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               next_amount(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                           (int)strtol(argv[4], NULL, 10)));
        return 0;
    }
    (void)d; (void)e; (void)f; (void)g;
    fprintf(stderr, "bad args\n");
    return 2;
}
