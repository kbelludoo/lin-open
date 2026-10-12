/*
 * Independent C11 oracle for Rocket Pool rETH exchange (uint64 scale).
 *
 * Two implementations of (x*y)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_rocket_reth.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: rocket-pool/rocketpool v1.4
 *   contracts/contract/token/RocketTokenRETH.sol (GPL-3.0-only)
 * This oracle is original C11 (not a verbatim port of the Solidity).
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MORPHO_VIRT_SHARES 1000000ULL
#define MORPHO_VIRT_ASSETS 1ULL
#define OZ_VIRT_SHARES 1ULL
#define OZ_VIRT_ASSETS 1ULL
#define ETHER 1000000000000000000ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d,
                            uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge;
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
            if (u_lt(r_lo, d)) r_hi = r_hi - 1;
            r_lo = r_lo - d;
            if (i >= 64) ov = 1;
            else q = q | (1ULL << i);
        }
    }
    *q_out = ov ? 0 : q;
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t floor_i128(uint64_t x, uint64_t y, uint64_t d, int *ov) {
    __uint128_t q;
    if (d == 0) {
        *ov = 1;
        return 0;
    }
    q = ((__uint128_t)x * (__uint128_t)y) / (__uint128_t)d;
    if (q > UINT64_MAX) {
        *ov = 1;
        return 0;
    }
    *ov = 0;
    return (uint64_t)q;
}

static uint64_t rem_i128(uint64_t x, uint64_t y, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)x * (__uint128_t)y) % (__uint128_t)d);
}

static uint64_t rocket_reth(uint64_t eth, uint64_t te, uint64_t ts, int *ov) {
    if (ts == 0) {
        *ov = 0;
        return eth;
    }
    if (te == 0) {
        *ov = 1;
        return 0;
    }
    return floor_i128(eth, ts, te, ov);
}

static uint64_t rocket_eth(uint64_t reth, uint64_t te, uint64_t ts, int *ov) {
    if (ts == 0) {
        *ov = 0;
        return reth;
    }
    return floor_i128(reth, te, ts, ov);
}

static uint64_t virt_shares(uint64_t eth, uint64_t te, uint64_t ts,
                            uint64_t va, uint64_t vs, int *ov) {
    if (te > UINT64_MAX - va || ts > UINT64_MAX - vs) {
        *ov = 1;
        return 0;
    }
    return floor_i128(eth, ts + vs, te + va, ov);
}

static uint64_t lido_shares(uint64_t eth, uint64_t te, uint64_t ts, int *ov) {
    if (te == 0) {
        *ov = 1;
        return 0;
    }
    return floor_i128(eth, ts, te, ov);
}

static int selftest(void) {
    uint64_t qL, rL, qI;
    int ovL, ovI;
    muldiv_limbs_qr(7, 9, 2, &qL, &rL, &ovL);
    qI = floor_i128(7, 9, 2, &ovI);
    if (ovL || ovI || qL != 31 || rL != 1 || qI != 31) return 1;
    muldiv_limbs_qr(1000000000000000000ULL, 1000000000000000000ULL, 1ULL, &qL, &rL, &ovL);
    qI = floor_i128(1000000000000000000ULL, 1000000000000000000ULL, 1ULL, &ovI);
    if (!ovL || !ovI || qL != 0 || qI != 0) return 1;
    qI = rocket_reth(1000, 0, 0, &ovI);
    if (ovI || qI != 1000ULL) return 1;
    qI = lido_shares(1000, 0, 0, &ovI);
    if (qI != 0) return 1;
    qI = virt_shares(1000, 0, 0, OZ_VIRT_ASSETS, OZ_VIRT_SHARES, &ovI);
    if (ovI || qI != 1000ULL) return 1;
    qI = virt_shares(1000, 0, 0, MORPHO_VIRT_ASSETS, MORPHO_VIRT_SHARES, &ovI);
    if (ovI || qI != 1000000000ULL) return 1;
    qI = rocket_reth(1000000ULL, 1000001ULL, 1ULL, &ovI);
    if (ovI || qI != 0) return 1;
    qI = rocket_eth(ETHER, 0, 0, &ovI);
    if (ovI || qI != ETHER) return 1;
    qI = rocket_reth(1000, 0, 2000, &ovI);
    if (qI != 0) return 1;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t a, b, c, out;
    int ov = 0, use_limbs = 0, i;
    uint64_t qL, rL;

    if (argc < 2) {
        fprintf(stderr,
                "usage: rocket_reth_c11 selftest | floor x y d [--limbs] | rem x y d | "
                "reth eth te ts | eth r te ts | rate te ts | lido-shares eth te ts | "
                "oz-shares eth te ts | morpho-shares eth te ts\n");
        return 2;
    }
    kind = argv[1];
    if (strcmp(kind, "selftest") == 0) return selftest();
    for (i = 2; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) use_limbs = 1;
    }
    if (strcmp(kind, "floor") == 0 || strcmp(kind, "rem") == 0 || strcmp(kind, "ov") == 0) {
        if (argc < 5) return 2;
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        if (use_limbs) {
            muldiv_limbs_qr(a, b, c, &qL, &rL, &ov);
            if (strcmp(kind, "rem") == 0) out = rL;
            else if (strcmp(kind, "ov") == 0) out = (uint64_t)ov;
            else out = qL;
        } else if (strcmp(kind, "rem") == 0) out = rem_i128(a, b, c);
        else if (strcmp(kind, "ov") == 0) {
            floor_i128(a, b, c, &ov);
            out = (uint64_t)ov;
        } else out = floor_i128(a, b, c, &ov);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "rate") == 0) {
        if (argc < 4) return 2;
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        out = rocket_eth(ETHER, a, b, &ov);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (argc < 5) return 2;
    a = strtoull(argv[2], NULL, 10);
    b = strtoull(argv[3], NULL, 10);
    c = strtoull(argv[4], NULL, 10);
    if (strcmp(kind, "reth") == 0) out = rocket_reth(a, b, c, &ov);
    else if (strcmp(kind, "eth") == 0) out = rocket_eth(a, b, c, &ov);
    else if (strcmp(kind, "lido-shares") == 0) out = lido_shares(a, b, c, &ov);
    else if (strcmp(kind, "oz-shares") == 0)
        out = virt_shares(a, b, c, OZ_VIRT_ASSETS, OZ_VIRT_SHARES, &ov);
    else if (strcmp(kind, "morpho-shares") == 0)
        out = virt_shares(a, b, c, MORPHO_VIRT_ASSETS, MORPHO_VIRT_SHARES, &ov);
    else {
        fprintf(stderr, "unknown kind %s\n", kind);
        return 2;
    }
    (void)use_limbs;
    printf("%" PRIu64 "\n", out);
    return 0;
}
