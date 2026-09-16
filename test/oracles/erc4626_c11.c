/*
 * Independent C11 oracle for OpenZeppelin ERC-4626 virtual-share math (uint64).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_erc4626_vault.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: OpenZeppelin/openzeppelin-contracts v5.0.2 ERC4626.sol (MIT).
 * Convert formula (Floor): assets * (supply + 10**offset) / (totalAssets + 1)
 * Ceil: same product, +1 if remainder != 0 (Math.mulDiv rounding).
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

static uint64_t muldiv_ceil_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t prod, q;
    uint64_t r;
    if (d == 0) return 0;
    prod = (__uint128_t)a * (__uint128_t)b;
    q = prod / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    r = (uint64_t)(prod % (__uint128_t)d);
    if (r == 0) return (uint64_t)q;
    if ((uint64_t)q == UINT64_MAX) return 0;
    return (uint64_t)q + 1U;
}

static uint64_t muldiv_ceil_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    if (ov) return 0;
    if (r == 0) return q;
    if (q == UINT64_MAX) return 0;
    return q + 1U;
}

static uint64_t pow10_u64(uint64_t exp) {
    uint64_t p = 1;
    uint64_t i = 0;
    if (exp > 18U) return 0;
    while (i < exp) {
        if (p > UINT64_MAX / 10ULL) return 0;
        p = p * 10ULL;
        i = i + 1U;
    }
    return p;
}

static uint64_t shares_floor(uint64_t assets, uint64_t supply, uint64_t total_assets,
                            uint64_t offset, uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t vs = pow10_u64(offset);
    if (vs == 0 && offset != 0) return 0;
    if (supply > UINT64_MAX - vs) return 0;
    if (total_assets == UINT64_MAX) return 0;
    return md(assets, supply + vs, total_assets + 1U);
}

static uint64_t shares_ceil(uint64_t assets, uint64_t supply, uint64_t total_assets,
                           uint64_t offset, int limbs) {
    uint64_t vs = pow10_u64(offset);
    if (vs == 0 && offset != 0) return 0;
    if (supply > UINT64_MAX - vs) return 0;
    if (total_assets == UINT64_MAX) return 0;
    if (limbs) return muldiv_ceil_limbs(assets, supply + vs, total_assets + 1U);
    return muldiv_ceil_i128(assets, supply + vs, total_assets + 1U);
}

static uint64_t assets_floor(uint64_t shares, uint64_t supply, uint64_t total_assets,
                            uint64_t offset, uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t vs = pow10_u64(offset);
    if (vs == 0 && offset != 0) return 0;
    if (supply > UINT64_MAX - vs) return 0;
    if (total_assets == UINT64_MAX) return 0;
    return md(shares, total_assets + 1U, supply + vs);
}

static uint64_t assets_ceil(uint64_t shares, uint64_t supply, uint64_t total_assets,
                           uint64_t offset, int limbs) {
    uint64_t vs = pow10_u64(offset);
    if (vs == 0 && offset != 0) return 0;
    if (supply > UINT64_MAX - vs) return 0;
    if (total_assets == UINT64_MAX) return 0;
    if (limbs) return muldiv_ceil_limbs(shares, total_assets + 1U, supply + vs);
    return muldiv_ceil_i128(shares, total_assets + 1U, supply + vs);
}

static int selftest(void) {
    int fail = 0;
    uint64_t (*md)(uint64_t, uint64_t, uint64_t);
    if (muldiv_i128(100, 200, 50) != 400) fail++;
    if (muldiv_limbs(100, 200, 50) != 400) fail++;
    if (muldiv_i128(7, 9, 2) != 31) fail++;
    if (muldiv_ceil_i128(7, 9, 2) != 32) fail++;
    if (muldiv_ceil_limbs(7, 9, 2) != 32) fail++;
    if (muldiv_rem_i128(7, 9, 2) != 1) fail++;
    if (muldiv_rem_limbs(7, 9, 2) != 1) fail++;
    if (pow10_u64(0) != 1) fail++;
    if (pow10_u64(3) != 1000) fail++;
    if (pow10_u64(18) != 1000000000000000000ULL) fail++;
    if (pow10_u64(19) != 0) fail++;
    md = muldiv_i128;
    if (shares_floor(1000, 0, 0, 0, md) != 1000) fail++;
    if (shares_floor(1000, 1000, 1000, 0, md) != 1000) fail++;
    if (shares_floor(1000000000000ULL, 1, 1000000000000ULL, 0, md) != 1) fail++;
    if (shares_floor(1000, 0, 0, 3, md) != 1000000ULL) fail++;
    if (assets_floor(1000, 0, 0, 0, md) != 1000) fail++;
    if (shares_floor(1000, 0, 0, 0, muldiv_limbs) != shares_floor(1000, 0, 0, 0, muldiv_i128)) fail++;
    if (muldiv_i128(1000000000000000000ULL, 1000000000000000000ULL, 1) != 0) fail++;
    if (fail) {
        fprintf(stderr, "erc4626_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("erc4626_c11 selftest PASS\n");
    printf("vector.empty_shares=%" PRIu64 "\n", shares_floor(1000, 0, 0, 0, muldiv_i128));
    printf("vector.donation_shares=%" PRIu64 "\n",
           shares_floor(1000000000000ULL, 1, 1000000000000ULL, 0, muldiv_i128));
    printf("vector.offset3_shares=%" PRIu64 "\n", shares_floor(1000, 0, 0, 3, muldiv_i128));
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    int limbs = 0;
    uint64_t (*md)(uint64_t, uint64_t, uint64_t) = muldiv_i128;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldiv a b d | rem a b d | ceil a b d | pow10 e | "
                "shares_floor a s t o | shares_ceil a s t o | assets_floor sh s t o | "
                "assets_ceil sh s t o [--limbs]\n",
                argv[0]);
        return 2;
    }
    cmd = argv[1];
    if (argc >= 3 && strcmp(argv[argc - 1], "--limbs") == 0) {
        limbs = 1;
        md = muldiv_limbs;
        argc--;
    }
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "muldiv") == 0 && argc == 5) {
        printf("%" PRIu64 "\n", md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                                   strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "rem") == 0 && argc == 5) {
        uint64_t a = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t d = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", limbs ? muldiv_rem_limbs(a, b, d) : muldiv_rem_i128(a, b, d));
        return 0;
    }
    if (strcmp(cmd, "ceil") == 0 && argc == 5) {
        uint64_t a = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t d = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", limbs ? muldiv_ceil_limbs(a, b, d) : muldiv_ceil_i128(a, b, d));
        return 0;
    }
    if (strcmp(cmd, "pow10") == 0 && argc == 3) {
        printf("%" PRIu64 "\n", pow10_u64(strtoull(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(cmd, "shares_floor") == 0 && argc == 6) {
        printf("%" PRIu64 "\n",
               shares_floor(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                            strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "shares_ceil") == 0 && argc == 6) {
        printf("%" PRIu64 "\n",
               shares_ceil(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                           strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10), limbs));
        return 0;
    }
    if (strcmp(cmd, "assets_floor") == 0 && argc == 6) {
        printf("%" PRIu64 "\n",
               assets_floor(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                            strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10), md));
        return 0;
    }
    if (strcmp(cmd, "assets_ceil") == 0 && argc == 6) {
        printf("%" PRIu64 "\n",
               assets_ceil(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                           strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10), limbs));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
