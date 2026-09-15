/*
 * Independent C11 oracle: Bitcoin Core v27.1 GetFee (IEEE) vs integer ceil.
 *
 * Two implementations:
 *   1. core_get_fee_double — same formula as CFeeRate::GetFee (std::ceil)
 *   2. integer path — bitcoin_getfee_integer.c (mirrors src/lin_bitcoin_core_getfee.lin)
 *
 * This file is not linked into the LIN compiler TCB.
 * Upstream algorithm: bitcoin/bitcoin v27.1 MIT.
 */
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../fixtures/external_proof/bitcoin_getfee_integer.c"

static int64_t core_get_fee_double(int64_t sat_per_kvb, int64_t n_size) {
    double n_fee;
    int64_t fee;
    if (n_size < 0) {
        return -1;
    }
    n_fee = (double)sat_per_kvb * (double)n_size / 1000.0;
    fee = (int64_t)ceil(n_fee);
    if (fee == 0 && n_size != 0) {
        if (sat_per_kvb > 0) {
            fee = 1;
        }
        if (sat_per_kvb < 0) {
            fee = -1;
        }
    }
    return fee;
}

static int wallet_scale_double_eq_int(void) {
    int64_t rate;
    int64_t size;
    int64_t d;
    int64_t i;
    for (rate = 0; rate <= 4000; rate++) {
        for (size = 0; size <= 400; size++) {
            d = core_get_fee_double(rate, size);
            i = btc_get_fee(rate, size);
            if (d != i) {
                printf("DOUBLE-NE-INT rate=%" PRId64 " size=%" PRId64 " d=%" PRId64 " i=%" PRId64 "\n",
                       rate, size, d, i);
                return 0;
            }
        }
    }
    return 1;
}

static void usage(void) {
    fprintf(stderr,
            "usage: bitcoin_core_getfee_c11 selftest\n"
            "       bitcoin_core_getfee_c11 getfee <sat_kvb> <vbytes>\n"
            "       bitcoin_core_getfee_c11 core_double <sat_kvb> <vbytes>\n"
            "       bitcoin_core_getfee_c11 vsize <wu>\n"
            "       bitcoin_core_getfee_c11 native <sat_kwu> <wu>\n"
            "       bitcoin_core_getfee_c11 core_weight <sat_kvb> <wu>\n"
            "       bitcoin_core_getfee_c11 gap <sat_kwu> <wu>\n"
            "       bitcoin_core_getfee_c11 fromfee <fee> <vbytes>\n"
            "       bitcoin_core_getfee_c11 gate\n");
}

int main(int argc, char **argv) {
    int64_t a;
    int64_t b;
    int64_t r;
    if (argc < 2) {
        usage();
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        r = btc_getfee_gate();
        if (r != 1) {
            printf("GATE-FAIL %" PRId64 "\n", r);
            return 1;
        }
        if (!wallet_scale_double_eq_int()) {
            printf("FAIL wallet-scale double vs integer\n");
            return 1;
        }
        printf("PASS gate=1 double_eq_int wallet-scale 0..4000 x 0..400\n");
        printf("DIVERGE wu=381 sat_kwu=864 core=%" PRId64 " native=%" PRId64 " gap=%" PRId64 "\n",
               btc_get_fee_from_weight(3456, 381),
               btc_fee_weight_native(864, 381),
               btc_gap_vsize_vs_weight(864, 381));
        printf("DIVERGE wu=381 sat_vb=100 core=%" PRId64 " native=%" PRId64 " gap=%" PRId64 "\n",
               btc_get_fee_from_weight(100000, 381),
               btc_fee_weight_native(25000, 381),
               btc_gap_vsize_vs_weight(25000, 381));
        printf("DOUBLE-ON-GAP-VEC core96=%" PRId64 " int96=%" PRId64 "\n",
               core_get_fee_double(3456, 96), btc_get_fee(3456, 96));
        return 0;
    }
    if (strcmp(argv[1], "gate") == 0) {
        printf("%" PRId64 "\n", btc_getfee_gate());
        return btc_getfee_gate() == 1 ? 0 : 1;
    }
    if (argc < 3) {
        usage();
        return 2;
    }
    a = (int64_t)strtoll(argv[2], NULL, 10);
    b = (argc >= 4) ? (int64_t)strtoll(argv[3], NULL, 10) : 0;
    if (strcmp(argv[1], "getfee") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", btc_get_fee(a, b));
        return 0;
    }
    if (strcmp(argv[1], "core_double") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", core_get_fee_double(a, b));
        return 0;
    }
    if (strcmp(argv[1], "vsize") == 0) {
        printf("%" PRId64 "\n", btc_vsize_from_weight(a));
        return 0;
    }
    if (strcmp(argv[1], "native") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", btc_fee_weight_native(a, b));
        return 0;
    }
    if (strcmp(argv[1], "core_weight") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", btc_get_fee_from_weight(a, b));
        return 0;
    }
    if (strcmp(argv[1], "gap") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", btc_gap_vsize_vs_weight(a, b));
        return 0;
    }
    if (strcmp(argv[1], "fromfee") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", btc_feerate_from_fee(a, b));
        return 0;
    }
    usage();
    return 2;
}
