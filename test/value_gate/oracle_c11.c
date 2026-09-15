/* Independent C11 oracles for the LIN value gate.
 *
 * Not linked into the LIN runtime. Built only by
 * test/prove_value_vs_established.py via `cc -std=c11`.
 *
 * Kernels:
 *   qoi         — phoboslab/qoi color index hash
 *   fac         — codeplea/tinyexpr integer factorial, LIN sentinels
 *   amount_out  — UniswapV2Library.getAmountOut (uint64 domain only)
 *
 * Usage: oracle_c11 <kernel> <ints...>
 * Prints a single decimal integer and exits 0.
 */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int64_t parse_i64(const char *s) {
    char *end = NULL;
    long long v = strtoll(s, &end, 10);
    if (end == s || *end != '\0') {
        fprintf(stderr, "oracle_c11: bad integer %s\n", s);
        exit(2);
    }
    return (int64_t)v;
}

static int64_t qoi_color_hash(int64_t r, int64_t g, int64_t b, int64_t a) {
    return ((r * 3) + (g * 5) + (b * 7) + (a * 11)) & 63;
}

static int64_t tinyexpr_fac(int64_t n) {
    if (n < 0) {
        return -9002;
    }
    if (n > 20) {
        return -9003;
    }
    int64_t acc = 1;
    for (int64_t i = 2; i <= n; i++) {
        acc *= i;
    }
    return acc;
}

static int64_t uniswap_amount_out(int64_t amount_in, int64_t reserve_in,
                                  int64_t reserve_out) {
    if (amount_in <= 0 || reserve_in <= 0 || reserve_out <= 0) {
        return 0;
    }
    uint64_t ain = (uint64_t)amount_in;
    uint64_t rin = (uint64_t)reserve_in;
    uint64_t rout = (uint64_t)reserve_out;
    uint64_t in_fee = ain * 997ULL;
    uint64_t num = in_fee * rout;
    uint64_t den = rin * 1000ULL + in_fee;
    if (den == 0) {
        return 0;
    }
    return (int64_t)(num / den);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: oracle_c11 qoi|fac|amount_out ...\n");
        return 2;
    }
    if (strcmp(argv[1], "qoi") == 0) {
        if (argc != 6) {
            fprintf(stderr, "usage: oracle_c11 qoi r g b a\n");
            return 2;
        }
        printf("%" PRId64 "\n",
               qoi_color_hash(parse_i64(argv[2]), parse_i64(argv[3]),
                              parse_i64(argv[4]), parse_i64(argv[5])));
        return 0;
    }
    if (strcmp(argv[1], "fac") == 0) {
        if (argc != 3) {
            fprintf(stderr, "usage: oracle_c11 fac n\n");
            return 2;
        }
        printf("%" PRId64 "\n", tinyexpr_fac(parse_i64(argv[2])));
        return 0;
    }
    if (strcmp(argv[1], "amount_out") == 0) {
        if (argc != 5) {
            fprintf(stderr, "usage: oracle_c11 amount_out ain rin rout\n");
            return 2;
        }
        printf("%" PRId64 "\n",
               uniswap_amount_out(parse_i64(argv[2]), parse_i64(argv[3]),
                                  parse_i64(argv[4])));
        return 0;
    }
    fprintf(stderr, "oracle_c11: unknown kernel %s\n", argv[1]);
    return 2;
}
