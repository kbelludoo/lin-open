/*
 * Independent C11 oracle for Bitcoin Core v27.1 GetDustThreshold / IsDust.
 *
 * Reconstructs the integer policy (CompactSize + 8-byte nValue + 148/67
 * spend overhead + integer-ceil GetFee) and, on dust-scale operands, checks
 * it against std::ceil-equivalent IEEE (math.h ceil of double).
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm origin: bitcoin/bitcoin (MIT) tag v27.1.
 */
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DUST_RELAY_TX_FEE 3000
#define DEFAULT_MIN_RELAY_TX_FEE 1000
#define WITNESS_SCALE_FACTOR 4

static int64_t overflow_mul(int64_t a, int64_t b) {
    int64_t p;
    if (a < 0 || b < 0) return -1;
    if (a == 0 || b == 0) return 0;
    p = a * b;
    if (p < 0) return -1;
    if (p / a != b) return -1;
    return p;
}

static int64_t ceil_div(int64_t n, int64_t d) {
    int64_t q, r;
    if (d <= 0 || n < 0) return -1;
    if (n == 0) return 0;
    q = n / d;
    r = n - (q * d);
    return (r == 0) ? q : (q + 1);
}

static int64_t get_fee(int64_t sat_per_kvb, int64_t nbytes) {
    int64_t num, fee;
    if (sat_per_kvb < 0 || nbytes < 0) return -1;
    if (nbytes == 0) return 0;
    num = overflow_mul(sat_per_kvb, nbytes);
    if (num < 0) return -1;
    fee = ceil_div(num, 1000);
    if (fee < 0) return -1;
    if (fee == 0 && sat_per_kvb > 0) return 1;
    return fee;
}

/* Core: std::ceil(nSatoshisPerK * nSize / 1000.0) on the promoted double. */
static int64_t get_fee_ieee(int64_t sat_per_kvb, int64_t nbytes) {
    double x;
    int64_t fee;
    if (sat_per_kvb < 0 || nbytes < 0) return -1;
    if (nbytes == 0) return 0;
    x = ((double)sat_per_kvb * (double)nbytes) / 1000.0;
    fee = (int64_t)ceil(x);
    if (fee == 0 && nbytes != 0 && sat_per_kvb > 0) return 1;
    return fee;
}

static int64_t compact_size(int64_t n) {
    if (n < 0) return -1;
    if (n < 253) return 1;
    if (n <= 65535) return 3;
    if (n <= (int64_t)4294967295LL) return 5;
    return 9;
}

static int64_t txout_size(int64_t script_len) {
    int64_t cs;
    if (script_len < 0) return -1;
    cs = compact_size(script_len);
    if (cs < 0) return -1;
    return 8 + cs + script_len;
}

static int64_t spend_overhead(int is_witness) {
    if (is_witness < 0) return -1;
    if (is_witness == 0) return 32 + 4 + 1 + 107 + 4;
    return 32 + 4 + 1 + (107 / WITNESS_SCALE_FACTOR) + 4;
}

static int64_t dust_nsize(int64_t script_len, int is_witness, int is_unspendable) {
    int64_t out_sz, oh;
    if (is_unspendable) return 0;
    out_sz = txout_size(script_len);
    if (out_sz < 0) return -1;
    oh = spend_overhead(is_witness);
    if (oh < 0) return -1;
    return out_sz + oh;
}

static int64_t get_dust_threshold(int64_t script_len, int is_witness,
                                  int is_unspendable, int64_t sat_per_kvb) {
    int64_t nsz;
    if (is_unspendable) return 0;
    nsz = dust_nsize(script_len, is_witness, 0);
    if (nsz < 0) return -1;
    return get_fee(sat_per_kvb, nsz);
}

static int64_t is_dust(int64_t nvalue, int64_t script_len, int is_witness,
                       int is_unspendable, int64_t sat_per_kvb) {
    int64_t thr = get_dust_threshold(script_len, is_witness, is_unspendable, sat_per_kvb);
    if (thr < 0) return 0;
    return nvalue < thr ? 1 : 0;
}

static int selftest(void) {
    int64_t sl, rate, nsz, a, b;
    if (spend_overhead(0) != 148) return 1;
    if (spend_overhead(1) != 67) return 2;
    if (txout_size(25) != 34 || txout_size(22) != 31) return 3;
    if (txout_size(34) != 43 || txout_size(23) != 32) return 4;
    if (get_dust_threshold(25, 0, 0, DUST_RELAY_TX_FEE) != 546) return 5;
    if (get_dust_threshold(22, 1, 0, DUST_RELAY_TX_FEE) != 294) return 6;
    if (get_dust_threshold(34, 1, 0, DUST_RELAY_TX_FEE) != 330) return 7;
    if (get_dust_threshold(23, 0, 0, DUST_RELAY_TX_FEE) != 540) return 8;
    if (is_dust(545, 25, 0, 0, 3000) != 1) return 9;
    if (is_dust(546, 25, 0, 0, 3000) != 0) return 10;
    if (get_dust_threshold(25, 0, 1, 3000) != 0) return 11;
    if (is_dust(1, 25, 0, 1, 3000) != 0) return 12;
    if (get_fee(DEFAULT_MIN_RELAY_TX_FEE, 200) != 200) return 13;
    for (sl = 0; sl <= 80; sl++) {
        for (rate = 1; rate <= 4000; rate += 137) {
            nsz = dust_nsize(sl, (int)(sl & 1), 0);
            a = get_fee(rate, nsz);
            b = get_fee_ieee(rate, nsz);
            if (a != b) return 14;
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    int64_t v;
    if (argc < 2) {
        fprintf(stderr, "usage: bitcoin_core_dust_c11 selftest|overhead|txout|nsize|fee|thr|dust|ieee ...\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        v = selftest();
        if (v != 0) {
            printf("FAIL %" PRId64 "\n", v);
            return 1;
        }
        printf("PASS\n");
        return 0;
    }
    if (strcmp(argv[1], "overhead") == 0 && argc == 3) {
        printf("%" PRId64 "\n", spend_overhead((int)strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "txout") == 0 && argc == 3) {
        printf("%" PRId64 "\n", txout_size(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "nsize") == 0 && argc == 5) {
        printf("%" PRId64 "\n", dust_nsize(strtoll(argv[2], NULL, 10),
                                           (int)strtoll(argv[3], NULL, 10),
                                           (int)strtoll(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "fee") == 0 && argc == 4) {
        printf("%" PRId64 "\n", get_fee(strtoll(argv[2], NULL, 10),
                                        strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "ieee") == 0 && argc == 4) {
        printf("%" PRId64 "\n", get_fee_ieee(strtoll(argv[2], NULL, 10),
                                             strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "thr") == 0 && argc == 6) {
        printf("%" PRId64 "\n", get_dust_threshold(strtoll(argv[2], NULL, 10),
                                                   (int)strtoll(argv[3], NULL, 10),
                                                   (int)strtoll(argv[4], NULL, 10),
                                                   strtoll(argv[5], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "dust") == 0 && argc == 7) {
        printf("%" PRId64 "\n", is_dust(strtoll(argv[2], NULL, 10),
                                        strtoll(argv[3], NULL, 10),
                                        (int)strtoll(argv[4], NULL, 10),
                                        (int)strtoll(argv[5], NULL, 10),
                                        strtoll(argv[6], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
