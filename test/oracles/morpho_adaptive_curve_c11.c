/*
 * Independent C11 oracle for Morpho AdaptiveCurveIRM (signed i64, WAD=1e18).
 *
 * Signed (x*y)/d via GCC/Clang signed __int128, towards zero.
 * Fail-closed if the quotient does not fit in int64.
 * Not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: morpho-org/morpho-blue-irm AdaptiveCurveIrm.sol (MIT).
 * This file is original C11; it does not vendor the Solidity.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WAD 1000000000000000000LL
#define STEEP 4000000000000000000LL
#define TARGET 900000000000000000LL
#define SPEED 1585489599188LL
#define INIT_RATE 1268391679LL
#define MIN_RATE 31709791LL
#define MAX_RATE 63419583967LL
#define LN2 693147180559945309LL

static int64_t fail_fit(__int128 q) {
    if (q > (__int128)INT64_MAX || q < (__int128)INT64_MIN) return 0;
    return (int64_t)q;
}

static int64_t muldiv(int64_t a, int64_t b, int64_t d) {
    __int128 q;
    if (d == 0) return 0;
    q = ((__int128)a * (__int128)b) / (__int128)d;
    return fail_fit(q);
}

static int64_t wmul(int64_t x, int64_t y) { return muldiv(x, y, WAD); }
static int64_t wdiv(int64_t x, int64_t y) {
    if (y == 0) return 0;
    return muldiv(x, WAD, y);
}

static int64_t ac_bound(int64_t x, int64_t lo, int64_t hi) {
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

static int64_t curve(int64_t rate, int64_t err) {
    int64_t coeff;
    if (err < 0)
        coeff = WAD - wdiv(WAD, STEEP);
    else
        coeff = STEEP - WAD;
    return wmul(wmul(coeff, err) + WAD, rate);
}

static int64_t util(int64_t supply, int64_t borrow) {
    if (supply <= 0 || borrow < 0) return 0;
    return muldiv(borrow, WAD, supply);
}

static int64_t err_of(int64_t u) {
    int64_t den = (u > TARGET) ? (WAD - TARGET) : TARGET;
    return wdiv(u - TARGET, den);
}

static int64_t wexp(int64_t x) {
    int64_t half, adj, q, r, rr2, expr;
    if (x < -(LN2 * 8)) return 0;
    half = muldiv(LN2, 1, 2);
    adj = (x < 0) ? -half : half;
    q = muldiv(x + adj, 1, LN2);
    if (q > 3 || q < -3) return 0;
    r = x - muldiv(q, LN2, 1);
    rr2 = muldiv(muldiv(r, r, WAD), 1, 2);
    expr = WAD + r + rr2;
    if (expr <= 0) return 0;
    if (q == 0) return expr;
    if (q > 0) {
        if (expr > (INT64_MAX >> q)) return 0;
        return expr << q;
    }
    return (int64_t)((uint64_t)expr >> (uint64_t)(-q));
}

static int64_t new_rate(int64_t start, int64_t linad) {
    if (start <= 0) return 0;
    return ac_bound(wmul(start, wexp(linad)), MIN_RATE, MAX_RATE);
}

static int64_t avg_rate(int64_t supply, int64_t borrow, int64_t start, int64_t elapsed) {
    int64_t e, speed, linad, end, mid, avg;
    e = err_of(util(supply, borrow));
    if (elapsed < 0) return 0;
    if (start == 0) return curve(INIT_RATE, e);
    speed = wmul(SPEED, e);
    linad = muldiv(speed, elapsed, 1);
    if (linad == 0) return curve(start, e);
    end = new_rate(start, linad);
    mid = new_rate(start, muldiv(linad, 1, 2));
    avg = muldiv(start + end + mid + mid, 1, 4);
    return curve(avg, e);
}

static int64_t end_rate(int64_t supply, int64_t borrow, int64_t start, int64_t elapsed) {
    int64_t e, speed, linad;
    e = err_of(util(supply, borrow));
    if (elapsed < 0) return 0;
    if (start == 0) return INIT_RATE;
    speed = wmul(SPEED, e);
    linad = muldiv(speed, elapsed, 1);
    if (linad == 0) return start;
    return new_rate(start, linad);
}

static int selftest(void) {
    int64_t w = WAD;
    int64_t init = INIT_RATE;
    int64_t supply90 = w + w;
    int64_t borrow90 = w + muldiv(8, w, 10);
    if (muldiv(100, 200, 50) != 400) return 1;
    if (muldiv(7, 9, 2) != 31) return 2;
    if (muldiv(-7, 9, 2) != -31) return 3;
    if (wmul(w, w) != w) return 4;
    if (curve(init, 0) != 1268391679LL) return 5;
    if (curve(init, w) != 5073566716LL) return 6;
    if (curve(init, -w) != 317097919LL) return 7;
    if (err_of(0) != -w) return 8;
    if (err_of(TARGET) != 0) return 9;
    if (err_of(w) != w) return 10;
    if (wexp(0) != w) return 11;
    if (avg_rate(w + w, 0, 0, 0) != 317097919LL) return 12;
    if (avg_rate(w + w, w + w, 0, 0) != 5073566716LL) return 13;
    if (avg_rate(supply90, borrow90, 0, 0) != 1268391679LL) return 14;
    if (end_rate(w + w, w + w, init, 86400) != 1454044805LL) return 15;
    if (avg_rate(w + w, w + w, init, 86400) != 5438922544LL) return 16;
    if (muldiv(3000000000000000000LL, w, 1) != 0) return 17;
    if (wmul(3000000000000000000LL, w) != 3000000000000000000LL) return 18;
    printf("PASS\n");
    return 0;
}

static int64_t arg(int i, char **argv) { return (int64_t)strtoll(argv[i], NULL, 10); }

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: morpho_adaptive_curve_c11 selftest|muldiv|wmul|wdiv|curve|util|err|wexp|newrate|avg|end ...\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRId64 "\n", muldiv(arg(2, argv), arg(3, argv), arg(4, argv)));
        return 0;
    }
    if (strcmp(argv[1], "wmul") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", wmul(arg(2, argv), arg(3, argv)));
        return 0;
    }
    if (strcmp(argv[1], "wdiv") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", wdiv(arg(2, argv), arg(3, argv)));
        return 0;
    }
    if (strcmp(argv[1], "curve") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", curve(arg(2, argv), arg(3, argv)));
        return 0;
    }
    if (strcmp(argv[1], "util") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", util(arg(2, argv), arg(3, argv)));
        return 0;
    }
    if (strcmp(argv[1], "err") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", err_of(arg(2, argv)));
        return 0;
    }
    if (strcmp(argv[1], "wexp") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", wexp(arg(2, argv)));
        return 0;
    }
    if (strcmp(argv[1], "newrate") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", new_rate(arg(2, argv), arg(3, argv)));
        return 0;
    }
    if (strcmp(argv[1], "avg") == 0 && argc >= 6) {
        printf("%" PRId64 "\n", avg_rate(arg(2, argv), arg(3, argv), arg(4, argv), arg(5, argv)));
        return 0;
    }
    if (strcmp(argv[1], "end") == 0 && argc >= 6) {
        printf("%" PRId64 "\n", end_rate(arg(2, argv), arg(3, argv), arg(4, argv), arg(5, argv)));
        return 0;
    }
    return 2;
}
