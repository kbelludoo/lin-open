/*
 * Independent C11 oracle for GMX V1 Vault.getNextFundingRate (uint64).
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_gmx_nextrate.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-contracts contracts/core/Vault.sol
 * Algorithm license: MIT. This oracle is original C11.
 * Kernel is factor * reserved * intervals / pool, not size*(cum-entry)/1e6,
 * not USDG tax-rebate, not Uniswap xy, not Solidly x3y+y3x, not Maker rpow.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FUNDING_PREC 1000000ULL

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

static uint64_t intervals(uint64_t now, uint64_t last, uint64_t interval) {
    if (interval == 0) return 0;
    if (now < last) return 0;
    if (last > UINT64_MAX - interval) return 0;
    if (last + interval > now) return 0;
    return (now - last) / interval;
}

static uint64_t next_rate(uint64_t now, uint64_t last, uint64_t interval,
                          uint64_t reserved, uint64_t pool, int is_stable,
                          uint64_t vol_factor, uint64_t stable_factor,
                          uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t iv, fac, t;
    if (pool == 0) return 0;
    iv = intervals(now, last, interval);
    if (iv == 0) return 0;
    fac = is_stable ? stable_factor : vol_factor;
    if (fac == 0) return 0;
    t = md(fac, reserved, 1);
    return md(t, iv, pool);
}

static uint64_t utilisation(uint64_t reserved, uint64_t pool,
                            uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (pool == 0) return 0;
    return md(reserved, FUNDING_PREC, pool);
}

static uint64_t ignore_interval(uint64_t reserved, uint64_t pool, uint64_t factor,
                                uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (pool == 0) return 0;
    return md(factor, reserved, pool);
}

static uint64_t use_elapsed(uint64_t now, uint64_t last, uint64_t reserved,
                            uint64_t pool, uint64_t factor,
                            uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t t;
    if (pool == 0 || now < last) return 0;
    t = md(factor, reserved, 1);
    return md(t, now - last, pool);
}

static uint64_t as_funding_fee(uint64_t reserved, uint64_t factor,
                               uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (reserved == 0 || factor == 0) return 0;
    return md(reserved, factor, FUNDING_PREC);
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
    if (next_rate(28800, 0, 28800, 50000000ULL, 100000000ULL, 0, 100, 10, muldiv_i128) != 50)
        return 4;
    if (next_rate(20000, 0, 28800, 50000000ULL, 100000000ULL, 0, 100, 10, muldiv_i128) != 0)
        return 5;
    if (ignore_interval(50000000ULL, 100000000ULL, 100, muldiv_i128) != 50) return 6;
    if (next_rate(86400, 0, 28800, 50000000ULL, 100000000ULL, 0, 100, 10, muldiv_i128) != 150)
        return 7;
    if (use_elapsed(86400, 0, 50000000ULL, 100000000ULL, 100, muldiv_i128) != 4320000)
        return 8;
    if (next_rate(28800, 0, 28800, 50000000ULL, 100000000ULL, 1, 100, 10, muldiv_i128) != 5)
        return 9;
    if (utilisation(50000000ULL, 100000000ULL, muldiv_i128) != 500000) return 10;
    if (as_funding_fee(50000000ULL, 100, muldiv_i128) != 5000) return 11;
    if (next_rate(1700000000ULL, 0, 28800, 50000000ULL, 100000000ULL, 0, 100, 10, muldiv_i128)
        != 2951350)
        return 12;
    if (naive_mul_wrap(4000000000LL, 3000000000LL, 2000000000LL) != -3223372036LL) return 13;
    if (muldiv_i128(4000000000ULL, 3000000000ULL, 2000000000ULL) != 6000000000ULL) return 14;
    if (next_rate(28800, 0, 28800, 50000000ULL, 100000000ULL, 0, 100, 10, muldiv_i128)
        != next_rate(28800, 0, 28800, 50000000ULL, 100000000ULL, 0, 100, 10, md_limbs))
        return 15;
    if (intervals(86400, 0, 28800) != 3) return 16;
    fprintf(stdout, "PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldiv a b d | next now last iv res pool st vol stb | "
                "util res pool | ignore res pool fac | elapsed now last res pool fac | "
                "fundfee res fac | wrap a b d | iv now last interval\n",
                argv[0]);
        return 2;
    }
    kind = argv[1];
    if (strcmp(kind, "selftest") == 0) return selftest();
    if (strcmp(kind, "muldiv") == 0 && argc >= 5) {
        uint64_t a = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t c = strtoull(argv[4], NULL, 10);
        uint64_t out = (argc >= 6 && strcmp(argv[5], "--limbs") == 0)
                           ? md_limbs(a, b, c)
                           : muldiv_i128(a, b, c);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "next") == 0 && argc >= 10) {
        printf("%" PRIu64 "\n",
               next_rate(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                         strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                         strtoull(argv[6], NULL, 10), atoi(argv[7]),
                         strtoull(argv[8], NULL, 10), strtoull(argv[9], NULL, 10),
                         muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "util") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               utilisation(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                           muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "ignore") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               ignore_interval(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                               strtoull(argv[4], NULL, 10), muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "elapsed") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               use_elapsed(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                           strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                           strtoull(argv[6], NULL, 10), muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "fundfee") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               as_funding_fee(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                              muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "wrap") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               naive_mul_wrap(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                              strtoll(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "iv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               intervals(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                         strtoull(argv[4], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
