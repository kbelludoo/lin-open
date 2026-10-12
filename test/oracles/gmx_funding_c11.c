/*
 * Independent C11 oracle for GMX V1 VaultUtils.getFundingFee (uint64).
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_gmx_funding.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-contracts contracts/core/VaultUtils.sol
 * Algorithm license: MIT. This oracle is original C11.
 * Kernel is size * (cumulative - entry) / 1e6, not USDG tax-rebate,
 * not Uniswap xy, not Solidly x3y+y3x, not Maker rpow.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FUNDING_PREC 1000000ULL
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

static uint64_t funding_fee(uint64_t size, uint64_t cum, uint64_t entry,
                            uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t rate;
    if (size == 0) return 0;
    if (cum < entry) return 0; /* Solidity 0.6 SafeMath.sub reverts; LIN fail-closes */
    rate = cum - entry;
    if (rate == 0) return 0;
    return md(size, rate, FUNDING_PREC);
}

static uint64_t position_fee(uint64_t size, uint64_t margin_bps,
                             uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t after;
    if (size == 0 || margin_bps > BPS) return 0;
    after = md(size, BPS - margin_bps, BPS);
    return size - after;
}

static uint64_t confused_bps(uint64_t size, uint64_t rate,
                             uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (size == 0 || rate == 0) return 0;
    return md(size, rate, BPS);
}

static uint64_t ignore_entry(uint64_t size, uint64_t cum,
                             uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (size == 0 || cum == 0) return 0;
    return md(size, cum, FUNDING_PREC);
}

static uint64_t uniswap_shot(uint64_t amount, uint64_t fee_bps,
                             uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (amount == 0 || fee_bps > BPS) return 0;
    return md(amount, fee_bps, BPS);
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
    if (funding_fee(1000000ULL, 1000ULL, 0, muldiv_i128) != 1000) return 5;
    if (funding_fee(1000000ULL, 1000ULL, 1000ULL, muldiv_i128) != 0) return 6;
    if (funding_fee(0, 1000ULL, 0, muldiv_i128) != 0) return 7;
    if (funding_fee(1000000ULL, 1000ULL, 400ULL, muldiv_i128) != 600) return 8;
    if (funding_fee(10000000ULL, 50ULL, 0, muldiv_i128) != 500) return 9;
    if (funding_fee(1000000ULL, 400ULL, 1000ULL, muldiv_i128) != 0) return 10;
    if (position_fee(1000000ULL, 10ULL, muldiv_i128) != 1000) return 11;
    if (confused_bps(1000000ULL, 1000ULL, muldiv_i128) != 100000) return 12;
    if (ignore_entry(1000000ULL, 5000ULL, muldiv_i128) != 5000) return 13;
    if (funding_fee(1000000ULL, 5000ULL, 4000ULL, muldiv_i128) != 1000) return 14;
    if (uniswap_shot(1000000ULL, 30ULL, muldiv_i128) != 3000) return 15;
    if (naive_mul_wrap(5000000000LL, 5000000000LL, 1000000LL) != 6553255926290LL) return 16;
    if (muldiv_i128(5000000000ULL, 5000000000ULL, 1000000ULL) != 25000000000000ULL) return 17;
    if (funding_fee(1000000ULL, 1000ULL, 400ULL, muldiv_i128) !=
        funding_fee(1000000ULL, 1000ULL, 400ULL, md_limbs))
        return 18;
    fprintf(stdout, "PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldiv a b d | fund size cum entry | "
                "pos size mbps | confused size rate | ignore size cum | "
                "uni amount bps | wrap a b d\n",
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
    if (strcmp(kind, "fund") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               funding_fee(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                           strtoull(argv[4], NULL, 10), muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "pos") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               position_fee(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                            muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "confused") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               confused_bps(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                            muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "ignore") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               ignore_entry(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                            muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "uni") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               uniswap_shot(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                            muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "wrap") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               naive_mul_wrap(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                              strtoll(argv[4], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
