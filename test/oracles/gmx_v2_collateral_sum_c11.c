/*
 * Independent C11 oracle for GMX V2 applyDeltaToCollateralSum
 * (uint64-scale, unsigned collateral sum, reject-negative, max always).
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
    int64_t is_long, sum, delta, max_value, index_token;
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

static int64_t mag_i64(int64_t x) {
    if (x >= 0) return x;
    return -x;
}

static int mag_ok(int64_t x) {
    if (x >= 0) return 1;
    return (-x) >= 0;
}

static int u_lt(int64_t a, int64_t b) {
    if (a < 0 && b >= 0) return 0;
    if (a >= 0 && b < 0) return 1;
    return a < b;
}

static int64_t wrap_add(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a + (uint64_t)b);
}

static int delta_ok_with(int64_t sum, int64_t delta, int (*uadd)(int64_t, int64_t)) {
    if (sum < 0) return 0;
    if (!mag_ok(delta)) return 0;
    if (delta >= 0) return uadd(sum, delta);
    return !u_lt(sum, mag_i64(delta));
}

static int64_t next_uint_with(int64_t sum, int64_t delta, int (*uadd)(int64_t, int64_t)) {
    if (!delta_ok_with(sum, delta, uadd)) return 0;
    if (delta >= 0) return sum + delta;
    return sum - mag_i64(delta);
}

static int ok_with(In in, int (*uadd)(int64_t, int64_t)) {
    int64_t nxt;
    if (in.max_value < 0) return 0;
    if (!delta_ok_with(in.sum, in.delta, uadd)) return 0;
    nxt = next_uint_with(in.sum, in.delta, uadd);
    if (u_lt(in.max_value, nxt)) return 0;
    return 1;
}

static int64_t next_value_with(In in, int (*uadd)(int64_t, int64_t)) {
    if (!ok_with(in, uadd)) return 0;
    return next_uint_with(in.sum, in.delta, uadd);
}

static int64_t wrong_bounded_next(int64_t sum, int64_t delta) {
    int64_t mag;
    if (delta >= 0) return sum + delta;
    mag = mag_i64(delta);
    if (u_lt(sum, mag)) return 0;
    return sum - mag;
}

static int wrong_bounded_ok(In in, int (*uadd)(int64_t, int64_t)) {
    int64_t nxt;
    if (in.sum < 0 || in.max_value < 0) return 0;
    if (!mag_ok(in.delta)) return 0;
    if (in.delta >= 0 && !uadd(in.sum, in.delta)) return 0;
    nxt = wrong_bounded_next(in.sum, in.delta);
    if (u_lt(in.max_value, nxt)) return 0;
    return 1;
}

static int64_t wrong_signed_next(int64_t sum, int64_t delta) { return sum + delta; }

static int wrong_no_max_ok(In in, int (*uadd)(int64_t, int64_t)) {
    return delta_ok_with(in.sum, in.delta, uadd);
}

static int64_t wrong_no_max_next(In in, int (*uadd)(int64_t, int64_t)) {
    if (!delta_ok_with(in.sum, in.delta, uadd)) return 0;
    return next_uint_with(in.sum, in.delta, uadd);
}

static int wrong_max_on_inc_ok(In in, int (*uadd)(int64_t, int64_t)) {
    int64_t nxt;
    if (in.max_value < 0) return 0;
    if (!delta_ok_with(in.sum, in.delta, uadd)) return 0;
    if (in.delta > 0) {
        nxt = next_uint_with(in.sum, in.delta, uadd);
        if (u_lt(in.max_value, nxt)) return 0;
    }
    return 1;
}

static int64_t wrong_max_on_inc_next(In in, int (*uadd)(int64_t, int64_t)) {
    if (!wrong_max_on_inc_ok(in, uadd)) return 0;
    return next_uint_with(in.sum, in.delta, uadd);
}

static int wrong_swap_only_ok(In in, int (*uadd)(int64_t, int64_t)) {
    if (in.index_token == 0) return 0;
    return ok_with(in, uadd);
}

static int64_t wrong_flip_next(In in) {
    return in.is_long == 1 ? in.sum + (-in.delta) : in.sum + in.delta;
}

static int64_t wrong_div(In in, int (*uadd)(int64_t, int64_t)) {
    if (!delta_ok_with(in.sum, in.delta, uadd)) return 0;
    return next_uint_with(in.sum, in.delta, uadd) / 2;
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
    in.is_long = parse_i64(argv[2]);
    in.sum = parse_i64(argv[3]);
    in.delta = parse_i64(argv[4]);
    in.max_value = parse_i64(argv[5]);
    in.index_token = parse_i64(argv[6]);
    return in;
}

static int selftest(void) {
    In u = {1, 100000000, 30000000, 200000000, 1};
    In s = {0, 100000000, 30000000, 200000000, 1};
    In oi = {1, 100000000, 30000000, 120000000, 1};
    In od = {1, 150000000, -20000000, 120000000, 1};
    In n = {1, 100000000, -150000000, 200000000, 1};
    In z = {1, 0, 1, 0, 1};
    In zz = {1, 0, 0, 0, 1};
    In sw = {1, 100000000, 30000000, 200000000, 0};
    In o = {1, 7000000000000000000LL, 3000000000000000000LL, INT64_MAX, 1};
    if (next_value_with(u, uadd_ok_i128) != 130000000) return 1;
    if (next_value_with(s, uadd_ok_portable) != 130000000) return 1;
    if (wrong_flip_next(u) != 70000000) return 1;
    if (ok_with(oi, uadd_ok_i128) != 0) return 1;
    if (wrong_no_max_next(oi, uadd_ok_i128) != 130000000) return 1;
    if (ok_with(od, uadd_ok_i128) != 0) return 1;
    if (wrong_max_on_inc_ok(od, uadd_ok_i128) != 1) return 1;
    if (wrong_max_on_inc_next(od, uadd_ok_portable) != 130000000) return 1;
    if (ok_with(n, uadd_ok_i128) != 0) return 1;
    if (wrong_bounded_ok(n, uadd_ok_i128) != 1) return 1;
    if (wrong_bounded_next(100000000, -150000000) != 0) return 1;
    if (wrong_signed_next(100000000, -150000000) != -50000000) return 1;
    if (ok_with(z, uadd_ok_i128) != 0) return 1;
    if (ok_with(zz, uadd_ok_i128) != 1) return 1;
    if (ok_with(sw, uadd_ok_i128) != 1) return 1;
    if (wrong_swap_only_ok(sw, uadd_ok_i128) != 0) return 1;
    if (wrong_div(u, uadd_ok_i128) != 65000000) return 1;
    if (ok_with(o, uadd_ok_i128) != 0) return 1;
    if (ok_with(o, uadd_ok_portable) != 0) return 1;
    if (wrap_add(7000000000000000000LL, 3000000000000000000LL) != -8446744073709551616LL)
        return 1;
    fputs("PASS\n", stdout);
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    In in;
    int64_t out;
    int (*uadd)(int64_t, int64_t);

    if (argc < 2) {
        fputs("usage: gmx_v2_collateral_sum_c11 selftest|kind is_long sum delta max index [--limbs]\n", stderr);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (argc < 7) {
        fputs("need is_long sum delta max_value index_token\n", stderr);
        return 2;
    }
    kind = argv[1];
    in = parse_in(argv);
    uadd = use_portable(argc, argv) ? uadd_ok_portable : uadd_ok_i128;

    if (strcmp(kind, "ok") == 0) out = ok_with(in, uadd);
    else if (strcmp(kind, "value") == 0) out = next_value_with(in, uadd);
    else if (strcmp(kind, "wrongboundok") == 0) out = wrong_bounded_ok(in, uadd);
    else if (strcmp(kind, "wrongbound") == 0) out = wrong_bounded_next(in.sum, in.delta);
    else if (strcmp(kind, "wrongsigned") == 0) out = wrong_signed_next(in.sum, in.delta);
    else if (strcmp(kind, "wrongnomaxok") == 0) out = wrong_no_max_ok(in, uadd);
    else if (strcmp(kind, "wrongnomax") == 0) out = wrong_no_max_next(in, uadd);
    else if (strcmp(kind, "wrongmaxincok") == 0) out = wrong_max_on_inc_ok(in, uadd);
    else if (strcmp(kind, "wrongmaxinc") == 0) out = wrong_max_on_inc_next(in, uadd);
    else if (strcmp(kind, "wrongswap") == 0) out = wrong_swap_only_ok(in, uadd);
    else if (strcmp(kind, "wrongflip") == 0) out = wrong_flip_next(in);
    else if (strcmp(kind, "wrongdiv") == 0) out = wrong_div(in, uadd);
    else if (strcmp(kind, "naiveadd") == 0) out = wrap_add(in.sum, in.delta);
    else {
        fprintf(stderr, "unknown kind %s\n", kind);
        return 2;
    }
    printf("%" PRId64 "\n", out);
    return 0;
}
