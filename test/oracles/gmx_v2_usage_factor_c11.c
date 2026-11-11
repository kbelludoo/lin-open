/*
 * Independent C11 oracle for GMX V2 getUsageFactor
 * (uint64-scale, nested applyFactor then toFactor).
 *
 * Two overflow detectors:
 *   1. GCC/Clang signed __int128
 *   2. Portable INT64_MAX headroom
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

typedef struct {
    int64_t reserved, pool, rfactor;
} In;

static int uadd_ok_i128(int64_t a, int64_t b) {
    __int128 s;
    if (a < 0 || b < 0) return 0;
    s = (__int128)a + (__int128)b;
    return s <= INT64_MAX;
}

static int uadd_ok_portable(int64_t a, int64_t b) {
    if (a < 0 || b < 0) return 0;
    return (uint64_t)b <= (uint64_t)INT64_MAX - (uint64_t)a;
}

static int umul_ok_i128(int64_t a, int64_t b) {
    __int128 p;
    if (a < 0 || b < 0) return 0;
    p = (__int128)a * (__int128)b;
    return p <= INT64_MAX;
}

static int umul_ok_portable(int64_t a, int64_t b) {
    if (a < 0 || b < 0) return 0;
    if (a == 0 || b == 0) return 1;
    return (uint64_t)b <= (uint64_t)INT64_MAX / (uint64_t)a;
}

static int u_lt(int64_t a, int64_t b) {
    if (a < 0 && b >= 0) return 0;
    if (a >= 0 && b < 0) return 1;
    return a < b;
}

static int64_t wrap_mul(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a * (uint64_t)b);
}

static int64_t gfloat(void) { return 1000000; }

static int64_t apply_with(int64_t value, int64_t factor, int (*umul)(int64_t, int64_t)) {
    if (value < 0 || factor < 0) return 0;
    if (!umul(value, factor)) return 0;
    return (value * factor) / gfloat();
}

static int64_t to_factor_with(int64_t value, int64_t divisor, int round_up,
                              int (*umul)(int64_t, int64_t),
                              int (*uadd)(int64_t, int64_t)) {
    int64_t prod, q, r;
    if (value < 0 || divisor < 0) return 0;
    if (round_up < 0 || round_up > 1) return 0;
    if (value == 0) return 0;
    if (divisor == 0) return 0;
    if (!umul(value, gfloat())) return 0;
    prod = value * gfloat();
    q = prod / divisor;
    r = prod - (q * divisor);
    if (round_up == 0 || r == 0) return q;
    if (!uadd(q, 1)) return 0;
    return q + 1;
}

static int inputs_ok_with(In in, int (*umul)(int64_t, int64_t)) {
    int64_t mx;
    if (in.reserved < 0 || in.pool < 0 || in.rfactor < 0) return 0;
    if (in.reserved == 0) return 1;
    if (!umul(in.pool, in.rfactor)) return 0;
    mx = apply_with(in.pool, in.rfactor, umul);
    if (mx == 0) return 0;
    if (!umul(in.reserved, gfloat())) return 0;
    return 1;
}

static int64_t usage_with(In in, int (*umul)(int64_t, int64_t),
                         int (*uadd)(int64_t, int64_t)) {
    int64_t mx;
    if (!inputs_ok_with(in, umul)) return 0;
    if (in.reserved == 0) return 0;
    mx = apply_with(in.pool, in.rfactor, umul);
    return to_factor_with(in.reserved, mx, 0, umul, uadd);
}

static int64_t wrong_pool_with(In in, int (*umul)(int64_t, int64_t),
                              int (*uadd)(int64_t, int64_t)) {
    if (in.rfactor < 0) return 0;
    return to_factor_with(in.reserved, in.pool, 0, umul, uadd);
}

static int64_t wrong_compound_with(In in, int (*umul)(int64_t, int64_t),
                                  int (*uadd)(int64_t, int64_t)) {
    int64_t den;
    if (in.rfactor < 0 || in.reserved < 0 || in.pool < 0) return 0;
    if (in.reserved == 0) return 0;
    if (!uadd(in.pool, in.reserved)) return 0;
    den = in.pool + in.reserved;
    if (den == 0) return 0;
    if (!umul(in.reserved, gfloat())) return 0;
    return (in.reserved * gfloat()) / den;
}

static int64_t wrong_apply_with(In in, int (*umul)(int64_t, int64_t)) {
    if (in.reserved < 0) return 0;
    return apply_with(in.pool, in.rfactor, umul);
}

static int64_t wrong_fused_with(In in, int (*umul)(int64_t, int64_t)) {
    int64_t den, n1;
    if (in.reserved < 0 || in.pool < 0 || in.rfactor < 0) return 0;
    if (in.reserved == 0) return 0;
    if (!umul(in.pool, in.rfactor)) return 0;
    den = in.pool * in.rfactor;
    if (den == 0) return 0;
    if (!umul(in.reserved, gfloat())) return 0;
    n1 = in.reserved * gfloat();
    if (!umul(n1, gfloat())) return 0;
    return (n1 * gfloat()) / den;
}

static int64_t wrong_ceil_with(In in, int (*umul)(int64_t, int64_t),
                              int (*uadd)(int64_t, int64_t)) {
    int64_t mx;
    if (!inputs_ok_with(in, umul)) return 0;
    if (in.reserved == 0) return 0;
    mx = apply_with(in.pool, in.rfactor, umul);
    return to_factor_with(in.reserved, mx, 1, umul, uadd);
}

static int64_t wrong_cap_with(In in, int (*umul)(int64_t, int64_t),
                             int (*uadd)(int64_t, int64_t)) {
    int64_t u = usage_with(in, umul, uadd);
    if (u_lt(gfloat(), u)) return gfloat();
    return u;
}

static int use_portable(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0 || strcmp(argv[i], "--portable") == 0)
            return 1;
    }
    return 0;
}

static int64_t parse_i64(const char *s) { return (int64_t)strtoll(s, NULL, 10); }

static In parse_in(char **argv) {
    In in;
    in.reserved = parse_i64(argv[2]);
    in.pool = parse_i64(argv[3]);
    in.rfactor = parse_i64(argv[4]);
    return in;
}

static int selftest(void) {
    In mainv = {40000000, 100000000, 500000};
    In rem = {400, 1001, 500000};
    In dust = {1, 3, 1000000};
    In zero = {0, 0, 0};
    In div0 = {1, 0, 500000};
    In over = {60000000, 100000000, 500000};
    In full = {50000000, 100000000, 500000};
    In r0 = {40000000, 100000000, 0};
    In ovf = {1, 7000000000LL, 2000000000LL};
    In ovf2 = {10000000000000LL, 100000000, 1000000};
    if (usage_with(mainv, umul_ok_i128, uadd_ok_i128) != 800000) return 1;
    if (wrong_pool_with(mainv, umul_ok_portable, uadd_ok_portable) != 400000) return 1;
    if (wrong_compound_with(mainv, umul_ok_i128, uadd_ok_i128) != 285714) return 1;
    if (wrong_apply_with(mainv, umul_ok_i128) != 50000000) return 1;
    if (usage_with(rem, umul_ok_i128, uadd_ok_i128) != 800000) return 1;
    if (wrong_fused_with(rem, umul_ok_i128) != 799200) return 1;
    if (wrong_fused_with(mainv, umul_ok_portable) != 0) return 1;
    if (usage_with(dust, umul_ok_i128, uadd_ok_i128) != 333333) return 1;
    if (wrong_ceil_with(dust, umul_ok_i128, uadd_ok_i128) != 333334) return 1;
    if (usage_with(zero, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    if (inputs_ok_with(zero, umul_ok_i128) != 1) return 1;
    if (inputs_ok_with(div0, umul_ok_i128) != 0) return 1;
    if (usage_with(over, umul_ok_i128, uadd_ok_i128) != 1200000) return 1;
    if (wrong_cap_with(over, umul_ok_portable, uadd_ok_portable) != 1000000) return 1;
    if (usage_with(full, umul_ok_i128, uadd_ok_i128) != 1000000) return 1;
    if (inputs_ok_with(r0, umul_ok_i128) != 0) return 1;
    if (inputs_ok_with(ovf, umul_ok_i128) != 0) return 1;
    if (inputs_ok_with(ovf, umul_ok_portable) != 0) return 1;
    if (wrap_mul(7000000000LL, 2000000000LL) != -4446744073709551616LL) return 1;
    if (inputs_ok_with(ovf2, umul_ok_i128) != 0) return 1;
    if (apply_with(100000000, 500000, umul_ok_i128) != 50000000) return 1;
    fputs("PASS\n", stdout);
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    In in;
    int64_t out;
    int (*umul)(int64_t, int64_t);
    int (*uadd)(int64_t, int64_t);

    if (argc < 2) {
        fputs("usage: gmx_v2_usage_factor_c11 selftest|kind args... [--limbs]\n", stderr);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    kind = argv[1];
    umul = use_portable(argc, argv) ? umul_ok_portable : umul_ok_i128;
    uadd = use_portable(argc, argv) ? uadd_ok_portable : uadd_ok_i128;

    if (strcmp(kind, "naivemul") == 0) {
        if (argc < 4) { fputs("need a b\n", stderr); return 2; }
        out = wrap_mul(parse_i64(argv[2]), parse_i64(argv[3]));
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "wrongborrow") == 0) {
        if (argc < 4) { fputs("need size factor\n", stderr); return 2; }
        out = apply_with(parse_i64(argv[2]), parse_i64(argv[3]), umul);
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (argc < 5) {
        fputs("need reserved pool rfactor\n", stderr);
        return 2;
    }
    in = parse_in(argv);
    if (strcmp(kind, "ok") == 0) out = inputs_ok_with(in, umul);
    else if (strcmp(kind, "usage") == 0) out = usage_with(in, umul, uadd);
    else if (strcmp(kind, "wrongpool") == 0) out = wrong_pool_with(in, umul, uadd);
    else if (strcmp(kind, "wrongcompound") == 0) out = wrong_compound_with(in, umul, uadd);
    else if (strcmp(kind, "wrongapply") == 0) out = wrong_apply_with(in, umul);
    else if (strcmp(kind, "wrongfused") == 0) out = wrong_fused_with(in, umul);
    else if (strcmp(kind, "wrongceil") == 0) out = wrong_ceil_with(in, umul, uadd);
    else if (strcmp(kind, "wrongcap") == 0) out = wrong_cap_with(in, umul, uadd);
    else {
        fprintf(stderr, "unknown kind %s\n", kind);
        return 2;
    }
    printf("%" PRId64 "\n", out);
    return 0;
}
