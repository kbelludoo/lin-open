/*
 * Independent C11 oracle for OpenZeppelin Math v5.0.2 (uint64 / i64 scale).
 *
 * Implements the published ceilDiv / average / max / min / try* formulas
 * with unsigned 64-bit arithmetic plus a signed-i64 naive average that
 * demonstrates wrap. Not linked into the LIN compiler TCB.
 *
 * Upstream: OpenZeppelin/openzeppelin-contracts contracts/utils/math/Math.sol
 * License of the algorithm: MIT. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX 9223372036854775807LL
#define HALF62 4611686018427387904LL

static int nn(int64_t a) { return a >= 0; }

static int add_ok(int64_t a, int64_t b) {
    int64_t s;
    if (!nn(a) || !nn(b)) return 0;
    s = (int64_t)((uint64_t)a + (uint64_t)b);
    if (s < 0) return 0;
    if ((uint64_t)s < (uint64_t)a) return 0;
    return 1;
}

static int64_t addv(int64_t a, int64_t b) {
    if (!add_ok(a, b)) return 0;
    return a + b;
}

static int sub_ok(int64_t a, int64_t b) {
    if (!nn(a) || !nn(b)) return 0;
    if (b > a) return 0;
    return 1;
}

static int64_t subv(int64_t a, int64_t b) {
    if (!sub_ok(a, b)) return 0;
    return a - b;
}

static int mul_ok(int64_t a, int64_t b) {
    if (!nn(a) || !nn(b)) return 0;
    if (a == 0 || b == 0) return 1;
    if (b > I64MAX / a) return 0;
    return 1;
}

static int64_t mulv(int64_t a, int64_t b) {
    if (!mul_ok(a, b)) return 0;
    return a * b;
}

static int div_ok(int64_t a, int64_t b) {
    if (!nn(a) || b <= 0) return 0;
    return 1;
}

static int64_t divv(int64_t a, int64_t b) {
    if (!div_ok(a, b)) return 0;
    return a / b;
}

static int64_t modv(int64_t a, int64_t b) {
    if (!div_ok(a, b)) return 0;
    return a % b;
}

static int64_t maxv(int64_t a, int64_t b) {
    if (!nn(a) || !nn(b)) return 0;
    return a > b ? a : b;
}

static int64_t minv(int64_t a, int64_t b) {
    if (!nn(a) || !nn(b)) return 0;
    return a < b ? a : b;
}

/* OZ: (a & b) + (a ^ b) / 2  — bitwise, no add overflow. */
static int64_t average(int64_t a, int64_t b) {
    if (!nn(a) || !nn(b)) return 0;
    return (a & b) + ((a ^ b) / 2);
}

/* Signed i64 wrap of (a+b)/2 — the overflow OZ documents for uint256 add. */
static int64_t naive_avg(int64_t a, int64_t b) {
    int64_t s = (int64_t)((uint64_t)a + (uint64_t)b);
    return s / 2;
}

/* OZ: a==0 ? 0 : (a-1)/b + 1.  b==0 panics in Solidity; here fail-closed 0. */
static int64_t ceil_div(int64_t a, int64_t b) {
    if (!nn(a) || b <= 0) return 0;
    if (a == 0) return 0;
    return ((a - 1) / b) + 1;
}

/* Naive (a+b-1)/b with defined i64 wrap — overflows where OZ distributes. */
static int64_t naive_ceil(int64_t a, int64_t b) {
    int64_t s;
    if (b == 0) return 0;
    s = (int64_t)((uint64_t)a + (uint64_t)b - 1u);
    return s / b;
}

static int selftest(void) {
    if (ceil_div(0, 1) != 0) return 1;
    if (ceil_div(1, 2) != 1) return 2;
    if (ceil_div(3, 2) != 2) return 3;
    if (ceil_div(10, 3) != 4) return 4;
    if (ceil_div(1000, 3) != 334) return 5;
    if (average(3, 5) != 4) return 6;
    if (average(HALF62, HALF62) != HALF62) return 7;
    if (naive_avg(HALF62, HALF62) == HALF62) return 8;
    if (add_ok(HALF62, HALF62) != 0) return 9;
    if (maxv(3, 9) != 9 || minv(3, 9) != 3) return 10;
    if (mulv(7, 9) != 63) return 11;
    if (divv(10, 3) != 3 || modv(10, 3) != 1) return 12;
    if (ceil_div(I64MAX, 2) != HALF62) return 13;
    if (naive_ceil(I64MAX, 2) == ceil_div(I64MAX, 2)) return 14;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    int64_t a, b;
    if (argc < 2) {
        fprintf(stderr, "usage: oz_math_c11 selftest | ceil a b | avg a b | ...\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (argc < 4) return 2;
    a = (int64_t)strtoll(argv[2], NULL, 10);
    b = (int64_t)strtoll(argv[3], NULL, 10);
    if (strcmp(argv[1], "ceil") == 0) printf("%" PRId64 "\n", ceil_div(a, b));
    else if (strcmp(argv[1], "ceil_ok") == 0) printf("%d\n", nn(a) && b > 0);
    else if (strcmp(argv[1], "avg") == 0) printf("%" PRId64 "\n", average(a, b));
    else if (strcmp(argv[1], "naive_avg") == 0) printf("%" PRId64 "\n", naive_avg(a, b));
    else if (strcmp(argv[1], "naive_ceil") == 0) printf("%" PRId64 "\n", naive_ceil(a, b));
    else if (strcmp(argv[1], "max") == 0) printf("%" PRId64 "\n", maxv(a, b));
    else if (strcmp(argv[1], "min") == 0) printf("%" PRId64 "\n", minv(a, b));
    else if (strcmp(argv[1], "add") == 0) printf("%" PRId64 "\n", addv(a, b));
    else if (strcmp(argv[1], "add_ok") == 0) printf("%d\n", add_ok(a, b));
    else if (strcmp(argv[1], "sub") == 0) printf("%" PRId64 "\n", subv(a, b));
    else if (strcmp(argv[1], "sub_ok") == 0) printf("%d\n", sub_ok(a, b));
    else if (strcmp(argv[1], "mul") == 0) printf("%" PRId64 "\n", mulv(a, b));
    else if (strcmp(argv[1], "mul_ok") == 0) printf("%d\n", mul_ok(a, b));
    else if (strcmp(argv[1], "div") == 0) printf("%" PRId64 "\n", divv(a, b));
    else if (strcmp(argv[1], "div_ok") == 0) printf("%d\n", div_ok(a, b));
    else if (strcmp(argv[1], "mod") == 0) printf("%" PRId64 "\n", modv(a, b));
    else {
        fprintf(stderr, "unknown op %s\n", argv[1]);
        return 2;
    }
    return 0;
}
