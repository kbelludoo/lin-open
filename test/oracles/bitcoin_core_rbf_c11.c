/*
 * Independent C11 oracle for Bitcoin Core v27.1 PaysForRBF / incremental relay.
 *
 * Three fee functions:
 *   1. integer ceil  — matches src/lin_bitcoin_core_rbf.lin (and Core on wallet-scale)
 *   2. IEEE ceil     — matches CFeeRate::GetFee std::ceil(n*size/1000.0)
 *   3. btcd trunc    — matches calcMinRequiredTxRelayFee (zero quotient → full rate)
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm license: MIT (Bitcoin Core) / ISC (btcd). Oracle is original C11.
 */
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define COIN 100000000LL
#define MAX_MONEY (21000000LL * COIN)
#define DEFAULT_INCREMENTAL_RELAY_FEE 1000LL
#define MAX_REPLACEMENT_CANDIDATES 100LL

static int64_t overflow_mul(int64_t a, int64_t b) {
    __int128 p;
    if (a < 0 || b < 0) return -1;
    p = (__int128)a * (__int128)b;
    if (p > INT64_MAX) return -1;
    return (int64_t)p;
}

static int64_t ceil_div(int64_t n, int64_t d) {
    int64_t q, r;
    if (d <= 0 || n < 0) return -1;
    if (n == 0) return 0;
    q = n / d;
    r = n - (q * d);
    return (r == 0) ? q : q + 1;
}

static int64_t get_fee_int(int64_t sat_kvb, int64_t vbytes) {
    int64_t num, fee;
    if (sat_kvb < 0 || vbytes < 0) return -1;
    if (vbytes == 0) return 0;
    num = overflow_mul(sat_kvb, vbytes);
    if (num < 0) return -1;
    fee = ceil_div(num, 1000);
    if (fee < 0) return -1;
    if (fee == 0 && sat_kvb > 0) return 1;
    return fee;
}

static int64_t get_fee_ieee(int64_t sat_kvb, int64_t vbytes) {
    int64_t fee;
    if (vbytes == 0) return 0;
    fee = (int64_t)ceil((double)sat_kvb * (double)vbytes / 1000.0);
    if (fee == 0 && vbytes != 0) {
        if (sat_kvb > 0) fee = 1;
        if (sat_kvb < 0) fee = -1;
    }
    return fee;
}

static int64_t btcd_min_fee(int64_t sat_kvb, int64_t nbytes) {
    int64_t min_fee;
    if (sat_kvb < 0 || nbytes < 0) return -1;
    min_fee = overflow_mul(nbytes, sat_kvb);
    if (min_fee < 0) return -1;
    min_fee = min_fee / 1000;
    if (min_fee == 0 && sat_kvb > 0) min_fee = sat_kvb;
    if (min_fee < 0 || min_fee > MAX_MONEY) return MAX_MONEY;
    return min_fee;
}

static int pays_for_rbf(int64_t orig, int64_t repl, int64_t vsize, int64_t rate) {
    int64_t additional, need;
    if (orig < 0 || repl < 0 || vsize < 0 || rate < 0) return -1;
    if (repl < orig) return 0;
    additional = repl - orig;
    need = get_fee_int(rate, vsize);
    if (need < 0) return -1;
    if (additional < need) return 0;
    return 1;
}

static int selftest(void) {
    int64_t k, v, a, b;
    if (get_fee_int(1000, 141) != 141) return 1;
    if (get_fee_ieee(1000, 141) != 141) return 2;
    if (get_fee_int(3, 2) != 1) return 3;
    if (get_fee_ieee(3, 2) != 1) return 4;
    if (btcd_min_fee(3, 2) != 3) return 5;
    if (pays_for_rbf(2000, 2140, 141, 1000) != 0) return 6;
    if (pays_for_rbf(2000, 2141, 141, 1000) != 1) return 7;
    if (pays_for_rbf(2000, 1999, 141, 1000) != 0) return 8;
    for (k = 0; k <= 4000; k += 17) {
        for (v = 0; v <= 400; v += 3) {
            a = get_fee_int(k, v);
            b = get_fee_ieee(k, v);
            if (a != b) return 9;
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: bitcoin_core_rbf_c11 selftest|getfee|ieee|btcd|pays|gap ARGS\n");
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        int rc = selftest();
        if (rc != 0) {
            printf("FAIL %d\n", rc);
            return 1;
        }
        printf("PASS\n");
        return 0;
    }
    if (strcmp(argv[1], "getfee") == 0 && argc == 4) {
        printf("%" PRId64 "\n", get_fee_int(atoll(argv[2]), atoll(argv[3])));
        return 0;
    }
    if (strcmp(argv[1], "ieee") == 0 && argc == 4) {
        printf("%" PRId64 "\n", get_fee_ieee(atoll(argv[2]), atoll(argv[3])));
        return 0;
    }
    if (strcmp(argv[1], "btcd") == 0 && argc == 4) {
        printf("%" PRId64 "\n", btcd_min_fee(atoll(argv[2]), atoll(argv[3])));
        return 0;
    }
    if (strcmp(argv[1], "gap") == 0 && argc == 4) {
        int64_t core = get_fee_int(atoll(argv[2]), atoll(argv[3]));
        int64_t other = btcd_min_fee(atoll(argv[2]), atoll(argv[3]));
        printf("%" PRId64 "\n", other - core);
        return 0;
    }
    if (strcmp(argv[1], "pays") == 0 && argc == 6) {
        printf("%d\n", pays_for_rbf(atoll(argv[2]), atoll(argv[3]), atoll(argv[4]), atoll(argv[5])));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
