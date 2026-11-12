/*
 * Independent C11 oracle for EigenLayer StrategyBase share conversion
 * (uint64 scale, SHARES_OFFSET = BALANCE_OFFSET = 1000).
 *
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_eigen_shares.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm (StrategyBase v1.13.0, BUSL-1.1, hash-pinned not vendored):
 *   sharesToUnderlying = ((tokenBalance + OFFSET) * amountShares)
 *                        / (totalShares + OFFSET)
 *   underlyingToShares = (amountUnderlying * (totalShares + OFFSET))
 *                        / (tokenBalance + OFFSET)
 *   deposit newShares  = (amount * (priorTotalShares + OFFSET))
 *                        / (tokenBalanceAfter + OFFSET - amount)
 *
 * Experimental uint64. MAX_TOTAL_SHARES=1e38 and IERC20.balanceOf are NOT
 * implemented. Upstream Solidity is hash-pinned, not vendored.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define OFFSET 1000ULL
#define I64MAX ((uint64_t)INT64_MAX)

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

static void muldiv_limbs(uint64_t a, uint64_t b, uint64_t d,
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

static uint64_t muldiv_limbs_q(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs(a, b, d, &q, &r, &ov);
    return q;
}

typedef uint64_t (*md_fn)(uint64_t, uint64_t, uint64_t);

static uint64_t shares_to_underlying(uint64_t shares, uint64_t total, uint64_t bal, md_fn md) {
    if (total > I64MAX - OFFSET) return 0;
    if (bal > I64MAX - OFFSET) return 0;
    return md(bal + OFFSET, shares, total + OFFSET);
}

static uint64_t underlying_to_shares(uint64_t und, uint64_t total, uint64_t bal, md_fn md) {
    if (total > I64MAX - OFFSET) return 0;
    if (bal > I64MAX - OFFSET) return 0;
    return md(und, total + OFFSET, bal + OFFSET);
}

static uint64_t deposit_shares(uint64_t amount, uint64_t prior, uint64_t bal_after, md_fn md) {
    uint64_t virt_prior, q;
    if (amount == 0 || bal_after < amount) return 0;
    if (prior > I64MAX - OFFSET) return 0;
    if (bal_after > I64MAX - OFFSET) return 0;
    virt_prior = (bal_after + OFFSET) - amount;
    if (virt_prior == 0) return 0;
    q = md(amount, prior + OFFSET, virt_prior);
    return q;
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    if (shares_to_underlying(1000, 0, 0, muldiv_i128) != 1000ULL) return 1;
    if (shares_to_underlying(1000, 0, 0, muldiv_limbs_q) != 1000ULL) return 1;
    if (underlying_to_shares(1000, 0, 0, muldiv_i128) != 1000ULL) return 1;
    if (shares_to_underlying(e9, e9, e9, muldiv_i128) != e9) return 1;
    if (shares_to_underlying(e9, e9, e9, muldiv_limbs_q) != e9) return 1;
    if (shares_to_underlying(e9, e9, 1100000000ULL, muldiv_i128) != 1099999900ULL) return 1;
    if (shares_to_underlying(e9, e9, 1100000000ULL, muldiv_limbs_q) != 1099999900ULL) return 1;
    if (underlying_to_shares(1100000000ULL, e9, 1100000000ULL, muldiv_i128) != 1000000090ULL) return 1;
    if (deposit_shares(e9, 0, e9, muldiv_i128) != e9) return 1;
    if (deposit_shares(e9, 0, e9, muldiv_limbs_q) != e9) return 1;
    if (deposit_shares(100000000ULL, e9, 1200000000ULL, muldiv_i128) != 90909099ULL) return 1;
    if (deposit_shares(100000000ULL, e9, 1200000000ULL, muldiv_limbs_q) != 90909099ULL) return 1;
    if (muldiv_i128(2000000000000000ULL, e9, 1) != 0) return 1;
    if (muldiv_limbs_q(2000000000000000ULL, e9, 1) != 0) return 1;
    puts("PASS");
    return 0;
}

static md_fn parse_md(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) return muldiv_limbs_q;
    }
    return muldiv_i128;
}

static void usage(void) {
    fprintf(stderr,
            "usage: eigen_shares_c11 selftest\n"
            "       eigen_shares_c11 s2u SHARES TOTAL BAL [--limbs]\n"
            "       eigen_shares_c11 u2s UND TOTAL BAL [--limbs]\n"
            "       eigen_shares_c11 dep AMOUNT PRIOR BAL_AFTER [--limbs]\n"
            "       eigen_shares_c11 muldiv A B D [--limbs]\n");
}

int main(int argc, char **argv) {
    md_fn md;
    if (argc < 2) {
        usage();
        return 2;
    }
    md = parse_md(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "s2u") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               shares_to_underlying(strtoull(argv[2], NULL, 10),
                                    strtoull(argv[3], NULL, 10),
                                    strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "u2s") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               underlying_to_shares(strtoull(argv[2], NULL, 10),
                                    strtoull(argv[3], NULL, 10),
                                    strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "dep") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               deposit_shares(strtoull(argv[2], NULL, 10),
                              strtoull(argv[3], NULL, 10),
                              strtoull(argv[4], NULL, 10), md));
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               md(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10)));
        return 0;
    }
    (void)muldiv_rem_i128;
    usage();
    return 2;
}
