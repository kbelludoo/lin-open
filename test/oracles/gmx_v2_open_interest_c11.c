/*
 * Independent C11 oracle for GMX V2 applyDeltaToOpenInterest
 * (uint64-scale, unsigned OI + signed long-flipped virtual inventory).
 *
 * Two overflow detectors:
 *   1. GCC/Clang signed __int128
 *   2. Portable INT64_MAX / INT64_MIN headroom
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
    int64_t index, oi, vi, has_v, is_long, delta, use_tok, max_oi;
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

static int sadd_ok_i128(int64_t a, int64_t b) {
    __int128 s = (__int128)a + (__int128)b;
    return s >= INT64_MIN && s <= INT64_MAX;
}

static int sadd_ok_portable(int64_t a, int64_t b) {
    if (b >= 0) return a <= INT64_MAX - b;
    return a >= INT64_MIN - b;
}

static int64_t mag_i64(int64_t x) {
    if (x >= 0) return x;
    return -x;
}

static int mag_ok(int64_t x) {
    if (x >= 0) return 1;
    return (-x) >= 0;
}

static int64_t vi_delta(int64_t is_long, int64_t delta) {
    return is_long == 1 ? -delta : delta;
}

static int64_t wrap_add(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a + (uint64_t)b);
}

static int ok_with(In in,
                   int (*uadd)(int64_t, int64_t),
                   int (*sadd)(int64_t, int64_t)) {
    int64_t mag, next_oi, vd;
    if (in.index == 0 || in.oi < 0 || in.max_oi < 0) return 0;
    if (!mag_ok(in.delta)) return 0;
    mag = mag_i64(in.delta);
    if (in.delta >= 0) {
        if (!uadd(in.oi, in.delta)) return 0;
        next_oi = in.oi + in.delta;
        if ((uint64_t)in.max_oi < (uint64_t)next_oi) return 0;
    } else if ((uint64_t)in.oi < (uint64_t)mag) {
        return 0;
    }
    if (in.use_tok == 0 && in.has_v == 1) {
        vd = vi_delta(in.is_long, in.delta);
        if (!sadd(in.vi, vd)) return 0;
    }
    return 1;
}

static int64_t next_oi_with(In in,
                            int (*uadd)(int64_t, int64_t),
                            int (*sadd)(int64_t, int64_t)) {
    if (!ok_with(in, uadd, sadd)) return 0;
    if (in.delta >= 0) return in.oi + in.delta;
    return in.oi - mag_i64(in.delta);
}

static int64_t next_vi_with(In in,
                            int (*uadd)(int64_t, int64_t),
                            int (*sadd)(int64_t, int64_t)) {
    if (!ok_with(in, uadd, sadd)) return 0;
    if (in.use_tok != 0 || in.has_v == 0) return in.vi;
    return in.vi + vi_delta(in.is_long, in.delta);
}

static int64_t wrong_naive_oi(In in) { return wrap_add(in.oi, in.delta); }

static int64_t wrong_bounded_oi(In in) {
    int64_t mag;
    if (in.oi < 0) return 0;
    if (in.delta >= 0) {
        if (!uadd_ok_i128(in.oi, in.delta)) return 0;
        return in.oi + in.delta;
    }
    mag = mag_i64(in.delta);
    if ((uint64_t)in.oi < (uint64_t)mag) return 0;
    return in.oi - mag;
}

static int64_t wrong_noflip_vi(In in) {
    if (in.use_tok != 0 || in.has_v == 0) return in.vi;
    return in.vi + in.delta;
}

static int64_t wrong_alwaysflip_vi(In in) {
    if (in.use_tok != 0 || in.has_v == 0) return in.vi;
    return in.vi - in.delta;
}

static int64_t wrong_tokens_vi(In in) {
    if (in.use_tok == 0 || in.has_v == 0) return in.vi;
    return in.vi + vi_delta(in.is_long, in.delta);
}

static int64_t wrong_unsigned_vi(In in) {
    int64_t n = in.vi + vi_delta(in.is_long, in.delta);
    return n < 0 ? 0 : n;
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
    in.index = parse_i64(argv[2]);
    in.oi = parse_i64(argv[3]);
    in.vi = parse_i64(argv[4]);
    in.has_v = parse_i64(argv[5]);
    in.is_long = parse_i64(argv[6]);
    in.delta = parse_i64(argv[7]);
    in.use_tok = parse_i64(argv[8]);
    in.max_oi = parse_i64(argv[9]);
    return in;
}

static int selftest(void) {
    In a = {1, 100000000, 50000000, 1, 1, 30000000, 0, 200000000};
    In b = {1, 100000000, 50000000, 1, 0, 30000000, 0, 200000000};
    In n = {1, 100000000, 50000000, 1, 1, -150000000, 0, 200000000};
    In v = {1, 100000000, 20000000, 1, 1, 50000000, 0, 200000000};
    In o = {1, 7000000000000000000LL, 0, 0, 1, 3000000000000000000LL, 1, 9000000000000000000LL};
    In w = {1, 0, 7000000000000000000LL, 1, 0, 3000000000000000000LL, 0, 9000000000000000000LL};
    if (next_oi_with(a, uadd_ok_i128, sadd_ok_i128) != 130000000) return 1;
    if (next_vi_with(a, uadd_ok_i128, sadd_ok_i128) != 20000000) return 1;
    if (next_vi_with(a, uadd_ok_portable, sadd_ok_portable) != 20000000) return 1;
    if (wrong_noflip_vi(a) != 80000000) return 1;
    if (next_vi_with(b, uadd_ok_i128, sadd_ok_i128) != 80000000) return 1;
    if (wrong_alwaysflip_vi(b) != 20000000) return 1;
    if (ok_with(n, uadd_ok_i128, sadd_ok_i128) != 0) return 1;
    if (wrong_naive_oi(n) != -50000000) return 1;
    if (wrong_bounded_oi(n) != 0) return 1;
    if (next_vi_with(v, uadd_ok_i128, sadd_ok_i128) != -30000000) return 1;
    if (wrong_unsigned_vi(v) != 0) return 1;
    if (ok_with(o, uadd_ok_i128, sadd_ok_i128) != 0) return 1;
    if (ok_with(o, uadd_ok_portable, sadd_ok_portable) != 0) return 1;
    if (ok_with(w, uadd_ok_i128, sadd_ok_i128) != 0) return 1;
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
    int (*sadd)(int64_t, int64_t);
    int portable;

    if (argc < 2) {
        fputs("usage: gmx_v2_open_interest_c11 selftest|kind index oi vi has_v is_long delta use_tok max_oi [--limbs]\n", stderr);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (argc < 10) {
        fputs("need index oi vi has_v is_long delta use_tok max_oi\n", stderr);
        return 2;
    }
    kind = argv[1];
    in = parse_in(argv);
    portable = use_portable(argc, argv);
    uadd = portable ? uadd_ok_portable : uadd_ok_i128;
    sadd = portable ? sadd_ok_portable : sadd_ok_i128;

    if (strcmp(kind, "oi") == 0) out = next_oi_with(in, uadd, sadd);
    else if (strcmp(kind, "vi") == 0) out = next_vi_with(in, uadd, sadd);
    else if (strcmp(kind, "ok") == 0) out = ok_with(in, uadd, sadd);
    else if (strcmp(kind, "wrongnaive") == 0) out = wrong_naive_oi(in);
    else if (strcmp(kind, "wrongbound") == 0) out = wrong_bounded_oi(in);
    else if (strcmp(kind, "wrongnoflip") == 0) out = wrong_noflip_vi(in);
    else if (strcmp(kind, "wrongflip") == 0) out = wrong_alwaysflip_vi(in);
    else if (strcmp(kind, "wrongtokens") == 0) out = wrong_tokens_vi(in);
    else if (strcmp(kind, "wrongu") == 0) out = wrong_unsigned_vi(in);
    else if (strcmp(kind, "naiveadd") == 0) out = wrap_add(in.oi, in.delta);
    else {
        fprintf(stderr, "unknown kind %s\n", kind);
        return 2;
    }
    printf("%" PRId64 "\n", out);
    return 0;
}
