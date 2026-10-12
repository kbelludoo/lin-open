/*
 * Independent C11 oracle for MakerDAO pot.rpow (uint64 / RAY'=1e9).
 * Two implementations of (a*b)/d and (a*b + d/2)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_maker_rpow.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: makerdao/dss src/pot.sol tag 1.3.0
 * Algorithm license: AGPL-3.0-or-later. This oracle is original C11 at RAY'=1e9
 * (not RAY=1e27). Kernel is binary fixed-point exponentiation, not share-rate.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAY9 1000000000ULL

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static void muldiv_limbs_qr(uint64_t a, uint64_t b, uint64_t d, int add_half,
                            uint64_t *q_out, uint64_t *r_out, int *ov_out) {
    uint64_t a0, a1, b0, b1, p0, p1, p2, p3, mid, t, lo, hi;
    uint64_t mid_carry, lo_carry, r_hi, r_lo, q, new_hi, new_lo, bit, ge, need_borrow;
    uint64_t half, nlo, nhi, add_c;
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
    if (add_half) {
        half = d / 2;
        nlo = lo + half;
        add_c = u_lt(nlo, lo) ? 1 : 0;
        lo = nlo;
        nhi = hi + add_c;
        if (add_c && u_lt(nhi, hi)) {
            *q_out = 0;
            *r_out = 0;
            *ov_out = 1;
            return;
        }
        hi = nhi;
    }
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
            if (need_borrow) r_hi -= 1;
            if (i >= 64) ov = 1;
            else q |= (1ULL << i);
        }
    }
    *q_out = ov ? 0 : q;
    *r_out = r_lo;
    *ov_out = ov;
}

static uint64_t muldiv_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static uint64_t muldiv_round_i128(uint64_t a, uint64_t b, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b + (__uint128_t)(d / 2)) / (__uint128_t)d;
    if (q > UINT64_MAX) return 0;
    return (uint64_t)q;
}

static uint64_t limbs_or_die(uint64_t a, uint64_t b, uint64_t d, int add_half) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, add_half, &q, &r, &ov);
    (void)r;
    return ov ? 0 : q;
}

static uint64_t rpow_gen(uint64_t x, uint64_t n, uint64_t base, int do_round,
                         uint64_t (*md)(uint64_t, uint64_t, uint64_t),
                         uint64_t (*mdr)(uint64_t, uint64_t, uint64_t)) {
    uint64_t z, xx;
    uint64_t (*step)(uint64_t, uint64_t, uint64_t) = do_round ? mdr : md;
    if (base == 0) return 0;
    if (x == 0) return (n == 0) ? base : 0;
    z = (n % 2 == 0) ? base : x;
    n = n / 2;
    while (n > 0) {
        xx = step(x, x, base);
        x = xx;
        if (n % 2 == 1) z = step(z, x, base);
        n = n / 2;
    }
    return z;
}

static uint64_t rpow_i128(uint64_t x, uint64_t n, uint64_t base) {
    return rpow_gen(x, n, base, 1, muldiv_i128, muldiv_round_i128);
}

static uint64_t rpow_nr_i128(uint64_t x, uint64_t n, uint64_t base) {
    return rpow_gen(x, n, base, 0, muldiv_i128, muldiv_round_i128);
}

static uint64_t md_limbs(uint64_t a, uint64_t b, uint64_t d) {
    return limbs_or_die(a, b, d, 0);
}

static uint64_t mdr_limbs(uint64_t a, uint64_t b, uint64_t d) {
    return limbs_or_die(a, b, d, 1);
}

static uint64_t rpow_limbs(uint64_t x, uint64_t n, uint64_t base) {
    return rpow_gen(x, n, base, 1, md_limbs, mdr_limbs);
}

static uint64_t rmul_i128(uint64_t x, uint64_t y) {
    return muldiv_i128(x, y, RAY9);
}

static uint64_t drip_chi(uint64_t dsr, uint64_t dt, uint64_t chi) {
    return rmul_i128(rpow_i128(dsr, dt, RAY9), chi);
}

static int64_t naive_sq_wrap(int64_t x, int64_t base) {
    return (int64_t)((uint64_t)x * (uint64_t)x) / base;
}

static int selftest(void) {
    uint64_t q, r;
    int ov;
    if (muldiv_i128(100, 200, 50) != 400) return 1;
    if (md_limbs(100, 200, 50) != 400) return 2;
    muldiv_limbs_qr(7, 9, 2, 0, &q, &r, &ov);
    if (ov || q != 31 || r != 1) return 3;
    if (muldiv_i128(1000000000000000000ULL, 1000000000000000000ULL, 1) != 0) return 4;
    if (rpow_i128(0, 0, RAY9) != RAY9) return 5;
    if (rpow_i128(0, 5, RAY9) != 0) return 6;
    if (rpow_i128(2000000000ULL, 3, RAY9) != 8000000000ULL) return 7;
    if (rpow_i128(1500000000ULL, 2, RAY9) != 2250000000ULL) return 8;
    if (rpow_i128(5000000000ULL, 2, RAY9) != 25000000000ULL) return 9;
    if (rpow_i128(3, 2, 2) != 5) return 10;
    if (rpow_nr_i128(3, 2, 2) != 4) return 11;
    if (rpow_i128(1050000000ULL, 2, RAY9) != 1102500000ULL) return 12;
    if (rpow_i128(1000001000ULL, 1000, RAY9) != 1001000482ULL) return 13;
    if (naive_sq_wrap(5000000000LL, (int64_t)RAY9) != 6553255926LL) return 14;
    if (drip_chi(1050000000ULL, 2, 2000000000ULL) != 2205000000ULL) return 15;
    if (rpow_i128(0, 0, RAY9) != rpow_limbs(0, 0, RAY9)) return 16;
    if (rpow_i128(5000000000ULL, 2, RAY9) != rpow_limbs(5000000000ULL, 2, RAY9)) return 17;
    if (rpow_i128(1000001000ULL, 1000, RAY9) != rpow_limbs(1000001000ULL, 1000, RAY9)) return 18;
    fprintf(stdout, "PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t a, b, c, out;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldiv a b d | round a b d | rpow x n base | "
                "noround x n base | wrap x base | drip dsr dt chi | rmul x y\n",
                argv[0]);
        return 2;
    }
    kind = argv[1];
    if (strcmp(kind, "selftest") == 0) return selftest();
    if (strcmp(kind, "muldiv") == 0 && argc >= 5) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        out = (argc >= 6 && strcmp(argv[5], "--limbs") == 0) ? md_limbs(a, b, c)
                                                            : muldiv_i128(a, b, c);
        printf("%" PRIu64 "\n", out);
        return 0;
    }
    if (strcmp(kind, "round") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               muldiv_round_i128(strtoull(argv[2], NULL, 10),
                                 strtoull(argv[3], NULL, 10),
                                 strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "rpow") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               rpow_i128(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                         strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "noround") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               rpow_nr_i128(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                            strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "wrap") == 0 && argc >= 4) {
        printf("%" PRId64 "\n",
               naive_sq_wrap(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "drip") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               drip_chi(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        strtoull(argv[4], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "rmul") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               rmul_i128(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10)));
        return 0;
    }
    fprintf(stderr, "bad args\n");
    return 2;
}
