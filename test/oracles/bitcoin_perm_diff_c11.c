/*
 * Independent C11 oracle for Bitcoin Core v27.1 PermittedDifficultyTransition
 * scalar gates + a 64-bit compact subset of the 4x retarget bound.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm source: bitcoin/bitcoin src/pow.cpp (MIT), tag v27.1.
 * Compact codec follows arith_uint256 SetCompact/GetCompact for nSize<=8.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAINNET_TIMESPAN 1209600LL
#define MAINNET_INTERVAL 2016LL
#define MANTISSA_MASK 0x007fffffu
#define NEG_BIT 0x00800000u

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static int64_t clamp_timespan(int64_t actual, int64_t target_timespan) {
    int64_t lo, hi, out;
    if (target_timespan <= 0 || target_timespan > (INT64_MAX / 4)) return 0;
    lo = target_timespan / 4;
    hi = target_timespan * 4;
    out = actual;
    if (out < lo) out = lo;
    if (out > hi) out = hi;
    return out;
}

static int on_retarget(int64_t height, int64_t interval) {
    if (interval <= 0 || height < 0) return 0;
    return (height % interval) == 0;
}

static int compact_fits(uint32_t n) {
    unsigned nsize = n >> 24;
    uint32_t nword = n & MANTISSA_MASK;
    if (nsize > 8) return 0;
    if (nword == 0) return 0;
    if (n & NEG_BIT) return 0;
    return 1;
}

static uint64_t setcompact(uint32_t n) {
    unsigned nsize = n >> 24;
    uint32_t nword = n & MANTISSA_MASK;
    if (!compact_fits(n)) return 0;
    if (nsize <= 3) return (uint64_t)nword >> (8 * (3 - nsize));
    return (uint64_t)nword << (8 * (nsize - 3));
}

static int bitlen(uint64_t n) {
    int b = 0;
    while (n) {
        n >>= 1;
        b++;
    }
    return b;
}

static uint32_t getcompact(uint64_t n) {
    int nsize;
    uint64_t ncompact;
    if (n == 0) return 0;
    nsize = (bitlen(n) + 7) / 8;
    if (nsize <= 3) ncompact = n << (8 * (3 - nsize));
    else ncompact = n >> (8 * (nsize - 3));
    if (ncompact & NEG_BIT) {
        ncompact >>= 8;
        nsize++;
    }
    ncompact |= ((uint64_t)nsize) << 24;
    return (uint32_t)ncompact;
}

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > (uint64_t)INT64_MAX) return 0;
    return (uint64_t)q;
}

static int timespan_bound(uint32_t old_n, uint32_t new_n, int64_t timespan,
                          uint64_t pow_limit) {
    uint64_t old_t, new_t, largest, smallest, max_rt, min_rt;
    int64_t lo, hi;
    if (!compact_fits(old_n) || !compact_fits(new_n) || timespan <= 0) return 0;
    old_t = setcompact(old_n);
    new_t = setcompact(new_n);
    if (old_t == 0 || new_t == 0) return 0;
    lo = timespan / 4;
    hi = timespan * 4;
    largest = muldiv_i128(old_t, (uint64_t)hi, (uint64_t)timespan);
    smallest = muldiv_i128(old_t, (uint64_t)lo, (uint64_t)timespan);
    if (pow_limit > 0) {
        if (largest > pow_limit) largest = pow_limit;
        if (smallest > pow_limit) smallest = pow_limit;
    }
    max_rt = setcompact(getcompact(largest));
    min_rt = setcompact(getcompact(smallest));
    if (u_lt(max_rt, new_t)) return 0;
    if (u_lt(new_t, min_rt)) return 0;
    return 1;
}

/* 1=permit, 0=reject, 2=unproven uint256 width */
static int permitted(int allow_min, int64_t height, int64_t interval,
                     int64_t timespan, uint32_t old_n, uint32_t new_n,
                     uint64_t pow_limit) {
    if (allow_min) return 1;
    if (interval <= 0 || height < 0) return 0;
    if (!on_retarget(height, interval)) return old_n == new_n;
    if (!compact_fits(old_n) || !compact_fits(new_n)) return 2;
    return timespan_bound(old_n, new_n, timespan, pow_limit);
}

