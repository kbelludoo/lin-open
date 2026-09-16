/*
 * Independent C11 oracle for OpenZeppelin Math.sqrt / log2 (i64-scale).
 *
 * Mirrors src/lin_oz_sqrt.lin: Newton integer square root after a log2
 * initial guess, seven iterations, min(result, a/result).
 *
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: OpenZeppelin Contracts v5.0.2 Math.sol (MIT).
 * This oracle is original C11. uint64 >> 64 and >> 128 are NOT performed:
 * those shifts are well-defined on Solidity uint256 and undefined on
 * C uint64_t / uint64_t-width types.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int64_t ozs_min(int64_t a, int64_t b) { return a < b ? a : b; }

static int ozs_rounds_up(int64_t rounding) {
    int64_t m = rounding - (rounding / 2) * 2;
    return (m == 1 || m == -1) ? 1 : 0;
}

static int64_t ozs_log2(int64_t value) {
    int64_t result = 0;
    uint64_t v;
    if (value <= 0) return 0;
    v = (uint64_t)value;
    if ((v >> 32) > 0) { v >>= 32; result += 32; }
    if ((v >> 16) > 0) { v >>= 16; result += 16; }
    if ((v >> 8) > 0) { v >>= 8; result += 8; }
    if ((v >> 4) > 0) { v >>= 4; result += 4; }
    if ((v >> 2) > 0) { v >>= 2; result += 2; }
    if ((v >> 1) > 0) { result += 1; }
    return result;
}

static int64_t ozs_newton_step(int64_t a, int64_t result) {
    uint64_t ua, ur, t;
    if (result == 0) return 0;
    ua = (uint64_t)a;
    ur = (uint64_t)result;
    t = (ur + (ua / ur)) >> 1;
    return (int64_t)t;
}

static int64_t ozs_sqrt(int64_t a) {
    int64_t lg, result, i;
    if (a <= 0) return 0;
    lg = ozs_log2(a);
    result = (int64_t)(1ULL << (uint64_t)(lg >> 1));
    if (result == 0) return 0;
    for (i = 0; i < 7; i++) result = ozs_newton_step(a, result);
    if (result == 0) return 0;
    return ozs_min(result, a / result);
}

static int ozs_sq_lt(int64_t result, int64_t a) {
    int64_t q, r;
    if (a <= 0) return 0;
    if (result <= 0) return 1;
    q = a / result;
    r = a - (q * result);
    if (q > result) return 1;
    if (q == result && r != 0) return 1;
    return 0;
}

static int64_t ozs_sqrt_round(int64_t a, int64_t rounding) {
    int64_t result = ozs_sqrt(a);
    if (!ozs_rounds_up(rounding)) return result;
    if (!ozs_sq_lt(result, a)) return result;
    return result + 1;
}

static int selftest(void) {
    if (ozs_sqrt(0) != 0) return 1;
    if (ozs_sqrt(1) != 1) return 1;
    if (ozs_sqrt(10) != 3) return 1;
    if (ozs_sqrt(81) != 9) return 1;
    if (ozs_sqrt(82) != 9) return 1;
    if (ozs_log2(1024) != 10) return 1;
    if (ozs_sqrt_round(10, 1) != 4) return 1;
    if (ozs_sqrt_round(9, 1) != 3) return 1;
    if (ozs_sqrt(1000000000000000000LL) != 1000000000LL) return 1;
    if (ozs_sqrt(4611686018427387904LL) != 2147483648LL) return 1;
    if (ozs_sqrt(9223372036854775807LL) != 3037000499LL) return 1;
    if (ozs_rounds_up(0) != 0 || ozs_rounds_up(1) != 1) return 1;
    if (ozs_rounds_up(2) != 0 || ozs_rounds_up(3) != 1) return 1;
    if (ozs_sq_lt(3, 10) != 1 || ozs_sq_lt(3, 9) != 0) return 1;
    return 0;
}

int main(int argc, char **argv) {
    const char *cmd;
    int64_t a, b;
    if (argc < 2) {
        fprintf(stderr, "usage: oz_sqrt_c11 selftest|min|log2|sqrt|sqrt_round|sq_lt args...\n");
        return 2;
    }
    cmd = argv[1];
    if (strcmp(cmd, "selftest") == 0) {
        if (selftest() != 0) {
            puts("FAIL");
            return 1;
        }
        puts("PASS");
        return 0;
    }
    if (strcmp(cmd, "min") == 0 && argc == 4) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        printf("%" PRId64 "\n", ozs_min(a, b));
        return 0;
    }
    if (strcmp(cmd, "log2") == 0 && argc == 3) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        printf("%" PRId64 "\n", ozs_log2(a));
        return 0;
    }
    if (strcmp(cmd, "sqrt") == 0 && argc == 3) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        printf("%" PRId64 "\n", ozs_sqrt(a));
        return 0;
    }
    if (strcmp(cmd, "sqrt_round") == 0 && argc == 4) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        printf("%" PRId64 "\n", ozs_sqrt_round(a, b));
        return 0;
    }
    if (strcmp(cmd, "sq_lt") == 0 && argc == 4) {
        a = (int64_t)strtoll(argv[2], NULL, 10);
        b = (int64_t)strtoll(argv[3], NULL, 10);
        printf("%d\n", ozs_sq_lt(a, b));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
