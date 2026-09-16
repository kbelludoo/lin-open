/*
 * Independent C11 oracle for Geth Osaka EIP-7918 excess-blob-gas (uint64 scale).
 *
 * Two implementations of (a*b)/d and fakeExponential:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_geth_eip7918.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: ethereum/go-ethereum consensus/misc/eip4844/eip4844.go
 * License of the algorithm: LGPL-3.0. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define GAS_PER_BLOB 131072ULL
#define BLOB_BASE_COST 8192ULL

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
    hi = p3 + (mid >> 32) + (mid_carry << 32) + lo_carry;
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

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static int muldiv_ov_i128(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 1;
    return (((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d) > UINT64_MAX;
}

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return q;
}

static int muldiv_ov_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return ov || d == 0;
}

static uint64_t fake_exp_i128(uint64_t factor, uint64_t numerator, uint64_t denominator) {
    __uint128_t output = 0, accum;
    uint64_t i;
    if (denominator == 0) return 0;
    accum = (__uint128_t)factor * (__uint128_t)denominator;
    for (i = 1; accum > 0 && i <= 256; i++) {
        output += accum;
        accum = accum * numerator / denominator / i;
    }
    if (accum > 0) return 0;
    if ((output / denominator) > UINT64_MAX) return 0;
    return (uint64_t)(output / denominator);
}

static uint64_t fake_exp_limbs(uint64_t factor, uint64_t numerator, uint64_t denominator) {
    uint64_t accum, out_lo, t, i, nlo;
    uint64_t out_hi, c, nhi;
    if (denominator == 0) return 0;
    if (muldiv_ov_limbs(factor, denominator, 1)) return 0;
    accum = muldiv_limbs(factor, denominator, 1);
    out_lo = 0;
    out_hi = 0;
    for (i = 1; i <= 256; i++) {
        if (accum == 0) {
            if (out_hi != 0) return 0;
            return muldiv_limbs(out_lo, 1, denominator);
        }
        nlo = out_lo + accum;
        c = (nlo < out_lo) ? 1 : 0;
        nhi = out_hi + c;
        if (c && nhi < out_hi) return 0;
        out_lo = nlo;
        out_hi = nhi;
        if (muldiv_ov_limbs(accum, numerator, denominator)) return 0;
        t = muldiv_limbs(accum, numerator, denominator);
        if (muldiv_ov_limbs(t, 1, i)) return 0;
        accum = muldiv_limbs(t, 1, i);
    }
    return 0;
}

static int reserve_gt_i128(uint64_t cost, uint64_t base_fee, uint64_t blob_fee, uint64_t gas) {
    return ((__uint128_t)cost * base_fee) > ((__uint128_t)blob_fee * gas);
}

static int reserve_gt_limbs(uint64_t cost, uint64_t base_fee, uint64_t blob_fee, uint64_t gas) {
    __uint128_t a = (__uint128_t)cost * base_fee;
    __uint128_t b = (__uint128_t)blob_fee * gas;
    return a > b;
}

static uint64_t scaled(uint64_t used, uint64_t maxv, uint64_t target, int limbs) {
    if (maxv == 0 || maxv < target) return 0;
    return limbs ? muldiv_limbs(used, maxv - target, maxv)
                 : muldiv_i128(used, maxv - target, maxv);
}

static uint64_t cancun(uint64_t excess, uint64_t used, uint64_t target, int limbs) {
    uint64_t (*md)(uint64_t, uint64_t, uint64_t) = limbs ? muldiv_limbs : muldiv_i128;
    uint64_t target_gas, s;
    if ((limbs ? muldiv_ov_limbs : muldiv_ov_i128)(target, GAS_PER_BLOB, 1)) return 0;
    target_gas = md(target, GAS_PER_BLOB, 1);
    if (excess > UINT64_MAX - used) return 0;
    s = excess + used;
    if (s < target_gas) return 0;
    return s - target_gas;
}

static uint64_t osaka(uint64_t excess, uint64_t used, uint64_t base_fee, uint64_t blob_fee,
                     uint64_t target, uint64_t maxv, int limbs) {
    uint64_t target_gas, s, sc;
    uint64_t (*md)(uint64_t, uint64_t, uint64_t) = limbs ? muldiv_limbs : muldiv_i128;
    int (*ov)(uint64_t, uint64_t, uint64_t) = limbs ? muldiv_ov_limbs : muldiv_ov_i128;
    int (*rgt)(uint64_t, uint64_t, uint64_t, uint64_t) =
        limbs ? reserve_gt_limbs : reserve_gt_i128;
    if (ov(target, GAS_PER_BLOB, 1)) return 0;
    target_gas = md(target, GAS_PER_BLOB, 1);
    if (excess > UINT64_MAX - used) return 0;
    s = excess + used;
    if (s < target_gas) return 0;
    if (rgt(BLOB_BASE_COST, base_fee, blob_fee, GAS_PER_BLOB)) {
        sc = scaled(used, maxv, target, limbs);
        if (excess > UINT64_MAX - sc) return 0;
        return excess + sc;
    }
    return s - target_gas;
}

static uint64_t osaka_from(uint64_t excess, uint64_t used, uint64_t base_fee,
                          uint64_t target, uint64_t maxv, uint64_t frac, int limbs) {
    uint64_t bf = limbs ? fake_exp_limbs(1, excess, frac) : fake_exp_i128(1, excess, frac);
    if (bf == 0) return 0;
    return osaka(excess, used, base_fee, bf, target, maxv, limbs);
}

static int selftest(void) {
    int fail = 0;
    uint64_t used6 = 6ULL * GAS_PER_BLOB;
    struct { uint64_t f, n, d, w; } fe[] = {
        {1, 0, 1, 1}, {1, 2, 1, 6}, {1, 4, 2, 6}, {1, 3, 1, 16},
        {1, 4, 1, 49}, {0, 1234, 2345, 0}, {1, 50000000, 2225652, 5709098764ULL},
        {1, 0, 3338477, 1}, {1, 2314057, 3338477, 1}, {1, 2314058, 3338477, 2},
        {1, 10ULL * 1024 * 1024, 3338477, 23},
    };
    size_t i;
    for (i = 0; i < sizeof(fe) / sizeof(fe[0]); i++) {
        uint64_t a = fake_exp_i128(fe[i].f, fe[i].n, fe[i].d);
        uint64_t b = fake_exp_limbs(fe[i].f, fe[i].n, fe[i].d);
        if (a != fe[i].w || b != fe[i].w) {
            fprintf(stderr, "fake_exp i=%zu i128=%" PRIu64 " limbs=%" PRIu64 " want=%" PRIu64 "\n",
                    i, a, b, fe[i].w);
            fail++;
        }
    }
    if (cancun(0, 4 * GAS_PER_BLOB, 3, 0) != GAS_PER_BLOB) fail++;
    if (cancun(0, 4 * GAS_PER_BLOB, 3, 1) != GAS_PER_BLOB) fail++;
    if (osaka_from(0, used6, 1000000000ULL, 6, 9, 5007716, 0) != 262144) fail++;
    if (osaka_from(0, used6, 1000000000ULL, 6, 9, 5007716, 1) != 262144) fail++;
    if (osaka_from(0, used6, 1, 6, 9, 5007716, 0) != 0) fail++;
    if (osaka_from(5149252, 1310720, 30, 9, 14, 8832827, 0) != 5617366) fail++;
    if (osaka_from(5149252, 1310720, 30, 9, 14, 8832827, 1) != 5617366) fail++;
    if (osaka_from(19251039, 2490368, 50, 21, 32, 20609697, 0) != 20107103) fail++;
    if (osaka_from(19251039, 2490368, 50, 21, 32, 20609697, 1) != 20107103) fail++;
    if (muldiv_i128(100, 200, 50) != muldiv_limbs(100, 200, 50)) fail++;
    if (fail) {
        fprintf(stderr, "selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("PASS\n");
    return 0;
}

static int limbs_flag(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++)
        if (strcmp(argv[i], "--limbs") == 0) return 1;
    return 0;
}

int main(int argc, char **argv) {
    int L;
    if (argc < 2) {
        fprintf(stderr, "usage: geth_eip7918_c11 selftest|fake_exp|cancun|osaka|scaled|full ...\n");
        return 2;
    }
    L = limbs_flag(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "fake_exp") == 0 && argc >= 5) {
        uint64_t f = strtoull(argv[2], NULL, 10);
        uint64_t n = strtoull(argv[3], NULL, 10);
        uint64_t d = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", L ? fake_exp_limbs(f, n, d) : fake_exp_i128(f, n, d));
        return 0;
    }
    if (strcmp(argv[1], "cancun") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               cancun(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                      strtoull(argv[4], NULL, 10), L));
        return 0;
    }
    if (strcmp(argv[1], "scaled") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               scaled(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                      strtoull(argv[4], NULL, 10), L));
        return 0;
    }
    if (strcmp(argv[1], "osaka") == 0 && argc >= 8) {
        printf("%" PRIu64 "\n",
               osaka(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                     strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                     strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10), L));
        return 0;
    }
    if (strcmp(argv[1], "full") == 0 && argc >= 8) {
        printf("%" PRIu64 "\n",
               osaka_from(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                          strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                          strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10), L));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
