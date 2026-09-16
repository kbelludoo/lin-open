/*
 * Independent C11 oracle for rust-bitcoin FeeRate sat/MvB conversions.
 *
 * Remainder ceil vs wrapping (n + d - 1) / d. Consensus with Python bigint
 * and LIN Compiler 0 is required before any PASS claim.
 *
 * Upstream: rust-bitcoin/rust-bitcoin units/src/fee_rate/mod.rs (CC0-1.0)
 * This oracle is original C11 and is not linked into the LIN compiler TCB.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MVB 1000000ULL
#define KWU 4000ULL
#define KVB 1000ULL

static uint64_t u32_ok(uint64_t x) { return x <= UINT32_MAX; }

static uint64_t from_sat_per_vb(uint64_t sat_vb) {
    if (!u32_ok(sat_vb)) return 0;
    return sat_vb * MVB;
}

static uint64_t from_sat_per_kwu(uint64_t sat_kwu) {
    if (!u32_ok(sat_kwu)) return 0;
    return sat_kwu * KWU;
}

static uint64_t from_sat_per_kvb(uint64_t sat_kvb) {
    if (!u32_ok(sat_kvb)) return 0;
    return sat_kvb * KVB;
}

static uint64_t div_floor(uint64_t n, uint64_t d) {
    if (d == 0) return 0;
    return n / d;
}

static uint64_t div_ceil_rem(uint64_t n, uint64_t d) {
    uint64_t q, r;
    if (d == 0) return 0;
    q = n / d;
    r = n % d;
    if (r == 0) return q;
    return q + 1;
}

static uint64_t div_ceil_naive_wrap(uint64_t n, uint64_t d) {
    if (d == 0) return 0;
    return (n + d - 1ULL) / d;
}

static int selftest(void) {
    if (from_sat_per_vb(10) != 10000000ULL) return 1;
    if (from_sat_per_kwu(2500) != 10000000ULL) return 2;
    if (from_sat_per_kvb(11) != 11000ULL) return 3;
    if (div_floor(2000400ULL, MVB) != 2ULL) return 4;
    if (div_ceil_rem(2000400ULL, MVB) != 3ULL) return 5;
    if (div_ceil_rem(2000000ULL, MVB) != 2ULL) return 6;
    if (div_floor(2000400ULL, KWU) != 500ULL) return 7;
    if (div_ceil_rem(2000400ULL, KWU) != 501ULL) return 8;
    if (div_floor(2000400ULL, KVB) != 2000ULL) return 9;
    if (div_ceil_rem(2000400ULL, KVB) != 2001ULL) return 10;
    if (div_ceil_rem(0, MVB) != 0) return 11;
    if (from_sat_per_vb(1) != 1000000ULL) return 12;
    if (div_floor(from_sat_per_vb(1), KWU) != 250ULL) return 13;
    if (from_sat_per_vb(3) != 3000000ULL) return 14;
    if (div_floor(from_sat_per_vb(3), KWU) != 750ULL) return 15;
    /* rust u64::div_ceil(MAX, 1e6) == MAX/1e6 + 1; naive add wraps to ~0 */
    if (div_ceil_rem(UINT64_MAX, MVB) != (UINT64_MAX / MVB) + 1ULL) return 16;
    if (div_ceil_naive_wrap(UINT64_MAX, MVB) == div_ceil_rem(UINT64_MAX, MVB))
        return 17;
    return 0;
}

static void usage(void) {
    fprintf(stderr,
            "usage: rust_bitcoin_vbceil_c11 selftest | "
            "from_vb N | from_kwu N | from_kvb N | "
            "vb_floor N | vb_ceil N | kwu_floor N | kwu_ceil N | "
            "kvb_floor N | kvb_ceil N | naive_wrap N D | rem_ceil N D\n");
}

int main(int argc, char **argv) {
    uint64_t n, d;
    int st;
    if (argc < 2) {
        usage();
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        st = selftest();
        if (st != 0) {
            printf("FAIL %d\n", st);
            return 1;
        }
        printf("PASS\n");
        return 0;
    }
    if (argc < 3) {
        usage();
        return 2;
    }
    n = strtoull(argv[2], NULL, 10);
    if (strcmp(argv[1], "from_vb") == 0) {
        printf("%" PRIu64 "\n", from_sat_per_vb(n));
        return 0;
    }
    if (strcmp(argv[1], "from_kwu") == 0) {
        printf("%" PRIu64 "\n", from_sat_per_kwu(n));
        return 0;
    }
    if (strcmp(argv[1], "from_kvb") == 0) {
        printf("%" PRIu64 "\n", from_sat_per_kvb(n));
        return 0;
    }
    if (strcmp(argv[1], "vb_floor") == 0) {
        printf("%" PRIu64 "\n", div_floor(n, MVB));
        return 0;
    }
    if (strcmp(argv[1], "vb_ceil") == 0) {
        printf("%" PRIu64 "\n", div_ceil_rem(n, MVB));
        return 0;
    }
    if (strcmp(argv[1], "kwu_floor") == 0) {
        printf("%" PRIu64 "\n", div_floor(n, KWU));
        return 0;
    }
    if (strcmp(argv[1], "kwu_ceil") == 0) {
        printf("%" PRIu64 "\n", div_ceil_rem(n, KWU));
        return 0;
    }
    if (strcmp(argv[1], "kvb_floor") == 0) {
        printf("%" PRIu64 "\n", div_floor(n, KVB));
        return 0;
    }
    if (strcmp(argv[1], "kvb_ceil") == 0) {
        printf("%" PRIu64 "\n", div_ceil_rem(n, KVB));
        return 0;
    }
    if (argc < 4) {
        usage();
        return 2;
    }
    d = strtoull(argv[3], NULL, 10);
    if (strcmp(argv[1], "naive_wrap") == 0) {
        printf("%" PRIu64 "\n", div_ceil_naive_wrap(n, d));
        return 0;
    }
    if (strcmp(argv[1], "rem_ceil") == 0) {
        printf("%" PRIu64 "\n", div_ceil_rem(n, d));
        return 0;
    }
    usage();
    return 2;
}
