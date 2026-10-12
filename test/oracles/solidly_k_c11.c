/*
 * Independent C11 oracle for Solidly BaseV1Pair cubic k (uint64 / WAD'=1e6).
 * Two implementations of (a*b)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_solidly_k.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Upstream: transmissions11/solidly contracts/BaseV1-core.sol
 * Algorithm license: MIT. This oracle is original C11 at WAD'=1e6 (not 1e18).
 * Kernel is x^3 y + y^3 x vs xy, not Uniswap V2, not Saddle getD, not Maker rpow.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WAD6 1000000ULL

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

static uint64_t md_limbs(uint64_t a, uint64_t b, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_limbs_qr(a, b, d, &q, &r, &ov);
    (void)r;
    return ov ? 0 : q;
}

static uint64_t k_stable(uint64_t x, uint64_t y, uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t a, b;
    if (x == 0 || y == 0) return 0;
    a = md(x, y, WAD6);
    b = md(x, x, WAD6) + md(y, y, WAD6);
    return md(a, b, WAD6);
}

static uint64_t sld_f(uint64_t x0, uint64_t y, uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t y2, y3, t1, x2, x3, t2;
    y2 = md(y, y, WAD6);
    y3 = md(y2, y, WAD6);
    t1 = md(x0, y3, WAD6);
    x2 = md(x0, x0, WAD6);
    x3 = md(x2, x0, WAD6);
    t2 = md(x3, y, WAD6);
    return t1 + t2;
}

static uint64_t sld_d(uint64_t x0, uint64_t y, uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t inner, t1, x2, x3;
    inner = md(y, y, WAD6);
    t1 = md(x0 + x0 + x0, inner, WAD6);
    x2 = md(x0, x0, WAD6);
    x3 = md(x2, x0, WAD6);
    return t1 + x3;
}

static uint64_t get_y(uint64_t x0, uint64_t xy, uint64_t y,
                     uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    int i;
    uint64_t y_prev, k, dd, dy;
    if (x0 == 0 || y == 0) return 0;
    for (i = 0; i < 16; i++) {
        y_prev = y;
        k = sld_f(x0, y, md);
        dd = sld_d(x0, y, md);
        if (dd == 0) return 0;
        if (k < xy) {
            dy = md(xy - k, WAD6, dd);
            y = y + dy;
        } else {
            dy = md(k - xy, WAD6, dd);
            if (y < dy) return 0;
            y = y - dy;
        }
        if (y > y_prev) {
            if (y - y_prev <= 1) return y;
        } else {
            if (y_prev - y <= 1) return y;
        }
    }
    return y;
}

static uint64_t apply_fee(uint64_t amount, uint64_t fee_bps,
                         uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    return amount - md(amount, fee_bps, 10000ULL);
}

static uint64_t amount_out(uint64_t ain, uint64_t rin, uint64_t rout, int stable,
                          uint64_t fee_bps, uint64_t (*md)(uint64_t, uint64_t, uint64_t)) {
    uint64_t a, xy, y, den;
    if (ain == 0 || rin == 0 || rout == 0) return 0;
    a = apply_fee(ain, fee_bps, md);
    if (a == 0) return 0;
    if (!stable) {
        den = rin + a;
        if (den == 0) return 0;
        return md(a, rout, den);
    }
    xy = k_stable(rin, rout, md);
    y = get_y(a + rin, xy, rout, md);
    if (rout < y) return 0;
    return rout - y;
}

static int64_t naive_sq_wrap(int64_t x, int64_t base) {
    return (int64_t)((uint64_t)x * (uint64_t)x) / base;
}

static int selftest(void) {
    uint64_t q, r;
    int ov;
    if (muldiv_i128(100, 200, 50) != 400) return 1;
    if (md_limbs(100, 200, 50) != 400) return 2;
    muldiv_limbs_qr(7, 9, 2, &q, &r, &ov);
    if (ov || q != 31 || r != 1) return 3;
    if (muldiv_i128(1000000000000000000ULL, 1000000000000000000ULL, 1) != 0) return 4;
    if (k_stable(WAD6, WAD6, muldiv_i128) != 2000000ULL) return 5;
    if (k_stable(WAD6, WAD6, md_limbs) != 2000000ULL) return 6;
    if (sld_f(WAD6, WAD6, muldiv_i128) != 2000000ULL) return 7;
    if (sld_d(WAD6, WAD6, muldiv_i128) != 4000000ULL) return 8;
    if (amount_out(10000, WAD6, WAD6, 0, 1, muldiv_i128) != 9900ULL) return 9;
    if (amount_out(10000, WAD6, WAD6, 1, 1, muldiv_i128) != 9997ULL) return 10;
    if (amount_out(10000, WAD6, WAD6, 1, 0, muldiv_i128) != 9999ULL) return 11;
    if (amount_out(10000, WAD6, 4000000ULL, 0, 1, muldiv_i128) != 39600ULL) return 12;
    if (amount_out(100000, WAD6, WAD6, 1, 1, muldiv_i128) != 99939ULL) return 13;
    if (amount_out(10000, 1200000ULL, 800000ULL, 1, 1, muldiv_i128) != 9827ULL) return 14;
    if (amount_out(10000, 1200000ULL, 800000ULL, 0, 1, muldiv_i128) != 6610ULL) return 15;
    if (naive_sq_wrap(5000000000LL, (int64_t)WAD6) != 6553255926290LL) return 16;
    if (muldiv_i128(5000000000ULL, 5000000000ULL, WAD6) != 25000000000000ULL) return 17;
    if (amount_out(10000, WAD6, WAD6, 1, 1, muldiv_i128) !=
        amount_out(10000, WAD6, WAD6, 1, 1, md_limbs))
        return 18;
    fprintf(stdout, "PASS\n");
    return 0;
}

int main(int argc, char **argv) {
    const char *kind;
    uint64_t a, b, c, d, e, out;
    int stable;
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s selftest | muldiv a b d | kstable x y | kvol x y | "
                "f x0 y | deriv x0 y | wrap x base | fee amt bps | "
                "out ain rin rout stable bps\n",
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
    if (strcmp(kind, "kstable") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               k_stable(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                        muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "kvol") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               muldiv_i128(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), 1));
        return 0;
    }
    if (strcmp(kind, "f") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               sld_f(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "deriv") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               sld_d(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "wrap") == 0 && argc >= 4) {
        printf("%" PRId64 "\n",
               naive_sq_wrap(strtoll(argv[2], NULL, 10), strtoll(argv[3], NULL, 10)));
        return 0;
    }
    if (strcmp(kind, "fee") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               apply_fee(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                         muldiv_i128));
        return 0;
    }
    if (strcmp(kind, "out") == 0 && argc >= 7) {
        a = strtoull(argv[2], NULL, 10);
        b = strtoull(argv[3], NULL, 10);
        c = strtoull(argv[4], NULL, 10);
        stable = (int)strtol(argv[5], NULL, 10);
        d = strtoull(argv[6], NULL, 10);
        printf("%" PRIu64 "\n", amount_out(a, b, c, stable, d, muldiv_i128));
        return 0;
    }
    (void)e;
    fprintf(stderr, "bad args\n");
    return 2;
}
