/*
 * Independent C11 oracle for Compound III mulPrice / divPrice (uint64 scale).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_comet_price.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: compound-finance/comet
 *   contracts/CometWithExtendedAssetList.sol
 *     mulPrice(n, price, fromScale) = n * price / fromScale
 *     divPrice(n, price, toScale)   = n * toScale / price
 *     mulFactor(n, factor)          = n * factor / FACTOR_SCALE
 *   contracts/CometCore.sol
 *     PRICE_FEED_DECIMALS=8  PRICE_SCALE=1e8
 *     FACTOR_SCALE=1e18  BASE_INDEX_SCALE=1e15
 * License of the algorithm: GPL-2.0-or-later after BUSL-1.1 Change Date
 * 2025-12-31. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PRICE_SCALE 100000000ULL
#define FACTOR_SCALE 1000000000000000000ULL
#define INDEX_SCALE 1000000000000000ULL
#define USDC_SCALE 1000000ULL

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

static uint64_t mul_price(uint64_t n, uint64_t price, uint64_t from_scale,
                          uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (price == 0 || from_scale == 0) return 0;
    return md(n, price, from_scale);
}

static uint64_t div_price(uint64_t n, uint64_t price, uint64_t to_scale,
                          uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (price == 0 || to_scale == 0) return 0;
    return md(n, to_scale, price);
}

static uint64_t reorder(uint64_t n, uint64_t price, uint64_t from_scale) {
    if (from_scale == 0 || price == 0) return 0;
    return (n / from_scale) * price;
}

static uint64_t is_borrow_ok(uint64_t borrow_base, uint64_t base_price,
                             uint64_t base_scale, uint64_t collat,
                             uint64_t asset_price, uint64_t asset_scale,
                             uint64_t cf,
                             uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t borrow_usd = mul_price(borrow_base, base_price, base_scale, md);
    uint64_t collat_usd = mul_price(collat, asset_price, asset_scale, md);
    uint64_t adj = md(collat_usd, cf, FACTOR_SCALE);
    return adj >= borrow_usd ? 1 : 0;
}

static uint64_t skip_cf(uint64_t borrow_base, uint64_t base_price,
                        uint64_t base_scale, uint64_t collat,
                        uint64_t asset_price, uint64_t asset_scale,
                        uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t borrow_usd = mul_price(borrow_base, base_price, base_scale, md);
    uint64_t collat_usd = mul_price(collat, asset_price, asset_scale, md);
    return collat_usd >= borrow_usd ? 1 : 0;
}

static uint64_t absorb_base(uint64_t seize, uint64_t asset_price,
                            uint64_t asset_scale, uint64_t liq_factor,
                            uint64_t base_price, uint64_t base_scale,
                            uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t value = mul_price(seize, asset_price, asset_scale, md);
    uint64_t delta = md(value, liq_factor, FACTOR_SCALE);
    return div_price(delta, base_price, base_scale, md);
}

static int selftest(void) {
    uint64_t a, b, d, q1, q2, r;
    int ov;
    uint64_t vecs[][3] = {
        {100, 200, 50},
        {7, 9, 1},
        {FACTOR_SCALE, 1, 2},
        {USDC_SCALE, PRICE_SCALE, USDC_SCALE},
    };
    size_t i, n = sizeof(vecs) / sizeof(vecs[0]);
    for (i = 0; i < n; i++) {
        a = vecs[i][0];
        b = vecs[i][1];
        d = vecs[i][2];
        q1 = muldiv_i128(a, b, d);
        q2 = muldiv_limbs(a, b, d);
        if (q1 != q2) return 1;
        muldiv_limbs_qr(a, b, d, &q2, &r, &ov);
        if (!ov && ((__uint128_t)a * b) % d != r) return 1;
    }
    if (mul_price(USDC_SCALE, PRICE_SCALE, USDC_SCALE, muldiv_i128) != PRICE_SCALE)
        return 1;
    if (mul_price(3, 5, 4, muldiv_i128) != 3) return 1;
    if (reorder(3, 5, 4) != 0) return 1;
    if (div_price(PRICE_SCALE, PRICE_SCALE, USDC_SCALE, muldiv_i128) != USDC_SCALE)
        return 1;
    if (muldiv_i128(USDC_SCALE, FACTOR_SCALE, USDC_SCALE) != FACTOR_SCALE)
        return 1;
    if (muldiv_i128(USDC_SCALE, PRICE_SCALE, FACTOR_SCALE) != 0) return 1;
    if (muldiv_i128(FACTOR_SCALE, FACTOR_SCALE, 1) != 0) return 1;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t x, y, z, u, v, w;
    int limbs = 0;
    uint64_t (*md)(uint64_t, uint64_t, uint64_t);
    int i;

    if (argc < 2) {
        fprintf(stderr,
                "usage: comet_price_c11 selftest | muldiv a b d | "
                "mulprice n price scale | divprice n price scale | "
                "reorder n price scale | factor n scale | index n scale | "
                "mulfactor n price | borrow ... | skipcf ... | absorb ...\n");
        return 2;
    }
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) limbs = 1;
    }
    md = limbs ? muldiv_limbs : muldiv_i128;
    kind = argv[1];
    if (strcmp(kind, "selftest") == 0) return selftest();
    if (argc < 4) return 2;
    x = strtoull(argv[2], NULL, 10);
    y = strtoull(argv[3], NULL, 10);
    if (strcmp(kind, "muldiv") == 0) {
        if (argc < 5) return 2;
        z = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", md(x, y, z));
        return 0;
    }
    if (strcmp(kind, "mulfactor") == 0) {
        printf("%" PRIu64 "\n", md(x, y, FACTOR_SCALE));
        return 0;
    }
    if (strcmp(kind, "factor") == 0) {
        printf("%" PRIu64 "\n", md(x, FACTOR_SCALE, y));
        return 0;
    }
    if (strcmp(kind, "index") == 0) {
        printf("%" PRIu64 "\n", md(x, INDEX_SCALE, y));
        return 0;
    }
    if (strcmp(kind, "mulprice") == 0) {
        if (argc < 5) return 2;
        z = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", mul_price(x, y, z, md));
        return 0;
    }
    if (strcmp(kind, "divprice") == 0) {
        if (argc < 5) return 2;
        z = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", div_price(x, y, z, md));
        return 0;
    }
    if (strcmp(kind, "reorder") == 0) {
        if (argc < 5) return 2;
        z = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", reorder(x, y, z));
        return 0;
    }
    if (strcmp(kind, "borrow") == 0) {
        if (argc < 9) return 2;
        z = strtoull(argv[4], NULL, 10);
        u = strtoull(argv[5], NULL, 10);
        v = strtoull(argv[6], NULL, 10);
        w = strtoull(argv[7], NULL, 10);
        printf("%" PRIu64 "\n",
               is_borrow_ok(x, y, z, u, v, w, strtoull(argv[8], NULL, 10), md));
        return 0;
    }
    if (strcmp(kind, "skipcf") == 0) {
        if (argc < 8) return 2;
        z = strtoull(argv[4], NULL, 10);
        u = strtoull(argv[5], NULL, 10);
        v = strtoull(argv[6], NULL, 10);
        w = strtoull(argv[7], NULL, 10);
        printf("%" PRIu64 "\n", skip_cf(x, y, z, u, v, w, md));
        return 0;
    }
    if (strcmp(kind, "absorb") == 0) {
        if (argc < 8) return 2;
        z = strtoull(argv[4], NULL, 10);
        u = strtoull(argv[5], NULL, 10);
        v = strtoull(argv[6], NULL, 10);
        w = strtoull(argv[7], NULL, 10);
        printf("%" PRIu64 "\n", absorb_base(x, y, z, u, v, w, md));
        return 0;
    }
    fprintf(stderr, "unknown kind %s\n", kind);
    return 2;
}
