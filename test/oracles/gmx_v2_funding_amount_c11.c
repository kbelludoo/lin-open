/*
 * Independent C11 oracle for GMX V2 getFundingAmount
 * (uint64-scale, round-up charge vs round-down claim).
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
    int64_t size, latest, entry;
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
static int64_t denom(void) { return 1000000000; }

static int inputs_ok_with(In in, int (*umul)(int64_t, int64_t)) {
    int64_t diff;
    if (in.size < 0 || in.latest < 0 || in.entry < 0) return 0;
    if (u_lt(in.latest, in.entry)) return 0;
    diff = in.latest - in.entry;
    if (!umul(in.size, diff)) return 0;
    return 1;
}

static int64_t amount_with(In in, int round_up, int (*umul)(int64_t, int64_t),
                           int (*uadd)(int64_t, int64_t)) {
    int64_t diff, prod, q, r, d;
    if (!inputs_ok_with(in, umul)) return 0;
    if (round_up < 0 || round_up > 1) return 0;
    d = denom();
    if (d == 0) return 0;
    diff = in.latest - in.entry;
    prod = in.size * diff;
    q = prod / d;
    r = prod - (q * d);
    if (round_up == 0 || r == 0) return q;
    if (!uadd(q, 1)) return 0;
    return q + 1;
}

static int64_t wrong_v1_with(In in, int (*umul)(int64_t, int64_t)) {
    int64_t diff;
    if (in.size < 0) return 0;
    if (u_lt(in.latest, in.entry)) return 0;
    diff = in.latest - in.entry;
    if (!umul(in.size, diff)) return 0;
    return (in.size * diff) / gfloat();
}

static int64_t wrong_signed(int64_t latest, int64_t entry) { return latest - entry; }

static int64_t wrong_inverse_with(int64_t funding, int64_t size, int (*umul)(int64_t, int64_t)) {
    if (funding < 0 || size <= 0) return 0;
    if (!umul(funding, denom())) return 0;
    return (funding * denom()) / size;
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
    in.size = parse_i64(argv[2]);
    in.latest = parse_i64(argv[3]);
    in.entry = parse_i64(argv[4]);
    return in;
}

static int selftest(void) {
    In mainv = {100000000, 5000123, 4000000};
    In dust = {100, 5000123, 4000000};
    In exact = {100000000, 5000000, 4000000};
    In equal = {100000000, 5000000, 5000000};
    In under = {100000000, 4000000, 5000000};
    In ovf = {7000000000LL, 2000000000LL, 0};
    In zsz = {0, 5000123, 4000000};
    if (amount_with(mainv, 1, umul_ok_i128, uadd_ok_i128) != 100013) return 1;
    if (amount_with(mainv, 0, umul_ok_portable, uadd_ok_portable) != 100012) return 1;
    if (wrong_v1_with(mainv, umul_ok_i128) != 100012300) return 1;
    if (amount_with(dust, 1, umul_ok_i128, uadd_ok_i128) != 1) return 1;
    if (amount_with(dust, 0, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    if (amount_with(exact, 1, umul_ok_i128, uadd_ok_i128) != 100000) return 1;
    if (amount_with(exact, 0, umul_ok_portable, uadd_ok_portable) != 100000) return 1;
    if (amount_with(equal, 1, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    if (inputs_ok_with(under, umul_ok_i128) != 0) return 1;
    if (wrong_signed(4000000, 5000000) != -1000000) return 1;
    if (inputs_ok_with(ovf, umul_ok_i128) != 0) return 1;
    if (inputs_ok_with(ovf, umul_ok_portable) != 0) return 1;
    if (wrap_mul(7000000000LL, 2000000000LL) != -4446744073709551616LL) return 1;
    if (wrong_inverse_with(100012, 100000000, umul_ok_i128) != 1000120) return 1;
    if (amount_with(zsz, 1, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    fputs("PASS\n", stdout);
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    In in;
    int64_t out;
    int (*umul)(int64_t, int64_t);
    int (*uadd)(int64_t, int64_t);
    int round_up;

    if (argc < 2) {
        fputs("usage: gmx_v2_funding_amount_c11 selftest|kind args... [--limbs]\n", stderr);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    kind = argv[1];
    umul = use_portable(argc, argv) ? umul_ok_portable : umul_ok_i128;
    uadd = use_portable(argc, argv) ? uadd_ok_portable : uadd_ok_i128;

    if (strcmp(kind, "wrongsigned") == 0) {
        if (argc < 4) { fputs("need latest entry\n", stderr); return 2; }
        out = wrong_signed(parse_i64(argv[2]), parse_i64(argv[3]));
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "wronginv") == 0) {
        if (argc < 4) { fputs("need funding size\n", stderr); return 2; }
        out = wrong_inverse_with(parse_i64(argv[2]), parse_i64(argv[3]), umul);
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "naivemul") == 0) {
        if (argc < 4) { fputs("need a b\n", stderr); return 2; }
        out = wrap_mul(parse_i64(argv[2]), parse_i64(argv[3]));
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (argc < 5) {
        fputs("need size latest entry\n", stderr);
        return 2;
    }
    in = parse_in(argv);
    if (strcmp(kind, "ok") == 0) out = inputs_ok_with(in, umul);
    else if (strcmp(kind, "charge") == 0) out = amount_with(in, 1, umul, uadd);
    else if (strcmp(kind, "claim") == 0) out = amount_with(in, 0, umul, uadd);
    else if (strcmp(kind, "amount") == 0) {
        if (argc < 6) { fputs("need size latest entry round_up\n", stderr); return 2; }
        round_up = (int)parse_i64(argv[5]);
        out = amount_with(in, round_up, umul, uadd);
    } else if (strcmp(kind, "wrongv1") == 0) out = wrong_v1_with(in, umul);
    else if (strcmp(kind, "wrongapply") == 0) out = wrong_v1_with(in, umul);
    else if (strcmp(kind, "wrongfloor") == 0) out = amount_with(in, 0, umul, uadd);
    else if (strcmp(kind, "wrongceil") == 0) out = amount_with(in, 1, umul, uadd);
    else {
        fprintf(stderr, "unknown kind %s\n", kind);
        return 2;
    }
    printf("%" PRId64 "\n", out);
    return 0;
}
