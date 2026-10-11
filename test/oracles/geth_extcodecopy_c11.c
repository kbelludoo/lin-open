/*
 * Independent C11 oracle for go-ethereum gasExtCodeCopyEIP2929.
 *
 * Dynamic gas (Cmem omitted): CopyGas*((size+31)/32) + 2500 if cold.
 * Jump-table constantGas WarmStorageReadCostEIP2929=100 is not in the fn.
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: ethereum/go-ethereum v1.16.9 core/vm/operations_acl.go
 * License of the algorithm: LGPL-3.0. This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    COPY_GAS = 3,
    WARM = 100,
    COLD = 2600,
    SURCHARGE = 2500
};

static int ok_size(int64_t size) { return size >= 0; }
static int ok_flag(int64_t v) { return v == 0 || v == 1; }

static int64_t lin_words(int64_t size) {
    if (!ok_size(size))
        return 0;
    return (size + 31) / 32;
}

static int64_t lin_copy(int64_t size) {
    if (!ok_size(size))
        return 0;
    return COPY_GAS * lin_words(size);
}

static int64_t lin_surcharge(int64_t is_cold) {
    if (!ok_flag(is_cold))
        return 0;
    return is_cold ? SURCHARGE : 0;
}

static int64_t lin_dynamic(int64_t size, int64_t is_cold) {
    int64_t copy;
    int64_t extra;
    int64_t s;
    if (!ok_size(size) || !ok_flag(is_cold))
        return 0;
    copy = lin_copy(size);
    extra = lin_surcharge(is_cold);
    s = copy + extra;
    if ((uint64_t)s < (uint64_t)copy)
        return 0;
    return s;
}

static int64_t lin_total(int64_t size, int64_t is_cold) {
    int64_t d;
    int64_t s;
    if (!ok_size(size) || !ok_flag(is_cold))
        return 0;
    d = lin_dynamic(size, is_cold);
    s = WARM + d;
    if ((uint64_t)s < (uint64_t)d)
        return 0;
    return s;
}

static int selftest(void) {
    if (lin_copy(0) != 0)
        return 1;
    if (lin_copy(1) != 3)
        return 2;
    if (lin_copy(32) != 3)
        return 3;
    if (lin_copy(33) != 6)
        return 4;
    if (lin_copy(1024) != 96)
        return 5;
    if (lin_dynamic(0, 0) != 0)
        return 6;
    if (lin_dynamic(0, 1) != 2500)
        return 7;
    if (lin_dynamic(1, 1) != 2503)
        return 8;
    if (lin_dynamic(1024, 1) != 2596)
        return 9;
    if (lin_total(0, 0) != 100)
        return 10;
    if (lin_total(0, 1) != 2600)
        return 11;
    if (lin_total(1024, 1) != 2696)
        return 12;
    if (lin_dynamic(-1, 0) != 0)
        return 13;
    if (lin_dynamic(32, 2) != 0)
        return 14;
    if (lin_surcharge(1) != 2500)
        return 15;
    return 0;
}

int main(int argc, char **argv) {
    int rc;
    if (argc < 2) {
        fprintf(stderr,
                "usage: geth_extcodecopy_c11 selftest|copy s|surcharge c|"
                "dynamic s c|total s c|delta s|words s\n");
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
    if (strcmp(argv[1], "copy") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_copy(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "words") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_words(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "surcharge") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", lin_surcharge(strtoll(argv[2], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "delta") == 0 && argc >= 3) {
        int64_t size = strtoll(argv[2], NULL, 10);
        printf("%" PRId64 "\n", lin_dynamic(size, 1) - lin_dynamic(size, 0));
        return 0;
    }
    if (strcmp(argv[1], "dynamic") == 0 && argc >= 4) {
        printf("%" PRId64 "\n",
               lin_dynamic(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "total") == 0 && argc >= 4) {
        printf("%" PRId64 "\n",
               lin_total(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "unknown op %s\n", argv[1]);
    return 2;
}
