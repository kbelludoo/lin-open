/*
 * Independent C11 oracle for Morpho Blue MathLib (i64-positive scale).
 *
 * Floor (x*y)/d and remainder-ceil via unsigned __int128.
 * Fail-closed if the quotient does not fit in int64.
 * Not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: morpho-org/morpho-blue src/libraries/MathLib.sol (MIT).
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WAD 1000000000000000000ULL

static int64_t fail_closed_i64(__uint128_t q) {
    if (q > (unsigned __int128)INT64_MAX) return 0;
    return (int64_t)q;
}

static int64_t muldiv_down(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 0;
    return fail_closed_i64(((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d);
}

static uint64_t muldiv_rem(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)a * (__uint128_t)b) % (__uint128_t)d);
}

static int64_t muldiv_ceil(uint64_t a, uint64_t b, uint64_t d) {
    int64_t q;
    uint64_t r;
    if (d == 0) return 0;
    if (((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d > (unsigned __int128)INT64_MAX)
        return 0;
    q = muldiv_down(a, b, d);
    r = muldiv_rem(a, b, d);
    if (r == 0) return q;
    if (q == INT64_MAX) return 0;
    return q + 1;
}

static int64_t wtaylor(uint64_t x, uint64_t n) {
    int64_t first, second, third;
    __uint128_t sum;
    first = muldiv_down(x, n, 1);
    if (first == 0) return 0;
    second = muldiv_down((uint64_t)first, (uint64_t)first, 2ULL * WAD);
    third = muldiv_down((uint64_t)second, (uint64_t)first, 3ULL * WAD);
    sum = (__uint128_t)(uint64_t)first + (__uint128_t)(uint64_t)second +
          (__uint128_t)(uint64_t)third;
    return fail_closed_i64(sum);
}

static int64_t accrue(uint64_t borrow, uint64_t rate, uint64_t elapsed) {
    int64_t t;
    if (elapsed == 0) return 0;
    t = wtaylor(rate, elapsed);
    if (t < 0) return 0;
    return muldiv_down(borrow, (uint64_t)t, WAD);
}

static int selftest(void) {
    int64_t w = (int64_t)WAD;
    if (muldiv_down(100, 200, 50) != 400) return 1;
    if (muldiv_down(7, 9, 2) != 31) return 2;
    if (muldiv_ceil(7, 9, 2) != 32) return 3;
    if (muldiv_rem(7, 9, 2) != 1) return 4;
    if (muldiv_down((uint64_t)w, (uint64_t)w, (uint64_t)w) != w) return 5;
    if (muldiv_down(2, (uint64_t)w, 3) != 666666666666666666LL) return 6;
    if (muldiv_ceil(2, (uint64_t)w, 3) != 666666666666666667LL) return 7;
    if (muldiv_down((uint64_t)w, (uint64_t)w, 1) != 0) return 8;
    if (wtaylor(3170979198ULL, 86400ULL) != 274010136628159LL) return 9;
    if (accrue((uint64_t)w, 3170979198ULL, 86400ULL) != 274010136628159LL) return 10;
    if (wtaylor(3170979198ULL, 0) != 0) return 11;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: morpho_mathlib_c11 selftest|muldiv|muldivup|wmul|wdiv|wdivup|taylor|accrue ...\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (argc < 4) return 2;
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRId64 "\n", muldiv_down(strtoull(argv[2], NULL, 10),
                                            strtoull(argv[3], NULL, 10),
                                            strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "muldivup") == 0 && argc >= 5) {
        printf("%" PRId64 "\n", muldiv_ceil(strtoull(argv[2], NULL, 10),
                                            strtoull(argv[3], NULL, 10),
                                            strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "wmul") == 0) {
        printf("%" PRId64 "\n", muldiv_down(strtoull(argv[2], NULL, 10),
                                            strtoull(argv[3], NULL, 10), WAD));
        return 0;
    }
    if (strcmp(argv[1], "wdiv") == 0) {
        printf("%" PRId64 "\n", muldiv_down(strtoull(argv[2], NULL, 10), WAD,
                                            strtoull(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "wdivup") == 0) {
        printf("%" PRId64 "\n", muldiv_ceil(strtoull(argv[2], NULL, 10), WAD,
                                            strtoull(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "taylor") == 0) {
        printf("%" PRId64 "\n", wtaylor(strtoull(argv[2], NULL, 10),
                                        strtoull(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "accrue") == 0 && argc >= 5) {
        printf("%" PRId64 "\n", accrue(strtoull(argv[2], NULL, 10),
                                       strtoull(argv[3], NULL, 10),
                                       strtoull(argv[4], NULL, 10)));
        return 0;
    }
    return 2;
}
