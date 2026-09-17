/*
 * Independent C11 oracle for go-ethereum IntrinsicGas (uint64/i64-scale).
 *
 * Two paths:
 *   1. LIN-domain: non-negative i64 (Geth MaxGasLimit = 2^63-1), overflow
 *      fail-closes to 0 on EVERY add/mul including access-list and auth-list.
 *   2. Geth-like uint64 wrap on access-list/auth-list (as published: no check).
 *
 * Consensus between (1) and Python bigint is required before LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: ethereum/go-ethereum v1.16.9 core/state_transition.go
 * License of the algorithm: LGPL-3.0 (go-ethereum). This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX 9223372036854775807ULL
#define TX_GAS 21000ULL
#define CREATE_GAS 53000ULL
#define ZERO_GAS 4ULL
#define NZ_FRONTIER 68ULL
#define NZ_ISTANBUL 16ULL
#define INIT_WORD 2ULL
#define AL_ADDR 2400ULL
#define AL_KEY 1900ULL
#define AUTH_GAS 25000ULL

static int add_ok(uint64_t a, uint64_t b) {
    if (a > I64MAX || b > I64MAX) return 0;
    if (a > I64MAX - b) return 0;
    return 1;
}

static int mul_ok(uint64_t count, uint64_t cost) {
    if (count > I64MAX || cost > I64MAX) return 0;
    if (cost == 0) return 1;
    if (count > I64MAX / cost) return 0;
    return 1;
}

static uint64_t charge(uint64_t gas, uint64_t count, uint64_t cost) {
    uint64_t add;
    if (!mul_ok(count, cost)) return 0;
    add = count * cost;
    if (!add_ok(gas, add)) return 0;
    return gas + add;
}

static int64_t word_size(int64_t size) {
    if (size < 0) return -1;
    if ((uint64_t)size > I64MAX - 31ULL) return -1;
    return (int64_t)(((uint64_t)size + 31ULL) / 32ULL);
}

static uint64_t intrinsic(uint64_t z, uint64_t nz, uint64_t naddr, uint64_t nkeys,
                          uint64_t nauth, int create, int homestead, int eip2028,
                          int eip3860) {
    uint64_t gas, dlen, nzg, w;

    gas = (create && homestead) ? CREATE_GAS : TX_GAS;
    if (!add_ok(z, nz)) return 0;
    dlen = z + nz;
    if (dlen > 0) {
        nzg = eip2028 ? NZ_ISTANBUL : NZ_FRONTIER;
        gas = charge(gas, nz, nzg);
        if (gas == 0) return 0;
        gas = charge(gas, z, ZERO_GAS);
        if (gas == 0) return 0;
        if (create && eip3860) {
            if (dlen > I64MAX - 31ULL) return 0;
            w = (dlen + 31ULL) / 32ULL;
            gas = charge(gas, w, INIT_WORD);
            if (gas == 0) return 0;
        }
    }
    gas = charge(gas, naddr, AL_ADDR);
    if (gas == 0) return 0;
    gas = charge(gas, nkeys, AL_KEY);
    if (gas == 0) return 0;
    gas = charge(gas, nauth, AUTH_GAS);
    if (gas == 0) return 0;
    return gas;
}

/* Geth v1.16.9 access-list/auth-list path: unchecked uint64 add/mul. */
static uint64_t geth_al_unchecked(uint64_t gas, uint64_t naddr, uint64_t nkeys,
                                  uint64_t nauth) {
    gas += naddr * AL_ADDR;
    gas += nkeys * AL_KEY;
    gas += nauth * AUTH_GAS;
    return gas;
}

static int selftest(void) {
    int fail = 0;
    if (word_size(0) != 0) fail++;
    if (word_size(1) != 1) fail++;
    if (word_size(32) != 1) fail++;
    if (word_size(33) != 2) fail++;
    if (intrinsic(0, 0, 0, 0, 0, 0, 1, 1, 1) != 21000ULL) fail++;
    if (intrinsic(0, 0, 0, 0, 0, 1, 1, 1, 1) != 53000ULL) fail++;
    if (intrinsic(0, 0, 0, 0, 0, 1, 0, 0, 0) != 21000ULL) fail++;
    if (intrinsic(1, 0, 0, 0, 0, 0, 1, 1, 0) != 21004ULL) fail++;
    if (intrinsic(0, 1, 0, 0, 0, 0, 1, 0, 0) != 21068ULL) fail++;
    if (intrinsic(0, 1, 0, 0, 0, 0, 1, 1, 0) != 21016ULL) fail++;
    if (intrinsic(0, 0, 1, 0, 0, 0, 1, 1, 0) != 23400ULL) fail++;
    if (intrinsic(0, 0, 1, 1, 0, 0, 1, 1, 0) != 25300ULL) fail++;
    if (intrinsic(0, 0, 0, 0, 1, 0, 1, 1, 0) != 46000ULL) fail++;
    if (intrinsic(0, 1, 0, 0, 0, 1, 1, 1, 1) != 53018ULL) fail++;
    if (mul_ok(3843071682022824ULL, 2400ULL) != 0) fail++;
    if (charge(21000ULL, 3843071682022824ULL, 2400ULL) != 0) fail++;
    if (fail) {
        printf("FAIL selftest count=%d\n", fail);
        return 1;
    }
    printf("PASS selftest\n");
    return 0;
}

static void usage(void) {
    fprintf(stderr,
            "usage: geth_intrinsicgas_c11 selftest\n"
            "       geth_intrinsicgas_c11 word <size>\n"
            "       geth_intrinsicgas_c11 mulok <count> <cost>\n"
            "       geth_intrinsicgas_c11 intrinsic z nz naddr nkeys nauth create homestead eip2028 eip3860\n"
            "       geth_intrinsicgas_c11 geth-al gas naddr nkeys nauth\n");
}

int main(int argc, char **argv) {
    if (argc < 2) {
        usage();
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "word") == 0 && argc == 3) {
        printf("%" PRId64 "\n", word_size(atoll(argv[2])));
        return 0;
    }
    if (strcmp(argv[1], "mulok") == 0 && argc == 4) {
        printf("%d\n", mul_ok(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "intrinsic") == 0 && argc == 11) {
        printf("%" PRIu64 "\n",
               intrinsic(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                         strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                         strtoull(argv[6], NULL, 10), atoi(argv[7]), atoi(argv[8]),
                         atoi(argv[9]), atoi(argv[10])));
        return 0;
    }
    if (strcmp(argv[1], "geth-al") == 0 && argc == 6) {
        printf("%" PRIu64 "\n",
               geth_al_unchecked(strtoull(argv[2], NULL, 10),
                                 strtoull(argv[3], NULL, 10),
                                 strtoull(argv[4], NULL, 10),
                                 strtoull(argv[5], NULL, 10)));
        return 0;
    }
    usage();
    return 2;
}
