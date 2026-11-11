/*
 * Independent C11 oracle for GMX V2 _getClaimableFactor
 * (uint64-scale, max(time,account) then delay-default then reduction).
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
    int64_t ft, fa, red, div, delay, tkey, now_ts;
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

static int inputs_ok_with(In in, int (*umul)(int64_t, int64_t)) {
    int64_t prod;
    if (in.ft < 0 || in.fa < 0 || in.red < 0 || in.div < 0 || in.delay < 0 ||
        in.tkey < 0 || in.now_ts < 0)
        return 0;
    if (!umul(in.tkey, in.div)) return 0;
    prod = in.tkey * in.div;
    if (u_lt(in.now_ts, prod)) return 0;
    return 1;
}

static int64_t pick(int64_t ft, int64_t fa) { return u_lt(ft, fa) ? fa : ft; }

static int64_t factor_with(In in, int (*umul)(int64_t, int64_t)) {
    int64_t f, td;
    if (!inputs_ok_with(in, umul)) return 0;
    f = pick(in.ft, in.fa);
    td = in.now_ts - (in.tkey * in.div);
    if (f == 0 && in.red == 0 && u_lt(in.delay, td)) f = gfloat();
    if (u_lt(in.red, f)) return f - in.red;
    return 0;
}

static int ok_with(In in, int (*umul)(int64_t, int64_t)) {
    int64_t f;
    if (!inputs_ok_with(in, umul)) return 0;
    f = factor_with(in, umul);
    if (u_lt(gfloat(), f)) return 0;
    return 1;
}

static int64_t apply_with(int64_t amount, int64_t factor, int (*umul)(int64_t, int64_t)) {
    if (amount < 0 || factor < 0) return 0;
    if (!umul(amount, factor)) return 0;
    return (amount * factor) / gfloat();
}

static int claim_ok_with(int64_t amount, int64_t factor, int64_t claimed, int (*umul)(int64_t, int64_t)) {
    int64_t adj;
    if (amount < 0 || claimed < 0) return 0;
    if (u_lt(gfloat(), factor)) return 0;
    if (!umul(amount, factor)) return 0;
    adj = apply_with(amount, factor, umul);
    if (!u_lt(claimed, adj)) return 0;
    return 1;
}

static int64_t amount_to_claim_with(int64_t amount, int64_t factor, int64_t claimed, int (*umul)(int64_t, int64_t)) {
    if (!claim_ok_with(amount, factor, claimed, umul)) return 0;
    return apply_with(amount, factor, umul) - claimed;
}

static int64_t wrong_min(int64_t ft, int64_t fa) { return u_lt(fa, ft) ? fa : ft; }
static int64_t wrong_time_only(int64_t ft, int64_t fa) { (void)fa; return ft; }

static int64_t wrong_no_default(In in, int (*umul)(int64_t, int64_t)) {
    int64_t f;
    if (!inputs_ok_with(in, umul)) return 0;
    f = pick(in.ft, in.fa);
    if (u_lt(in.red, f)) return f - in.red;
    return 0;
}

static int64_t wrong_ge_delay(In in, int (*umul)(int64_t, int64_t)) {
    int64_t f, td;
    if (!inputs_ok_with(in, umul)) return 0;
    f = pick(in.ft, in.fa);
    td = in.now_ts - (in.tkey * in.div);
    if (f == 0 && in.red == 0 && !u_lt(td, in.delay)) f = gfloat();
    if (u_lt(in.red, f)) return f - in.red;
    return 0;
}

static int64_t wrong_default_then_reduce(In in, int (*umul)(int64_t, int64_t)) {
    int64_t f, td;
    if (!inputs_ok_with(in, umul)) return 0;
    f = pick(in.ft, in.fa);
    td = in.now_ts - (in.tkey * in.div);
    if (f == 0 && u_lt(in.delay, td)) f = gfloat();
    if (u_lt(in.red, f)) return f - in.red;
    return 0;
}

static int64_t wrong_ignore_reduction(In in, int (*umul)(int64_t, int64_t)) {
    int64_t f, td;
    if (!inputs_ok_with(in, umul)) return 0;
    f = pick(in.ft, in.fa);
    td = in.now_ts - (in.tkey * in.div);
    if (f == 0 && in.red == 0 && u_lt(in.delay, td)) f = gfloat();
    return f;
}

static int64_t wrong_signed_reduction(int64_t ft, int64_t fa, int64_t red) {
    return pick(ft, fa) - red;
}

static int64_t wrong_add_reduction(int64_t ft, int64_t fa, int64_t red) {
    return pick(ft, fa) + red;
}

static int64_t wrong_cap(In in, int (*umul)(int64_t, int64_t)) {
    int64_t f = factor_with(in, umul);
    if (u_lt(gfloat(), f)) return gfloat();
    return f;
}

static int64_t wrong_rate_dist(int64_t pool, int64_t min_pool, int64_t duration, int64_t rate, int (*umul)(int64_t, int64_t)) {
    int64_t dist, cap;
    if (u_lt(pool, min_pool) || pool == min_pool) return 0;
    if (!umul(duration, rate)) return 0;
    dist = apply_with(duration, rate, umul);
    cap = pool - min_pool;
    if (u_lt(cap, dist)) return cap;
    return dist;
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
    in.ft = parse_i64(argv[2]);
    in.fa = parse_i64(argv[3]);
    in.red = parse_i64(argv[4]);
    in.div = parse_i64(argv[5]);
    in.delay = parse_i64(argv[6]);
    in.tkey = parse_i64(argv[7]);
    in.now_ts = parse_i64(argv[8]);
    return in;
}

static int selftest(void) {
    In maxp = {400000, 600000, 0, 3600, 86400, 1000, 3686399};
    In ddef = {0, 0, 0, 3600, 86400, 1000, 3686401};
    In exact = {0, 0, 0, 3600, 86400, 1000, 3686400};
    In redc = {800000, 0, 300000, 3600, 86400, 1000, 3686399};
    In over = {300000, 0, 500000, 3600, 86400, 1000, 3686399};
    In blockd = {0, 0, 200000, 3600, 86400, 1000, 3686401};
    In bigf = {2000000, 0, 0, 3600, 86400, 1000, 3686399};
    In under = {0, 0, 0, 3600, 86400, 1000, 1};
    In ovf = {0, 0, 0, 2000000000LL, 0, 7000000000LL, 0};
    In eq = {500000, 500000, 0, 3600, 86400, 1000, 3686399};
    if (factor_with(maxp, umul_ok_i128) != 600000) return 1;
    if (factor_with(maxp, umul_ok_portable) != 600000) return 1;
    if (wrong_min(400000, 600000) != 400000) return 1;
    if (factor_with(ddef, umul_ok_i128) != 1000000) return 1;
    if (wrong_no_default(ddef, umul_ok_i128) != 0) return 1;
    if (factor_with(exact, umul_ok_i128) != 0) return 1;
    if (wrong_ge_delay(exact, umul_ok_i128) != 1000000) return 1;
    if (factor_with(redc, umul_ok_i128) != 500000) return 1;
    if (wrong_ignore_reduction(redc, umul_ok_i128) != 800000) return 1;
    if (factor_with(over, umul_ok_i128) != 0) return 1;
    if (wrong_signed_reduction(300000, 0, 500000) != -200000) return 1;
    if (wrong_add_reduction(800000, 0, 300000) != 1100000) return 1;
    if (factor_with(blockd, umul_ok_i128) != 0) return 1;
    if (wrong_default_then_reduce(blockd, umul_ok_i128) != 800000) return 1;
    if (ok_with(bigf, umul_ok_i128) != 0) return 1;
    if (factor_with(bigf, umul_ok_i128) != 2000000) return 1;
    if (wrong_cap(bigf, umul_ok_i128) != 1000000) return 1;
    if (ok_with(under, umul_ok_i128) != 0) return 1;
    if (ok_with(ovf, umul_ok_i128) != 0) return 1;
    if (ok_with(ovf, umul_ok_portable) != 0) return 1;
    if (amount_to_claim_with(100000000, 500000, 0, umul_ok_i128) != 50000000) return 1;
    if (amount_to_claim_with(100000000, 500000, 10000000, umul_ok_portable) != 40000000) return 1;
    if (claim_ok_with(100000000, 500000, 50000000, umul_ok_i128) != 0) return 1;
    if (claim_ok_with(100000000, 2000000, 0, umul_ok_i128) != 0) return 1;
    if (factor_with(eq, umul_ok_i128) != 500000) return 1;
    if (wrong_rate_dist(200000000, 100000000, 500000, 1000000, umul_ok_i128) != 500000) return 1;
    if (wrap_mul(7000000000LL, 2000000000LL) != -4446744073709551616LL) return 1;
    (void)uadd_ok_i128;
    (void)uadd_ok_portable;
    fputs("PASS\n", stdout);
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    In in;
    int64_t out;
    int (*umul)(int64_t, int64_t);
    int64_t amount, factor, claimed, pool, min_pool, duration, rate;

    if (argc < 2) {
        fputs("usage: gmx_v2_claimable_factor_c11 selftest|kind args... [--limbs]\n", stderr);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    kind = argv[1];
    umul = use_portable(argc, argv) ? umul_ok_portable : umul_ok_i128;

    if (strcmp(kind, "wrongmin") == 0 || strcmp(kind, "wrongtime") == 0) {
        if (argc < 4) { fputs("need ft fa\n", stderr); return 2; }
        if (strcmp(kind, "wrongmin") == 0) out = wrong_min(parse_i64(argv[2]), parse_i64(argv[3]));
        else out = wrong_time_only(parse_i64(argv[2]), parse_i64(argv[3]));
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "wrongsigned") == 0 || strcmp(kind, "wrongadd") == 0) {
        if (argc < 5) { fputs("need ft fa red\n", stderr); return 2; }
        if (strcmp(kind, "wrongsigned") == 0)
            out = wrong_signed_reduction(parse_i64(argv[2]), parse_i64(argv[3]), parse_i64(argv[4]));
        else
            out = wrong_add_reduction(parse_i64(argv[2]), parse_i64(argv[3]), parse_i64(argv[4]));
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "apply") == 0 || strcmp(kind, "claimok") == 0 || strcmp(kind, "amount") == 0) {
        if (argc < 5) { fputs("need amount factor claimed\n", stderr); return 2; }
        amount = parse_i64(argv[2]);
        factor = parse_i64(argv[3]);
        claimed = parse_i64(argv[4]);
        if (strcmp(kind, "apply") == 0) out = apply_with(amount, factor, umul);
        else if (strcmp(kind, "claimok") == 0) out = claim_ok_with(amount, factor, claimed, umul);
        else out = amount_to_claim_with(amount, factor, claimed, umul);
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "wrongdist") == 0) {
        if (argc < 6) { fputs("need pool min duration rate\n", stderr); return 2; }
        pool = parse_i64(argv[2]);
        min_pool = parse_i64(argv[3]);
        duration = parse_i64(argv[4]);
        rate = parse_i64(argv[5]);
        out = wrong_rate_dist(pool, min_pool, duration, rate, umul);
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "naivemul") == 0) {
        if (argc < 4) { fputs("need a b\n", stderr); return 2; }
        out = wrap_mul(parse_i64(argv[2]), parse_i64(argv[3]));
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (argc < 9) {
        fputs("need ft fa red div delay tkey now\n", stderr);
        return 2;
    }
    in = parse_in(argv);
    if (strcmp(kind, "ok") == 0) out = ok_with(in, umul);
    else if (strcmp(kind, "value") == 0) out = factor_with(in, umul);
    else if (strcmp(kind, "wrongnodef") == 0) out = wrong_no_default(in, umul);
    else if (strcmp(kind, "wrongge") == 0) out = wrong_ge_delay(in, umul);
    else if (strcmp(kind, "wrongdtr") == 0) out = wrong_default_then_reduce(in, umul);
    else if (strcmp(kind, "wrongign") == 0) out = wrong_ignore_reduction(in, umul);
    else if (strcmp(kind, "wrongcap") == 0) out = wrong_cap(in, umul);
    else {
        fprintf(stderr, "unknown kind %s\n", kind);
        return 2;
    }
    printf("%" PRId64 "\n", out);
    return 0;
}
