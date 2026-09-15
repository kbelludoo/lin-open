/*
 * Independent C11 oracle for Compound JumpRateModel V2 math (uint64 scale).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128 (hardware/compiler bigint)
 *   2. Portable 32-bit limbs matching src/lin_compound_jumprate.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: compound-finance/compound-protocol contracts/BaseJumpRateModelV2.sol
 * License of the algorithm: BSD-3-Clause (Compound). This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BASE_WAD 1000000000000000000ULL
#define BLOCKS_PER_YEAR 2102400ULL

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > (__uint128_t)INT64_MAX) return 0;
    return (uint64_t)q;
}

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo;
    uint64_t bit, ge, need_borrow, ov;
    int i;

    if (d == 0) return 0;
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
            if (i >= 63) ov = 1;
            else q = q | (1ULL << i);
        }
    }
    if (ov) return 0;
    return q;
}

static uint64_t utilization(uint64_t cash, uint64_t borrows, uint64_t reserves,
                            uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t sum, denom;
    if (borrows == 0) return 0;
    if (cash > UINT64_MAX - borrows) return 0;
    sum = cash + borrows;
    if (sum < reserves) return 0;
    denom = sum - reserves;
    if (denom == 0) return 0;
    return md(borrows, BASE_WAD, denom);
}

static uint64_t borrow_rate(uint64_t cash, uint64_t borrows, uint64_t reserves,
                            uint64_t base_block, uint64_t mult_block,
                            uint64_t jump_block, uint64_t kink,
                            uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t util = utilization(cash, borrows, reserves, md);
    uint64_t normal, excess;
    if (util <= kink) {
        return md(util, mult_block, BASE_WAD) + base_block;
    }
    normal = md(kink, mult_block, BASE_WAD) + base_block;
    excess = util - kink;
    return md(excess, jump_block, BASE_WAD) + normal;
}

static uint64_t supply_rate(uint64_t cash, uint64_t borrows, uint64_t reserves,
                            uint64_t base_block, uint64_t mult_block,
                            uint64_t jump_block, uint64_t kink,
                            uint64_t reserve_factor,
                            uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t one_minus, br, rate_to_pool, util;
    if (reserve_factor > BASE_WAD) return 0;
    one_minus = BASE_WAD - reserve_factor;
    br = borrow_rate(cash, borrows, reserves, base_block, mult_block, jump_block, kink, md);
    rate_to_pool = md(br, one_minus, BASE_WAD);
    util = utilization(cash, borrows, reserves, md);
    return md(util, rate_to_pool, BASE_WAD);
}

static int selftest(void) {
    int fail = 0;
    struct { uint64_t a, b, d; } md[] = {
        {100, 200, 50},
        {7, 9, 1},
        {BASE_WAD, 1, 2},
        {BASE_WAD, BASE_WAD, 2 * BASE_WAD},
        {BASE_WAD, 997, 1000},
        {123456789ULL, 987654321ULL, 42},
        {0, 100, 5},
        {UINT64_C(0xffffffff), UINT64_C(0xffffffff), 1},
    };
    size_t i;
    uint64_t kink = 800000000000000000ULL;
    uint64_t mult_year = 40000000000000000ULL;
    uint64_t jump_year = 1090000000000000000ULL;
    uint64_t mb_a, mb_b, jb_a, jb_b, r50a, r50b, r90a, r90b;

    for (i = 0; i < sizeof(md) / sizeof(md[0]); i++) {
        uint64_t x = muldiv_i128(md[i].a, md[i].b, md[i].d);
        uint64_t y = muldiv_limbs(md[i].a, md[i].b, md[i].d);
        if (x != y) {
            fprintf(stderr, "muldiv mismatch i=%zu i128=%" PRIu64 " limbs=%" PRIu64 "\n", i, x, y);
            fail++;
        }
    }
    if (utilization(100, 0, 0, muldiv_i128) != 0) fail++;
    if (utilization(BASE_WAD, BASE_WAD, 0, muldiv_i128)
        != utilization(BASE_WAD, BASE_WAD, 0, muldiv_limbs)) fail++;
    if (utilization(BASE_WAD, BASE_WAD, 0, muldiv_i128) != 500000000000000000ULL) fail++;
    if (utilization(0, BASE_WAD, 0, muldiv_i128) != BASE_WAD) fail++;
    if (utilization(0, 100, 200, muldiv_i128) != 0) fail++;
    if (utilization(0, BASE_WAD, BASE_WAD / 2, muldiv_i128) != 2000000000000000000ULL) fail++;
    if (muldiv_i128(BASE_WAD, BASE_WAD, 1) != 0) fail++;
    if (muldiv_limbs(BASE_WAD, BASE_WAD, 1) != 0) fail++;

    for (i = 0; i < sizeof(md) / sizeof(md[0]); i++) {
        __uint128_t prod = (__uint128_t)md[i].a * (__uint128_t)md[i].b;
        uint64_t q = muldiv_i128(md[i].a, md[i].b, md[i].d);
        if (md[i].d == 0) {
            if (q != 0) fail++;
        } else if (prod / md[i].d > (__uint128_t)INT64_MAX) {
            if (q != 0) fail++;
        } else if (q != (uint64_t)(prod / md[i].d)) {
            fail++;
        } else if (prod != (__uint128_t)q * md[i].d + (prod % md[i].d)) {
            fail++;
        }
    }

    mb_a = muldiv_i128(muldiv_i128(mult_year, BASE_WAD, kink), 1, BLOCKS_PER_YEAR);
    mb_b = muldiv_limbs(muldiv_limbs(mult_year, BASE_WAD, kink), 1, BLOCKS_PER_YEAR);
    jb_a = muldiv_i128(jump_year, 1, BLOCKS_PER_YEAR);
    jb_b = muldiv_limbs(jump_year, 1, BLOCKS_PER_YEAR);
    if (mb_a != mb_b || jb_a != jb_b) fail++;

    r50a = borrow_rate(BASE_WAD, BASE_WAD, 0, 0, mb_a, jb_a, kink, muldiv_i128);
    r50b = borrow_rate(BASE_WAD, BASE_WAD, 0, 0, mb_b, jb_b, kink, muldiv_limbs);
    r90a = borrow_rate(100000000000000000ULL, 900000000000000000ULL, 0, 0, mb_a, jb_a, kink, muldiv_i128);
    r90b = borrow_rate(100000000000000000ULL, 900000000000000000ULL, 0, 0, mb_b, jb_b, kink, muldiv_limbs);
    if (r50a != r50b || r90a != r90b) fail++;
    if (r90a < r50a) fail++;
    if (r50a != 11891171993ULL) fail++;
    if (r90a != 70871385082ULL) fail++;
    if (supply_rate(BASE_WAD, BASE_WAD, 0, 0, mb_a, jb_a, kink, 100000000000000000ULL, muldiv_i128)
        != 5351027396ULL) fail++;
    if (supply_rate(BASE_WAD, BASE_WAD, 0, 0, mb_a, jb_a, kink, 100000000000000000ULL, muldiv_i128)
        != supply_rate(BASE_WAD, BASE_WAD, 0, 0, mb_b, jb_b, kink, 100000000000000000ULL, muldiv_limbs)) fail++;

    if (fail) {
        fprintf(stderr, "compound_jumprate_c11 selftest FAIL count=%d\n", fail);
        return 1;
    }
    printf("compound_jumprate_c11 selftest PASS\n");
    printf("vector.util_50=%" PRIu64 "\n", utilization(BASE_WAD, BASE_WAD, 0, muldiv_i128));
    printf("vector.mult_block=%" PRIu64 "\n", mb_a);
    printf("vector.jump_block=%" PRIu64 "\n", jb_a);
    printf("vector.borrow_50=%" PRIu64 "\n", r50a);
    printf("vector.borrow_90=%" PRIu64 "\n", r90a);
    printf("vector.supply_50_rf10=%" PRIu64 "\n",
           supply_rate(BASE_WAD, BASE_WAD, 0, 0, mb_a, jb_a, kink, 100000000000000000ULL, muldiv_i128));
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    uint64_t (*md)(uint64_t, uint64_t, uint64_t) = muldiv_i128;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldiv a b d | util c b r | borrow c b r base mult jump kink | supply ... rf\n",
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
    if (strcmp(cmd, "util") == 0 && argc == 5) {
        uint64_t c = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t r = strtoull(argv[4], NULL, 10);
        printf("%" PRIu64 "\n", utilization(c, b, r, md));
        return 0;
    }
    if (strcmp(cmd, "borrow") == 0 && argc == 9) {
        uint64_t c = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t r = strtoull(argv[4], NULL, 10);
        uint64_t base = strtoull(argv[5], NULL, 10);
        uint64_t mult = strtoull(argv[6], NULL, 10);
        uint64_t jump = strtoull(argv[7], NULL, 10);
        uint64_t kink = strtoull(argv[8], NULL, 10);
        printf("%" PRIu64 "\n", borrow_rate(c, b, r, base, mult, jump, kink, md));
        return 0;
    }
    if (strcmp(cmd, "supply") == 0 && argc == 10) {
        uint64_t c = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t r = strtoull(argv[4], NULL, 10);
        uint64_t base = strtoull(argv[5], NULL, 10);
        uint64_t mult = strtoull(argv[6], NULL, 10);
        uint64_t jump = strtoull(argv[7], NULL, 10);
        uint64_t kink = strtoull(argv[8], NULL, 10);
        uint64_t rf = strtoull(argv[9], NULL, 10);
        printf("%" PRIu64 "\n", supply_rate(c, b, r, base, mult, jump, kink, rf, md));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
