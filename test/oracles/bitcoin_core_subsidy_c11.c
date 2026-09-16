/*
 * Independent C11 oracle for Bitcoin Core GetBlockSubsidy / issuance.
 *
 * Modes:
 *   core  — C99 toward-zero division, no negative-height guard (matches Core
 *           for height >= -interval+1). interval<=0 returns INT64_MIN (UB stand-in).
 *   lin   — fail-closed: height<0 or interval<=0 or genesis<0 => 0.
 *   shift — portable guarded shift vs arithmetic loop (must agree).
 *
 * This file is not linked into the LIN compiler TCB.
 * Algorithm: MIT (Bitcoin Core). This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define COIN 100000000LL
#define MAX_MONEY (21000000LL * COIN)
#define INTERVAL 210000LL
#define GENESIS (50LL * COIN)

static int64_t shr_loop(int64_t v, int64_t n) {
    int64_t i;
    if (v < 0 || n < 0 || n >= 64) return 0;
    for (i = 0; i < n; i++) v = (int64_t)((uint64_t)v >> 1);
    return v;
}

static int64_t shr_guarded(int64_t v, int64_t n) {
    if (v < 0 || n < 0 || n >= 64) return 0;
    return (int64_t)((uint64_t)v >> (unsigned)n);
}

static int64_t subsidy_core(int64_t height, int64_t interval, int64_t genesis) {
    int64_t halvings;
    if (interval == 0) return INT64_MIN; /* Core would be UB */
    halvings = height / interval;        /* C99 toward zero */
    if (halvings >= 64) return 0;
    if (halvings < 0) return INT64_MIN;  /* Core >>= negative is UB */
    return shr_guarded(genesis, halvings);
}

static int64_t subsidy_lin(int64_t height, int64_t interval, int64_t genesis) {
    int64_t era;
    if (height < 0 || interval <= 0 || genesis < 0) return 0;
    era = height / interval;
    return shr_guarded(genesis, era);
}

static int64_t supply_all(void) {
    int64_t pos = 0, e;
    for (e = 0; e < 64; e++) pos += INTERVAL * shr_guarded(GENESIS, e);
    return pos;
}

static int selftest(void) {
    int e;
    if (subsidy_lin(0, INTERVAL, GENESIS) != 5000000000LL) return 1;
    if (subsidy_lin(210000, INTERVAL, GENESIS) != 2500000000LL) return 2;
    if (subsidy_lin(840000, INTERVAL, GENESIS) != 312500000LL) return 3;
    if (subsidy_lin(-1, INTERVAL, GENESIS) != 0) return 4;
    if (subsidy_core(-1, INTERVAL, GENESIS) != 5000000000LL) return 5;
    if (subsidy_lin(10, 0, GENESIS) != 0) return 6;
    if (subsidy_core(10, 0, GENESIS) != INT64_MIN) return 7;
    if (supply_all() != 2099999997690000LL) return 8;
    if (supply_all() >= MAX_MONEY) return 9;
    for (e = 0; e < 40; e++) {
        if (shr_loop(GENESIS, e) != shr_guarded(GENESIS, e)) return 10;
        if (shr_loop(GENESIS, e) != subsidy_lin((int64_t)e * INTERVAL, INTERVAL, GENESIS))
            return 11;
    }
    if (subsidy_core(0, INTERVAL, GENESIS) != subsidy_lin(0, INTERVAL, GENESIS)) return 12;
    return 0;
}

int main(int argc, char **argv) {
    int64_t h, interval, genesis, v;
    const char *mode;
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest | core|lin|supply HEIGHT [INTERVAL GENESIS]\n", argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        v = selftest();
        if (v != 0) {
            printf("FAIL %lld\n", (long long)v);
            return 1;
        }
        printf("PASS\n");
        return 0;
    }
    if (strcmp(argv[1], "supply") == 0) {
        printf("%lld\n", (long long)supply_all());
        return 0;
    }
    if (argc < 3) return 2;
    mode = argv[1];
    h = strtoll(argv[2], NULL, 10);
    interval = argc > 3 ? strtoll(argv[3], NULL, 10) : INTERVAL;
    genesis = argc > 4 ? strtoll(argv[4], NULL, 10) : GENESIS;
    if (strcmp(mode, "core") == 0) v = subsidy_core(h, interval, genesis);
    else if (strcmp(mode, "lin") == 0) v = subsidy_lin(h, interval, genesis);
    else return 2;
    printf("%lld\n", (long long)v);
    return 0;
}
