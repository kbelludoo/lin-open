/*
 * Independent C11 oracle for go-ethereum makeGasLog / LOG0-LOG4.
 *
 * Two implementations:
 *   1. Geth uint64: exec = LogGas + n*LogTopicGas + size*LogDataGas
 *      (375 + n*375 + size*8). Add/mul overflow is OVERFLOW.
 *   2. LIN fail-closed i64: n outside 0..4, negatives, and wrap return 0.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: ethereum/go-ethereum v1.16.9 core/vm/gas_table.go
 * License of the algorithm: LGPL-3.0. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { LOG_GAS = 375, TOPIC_GAS = 375, DATA_GAS = 8 };

static int geth_exec(uint64_t n, uint64_t size, uint64_t memgas, uint64_t *out) {
    uint64_t topics, data, base, sum;
    if (n > UINT64_MAX / (uint64_t)TOPIC_GAS)
        return 1;
    topics = n * (uint64_t)TOPIC_GAS;
    if (size > UINT64_MAX / (uint64_t)DATA_GAS)
        return 1;
    data = size * (uint64_t)DATA_GAS;
    if ((uint64_t)LOG_GAS > UINT64_MAX - topics)
        return 1;
    base = (uint64_t)LOG_GAS + topics;
    if (base > UINT64_MAX - data)
        return 1;
    sum = base + data;
    if (memgas > UINT64_MAX - sum)
        return 1;
    *out = memgas + sum;
    return 0;
}

static int64_t lin_ok_n(int64_t n) { return n >= 0 && n <= 4; }
static int64_t lin_ok_size(int64_t size) { return size >= 0; }

static int64_t lin_data(int64_t size) {
    if (!lin_ok_size(size))
        return 0;
    if ((uint64_t)size > 1152921504606846975ULL)
        return 0;
    return size * DATA_GAS;
}

static int64_t lin_exec(int64_t n, int64_t size) {
    int64_t data, base, s;
    if (!lin_ok_n(n) || !lin_ok_size(size))
        return 0;
    data = lin_data(size);
    if (size > 0 && data == 0)
        return 0;
    base = (int64_t)LOG_GAS + n * (int64_t)TOPIC_GAS;
    s = base + data;
    if ((uint64_t)s < (uint64_t)base)
        return 0;
    return s;
}

static int64_t lin_with_mem(int64_t memgas, int64_t n, int64_t size) {
    int64_t more, s;
    if (memgas < 0)
        return 0;
    more = lin_exec(n, size);
    if (more == 0 && (!lin_ok_n(n) || !lin_ok_size(size)))
        return 0;
    if (more == 0 && size > 0)
        return 0;
    s = memgas + more;
    if ((uint64_t)s < (uint64_t)memgas)
        return 0;
    return s;
}

static int selftest(void) {
    uint64_t g;
    if (lin_exec(0, 0) != 375)
        return 1;
    if (lin_exec(0, 1) != 383)
        return 2;
    if (lin_exec(0, 32) != 631)
        return 3;
    if (lin_exec(3, 32) != 1756)
        return 4;
    if (lin_exec(4, 1024) != 10067)
        return 5;
    if (lin_exec(-1, 0) != 0)
        return 6;
    if (lin_exec(5, 0) != 0)
        return 7;
    if (lin_with_mem(100, 3, 32) != 1856)
        return 8;
    if (geth_exec(3, 32, 0, &g) != 0 || g != 1756)
        return 9;
    if (geth_exec(0, 0, 0, &g) != 0 || g != 375)
        return 10;
    if (lin_exec(4, 0) != 1875)
        return 11;
    return 0;
}

int main(int argc, char **argv) {
    uint64_t g;
    int rc;
    if (argc < 2) {
        fprintf(stderr,
                "usage: geth_gaslog_c11 selftest|exec n size|with mem n size|"
                "geth-exec n size|geth-with mem n size\n");
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
    if (strcmp(argv[1], "exec") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", lin_exec(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "with") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               lin_with_mem(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10),
                            strtoll(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "geth-exec") == 0 && argc >= 4) {
        rc = geth_exec(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), 0, &g);
        if (rc != 0) {
            puts("OVERFLOW");
            return 0;
        }
        printf("%" PRIu64 "\n", g);
        return 0;
    }
    if (strcmp(argv[1], "geth-with") == 0 && argc >= 5) {
        rc = geth_exec(strtoull(argv[3], NULL, 10), strtoull(argv[4], NULL, 10),
                       strtoull(argv[2], NULL, 10), &g);
        if (rc != 0) {
            puts("OVERFLOW");
            return 0;
        }
        printf("%" PRIu64 "\n", g);
        return 0;
    }
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
