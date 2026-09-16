/*
 * Independent C11 oracle for rust-bitcoin Amount::div_by_fee_rate_ceil
 * (CC0-1.0 algorithm).
 *
 * FeeRate inner unit is sat/MvB. rust-bitcoin:
 *   rate_kwu = sat_mvb.div_ceil(4000)
 *   wu_ceil  = (sats * 1000).div_ceil(rate_kwu)
 *
 * Two ceil implementations:
 *   1. remainder (q, r=num%den; r? q+1 : q) — matches the LIN clone
 *   2. unsigned __int128 (num + den - 1) / den as a cross-check
 *
 * Option None is encoded as -1. This file is not linked into the LIN TCB.
 *
 * Upstream: rust-bitcoin/rust-bitcoin units/src/amount/unsigned.rs
 *           units/src/fee_rate/mod.rs
 * @ 1cbf4bd62ea99c558c6d8ef794edbd984a2a4684
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_MONEY (21000000LL * 100000000LL)
#define KWU_PER_MVB 4000ULL

static int64_t from_sat(int64_t sat) {
    if (sat < 0 || sat > MAX_MONEY) return -1;
    return sat;
}

static int64_t from_sat_per_kwu(int64_t sat_kwu) {
    if (sat_kwu < 0) return -1;
    if ((uint64_t)sat_kwu > (uint64_t)INT64_MAX / KWU_PER_MVB) return -1;
    return sat_kwu * (int64_t)KWU_PER_MVB;
}

static int64_t div_ceil_rem(int64_t num, int64_t den) {
    int64_t q, r, n;
    if (num < 0 || den <= 0) return -1;
    q = num / den;
    r = num - q * den;
    if (r == 0) return q;
    n = q + 1;
    if (n <= 0) return -1;
    return n;
}

static int64_t div_ceil_i128(int64_t num, int64_t den) {
    __uint128_t q;
    if (num < 0 || den <= 0) return -1;
    q = ((__uint128_t)(uint64_t)num + (__uint128_t)(uint64_t)den - 1) / (__uint128_t)(uint64_t)den;
    if (q > (uint64_t)INT64_MAX) return -1;
    return (int64_t)q;
}

static int64_t div_floor(int64_t num, int64_t den) {
    if (num < 0 || den <= 0) return -1;
    return num / den;
}

static int64_t to_kwu_ceil(int64_t sat_mvb, int i128) {
    if (sat_mvb < 0) return -1;
    if (sat_mvb == 0) return 0;
    return i128 ? div_ceil_i128(sat_mvb, (int64_t)KWU_PER_MVB)
                : div_ceil_rem(sat_mvb, (int64_t)KWU_PER_MVB);
}

static int64_t to_kwu_floor(int64_t sat_mvb) {
    if (sat_mvb < 0) return -1;
    if (sat_mvb == 0) return 0;
    return div_floor(sat_mvb, (int64_t)KWU_PER_MVB);
}

static int64_t fceil(int64_t sat, int64_t sat_mvb, int i128) {
    int64_t rate, msats;
    if (from_sat(sat) < 0) return -1;
    rate = to_kwu_ceil(sat_mvb, i128);
    if (rate <= 0) return -1;
    msats = sat * 1000;
    return i128 ? div_ceil_i128(msats, rate) : div_ceil_rem(msats, rate);
}

static int64_t ffloor(int64_t sat, int64_t sat_mvb) {
    int64_t rate, msats;
    if (from_sat(sat) < 0) return -1;
    rate = to_kwu_ceil(sat_mvb, 0);
    if (rate <= 0) return -1;
    msats = sat * 1000;
    return div_floor(msats, rate);
}

static int selftest(void) {
    int64_t mvb2 = from_sat_per_kwu(2);
    int64_t mvb3 = from_sat_per_kwu(3);
    int64_t mvb1 = from_sat_per_kwu(1);
    if (from_sat(0) != 0) return 1;
    if (from_sat(MAX_MONEY) != MAX_MONEY) return 2;
    if (from_sat(MAX_MONEY + 1) != -1) return 3;
    if (mvb2 != 8000) return 4;
    if (to_kwu_ceil(2000400, 0) != 501) return 5;
    if (to_kwu_ceil(2000400, 1) != 501) return 6;
    if (to_kwu_floor(2000400) != 500) return 7;
    if (fceil(1000, mvb2, 0) != 500000) return 8;
    if (fceil(1000, mvb2, 1) != 500000) return 9;
    if (ffloor(1000, mvb3) != 333333) return 10;
    if (fceil(1000, mvb3, 0) != 333334) return 11;
    if (fceil(1000, mvb3, 1) != 333334) return 12;
    if (fceil(1000, 0, 0) != -1) return 13;
    if (ffloor(MAX_MONEY, mvb1) != 2100000000000000000LL) return 14;
    if (div_ceil_rem(1000, 0) != -1) return 15;
    if (div_ceil_i128(10, 3) != div_ceil_rem(10, 3)) return 16;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    int i128 = 0;
    int i;
    const char *cmd;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | from_sat N | from_kwu N | kwu_ceil MVB | "
                "kwu_floor MVB | fceil SAT MVB | ffloor SAT MVB | dceil A D [--i128]\n",
                argv[0]);
        return 2;
    }
    for (i = 2; i < argc; i++) {
        if (strcmp(argv[i], "--i128") == 0) i128 = 1;
    }
    cmd = argv[1];
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "from_sat") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", from_sat(atoll(argv[2])));
        return 0;
    }
    if (strcmp(cmd, "from_kwu") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", from_sat_per_kwu(atoll(argv[2])));
        return 0;
    }
    if (strcmp(cmd, "kwu_ceil") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", to_kwu_ceil(atoll(argv[2]), i128));
        return 0;
    }
    if (strcmp(cmd, "kwu_floor") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", to_kwu_floor(atoll(argv[2])));
        return 0;
    }
    if (strcmp(cmd, "fceil") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", fceil(atoll(argv[2]), atoll(argv[3]), i128));
        return 0;
    }
    if (strcmp(cmd, "ffloor") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", ffloor(atoll(argv[2]), atoll(argv[3])));
        return 0;
    }
    if (strcmp(cmd, "dceil") == 0 && argc >= 4) {
        int64_t a = atoll(argv[2]);
        int64_t d = atoll(argv[3]);
        printf("%" PRId64 "\n", i128 ? div_ceil_i128(a, d) : div_ceil_rem(a, d));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
