/*
 * Independent C11 oracle for GMX V1 Vault.adjustForDecimals / tokenToUsdMin
 * (uint64 scale).
 *
 * (a*b)/d uses unsigned __int128 AND a portable 32-bit limb muldiv that
 * mirrors src/lin_gmx_dec.lin. Consensus is required before any LIN
 * comparison. This file is not linked into the LIN compiler TCB.
 *
 * Upstream: gmx-io/gmx-contracts contracts/core/Vault.sol (MIT).
 * This oracle is original C11 of the published formula, not a Solidity dump.
 * PRICE_PRECISION 1e30 does not fit signed i64; pow10 is capped at 18.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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
            else q |= (1ULL << i);
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

static uint64_t pow10_u(int n) {
    uint64_t p;
    int i;
    if (n < 0 || n > 18) return 0;
    p = 1;
    for (i = 0; i < n; i++) p *= 10ULL;
    return p;
}

static uint64_t adjust_u(uint64_t amount, int dec_div, int dec_mul, int use_limbs) {
    uint64_t pm = pow10_u(dec_mul);
    uint64_t pd = pow10_u(dec_div);
    if (pm == 0 || pd == 0) return 0;
    if (dec_mul != 0 && pm == 1) return 0;
    if (dec_div != 0 && pd == 1) return 0;
    return use_limbs ? muldiv_limbs(amount, pm, pd) : muldiv_i128(amount, pm, pd);
}

static uint64_t token_to_usd_u(uint64_t amount, uint64_t price, int decimals, int use_limbs) {
    uint64_t pd;
    if (amount == 0) return 0;
    pd = pow10_u(decimals);
    if (pd == 0) return 0;
    return use_limbs ? muldiv_limbs(amount, price, pd) : muldiv_i128(amount, price, pd);
}

static uint64_t usd_to_token_u(uint64_t usd, uint64_t price, int decimals, int use_limbs) {
    uint64_t pm;
    if (usd == 0 || price == 0) return 0;
    pm = pow10_u(decimals);
    if (pm == 0) return 0;
    return use_limbs ? muldiv_limbs(usd, pm, price) : muldiv_i128(usd, pm, price);
}

static int64_t naive_i64_adjust(int64_t amount, int dec_div, int dec_mul) {
    uint64_t pm = pow10_u(dec_mul);
    uint64_t pd = pow10_u(dec_div);
    int64_t s;
    if (pd == 0) return 0;
    /* wrap mod 2^64 then signed-divide, matching Compiler 0 i64 wrap */
    s = (int64_t)((uint64_t)amount * pm);
    return s / (int64_t)pd;
}

static void usage(void) {
    fprintf(stderr,
            "usage: gmx_dec_c11 selftest | pow10 n | adjust amt div mul |\n"
            "  tok2usd amt price dec | usd2tok usd price dec |\n"
            "  naive amt div mul | ignore amt | as18 amt price [--limbs]\n");
}

int main(int argc, char **argv) {
    int use_limbs = 0;
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) use_limbs = 1;
    }
    if (argc < 2) {
        usage();
        return 2;
    }
    if (strcmp(argv[1], "selftest") == 0) {
        if (pow10_u(0) != 1ULL || pow10_u(6) != 1000000ULL) return 1;
        if (pow10_u(18) != 1000000000000000000ULL) return 1;
        if (pow10_u(19) != 0 || pow10_u(30) != 0) return 1;
        if (adjust_u(1000000ULL, 6, 18, 0) != 1000000000000000000ULL) return 1;
        if (adjust_u(1000000ULL, 6, 18, 1) != 1000000000000000000ULL) return 1;
        if (adjust_u(100000000ULL, 8, 18, 0) != 1000000000000000000ULL) return 1;
        if (adjust_u(1000000000000000000ULL, 18, 6, 0) != 1000000ULL) return 1;
        if (adjust_u(5000000000ULL, 6, 10, 0) != 50000000000000ULL) return 1;
        if (adjust_u(5000000000ULL, 6, 10, 1) != 50000000000000ULL) return 1;
        if (naive_i64_adjust(5000000000LL, 6, 10) == 50000000000000LL) return 1;
        if (token_to_usd_u(0, 100000000ULL, 6, 0) != 0) return 1;
        if (token_to_usd_u(100000000ULL, 4000000000000ULL, 8, 0) != 4000000000000ULL) return 1;
        if (token_to_usd_u(1000000ULL, 100000000ULL, 6, 0) != 100000000ULL) return 1;
        if (token_to_usd_u(1000000ULL, 100000000ULL, 6, 1) != 100000000ULL) return 1;
        if (muldiv_i128(1000000ULL, 100000000ULL, 1000000000000000000ULL) != 0) return 1;
        if (usd_to_token_u(4000000000000ULL, 4000000000000ULL, 8, 0) != 100000000ULL) return 1;
        if (adjust_u(1000000ULL, 6, 30, 0) != 0) return 1;
        if (muldiv_i128(100, 200, 50) != 400) return 1;
        if (muldiv_limbs(100, 200, 50) != 400) return 1;
        if (muldiv_rem_i128(7, 9, 2) != 1) return 1;
        printf("PASS\n");
        return 0;
    }
    if (strcmp(argv[1], "pow10") == 0 && argc >= 3) {
        printf("%" PRIu64 "\n", pow10_u(atoi(argv[2])));
        return 0;
    }
    if (strcmp(argv[1], "adjust") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               adjust_u((uint64_t)atoll(argv[2]), atoi(argv[3]), atoi(argv[4]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "tok2usd") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               token_to_usd_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                              atoi(argv[4]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "usd2tok") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               usd_to_token_u((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                              atoi(argv[4]), use_limbs));
        return 0;
    }
    if (strcmp(argv[1], "naive") == 0 && argc >= 5) {
        printf("%" PRId64 "\n",
               naive_i64_adjust(atoll(argv[2]), atoi(argv[3]), atoi(argv[4])));
        return 0;
    }
    if (strcmp(argv[1], "ignore") == 0 && argc >= 3) {
        printf("%" PRId64 "\n", (int64_t)atoll(argv[2]));
        return 0;
    }
    if (strcmp(argv[1], "as18") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               muldiv_i128((uint64_t)atoll(argv[2]), (uint64_t)atoll(argv[3]),
                           1000000000000000000ULL));
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        uint64_t a = (uint64_t)atoll(argv[2]);
        uint64_t b = (uint64_t)atoll(argv[3]);
        uint64_t d = (uint64_t)atoll(argv[4]);
        printf("%" PRIu64 "\n", use_limbs ? muldiv_limbs(a, b, d) : muldiv_i128(a, b, d));
        return 0;
    }
    usage();
    return 2;
}