static int selftest(void) {
    int64_t T = MAINNET_TIMESPAN;
    int64_t I = MAINNET_INTERVAL;
    uint32_t old = 0x0400ffffu;
    uint32_t four, five;
    if (clamp_timespan(1022578, T) != 1022578) return -3;
    if (clamp_timespan(289434, T) != 302400) return -4;
    if (clamp_timespan(6048000, T) != 4838400) return -5;
    if (on_retarget(32256, I) != 1) return -6;
    if (on_retarget(32255, I) != 0) return -7;
    if (permitted(0, 32255, I, T, 0x1d00ffffu, 0x1d00ffffu, 0) != 1) return -12;
    if (permitted(0, 32255, I, T, 0x1d00ffffu, 0x1d00fffeu, 0) != 0) return -13;
    if (permitted(0, 32256, I, T, 0x1d00ffffu, 0x1d00ffffu, 0) != 2) return -14;
    if (setcompact(old) != 16776960ull) return -16;
    four = getcompact(67107840ull);
    five = getcompact(83884800ull);
    if (timespan_bound(old, four, T, 0) != 1) return -19;
    if (timespan_bound(old, five, T, 0) != 0) return -20;
    return 1;
}

static void usage(void) {
    fprintf(stderr,
            "usage: bitcoin_perm_diff_c11 selftest\n"
            "       bitcoin_perm_diff_c11 clamp ACTUAL T\n"
            "       bitcoin_perm_diff_c11 on HEIGHT INTERVAL\n"
            "       bitcoin_perm_diff_c11 setcompact NBITS\n"
            "       bitcoin_perm_diff_c11 getcompact N\n"
            "       bitcoin_perm_diff_c11 bound OLD NEW T POW_LIMIT\n"
            "       bitcoin_perm_diff_c11 permitted ALLOW H I T OLD NEW POW_LIMIT\n");
}

int main(int argc, char **argv) {
    if (argc < 2) {
        usage();
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        printf("%d\n", selftest());
        return 0;
    }
    if (strcmp(argv[1], "clamp") == 0 && argc == 4) {
        printf("%" PRId64 "\n",
               clamp_timespan(atoll(argv[2]), atoll(argv[3])));
        return 0;
    }
    if (strcmp(argv[1], "on") == 0 && argc == 4) {
        printf("%d\n", on_retarget(atoll(argv[2]), atoll(argv[3])));
        return 0;
    }
    if (strcmp(argv[1], "setcompact") == 0 && argc == 3) {
        printf("%" PRIu64 "\n", setcompact((uint32_t)strtoul(argv[2], NULL, 0)));
        return 0;
    }
    if (strcmp(argv[1], "getcompact") == 0 && argc == 3) {
        printf("%u\n", getcompact(strtoull(argv[2], NULL, 0)));
        return 0;
    }
    if (strcmp(argv[1], "bound") == 0 && argc == 6) {
        printf("%d\n",
               timespan_bound((uint32_t)strtoul(argv[2], NULL, 0),
                              (uint32_t)strtoul(argv[3], NULL, 0), atoll(argv[4]),
                              strtoull(argv[5], NULL, 0)));
        return 0;
    }
    if (strcmp(argv[1], "permitted") == 0 && argc == 9) {
        printf("%d\n",
               permitted(atoi(argv[2]), atoll(argv[3]), atoll(argv[4]),
                         atoll(argv[5]), (uint32_t)strtoul(argv[6], NULL, 0),
                         (uint32_t)strtoul(argv[7], NULL, 0),
                         strtoull(argv[8], NULL, 0)));
        return 0;
    }
    usage();
    return 2;
}
