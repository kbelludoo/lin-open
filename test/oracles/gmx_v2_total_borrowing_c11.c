/*
 * Independent C11 oracle for GMX V2 getNextTotalBorrowing
 * (uint64-scale, unsigned sub-then-add of applyFactor contributions).
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
    int64_t total, ps, pf, ns, nf;
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

static int usub_ok(int64_t a, int64_t b) {
    if (a < 0 || b < 0) return 0;
    return (uint64_t)a >= (uint64_t)b;
}

static int64_t wrap_mul(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a * (uint64_t)b);
}

static int64_t wrap_add(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a + (uint64_t)b);
}

static int64_t gfloat(void) { return 1000000; }

static int64_t apply_with(int64_t value, int64_t factor, int (*umul)(int64_t, int64_t)) {
    if (value < 0 || factor < 0) return 0;
    if (!umul(value, factor)) return 0;
    return (value * factor) / gfloat();
}

static int inputs_ok_with(In in, int (*umul)(int64_t, int64_t), int (*uadd)(int64_t, int64_t)) {
    int64_t pc, nc, mid;
    if (in.total < 0 || in.ps < 0 || in.pf < 0 || in.ns < 0 || in.nf < 0) return 0;
    if (!umul(in.ps, in.pf) || !umul(in.ns, in.nf)) return 0;
    pc = apply_with(in.ps, in.pf, umul);
    nc = apply_with(in.ns, in.nf, umul);
    if (!usub_ok(in.total, pc)) return 0;
    mid = in.total - pc;
    if (!uadd(mid, nc)) return 0;
    return 1;
}

static int64_t next_with(In in, int (*umul)(int64_t, int64_t), int (*uadd)(int64_t, int64_t)) {
    int64_t pc, nc;
    if (!inputs_ok_with(in, umul, uadd)) return 0;
    pc = apply_with(in.ps, in.pf, umul);
    nc = apply_with(in.ns, in.nf, umul);
    return (in.total - pc) + nc;
}

static int64_t wrong_fused_with(In in, int (*umul)(int64_t, int64_t)) {
    int64_t pc, nc;
    if (in.ps < 0 || in.pf < 0 || in.ns < 0 || in.nf < 0) return 0;
    if (!umul(in.ps, in.pf) || !umul(in.ns, in.nf)) return 0;
    pc = apply_with(in.ps, in.pf, umul);
    nc = apply_with(in.ns, in.nf, umul);
    return (in.total - pc) + nc;
}

static int64_t wrong_muldiv_with(In in, int (*umul)(int64_t, int64_t), int (*uadd)(int64_t, int64_t)) {
    int64_t pp, np, d;
    if (in.total < 0 || in.ps < 0 || in.pf < 0 || in.ns < 0 || in.nf < 0) return 0;
    if (!umul(in.ps, in.pf) || !umul(in.ns, in.nf)) return 0;
    pp = in.ps * in.pf;
    np = in.ns * in.nf;
    if ((uint64_t)np < (uint64_t)pp) {
        d = (pp - np) / gfloat();
        if (!usub_ok(in.total, d)) return 0;
        return in.total - d;
    }
    d = (np - pp) / gfloat();
    if (!uadd(in.total, d)) return 0;
    return in.total + d;
}

static int64_t wrong_size_with(In in, int (*umul)(int64_t, int64_t), int (*uadd)(int64_t, int64_t)) {
    int64_t c;
    if (in.pf < 0) return 0;
    if (!usub_ok(in.ns, in.ps)) return 0;
    c = apply_with(in.ns - in.ps, in.nf, umul);
    if (!uadd(in.total, c)) return 0;
    return in.total + c;
}

static int64_t wrong_fee_with(int64_t size, int64_t pf, int64_t nf, int (*umul)(int64_t, int64_t)) {
    if (!usub_ok(nf, pf)) return 0;
    return apply_with(size, nf - pf, umul);
}

static int64_t wrong_pending_with(int64_t oi, int64_t cum, int64_t total, int (*umul)(int64_t, int64_t)) {
    int64_t a = apply_with(oi, cum, umul);
    if (!usub_ok(a, total)) return 0;
    return a - total;
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
    in.total = parse_i64(argv[2]);
    in.ps = parse_i64(argv[3]);
    in.pf = parse_i64(argv[4]);
    in.ns = parse_i64(argv[5]);
    in.nf = parse_i64(argv[6]);
    return in;
}

static int selftest(void) {
    In mainv = {100000000, 50000000, 400000, 50000000, 500000};
    In under = {10000000, 50000000, 400000, 50000000, 500000};
    In sized = {100000000, 50000000, 400000, 80000000, 500000};
    In rem = {10, 3, 400000, 3, 700000};
    In openp = {100000000, 0, 0, 50000000, 500000};
    In closep = {100000000, 50000000, 400000, 0, 0};
    In equal = {20000000, 50000000, 400000, 50000000, 500000};
    In zclose = {0, 50000000, 400000, 0, 0};
    In ovf = {1, 7000000000LL, 2000000000LL, 0, 0};
    In addo = {9223372036850000000LL, 0, 0, 5000000, 1000000};
    In first = {0, 0, 0, 50000000, 500000};
    if (next_with(mainv, umul_ok_i128, uadd_ok_i128) != 105000000) return 1;
    if (wrong_fused_with(under, umul_ok_i128) != 15000000) return 1;
    if (inputs_ok_with(under, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    if (wrong_fee_with(50000000, 400000, 500000, umul_ok_i128) != 5000000) return 1;
    if (wrong_pending_with(200000000, 600000, 100000000, umul_ok_i128) != 20000000) return 1;
    if (next_with(sized, umul_ok_i128, uadd_ok_i128) != 120000000) return 1;
    if (wrong_size_with(sized, umul_ok_i128, uadd_ok_i128) != 115000000) return 1;
    if (next_with(rem, umul_ok_i128, uadd_ok_i128) != 11) return 1;
    if (wrong_muldiv_with(rem, umul_ok_portable, uadd_ok_portable) != 10) return 1;
    if (next_with(openp, umul_ok_i128, uadd_ok_i128) != 125000000) return 1;
    if (next_with(closep, umul_ok_i128, uadd_ok_i128) != 80000000) return 1;
    if (next_with(equal, umul_ok_i128, uadd_ok_i128) != 25000000) return 1;
    if (inputs_ok_with(zclose, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    if (inputs_ok_with(ovf, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    if (inputs_ok_with(ovf, umul_ok_portable, uadd_ok_portable) != 0) return 1;
    if (wrap_mul(7000000000LL, 2000000000LL) != -4446744073709551616LL) return 1;
    if (inputs_ok_with(addo, umul_ok_i128, uadd_ok_i128) != 0) return 1;
    if (wrap_add(9223372036850000000LL, 5000000LL) != -9223372036854551616LL) return 1;
    if (inputs_ok_with(mainv, umul_ok_i128, uadd_ok_i128) != 1) return 1;
    if (next_with(first, umul_ok_i128, uadd_ok_i128) != 25000000) return 1;
    if (wrong_fused_with(mainv, umul_ok_i128) != 105000000) return 1;
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
        fputs("usage: gmx_v2_total_borrowing_c11 selftest|kind args... [--limbs]\n", stderr);
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
    if (strcmp(kind, "wrongfee") == 0) {
        if (argc < 5) { fputs("need size pf nf\n", stderr); return 2; }
        out = wrong_fee_with(parse_i64(argv[2]), parse_i64(argv[3]), parse_i64(argv[4]), umul);
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "wrongpending") == 0) {
        if (argc < 5) { fputs("need oi cum total\n", stderr); return 2; }
        out = wrong_pending_with(parse_i64(argv[2]), parse_i64(argv[3]), parse_i64(argv[4]), umul);
        printf("%" PRId64 "\n", out);
        return 0;
    }
    if (argc < 7) {
        fputs("need total ps pf ns nf\n", stderr);
        return 2;
    }
    in = parse_in(argv);
    if (strcmp(kind, "ok") == 0) out = inputs_ok_with(in, umul, uadd);
    else if (strcmp(kind, "next") == 0) out = next_with(in, umul, uadd);
    else if (strcmp(kind, "wrongfused") == 0) out = wrong_fused_with(in, umul);
    else if (strcmp(kind, "wrongmuldiv") == 0) out = wrong_muldiv_with(in, umul, uadd);
    else if (strcmp(kind, "wrongsize") == 0) out = wrong_size_with(in, umul, uadd);
    else {
        fprintf(stderr, "unknown kind %s\n", kind);
        return 2;
    }
    printf("%" PRId64 "\n", out);
    return 0;
}
