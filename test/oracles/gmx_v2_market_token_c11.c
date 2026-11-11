/*
 * Independent C11 oracle for GMX V2 usdToMarketTokenAmount
 * (uint64-scale, three-branch first deposit + inverse).
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
    int64_t usd, pool, supply;
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

static int64_t wrap_mul(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a * (uint64_t)b);
}

static int64_t wrap_add(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a + (uint64_t)b);
}

static int64_t gdiv(void) { return 1000000; }

static int64_t wei(int64_t value) {
    if (value < 0) return 0;
    return value / gdiv();
}

static int usd_ok_with(In in, int (*umul)(int64_t, int64_t), int (*uadd)(int64_t, int64_t)) {
    if (in.usd < 0 || in.pool < 0 || in.supply < 0) return 0;
    if (in.supply == 0) {
        if (in.pool == 0) return 1;
        return uadd(in.pool, in.usd);
    }
    if (in.pool == 0) return 0;
    return umul(in.supply, in.usd);
}

static int64_t usd_with(In in, int (*umul)(int64_t, int64_t), int (*uadd)(int64_t, int64_t)) {
    if (!usd_ok_with(in, umul, uadd)) return 0;
    if (in.supply == 0) {
        if (in.pool == 0) return wei(in.usd);
        return wei(in.pool + in.usd);
    }
    return (in.supply * in.usd) / in.pool;
}

static int tok_ok_with(In in, int (*umul)(int64_t, int64_t)) {
    if (in.usd < 0 || in.pool < 0 || in.supply < 0) return 0;
    if (in.supply == 0) return 0;
    return umul(in.pool, in.usd);
}

static int64_t tok_with(In in, int (*umul)(int64_t, int64_t)) {
    if (!tok_ok_with(in, umul)) return 0;
    return (in.pool * in.usd) / in.supply;
}

static int64_t wrong_lido(In in, int (*umul)(int64_t, int64_t)) {
    if (in.usd < 0 || in.pool < 0 || in.supply < 0) return 0;
    if (in.pool == 0) return in.usd;
    if (!umul(in.supply, in.usd)) return 0;
    return (in.supply * in.usd) / in.pool;
}

static int64_t wrong_ignore(In in, int (*umul)(int64_t, int64_t)) {
    if (in.usd < 0 || in.pool < 0 || in.supply < 0) return 0;
    if (in.supply == 0) return wei(in.usd);
    if (in.pool == 0) return 0;
    if (!umul(in.supply, in.usd)) return 0;
    return (in.supply * in.usd) / in.pool;
}

static int64_t wrong_sum(In in, int (*umul)(int64_t, int64_t), int (*uadd)(int64_t, int64_t)) {
    if (in.usd < 0 || in.pool < 0 || in.supply < 0) return 0;
    if (in.supply == 0) {
        if (in.pool == 0) return in.usd;
        if (!uadd(in.pool, in.usd)) return 0;
        return in.pool + in.usd;
    }
    if (in.pool == 0) return 0;
    if (!umul(in.supply, in.usd)) return 0;
    return (in.supply * in.usd) / in.pool;
}

static int64_t wrong_or(In in, int (*umul)(int64_t, int64_t)) {
    if (in.usd < 0 || in.pool < 0 || in.supply < 0) return 0;
    if (in.supply == 0) return wei(in.usd);
    if (in.pool == 0) return wei(in.usd);
    if (!umul(in.supply, in.usd)) return 0;
    return (in.supply * in.usd) / in.pool;
}

static int64_t wrong_always(In in, int (*umul)(int64_t, int64_t)) {
    if (in.usd < 0 || in.pool < 0 || in.supply < 0) return 0;
    if (in.pool == 0) return 0;
    if (!umul(in.supply, in.usd)) return 0;
    return (in.supply * in.usd) / in.pool;
}

static int64_t wrong_wei(In in) {
    if (in.usd < 0 || in.pool < 0 || in.supply < 0) return 0;
    return wei(in.usd);
}

static int64_t wrong_ceil(In in, int (*umul)(int64_t, int64_t), int (*uadd)(int64_t, int64_t)) {
    int64_t prod;
    if (in.usd < 0 || in.pool < 0 || in.supply < 0) return 0;
    if (in.supply == 0 || in.pool == 0) return 0;
    if (!umul(in.supply, in.usd)) return 0;
    prod = in.supply * in.usd;
    if (!uadd(prod, in.pool - 1)) return 0;
    return (prod + (in.pool - 1)) / in.pool;
}

static int64_t wrong_inv(In in, int (*umul)(int64_t, int64_t)) {
    if (in.usd < 0 || in.pool < 0 || in.supply < 0) return 0;
    if (in.supply == 0) return in.usd;
    if (!umul(in.pool, in.usd)) return 0;
    return (in.pool * in.usd) / in.supply;
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
    in.usd = parse_i64(argv[2]);
    in.pool = parse_i64(argv[3]);
    in.supply = parse_i64(argv[4]);
    return in;
}

static int selftest(void) {
    In first = {100000000, 0, 0};
    In left = {100000000, 20000000, 0};
    In sub = {50000000, 200000000, 100000000};
    In inv = {25000000, 200000000, 100000000};
    In rem = {4, 5, 3};
    In dust = {1, 3, 1};
    In pz = {50000000, 0, 100000000};
    In leftover0 = {0, 20000000, 0};
    In rt = {100, 100000000, 100};
    In addo = {3000000000000000000LL, 7000000000000000000LL, 0};
    In mulo = {2000000000LL, 1, 7000000000LL};
    In eq = {50000000, 100000000, 100000000};
    In z = {0, 0, 0};
    if (usd_with(first, umul_ok_i128, uadd_ok_i128) != 100) return 1;
    if (wrong_lido(first, umul_ok_i128) != 100000000) return 1;
    if (usd_with(left, umul_ok_i128, uadd_ok_i128) != 120) return 1;
    if (wrong_lido(left, umul_ok_i128) != 0) return 1;
    if (wrong_ignore(left, umul_ok_i128) != 100) return 1;
    if (wrong_sum(left, umul_ok_i128, uadd_ok_i128) != 120000000) return 1;
    if (usd_with(sub, umul_ok_i128, uadd_ok_i128) != 25000000) return 1;
    if (wrong_wei(sub) != 50) return 1;
    if (tok_with(inv, umul_ok_i128) != 50000000) return 1;
    if (tok_ok_with(first, umul_ok_i128) != 0) return 1;
    if (wrong_inv(first, umul_ok_i128) != 100000000) return 1;
    if (usd_ok_with(pz, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    if (wrong_lido(pz, umul_ok_i128) != 50000000) return 1;
    if (wrong_or(pz, umul_ok_i128) != 50) return 1;
    if (usd_with(rem, umul_ok_i128, uadd_ok_i128) != 2) return 1;
    if (wrong_ceil(rem, umul_ok_i128, uadd_ok_i128) != 3) return 1;
    if (usd_with(dust, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    if (usd_with(leftover0, umul_ok_i128, uadd_ok_i128) != 20) return 1;
    if (tok_with(rt, umul_ok_i128) != 100000000) return 1;
    if (usd_ok_with(addo, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    if (usd_ok_with(addo, umul_ok_portable, uadd_ok_portable) != 0) return 1;
    if (wrap_add(7000000000000000000LL, 3000000000000000000LL) != -8446744073709551616LL) return 1;
    if (usd_ok_with(mulo, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    if (usd_ok_with(mulo, umul_ok_portable, uadd_ok_portable) != 0) return 1;
    if (wrap_mul(7000000000LL, 2000000000LL) != -4446744073709551616LL) return 1;
    if (usd_with(eq, umul_ok_i128, uadd_ok_i128) != 50000000) return 1;
    if (usd_ok_with(first, umul_ok_i128, uadd_ok_i128) != 1) return 1;
    if (wrong_always(first, umul_ok_i128) != 0) return 1;
    if (wrong_or(left, umul_ok_i128) != 100) return 1;
    if (usd_with(z, umul_ok_i128, uadd_ok_i128) != 0) return 1;
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
        fputs("usage: gmx_v2_market_token_c11 selftest|kind usd pool supply [--limbs]\n", stderr);
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
    if (strcmp(kind, "naiveadd") == 0) {
        if (argc < 4) { fputs("need a b\n", stderr); return 2; }
        out = wrap_add(parse_i64(argv[2]), parse_i64(argv[3]));
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (argc < 5) {
        fputs("need usd pool supply\n", stderr);
        return 2;
    }
    in = parse_in(argv);
    if (strcmp(kind, "ok") == 0) out = usd_ok_with(in, umul, uadd);
    else if (strcmp(kind, "usd") == 0) out = usd_with(in, umul, uadd);
    else if (strcmp(kind, "tok") == 0) out = tok_with(in, umul);
    else if (strcmp(kind, "tokok") == 0) out = tok_ok_with(in, umul);
    else if (strcmp(kind, "wronglido") == 0) out = wrong_lido(in, umul);
    else if (strcmp(kind, "wrongignore") == 0) out = wrong_ignore(in, umul);
    else if (strcmp(kind, "wrongsum") == 0) out = wrong_sum(in, umul, uadd);
    else if (strcmp(kind, "wrongor") == 0) out = wrong_or(in, umul);
    else if (strcmp(kind, "wrongalways") == 0) out = wrong_always(in, umul);
    else if (strcmp(kind, "wrongwei") == 0) out = wrong_wei(in);
    else if (strcmp(kind, "wrongceil") == 0) out = wrong_ceil(in, umul, uadd);
    else if (strcmp(kind, "wronginv") == 0) out = wrong_inv(in, umul);
    else {
        fprintf(stderr, "unknown kind %s\n", kind);
        return 2;
    }
    printf("%" PRId64 "\n", out);
    return 0;
}
