/*
 * Independent C11 oracle for OpenZeppelin Math.log10 / log256 (uint64 scale).
 *
 * Mirrors src/lin_oz_log10.lin: skip 10**64 / 10**32 (do not fit i64),
 * skip >>128 / >>64 (C uint64 shift UB), negatives fail-closed.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: OpenZeppelin Contracts v5.0.2 Math.sol (MIT).
 * This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int ozl_ok(int64_t v) { return v < 0 ? 0 : 1; }

static int64_t ozl_pow10(int64_t n) {
    int64_t p = 1;
    int64_t i;
    if (n < 0 || n > 18) return 0;
    for (i = 0; i < n; i++) p *= 10;
    return p;
}

static int64_t ozl_log10(int64_t v) {
    int64_t result = 0;
    if (v < 0) return 0;
    if (v >= 10000000000000000LL) {
        v /= 10000000000000000LL;
        result += 16;
    }
    if (v >= 100000000LL) {
        v /= 100000000LL;
        result += 8;
    }
    if (v >= 10000LL) {
        v /= 10000LL;
        result += 4;
    }
    if (v >= 100LL) {
        v /= 100LL;
        result += 2;
    }
    if (v >= 10LL) result += 1;
    return result;
}

static int64_t ozl_log10_round(int64_t v, int64_t round_up) {
    int64_t r = ozl_log10(v);
    int64_t p;
    if (!round_up) return r;
    if (v < 0) return 0;
    p = ozl_pow10(r);
    return (p < v) ? r + 1 : r;
}

static int64_t ozl_log256(int64_t v) {
    int64_t result = 0;
    uint64_t u;
    if (v < 0) return 0;
    u = (uint64_t)v;
    if ((u >> 32) > 0) {
        u >>= 32;
        result += 4;
    }
    if ((u >> 16) > 0) {
        u >>= 16;
        result += 2;
    }
    if ((u >> 8) > 0) result += 1;
    return result;
}

static int64_t ozl_log256_round(int64_t v, int64_t round_up) {
    int64_t r = ozl_log256(v);
    int64_t shift;
    uint64_t p;
    if (!round_up) return r;
    if (v < 0) return 0;
    shift = r << 3;
    if (shift >= 63) return r;
    p = 1ULL << (unsigned)shift;
    return (p < (uint64_t)v) ? r + 1 : r;
}

static int64_t ozl_dec_digits(int64_t v) {
    if (v < 0) return 0;
    if (v == 0) return 1;
    return ozl_log10(v) + 1;
}

static int64_t ozl_hex_nbytes(int64_t v) {
    if (v < 0) return 0;
    if (v == 0) return 1;
    return ozl_log256(v) + 1;
}

static int selftest(void) {
    if (ozl_log10(0) != 0) return 1;
    if (ozl_log10(10) != 1) return 2;
    if (ozl_log10(1000000000000000000LL) != 18) return 3;
    if (ozl_log10(9223372036854775807LL) != 18) return 4;
    if (ozl_ok(-1) != 0) return 5;
    if (ozl_pow10(18) != 1000000000000000000LL) return 6;
    if (ozl_pow10(19) != 0) return 7;
    if (ozl_log10_round(11, 1) != 2) return 8;
    if (ozl_log256(256) != 1) return 9;
    if (ozl_log256(4294967296LL) != 4) return 10;
    if (ozl_dec_digits(100000000LL) != 9) return 11;
    if (ozl_hex_nbytes(255) != 1) return 12;
    return 0;
}

int main(int argc, char **argv) {
    const char *op;
    int64_t a, b, out;
    int st;
    if (argc < 2) {
        fprintf(stderr, "usage: oz_log10_c11 selftest|log10|log10r|log256|log256r|pow10|digits|nbytes|ok N [ROUND]\n");
        return 2;
    }
    op = argv[1];
    if (strcmp(op, "selftest") == 0) {
        st = selftest();
        if (st != 0) {
            printf("FAIL %d\n", st);
            return 1;
        }
        printf("PASS\n");
        return 0;
    }
    if (argc < 3) return 2;
    a = (int64_t)strtoll(argv[2], NULL, 10);
    b = (argc > 3) ? (int64_t)strtoll(argv[3], NULL, 10) : 0;
    out = 0;
    if (strcmp(op, "log10") == 0) out = ozl_log10(a);
    else if (strcmp(op, "log10r") == 0) out = ozl_log10_round(a, b);
    else if (strcmp(op, "log256") == 0) out = ozl_log256(a);
    else if (strcmp(op, "log256r") == 0) out = ozl_log256_round(a, b);
    else if (strcmp(op, "pow10") == 0) out = ozl_pow10(a);
    else if (strcmp(op, "digits") == 0) out = ozl_dec_digits(a);
    else if (strcmp(op, "nbytes") == 0) out = ozl_hex_nbytes(a);
    else if (strcmp(op, "ok") == 0) out = ozl_ok(a);
    else return 2;
    printf("%" PRId64 "\n", out);
    return 0;
}
