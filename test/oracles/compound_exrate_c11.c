/*
 * Independent C11 oracle for Compound CToken.exchangeRateStoredInternal
 * (uint64 scale, SCALE=1e9).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_compound_exrate.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm (CToken.exchangeRateStoredInternal + expScale):
 *   if supply == 0: return initialExchangeRate
 *   underlying = cash + borrows - reserves   (fail-closed on overflow/underflow)
 *   rate = (underlying * scale) / supply     (fail-closed if quotient > i64)
 *
 * Experimental SCALE=1e9. Solidity uint256 / getCashPrior token balance is NOT
 * implemented. Upstream Solidity is hash-pinned, not vendored. Oracle is original C11.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define I64MAX ((uint64_t)INT64_MAX)
#define SCALE 1000000000ULL
#define INITIAL 20000000ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > I64MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_rem_i128(uint64_t a, uint64_t b, uint64_t d) {
    if (d == 0) return 0;
    return (uint64_t)(((__uint128_t)a * (__uint128_t)b) % (__uint128_t)d);
}

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
            if (i < 64) q = q | (1ULL << i);
        }
    }
    if ((int64_t)q < 0) ov = 1;
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

typedef uint64_t (*md_fn)(uint64_t, uint64_t, uint64_t);

static uint64_t underlying(uint64_t cash, uint64_t borrows, uint64_t reserves) {
    uint64_t sum;
    if (cash > UINT64_MAX - borrows) return 0;
    sum = cash + borrows;
    if (sum < reserves) return 0;
    return sum - reserves;
}

static int underlying_ok(uint64_t cash, uint64_t borrows, uint64_t reserves) {
    uint64_t sum;
    if (cash > UINT64_MAX - borrows) return 0;
    sum = cash + borrows;
    return sum >= reserves;
}

static uint64_t exchange_rate(uint64_t cash, uint64_t borrows, uint64_t reserves,
                              uint64_t supply, uint64_t scale, uint64_t initial,
                              md_fn md) {
    uint64_t u;
    if (scale == 0) return 0;
    if (supply == 0) return initial;
    if (!underlying_ok(cash, borrows, reserves)) return 0;
    u = underlying(cash, borrows, reserves);
    return md(u, scale, supply);
}

static int selftest(void) {
    uint64_t e9 = SCALE;
    uint64_t init = INITIAL;
    if (exchange_rate(e9, 0, 0, e9, e9, init, muldiv_i128) != e9) return 1;
    if (exchange_rate(e9, 0, 0, e9, e9, init, muldiv_limbs) != e9) return 1;
    if (exchange_rate(e9, 100000000ULL, 0, e9, e9, init, muldiv_i128) != 1100000000ULL) return 1;
    if (exchange_rate(e9, 0, 100000000ULL, e9, e9, init, muldiv_i128) != 900000000ULL) return 1;
    if (exchange_rate(0, 0, 0, 0, e9, init, muldiv_i128) != init) return 1;
    if (exchange_rate(100, 0, 200, e9, e9, init, muldiv_i128) != 0) return 1;
    if (exchange_rate(0, e9, 0, 500000000ULL, e9, init, muldiv_i128) != 2000000000ULL) return 1;
    if (muldiv_i128(2000000000000000ULL, e9, e9) != 2000000000000000ULL) return 1;
    if (muldiv_limbs(2000000000000000ULL, e9, e9) != 2000000000000000ULL) return 1;
    if (muldiv_i128(2000000000000000ULL, e9, 1) != 0) return 1;
    if (muldiv_limbs(2000000000000000ULL, e9, 1) != 0) return 1;
    puts("PASS");
    return 0;
}

static md_fn parse_md(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) return muldiv_limbs;
    }
    return muldiv_i128;
}

static void usage(void) {
    fprintf(stderr,
            "usage: compound_exrate_c11 selftest\n"
            "       compound_exrate_c11 rate CASH BORROWS RESERVES SUPPLY SCALE INITIAL [--limbs]\n"
            "       compound_exrate_c11 muldiv A B D [--limbs]\n"
            "       compound_exrate_c11 rem A B D [--limbs]\n");
}

int main(int argc, char **argv) {
    md_fn md;
    if (argc < 2) {
        usage();
        return 2;
    }
    md = parse_md(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "rate") == 0 && argc >= 8) {
        printf("%" PRIu64 "\n",
               exchange_rate(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                             strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                             strtoull(argv[6], NULL, 10), strtoull(argv[7], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(argv[1], "rem") == 0 && argc >= 5) {
        uint64_t a = strtoull(argv[2], NULL, 10);
        uint64_t b = strtoull(argv[3], NULL, 10);
        uint64_t d = strtoull(argv[4], NULL, 10);
        if (md == muldiv_limbs) {
            uint64_t q, r;
            int ov;
            muldiv_limbs_qr(a, b, d, &q, &r, &ov);
            printf("%" PRIu64 "\n", r);
        } else {
            printf("%" PRIu64 "\n", muldiv_rem_i128(a, b, d));
        }
        return 0;
    }
    usage();
    return 2;
}
