/*
 * Independent C11 oracle for Compound CToken exchangeRateStoredInternal
 * (uint64 scale).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_compound_exchange_rate.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream algorithm: compound-finance/compound-protocol
 * contracts/CToken.sol exchangeRateStoredInternal (BSD-3-Clause).
 * This oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define EXP_SCALE 1000000000000000000ULL

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_rem_i128(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)a * (__uint128_t)b) % (__uint128_t)d);
}

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d,
                            uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo;
    uint64_t bit, ge, need_borrow;
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
            if (i < 64) q = q | (1ULL << i);
        }
    }
    *q_out = ov ? 0 : q;
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t muldiv_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return q;
}

static uint64_t muldiv_rem_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    return r;
}

static int underlying_ok(uint64_t cash, uint64_t borrows, uint64_t reserves) {
    uint64_t sum;
    if (cash > UINT64_MAX - borrows) return 0;
    sum = cash + borrows;
    if (sum < reserves) return 0;
    return 1;
}

static uint64_t underlying(uint64_t cash, uint64_t borrows, uint64_t reserves) {
    if (!underlying_ok(cash, borrows, reserves)) return 0;
    return (cash + borrows) - reserves;
}

static uint64_t exchange_rate(uint64_t cash, uint64_t borrows, uint64_t reserves,
                              uint64_t total_supply, uint64_t initial_rate,
                              uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    if (total_supply == 0) return initial_rate;
    if (!underlying_ok(cash, borrows, reserves)) return 0;
    return md(underlying(cash, borrows, reserves), EXP_SCALE, total_supply);
}

static int rate_ok(uint64_t cash, uint64_t borrows, uint64_t reserves,
                   uint64_t total_supply) {
    if (total_supply == 0) return 1;
    return underlying_ok(cash, borrows, reserves);
}

static int selftest(void) {
    uint64_t q1, q2, r1, r2, e1, e2;
    int ov;
    const uint64_t init = 200000000000000000ULL;

    q1 = muldiv_i128(100, 200, 50);
    q2 = muldiv_limbs(100, 200, 50);
    if (q1 != 400 || q1 != q2) return 1;
    r1 = muldiv_rem_i128(7, 9, 2);
    r2 = muldiv_rem_limbs(7, 9, 2);
    if (r1 != 1 || r1 != r2) return 2;
    q1 = muldiv_i128(EXP_SCALE, EXP_SCALE, EXP_SCALE);
    q2 = muldiv_limbs(EXP_SCALE, EXP_SCALE, EXP_SCALE);
    if (q1 != EXP_SCALE || q1 != q2) return 3;
    q1 = muldiv_i128(EXP_SCALE, EXP_SCALE, 1);
    q2 = muldiv_limbs(EXP_SCALE, EXP_SCALE, 1);
    if (q1 != 0 || q1 != q2) return 4;
    e1 = exchange_rate(0, 0, 0, 0, init, muldiv_i128);
    e2 = exchange_rate(0, 0, 0, 0, init, muldiv_limbs);
    if (e1 != init || e1 != e2) return 5;
    e1 = exchange_rate(1000, 0, 0, 1000, init, muldiv_i128);
    e2 = exchange_rate(1000, 0, 0, 1000, init, muldiv_limbs);
    if (e1 != EXP_SCALE || e1 != e2) return 6;
    e1 = exchange_rate(1000, 1000, 0, 1000, init, muldiv_i128);
    e2 = exchange_rate(1000, 1000, 0, 1000, init, muldiv_limbs);
    if (e1 != 2 * EXP_SCALE || e1 != e2) return 7;
    e1 = exchange_rate(1, 1, 3, 1, init, muldiv_i128);
    e2 = exchange_rate(1, 1, 3, 1, init, muldiv_limbs);
    if (e1 != 0 || e1 != e2 || rate_ok(1, 1, 3, 1) != 0) return 8;
    muldiv_limbs_qr(100, 200, 50, &q1, &r1, &ov);
    if (ov || q1 != 400 || r1 != 0) return 9;
    (void)q2;
    return 0;
}

static uint64_t parse_u64(const char *s) {
    char *end = NULL;
    unsigned long long v = strtoull(s, &end, 10);
    if (end == s || (end && *end != '\0')) {
        fprintf(stderr, "bad u64: %s\n", s);
        exit(2);
    }
    return (uint64_t)v;
}

static int use_limbs(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    uint64_t (*md)(uint64_t, uint64_t, uint64_t);
    int limbs;

    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldiv a b d | rem a b d | "
                "under cash borrows reserves | rate cash borrows reserves supply init "
                "[--limbs]\n",
                argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        int rc = selftest();
        if (rc == 0) {
            puts("PASS");
            return 0;
        }
        printf("FAIL %d\n", rc);
        return 1;
    }
    limbs = use_limbs(argc, argv);
    md = limbs ? muldiv_limbs : muldiv_i128;
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n", md(parse_u64(argv[2]), parse_u64(argv[3]), parse_u64(argv[4])));
        return 0;
    }
    if (strcmp(argv[1], "rem") == 0 && argc >= 5) {
        uint64_t a = parse_u64(argv[2]), b = parse_u64(argv[3]), d = parse_u64(argv[4]);
        printf("%" PRIu64 "\n", limbs ? muldiv_rem_limbs(a, b, d) : muldiv_rem_i128(a, b, d));
        return 0;
    }
    if (strcmp(argv[1], "under") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               underlying(parse_u64(argv[2]), parse_u64(argv[3]), parse_u64(argv[4])));
        return 0;
    }
    if (strcmp(argv[1], "ok") == 0 && argc >= 6) {
        printf("%d\n",
               rate_ok(parse_u64(argv[2]), parse_u64(argv[3]), parse_u64(argv[4]),
                       parse_u64(argv[5])));
        return 0;
    }
    if (strcmp(argv[1], "rate") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               exchange_rate(parse_u64(argv[2]), parse_u64(argv[3]), parse_u64(argv[4]),
                             parse_u64(argv[5]), parse_u64(argv[6]), md));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
