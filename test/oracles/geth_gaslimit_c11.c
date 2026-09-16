/*
 * Independent C11 oracle for go-ethereum v1.14.12 CalcGasLimit / VerifyGaslimit.
 *
 * Two semantics:
 *   geth  — uint64 wrap on (parent/divisor)-1 and int64 casts on VerifyGaslimit
 *   lin   — fail-closed when that wrap would fire, unsigned abs, reject negatives
 *
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: ethereum/go-ethereum LGPL-3.0
 *   core/block_validator.go CalcGasLimit
 *   consensus/misc/gaslimit.go VerifyGaslimit
 * This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define GL_DIVISOR 1024ULL
#define GL_MIN 5000ULL

static uint64_t geth_calc(uint64_t parent, uint64_t desired) {
    uint64_t delta = parent / GL_DIVISOR - 1ULL;
    uint64_t limit = parent;
    if (desired < GL_MIN) {
        desired = GL_MIN;
    }
    if (limit < desired) {
        limit = parent + delta;
        if (limit > desired) {
            limit = desired;
        }
        return limit;
    }
    if (limit > desired) {
        limit = parent - delta;
        if (limit < desired) {
            limit = desired;
        }
    }
    return limit;
}

static int geth_verify(uint64_t parent, uint64_t header) {
    int64_t diff = (int64_t)parent - (int64_t)header;
    uint64_t bound;
    if (diff < 0) {
        diff = -diff;
    }
    bound = parent / GL_DIVISOR;
    if ((uint64_t)diff >= bound) {
        return 0;
    }
    if (header < GL_MIN) {
        return 0;
    }
    return 1;
}

static int lin_neg(int64_t x) { return x < 0; }

static uint64_t lin_abs_diff(uint64_t a, uint64_t b) {
    return (a >= b) ? (a - b) : (b - a);
}

static int lin_delta_ok(int64_t parent, int64_t divisor) {
    int64_t q;
    if (divisor <= 0 || lin_neg(parent)) {
        return 0;
    }
    q = parent / divisor;
    return q != 0;
}

static int64_t lin_delta(int64_t parent, int64_t divisor) {
    int64_t q;
    if (!lin_delta_ok(parent, divisor)) {
        return 0;
    }
    q = parent / divisor;
    return q - 1;
}

static int lin_add_ok(int64_t a, int64_t b) {
    int64_t s;
    if (lin_neg(a) || lin_neg(b)) {
        return 0;
    }
    s = a + b;
    return s >= a;
}

static int lin_calc_ok(int64_t parent, int64_t desired, int64_t divisor, int64_t min_limit) {
    int64_t delta;
    if (lin_neg(parent) || lin_neg(desired) || lin_neg(min_limit)) {
        return 0;
    }
    if (!lin_delta_ok(parent, divisor)) {
        return 0;
    }
    delta = lin_delta(parent, divisor);
    return lin_add_ok(parent, delta);
}

static int64_t lin_calc(int64_t parent, int64_t desired, int64_t divisor, int64_t min_limit) {
    int64_t d, delta, limit;
    if (!lin_calc_ok(parent, desired, divisor, min_limit)) {
        return 0;
    }
    d = desired;
    if (d < min_limit) {
        d = min_limit;
    }
    delta = lin_delta(parent, divisor);
    if (parent < d) {
        limit = parent + delta;
        return (limit > d) ? d : limit;
    }
    if (parent > d) {
        limit = parent - delta;
        return (limit < d) ? d : limit;
    }
    return parent;
}

static int lin_verify(int64_t parent, int64_t header, int64_t divisor, int64_t min_limit) {
    int64_t bound;
    uint64_t diff;
    if (lin_neg(parent) || lin_neg(header) || divisor <= 0) {
        return 0;
    }
    if (header < min_limit) {
        return 0;
    }
    bound = parent / divisor;
    diff = lin_abs_diff((uint64_t)parent, (uint64_t)header);
    if (diff >= (uint64_t)bound) {
        return 0;
    }
    return 1;
}

static int selftest(void) {
    if (geth_calc(20000000ULL, 40000000ULL) != 20019530ULL) return 1;
    if (geth_calc(20000000ULL, 0ULL) != 19980470ULL) return 1;
    if (geth_calc(20000000ULL, 19999999ULL) != 19999999ULL) return 1;
    if (geth_calc(20000000ULL, 20000001ULL) != 20000001ULL) return 1;
    if (geth_calc(20000000ULL, 20000000ULL) != 20000000ULL) return 1;
    if (geth_calc(40000000ULL, 80000000ULL) != 40039061ULL) return 1;
    if (geth_calc(40000000ULL, 0ULL) != 39960939ULL) return 1;
    if (lin_calc(20000000, 40000000, 1024, 5000) != 20019530) return 1;
    if (lin_calc(20000000, 0, 1024, 5000) != 19980470) return 1;
    if (lin_verify(20000000, 20019530, 1024, 5000) != 1) return 1;
    if (lin_verify(20000000, 20019531, 1024, 5000) != 0) return 1;
    if (lin_verify(20000000, 4999, 1024, 5000) != 0) return 1;
    if (lin_calc_ok(500, 5000, 1024, 5000) != 0) return 1;
    if (lin_calc(500, 5000, 1024, 5000) != 0) return 1;
    if (geth_calc(500ULL, 5000ULL) == 0ULL) return 1;
    printf("PASS selftest\n");
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: geth_gaslimit_c11 selftest|calc|verify|lin_calc|lin_verify|lin_ok|delta ...\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        return selftest();
    }
    if (strcmp(argv[1], "calc") == 0 && argc == 4) {
        uint64_t p = strtoull(argv[2], NULL, 0);
        uint64_t d = strtoull(argv[3], NULL, 0);
        printf("value=%" PRIu64 "\n", geth_calc(p, d));
        return 0;
    }
    if (strcmp(argv[1], "verify") == 0 && argc == 4) {
        uint64_t p = strtoull(argv[2], NULL, 0);
        uint64_t h = strtoull(argv[3], NULL, 0);
        printf("value=%d\n", geth_verify(p, h));
        return 0;
    }
    if (strcmp(argv[1], "lin_calc") == 0 && argc == 6) {
        int64_t p = (int64_t)strtoll(argv[2], NULL, 0);
        int64_t d = (int64_t)strtoll(argv[3], NULL, 0);
        int64_t div = (int64_t)strtoll(argv[4], NULL, 0);
        int64_t mn = (int64_t)strtoll(argv[5], NULL, 0);
        printf("value=%" PRId64 "\n", lin_calc(p, d, div, mn));
        return 0;
    }
    if (strcmp(argv[1], "lin_ok") == 0 && argc == 6) {
        int64_t p = (int64_t)strtoll(argv[2], NULL, 0);
        int64_t d = (int64_t)strtoll(argv[3], NULL, 0);
        int64_t div = (int64_t)strtoll(argv[4], NULL, 0);
        int64_t mn = (int64_t)strtoll(argv[5], NULL, 0);
        printf("value=%d\n", lin_calc_ok(p, d, div, mn));
        return 0;
    }
    if (strcmp(argv[1], "lin_verify") == 0 && argc == 6) {
        int64_t p = (int64_t)strtoll(argv[2], NULL, 0);
        int64_t h = (int64_t)strtoll(argv[3], NULL, 0);
        int64_t div = (int64_t)strtoll(argv[4], NULL, 0);
        int64_t mn = (int64_t)strtoll(argv[5], NULL, 0);
        printf("value=%d\n", lin_verify(p, h, div, mn));
        return 0;
    }
    if (strcmp(argv[1], "delta") == 0 && argc == 4) {
        int64_t p = (int64_t)strtoll(argv[2], NULL, 0);
        int64_t div = (int64_t)strtoll(argv[3], NULL, 0);
        printf("value=%" PRId64 "\n", lin_delta(p, div));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
