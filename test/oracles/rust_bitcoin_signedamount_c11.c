/*
 * Independent C11 oracle for rust-bitcoin SignedAmount (CC0-1.0) plus
 * Bitcoin Core MoneyRange (MIT). Not linked into the LIN compiler TCB.
 *
 * Two implementations of |a|*|b|:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_rust_bitcoin_signedamount.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 *
 * Honest divergence: rust-bitcoin SignedAmount range is [-MAX, MAX];
 * Bitcoin Core MoneyRange is [0, MAX]. Negative one sat is valid in
 * rust-bitcoin and invalid in Core consensus.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define COIN ((int64_t)100000000)
#define MAX_MONEY ((int64_t)21000000 * COIN)
#define MIN_MONEY (-MAX_MONEY)

static int in_range(int64_t sat) {
    return sat <= MAX_MONEY && sat >= MIN_MONEY;
}

static int core_money_range(int64_t sat) {
    return sat >= 0 && sat <= MAX_MONEY;
}

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void umul_limbs(uint64_t a, uint64_t b, uint64_t *hi_out, uint64_t *lo_out) {
    uint64_t a0 = a & 0xffffffffULL, a1 = a >> 32;
    uint64_t b0 = b & 0xffffffffULL, b1 = b >> 32;
    uint64_t p0 = a0 * b0, p1 = a0 * b1, p2 = a1 * b0, p3 = a1 * b1;
    uint64_t mid = p1 + p2;
    uint64_t mid_carry = (mid < p1) ? 1 : 0;
    uint64_t t = (mid & 0xffffffffULL) << 32;
    uint64_t lo = p0 + t;
    uint64_t lo_carry = (lo < p0) ? 1 : 0;
    uint64_t hi = p3 + (mid >> 32);
    hi = hi + (mid_carry << 32);
    hi = hi + lo_carry;
    *hi_out = hi;
    *lo_out = lo;
}

static int mul_ok_i128(int64_t a, int64_t b, int64_t *out) {
    uint64_t ua, ub, lo;
    __uint128_t p;
    int64_t mag, s;
    int neg;
    if (!in_range(a)) return 0;
    ua = (a < 0) ? (uint64_t)(-a) : (uint64_t)a;
    ub = (b < 0) ? (uint64_t)(-b) : (uint64_t)b;
    p = (__uint128_t)ua * (__uint128_t)ub;
    if (p > (unsigned __int128)(uint64_t)MAX_MONEY) return 0;
    lo = (uint64_t)p;
    mag = (int64_t)lo;
    neg = ((a < 0) && (b >= 0)) || ((a >= 0) && (b < 0));
    s = neg ? -mag : mag;
    if (!in_range(s)) return 0;
    *out = s;
    return 1;
}

static int mul_ok_limbs(int64_t a, int64_t b, int64_t *out) {
    uint64_t ua, ub, hi, lo;
    int64_t mag, s;
    int neg;
    if (!in_range(a)) return 0;
    ua = (a < 0) ? (uint64_t)(-a) : (uint64_t)a;
    ub = (b < 0) ? (uint64_t)(-b) : (uint64_t)b;
    umul_limbs(ua, ub, &hi, &lo);
    if (hi != 0) return 0;
    if (u_lt((uint64_t)MAX_MONEY, lo)) return 0;
    mag = (int64_t)lo;
    neg = ((a < 0) && (b >= 0)) || ((a >= 0) && (b < 0));
    s = neg ? -mag : mag;
    if (!in_range(s)) return 0;
    *out = s;
    return 1;
}

static void die(const char *msg) {
    fprintf(stderr, "oracle: %s\n", msg);
    exit(2);
}

int main(int argc, char **argv) {
    int64_t a, b, s, s128, slimb;
    int ok128, oklimb;
    if (argc < 2) die("usage");
    if (strcmp(argv[1], "max") == 0) {
        printf("%" PRId64 "\n", MAX_MONEY);
        return 0;
    }
    if (strcmp(argv[1], "min") == 0) {
        printf("%" PRId64 "\n", MIN_MONEY);
        return 0;
    }
    if (strcmp(argv[1], "coin") == 0) {
        printf("%" PRId64 "\n", COIN);
        return 0;
    }
    if (strcmp(argv[1], "from_sat_ok") == 0 && argc == 3) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        printf("%d\n", in_range(a));
        return 0;
    }
    if (strcmp(argv[1], "core_range") == 0 && argc == 3) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        printf("%d\n", core_money_range(a));
        return 0;
    }
    if (strcmp(argv[1], "add") == 0 && argc == 4) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        if (!in_range(a) || !in_range(b) || !in_range(a + b)) {
            printf("0 0\n");
            return 0;
        }
        printf("1 %" PRId64 "\n", a + b);
        return 0;
    }
    if (strcmp(argv[1], "sub") == 0 && argc == 4) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        if (!in_range(a) || !in_range(b) || !in_range(a - b)) {
            printf("0 0\n");
            return 0;
        }
        printf("1 %" PRId64 "\n", a - b);
        return 0;
    }
    if (strcmp(argv[1], "mul") == 0 && argc == 4) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        ok128 = mul_ok_i128(a, b, &s128);
        oklimb = mul_ok_limbs(a, b, &slimb);
        if (ok128 != oklimb) die("i128/limbs ok mismatch");
        if (ok128 && s128 != slimb) die("i128/limbs value mismatch");
        if (!ok128) {
            printf("0 0\n");
            return 0;
        }
        printf("1 %" PRId64 "\n", s128);
        return 0;
    }
    if (strcmp(argv[1], "abs") == 0 && argc == 3) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        if (!in_range(a)) {
            printf("0\n");
            return 0;
        }
        s = (a < 0) ? -a : a;
        printf("%" PRId64 "\n", s);
        return 0;
    }
    if (strcmp(argv[1], "i64_wrap_mul") == 0 && argc == 4) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        /* defined wrap: uint64 product, bitcast back. signed i64 * is UB on overflow */
        printf("%" PRId64 "\n", (int64_t)((uint64_t)a * (uint64_t)b));
        return 0;
    }
    die("unknown command");
    return 2;
}
