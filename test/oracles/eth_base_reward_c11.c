/*
 * Independent C11 oracle for ethereum/consensus-specs (CC0-1.0) integer
 * square root and Altair base-reward math.
 *
 * Two isqrt implementations:
 *   1. Spec Babylonian with UINT64_MAX special case (beacon-chain.md)
 *   2. Overflow-safe floor((a+b)/2) clone matching src/lin_eth_base_reward.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: ethereum/consensus-specs v1.5.0
 *   specs/phase0/beacon-chain.md  integer_squareroot
 *   specs/altair/beacon-chain.md  get_base_reward_per_increment / get_base_reward
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define UINT64_MAX_SQRT 4294967295ULL
#define BASE_REWARD_FACTOR 64ULL
#define BASE_REWARDS_PER_EPOCH 4ULL
#define EB_INCREMENT 1000000000ULL

static uint64_t isqrt_spec(uint64_t n) {
    uint64_t x, y;
    if (n == UINT64_MAX) return UINT64_MAX_SQRT;
    x = n;
    y = (x + 1ULL) / 2ULL;
    while (y < x) {
        x = y;
        y = (x + n / x) / 2ULL;
    }
    return x;
}

static uint64_t uhalf(uint64_t x) { return (x >> 1) + (x & 1ULL); }

static uint64_t uavg_floor(uint64_t a, uint64_t b) {
    return (a >> 1) + (b >> 1) + (a & b & 1ULL);
}

static uint64_t isqrt_safe(uint64_t n) {
    uint64_t x, y;
    if (n == UINT64_MAX) return UINT64_MAX_SQRT;
    if (n == 0) return 0;
    x = n;
    y = uhalf(x);
    while (y < x) {
        x = y;
        if (x == 0) return 0;
        y = uavg_floor(x, n / x);
    }
    return x;
}

static uint64_t brpi(uint64_t total) {
    uint64_t s;
    if (total == 0) return 0;
    s = isqrt_spec(total);
    if (s == 0) return 0;
    return (EB_INCREMENT * BASE_REWARD_FACTOR) / s;
}

static uint64_t altair_br(uint64_t eb, uint64_t total) {
    return (eb / EB_INCREMENT) * brpi(total);
}

static uint64_t phase0_br(uint64_t eb, uint64_t total) {
    uint64_t s;
    if (total == 0) return 0;
    s = isqrt_spec(total);
    if (s == 0) return 0;
    return ((eb * BASE_REWARD_FACTOR) / s) / BASE_REWARDS_PER_EPOCH;
}

static int selftest(void) {
    static const uint64_t ns[] = {
        0, 1, 2, 3, 4, 15, 16, 17, 24, 25, 100, 1000000ULL, 1000000000ULL,
        32000000000ULL, 32000000000000ULL, 4294967295ULL, 4294967296ULL,
        UINT64_MAX
    };
    size_t i;
    for (i = 0; i < sizeof(ns) / sizeof(ns[0]); i++) {
        uint64_t a = isqrt_spec(ns[i]);
        uint64_t b = isqrt_safe(ns[i]);
        if (a != b) {
            printf("FAIL isqrt spec=%" PRIu64 " safe=%" PRIu64 " n=%" PRIu64 "\n", a, b, ns[i]);
            return 1;
        }
        if (ns[i] != UINT64_MAX) {
            __uint128_t sq = (__uint128_t)a * (__uint128_t)a;
            if (sq > ns[i]) {
                printf("FAIL isqrt^2 > n n=%" PRIu64 "\n", ns[i]);
                return 1;
            }
            if (a < UINT64_MAX_SQRT) {
                __uint128_t sq1 = (__uint128_t)(a + 1) * (__uint128_t)(a + 1);
                if (sq1 <= ns[i]) {
                    printf("FAIL (isqrt+1)^2 <= n n=%" PRIu64 "\n", ns[i]);
                    return 1;
                }
            }
        }
    }
    if (isqrt_spec(32000000000ULL) != 178885ULL) return 1;
    if (brpi(32000000000ULL) != 357771ULL) return 1;
    if (altair_br(32000000000ULL, 32000000000ULL) != 11448672ULL) return 1;
    if (phase0_br(32000000000ULL, 32000000000ULL) != 2862174ULL) return 1;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: eth_base_reward_c11 selftest|isqrt N|brpi T|altair EB T|phase0 EB T\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "isqrt") == 0 && argc >= 3) {
        uint64_t n = strtoull(argv[2], NULL, 10);
        printf("%" PRIu64 "\n", isqrt_spec(n));
        return 0;
    }
    if (strcmp(argv[1], "brpi") == 0 && argc >= 3) {
        printf("%" PRIu64 "\n", brpi(strtoull(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "altair") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n", altair_br(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "phase0") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n", phase0_br(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
