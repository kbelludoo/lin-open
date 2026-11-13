/*
 * Independent C11 oracle for Maker ExponentialDecrease.price
 * (uint64-scale, RAY'=1e9). Continuous per-second n=dur (no step).
 *
 * rpow / rmul two implementations:
 *   1. unsigned wrap-detect (p/a == b and p <= INT64_MAX) then half-up div
 *   2. unsigned __int128 product + half, fail-closed if quotient > INT64_MAX
 *
 * Consensus between (1) and (2) is required before any LIN comparison on
 * vectors whose intermediates fit uint64. Wide products use (2) only and
 * the Python bigint harness.
 *
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: makerdao/dss src/abaci.sol ExponentialDecrease.price
 * (AGPL-3.0-or-later). This oracle is original C11 and does not copy abaci.sol.
 *
 * Distinct from LinearDecrease (no tau) and from StairstepExponentialDecrease
 * (n=dur, not dur/step). cut is an argument (not wards/file storage).
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)
#define RAY 1000000000ULL

static int use_i128 = 0;

static int u_mul_ok_wrap(uint64_t a, uint64_t b) {
    uint64_t p;
    if (a > I64MAX || b > I64MAX) return 0;
    if (a == 0 || b == 0) return 1;
    p = a * b;
    if (p > I64MAX) return 0;
    return p / a == b;
}

static uint64_t muldiv_round_wrap(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t p, t;
    if (d == 0 || !u_mul_ok_wrap(a, b)) return 0;
    p = a * b;
    t = p + (d / 2);
    if (t < p) return 0;
    return t / d;
}

static uint64_t muldiv_round_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t p, q;
    if (d == 0) return 0;
    p = (__uint128_t)a * (__uint128_t)b;
    q = p + (__uint128_t)(d / 2);
    if (q < p) return 0;
    q = q / (__uint128_t)d;
    if (q > I64MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_floor_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > I64MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_round(uint64_t a, uint64_t b, uint64_t d) {
    return use_i128 ? muldiv_round_i128(a, b, d) : muldiv_round_wrap(a, b, d);
}

static uint64_t rpow(uint64_t x, uint64_t n, uint64_t b) {
    uint64_t z, odd;
    if (b == 0) return 0;
    if (n == 0) return b;
    if (x == 0) return 0;
    z = (n % 2 == 0) ? b : x;
    n = n / 2;
    while (n > 0) {
        x = muldiv_round(x, x, b);
        odd = n % 2;
        if (odd) z = muldiv_round(z, x, b);
        n = n / 2;
    }
    return z;
}

static int64_t price(uint64_t top, uint64_t dur, uint64_t cut) {
    uint64_t p;
    if (top > I64MAX || cut > RAY) return 0;
    p = rpow(cut, dur, RAY);
    if (use_i128) return (int64_t)muldiv_floor_i128(top, p, RAY);
    if (!u_mul_ok_wrap(top, p)) return 0;
    return (int64_t)((top * p) / RAY);
}

static int64_t ok_price(uint64_t top, uint64_t dur, uint64_t cut) {
    (void)dur;
    if (top > I64MAX || cut > RAY) return 0;
    return 1;
}

static int selftest(void) {
    int64_t w;
    use_i128 = 0;
    if (rpow(3, 2, 2) != 5) return 1;
    if (rpow(990000000ULL, 1, RAY) != 990000000ULL) return 1;
    if (rpow(990000000ULL, 2, RAY) != 980100000ULL) return 1;
    if (price(1000000000ULL, 0, 990000000ULL) != 1000000000LL) return 1;
    if (price(1000000000ULL, 1, 990000000ULL) != 990000000LL) return 1;
    if (price(1000000000ULL, 2, 990000000ULL) != 980100000LL) return 1;
    if (price(1000000000ULL, 3, 990000000ULL) != 970299000LL) return 1;
    if (price(123456789ULL, 1, 990000000ULL) != 122222221LL) return 1;
    if (price(1000000000ULL, 89, 990000000ULL) != 408820172LL) return 1;
    if (price(1000000000ULL, 1, 1000000001ULL) != 0) return 1;
    use_i128 = 1;
    if (price(1000000000ULL, 2, 990000000ULL) != 980100000LL) return 1;
    if (price(1000000000ULL, 89, 990000000ULL) != 408820172LL) return 1;
    if (rpow(3, 2, 2) != 5) return 1;
    w = (int64_t)((uint64_t)10000000000LL * (uint64_t)1000000000LL);
    if (w != -8446744073709551616LL) return 1;
    if (muldiv_floor_i128(10000000000ULL, 1000000000ULL, 1) != 0) return 1;
    puts("PASS");
    return 0;
}

static void usage(void) {
    fputs("usage: maker_abacus_exp_c11 selftest\n", stderr);
    fputs("  rpow X N B [--i128]\n", stderr);
    fputs("  price|ok TOP DUR CUT [--i128]\n", stderr);
    fputs("  naive_mul A B\n", stderr);
}

static int last_i128(int argc, char **argv) {
    int i;
    for (i = 2; i < argc; i++)
        if (strcmp(argv[i], "--i128") == 0) return 1;
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    if (argc < 2) {
        usage();
        return 2;
    }
    use_i128 = last_i128(argc, argv);
    cmd = argv[1];
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "rpow") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               rpow(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                    strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (argc >= 5 && (strcmp(cmd, "price") == 0 || strcmp(cmd, "ok") == 0)) {
        uint64_t top = strtoull(argv[2], NULL, 10);
        uint64_t dur = strtoull(argv[3], NULL, 10);
        uint64_t cut = strtoull(argv[4], NULL, 10);
        if (strcmp(cmd, "price") == 0)
            printf("%" PRId64 "\n", price(top, dur, cut));
        else
            printf("%" PRId64 "\n", ok_price(top, dur, cut));
        return 0;
    }
    if (strcmp(cmd, "naive_mul") == 0 && argc >= 4) {
        int64_t a = strtoll(argv[2], NULL, 10);
        int64_t b = strtoll(argv[3], NULL, 10);
        printf("%" PRId64 "\n", (int64_t)((uint64_t)a * (uint64_t)b));
        return 0;
    }
    usage();
    return 2;
}
