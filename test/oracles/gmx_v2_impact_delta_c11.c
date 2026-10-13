/*
 * Independent C11 oracle for GMX V2 applyDeltaToPositionImpactPool
 * (uint64-scale, signed delta, lent pairing).
 *
 * Two overflow detectors for a+b:
 *   1. GCC/Clang signed __int128
 *   2. Portable uint64 headroom vs INT64_MAX
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
 * License of the algorithm: GPL-2.0-or-later after BUSL Change Date
 * 2026-08-31. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int add_ok_i128(int64_t a, int64_t b) {
    __int128 s;
    if (a < 0 || b < 0) return 0;
    s = (__int128)a + (__int128)b;
    if (s > INT64_MAX) return 0;
    return 1;
}

static int add_ok_portable(int64_t a, int64_t b) {
    uint64_t ua, ub;
    if (a < 0 || b < 0) return 0;
    ua = (uint64_t)a;
    ub = (uint64_t)b;
    if (ub > (uint64_t)INT64_MAX - ua) return 0;
    return 1;
}

static int64_t mag_i64(int64_t x) {
    if (x >= 0) return x;
    return -x;
}

static int mag_ok(int64_t x) {
    int64_t m;
    if (x >= 0) return 1;
    m = -x;
    return m >= 0;
}

static int ok_with(int64_t pool, int64_t lent, int64_t delta,
                   int (*add_ok)(int64_t, int64_t)) {
    int64_t mag, excess;
    if (pool < 0 || lent < 0) return 0;
    if (!mag_ok(delta)) return 0;
    mag = mag_i64(delta);
    if (delta < 0) {
        if ((uint64_t)pool < (uint64_t)mag) {
            excess = mag - pool;
            return add_ok(lent, excess);
        }
        return 1;
    }
    if ((uint64_t)lent < (uint64_t)mag) {
        excess = mag - lent;
        return add_ok(pool, excess);
    }
    return 1;
}

static int64_t next_pool_with(int64_t pool, int64_t lent, int64_t delta,
                              int (*add_ok)(int64_t, int64_t)) {
    int64_t mag, excess;
    if (!ok_with(pool, lent, delta, add_ok)) return 0;
    mag = mag_i64(delta);
    if (delta < 0) {
        if ((uint64_t)pool < (uint64_t)mag) return 0;
        return pool - mag;
    }
    if ((uint64_t)lent < (uint64_t)mag) {
        excess = mag - lent;
        return pool + excess;
    }
    return pool;
}

static int64_t next_lent_with(int64_t pool, int64_t lent, int64_t delta,
                              int (*add_ok)(int64_t, int64_t)) {
    int64_t mag, excess;
    if (!ok_with(pool, lent, delta, add_ok)) return 0;
    mag = mag_i64(delta);
    if (delta < 0) {
        if ((uint64_t)pool < (uint64_t)mag) {
            excess = mag - pool;
            return lent + excess;
        }
        return lent;
    }
    if ((uint64_t)lent < (uint64_t)mag) return 0;
    return lent - mag;
}

static int64_t wrap_add(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a + (uint64_t)b);
}

static int64_t wrong_naive_pool(int64_t pool, int64_t delta) {
    return wrap_add(pool, delta);
}

static int64_t wrong_swap_pool(int64_t pool, int64_t delta) {
    int64_t mag;
    if (pool < 0) return 0;
    if (delta >= 0) {
        if (!add_ok_i128(pool, delta)) return 0;
        return pool + delta;
    }
    mag = mag_i64(delta);
    if ((uint64_t)pool < (uint64_t)mag) return 0;
    return pool - mag;
}

static int64_t wrong_repay_only_pool(int64_t pool, int64_t lent, int64_t delta) {
    if (delta <= 0) return next_pool_with(pool, lent, delta, add_ok_i128);
    return pool;
}

static int64_t wrong_abs_pool(int64_t pool, int64_t lent, int64_t delta) {
    return next_pool_with(pool, lent, -mag_i64(delta), add_ok_i128);
}

static int use_portable(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0 || strcmp(argv[i], "--portable") == 0)
            return 1;
    }
    return 0;
}

static int64_t parse_i64(const char *s) {
    return (int64_t)strtoll(s, NULL, 10);
}

static int selftest(void) {
    int64_t p, l, d;
    p = 100000000; l = 20000000; d = -150000000;
    if (next_pool_with(p, l, d, add_ok_i128) != 0) return 1;
    if (next_lent_with(p, l, d, add_ok_i128) != 70000000) return 1;
    if (next_pool_with(p, l, d, add_ok_portable) != 0) return 1;
    if (next_lent_with(p, l, d, add_ok_portable) != 70000000) return 1;
    if (wrong_naive_pool(p, d) != -50000000) return 1;
    if (wrong_swap_pool(p, d) != 0) return 1;
    d = 50000000;
    if (next_pool_with(p, l, d, add_ok_i128) != 130000000) return 1;
    if (next_lent_with(p, l, d, add_ok_i128) != 0) return 1;
    if (next_pool_with(p, l, d, add_ok_portable) != 130000000) return 1;
    if (wrong_naive_pool(p, d) != 150000000) return 1;
    if (wrong_repay_only_pool(p, l, d) != 100000000) return 1;
    if (wrong_abs_pool(p, l, d) != 50000000) return 1;
    p = 7000000000000000000LL;
    d = 3000000000000000000LL;
    if (ok_with(p, 0, d, add_ok_i128) != 0) return 1;
    if (ok_with(p, 0, d, add_ok_portable) != 0) return 1;
    if (add_ok_i128(p, d) != add_ok_portable(p, d)) return 1;
    fputs("PASS\n", stdout);
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    int64_t pool, lent, delta, out;
    int (*add_ok)(int64_t, int64_t);
    int portable;

    if (argc < 2) {
        fputs("usage: gmx_v2_impact_delta_c11 selftest|kind pool lent delta [--limbs]\n", stderr);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (argc < 5) {
        fputs("need pool lent delta\n", stderr);
        return 2;
    }
    kind = argv[1];
    pool = parse_i64(argv[2]);
    lent = parse_i64(argv[3]);
    delta = parse_i64(argv[4]);
    portable = use_portable(argc, argv);
    add_ok = portable ? add_ok_portable : add_ok_i128;

    if (strcmp(kind, "pool") == 0)
        out = next_pool_with(pool, lent, delta, add_ok);
    else if (strcmp(kind, "lent") == 0)
        out = next_lent_with(pool, lent, delta, add_ok);
    else if (strcmp(kind, "ok") == 0)
        out = ok_with(pool, lent, delta, add_ok);
    else if (strcmp(kind, "wrongnaive") == 0)
        out = wrong_naive_pool(pool, delta);
    else if (strcmp(kind, "wrongswap") == 0)
        out = wrong_swap_pool(pool, delta);
    else if (strcmp(kind, "wrongswaplent") == 0)
        out = lent;
    else if (strcmp(kind, "wrongrepay") == 0)
        out = wrong_repay_only_pool(pool, lent, delta);
    else if (strcmp(kind, "wrongabs") == 0)
        out = wrong_abs_pool(pool, lent, delta);
    else if (strcmp(kind, "naiveadd") == 0)
        out = wrap_add(pool, lent);
    else {
        fprintf(stderr, "unknown kind %s\n", kind);
        return 2;
    }
    printf("%" PRId64 "\n", out);
    return 0;
}
