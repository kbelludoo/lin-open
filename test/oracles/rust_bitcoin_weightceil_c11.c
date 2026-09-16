/*
 * Independent C11 oracle for rust-bitcoin Amount::div_by_weight_ceil
 * (CC0-1.0 algorithm).
 *
 * Weight ceil: (sats * 4_000_000).div_ceil(wu) uses unsigned __int128 AND a
 * portable 32-bit limb clone matching lin_rust_bitcoin_weightceil.lin.
 *
 * Option None is encoded as -1. This file is not linked into the LIN TCB.
 *
 * Upstream: rust-bitcoin/rust-bitcoin units/src/amount/unsigned.rs
 * @ 1cbf4bd62ea99c558c6d8ef794edbd984a2a4684
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_MONEY (21000000LL * 100000000LL)
#define MVB_PER_WU 4000000ULL

static int64_t from_sat(int64_t sat) {
    if (sat < 0 || sat > MAX_MONEY) return -1;
    return sat;
}

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d,
                            uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge, need_borrow;
    int i, ov;

    if (d == 0) {
        *q_out = 0;
        *r_out = 0;
        *ov_out = 1;
        return;
    }
    a0 = a & 0xffffffffULL;
    a1 = a >> 32;
    b0 = b & 0xffffffffULL;
    b1 = b >> 32;
    p0 = a0 * b0;
    p1 = a0 * b1;
    p2 = a1 * b0;
    p3 = a1 * b1;
    mid = p1 + p2;
    mid_carry = (mid < p1) ? 1 : 0;
    t = (mid & 0xffffffffULL) << 32;
    lo = p0 + t;
    lo_carry = (lo < p0) ? 1 : 0;
    hi = p3 + (mid >> 32);
    hi = hi + (mid_carry << 32);
    hi = hi + lo_carry;

    r_hi = 0;
    r_lo = 0;
    q = 0;
    ov = 0;
    for (i = 127; i >= 0; i--) {
        bit = (i >= 64) ? ((hi >> (i - 64)) & 1ULL) : ((lo >> i) & 1ULL);
        new_hi = (r_hi << 1) | (r_lo >> 63);
        new_lo = (r_lo << 1) | bit;
        r_hi = new_hi;
        r_lo = new_lo;
        ge = (r_hi != 0) || (r_lo >= d);
        if (ge) {
            need_borrow = u_lt(r_lo, d);
            r_lo = r_lo - d;
            if (need_borrow) r_hi = r_hi - 1;
            if (i >= 64) ov = 1;
            else q |= (1ULL << i);
        }
    }
    *q_out = q;
    *r_out = r_lo;
    *ov_out = ov;
}

static int64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d, int want_rem) {
    __uint128_t prod, q, r;
    if (d == 0) return -1;
    prod = (__uint128_t)a * (__uint128_t)b;
    if (want_rem) {
        r = prod % (__uint128_t)d;
        return (int64_t)r;
    }
    q = prod / (__uint128_t)d;
    if (q > (uint64_t)INT64_MAX) return -1;
    return (int64_t)q;
}

static int64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d, int want_rem) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    if (d == 0) return -1;
    if (want_rem) return (int64_t)r;
    if (ov || q > (uint64_t)INT64_MAX) return -1;
    return (int64_t)q;
}

static int64_t wfloor(int64_t sat, int64_t wu, int limbs) {
    if (from_sat(sat) < 0 || wu <= 0) return -1;
    if (limbs) return muldiv_limbs((uint64_t)sat, MVB_PER_WU, (uint64_t)wu, 0);
    return muldiv_i128((uint64_t)sat, MVB_PER_WU, (uint64_t)wu, 0);
}

static int64_t wrem(int64_t sat, int64_t wu, int limbs) {
    if (from_sat(sat) < 0 || wu <= 0) return -1;
    if (limbs) return muldiv_limbs((uint64_t)sat, MVB_PER_WU, (uint64_t)wu, 1);
    return muldiv_i128((uint64_t)sat, MVB_PER_WU, (uint64_t)wu, 1);
}

static int64_t wceil(int64_t sat, int64_t wu, int limbs) {
    int64_t q, r, n;
    if (from_sat(sat) < 0 || wu <= 0) return -1;
    q = limbs ? muldiv_limbs((uint64_t)sat, MVB_PER_WU, (uint64_t)wu, 0)
              : muldiv_i128((uint64_t)sat, MVB_PER_WU, (uint64_t)wu, 0);
    r = limbs ? muldiv_limbs((uint64_t)sat, MVB_PER_WU, (uint64_t)wu, 1)
              : muldiv_i128((uint64_t)sat, MVB_PER_WU, (uint64_t)wu, 1);
    if (q < 0) return -1;
    if (r == 0) return q;
    n = q + 1;
    if (n <= 0) return -1;
    return n;
}

static int selftest(void) {
    if (from_sat(0) != 0) return 1;
    if (from_sat(MAX_MONEY) != MAX_MONEY) return 2;
    if (from_sat(MAX_MONEY + 1) != -1) return 3;
    if (wceil(1, 1000, 0) != 4000) return 4;
    if (wceil(1, 1000, 1) != 4000) return 5;
    if (wfloor(329, 381, 0) != 3454068) return 6;
    if (wceil(329, 381, 0) != 3454069) return 7;
    if (wceil(329, 381, 1) != 3454069) return 8;
    if (wceil(10, 200, 0) != 200000) return 9;
    if (wceil(10, 300, 0) != 133334) return 10;
    if (wfloor(10, 300, 0) != 133333) return 11;
    if (wrem(10, 300, 0) != 100) return 12;
    if (wceil(10, 0, 0) != -1) return 13;
    if (wceil((int64_t)MAX_MONEY, 1, 0) != -1) return 14;
    if (wceil((int64_t)MAX_MONEY, 1, 1) != -1) return 15;
    printf("PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    int limbs = 0;
    int i;
    const char *cmd;
    if (argc < 2) {
        fprintf(stderr, "usage: %s selftest | from_sat N | wfloor A W | wceil A W | wrem A W | muldiv A B D [--limbs]\n", argv[0]);
        return 2;
    }
    for (i = 2; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) limbs = 1;
    }
    cmd = argv[1];
    if (strcmp(cmd, "selftest") == 0) return selftest();
    if (strcmp(cmd, "from_sat") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", from_sat(atoll(argv[2])));
        return 0;
    }
    if (strcmp(cmd, "wfloor") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", wfloor(atoll(argv[2]), atoll(argv[3]), limbs));
        return 0;
    }
    if (strcmp(cmd, "wceil") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", wceil(atoll(argv[2]), atoll(argv[3]), limbs));
        return 0;
    }
    if (strcmp(cmd, "wrem") == 0 && argc >= 4) {
        printf("%" PRId64 "\n", wrem(atoll(argv[2]), atoll(argv[3]), limbs));
        return 0;
    }
    if (strcmp(cmd, "muldiv") == 0 && argc >= 5) {
        uint64_t a = (uint64_t)atoll(argv[2]);
        uint64_t b = (uint64_t)atoll(argv[3]);
        uint64_t d = (uint64_t)atoll(argv[4]);
        int64_t v = limbs ? muldiv_limbs(a, b, d, 0) : muldiv_i128(a, b, d, 0);
        printf("%" PRId64 "\n", v);
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
