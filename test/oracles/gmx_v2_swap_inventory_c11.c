/*
 * Independent C11 oracle for GMX V2 applyDeltaToVirtualInventoryForSwaps
 * (uint64-scale, unsigned long-token / short-token pair, floor-at-zero).
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
    int64_t has_v, token_ok, is_long_token, long_inv, short_inv, delta;
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

static int64_t bounded(int64_t inv, int64_t delta) {
    int64_t mag;
    if (delta >= 0) return inv + delta;
    mag = mag_i64(delta);
    if ((uint64_t)inv < (uint64_t)mag) return 0;
    return inv - mag;
}

static int64_t wrap_add(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a + (uint64_t)b);
}

static int ok_with(In in, int (*uadd)(int64_t, int64_t)) {
    int64_t inv;
    if (in.long_inv < 0 || in.short_inv < 0) return 0;
    if (!mag_ok(in.delta)) return 0;
    if (in.has_v == 0) return 1;
    if (in.token_ok == 0) return 0;
    inv = in.is_long_token == 1 ? in.long_inv : in.short_inv;
    if (in.delta >= 0 && !uadd(inv, in.delta)) return 0;
    return 1;
}

static int64_t applied_with(In in, int (*uadd)(int64_t, int64_t)) {
    if (!ok_with(in, uadd)) return 0;
    return in.has_v == 0 ? 0 : 1;
}

static int64_t next_long_with(In in, int (*uadd)(int64_t, int64_t)) {
    if (!ok_with(in, uadd)) return 0;
    if (in.has_v == 0) return in.long_inv;
    if (in.is_long_token == 1) return bounded(in.long_inv, in.delta);
    return in.long_inv;
}

static int64_t next_short_with(In in, int (*uadd)(int64_t, int64_t)) {
    if (!ok_with(in, uadd)) return 0;
    if (in.has_v == 0) return in.short_inv;
    if (in.is_long_token == 1) return in.short_inv;
    return bounded(in.short_inv, in.delta);
}

static int64_t next_value_with(In in, int (*uadd)(int64_t, int64_t)) {
    if (!ok_with(in, uadd)) return 0;
    if (in.has_v == 0) return 0;
    if (in.is_long_token == 1) return bounded(in.long_inv, in.delta);
    return bounded(in.short_inv, in.delta);
}

static int64_t wrong_both_long(In in) { return bounded(in.long_inv, in.delta); }
static int64_t wrong_both_short(In in) { return bounded(in.short_inv, in.delta); }

static int64_t wrong_other_long(In in) {
    return in.is_long_token == 1 ? in.long_inv : bounded(in.long_inv, in.delta);
}

static int64_t wrong_other_short(In in) {
    return in.is_long_token == 1 ? bounded(in.short_inv, in.delta) : in.short_inv;
}

static int64_t wrong_flip_long(In in) {
    return in.is_long_token == 1 ? bounded(in.long_inv, -in.delta) : in.long_inv;
}

static int64_t wrong_reject_ok(In in) {
    int64_t inv;
    if (in.has_v == 0) return 1;
    if (in.token_ok == 0) return 0;
    if (in.long_inv < 0 || in.short_inv < 0) return 0;
    if (!mag_ok(in.delta)) return 0;
    inv = in.is_long_token == 1 ? in.long_inv : in.short_inv;
    if (in.delta < 0 && (uint64_t)inv < (uint64_t)mag_i64(in.delta)) return 0;
    if (in.delta >= 0 && !uadd_ok_i128(inv, in.delta)) return 0;
    return 1;
}

static int64_t wrong_signed_long(In in) { return in.long_inv + in.delta; }

static int64_t wrong_token_first(In in, int (*uadd)(int64_t, int64_t)) {
    if (in.token_ok == 0) return 0;
    return ok_with(in, uadd);
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

static In parse_in(char **argv) {
    In in;
    in.has_v = parse_i64(argv[2]);
    in.token_ok = parse_i64(argv[3]);
    in.is_long_token = parse_i64(argv[4]);
    in.long_inv = parse_i64(argv[5]);
    in.short_inv = parse_i64(argv[6]);
    in.delta = parse_i64(argv[7]);
    return in;
}

static int selftest(void) {
    In a = {1, 1, 1, 100000000, 50000000, 30000000};
    In b = {1, 1, 0, 100000000, 50000000, 30000000};
    In f = {1, 1, 1, 100000000, 50000000, -150000000};
    In s = {1, 1, 0, 100000000, 50000000, -80000000};
    In n = {0, 1, 1, 100000000, 50000000, 30000000};
    In t = {0, 0, 0, 100000000, 50000000, 30000000};
    In bad = {1, 0, 0, 100000000, 50000000, 30000000};
    In o = {1, 1, 1, 7000000000000000000LL, 0, 3000000000000000000LL};
    if (next_long_with(a, uadd_ok_i128) != 130000000) return 1;
    if (next_short_with(a, uadd_ok_i128) != 50000000) return 1;
    if (next_short_with(a, uadd_ok_portable) != 50000000) return 1;
    if (wrong_both_short(a) != 80000000) return 1;
    if (wrong_flip_long(a) != 70000000) return 1;
    if (next_short_with(b, uadd_ok_i128) != 80000000) return 1;
    if (next_long_with(b, uadd_ok_i128) != 100000000) return 1;
    if (ok_with(f, uadd_ok_i128) != 1) return 1;
    if (next_long_with(f, uadd_ok_i128) != 0) return 1;
    if (wrong_reject_ok(f) != 0) return 1;
    if (wrong_signed_long(f) != -50000000) return 1;
    if (next_short_with(s, uadd_ok_i128) != 0) return 1;
    if (applied_with(n, uadd_ok_i128) != 0) return 1;
    if (next_value_with(n, uadd_ok_i128) != 0) return 1;
    if (ok_with(t, uadd_ok_i128) != 1) return 1;
    if (wrong_token_first(t, uadd_ok_i128) != 0) return 1;
    if (ok_with(bad, uadd_ok_i128) != 0) return 1;
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
    int portable;

    if (argc < 2) {
        fputs("usage: gmx_v2_swap_inventory_c11 selftest|kind has_v token_ok is_long_token long_inv short_inv delta [--limbs]\n", stderr);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (argc < 8) {
        fputs("need has_v token_ok is_long_token long_inv short_inv delta\n", stderr);
        return 2;
    }
    kind = argv[1];
    in = parse_in(argv);
    portable = use_portable(argc, argv);
    uadd = portable ? uadd_ok_portable : uadd_ok_i128;

    if (strcmp(kind, "ok") == 0) out = ok_with(in, uadd);
    else if (strcmp(kind, "applied") == 0) out = applied_with(in, uadd);
    else if (strcmp(kind, "long") == 0) out = next_long_with(in, uadd);
    else if (strcmp(kind, "short") == 0) out = next_short_with(in, uadd);
    else if (strcmp(kind, "value") == 0) out = next_value_with(in, uadd);
    else if (strcmp(kind, "wrongbothL") == 0) out = wrong_both_long(in);
    else if (strcmp(kind, "wrongbothS") == 0) out = wrong_both_short(in);
    else if (strcmp(kind, "wrongotherL") == 0) out = wrong_other_long(in);
    else if (strcmp(kind, "wrongotherS") == 0) out = wrong_other_short(in);
    else if (strcmp(kind, "wrongflipL") == 0) out = wrong_flip_long(in);
    else if (strcmp(kind, "wrongrej") == 0) out = wrong_reject_ok(in);
    else if (strcmp(kind, "wrongsigned") == 0) out = wrong_signed_long(in);
    else if (strcmp(kind, "wrongtok") == 0) out = wrong_token_first(in, uadd);
    else if (strcmp(kind, "naiveadd") == 0) out = wrap_add(in.long_inv, in.delta);
    else {
        fprintf(stderr, "unknown kind %s\n", kind);
        return 2;
    }
    printf("%" PRId64 "\n", out);
    return 0;
}
