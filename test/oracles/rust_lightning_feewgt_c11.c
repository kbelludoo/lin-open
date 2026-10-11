/*
 * Independent C11 oracle for rust-lightning v0.2.7 fee_for_weight.
 *
 * Two implementations:
 *   1. LDK wrapping uint64 path: ((feerate * weight) + 1000 - 1) / 1000
 *      (the published v0.2.7 formula; * and + wrap).
 *   2. LIN fail-closed i64: remainder ceil, reject weight<=0 / negatives /
 *      feerate > u32::MAX / product overflow.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: lightningdevkit/rust-lightning v0.2.7
 *   lightning/src/chain/chaininterface.rs
 * License of the algorithm: Apache-2.0 OR MIT. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    KW = 1000,
    FLOOR = 253
};

#define U32_MAX 4294967295LL
#define I64_MAX 9223372036854775807LL

static int prod_ok(int64_t a, int64_t b) {
    if (a < 0 || b < 0)
        return 0;
    if (a == 0 || b == 0)
        return 1;
    return b <= (I64_MAX / a);
}

static int64_t ceil_div(int64_t num, int64_t den) {
    int64_t q, r;
    if (den <= 0 || num < 0)
        return 0;
    q = num / den;
    r = num - q * den;
    return r == 0 ? q : q + 1;
}

static int64_t lin_fee(int64_t feerate, int64_t weight) {
    if (feerate < 0 || feerate > U32_MAX || weight <= 0)
        return 0;
    if (!prod_ok(feerate, weight))
        return 0;
    return ceil_div(feerate * weight, KW);
}

static int64_t lin_feerate(int64_t fee_sat, int64_t weight) {
    int64_t q;
    if (fee_sat < 0 || weight <= 0)
        return 0;
    if (!prod_ok(fee_sat, KW))
        return U32_MAX;
    q = (fee_sat * KW) / weight;
    return q > U32_MAX ? U32_MAX : q;
}

static int64_t lin_bounded(int64_t est) {
    if (est < 0 || est > U32_MAX)
        return 0;
    return est < FLOOR ? FLOOR : est;
}

/* Published LDK v0.2.7 wrapping formula. weight==0 is UB in Rust (panic). */
static uint64_t rust_fee(uint64_t feerate, uint64_t weight) {
    return (feerate * weight + 1000u - 1u) / 1000u;
}

static uint32_t rust_feerate(uint64_t fee_sat, uint64_t weight) {
    uint64_t q = (fee_sat * 1000u) / weight;
    return q > (uint64_t)UINT32_MAX ? UINT32_MAX : (uint32_t)q;
}

static int selftest(void) {
    if (lin_fee(253, 1000) != 253)
        return 1;
    if (lin_fee(253, 1) != 1)
        return 2;
    if (lin_fee(1, 1001) != 2)
        return 3;
    if (lin_fee(250, 400) != 100)
        return 4;
    if (lin_fee(253, 440) != 112)
        return 5;
    if (lin_fee(253, 724) != 184)
        return 6;
    if (lin_fee(253, 0) != 0)
        return 7;
    if (lin_fee(4294967295LL, 2147483649LL) != 0)
        return 8;
    if (lin_feerate(5000000000LL, 1) != U32_MAX)
        return 9;
    if (lin_bounded(100) != 253 || lin_bounded(1000) != 1000)
        return 10;
    if (rust_fee(253, 440) != 112)
        return 11;
    if (rust_fee(1, 1001) != 2)
        return 12;
    return 0;
}

int main(int argc, char **argv) {
    int rc;
    if (argc < 2) {
        fprintf(stderr,
                "usage: rust_lightning_feewgt_c11 selftest|fee r w|"
                "feerate f w|bounded e|rust-fee r w\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        rc = selftest();
        if (rc == 0) {
            puts("PASS");
            return 0;
        }
        printf("FAIL %d\n", rc);
        return 1;
    }
    if (strcmp(argv[1], "fee") == 0 && argc >= 4) {
        printf("%" PRId64 "\n",
               lin_fee(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "feerate") == 0 && argc >= 4) {
        printf("%" PRId64 "\n",
               lin_feerate(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "bounded") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_bounded(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "rust-fee") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               rust_fee(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
