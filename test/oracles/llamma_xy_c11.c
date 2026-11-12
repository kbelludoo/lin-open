/*
 * Independent C11 oracle for Curve LLAMMA get_xy_up / get_y_up / get_x_down
 * (uint64 scale, one band, SCALE=1e9 standing in for WAD=1e18).
 *
 * Two implementations of (a*b+add)/d:
 *   1. GCC/Clang unsigned __int128
 *   2. Portable 32-bit limbs matching src/lin_llamma_xy.lin
 *
 * Consensus between (1) and (2) is required before any LIN comparison.
 * This file is not linked into the LIN compiler TCB.
 *
 * Algorithm: published LLAMMA single-band adiabatic conversion.
 * Inv=(f+x)*(g+y) is not materialized; 128-bit muldiv(fx,gy,den) fail-closes
 * if the quotient exceeds i64. Upstream Curve.Fi AMM.vy is all-rights-reserved
 * / informational-only, so this oracle is original C11 and does not vendor
 * the Vyper source.
 *
 * Experimental uint64. Not mainnet uint256 / WAD=1e18 / multi-tick user
 * positions / p_oracle storage / bands_x[n].
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SCALE 1000000000ULL
#define DEAD_SHARES 1000ULL
#define I64MAX ((uint64_t)INT64_MAX)

static int u_lt(uint64_t a, uint64_t b) { return a < b; }

static uint64_t muldiv_add_i128(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    __uint128_t q;
    if (d == 0) return 0;
    q = ((__uint128_t)a * (__uint128_t)b + (__uint128_t)add) / (__uint128_t)d;
    if (q > I64MAX) return 0;
    return (uint64_t)q;
}

static void muldiv_add_limbs(uint64_t a, uint64_t b, uint64_t add, uint64_t d,
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
    lo = lo + add;
    if (lo < add) hi = hi + 1;
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

static uint64_t muldiv_add_limbs_q(uint64_t a, uint64_t b, uint64_t add, uint64_t d) {
    uint64_t q, r;
    int ov;
    muldiv_add_limbs(a, b, add, d, &q, &r, &ov);
    return q;
}

typedef uint64_t (*mdadd_fn)(uint64_t, uint64_t, uint64_t, uint64_t);

static uint64_t md(mdadd_fn f, uint64_t a, uint64_t b, uint64_t d) {
    return f(a, b, 0, d);
}

static uint64_t sub0(uint64_t a, uint64_t b) { return a < b ? 0 : a - b; }

static uint64_t isqrt(uint64_t n) {
    uint64_t x, y;
    int iter, done;
    if (n == 0) return 0;
    if (n < 4) return 1;
    x = n;
    y = (n / 2) + 1;
    done = 0;
    for (iter = 0; iter < 64; iter++) {
        if (!done) {
            if (y >= x) {
                done = 1;
            } else {
                x = y;
                if (x == 0) return 0;
                y = (x + (n / x)) / 2;
            }
        }
    }
    return x;
}

static uint64_t sqrt_band_ratio(uint64_t amp, mdadd_fn f) {
    uint64_t num, rad;
    if (amp <= 1) return 0;
    num = md(f, amp, SCALE, 1);
    if (num == 0) return 0;
    rad = md(f, num, SCALE, amp - 1);
    return isqrt(rad);
}

static uint64_t p_down(uint64_t p_up, uint64_t amp, mdadd_fn f) {
    if (amp <= 1 || p_up == 0) return 0;
    return md(f, p_up, amp - 1, amp);
}

static uint64_t p_mid(uint64_t p_o, uint64_t p_up, uint64_t p_dn, mdadd_fn f) {
    uint64_t t;
    if (p_o == 0 || p_up == 0 || p_dn == 0) return 0;
    t = md(f, p_o, p_o, p_dn);
    return md(f, t, p_o, p_up);
}

static uint64_t get_y0(uint64_t x, uint64_t y, uint64_t p_o, uint64_t p_up,
                       uint64_t amp, mdadd_fn f) {
    uint64_t b = 0, po2, term, b2, four, inner, extra, dlt, s, den;
    if (p_o == 0 || p_up == 0 || amp <= 1) return 0;
    if (x != 0) {
        b = md(f, md(f, p_up, amp - 1, 1), x, p_o);
        if (b == 0) return 0;
    }
    if (y != 0) {
        po2 = md(f, p_o, p_o, p_up);
        term = md(f, md(f, amp, po2, 1), y, SCALE);
        if (b > I64MAX - term) return 0;
        b += term;
    }
    if (x > 0 && y > 0) {
        b2 = md(f, b, b, 1);
        if (b2 == 0 && b != 0) return 0;
        four = md(f, md(f, 4, amp, 1), p_o, 1);
        inner = md(f, four, y, SCALE);
        extra = md(f, inner, x, 1);
        if (b2 > I64MAX - extra) return 0;
        dlt = b2 + extra;
        s = isqrt(dlt);
        den = md(f, md(f, 2, amp, 1), p_o, 1);
        if (den == 0) return 0;
        if (b > I64MAX - s) return 0;
        return md(f, b + s, SCALE, den);
    }
    den = md(f, amp, p_o, 1);
    if (den == 0) return 0;
    return md(f, b, SCALE, den);
}

static uint64_t xy_up(uint64_t x, uint64_t y, uint64_t p_o, uint64_t p_up,
                      uint64_t amp, int use_y, mdadd_fn f) {
    uint64_t p_dn, pmid, sbr, y0, ff, g, fx, gy, yo, xo, den, sp, add;
    int pure;
    if (p_o == 0 || p_up == 0 || amp <= 1) return 0;
    if (x == 0 && y == 0) return 0;
    p_dn = p_down(p_up, amp, f);
    if (p_dn == 0) return 0;
    pmid = p_mid(p_o, p_up, p_dn, f);
    if (pmid == 0) return 0;
    sbr = sqrt_band_ratio(amp, f);
    if (sbr == 0) return 0;
    pure = (x == 0) || (y == 0);
    if (pure) {
        if (p_o > p_up) {
            yo = (y == 0) ? md(f, x, SCALE, pmid) : y;
            return use_y ? yo : md(f, yo, p_up, sbr);
        }
        if (p_o < p_dn) {
            xo = (x == 0) ? md(f, y, pmid, SCALE) : x;
            return use_y ? md(f, xo, sbr, p_up) : xo;
        }
    }
    y0 = get_y0(x, y, p_o, p_up, amp, f);
    if (y0 == 0) return 0;
    ff = md(f, md(f, md(f, amp, y0, 1), p_o, p_up), p_o, SCALE);
    g = md(f, md(f, amp - 1, y0, 1), p_up, p_o);
    if (ff == 0 || g == 0) return 0;
    if (ff > I64MAX - x) return 0;
    if (g > I64MAX - y) return 0;
    fx = ff + x;
    gy = g + y;
    if (p_o > p_up) {
        yo = sub0(md(f, fx, gy, ff), g);
        return use_y ? yo : md(f, yo, p_up, sbr);
    }
    if (p_o < p_dn) {
        xo = sub0(md(f, fx, gy, g), ff);
        return use_y ? md(f, xo, sbr, p_up) : xo;
    }
    yo = md(f, md(f, amp, y0, 1), p_o - p_dn, p_o);
    if (g > I64MAX - yo) return 0;
    den = g + yo;
    if (den == 0) return 0;
    xo = sub0(md(f, fx, gy, den), ff);
    if (use_y) {
        sp = isqrt(md(f, p_up, p_o, 1));
        if (sp == 0) return 0;
        add = md(f, xo, SCALE, sp);
        if (yo > I64MAX - add) return 0;
        return yo + add;
    }
    sp = isqrt(md(f, p_dn, p_o, 1));
    add = md(f, yo, sp, SCALE);
    if (xo > I64MAX - add) return 0;
    return xo + add;
}

static uint64_t xy_up_share(uint64_t x, uint64_t y, uint64_t p_o, uint64_t p_up,
                            uint64_t amp, int use_y, uint64_t user_share,
                            uint64_t total_share, mdadd_fn f) {
    uint64_t xy, den;
    if (user_share == 0 || total_share == 0) return 0;
    xy = xy_up(x, y, p_o, p_up, amp, use_y, f);
    if (total_share > I64MAX - DEAD_SHARES) return 0;
    den = total_share + DEAD_SHARES;
    return md(f, xy, user_share, den);
}

static int selftest(void) {
    uint64_t e9 = 1000000000ULL;
    uint64_t amp = 100;
    mdadd_fn i128 = muldiv_add_i128;
    mdadd_fn limbs = muldiv_add_limbs_q;
    if (md(i128, 100, 200, 50) != 400) return 1;
    if (md(limbs, 100, 200, 50) != 400) return 1;
    if (p_down(e9, amp, i128) != 990000000ULL) return 1;
    if (sqrt_band_ratio(amp, i128) != 1005037815ULL) return 1;
    if (sqrt_band_ratio(amp, limbs) != 1005037815ULL) return 1;
    if (xy_up(0, e9, 1100000000ULL, e9, amp, 1, i128) != e9) return 1;
    if (xy_up(0, e9, 1100000000ULL, e9, amp, 0, i128) != 994987437ULL) return 1;
    if (xy_up(0, e9, 1100000000ULL, e9, amp, 0, limbs) != 994987437ULL) return 1;
    if (xy_up(e9, 0, 900000000ULL, e9, amp, 1, i128) != 1005037815ULL) return 1;
    if (xy_up(0, e9, e9, e9, amp, 1, i128) != e9) return 1;
    if (xy_up(1000000ULL, 1000000ULL, e9, e9, amp, 1, i128) != 1995012ULL) return 1;
    if (xy_up(1000000ULL, 1000000ULL, e9, e9, amp, 1, limbs) != 1995012ULL) return 1;
    if (xy_up_share(0, e9, 1100000000ULL, e9, amp, 1, 1000000ULL, 2000000ULL, i128)
        != 499750124ULL) return 1;
    if (md(i128, 12000000000ULL, e9, 1) != 0) return 1;
    printf("PASS\n");
    return 0;
}

static mdadd_fn parse_md(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--limbs") == 0) return muldiv_add_limbs_q;
    }
    return muldiv_add_i128;
}

static void usage(void) {
    fprintf(stderr,
            "usage: llamma_xy_c11 selftest\n"
            "       llamma_xy_c11 yup X Y PO PUP AMP [--limbs]\n"
            "       llamma_xy_c11 xdown X Y PO PUP AMP [--limbs]\n"
            "       llamma_xy_c11 share X Y PO PUP AMP USE_Y US TS [--limbs]\n"
            "       llamma_xy_c11 pdown PUP AMP [--limbs]\n"
            "       llamma_xy_c11 sbr AMP [--limbs]\n"
            "       llamma_xy_c11 muldiv A B D [--limbs]\n");
}

int main(int argc, char **argv) {
    mdadd_fn f;
    if (argc < 2) {
        usage();
        return 2;
    }
    f = parse_md(argc, argv);
    if (strcmp(argv[1], "selftest") == 0) return selftest();
    if (strcmp(argv[1], "yup") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               xy_up(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                     strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                     strtoull(argv[6], NULL, 10), 1, f));
        return 0;
    }
    if (strcmp(argv[1], "xdown") == 0 && argc >= 7) {
        printf("%" PRIu64 "\n",
               xy_up(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                     strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                     strtoull(argv[6], NULL, 10), 0, f));
        return 0;
    }
    if (strcmp(argv[1], "share") == 0 && argc >= 10) {
        printf("%" PRIu64 "\n",
               xy_up_share(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                           strtoull(argv[4], NULL, 10), strtoull(argv[5], NULL, 10),
                           strtoull(argv[6], NULL, 10), (int)strtoll(argv[7], NULL, 10),
                           strtoull(argv[8], NULL, 10), strtoull(argv[9], NULL, 10), f));
        return 0;
    }
    if (strcmp(argv[1], "pdown") == 0 && argc >= 4) {
        printf("%" PRIu64 "\n",
               p_down(strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10), f));
        return 0;
    }
    if (strcmp(argv[1], "sbr") == 0 && argc >= 3) {
        printf("%" PRIu64 "\n", sqrt_band_ratio(strtoull(argv[2], NULL, 10), f));
        return 0;
    }
    if (strcmp(argv[1], "muldiv") == 0 && argc >= 5) {
        printf("%" PRIu64 "\n",
               md(f, strtoull(argv[2], NULL, 10), strtoull(argv[3], NULL, 10),
                  strtoull(argv[4], NULL, 10)));
        return 0;
    }
    usage();
    return 2;
}
